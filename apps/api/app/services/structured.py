"""JSON-mode LLM calls with validation + one retry, and [S#] → sentence-level citations."""

import json
import re
from typing import Any

from app.providers.base import Msg
from app.providers.registry import Providers
from app.services.answer import SentenceIndex, citation_payload
from app.services.retrieval import Hit

SREF = re.compile(r"S?(\d+)")


class GenerationFailed(Exception):
    pass


def _extract_json(raw: str) -> Any:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start = min((i for i in (raw.find("{"), raw.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("no JSON object in output")
    end = max(raw.rfind("}"), raw.rfind("]"))
    return json.loads(raw[start : end + 1])


async def llm_json(
    providers: Providers, task: str, prompt: str, *, max_tokens: int = 1500, system: str | None = None
) -> tuple[Any, str]:
    """Returns (parsed JSON, model). Retries once with the parse error appended."""
    msgs = [Msg("system", system or "You return valid JSON only."), Msg("user", prompt)]
    last_err = ""
    for _ in range(2):
        if last_err:
            msgs = [
                *msgs,
                Msg("user", f"Your previous output was invalid ({last_err}). Return valid JSON only."),
            ]
        raw, p = await providers.llm.complete(
            task, msgs, temperature=0.1, max_tokens=max_tokens, json_mode=True
        )
        try:
            return _extract_json(raw), f"{p.name}/{p.model}"
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = str(exc)[:200]
    raise GenerationFailed(last_err)


async def cite_items(
    providers: Providers, hits: list[Hit], items: list[tuple[str, list[str]]]
) -> list[list[dict[str, Any]]]:
    """For each (text, ["S3", ...]) return Citation objects pointing at the best sentence."""
    if not items:
        return []
    sindex = SentenceIndex(providers)
    vecs = await providers.embeddings.embed([t or " " for t, _ in items], kind="doc")
    out: list[list[dict[str, Any]]] = []
    for (_, refs), vec in zip(items, vecs, strict=True):
        cits: list[dict[str, Any]] = []
        for ref in refs[:3]:
            m = SREF.fullmatch(str(ref).strip(" []"))
            if not m or not 1 <= int(m.group(1)) <= len(hits):
                continue
            hit = hits[int(m.group(1)) - 1]
            picks = await sindex.best(hit.chunk, vec)
            cits.append(citation_payload(len(cits) + 1, hit, picks))
        out.append(cits)
    return out


def sources_block(hits: list[Hit]) -> str:
    from app.services.retrieval import format_sources

    return format_sources(hits)
