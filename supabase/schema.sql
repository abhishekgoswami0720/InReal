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
-- the cap is counted in a definer function: a count of a table inside its own policy is infinite recursion
create or replace function private.my_bookmark_count() returns bigint
language sql stable security definer set search_path = '' as $$
  select count(*) from public.bookmarks b where b.user_id = (select auth.uid());
$$;
revoke execute on function private.my_bookmark_count() from public, anon;
grant execute on function private.my_bookmark_count() to authenticated;
create policy "own bookmarks: add" on public.bookmarks for insert to authenticated with check (
  (select auth.uid()) = user_id and private.my_bookmark_count() < 500);   -- abuse cap only
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

-- A signed-in user whose profiles row is missing (deleted by hand) gets it back on the next visit
-- (migration ensure_profile). Only for the caller's own id; nothing happens if the row exists.
create or replace function public.ensure_profile() returns void
language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is null then return; end if;
  insert into public.profiles (id, name, email, avatar_url)
  select u.id, coalesce(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name'),
         u.email, u.raw_user_meta_data->>'avatar_url'
  from auth.users u where u.id = (select auth.uid())
  on conflict (id) do nothing;
end; $$;
revoke execute on function public.ensure_profile() from public, anon;
grant execute on function public.ensure_profile() to authenticated;

-- ---------------------------------------------------------------------------
-- Security pass (26 Oct 2026): least-privilege grants and profile size limits.
-- RLS already blocks these writes; the grants are a second lock in case a policy
-- is ever added by mistake (an INSERT policy would otherwise let anyone set is_admin).
revoke all on public.listings from anon;
revoke insert, update, delete, truncate, references, trigger on public.listings from authenticated;
revoke all on public.bookmarks from anon;
revoke update, truncate, references, trigger on public.bookmarks from authenticated;
revoke all on public.profiles from anon;
revoke insert, delete, truncate, references, trigger on public.profiles from authenticated;
-- One account must not be able to fill the database through its own profile.
alter table public.profiles drop constraint if exists profiles_name_len,
  drop constraint if exists profiles_small_text, drop constraint if exists profiles_list_sizes,
  drop constraint if exists profiles_stipend_range;
alter table public.profiles
  add constraint profiles_name_len check (char_length(name) <= 120),
  add constraint profiles_small_text check (char_length(coalesce(field,'')) <= 60 and char_length(coalesce(experience,'')) <= 40
      and char_length(coalesce(study_year,'')) <= 40 and char_length(coalesce(work_mode,'')) <= 40 and char_length(coalesce(max_duration,'')) <= 40),
  add constraint profiles_list_sizes check (coalesce(cardinality(regions),0) <= 40 and coalesce(cardinality(sources),0) <= 40
      and coalesce(cardinality(companies),0) <= 60 and coalesce(cardinality(roles),0) <= 40 and coalesce(cardinality(skills),0) <= 80),
  add constraint profiles_stipend_range check (min_stipend is null or min_stipend between 0 and 10000000);
drop function if exists public.is_pro();
drop function if exists public.my_field();

-- ---------------------------------------------------------------------------
-- "My applications" (1 Nov 2026): internships a user says they applied to. The post's title,
-- company, site and link are copied, because the post itself leaves the list after a few days.
create table if not exists public.applications (
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  listing_id text not null check (char_length(listing_id) between 1 and 200),
  role_title text check (char_length(role_title) <= 300),
  company_name text check (char_length(company_name) <= 200),
  source_platform text check (char_length(source_platform) <= 100),
  apply_link text check (char_length(apply_link) <= 2000 and apply_link ~* '^https?://'),
  applied_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);
alter table public.applications enable row level security;
revoke all on public.applications from anon;
revoke all on public.applications from authenticated;
grant select, insert, delete on public.applications to authenticated;
drop policy if exists "own applications: read" on public.applications;
drop policy if exists "own applications: add" on public.applications;
drop policy if exists "own applications: remove" on public.applications;
create policy "own applications: read" on public.applications for select to authenticated
  using ((select auth.uid()) = user_id);
create or replace function private.my_application_count() returns bigint
language sql stable security definer set search_path = '' as $$
  select count(*) from public.applications a where a.user_id = (select auth.uid());
$$;
revoke execute on function private.my_application_count() from public, anon;
grant execute on function private.my_application_count() to authenticated;
create policy "own applications: add" on public.applications for insert to authenticated
  with check ((select auth.uid()) = user_id and private.my_application_count() < 2000);
create policy "own applications: remove" on public.applications for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- My profile (1 Nov 2026): a username, a chosen avatar, and an uploaded photo.
alter table public.profiles add column if not exists username text;
alter table public.profiles add column if not exists avatar_preset text;
alter table public.profiles drop constraint if exists profiles_username_format,
  drop constraint if exists profiles_avatar_preset_len, drop constraint if exists profiles_avatar_url_https;
alter table public.profiles
  add constraint profiles_username_format check (username is null or username ~ '^[a-z0-9_.]{3,20}$'),
  add constraint profiles_avatar_preset_len check (avatar_preset is null or char_length(avatar_preset) <= 40),
  add constraint profiles_avatar_url_https check (avatar_url is null or (char_length(avatar_url) <= 600 and avatar_url ~* '^https://'));
create unique index if not exists profiles_username_unique on public.profiles (lower(username)) where username is not null;
grant update (username, avatar_preset, avatar_url) on public.profiles to authenticated;

create or replace function public.username_available(name text) returns boolean
language sql stable security definer set search_path = '' as $$
  select name ~ '^[a-z0-9_.]{3,20}$'
     and not exists (select 1 from public.profiles p where lower(p.username) = lower(name) and p.id <> (select auth.uid()));
$$;
revoke execute on function public.username_available(text) from public, anon;
grant execute on function public.username_available(text) to authenticated;

-- photos: public to read (profile pictures); each user writes only in a folder named after their id, 10 files at most
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('avatars', 'avatars', true, 1048576, array['image/webp', 'image/jpeg', 'image/png'])
on conflict (id) do update set public = excluded.public, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
drop policy if exists "avatars: own folder read" on storage.objects;
drop policy if exists "avatars: own folder upload" on storage.objects;
drop policy if exists "avatars: own folder delete" on storage.objects;
create policy "avatars: own folder read" on storage.objects for select to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);
-- the cap is counted in a definer function: a count of storage.objects inside a policy on
-- storage.objects is infinite recursion (1 Nov: every upload failed)
create or replace function private.my_avatar_count() returns bigint
language sql stable security definer set search_path = '' as $$
  select count(*) from storage.objects o
  where o.bucket_id = 'avatars' and (storage.foldername(o.name))[1] = (select auth.uid())::text;
