# 03 · Data Model

Postgres 15+ on Supabase with `pgvector` ≥ 0.7 (for `halfvec`) and built-in full-text search. Every migration is plain SQL in `supabase/migrations/`.

## 1. Entity overview

```
auth.users ─1:1─ profiles
profiles ─1:n─ collections
profiles ─n:m─ papers          (via user_papers; one paper row can serve many users if public)
papers ─1:n─ sections ─1:n─ chunks          (chunks carry embeddings, FTS, sentence boxes)
papers ─1:n─ references_parsed
papers ─1:n─ summaries         (per kind + language + level)
profiles ─1:n─ threads ─1:n─ messages ─1:n─ feedback
profiles ─1:n─ notes           (anchored to paper page rectangles)
profiles ─1:n─ comparisons
profiles ─1:n─ flashcards
jobs, llm_cache, usage_daily, provider_events (operational)
```

**Shared public-paper cache.** A paper imported from arXiv or an open-access DOI is stored once with `visibility = 'public_cache'` and `owner_id = null`. Each user who adds it gets a `user_papers` row. Private uploads always get `visibility = 'private'` and an `owner_id`, even if another user uploaded identical bytes (no cross-user dedupe for private files).

## 2. Schema (core)

```sql
create extension if not exists vector;
create extension if not exists pg_trgm;

create type paper_source as enum ('upload','arxiv','doi','url');
create type paper_visibility as enum ('private','public_cache');
create type paper_status as enum ('queued','fetching','parsing','indexing','ready','failed');
create type chunk_kind as enum ('abstract','body','caption','table','equation','reference');
create type job_status as enum ('queued','running','succeeded','failed','cancelled');

create table profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  display_name  text,
  locale        text not null default 'en',
  explain_level text not null default 'student' check (explain_level in ('eli5','student','expert')),
  plan          text not null default 'free',
  is_admin      boolean not null default false,
  created_at    timestamptz not null default now()
);

create table collections (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles(id) on delete cascade,
  name        text not null check (char_length(name) between 1 and 120),
  description text,
  created_at  timestamptz not null default now()
);

create table papers (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid references profiles(id) on delete cascade,      -- null for public_cache
  visibility    paper_visibility not null,
  source        paper_source not null,
  source_ref    text,                                                -- arXiv id, DOI, URL, or filename
  sha256        text not null,
  title         text,
  authors       jsonb not null default '[]',                          -- [{name, affiliation?}]
  year          int,
  venue         text,
  abstract      text,
  doi           text,
  arxiv_id      text,
  s2_paper_id   text,
  blob_path     text,                                                -- null for arXiv (fetched on view)
  page_count    int,
  parser        text,                                                -- which parser produced the index
  status        paper_status not null default 'queued',
  error         text,
  created_at    timestamptz not null default now(),
  check ((visibility = 'private' and owner_id is not null) or
         (visibility = 'public_cache' and owner_id is null))
);
create unique index papers_public_arxiv_uq on papers(arxiv_id) where visibility = 'public_cache' and arxiv_id is not null;
create unique index papers_public_doi_uq   on papers(lower(doi)) where visibility = 'public_cache' and doi is not null;
create unique index papers_private_hash_uq on papers(owner_id, sha256) where visibility = 'private';
create index papers_title_trgm on papers using gin (title gin_trgm_ops);

create table user_papers (
  user_id       uuid not null references profiles(id) on delete cascade,
  paper_id      uuid not null references papers(id) on delete cascade,
  collection_id uuid references collections(id) on delete set null,
  tags          text[] not null default '{}',
  starred       boolean not null default false,
  read_progress real not null default 0 check (read_progress between 0 and 1),
  added_at      timestamptz not null default now(),
  primary key (user_id, paper_id)
);

create table sections (
  id         uuid primary key default gen_random_uuid(),
  paper_id   uuid not null references papers(id) on delete cascade,
  idx        int not null,
  heading    text not null,
  level      smallint not null default 1,
  page_start int,
  page_end   int
);
create index on sections(paper_id, idx);

create table chunks (
  id             uuid primary key default gen_random_uuid(),
  paper_id       uuid not null references papers(id) on delete cascade,
  section_id     uuid references sections(id) on delete set null,
  idx            int not null,
  kind           chunk_kind not null default 'body',
  text           text not null,
  context_header text not null,                 -- "Title | Section 3.2 Multi-Head Attention"
  page_start     int not null,
  page_end       int not null,
  sentences      jsonb not null,                -- [{s, e, page, rects:[[x0,y0,x1,y1],...]}] char offsets into text
  token_count    int not null,
  embedding      halfvec(384),                  -- dim must equal EMBEDDINGS_DIM
  fts            tsvector generated always as (
                   setweight(to_tsvector('english', context_header), 'A') ||
                   setweight(to_tsvector('english', text), 'B')) stored
);
create index chunks_paper_idx on chunks(paper_id, idx);
create index chunks_fts_idx   on chunks using gin (fts);
create index chunks_vec_idx   on chunks using hnsw (embedding halfvec_cosine_ops) with (m = 16, ef_construction = 64);

create table references_parsed (
  id                uuid primary key default gen_random_uuid(),
  paper_id          uuid not null references papers(id) on delete cascade,
  idx               int not null,
  raw               text not null,
  title             text,
  year              int,
  doi               text,
  arxiv_id          text,
  s2_paper_id       text,
  resolved_paper_id uuid references papers(id) on delete set null
);

create table summaries (
  id         uuid primary key default gen_random_uuid(),
  paper_id   uuid not null references papers(id) on delete cascade,
  kind       text not null check (kind in ('structured','tldr','glossary','reading_path')),
  lang       text not null default 'en',
  level      text not null default 'student',
  content    jsonb not null,                    -- validated against JSON schema in prompts doc
  model      text not null,
  prompt_ver text not null,
  created_at timestamptz not null default now(),
  unique (paper_id, kind, lang, level)
);

create table threads (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  title      text,
  scope      jsonb not null,                    -- {"paper_ids":[...]} or {"collection_id":"..."}
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table messages (
  id                uuid primary key default gen_random_uuid(),
  thread_id         uuid not null references threads(id) on delete cascade,
  role              text not null check (role in ('user','assistant')),
  content           text not null,
  citations         jsonb not null default '[]', -- [{n, chunk_id, paper_id, page, sentence_idx[], quote}]
  grounded          boolean,
  support_score     real,
  provider          text,
  model             text,
  prompt_tokens     int,
  completion_tokens int,
  latency_ms        int,
  created_at        timestamptz not null default now()
);
create index on messages(thread_id, created_at);

create table feedback (
  message_id uuid references messages(id) on delete cascade,
  user_id    uuid references profiles(id) on delete cascade,
  rating     smallint not null check (rating in (-1, 1)),
  reason     text,
  created_at timestamptz not null default now(),
  primary key (message_id, user_id)
);

create table notes (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  paper_id   uuid not null references papers(id) on delete cascade,
  anchor     jsonb,                             -- {page, rects:[[...]], text}
  body_md    text not null default '',
  color      text not null default 'yellow',
  origin     text not null default 'manual' check (origin in ('manual','ai')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table comparisons (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  title      text,
  paper_ids  uuid[] not null check (cardinality(paper_ids) between 2 and 10),
  columns    jsonb not null,                    -- [{key, label, question}]
  cells      jsonb not null default '{}',       -- {paper_id: {key: {value, citations:[...], status}}}
  status     text not null default 'queued',
  share_id   text unique,
  created_at timestamptz not null default now()
);

create table flashcards (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references profiles(id) on delete cascade,
  paper_id    uuid not null references papers(id) on delete cascade,
  front       text not null,
  back        text not null,
  citation    jsonb,
  ease        real not null default 2.5,
  interval_d  int not null default 0,
  due_at      timestamptz not null default now()
);

-- Operational tables
create table jobs (
  id         uuid primary key default gen_random_uuid(),
  type       text not null,                     -- ingest_paper | build_summary | compare | ...
  payload    jsonb not null,
  user_id    uuid references profiles(id) on delete cascade,
  status     job_status not null default 'queued',
  priority   smallint not null default 5,       -- lower = sooner
  progress   smallint not null default 0,
  stage      text,
  attempts   smallint not null default 0,
  error      text,
  run_after  timestamptz not null default now(),
  locked_at  timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_ready_idx on jobs(priority, run_after) where status = 'queued';

create table llm_cache (
  key        text primary key,                  -- sha256(task|model|prompt_ver|normalized inputs)
  value      jsonb not null,
  hits       int not null default 0,
  created_at timestamptz not null default now()
);

create table usage_daily (
  user_id   uuid not null references profiles(id) on delete cascade,
  day       date not null,
  questions int not null default 0,
  imports   int not null default 0,
  compares  int not null default 0,
  tokens    int not null default 0,
  primary key (user_id, day)
);

create table provider_events (
  id         bigint generated always as identity primary key,
  provider   text not null,
  model      text,
  task       text not null,
  ok         boolean not null,
  status     int,
  latency_ms int,
  created_at timestamptz not null default now()
);
```

