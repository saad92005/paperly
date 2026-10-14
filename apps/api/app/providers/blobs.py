"""PDF blob storage in Postgres (ADR-008). Small free-tier scale; swap for S3/R2 behind the Protocol."""

from sqlalchemy import text

from app import db


class PgBlobStore:
    async def put(self, path: str, data: bytes, content_type: str) -> None:
        async with db.get_engine().begin() as conn:
            await conn.execute(
                text(
                    "insert into blobs (path, content_type, size_bytes, data) values (:p, :c, :n, :d) "
                    "on conflict (path) do update set data = excluded.data, size_bytes = excluded.size_bytes"
                ),
                {"p": path, "c": content_type, "n": len(data), "d": data},
            )

    async def get(self, path: str) -> bytes | None:
        async with db.get_engine().connect() as conn:
            row = (await conn.execute(text("select data from blobs where path = :p"), {"p": path})).first()
        return bytes(row[0]) if row else None

    async def delete(self, path: str) -> None:
        async with db.get_engine().begin() as conn:
            await conn.execute(text("delete from blobs where path = :p"), {"p": path})


class MemoryBlobStore:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    async def put(self, path: str, data: bytes, content_type: str) -> None:
        self.items[path] = data

    async def get(self, path: str) -> bytes | None:
        return self.items.get(path)

    async def delete(self, path: str) -> None:
        self.items.pop(path, None)
