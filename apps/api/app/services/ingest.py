"""ingest_paper job: fetch → parse → chunk → embed → index (docs/06 §1)."""

import hashlib
import re
from collections import OrderedDict
from typing import Any
from uuid import UUID

import structlog

from app import db
from app.config import Settings
from app.errors import AppError
from app.ingest import sources
from app.ingest.chunker import CHUNKER_VERSION, chunk_document
from app.ingest.fetch import FetchFailed, fetch_bytes
from app.jobs import queue
from app.jobs.worker import JobContext, RetryableError
from app.providers.registry import Providers
from app.repos import papers as repo

log = structlog.get_logger()


class TooManyPages(AppError):
    code, status = "too_many_pages", 422


class NotPdf(AppError):
    code, status, message = "unsupported_file", 422, "That link did not return a PDF."


# arXiv PDFs are not stored (docs/03 §5); a small in-memory LRU serves the reader.
_pdf_cache: OrderedDict[str, bytes] = OrderedDict()
_PDF_CACHE_BYTES = 120 * 1024 * 1024


def _cache_put(key: str, data: bytes) -> None:
    _pdf_cache[key] = data
    _pdf_cache.move_to_end(key)
    while sum(len(v) for v in _pdf_cache.values()) > _PDF_CACHE_BYTES and len(_pdf_cache) > 1:
        _pdf_cache.popitem(last=False)


async def paper_pdf(paper: dict[str, Any], providers: Providers, settings: Settings) -> bytes:
    """Bytes of the paper's PDF: from blob storage, or (arXiv) the cache / arXiv itself."""
    if paper.get("blob_path"):
        data = await providers.blobs.get(paper["blob_path"])
        if data is None:
            raise FetchFailed("The stored PDF is missing.")
        return data
    if paper.get("arxiv_id"):
        key = f"arxiv:{paper['arxiv_id']}"
        if key in _pdf_cache:
            _pdf_cache.move_to_end(key)
            return _pdf_cache[key]
        data, _ = await fetch_bytes(
            f"https://arxiv.org/pdf/{paper['arxiv_id']}",
            max_bytes=settings.max_upload_mb * 1024 * 1024 * 2,
            user_agent=sources.user_agent(settings.contact_email),
            accept="application/pdf",
        )
        _cache_put(key, data)
        return data
    raise FetchFailed("No PDF source for this paper.")


def _ref_fields(raw: str) -> dict[str, Any]:
    year = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", raw)
    doi = sources.DOI.search(raw)
    arx = re.search(r"arXiv[:\s]*(\d{4}\.\d{4,5})", raw, re.I)
    # Title guess: the longest sentence-like piece after the author list.
    parts = [p.strip() for p in re.split(r"(?<=[a-z0-9\)])\.\s+", re.sub(r"^\[\d+\]\s*", "", raw))]
    title = max(parts[1:3] or parts[:1], key=len) if parts else None
    return {
        "raw": raw[:2000],
        "title": (title or "")[:300] or None,
        "year": int(year.group(1)) if year else None,
        "doi": doi.group(1).rstrip(".,;") if doi else None,
        "arxiv_id": arx.group(1) if arx else None,
    }


