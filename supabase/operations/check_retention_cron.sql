-- READ ONLY. Run as postgres after pg_cron is enabled; no payload/error text is selected.
with target as (
  select jobid,jobname,schedule,command,active from cron.job
  where jobname='wqrs-relay-retention-v1'
    and database=current_database() and username=current_user
), latest as (
  select status,start_time,end_time from cron.job_run_details
  where jobid in (select jobid from target)
  order by start_time desc, runid desc limit 1
), success as (
  select max(end_time) as last_success_at from cron.job_run_details
  where jobid in (select jobid from target) and status='succeeded'
)
select target.jobid,target.jobname,target.schedule,target.active,
  case
    when target.jobid is null then 'missing'
    when target.schedule <> '*/5 * * * *' or target.command <> 'BEGIN; SET LOCAL statement_timeout = ''30s''; SET LOCAL lock_timeout = ''2s''; SELECT public.relay_cleanup(floor(extract(epoch from clock_timestamp()))::bigint); COMMIT;'
      then 'unexpected_definition'
    when not target.active then 'inactive'
    when latest.status = 'failed' then 'failed'
    when latest.status is null then 'not_yet_run'
    when success.last_success_at is null then 'awaiting_success'
    when success.last_success_at < now()-interval '15 minutes' then 'stale'
    else 'ok'
  end as health,
  success.last_success_at,latest.status as last_run_status,
  latest.start_time as last_run_started_at
from (values (1)) as singleton(value)
left join target on true
left join latest on true
cross join success;
