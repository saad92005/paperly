"""SQL for threads, messages, feedback and the LLM cache."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

THREAD_COLS = "id, user_id, title, scope, created_at, updated_at"
MSG_COLS = (
    "id, thread_id, role, content, citations, grounded, support_score, provider, model, "
    "prompt_tokens, completion_tokens, latency_ms, created_at"
)


async def create_thread(
    s: AsyncSession, user_id: UUID, scope: dict[str, Any], title: str | None
) -> dict[str, Any]:
    row = (
        (
            await s.execute(
                text(
                    "insert into threads (user_id, scope, title) values (:u, cast(:sc as jsonb), :t) "
                    f"returning {THREAD_COLS}"
                ),
                {"u": user_id, "sc": json.dumps(scope), "t": title},
            )
        )
        .mappings()
        .one()
    )
    return dict(row)


async def get_thread(s: AsyncSession, user_id: UUID, thread_id: UUID) -> dict[str, Any] | None:
    row = (
        (
            await s.execute(
                text(f"select {THREAD_COLS} from threads where id = :id and user_id = :u"),
                {"id": thread_id, "u": user_id},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def list_threads(
    s: AsyncSession, user_id: UUID, paper_id: UUID | None, limit: int, offset: int
) -> list[dict[str, Any]]:
    where = "user_id = :u"
    params: dict[str, Any] = {"u": user_id, "lim": limit + 1, "off": offset}
    if paper_id:
        where += " and scope->'paper_ids' ? :pid"
        params["pid"] = str(paper_id)
    sql = f"select {THREAD_COLS} from threads where {where} order by updated_at desc limit :lim offset :off"
    return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


async def delete_thread(s: AsyncSession, user_id: UUID, thread_id: UUID) -> bool:
    res = await s.execute(
        text("delete from threads where id = :id and user_id = :u"), {"id": thread_id, "u": user_id}
    )
    return bool(res.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


async def messages(s: AsyncSession, thread_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
    sql = f"select {MSG_COLS} from messages where thread_id = :t order by created_at limit :lim"
    return [dict(r) for r in (await s.execute(text(sql), {"t": thread_id, "lim": limit})).mappings().all()]


async def add_message(s: AsyncSession, thread_id: UUID, role: str, content: str, **f: Any) -> UUID:
    cols = {"thread_id": thread_id, "role": role, "content": content, **f}
    if "citations" in cols:
        cols["citations"] = json.dumps(cols["citations"])
    names = ", ".join(cols)
    vals = ", ".join(f"cast(:{k} as jsonb)" if k == "citations" else f":{k}" for k in cols)
    row = (await s.execute(text(f"insert into messages ({names}) values ({vals}) returning id"), cols)).one()
    await s.execute(text("update threads set updated_at = now() where id = :t"), {"t": thread_id})
    return row[0]


async def get_message_for_user(s: AsyncSession, user_id: UUID, message_id: UUID) -> dict[str, Any] | None:
    sql = (
        "select m.id, m.thread_id, m.role, m.content, m.citations from messages m "
        "join threads t on t.id = m.thread_id where m.id = :m and t.user_id = :u"
    )
    row = (await s.execute(text(sql), {"m": message_id, "u": user_id})).mappings().first()
    return dict(row) if row else None


async def set_feedback(
    s: AsyncSession, user_id: UUID, message_id: UUID, rating: int, reason: str | None
) -> None:
    await s.execute(
        text(
            "insert into feedback (message_id, user_id, rating, reason) values (:m, :u, :r, :why) "
            "on conflict (message_id, user_id) do update set "
            "rating = excluded.rating, reason = excluded.reason"
        ),
        {"m": message_id, "u": user_id, "r": rating, "why": reason},
    )


async def cache_get(s: AsyncSession, key: str) -> dict[str, Any] | None:
    row = (
        await s.execute(
            text("update llm_cache set hits = hits + 1 where key = :k returning value"), {"k": key}
        )
    ).first()
    return dict(row[0]) if row else None


async def cache_put(s: AsyncSession, key: str, value: dict[str, Any]) -> None:
    await s.execute(
        text(
            "insert into llm_cache (key, value) values (:k, cast(:v as jsonb)) "
            "on conflict (key) do update set value = excluded.value"
        ),
        {"k": key, "v": json.dumps(value, default=str)},
    )


async def record_provider_events(
    s: AsyncSession, events: list[tuple[str, str, str, bool, int | None, int]]
) -> None:
    if not events:
        return
    await s.execute(
        text(
            "insert into provider_events (provider, model, task, ok, status, latency_ms) "
            "values (:p, :m, :t, :ok, :st, :ms)"
        ),
        [{"p": p, "m": m, "t": t, "ok": ok, "st": st, "ms": ms} for p, m, t, ok, st, ms in events],
    )