def make_ingest_handler(providers: Providers, settings: Settings):
    async def handle(job: dict[str, Any], ctx: JobContext) -> None:
        paper_id = UUID(str(job["payload"]["paper_id"]))
        engine = db.get_engine()
        async with engine.begin() as conn:
            paper = await repo.get_paper(conn, paper_id)
            if paper is None:
                return  # deleted meanwhile
            await repo.update_paper(conn, paper_id, status="fetching", error=None)
        await ctx.progress("fetching", 5)

        try:
            if paper["source"] in ("doi", "url") and not paper["blob_path"] and not paper["arxiv_id"]:
                url = job["payload"].get("pdf_url")
                if not url:
                    raise FetchFailed("No open-access PDF was found for this paper.")
                data, ctype = await fetch_bytes(
                    url,
                    max_bytes=settings.max_upload_mb * 1024 * 1024,
                    user_agent=sources.user_agent(settings.contact_email),
                    accept="application/pdf",
                )
                if not data.startswith(b"%PDF-"):
                    raise NotPdf(details={"content_type": ctype})
                blob_path = f"papers/{paper_id}.pdf"
                await providers.blobs.put(blob_path, data, "application/pdf")
                paper["blob_path"] = blob_path
                async with engine.begin() as conn:
                    await repo.update_paper(conn, paper_id, blob_path=blob_path,
                                            sha256=hashlib.sha256(data).hexdigest())  # fmt: skip
            else:
                data = await paper_pdf(paper, providers, settings)
        except AppError:
            raise
        except Exception as exc:
            raise RetryableError(f"download failed: {type(exc).__name__}") from exc

        await ctx.progress("parsing", 20)
        async with engine.begin() as conn:
            await repo.update_paper(conn, paper_id, status="parsing")
        doc = await providers.parser.parse(data)
        if doc.page_count > settings.max_pages_free:
            raise TooManyPages(
                f"This paper has {doc.page_count} pages; the free limit is {settings.max_pages_free}."
            )

        title = paper["title"] or doc.title
        meta: dict[str, Any] = {
            "page_count": doc.page_count,
            "parser": f"{providers.parser.name}/{CHUNKER_VERSION}/{providers.embeddings.name}",
            "title": title,
            "abstract": paper["abstract"] or doc.abstract,
            "year": paper["year"] or doc.year,
        }
        if not paper["doi"] and doc.doi and paper["visibility"] == "private":
            meta["doi"] = doc.doi
        if not paper["arxiv_id"] and doc.arxiv_id and paper["visibility"] == "private":
            meta["arxiv_id"] = doc.arxiv_id
        if paper["sha256"].startswith(("arxiv:", "doi:", "url:")):
            meta["sha256"] = hashlib.sha256(data).hexdigest()

        await ctx.progress("indexing", 45)
        async with engine.begin() as conn:
            await repo.update_paper(conn, paper_id, status="indexing")
        drafts = chunk_document(doc, title)
        vectors: list[list[float]] = []
        for i in range(0, len(drafts), 64):
            batch = drafts[i : i + 64]
            vectors.extend(await providers.embeddings.embed([d.embed_text for d in batch], kind="doc"))
            await ctx.progress("indexing", 45 + int(50 * min(1.0, (i + 64) / max(1, len(drafts)))))
        chunks = [{**d.__dict__, "embedding": v} for d, v in zip(drafts, vectors, strict=True)]
        secs = [
            {"idx": i, "heading": s.heading[:300], "level": s.level,
             "page_start": s.page_start, "page_end": s.page_end}
            for i, s in enumerate(doc.sections)
        ]  # fmt: skip
        refs = [{"idx": i, **_ref_fields(r)} for i, r in enumerate(doc.references)]
        async with engine.begin() as conn:
            await repo.replace_index(conn, paper_id, secs, chunks, refs)
            await repo.update_paper(conn, paper_id, status="ready", **meta)
            # Post-ingest: a cited structured summary, low priority (docs/06 §1.4).
            if providers.llm.available:
                await queue.enqueue(conn, "build_summary",
                                    {"paper_id": str(paper_id), "lang": "en", "level": "student"},
                                    None, priority=8)  # fmt: skip
        log.info("paper_indexed", paper_id=str(paper_id), pages=doc.page_count, chunks=len(chunks),
                 sections=len(secs), references=len(refs), dropped_lines=doc.dropped_lines)  # fmt: skip

    async def on_final_failure(job: dict[str, Any], message: str) -> None:
        async with db.get_engine().begin() as conn:
            await repo.update_paper(conn, UUID(str(job["payload"]["paper_id"])),
                                    status="failed", error=message[:500])  # fmt: skip

    handle.on_final_failure = on_final_failure  # type: ignore[attr-defined]
    return handle
