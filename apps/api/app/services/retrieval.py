"""Hybrid retrieval (vector + full-text, RRF) → FlashRank rerank → per-paper selection (docs/06 §2.2)."""

import math
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.registry import Providers
from app.repos.papers import _vec  # pyright: ignore[reportPrivateUsage]

HYBRID_SQL = text(
    """
with vec as (
  select id, row_number() over (order by embedding <=> cast(:qv as halfvec)) as r
  from chunks
  where paper_id = any(:pids) and kind <> 'reference' and embedding is not null
  order by embedding <=> cast(:qv as halfvec)
  limit :k
),
fts as (
  select id, row_number() over (order by ts_rank_cd(fts, query) desc) as r
  from chunks, websearch_to_tsquery('english', :qt) query
  where paper_id = any(:pids) and kind <> 'reference' and fts @@ query
  order by ts_rank_cd(fts, query) desc
  limit :k
)
select c.id, c.paper_id, c.idx, c.kind, c.text, c.context_header, c.page_start, c.page_end,
       c.sentences, sec.heading as section, p.title as paper_title,
       coalesce(1.0/(60+vec.r),0) + coalesce(1.0/(60+fts.r),0) as rrf,
       1 - (c.embedding <=> cast(:qv as halfvec)) as vsim
from chunks c
join papers p on p.id = c.paper_id
left join sections sec on sec.id = c.section_id
left join vec on vec.id = c.id
left join fts on fts.id = c.id
where vec.id is not null or fts.id is not null
order by rrf desc
limit :k
"""
)


GENERIC = re.compile(
    r"\b(limitations?|weakness(es)?|contributions?|future work|main (idea|finding|result)s?|key (idea|finding|result)s?|"
    r"summar(y|ize|ise)|conclusions?|method(ology)?|approach|results?|datasets?|baselines?|experiments?|"
    r"novelty|motivation|problem)\b",
    re.I,
)

STOP = set(
    "a an the of in on for to and or is are was were be been what which who whom how why where when "
    "does do did it its this that these those paper model use used using with by from about discuss "
    "explain describe show me tell".split()
)


def _terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def heading_boost(query: str, heading: str | None) -> float:
    """Papers announce topics in headings: boost chunks whose section heading matches the query."""
    q, h = _terms(query), _terms(heading or "")
    if not q or not h:
        return 0.0
    return 0.15 * len(q & h) / len(q)


@dataclass
class Hit:
    chunk: dict[str, Any]
    rrf: float
    score: float = 0.0  # rerank score

    @property
    def paper_id(self) -> UUID:
        return self.chunk["paper_id"]


def blend(rerank: float, h: Hit, query: str) -> float:
    """Cross-encoder score blended with vector similarity (robust to its 256-token truncation),
    a small heading match boost, and a penalty for equation/table debris."""
    vsim = float(h.chunk.get("vsim") or 0.0)
    v = min(1.0, max(0.0, (vsim - 0.55) / 0.35))
    score = 0.65 * rerank + 0.35 * v + heading_boost(query, h.chunk.get("section"))
    return score * (0.6 if h.chunk["kind"] == "equation" else 1.0)


@dataclass
class Retrieval:
    hits: list[Hit]
    candidates: list[Hit] = field(default_factory=lambda: [])
    best_score: float = 0.0
    best_vsim: float = 0.0

    def abstain(self, tau: float, vtau: float, query: str = "") -> bool:
        """Refuse only when both the reranker and plain vector similarity say "unrelated".
        Questions about parts every paper has (limitations, method, results...) never abstain."""
        if self.hits and GENERIC.search(query):
            return False
        return not self.hits or (self.best_score < tau and self.best_vsim < vtau)


async def hybrid(
    s: AsyncSession, providers: Providers, query: str, paper_ids: list[UUID], k: int = 40
) -> list[Hit]:
    [qv] = await providers.embeddings.embed([query], kind="query")
    await s.execute(text("set local hnsw.ef_search = 80"))
    rows = (await s.execute(HYBRID_SQL, {"qv": _vec(qv), "qt": query, "pids": paper_ids, "k": k})).mappings()
    return [Hit(dict(r), float(r["rrf"])) for r in rows]


def select(hits: list[Hit], n_papers: int, tau: float) -> list[Hit]:
    """Single paper → top 8; several → top 12 with a per-paper cap and ≥ 1 per relevant paper."""
    if n_papers <= 1:
        return hits[:8]
    cap = math.ceil(12 / n_papers) + 1
    out: list[Hit] = []
    per: dict[UUID, int] = {}
    # First guarantee one chunk from each paper whose best score clears τ.
    for h in hits:
        if h.paper_id not in per and h.score >= tau:
            out.append(h)
            per[h.paper_id] = 1
    for h in hits:
        if len(out) >= 12:
            break
        if h in out or per.get(h.paper_id, 0) >= cap:
            continue
        out.append(h)
        per[h.paper_id] = per.get(h.paper_id, 0) + 1
    return sorted(out, key=lambda h: h.score, reverse=True)


async def retrieve(
    s: AsyncSession,
    providers: Providers,
    query: str,
    paper_ids: list[UUID],
    *,
    tau: float,
    per_paper: int | None = None,
) -> Retrieval:
    cands = await hybrid(s, providers, query, paper_ids)
    if not cands:
        return Retrieval([], [], 0.0, 0.0)
    ranked = await providers.reranker.rerank(
        query, [f"{h.chunk['context_header']}\n{h.chunk['text']}" for h in cands], len(cands)
    )
    for i, score in ranked:
        cands[i].score = blend(score, cands[i], query)
    cands.sort(key=lambda h: h.score, reverse=True)
    if per_paper is not None:
        picked: list[Hit] = []
        for pid in paper_ids:
            picked.extend([h for h in cands if h.paper_id == pid][:per_paper])
        hits = sorted(picked, key=lambda h: h.score, reverse=True)
    else:
        hits = select(cands, len(paper_ids), tau)
    return Retrieval(hits, cands, cands[0].score, max(float(h.chunk.get("vsim") or 0) for h in cands))


def source_label(h: Hit) -> str:
    sec = h.chunk.get("section") or h.chunk["kind"]
    pages = (
        f"p.{h.chunk['page_start']}"
        if h.chunk["page_start"] == h.chunk["page_end"]
        else f"pp.{h.chunk['page_start']}-{h.chunk['page_end']}"
    )
    return f"({h.chunk.get('paper_title') or 'Untitled'} · {sec} · {pages})"


def format_sources(hits: list[Hit]) -> str:
    return "\n\n".join(f"[S{i}] {source_label(h)}\n{h.chunk['text']}" for i, h in enumerate(hits, 1))
