# 10 · Roadmap, Phases and Risks

Each phase is one or more Claude Code sessions. Do not start a phase until the previous one meets its **Definition of Done (DoD)**. Estimates assume part-time work (≈ 3–4 focused hours a day) with Claude Code doing most of the typing.

## Timeline at a glance

| # | Phase | Release | Estimate |
|---|---|---|---|
| 0 | Foundation | MVP | 2–3 days |
| 1 | Ingestion | MVP | 1 week |
| 2 | Retrieval + grounded chat | MVP | 1.5 weeks |
| 3 | Reader + citations-to-highlight + notes | MVP | 1 week |
| 4 | Summaries, collections, multi-paper, levels, exports | MVP | 1 week |
| 5 | Quality, eval, observability, security | MVP | 1 week |
| 6 | Deploy + launch MVP | MVP | 3–4 days |
| 7 | Comparison matrix | 1.5 | 1 week |
| 8 | Discover, references, shared cache, arXiv HTML path | 1.5 | 1 week |
| 9 | Glossary, equation explainer, diagrams, multilingual | 1.5 | 1 week |
| 10 | Study mode, lit-review drafter, share links | 1.5 | 1 week |
| 11 | Self-host / local mode | 1.5 | 3–4 days |
| 12–15 | v2 moat features | 2.0 | 6–8 weeks |

## MVP phases

### Phase 0 — Foundation
**Build:** monorepo layout from `CLAUDE.md`; `uv` + FastAPI skeleton (`/health`, settings, logging, error handler, request IDs); provider Protocols with stub implementations; Next.js app with Tailwind, shadcn/ui, design tokens, light/dark; Supabase local stack; first migration (profiles, collections, papers, user_papers, jobs); Supabase Auth (Google + magic link) in web; JWT verification in API; `GET /v1/me`; Makefile targets; `.env.example`; GitHub Actions (lint + tests); `docs/PROGRESS.md`, `docs/DECISIONS.md`.
**DoD:** `make setup && make dev` works from a clean clone; a user can sign in and see an empty library; `/v1/me` returns the profile; CI green.

### Phase 1 — Ingestion
**Build:** upload endpoint (validation, hashing, Storage), arXiv/DOI import (arXiv API, Unpaywall/Crossref resolution, SSRF guard), Postgres job queue + in-process worker with retries and SSE progress; pdfplumber parser (column order, header/footer and invisible-text removal, headings, captions, references, scanned detection), `pysbd` sentences with rects; chunker; fastembed embeddings; chunks/sections migration with HNSW + GIN; metadata extraction; library UI with import dialog and live status; **dev-only debug view** `/paper/[id]/debug` that overlays chunk and sentence boxes on the PDF.
**DoD:** the 3 fixture PDFs and 5 arXiv papers ingest correctly (sections sensible, references excluded from body, hidden-text line removed); 15-page paper indexes in ≤ 60 s locally; unit tests for parser and chunker pass.

### Phase 2 — Retrieval and grounded chat
**Build:** hybrid search SQL + RRF; FlashRank rerank; selection with per-paper caps; abstain gate; OpenAI-compatible LLM adapter for Groq/Gemini/OpenRouter/Ollama with router + fallback + cooling; query analyzer (with skip heuristic); answer prompt `answer.v1`; SSE streaming with marker parsing and renumbering; sentence-level citation selection; support check + number guard; threads/messages/feedback; quotas + usage; exact + semantic cache; minimal chat panel UI.
**DoD:** streamed cited answers on all 5 papers; unanswerable questions return NOT_FOUND; provider fallback proven by a test that forces 429; `make eval-smoke` runs and records a baseline; TTFT p95 ≤ 2.5 s locally (warm).

### Phase 3 — Reader, citation highlights, notes
**Build:** pdf.js reader (virtualised pages, zoom, outline, thumbnails, find-in-paper); highlight layer (PDF-space → viewport rects); citation click → scroll + pulse highlight; `J/K` citation navigation; selection toolbar (Highlight, Note, Explain, Simplify, Translate, Ask); notes CRUD + Markdown export; resizable split view; mobile tab layout; read-progress tracking.
**DoD:** clicking any citation lands on the right sentence on the right page for the 5 papers; notes persist and export; Playwright test covers ask → click citation → highlight visible; works at 375 px width.

