-- TEST ONLY: run in a fresh in-memory database or the dedicated CI database.
-- cron.* below is a boundary fixture, NOT pg_cron and NOT a running scheduler.
do $$ begin
  if to_regclass('public.relay_devices') is not null
     or to_regclass('public.relay_deliveries') is not null
     or to_regnamespace('cron') is not null then
    raise exception 'Retention fixture requires an empty disposable database';
  end if;
end $$;
create role anon nologin;
create role authenticated nologin;
create role service_role nologin;
create table public.relay_pairings (pairing_id text primary key, expires_at bigint not null);
create table public.relay_pairs (pair_id text primary key, sender_token_hash text not null);
create table public.relay_rate_limits (key text primary key, expires_at bigint not null);
create table public.relay_deliveries (
  delivery_id text primary key, pair_id text not null, message_id text not null,
  status text not null, envelope jsonb not null, ack_envelope jsonb,
  expires_at bigint not null, unique(pair_id,message_id)
);
create schema cron;
create table cron.job (
  jobid bigserial primary key, jobname text,
  schedule text not null, command text not null,
  database text not null default current_database(),
  username text not null default current_user, active boolean not null default true,
  unique(jobname, username)
);
create table cron.job_run_details (
  runid bigserial primary key, jobid bigint not null,
  status text, start_time timestamptz, end_time timestamptz, return_message text
);
create function cron.schedule(text,text,text) returns bigint language plpgsql as $$
declare result bigint;
begin
  insert into cron.job(jobname,schedule,command) values($1,$2,$3)
  on conflict(jobname,username) do update
    set schedule=excluded.schedule,command=excluded.command,active=true
  returning jobid into result;
  return result;
end $$;
create function cron.unschedule(bigint) returns boolean language plpgsql as $$
begin
  delete from cron.job where jobid=$1 and username=current_user;
  return found;
end $$;
