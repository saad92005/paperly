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

### ADR-001 · One Postgres for rows, vectors and full-text · 2026-10
**Context:** Need vector search and keyword search at $0. **Options:** Pinecone/Chroma + Postgres, or Supabase Postgres with pgvector + tsvector. **Decision:** Supabase Postgres only. **Why:** one system, hybrid search in one SQL query, RLS, free tier. **Revisit when:** > 1M chunks or p95 retrieval > 400 ms.

### ADR-002 · OpenAI-compatible adapter for all LLM providers · 2026-10
**Context:** Must swap free providers as limits change. **Decision:** one client, per-provider `base_url`, model and key from config; router with fallback. **Why:** Groq, Gemini, OpenRouter and Ollama all expose OpenAI-compatible chat APIs; fewer dependencies. **Revisit when:** a needed feature (e.g. vision, JSON schema) is missing from a provider's compatible endpoint — then add a native adapter behind the same Protocol.

### ADR-003 · Permissive PDF parsing (pdfplumber/pypdfium2), GROBID optional · 2026-10
**Context:** PyMuPDF is AGPL; GROBID needs more RAM than the free API host. **Decision:** pdfplumber default, GROBID when `GROBID_URL` is set, arXiv HTML fast path. **Why:** licence freedom for future commercial use; fits 512 MB. **Revisit when:** parsing quality on the eval set is below target.
