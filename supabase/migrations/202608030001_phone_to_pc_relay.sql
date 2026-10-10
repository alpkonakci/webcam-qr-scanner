-- Webcam QR Scanner Phone-to-PC relay for Supabase.
--
-- The relay stores only opaque WQRS/1 envelopes and token hashes. QR images,
-- plaintext URLs, account profiles, and location data are never stored here.

create extension if not exists pgcrypto;

create table public.relay_devices (
  device_id text primary key check (device_id ~ '^[A-Za-z0-9_-]{22}$'),
  receiver_token_hash text not null unique
    check (receiver_token_hash ~ '^[0-9a-f]{64}$'),
  realtime_user_id uuid not null references auth.users(id) on delete cascade,
  created_at bigint not null,
  last_seen_at bigint
);

create index relay_devices_realtime_user_idx
  on public.relay_devices (realtime_user_id);

create table public.relay_pairings (
  pairing_id text primary key check (pairing_id ~ '^[A-Za-z0-9_-]{22}$'),
  device_id text not null references public.relay_devices(device_id) on delete cascade,
  pairing_token_hash text not null unique
    check (pairing_token_hash ~ '^[0-9a-f]{64}$'),
  created_at bigint not null,
  expires_at bigint not null,
  request_envelope jsonb,
  result_envelope jsonb,
  status text not null check (
    status in ('open', 'opened', 'requested', 'complete', 'cancelled_by_phone')
  )
);

create index relay_pairings_device_idx
  on public.relay_pairings (device_id);
create index relay_pairings_expiry_idx
  on public.relay_pairings (expires_at);

create table public.relay_pairs (
  pair_id text primary key check (pair_id ~ '^[A-Za-z0-9_-]{22}$'),
  device_id text not null references public.relay_devices(device_id) on delete cascade,
  sender_token_hash text not null unique
    check (sender_token_hash ~ '^[0-9a-f]{64}$'),
  created_at bigint not null,
  revoked_at bigint
);

create index relay_pairs_device_idx on public.relay_pairs (device_id);

create table public.relay_deliveries (
  delivery_id text primary key check (delivery_id ~ '^[A-Za-z0-9_-]{22}$'),
  pair_id text not null references public.relay_pairs(pair_id) on delete cascade,
  device_id text not null references public.relay_devices(device_id) on delete cascade,
  message_id text not null check (message_id ~ '^[A-Za-z0-9_-]{22}$'),
  envelope jsonb not null,
  created_at bigint not null,
  expires_at bigint not null,
  lease_until bigint,
  status text not null check (
    status in ('pending', 'delivering', 'delivered', 'rejected')
  ),
  ack_envelope jsonb,
  unique (pair_id, message_id)
);

create index relay_deliveries_device_status_idx
  on public.relay_deliveries (device_id, status, created_at);
create index relay_deliveries_expiry_idx
  on public.relay_deliveries (expires_at);

create table public.relay_rate_limits (
  key text primary key,
  window_started_at bigint not null,
  request_count integer not null check (request_count > 0),
  expires_at bigint not null
);

-- No browser or desktop client reads relay tables through the Data API.
-- All mutations go through the Vercel API with a server-only Supabase key.
alter table public.relay_devices enable row level security;
alter table public.relay_pairings enable row level security;
alter table public.relay_pairs enable row level security;
alter table public.relay_deliveries enable row level security;
alter table public.relay_rate_limits enable row level security;

revoke all on public.relay_devices from anon, authenticated, service_role;
revoke all on public.relay_pairings from anon, authenticated, service_role;
revoke all on public.relay_pairs from anon, authenticated, service_role;
revoke all on public.relay_deliveries from anon, authenticated, service_role;
revoke all on public.relay_rate_limits from anon, authenticated, service_role;

-- New tables are intentionally not exposed automatically. Grant only the
-- trusted Vercel backend the CRUD operations used by the relay API. Browser
-- sessions receive no direct table privileges; they can only subscribe to the
-- narrowly scoped private Realtime policy below.
grant select, insert, update, delete on public.relay_devices to service_role;
grant select, insert, update, delete on public.relay_pairings to service_role;
grant select, insert, update, delete on public.relay_pairs to service_role;
grant select, insert, update, delete on public.relay_deliveries to service_role;