## 3. Row-level security (defense in depth)

The API connects with a server role and enforces ownership in `services/`; RLS still protects data if any client ever talks to Supabase directly.

```sql
alter table papers enable row level security;
create policy papers_read on papers for select using (
  visibility = 'public_cache'
  or owner_id = auth.uid()
);
create policy papers_write on papers for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

alter table chunks enable row level security;
create policy chunks_read on chunks for select using (
  exists (select 1 from user_papers up where up.paper_id = chunks.paper_id and up.user_id = auth.uid())
);

-- Same "owner = auth.uid()" pattern for: collections, user_papers, threads, messages (via thread),
-- notes, comparisons, flashcards, feedback, usage_daily. jobs/llm_cache/provider_events: no client access.
```

## 4. Hybrid search query (one round trip)

```sql
-- :q_vec  halfvec(384), :q_text text, :paper_ids uuid[], :k int (e.g. 40)
with vec as (
  select id, row_number() over (order by embedding <=> :q_vec) as r
  from chunks
  where paper_id = any(:paper_ids) and kind <> 'reference'
  order by embedding <=> :q_vec
  limit :k
),
fts as (
  select id, row_number() over (order by ts_rank_cd(fts, query) desc) as r
  from chunks, websearch_to_tsquery('english', :q_text) query
  where paper_id = any(:paper_ids) and kind <> 'reference' and fts @@ query
  order by ts_rank_cd(fts, query) desc
  limit :k
)
select c.*, coalesce(1.0/(60+vec.r),0) + coalesce(1.0/(60+fts.r),0) as rrf
from chunks c
left join vec on vec.id = c.id
left join fts on fts.id = c.id
where vec.id is not null or fts.id is not null
order by rrf desc
limit :k;
```
Set `hnsw.ef_search = 80` for the session; with a `paper_id` filter on small sets, pgvector ≥ 0.8 iterative index scans keep recall high (`set hnsw.iterative_scan = relaxed_order`). For very small scopes (≤ 3 papers), an exact scan is fast enough and is preferred.

## 5. Storage estimate

| Item | Per chunk | Per paper (~60 chunks) |
|---|---|---|
| `halfvec(384)` | 768 B | 46 KB |
| Text + header + sentences JSON | ~2.2 KB | 132 KB |
| FTS + indexes (HNSW, GIN) | ~1.2 KB | 72 KB |
| **Total** | **~4.2 KB** | **~250 KB** |

500 MB free plan ≈ **1,500–2,000 papers** across all users (shared cache makes popular papers free after the first import). Upgrade trigger: DB > 400 MB → Supabase Pro.
