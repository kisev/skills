import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import {
  applyConfigSetup,
  ConfigSetupError,
  defaultConfigSelection,
  normalizeConfigSelection,
  previewConfigSetup,
} from "../dist/config-setup.js";
import { applyJsoncEdits, JsoncError, parseJsonc } from "../dist/jsonc.js";

const PACKAGE = resolve(import.meta.dirname, "..");

function temporary() {
  return mkdtempSync(join(tmpdir(), "skills-config-setup-test-"));
}

async function homeWithConfigs(directory) {
  const root = join(directory, "home");
  await mkdir(join(root, ".config", "opencode"), { recursive: true });
  await mkdir(join(root, ".config", "kilo"), { recursive: true });
  await mkdir(join(root, ".config", "mimocode"), { recursive: true });
  return root;
}

const FULL_SELECTION = {
  targets: ["opencode", "kilo", "mimo"],
  fragments: [
    "core-plugin",
    "skills-state-permissions",
    "lsp-preset",
    "secrets-guard",
    "kilo-display",
    "tui-schema",
  ],
};

test("jsonc editor appends unique values while preserving comments and formatting", () => {
  const text = [
    "{",
    "  // user plugins",
    '  "plugin": [',
    '    "user-plugin", // keep me',
    "  ],",
    "}",
  ].join("\n");
  const applied = applyJsoncEdits(text, [
    { kind: "append-unique", path: ["plugin"], value: "@kisev/agentomatic" },
    { kind: "append-unique", path: ["plugin"], value: "@kisev/agentomatic" },
  ]);
  assert.equal(applied.results[0], "appended");
  assert.equal(applied.results[1], "present");
  assert.match(applied.text, /"user-plugin", "@kisev\/agentomatic"/);
  assert.match(applied.text, /\/\/ keep me/);
  assert.deepEqual(parseJsonc(applied.text).plugin, ["user-plugin", "@kisev/agentomatic"]);
});

test("jsonc editor creates nested objects, empty arrays, and keeps existing entries", () => {
  const text = '{\n  "model": "openai/gpt-5",\n}\n';
  const applied = applyJsoncEdits(text, [
    { kind: "set-if-absent", path: ["plugin"], value: [] },
    { kind: "append-unique", path: ["plugin"], value: "@kisev/agentomatic" },
    { kind: "set-if-absent", path: ["permission", "read"], value: { "~/*": "allow" } },
    { kind: "set-if-absent", path: ["model"], value: "anthropic/claude" },
  ]);
  assert.equal(applied.results[0], "created");
  assert.equal(applied.results[3], "present");
  const value = parseJsonc(applied.text);
  assert.equal(value.model, "openai/gpt-5");
  assert.deepEqual(value.plugin, ["@kisev/agentomatic"]);
  assert.deepEqual(value.permission.read, { "~/*": "allow" });
});

test("jsonc editor widens scalar permission maps and keeps the scalar as the wildcard", () => {
  const text =
    '{\n  "permission": {\n    "edit": "ask",\n    "external_directory": "ask"\n  }\n}\n';
  const applied = applyJsoncEdits(text, [
    {
      kind: "widen-scalar-map",
      path: ["permission", "edit"],
      entries: { "~/.local/state/agent-skills/**": "allow" },
    },
    {
      kind: "widen-scalar-map",
      path: ["permission", "external_directory"],
      entries: { "~/.local/state/agent-skills/**": "allow" },
    },
  ]);
  assert.deepEqual(applied.results, ["widened", "widened"]);
  const value = parseJsonc(applied.text);
  assert.deepEqual(value.permission.edit, {
    "*": "ask",
    "~/.local/state/agent-skills/**": "allow",
  });
  assert.deepEqual(value.permission.external_directory, {
    "*": "ask",
    "~/.local/state/agent-skills/**": "allow",
  });
});

test("jsonc editor rejects invalid documents and conflicting shapes", () => {
  assert.throws(() => parseJsonc("{ not json"), JsoncError);
  assert.throws(
    () =>
      applyJsoncEdits('{"plugin": "x"}', [{ kind: "append-unique", path: ["plugin"], value: "y" }]),
    JsoncError,
  );
  assert.throws(
    () =>
      applyJsoncEdits('{"model": "openai/gpt-5"}', [
        { kind: "set-if-absent", path: ["model", "temperature"], value: 0.2 },
      ]),
    JsoncError,
  );
});

