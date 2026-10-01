import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import {
  applyConfigSetup,
  ConfigSetupError,
  defaultConfigSelection,
  normalizeConfigSelection,
  previewConfigSetup,
  recoverConfigSetup,
} from "../dist/config-setup.js";
import { applyJsoncEdits, JsoncError, parseJsonc } from "../dist/jsonc.js";
import { corePluginEdits, permissionEdits } from "../dist/opencode-config.js";
import { requirePackageVersion } from "../dist/package-metadata.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const PINNED = `@kisev/agentomatic@${requirePackageVersion()}`;

test("interrupted config recovery is read-only until its exact journal is confirmed", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  try {
    const { applyTransaction, deploymentRoot, lifecycleRoot, sha256 } =
      await import("../dist/lifecycle.js");
    const root = deploymentRoot("global", directory, home);
    const state = lifecycleRoot("global", directory, home);
    const file = join(home, ".config", "opencode", "opencode.jsonc");
    const original = Buffer.from('{"model":"original"}\n');
    await writeFile(file, original);
    await assert.rejects(
      applyTransaction(
        root,
        state,
        [
          {
            path: "opencode.jsonc",
            operation: "write",
            content: Buffer.from('{"model":"interrupted"}\n'),
            mode: 0o644,
            expected: { sha256: sha256(original) },
          },
        ],
        { afterPublish: () => "interrupt" },
      ),
      { code: "test_interruption" },
    );
    const preview = await recoverConfigSetup("global", true, directory, home);
    assert.ok(preview.paths.includes(file));
    assert.match(readFileSync(file, "utf8"), /interrupted/);
    await assert.rejects(recoverConfigSetup("global", false, directory, home, "changed"), {
      code: "stale_receipt",
    });
    assert.match(readFileSync(file, "utf8"), /interrupted/);
    const result = await recoverConfigSetup("global", false, directory, home, preview.digest);
    assert.equal(result.recovered, true);
    assert.deepEqual(readFileSync(file), original);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

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
    "secrets-guard",
    "kilo-display",
    "tui-schema",
  ],
};

function assertRule(config, action, resource, effect) {
  assert.deepEqual(
    config.permissions.findLast((rule) => rule.action === action && rule.resource === resource),
    { action, resource, effect },
  );
}

