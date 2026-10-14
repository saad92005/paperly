-- Literature review drafts (Phase 10).
create table reviews (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references profiles(id) on delete cascade,
  collection_id uuid references collections(id) on delete set null,
  job_id        uuid unique,
  topic         text,
  style         text not null default 'apa' check (style in ('apa','ieee')),
  content_md    text not null default '',
  bibtex        text not null default '',
  created_at    timestamptz not null default now()
);
create index reviews_user_idx on reviews(user_id, created_at desc);
alter table reviews enable row level security;
create policy reviews_owner on reviews for all
  using (user_id = (select app_uid())) with check (user_id = (select app_uid()));
