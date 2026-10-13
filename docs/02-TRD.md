# 02 · Technical Requirements Document (TRD)

## 1. Architecture overview

Paperly is a **two-app monolith**: a Next.js web app and a FastAPI service with an in-process job worker, sharing one Postgres database (Supabase) that holds relational data, vectors and full-text indexes. External AI providers are reached through swappable adapters. This keeps the system cheap, debuggable by one person, and deployable on free tiers — while the provider layer and job table make it easy to scale out later.

![System architecture](diagrams/architecture.svg)

**Why this shape**
- *One database for everything* (rows + `pgvector` + `tsvector`): no separate vector DB to pay for or sync; hybrid search is a single SQL query; RLS protects data.
- *One Python service*: the RAG pipeline, eval harness and parsers share code; the worker runs in the same process on the free tier and can be split into its own process later with no code change (it reads a Postgres job queue).
- *OpenAI-compatible provider adapters*: Groq, Google Gemini, OpenRouter and Ollama all expose OpenAI-compatible chat endpoints, so one small client with different `base_url`s covers every LLM provider.

## 2. Tech stack ($0)

| Layer | Choice | Licence / cost | Notes |
|---|---|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui | MIT · free | TanStack Query, Zustand, cmdk (command palette) |
| PDF viewer | pdf.js (`pdfjs-dist`, optionally `react-pdf`) | Apache-2.0 | Text layer + custom highlight layer; `isEvalSupported:false` |
| Math / diagrams | KaTeX, Mermaid | MIT | Render equations and generated diagrams |
| API | FastAPI + Uvicorn, Pydantic v2, SQLAlchemy 2 async + asyncpg | MIT/BSD | Python 3.12, managed with `uv` |
| Jobs | Postgres job table (`SELECT … FOR UPDATE SKIP LOCKED`) + asyncio worker | free | No Redis required |
| Database | Supabase Postgres + `pgvector` (`halfvec`) + full-text search | Free plan | Free plan (checked Oct 2026): 500 MB DB, 1 GB file storage, 50k MAU, 2 projects, pauses after 7 days idle |
| Auth | Supabase Auth (Google OAuth + magic link) | Free plan | API verifies Supabase JWTs via JWKS |
| File storage | Supabase Storage (private bucket, signed URLs) | Free plan | arXiv PDFs are *not* stored — fetched from arXiv on view |
| PDF parsing (default) | `pdfplumber` (words, fonts, boxes) + `pypdfium2` (render/thumbs) | MIT · Apache/BSD | Light enough for a 512 MB server |
| PDF parsing (best quality) | GROBID (self-host / local) | Apache-2.0 | CPU-only, de-facto standard for scholarly PDFs (sections, references, coordinates) |
| arXiv fast path | arXiv HTML version when available | free | Clean sections and LaTeX math without PDF heuristics |
| Embeddings (default) | `fastembed` + `BAAI/bge-small-en-v1.5` (384-d, ONNX, CPU) | Apache-2.0 / MIT | Local, private, no rate limits |
| Embeddings (alt) | Gemini embedding model (free tier) | free tier | Switch via `EMBEDDINGS_PROVIDER` |
| Reranker | FlashRank (tiny cross-encoder, CPU) | Apache-2.0 | ~ms per pair; optional `bge-reranker-base` in self-host |
| LLM primary | Groq free plan (e.g. GPT-OSS-120B or Llama-3.3-70B — pick from current list) | free, rate-limited | Very fast streaming; limits are per model and per organisation (sample: ~30 RPM / 1,000 RPD) |
| LLM secondary | Google Gemini API free tier (current Flash / Flash-Lite) | free, rate-limited | Long context for whole-paper summaries; vision for figures |
| LLM tertiary | OpenRouter `:free` models | free, ~50 req/day | Last cloud fallback |
| LLM local | Ollama (e.g. Qwen3 or Llama 3.x 8B) | MIT | Self-host / privacy mode |
| Metadata | arXiv API, Semantic Scholar API, Crossref, Unpaywall, OpenAlex | free | Respect each API's rate limits; cache responses |
| Observability | Langfuse (cloud free tier or self-host), Sentry (free dev tier) | free | Traces per answer; errors |
| Product analytics | PostHog free tier (optional, opt-out respected) | free | Feature usage, funnels |
| Email | Resend free tier (magic links via Supabase; alerts in v2) | free | — |
| Hosting web | Vercel Hobby (portfolio) → Cloudflare Workers/OpenNext if monetised | free | Vercel Hobby is non-commercial |
| Hosting API | Render free web service (512 MB, sleeps after 15 min idle) | free, no card | Cold start 30–60 s handled in UI; see Deployment doc for alternatives |
| CI | GitHub Actions | free for public repos | Lint, tests, eval-smoke, migrations check |

