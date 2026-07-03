-- ============================================================
-- ONLYCHAT AI — Schéma Supabase
-- Colle ce SQL dans Supabase → SQL Editor → Run
-- ============================================================

-- Conversations (une par fan)
create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  platform text not null default 'telegram', -- 'telegram' | 'onlyfans' | 'test'
  fan_id text not null,                       -- ID Telegram ou OF
  fan_username text,                          -- @username
  creator_name text,                          -- nom de la créatrice
  total_revenue numeric default 0,            -- revenus générés par ce fan
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique(platform, fan_id)
);

-- Messages (historique complet)
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now(),
  metadata jsonb default '{}'
);

-- Settings IA (une ligne par créatrice)
create table if not exists ai_settings (
  id uuid primary key default gen_random_uuid(),
  creator_name text not null default '',
  personality text not null default 'flirty',
  custom_prompt text default '',
  languages text[] default array['Français', 'English'],
  ppv_enabled boolean default true,
  ppv_price text default '15',
  nudge_delay text default '48',
  welcome_enabled boolean default true,
  updated_at timestamptz default now()
);

-- Insérer les settings par défaut
insert into ai_settings (id) values ('00000000-0000-0000-0000-000000000001')
on conflict (id) do nothing;

-- Analytics (revenus par jour)
create table if not exists daily_stats (
  id uuid primary key default gen_random_uuid(),
  date date not null default current_date,
  messages_sent integer default 0,
  ppv_sold integer default 0,
  revenue numeric default 0,
  new_fans integer default 0,
  unique(date)
);

-- Trigger pour mettre à jour updated_at sur conversations
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger conversations_updated_at
  before update on conversations
  for each row execute function update_updated_at();

-- Index pour les perfs
create index if not exists messages_conversation_id_idx on messages(conversation_id);
create index if not exists messages_created_at_idx on messages(created_at);
create index if not exists conversations_fan_id_idx on conversations(platform, fan_id);

-- RLS désactivé (accès via service role uniquement)
alter table conversations disable row level security;
alter table messages disable row level security;
alter table ai_settings disable row level security;
alter table daily_stats disable row level security;
