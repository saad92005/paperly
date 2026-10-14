"""Discover (arXiv + Semantic Scholar search), "cited by" and reference resolution."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.ingest import sources
from app.repos import chat as chat_repo


async def library_keys(s: AsyncSession, user_id: UUID) -> tuple[set[str], set[str], set[str]]:
    rows = (
        await s.execute(
            text(
                "select p.arxiv_id, lower(p.doi) as doi, lower(p.title) as title from user_papers up "
                "join papers p on p.id = up.paper_id where up.user_id = :u"
            ),
            {"u": user_id},
        )
    ).all()
    return ({r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]}, {r[2] for r in rows if r[2]})


def _norm_title(t: str | None) -> str:
    return re.sub(r"\W+", " ", (t or "").lower()).strip()


async def search(
    s: AsyncSession, settings: Settings, user_id: UUID, q: str, source: str, year_from: int | None,
    open_access_only: bool,
) -> list[dict[str, Any]]:  # fmt: skip
    results: list[dict[str, Any]] = []
    if source in ("arxiv", "all"):
        for m in await sources.arxiv_search(q, settings.contact_email, 12):
            results.append({
                "title": m.title, "authors": m.authors[:8], "year": m.year, "venue": m.venue or "arXiv",
                "abstract": (m.abstract or "")[:1200], "arxiv_id": m.arxiv_id, "doi": m.doi,
                "oa_pdf": m.pdf_url, "citation_count": None, "source": "arxiv",
            })  # fmt: skip
    if source in ("s2", "all"):
        for d in await sources.s2_search(q, settings.contact_email, 12):
            ext = d.get("externalIds") or {}
            oa = (d.get("openAccessPdf") or {}).get("url")
            results.append({
                "title": d.get("title"), "authors": [a.get("name") for a in d.get("authors") or []][:8],
                "year": d.get("year"), "venue": d.get("venue") or None, "abstract": (d.get("abstract") or "")[:1200],
                "arxiv_id": ext.get("ArXiv"), "doi": ext.get("DOI"), "oa_pdf": oa,
                "citation_count": d.get("citationCount"), "source": "s2",
            })  # fmt: skip
    arx, dois, titles = await library_keys(s, user_id)
    merged: dict[str, dict[str, Any]] = {}
    for r in results:
        key = r["arxiv_id"] or (r["doi"] or "").lower() or _norm_title(r["title"])
        if not key:
            continue
        if key in merged:  # prefer the richer record, keep citation counts
            merged[key]["citation_count"] = merged[key]["citation_count"] or r["citation_count"]
            continue
        merged[key] = r
    out: list[dict[str, Any]] = []
    for r in merged.values():
        if year_from and (r["year"] or 0) < year_from:
            continue
        importable = bool(r["arxiv_id"] or (r["doi"] and r["oa_pdf"]))
        if open_access_only and not importable:
            continue
        r["importable"] = importable
        r["in_library"] = bool(
            (r["arxiv_id"] and r["arxiv_id"] in arx) or (r["doi"] and r["doi"].lower() in dois)
            or _norm_title(r["title"]) in {_norm_title(t) for t in titles}
        )  # fmt: skip
        out.append(r)
    return out[:20]


async def cited_by(s: AsyncSession, settings: Settings, paper: dict[str, Any]) -> list[dict[str, Any]]:
    ident = (
        f"arXiv:{paper['arxiv_id']}"
        if paper.get("arxiv_id")
        else (f"DOI:{paper['doi']}" if paper.get("doi") else None)
    )
    if not ident:
        return []
    key = f"citedby:{ident}"
    cached = await chat_repo.cache_get(s, key)
    if cached and "items" in cached:
        return list(cached["items"])
    items = []
    for d in await sources.s2_citations(ident, settings.contact_email, 25):
        ext = d.get("externalIds") or {}
        items.append({"title": d.get("title"), "authors": [a.get("name") for a in d.get("authors") or []][:5],
                      "year": d.get("year"), "venue": d.get("venue"), "arxiv_id": ext.get("ArXiv"),
                      "doi": ext.get("DOI")})  # fmt: skip
    await chat_repo.cache_put(s, key, {"items": items})
    await s.commit()
    return items