test("core-plugin setup preserves V2 plugins and does not create a legacy array", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  const file = join(home, ".config/opencode/opencode.jsonc");
  try {
    await writeFile(
      file,
      '{\n  // V2 plugins\n  "plugins": ["user-plugin", "@kisev/skills-opencode"]\n}\n',
    );
    const selection = { targets: ["opencode"], fragments: ["core-plugin"] };
    const setup = await previewConfigSetup(selection, "global", directory, home);
    await applyConfigSetup(selection, "global", directory, home, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
      receipt: setup.receipt,
    });
    const source = readFileSync(file, "utf8");
    const config = parseJsonc(source);
    assert.deepEqual(config.plugins, ["user-plugin", PINNED]);
    assert.equal(config.plugin, undefined);
    assert.match(source, /\/\/ V2 plugins/);
    const preview = await previewConfigSetup(selection, "global", directory, home);
    assert.ok(preview.operations.every((operation) => operation.operation === "unchanged"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("core-plugin setup repins a bare or stale registration instead of resolving latest", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  const file = join(home, ".config/opencode/opencode.jsonc");
  try {
    await writeFile(
      file,
      JSON.stringify(
        {
          plugins: [
            "@kisev/agentomatic",
            "@kisev/agentomatic@0.0.1-dev.0.g000000000000",
            "user-plugin",
          ],
        },
        null,
        2,
      ) + "\n",
    );
    const selection = { targets: ["opencode"], fragments: ["core-plugin"] };
    const setup = await previewConfigSetup(selection, "global", directory, home);
    await applyConfigSetup(selection, "global", directory, home, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
      receipt: setup.receipt,
    });
    assert.deepEqual(parseJsonc(readFileSync(file, "utf8")).plugins, [PINNED, "user-plugin"]);
    const again = await previewConfigSetup(selection, "global", directory, home);
    assert.ok(again.operations.every((operation) => operation.operation === "unchanged"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

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
    assert.deepEqual(opencode.plugins, [PINNED]);
    assert.equal(opencode.permission, undefined);
    assertRule(opencode, "read", "~/.local/state/agent-skills/**", "allow");
    assertRule(opencode, "read", "~/.config/opencode/skills/**", "allow");
    assertRule(opencode, "read", "~/.agents/skills/**", "allow");
    assertRule(opencode, "edit", "~/.local/state/agent-skills/**", "allow");
    assertRule(opencode, "read", "*.env", "deny");
    assertRule(opencode, "edit", "*.ssh/**", "deny");
    assertRule(opencode, "external_directory", "~/.local/state/agent-skills/**", "allow");
    assertRule(opencode, "external_directory", "~/.agents/skills/**", "allow");
    assertRule(opencode, "external_directory", "~/.agents", "allow");
    assertRule(opencode, "external_directory", "~/.agents/skills", "allow");
    assertRule(opencode, "external_directory", "~/.config/opencode/skills", "allow");
    assertRule(opencode, "external_directory", "~/.local/state/agent-skills", "allow");
    assert.equal(opencode.lsp, undefined);

    const cli = parseJsonc(readFileSync(join(root, ".config", "opencode", "cli.json"), "utf8"));
    assert.equal(cli.$schema, "https://opencode.ai/v2/cli.json");
    assert.deepEqual(cli.theme, { name: "ayu" });
    assert.equal(cli.diff_style, undefined);
    assert.equal(cli.keybinds["command.palette.show"], "alt+p");

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
      join(root, ".config", "opencode", "cli.json"),
      [
        "{",
        '  "theme": { "name": "user-theme" },',
        '  "keybinds": { "app.exit": "ctrl+q" }',
        "}",
      ].join("\n"),
      "utf8",
    );
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
    const applied = await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: async () => ({ stdout: "", stderr: "" }),
    });
    assert.equal(applied.operations.filter((item) => item.operation === "conflict").length, 0);
    const preservedTui = parseJsonc(
      readFileSync(join(root, ".config", "opencode", "cli.json"), "utf8"),
    );
    assert.equal(preservedTui.theme.name, "user-theme");
    assert.equal(preservedTui.keybinds["app.exit"], "ctrl+q");
    assert.equal(preservedTui.keybinds["command.palette.show"], "alt+p");

    const raw = readFileSync(join(root, ".config", "opencode", "opencode.jsonc"), "utf8");
    assert.match(raw, /\/\/ model choice stays/);
    const opencode = parseJsonc(raw);
    assert.equal(opencode.model, "openai/gpt-5.6-luna");
    assert.deepEqual(opencode.plugins, ["user-plugin", PINNED]);
    assert.equal(opencode.plugin, undefined);
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

test("config --no-dependency applies the core fragment without provisioning npm", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  const project = join(directory, "project");
  const manifest = join(home, ".config", "opencode", "package.json");
  try {
    await mkdir(project);
    await writeFile(manifest, '{"name":"opencode","private":true}\n');
    const result = spawnSync(
      process.execPath,
      [
        join(PACKAGE, "dist", "cli.js"),
        "config",
        "--global",
        "--targets",
        "opencode",
        "--fragments",
        "core-plugin",
        "--no-dependency",
        "--yes",
      ],
      { cwd: project, env: { ...process.env, HOME: home }, encoding: "utf8" },
    );
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    assert.equal(await readFile(manifest, "utf8"), '{"name":"opencode","private":true}\n');
    assert.equal(existsSync(join(home, ".config", "opencode", "node_modules")), false);
    assert.deepEqual(
      parseJsonc(await readFile(join(home, ".config", "opencode", "opencode.jsonc"), "utf8"))
        .plugins,
      [PINNED],
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("applying the core-plugin fragment provisions the npm dependency", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  const calls = [];
  try {
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
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
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
    await applyConfigSetup(FULL_SELECTION, "global", directory, root, {
      dependencyRunner: runner,
    });
    const before = calls.length;
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
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
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
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
    await previewConfigSetup(FULL_SELECTION, "global", directory, root);
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

test("config preview is read-only and receipts reject changed bytes and replay", async () => {
  const directory = temporary();
  const root = join(directory, "home");
  const selection = { targets: ["opencode"], fragments: ["core-plugin"] };
  try {
    const { existsSync } = await import("node:fs");
    const preview = await previewConfigSetup(selection, "global", directory, root, false);
    assert.equal(existsSync(root), false);
    const config = join(root, ".config", "opencode", "opencode.jsonc");
    await mkdir(join(root, ".config", "opencode"), { recursive: true });
    await writeFile(config, '{"model":"changed"}\n');
    const options = {
      provisionDependency: false,
      receipt: preview.receipt,
      dependencyRunner: async () => {
        throw new Error("npm must not run");
      },
    };
    await assert.rejects(applyConfigSetup(selection, "global", directory, root, options), {
      code: "stale_receipt",
    });
    assert.equal(readFileSync(config, "utf8"), '{"model":"changed"}\n');
    const fresh = await previewConfigSetup(selection, "global", directory, root, false);
    options.receipt = fresh.receipt;
    await applyConfigSetup(selection, "global", directory, root, options);
    await assert.rejects(applyConfigSetup(selection, "global", directory, root, options), {
      code: "stale_receipt",
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("config preview preserves an interrupted transaction for explicit recovery", async () => {
  const directory = temporary();
  const root = await homeWithConfigs(directory);
  try {
    const { lifecycleRoot } = await import("../dist/lifecycle.js");
    const state = lifecycleRoot("global", directory, root);
    await mkdir(state, { recursive: true });
    const journal = join(state, "transaction-journal.json");
    await writeFile(journal, "pending recovery");
    await assert.rejects(previewConfigSetup(FULL_SELECTION, "global", directory, root), {
      code: "recovery_required",
    });
    assert.equal(readFileSync(journal, "utf8"), "pending recovery");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("permission migration preserves legacy rule order, scalar defaults, aliases, and comments", () => {
  const source = `{
    "model": "user/model",
    "providers": { "custom": { "settings": { "apiKey": "{env:USER_KEY}" } } },
    "permission": {
      // keep shell restrictions
      "bash": { "*": "ask", "git push *": "deny" },
      "task": "deny",
      "edit": "ask",
      "read": { "*": "allow", "secrets/*": "deny" }
    }
  }`;
  const addition = { action: "read", resource: "~/state/*", effect: "allow" };
  const edits = permissionEdits(parseJsonc(source), [addition]);
  const migrated = applyJsoncEdits(source, edits);
  const config = parseJsonc(migrated.text);
  assert.deepEqual(config.permissions, [
    { action: "shell", resource: "*", effect: "ask" },
    { action: "shell", resource: "git push *", effect: "deny" },
    { action: "subagent", resource: "*", effect: "deny" },
    { action: "edit", resource: "*", effect: "ask" },
    { action: "read", resource: "*", effect: "allow" },
    { action: "read", resource: "secrets/*", effect: "deny" },
    addition,
  ]);
  assert.equal(config.permission, undefined);
  assert.match(migrated.text, /\/\/ keep shell restrictions/);
  assert.equal(config.model, "user/model");
  assert.deepEqual(config.providers, parseJsonc(source).providers);
  assert.equal(applyJsoncEdits(migrated.text, permissionEdits(config, [addition])).changed, false);
  const scalar = applyJsoncEdits(
    '{"permission":"ask"}',
    permissionEdits({ permission: "ask" }, [addition]),
  );
  assert.deepEqual(parseJsonc(scalar.text).permissions, [
    { action: "*", resource: "*", effect: "ask" },
    addition,
  ]);
});

test("native permission edits preserve existing comments and ordered user exceptions", () => {
  const source = `{
    "permissions": [
      { "action": "*", "resource": "*", "effect": "ask" }, // broad default
      { "action": "shell", "resource": "git push *", "effect": "deny" }, // never push
    ],
    "mcp": { "servers": {} },
  }`;
  const original = parseJsonc(source);
  const addition = { action: "read", resource: "~/state/*", effect: "allow" };
  const migrated = applyJsoncEdits(source, permissionEdits(original, [addition]));
  const config = parseJsonc(migrated.text);
  assert.deepEqual(config.permissions, [...original.permissions, addition]);
  assert.match(migrated.text, /\/\/ broad default/);
  assert.match(migrated.text, /\/\/ never push/);
  assert.deepEqual(config.mcp, original.mcp);
});

test("ambiguous or malformed permission sections conflict rather than weaken user rules", () => {
  const allow = { action: "read", resource: "~/state/*", effect: "allow" };
  for (const config of [
    { permissions: "allow" },
    { permissions: [{ action: "read", effect: "allow" }] },
    { permission: { read: true } },
    { permission: { lsp: "allow" } },
    { tools: { read: "ask" } },
    { permissions: [{ ...allow, effect: "deny" }] },
    { permissions: [allow, { action: "*", resource: "*", effect: "ask" }] },
  ])
    assert.throws(() => permissionEdits(config, [allow]), JsoncError);
  const source =
    '{"permission":{"read":"allow"},/*keep*/"permissions":[{"action":"read","resource":"*","effect":"allow"}],"model":"user/model"}';
  const migrated = applyJsoncEdits(source, permissionEdits(parseJsonc(source), []));
  assert.equal(parseJsonc(migrated.text).permission, undefined);
  assert.match(migrated.text, /\/\*keep\*\//);
  assert.equal(parseJsonc(migrated.text).model, "user/model");
});

test("legacy tools migrate once and plugin options are not duplicated or discarded", () => {
  const source = '{"tools":{"websearch":false,"bash":true,"patch":false},"model":"user/model"}';
  const migrated = applyJsoncEdits(source, permissionEdits(parseJsonc(source), []));
  assert.deepEqual(parseJsonc(migrated.text).permissions, [
    { action: "websearch", resource: "*", effect: "deny" },
    { action: "shell", resource: "*", effect: "allow" },
    { action: "edit", resource: "*", effect: "deny" },
  ]);
  assert.equal(parseJsonc(migrated.text).tools, undefined);
  const plugins =
    '{"plugin":[["@kisev/skills-opencode",{"enabled":false}],"user-plugin"],"model":"user/model"}';
  const config = applyJsoncEdits(plugins, corePluginEdits(parseJsonc(plugins)));
  assert.deepEqual(parseJsonc(config.text).plugins, [
    { package: PINNED, options: { enabled: false } },
    "user-plugin",
  ]);
  assert.equal(parseJsonc(config.text).plugin, undefined);
  assert.equal(
    applyJsoncEdits(config.text, corePluginEdits(parseJsonc(config.text))).changed,
    false,
  );
  assert.throws(() => corePluginEdits({ plugin: ["old"], plugins: ["new"] }), JsoncError);
});

test("JSONC key edits preserve comments, first/last properties, and unrelated bytes", () => {
  for (const source of [
    '{"old":1,/*note*/"keep":2}',
    '{"keep":2,/*note*/"old":1}',
    '{"old":{/*note*/"nested":1}}',
    '{"keep":2,"old":1,/*note*/}',
  ]) {
    const migrated = applyJsoncEdits(source, [{ kind: "remove-key", path: ["old"] }]);
    const config = parseJsonc(migrated.text);
    assert.equal(config.old, undefined);
    assert.equal(config.keep, parseJsonc(source).keep);
    assert.match(migrated.text, /\/\*note\*\//);
  }
});

test("terminal setup leaves legacy TUI migration to V2 and never writes an inactive file", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  try {
    const original = '{"theme":"user-theme","keybinds":{"app_exit":"ctrl+q"}}\n';
    const file = join(home, ".config/opencode/tui.json");
    await writeFile(file, original);
    const selection = { targets: ["opencode"], fragments: ["tui-schema"] };
    const preview = await previewConfigSetup(selection, "global", directory, home, false);
    assert.equal(preview.confirmable, false);
    assert.equal(preview.operations[0].operation, "conflict");
    assert.match(preview.operations[0].reason, /Start OpenCode V2 once/);
    assert.equal(readFileSync(file, "utf8"), original);
    await assert.rejects(
      applyConfigSetup(selection, "global", directory, home, {
        receipt: preview.receipt,
        provisionDependency: false,
      }),
      { code: "invalid_state" },
    );
    assert.equal(readFileSync(file, "utf8"), original);
    assert.throws(
      () =>
        normalizeConfigSelection("global", { targets: ["opencode"], fragments: ["lsp-preset"] }),
      ConfigSetupError,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("a permission conflict leaves its whole section unchanged while unrelated fragments apply", async () => {
  const directory = temporary();
  const home = await homeWithConfigs(directory);
  const file = join(home, ".config/opencode/opencode.jsonc");
  try {
    const original = {
      permissions: [{ action: "read", resource: "~/.local/state/agent-skills/**", effect: "deny" }],
      model: "user/model",
    };
    await writeFile(file, JSON.stringify(original));
    const selection = {
      targets: ["opencode"],
      fragments: ["core-plugin", "skills-state-permissions"],
    };
    const preview = await previewConfigSetup(selection, "global", directory, home, false);
    assert.ok(
      preview.operations.some(
        (item) => item.fragment === "skills-state-permissions" && item.operation === "conflict",
      ),
    );
    await applyConfigSetup(selection, "global", directory, home, {
      receipt: preview.receipt,
      provisionDependency: false,
    });
    const config = parseJsonc(readFileSync(file, "utf8"));
    assert.deepEqual(config.permissions, original.permissions);
    assert.equal(config.model, original.model);
    assert.deepEqual(config.plugins, [PINNED]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("mixed permission sections preserve the exact V2 normalization precedence", () => {
  const source =
    '{"tools":{"bash":false},"permission":{"bash":{"*":"ask","git push *":"deny"}},"permissions":[{"action":"shell","resource":"git status *","effect":"allow"}]}';
  const result = applyJsoncEdits(source, permissionEdits(parseJsonc(source), []));
  const config = parseJsonc(result.text);
  assert.deepEqual(config.permissions, [
    { action: "shell", resource: "*", effect: "deny" },
    { action: "shell", resource: "*", effect: "ask" },
    { action: "shell", resource: "git push *", effect: "deny" },
    { action: "shell", resource: "git status *", effect: "allow" },
  ]);
  assert.equal(config.tools, undefined);
  assert.equal(config.permission, undefined);
  assert.equal(applyJsoncEdits(result.text, permissionEdits(config, [])).changed, false);
});

test("JSONC validation rejects missing separators and preserves prototype-named user fields", () => {
  for (const source of ['{"permissions":[]"model":"user/model"}', '["a" "b"]'])
    assert.throws(() => parseJsonc(source), JsoncError);
  const config = parseJsonc('{"__proto__":{"permissions":"allow"},"model":"user/model"}');
  assert.equal(Object.hasOwn(config, "__proto__"), true);
  assert.equal(Object.getPrototypeOf(config), Object.prototype);
  assert.equal(config.permissions, undefined);
});
