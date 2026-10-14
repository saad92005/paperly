"""Literature-review drafter (docs/06 §3): cluster papers into themes, synthesise each theme with
citations, then render APA or IEEE in-text citations plus a reference list and BibTeX."""

import math
import re
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import db, prompts
from app.jobs.worker import JobContext, RetryableError
from app.providers.base import Msg
from app.providers.llm import ProviderError
from app.providers.registry import Providers
from app.services.answer import cosine
from app.services.papers import bibtex
from app.services.retrieval import Hit, retrieve
from app.services.structured import sources_block
from app.services.study import NoProvider, get_or_build_summary


def kmeans(vectors: list[list[float]], k: int, iters: int = 15) -> list[int]:
    """Tiny deterministic k-means on cosine similarity (n ≤ 30)."""
    n = len(vectors)
    k = max(1, min(k, n))
    centers = [vectors[round(i * (n - 1) / max(1, k - 1))] for i in range(k)] if k > 1 else [vectors[0]]
    labels = [0] * n
    for _ in range(iters):
        labels = [max(range(k), key=lambda j, v=v: cosine(v, centers[j])) for v in vectors]
        for j in range(k):
            members = [vectors[i] for i in range(n) if labels[i] == j]
            if members:
                centers[j] = [sum(x) / len(members) for x in zip(*members, strict=True)]
    return labels


def _author_year(card: dict[str, Any]) -> str:
    names = [a.get("name", "") for a in card.get("authors") or [] if a.get("name")]
    last = names[0].split()[-1] if names else (card.get("title") or "Anon").split()[0]
    who = (
        last
        if len(names) <= 1
        else f"{last} & {names[1].split()[-1]}"
        if len(names) == 2
        else f"{last} et al."
    )
    return f"{who}, {card.get('year') or 'n.d.'}"


