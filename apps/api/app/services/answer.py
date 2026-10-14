"""Grounded generation engine shared by chat, explain and summaries (docs/06 §2.3-2.5).

Streams LLM text, parses [S#] markers on the fly (they can split across tokens), renumbers
them [1], [2]… in order of first use, picks the exact cited sentence(s) by embedding
similarity, and finally scores how well the answer is supported (support check + number guard).
"""

import math
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.providers.base import Msg
from app.providers.llm import ProviderError
from app.providers.registry import Providers
from app.services.retrieval import Hit

MARK = re.compile(r"\[S(\d+(?:\s*[,;]\s*S?\d+)*)\]")
HIGHLIGHT_MIN = 0.72  # bge-small cosine; calibrated on the eval set (see docs/07)
SUPPORT_MIN = 0.62
NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%)?")
SENT_END = re.compile(r"(?<=[.!?])\s+|\n+")


def norm_numbers(text: str) -> set[str]:
    out: set[str] = set()
    for m in NUM.finditer(text):
        whole = m.group(1).replace(",", "")
        frac = m.group(2)
        out.add(f"{int(whole)}.{frac.rstrip('0')}".rstrip(".") if frac else str(int(whole)))
    return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


@dataclass
class Event:
    kind: str  # token | citation | diagram
    data: dict[str, Any]


@dataclass
class Result:
    text: str = ""
    raw: str = ""  # model output with original [S#] markers (cache replay)
    citations: list[dict[str, Any]] = field(default_factory=lambda: [])
    not_found: bool = False
    grounded: bool | None = None
    support_score: float | None = None
    provider: str | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    ttft_ms: int | None = None


class SentenceIndex:
    """Lazily embeds the sentences of cited chunks (once per request)."""

    def __init__(self, providers: Providers) -> None:
        self.providers = providers
        self.cache: dict[str, list[list[float]]] = {}

    async def vectors(self, chunk: dict[str, Any]) -> list[list[float]]:
        key = str(chunk["id"])
        if key not in self.cache:
            texts = [chunk["text"][s["s"] : s["e"]] for s in chunk["sentences"]] or [chunk["text"]]
            self.cache[key] = await self.providers.embeddings.embed(texts, kind="doc")
        return self.cache[key]

    async def best(self, chunk: dict[str, Any], vec: list[float]) -> list[tuple[int, float]]:
        scores = [(i, cosine(vec, v)) for i, v in enumerate(await self.vectors(chunk))]
        scores.sort(key=lambda x: x[1], reverse=True)
        top = [x for x in scores[:2] if x[1] >= HIGHLIGHT_MIN]
        return top or scores[:1]


def citation_payload(n: int, hit: Hit, picks: list[tuple[int, float]]) -> dict[str, Any]:
    c = hit.chunk
    sents = c["sentences"]
    idx = sorted(i for i, _ in picks) if sents else []
    quote = " ".join(c["text"][sents[i]["s"] : sents[i]["e"]] for i in idx) if sents else c["text"][:300]
    rects = [{"page": r[0], "rect": [r[1], r[2], r[3], r[4]]} for i in idx for r in sents[i].get("rects", [])]
    page = sents[idx[0]]["page"] if idx else c["page_start"]
    return {
        "n": n,
        "paper_id": str(c["paper_id"]),
        "paper_title": c.get("paper_title"),
        "chunk_id": str(c["id"]),
        "page": page,
        "section": c.get("section"),
        "sentence_idx": idx,
        "quote": quote[:600],
        "rects": rects,
    }


class MarkerStream:
    """Incremental [S#] parser with renumbering."""

    def __init__(self, n_sources: int) -> None:
        self.n_sources = n_sources
        self.buf = ""
        self.numbers: dict[int, int] = {}  # source index (1-based) → display number

    def _render(self, inner: str) -> tuple[str, list[int]]:
        out: list[int] = []
        for part in re.split(r"\s*[,;]\s*S?", inner):
            if part.isdigit() and 1 <= int(part) <= self.n_sources:
                out.append(int(part))
        text = "".join(f"[{self.numbers.setdefault(i, len(self.numbers) + 1)}]" for i in dict.fromkeys(out))
        return text, out

    def feed(self, chunk: str, final: bool = False) -> list[tuple[str, list[int]]]:
        """Returns (text, newly-cited source indexes) pieces ready to emit."""
        self.buf += chunk
        pieces: list[tuple[str, list[int]]] = []
        while True:
            m = MARK.search(self.buf)
            if not m:
                break
            if m.start():
                pieces.append((self.buf[: m.start()], []))
            rendered, srcs = self._render(m.group(1))
            pieces.append((rendered, srcs))
            self.buf = self.buf[m.end() :]
        hold = self.buf.rfind("[")
        if not final and hold != -1 and len(self.buf) - hold < 24:
            emit, self.buf = self.buf[:hold], self.buf[hold:]
        else:
            emit, self.buf = self.buf, ""
        if emit:
            pieces.append((emit, []))
        return pieces


def last_sentence(text: str) -> str:
    parts = [p for p in SENT_END.split(text.strip()) if p.strip()]
    s = parts[-1] if parts else text
    return re.sub(r"\[\d+\]", "", s).strip(" -*•")


