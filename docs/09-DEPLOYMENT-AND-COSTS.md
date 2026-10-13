# 09 · Deployment, Operations and Costs

## 1. Environments

| Env | Web | API + worker | DB / Auth / Storage | LLMs |
|---|---|---|---|---|
| **Local dev** | `next dev` | `uvicorn --reload` (in-process worker) | `supabase start` (Docker) | Groq/Gemini free keys or Ollama |
| **Self-host / offline** | container | container | Postgres + pgvector container, local auth | Ollama + GROBID containers |
| **Production ($0)** | Vercel Hobby | Render free web service | Supabase free project | Groq → Gemini → OpenRouter free tiers |

## 2. Accounts to create (all free)
GitHub · Supabase · Groq Console · Google AI Studio (Gemini key) · OpenRouter · Vercel · Render · Langfuse Cloud · Sentry · (optional) PostHog, Resend, Cloudflare (Turnstile).
Card-free path: GitHub, Supabase, Groq, Google AI Studio, OpenRouter, Vercel, Render. Keep keys in a password manager; add them as environment secrets, never in code.

## 3. Production runbook (first deploy)
1. **Supabase:** create project → enable `vector` and `pg_trgm` extensions → `supabase link` + `supabase db push` (applies migrations) → create private Storage bucket `papers` → Auth: enable Google provider and magic link, set Site URL and redirect URLs to the Vercel domain.
2. **Render (API):** New Web Service from the repo, root `apps/api`, Docker or native Python build (`uv sync --frozen`), start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; set env vars from `.env.example`; health check path `/health`.
3. **Vercel (web):** import repo, root `apps/web`, env `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
4. **Smoke test:** sign in → import `1706.03762` → ask a question → click a citation → check Langfuse trace and Sentry are receiving data.
5. **Tag release** `v1.0.0`; publish eval report in the README.

## 4. Living with free tiers

| Limit | Effect | Mitigation built into Paperly |
|---|---|---|
| Render free sleeps after ~15 min idle (cold start 30–60 s) | First request is slow | `/health` probe + "waking up" banner; web prefetches `/health` on page load; cached summaries load from DB via API once awake |
| Supabase free pauses after 7 days of inactivity | App down until resumed | Weekly scheduled GitHub Action runs a trivial authenticated query; README tells self-hosters how to resume a paused project |
| Supabase free: 500 MB DB, 1 GB files | Storage ceiling | `halfvec`, no stored arXiv PDFs, shared public cache, 25 MB / 100-page caps, admin storage meter with alert at 80% |
| LLM free tiers are rate-limited (per minute and per day) | 429s at peaks | Provider fallback chain, response caching, `locate` intent with no LLM call, per-user quotas, queueing for heavy jobs |
| Free-tier data-use and commercial terms | Privacy/commercial limits | Disclosure in settings; local mode; switch providers by config before monetising |
| Vercel Hobby is for non-commercial use | Can't charge users on it | Move web to Cloudflare Workers (OpenNext) or Vercel Pro when monetising |
| No managed backups on free DB | Risk of data loss | Weekly `pg_dump` GitHub Action (encrypted artifact) |

**Alternative API hosts** (check current terms before choosing): Google Cloud Run (generous free tier, needs a billing account/card), Oracle Cloud Always Free VM (card verification; enough RAM to run GROBID and the API together), Koyeb (free tier terms have changed in 2026 — verify). Hugging Face Docker Spaces now require a paid plan for new accounts, so they are not used.

## 5. Observability and operations
- **Dashboards:** Langfuse (latency, tokens, provider mix, grounding rate), Sentry (errors, release health), `/admin` (jobs, failures, quotas, storage).
- **Alerts (free):** Sentry email on new issue; GitHub Action daily check that posts to email if `/health` fails or DB > 80%.
- **Runbooks** in `docs/runbooks/`: provider outage, DB near limit, stuck jobs, bad deploy rollback (Render and Vercel both support instant rollback to previous deploy).

## 6. Self-host (`infra/docker-compose.selfhost.yml`)
Services: `db` (`pgvector/pgvector:pg16`), `api` (with `WORKER_MODE=inprocess`, `AUTH_MODE=local` single-user or GoTrue), `web`, `grobid` (`grobid/grobid` image, CPU), `ollama` (pull an 8B instruct model on first run). One command: `docker compose -f infra/docker-compose.selfhost.yml up`. Minimum machine: 4 CPU cores, 16 GB RAM recommended (GROBID + 8B model).

## 7. Cost model

| Stage | Users (DAU) | Monthly cost | What changes |
|---|---|---|---|
| Build + portfolio demo | 1–50 | **$0** | Everything on free tiers |
| Early traction | 50–300 | **$0–7** | Optionally keep API warm on a paid instance (Render starter plans from ~$7/mo) |
| Growing | 300–2,000 | **~$35–100** | Supabase Pro ($25/mo base: 8 GB DB), paid LLM tier usage-based, Vercel Pro or Cloudflare |
| Monetised (Pro plan) | 2,000+ | revenue-funded | Separate worker service, dedicated GROBID, paid models for Pro users |

The architecture does not change between stages — only configuration and plan levels.

## 8. Launch checklist
README with GIF demo, architecture diagram and eval numbers · MIT licence · `SECURITY.md`, `CONTRIBUTING.md`, issue templates · Privacy Policy and Terms pages · demo video (2 min) · seed demo account with 5 classic papers · posts: GitHub, LinkedIn, Product Hunt, relevant subreddits and university groups · blog post: "Sentence-level citations on a $0 stack — what it took".
