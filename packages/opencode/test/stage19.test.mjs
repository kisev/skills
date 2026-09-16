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
const PACKAGE_METADATA = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
const PACKAGE_VERSION = PACKAGE_METADATA.version;
const PACKAGE_SPEC = `@kisev/skills-opencode@${PACKAGE_VERSION}`;
const SKILLS_INSTALLER_SPEC = `skills@${PACKAGE_METADATA.skillsInstallerVersion}`;

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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
  assert.deepEqual(Object.keys(PACKAGE_METADATA.exports).sort(), [
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
  assert.equal(version.stdout.trim(), PACKAGE_VERSION);
});

test("CLI help is structured and explains commands options workflow and scope", () => {
  const help = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), "--help"], {
    encoding: "utf8",
  });
  assert.equal(help.status, 0, help.stderr);
  assert.match(
    help.stdout,
    /Usage:[\s\S]*Commands:[\s\S]*Common options:[\s\S]*Install selection:[\s\S]*Agent model options:[\s\S]*Safe mutation workflow:[\s\S]*Scope behavior:[\s\S]*Examples:[\s\S]*Documentation:/,
  );
  assert.match(help.stdout, /^  install\s{2,}Select and deploy package-owned commands/m);
  assert.match(help.stdout, /^  doctor\s{2,}Inspect versions, ownership, drift/m);
  assert.match(help.stdout, /^  agent configure\s{2,}Choose an agent model interactively/m);
  assert.match(help.stdout, /^  critic remove\s{2,}Remove a package-managed additional critic/m);
  for (const option of [
    "--global",
    "--dry-run",
    "--confirm <digest>",
    "--commands <list|none>",
    "--model <id>",
  ]) {
    assert.ok(help.stdout.includes(option), option);
  }
  assert.match(
    help.stdout,
    /^  default\s{2,}Targets \.opencode under the current directory; run from the project root/m,
  );
  assert.match(help.stdout, /^  --global\s{2,}Targets ~\/\.config\/opencode/m);
  assert.doesNotMatch(help.stdout, /--scope/);
  assert.match(
    help.stdout,
    new RegExp(`npx --yes ${escapeRegExp(PACKAGE_SPEC)} install --global --dry-run`),
  );
  assert.ok(
    help.stdout.includes(
      `Portable Agent Skills are installed separately with npx --yes ${SKILLS_INSTALLER_SPEC}.`,
    ),
  );
  assert.doesNotMatch(help.stdout, /Commands: install, uninstall/);
});

test("CLI rejects removed scope syntax and irrelevant command options", () => {
  for (const arguments_ of [
    ["doctor", "--scope", "project"],
    ["doctor", "--scope", "project", "--help"],
    ["doctor", "--scope=project", "--version"],
    ["doctor", "--global", "--global"],
    ["doctor", "--global", "--global", "--help"],
    ["doctor", "--dry-run"],
    ["doctor", "--dry-run", "--help"],
    ["capabilities", "--global"],
    ["capabilities", "--global", "--help"],
    ["capabilities", "--dry-run"],
    ["capabilities", "--dry-run", "--version"],
    ["capabilities", "unexpected"],
    ["reconcile", "--model", "x/y"],
    ["uninstall", "--commands", "none"],
    ["agent", "list", "--dry-run"],
    ["agent", "configure", "manager", "--commands", "none"],
    ["agent", "model-set", "manager", "--commands", "none"],
    ["agent", "reconcile", "--model", "x/y"],
    ["critic", "add", "security", "--clear-variant"],
    ["critic", "remove", "security", "--model", "x/y"],
    ["agent", "nonsense", "--version"],
    ["unknown", "--help"],
  ]) {
    const result = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist", "cli.js"), ...arguments_, "--json"],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 2, `${arguments_.join(" ")}\n${result.stdout}\n${result.stderr}`);
    assert.equal(JSON.parse(result.stdout).error.code, "invalid_input");
  }
  const capabilities = spawnSync(
    process.execPath,
    [join(PACKAGE, "dist", "cli.js"), "capabilities", "--json"],
    { encoding: "utf8" },
  );
  assert.equal(capabilities.status, 0, capabilities.stderr);
  assert.equal(JSON.parse(capabilities.stdout).status, "ok");
});

