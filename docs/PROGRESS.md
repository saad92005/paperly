# PROGRESS

> Claude Code updates this file at the end of every phase. Newest entry on top.

## Current phase
Phases 0–5 ✅ and most of 7–10 ✅ (2026-10-14). Phase 6 (deploy): web on Vercel; API Render Blueprint ready —
needs the owner's Render account (one-time). Next: deploy the API, add a free LLM key, tag v1.0.0.

## Neon setup (one-time, ~3 min)
1. Sign in at console.neon.tech → **New project** (Postgres 17, region near you).
2. **Connect** → copy the **pooled** connection string. In `.env`, set
   `DATABASE_URL=postgresql+asyncpg://…` (change only the scheme; replace the query string with `?ssl=require` (asyncpg rejects `channel_binding`; the web app converts it for node-postgres)).
3. `BETTER_AUTH_SECRET` is already generated in `.env`; keep it secret.
4. `make db-migrate` → `make dev` → http://localhost:3000/login.
5. Magic links print in the `make dev` console until `RESEND_API_KEY` is set. Google sign-in is optional (see `.env.example`).

## Log

### Phases 7–10 (v1.5 differentiators) · 2026-10-14
**Built:** comparison matrix (default + custom columns, per-paper extraction, strict verifier, CSV/XLSX/MD export, share link);
discover (arXiv + Semantic Scholar, in-library flags, one-click import), reference resolution + "cited by";
glossary, equation explainer and translate actions, Mermaid diagrams in answers, answer language selector (RTL via `dir="auto"`);
SM-2 flashcards + Anki export + Study page; lit-review drafter (k-means themes, APA/IEEE, .md/.tex/.bib); public share pages.
**Not done:** Phase 11 self-host docker-compose (owner has no Docker), quiz/MCQ mode, arXiv HTML fast path, GROBID.

### Phase 6 — Deploy · 2026-10-14
**Built:** `apps/api/Dockerfile` (models baked in, non-root, migrations on boot), `render.yaml` Blueprint, Vercel config,
`ops.yml` (daily health, weekly gpg-encrypted pg_dump), README, SECURITY.md, CONTRIBUTING.md, privacy/terms pages, landing page.
**Pending owner action:** create a free Render account → New Blueprint → this repo → paste secrets; add `GROQ_API_KEY`.

### Phase 5 — Quality, eval, observability, security · 2026-10-14
**Built:** golden set (45 items, 5 arXiv papers incl. unanswerable) + `make eval` report; fixture `make eval-smoke` CI gate;
Playwright suite (core reader flow, axe on 4 pages, 375 px); cross-user access tests on real Postgres; CSP + HSTS (prod);
rate limiting; parse timeout, page cap, encrypted-PDF message; gitleaks, pip-audit, pnpm audit, Dependabot; optional Sentry; `/admin`.
**Eval (no LLM):** recall@8 0.90 · MRR 0.72 · abstention accuracy 1.00 · false abstain 0.00 (evals/report-golden.md).
**Gaps:** golden set is 45 items not 120; LLM-judged faithfulness not measured (no key configured); Lighthouse not run;
Langfuse deferred (ADR-013); RLS still bypassed by the owner role.
**Fixed:** contrast of ok/warn tokens (axe), production build broken by Turbopack CSS rule (ADR-014), page cap never firing.

### Phase 3–4 — Reader, citations, notes, summaries, collections · 2026-10-14
**Built:** pdf.js reader (lazy pages, text layer, zoom, outline, find), citation click → scroll + pulse highlight on the exact
sentence, J/K navigation, selection toolbar, notes CRUD + Markdown export, resizable panel, mobile tabs, read progress;
cited structured summary (LLM or extractive), collections, scope switcher (paper / selected / collection) with paper colours,
explain levels, BibTeX/APA/IEEE, settings (usage meter, data export, delete account), command palette.
**Verified (Playwright, Neon):** ask → citation → highlight lands on Table 2 "Transformer (big) 28.4"; highlights persist; 375 px fits.

### Phase 2 — Retrieval and grounded chat · 2026-10-14
**Built:** hybrid SQL + RRF, FlashRank rerank, blended scoring (ADR-012), abstain gate, OpenAI-compatible router with
fallback/cooling (429 test), marker parsing + renumbering, sentence-level citations, support check + number guard, intents
(qa/locate/metadata/out_of_scope), exact answer cache, quotas, threads/messages/feedback, extractive mode (ADR-010).

### Phase 1 — Ingestion · 2026-10-14
**Built:** pdfplumber parser (columns, headers/footers, invisible text, headings incl. small caps, captions, footnotes,
references, scanned detection, sentence boxes), chunker, fastembed, job queue + worker + SSE, upload/arXiv/DOI/URL import with
SSRF guard, blobs in Postgres (ADR-008), library UI, parser debug view. 15-page *Attention* paper indexes in ~45 s locally.

### Phase 0 — Foundation · 2026-10-13
**Built:** monorepo (pnpm workspace + uv); FastAPI app factory with request IDs, structlog JSON logs, CORS, one error handler (docs/04 error shape), `/health` (`db`/`worker`), JWT verification via JWKS (ES256, `aud`/`iss`/`exp` checked), `GET/PATCH /v1/me` (routers → services → repos); provider Protocols with deterministic stubs and a config registry; migrations in `db/migrations/` (Better Auth tables, enums, profiles, collections, papers, user_papers, jobs, profile trigger, RLS via `app_uid()`) with our own runner; Next.js 16 web app: Tailwind v4 + shadcn/ui on the docs/05 tokens, light/dark, Inter/Source Serif 4/JetBrains Mono, waking-server banner, **Better Auth** (email+password, magic link, optional Google) issuing 15-min JWTs for the API, library empty/loading/error states; OpenAPI → TS types (`packages/api-types`); Makefile; GitHub Actions (API, web, migrations-twice on pgvector Postgres).
**How to run/try:** `make setup` → fill `.env` (Neon setup above) → `make db-migrate` → `make dev` → `/login` → "Use a password instead" → Create account → `/library`.
**Tests:** API 13 passing (auth rejections incl. wrong issuer/audience/expired/foreign key, profile, error shape, request IDs); web 4 passing (API client incl. Bearer header). `make lint` clean (ruff, pyright strict, eslint, tsc).
**Verified in browser (Playwright, local Postgres):** sign up with password → `/library` → `/v1/me` 200 with the trigger-created profile; sign out → magic link (from dev console) → signed in again → `/v1/me` 200. No console errors. Earlier: `/`, `/login`, `/library` light 1280 px and dark 375 px.
**Verified on Neon (pgvector 0.8.6):** migrations applied; same browser flow passes; test users deleted afterwards.
**Known gaps / follow-ups:** CI not run on GitHub yet (no remote); PDF blob storage choice moves to Phase 1 (ADR-007); RLS is defense in depth only — the API connects as table owner, which bypasses it, until a restricted role is added (Phase 5 security pass); `make e2e`/`eval` are placeholders until Phases 2–3.
**Fixed:** login page kept a spinning "Sign in" after sign-out because Next 16 (cacheComponents) keeps page state across navigation — the form now resets on success. Signing out made the still-mounted library page refetch `/v1/me` with a dead session (two 401s) — user-scoped query keys now include the user id and sign-out no longer clears the cache. Routes read the app's own settings (`create_app(settings)`), not the global ones.
