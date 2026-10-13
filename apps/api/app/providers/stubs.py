"""Deterministic stub providers: used in tests and until real adapters land (Phases 1-2)."""

import hashlib
import math
from collections.abc import AsyncIterator
from typing import Any, Literal

from app.providers.base import Delta, Msg, PaperMetadata, ParsedDocument


class StubLLM:
    name = "stub"

    async def stream_chat(
        self,
        messages: list[Msg],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[Delta]:
        for word in "NOT_FOUND\nThe stub provider does not answer questions.".split(" "):
            yield Delta(text=word + " ")
        yield Delta(prompt_tokens=0, completion_tokens=0)


class StubEmbeddings:
    def __init__(self, dim: int) -> None:
        self.dim = dim

    async def embed(self, texts: list[str], *, kind: Literal["query", "doc"]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            seed = hashlib.sha256(t.encode()).digest()
            v = [((seed[i % len(seed)] / 255.0) - 0.5) for i in range(self.dim)]
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


class StubReranker:
    async def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        q = set(query.lower().split())
        scores = [(i, len(q & set(d.lower().split())) / (len(q) or 1)) for i, d in enumerate(docs)]
        return sorted(scores, key=lambda s: s[1], reverse=True)[:top_k]


class StubParser:
    name = "stub"

    async def parse(self, pdf: bytes) -> ParsedDocument:
        return ParsedDocument(page_count=0)


class StubMetadata:
    name = "stub"

    async def lookup(self, identifier: str) -> PaperMetadata | None:
        return None
