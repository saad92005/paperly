"""Request-driven job processing for serverless hosts (WORKER_MODE=request).

The web app calls POST /v1/worker/tick after it enqueues work and while it waits for results.
Each call processes queued jobs until none are left or the time budget is spent.
"""

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app import db
from app.auth import CurrentUserDep
from app.config import Settings, get_settings
from app.deps import ProvidersDep
from app.jobs import queue
from app.jobs.handlers import build_handlers
from app.jobs.worker import Worker

router = APIRouter(prefix="/v1/worker", tags=["worker"])
BUDGET_S = 240  # stay under the 300 s function limit


@router.post("/tick")
async def tick(
    user: CurrentUserDep, providers: ProvidersDep, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, Any]:
    if settings.worker_mode != "request":
        return {"processed": 0, "mode": settings.worker_mode}
    async with db.get_engine().begin() as conn:
        await queue.recover_stale(conn)
    worker = Worker(build_handlers(providers, settings), 1)
    started, processed = time.monotonic(), 0
    while time.monotonic() - started < BUDGET_S and await worker.run_once():
        processed += 1
    return {"processed": processed, "mode": "request"}
