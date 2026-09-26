-- Tighten SECURITY DEFINER execution after enabling Supabase's automatic RLS
-- helper. The event trigger invokes rls_auto_enable as its owner and does not
-- require browser-facing roles to call that function directly.
do $$
begin
  if to_regprocedure('public.rls_auto_enable()') is not null then
    execute 'revoke all on function public.rls_auto_enable() '
      || 'from public, anon, authenticated, service_role';
  end if;
end;
$$;

-- Anonymous Supabase Auth is intentionally used to avoid collecting an email,
-- phone number, or account profile. Require that claim explicitly as well as
-- the one-to-one device ownership check before a private topic is authorized.
create or replace function public.relay_can_receive_topic(p_topic text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(auth.jwt() ->> 'is_anonymous' = 'true', false)
    and exists (
      select 1
      from public.relay_devices
      where realtime_user_id = auth.uid()
        and p_topic = 'device:' || device_id
    );
$$;

revoke all on function public.relay_can_receive_topic(text)
  from public, anon, authenticated, service_role;
grant execute on function public.relay_can_receive_topic(text)
  to authenticated;