-- A short-lived anonymous Supabase Auth session is bound to exactly one PC
-- device. It authorizes only that device's private Realtime topic.
create or replace function public.relay_can_receive_topic(p_topic text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.relay_devices
    where realtime_user_id = auth.uid()
      and p_topic = 'device:' || device_id
  );
$$;

revoke all on function public.relay_can_receive_topic(text) from public;
grant execute on function public.relay_can_receive_topic(text) to authenticated;

create policy "paired PC may receive its device topic"
on realtime.messages
for select
to authenticated
using (public.relay_can_receive_topic(realtime.topic()));

-- The database emits only a wake-up identifier. The encrypted envelope is
-- claimed through the authenticated Vercel API, which also provides the
-- five-second recovery poll if a WebSocket event is missed.
create or replace function public.relay_broadcast_delivery_ready()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  perform realtime.send(
    jsonb_build_object('delivery_id', new.delivery_id),
    'delivery_ready',
    'device:' || new.device_id,
    true
  );
  return new;
end;
$$;

create trigger relay_delivery_ready_trigger
after insert on public.relay_deliveries
for each row execute function public.relay_broadcast_delivery_ready();

revoke all on function public.relay_broadcast_delivery_ready() from public;

-- Atomically lease one pending delivery so reconnects or fallback polls cannot
-- show the same URL confirmation twice at the same time.
create or replace function public.relay_claim_delivery(
  p_device_id text,
  p_now bigint,
  p_lease_until bigint
)
returns table (
  delivery_id text,
  pair_id text,
  device_id text,
  message_id text,
  envelope jsonb,
  expires_at bigint,
  status text,
  ack_envelope jsonb
)
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidate as (
    select d.delivery_id
    from public.relay_deliveries d
    where d.device_id = p_device_id
      and d.expires_at >= p_now
      and (
        d.status = 'pending'
        or (d.status = 'delivering' and d.lease_until <= p_now)
      )
    order by d.created_at
    for update skip locked
    limit 1
  )
  update public.relay_deliveries d
  set status = 'delivering', lease_until = p_lease_until
  from candidate c
  where d.delivery_id = c.delivery_id
  returning
    d.delivery_id,
    d.pair_id,
    d.device_id,
    d.message_id,
    d.envelope,
    d.expires_at,
    d.status,
    d.ack_envelope;
end;
$$;

revoke all on function public.relay_claim_delivery(text, bigint, bigint) from public;
grant execute on function public.relay_claim_delivery(text, bigint, bigint) to service_role;

-- Rate-limit counters are updated in one statement so parallel requests cannot
-- bypass the limit.
create or replace function public.relay_consume_rate_limit(
  p_key text,
  p_limit integer,
  p_window_seconds integer,
  p_now bigint
)
returns table (allowed boolean, retry_after integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_count integer;
  current_started bigint;
begin
  insert into public.relay_rate_limits (
    key,
    window_started_at,
    request_count,
    expires_at
  ) values (
    p_key,
    p_now,
    1,
    p_now + p_window_seconds
  )
  on conflict (key) do update set
    window_started_at = case
      when public.relay_rate_limits.window_started_at + p_window_seconds <= p_now
        then p_now
      else public.relay_rate_limits.window_started_at
    end,
    request_count = case
      when public.relay_rate_limits.window_started_at + p_window_seconds <= p_now
        then 1
      else public.relay_rate_limits.request_count + 1
    end,
    expires_at = case
      when public.relay_rate_limits.window_started_at + p_window_seconds <= p_now
        then p_now + p_window_seconds
      else public.relay_rate_limits.expires_at
    end
  returning request_count, window_started_at
    into current_count, current_started;

  allowed := current_count <= p_limit;
  retry_after := greatest(
    1,
    (current_started + p_window_seconds - p_now)::integer
  );
  return next;
end;
$$;

revoke all on function public.relay_consume_rate_limit(text, integer, integer, bigint) from public;
grant execute on function public.relay_consume_rate_limit(text, integer, integer, bigint) to service_role;

create or replace function public.relay_cleanup(p_now bigint)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.relay_pairings where expires_at < p_now;
  delete from public.relay_deliveries where expires_at < p_now;
  delete from public.relay_rate_limits where expires_at < p_now;
end;
$$;

revoke all on function public.relay_cleanup(bigint) from public;
grant execute on function public.relay_cleanup(bigint) to service_role;
