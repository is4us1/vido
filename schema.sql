-- vido — CRM + usage schema
-- הרץ את זה ב-Supabase: Project → SQL Editor → New query → הדבק → Run

create extension if not exists "pgcrypto";

-- לידים / לקוחות (CRM)
create table if not exists leads (
  id          uuid primary key default gen_random_uuid(),
  name        text,
  email       text,
  phone       text,
  source      text default 'website',
  status      text default 'new',          -- new / contacted / trial / customer / lost
  notes       text default '',
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

-- אירועי שימוש (אנליטיקס)
create table if not exists events (
  id          bigint generated always as identity primary key,
  type        text not null,               -- edit / create_audio / create_slides ...
  detail      text default '',
  session     text default '',
  created_at  timestamptz default now()
);

create index if not exists idx_events_created on events(created_at);
create index if not exists idx_leads_status  on leads(status);

-- אבטחה: סוגרים גישה ציבורית. רק ה-service key (בצד השרת) עוקף RLS.
alter table leads  enable row level security;
alter table events enable row level security;
