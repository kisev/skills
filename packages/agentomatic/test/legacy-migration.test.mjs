import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { migrateLegacyDeploymentNamespace, migrateLegacyNamespaces } from "../dist/lifecycle.js";
import { applyJsoncEdits } from "../dist/jsonc.js";
import { apply, installedSelection, preview } from "../dist/installer.js";

const PACKAGE = join(import.meta.dirname, "..");

function environment() {
  const root = mkdtempSync(join(tmpdir(), "agentomatic-legacy-"));
  const state = join(root, "state");
  const data = join(root, "data");
  const config = join(root, "config");
  mkdirSync(state, { recursive: true });
  mkdirSync(data, { recursive: true });
  mkdirSync(config, { recursive: true });
  process.env.XDG_STATE_HOME = state;
  process.env.XDG_DATA_HOME = data;
  process.env.XDG_CONFIG_HOME = config;
  return { root, state, data, config };
}

test("legacy XDG namespaces move once and stay idempotent", async () => {
  const env = environment();
  try {
    const legacyState = join(env.state, "opencode", "skills-opencode", "global");
    mkdirSync(legacyState, { recursive: true });
    writeFileSync(join(legacyState, "receipt.json"), "pending\n", "utf8");
    const legacyArchive = join(env.data, "opencode", "skills-opencode", "archive", "global");
    mkdirSync(legacyArchive, { recursive: true });
    writeFileSync(join(legacyArchive, "agents.md"), "archived\n", "utf8");

    const moved = await migrateLegacyNamespaces();
    assert.equal(moved.length, 2);
    assert.equal(
      readFileSync(join(env.state, "opencode", "agentomatic", "global", "receipt.json"), "utf8"),
      "pending\n",
    );
    assert.equal(
      readFileSync(
        join(env.data, "opencode", "agentomatic", "archive", "global", "agents.md"),
        "utf8",
      ),
      "archived\n",
    );
    assert.equal(existsSync(join(env.state, "opencode", "skills-opencode")), false);

    const again = await migrateLegacyNamespaces();
    assert.equal(again.length, 0);

    mkdirSync(join(env.state, "opencode", "skills-opencode"), { recursive: true });
    const skipped = await migrateLegacyNamespaces();
    assert.equal(skipped.length, 0);
    assert.equal(existsSync(join(env.state, "opencode", "skills-opencode")), true);
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("legacy semantic deployment directory moves once", async () => {
  const env = environment();
  try {
    const deployment = join(env.config, "opencode");
    const legacy = join(deployment, ".skills-opencode");
    mkdirSync(legacy, { recursive: true });
    writeFileSync(join(legacy, "agent-profiles.json"), "{}\n", "utf8");

    assert.equal(await migrateLegacyDeploymentNamespace(deployment), true);
    assert.equal(
      readFileSync(join(deployment, ".agentomatic", "agent-profiles.json"), "utf8"),
      "{}\n",
    );
    assert.equal(existsSync(legacy), false);
    assert.equal(await migrateLegacyDeploymentNamespace(deployment), false);
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("applying an upgrade migrates legacy namespaces before installing", () => {
  const env = environment();
  try {
    const project = join(env.root, "project");
    mkdirSync(project, { recursive: true });
    writeFileSync(join(project, "package.json"), '{"private":true}\n', "utf8");
    const legacyState = join(env.state, "opencode", "skills-opencode", "global");
    mkdirSync(legacyState, { recursive: true });
    writeFileSync(join(legacyState, "journal.json"), "pending\n", "utf8");
    for (const directory of [
      join(env.state, "opencode"),
      join(env.state, "opencode", "skills-opencode"),
      legacyState,
    ])
      chmodSync(directory, 0o700);
    const legacySemantic = join(env.root, "home", ".config", "opencode", ".skills-opencode");
    mkdirSync(legacySemantic, { recursive: true });
    const semanticConfig = join(legacySemantic, "agent-profiles.json");
    writeFileSync(
      semanticConfig,
      `${JSON.stringify(
        {
          schema_version: 1,
          fixed: Object.fromEntries(
            ["manager", "architect", "mapper", "worker", "review", "critic"].map((role) => [
              role,
              {},
            ]),
          ),
          additional_critics: {},
        },
        null,
        2,
      )}\n`,
      "utf8",
    );
    chmodSync(semanticConfig, 0o600);

    const environment_variables = {
      ...process.env,
      HOME: join(env.root, "home"),
    };
    const cli = (arguments_) =>
      spawnSync(process.execPath, [join(PACKAGE, "dist", "cli.js"), ...arguments_], {
        cwd: project,
        env: environment_variables,
        encoding: "utf8",
      });
    const selection = [
      "--commands",
      "agents-md",
      "--plugins",
      "none",
      "--no-dependency",
      "--global",
      "--json",
    ];
    JSON.parse(cli(["install", ...selection, "--dry-run"]).stdout);
    const applied = JSON.parse(cli(["install", ...selection, "--yes"]).stdout);
    assert.equal(applied.applied, true);
    assert.equal(
      readFileSync(join(env.state, "opencode", "agentomatic", "global", "journal.json"), "utf8"),
      "pending\n",
    );
    assert.equal(
      existsSync(join(env.root, "home", ".config", "opencode", ".skills-opencode")),
      false,
    );
    assert.equal(existsSync(join(env.root, "home", ".config", "opencode", ".agentomatic")), true);
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("core-plugin fragment replaces the legacy package entry in place", () => {
  const text = ["{", '  "plugin": ["@kisev/skills-opencode", "user-plugin"]', "}"].join("\n");
  const applied = applyJsoncEdits(text, [
    {
      kind: "replace-array-value",
      path: ["plugin"],
      from: "@kisev/skills-opencode",
      to: "@kisev/agentomatic",
    },
    { kind: "append-unique", path: ["plugin"], value: "@kisev/agentomatic" },
  ]);
  assert.equal(applied.results[0], "replaced");
  assert.equal(applied.results[1], "present");
  assert.deepEqual(JSON.parse(applied.text).plugin, ["@kisev/agentomatic", "user-plugin"]);
});

test("replace-array-value keeps clean configurations untouched", () => {
  const applied = applyJsoncEdits('{"plugin": ["user-plugin"]}\n', [
    {
      kind: "replace-array-value",
      path: ["plugin"],
      from: "@kisev/skills-opencode",
      to: "@kisev/agentomatic",
    },
  ]);
  assert.equal(applied.results[0], "present");
  assert.deepEqual(JSON.parse(applied.text).plugin, ["user-plugin"]);
});

test("install migrates a legacy-named ownership manifest in one transaction", async () => {
  const root = mkdtempSync(join(tmpdir(), "agentomatic-legacy-upgrade-"));
  try {
    const home = join(root, "home");
    const config = join(home, ".config", "opencode");
    mkdirSync(join(config, "commands"), { recursive: true });
    mkdirSync(join(config, "plugins"), { recursive: true });
    const hash = (value) => createHash("sha256").update(value).digest("hex");
    const files = {};
    for (const name of ["agents-md", "askme"]) {
      const content = `legacy ${name}\n`;
      writeFileSync(join(config, "commands", `${name}.md`), content);
      files[`commands/${name}.md`] = { sha256: hash(content), mode: 0o644, kind: "command" };
    }
    const rtk = "legacy rtk\n";
    writeFileSync(join(config, "plugins", "rtk.js"), rtk);
    files["plugins/rtk.js"] = { sha256: hash(rtk), mode: 0o644, kind: "plugin" };
    writeFileSync(
      join(config, ".skills-opencode-manifest.json"),
      `${JSON.stringify({
        schema_version: 2,
        package: "@kisev/skills-opencode",
        package_version: "3.0.0",
        version: "3.0.0",
        scope: "global",
        commands: ["agents-md", "askme"],
        agents: [],
        plugins: ["rtk"],
        core_activation: false,
        files,
      })}\n`,
      { mode: 0o600 },
    );
    const selection = { commands: ["agents-md", "askme"], agents: [], plugins: ["rtk"] };
    const plan = await preview("install", "global", root, home, selection, false);
    assert.ok(plan.operations.some((item) => item.path === ".agentomatic-manifest.json"));
    await apply("install", "global", root, home, {}, selection, false);
    const migrated = JSON.parse(readFileSync(join(config, ".agentomatic-manifest.json"), "utf8"));
    assert.equal(migrated.package, "@kisev/agentomatic");
    assert.equal(existsSync(join(config, ".skills-opencode-manifest.json")), false);
    assert.match(
      readFileSync(join(config, "commands", "agents-md.md"), "utf8"),
      /native Skill tool/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("saved legacy selection migrates renamed commands instead of failing install", async () => {
  const root = mkdtempSync(join(tmpdir(), "agentomatic-legacy-selection-"));
  try {
    const home = join(root, "home");
    const project = join(root, "project");
    const deployment = join(home, ".config", "opencode");
    mkdirSync(join(deployment, "commands"), { recursive: true });
    mkdirSync(project, { recursive: true });
    const hash = (value) => createHash("sha256").update(value).digest("hex");
    const files = {};
    for (const name of ["stopit", "skill-improver"]) {
      const content = `legacy ${name}\n`;
      writeFileSync(join(deployment, "commands", `${name}.md`), content);
      files[`commands/${name}.md`] = { sha256: hash(content), mode: 0o644, kind: "command" };
    }
    const manifest = {
      schema_version: 2,
      package: "@kisev/agentomatic",
      package_version: "11.0.2",
      version: "11.0.2",
      scope: "global",
      commands: ["stopit", "skill-improver"],
      agents: [],
      plugins: [],
      core_activation: false,
      files,
    };
    writeFileSync(join(deployment, ".agentomatic-manifest.json"), `${JSON.stringify(manifest)}\n`, {
      mode: 0o600,
    });
    const saved = await installedSelection("global", project, home);
    assert.deepEqual(saved, {
      commands: ["handoff", "skill-doctor"],
      agents: [],
      plugins: [],
      core_activation: false,
    });

    const cli = (arguments_) =>
      spawnSync(process.execPath, [join(PACKAGE, "dist", "cli.js"), ...arguments_], {
        cwd: project,
        env: { ...process.env, HOME: home },
        encoding: "utf8",
      });
    const applied = cli(["install", "--global", "--no-dependency", "--yes", "--json"]);
    assert.equal(applied.status, 0, applied.stdout + applied.stderr);
    assert.equal(JSON.parse(applied.stdout).plan.selection.commands.length, 2);
    const updated = JSON.parse(
      readFileSync(join(deployment, ".agentomatic-manifest.json"), "utf8"),
    );
    assert.deepEqual(updated.commands, ["handoff", "skill-doctor"]);
    assert.equal(existsSync(join(deployment, "commands", "stopit.md")), false);
    assert.equal(existsSync(join(deployment, "commands", "skill-improver.md")), false);
    assert.match(readFileSync(join(deployment, "commands", "handoff.md"), "utf8"), /handoff/);
    const status = cli(["status", "--global", "--json"]);
    assert.equal(status.status, 0, status.stdout + status.stderr);
    assert.deepEqual(JSON.parse(status.stdout).selection.commands, ["handoff", "skill-doctor"]);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
