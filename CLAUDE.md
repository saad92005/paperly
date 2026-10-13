# CLAUDE.md — working rules for Paperly

Paperly is an open-source AI research-paper copilot: import papers, read them in a PDF reader, ask questions, compare papers — every claim cited to the exact sentence. Built on a $0 stack.

## Repo layout

```
paperly/
├─ apps/
│  ├─ web/              Next.js (App Router, TypeScript, Tailwind, shadcn/ui)
│  └─ api/              FastAPI (Python 3.12, uv) + in-process job worker
├─ packages/
│  └─ api-types/        TypeScript types generated from the FastAPI OpenAPI schema
├─ supabase/
│  └─ migrations/       Plain SQL migrations (single source of truth for the DB)
├─ eval/                Golden dataset, eval runner, reports
├─ infra/               docker-compose.selfhost.yml (GROBID, Ollama — optional)
├─ docs/                PRD, TRD, specs, PROGRESS.md, DECISIONS.md
├─ .github/workflows/   CI (lint, type-check, test, eval-smoke)
├─ Makefile
└─ CLAUDE.md
```

## Commands (keep these working)

| Command | What it does |
|---|---|
| `make setup` | Install deps (uv sync, pnpm install), copy `.env.example` → `.env` if missing |
| `make dev` | `supabase start` + API (uvicorn --reload) + web (next dev) |
| `make db-reset` | Re-apply all migrations to the local Supabase DB and seed |
| `make test` | API pytest + web vitest |
| `make e2e` | Playwright tests against the dev stack |
| `make lint` | ruff + pyright (api), eslint + tsc --noEmit (web) |
| `make types` | Regenerate `packages/api-types` from the running API's OpenAPI |
| `make eval` | Run the full eval set and write `eval/reports/<date>.md` |
| `make eval-smoke` | 10-question eval subset (used in CI) |

## Conventions

**Python (apps/api)**
- Python 3.12, `uv` for deps (lockfile committed), `ruff` (lint + format), `pyright` strict on `app/`.
- Layering: `routers/` (HTTP only) → `services/` (business logic) → `repos/` (SQL) and `providers/` (external APIs). Routers never touch SQL or providers directly.
- Async everywhere (`asyncpg` via SQLAlchemy 2.0 async). Pydantic v2 models for every request/response.
- Every provider implements a Protocol in `app/providers/base.py` (`LLMProvider`, `EmbeddingProvider`, `Reranker`, `PdfParser`, `MetadataSource`, `BlobStore`). Choose implementations in `app/config.py` from env vars.
- Settings via `pydantic-settings`. No literal limits/model names in code.
- Errors: raise domain exceptions; one exception handler maps them to the error shape in `docs/04-API-SPEC.md`.
- Logging: structlog JSON, include `request_id`, `user_id`, `paper_id` where known. Never log paper text or prompts at INFO.

**TypeScript (apps/web)**
- Strict TS, no `any`. Server state with TanStack Query; UI state with Zustand (small stores).
- API calls only through `lib/api.ts` using generated types from `packages/api-types`.
- Components: shadcn/ui primitives, Tailwind tokens from `docs/05-UI-UX.md`. No inline hex colors.
- PDF rendering with pdf.js (via `react-pdf` or `pdfjs-dist` directly); `isEvalSupported: false`.
- Every screen ships its empty, loading, error and offline/waking states.

**Database**
- Change schema only through a new file in `supabase/migrations/` (timestamped). Never edit an applied migration.
- RLS enabled on every user-owned table even though the API uses a server key (defense in depth).

**Git**
- Small commits, Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- Do not commit `.env`, model weights, PDFs, or eval outputs other than the markdown report.

## Definition of done (every task)
1. Lint, type-check and tests pass locally.
2. New behaviour has tests; bug fixes start with a failing test.
3. `docs/PROGRESS.md` updated; non-trivial decisions in `docs/DECISIONS.md`.
4. No new paid dependency; licences are permissive.
5. The feature works in the browser end to end (check it, don't assume).

## Things to never do
- Never put an API key in the frontend bundle or in git.
- Never send a private user upload to the shared public paper cache.
- Never let the LLM answer from outside the retrieved context in "grounded" mode.
- Never bypass the quota/rate-limit layer, even in internal calls.
- Never silently swallow provider errors — fall back, log, and surface a friendly message.
