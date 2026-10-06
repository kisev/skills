import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import rootPlugin, { codeSimplify, rulesInjector, rtk, zedBell } from "../dist/index.js";
import { apply, preview } from "../dist/installer.js";
import { archiveRoot } from "../dist/lifecycle.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const OLD_PLUGIN = "plugins/background-attempts.js";
const PACKAGE_METADATA = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
const PACKAGE_VERSION = PACKAGE_METADATA.version;

function hash(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("installer preserves exact selection and keeps core separate from plugins", async () => {
  const base = mkdtempSync(join(tmpdir(), "agentomatic-stage19-"));
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
    await apply("install", "project", project, home, {}, selection);
    const manifest = JSON.parse(
      await readFile(join(project, ".opencode", ".agentomatic-manifest.json"), "utf8"),
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
  const base = mkdtempSync(join(tmpdir(), "agentomatic-archive-"));
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
      package: "@kisev/agentomatic",
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
      join(project, ".opencode", ".agentomatic-manifest.json"),
      `${JSON.stringify(manifest)}\n`,
    );
    const plan = await preview("uninstall", "project", project, home);
    assert.equal(
      plan.operations.find((item) => item.path === OLD_PLUGIN).operation,
      "archive-pending",
    );
    await apply("uninstall", "project", project, home);
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
  const base = mkdtempSync(join(tmpdir(), "agentomatic-stale-"));
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
      join(project, ".opencode", ".agentomatic-manifest.json"),
      `${JSON.stringify({
        schema_version: 2,
        package: "@kisev/agentomatic",
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
      apply("install", "project", project, home, { afterPublish: () => "fail" }),
      (error) => error.code === "rolled_back",
    );
    assert.deepEqual(await readFile(join(project, ".opencode", "commands", "old.md")), content);
    await assert.rejects(lstat(join(archiveRoot("project", project, home), "index.json")), {
      code: "ENOENT",
    });
    await apply("install", "project", project, home);
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

test("upgrade archives the retired memomatic wrapper but preserves user edits", async () => {
  for (const edited of [false, true]) {
    const base = mkdtempSync(join(tmpdir(), "agentomatic-memory-migration-"));
    const project = join(base, "project");
    const home = join(base, "home");
    const deployment = join(project, ".opencode");
    const path = "plugins/memomatic.js";
    const content =
      'import plugin from "@kisev/agentomatic/plugins/memomatic";\n\nexport default (input) => plugin(input);\n';
    const selection = { commands: [], agents: [], plugins: [], core_activation: false };
    try {
      await mkdir(join(deployment, "plugins"), { recursive: true });
      await mkdir(home);
      await writeFile(join(deployment, path), edited ? `${content}// user edit\n` : content);
      await writeFile(
        join(deployment, ".agentomatic-manifest.json"),
        JSON.stringify({
          schema_version: 2,
          package: "@kisev/agentomatic",
          package_version: "11.0.0-dev.62.g445d44a8adf0",
          version: "11.0.0-dev.62.g445d44a8adf0",
          scope: "project",
          commands: [],
          agents: [],
          plugins: ["memomatic"],
          core_activation: false,
          files: { [path]: { sha256: hash(content), mode: 0o644, kind: "plugin" } },
        }),
      );
      const plan = await preview("install", "project", project, home, selection);
      assert.equal(
        plan.operations.find((item) => item.path === path).operation,
        edited ? "conflict" : "archive-pending",
      );
      if (edited) {
        await assert.rejects(apply("install", "project", project, home, {}, selection));
        assert.equal(await readFile(join(deployment, path), "utf8"), `${content}// user edit\n`);
      } else {
        await apply("install", "project", project, home, {}, selection);
        await assert.rejects(lstat(join(deployment, path)), { code: "ENOENT" });
        assert.equal(
          await readFile(
            join(archiveRoot("project", project, home), "objects", hash(content)),
            "utf8",
          ),
          content,
        );
        const manifest = JSON.parse(
          await readFile(join(deployment, ".agentomatic-manifest.json"), "utf8"),
        );
        assert.deepEqual(manifest.plugins, []);
        assert.equal(path in manifest.files, false);
      }
      await assert.rejects(
        preview("install", "project", project, home, { ...selection, plugins: ["memomatic"] }),
        /Unknown plugin selection/,
      );
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  }
});

