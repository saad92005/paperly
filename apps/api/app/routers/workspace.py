"""Comparisons, discover, share links, literature reviews, account and admin."""

import secrets
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.auth import CurrentUser, CurrentUserDep
from app.config import Settings, get_settings
from app.deps import ProvidersDep, SessionDep, wake_worker
from app.errors import Forbidden, Invalid, NotFound
from app.jobs import queue
from app.repos import library as repo
from app.repos import papers as papers_repo
from app.repos import profiles
from app.repos import study as study_repo
from app.services import compare, discover, quotas, review

router = APIRouter(prefix="/v1", tags=["workspace"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class ColumnIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    question: str = Field(min_length=3, max_length=300)


class ComparisonIn(BaseModel):
    paper_ids: list[UUID] = Field(min_length=2, max_length=10)
    columns: list[ColumnIn] | None = Field(default=None, max_length=12)
    title: str | None = Field(default=None, max_length=200)


class Comparison(BaseModel):
    id: UUID
    title: str | None
    paper_ids: list[UUID]
    columns: list[dict[str, str]]
    cells: dict[str, Any]
    status: str
    share_id: str | None
    created_at: datetime
    papers: list[dict[str, Any]] = Field(default_factory=lambda: [])


class ShareIn(BaseModel):
    kind: Literal["summary", "comparison"]
    ref_id: UUID


class LitReviewIn(BaseModel):
    topic: str | None = Field(default=None, max_length=200)
    style: Literal["apa", "ieee"] = "apa"
    length: Literal["short", "long"] = "short"


async def _with_papers(s: Any, cmp: dict[str, Any]) -> Comparison:
    papers: list[dict[str, Any]] = []
    for pid in cmp["paper_ids"]:
        p = await papers_repo.get_paper(s, pid)
        if p:
            papers.append({"id": str(pid), "title": p["title"], "year": p["year"],
                           "authors": [a.get("name") for a in p["authors"] or []][:3]})  # fmt: skip
    return Comparison(**cmp, papers=papers)


# ---------- Comparisons ----------


@router.post("/comparisons", status_code=202)
async def create_comparison(
    request: Request, body: ComparisonIn, user: CurrentUserDep, s: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    ids = list(dict.fromkeys(body.paper_ids))
    if len(ids) < 2 or not await papers_repo.user_has(s, user.id, ids):
        raise Invalid("Pick 2 to 10 papers from your library.")
    await quotas.consume(s, settings, user.id, "compares")
    if body.columns:
        cols: list[dict[str, str]] = []
        for c in body.columns:
            cols.append({"key": compare.column_key(c.label, cols), "label": c.label, "question": c.question})
    else:
        cols = compare.default_columns()
    cmp = await repo.create_comparison(s, user.id, body.title, ids, cols)
    job_id = await queue.enqueue(s, "compare", {"comparison_id": str(cmp["id"])}, user.id, 3)
    await s.commit()
    wake_worker(request)
    return {"comparison_id": cmp["id"], "job_id": job_id}


@router.get("/comparisons")
async def list_comparisons(user: CurrentUserDep, s: SessionDep) -> list[Comparison]:
    return [await _with_papers(s, c) for c in await repo.list_comparisons(s, user.id)]


@router.get("/comparisons/{cid}")
async def get_comparison(cid: UUID, user: CurrentUserDep, s: SessionDep) -> Comparison:
    cmp = await repo.get_comparison(s, cid, user.id)
    if cmp is None:
        raise NotFound()
    return await _with_papers(s, cmp)


@router.delete("/comparisons/{cid}", status_code=204)
async def delete_comparison(cid: UUID, user: CurrentUserDep, s: SessionDep) -> None:
    if not await repo.delete_comparison(s, user.id, cid):
        raise NotFound()
    await s.commit()


@router.post("/comparisons/{cid}/columns", status_code=202)
async def add_column(
    request: Request, cid: UUID, body: ColumnIn, user: CurrentUserDep, s: SessionDep
) -> dict[str, Any]:
    cmp = await repo.get_comparison(s, cid, user.id)
    if cmp is None:
        raise NotFound()
    if len(cmp["columns"]) >= 14:
        raise Invalid("A comparison can have at most 14 columns.")
    key = compare.column_key(body.label, cmp["columns"])
    cols = [*cmp["columns"], {"key": key, "label": body.label, "question": body.question}]
    await repo.set_comparison(s, cid, columns=cols)
    job_id = await queue.enqueue(s, "compare", {"comparison_id": str(cid), "column_keys": [key]}, user.id, 3)
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id, "key": key}


@router.get("/comparisons/{cid}/export")
async def export_comparison(
    cid: UUID,
    user: CurrentUserDep,
    s: SessionDep,
    format: Literal["csv", "xlsx", "md"] = "csv",
) -> Response:
    cmp = await repo.get_comparison(s, cid, user.id)
    if cmp is None:
        raise NotFound()
    full = await _with_papers(s, cmp)
    header, rows = compare.export_rows(cmp, {p["id"]: p["title"] or "Untitled" for p in full.papers})
    name = f"paperly-comparison.{format}"
    disp = {"Content-Disposition": f'attachment; filename="{name}"'}
    if format == "xlsx":
        return Response(compare.to_xlsx(header, rows), headers=disp,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")  # fmt: skip
    if format == "md":
        return PlainTextResponse(compare.to_markdown(header, rows), headers=disp, media_type="text/markdown")
    return PlainTextResponse(compare.to_csv(header, rows), headers=disp, media_type="text/csv")


# ---------- Discover ----------


@router.get("/discover/search")
async def discover_search(
    user: CurrentUserDep, s: SessionDep, settings: SettingsDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    source: Literal["arxiv", "s2", "all"] = "all", year_from: int | None = None, open_access_only: bool = True,
) -> list[dict[str, Any]]:  # fmt: skip
    return await discover.search(s, settings, user.id, q, source, year_from, open_access_only)


# ---------- Share links ----------


@router.post("/share")
async def create_share(
    body: ShareIn, user: CurrentUserDep, s: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    if body.kind == "comparison":
        if await repo.get_comparison(s, body.ref_id, user.id) is None:
            raise NotFound()
    elif await papers_repo.get_card(s, user.id, body.ref_id) is None:
        raise NotFound()
    sid = await repo.find_share(s, user.id, body.kind, body.ref_id)
    if sid is None:
        sid = secrets.token_urlsafe(9)
        await repo.create_share(s, sid, user.id, body.kind, body.ref_id)
        if body.kind == "comparison":
            await repo.set_comparison(s, body.ref_id, share_id=sid)
        await s.commit()
    return {"share_id": sid, "url": f"{settings.web_base_url.rstrip('/')}/s/{sid}"}


@router.get("/share/{share_id}")
async def get_share(share_id: str, s: SessionDep) -> dict[str, Any]:
    """Public, read-only: no PDF, no notes."""
    sh = await repo.get_share(s, share_id)
    if sh is None:
        raise NotFound()
    if sh["kind"] == "comparison":
        cmp = await repo.get_comparison(s, sh["ref_id"])
        if cmp is None:
            raise NotFound()
        full = await _with_papers(s, cmp)
        return {"kind": "comparison", "title": cmp["title"], "columns": cmp["columns"], "cells": cmp["cells"],
                "papers": full.papers, "paper_ids": [str(p) for p in cmp["paper_ids"]]}  # fmt: skip
    paper = await papers_repo.get_paper(s, sh["ref_id"])
    summary = await study_repo.get_summary(s, sh["ref_id"], "structured", "en", "student")
    if paper is None:
        raise NotFound()
    return {
        "kind": "summary",
        "paper": {"title": paper["title"], "authors": [a.get("name") for a in paper["authors"] or []],
                  "year": paper["year"], "venue": paper["venue"], "arxiv_id": paper["arxiv_id"], "doi": paper["doi"]},
        "summary": summary["content"] if summary else None,
    }  # fmt: skip


# ---------- Literature reviews ----------


@router.post("/collections/{cid}/review", status_code=202)
async def start_review(
    request: Request,
    cid: UUID,
    body: LitReviewIn,
    user: CurrentUserDep,
    s: SessionDep,
    providers: ProvidersDep,
) -> dict[str, Any]:
    if not await repo.owns_collection(s, user.id, cid):
        raise NotFound()
    if not providers.llm.available:
        from app.services.study import NoProvider

        raise NoProvider()
    job_id = await queue.enqueue(
        s, "lit_review", {"collection_id": str(cid), **body.model_dump()}, user.id, 3
    )
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id}


@router.get("/reviews")
async def list_reviews(user: CurrentUserDep, s: SessionDep) -> list[dict[str, Any]]:
    return await review.list_reviews(s, user.id)


@router.get("/exports/{job_id}")
async def export_review(
    job_id: UUID,
    user: CurrentUserDep,
    s: SessionDep,
    format: Literal["md", "tex", "bib"] = "md",
) -> PlainTextResponse:
    r = await review.get_review(s, user.id, job_id)
    if r is None:
        raise NotFound("That review isn't ready yet.")
    body = {"md": r["content_md"], "tex": review.to_latex(r["content_md"]), "bib": r["bibtex"]}[format]
    return PlainTextResponse(
        body, headers={"Content-Disposition": f'attachment; filename="paperly-review.{format}"'}
    )


# ---------- Account ----------


@router.get("/me/usage")
async def my_usage(user: CurrentUserDep, s: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    used = await quotas.usage(s, user.id)
    return {
        "used": used,
        "limits": {"questions": settings.quota_questions_per_day, "imports": settings.quota_imports_per_day,
                   "compares": settings.quota_compares_per_day},
        "reset_at": quotas.reset_at(),
    }  # fmt: skip


@router.delete("/me", status_code=202)
async def delete_me(request: Request, user: CurrentUserDep, s: SessionDep) -> dict[str, Any]:
    job_id = await queue.enqueue(s, "delete_account", {"user_id": str(user.id)}, None, 1)
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id}


# ---------- Admin ----------


async def require_admin(s: Any, user: CurrentUser) -> None:
    prof = await profiles.get_or_create(s, user.id)
    if not prof["is_admin"]:
        raise Forbidden()


@router.get("/admin/metrics")
async def admin_metrics(user: CurrentUserDep, s: SessionDep, providers: ProvidersDep) -> dict[str, Any]:
    await require_admin(s, user)
    m = await repo.metrics(s)
    m["llm_providers"] = sorted(providers.llm.providers)
    m["cooling"] = {k: v for k, v in providers.llm.cooling.items()}
    return m


@router.get("/admin/jobs")
async def admin_jobs(user: CurrentUserDep, s: SessionDep) -> list[dict[str, Any]]:
    await require_admin(s, user)
    return await repo.failed_jobs(s)


@router.post("/admin/jobs/{job_id}/retry", status_code=202)
async def admin_retry(request: Request, job_id: UUID, user: CurrentUserDep, s: SessionDep) -> dict[str, Any]:
    await require_admin(s, user)
    if not await repo.retry_job(s, job_id):
        raise NotFound()
    await s.commit()
    wake_worker(request)
    return {"job_id": job_id}
