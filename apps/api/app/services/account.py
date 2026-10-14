"""Account deletion job: remove private blobs, then the auth user (cascades to all owned rows)."""

from typing import Any
from uuid import UUID

from sqlalchemy import text

from app import db
from app.jobs.worker import JobContext
from app.providers.registry import Providers


def make_delete_account_handler(providers: Providers):
    async def handle(job: dict[str, Any], ctx: JobContext) -> None:
        uid = UUID(job["payload"]["user_id"])
        async with db.get_engine().begin() as conn:
            paths = (
                (
                    await conn.execute(
                        text("select blob_path from papers where owner_id = :u and blob_path is not null"),
                        {"u": uid},
                    )
                )
                .scalars()
                .all()
            )
        for p in paths:
            await providers.blobs.delete(p)
        async with db.get_engine().begin() as conn:
            await conn.execute(text('delete from "user" where id = :u'), {"u": uid})

    return handle
