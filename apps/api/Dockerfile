# Paperly API (FastAPI + in-process worker). Build from the repo root:
#   docker build -f apps/api/Dockerfile -t paperly-api .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    MODEL_CACHE_DIR=/app/.models \
    MIGRATIONS_DIR=/app/db/migrations \
    APP_ENV=prod

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /bin/uv
WORKDIR /app

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api/app ./app
COPY apps/api/scripts ./scripts
COPY db/migrations ./db/migrations

# Bake the embedding and rerank models into the image so cold starts don't download them.
RUN uv run --no-sync python -c "from fastembed import TextEmbedding; from flashrank import Ranker; \
TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/app/.models'); Ranker(cache_dir='/app/.models')"

RUN useradd --create-home --uid 10001 paperly && chown -R paperly /app
USER paperly

EXPOSE 8000
# Migrations are idempotent; apply them on boot, then serve.
CMD ["sh", "-c", "uv run --no-sync python scripts/migrate.py && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