test("2.0.0 public surface and CLI contracts exclude retired APIs", () => {
  assert.equal("@kisev/memomatic" in PACKAGE_METADATA.dependencies, false);
  assert.equal(rootPlugin.server, undefined);
  assert.equal(typeof rootPlugin.setup, "function");
  assert.equal(typeof rulesInjector, "function");
  assert.equal(typeof rtk, "function");
  assert.equal(typeof zedBell, "function");
  assert.equal(typeof codeSimplify, "function");
  assert.deepEqual(Object.keys(PACKAGE_METADATA.exports).sort(), [
    ".",
    "./plugins/code-simplify",
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

test("common CLI runtime is materialized from one authored source and env cannot confirm mutations", async () => {
  const source = await readFile(
    new URL("../../../shared/references/cli_runtime.ts", import.meta.url),
    "utf8",
  );
  for (const target of [
    "../src/generated/cli.ts",
    "../../../apps/memomatic/src/generated/cli.ts",
    "../../../apps/taskmatic/src/generated/cli.ts",
  ])
    assert.equal(await readFile(new URL(target, import.meta.url), "utf8"), source);
  const root = mkdtempSync(join(tmpdir(), "agentomatic-cli-config-"));
  try {
    const config = join(root, "cli.json");
    await writeFile(config, JSON.stringify({ yes: true, global: true, json: true }));
    const result = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist/cli.js"), "install", "--config", config],
      {
        cwd: root,
        env: {
          ...process.env,
          HOME: root,
          XDG_CONFIG_HOME: join(root, "config"),
          XDG_STATE_HOME: join(root, "state"),
          AGENTOMATIC_YES: "true",
        },
        encoding: "utf8",
      },
    );
    assert.notEqual(result.status, 0);
    await assert.rejects(lstat(join(root, "config/opencode")), { code: "ENOENT" });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("CLI help is structured and explains commands options workflow and scope", () => {
  const help = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), "--help"], {
    encoding: "utf8",
  });
  assert.equal(help.status, 0, help.stderr);
  assert.match(
    help.stdout,
    /Usage:[\s\S]*install[\s\S]*configure[\s\S]*status[\s\S]*doctor[\s\S]*uninstall[\s\S]*Common:[\s\S]*Mutations:/,
  );
  assert.match(help.stdout, /^  install\s{2,}Install components/m);
  assert.match(help.stdout, /^  doctor\s{2,}Diagnose versions, ownership, drift/m);
  assert.doesNotMatch(help.stdout, /agent model-set|agent reconcile|critic remove/);
  for (const option of [
    "--global",
    "--dry-run",
    "--yes",
    "--commands <list|none>",
    "--agents <list|none>",
  ]) {
    assert.ok(help.stdout.includes(option), option);
  }
  assert.match(
    help.stdout,
    /Project scope uses \.opencode under the current directory; run from the project root/,
  );
  assert.match(help.stdout, /--global \(otherwise project\)/);
  assert.doesNotMatch(help.stdout, /--scope/);
  assert.match(help.stdout, /Portable skills use the separate skills CLI/);
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
    [join(PACKAGE, "dist", "cli.js"), "catalog", "--json"],
    { encoding: "utf8" },
  );
  assert.equal(capabilities.status, 0, capabilities.stderr);
  assert.equal(JSON.parse(capabilities.stdout).status, "ok");
});

test("CLI exposes contextual help for every command and group", () => {
  const topics = [
    { args: ["install", "--help"], topic: "install", usage: "agentomatic install" },
    { args: ["uninstall", "--help"], topic: "uninstall", usage: "agentomatic uninstall" },
    { args: ["doctor", "--help"], topic: "doctor", usage: "agentomatic doctor" },
    {
      args: ["catalog", "--help"],
      topic: "catalog",
      usage: "agentomatic catalog",
    },
    {
      args: ["maintenance", "cleanup", "--help"],
      topic: "maintenance cleanup",
      usage: "agentomatic maintenance cleanup",
    },
    { args: ["agent", "--help"], topic: "agent", usage: "agentomatic agent", group: true },
    {
      args: ["agent", "list", "--help"],
      topic: "agent list",
      usage: "agentomatic agent list",
    },
    {
      args: ["configure", "agent", "--help"],
      topic: "configure agent",
      usage: "agentomatic configure agent",
    },
    {
      args: ["configure", "agent", "worker", "--help"],
      topic: "configure agent",
      usage: "agentomatic configure agent",
    },
    {
      args: ["maintenance", "repair", "--help"],
      topic: "maintenance repair",
      usage: "agentomatic maintenance repair",
    },
    {
      args: ["configure", "--help"],
      topic: "configure",
      usage: "agentomatic configure",
      group: true,
    },
  ];
  const outputs = new Map();
  for (const item of topics) {
    const result = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), ...item.args], {
      encoding: "utf8",
    });
    assert.equal(result.status, 0, `${item.topic}: ${result.stderr}`);
    assert.ok(result.stdout.startsWith(`agentomatic ${PACKAGE_VERSION}\n`), item.topic);
    assert.ok(result.stdout.includes(item.usage), item.topic);
    const expectedSections = ["Usage:", "Common:"];
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
    assert.match(result.stdout, /Project scope/);
    assert.doesNotMatch(result.stdout, /Error \[/);
    outputs.set(item.topic, result.stdout);
  }

  assert.match(outputs.get("install"), /--plugins <list\|none>/);
  assert.doesNotMatch(outputs.get("doctor"), /--confirm/);
  assert.match(outputs.get("configure agent"), /--model <value>[\s\S]*--variant <value>/);
  assert.match(outputs.get("agent"), /agent list/);
  assert.doesNotMatch(outputs.get("agent"), /add-critic|agent remove/);
  // Removed mutation commands answer with a one-line pointer to configure agent.
  for (const removed of [
    ["agent", "add-critic"],
    ["agent", "remove", "critic-security"],
  ]) {
    const result = spawnSync("node", [join(PACKAGE, "dist", "cli.js"), ...removed], {
      encoding: "utf8",
    });
    assert.notEqual(result.status, 0, removed.join(" "));
    assert.match(
      result.stderr,
      /Removed command; agentomatic configure agent is the single mutation point/,
      removed.join(" "),
    );
  }
  assert.match(
    outputs.get("configure"),
    /configure components[\s\S]*configure agent[\s\S]*configure critics/,
  );
});