def make_review_handler(providers: Providers):
    async def handle(job: dict[str, Any], ctx: JobContext) -> None:
        p = job["payload"]
        user_id = UUID(str(job["user_id"]))
        if not providers.llm.available:
            raise NoProvider()
        async with AsyncSession(db.get_engine()) as s:
            rows = (
                (
                    await s.execute(
                        text(
                            "select p.id, p.title, p.authors, p.year, p.venue, p.doi, p.arxiv_id from user_papers up "
                            "join papers p on p.id = up.paper_id where up.user_id = :u and up.collection_id = :c "
                            "and p.status = 'ready' order by p.year nulls last limit 12"
                        ),
                        {"u": user_id, "c": UUID(p["collection_id"])},
                    )
                )
                .mappings()
                .all()
            )
            cards = [dict(r) for r in rows]
            if len(cards) < 2:
                raise ValueError("A review needs at least 2 indexed papers in the collection.")
            await ctx.progress("summarising papers", 10)
            summaries: list[dict[str, Any]] = []
            for c in cards:
                summaries.append(await get_or_build_summary(s, providers, c["id"], "en", "expert"))
            # Theme clustering on keywords + tl;dr.
            texts = [
                " ".join(sm.get("keywords", [])) + " " + " ".join(i["text"] for i in sm.get("tldr", []))
                for sm in summaries
            ]
            vecs = await providers.embeddings.embed([t or c["title"] or "" for t, c in zip(texts, cards, strict=True)],
                                                    kind="doc")  # fmt: skip
            k = 1 if len(cards) <= 3 else min(5, max(2, round(math.sqrt(len(cards)))))
            labels = kmeans(vecs, k)
            topic = p.get("topic") or ""
            style = p.get("style", "apa")
            numbering = {str(c["id"]): i for i, c in enumerate(cards, 1)}
            sections: list[str] = []
            for j in range(k):
                members = [cards[i] for i in range(len(cards)) if labels[i] == j]
                if not members:
                    continue
                kw: dict[str, int] = {}
                for i in range(len(cards)):
                    if labels[i] == j:
                        for w in summaries[i].get("keywords", [])[:5]:
                            kw[w] = kw.get(w, 0) + 1
                theme = ", ".join(sorted(kw, key=lambda w: -kw[w])[:3]).title() or "Overview"
                if k == 1:
                    theme = topic.title() or "Overview"
                await ctx.progress(f"writing: {theme}", 30 + int(60 * j / k))
                hits: list[Hit] = []
                query = f"{topic} {theme} main contribution method results".strip()
                for m in members:
                    r = await retrieve(s, providers, query, [m["id"]], tau=0.0, per_paper=3)
                    hits.extend(Hit({**h.chunk, "paper_title": f"{m['title']} ({_author_year(m)})"}, h.rrf, h.score)
                                for h in r.hits[:3])  # fmt: skip
                prompt = prompts.REVIEW.format(
                    theme=theme, length="2-3 paragraphs" if p.get("length") == "long" else "1-2 paragraphs",
                    sources=sources_block(hits),
                )  # fmt: skip
                try:
                    out, _ = await providers.llm.complete(
                        "summary", [Msg("system", "You write rigorous, cited academic prose."), Msg("user", prompt)],
                        temperature=0.3, max_tokens=1200,
                    )  # fmt: skip
                except ProviderError as exc:
                    raise RetryableError(str(exc)) from exc

                def cite(m: re.Match[str], hits: list[Hit] = hits) -> str:
                    refs: list[str] = []
                    for x in re.findall(r"\d+", m.group(0)):
                        idx = int(x)
                        if 1 <= idx <= len(hits):
                            card = next(c for c in cards if c["id"] == hits[idx - 1].chunk["paper_id"])
                            refs.append(
                                f"[{numbering[str(card['id'])]}]" if style == "ieee" else _author_year(card)
                            )
                    refs = list(dict.fromkeys(refs))
                    if not refs:
                        return ""
                    return "".join(refs) if style == "ieee" else f"({'; '.join(refs)})"

                body = re.sub(r"(?:\[S\d+(?:\s*,\s*S?\d+)*\])+", cite, out).strip()
                sections.append(f"## {theme}\n\n{body}")
            refs = [
                (f"[{numbering[str(c['id'])]}] " if style == "ieee" else "- ") + bibtex(c, style)
                for c in cards
            ]
            if style == "apa":
                refs.sort()
            title = topic.title() or "Literature review"
            md = f"# {title}\n\n" + "\n\n".join(sections) + "\n\n## References\n\n" + "\n".join(refs) + "\n"
            bib = "\n".join(bibtex(c, "bibtex") for c in cards)
            await s.execute(
                text(
                    "insert into reviews (user_id, collection_id, job_id, topic, style, content_md, bibtex) "
                    "values (:u, :c, :j, :t, :st, :md, :bib)"
                ),
                {"u": user_id, "c": UUID(p["collection_id"]), "j": job["id"], "t": topic, "st": style, "md": md,
                 "bib": bib},
            )  # fmt: skip
            await s.commit()

    return handle


def to_latex(md: str) -> str:
    def esc(t: str) -> str:
        for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                     ("_", r"\_"), ("{", r"\{"), ("}", r"\}")):  # fmt: skip
            t = t.replace(a, b)
        return t

    out = [r"\documentclass{article}", r"\usepackage[utf8]{inputenc}", r"\begin{document}"]
    for line in md.splitlines():
        if line.startswith("# "):
            out.append(r"\title{" + esc(line[2:]) + r"}\maketitle")
        elif line.startswith("## "):
            out.append(r"\section*{" + esc(line[3:]) + "}")
        else:
            out.append(esc(line.removeprefix("- ")))
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"


async def get_review(s: AsyncSession, user_id: UUID, job_id: UUID) -> dict[str, Any] | None:
    row = (
        (
            await s.execute(
                text(
                    "select id, topic, style, content_md, bibtex, created_at from reviews where job_id = :j and user_id = :u"
                ),
                {"j": job_id, "u": user_id},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def list_reviews(s: AsyncSession, user_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await s.execute(
            text(
                "select id, job_id, collection_id, topic, style, created_at, left(content_md, 400) as preview "
                "from reviews where user_id = :u order by created_at desc limit 50"
            ),
            {"u": user_id},
        )
    ).mappings()
    return [dict(r) for r in rows]
