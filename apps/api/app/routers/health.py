from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import db
from app.config import Settings, get_settings
from app.schemas.me import Health

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> Health:
    if not settings.database_url:
        db_state = "unconfigured"
    else:
        db_state = "ok" if await db.ping() else "down"
    w = getattr(request.app.state, "worker", None)
    if settings.worker_mode == "request":
        worker = "on_demand"
    else:
        worker = "running" if w is not None and w.running else "off"
    return Health(
        status="ok" if db_state == "ok" else "degraded",
        version=settings.version,
        db=db_state,
        worker=worker,
    )
