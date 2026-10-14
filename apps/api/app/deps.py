"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.providers.registry import Providers

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_providers(request: Request) -> Providers:
    return request.app.state.providers


ProvidersDep = Annotated[Providers, Depends(get_providers)]


def wake_worker(request: Request) -> None:
    worker = getattr(request.app.state, "worker", None)
    if worker is not None:
        worker.wake.set()
