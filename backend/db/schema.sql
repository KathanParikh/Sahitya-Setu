-- Sahitya Setu schema for Supabase Postgres. Safe to run more than once.
-- Run it in the Supabase SQL Editor.

create extension if not exists vector with schema extensions;

create table if not exists documents (
    doc_id           text primary key,
    -- Nullable until login is added; every new book gets an owner after that.
    user_id          uuid references auth.users (id) on delete cascade,
    filename         text not null,
    title            text,
    author           text,
    page_count       integer not null default 0,
    chunk_count      integer not null default 0,
    chapter_count    integer not null default 0,
    status           text not null default 'pending',
    progress         text,
    error            text,
    file_path        text,
    extraction_stats jsonb not null default '{}',
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create table if not exists chapters (
    id            bigint generated always as identity primary key,
    doc_id        text not null references documents (doc_id) on delete cascade,
    chapter_index integer not null,
    title         text not null,
    start_page    integer not null,
    end_page      integer not null,
    unique (doc_id, chapter_index)
);

create table if not exists summaries (
    id            bigint generated always as identity primary key,
    doc_id        text not null references documents (doc_id) on delete cascade,
    kind          text not null,  -- 'full' | 'chapter'
    chapter_index integer not null default -1,
    content       text not null,
    created_at    timestamptz not null default now(),
    unique (doc_id, kind, chapter_index)
);

create table if not exists evaluations (
    id           bigint generated always as identity primary key,
    doc_id       text not null references documents (doc_id) on delete cascade,
    metrics      jsonb not null,
    sample_count integer not null default 0,
    created_at   timestamptz not null default now()
);

-- BM25 tokens are not stored: they are recomputed from text.
create table if not exists chunks (
    doc_id        text not null references documents (doc_id) on delete cascade,
    chunk_id      text not null,
    chunk_index   integer not null,
    text          text not null,
    page_start    integer not null,
    page_end      integer not null,
    chapter_index integer not null default -1,
    chapter_title text not null default '',
    token_count   integer not null default 0,
    embedding     extensions.vector(768) not null,
    primary key (doc_id, chunk_id),
    unique (doc_id, chunk_index)
);

-- The text of each page as indexed, for citation checks.
create table if not exists pages (
    doc_id      text not null references documents (doc_id) on delete cascade,
    page_number integer not null,
    text        text not null default '',
    source      text not null default 'digital',  -- 'digital' | 'ocr' | 'empty'
    primary key (doc_id, page_number)
);

create index if not exists idx_documents_user on documents (user_id);
create index if not exists idx_summaries_doc on summaries (doc_id);
create index if not exists idx_evaluations_doc on evaluations (doc_id);

-- Vector search is exact, within one book, using the chunks primary key to
-- find that book's rows. An HNSW index over all books would filter by book
-- after the search and could return fewer than top_k results.

-- Supabase publishes tables through a public REST API. With RLS on and no
-- policies, that API returns nothing. The backend connects as the database
-- owner, which bypasses RLS, and does its own per-user checks.
alter table documents   enable row level security;
alter table chapters    enable row level security;
alter table summaries   enable row level security;
alter table evaluations enable row level security;
alter table chunks      enable row level security;
alter table pages       enable row level security;
