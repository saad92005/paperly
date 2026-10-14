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

### ADR-014 · Tailwind via PostCSS, not a Turbopack CSS rule · 2026-10-14
**Context:** the Phase 0 custom Turbopack rule (`*.css` → `@tailwindcss/turbopack`) also captured `next/font`'s generated CSS and broke `next build`. **Decision:** standard `@tailwindcss/postcss` plugin (`postcss.config.mjs`). **Why:** documented path, works for dev and production builds.

### ADR-013 · Observability: Sentry optional, Langfuse deferred · 2026-10-14
**Context:** docs/09 lists Langfuse tracing and Sentry for web + API. **Decision:** API initialises Sentry only when `SENTRY_DSN` is set (errors only, `send_default_pii=False`, no request bodies, so paper text never leaves). Web Sentry and Langfuse are deferred. LLM latency, provider error rates, grounding rate and feedback are already recorded in Postgres (`provider_events`, `messages`, `feedback`) and shown on `/admin`. **Revisit when:** there's real traffic, or prompt-level traces are needed to debug quality.

### ADR-012 · Retrieval scoring: blended score + two-signal abstain gate · 2026-10-14
**Context:** FlashRank alone mis-ranked long chunks (it truncates to 256 tokens to stay within 512 MB RAM) and scored short valid questions near 0 ("What optimizer was used?" → 0.002), so a rerank-only abstain gate refused answerable questions. **Decision:** final score = 0.65·rerank + 0.35·normalised vector similarity + a small heading-match boost, ×0.6 for `equation` chunks (symbol debris). Abstain only when rerank < 0.15 **and** best cosine < 0.62, and never for questions about parts every paper has (method, results, limitations…). **Evidence (golden set, 45 items):** recall@8 0.87 → 0.90, MRR 0.67 → 0.72, abstention accuracy 0.98 → 1.00 (in-domain cosine ≥ 0.67, off-topic ≤ 0.58). **Revisit when:** the golden set grows or the embedding model changes (re-calibrate thresholds).

### ADR-011 · Memory budget for a 512 MB API host · 2026-10-14
**Context:** with default settings (batch 64, all threads) the API peaked at ~1.1 GB, which won't fit Render's free 512 MB. **Decision:** `EMBED_BATCH=4`, `EMBED_THREADS=1`, FlashRank `max_length=256`, reranking in batches of 10, worker concurrency 1 in production. Peak measured at ~360 MB. Local `.env` can raise batch/threads for speed. **Trade-off:** ingest is slower on the free host (minutes for a long paper; progress is streamed).

### ADR-010 · Extractive mode when no LLM key is configured · 2026-10-14
**Context:** the app must work at $0, even before anyone creates a Groq/Gemini key. **Decision:** without a provider, chat returns the best-matching sentences from the retrieved chunks (each cited, clearly labelled "extractive mode"), summaries are built from quoted sentences per section, and comparison cells hold the best matching sentence. Features that genuinely need generation (glossary, flashcards, lit review, explain) return `provider_unavailable` with setup instructions. If every provider fails mid-request before any token is streamed, chat degrades to extractive instead of erroring.

### ADR-009 · Box coordinates are PDF points with a top-left origin · 2026-10-14
**Decision:** sentence and highlight rects are stored as `[page, x0, top, x1, bottom]` in PDF points with a top-left origin (pdfplumber's space). The reader multiplies by the zoom factor, with no y-flip. User highlights captured from the pdf.js text layer are converted back into the same space.

### ADR-008 · PDF blobs in Postgres (bytea); arXiv PDFs not stored · 2026-10-14
**Context:** Supabase Storage is gone (ADR-007), and R2/B2 need a card or extra accounts. **Options:** A) Postgres `blobs` table; B) Cloudflare R2; C) local disk (lost on free-host restarts). **Decision:** A, behind the `BlobStore` Protocol. Uploads ≤ 25 MB. arXiv papers are fetched on demand through an in-memory LRU proxy (`/v1/papers/{id}/file`), so the browser never hits arXiv's CORS and their bytes never take DB space. **Revisit when:** blobs exceed ~200 MB of the 0.5 GB Neon free tier (`/admin` shows the size); then switch the implementation to R2.

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
