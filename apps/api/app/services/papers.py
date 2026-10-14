"""Library: uploads, imports, listing and per-paper reads. Ownership is enforced here."""

import base64
import hashlib
import re
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser
from app.config import Settings
from app.errors import AppError, Invalid, NotFound
from app.ingest import sources
from app.ingest.fetch import TooLarge, check_url
from app.jobs import queue
from app.providers.registry import Providers
from app.repos import papers as repo
from app.services import quotas


class UnsupportedFile(AppError):
    code, status, message = "unsupported_file", 415, "Only PDF files are supported."


class NoOpenAccess(AppError):
    code, status = "not_found", 404
    message = "No open-access PDF was found for this DOI. Download it and upload the PDF instead."


def _cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode()).decode()))
    except ValueError:
        return 0


async def require_access(s: AsyncSession, user: CurrentUser, paper_id: UUID) -> dict[str, Any]:
    card = await repo.get_card(s, user.id, paper_id)
    if card is None:
        raise NotFound("Paper not found in your library.")
    return card


async def upload(
    s: AsyncSession,
    settings: Settings,
    providers: Providers,
    user: CurrentUser,
    data: bytes,
    filename: str,
    collection_id: UUID | None,
) -> dict[str, Any]:
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise TooLarge(f"PDFs up to {settings.max_upload_mb} MB are supported.")
    if not data.startswith(b"%PDF-"):
        raise UnsupportedFile()
    sha = hashlib.sha256(data).hexdigest()
    existing = await repo.find_private_by_hash(s, user.id, sha)
    if existing:
        await repo.link(s, user.id, existing["id"], collection_id)
        await s.commit()
        return {"paper_id": existing["id"], "job_id": None, "status": existing["status"]}
    await quotas.consume(s, settings, user.id, "imports")
    clean = re.sub(r"[^\w.\- ]+", "_", filename)[:200] or "paper.pdf"
    paper_id = await repo.insert_paper(
        s, owner_id=user.id, visibility="private", source="upload", source_ref=clean, sha256=sha,
        title=None,
    )  # fmt: skip
    blob_path = f"uploads/{user.id}/{paper_id}.pdf"
    await providers.blobs.put(blob_path, data, "application/pdf")
    await repo.update_paper(s, paper_id, blob_path=blob_path)
    await repo.link(s, user.id, paper_id, collection_id)
    job_id = await queue.enqueue(s, "ingest_paper", {"paper_id": str(paper_id)}, user.id, priority=2)
    await s.commit()
    return {"paper_id": paper_id, "job_id": job_id, "status": "queued"}


async def import_paper(
    s: AsyncSession,
    settings: Settings,
    user: CurrentUser,
    source: Literal["arxiv", "doi", "url"],
    value: str,
    collection_id: UUID | None,
) -> dict[str, Any]:
    contact = settings.contact_email
    arxiv_id = sources.normalize_arxiv(value) if source in ("arxiv", "url") else None
    doi = sources.normalize_doi(value) if source == "doi" else None
    if doi and doi.lower().startswith("10.48550/arxiv."):
        arxiv_id, doi = re.sub(r"^10\.48550/arxiv\.", "", doi, flags=re.I), None
    if source == "arxiv" and not arxiv_id:
        raise Invalid("That doesn't look like an arXiv id (e.g. 1706.03762).")
    if source == "doi" and not doi:
        raise Invalid("That doesn't look like a DOI (e.g. 10.1145/3292500.3330701).")

    if arxiv_id or doi:
        cached = await repo.find_public(s, arxiv_id=arxiv_id, doi=doi)
        if cached:
            await repo.link(s, user.id, cached["id"], collection_id)
            job_id = None
            if cached["status"] == "failed":
                job_id = await queue.enqueue(s, "ingest_paper", {"paper_id": str(cached["id"])}, user.id, 2)
            await s.commit()
            return {"paper_id": cached["id"], "job_id": job_id, "status": cached["status"]}

    await quotas.consume(s, settings, user.id, "imports")
    payload: dict[str, Any] = {}
    if arxiv_id:
        meta = await sources.arxiv_lookup(arxiv_id, contact)
        if meta is None:
            raise NotFound(f"arXiv has no paper {arxiv_id}.")
        paper_id = await repo.insert_paper(
            s, owner_id=None, visibility="public_cache", source="arxiv", source_ref=arxiv_id,
            sha256=f"arxiv:{arxiv_id}", title=meta.title, authors=[{"name": a} for a in meta.authors],
            year=meta.year, venue=meta.venue, abstract=meta.abstract, doi=meta.doi, arxiv_id=arxiv_id,
        )  # fmt: skip
    elif doi:
        meta = await sources.crossref_lookup(doi, contact)
        pdf = await sources.unpaywall_pdf(doi, contact)
        if not pdf:
            raise NoOpenAccess()
        payload["pdf_url"] = pdf
        paper_id = await repo.insert_paper(
            s, owner_id=None, visibility="public_cache", source="doi", source_ref=doi,
            sha256=f"doi:{doi.lower()}", title=meta.title if meta else None,
            authors=[{"name": a} for a in (meta.authors if meta else [])],
            year=meta.year if meta else None, venue=meta.venue if meta else None,
            abstract=meta.abstract if meta else None, doi=doi,
        )  # fmt: skip
    else:
        await check_url(value)
        payload["pdf_url"] = value
        paper_id = await repo.insert_paper(
            s, owner_id=user.id, visibility="private", source="url", source_ref=value[:500],
            sha256=f"url:{hashlib.sha256(value.encode()).hexdigest()}",
        )  # fmt: skip
    payload["paper_id"] = str(paper_id)
    await repo.link(s, user.id, paper_id, collection_id)
    job_id = await queue.enqueue(s, "ingest_paper", payload, user.id, priority=2)
    await s.commit()
    return {"paper_id": paper_id, "job_id": job_id, "status": "queued"}


