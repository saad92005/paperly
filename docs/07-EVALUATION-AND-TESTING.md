# 07 · Evaluation and Testing

Paperly's promise is trust, so quality is measured, published and enforced in CI.

## 1. Golden dataset (`eval/`)

```
eval/
  papers/manifest.yaml        # 12 open-access arXiv papers (IDs only; PDFs downloaded at run time)
  questions.jsonl             # ~120 items
  run_eval.py                 # runs the real pipeline through the service layer
  judges.py                   # LLM-judge + deterministic metrics
  reports/2026-10-xx.md       # committed markdown reports (no PDFs)
```
**Paper mix:** classic and diverse layouts — e.g. *Attention Is All You Need*, *BERT*, *ResNet*, *YOLO*, *Vision Transformer (ViT)*, *LoRA*, *Retrieval-Augmented Generation (Lewis et al.)*, *Chain-of-Thought prompting*, *DDPM (diffusion)*, *CLIP*, one two-column conference paper with many tables, one long (40+ page) paper.

**Item schema:**
```json
{"id":"attn-007","papers":["1706.03762"],"question":"What BLEU score does the big model reach on WMT 2014 English-to-German?",
 "type":"numeric","answer":"28.4 BLEU","evidence":[{"paper":"1706.03762","page":8,"quote":"…28.4 BLEU…"}],
 "answerable":true,"level":"expert","lang":"en"}
```
**Coverage (≈120 items):** factual (30) · numeric results (20) · method explanation (20) · multi-paper comparison (15) · unanswerable/trick (20 — e.g. asks for a dataset the paper never uses) · non-English questions (10, Urdu/Spanish/Arabic) · follow-up turns (5).
Grow it weekly from thumbs-down feedback (anonymised, public papers only).

## 2. Metrics

| Metric | How | Target |
|---|---|---|
| Retrieval recall@8 | Gold evidence page/quote found in selected chunks | ≥ 0.90 |
| MRR | Rank of first gold chunk | ≥ 0.75 |
| Faithfulness | LLM-judge: share of answer claims supported by cited sources (RAGAS-style) | ≥ 0.90 |
| Citation precision | Cited sentence supports the claim (verifier prompt) | ≥ 0.90 |
| Citation recall | Factual sentences that carry a citation | ≥ 0.95 |
| Answer correctness | Judge vs gold answer (numeric: exact match after normalisation) | ≥ 0.85 |
| Abstention accuracy | NOT_FOUND on unanswerable, answered on answerable | ≥ 0.85 |
| Highlight accuracy | Highlighted rects overlap gold quote location (IoU > 0.3 on same page) | ≥ 0.85 |
| Latency | TTFT p50/p95, total p95 | ≤ 1.2 s / 2.5 s |
| Cost proxy | Avg prompt + completion tokens per answer | track trend |

**Judge setup:** use a different model family from the generator when possible (e.g. generate with Groq, judge with Gemini), temperature 0, fixed prompt version, 3 runs on disagreements. Deterministic checks (numbers, abstention, recall) never rely on an LLM. Libraries such as RAGAS or DeepEval may be used if their current versions support the chosen providers; otherwise the in-house `judges.py` implements the same definitions.

## 3. When evals run
- `make eval-smoke` (10 items, cached embeddings) on every PR touching `apps/api/app/{services,prompts,providers}` — blocks merge if faithfulness or abstention drops > 3 points vs `main`.
- `make eval` (full set) before each release and whenever a model, prompt, parser or chunker changes. Report committed to `eval/reports/` and the headline numbers copied into the README.
- Free-tier friendly: cache retrieval results and judge outputs by hash; run the full eval at most a few times per week.

## 4. Test pyramid

| Level | Tooling | What |
|---|---|---|
| Unit (API) | pytest | heading detection, column ordering, sentence boxes, chunk packing, RRF fusion, per-paper caps, marker parsing across token splits, renumbering, number guard, quota math, SM-2 scheduling, cache keys |
| Contract | pytest + httpx | every endpoint: auth, validation errors, error shape, pagination, SSE event order (`meta` → `token`/`citation` → `done`) |
| Provider | pytest with recorded fixtures (`respx`) | fallback on 429/5xx/timeout, cooling period, JSON-mode retry |
| Integration | pytest + local Supabase | ingest a fixture PDF end to end, hybrid SQL returns expected chunk, RLS denies cross-user reads |
| Frontend unit | Vitest + Testing Library | citation chip rendering, SSE parser, highlight rect transform, stores |
| E2E | Playwright | sign in (test user) → import arXiv paper → ask → click citation → highlight visible; notes export; compare 2 papers; quota message; dark mode; mobile viewport; axe accessibility scan |
| Load (pre-launch) | k6 or Locust | 20 concurrent askers on a warm instance; p95 within NFRs |

**Fixtures:** 3 tiny PDFs generated in-repo (one single-column, one two-column, one with a hidden-text injection line) so tests never depend on network.

## 5. CI pipeline (GitHub Actions)
1. `lint` — ruff, pyright, eslint, tsc.
2. `test-api` — spins up Postgres with pgvector service container, applies migrations, runs pytest with coverage (fail < 80% for `services/`).
3. `test-web` — vitest.
4. `e2e` — on `main` and release branches only (Supabase local in CI, providers mocked).
5. `eval-smoke` — conditional on paths; uses repo secrets for free-tier keys; skipped on forks.
6. `security` — `pip-audit`, `pnpm audit --prod`, gitleaks, Dependabot alerts.

## 6. Production quality loop
Langfuse traces every answer (retrieved chunk IDs, scores, prompt version, provider, latency, grounding result). Weekly: review thumbs-down answers and low-support answers → add to golden set → fix (parser, chunking, τ, prompt) → re-run eval → ship if better.
