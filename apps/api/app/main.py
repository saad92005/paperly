"""App factory: middleware (request id, CORS), error handlers, routers."""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.jobs.handlers import build_handlers
from app.jobs.worker import Worker
from app.logging import configure_logging
from app.providers.registry import build_providers
from app.routers import health, jobs, me, papers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        providers = build_providers(settings)
        app.state.providers = providers
        app.state.worker = None
        if settings.worker_mode == "inprocess" and settings.database_url:
            worker = Worker(build_handlers(providers, settings), settings.worker_concurrency)
            worker.start()
            app.state.worker = worker
        yield
        if app.state.worker is not None:
            await app.state.worker.stop()
        await db.dispose()

    app = FastAPI(title=f"{settings.app_name} API", version=settings.version, lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # Routes depend on get_settings; make them see the settings this app was built with.
    app.dependency_overrides[get_settings] = lambda: settings
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(papers.router)
    app.include_router(jobs.router)
    return app


app = create_app()
