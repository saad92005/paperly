"""SQL for summaries and flashcards."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

Conn = AsyncSession | AsyncConnection


async def get_summary(s: Conn, paper_id: UUID, kind: str, lang: str, level: str) -> dict[str, Any] | None:
    row = (
        (
            await s.execute(
                text(
                    "select content, model, prompt_ver, created_at from summaries "
                    "where paper_id = :p and kind = :k and lang = :l and level = :lv"
                ),
                {"p": paper_id, "k": kind, "l": lang, "lv": level},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def put_summary(
    s: Conn, paper_id: UUID, kind: str, lang: str, level: str, content: dict[str, Any], model: str, ver: str
) -> None:
    await s.execute(
        text(
            "insert into summaries (paper_id, kind, lang, level, content, model, prompt_ver) "
            "values (:p, :k, :l, :lv, cast(:c as jsonb), :m, :v) "
            "on conflict (paper_id, kind, lang, level) do update set content = excluded.content, "
            "model = excluded.model, prompt_ver = excluded.prompt_ver, created_at = now()"
        ),
        {"p": paper_id, "k": kind, "l": lang, "lv": level, "c": json.dumps(content), "m": model, "v": ver},
    )


async def delete_summary(s: Conn, paper_id: UUID, kind: str, lang: str, level: str) -> None:
    await s.execute(
        text("delete from summaries where paper_id = :p and kind = :k and lang = :l and level = :lv"),
        {"p": paper_id, "k": kind, "l": lang, "lv": level},
    )


async def insert_cards(s: Conn, user_id: UUID, paper_id: UUID, cards: list[dict[str, Any]]) -> int:
    if not cards:
        return 0
    await s.execute(
        text(
            "insert into flashcards (user_id, paper_id, front, back, citation) "
            "values (:u, :p, :f, :b, cast(:c as jsonb))"
        ),
        [
            {"u": user_id, "p": paper_id, "f": c["front"], "b": c["back"], "c": json.dumps(c.get("citation"))}
            for c in cards
        ],
    )
    return len(cards)


CARD_COLS = "f.id, f.paper_id, f.front, f.back, f.citation, f.ease, f.interval_d, f.reps, f.due_at, p.title"


async def due_cards(s: Conn, user_id: UUID, paper_id: UUID | None, limit: int) -> list[dict[str, Any]]:
    where = "f.user_id = :u and f.due_at <= now()"
    params: dict[str, Any] = {"u": user_id, "lim": limit}
    if paper_id:
        where += " and f.paper_id = :p"
        params["p"] = paper_id
    sql = (
        f"select {CARD_COLS} as paper_title from flashcards f join papers p on p.id = f.paper_id "
        f"where {where} order by f.due_at limit :lim"
    )
    return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


async def all_cards(s: Conn, user_id: UUID, paper_id: UUID) -> list[dict[str, Any]]:
    sql = (
        f"select {CARD_COLS} as paper_title from flashcards f join papers p on p.id = f.paper_id "
        "where f.user_id = :u and f.paper_id = :p order by f.due_at"
    )
    return [dict(r) for r in (await s.execute(text(sql), {"u": user_id, "p": paper_id})).mappings().all()]


async def get_card(s: Conn, user_id: UUID, card_id: UUID) -> dict[str, Any] | None:
    sql = (
        f"select {CARD_COLS} as paper_title from flashcards f join papers p on p.id = f.paper_id "
        "where f.user_id = :u and f.id = :id"
    )
    row = (await s.execute(text(sql), {"u": user_id, "id": card_id})).mappings().first()
    return dict(row) if row else None


async def update_card(s: Conn, card_id: UUID, ease: float, interval_d: int, reps: int) -> None:
    await s.execute(
        text(
            "update flashcards set ease = :e, interval_d = :i, reps = :r, "
            "due_at = now() + make_interval(days => :i) where id = :id"
        ),
        {"e": ease, "i": interval_d, "r": reps, "id": card_id},
    )


async def delete_cards(s: Conn, user_id: UUID, paper_id: UUID) -> None:
    await s.execute(
        text("delete from flashcards where user_id = :u and paper_id = :p"), {"u": user_id, "p": paper_id}
    )
