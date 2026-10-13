# 08 · Security and Privacy

Baseline: OWASP ASVS Level 1 plus the AI-specific controls below. Threat model in one line: *untrusted PDFs and untrusted users, talking to third-party AI providers on free tiers.*

## 1. Threats and controls

| Threat | Control |
|---|---|
| Malicious PDF (exploit in viewer) | pdf.js kept current; `isEvalSupported: false`; render in the main origin with a strict CSP; no PDF JavaScript, forms or embedded files executed |
| Malicious PDF (server parser) | Parse in a worker task with timeout (60 s), memory guard, page cap; magic-byte check (`%PDF-`); size ≤ 25 MB; reject encrypted PDFs with a clear message |
| Prompt injection inside papers | Strip invisible text at parse time; delimited untrusted SOURCES block; system rule to ignore instructions in sources; model has no tools or secrets in answer mode; output rendered with HTML disabled |
| SSRF via URL import | Allow-list hosts (arxiv.org, export.arxiv.org, doi.org resolution through Unpaywall/Crossref, known OA hosts); resolve DNS and block private/link-local ranges; no redirects to disallowed hosts; 30 s timeout; 25 MB cap |
| Broken access control | JWT verified on every request (Supabase JWKS, `aud`/`exp` checked); ownership checks in services; RLS on every user table; IDs are UUIDs; tests for cross-user access |
| Secret leakage | Keys only in server env (Render/Vercel secrets); web bundle uses only the Supabase anon key; gitleaks in CI; no prompts or paper text in INFO logs |
| Abuse of free tiers | Per-user quotas (Postgres counters), per-IP rate limit on auth and import routes, job concurrency caps, email-verified accounts only, CAPTCHA (Cloudflare Turnstile, free) on sign-up if abuse appears |
| Supply chain | Lockfiles committed (`uv.lock`, `pnpm-lock.yaml`), pinned versions, Dependabot, `pip-audit`/`pnpm audit`; minimal dependency count; review new packages before adding (popular AI packages have been targeted by malicious releases) |
| XSS via model output | Markdown renderer with raw HTML disabled, URL sanitiser, Mermaid `securityLevel: 'strict'`, KaTeX `trust: false`, CSP `script-src 'self'` |
| Data loss | Supabase daily backups exist only on paid plans → weekly `pg_dump` via GitHub Actions to a private artifact (encrypted) while on free plan |

## 2. Security headers (web and API)
`Content-Security-Policy` (self + Supabase + API origins; `frame-ancestors 'none'`), `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (no camera/mic/geolocation). CORS on the API: exact web origin(s) only.

## 3. Privacy

- **Private by default.** Uploads are visible only to their owner. Only arXiv/open-access imports enter the shared cache, and a user's notes, chats and highlights are never shared.
- **Provider transparency.** Settings → Data & privacy lists which providers may process text and links to their terms. Free tiers of some providers may use inputs to improve models and may restrict commercial use — this is stated plainly. Each answer shows the provider that produced it.
- **Local mode.** Self-host (`infra/docker-compose.selfhost.yml`) runs Ollama + local embeddings + GROBID: no paper text leaves the machine. Telemetry off by default there.
- **Data minimisation.** Store only what features need; no tracking cookies without consent; PostHog (if enabled) anonymised and opt-out respected.
- **User rights.** Export my data (JSON + Markdown notes + BibTeX) and delete my account (cascade delete of rows and blobs within 24 h, logged).
- **Copyright.** Paperly processes papers the user uploads or that are openly accessible. It never republishes PDFs; share links expose only generated summaries/comparisons and short quotes with attribution.
- **Policies to publish before launch:** Privacy Policy, Terms of Use, Acceptable Use, and a security contact (`SECURITY.md` with responsible-disclosure email).
