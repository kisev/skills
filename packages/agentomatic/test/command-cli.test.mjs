import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, mkdir, readFile, readdir, writeFile, unlink, chmod, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { stripVTControlCharacters } from "node:util";
import { apply, preview } from "../dist/installer.js";
import {
  applyAgentProfileChange,
  listAgentProfiles,
  previewAgentProfileChange,
} from "../dist/agent-profiles.js";
import { previewDependencyRemoval, removeDependency } from "../dist/self-install.js";
import { applyTransaction, lifecycleRoot } from "../dist/lifecycle.js";
import { recoverConfigSetup } from "../dist/config-setup.js";

const cli = resolve(import.meta.dirname, "../dist/cli.js");
async function sandbox(t) {
  const base = await mkdtemp(join(tmpdir(), "agentomatic-cli-workflow-"));
  const project = join(base, "project");
  const home = join(base, "home");
  await Promise.all([mkdir(project), mkdir(home)]);
  t.after(() => rm(base, { recursive: true, force: true }));
  const env = { ...process.env, HOME: home, XDG_STATE_HOME: join(home, ".state") };
  const run = (args) =>
    spawnSync(process.execPath, [cli, ...args, "--json"], { cwd: project, env, encoding: "utf8" });
  const ok = (args) => {
    const result = run(args);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    return JSON.parse(result.stdout);
  };
  return { base, project, home, root: join(project, ".opencode"), env, run, ok };
}
const subset = [
  "--commands",
  "askme",
  "--agents",
  "critic",
  "--plugins",
  "none",
  "--no-core",
  "--no-dependency",
];

test("partial install, model edits, repeat install, repair, and uninstall retain exactly the selected set", async (t) => {
  const context = await sandbox(t);
  const { ok, root, run } = context;
  const draft = ok(["install", ...subset, "--dry-run"]);
  assert.equal(draft.applied, false);
  await assert.rejects(readdir(root), { code: "ENOENT" });
  ok(["install", ...subset, "--yes"]);
  ok(["configure", "agent", "critic", "--model", "openai/example", "--variant", "high", "--yes"]);
  // Saving a model for an uninstalled role must not deploy it.
  ok(["configure", "agent", "worker", "--model", "openai/worker", "--yes"]);
  assert.deepEqual(await readdir(join(root, "agents")), ["critic.md"]);
  assert.equal(
    ok(["agent", "list"]).inventory.profiles.find((profile) => profile.name === "worker").state,
    "not-installed",
  );
  ok(["install", "--no-dependency", "--yes"]);
  await unlink(join(root, "agents/critic.md"));
  await unlink(join(root, "commands/askme.md"));
  ok(["maintenance", "repair", "--no-dependency", "--yes"]);
  assert.deepEqual(await readdir(join(root, "agents")), ["critic.md"]);
  assert.match(
    await readFile(join(root, "agents/critic.md"), "utf8"),
    /model: openai\/example#high/,
  );
  await writeFile(join(root, "agents/critic.md"), "user changed\n");
  const blocked = run(["maintenance", "repair", "--no-dependency", "--yes"]);
  assert.equal(blocked.status, 2);
  assert.equal(JSON.parse(blocked.stdout).error.code, "conflict");
  assert.equal(await readFile(join(root, "agents/critic.md"), "utf8"), "user changed\n");
});

test("installation drafts atomically include models and multiple critics", async (t) => {
  const context = await sandbox(t);
  const selection = { commands: [], agents: ["critic"], plugins: [], core_activation: false };
  const changes = [
    { action: "model-set", name: "critic", model: "openai/base", variant: "high" },
    { action: "critic-add", name: "critic-security", model: "anthropic/security" },
    { action: "critic-add", name: "critic-performance", model: "openai/performance" },
  ];
  const plan = await preview(
    "install",
    "project",
    context.project,
    context.home,
    selection,
    false,
    changes,
  );
  await assert.rejects(readdir(context.root), { code: "ENOENT" });
  await assert.rejects(
    apply(
      "install",
      "project",
      context.project,
      context.home,
      {
        expectedDigest: plan.digest,
        beforePublish: () => {
          throw new Error("injected draft failure");
        },
      },
      selection,
      false,
      changes,
    ),
  );
  const fresh = await preview(
    "install",
    "project",
    context.project,
    context.home,
    selection,
    false,
    changes,
  );
  await apply(
    "install",
    "project",
    context.project,
    context.home,
    { expectedDigest: fresh.digest },
    selection,
    false,
    changes,
  );
  const inventory = await listAgentProfiles("project", context.project, context.home);
  assert.deepEqual(inventory.critic_pool, ["critic", "critic-performance", "critic-security"]);
  assert.deepEqual(
    (await readdir(join(context.root, "agents"))).sort(),
    inventory.critic_pool.map((name) => `${name}.md`).sort(),
  );
});

