-- Stop ONLY the verified WQRS job. Never drop pg_cron or touch another job.
-- Already deleted data is NOT restored; an already-running execution may finish.
begin;
set local lock_timeout = '2s';
set local statement_timeout = '10s';
do $uninstall$
declare
  expected_name constant text := 'wqrs-relay-retention-v1';
  expected_command constant text := 'BEGIN; SET LOCAL statement_timeout = ''30s''; SET LOCAL lock_timeout = ''2s''; SELECT public.relay_cleanup(floor(extract(epoch from clock_timestamp()))::bigint); COMMIT;';
  target_id bigint;
begin
  if current_user <> 'postgres' then
    raise exception 'Use the postgres role in the verified target project';
  end if;
  if to_regclass('cron.job') is null then
    raise notice 'pg_cron is not installed; no retention job to remove';
    return;
  end if;
  if exists (
    select 1 from cron.job where jobname = expected_name
      and (database <> current_database() or username <> current_user
           or command <> expected_command or schedule <> '*/5 * * * *')
  ) then
    raise exception 'Retention job has an unexpected definition; inspect before removing';
  end if;
  select jobid into target_id from cron.job
    where jobname = expected_name and database = current_database() and username = current_user;
  if target_id is not null then
    perform cron.unschedule(target_id);
  end if;
end $uninstall$;
commit;
