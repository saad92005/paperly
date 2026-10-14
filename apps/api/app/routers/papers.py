from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse

from app.auth import CurrentUserDep
from app.config import Settings, get_settings
from app.deps import ProvidersDep, SessionDep, wake_worker
from app.errors import NotFound
from app.ingest.fetch import TooLarge
from app.repos import papers as repo
from app.schemas.papers import (
    ChunkOut,
    ImportIn,
    ImportOut,
    Paper,
    PaperCard,
    PaperPage,
    PaperPatch,
    ReferenceOut,
    SectionOut,
)
from app.services import ingest, papers

router = APIRouter(prefix="/v1/papers", tags=["papers"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/upload", status_code=202)
async def upload(
    request: Request,
    user: CurrentUserDep,
    s: SessionDep,
    settings: SettingsDep,
    providers: ProvidersDep,
    file: Annotated[UploadFile, File()],
    collection_id: Annotated[UUID | None, Form()] = None,
) -> ImportOut:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise TooLarge(f"PDFs up to {settings.max_upload_mb} MB are supported.")
    out = await papers.upload(s, settings, providers, user, data, file.filename or "paper.pdf", collection_id)
    wake_worker(request)
    return ImportOut(**out)


@router.post("/import")
async def import_paper(
    request: Request, body: ImportIn, response: Response, user: CurrentUserDep, s: SessionDep,
    settings: SettingsDep,
) -> ImportOut:  # fmt: skip
    out = await papers.import_paper(s, settings, user, body.source, body.value, body.collection_id)
    response.status_code = 200 if out["status"] == "ready" else 202
    wake_worker(request)
    return ImportOut(**out)


@router.get("")
async def list_papers(
    user: CurrentUserDep,
    s: SessionDep,
    collection_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    starred: bool | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> PaperPage:
    out = await papers.list_papers(
        s, user, collection_id=collection_id, q=q, starred=starred, status=status,
        limit=limit, cursor=cursor,
    )  # fmt: skip
    return PaperPage(items=[PaperCard(**r) for r in out["items"]], next_cursor=out["next_cursor"])


@router.get("/{paper_id}")
async def get_paper(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> Paper:
    card = await papers.require_access(s, user, paper_id)
    secs = await repo.sections(s, paper_id)
    return Paper(**card, sections=[SectionOut(**x) for x in secs])


@router.patch("/{paper_id}")
async def patch_paper(paper_id: UUID, body: PaperPatch, user: CurrentUserDep, s: SessionDep) -> Paper:
    await papers.require_access(s, user, paper_id)
    await repo.update_link(s, user.id, paper_id, **body.model_dump(exclude_unset=True))
    await s.commit()
    return await get_paper(paper_id, user, s)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(paper_id: UUID, user: CurrentUserDep, s: SessionDep, providers: ProvidersDep) -> None:
    await papers.delete_paper(s, providers, user, paper_id)


@router.get("/{paper_id}/file")
async def get_file(
    paper_id: UUID,
    user: CurrentUserDep,
    s: SessionDep,
    settings: SettingsDep,
    providers: ProvidersDep,
) -> Response:
    card = await papers.require_access(s, user, paper_id)
    data = await ingest.paper_pdf(card, providers, settings)
    return Response(
        data,
        media_type="application/pdf",
        headers={"Cache-Control": "private, max-age=3600", "Content-Disposition": "inline"},
    )


@router.get("/{paper_id}/chunks")
async def list_chunks(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> list[ChunkOut]:
    await papers.require_access(s, user, paper_id)
    return [ChunkOut(**c) for c in await repo.all_chunks(s, paper_id)]


@router.get("/{paper_id}/chunks/{chunk_id}")
async def get_chunk(paper_id: UUID, chunk_id: UUID, user: CurrentUserDep, s: SessionDep) -> ChunkOut:
    await papers.require_access(s, user, paper_id)
    c = await repo.chunk(s, paper_id, chunk_id)
    if c is None:
        raise NotFound()
    return ChunkOut(**c)


@router.get("/{paper_id}/references")
async def references(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> list[ReferenceOut]:
    await papers.require_access(s, user, paper_id)
    refs = await repo.references(s, paper_id)
    return [ReferenceOut(**r) for r in refs]


@router.get("/{paper_id}/bibtex", response_class=PlainTextResponse)
async def bibtex(
    paper_id: UUID, user: CurrentUserDep, s: SessionDep,
    style: Literal["bibtex", "apa", "ieee"] = "bibtex",
) -> str:  # fmt: skip
    card = await papers.require_access(s, user, paper_id)
    return papers.bibtex(card, style)
