"""Choose provider implementations from settings (config-driven, docs/02 §3.4)."""

from dataclasses import dataclass

from app.config import Settings
from app.ingest.pdfplumber_parser import PdfPlumberParser
from app.providers.base import BlobStore, EmbeddingProvider, PdfParser, Reranker
from app.providers.blobs import PgBlobStore
from app.providers.llm import LLMRouter, build_llm_router
from app.providers.stubs import StubEmbeddings, StubLLM, StubReranker


@dataclass
class Providers:
    llm: LLMRouter
    embeddings: EmbeddingProvider
    reranker: Reranker
    parser: PdfParser
    blobs: BlobStore


def build_providers(settings: Settings) -> Providers:
    if settings.llm_provider_impl == "stub":
        llm = LLMRouter({"stub": StubLLM()}, {"chat": ["stub"]})
    else:
        llm = build_llm_router(settings)
    if settings.embeddings_provider == "fastembed":
        from app.providers.local import FastEmbedEmbeddings

        embeddings: EmbeddingProvider = FastEmbedEmbeddings(
            settings.embeddings_model, settings.embeddings_dim, settings.model_cache_dir
        )
    else:
        embeddings = StubEmbeddings(settings.embeddings_dim)
    if settings.reranker == "flashrank":
        from app.providers.local import FlashRankReranker

        reranker: Reranker = FlashRankReranker(settings.model_cache_dir)
    else:
        reranker = StubReranker()
    return Providers(
        llm=llm,
        embeddings=embeddings,
        reranker=reranker,
        parser=PdfPlumberParser(settings.max_pages_free),
        blobs=PgBlobStore(),
    )