async def generate(
    providers: Providers,
    hits: list[Hit],
    messages: list[Msg],
    result: Result,
    *,
    task: str = "chat",
    max_tokens: int = 600,
    canned: str | None = None,
    check: bool = True,
) -> AsyncIterator[Event]:
    """Stream tokens + citation events into `result`. `canned` replays fixed text (extractive/cache)."""
    started = time.monotonic()
    ms = MarkerStream(len(hits))
    sindex = SentenceIndex(providers)
    out: list[str] = []
    cited_pairs: list[tuple[str, int]] = []  # (answer sentence, source idx) for support check
    emitted: set[int] = set()
    head = ""
    head_done = False

    async def handle(piece: str, srcs: list[int]) -> AsyncIterator[Event]:
        if srcs:
            sentence = last_sentence("".join(out))
            vec = (await providers.embeddings.embed([sentence or " "], kind="doc"))[0]
            for src in srcs:
                cited_pairs.append((sentence, src))
                n = ms.numbers[src]
                if n not in emitted:
                    emitted.add(n)
                    hit = hits[src - 1]
                    picks = await sindex.best(hit.chunk, vec)
                    cit = citation_payload(n, hit, picks)
                    result.citations.append(cit)
                    yield Event("citation", cit)
        out.append(piece)
        yield Event("token", {"t": piece})

    async def source() -> AsyncIterator[str]:
        if canned is not None:
            for i in range(0, len(canned), 24):
                yield canned[i : i + 24]
            return
        async for p, d in providers.llm.stream(task, messages, temperature=0.2, max_tokens=max_tokens):
            result.provider, result.model = p.name, p.model
            if d.prompt_tokens:
                result.prompt_tokens = d.prompt_tokens
            if d.completion_tokens:
                result.completion_tokens = d.completion_tokens
            if d.text:
                yield d.text

    raw_all: list[str] = []
    async for raw in source():
        raw_all.append(raw)
        if result.ttft_ms is None:
            result.ttft_ms = int((time.monotonic() - started) * 1000)
        if not head_done:
            # Hold the first characters until we know whether this is the NOT_FOUND sentinel.
            head += raw
            if len(head.lstrip()) < len("NOT_FOUND"):
                continue
            head_done = True
            result.not_found = head.lstrip().startswith("NOT_FOUND")
            raw, head = head, ""
        if result.not_found:
            out.append(raw)
            continue
        for piece, srcs in ms.feed(raw):
            async for ev in handle(piece, srcs):
                yield ev
    if not head_done and head:
        if head.lstrip().startswith("NOT_FOUND"):
            result.not_found = True
            out.append(head)
        else:
            for piece, srcs in ms.feed(head):
                async for ev in handle(piece, srcs):
                    yield ev
    if not result.not_found:
        for piece, srcs in ms.feed("", final=True):
            async for ev in handle(piece, srcs):
                yield ev
    result.text = "".join(out).strip()
    result.raw = "".join(raw_all)
    if result.not_found:
        result.text = re.sub(r"^\s*NOT_FOUND\s*", "", result.text)
    else:
        m = re.search(r"```mermaid\n(.+?)```", result.text, re.S)
        if m:
            yield Event("diagram", {"mermaid": m.group(1).strip()})
        if check:
            await support_check(providers, hits, result, cited_pairs, sindex)
    result.citations.sort(key=lambda c: c["n"])
    result.latency_ms = int((time.monotonic() - started) * 1000)


async def support_check(
    providers: Providers,
    hits: list[Hit],
    result: Result,
    cited_pairs: list[tuple[str, int]],
    sindex: SentenceIndex,
) -> None:
    text = re.sub(r"```.*?```", "", result.text, flags=re.S)
    sentences = [s.strip() for s in SENT_END.split(text) if len(s.strip()) > 3]
    factual = [
        s for s in sentences
        if re.search(r"\[\d+\]", s) or (norm_numbers(s) and not s.startswith("(General context)"))
    ]  # fmt: skip
    if not factual:
        result.grounded, result.support_score = (False, 0.0) if sentences else (None, None)
        return
    by_sentence: dict[str, list[int]] = {}
    for sent, src in cited_pairs:
        by_sentence.setdefault(sent, []).append(src)
    clean = [re.sub(r"\[\d+\]", "", s).strip(" -*•") for s in factual]
    vecs = await providers.embeddings.embed(clean, kind="doc")
    ok = 0
    for s, v in zip(clean, vecs, strict=True):
        srcs = by_sentence.get(s) or next((x for k, x in by_sentence.items() if k and k in s), [])
        if not srcs:
            continue
        support = 0.0
        cited_text = ""
        for src in srcs:
            chunk = hits[src - 1].chunk
            cited_text += " " + chunk["text"]
            support = max(support, max((cosine(v, w) for w in await sindex.vectors(chunk)), default=0.0))
        nums_ok = norm_numbers(s) <= norm_numbers(cited_text)
        if support >= SUPPORT_MIN and nums_ok:
            ok += 1
    score = ok / len(factual)
    result.support_score = round(score, 3)
    result.grounded = score >= 0.85


def extractive_answer(
    hits: list[Hit], query_vec: list[float], sent_vecs: dict[str, list[list[float]]]
) -> str:
    """No-LLM fallback: quote the best-matching sentences, each with its source marker."""
    picks: list[tuple[float, int, str]] = []
    for i, h in enumerate(hits[:5], 1):
        c = h.chunk
        vecs = sent_vecs.get(str(c["id"])) or []
        for j, s in enumerate(c["sentences"]):
            if j < len(vecs):
                text = c["text"][s["s"] : s["e"]].strip()
                if 25 <= len(text) <= 600:
                    picks.append((cosine(query_vec, vecs[j]), i, text))
    picks.sort(key=lambda x: x[0], reverse=True)
    seen: set[str] = set()
    lines: list[str] = []
    for _, i, t in picks:
        key = re.sub(r"\W+", " ", t.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {t} [S{i}]")
        if len(lines) == 4:
            break
    return "Most relevant passages (extractive mode: no AI model is configured):\n\n" + "\n".join(lines)


__all__ = ["Event", "ProviderError", "Result", "extractive_answer", "generate"]
