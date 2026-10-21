// Test-only runner. Never reads a production DB URL, .env or Supabase key.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const root = new URL("../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");
const operations = "supabase/operations/";
// Read before opening even the disposable database, so absent delivery files fail clearly.
const [install, remove, check, fixture, migration] = await Promise.all([
  read(`${operations}install_retention_cron.sql`), read(`${operations}uninstall_retention_cron.sql`),
  read(`${operations}check_retention_cron.sql`), read("protocol/fixtures/retention_schedule.sql"),
  read("supabase/migrations/202610030001_separate_receipts_from_replay.sql"),
]);
let db;
if (process.argv[2] === "--pglite" && process.argv[3]) {
  const { PGlite } = await import(pathToFileURL(process.argv[3]).href);
  const memory = new PGlite();
  db = { exec: sql => memory.exec(sql), query: async sql => (await memory.query(sql)).rows, close: () => memory.close() };
} else if (process.argv[2] === "--postgres") {
  const run = sql => {
    const result = spawnSync("psql", ["-X", "--no-password", "-v", "ON_ERROR_STOP=1", "-Atq",
      "-h", "127.0.0.1", "-p", "5432", "-U", "postgres", "-d", "wqrs_retention_test"],
    { input: sql, encoding: "utf8", timeout: 30_000, windowsHide: true });
    if (result.error) throw result.error;
    if (result.status !== 0) throw new Error(result.stderr);
    return result.stdout.trim();
  };
  // Fixed loopback host + fixed disposable database, no DATABASE_URL override.
  assert.equal(run("select current_database();"), "wqrs_retention_test");
  db = { exec: async sql => run(sql), query: async sql => JSON.parse(run(
    `select coalesce(json_agg(q), '[]'::json) from (${sql.trim().replace(/;$/, "")}) q;`)), close: async () => {} };
} else {
  throw new Error("Use --postgres (fixed local CI database) or --pglite <absolute module path>");
}
const jobName = "wqrs-relay-retention-v1";
const query = sql => db.query(sql);
const expectFailure = async (sql, pattern) => {
  await assert.rejects(db.exec(sql), pattern);
  // Installation scripts use explicit transactions; reset the failed test transaction.
  await db.exec("rollback;");
};
try {
  await db.exec(fixture);
  const retentionRegression = await read("protocol/check_relay_retention.sql");
  assert.equal(retentionRegression.split("-- RELEASE_MIGRATION_HERE").length, 2);
  const isolatedMigration = migration.replaceAll("public.", "wqrs_retention_validation_20261004.");
  assert.ok(!isolatedMigration.includes("public."));
  // A replacement callback preserves PostgreSQL $$ quoting literally.
  await db.exec(retentionRegression.replace("-- RELEASE_MIGRATION_HERE", () => isolatedMigration));
  await expectFailure(install, /relay_cleanup migration/i);
  await db.exec(migration);
  assert.equal((await query(check))[0].health, "missing");
  await db.exec("insert into public.relay_pairs values ('saved-phone','synthetic-token-hash');");
  await db.exec("insert into public.relay_pairings values ('expired',0),('live',4102444800);");
  await db.exec("insert into public.relay_rate_limits values ('expired',0),('live',4102444800);");
  await db.exec(`insert into public.relay_deliveries values
    ('expired','saved-phone','expired','pending','{}',null,0),
    ('pending','saved-phone','pending','pending','{"ciphertext":"synthetic"}',null,4102444800),
    ('receipt','saved-phone','receipt','delivered','{}','{"expires_at":0}',4102444800);`);
  await db.exec(install);
  const [job] = await query(`select * from cron.job where jobname='${jobName}'`);
  assert.equal(job.schedule, "*/5 * * * *");
  assert.equal(job.active, true);
  assert.equal((await query("select count(*)::integer as n from public.relay_deliveries"))[0].n, 3,
    "install must not run cleanup immediately");
  await db.exec(install);
  assert.equal((await query("select count(*)::integer as n from cron.job"))[0].n, 1);
  assert.equal((await query(check))[0].health, "not_yet_run");
  // Run the EXACT registered command in the disposable database (not a re-created equivalent).
  await db.exec(job.command);
  assert.deepEqual((await query("select pairing_id from public.relay_pairings")).map(row => row.pairing_id), ["live"]);
  assert.equal((await query("select count(*)::integer as n from public.relay_pairs"))[0].n, 1);
  assert.equal((await query("select count(*)::integer as n from public.relay_deliveries"))[0].n, 2);
  assert.equal((await query("select envelope->>'ciphertext' as text from public.relay_deliveries where delivery_id='pending'"))[0].text, "synthetic");
  assert.equal((await query("select ack_envelope from public.relay_deliveries where delivery_id='receipt'"))[0].ack_envelope, null);
  await db.exec(`insert into cron.job_run_details(jobid,status,start_time,end_time,return_message)
    values (${job.jobid},'succeeded',now(),now(),'must-not-appear-in-status');`);
  assert.equal((await query(check))[0].health, "ok");
  assert.doesNotMatch(JSON.stringify(await query(check)), /must-not-appear|synthetic-token/);
  await db.exec("update cron.job_run_details set start_time=now()-interval '1 hour', end_time=now()-interval '1 hour';");
  assert.equal((await query(check))[0].health, "stale");
  await db.exec("update cron.job_run_details set status='failed';");
  assert.equal((await query(check))[0].health, "failed");
  await db.exec("update cron.job set active=false;");
  assert.equal((await query(check))[0].health, "inactive");
  await db.exec(install);
  assert.equal((await query(`select active from cron.job where jobname='${jobName}'`))[0].active, true);
  for (const [change, restore] of [
    ["database='other-database'", "database=current_database()"],
    ["username='other-owner'", "username=current_user"],
    ["schedule='0 * * * *'", "schedule='*/5 * * * *'"],
    ["command='select 42'", `command='${job.command.replaceAll("'", "''")}'`],
  ]) {
    await db.exec(`update cron.job set ${change} where jobname='${jobName}';`);
    await expectFailure(install, /unexpected definition/i);
    await expectFailure(remove, /unexpected definition/i);
    assert.equal((await query(`select count(*)::integer as n from cron.job where jobname='${jobName}'`))[0].n, 1);
    await db.exec(`update cron.job set ${restore} where jobname='${jobName}';`);
  }
  await db.exec("insert into cron.job(jobname,schedule,command) values('unrelated-job','0 * * * *','select 1');");
  await db.exec(remove);
  await db.exec(remove);
  assert.deepEqual((await query("select jobname from cron.job")).map(row => row.jobname), ["unrelated-job"]);
  await db.exec(`insert into cron.job(jobname,schedule,command) values('${jobName}','0 * * * *','select 42');`);
  assert.equal((await query(check))[0].health, "unexpected_definition");
  await expectFailure(install, /unexpected definition/i);
  await expectFailure(remove, /unexpected definition/i);
  await db.exec(`delete from cron.job where jobname='${jobName}';`);
  await db.exec(`insert into cron.job(jobname,schedule,command) values('duplicate-cleanup','*/5 * * * *',${"'" + job.command.replaceAll("'", "''") + "'"});`);
  await expectFailure(install, /another cleanup job/i);
  await db.exec("update cron.job set jobname=null where jobname='duplicate-cleanup';");
  await expectFailure(install, /another cleanup job/i);
  await db.exec("delete from cron.job where jobname is null;");
  await db.exec("delete from cron.job where jobname='duplicate-cleanup'; grant execute on function public.relay_cleanup(bigint) to anon;");
  await expectFailure(install, /public client roles/i);
  await db.exec("revoke execute on function public.relay_cleanup(bigint) from anon;");
  await expectFailure("set role authenticated; " + install, /postgres role/i);
  await db.exec("reset role;");
  console.log("PASS: SQL install/idempotence, exact scheduled command, live-pair preservation, expiry/ACK cleanup,");
  console.log("status/privacy, stale/failure detection, scoped uninstall, collision/duplicate/role guards");
  console.log("Boundary fixture only: pg_cron's scheduler, worker and real hosted project were NOT exercised.");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  await db.close();
}
