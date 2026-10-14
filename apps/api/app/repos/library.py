"""SQL for notes, collections, comparisons, shares and admin metrics."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

Conn = AsyncSession | AsyncConnection

NOTE_COLS = "id, paper_id, anchor, body_md, color, origin, created_at, updated_at"


async def _one(s: Conn, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
    row = (await s.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


async def _all(s: Conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


# Notes
async def list_notes(s: Conn, user_id: UUID, paper_id: UUID) -> list[dict[str, Any]]:
    return await _all(
        s,
        f"select {NOTE_COLS} from notes where user_id = :u and paper_id = :p "
        "order by coalesce((anchor->>'page')::int, 0), created_at",
        {"u": user_id, "p": paper_id},
    )


async def create_note(
    s: Conn, user_id: UUID, paper_id: UUID, anchor: dict[str, Any] | None, body: str, color: str, origin: str
) -> dict[str, Any]:
    row = await _one(
        s,
        "insert into notes (user_id, paper_id, anchor, body_md, color, origin) "
        f"values (:u, :p, cast(:a as jsonb), :b, :c, :o) returning {NOTE_COLS}",
        {"u": user_id, "p": paper_id, "a": json.dumps(anchor) if anchor else None, "b": body, "c": color,
         "o": origin},
    )  # fmt: skip
    assert row is not None
    return row


async def update_note(
    s: Conn, user_id: UUID, note_id: UUID, body: str | None, color: str | None
) -> dict[str, Any] | None:
    return await _one(
        s,
        "update notes set body_md = coalesce(:b, body_md), color = coalesce(:c, color), updated_at = now() "
        f"where id = :id and user_id = :u returning {NOTE_COLS}",
        {"b": body, "c": color, "id": note_id, "u": user_id},
    )


async def delete_note(s: Conn, user_id: UUID, note_id: UUID) -> bool:
    res = await s.execute(
        text("delete from notes where id = :id and user_id = :u"), {"id": note_id, "u": user_id}
    )
    return bool(res.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


# Collections
async def list_collections(s: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return await _all(
        s,
        "select c.id, c.name, c.description, c.created_at, "
        "(select count(*) from user_papers up where up.collection_id = c.id) as paper_count "
        "from collections c where c.owner_id = :u order by c.name",
        {"u": user_id},
    )


async def create_collection(s: Conn, user_id: UUID, name: str, description: str | None) -> dict[str, Any]:
    row = await _one(
        s,
        "insert into collections (owner_id, name, description) values (:u, :n, :d) "
        "returning id, name, description, created_at, 0 as paper_count",
        {"u": user_id, "n": name, "d": description},
    )
    assert row is not None
    return row


async def update_collection(
    s: Conn, user_id: UUID, cid: UUID, name: str | None, description: str | None
) -> dict[str, Any] | None:
    return await _one(
        s,
        "update collections set name = coalesce(:n, name), description = coalesce(:d, description) "
        "where id = :id and owner_id = :u returning id, name, description, created_at, "
        "(select count(*) from user_papers up where up.collection_id = collections.id) as paper_count",
        {"n": name, "d": description, "id": cid, "u": user_id},
    )


async def delete_collection(s: Conn, user_id: UUID, cid: UUID) -> bool:
    res = await s.execute(
        text("delete from collections where id = :id and owner_id = :u"), {"id": cid, "u": user_id}
    )
    return bool(res.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


async def owns_collection(s: Conn, user_id: UUID, cid: UUID) -> bool:
    return (
        await _one(
            s, "select 1 as x from collections where id = :id and owner_id = :u", {"id": cid, "u": user_id}
        )
        is not None
    )


# Comparisons
CMP_COLS = "id, user_id, title, paper_ids, columns, cells, status, share_id, created_at"


async def create_comparison(
    s: Conn, user_id: UUID, title: str | None, paper_ids: list[UUID], columns: list[dict[str, str]]
) -> dict[str, Any]:
    row = await _one(
        s,
        "insert into comparisons (user_id, title, paper_ids, columns) values (:u, :t, :p, cast(:c as jsonb)) "
        f"returning {CMP_COLS}",
        {"u": user_id, "t": title, "p": paper_ids, "c": json.dumps(columns)},
    )
    assert row is not None
    return row


async def get_comparison(s: Conn, cid: UUID, user_id: UUID | None = None) -> dict[str, Any] | None:
    sql = f"select {CMP_COLS} from comparisons where id = :id"
    params: dict[str, Any] = {"id": cid}
    if user_id is not None:
        sql += " and user_id = :u"
        params["u"] = user_id
    return await _one(s, sql, params)


async def list_comparisons(s: Conn, user_id: UUID) -> list[dict[str, Any]]:
    return await _all(s, f"select {CMP_COLS} from comparisons where user_id = :u order by created_at desc limit 50",
                      {"u": user_id})  # fmt: skip


async def set_cells(s: Conn, cid: UUID, paper_id: str, cells: dict[str, Any]) -> None:
    await s.execute(
        text(
            "update comparisons set cells = jsonb_set(cells, array[:p], coalesce(cells->:p, '{}'::jsonb) || cast(:c as jsonb)) "
            "where id = :id"
        ),
        {"p": paper_id, "c": json.dumps(cells), "id": cid},
    )


async def set_comparison(s: Conn, cid: UUID, **f: Any) -> None:
    allowed = {k: v for k, v in f.items() if k in ("status", "columns", "share_id", "title")}
    if "columns" in allowed:
        allowed["columns"] = json.dumps(allowed["columns"])
    sets = ", ".join(f"{k} = cast(:{k} as jsonb)" if k == "columns" else f"{k} = :{k}" for k in allowed)
    await s.execute(text(f"update comparisons set {sets} where id = :id"), {**allowed, "id": cid})


async def delete_comparison(s: Conn, user_id: UUID, cid: UUID) -> bool:
    res = await s.execute(
        text("delete from comparisons where id = :id and user_id = :u"), {"id": cid, "u": user_id}
    )
    return bool(res.rowcount)  # pyright: ignore[reportAttributeAccessIssue]


# Shares
async def create_share(s: Conn, share_id: str, user_id: UUID, kind: str, ref_id: UUID) -> None:
    await s.execute(
        text("insert into shares (id, user_id, kind, ref_id) values (:id, :u, :k, :r)"),
        {"id": share_id, "u": user_id, "k": kind, "r": ref_id},
    )


async def find_share(s: Conn, user_id: UUID, kind: str, ref_id: UUID) -> str | None:
    row = await _one(s, "select id from shares where user_id = :u and kind = :k and ref_id = :r",
                     {"u": user_id, "k": kind, "r": ref_id})  # fmt: skip
    return row["id"] if row else None


async def get_share(s: Conn, share_id: str) -> dict[str, Any] | None:
    return await _one(
        s, "select id, user_id, kind, ref_id, created_at from shares where id = :id", {"id": share_id}
    )


# Admin
async def metrics(s: Conn) -> dict[str, Any]:
    one = await _one(
        s,
        'select (select count(*) from "user") as users, (select count(*) from papers) as papers, '
        "(select count(*) from chunks) as chunks, (select count(*) from messages where role = 'assistant') as answers, "
        "(select pg_database_size(current_database())) as db_bytes, "
        "(select coalesce(sum(size_bytes), 0) from blobs) as blob_bytes, "
        "(select count(*) from feedback where rating = 1) as thumbs_up, "
        "(select count(*) from feedback where rating = -1) as thumbs_down",
        {},
    )
    jobs = await _all(s, "select status::text, count(*) as n from jobs group by status", {})
    providers = await _all(
        s,
        "select provider, count(*) as calls, avg(case when ok then 0 else 1 end) as error_rate, "
        "percentile_cont(0.95) within group (order by latency_ms) as p95_ms "
        "from provider_events where created_at > now() - interval '7 days' group by provider",
        {},
    )
    latency = await _one(
        s,
        "select percentile_cont(0.5) within group (order by latency_ms) as p50_ms, "
        "percentile_cont(0.95) within group (order by latency_ms) as p95_ms, "
        "avg(case when grounded then 1.0 else 0.0 end) as grounded_rate "
        "from messages where role = 'assistant' and created_at > now() - interval '7 days'",
        {},
    )
    quota = await _one(
        s,
        "select count(*) as quota_hits from usage_daily where day = (now() at time zone 'utc')::date "
        "and questions >= 50",
        {},
    )
    return {**(one or {}), "jobs": {j["status"]: j["n"] for j in jobs}, "providers": providers,
            "answers_7d": latency, **(quota or {})}  # fmt: skip


async def failed_jobs(s: Conn, limit: int = 50) -> list[dict[str, Any]]:
    return await _all(
        s,
        "select id, type, payload, user_id, status::text, attempts, error, updated_at from jobs "
        "where status = 'failed' order by updated_at desc limit :lim",
        {"lim": limit},
    )


async def retry_job(s: Conn, job_id: UUID) -> bool:
    res = await s.execute(
        text(
            "update jobs set status = 'queued', attempts = 0, error = null, run_after = now(), updated_at = now() "
            "where id = :id and status = 'failed'"
        ),
        {"id": job_id},
    )
    return bool(res.rowcount)  # pyright: ignore[reportAttributeAccessIssue]
