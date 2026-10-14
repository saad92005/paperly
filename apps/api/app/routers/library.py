"""Notes, collections, summaries, glossary, explain, flashcards, references and cited-by."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.auth import CurrentUserDep
from app.config import Settings, get_settings
from app.deps import ProvidersDep, SessionDep, wake_worker
from app.errors import Invalid, NotFound
from app.jobs import queue
from app.repos import chat as chat_repo
from app.repos import library as repo
from app.repos import study as study_repo
from app.services import discover, quotas, study
from app.services.papers import require_access

router = APIRouter(prefix="/v1", tags=["library"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
Color = Literal["yellow", "green", "blue", "pink", "purple"]


class Anchor(BaseModel):
    page: int = Field(ge=1)
    rects: list[list[float]] = Field(default_factory=lambda: [], max_length=50)
    text: str = Field(default="", max_length=4000)


class NoteIn(BaseModel):
    anchor: Anchor | None = None
    body_md: str = Field(default="", max_length=20000)
    color: Color = "yellow"


class NotePatch(BaseModel):
    body_md: str | None = Field(default=None, max_length=20000)
    color: Color | None = None


class Note(BaseModel):
    id: UUID
    paper_id: UUID
    anchor: dict[str, Any] | None
    body_md: str
    color: str
    origin: str
    created_at: datetime
    updated_at: datetime


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class CollectionPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class Collection(BaseModel):
    id: UUID
    name: str
    description: str | None
    paper_count: int
    created_at: datetime


class ExplainIn(BaseModel):
    text: str = Field(min_length=2, max_length=4000)
    page: int = Field(ge=1)
    kind: Literal["explain", "simplify", "translate", "equation"] = "explain"
    lang: str = Field(default="en", max_length=8)
    level: Literal["eli5", "student", "expert"] = "student"


class FlashcardsIn(BaseModel):
    count: int = Field(default=10, ge=5, le=30)


class ReviewIn(BaseModel):
    grade: int = Field(ge=0, le=5)


class SaveNoteIn(BaseModel):
    paper_id: UUID


# ---------- Notes ----------


@router.get("/papers/{paper_id}/notes")
async def list_notes(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> list[Note]:
    await require_access(s, user, paper_id)
    return [Note(**n) for n in await repo.list_notes(s, user.id, paper_id)]


@router.post("/papers/{paper_id}/notes", status_code=201)
async def create_note(paper_id: UUID, body: NoteIn, user: CurrentUserDep, s: SessionDep) -> Note:
    await require_access(s, user, paper_id)
    n = await repo.create_note(
        s,
        user.id,
        paper_id,
        body.anchor.model_dump() if body.anchor else None,
        body.body_md,
        body.color,
        "manual",
    )
    await s.commit()
    return Note(**n)


@router.patch("/notes/{note_id}")
async def patch_note(note_id: UUID, body: NotePatch, user: CurrentUserDep, s: SessionDep) -> Note:
    n = await repo.update_note(s, user.id, note_id, body.body_md, body.color)
    if n is None:
        raise NotFound()
    await s.commit()
    return Note(**n)


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: UUID, user: CurrentUserDep, s: SessionDep) -> None:
    if not await repo.delete_note(s, user.id, note_id):
        raise NotFound()
    await s.commit()


@router.get("/papers/{paper_id}/notes/export", response_class=PlainTextResponse)
async def export_notes(
    paper_id: UUID, user: CurrentUserDep, s: SessionDep, format: Literal["md"] = "md"
) -> str:
    card = await require_access(s, user, paper_id)
    notes = await repo.list_notes(s, user.id, paper_id)
    lines = [f"# Notes — {card['title'] or 'Untitled paper'}", ""]
    for n in notes:
        a = n["anchor"] or {}
        where = f"p.{a['page']}" if a.get("page") else "General"
        lines.append(f"## {where}" + (" · AI" if n["origin"] == "ai" else ""))
        if a.get("text"):
            lines.append("> " + a["text"].replace("\n", " "))
        if n["body_md"]:
            lines += ["", n["body_md"]]
        lines.append("")
    return "\n".join(lines)


@router.post("/messages/{message_id}/save-note", status_code=201)
async def save_message_as_note(
    message_id: UUID, body: SaveNoteIn, user: CurrentUserDep, s: SessionDep
) -> Note:
    m = await chat_repo.get_message_for_user(s, user.id, message_id)
    if m is None or m["role"] != "assistant":
        raise NotFound()
    await require_access(s, user, body.paper_id)
    cits = [c for c in m["citations"] if c.get("paper_id") == str(body.paper_id)]
    anchor = None
    if cits:
        c = cits[0]
        anchor = {"page": c["page"], "rects": [r["rect"] for r in c.get("rects", []) if r["page"] == c["page"]],
                  "text": c.get("quote", "")[:1000]}  # fmt: skip
    pages = sorted({c["page"] for c in cits})
    body_md = m["content"] + (f"\n\n_Sources: p.{', p.'.join(map(str, pages))}_" if pages else "")
    n = await repo.create_note(s, user.id, body.paper_id, anchor, body_md, "blue", "ai")
    await s.commit()
    return Note(**n)


# ---------- Collections ----------


@router.get("/collections")
async def list_collections(user: CurrentUserDep, s: SessionDep) -> list[Collection]:
    return [Collection(**c) for c in await repo.list_collections(s, user.id)]


@router.post("/collections", status_code=201)
async def create_collection(body: CollectionIn, user: CurrentUserDep, s: SessionDep) -> Collection:
    c = await repo.create_collection(s, user.id, body.name.strip(), body.description)
    await s.commit()
    return Collection(**c)


@router.patch("/collections/{cid}")
async def patch_collection(
    cid: UUID, body: CollectionPatch, user: CurrentUserDep, s: SessionDep
) -> Collection:
    c = await repo.update_collection(s, user.id, cid, body.name, body.description)
    if c is None:
        raise NotFound()
    await s.commit()
    return Collection(**c)


@router.delete("/collections/{cid}", status_code=204)
async def delete_collection(cid: UUID, user: CurrentUserDep, s: SessionDep) -> None:
    if not await repo.delete_collection(s, user.id, cid):
        raise NotFound()
    await s.commit()


# ---------- Summaries, glossary, explain ----------


@router.get("/papers/{paper_id}/summary")
async def get_summary(
    paper_id: UUID, user: CurrentUserDep, s: SessionDep, providers: ProvidersDep,
    kind: Literal["structured", "glossary"] = "structured", lang: str = "en",
    level: Literal["eli5", "student", "expert"] = "student",
) -> dict[str, Any]:  # fmt: skip
    card = await require_access(s, user, paper_id)
    if card["status"] != "ready":
        raise Invalid("The paper is still being indexed.")
    if kind == "glossary":
        return await study.glossary(s, providers, paper_id, level)
    return await study.get_or_build_summary(s, providers, paper_id, lang, level)


@router.post("/papers/{paper_id}/summary/regenerate", status_code=202)
async def regenerate_summary(
    request: Request, paper_id: UUID, user: CurrentUserDep, s: SessionDep, lang: str = "en",
    level: Literal["eli5", "student", "expert"] = "student",
) -> dict[str, Any]:  # fmt: skip
    await require_access(s, user, paper_id)
    job_id = await queue.enqueue(
        s,
        "build_summary",
        {"paper_id": str(paper_id), "lang": lang, "level": level, "force": True},
        user.id,
        3,
    )
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id}


@router.post("/papers/{paper_id}/explain")
async def explain(
    paper_id: UUID, body: ExplainIn, user: CurrentUserDep, s: SessionDep, settings: SettingsDep,
    providers: ProvidersDep,
) -> StreamingResponse:  # fmt: skip
    await require_access(s, user, paper_id)
    await quotas.consume(s, settings, user.id, "questions")
    await s.commit()
    gen = study.explain(s, providers, user, paper_id, body.text, body.page, body.kind, body.lang, body.level)
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ---------- Flashcards ----------


@router.post("/papers/{paper_id}/flashcards", status_code=202)
async def make_flashcards(
    request: Request, paper_id: UUID, body: FlashcardsIn, user: CurrentUserDep, s: SessionDep,
    providers: ProvidersDep,
) -> dict[str, Any]:  # fmt: skip
    await require_access(s, user, paper_id)
    if not providers.llm.available:
        raise study.NoProvider()
    job_id = await queue.enqueue(
        s, "flashcards", {"paper_id": str(paper_id), "count": body.count}, user.id, 3
    )
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id}


@router.get("/papers/{paper_id}/flashcards")
async def paper_flashcards(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> list[dict[str, Any]]:
    await require_access(s, user, paper_id)
    return await study_repo.all_cards(s, user.id, paper_id)


@router.get("/flashcards/due")
async def due_flashcards(
    user: CurrentUserDep, s: SessionDep, paper_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict[str, Any]]:  # fmt: skip
    return await study_repo.due_cards(s, user.id, paper_id, limit)


@router.post("/flashcards/{card_id}/review")
async def review_card(card_id: UUID, body: ReviewIn, user: CurrentUserDep, s: SessionDep) -> dict[str, Any]:
    c = await study_repo.get_card(s, user.id, card_id)
    if c is None:
        raise NotFound()
    ease, interval, reps = study.sm2(c["ease"], c["interval_d"], c["reps"], body.grade)
    await study_repo.update_card(s, card_id, ease, interval, reps)
    await s.commit()
    return {"id": card_id, "ease": ease, "interval_d": interval, "reps": reps}


@router.get("/papers/{paper_id}/flashcards/anki", response_class=PlainTextResponse)
async def anki_export(paper_id: UUID, user: CurrentUserDep, s: SessionDep) -> PlainTextResponse:
    await require_access(s, user, paper_id)
    cards = await study_repo.all_cards(s, user.id, paper_id)

    def clean(x: str) -> str:
        return x.replace("\t", " ").replace("\n", "<br>")

    lines = ["#separator:tab", "#html:true"]
    for c in cards:
        page = (c.get("citation") or {}).get("page")
        back = clean(c["back"]) + (f"<br><small>p.{page}</small>" if page else "")
        lines.append(f"{clean(c['front'])}\t{back}")
    return PlainTextResponse(
        "\n".join(lines) + "\n", headers={"Content-Disposition": 'attachment; filename="paperly-cards.txt"'}
    )


# ---------- References and cited-by ----------


@router.get("/papers/{paper_id}/citations")
async def cited_by(
    paper_id: UUID, user: CurrentUserDep, s: SessionDep, settings: SettingsDep
) -> list[dict[str, Any]]:
    card = await require_access(s, user, paper_id)
    return await discover.cited_by(s, settings, card)
