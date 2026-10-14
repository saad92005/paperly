"""Paper metadata sources: arXiv API, Crossref, Unpaywall, Semantic Scholar (all free, no key).

Every call sends a descriptive User-Agent with the contact email (polite-pool etiquette).
"""

import re
from typing import Any

import defusedxml.ElementTree as ET
import httpx

from app.providers.base import PaperMetadata

ARXIV_ID = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?|([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)
DOI = re.compile(r"(10\.\d{4,9}/\S+)", re.I)
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def user_agent(contact: str) -> str:
    return f"Paperly/0.1 (open-source paper reader; mailto:{contact or 'noreply@example.com'})"


def normalize_arxiv(value: str) -> str | None:
    v = value.strip()
    v = re.sub(r"^https?://(www\.|export\.)?arxiv\.org/(abs|pdf|html)/", "", v, flags=re.I)
    v = re.sub(r"^arxiv:", "", v, flags=re.I).removesuffix(".pdf")
    m = ARXIV_ID.fullmatch(v)
    if not m:
        return None
    return m.group(1) or m.group(3)  # drop the version suffix: the latest version is used


def normalize_doi(value: str) -> str | None:
    v = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    v = re.sub(r"^doi:\s*", "", v, flags=re.I)
    m = DOI.fullmatch(v)
    return m.group(1).rstrip(".") if m else None


def _parse_arxiv_entry(e: Any) -> PaperMetadata:
    raw_id = (e.findtext(f"{ATOM}id") or "").rsplit("/abs/", 1)[-1]
    aid = normalize_arxiv(raw_id) or raw_id
    published = e.findtext(f"{ATOM}published") or ""
    return PaperMetadata(
        title=re.sub(r"\s+", " ", e.findtext(f"{ATOM}title") or "").strip() or None,
        authors=[a.findtext(f"{ATOM}name") or "" for a in e.findall(f"{ATOM}author")],
        year=int(published[:4]) if published[:4].isdigit() else None,
        venue=(e.findtext(f"{ARXIV_NS}journal_ref") or "arXiv").strip(),
        abstract=re.sub(r"\s+", " ", e.findtext(f"{ATOM}summary") or "").strip() or None,
        doi=e.findtext(f"{ARXIV_NS}doi"),
        arxiv_id=aid,
        pdf_url=f"https://arxiv.org/pdf/{aid}",
    )


async def arxiv_lookup(arxiv_id: str, contact: str) -> PaperMetadata | None:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id})
    if r.status_code != 200:
        return None
    entries = ET.fromstring(r.content).findall(f"{ATOM}entry")
    if not entries or entries[0].findtext(f"{ATOM}title") in (None, "Error"):
        return None
    return _parse_arxiv_entry(entries[0])


async def arxiv_search(q: str, contact: str, limit: int = 10) -> list[PaperMetadata]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{q}", "max_results": limit, "sortBy": "relevance"},
        )
    if r.status_code != 200:
        return []
    return [_parse_arxiv_entry(e) for e in ET.fromstring(r.content).findall(f"{ATOM}entry")]


async def crossref_lookup(doi: str, contact: str) -> PaperMetadata | None:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get(f"https://api.crossref.org/works/{doi}")
    if r.status_code != 200:
        return None
    m = r.json().get("message", {})
    parts = (m.get("issued") or {}).get("date-parts") or [[None]]
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in m.get("author", [])]
    abstract = re.sub(r"<[^>]+>", "", m.get("abstract") or "").strip() or None
    return PaperMetadata(
        title=(m.get("title") or [None])[0],
        authors=[a for a in authors if a],
        year=parts[0][0] if parts and parts[0] else None,
        venue=(m.get("container-title") or [None])[0],
        abstract=abstract,
        doi=m.get("DOI") or doi,
    )


async def unpaywall_pdf(doi: str, contact: str) -> str | None:
    if not contact:
        return None
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get(f"https://api.unpaywall.org/v2/{doi}", params={"email": contact})
    if r.status_code != 200:
        return None
    loc = r.json().get("best_oa_location") or {}
    return loc.get("url_for_pdf")


async def s2_search(q: str, contact: str, limit: int = 10) -> list[dict[str, Any]]:
    fields = "title,authors,year,venue,abstract,externalIds,openAccessPdf,citationCount"
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": q, "limit": limit, "fields": fields},
        )
    if r.status_code != 200:
        return []
    return list(r.json().get("data") or [])


async def s2_citations(ident: str, contact: str, limit: int = 20) -> list[dict[str, Any]]:
    fields = "title,authors,year,venue,externalIds"
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": user_agent(contact)}) as c:
        r = await c.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{ident}/citations",
            params={"limit": limit, "fields": fields},
        )
    if r.status_code != 200:
        return []
    return [x.get("citingPaper", {}) for x in r.json().get("data") or []]
