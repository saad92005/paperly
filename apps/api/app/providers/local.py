"""Local CPU models: fastembed (Apache-2.0) embeddings and FlashRank (Apache-2.0) reranking.

Models load lazily on first use, from ./models (plain files from scripts/bundle_models.py, used for
serverless bundles) when present, else from MODEL_CACHE_DIR (downloaded once).
"""

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

import anyio

_lock = threading.Lock()
BUNDLED_DIR = str(Path(__file__).resolve().parents[2] / "models")


def writable_cache(cache_dir: str) -> str:
    """Serverless bundles are read-only and model loaders may write lock files: copy to /tmp once."""
    if os.access(cache_dir, os.W_OK) or not os.path.isdir(cache_dir):
        return cache_dir
    target = os.path.join(tempfile.gettempdir(), "paperly-" + os.path.basename(cache_dir.rstrip("/\\")))
    if not os.path.isdir(target):
        shutil.copytree(cache_dir, target + ".tmp", dirs_exist_ok=True)
        os.replace(target + ".tmp", target)
    return target


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

                bundled = os.path.join(BUNDLED_DIR, self.model_name.split("/")[-1])
                if os.path.isfile(os.path.join(bundled, "model_optimized.onnx")):
                    self._model = TextEmbedding(
                        self.model_name,
                        cache_dir=tempfile.gettempdir(),
                        threads=self.threads,
                        specific_model_path=writable_cache(bundled),
                    )
                else:
                    self._model = TextEmbedding(
                        self.model_name, cache_dir=writable_cache(self.cache_dir), threads=self.threads
                    )
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

                cache = (
                    BUNDLED_DIR if os.path.isdir(os.path.join(BUNDLED_DIR, self.model)) else self.cache_dir
                )
                self._ranker = Ranker(
                    model_name=self.model, cache_dir=writable_cache(cache), max_length=self.max_length
                )
        return self._ranker

    def _rerank_sync(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        from flashrank import RerankRequest

        ranker = self._load()
        scored: list[tuple[int, float]] = []
        for start in range(0, len(docs), 10):  # small batches bound peak memory
            part = [{"id": i, "text": d} for i, d in enumerate(docs[start : start + 10], start)]
            res: list[dict[str, Any]] = ranker.rerank(RerankRequest(query=query, passages=part))
            scored.extend((int(r["id"]), float(r["score"])) for r in res)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        if not docs:
            return []
        return await anyio.to_thread.run_sync(lambda: self._rerank_sync(query, docs, top_k))
