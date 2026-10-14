from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.config import Settings, get_settings
from app.deps import ProvidersDep, SessionDep
from app.errors import NotFound
from app.repos import chat as repo
from app.services import chat
from app.services.papers import decode_cursor

router = APIRouter(prefix="/v1", tags=["chat"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class Scope(BaseModel):
    paper_ids: list[UUID] | None = None
    collection_id: UUID | None = None


class ThreadIn(BaseModel):
    scope: Scope
    title: str | None = Field(default=None, max_length=200)


class Thread(BaseModel):
    id: UUID
    title: str | None
    scope: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict[str, Any]]
    grounded: bool | None
    support_score: float | None
    provider: str | None
    model: str | None
    latency_ms: int | None
    created_at: datetime


class ThreadDetail(Thread):
    messages: list[Message]


class ThreadPage(BaseModel):
    items: list[Thread]
    next_cursor: str | None


class Selection(BaseModel):
    paper_id: UUID
    page: int
    text: str = Field(max_length=4000)


class AskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    mode: Literal["grounded", "strict"] = "grounded"
    level: Literal["eli5", "student", "expert"] | None = None
    lang: str = Field(default="en", max_length=8)
    selection: Selection | None = None


class FeedbackIn(BaseModel):
    rating: Literal[1, -1]
    reason: str | None = Field(default=None, max_length=500)


@router.post("/threads")
async def create_thread(body: ThreadIn, user: CurrentUserDep, s: SessionDep) -> Thread:
    scope = body.scope.model_dump(mode="json", exclude_none=True)
    return Thread(**await chat.create_thread(s, user, scope, body.title))


@router.get("/threads")
async def list_threads(
    user: CurrentUserDep, s: SessionDep, paper_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30, cursor: str | None = None,
) -> ThreadPage:  # fmt: skip
    off = decode_cursor(cursor)
    rows = await repo.list_threads(s, user.id, paper_id, limit, off)
    from app.services.papers import _cursor  # pyright: ignore[reportPrivateUsage]

    return ThreadPage(
        items=[Thread(**r) for r in rows[:limit]],
        next_cursor=_cursor(off + limit) if len(rows) > limit else None,
    )


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: UUID, user: CurrentUserDep, s: SessionDep) -> ThreadDetail:
    t = await repo.get_thread(s, user.id, thread_id)
    if t is None:
        raise NotFound()
    msgs = await repo.messages(s, thread_id)
    return ThreadDetail(**t, messages=[Message(**m) for m in msgs])


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: UUID, user: CurrentUserDep, s: SessionDep) -> None:
    if not await repo.delete_thread(s, user.id, thread_id):
        raise NotFound()
    await s.commit()


@router.post("/threads/{thread_id}/messages")
async def ask(
    thread_id: UUID, body: AskIn, user: CurrentUserDep, s: SessionDep, settings: SettingsDep,
    providers: ProvidersDep,
) -> StreamingResponse:  # fmt: skip
    t = await repo.get_thread(s, user.id, thread_id)
    if t is None:
        raise NotFound()
    remaining = await chat.check_quota(s, settings, user)
    await s.commit()
    level = body.level
    if level is None:
        from app.repos import profiles

        level = (await profiles.get_or_create(s, user.id))["explain_level"]
    gen = chat.ask(
        s, settings, providers, user, t, body.content, mode=body.mode, level=level or "student",
        lang=body.lang, selection=body.selection.model_dump(mode="json") if body.selection else None,
    )  # fmt: skip
    headers = {**STREAM_HEADERS, "X-Quota-Questions-Remaining": str(remaining)}
    return StreamingResponse(gen, media_type="text/event-stream", headers=headers)


@router.post("/messages/{message_id}/feedback", status_code=204)
async def feedback(message_id: UUID, body: FeedbackIn, user: CurrentUserDep, s: SessionDep) -> None:
    if await repo.get_message_for_user(s, user.id, message_id) is None:
        raise NotFound()
    await repo.set_feedback(s, user.id, message_id, body.rating, body.reason)
    await s.commit()
