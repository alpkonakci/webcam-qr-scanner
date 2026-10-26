// Disposable SQL only; no environment, credentials or production URLs are read.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';

const psqlArgs = ['-X', '--no-password', '-v', 'ON_ERROR_STOP=1',
  '-v', 'VERBOSITY=verbose', '-Atq', '-h', '127.0.0.1', '-p', '5432',
  '-U', 'postgres', '-d', 'wqrs_revocation_test'];

async function holdTransaction(sql) {
  const child = spawn('psql', psqlArgs, { windowsHide: true });
  let output = '';
  let errors = '';
  child.stdout.on('data', chunk => { output += chunk; });
  child.stderr.on('data', chunk => { errors += chunk; });
  const exited = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve() : reject(new Error(errors)));
  });
  // Observe rejection immediately, even if startup fails before the marker.
  exited.catch(() => {});
  const deadline = Date.now() + 10_000;
  child.stdin.write(`begin; set role service_role; ${sql};\n\\echo LOCK_HELD\n`);
  try {
    while (!output.includes('LOCK_HELD')) {
      if (child.exitCode !== null || Date.now() > deadline) throw new Error(errors || 'SQL lock holder timed out');
      await new Promise(resolve => setTimeout(resolve, 20));
    }
  } catch (error) { child.kill(); throw error; }
  return async () => {
    child.stdin.end('commit;\n');
    await exited;
  };
}

