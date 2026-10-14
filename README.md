# Paperly

**Read research papers with an AI that shows its sources.** Paperly answers questions about your papers with
**sentence-level citations**, highlights the exact evidence in the PDF, and says *"not found"* instead of guessing.
It runs at **$0**: free-tier hosting, local CPU embeddings and free LLM APIs. With no API key at all, it still works in an
honest extractive mode.

**Live:** https://paperly-beryl-ten.vercel.app

> Open source (MIT) · Next.js 16 + FastAPI · Postgres/pgvector on Neon · pdf.js · fastembed + FlashRank · Groq/Gemini/OpenRouter

## What it does

| | |
|---|---|
| 📄 **Import** | Upload PDFs, paste an arXiv ID / DOI / PDF link, or search arXiv + Semantic Scholar. Live progress: fetching → parsing → indexing. |
| 💬 **Cited chat** | Streamed answers where every factual sentence carries a `[n]` chip. Clicking a chip scrolls the PDF to the exact sentence and pulses its highlight. `J`/`K` steps through citations. |
| 🛡️ **Grounding** | An abstain gate (rerank + vector-similarity signals), a support check that compares each answer sentence with its cited sentences, a **number guard** (every number must appear in the source), and a *Grounded / Partly grounded* badge. |
| 🧭 **Reader** | pdf.js with an outline, zoom, find in paper, highlights and notes, and a selection toolbar (Explain · Simplify · Translate · equation explainer · Ask). There's a resizable side panel on desktop and Paper / Ask / Notes tabs on mobile. |
| 🧾 **Summaries** | Structured, cited summaries (TL;DR, problem, method, data, results, limitations, contributions) at ELI5, student or expert level, plus a glossary, share links and text-to-speech. |
| 📊 **Compare** | A cited matrix across 2–10 papers (task, method, data, metrics, results, compute, limitations, code). Every cell is strictly verified, and you can add custom columns. Export to CSV, XLSX or Markdown. |
| 🧠 **Study** | Cited flashcards with SM-2 spaced repetition and Anki export. |
| ✍️ **Lit review** | Clusters a collection into themes and writes a synthesis that cites every sentence (APA or IEEE). Export to `.md`, `.tex` or `.bib`. |
| 🔗 **More** | Collections, BibTeX/APA/IEEE export, reference resolution with one-click import, "cited by" lists, a command palette (`Ctrl K`), dark mode, data export and account deletion. |

## How it works

```
PDF ──► pdfplumber parser ──────────► structure-aware chunker ──► fastembed (bge-small, 384-d)
        • column detection              • never crosses a section        │
        • header/footer + invisible     • 380-token packs, 1-sentence    ▼
          (prompt-injection) text         overlap, context headers     Postgres (Neon)
          removal                       • abstract/captions/refs       halfvec HNSW + tsvector GIN
        • headings, captions, refs        kept separate                  │
        • pysbd sentences with boxes                                     │
                                                                         ▼
question ──► hybrid SQL (vector + full-text, RRF) ──► FlashRank rerank + blend ──► abstain gate
         ──► LLM router (Groq → Gemini → OpenRouter, fallback + cooling)  ──► streamed [S#] markers
         ──► renumber to [n] + pick exact cited sentence(s) by embedding ──► support check + number guard
```

- **Web:** Next.js 16 (App Router, `cacheComponents`), Tailwind v4 and shadcn/ui, TanStack Query, pdf.js, react-markdown with KaTeX and Mermaid (strict mode). Better Auth handles email/password and magic links, and issues 15-minute ES256 JWTs to the API.
- **API:** FastAPI with a Postgres job queue (`for update skip locked`, retries) and an in-process worker. SSE streams chat and job progress. Per-user quotas, rate limits, an SSRF-guarded fetcher and security headers.
- **Data:** Neon Postgres with pgvector 0.8. RLS policies serve as defence in depth. Migrations are plain SQL in `db/migrations`.

## Quality (measured, not claimed)

`make eval` runs the real pipeline on 45 questions over 5 arXiv papers (Transformer, BERT, RAG, ResNet, LoRA), including
unanswerable ones. Report: [`evals/report-golden.md`](evals/report-golden.md).

| Metric (retrieval + abstain, no LLM) | Value | Target |
|---|---|---|
| Recall@8 (evidence phrase in selected chunks) | **0.90** | ≥ 0.90 |
| MRR | **0.72** | ≥ 0.75 |
| Abstention accuracy | **1.00** | ≥ 0.85 |
| False abstain rate | **0.00** | — |

CI runs a fixture-based smoke gate (`make eval-smoke`) on every push. With an LLM key in `.env`, `make eval` also scores
answer correctness, citation hit rate and grounding.

## Run it locally

Requirements: Node 24 + pnpm, Python 3.12 + [uv](https://docs.astral.sh/uv/), a free [Neon](https://neon.tech) Postgres.

```bash
make setup                 # install deps
cp .env.example .env       # set DATABASE_URL (Neon, postgresql+asyncpg://…?ssl=require) and BETTER_AUTH_SECRET
make db-migrate            # apply db/migrations
make dev                   # web http://localhost:3000 · API http://localhost:8000
```

Optional: add a free `GROQ_API_KEY` (console.groq.com) or `GEMINI_API_KEY` (aistudio.google.com) to get written answers.
Without one, Paperly runs in extractive mode. Magic links print in the `make dev` console until `RESEND_API_KEY` is set.

| Command | |
|---|---|
| `make test` / `make lint` | API (pytest, ruff, pyright strict) and web (vitest, eslint, tsc) |
| `make e2e` | Playwright: sign up → import → ask → click citation → highlight, plus axe accessibility and 375 px checks |
| `make eval` / `make eval-smoke` | Golden-set evaluation / CI gate |

## Deploy ($0)

- **API → Vercel** (Python function, `apps/api`): `uv run python scripts/bundle_models.py && vercel deploy --prod`.
  `WORKER_MODE=request` runs queued jobs inside `POST /v1/worker/tick`, which the web app calls while it waits, so no
  always-on server is needed and nothing has to "wake up". Alternative: Render/Docker with `render.yaml` (512 MB-safe, ADR-011).
- **Web → Vercel** (root `apps/web`). Env: `DATABASE_URL`, `BETTER_AUTH_SECRET`, `WEB_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`.
- **Ops:** `.github/workflows/ops.yml` runs a daily `/health` check and a weekly encrypted `pg_dump`.

## Docs

`docs/` holds the full spec: PRD, TRD, data model, API, UI/UX, AI pipeline and prompts, evaluation, security, deployment and roadmap.
Decisions are recorded as ADRs in [`docs/DECISIONS.md`](docs/DECISIONS.md), and progress per phase is in [`docs/PROGRESS.md`](docs/PROGRESS.md).

## License

MIT. Paperly processes papers you upload or that are openly accessible, and never republishes PDFs.
