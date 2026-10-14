"""Cross-user access control against a real Postgres (docs/08: "tests for cross-user access").

Runs when TEST_DATABASE_URL points at a migrated database (CI's migrations job sets it).
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.auth import CurrentUser
from app.errors import NotFound
from app.repos import chat as chat_repo
from app.repos import library as lib_repo
from app.repos import papers as papers_repo
from app.services import chat, papers

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def s() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(URL, connect_args={"statement_cache_size": 0})
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


async def make_user(s: AsyncSession) -> CurrentUser:
    uid = uuid.uuid4()
    await s.execute(
        text('insert into "user" (id, name, email, "emailVerified") values (:i, :n, :e, true)'),
        {"i": uid, "n": "t", "e": f"{uid.hex}@test.invalid"},
    )
    await s.commit()
    return CurrentUser(uid, None, {})


async def test_users_cannot_see_each_others_private_data(s: AsyncSession) -> None:
    alice, bob = await make_user(s), await make_user(s)
    pid = await papers_repo.insert_paper(
        s, owner_id=alice.id, visibility="private", source="upload", sha256=uuid.uuid4().hex, title="Secret"
    )
    await papers_repo.link(s, alice.id, pid, None)
    await papers_repo.update_paper(s, pid, status="ready")
    note = await lib_repo.create_note(s, alice.id, pid, None, "alice's note", "yellow", "manual")
    thread = await chat.create_thread(s, alice, {"paper_ids": [str(pid)]}, "t")
    await s.commit()

    # Alice can, Bob cannot.
    assert (await papers.require_access(s, alice, pid))["title"] == "Secret"
    with pytest.raises(NotFound):
        await papers.require_access(s, bob, pid)
    listing = await papers.list_papers(s, bob, collection_id=None, q=None, starred=None, status=None, limit=50,
                                       cursor=None)  # fmt: skip
    assert listing["items"] == []
    assert await chat_repo.get_thread(s, bob.id, thread["id"]) is None
    with pytest.raises(NotFound):
        await chat.create_thread(s, bob, {"paper_ids": [str(pid)]}, None)
    assert await lib_repo.update_note(s, bob.id, note["id"], "hacked", None) is None
    assert not await lib_repo.delete_note(s, bob.id, note["id"])
    assert await lib_repo.list_notes(s, bob.id, pid) == []

    # Deleting Bob's link to a paper he never had does nothing to Alice's.
    with pytest.raises(NotFound):
        await papers.delete_paper(s, None, bob, pid)  # type: ignore[arg-type]
    assert await papers_repo.get_paper(s, pid) is not None


async def test_shared_cache_paper_is_per_user_linked(s: AsyncSession) -> None:
    alice, bob = await make_user(s), await make_user(s)
    arxiv = f"9999.{uuid.uuid4().int % 99999:05d}"
    pid = await papers_repo.insert_paper(
        s, owner_id=None, visibility="public_cache", source="arxiv", sha256=f"arxiv:{arxiv}", arxiv_id=arxiv
    )
    await papers_repo.link(s, alice.id, pid, None)
    await s.commit()
    assert await papers_repo.get_card(s, alice.id, pid) is not None
    # Bob only sees it after adding it himself.
    assert await papers_repo.get_card(s, bob.id, pid) is None
    await papers_repo.link(s, bob.id, pid, None)
    await s.commit()
    assert await papers_repo.get_card(s, bob.id, pid) is not None
    # Removing it from Bob's library keeps the shared row for Alice.
    await papers_repo.unlink(s, bob.id, pid)
    await s.commit()
    assert await papers_repo.get_card(s, alice.id, pid) is not None
