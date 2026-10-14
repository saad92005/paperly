"""Grounded chat: threads, query analysis, intents, retrieval, streaming answers (docs/06 §2)."""

import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import prompts
from app.auth import CurrentUser
from app.config import Settings
from app.errors import Invalid, NotFound
from app.providers.base import Msg
from app.providers.llm import ProviderError
from app.providers.registry import Providers
from app.repos import chat as repo
from app.repos import papers as papers_repo
from app.services import quotas
from app.services.answer import Event, Result, SentenceIndex, extractive_answer, generate
from app.services.retrieval import Hit, format_sources, retrieve
from app.sse import sse

log = structlog.get_logger()
Intent = Literal["qa", "summary", "compare", "locate", "metadata", "out_of_scope"]
PRONOUNS = re.compile(r"\b(it|its|this|that|these|those|they|them|their|he|she|above|previous)\b", re.I)


async def scope_papers(s: AsyncSession, user: CurrentUser, scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Ready papers in the scope that the user has in their library."""
    if scope.get("collection_id"):
        sql = (
            "select p.id, p.title, p.authors, p.year, p.venue, p.status from user_papers up "
            "join papers p on p.id = up.paper_id where up.user_id = :u and up.collection_id = :c"
        )
        params: dict[str, Any] = {"u": user.id, "c": UUID(str(scope["collection_id"]))}
    else:
        ids = [UUID(str(x)) for x in scope.get("paper_ids") or []]
        sql = (
            "select p.id, p.title, p.authors, p.year, p.venue, p.status from user_papers up "
            "join papers p on p.id = up.paper_id where up.user_id = :u and up.paper_id = any(:ids)"
        )
        params = {"u": user.id, "ids": ids}
    return [dict(r) for r in (await s.execute(text(sql), params)).mappings().all()]


async def create_thread(
    s: AsyncSession, user: CurrentUser, scope: dict[str, Any], title: str | None
) -> dict[str, Any]:
    if scope.get("collection_id"):
        papers = await scope_papers(s, user, scope)
        if not papers:
            raise Invalid("That collection has no papers yet.")
    else:
        ids = [UUID(str(x)) for x in scope.get("paper_ids") or []]
        if not ids or len(ids) > 20:
            raise Invalid("Choose between 1 and 20 papers.")
        if not await papers_repo.user_has(s, user.id, ids):
            raise NotFound("Paper not found in your library.")
        scope = {"paper_ids": [str(i) for i in ids]}
    t = await repo.create_thread(s, user.id, scope, title)
    await s.commit()
    return t


def needs_analysis(message: str, history: list[dict[str, Any]]) -> bool:
    if not history:
        return len(message.split()) > 25 or not message.isascii()
    return bool(PRONOUNS.search(message)) or len(message.split()) > 25 or not message.isascii()


async def analyze(
    providers: Providers, message: str, history: list[dict[str, Any]], titles: list[str]
) -> dict[str, Any]:
    default: dict[str, Any] = {
        "standalone_query": message,
        "language": "en",
        "intent": "qa",
        "sub_queries": [],
    }
    if not providers.llm.available:
        return default
    hist = "\n".join(f"{m['role'].title()}: {m['content'][:400]}" for m in history[-4:])
    prompt = prompts.ANALYZE.format(paper_titles="; ".join(titles), history=hist or "(none)", message=message)
    try:
        raw, _ = await providers.llm.complete(
            "analyze", [Msg("user", prompt)], temperature=0.0, max_tokens=300, json_mode=True
        )
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except (ProviderError, ValueError) as exc:
        log.info("analyze_skipped", reason=type(exc).__name__)
        return default
    if data.get("intent") not in ("qa", "summary", "compare", "locate", "metadata", "out_of_scope"):
        data["intent"] = "qa"
    data["standalone_query"] = str(data.get("standalone_query") or message)[:500]
    return {**default, **data}


def quick_intent(message: str) -> Intent | None:
    m = message.lower().strip()
    if re.match(r"^(where|which (page|section)|find|locate|show me where)\b", m):
        return "locate"
    if re.match(r"^(who (wrote|are the authors)|when was|what year|which (venue|conference|journal)|"
                r"what is the title|authors?\b)", m):  # fmt: skip
        return "metadata"
    if re.match(r"^(summari[sz]e|give me (a|the) summary|tl;?dr|what is this paper about)", m):
        return "summary"
    return None


def cache_key(task: str, model: str, scope: list[UUID], level: str, lang: str, q: str, mode: str) -> str:
    norm = re.sub(r"\s+", " ", q.lower().strip(" ?.!"))
    raw = "|".join([task, prompts.ANSWER_VER, model, *sorted(map(str, scope)), level, lang, mode, norm])
    return hashlib.sha256(raw.encode()).hexdigest()


def answer_messages(
    hits: list[Hit], question: str, original: str, history: list[dict[str, Any]], level: str, lang: str,
    strict: bool,
) -> list[Msg]:  # fmt: skip
    language = prompts.LANG_NAMES.get(lang, "English")
    system = prompts.ANSWER_SYSTEM.format(
        level_guidance=prompts.LEVEL_GUIDANCE.get(level, prompts.LEVEL_GUIDANCE["student"]),
        language=language,
        strict=prompts.STRICT_ADDON if strict else "",
    )
    hist = "\n".join(f"{m['role'].title()}: {m['content'][:600]}" for m in history[-4:])
    user = f"SOURCES\n{format_sources(hits)}\n\nRECENT CONVERSATION (context only, may be empty)\n{hist}\n\n"
    user += f"QUESTION\n{question}"
    if original.strip() != question.strip():
        user += f'\n(The user asked originally in {language}: "{original}")'
    return [Msg("system", system), Msg("user", user)]


async def _sentence_vectors(providers: Providers, hits: list[Hit]) -> dict[str, list[list[float]]]:
    idx = SentenceIndex(providers)
    return {str(h.chunk["id"]): await idx.vectors(h.chunk) for h in hits[:5]}


async def ask(
    s: AsyncSession,
    settings: Settings,
    providers: Providers,
    user: CurrentUser,
    thread: dict[str, Any],
    content: str,
    *,
    mode: Literal["grounded", "strict"],
    level: str,
    lang: str,
    selection: dict[str, Any] | None,
) -> AsyncIterator[str]:
    """SSE stream. Quota is consumed by the caller before streaming starts."""
    papers = [p for p in await scope_papers(s, user, thread["scope"]) if p["status"] == "ready"]
    history = await repo.messages(s, thread["id"])
    user_msg_id = await repo.add_message(s, thread["id"], "user", content)
    if thread["title"] is None:
        await s.execute(
            text("update threads set title = :t where id = :id"), {"t": content[:80], "id": thread["id"]}
        )
    await s.commit()
    if not papers:
        yield sse("error", {"code": "not_found", "message": "No indexed papers in this chat yet."})
        return
    paper_ids = [p["id"] for p in papers]
    titles = [p["title"] or "Untitled" for p in papers]

    question = content
    if selection and selection.get("text"):
        question = (
            f'{content}\n(About this passage on page {selection.get("page")}: "{selection["text"][:800]}")'
        )
    quick = quick_intent(content)
    intent: Intent = quick or "qa"
    analysis: dict[str, Any] = {"standalone_query": question, "language": lang}
    if needs_analysis(content, history):
        analysis = await analyze(providers, question, history, titles)
        intent = quick or analysis["intent"]
        lang = lang if lang != "auto" else analysis.get("language", "en")
    if lang == "auto":
        lang = "en"
    query = analysis["standalone_query"]

    result = Result()
    meta: dict[str, Any] = {
        "user_message_id": str(user_msg_id),
        "intent": intent,
        "scope_paper_ids": [str(i) for i in paper_ids],
    }

    if intent == "out_of_scope":
        canned = ("I can only answer questions about the papers in this chat. Try asking about their "
                  "methods, results or limitations.")  # fmt: skip
        async for ev in _finish(s, providers, thread, result, [], [], meta, canned=canned):
            yield ev
        return

    if intent == "metadata":
        chunk_rows = []
        for p in papers:
            first = await papers_repo.all_chunks(s, p["id"], with_refs=False)
            if first:
                chunk_rows.append(Hit({**first[0], "paper_title": p["title"]}, 0.0, 1.0))
        lines = []
        for i, p in enumerate(papers):
            authors = ", ".join(a.get("name", "") for a in (p["authors"] or [])) or "unknown authors"
            where = f", {p['venue']}" if p.get("venue") else ""
            marker = f" [S{i + 1}]" if i < len(chunk_rows) else ""
            lines.append(
                f"**{p['title'] or 'Untitled'}** — {authors} ({p['year'] or 'n.d.'}{where}).{marker}"
            )
        async for ev in _finish(s, providers, thread, result, chunk_rows, [], meta, canned="\n".join(lines)):
            yield ev
        return

    r = await retrieve(s, providers, query, paper_ids, tau=settings.abstain_threshold)
    hits = r.hits
    if intent == "locate":
        top = r.candidates[:5]
        lines = [
            f"- p.{h.chunk['page_start']} · {h.chunk.get('section') or h.chunk['kind']}: "
            f"“{h.chunk['text'][:160].strip()}…” [S{i}]"
            for i, h in enumerate(top, 1)
        ]
        canned = "Here is where the paper discusses this:\n\n" + "\n".join(lines) if top else "NOT_FOUND\n"
        async for ev in _finish(s, providers, thread, result, top, [], meta, canned=canned, check=False):
            yield ev
        return

    if r.abstain(settings.abstain_threshold, settings.abstain_vsim, query):
        closest = r.candidates[:3]
        canned = "NOT_FOUND\nI couldn't find this in the paper" + ("s" if len(papers) > 1 else "") + "."
        meta["closest"] = [
            {"paper_id": str(h.paper_id), "chunk_id": str(h.chunk["id"]), "page": h.chunk["page_start"],
             "section": h.chunk.get("section"), "quote": h.chunk["text"][:220]}
            for h in closest
        ]  # fmt: skip
        async for ev in _finish(s, providers, thread, result, hits, [], meta, canned=canned):
            yield ev
        return

    model_family = ",".join(sorted(providers.llm.providers)) or "extractive"
    key = cache_key("chat", model_family, paper_ids, level, lang, query, mode)
    if not history:
        cached = await repo.cache_get(s, key)
        if cached:
            result.provider, result.model = cached.get("provider"), cached.get("model")
            meta["cached"] = True
            async for ev in _finish(s, providers, thread, result, hits, [], meta, canned=cached["raw"]):
                yield ev
            return

    msgs = answer_messages(hits, query, content, history, level, lang, mode == "strict")
    canned: str | None = None
    if not providers.llm.available:
        [qv] = await providers.embeddings.embed([query], kind="query")
        canned = extractive_answer(hits, qv, await _sentence_vectors(providers, hits))
        result.provider, result.model = "extractive", "none"
    max_tokens = 800 if level == "expert" else 600
    async for ev in _finish(s, providers, thread, result, hits, msgs, meta, canned=canned,
                            max_tokens=max_tokens, cache=(key if not history else None)):  # fmt: skip
        yield ev


async def _finish(
    s: AsyncSession,
    providers: Providers,
    thread: dict[str, Any],
    result: Result,
    hits: list[Hit],
    msgs: list[Msg],
    meta: dict[str, Any],
    *,
    canned: str | None = None,
    max_tokens: int = 600,
    cache: str | None = None,
    check: bool = True,
) -> AsyncIterator[str]:
    raw_parts: list[str] = []
    yield sse("meta", {**meta, "provider": result.provider, "model": result.model})
    try:
        async for ev in generate(
            providers, hits, msgs, result, max_tokens=max_tokens, canned=canned, check=check
        ):
            yield _event(ev)
            if ev.kind == "token":
                raw_parts.append(ev.data["t"])
    except ProviderError as exc:
        log.warning("all_providers_failed", status=exc.status)
        if raw_parts or not hits:
            yield sse("error", {"code": "provider_unavailable",
                                "message": "All AI providers are busy. Try again in a minute."})  # fmt: skip
            return
        # Nothing streamed yet: degrade to an extractive answer instead of failing.
        [qv] = await providers.embeddings.embed([thread.get("title") or "summary"], kind="query")
        fallback = extractive_answer(hits, qv, await _sentence_vectors(providers, hits))
        result.__init__()  # type: ignore[misc]
        result.provider, result.model = "extractive", "none"
        async for ev in generate(providers, hits, [], result, canned=fallback):
            yield _event(ev)
    await repo.record_provider_events(s, providers.llm.events[-5:])
    providers.llm.events.clear()
    msg_id = await repo.add_message(
        s, thread["id"], "assistant", result.text or "", citations=result.citations,
        grounded=None if result.not_found else result.grounded, support_score=result.support_score,
        provider=result.provider, model=result.model, prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens, latency_ms=result.latency_ms,
    )  # fmt: skip
    if cache and not result.not_found and result.grounded and canned is None:
        await repo.cache_put(
            s, cache, {"raw": result.raw, "provider": result.provider, "model": result.model}
        )
    await s.commit()
    yield sse(
        "done",
        {
            "message_id": str(msg_id),
            "not_found": result.not_found,
            "grounded": result.grounded,
            "support_score": result.support_score,
            "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens},
            "latency_ms": result.latency_ms,
            "ttft_ms": result.ttft_ms,
            "cached": bool(meta.get("cached")),
            "provider": result.provider,
            "model": result.model,
            "closest": meta.get("closest"),
        },
    )


def _event(ev: Event) -> str:
    return sse(ev.kind, ev.data)


async def check_quota(s: AsyncSession, settings: Settings, user: CurrentUser) -> int:
    return await quotas.consume(s, settings, user.id, "questions")
