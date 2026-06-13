-- ═══════════════════════════════════════════════════════════════
-- World Cup 2026 Prediction Engine — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ═══════════════════════════════════════════════════════════════

-- 1. TEAMS ──────────────────────────────────────────────────────
create table if not exists teams (
  id              bigint generated always as identity primary key,
  name            text unique not null,
  elo             numeric default 1500,
  confederation   text default 'UEFA',
  fifa_ranking    int,
  flag_emoji      text,
  group_letter    text,
  updated_at      timestamptz default now()
);

-- 2. MATCHES ────────────────────────────────────────────────────
create table if not exists matches (
  id              bigint generated always as identity primary key,
  fixture_id      int unique not null,      -- API-Football fixture ID
  team1           text not null,
  team2           text not null,
  goals1          int,
  goals2          int,
  stage           text not null,            -- group, r16, qf, sf, final
  xg1             numeric,
  xg2             numeric,
  possession1     numeric,
  possession2     numeric,
  shots1          int,
  shots2          int,
  date            date,
  status          text default 'NS',        -- NS, 1H, HT, 2H, FT, AET, PEN
  created_at      timestamptz default now()
);

-- 3. PLAYER STATS ───────────────────────────────────────────────
create table if not exists player_stats (
  id              bigint generated always as identity primary key,
  fixture_id      int not null,
  team            text not null,
  player_name     text not null,
  rating          numeric,
  minutes         int,
  goals           int default 0,
  assists         int default 0,
  shots           int default 0,
  passes_key      int default 0,
  dribbles        int default 0,
  tackles         int default 0,
  created_at      timestamptz default now(),
  unique(fixture_id, player_name)
);

-- 4. PREDICTIONS ────────────────────────────────────────────────
create table if not exists predictions (
  id                  bigint generated always as identity primary key,
  fixture_id          int unique not null,
  team1               text not null,
  team2               text not null,
  win_prob            numeric,              -- P(team1 wins)
  draw_prob           numeric,
  loss_prob           numeric,              -- P(team2 wins)
  predicted_score1    int,
  predicted_score2    int,
  confidence          int,                  -- 0–100
  reasoning           text,                 -- Claude's analytical text
  model_breakdown     jsonb,                -- per-model outputs
  xg1                 numeric,
  xg2                 numeric,
  actual_score1       int,                  -- filled after match
  actual_score2       int,
  was_correct         boolean,              -- did we get the winner right?
  created_at          timestamptz default now(),
  updated_at          timestamptz default now()
);

-- 5. TEAM FORM ──────────────────────────────────────────────────
create table if not exists team_form (
  id              bigint generated always as identity primary key,
  team_name       text not null,
  match_date      date not null,
  result          text not null,            -- W, D, L
  xg_for          numeric default 0,
  xg_against      numeric default 0,
  goals_for       int default 0,
  goals_against   int default 0,
  opponent        text,
  stage           text,
  created_at      timestamptz default now(),
  unique(team_name, match_date)
);

-- ── INDEXES ────────────────────────────────────────────────────
create index if not exists idx_matches_stage        on matches(stage);
create index if not exists idx_matches_status       on matches(status);
create index if not exists idx_matches_date         on matches(date);
create index if not exists idx_predictions_fixture  on predictions(fixture_id);
create index if not exists idx_player_stats_fixture on player_stats(fixture_id);
create index if not exists idx_team_form_team       on team_form(team_name);
create index if not exists idx_team_form_date       on team_form(match_date desc);

-- ── UPDATED_AT TRIGGER ─────────────────────────────────────────
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger predictions_updated_at
  before update on predictions
  for each row execute function update_updated_at();

create trigger teams_updated_at
  before update on teams
  for each row execute function update_updated_at();

-- ── SEED TEAMS ─────────────────────────────────────────────────
insert into teams (name, elo, confederation, flag_emoji) values
  ('Argentina',    2090, 'CONMEBOL', '🇦🇷'),
  ('France',       2005, 'UEFA',     '🇫🇷'),
  ('Brazil',       1985, 'CONMEBOL', '🇧🇷'),
  ('England',      1930, 'UEFA',     '🏴󠁧󠁢󠁥󠁮󠁧󠁿'),
  ('Spain',        1920, 'UEFA',     '🇪🇸'),
  ('Portugal',     1900, 'UEFA',     '🇵🇹'),
  ('Netherlands',  1885, 'UEFA',     '🇳🇱'),
  ('Germany',      1870, 'UEFA',     '🇩🇪'),
  ('Belgium',      1840, 'UEFA',     '🇧🇪'),
  ('Croatia',      1810, 'UEFA',     '🇭🇷'),
  ('Morocco',      1780, 'CAF',      '🇲🇦'),
  ('USA',          1755, 'CONCACAF', '🇺🇸'),
  ('Mexico',       1740, 'CONCACAF', '🇲🇽'),
  ('Uruguay',      1720, 'CONMEBOL', '🇺🇾'),
  ('Japan',        1720, 'AFC',      '🇯🇵'),
  ('Colombia',     1710, 'CONMEBOL', '🇨🇴'),
  ('Senegal',      1730, 'CAF',      '🇸🇳'),
  ('Italy',        1830, 'UEFA',     '🇮🇹'),
  ('Switzerland',  1760, 'UEFA',     '🇨🇭'),
  ('Denmark',      1750, 'UEFA',     '🇩🇰'),
  ('South Korea',  1700, 'AFC',      '🇰🇷'),
  ('Ecuador',      1680, 'CONMEBOL', '🇪🇨'),
  ('Australia',    1640, 'OFC',      '🇦🇺'),
  ('Iran',         1630, 'AFC',      '🇮🇷'),
  ('Nigeria',      1600, 'CAF',      '🇳🇬'),
  ('Egypt',        1610, 'CAF',      '🇪🇬'),
  ('Saudi Arabia', 1590, 'AFC',      '🇸🇦'),
  ('Ghana',        1580, 'CAF',      '🇬🇭'),
  ('Cameroon',     1570, 'CAF',      '🇨🇲'),
  ('Tunisia',      1560, 'CAF',      '🇹🇳'),
  ('Canada',       1650, 'CONCACAF', '🇨🇦'),
  ('Qatar',        1500, 'AFC',      '🇶🇦')
on conflict (name) do update
  set elo = excluded.elo,
      confederation = excluded.confederation,
      flag_emoji = excluded.flag_emoji;

-- ── ROW LEVEL SECURITY ─────────────────────────────────────────
-- Allow public read on all tables (predictions dashboard is public)
alter table teams        enable row level security;
alter table matches      enable row level security;
alter table predictions  enable row level security;
alter table player_stats enable row level security;
alter table team_form    enable row level security;

create policy "public read teams"        on teams        for select using (true);
create policy "public read matches"      on matches      for select using (true);
create policy "public read predictions"  on predictions  for select using (true);
create policy "public read player_stats" on player_stats for select using (true);
create policy "public read team_form"    on team_form    for select using (true);

-- Service role (backend) gets full access via the service_role key
-- No additional policy needed — service_role bypasses RLS by default
