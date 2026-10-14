import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx

from app.providers.base import Delta, Msg
from app.providers.blobs import MemoryBlobStore
from app.providers.llm import LLMRouter, OpenAICompatLLM, ProviderError
from app.providers.registry import Providers
from app.providers.stubs import StubEmbeddings, StubLLM, StubParser, StubReranker
from app.services.answer import MarkerStream, Result, generate, norm_numbers
from app.services.retrieval import Hit, heading_boost, select


def chunk(text: str, page: int = 3) -> dict[str, Any]:
    sents: list[dict[str, Any]] = []
    pos = 0
    for part in text.split(". "):
        part = part if part.endswith(".") else part + "."
        start = text.find(part.rstrip("."), pos)
        sents.append({"s": start, "e": start + len(part.rstrip(".")), "page": page,
                      "rects": [[page, 10.0, 20.0, 200.0, 30.0]]})  # fmt: skip
        pos = start + len(part)
    return {"id": uuid.uuid4(), "paper_id": uuid.uuid4(), "text": text, "sentences": sents,
            "page_start": page, "page_end": page, "section": "3 Model", "kind": "body",
            "context_header": "P — 3 Model", "paper_title": "P"}  # fmt: skip


class SplitLLM(StubLLM):
    """Emits the reply in awkward pieces so markers split across tokens."""

    async def stream_chat(
        self, messages: list[Msg], *, temperature: float, max_tokens: int, json_mode: bool = False
    ) -> AsyncIterator[Delta]:
        for piece in [
            "The model uses 8 he",
            "ads [",
            "S2",
            "]. It was trained",
            " for 12 epochs [S1][S9",
            "].",
        ]:
            yield Delta(text=piece)


def providers(llm: Any) -> Providers:
    return Providers(
        llm=LLMRouter({"stub": llm}, {"chat": ["stub"]}),
        embeddings=StubEmbeddings(384),
        reranker=StubReranker(),
        parser=StubParser(),
        blobs=MemoryBlobStore(),
    )


def test_marker_stream_renumbers_and_handles_splits() -> None:
    ms = MarkerStream(3)
    out = "".join(t for piece in ["A [S", "3] b [S1, S3]", " c [S7] d"] for t, _ in ms.feed(piece))
    out += "".join(t for t, _ in ms.feed("", final=True))
    assert out == "A [1] b [2][1] c  d"
    assert ms.numbers == {3: 1, 1: 2}


async def test_generate_emits_renumbered_tokens_and_citations() -> None:
    hits = [Hit(chunk("We trained for 12 epochs. Dropout was 0.1"), 0.1, 0.9),
            Hit(chunk("We use 8 heads. Each head has 64 dims", page=5), 0.1, 0.8)]  # fmt: skip
    result = Result()
    events = [e async for e in generate(providers(SplitLLM()), hits, [Msg("user", "q")], result)]
    tokens = "".join(e.data["t"] for e in events if e.kind == "token")
    assert tokens == "The model uses 8 heads [1]. It was trained for 12 epochs [2]."
    cits = [e.data for e in events if e.kind == "citation"]
    assert [c["n"] for c in cits] == [1, 2]
    assert cits[0]["chunk_id"] == str(hits[1].chunk["id"]) and cits[0]["page"] == 5
    assert cits[0]["rects"] == [{"page": 5, "rect": [10.0, 20.0, 200.0, 30.0]}]
    assert result.text == tokens and not result.not_found
    assert result.raw.count("[S2]") == 1
    assert result.support_score is not None


async def test_not_found_sentinel_is_never_streamed() -> None:
    result = Result()
    llm = StubLLM("NOT_FOUND\nThe papers cover training, not cooking.")
    events = [e async for e in generate(providers(llm), [Hit(chunk("x y z"), 0, 0)], [], result)]
    assert result.not_found
    assert not [e for e in events if e.kind == "token"]
    assert result.text == "The papers cover training, not cooking."


def test_number_normalisation() -> None:
    assert norm_numbers("0.50 and 1,000 and 28.4 BLEU and 12%") == {"0.5", "1000", "28.4", "12"}
    assert norm_numbers("rate 3e-4") == {"3", "4"}


def test_selection_caps_per_paper() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    hits = [Hit({**chunk("t"), "paper_id": a}, 0, 0.9 - i * 0.01) for i in range(20)]
    hits.append(Hit({**chunk("t"), "paper_id": b}, 0, 0.3))
    picked = select(hits, 2, tau=0.15)
    assert len(picked) <= 12
    assert sum(1 for h in picked if h.paper_id == a) <= 7
    assert any(h.paper_id == b for h in picked)


def test_heading_boost() -> None:
    assert heading_boost("Where does it discuss positional encoding?", "3.5 Positional Encoding") == 0.15
    assert heading_boost("What optimizer?", "6 Results") == 0.0


@respx.mock
async def test_router_falls_back_on_429_and_cools_down() -> None:
    respx.post("https://a.test/v1/chat/completions").mock(
        return_value=httpx.Response(429, headers={"retry-after": "20"})
    )
    sse = 'data: {"choices":[{"delta":{"content":"Hello [S1]."}}]}\n\ndata: [DONE]\n\n'
    respx.post("https://b.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    )
    router = LLMRouter(
        {"a": OpenAICompatLLM("a", "https://a.test/v1", "m1", "k"),
         "b": OpenAICompatLLM("b", "https://b.test/v1", "m2", "k")},
        {"chat": ["a", "b"]},
    )  # fmt: skip
    text, provider = await router.complete("chat", [Msg("user", "hi")])
    assert (text, provider.name) == ("Hello [S1].", "b")
    assert router.cooling["a"] > 0
    assert [p.name for p in router.chain("chat")] == ["b"]
    assert [(e[0], e[3], e[4]) for e in router.events] == [("a", False, 429), ("b", True, 200)]


@respx.mock
async def test_router_raises_when_every_provider_fails() -> None:
    respx.post("https://a.test/v1/chat/completions").mock(return_value=httpx.Response(503))
    router = LLMRouter({"a": OpenAICompatLLM("a", "https://a.test/v1", "m", "k")}, {"chat": ["a"]})
    with pytest.raises(ProviderError):
        await router.complete("chat", [Msg("user", "hi")])
