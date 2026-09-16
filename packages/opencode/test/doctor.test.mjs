import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import { collectDoctorFacts, doctorExitCode } from "../dist/doctor.js";
import { renderDoctor } from "../dist/cli-output.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const ROOT = resolve(PACKAGE, "../..");
const PACKAGE_VERSION = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8")).version;

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "skills-opencode-doctor-"));
  const project = join(root, "project");
  const home = join(root, "home");
  mkdirSync(project);
  mkdirSync(home);
  return { root, project, home };
}

function environment(home) {
  return {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: join(home, ".config"),
    XDG_STATE_HOME: join(home, ".state"),
  };
}

test("doctor JSON is versioned, read-only, partial tolerant, and has stable exit code", async () => {
  const item = fixture();
  try {
    const before = readdirSync(item.root).sort();
    const result = spawnSync(process.execPath, [join(PACKAGE, "dist/cli.js"), "doctor", "--json"], {
      cwd: item.project,
      env: environment(item.home),
      encoding: "utf8",
    });
    assert.equal(result.status, 1);
    const report = JSON.parse(result.stdout);
    assert.equal(report.schema_version, 1);
    assert.equal(report.mutations, false);
    assert.equal(report.scope, "project");
    assert.equal(report.status, "problems");
    assert.ok(report.counts.incomplete > 0 || report.counts.fail > 0);
    assert.ok(
      report.checks.every((check) => ["pass", "warn", "fail", "incomplete"].includes(check.status)),
    );
    assert.deepEqual(readdirSync(item.root).sort(), before);
    assert.equal(doctorExitCode({ status: "clean" }), 0);
    assert.equal(doctorExitCode({ status: "problems" }), 1);
    assert.equal(doctorExitCode({ status: "incomplete" }), 2);
  } finally {
    rmSync(item.root, { recursive: true, force: true });
  }
});

test("doctor rejects removed scope syntax with exit code two", () => {
  const item = fixture();
  try {
    const result = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist/cli.js"), "doctor", "--scope", "project", "--json"],
      { cwd: item.project, env: environment(item.home), encoding: "utf8" },
    );
    assert.equal(result.status, 2);
    assert.equal(JSON.parse(result.stdout).error.code, "invalid_input");
  } finally {
    rmSync(item.root, { recursive: true, force: true });
  }
});

test("doctor classifies malformed durable state as incomplete without recovery", async () => {
  const item = fixture();
  try {
    const state = join(item.home, ".local", "state", "opencode", "skills", "attempt", "attempts");
    mkdirSync(state, { recursive: true });
    writeFileSync(join(state, "malformed.json"), "{not-json\n");
    const report = await collectDoctorFacts("project", item.project, item.home);
    const attempt = report.checks.find((check) => check.id === "state.attempt");
    assert.equal(attempt.status, "incomplete");
    assert.equal(attempt.evidence.malformed, 1);
    assert.equal(readFileSync(join(state, "malformed.json"), "utf8"), "{not-json\n");
  } finally {
    rmSync(item.root, { recursive: true, force: true });
  }
});

test("doctor never serializes config secrets and classifies collisions as problems", async () => {
  const item = fixture();
  try {
    mkdirSync(join(item.project, ".opencode", "commands"), { recursive: true });
    writeFileSync(
      join(item.project, "opencode.json"),
      JSON.stringify({
        plugin: ["@kisev/skills-opencode"],
        token: "doctor-secret",
        apiKey: "another-secret",
        authorization: "Bearer hidden",
      }),
    );
    writeFileSync(join(item.project, ".opencode", "commands", "doctor.md"), "user-owned\n");
    const report = await collectDoctorFacts("project", item.project, item.home);
    const serialized = JSON.stringify(report);
    assert.equal(serialized.includes("doctor-secret"), false);
    assert.equal(serialized.includes("another-secret"), false);
    assert.equal(serialized.includes("Bearer hidden"), false);
    assert.equal(report.mutations, false);
    assert.ok(report.checks.some((check) => check.status === "fail"));
    assert.equal(report.status, "problems");
    const rendered = renderDoctor(report);
    assert.equal(rendered.includes("doctor-secret"), false);
    assert.match(
      rendered,
      new RegExp(
        `npx --yes ${escapeRegExp(`@kisev/skills-opencode@${PACKAGE_VERSION}`)} install --dry-run`,
      ),
    );
    assert.doesNotMatch(rendered, /npm exec -- skills-opencode/);
  } finally {
    rmSync(item.root, { recursive: true, force: true });
  }
});

test("doctor reports disabled LSP and inaccessible symlink inputs without reading through them", async () => {
  const item = fixture();
  const previous = process.env.OPENCODE_DISABLE_LSP_DOWNLOAD;
  try {
    writeFileSync(join(item.project, "sample.py"), "print('ok')\n");
    mkdirSync(join(item.root, "outside"));
    writeFileSync(
      join(item.root, "outside", "opencode.json"),
      JSON.stringify({ token: "outside-secret" }),
    );
    const link = join(item.project, ".opencode");
    symlinkSync(join(item.root, "outside"), link);
    process.env.OPENCODE_DISABLE_LSP_DOWNLOAD = "true";
    const report = await collectDoctorFacts("project", item.project, item.home);
    assert.ok(report.partial.includes("config.local"));
    assert.equal(
      report.lsp.servers.find((server) => server.name === "python").reason,
      "download-disabled",
    );
    assert.equal(JSON.stringify(report).includes("outside-secret"), false);
    assert.equal(report.status, "problems");
  } finally {
    if (previous === undefined) delete process.env.OPENCODE_DISABLE_LSP_DOWNLOAD;
    else process.env.OPENCODE_DISABLE_LSP_DOWNLOAD = previous;
    rmSync(item.root, { recursive: true, force: true });
  }
});

test("built package LSP catalog is byte-identical to the shared catalog", () => {
  const canonical = readFileSync(join(ROOT, "shared/references/lsp-catalog.json"));
  assert.deepEqual(readFileSync(join(PACKAGE, "dist/assets/lsp-catalog.json")), canonical);
});
