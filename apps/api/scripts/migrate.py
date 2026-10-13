"""Apply db/migrations/*.sql in order, once each, recording them in schema_migrations.

Usage: uv run python scripts/migrate.py [--status]
Each file runs in its own transaction. Never edit a migration that has been applied.
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

from app.config import get_settings

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"


def plain_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def migrate(url: str, *, status_only: bool = False) -> list[str]:
    conn = await asyncpg.connect(plain_url(url), statement_cache_size=0)
    try:
        await conn.execute(
            "create table if not exists schema_migrations ("
            " version text primary key, applied_at timestamptz not null default now())"
        )
        done = {r["version"] for r in await conn.fetch("select version from schema_migrations")}
        pending = [f for f in sorted(MIGRATIONS.glob("*.sql")) if f.stem not in done]
        if status_only:
            return [f.stem for f in pending]
        for f in pending:
            async with conn.transaction():
                await conn.execute(f.read_text(encoding="utf-8"))
                await conn.execute("insert into schema_migrations (version) values ($1)", f.stem)
            print(f"applied {f.name}")
        return [f.stem for f in pending]
    finally:
        await conn.close()


def main() -> None:
    url = get_settings().database_url
    if not url:
        sys.exit("DATABASE_URL is not set in .env")
    status_only = "--status" in sys.argv
    names = asyncio.run(migrate(url, status_only=status_only))
    if status_only:
        print("pending:", ", ".join(names) or "none")
    elif not names:
        print("database is up to date")


if __name__ == "__main__":
    main()