### Phase 4 — Summaries, collections, multi-paper, levels, exports
**Build:** structured summary job + Summary tab (cited bullets, regenerate, copy); collections and tags; scope switcher (paper / selected / collection); multi-paper retrieval and paper colour coding; explain levels and language selector (English answers in MVP, other languages behind a flag); BibTeX/APA/IEEE export; settings page; usage meter; command palette.
**DoD:** summary renders in ≤ 20 s first time and instantly after; a 3-paper question cites at least two papers when relevant; exports validate (BibTeX parses).

### Phase 5 — Quality, eval, observability, security
**Build:** full golden set (≈120 items) + `make eval` report; CI eval-smoke gate; Langfuse tracing; Sentry (web + API); `/admin` page; security headers, CORS, rate limits, Turnstile hook (off by default); Playwright suite incl. axe accessibility checks; performance pass (bundle size, DB indexes, N+1 check).
**DoD:** eval meets PRD targets or gaps are listed with a plan; no critical axe violations; Lighthouse ≥ 90 on Library and Reader; all security controls in `08-SECURITY-PRIVACY.md` implemented or explicitly deferred in DECISIONS.md.

### Phase 6 — Deploy and launch MVP
**Build:** production deploy per `09-DEPLOYMENT-AND-COSTS.md`; GitHub Actions for Supabase keep-alive, weekly `pg_dump`, health alert; landing page; README (GIF, architecture, eval table, self-host instructions); Privacy/Terms pages; `SECURITY.md`, `CONTRIBUTING.md`; demo seed.
**DoD:** a stranger can sign up on the live URL, import a paper and get a cited answer; rollback tested once; tag `v1.0.0`.

## v1.5 phases (differentiators)
- **Phase 7 — Comparison matrix:** default + custom columns, per-paper batched extraction, strict verification, streaming cells, CSV/XLSX/MD export, share link.
- **Phase 8 — Discover and connect:** arXiv + Semantic Scholar search, one-click import, references resolution, "cited by", mini citation graph, shared public-paper cache, arXiv HTML fast path.
- **Phase 9 — Understanding tools:** glossary + hover definitions, equation explainer (KaTeX), Mermaid diagrams in answers, full multilingual answers with RTL.
- **Phase 10 — Study and synthesis:** flashcards + quiz + Anki export, literature-review drafter (.md/.docx/.tex + .bib), public share pages.
- **Phase 11 — Self-host / local mode:** docker-compose with Ollama, GROBID, local auth; docs and a one-command start.

## v2 phases (moat)
- **Phase 12:** figure and table Q&A (vision), table → CSV; claim check across a collection.
- **Phase 13:** research agent (bounded tool loop, step log, cited mini-review).
- **Phase 14:** MCP server (`search_library`, `ask`, `get_citation`, `add_paper`), browser extension, Zotero/BibTeX import.
- **Phase 15:** topic/author alerts digest, spaced repetition, audio overview, team workspaces with shared collections and comments.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Free-tier limits or terms change | High | High | Provider interfaces, config-driven routes, fallback chain, local mode, cost plan ready |
| Parsing errors on complex layouts (two-column, math, tables) | Medium | High | Column detection + debug view; GROBID in self-host; arXiv HTML path; eval set includes hard layouts |
| Hallucinated or loosely cited answers | Medium | High | Abstain gate, forced markers, support check, number guard, strict mode, CI eval gate |
| Cold starts make the app feel broken | High | Medium | Waking banner, prefetch `/health`, cached content, optional ~$7/mo warm instance later |
| Storage ceiling (500 MB DB / 1 GB files) | Medium | Medium | `halfvec`, shared cache, no stored arXiv PDFs, caps, storage alerts |
| Scope creep (too many features) | High | High | Strict phase gates; P1/P2 never start before MVP ships |
| Third-party API rate limits (arXiv, Semantic Scholar) | Medium | Low | Caching, backoff, polite delays, contact email in User-Agent |
| Copyright complaints | Low | Medium | Only uploads + open access; no PDF redistribution; takedown contact |
| Abuse / spam sign-ups draining quotas | Medium | Medium | Verified email, quotas, IP rate limits, Turnstile switch |
| Security issue in dependencies | Medium | High | Lockfiles, audits, Dependabot, minimal dependencies |