test("confirmed profile and component plans reject changed sources instead of silently replanning", async (t) => {
  const context = await sandbox(t);
  context.ok(["install", ...subset, "--yes"]);
  const request = { action: "model-set", name: "critic", model: "openai/new" };
  const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
  const path = join(context.root, ".agentomatic/agent-profiles.json");
  const original = await readFile(path, "utf8");
  await writeFile(path, original + "\n");
  await assert.rejects(
    applyAgentProfileChange(request, "project", context.project, context.home, {
      expectedDigest: plan.digest,
    }),
    { code: "stale_plan" },
  );
  const selection = {
    commands: ["askme"],
    agents: ["critic"],
    plugins: [],
    core_activation: false,
  };
  const installer = await preview(
    "install",
    "project",
    context.project,
    context.home,
    selection,
    false,
  );
  await writeFile(path, original + "\n\n");
  await assert.rejects(
    apply(
      "install",
      "project",
      context.project,
      context.home,
      { expectedDigest: installer.digest },
      selection,
      false,
    ),
    { code: "stale_plan" },
  );
});

test("configure integration saves disconnection for repair and uninstall preserves comments and model choices", async (t) => {
  const { ok, project, root } = await sandbox(t);
  ok(["install", ...subset, "--yes"]);
  ok(["configure", "agent", "critic", "--model", "openai/base", "--yes"]);
  const configPath = join(project, "opencode.jsonc");
  await writeFile(
    configPath,
    '{\n  // keep me\n  "plugins": ["foreign", "@kisev/agentomatic@11.0.2"],\n  "model": "user/model"\n}\n',
  );
  ok(["configure", "integration", "--targets", "opencode", "--fragments", "core-disable", "--yes"]);
  assert.equal(ok(["status"]).selection.core_activation, false);
  ok(["maintenance", "repair", "--no-dependency", "--yes"]);
  assert.equal(ok(["status"]).connection.connected, false);
  ok(["agent", "add-critic", "security", "--model", "openai/security", "--yes"]);
  const preview = ok(["uninstall", "--dry-run"]);
  assert.equal(preview.models, "retained");
  ok(["uninstall", "--yes"]);
  const config = await readFile(configPath, "utf8");
  assert.match(config, /keep me/);
  assert.match(config, /foreign/);
  assert.match(config, /user\/model/);
  assert.doesNotMatch(config, /agentomatic/);
  const inventory = ok(["agent", "list"]).inventory;
  assert.equal(
    inventory.profiles.find((profile) => profile.name === "critic").model,
    "openai/base",
  );
  assert.equal(
    inventory.profiles.find((profile) => profile.name === "critic-security").state,
    "not-installed",
  );
  assert.deepEqual(inventory.critic_pool, []);
  assert.equal(ok(["status"]).installed, false);
  assert.deepEqual(await readdir(join(root, "agents")), []);
});

test("dependency removal is explicit, bounded, and rejects stale npm files", async (t) => {
  const { project, home } = await sandbox(t);
  const path = join(project, "package.json");
  await writeFile(
    path,
    JSON.stringify({ dependencies: { "@kisev/agentomatic": "11.0.2", foreign: "1.0.0" } }),
  );
  const plan = await previewDependencyRemoval("project", project, home);
  assert.deepEqual(plan.names, ["@kisev/agentomatic"]);
  const calls = [];
  await removeDependency(plan, async (command, args, options) => {
    calls.push({ command, args, options });
    await writeFile(path, '{"dependencies":{"foreign":"1.0.0"}}');
    return { stdout: "", stderr: "" };
  });
  assert.deepEqual(calls[0].args, ["rm", "@kisev/agentomatic", "--no-audit", "--no-fund"]);
  await writeFile(path, '{"dependencies":{"foreign":"2.0.0"}}');
  await assert.rejects(
    removeDependency(plan, async () => {
      throw new Error("must not launch npm");
    }),
    { code: "stale_plan" },
  );
});

test("removed commands have no aliases and every new command has focused help", async (t) => {
  const { run } = await sandbox(t);
  for (const args of [
    ["config"],
    ["capabilities"],
    ["reconcile"],
    ["agent", "configure"],
    ["agent", "model-set"],
    ["agent", "reconcile"],
    ["critic", "add"],
    ["critic", "remove"],
  ]) {
    const result = run([...args, "--dry-run"]);
    assert.equal(result.status, 2, args.join(" "));
    assert.equal(JSON.parse(result.stdout).error.code, "invalid_input");
  }
  for (const args of [
    ["status"],
    ["configure", "critics"],
    ["configure", "integration"],
    ["maintenance", "recover"],
    ["catalog"],
  ]) {
    const result = run([...args, "--help"]);
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Usage:/);
  }
});

