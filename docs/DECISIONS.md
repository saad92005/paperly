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

### ADR-006 · Client-side auth with Bearer tokens in the web app · 2026-10-13
**Context:** Next.js 16 with `cacheComponents` makes cookie-based SSR auth more complex, and the TRD already says the web app talks only to the FastAPI API with `Authorization: Bearer`. **Options:** A) `@supabase/ssr` cookies + proxy; B) browser Supabase client (PKCE), session held client-side. **Decision:** B. **Why:** simplest correct option; pages stay static shells, and the API is the only trusted gate. **Revisit when:** a page needs server-rendered user data (e.g. SEO for share links — those are public anyway).

### ADR-005 · Replace shadcn's `cn` npm package with clsx + tailwind-merge · 2026-10-13
**Context:** `shadcn init` (base-nova preset) added a little-known `cn@0.4.0` dependency. **Decision:** remove it and use the standard `clsx` + `tailwind-merge` helper in `src/lib/utils.ts`. **Why:** supply-chain caution (docs/08); both replacements are MIT and widely used.

### ADR-004 · Cloud Supabase project for development instead of the Docker stack · 2026-10-13
**Context:** Docker does not run on the developer's machine, so `supabase start` is unavailable. **Options:** A) Docker local stack (spec default); B) a free cloud Supabase project for dev; C) plain local Postgres without auth. **Decision:** B. **Why:** $0, keeps real Supabase Auth/JWKS/RLS, and the Supabase CLI (installed via npm, no Docker) applies migrations with `make db-migrate`. `make dev` therefore starts only the API and web; `make db-reset` is a documented no-op. CI still checks migrations against a pgvector Postgres container. **Conflict noted:** CLAUDE.md says `make dev` runs `supabase start`. **Revisit when:** Docker becomes available, or a second dev/prod project is needed (free plan allows 2 projects — use one for dev, one for prod).

### ADR-001 · One Postgres for rows, vectors and full-text · 2026-10
**Context:** Need vector search and keyword search at $0. **Options:** Pinecone/Chroma + Postgres, or Supabase Postgres with pgvector + tsvector. **Decision:** Supabase Postgres only. **Why:** one system, hybrid search in one SQL query, RLS, free tier. **Revisit when:** > 1M chunks or p95 retrieval > 400 ms.

### ADR-002 · OpenAI-compatible adapter for all LLM providers · 2026-10
**Context:** Must swap free providers as limits change. **Decision:** one client, per-provider `base_url`, model and key from config; router with fallback. **Why:** Groq, Gemini, OpenRouter and Ollama all expose OpenAI-compatible chat APIs; fewer dependencies. **Revisit when:** a needed feature (e.g. vision, JSON schema) is missing from a provider's compatible endpoint — then add a native adapter behind the same Protocol.

### ADR-003 · Permissive PDF parsing (pdfplumber/pypdfium2), GROBID optional · 2026-10
**Context:** PyMuPDF is AGPL; GROBID needs more RAM than the free API host. **Decision:** pdfplumber default, GROBID when `GROBID_URL` is set, arXiv HTML fast path. **Why:** licence freedom for future commercial use; fits 512 MB. **Revisit when:** parsing quality on the eval set is below target.
