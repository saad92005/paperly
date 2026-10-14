import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import db
from app.auth import CurrentUserDep
from app.deps import SessionDep
from app.errors import NotFound
from app.jobs import queue
from app.schemas.papers import JobOut

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(job_id: UUID, user: CurrentUserDep, s: SessionDep) -> JobOut:
    job = await queue.get(s, job_id, user.id)
    if job is None:
        raise NotFound()
    return JobOut(**job)


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/{job_id}/events")
async def job_events(
    job_id: UUID, request: Request, user: CurrentUserDep, s: SessionDep
) -> StreamingResponse:
    if await queue.get(s, job_id, user.id) is None:
        raise NotFound()

    async def gen() -> AsyncIterator[str]:
        last: tuple[object, object, object] | None = None
        for _ in range(1200):  # ≤ ~10 minutes
            if await request.is_disconnected():
                return
            async with db.get_engine().connect() as conn:
                from sqlalchemy.ext.asyncio import AsyncSession

                async with AsyncSession(bind=conn) as s2:
                    job = await queue.get(s2, job_id, user.id)
            if job is None:
                yield sse("error", {"code": "not_found", "message": "Job disappeared."})
                return
            cur = (job["status"], job["stage"], job["progress"])
            if cur != last:
                yield sse(
                    "progress",
                    {"stage": job["stage"] or job["status"], "progress": job["progress"]},
                )
                last = cur
            if job["status"] == "succeeded":
                yield sse("done", {"status": "succeeded"})
                return
            if job["status"] in ("failed", "cancelled"):
                yield sse("error", {"code": "job_failed", "message": job["error"] or "Job failed."})
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})  # fmt: skip