test("npm install failure reports committed components without claiming configuration success", async (t) => {
  const context = await sandbox(t);
  const bin = join(context.base, "bin");
  await mkdir(bin);
  await writeFile(join(bin, "npm"), "#!/bin/sh\nexit 1\n");
  await chmod(join(bin, "npm"), 0o755);
  context.env.PATH = `${bin}:${context.env.PATH}`;
  const result = context.run([
    "install",
    "--global",
    "--commands",
    "none",
    "--agents",
    "critic",
    "--plugins",
    "none",
    "--core",
    "--yes",
  ]);
  assert.equal(result.status, 2, result.stdout + result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.status, "partial");
  assert.deepEqual(output.completed_stages, ["owned-components-and-profiles"]);
  assert.equal(output.error.code, "npm_dependency_failed");
  assert.equal(output.requires_restart, true);
  assert.match(output.next_step, /status/);
  assert.equal(context.ok(["status", "--global"]).installed, true);
  assert.equal(context.ok(["status", "--global"]).connection.connected, false);
});

test("observations and all previews leave existing files unchanged; recovery supports cleanup roots", async (t) => {
  const context = await sandbox(t);
  context.ok(["install", ...subset, "--yes"]);
  const config = join(context.project, "opencode.jsonc");
  await writeFile(config, '{"plugins":["foreign"]}\n');
  const before = await readFile(config);
  const profilesPath = join(context.root, ".agentomatic/agent-profiles.json");
  const profilesBefore = await readFile(profilesPath);
  for (const args of [
    ["status"],
    ["catalog"],
    ["agent", "list"],
    ["install", "--no-dependency", "--dry-run"],
    ["maintenance", "repair", "--no-dependency", "--dry-run"],
    ["maintenance", "cleanup", "--dry-run"],
    ["uninstall", "--dry-run"],
  ])
    context.ok(args);
  context.run(["doctor"]);
  assert.deepEqual(await readFile(config), before);
  assert.deepEqual(await readFile(profilesPath), profilesBefore);
  for (const scope of ["project", "global"]) {
    const transactionRoot = scope === "project" ? context.project : context.home;
    const state = lifecycleRoot(scope, context.project, context.home);
    const path =
      scope === "project"
        ? ".opencode/commands/recovery.md"
        : ".config/opencode/commands/recovery.md";
    await assert.rejects(
      applyTransaction(
        transactionRoot,
        state,
        [
          {
            path,
            operation: "write",
            content: Buffer.from("interrupted\n"),
            mode: 0o600,
            expected: { absent: true },
          },
        ],
        { afterPublish: () => "interrupt" },
      ),
      { code: "test_interruption" },
    );
    const journalBefore = await readFile(join(state, "transaction-journal.json"));
    const recovery = await recoverConfigSetup(scope, true, context.project, context.home);
    assert.deepEqual(await readFile(join(state, "transaction-journal.json")), journalBefore);
    await recoverConfigSetup(scope, false, context.project, context.home, recovery.digest);
    await assert.rejects(readFile(join(transactionRoot, path)), { code: "ENOENT" });
  }
});

const ttyPreload = `data:text/javascript,${encodeURIComponent('Object.defineProperty(process.stdin,"isTTY",{value:true});Object.defineProperty(process.stderr,"isTTY",{value:true});process.stdin.setRawMode=()=>process.stdin;process.stderr.columns=120;')}`;
async function wizard(context, answers, args = ["install", "--no-dependency", "--no-core"]) {
  const child = spawn(process.execPath, ["--import", ttyPreload, cli, ...args], {
    cwd: context.project,
    env: context.env,
    stdio: ["pipe", "pipe", "pipe"],
  });
  let output = "";
  let pending = "";
  let index = 0;
  const timeout = setTimeout(() => child.kill(), 15_000);
  const receive = (chunk) => {
    output += chunk.toString();
    pending += stripVTControlCharacters(chunk.toString());
    if (index < answers.length && pending.includes(answers[index][0])) {
      const [, keys] = answers[index++];
      pending = "";
      child.stdin.write(keys);
      if (index === answers.length) child.stdin.end();
    }
  };
  child.stdout.on("data", receive);
  child.stderr.on("data", receive);
  const status = await new Promise((resolve) => child.on("close", resolve));
  clearTimeout(timeout);
  assert.equal(index, answers.length, output);
  return { status, output };
}

