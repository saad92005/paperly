"""SQL for papers, user_papers, sections, chunks and references."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

Conn = AsyncSession | AsyncConnection

PAPER_COLS = (
    "p.id, p.owner_id, p.visibility, p.source, p.source_ref, p.sha256, p.title, p.authors, "
    "p.year, p.venue, p.abstract, p.doi, p.arxiv_id, p.blob_path, p.page_count, p.parser, "
    "p.status, p.error, p.created_at"
)
CARD_COLS = f"{PAPER_COLS}, up.collection_id, up.tags, up.starred, up.read_progress, up.added_at"


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def insert_paper(s: Conn, **f: Any) -> UUID:
    f.setdefault("authors", [])
    f["authors"] = json.dumps(f["authors"])
    cols = ", ".join(f)
    vals = ", ".join(f"cast(:{k} as jsonb)" if k == "authors" else f":{k}" for k in f)
    row = (await s.execute(text(f"insert into papers ({cols}) values ({vals}) returning id"), f)).one()
    return row[0]


_UPDATABLE = {"title", "authors", "year", "venue", "abstract", "doi", "arxiv_id", "page_count",
              "parser", "status", "error", "sha256", "blob_path", "s2_paper_id"}  # fmt: skip


async def update_paper(s: Conn, paper_id: UUID, **f: Any) -> None:
    f = {k: v for k, v in f.items() if k in _UPDATABLE}
    if not f:
        return
    if "authors" in f:
        f["authors"] = json.dumps(f["authors"])
    sets = ", ".join(f"{k} = cast(:{k} as jsonb)" if k == "authors" else f"{k} = :{k}" for k in f)
    await s.execute(text(f"update papers set {sets} where id = :id"), {**f, "id": paper_id})


async def get_paper(s: Conn, paper_id: UUID) -> dict[str, Any] | None:
    row = (
        (await s.execute(text(f"select {PAPER_COLS} from papers p where p.id = :id"), {"id": paper_id}))
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def find_public(
    s: Conn, *, arxiv_id: str | None = None, doi: str | None = None
) -> dict[str, Any] | None:
    if arxiv_id:
        where, params = "p.arxiv_id = :v", {"v": arxiv_id}
    elif doi:
        where, params = "lower(p.doi) = lower(:v)", {"v": doi}
    else:
        return None
    sql = f"select {PAPER_COLS} from papers p where p.visibility = 'public_cache' and {where}"
    row = (await s.execute(text(sql), params)).mappings().first()
    return dict(row) if row else None


async def find_private_by_hash(s: Conn, owner_id: UUID, sha: str) -> dict[str, Any] | None:
    sql = f"select {PAPER_COLS} from papers p where p.owner_id = :o and p.sha256 = :h and p.visibility = 'private'"
    row = (await s.execute(text(sql), {"o": owner_id, "h": sha})).mappings().first()
    return dict(row) if row else None


async def link(s: Conn, user_id: UUID, paper_id: UUID, collection_id: UUID | None) -> None:
    await s.execute(
        text(
            "insert into user_papers (user_id, paper_id, collection_id) values (:u, :p, :c) "
            "on conflict (user_id, paper_id) do update set "
            "collection_id = coalesce(excluded.collection_id, user_papers.collection_id)"
        ),
        {"u": user_id, "p": paper_id, "c": collection_id},
    )


async def get_card(s: Conn, user_id: UUID, paper_id: UUID) -> dict[str, Any] | None:
    sql = (
        f"select {CARD_COLS} from user_papers up join papers p on p.id = up.paper_id "
        "where up.user_id = :u and up.paper_id = :p"
    )
    row = (await s.execute(text(sql), {"u": user_id, "p": paper_id})).mappings().first()
    return dict(row) if row else None


async def list_cards(
    s: Conn,
    user_id: UUID,
    *,
    collection_id: UUID | None,
    q: str | None,
    starred: bool | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    where = ["up.user_id = :u"]
    params: dict[str, Any] = {"u": user_id, "lim": limit + 1, "off": offset}
    if collection_id:
        where.append("up.collection_id = :c")
        params["c"] = collection_id
    if q:
        where.append(
            "(p.title ilike :q or p.authors::text ilike :q or p.abstract ilike :q or :tag = any(up.tags))"
        )
        params["q"] = f"%{q}%"
        params["tag"] = q
    if starred is not None:
        where.append("up.starred = :st")
        params["st"] = starred
    if status:
        where.append("p.status = cast(:status as paper_status)")
        params["status"] = status
    sql = (
        f"select {CARD_COLS} from user_papers up join papers p on p.id = up.paper_id "
        f"where {' and '.join(where)} order by up.added_at desc, p.id limit :lim offset :off"
    )
    return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


async def update_link(s: Conn, user_id: UUID, paper_id: UUID, **f: Any) -> None:
    allowed = {k: v for k, v in f.items() if k in ("collection_id", "tags", "starred", "read_progress")}
    if not allowed:
        return
    sets = ", ".join(f"{k} = :{k}" for k in allowed)
    await s.execute(
        text(f"update user_papers set {sets} where user_id = :u and paper_id = :p"),
        {**allowed, "u": user_id, "p": paper_id},
    )


async def unlink(s: Conn, user_id: UUID, paper_id: UUID) -> None:
    await s.execute(text("delete from user_papers where user_id = :u and paper_id = :p"),
                    {"u": user_id, "p": paper_id})  # fmt: skip


async def delete_paper(s: Conn, paper_id: UUID) -> None:
    await s.execute(text("delete from papers where id = :p"), {"p": paper_id})


async def replace_index(
    s: Conn,
    paper_id: UUID,
    sections: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> None:
    await s.execute(text("delete from chunks where paper_id = :p"), {"p": paper_id})
    await s.execute(text("delete from sections where paper_id = :p"), {"p": paper_id})
    await s.execute(text("delete from references_parsed where paper_id = :p"), {"p": paper_id})
    ids: list[UUID] = []
    for sec in sections:
        row = (
            await s.execute(
                text(
                    "insert into sections (paper_id, idx, heading, level, page_start, page_end) "
                    "values (:p, :idx, :heading, :level, :page_start, :page_end) returning id"
                ),
                {"p": paper_id, **sec},
            )
        ).one()
        ids.append(row[0])
    if chunks:
        rows = [
            {
                "p": paper_id,
                "sid": ids[c["section_idx"]] if c["section_idx"] < len(ids) else None,
                "idx": c["idx"],
                "kind": c["kind"],
                "text": c["text"],
                "hdr": c["context_header"],
                "ps": c["page_start"],
                "pe": c["page_end"],
                "sent": json.dumps(c["sentences"]),
                "tok": c["token_count"],
                "emb": _vec(c["embedding"]) if c.get("embedding") else None,
            }
            for c in chunks
        ]
        for i in range(0, len(rows), 100):
            await s.execute(
                text(
                    "insert into chunks (paper_id, section_id, idx, kind, text, context_header, "
                    "page_start, page_end, sentences, token_count, embedding) values "
                    "(:p, :sid, :idx, cast(:kind as chunk_kind), :text, :hdr, :ps, :pe, "
                    "cast(:sent as jsonb), :tok, cast(:emb as halfvec))"
                ),
                rows[i : i + 100],
            )
    if references:
        await s.execute(
            text(
                "insert into references_parsed (paper_id, idx, raw, title, year, doi, arxiv_id) "
                "values (:p, :idx, :raw, :title, :year, :doi, :arxiv_id)"
            ),
            [{"p": paper_id, **r} for r in references],
        )


async def sections(s: Conn, paper_id: UUID) -> list[dict[str, Any]]:
    sql = (
        "select id, idx, heading, level, page_start, page_end from sections where paper_id = :p order by idx"
    )
    return [dict(r) for r in (await s.execute(text(sql), {"p": paper_id})).mappings().all()]


async def chunk(s: Conn, paper_id: UUID, chunk_id: UUID) -> dict[str, Any] | None:
    sql = (
        "select c.id, c.paper_id, c.idx, c.kind, c.text, c.context_header, c.page_start, "
        "c.page_end, c.sentences, c.token_count, sec.heading as section "
        "from chunks c left join sections sec on sec.id = c.section_id "
        "where c.paper_id = :p and c.id = :c"
    )
    row = (await s.execute(text(sql), {"p": paper_id, "c": chunk_id})).mappings().first()
    return dict(row) if row else None


async def all_chunks(s: Conn, paper_id: UUID, *, with_refs: bool = True) -> list[dict[str, Any]]:
    sql = (
        "select c.id, c.paper_id, c.idx, c.kind, c.text, c.context_header, c.page_start, "
        "c.page_end, c.sentences, c.token_count, sec.heading as section "
        "from chunks c left join sections sec on sec.id = c.section_id where c.paper_id = :p "
        + ("" if with_refs else "and c.kind <> 'reference' ")
        + "order by c.idx"
    )
    return [dict(r) for r in (await s.execute(text(sql), {"p": paper_id})).mappings().all()]


async def references(s: Conn, paper_id: UUID) -> list[dict[str, Any]]:
    sql = (
        "select r.idx, r.raw, r.title, r.year, r.doi, r.arxiv_id, r.resolved_paper_id "
        "from references_parsed r where r.paper_id = :p order by r.idx"
    )
    return [dict(r) for r in (await s.execute(text(sql), {"p": paper_id})).mappings().all()]


async def user_has(s: Conn, user_id: UUID, paper_ids: list[UUID]) -> bool:
    if not paper_ids:
        return False
    row = (
        await s.execute(
            text("select count(*) from user_papers where user_id = :u and paper_id = any(:ids)"),
            {"u": user_id, "ids": paper_ids},
        )
    ).one()
    return int(row[0]) == len(set(paper_ids))


async def links_count(s: Conn, paper_id: UUID) -> int:
    row = (
        await s.execute(text("select count(*) from user_papers where paper_id = :p"), {"p": paper_id})
    ).one()
    return int(row[0])