let db;
if (process.argv[2] === '--pglite' && process.argv[3]) {
  const { PGlite } = await import(pathToFileURL(process.argv[3]).href);
  db = new PGlite();
} else if (process.argv[2] === '--postgres') {
  const run = sql => {
    const result = spawnSync('psql', psqlArgs,
    { input: sql, encoding: 'utf8', timeout: 30_000, windowsHide: true });
    if (result.error) throw result.error;
    if (result.status !== 0) {
      const error = new Error(result.stderr);
      error.code = result.stderr.match(/ERROR:\s+([A-Z0-9]{5}):/)?.[1];
      throw error;
    }
    return result.stdout.trim();
  };
  assert.equal(run('select current_database()'), 'wqrs_revocation_test');
  // Each psql invocation is a fresh session; carry only the chosen test role.
  let role = '';
  const sessionSql = sql => {
    if (/^reset role; set role /.test(sql)) {
      role = sql.split('set role ').at(-1);
      return '';
    }
    if (/^set role /.test(sql)) { role = sql.slice(9); return ''; }
    return (role ? `set role ${role};` : '') + sql;
  };
  db = {
    exec: async sql => run(sessionSql(sql)),
    query: async sql => ({ rows: JSON.parse(run(sessionSql(
      `select coalesce(json_agg(q),'[]'::json) from (${sql}) q`))) }),
    close: async () => {},
  };
} else {
  throw new Error('Use --postgres (fixed disposable CI database) or --pglite <absolute module path> [--baseline]');
}
const read = path => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
try {
  await db.exec(`
    do $$ begin
      if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
      if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
      if not exists(select 1 from pg_roles where rolname='service_role') then create role service_role bypassrls; end if;
    end $$;
    alter role service_role bypassrls;
    create schema auth; create table auth.users(id uuid primary key);
    create function auth.uid() returns uuid language sql as $$ select null::uuid $$;
    create schema realtime; create table realtime.messages(id int);
    create function realtime.topic() returns text language sql as $$ select ''::text $$;
    create function realtime.send(jsonb,text,text,boolean) returns void language sql as $$ select $$;
  `);
  await db.exec((await read('supabase/migrations/202608030001_phone_to_pc_relay.sql'))
    .replace('create extension if not exists pgcrypto;', ''));
  if (!process.argv.includes('--baseline')) {
    await db.exec(await read('supabase/migrations/202610260001_serialize_delivery_revocation.sql'));
  }
  await db.exec(`
    insert into auth.users values ('00000000-0000-0000-0000-000000000001');
    insert into public.relay_devices values
      (repeat('d',22),repeat('a',64),'00000000-0000-0000-0000-000000000001',1,100);
    insert into public.relay_pairs values (repeat('p',22),repeat('d',22),repeat('b',64),1,null);
  `);
  const insert = (id, device = 'd') => `insert into public.relay_deliveries
    (delivery_id,pair_id,device_id,message_id,envelope,created_at,expires_at,status)
    values (repeat('${id}',22),repeat('p',22),repeat('${device}',22),repeat('${id}',22),'{}',100,400,'pending')`;
  await db.exec('set role service_role');
  // Send wins first: removal must delete its queued delivery.
  await db.exec(insert('x'));
  await db.exec(`update public.relay_pairs set revoked_at=101;
    delete from public.relay_deliveries where pair_id=repeat('p',22);`);
  // Removal wins first (including authorization followed by a slow body upload).
  await assert.rejects(db.exec(insert('y')), error => error.code === 'P0410');
  assert.equal((await db.query('select count(*)::int as n from public.relay_deliveries')).rows[0].n, 0);
  // Compatibility with older split removal: a row existing between UPDATE and
  // DELETE must not be claimable after revocation is visible.
  await db.exec('update public.relay_pairs set revoked_at=null');
  await db.exec(insert('z'));
  const claimed = await db.query(`select * from public.relay_claim_delivery(repeat('d',22),100,108)`);
  assert.equal(claimed.rows.length, 1);
  assert.equal(claimed.rows[0].delivery_id, 'z'.repeat(22));
  assert.equal((await db.query(`select * from public.relay_claim_delivery(repeat('d',22),101,109)`)).rows.length, 0);
  assert.equal((await db.query(`select * from public.relay_claim_delivery(repeat('d',22),108,116)`)).rows.length, 1);
  await db.exec('update public.relay_pairs set revoked_at=102');
  assert.equal((await db.query(`select * from public.relay_claim_delivery(repeat('d',22),117,125)`)).rows.length, 0);
  await db.exec('update public.relay_pairs set revoked_at=null');
  await assert.rejects(db.exec(insert('w', 'e')), error => error.code === '23514');
  if (process.argv[2] === '--postgres') {
    await db.exec('delete from public.relay_deliveries');
    // Two real sessions: without the trigger's FOR UPDATE, this INSERT would
    // succeed against the old visible row instead of waiting for revocation.
    const commitRevocation = await holdTransaction('update public.relay_pairs set revoked_at=120');
    try {
      await assert.rejects(db.exec(`set lock_timeout='250ms'; ${insert('r')}`),
        error => error.code === '55P03');
    } finally { await commitRevocation(); }
    await assert.rejects(db.exec(insert('r')), error => error.code === 'P0410');
    await db.exec('update public.relay_pairs set revoked_at=null');
    const commitSend = await holdTransaction(insert('s'));
    try {
      await assert.rejects(db.exec(`set lock_timeout='250ms'; update public.relay_pairs set revoked_at=121`),
        error => error.code === '55P03');
    } finally { await commitSend(); }
    await db.exec(`update public.relay_pairs set revoked_at=121; delete from public.relay_deliveries`);
    assert.equal((await db.query('select count(*)::int as n from public.relay_deliveries')).rows[0].n, 0);
    console.log('PASS: two-session enqueue/revocation lock contention in both directions');
  }
  for (const role of ['anon', 'authenticated']) {
    await db.exec(`reset role; set role ${role}`);
    await assert.rejects(db.exec(insert('u')), error => error.code === '42501');
    await assert.rejects(db.exec(`select * from public.relay_claim_delivery(repeat('d',22),109,117)`),
      error => error.code === '42501');
  }
  console.log('PASS: revocation ordering, active/expired lease, device binding, service/browser role boundaries');
} finally { await db.close(); }
