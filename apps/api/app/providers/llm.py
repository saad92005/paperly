"""OpenAI-compatible chat adapter (ADR-002) and a router with fallback + cooling.

One client serves Groq, Gemini, OpenRouter and Ollama: only base_url, model and key differ.
The router falls back on 429/5xx/timeouts only before the first token has been streamed.
"""

import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import structlog

from app.config import Settings
from app.providers.base import Delta, LLMProvider, Msg

log = structlog.get_logger()

PRESETS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
    "ollama": ("http://localhost:11434/v1", "llama3.1:8b"),
}


class ProviderError(Exception):
    def __init__(self, provider: str, status: int | None, retry_after: float | None = None) -> None:
        super().__init__(f"{provider} failed with status {status}")
        self.provider, self.status, self.retry_after = provider, status, retry_after


class OpenAICompatLLM:
    def __init__(self, name: str, base_url: str, model: str, api_key: str, timeout: float = 60) -> None:
        self.name, self.base_url, self.model, self.api_key = (
            name,
            base_url.rstrip("/"),
            model,
            api_key,
        )
        self.timeout = timeout

    async def stream_chat(
        self, messages: list[Msg], *, temperature: float, max_tokens: int, json_mode: bool = False
    ) -> AsyncIterator[Delta]:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with (
                httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=10)) as client,
                client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=headers) as r,
            ):
                if r.status_code >= 400:
                    await r.aread()
                    ra = r.headers.get("retry-after")
                    log.warning("llm_http_error", provider=self.name, status=r.status_code,
                                body=r.text[:300])  # fmt: skip
                    raise ProviderError(
                        self.name,
                        r.status_code,
                        float(ra) if ra and ra.replace(".", "").isdigit() else None,
                    )
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in obj.get("choices") or []:
                        text = (choice.get("delta") or {}).get("content")
                        if text:
                            yield Delta(text=text)
                    usage = obj.get("usage")
                    if usage:
                        yield Delta(
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                        )
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, 504) from exc
        except httpx.TransportError as exc:
            raise ProviderError(self.name, 503) from exc


@dataclass
class LLMRouter:
    """Ordered chain per task with cooling after rate limits."""

    providers: dict[str, LLMProvider]
    routes: dict[str, list[str]]
    cooling: dict[str, float] = field(default_factory=lambda: {})
    events: list[tuple[str, str, str, bool, int | None, int]] = field(default_factory=lambda: [])

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def chain(self, task: str) -> list[LLMProvider]:
        names = self.routes.get(task) or self.routes.get("chat") or list(self.providers)
        names = [n for n in names if n in self.providers] or list(self.providers)
        now = time.monotonic()
        ready = [self.providers[n] for n in names if self.cooling.get(n, 0) <= now]
        return ready or [self.providers[n] for n in names]  # all cooling: try anyway

    async def stream(
        self,
        task: str,
        messages: list[Msg],
        *,
        temperature: float = 0.2,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> AsyncIterator[tuple[LLMProvider, Delta]]:
        last: ProviderError | None = None
        for p in self.chain(task):
            started = time.monotonic()
            got_any = False
            try:
                async for d in p.stream_chat(
                    messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode
                ):
                    got_any = True
                    yield p, d
                self._record(p, task, True, 200, started)
                return
            except ProviderError as exc:
                self._record(p, task, False, exc.status, started)
                if got_any:
                    raise
                if exc.status == 429:
                    self.cooling[p.name] = time.monotonic() + (exc.retry_after or 30)
                last = exc
                continue
        raise last or ProviderError("none", None)

    async def complete(self, task: str, messages: list[Msg], **kw: object) -> tuple[str, LLMProvider]:
        out: list[str] = []
        provider: LLMProvider | None = None
        async for p, d in self.stream(task, messages, **kw):  # pyright: ignore[reportArgumentType]
            provider = p
            out.append(d.text)
        assert provider is not None
        return "".join(out), provider

    def _record(self, p: LLMProvider, task: str, ok: bool, status: int | None, started: float) -> None:
        self.events.append((p.name, p.model, task, ok, status, int((time.monotonic() - started) * 1000)))
        del self.events[:-500]


def build_llm_router(settings: Settings) -> LLMRouter:
    providers: dict[str, LLMProvider] = {}
    keys = {
        "groq": (settings.groq_api_key, settings.groq_chat_model),
        "gemini": (settings.gemini_api_key, settings.gemini_chat_model),
        "openrouter": (settings.openrouter_api_key, settings.openrouter_chat_model),
    }
    for name, (key, model) in keys.items():
        if key:
            base, default_model = PRESETS[name]
            providers[name] = OpenAICompatLLM(name, base, model or default_model, key)
    if settings.ollama_enabled:
        base, default_model = PRESETS["ollama"]
        providers["ollama"] = OpenAICompatLLM(
            "ollama", settings.ollama_base_url or base, settings.ollama_model or default_model, ""
        )
    routes = {
        "chat": [s.strip() for s in settings.route_chat.split(",") if s.strip()] + ["ollama"],
        "summary": [s.strip() for s in settings.route_summary.split(",") if s.strip()] + ["ollama"],
    }
    return LLMRouter(providers, routes)
