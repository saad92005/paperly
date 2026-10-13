# 04 · API Specification

Base URL: `/v1`. JSON over HTTPS. Auth: `Authorization: Bearer <Supabase access token>` on every route except `/health` and `/v1/share/*`. FastAPI generates OpenAPI at `/openapi.json`; TypeScript types are generated from it (`make types`).

## 1. Conventions

- IDs are UUIDs. Timestamps are ISO-8601 UTC.
- Pagination: `?limit=20&cursor=<opaque>` → `{items:[...], next_cursor: string|null}`.
- Idempotency: `POST` routes that create jobs accept `Idempotency-Key` header (24 h).
- Rate-limit headers on every response: `X-RateLimit-Remaining`, `X-Quota-Questions-Remaining`, `Retry-After` on 429.
- Error shape (all non-2xx):
```json
{ "error": { "code": "quota_exceeded", "message": "Daily question limit reached. Resets at 00:00 UTC.",
             "details": {"reset_at": "2026-10-14T00:00:00Z"}, "request_id": "req_8f2c..." } }
```
Codes: `unauthorized`, `forbidden`, `not_found`, `validation_error`, `unsupported_file`, `too_large`, `too_many_pages`, `scanned_pdf`, `quota_exceeded`, `rate_limited`, `provider_unavailable`, `conflict`, `internal`.

## 2. Endpoints

### Health and me
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | `{status, version, db, worker}` — used for cold-start detection |
| GET | `/v1/me` | Profile + plan + settings |
| PATCH | `/v1/me` | Update `display_name`, `locale`, `explain_level` |
| GET | `/v1/me/usage` | Today's usage vs quota |
| DELETE | `/v1/me` | Delete account and all owned data (async job; returns 202) |

### Papers and imports
| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/v1/papers/upload` | multipart `file`, optional `collection_id` | 202 `{paper_id, job_id}` |
| POST | `/v1/papers/import` | `{source: "arxiv"\|"doi"\|"url", value, collection_id?}` | 202 `{paper_id, job_id}` or 200 if cache hit `{paper_id, status:"ready"}` |
| GET | `/v1/papers` | `collection_id?`, `q?`, `starred?`, `status?`, pagination | `{items:[PaperCard], next_cursor}` |
| GET | `/v1/papers/{id}` | — | `Paper` (metadata, status, sections outline, user fields) |
| PATCH | `/v1/papers/{id}` | `{collection_id?, tags?, starred?, read_progress?}` | `Paper` |
| DELETE | `/v1/papers/{id}` | — | 204 (removes user link; deletes private paper rows/blob) |
| GET | `/v1/papers/{id}/file` | — | 307 to a signed URL (uploads) or arXiv PDF URL |
| GET | `/v1/papers/{id}/chunks/{chunk_id}` | — | Chunk text + sentences + boxes (for highlight) |
| GET | `/v1/papers/{id}/references` | — | Parsed references with resolution status |
| GET | `/v1/papers/{id}/citations` | — | "Cited by" list from Semantic Scholar/OpenAlex (cached) |
| GET | `/v1/papers/{id}/bibtex` | `style=bibtex\|apa\|ieee` | text |

### Jobs
| Method | Path | Returns |
|---|---|---|
| GET | `/v1/jobs/{id}` | `{id, type, status, stage, progress, error}` |
| GET | `/v1/jobs/{id}/events` | SSE: `progress` events `{stage, progress}` then `done` or `error` |

### Chat
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/v1/threads` | `{scope: {paper_ids:[...]} \| {collection_id}, title?}` | `Thread` |
| GET | `/v1/threads` | `paper_id?`, pagination | `{items, next_cursor}` |
| GET | `/v1/threads/{id}` | — | `Thread` + messages |
| DELETE | `/v1/threads/{id}` | — | 204 |
| POST | `/v1/threads/{id}/messages` | `{content, mode: "grounded"\|"strict", level?: "eli5"\|"student"\|"expert", lang?, selection?: {paper_id, page, text}}` | **SSE stream** (below) |
| POST | `/v1/messages/{id}/feedback` | `{rating: 1\|-1, reason?}` | 204 |
| POST | `/v1/messages/{id}/save-note` | `{paper_id}` | `Note` |

