-- Preserve the original message's replay window independently of its ACK.
-- No new tables/columns or client privileges are introduced.
-- Apply before deploying the corresponding relay handler. Surviving legacy
-- delivered rows can be repaired; already deleted rows cannot be recovered.
update public.relay_deliveries
set expires_at = greatest(expires_at, (envelope ->> 'expires_at')::bigint),
    envelope = '{}'::jsonb
where status in ('delivered', 'rejected')
  and (envelope ->> 'expires_at') ~ '^[0-9]{1,16}$';

create or replace function public.relay_cleanup(p_now bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.relay_pairings where expires_at < p_now;
  -- Opaque replay IDs remain until URL expiry; expired receipt ciphertext does not.
  update public.relay_deliveries
    set ack_envelope = null
    where status = 'delivered'
      and case
        when (ack_envelope ->> 'expires_at') ~ '^[0-9]{1,16}$'
          then (ack_envelope ->> 'expires_at')::bigint < p_now
        else false
      end;
  delete from public.relay_deliveries where expires_at < p_now;
  delete from public.relay_rate_limits where expires_at < p_now;
end;
$$;

revoke all on function public.relay_cleanup(bigint) from public, anon, authenticated;
grant execute on function public.relay_cleanup(bigint) to service_role;
