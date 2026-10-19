-- InReal: Supabase schema (end state after the migrations of 19 Oct 2026)

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  name text, email text, avatar_url text,
  field text, experience text,
  regions text[] not null default '{}', sources text[] not null default '{}', companies text[] not null default '{}',
  -- the 5-section profile (migration profile_sections)
  study_year text, roles text[] not null default '{}', skills text[] not null default '{}',
  work_mode text, min_stipend integer, max_duration text,
  plan text not null default 'free' check (plan in ('free','pro')),
  is_admin boolean not null default false,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
create policy "read own profile" on public.profiles for select to authenticated using ((select auth.uid()) = id);
create policy "update own profile" on public.profiles for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
revoke update on public.profiles from authenticated, anon;
grant update (name, field, experience, regions, sources, companies) on public.profiles to authenticated;
grant update (study_year, roles, skills, work_mode, min_stipend, max_duration) on public.profiles to authenticated;
alter table public.profiles add constraint profiles_skills_max check (cardinality(skills) <= 15);
alter table public.profiles add constraint profiles_min_stipend_range check (min_stipend is null or min_stipend between 0 and 1000000);

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, name, email, avatar_url)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'),
          new.email, new.raw_user_meta_data->>'avatar_url');
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();
revoke execute on function public.handle_new_user() from public, anon, authenticated;

create schema if not exists private;
grant usage on schema private to authenticated;
create or replace function private.is_pro() returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.profiles where id = (select auth.uid()) and (plan = 'pro' or is_admin)); $$;
create or replace function private.my_field() returns text language sql stable security definer set search_path = '' as $$
  select field from public.profiles where id = (select auth.uid()); $$;
revoke execute on function private.is_pro() from public, anon;
revoke execute on function private.my_field() from public, anon;
grant execute on function private.is_pro() to authenticated;
grant execute on function private.my_field() to authenticated;

create table public.listings (
  id text primary key,
  source_platform text not null, company_name text, role_title text not null,
  location text, location_type text, duration text,
  stipend text, stipend_numeric numeric, stipend_currency text,
  required_skills text, apply_link text, description text,
  fields text[] not null default '{}', org_type text, posted text, trust_flags text,
  status text not null check (status in ('approved','review','blocked')),
  scam_risk numeric, moderation_reasons text,
  verified_at timestamptz,
  first_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index listings_status_verified_idx on public.listings (status, verified_at desc);
create index listings_fields_idx on public.listings using gin (fields);
alter table public.listings enable row level security;
-- No plans for now (migration everything_free_for_now): every signed-in user sees every checked post
-- at once. Blocked posts are never readable. The page filters to the user's field.
create policy "signed-in users read checked posts" on public.listings for select to authenticated using (
  status in ('approved', 'review'));

create or replace function public.teaser_listings() returns table (
  id text, source_platform text, company_name text, role_title text, location text, stipend text, verified_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select l.id, l.source_platform, l.company_name, l.role_title, l.location, l.stipend, l.verified_at
  from public.listings l where l.status = 'approved' order by l.verified_at desc nulls last limit 6; $$;
create or replace function public.listing_stats() returns json
language sql stable security definer set search_path = '' as $$
  select json_build_object(
    'verified_total', count(*) filter (where l.status = 'approved'),
    'verified_week', count(*) filter (where l.status = 'approved' and l.verified_at > now() - interval '7 days'),
    'hidden_scams', count(*) filter (where l.status = 'blocked'),
    'updated_at', max(l.updated_at))
  from public.listings l; $$;
revoke execute on function public.teaser_listings() from public;
revoke execute on function public.listing_stats() from public;
grant execute on function public.teaser_listings() to anon, authenticated;
grant execute on function public.listing_stats() to anon, authenticated;

create table public.bookmarks (
  user_id uuid not null references auth.users(id) on delete cascade,
  listing_id text not null references public.listings(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);
alter table public.bookmarks enable row level security;
create policy "own bookmarks: read" on public.bookmarks for select to authenticated using ((select auth.uid()) = user_id);
create policy "own bookmarks: add" on public.bookmarks for insert to authenticated with check (
  (select auth.uid()) = user_id
  and (select count(*) from public.bookmarks b where b.user_id = (select auth.uid())) < 500);   -- abuse cap only
create policy "own bookmarks: remove" on public.bookmarks for delete to authenticated using ((select auth.uid()) = user_id);

-- Left over from the first migration, no longer used and executable by no one:
-- public.is_pro(), public.my_field() (the policies use the private.* copies).

-- verified_at = the first time a post was approved (shown as "Verified" on each post).
-- An upsert from the laptop can never move it or first_seen_at.
create or replace function private.listing_timestamps() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  if tg_op = 'UPDATE' then
    new.first_seen_at := old.first_seen_at;
    new.verified_at := coalesce(old.verified_at, case when new.status = 'approved' then now() end);
  else
    new.verified_at := case when new.status = 'approved' then now() end;
  end if;
  return new;
end $$;
revoke execute on function private.listing_timestamps() from public, anon, authenticated;
create trigger listings_timestamps before insert or update on public.listings
  for each row execute function private.listing_timestamps();
