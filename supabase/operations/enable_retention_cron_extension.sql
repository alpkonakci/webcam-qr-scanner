-- OPT-IN prerequisite for install_retention_cron.sql in a verified project.
-- No cleanup is executed and no jobs are created by this file.
-- Do not drop the extension to undo a single job: use the scoped uninstall file.
begin;
set local lock_timeout = '2s';
set local statement_timeout = '10s';
do $guard$
begin
  if current_user <> 'postgres' then
    raise exception 'Use the postgres role in the verified target project';
  end if;
  if to_regprocedure('public.relay_cleanup(bigint)') is null then
    raise exception 'Verify the relay schema before enabling retention Cron';
  end if;
end $guard$;
create extension if not exists pg_cron with schema pg_catalog;
commit;