test("config setup applies all fragments globally and stays idempotent", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  try {
    const preview = await previewConfigSetup(FULL_SELECTION, "global", directory, root);
    assert.equal(preview.confirmable, true);
    assert.equal(preview.requires_restart, true);
    const applied = await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
    });
    assert.deepEqual(
      applied.operations.filter((item) => item.operation === "conflict"),
      [],
    );

    const opencode = parseJsonc(
      readFileSync(join(root, ".config", "opencode", "opencode.jsonc"), "utf8"),
    );
    assert.deepEqual(opencode.plugin, ["@kisev/agentomatic"]);
    assert.equal(opencode.permission.read["~/.local/state/agent-skills/**"], "allow");
    assert.equal(opencode.permission.read["~/.config/opencode/skills/**"], "allow");
    assert.equal(opencode.permission.edit["~/.local/state/agent-skills/**"], "allow");
    assert.equal(opencode.permission.read["**/.env"], "deny");
    assert.equal(opencode.permission.edit["**/.ssh/**"], "deny");
    assert.equal(opencode.permission.external_directory["~/.local/state/agent-skills/**"], "allow");
    assert.deepEqual(opencode.lsp.python.command, ["basedpyright-langserver", "--stdio"]);
    assert.deepEqual(opencode.lsp.typescript.extensions, [".ts", ".tsx", ".js", ".jsx"]);

    const tui = parseJsonc(readFileSync(join(root, ".config", "opencode", "tui.json"), "utf8"));
    assert.equal(tui.$schema, "https://opencode.ai/tui.json");
    assert.equal(tui.diff_style, "stacked");

    const kilo = parseJsonc(readFileSync(join(root, ".config", "kilo", "kilo.jsonc"), "utf8"));
    assert.equal(kilo.reasoning_display, "expanded");
    assert.equal(kilo.permission.read["~/.local/state/agent-skills/**"], "allow");

    const mimo = parseJsonc(
      readFileSync(join(root, ".config", "mimocode", "mimocode.jsonc"), "utf8"),
    );
    assert.equal(mimo.permission.read["**/.env"], "deny");

    const second = await previewConfigSetup(FULL_SELECTION, "global", directory, root);
    assert.equal(second.confirmable, false);
    assert.ok(second.operations.every((item) => item.operation === "unchanged"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("config setup preserves user entries, comments, and scalar permissions", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  try {
    await writeFile(
      join(root, ".config", "opencode", "opencode.jsonc"),
      [
        "{",
        "  // model choice stays",
        '  "model": "openai/gpt-5.6-luna",',
        '  "plugin": ["user-plugin"],',
        '  "lsp": {',
        '    "python": { "command": ["pyright-langserver", "--stdio"] }',
        "  },",
        "}",
      ].join("\n"),
      "utf8",
    );
    await writeFile(
      join(root, ".config", "kilo", "kilo.jsonc"),
      [
        "{",
        '  "permission": { "edit": "ask", "external_directory": "ask" },',
        '  "reasoning_display": "collapsed",',
        "}",
      ].join("\n"),
      "utf8",
    );
    await writeFile(
      join(root, ".config", "opencode", "tui.json"),
      ["{", '  "theme": "user-theme",', '  "keybinds": { "app_exit": "ctrl+q" }', "}"].join("\n"),
      "utf8",
    );
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
    const applied = await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
    });
    assert.equal(applied.operations.filter((item) => item.operation === "conflict").length, 0);
    const preservedTui = parseJsonc(
      readFileSync(join(root, ".config", "opencode", "tui.json"), "utf8"),
    );
    assert.equal(preservedTui.theme, "user-theme");
    assert.equal(preservedTui.keybinds.app_exit, "ctrl+q");
    assert.equal(preservedTui.keybinds.command_list, "alt+p");

    const raw = readFileSync(join(root, ".config", "opencode", "opencode.jsonc"), "utf8");
    assert.match(raw, /\/\/ model choice stays/);
    const opencode = parseJsonc(raw);
    assert.equal(opencode.model, "openai/gpt-5.6-luna");
    assert.deepEqual(opencode.plugin, ["user-plugin", "@kisev/agentomatic"]);
    assert.deepEqual(opencode.lsp.python.command, ["pyright-langserver", "--stdio"]);
    assert.equal(opencode.lsp.python.extensions, undefined);

    const kilo = parseJsonc(readFileSync(join(root, ".config", "kilo", "kilo.jsonc"), "utf8"));
    assert.equal(kilo.reasoning_display, "collapsed");
    assert.equal(kilo.permission.edit["*"], "ask");
    assert.equal(kilo.permission.external_directory["*"], "ask");
    assert.equal(kilo.permission.edit["~/.local/state/agent-skills/**"], "allow");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("config setup selection validation and project scope behavior", async () => {
  assert.throws(
    () => normalizeConfigSelection("global", { targets: ["nope"], fragments: [] }),
    ConfigSetupError,
  );
  assert.throws(
    () => normalizeConfigSelection("global", { targets: ["opencode"], fragments: ["nope"] }),
    ConfigSetupError,
  );
  assert.throws(
    () => normalizeConfigSelection("project", { targets: ["kilo"], fragments: [] }),
    ConfigSetupError,
  );

  const directory = temporary();
  const project = join(directory, "project");
  const root = await homeWithConfigs(directory);
  try {
    await mkdir(project, { recursive: true });
    const selection = normalizeConfigSelection("project", {
      targets: ["opencode"],
      fragments: ["core-plugin", "kilo-display"],
    });
    const preview = await previewConfigSetup(selection, "project", project, root);
    assert.equal(preview.targets.length, 1);
    assert.equal(preview.targets[0].target, "opencode");
    assert.equal(preview.targets[0].path, join(project, "opencode.jsonc"));
    assert.ok(preview.skipped_fragments.some((item) => item.fragment === "kilo-display"));

    const bare = await defaultConfigSelection("global", directory, root);
    assert.deepEqual(bare.targets, ["opencode"]);
    await writeFile(join(root, ".config", "opencode", "tui.json"), "{}\n", "utf8");
    await writeFile(join(root, ".config", "kilo", "kilo.jsonc"), "{}\n", "utf8");
    await writeFile(join(root, ".config", "mimocode", "mimocode.jsonc"), "{}\n", "utf8");
    const configured = await defaultConfigSelection("global", directory, root);
    assert.deepEqual(configured.targets, ["opencode", "kilo", "mimo"]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("cli exposes the config command and install hints at it", () => {
  const help = spawnSync(process.execPath, [join(PACKAGE, "dist", "cli.js"), "config", "--help"], {
    encoding: "utf8",
  });
  assert.equal(help.status, 0);
  assert.match(help.stdout, /Connect the package and recommended fragments/);
  assert.match(help.stdout, /--targets/);
  assert.match(help.stdout, /--fragments/);

  const source = readFileSync(join(PACKAGE, "src", "cli.ts"), "utf8");
  assert.match(source, /"config", \.\.\.scopeArguments\(options\.scope\), "--dry-run"/);
});

test("applying the core-plugin fragment provisions the npm dependency", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  const calls = [];
  try {
    const applied = await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async (command, args, options) => {
        calls.push({ command, args, options });
        return { stdout: "", stderr: "" };
      },
    });
    assert.equal(applied.confirmable, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].command, "npm");
    assert.equal(calls[0].args[0], "install");
    assert.ok(calls[0].args[2].startsWith("@kisev/agentomatic@"));
    assert.equal(calls[0].options.cwd, join(root, ".config", "opencode"));
    const pinned = JSON.parse(
      readFileSync(join(root, ".config", "opencode", "package.json"), "utf8"),
    );
    assert.equal(pinned.private, true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("an unchanged config rerun still heals the plugin dependency", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  const calls = [];
  const runner = async (command, args, options) => {
    calls.push({ command, args, options });
    return { stdout: "", stderr: "" };
  };
  try {
    await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: runner,
    });
    const before = calls.length;
    const healed = await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: runner,
    });
    assert.equal(healed.confirmable, false);
    assert.equal(calls.length, before + 1);
    assert.equal(calls[calls.length - 1].args[0], "install");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("config apply archives the previous user configuration content", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  const configPath = join(root, ".config", "opencode", "opencode.jsonc");
  const original = `${JSON.stringify({ model: "user/model" }, null, 2)}\n`;
  await writeFile(configPath, original);
  try {
    await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
    });
    const archive = join(root, ".local", "share", "opencode", "agentomatic", "archive", "global");
    const index = JSON.parse(readFileSync(join(archive, "index.json"), "utf8"));
    const entry = index.entries.find(
      (item) => item.kind === "config-backup" && item.original_path === configPath,
    );
    assert.ok(entry, `backup entry for ${configPath}`);
    assert.equal(readFileSync(join(archive, "objects", entry.digest), "utf8"), original);

    const evolved = `${JSON.stringify({ model: "user/model-2" }, null, 2)}\n`;
    await writeFile(configPath, evolved);
    await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
    });
    const second = JSON.parse(readFileSync(join(archive, "index.json"), "utf8"));
    assert.equal(
      second.entries.filter(
        (item) => item.kind === "config-backup" && item.original_path === configPath,
      ).length,
      2,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
