from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Status = Literal["queued", "fetching", "parsing", "indexing", "ready", "failed"]


class Author(BaseModel):
    name: str


class PaperCard(BaseModel):
    id: UUID
    title: str | None
    authors: list[Author]
    year: int | None
    venue: str | None
    source: Literal["upload", "arxiv", "doi", "url"]
    source_ref: str | None
    status: Status
    error: str | None
    page_count: int | None
    starred: bool
    read_progress: float
    collection_id: UUID | None
    tags: list[str]
    added_at: datetime
    arxiv_id: str | None
    doi: str | None


class SectionOut(BaseModel):
    id: UUID
    idx: int
    heading: str
    level: int
    page_start: int | None
    page_end: int | None


class Paper(PaperCard):
    abstract: str | None
    visibility: Literal["private", "public_cache"]
    parser: str | None
    sections: list[SectionOut]


class PaperPage(BaseModel):
    items: list[PaperCard]
    next_cursor: str | None


class ImportIn(BaseModel):
    source: Literal["arxiv", "doi", "url"]
    value: str = Field(min_length=3, max_length=500)
    collection_id: UUID | None = None


class ImportOut(BaseModel):
    paper_id: UUID
    job_id: UUID | None
    status: Status


class PaperPatch(BaseModel):
    collection_id: UUID | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    starred: bool | None = None
    read_progress: float | None = Field(default=None, ge=0, le=1)


class ChunkOut(BaseModel):
    id: UUID
    paper_id: UUID
    idx: int
    kind: str
    text: str
    context_header: str
    page_start: int
    page_end: int
    section: str | None
    sentences: list[dict[str, Any]]
    token_count: int


class ReferenceOut(BaseModel):
    idx: int
    raw: str
    title: str | None
    year: int | None
    doi: str | None
    arxiv_id: str | None
    resolved_paper_id: UUID | None
    in_library: bool = False


class JobOut(BaseModel):
    id: UUID
    type: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    stage: str | None
    progress: int
    error: str | None
