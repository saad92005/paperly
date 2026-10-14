"""In-process worker: N asyncio loops claim jobs and dispatch to handlers by type."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app import db
from app.jobs import queue

log = structlog.get_logger()

Handler = Callable[[dict[str, Any], "JobContext"], Awaitable[None]]


class RetryableError(Exception):
    """Transient failure (network, provider busy): the job is retried with backoff."""


class JobContext:
    def __init__(self, job: dict[str, Any]) -> None:
        self.job = job

    async def progress(self, stage: str, pct: int) -> None:
        async with db.get_engine().begin() as conn:
            await queue.progress(conn, self.job["id"], stage, pct)


class Worker:
    def __init__(self, handlers: dict[str, Handler], concurrency: int = 2, poll_s: float = 1.0) -> None:
        self.handlers, self.concurrency, self.poll_s = handlers, concurrency, poll_s
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()
        self.wake = asyncio.Event()

    @property
    def running(self) -> bool:
        return any(not t.done() for t in self._tasks)

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._loop(i)) for i in range(self.concurrency)]

    async def stop(self) -> None:
        self._stop.set()
        self.wake.set()
        for t in self._tasks:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    async def _loop(self, n: int) -> None:
        if n == 0:
            with contextlib.suppress(Exception):
                async with db.get_engine().begin() as conn:
                    await queue.recover_stale(conn)
        while not self._stop.is_set():
            try:
                ran = await self.run_once()
            except Exception:
                log.exception("worker_loop_error")
                ran = False
            if not ran:
                self.wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), timeout=self.poll_s)

    async def run_once(self) -> bool:
        async with db.get_engine().begin() as conn:
            job = await queue.claim(conn)
        if job is None:
            return False
        handler = self.handlers.get(job["type"])
        structlog.contextvars.bind_contextvars(job_id=str(job["id"]), job_type=job["type"])
        log.info("job_started", attempt=job["attempts"])
        try:
            if handler is None:
                raise ValueError(f"no handler for job type {job['type']}")
            await handler(job, JobContext(job))
        except Exception as exc:
            retryable = isinstance(exc, RetryableError)
            msg = getattr(exc, "message", None) or str(exc) or type(exc).__name__
            async with db.get_engine().begin() as conn:
                retry = await queue.fail(conn, job, msg, retryable)
            log.warning("job_failed", error=msg, retry=retry, error_type=type(exc).__name__)
            on_fail = getattr(handler, "on_final_failure", None)
            if not retry and on_fail is not None:
                with contextlib.suppress(Exception):
                    await on_fail(job, msg)
        else:
            async with db.get_engine().begin() as conn:
                await queue.succeed(conn, job["id"])
            log.info("job_succeeded")
        finally:
            structlog.contextvars.unbind_contextvars("job_id", "job_type")
        return True