async def list_papers(
    s: AsyncSession, user: CurrentUser, *, collection_id: UUID | None, q: str | None,
    starred: bool | None, status: str | None, limit: int, cursor: str | None,
) -> dict[str, Any]:  # fmt: skip
    offset = decode_cursor(cursor)
    rows = await repo.list_cards(
        s, user.id, collection_id=collection_id, q=q, starred=starred, status=status,
        limit=limit, offset=offset,
    )  # fmt: skip
    more = len(rows) > limit
    return {"items": rows[:limit], "next_cursor": _cursor(offset + limit) if more else None}


async def delete_paper(s: AsyncSession, providers: Providers, user: CurrentUser, paper_id: UUID) -> None:
    card = await require_access(s, user, paper_id)
    await repo.unlink(s, user.id, paper_id)
    if card["visibility"] == "private" and card["owner_id"] == user.id:
        if card["blob_path"]:
            await providers.blobs.delete(card["blob_path"])
        await repo.delete_paper(s, paper_id)
    await s.commit()


def bibtex(card: dict[str, Any], style: Literal["bibtex", "apa", "ieee"]) -> str:
    authors = [a.get("name", "") for a in card.get("authors") or [] if a.get("name")]
    title = card.get("title") or "Untitled"
    year = card.get("year") or "n.d."
    venue = card.get("venue") or ("arXiv" if card.get("arxiv_id") else "")
    if style == "apa":

        def apa_name(n: str) -> str:
            parts = n.split()
            return f"{parts[-1]}, {' '.join(p[0] + '.' for p in parts[:-1])}" if len(parts) > 1 else n

        names = [apa_name(n) for n in authors]
        who = ", ".join(names[:-1]) + (", & " if len(names) > 1 else "") + names[-1] if names else ""
        tail = (
            f" https://doi.org/{card['doi']}"
            if card.get("doi")
            else (f" https://arxiv.org/abs/{card['arxiv_id']}" if card.get("arxiv_id") else "")
        )
        return f"{who} ({year}). {title}. {venue + '.' if venue else ''}{tail}".strip()
    if style == "ieee":

        def ieee_name(n: str) -> str:
            parts = n.split()
            return " ".join([*(p[0] + "." for p in parts[:-1]), parts[-1]]) if parts else n

        names = [ieee_name(n) for n in authors]
        who = ", ".join(names[:-1]) + (", and " if len(names) > 1 else "") + names[-1] if names else ""
        return f'{who}, "{title}," {venue + ", " if venue else ""}{year}.'
    last = re.sub(r"\W", "", (authors[0].split()[-1] if authors else "paper")).lower()
    word = re.sub(r"\W", "", (title.split() or ["x"])[0]).lower()
    key = f"{last}{year}{word}"

    def esc(v: str) -> str:
        return v.replace("{", "\\{").replace("}", "\\}")

    fields = [("title", "{" + esc(title) + "}"), ("author", esc(" and ".join(authors)) or "Unknown"),
              ("year", str(year))]  # fmt: skip
    if venue:
        fields.append(("journal", esc(venue)))
    if card.get("doi"):
        fields.append(("doi", card["doi"]))
    if card.get("arxiv_id"):
        fields += [("eprint", card["arxiv_id"]), ("archivePrefix", "arXiv")]
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields)
    kind = "article" if venue else "misc"
    return f"@{kind}{{{key},\n{body}\n}}\n"
