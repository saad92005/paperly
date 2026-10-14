"""Deterministic stub providers for tests."""

import hashlib
import math
from collections.abc import AsyncIterator
from typing import Literal

from app.providers.base import Delta, Msg, PaperMetadata, ParsedDocument


class StubLLM:
    """Replays a scripted reply (tests set `reply`); defaults to NOT_FOUND."""

    name = "stub"
    model = "stub-1"

    def __init__(self, reply: str = "NOT_FOUND\nThe stub provider does not answer questions.") -> None:
        self.reply = reply

    async def stream_chat(
        self, messages: list[Msg], *, temperature: float, max_tokens: int, json_mode: bool = False
    ) -> AsyncIterator[Delta]:
        for i in range(0, len(self.reply), 7):
            yield Delta(text=self.reply[i : i + 7])
        yield Delta(prompt_tokens=10, completion_tokens=10)


class StubEmbeddings:
    name = "stub"

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