test("TTY install can skip model setup and cancellation before apply leaves no files", async (t) => {
  const context = await sandbox(t);
  const cancelled = await wizard(context, [
    ["Skill command adapters", "\r"],
    ["Fixed agents", "\r"],
    ["Optional plugins", "\r"],
    ["Configure application presets", "n\r"],
    ["Configure agent models", "n\r"],
    ["Apply the displayed changes", "n\r"],
  ]);
  assert.equal(cancelled.status, 2, cancelled.output);
  await assert.rejects(readdir(context.root), { code: "ENOENT" });
  await assert.rejects(readdir(join(context.home, ".state")), { code: "ENOENT" });
});

test("TTY install stages a critic model from the catalog and applies it with one confirmation", async (t) => {
  const context = await sandbox(t);
  const bin = join(context.base, "bin");
  await mkdir(bin);
  await writeFile(
    join(bin, "opencode"),
    '#!/bin/sh\nprintf \'%s\\n\' \'{"data":[{"providerID":"openai","id":"example","variants":[{"id":"high"}]}]}\'\n',
  );
  await chmod(join(bin, "opencode"), 0o755);
  context.env.PATH = `${bin}:${context.env.PATH}`;
  const result = await wizard(context, [
    ["Skill command adapters", "a\r"],
    ["Fixed agents", "a\x1b[B\x1b[B\x1b[B\x1b[B\x1b[B \r"],
    ["Optional plugins", "\x1b[B \r"],
    ["Configure application presets", "n\r"],
    ["Configure agent models", "y\r"],
    ["changes are staged", "\x1b[A\x1b[A\x1b[A\r"],
    ["Agent", "\r"],
    ["Agent: critic", "\r"],
    ["Provider", "\r"],
    ["Model", "\r"],
    ["Variant", "\x1b[B\r"],
    ["Agent models and critics", "\r"],
    ["Apply the displayed changes", "y\r"],
  ]);
  assert.equal(result.status, 0, result.output);
  assert.match(
    await readFile(join(context.root, "agents/critic.md"), "utf8"),
    /model: openai\/example#high/,
  );
});

test("TTY install can apply with model setup skipped", async (t) => {
  const context = await sandbox(t);
  const result = await wizard(context, [
    ["Skill command adapters", "a\r"],
    ["Fixed agents", "a\x1b[B\x1b[B\x1b[B\x1b[B\x1b[B \r"],
    ["Optional plugins", "\x1b[B \r"],
    ["Configure application presets", "n\r"],
    ["Configure agent models", "n\r"],
    ["Apply the displayed changes", "y\r"],
  ]);
  assert.equal(result.status, 0, result.output);
  assert.deepEqual(await readdir(join(context.root, "agents")), ["critic.md"]);
  assert.doesNotMatch(await readFile(join(context.root, "agents/critic.md"), "utf8"), /^model:/m);
});

test("cancelling the staged model wizard before catalog selection writes nothing", async (t) => {
  const context = await sandbox(t);
  const result = await wizard(context, [
    ["Skill command adapters", "\r"],
    ["Fixed agents", "\r"],
    ["Optional plugins", "\r"],
    ["Configure application presets", "n\r"],
    ["Configure agent models", "y\r"],
    ["changes are staged", "\x1b[A\x1b[A\x1b[A\r"],
    ["Agent", "\r"],
    ["Agent: architect", "\x03"],
  ]);
  assert.equal(result.status, 2, result.output);
  await assert.rejects(readdir(context.root), { code: "ENOENT" });
});

test("repeat TTY installation defaults to saved components, models, and disconnected core", async (t) => {
  const context = await sandbox(t);
  context.ok(["install", ...subset, "--yes"]);
  context.ok([
    "configure",
    "agent",
    "critic",
    "--model",
    "openai/retained",
    "--variant",
    "high",
    "--yes",
  ]);
  const result = await wizard(
    context,
    [
      ["Skill command adapters", "\r"],
      ["Fixed agents", "\r"],
      ["Optional plugins", "\r"],
      ["Connect the OpenCode plugin", "\r"],
      ["Configure application presets", "n\r"],
      ["Configure agent models", "n\r"],
    ],
    ["install", "--no-dependency"],
  );
  assert.equal(result.status, 0, result.output);
  const status = context.ok(["status"]);
  assert.deepEqual(status.selection.agents, ["critic"]);
  assert.equal(status.selection.core_activation, false);
  assert.equal(
    status.inventory.profiles.find((profile) => profile.name === "critic").variant,
    "high",
  );
});
