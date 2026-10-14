"""Copy the embedding and rerank models into ./models as plain files (no Hugging Face symlinks).

Serverless bundles (Vercel) drop symlinks, so deploy with this folder present:
  uv run python scripts/bundle_models.py && vercel deploy --prod
"""

import shutil
from pathlib import Path

from fastembed import TextEmbedding
from flashrank import Ranker

API = Path(__file__).resolve().parents[1]
CACHE = API / ".models"
OUT = API / "models"


def main() -> None:
    TextEmbedding("BAAI/bge-small-en-v1.5", cache_dir=str(CACHE))
    Ranker(cache_dir=str(CACHE))
    snap = next((CACHE / "models--Qdrant--bge-small-en-v1.5-onnx-Q" / "snapshots").iterdir())
    dst = OUT / "bge-small-en-v1.5"
    dst.mkdir(parents=True, exist_ok=True)
    for f in snap.iterdir():
        shutil.copyfile(f.resolve(), dst / f.name)  # resolve symlink -> real bytes
    shutil.copytree(CACHE / "ms-marco-TinyBERT-L-2-v2", OUT / "ms-marco-TinyBERT-L-2-v2", dirs_exist_ok=True)
    print("bundled:", sorted(p.name for p in OUT.rglob("*") if p.is_file()))


if __name__ == "__main__":
    main()
