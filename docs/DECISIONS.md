# DECISIONS (lightweight ADRs)

> One short entry per non-trivial decision. Newest on top.

<!-- Template
### ADR-NNN · <title> · <date>
**Context:** …
**Options:** A) … B) …
**Decision:** …
**Why:** …
**Revisit when:** …
-->

### ADR-007 · Neon Postgres + Better Auth instead of Supabase · 2026-10-13
**Context:** The owner's Supabase free-tier project slots are used up and Docker doesn't run locally, so neither cloud nor local Supabase is available. **Options:** A) pause an old Supabase project; B) Neon free Postgres + Better Auth; C) local Postgres only. **Decision:** B (owner's choice). **How:** Neon holds all tables (pgvector supported). Better Auth (MIT, TypeScript) runs in the Next.js app at `/api/auth/*` with email+password, magic link (Resend free tier, or console in dev) and optional Google; its `jwt` plugin issues 15-minute ES256 tokens (aud `paperly-api`, iss = web URL) that FastAPI verifies through `/api/auth/jwks` — the API side barely changed. Users get UUID ids (`generateId: "uuid"`) so `profiles.id` references `"user"(id)`; a trigger creates the profile. Migrations moved to `db/migrations/` with our own runner (`scripts/migrate.py`, `schema_migrations` table). RLS policies read `app_uid()` = `current_setting('app.user_id')` instead of Supabase's `auth.uid()`. **Consequences:** Supabase Storage is gone — PDF blob storage is decided in Phase 1 (candidates: Neon bytea for small files, Cloudflare R2/Backblaze B2 free tiers — R2 needs a card); `make db-reset` is not automatic. **Supersedes:** ADR-004, ADR-006 (client-side Supabase auth). **Revisit when:** Neon free limits (0.5 GB per project) become tight.

### ADR-006 · (superseded by ADR-007) Client-side auth with Bearer tokens in the web app · 2026-10-13
**Context:** Next.js 16 with `cacheComponents` makes cookie-based SSR auth more complex, and the TRD already says the web app talks only to the FastAPI API with `Authorization: Bearer`. **Options:** A) `@supabase/ssr` cookies + proxy; B) browser Supabase client (PKCE), session held client-side. **Decision:** B. **Why:** simplest correct option; pages stay static shells, and the API is the only trusted gate. **Revisit when:** a page needs server-rendered user data (e.g. SEO for share links — those are public anyway).

### ADR-005 · Replace shadcn's `cn` npm package with clsx + tailwind-merge · 2026-10-13
**Context:** `shadcn init` (base-nova preset) added a little-known `cn@0.4.0` dependency. **Decision:** remove it and use the standard `clsx` + `tailwind-merge` helper in `src/lib/utils.ts`. **Why:** supply-chain caution (docs/08); both replacements are MIT and widely used.

### ADR-004 · (superseded by ADR-007) Cloud Supabase project for development instead of the Docker stack · 2026-10-13
**Context:** Docker does not run on the developer's machine, so `supabase start` is unavailable. **Options:** A) Docker local stack (spec default); B) a free cloud Supabase project for dev; C) plain local Postgres without auth. **Decision:** B. **Why:** $0, keeps real Supabase Auth/JWKS/RLS, and the Supabase CLI (installed via npm, no Docker) applies migrations with `make db-migrate`. `make dev` therefore starts only the API and web; `make db-reset` is a documented no-op. CI still checks migrations against a pgvector Postgres container. **Conflict noted:** CLAUDE.md says `make dev` runs `supabase start`. **Revisit when:** Docker becomes available, or a second dev/prod project is needed (free plan allows 2 projects — use one for dev, one for prod).

### ADR-001 · One Postgres for rows, vectors and full-text · 2026-10
**Context:** Need vector search and keyword search at $0. **Options:** Pinecone/Chroma + Postgres, or Supabase Postgres with pgvector + tsvector. **Decision:** Supabase Postgres only. **Why:** one system, hybrid search in one SQL query, RLS, free tier. **Revisit when:** > 1M chunks or p95 retrieval > 400 ms.

### ADR-002 · OpenAI-compatible adapter for all LLM providers · 2026-10
**Context:** Must swap free providers as limits change. **Decision:** one client, per-provider `base_url`, model and key from config; router with fallback. **Why:** Groq, Gemini, OpenRouter and Ollama all expose OpenAI-compatible chat APIs; fewer dependencies. **Revisit when:** a needed feature (e.g. vision, JSON schema) is missing from a provider's compatible endpoint — then add a native adapter behind the same Protocol.

### ADR-003 · Permissive PDF parsing (pdfplumber/pypdfium2), GROBID optional · 2026-10
**Context:** PyMuPDF is AGPL; GROBID needs more RAM than the free API host. **Decision:** pdfplumber default, GROBID when `GROBID_URL` is set, arXiv HTML fast path. **Why:** licence freedom for future commercial use; fits 512 MB. **Revisit when:** parsing quality on the eval set is below target.
