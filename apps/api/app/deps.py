"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.providers.registry import Providers

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_providers(request: Request) -> Providers:
    # Serverless hosts may skip the lifespan hook; build providers on first use instead.
    providers = getattr(request.app.state, "providers", None)
    if providers is None:
        from app.config import get_settings
        from app.providers.registry import build_providers

        providers = build_providers(get_settings())
        request.app.state.providers = providers
    return providers


ProvidersDep = Annotated[Providers, Depends(get_providers)]


def wake_worker(request: Request) -> None:
    worker = getattr(request.app.state, "worker", None)
    if worker is not None:
        worker.wake.set()
