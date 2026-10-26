-- Serialize enqueue with revocation on the pair row, including older API
-- deployments whose authorization read precedes a slow request-body upload.
begin;

create or replace function public.relay_require_active_delivery_pair()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  pair_device text;
  pair_revoked bigint;
begin
  select p.device_id, p.revoked_at into pair_device, pair_revoked
  from public.relay_pairs p
  where p.pair_id = new.pair_id
  for update;

  if not found or pair_revoked is not null then
    raise exception using errcode = 'P0410', message = 'Pair revoked';
  end if;
  if pair_device <> new.device_id then
    raise exception using errcode = '23514', message = 'Delivery device does not match pair';
  end if;
  return new;
end;
$$;

revoke all on function public.relay_require_active_delivery_pair()
  from public, anon, authenticated, service_role;

create trigger relay_require_active_delivery_pair_trigger
before insert or update of pair_id, device_id on public.relay_deliveries
for each row execute function public.relay_require_active_delivery_pair();

-- The existing revocation UPDATE takes the same pair-row lock. If enqueue
-- wins, its transaction commits before UPDATE and the subsequent DELETE
-- removes it. If UPDATE wins, the trigger observes revoked_at and rejects.
-- Also exclude rows during the older API's UPDATE -> DELETE interval.
create or replace function public.relay_claim_delivery(
  p_device_id text,
  p_now bigint,
  p_lease_until bigint
)
returns table (
  delivery_id text, pair_id text, device_id text, message_id text,
  envelope jsonb, expires_at bigint, status text, ack_envelope jsonb
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  return query
  with candidate as (
    select d.delivery_id
    from public.relay_deliveries d
    where d.device_id = p_device_id
      and d.expires_at >= p_now
      and exists (
        select 1 from public.relay_pairs p
        where p.pair_id = d.pair_id and p.device_id = d.device_id
          and p.revoked_at is null
      )
      and (d.status = 'pending'
        or (d.status = 'delivering' and d.lease_until <= p_now))
    order by d.created_at
    for update of d skip locked
    limit 1
  )
  update public.relay_deliveries d
  set status = 'delivering', lease_until = p_lease_until
  from candidate c
  where d.delivery_id = c.delivery_id
  returning d.delivery_id, d.pair_id, d.device_id, d.message_id,
    d.envelope, d.expires_at, d.status, d.ack_envelope;
end;
$$;

revoke all on function public.relay_claim_delivery(text, bigint, bigint)
  from public, anon, authenticated, service_role;
grant execute on function public.relay_claim_delivery(text, bigint, bigint)
  to service_role;

commit;
