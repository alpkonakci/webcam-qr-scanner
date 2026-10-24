import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const yaml = require("js-yaml");
const path = new URL("../../.github/workflows/ci.yml", import.meta.url);

test("CI is unprivileged, pinned, bounded, and runs all release checks without deploying", () => {
  assert.ok(existsSync(path), "the repository must define the approved CI gate");
  const source = readFileSync(path, "utf8");
  const workflow = yaml.load(source);
  assert.deepEqual(workflow.permissions, { contents: "read" });
  assert.deepEqual(Object.keys(workflow.on).sort(), ["pull_request", "push", "workflow_dispatch"]);
  assert.doesNotMatch(source, /\$\{\{\s*(?:secrets\.|github\.event\.(?:issue|pull_request)\.(?:title|body))/);
  assert.equal(workflow.concurrency["cancel-in-progress"], true);
  for (const job of Object.values(workflow.jobs)) {
    assert.ok(job["timeout-minutes"] > 0 && job["timeout-minutes"] <= 20);
    assert.equal(job.permissions, undefined);
    assert.equal(job["continue-on-error"], undefined);
    for (const step of job.steps) {
      if (step.uses) {
        assert.match(step.uses, /^actions\/(?:checkout|setup-python|setup-node)@[a-f0-9]{40}$/);
        if (step.uses.startsWith("actions/checkout@")) assert.equal(step.with["persist-credentials"], false);
      }
      assert.equal(step["continue-on-error"], undefined);
      assert.doesNotMatch(step.run ?? "", /(?:vercel|supabase|gh release|git push|curl.*\|.*sh)/i);
    }
  }
  const desktop = workflow.jobs.desktop;
  assert.match(desktop["runs-on"], /^windows-/);
  const desktopCommands = desktop.steps.map(step => step.run ?? "").join("\n");
  assert.match(desktopCommands, /-m venv \.venv/);
  assert.match(desktopCommands, /-m unittest discover -s tests/);
  assert.match(desktopCommands, /-c requirements-ci-constraints\.txt/);
  const web = workflow.jobs.web;
  assert.equal(web.defaults.run["working-directory"], "pwa");
  const webCommands = web.steps.map(step => step.run ?? "").join("\n");
  for (const command of ["npm ci", "npm test", "npm run lint", "npm run typecheck"]) {
    assert.ok(webCommands.includes(command), `missing release gate: ${command}`);
  }
  assert.match(workflow.jobs.retention.services.postgres.image, /^postgres:17@sha256:[a-f0-9]{64}$/);
  assert.ok(workflow.jobs.retention.steps.some(step => step.run === "node scripts/check_retention_schedule.mjs --postgres"));
});