$$;
revoke execute on function private.my_avatar_count() from public, anon;
grant execute on function private.my_avatar_count() to authenticated;
create policy "avatars: own folder upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text
    and private.my_avatar_count() < 10);
create policy "avatars: own folder delete" on storage.objects for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = (select auth.uid())::text);

-- My profile banner (1 Nov 2026): an uploaded picture (in the avatars bucket) or one of the drawn ones.
alter table public.profiles add column if not exists banner_url text;
alter table public.profiles add column if not exists banner_preset text;
alter table public.profiles drop constraint if exists profiles_banner_url_https, drop constraint if exists profiles_banner_preset_len;
alter table public.profiles
  add constraint profiles_banner_url_https check (banner_url is null or (char_length(banner_url) <= 600 and banner_url ~* '^https://')),
  add constraint profiles_banner_preset_len check (banner_preset is null or char_length(banner_preset) <= 40);
grant update (banner_url, banner_preset) on public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- "Report this post" (2 Nov 2026). A signed-in user can report a post on the shared list once.
-- The report hides the post for that user straight away. The laptop reads the reports every
-- 15 minutes (supabase_sync.report_counts) and moves a verified post to "needs a look" once
-- 2 or more different users have reported it. A report never blocks a post by itself, so one
-- person can't take down a real company's internship.
create table if not exists public.reports (
  user_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  listing_id text not null references public.listings(id) on delete cascade,
  reason text not null check (reason in ('asks_money', 'fake_company', 'task_scam', 'wants_documents', 'other')),
  note text check (char_length(note) <= 500),
  created_at timestamptz not null default now(),
  primary key (user_id, listing_id)
);
create index if not exists reports_listing_idx on public.reports (listing_id);
alter table public.reports enable row level security;
revoke all on public.reports from anon;
revoke all on public.reports from authenticated;
grant select, insert, delete on public.reports to authenticated;
drop policy if exists "own reports: read" on public.reports;
drop policy if exists "own reports: add" on public.reports;
drop policy if exists "own reports: remove" on public.reports;
create policy "own reports: read" on public.reports for select to authenticated
  using ((select auth.uid()) = user_id);
-- at most 20 reports a day per user (against spam), counted in a definer function (no policy recursion)
create or replace function private.my_reports_today() returns bigint
language sql stable security definer set search_path = '' as $$
  select count(*) from public.reports r
  where r.user_id = (select auth.uid()) and r.created_at > now() - interval '1 day';
$$;
revoke execute on function private.my_reports_today() from public, anon;
grant execute on function private.my_reports_today() to authenticated;
create policy "own reports: add" on public.reports for insert to authenticated
  with check ((select auth.uid()) = user_id and private.my_reports_today() < 20);
create policy "own reports: remove" on public.reports for delete to authenticated
  using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- My applications: where each application stands (2 Nov 2026), set by the user.
alter table public.applications add column if not exists status text not null default 'applied';
alter table public.applications add column if not exists status_at timestamptz;
alter table public.applications drop constraint if exists applications_status_check;
alter table public.applications add constraint applications_status_check
  check (status in ('applied', 'interview', 'offer', 'rejected', 'no_reply'));
grant update (status, status_at) on public.applications to authenticated;
drop policy if exists "own applications: change status" on public.applications;
create policy "own applications: change status" on public.applications for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
