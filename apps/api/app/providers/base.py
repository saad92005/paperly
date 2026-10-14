"""Provider Protocols (docs/02 §3.4). Business logic depends only on these."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

Rect = tuple[float, float, float, float]  # x0, top, x1, bottom in PDF points, top-left origin


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
    rects: list[tuple[int, Rect]] = field(default_factory=lambda: [])  # (page, rect) per line


@dataclass
class Block:
    """A run of text in one section: body, abstract, caption or reference entry."""

    kind: Literal["abstract", "body", "caption", "table", "equation", "reference"]
    section_idx: int
    sentences: list[Sentence] = field(default_factory=lambda: [])


@dataclass
class ParsedSection:
    heading: str
    level: int
    page_start: int
    page_end: int


@dataclass
class ParsedDocument:
    page_count: int
    title: str | None = None
    abstract: str | None = None
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    sections: list[ParsedSection] = field(default_factory=lambda: [])
    blocks: list[Block] = field(default_factory=lambda: [])
    references: list[str] = field(default_factory=lambda: [])
    page_sizes: list[tuple[float, float]] = field(default_factory=lambda: [])
    dropped_lines: int = 0  # headers/footers/invisible lines removed (debug view)


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
    model: str

    def stream_chat(
        self,
        messages: list[Msg],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> AsyncIterator[Delta]: ...


class EmbeddingProvider(Protocol):
    dim: int
    name: str

    async def embed(self, texts: list[str], *, kind: Literal["query", "doc"]) -> list[list[float]]: ...


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
    async def get(self, path: str) -> bytes | None: ...
    async def delete(self, path: str) -> None: ...
