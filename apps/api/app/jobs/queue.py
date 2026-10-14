"""Postgres job queue (docs/02 §3.3): `for update skip locked`, retries with backoff, progress."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

MAX_ATTEMPTS = 3
STALE_MINUTES = 10

_COLS = "id, type, payload, user_id, status, priority, progress, stage, attempts, error, created_at"


async def enqueue(
    s: AsyncSession | AsyncConnection,
    type_: str,
    payload: dict[str, Any],
    user_id: UUID | None,
    priority: int = 5,
) -> UUID:
    row = (
        await s.execute(
            text(
                "insert into jobs (type, payload, user_id, priority) "
                "values (:t, cast(:p as jsonb), :u, :pr) returning id"
            ),
            {"t": type_, "p": json.dumps(payload, default=str), "u": user_id, "pr": priority},
        )
    ).one()
    return row[0]


async def claim(conn: AsyncConnection) -> dict[str, Any] | None:
    row = (
        (
            await conn.execute(
                text(
                    "update jobs set status = 'running', locked_at = now(), "
                    "attempts = attempts + 1, updated_at = now() "
                    "where id = (select id from jobs where status = 'queued' and run_after <= now() "
                    "order by priority, run_after for update skip locked limit 1) "
                    f"returning {_COLS}"
                )
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def recover_stale(conn: AsyncConnection) -> int:
    res = await conn.execute(
        text(
            "update jobs set status = 'queued', locked_at = null, updated_at = now() "
            f"where status = 'running' and locked_at < now() - interval '{STALE_MINUTES} minutes'"
        )
    )
    return res.rowcount or 0  # pyright: ignore[reportAttributeAccessIssue]


async def progress(conn: AsyncConnection, job_id: UUID, stage: str, pct: int) -> None:
    await conn.execute(
        text("update jobs set stage = :s, progress = :p, updated_at = now() where id = :id"),
        {"s": stage, "p": max(0, min(100, pct)), "id": job_id},
    )


async def succeed(conn: AsyncConnection, job_id: UUID) -> None:
    await conn.execute(
        text(
            "update jobs set status = 'succeeded', progress = 100, stage = 'done', "
            "error = null, locked_at = null, updated_at = now() where id = :id"
        ),
        {"id": job_id},
    )


async def fail(conn: AsyncConnection, job: dict[str, Any], error: str, retryable: bool) -> bool:
    """Returns True when the job will be retried."""
    retry = retryable and job["attempts"] < MAX_ATTEMPTS
    if retry:
        backoff = 10 * (3 ** (job["attempts"] - 1))
        await conn.execute(
            text(
                "update jobs set status = 'queued', error = :e, locked_at = null, "
                "run_after = now() + make_interval(secs => :b), updated_at = now() where id = :id"
            ),
            {"e": error[:500], "b": backoff, "id": job["id"]},
        )
    else:
        await conn.execute(
            text(
                "update jobs set status = 'failed', error = :e, locked_at = null, "
                "updated_at = now() where id = :id"
            ),
            {"e": error[:500], "id": job["id"]},
        )
    return retry


async def get(s: AsyncSession, job_id: UUID, user_id: UUID | None) -> dict[str, Any] | None:
    sql = f"select {_COLS} from jobs where id = :id"
    params: dict[str, Any] = {"id": job_id}
    if user_id is not None:
        sql += " and user_id = :u"
        params["u"] = user_id
    row = (await s.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None
