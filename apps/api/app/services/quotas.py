"""Daily quotas per user (docs/02, docs/04 §1). Counters live in usage_daily (UTC days)."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import AppError

Kind = Literal["questions", "imports", "compares"]


class QuotaExceeded(AppError):
    code, status = "quota_exceeded", 429


def _limit(settings: Settings, kind: Kind) -> int:
    return {
        "questions": settings.quota_questions_per_day,
        "imports": settings.quota_imports_per_day,
        "compares": settings.quota_compares_per_day,
    }[kind]


def reset_at() -> str:
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
    return f"{tomorrow.isoformat()}T00:00:00Z"


async def usage(s: AsyncSession, user_id: UUID) -> dict[str, Any]:
    row = (
        (
            await s.execute(
                text(
                    "select questions, imports, compares, tokens from usage_daily "
                    "where user_id = :u and day = (now() at time zone 'utc')::date"
                ),
                {"u": user_id},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else {"questions": 0, "imports": 0, "compares": 0, "tokens": 0}


async def consume(s: AsyncSession, settings: Settings, user_id: UUID, kind: Kind, n: int = 1) -> int:
    """Atomically take `n` units; raises QuotaExceeded if over the limit. Returns remaining."""
    limit = _limit(settings, kind)
    row = (
        await s.execute(
            text(
                f"insert into usage_daily (user_id, day, {kind}) "
                "values (:u, (now() at time zone 'utc')::date, :n) "
                f"on conflict (user_id, day) do update set {kind} = usage_daily.{kind} + :n "
                f"where usage_daily.{kind} + :n <= :lim returning {kind}"
            ),
            {"u": user_id, "n": n, "lim": limit},
        )
    ).first()
    if row is None or row[0] > limit:
        await s.rollback()
        noun = {"questions": "question", "imports": "import", "compares": "comparison"}[kind]
        raise QuotaExceeded(
            f"Daily {noun} limit reached. Resets at 00:00 UTC.",
            {"reset_at": reset_at(), "limit": limit},
        )
    return limit - int(row[0])


async def add_tokens(s: AsyncSession, user_id: UUID, tokens: int) -> None:
    await s.execute(
        text(
            "insert into usage_daily (user_id, day, tokens) "
            "values (:u, (now() at time zone 'utc')::date, :t) "
            "on conflict (user_id, day) do update set tokens = usage_daily.tokens + :t"
        ),
        {"u": user_id, "t": tokens},
    )
