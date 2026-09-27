import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { mkdtemp } from "node:fs/promises";
import {
  SELF_PACKAGE_NAME,
  SelfInstallError,
  ensureDependency,
  owningProjectDir,
  planDependency,
} from "../dist/self-install.js";
import { apply, preview } from "../dist/installer.js";
import { readPackageVersion } from "../dist/package-metadata.js";

const VERSION = readPackageVersion();

function temporary() {
  return mkdtempSync(join(tmpdir(), "self-install-"));
}

function stubRunner() {
  const calls = [];
  const runner = async (command, args, options) => {
    calls.push({ command, args, options });
    return { stdout: "", stderr: "" };
  };
  return { runner, calls };
}

test("owningProjectDir resolves global config and walks up for project scope", () => {
  const base = temporary();
  const project = join(base, "wrapped", "project");
  mkdirSync(project, { recursive: true });
  writeFileSync(join(base, "wrapped", "package.json"), '{"name":"host"}\n');
  assert.equal(
    owningProjectDir("global", project, join(base, "home")),
    join(base, "home", ".config", "opencode"),
  );
  assert.equal(owningProjectDir("project", project, join(base, "home")), join(base, "wrapped"));
  assert.equal(owningProjectDir("project", base, join(base, "home")), null);
});

test("planDependency reports manual for project scope without an npm project", () => {
  const base = temporary();
  const project = join(base, "project");
  mkdirSync(project);
  const plan = planDependency("project", project, join(base, "home"), VERSION);
  assert.equal(plan.status, "manual");
  assert.equal(plan.package_json, "missing");
  assert.equal(plan.dir, null);
});

test("planDependency detects satisfied, install, and update states", () => {
  const base = temporary();
  const home = join(base, "home");
  const dir = join(home, ".config", "opencode");
  mkdirSync(dir, { recursive: true });

  writeFileSync(
    join(dir, "package.json"),
    `{"name":"host","dependencies":{"${SELF_PACKAGE_NAME}":"${VERSION}"}}\n`,
  );
  assert.equal(planDependency("global", "/tmp", home, VERSION).status, "satisfied");

  writeFileSync(join(dir, "package.json"), '{"name":"host"}\n');
  const installPlan = planDependency("global", "/tmp", home, VERSION);
  assert.equal(installPlan.status, "install");
  assert.equal(installPlan.package_json, "present");

  writeFileSync(
    join(dir, "package.json"),
    `{"name":"host","dependencies":{"${SELF_PACKAGE_NAME}":"0.0.1"}}\n`,
  );
  assert.equal(planDependency("global", "/tmp", home, VERSION).status, "update");
});

test("planDependency proposes package.json creation for a fresh global home", () => {
  const base = temporary();
  const plan = planDependency("global", "/tmp", join(base, "home"), VERSION);
  assert.equal(plan.status, "install");
  assert.equal(plan.package_json, "create");
  assert.equal(plan.dir, join(base, "home", ".config", "opencode"));
});

test("ensureDependency creates package.json and runs npm install once", async () => {
  const base = temporary();
  const home = join(base, "home");
  const plan = planDependency("global", "/tmp", home, VERSION);
  const { runner, calls } = stubRunner();
  const result = await ensureDependency(plan, runner);
  assert.equal(result.applied, "changed");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, "npm");
  assert.deepEqual(calls[0].args, [
    "install",
    "--save-exact",
    `${SELF_PACKAGE_NAME}@${VERSION}`,
    "--no-audit",
    "--no-fund",
  ]);
  assert.equal(calls[0].options.cwd, plan.dir);
  const created = JSON.parse(readFileSync(join(plan.dir, "package.json"), "utf8"));
  assert.equal(created.private, true);
});

test("ensureDependency skips satisfied and manual plans without npm", async () => {
  const base = temporary();
  const { runner, calls } = stubRunner();
  const satisfied = {
    dir: "/tmp",
    name: SELF_PACKAGE_NAME,
    version: VERSION,
    status: "satisfied",
    package_json: "present",
  };
  const manual = {
    dir: null,
    name: SELF_PACKAGE_NAME,
    version: VERSION,
    status: "manual",
    package_json: "missing",
  };
  assert.equal((await ensureDependency(satisfied, runner)).applied, "unchanged");
  assert.equal((await ensureDependency(manual, runner)).applied, "skipped");
  assert.equal(calls.length, 0);
});

test("ensureDependency wraps npm failures as SelfInstallError", async () => {
  const base = temporary();
  const plan = {
    dir: "/tmp",
    name: SELF_PACKAGE_NAME,
    version: VERSION,
    status: "install",
    package_json: "present",
  };
  const failing = async () => {
    throw new Error("boom\nsecond line");
  };
  await assert.rejects(ensureDependency(plan, failing), (error) => {
    assert.ok(error instanceof SelfInstallError);
    assert.equal(error.code, "npm_dependency_failed");
    return true;
  });
});

test("project install plans and applies the dependency step", async () => {
  const base = await mkdtemp(join(tmpdir(), "self-install-apply-"));
  const project = join(base, "project");
  const home = join(base, "home");
  mkdirSync(project);
  mkdirSync(home);
  writeFileSync(join(project, "package.json"), '{"name":"host"}\n');
  const plan = await preview("install", "project", project, home);
  assert.equal(plan.dependency.status, "install");
  assert.equal(plan.dependency.dir, project);
  const { runner, calls } = stubRunner();
  const applied = await apply("install", "project", project, home, {
    dependencyRunner: runner,
  });
  assert.equal(applied.dependency.applied, "changed");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.cwd, project);
});

test("project install without an npm project skips the dependency step", async () => {
  const base = await mkdtemp(join(tmpdir(), "self-install-skip-"));
  const project = join(base, "project");
  const home = join(base, "home");
  mkdirSync(project);
  mkdirSync(home);
  const plan = await preview("install", "project", project, home);
  assert.equal(plan.dependency.status, "manual");
  const { runner, calls } = stubRunner();
  const applied = await apply("install", "project", project, home, {
    dependencyRunner: runner,
  });
  assert.equal(applied.dependency.applied, "skipped");
  assert.equal(calls.length, 0);
});