**Chat SSE events** (`Content-Type: text/event-stream`):
```
event: meta
data: {"message_id":"…","provider":"groq","model":"…","intent":"qa","scope_paper_ids":["…"]}

event: token
data: {"t":"The paper introduces the Transformer"}

event: citation
data: {"n":1,"paper_id":"…","chunk_id":"…","page":3,"section":"3 Model Architecture",
       "sentence_idx":[2,3],"quote":"The Transformer follows this overall architecture…",
       "rects":[{"page":3,"rect":[108.0,512.4,504.1,530.9]}]}

event: diagram
data: {"mermaid":"flowchart LR\n A[Input Embedding] --> B[Multi-Head Attention] --> C[Feed Forward]"}

event: done
data: {"grounded":true,"support_score":0.93,"usage":{"prompt_tokens":2100,"completion_tokens":240},
       "latency_ms":1840,"cached":false}

event: error
data: {"code":"provider_unavailable","message":"All AI providers are busy. Try again in a minute."}
```
Tokens arrive with internal markers already replaced by `[n]`. The client renders `[n]` as a citation chip as soon as the matching `citation` event arrives (it is sent the moment its marker is seen).

### Summaries and study
| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/v1/papers/{id}/summary` | `kind=structured\|tldr\|glossary\|reading_path`, `lang`, `level` | 200 cached JSON, or SSE stream while generating |
| POST | `/v1/papers/{id}/summary/regenerate` | same | 202 `{job_id}` |
| POST | `/v1/papers/{id}/explain` | `{text, page, kind: "explain"\|"simplify"\|"translate"\|"equation", lang?, level?}` | SSE (same events as chat) |
| POST | `/v1/papers/{id}/flashcards` | `{count: 5..30}` | 202 `{job_id}` |
| GET | `/v1/flashcards/due` | `limit` | cards due today |
| POST | `/v1/flashcards/{id}/review` | `{grade: 0..5}` | updated schedule (SM-2) |

### Notes and collections
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/v1/collections` | list / create |
| PATCH/DELETE | `/v1/collections/{id}` | rename / delete (papers stay in library) |
| GET/POST | `/v1/papers/{id}/notes` | list / create `{anchor?, body_md, color}` |
| PATCH/DELETE | `/v1/notes/{id}` | edit / delete |
| GET | `/v1/papers/{id}/notes/export` | `format=md` → Markdown with page refs |

### Compare and export
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/v1/comparisons` | `{paper_ids, columns?: [{label, question}]}` (default columns if omitted) | 202 `{comparison_id, job_id}` |
| GET | `/v1/comparisons/{id}` | — | matrix with per-cell status, value, citations |
| POST | `/v1/comparisons/{id}/columns` | `{label, question}` | 202 (fills new column) |
| GET | `/v1/comparisons/{id}/export` | `format=csv\|xlsx\|md` | file |
| POST | `/v1/collections/{id}/review` | `{topic?, style: "apa"\|"ieee", length: "short"\|"long"}` | 202 job → lit review draft |
| GET | `/v1/exports/{job_id}` | `format=md\|docx\|tex\|bib` | file |
| POST | `/v1/share` | `{kind: "summary"\|"comparison", ref_id}` | `{share_id, url}` |
| GET | `/v1/share/{share_id}` | public, no auth | read-only content (no PDF, no notes) |

### Discover
| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/v1/discover/search` | `q`, `source=arxiv\|s2\|all`, `year_from?`, `open_access_only=true` | normalised results `{title, authors, year, venue, abstract, arxiv_id, doi, oa_pdf, in_library}` |

### Admin (is_admin only)
| Method | Path | Returns |
|---|---|---|
| GET | `/v1/admin/metrics` | users, papers, jobs by status, provider error rates, p95 latencies, quota hits |
| GET | `/v1/admin/jobs?status=failed` | failed jobs with errors |
| POST | `/v1/admin/jobs/{id}/retry` | re-queues a failed job |

## 3. Core response models (abridged)

```ts
type PaperCard = {
  id: string; title: string | null; authors: {name: string}[]; year: number | null;
  venue: string | null; source: "upload" | "arxiv" | "doi" | "url";
  status: "queued" | "fetching" | "parsing" | "indexing" | "ready" | "failed";
  page_count: number | null; starred: boolean; read_progress: number;
  collection_id: string | null; tags: string[]; added_at: string;
};

type Citation = {
  n: number; paper_id: string; chunk_id: string; page: number; section: string | null;
  sentence_idx: number[]; quote: string;
  rects: { page: number; rect: [number, number, number, number] }[];  // PDF user-space points
};

type StructuredSummary = {
  tldr: CitedText[]; problem: CitedText[]; method: CitedText[]; data: CitedText[];
  results: CitedText[]; limitations: CitedText[]; contributions: CitedText[];
  keywords: string[];
};
type CitedText = { text: string; citations: Citation[] };
```
