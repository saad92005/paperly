# PROGRESS

> Claude Code updates this file at the end of every phase. Newest entry on top.

## Current phase
Phase 0 — Foundation ✅ done 2026-10-13 (verified on Neon). Next: Phase 1 — Ingestion

## Neon setup (one-time, ~3 min)
1. Sign in at console.neon.tech → **New project** (Postgres 17, region near you).
2. **Connect** → copy the **pooled** connection string. In `.env`, set
   `DATABASE_URL=postgresql+asyncpg://…` (change only the scheme; replace the query string with `?ssl=require` (asyncpg rejects `channel_binding`; the web app converts it for node-postgres)).
3. `BETTER_AUTH_SECRET` is already generated in `.env`; keep it secret.
4. `make db-migrate` → `make dev` → http://localhost:3000/login.
5. Magic links print in the `make dev` console until `RESEND_API_KEY` is set. Google sign-in is optional (see `.env.example`).

## Log

### Phase 0 — Foundation · 2026-10-13
**Built:** monorepo (pnpm workspace + uv); FastAPI app factory with request IDs, structlog JSON logs, CORS, one error handler (docs/04 error shape), `/health` (`db`/`worker`), JWT verification via JWKS (ES256, `aud`/`iss`/`exp` checked), `GET/PATCH /v1/me` (routers → services → repos); provider Protocols with deterministic stubs and a config registry; migrations in `db/migrations/` (Better Auth tables, enums, profiles, collections, papers, user_papers, jobs, profile trigger, RLS via `app_uid()`) with our own runner; Next.js 16 web app: Tailwind v4 + shadcn/ui on the docs/05 tokens, light/dark, Inter/Source Serif 4/JetBrains Mono, waking-server banner, **Better Auth** (email+password, magic link, optional Google) issuing 15-min JWTs for the API, library empty/loading/error states; OpenAPI → TS types (`packages/api-types`); Makefile; GitHub Actions (API, web, migrations-twice on pgvector Postgres).
**How to run/try:** `make setup` → fill `.env` (Neon setup above) → `make db-migrate` → `make dev` → `/login` → "Use a password instead" → Create account → `/library`.
**Tests:** API 13 passing (auth rejections incl. wrong issuer/audience/expired/foreign key, profile, error shape, request IDs); web 4 passing (API client incl. Bearer header). `make lint` clean (ruff, pyright strict, eslint, tsc).
**Verified in browser (Playwright, local Postgres):** sign up with password → `/library` → `/v1/me` 200 with the trigger-created profile; sign out → magic link (from dev console) → signed in again → `/v1/me` 200. No console errors. Earlier: `/`, `/login`, `/library` light 1280 px and dark 375 px.
**Verified on Neon (pgvector 0.8.6):** migrations applied; same browser flow passes; test users deleted afterwards.
**Known gaps / follow-ups:** CI not run on GitHub yet (no remote); PDF blob storage choice moves to Phase 1 (ADR-007); RLS is defense in depth only — the API connects as table owner, which bypasses it, until a restricted role is added (Phase 5 security pass); `make e2e`/`eval` are placeholders until Phases 2–3.
**Fixed:** login page kept a spinning "Sign in" after sign-out because Next 16 (cacheComponents) keeps page state across navigation — the form now resets on success. Signing out made the still-mounted library page refetch `/v1/me` with a dead session (two 401s) — user-scoped query keys now include the user id and sign-out no longer clears the cache. Routes read the app's own settings (`create_app(settings)`), not the global ones.
