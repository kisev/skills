import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const cli = new URL("../dist/cli.js", import.meta.url).pathname;
const version = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
).version;

function run(args, env = {}) {
  const environment = { ...process.env };
  delete environment.REVIEWMATIC_CONFIG;
  delete environment.REVIEWMATIC_JSON;
  return spawnSync(process.execPath, [cli, ...args], {
    encoding: "utf8",
    env: { ...environment, ...env },
  });
}

test("version, help, and bogus subcommands exit cleanly", () => {
  assert.equal(run(["--version"]).stdout.trim(), version);
  for (const args of [
    [],
    ["--help"],
    ["prepare", "--help"],
    ["finalize-review", "--help"],
    ["publication", "--help"],
  ]) {
    const result = run(args);
    assert.equal(result.status, 0, args.join(" "));
    assert.ok(result.stdout.includes("Usage:"));
  }
  const rootHelp = run(["--help"]).stdout;
  for (const command of [
    "prepare",
    "context",
    "scaffold-review",
    "status",
    "next",
    "template-review",
    "report-review",
    "finalize",
    "prepare-local",
    "finalize-local",
    "assess-mode",
    "finalize-review",
    "record-artifact",
    "publication",
    "capabilities",
    "marker-run",
  ]) {
    assert.ok(rootHelp.includes(command), command);
  }
  const bogus = run(["bogus"]);
  assert.equal(bogus.status, 2);
  assert.ok(bogus.stderr.length > 0);
  assert.equal(run(["status"]).status, 2);
});

test("status on an empty XDG state home reports incomplete stale state", () => {
  const home = mkdtempSync(join(tmpdir(), "reviewmatic-cli-"));
  try {
    const root = join(home, "agent-skills", "gitlab", "c".repeat(32));
    const result = run(["status", "--artifact-root", root], { XDG_STATE_HOME: home });
    assert.equal(result.status, 0);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.status, "incomplete");
    assert.equal(payload.stage, "stale");
    assert.equal(payload.resume_stage, "prepared");
    assert.equal(payload.external_mutations, false);
    const next = run(["next", "--artifact-root", root], { XDG_STATE_HOME: home });
    assert.equal(next.status, 0);
    assert.equal(JSON.parse(next.stdout).status, "incomplete");
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});

test("capabilities emit the contract and publication payloads", () => {
  for (const args of [["capabilities"], ["--capabilities"]]) {
    const result = run(args);
    assert.equal(result.status, 0);
    const payload = JSON.parse(result.stdout);
    assert.equal(payload.profile, "code-review");
    assert.equal(payload.external_mutations, false);
    assert.equal(payload.mutation, "local-write");
    assert.equal(payload.dry_run, true);
  }
  const publication = run(["publication", "--capabilities"]);
  assert.equal(publication.status, 0);
  const payload = JSON.parse(publication.stdout);
  assert.equal(payload.schema, "code-review/publication/v1");
  assert.equal(payload.platform, "posix");
  assert.deepEqual(payload.operations, ["apply", "inspect", "retry"]);
  assert.equal(payload.external_mutations, false);
});

test("publication and marker-run surface mirror their Python entrypoints", () => {
  const missing = run(["publication"]);
  assert.equal(missing.status, 2);
  assert.equal(JSON.parse(missing.stdout).error, "mode, --action and --confirm are required");
  const invalid = run(["publication", "bogus"]);
  assert.equal(invalid.status, 2);
  assert.match(JSON.parse(invalid.stdout).error, /invalid choice: 'bogus'/);
  const marker = run(["marker-run", "--skill", "code-review"]);
  assert.equal(marker.status, 2);
  assert.equal(
    marker.stderr.trim(),
    "error: the following arguments are required: --action, --binding",
  );
  const home = mkdtempSync(join(tmpdir(), "reviewmatic-marker-"));
  try {
    const applied = run(
      [
        "marker-run",
        "--skill",
        "code-review",
        "--action",
        "test",
        "--binding",
        "a".repeat(64),
        "--",
        "/bin/true",
      ],
      { XDG_STATE_HOME: home },
    );
    assert.equal(applied.status, 0);
  } finally {
    rmSync(home, { recursive: true, force: true });
  }
});