> **Free-tier reality check.** Limits above were checked in October 2026 and change without notice. Hugging Face Docker Spaces, for example, now need a paid plan for new accounts, so they are deliberately not used. Every limit lives in config; the app degrades gracefully (fallback provider, queued work, clear messages) instead of failing.

## 3. Components

### 3.1 Web app (`apps/web`)
- Routes: `/` landing · `/login` · `/library` · `/library/[collectionId]` · `/paper/[id]` (reader + AI panel) · `/compare/[id]` · `/discover` · `/study` · `/settings` · `/s/[shareId]` (public share).
- Talks only to the FastAPI API with the Supabase access token in `Authorization: Bearer`.
- Streams chat with `fetch` + `ReadableStream` parsing Server-Sent Events.
- Highlight layer: converts stored PDF-space rectangles to viewport rectangles with pdf.js `viewport.convertToViewportRectangle`.
- Shows a "server waking up" banner when `/health` takes > 3 s (free-tier cold start).

### 3.2 API (`apps/api`)
```
app/
  main.py            app factory, middleware (request id, CORS, rate limit), routers
  config.py          Settings (pydantic-settings) + provider wiring
  auth.py            Supabase JWT verification (JWKS cached)
  routers/           papers, imports, jobs, chat, summaries, notes, collections,
                     compare, discover, study, export, me, admin, health
  services/          ingestion, retrieval, answering, citations, summaries,
                     compare, quotas, cache, metadata, export
  providers/         base.py (Protocols) + llm_openai_compat.py, embed_fastembed.py,
                     embed_gemini.py, rerank_flashrank.py, parse_pdfplumber.py,
                     parse_grobid.py, parse_arxiv_html.py, meta_arxiv.py,
                     meta_semantic_scholar.py, meta_crossref.py, blob_supabase.py
  repos/             SQL access per aggregate
  worker/            job loop, handlers (ingest_paper, build_summary, compare, ...)
  prompts/           versioned prompt templates (Jinja2) — see AI pipeline doc
  schemas/           Pydantic request/response models
tests/
```

### 3.3 Worker
- Same process as the API on the free tier (`WORKER_MODE=inprocess`), started on app startup; can run standalone (`python -m app.worker`) later.
- Polls `jobs` every 1 s with `FOR UPDATE SKIP LOCKED`; handlers are idempotent; retries with exponential backoff (max 3); progress written to the job row and pushed to SSE listeners.
- Concurrency limit `WORKER_CONCURRENCY=2` to stay inside 512 MB.

### 3.4 Provider layer
```python
class LLMProvider(Protocol):
    name: str
    async def stream_chat(self, messages: list[Msg], *, model: str,
                          temperature: float, max_tokens: int,
                          json_schema: dict | None = None) -> AsyncIterator[Delta]: ...

class EmbeddingProvider(Protocol):
    dim: int
    async def embed(self, texts: list[str], *, kind: Literal["query", "doc"]) -> list[list[float]]: ...

class Reranker(Protocol):
    async def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]: ...

class PdfParser(Protocol):
    async def parse(self, pdf: bytes) -> ParsedDocument: ...   # pages, blocks, sentences+bboxes, sections, refs
```
**LLM router:** an ordered chain per task (`ROUTE_CHAT=groq,gemini,openrouter`; `ROUTE_SUMMARY=gemini,groq`; `ROUTE_VISION=gemini`). On 429/5xx/timeout the router marks the provider "cooling" for the `retry-after` period and tries the next. Each call records provider, model, tokens and latency.

## 4. Core flows

![Ingestion and answering pipeline](diagrams/pipeline.svg)