test("non-TTY install requires explicit complete selection and writes no state", async () => {
  const base = mkdtempSync(join(tmpdir(), "agentomatic-cli-"));
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

test("explicit CLI selection replaces retired saved commands without resetting core", async () => {
  for (const core of [false, true]) {
    const base = mkdtempSync(join(tmpdir(), "agentomatic-command-rename-"));
    const project = join(base, "project");
    const home = join(base, "home");
    const deployment = join(project, ".opencode");
    const legacyPath = "commands/stopit.md";
    const legacyContent = "Load skill `stopit`.\n";
    const manifestPath = join(deployment, ".agentomatic-manifest.json");
    try {
      await Promise.all([mkdir(join(deployment, "commands"), { recursive: true }), mkdir(home)]);
      await writeFile(join(deployment, legacyPath), legacyContent);
      const manifest = JSON.stringify({
        schema_version: 2,
        package: "@kisev/agentomatic",
        package_version: PACKAGE_VERSION,
        version: PACKAGE_VERSION,
        scope: "project",
        commands: ["stopit"],
        agents: [],
        plugins: [],
        core_activation: core,
        files: { [legacyPath]: { sha256: hash(legacyContent), mode: 0o644, kind: "command" } },
      });
      await writeFile(manifestPath, manifest);
      const invoke = (commands, action) =>
        spawnSync(
          process.execPath,
          [
            join(PACKAGE, "dist/cli.js"),
            "install",
            "--commands",
            commands,
            "--agents",
            "none",
            "--plugins",
            "none",
            "--no-dependency",
            "--json",
            action,
          ],
          {
            cwd: project,
            env: {
              ...process.env,
              HOME: home,
              XDG_CONFIG_HOME: join(home, "config"),
              XDG_DATA_HOME: join(home, ".local/share"),
              XDG_STATE_HOME: join(home, "state"),
            },
            encoding: "utf8",
          },
        );
      const rejected = invoke("stopit", "--dry-run");
      assert.equal(rejected.status, 2);
      assert.equal(JSON.parse(rejected.stdout).error.code, "invalid_selection");
      const planned = invoke("handoff", "--dry-run");
      assert.equal(planned.status, 0, planned.stdout + planned.stderr);
      const selection = JSON.parse(planned.stdout).plan.selection;
      assert.deepEqual(selection.commands, ["handoff"]);
      assert.equal(selection.core_activation, core);
      assert.equal(await readFile(manifestPath, "utf8"), manifest);
      assert.equal(await readFile(join(deployment, legacyPath), "utf8"), legacyContent);
      const applied = invoke("handoff", "--yes");
      assert.equal(applied.status, 0, applied.stdout + applied.stderr);
      const updated = JSON.parse(await readFile(manifestPath, "utf8"));
      assert.deepEqual(updated.commands, ["handoff"]);
      assert.equal(updated.core_activation, core);
      assert.match(
        await readFile(join(deployment, "commands/handoff.md"), "utf8"),
        /skill `handoff`/,
      );
      await assert.rejects(lstat(join(deployment, legacyPath)), { code: "ENOENT" });
      const archive = JSON.parse(
        await readFile(join(archiveRoot("project", project, home), "index.json"), "utf8"),
      );
      assert.ok(archive.entries.some((entry) => entry.original_hash === hash(legacyContent)));
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  }
});
