"""App factory: middleware (request id, CORS), error handlers, routers."""

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.jobs.handlers import build_handlers
from app.jobs.worker import Worker
from app.logging import configure_logging
from app.providers.registry import build_providers
from app.ratelimit import RateLimiter, client_key
from app.routers import chat, health, jobs, library, me, papers, workspace


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    if settings.sentry_dsn:
        import sentry_sdk

        # Errors only, no request bodies or PII (paper text never leaves via Sentry).
        sentry_sdk.init(
            dsn=settings.sentry_dsn, environment=settings.app_env, release=settings.version,
            traces_sample_rate=0.05, send_default_pii=False, max_request_body_size="never",
        )  # fmt: skip

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
    limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:16]}"
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        remaining = None
        if request.url.path.startswith("/v1/") and request.method != "OPTIONS":
            ok, remaining, retry = limiter.check(client_key(request))
            if not ok:
                return JSONResponse(
                    {"error": {"code": "rate_limited", "message": "Too many requests. Slow down a little.",
                               "details": {}, "request_id": rid}},
                    status_code=429,
                    headers={"Retry-After": str(retry), "X-Request-ID": rid, "X-RateLimit-Remaining": "0"},
                )  # fmt: skip
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if settings.app_env == "prod":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Remaining",
            "X-Quota-Questions-Remaining",
            "Retry-After",
        ],
    )
    # Routes depend on get_settings; make them see the settings this app was built with.
    app.dependency_overrides[get_settings] = lambda: settings
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(papers.router)
    app.include_router(jobs.router)
    app.include_router(chat.router)
    app.include_router(library.router)
    app.include_router(workspace.router)
    return app


app = create_app()
