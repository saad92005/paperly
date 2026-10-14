"""Local CPU models: fastembed (Apache-2.0) embeddings and FlashRank (Apache-2.0) reranking.

Models download once into MODEL_CACHE_DIR and are loaded lazily on first use.
"""

import threading
from typing import Any, Literal

import anyio

_lock = threading.Lock()


class FastEmbedEmbeddings:
    name = "fastembed"

    def __init__(self, model: str, dim: int, cache_dir: str, batch: int = 4, threads: int | None = 1) -> None:
        # Small batches + 1 thread keep onnxruntime's arena under ~350 MB (fits a 512 MB host).
        self.model_name, self.dim, self.cache_dir = model, dim, cache_dir
        self.batch, self.threads = batch, threads
        self._model: Any = None

    def _load(self) -> Any:
        with _lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(self.model_name, cache_dir=self.cache_dir, threads=self.threads)
        return self._model

    def _embed_sync(self, texts: list[str], kind: Literal["query", "doc"]) -> list[list[float]]:
        m = self._load()
        # bge models want a query instruction; documents get none (model card).
        vecs = m.query_embed(texts) if kind == "query" else m.embed(texts, batch_size=self.batch)
        return [[float(x) for x in v] for v in vecs]

    async def embed(self, texts: list[str], *, kind: Literal["query", "doc"]) -> list[list[float]]:
        if not texts:
            return []
        return await anyio.to_thread.run_sync(lambda: self._embed_sync(texts, kind))


class FlashRankReranker:
    def __init__(
        self, cache_dir: str, model: str = "ms-marco-TinyBERT-L-2-v2", max_length: int = 256
    ) -> None:
        self.cache_dir, self.model, self.max_length = cache_dir, model, max_length
        self._ranker: Any = None

    def _load(self) -> Any:
        with _lock:
            if self._ranker is None:
                from flashrank import Ranker

                self._ranker = Ranker(
                    model_name=self.model, cache_dir=self.cache_dir, max_length=self.max_length
                )
        return self._ranker

    def _rerank_sync(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        from flashrank import RerankRequest

        req = RerankRequest(query=query, passages=[{"id": i, "text": d} for i, d in enumerate(docs)])
        res: list[dict[str, Any]] = self._load().rerank(req)
        return [(int(r["id"]), float(r["score"])) for r in res][:top_k]

    async def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        if not docs:
            return []
        return await anyio.to_thread.run_sync(lambda: self._rerank_sync(query, docs, top_k))
