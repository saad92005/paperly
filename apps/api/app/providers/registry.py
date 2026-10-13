"""Choose provider implementations from settings. Real adapters replace stubs in later phases."""

from dataclasses import dataclass

from app.config import Settings
from app.providers.base import EmbeddingProvider, LLMProvider, Reranker
from app.providers.stubs import StubEmbeddings, StubLLM, StubReranker


@dataclass
class Providers:
    llm_chain: list[LLMProvider]
    embeddings: EmbeddingProvider
    reranker: Reranker


def build_providers(settings: Settings) -> Providers:
    # Only stubs exist in Phase 0; unknown choices fail loudly rather than silently degrade.
    if settings.llm_provider_impl != "stub":
        raise NotImplementedError(f"LLM impl {settings.llm_provider_impl!r} arrives in Phase 2")
    if settings.embeddings_provider != "stub":
        raise NotImplementedError(f"Embeddings {settings.embeddings_provider!r} arrive in Phase 1")
    if settings.reranker != "stub":
        raise NotImplementedError(f"Reranker {settings.reranker!r} arrives in Phase 2")
    return Providers(
        llm_chain=[StubLLM()],
        embeddings=StubEmbeddings(settings.embeddings_dim),
        reranker=StubReranker(),
    )
