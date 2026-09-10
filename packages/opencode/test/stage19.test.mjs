import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import rootPlugin, { rulesInjector, rtk, zedBell } from "../dist/index.js";
import { apply, preview } from "../dist/installer.js";
import { archiveRoot } from "../dist/lifecycle.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const OLD_PLUGIN = "plugins/background-attempts.js";

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("installer preserves exact selection and keeps core separate from plugins", async () => {
  const base = mkdtempSync(join(tmpdir(), "skills-opencode-stage19-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([mkdir(project), mkdir(home)]);
  try {
    const selection = { commands: ["agents-md"], agents: [], plugins: [] };
    const plan = await preview("install", "project", project, home, selection);
    assert.equal(plan.schema_version, 2);
    assert.deepEqual(plan.selection, {
      commands: ["agents-md"],
      agents: [],
      plugins: [],
      core_activation: false,
    });
    assert.equal(
      plan.operations.some((item) => item.path.startsWith("plugins/")),
      false,
    );
    await apply("install", "project", plan.digest, project, home, {}, selection);
    const manifest = JSON.parse(
      await readFile(join(project, ".opencode", ".skills-opencode-manifest.json"), "utf8"),
    );
    assert.deepEqual(manifest.commands, ["agents-md"]);
    assert.deepEqual(manifest.agents, []);
    assert.deepEqual(manifest.plugins, []);
    assert.equal(manifest.core_activation, false);
    await assert.rejects(lstat(join(project, ".opencode", "agents")), { code: "ENOENT" });
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});

test("retired exact-owned plugin is archived once during uninstall", async () => {
  const base = mkdtempSync(join(tmpdir(), "skills-opencode-archive-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([
    mkdir(join(project, ".opencode", "plugins"), { recursive: true }),
    mkdir(home),
  ]);
  try {
    const content = execFileSync(
      "git",
      ["show", `cf470eba56de19ee245834d20f527fb007065597:packages/opencode/assets/${OLD_PLUGIN}`],
      {
        cwd: resolve(PACKAGE, "../.."),
      },
    );
    const fileHash = hash(content);
    await writeFile(join(project, ".opencode", "plugins", "background-attempts.js"), content);
    const manifest = {
      schema_version: 2,
      package: "@kisev/skills-opencode",
      package_version: "1.0.0",
      version: "1.0.0",
      scope: "project",
      commands: [],
      agents: [],
      plugins: [],
      core_activation: false,
      files: { [OLD_PLUGIN]: { sha256: fileHash, mode: 0o644, kind: "plugin" } },
    };
    await writeFile(
      join(project, ".opencode", ".skills-opencode-manifest.json"),
      `${JSON.stringify(manifest)}\n`,
    );
    const plan = await preview("uninstall", "project", project, home);
    assert.equal(
      plan.operations.find((item) => item.path === OLD_PLUGIN).operation,
      "archive-pending",
    );
    await apply("uninstall", "project", plan.digest, project, home);
    await assert.rejects(lstat(join(project, ".opencode", OLD_PLUGIN)), { code: "ENOENT" });
    const index = JSON.parse(
      await readFile(join(archiveRoot("project", project, home), "index.json"), "utf8"),
    );
    assert.equal(index.entries.length, 1);
    assert.equal(index.entries[0].original_hash, fileHash);
    const object = join(archiveRoot("project", project, home), "objects", fileHash);
    assert.equal(hash(await readFile(object)), fileHash);
    const second = await preview("uninstall", "project", project, home);
    assert.equal(second.operations.length, 0);
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});

test("stale install archival is transactional and recoverable", async () => {
  const base = mkdtempSync(join(tmpdir(), "skills-opencode-stale-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([
    mkdir(join(project, ".opencode", "commands"), { recursive: true }),
    mkdir(home),
  ]);
  try {
    const content = Buffer.from("stale managed command\n");
    const fileHash = hash(content);
    await writeFile(join(project, ".opencode", "commands", "old.md"), content);
    await writeFile(
      join(project, ".opencode", ".skills-opencode-manifest.json"),
      `${JSON.stringify({
        schema_version: 2,
        package: "@kisev/skills-opencode",
        package_version: "1.0.0",
        version: "1.0.0",
        scope: "project",
        commands: [],
        agents: [],
        plugins: [],
        core_activation: false,
        files: { "commands/old.md": { sha256: fileHash, mode: 0o644, kind: "command" } },
      })}\n`,
    );
    const plan = await preview("install", "project", project, home);
    assert.equal(
      plan.operations.find((item) => item.path === "commands/old.md").operation,
      "archive-pending",
    );
    await assert.rejects(
      apply("install", "project", plan.digest, project, home, { afterPublish: () => "fail" }),
      (error) => error.code === "rolled_back",
    );
    assert.deepEqual(await readFile(join(project, ".opencode", "commands", "old.md")), content);
    await assert.rejects(lstat(join(archiveRoot("project", project, home), "index.json")), {
      code: "ENOENT",
    });
    const fresh = await preview("install", "project", project, home);
    await apply("install", "project", fresh.digest, project, home);
    await assert.rejects(lstat(join(project, ".opencode", "commands", "old.md")), {
      code: "ENOENT",
    });
    const index = JSON.parse(
      await readFile(join(archiveRoot("project", project, home), "index.json"), "utf8"),
    );
    assert.equal(index.entries[0].digest, fileHash);
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});

test("2.0.0 public surface and CLI contracts exclude retired APIs", () => {
  assert.equal(typeof rootPlugin, "function");
  assert.equal(typeof rulesInjector, "function");
  assert.equal(typeof rtk, "function");
  assert.equal(typeof zedBell, "function");
  const metadata = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
  assert.deepEqual(Object.keys(metadata.exports).sort(), [
    ".",
    "./plugins/rtk",
    "./plugins/rules-injector",
    "./plugins/zed-bell",
  ]);
  const help = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), "--help"], { encoding: "utf8" });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /install.*uninstall.*doctor/s);
  const version = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), "--version"], {
    encoding: "utf8",
  });
  assert.equal(version.status, 0);
  assert.equal(version.stdout.trim(), metadata.version);
});

test("non-TTY install requires explicit complete selection and creates no receipt", async () => {
  const base = mkdtempSync(join(tmpdir(), "skills-opencode-cli-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([mkdir(project), mkdir(home)]);
  try {
    const result = spawnSync(
      process.execPath,
      [
        join(PACKAGE, "dist", "cli.js"),
        "install",
        "--scope",
        "project",
        "--commands",
        "agents-md",
        "--json",
      ],
      {
        cwd: project,
        env: { ...process.env, HOME: home, XDG_STATE_HOME: join(home, ".state") },
        encoding: "utf8",
      },
    );
    assert.equal(result.status, 2);
    assert.equal(JSON.parse(result.stdout).error.code, "invalid_input");
    await assert.rejects(lstat(join(home, ".state")), { code: "ENOENT" });
  } finally {
    rmSync(base, { recursive: true, force: true });
  }
});
