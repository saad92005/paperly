"""Provider Protocols (docs/02 §3.4). Business logic depends only on these."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class Msg:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class Delta:
    text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class Sentence:
    text: str
    page: int
    rects: list[tuple[float, float, float, float]] = field(default_factory=lambda: [])


@dataclass
class ParsedDocument:
    page_count: int
    title: str | None = None
    sections: list[dict[str, Any]] = field(default_factory=lambda: [])
    blocks: list[dict[str, Any]] = field(default_factory=lambda: [])
    sentences: list[Sentence] = field(default_factory=lambda: [])
    references: list[str] = field(default_factory=lambda: [])


@dataclass
class PaperMetadata:
    title: str | None = None
    authors: list[str] = field(default_factory=lambda: [])
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    pdf_url: str | None = None


class LLMProvider(Protocol):
    name: str

    def stream_chat(
        self,
        messages: list[Msg],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        json_schema: dict[str, Any] | None = None,
    ) -> AsyncIterator[Delta]: ...


class EmbeddingProvider(Protocol):
    dim: int

    async def embed(
        self, texts: list[str], *, kind: Literal["query", "doc"]
    ) -> list[list[float]]: ...


class Reranker(Protocol):
    async def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]: ...


class PdfParser(Protocol):
    name: str

    async def parse(self, pdf: bytes) -> ParsedDocument: ...


class MetadataSource(Protocol):
    name: str

    async def lookup(self, identifier: str) -> PaperMetadata | None: ...


class BlobStore(Protocol):
    async def put(self, path: str, data: bytes, content_type: str) -> None: ...
    async def signed_url(self, path: str, expires_s: int) -> str: ...
    async def delete(self, path: str) -> None: ...
