-- Phases 1-10 content tables (docs/03-DATA-MODEL.md) + blobs (ADR-008).

create table blobs (
  path         text primary key,
  content_type text not null,
  size_bytes   int not null,
  data         bytea not null,
  created_at   timestamptz not null default now()
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
create index sections_paper_idx on sections(paper_id, idx);

create table chunks (
  id             uuid primary key default gen_random_uuid(),
  paper_id       uuid not null references papers(id) on delete cascade,
  section_id     uuid references sections(id) on delete set null,
  idx            int not null,
  kind           chunk_kind not null default 'body',
  text           text not null,
  context_header text not null,
  page_start     int not null,
  page_end       int not null,
  sentences      jsonb not null,
  token_count    int not null,
  embedding      halfvec(384),
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
create index references_paper_idx on references_parsed(paper_id, idx);

create table summaries (
  id         uuid primary key default gen_random_uuid(),
  paper_id   uuid not null references papers(id) on delete cascade,
  kind       text not null check (kind in ('structured','tldr','glossary','reading_path')),
  lang       text not null default 'en',
  level      text not null default 'student',
  content    jsonb not null,
  model      text not null,
  prompt_ver text not null,
  created_at timestamptz not null default now(),
  unique (paper_id, kind, lang, level)
);

create table threads (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  title      text,
  scope      jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index threads_user_idx on threads(user_id, updated_at desc);

create table messages (
  id                uuid primary key default gen_random_uuid(),
  thread_id         uuid not null references threads(id) on delete cascade,
  role              text not null check (role in ('user','assistant')),
  content           text not null,
  citations         jsonb not null default '[]',
  grounded          boolean,
  support_score     real,
  provider          text,
  model             text,
  prompt_tokens     int,
  completion_tokens int,
  latency_ms        int,
  created_at        timestamptz not null default now()
);
create index messages_thread_idx on messages(thread_id, created_at);

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
  anchor     jsonb,
  body_md    text not null default '',
  color      text not null default 'yellow',
  origin     text not null default 'manual' check (origin in ('manual','ai')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index notes_user_paper_idx on notes(user_id, paper_id);

create table comparisons (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references profiles(id) on delete cascade,
  title      text,
  paper_ids  uuid[] not null check (cardinality(paper_ids) between 2 and 10),
  columns    jsonb not null,
  cells      jsonb not null default '{}',
  status     text not null default 'queued',
  share_id   text unique,
  created_at timestamptz not null default now()
);
create index comparisons_user_idx on comparisons(user_id, created_at desc);

create table flashcards (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references profiles(id) on delete cascade,
  paper_id    uuid not null references papers(id) on delete cascade,
  front       text not null,
  back        text not null,
  citation    jsonb,
  ease        real not null default 2.5,
  interval_d  int not null default 0,
  reps        int not null default 0,
  due_at      timestamptz not null default now()
);
create index flashcards_due_idx on flashcards(user_id, due_at);

create table shares (
  id         text primary key,
  user_id    uuid not null references profiles(id) on delete cascade,
  kind       text not null check (kind in ('summary','comparison','review')),
  ref_id     uuid not null,
  created_at timestamptz not null default now()
);

create table llm_cache (
  key        text primary key,
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
create index provider_events_time_idx on provider_events(created_at);

-- RLS (defense in depth; see ADR-007 note on the owner role).
alter table blobs             enable row level security;  -- no client access
alter table sections          enable row level security;
alter table chunks            enable row level security;
alter table references_parsed enable row level security;
alter table summaries         enable row level security;
alter table threads           enable row level security;
alter table messages          enable row level security;
alter table feedback          enable row level security;
alter table notes             enable row level security;
alter table comparisons       enable row level security;
alter table flashcards        enable row level security;
alter table shares            enable row level security;
alter table llm_cache         enable row level security;  -- no client access
alter table usage_daily       enable row level security;
alter table provider_events   enable row level security;  -- no client access

create policy sections_read on sections for select using (
  exists (select 1 from user_papers up where up.paper_id = sections.paper_id and up.user_id = (select app_uid())));
create policy chunks_read on chunks for select using (
  exists (select 1 from user_papers up where up.paper_id = chunks.paper_id and up.user_id = (select app_uid())));
create policy references_read on references_parsed for select using (
  exists (select 1 from user_papers up where up.paper_id = references_parsed.paper_id and up.user_id = (select app_uid())));
create policy summaries_read on summaries for select using (
  exists (select 1 from user_papers up where up.paper_id = summaries.paper_id and up.user_id = (select app_uid())));
create policy threads_owner on threads for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy messages_owner on messages for all using (
  exists (select 1 from threads t where t.id = messages.thread_id and t.user_id = (select app_uid())));
create policy feedback_owner on feedback for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy notes_owner on notes for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy comparisons_owner on comparisons for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy flashcards_owner on flashcards for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy shares_owner on shares for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
create policy usage_owner on usage_daily for select using (user_id = (select app_uid()));