**Ingestion (async job):** validate → hash (SHA-256) → dedupe/shared-cache lookup → store blob (uploads only) → metadata (arXiv/Crossref/heuristics) → parse (arXiv HTML → GROBID if configured → pdfplumber) → clean (drop headers/footers, invisible text) → section tree → sentence segmentation with boxes → structure-aware chunking → contextual chunk headers → embed (batched) → upsert chunks → build references → mark ready → enqueue summary pre-generation (low priority).

**Answering (streamed):** auth + quota → cache lookup → query understanding (standalone rewrite, language detect + translate to English, intent route) → hybrid retrieval (vector + full-text, RRF) → rerank → diversify across papers → prompt with numbered sources → stream tokens → map `[S#]` markers to citations with sentence boxes → support check → persist message + usage → emit `done`.

Details, prompts and thresholds: `docs/06-AI-PIPELINE-AND-PROMPTS.md`.

## 5. Non-functional requirements

| Category | Requirement |
|---|---|
| Performance | TTFT p95 ≤ 2.5 s warm; retrieval (SQL + rerank) p95 ≤ 400 ms; reader first page ≤ 1.5 s; ingestion of 15 pages p95 ≤ 60 s |
| Quality | Faithfulness ≥ 0.90, citation precision ≥ 0.90, abstention accuracy ≥ 0.85 on the golden set (CI blocks merges that drop > 3 points) |
| Scalability | Stateless API; job queue in Postgres; can move to paid tiers by config only; designed for 10k papers / 1k users on Supabase Pro |
| Storage budget | ~250 KB per paper in DB (384-d `halfvec` + text + FTS); shared cache for public papers; ≈ 1,500 papers in 500 MB |
| Availability | Best effort on free tiers; graceful degradation (provider fallback, queued ingestion, cached summaries) |
| Security | OWASP ASVS L1, RLS, JWT, signed URLs, SSRF guard, prompt-injection mitigations — see Security doc |
| Privacy | Uploads private by default; provider used is shown per answer; local mode keeps all data on device; account deletion cascades |
| Accessibility | WCAG 2.2 AA; full keyboard use; screen-reader labels for citations |
| i18n | UI strings externalised (next-intl); answers in user language; RTL support for Urdu/Arabic answer text |
| Observability | Structured logs with request IDs; Langfuse trace for every LLM call; Sentry for errors; `/admin` metrics |
| Maintainability | 80%+ line coverage in `services/`; typed end to end (OpenAPI → TS types); ADRs for decisions |
| Portability | `docker compose -f infra/docker-compose.selfhost.yml up` runs the whole stack offline |

## 6. Configuration (`.env.example`, abridged)

```dotenv
# Core
APP_ENV=dev
API_BASE_URL=http://localhost:8000
WEB_BASE_URL=http://localhost:3000
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres
SUPABASE_URL=http://localhost:54321
SUPABASE_JWKS_URL=http://localhost:54321/auth/v1/.well-known/jwks.json
SUPABASE_SERVICE_ROLE_KEY=            # server only, never in web

# Providers (order = fallback order)
ROUTE_CHAT=groq,gemini,openrouter
ROUTE_SUMMARY=gemini,groq
ROUTE_VISION=gemini
GROQ_API_KEY=
GROQ_CHAT_MODEL=                      # set from Groq's current model list
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=                    # current free Flash model
OPENROUTER_API_KEY=
OPENROUTER_CHAT_MODEL=                # a ":free" model
OLLAMA_BASE_URL=http://localhost:11434/v1
EMBEDDINGS_PROVIDER=fastembed         # fastembed | gemini
EMBEDDINGS_MODEL=BAAI/bge-small-en-v1.5
EMBEDDINGS_DIM=384
RERANKER=flashrank
PDF_PARSER_CHAIN=arxiv_html,grobid,pdfplumber
GROBID_URL=                           # empty = skip GROBID

# Limits
MAX_UPLOAD_MB=25
MAX_PAGES_FREE=100
QUOTA_QUESTIONS_PER_DAY=50
QUOTA_IMPORTS_PER_DAY=10
QUOTA_COMPARES_PER_DAY=5
WORKER_CONCURRENCY=2

# Observability
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
SENTRY_DSN=
CONTACT_EMAIL=                        # used in polite User-Agent for arXiv/Crossref/Unpaywall
```
