# PROGRESS

> Claude Code updates this file at the end of every phase. Newest entry on top.

## Current phase
Phase 0 — Foundation (code complete; DoD waiting on Supabase project keys — see "Supabase setup")

## Supabase setup (one-time, ~5 min)
1. Create a free project at supabase.com (region near you). Save the DB password.
2. Copy `.env.example` → `.env` (`make setup` does it) and fill in:
   - `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL` = Project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = publishable/anon key
   - `SUPABASE_SERVICE_ROLE_KEY` = secret/service_role key (server only)
   - `DATABASE_URL` = Connect → **Session pooler** URI, scheme changed to `postgresql+asyncpg://`
3. `make db-migrate` — applies `supabase/migrations/`.
4. Auth → URL configuration: Site URL `http://localhost:3000`, redirect URL `http://localhost:3000/library`.
5. Auth → Providers: email (magic link) is on by default. Google needs a Google Cloud OAuth client (optional now).
6. Auth → Sign In / Up → JWT signing keys: make sure asymmetric keys are used (the API verifies via JWKS).

## Log

### Phase 0 — Foundation · 2026-10-13
**Built:** monorepo (pnpm workspace + uv); FastAPI app factory with request IDs, structlog JSON logs, CORS, single error handler (docs/04 error shape), `/health` (`db`/`worker` status), Supabase JWT verification via JWKS (ES256/RS256), `GET/PATCH /v1/me` (routers → services → repos); provider Protocols (`LLMProvider`, `EmbeddingProvider`, `Reranker`, `PdfParser`, `MetadataSource`, `BlobStore`) with deterministic stubs and a config-driven registry; first migration (enums, profiles, collections, papers, user_papers, jobs, signup trigger, RLS); Next.js 16 web app with Tailwind v4 + shadcn/ui mapped to the docs/05 tokens, light/dark toggle, Inter/Source Serif 4/JetBrains Mono, waking-server banner, login (Google + magic link), library empty state with loading/error/unconfigured states; OpenAPI → TS types in `packages/api-types`; Makefile; GitHub Actions (api lint/types/tests, web lint/types/tests, migrations applied to pgvector Postgres).
**How to run/try:** `make setup` → fill `.env` (above) → `make db-migrate` → `make dev` → open http://localhost:3000/login, sign in by magic link → `/library` shows your empty library.
**Tests:** API 12 passing (auth rejection cases, profile, error shape, request IDs, stubs); web 3 passing (API client). `make lint` clean (ruff, pyright strict, eslint, tsc).
**Verified in browser:** `/`, `/login`, `/library` in light 1280px and dark 375px — no console errors; "Supabase isn't configured" state shown without keys.
**Known gaps / follow-ups:** sign-in → `/v1/me` against a real project not yet verified (needs keys); CI not yet run on GitHub (no remote); `make e2e`/`eval` are placeholders until Phases 2–3; Windows needs GNU make (`winget install ezwinports.make`) and Git for Windows.