test("CLI exposes contextual help for every command and group", () => {
  const topics = [
    { args: ["install", "--help"], topic: "install", usage: "skills-opencode install" },
    { args: ["uninstall", "--help"], topic: "uninstall", usage: "skills-opencode uninstall" },
    { args: ["doctor", "--help"], topic: "doctor", usage: "skills-opencode doctor" },
    {
      args: ["capabilities", "--help"],
      topic: "capabilities",
      usage: "skills-opencode capabilities",
    },
    { args: ["reconcile", "--help"], topic: "reconcile", usage: "skills-opencode reconcile" },
    { args: ["agent", "--help"], topic: "agent", usage: "skills-opencode agent", group: true },
    {
      args: ["agent", "list", "--help"],
      topic: "agent list",
      usage: "skills-opencode agent list",
    },
    {
      args: ["agent", "configure", "--help"],
      topic: "agent configure",
      usage: "skills-opencode agent configure",
    },
    {
      args: ["agent", "model-set", "worker", "--help"],
      topic: "agent model-set",
      usage: "skills-opencode agent model-set",
    },
    {
      args: ["agent", "reconcile", "--help"],
      topic: "agent reconcile",
      usage: "skills-opencode agent reconcile",
    },
    { args: ["critic", "--help"], topic: "critic", usage: "skills-opencode critic", group: true },
    {
      args: ["critic", "add", "security", "--help"],
      topic: "critic add",
      usage: "skills-opencode critic add",
    },
    {
      args: ["critic", "remove", "security", "--help"],
      topic: "critic remove",
      usage: "skills-opencode critic remove",
    },
  ];
  const outputs = new Map();
  for (const item of topics) {
    const result = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), ...item.args], {
      encoding: "utf8",
    });
    assert.equal(result.status, 0, `${item.topic}: ${result.stderr}`);
    assert.ok(
      result.stdout.startsWith(`skills-opencode ${PACKAGE_VERSION} - ${item.topic}\n`),
      item.topic,
    );
    assert.ok(result.stdout.includes(item.usage), item.topic);
    const expectedSections = item.group
      ? ["Usage:", "Commands:", "Behavior:", "Examples:"]
      : ["Usage:", "Options:", "Behavior:", "Examples:"];
    const positions = expectedSections.map((section) => result.stdout.indexOf(section));
    assert.ok(
      positions.every((position) => position >= 0),
      item.topic,
    );
    assert.deepEqual(
      positions,
      [...positions].sort((left, right) => left - right),
      item.topic,
    );
    assert.match(result.stdout, new RegExp(`npx --yes ${escapeRegExp(PACKAGE_SPEC)}`));
    assert.doesNotMatch(result.stdout, /Error \[/);
    outputs.set(item.topic, result.stdout);
  }

  assert.match(outputs.get("install"), /--plugins <list\|none>/);
  assert.doesNotMatch(outputs.get("doctor"), /--confirm/);
  assert.match(outputs.get("agent model-set"), /--model <id>[\s\S]*--variant <id>/);
  assert.match(outputs.get("agent"), /^  list\s{2,}[\s\S]*^  reconcile\s{2,}/m);
  assert.match(outputs.get("critic"), /^  add\s{2,}[\s\S]*^  remove\s{2,}/m);
});

test("non-TTY install requires explicit complete selection and creates no receipt", async () => {
  const base = mkdtempSync(join(tmpdir(), "skills-opencode-cli-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([mkdir(project), mkdir(home)]);
  try {
    const result = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist", "cli.js"), "install", "--commands", "agents-md", "--json"],
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
