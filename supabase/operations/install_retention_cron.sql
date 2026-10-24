-- OPT-IN OPERATION, NOT AN AUTOMATIC MIGRATION.
-- Run only after project verification and explicit live activation approval.
-- Requires pg_cron enabled and all relay migrations applied, including 202610030001.
-- Registers a job; it does NOT call relay_cleanup immediately.
begin;
set local lock_timeout = '2s';
set local statement_timeout = '10s';
do $install$
declare
  expected_name constant text := 'wqrs-relay-retention-v1';
  expected_command constant text := 'BEGIN; SET LOCAL statement_timeout = ''30s''; SET LOCAL lock_timeout = ''2s''; SELECT public.relay_cleanup(floor(extract(epoch from clock_timestamp()))::bigint); COMMIT;';
begin
  if current_user <> 'postgres' then
    raise exception 'Use the postgres role in the verified target project';
  end if;
  if to_regclass('cron.job') is null
     or to_regprocedure('cron.schedule(text,text,text)') is null then
    raise exception 'Enable pg_cron explicitly before installing the retention job';
  end if;
  if to_regprocedure('public.relay_cleanup(bigint)') is null then
    raise exception 'Apply the relay_cleanup migration before scheduling retention';
  end if;
  if has_function_privilege('anon','public.relay_cleanup(bigint)','execute')
     or has_function_privilege('authenticated','public.relay_cleanup(bigint)','execute') then
    raise exception 'Cleanup must not be executable by public client roles';
  end if;
  if exists (
    select 1 from cron.job where jobname = expected_name
      and (database <> current_database() or username <> current_user
           or command <> expected_command or schedule <> '*/5 * * * *')
  ) then
    raise exception 'Retention job has an unexpected definition; inspect before replacing';
  end if;
  if exists (
    select 1 from cron.job where database = current_database()
      and jobname is distinct from expected_name and position('relay_cleanup' in lower(command)) > 0
  ) then
    raise exception 'Another cleanup job already exists; inspect before installing a duplicate';
  end if;
  perform cron.schedule(expected_name, '*/5 * * * *', expected_command);
end $install$;
commit;
