-- Isolated PostgreSQL regression. No public relay tables or pairings are used.
-- All fixture schema/function/row changes are rolled back, including grants.
-- Insert the release migration at the marker after replacing public. ONLY
-- with wqrs_retention_validation_20261004. (checked by the caller).
begin;
create schema wqrs_retention_validation_20261004;
create table wqrs_retention_validation_20261004.relay_pairings (
  pairing_id text primary key, expires_at bigint not null
);
create table wqrs_retention_validation_20261004.relay_rate_limits (
  fingerprint text primary key, expires_at bigint not null
);
create table wqrs_retention_validation_20261004.relay_deliveries (
  delivery_id text primary key, pair_id text not null, message_id text not null,
  status text not null, envelope jsonb not null, ack_envelope jsonb,
  expires_at bigint not null, unique (pair_id, message_id)
);
revoke all on schema wqrs_retention_validation_20261004 from public, anon, authenticated;
revoke all on all tables in schema wqrs_retention_validation_20261004 from public, anon, authenticated;
alter table wqrs_retention_validation_20261004.relay_pairings enable row level security;
alter table wqrs_retention_validation_20261004.relay_rate_limits enable row level security;
alter table wqrs_retention_validation_20261004.relay_deliveries enable row level security;
insert into wqrs_retention_validation_20261004.relay_pairings values ('expired-pair',1699999999);
insert into wqrs_retention_validation_20261004.relay_rate_limits values ('expired-rate',1699999999);
insert into wqrs_retention_validation_20261004.relay_deliveries values
 ('legacy','pair','message','delivered','{"expires_at":1700000300,"ciphertext":"synthetic"}','{"expires_at":1700000010}',1700000010),
 ('rejected','pair','reject','rejected','{"expires_at":1700000300,"ciphertext":"synthetic"}',null,1700000300),
 ('pending','pair','pending','pending','{"expires_at":1700000300,"ciphertext":"synthetic"}',null,1700000300),
 ('expired','pair','expired','pending','{}',null,1699999999),
 ('invalid-ack','pair','invalid','delivered','{}','{"expires_at":"bad"}',1700000300);

-- RELEASE_MIGRATION_HERE

do $$
begin
  if not exists (
    select 1 from wqrs_retention_validation_20261004.relay_deliveries
    where delivery_id='legacy' and expires_at=1700000300 and envelope='{}'::jsonb
  ) then raise exception 'legacy expiry repair/ciphertext clearing failed'; end if;
  if exists (
    select 1 from wqrs_retention_validation_20261004.relay_deliveries
    where status='rejected' and envelope <> '{}'::jsonb
  ) then raise exception 'rejected ciphertext retained'; end if;

  perform wqrs_retention_validation_20261004.relay_cleanup(1700000011);
  if not exists (
    select 1 from wqrs_retention_validation_20261004.relay_deliveries
    where delivery_id='legacy' and expires_at=1700000300 and ack_envelope is null
  ) then raise exception 'ACK cleanup removed or shortened replay tombstone'; end if;
  if not exists (
    select 1 from wqrs_retention_validation_20261004.relay_deliveries
    where delivery_id='pending' and envelope->>'ciphertext'='synthetic'
  ) then raise exception 'live pending ciphertext removed'; end if;
  if exists (select 1 from wqrs_retention_validation_20261004.relay_pairings)
    or exists (select 1 from wqrs_retention_validation_20261004.relay_rate_limits)
    or exists (select 1 from wqrs_retention_validation_20261004.relay_deliveries where delivery_id='expired')
    then raise exception 'expired fixture cleanup failed'; end if;
  begin
    insert into wqrs_retention_validation_20261004.relay_deliveries values
      ('duplicate','pair','message','pending','{}',null,1700000300);
    raise exception 'duplicate message accepted after ACK expiry';
  exception when unique_violation then null;
  end;
  if has_function_privilege('anon','wqrs_retention_validation_20261004.relay_cleanup(bigint)','execute')
    or has_function_privilege('authenticated','wqrs_retention_validation_20261004.relay_cleanup(bigint)','execute')
    or not has_function_privilege('service_role','wqrs_retention_validation_20261004.relay_cleanup(bigint)','execute')
    then raise exception 'cleanup grants are incorrect'; end if;
  perform wqrs_retention_validation_20261004.relay_cleanup(1700000301);
  if exists (select 1 from wqrs_retention_validation_20261004.relay_deliveries)
    then raise exception 'expired replay tombstones remain'; end if;
end;
$$;
rollback;
select 'PASS: isolated migration, ACK cleanup, replay uniqueness, URL expiry and role grants; fixture changes rolled back' as verification;
