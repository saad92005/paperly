-- Phase 0 foundation: profiles, collections, papers, user_papers, jobs (docs/03-DATA-MODEL.md).

create extension if not exists vector with schema extensions;
create extension if not exists pg_trgm with schema extensions;

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
create index collections_owner_idx on collections(owner_id);

create table papers (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid references profiles(id) on delete cascade,
  visibility    paper_visibility not null,
  source        paper_source not null,
  source_ref    text,
  sha256        text not null,
  title         text,
  authors       jsonb not null default '[]',
  year          int,
  venue         text,
  abstract      text,
  doi           text,
  arxiv_id      text,
  s2_paper_id   text,
  blob_path     text,
  page_count    int,
  parser        text,
  status        paper_status not null default 'queued',
  error         text,
  created_at    timestamptz not null default now(),
  check ((visibility = 'private' and owner_id is not null) or
         (visibility = 'public_cache' and owner_id is null))
);
create unique index papers_public_arxiv_uq on papers(arxiv_id) where visibility = 'public_cache' and arxiv_id is not null;
create unique index papers_public_doi_uq   on papers(lower(doi)) where visibility = 'public_cache' and doi is not null;
create unique index papers_private_hash_uq on papers(owner_id, sha256) where visibility = 'private';
create index papers_title_trgm on papers using gin (title extensions.gin_trgm_ops);

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
create index user_papers_paper_idx on user_papers(paper_id);
create index user_papers_collection_idx on user_papers(collection_id);

create table jobs (
  id         uuid primary key default gen_random_uuid(),
  type       text not null,
  payload    jsonb not null,
  user_id    uuid references profiles(id) on delete cascade,
  status     job_status not null default 'queued',
  priority   smallint not null default 5,
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

-- Create a profile for every new auth user.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'))
  on conflict (id) do nothing;
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Row-level security (defense in depth; the API also enforces ownership).
alter table profiles    enable row level security;
alter table collections enable row level security;
alter table papers      enable row level security;
alter table user_papers enable row level security;
alter table jobs        enable row level security;  -- no policies: no client access

create policy profiles_self on profiles for all
  using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy collections_owner on collections for all
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy papers_read on papers for select
  using (visibility = 'public_cache' or owner_id = (select auth.uid()));
create policy papers_write on papers for all
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy user_papers_owner on user_papers for all
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
