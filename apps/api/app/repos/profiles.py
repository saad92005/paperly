"""SQL access for profiles."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_COLS = "id, display_name, locale, explain_level, plan, is_admin, created_at"
_UPDATABLE = ("display_name", "locale", "explain_level")
# The auth.users trigger normally creates the row; this upsert covers users created before it.
_UPSERT = text(
    "insert into profiles (id) values (:id) "
    f"on conflict (id) do update set id = excluded.id returning {_COLS}"
)


async def get_or_create(session: AsyncSession, user_id: UUID) -> dict[str, Any]:
    row = (await session.execute(_UPSERT, {"id": user_id})).mappings().one()
    await session.commit()
    return dict(row)


async def update(session: AsyncSession, user_id: UUID, fields: dict[str, Any]) -> dict[str, Any]:
    # Column names come only from the fixed _UPDATABLE allow-list; values are bound parameters.
    allowed = {k: v for k, v in fields.items() if k in _UPDATABLE}
    if not allowed:
        return await get_or_create(session, user_id)
    sets = ", ".join(f"{k} = :{k}" for k in allowed)
    sql = text(f"update profiles set {sets} where id = :id returning {_COLS}")
    row = (await session.execute(sql, {**allowed, "id": user_id})).mappings().one()
    await session.commit()
    return dict(row)
