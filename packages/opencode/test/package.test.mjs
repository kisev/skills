import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync } from "node:fs";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import plugin, { COMMAND_REGISTRY, RoutingGate, renderCommand, resolveRouting } from "../dist/index.js";
import { InstallerError, apply, preview } from "../dist/installer.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const REPOSITORY = resolve(PACKAGE, "../..");

function temporary() {
  return mkdtempSync(join(tmpdir(), "agent-skills-opencode-test-"));
}

function capable(agent, capabilities, tools) {
  return { agent, available: true, capabilities, tools };
}

async function install(scope, cwd, home) {
  const plan = await preview("install", scope, cwd, home);
  return { plan, applied: await apply("install", scope, plan.digest, cwd, home) };
}

test("registry generates exactly thirty-one thin portable command assets", () => {
  assert.equal(COMMAND_REGISTRY.length, 31);
  assert.equal(new Set(COMMAND_REGISTRY.map(({ name }) => name)).size, 31);
  const skills = new Set(readdirSync(join(REPOSITORY, "skills")));
  for (const entry of COMMAND_REGISTRY) {
    assert.ok(skills.has(entry.skill), entry.skill);
    const rendered = renderCommand(entry);
    assert.match(rendered, /native Skill tool/);
    assert.match(rendered, /недоверенный ввод/);
    assert.match(rendered, /\$ARGUMENTS/);
    assert.ok(rendered.includes(`Required skill \`${entry.skill}\` is not installed`));
    assert.doesNotMatch(rendered, /python|runner|curl|fetch\(/i);
    assert.equal(readFileSync(join(PACKAGE, "assets", "commands", `${entry.name}.md`), "utf8"), rendered);
  }
  for (const forbidden of ["attempt", "goal", "schedule", "multi-run", "overview", "lsp-report", "agent-profiles", "capabilities", "doctor"]) assert.ok(!COMMAND_REGISTRY.some((entry) => entry.skill === forbidden));
});

test("agent assets contain six contract-bound profiles without model selection", () => {
  const agents = readdirSync(join(PACKAGE, "assets", "agents")).filter((name) => name.endsWith(".md")).sort();
  assert.deepEqual(agents, ["architect.md", "critic.md", "manager.md", "mapper.md", "review.md", "worker.md"]);
  for (const name of agents) {
    const content = readFileSync(join(PACKAGE, "assets", "agents", name), "utf8");
    const frontmatter = content.slice(0, content.indexOf("---", 4));
    assert.doesNotMatch(frontmatter, /^(model|provider):/m);
    assert.doesNotMatch(content, /bedrock|~\/\.config\/opencode/i);
    assert.match(frontmatter, /permission:/);
  }
  assert.match(readFileSync(join(PACKAGE, "assets", "agents", "mapper.md"), "utf8"), /mapper_report/);
  assert.match(readFileSync(join(PACKAGE, "assets", "agents", "architect.md"), "utf8"), /execution_card/);
  assert.match(readFileSync(join(PACKAGE, "assets", "agents", "worker.md"), "utf8"), /worker_report/);
  assert.match(readFileSync(join(PACKAGE, "assets", "agents", "critic.md"), "utf8"), /critic_report/);
});

test("installer dry-run is deterministic and keeps global and project roots isolated", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    const first = await preview("install", "global", project, home);
    const second = await preview("install", "global", project, home);
    assert.deepEqual(second, first);
    assert.equal(first.operations.filter((item) => item.operation === "create").length, 37);
    await assert.rejects(lstat(join(home, ".config")), { code: "ENOENT" });
    await install("global", project, home);
    assert.equal(readdirSync(join(home, ".config", "opencode", "agents")).length, 6);
    assert.equal(readdirSync(join(home, ".config", "opencode", "commands")).length, 31);
    await assert.rejects(lstat(join(home, ".config", "opencode", "opencode.json")), { code: "ENOENT" });
    await assert.rejects(lstat(join(project, ".opencode")), { code: "ENOENT" });
    await install("project", project, home);
    assert.equal(readdirSync(join(project, ".opencode", "agents")).length, 6);
    await assert.rejects(lstat(join(project, "opencode.json")), { code: "ENOENT" });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("installer rejects stale plans, unmanaged collisions, traversal, and symlinks", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    const stale = await preview("install", "project", project, home);
    await mkdir(join(project, ".opencode", "agents"), { recursive: true });
    await writeFile(join(project, ".opencode", "agents", "manager.md"), "user\n");
    await assert.rejects(apply("install", "project", stale.digest, project, home), (error) => error instanceof InstallerError && error.code === "stale_plan");
    const collision = await preview("install", "project", project, home);
    assert.deepEqual(collision.operations.find((item) => item.path === "agents/manager.md"), { path: "agents/manager.md", operation: "conflict", reason: "unmanaged_file", sha256: collision.operations.find((item) => item.path === "agents/manager.md").sha256 });
    await assert.rejects(apply("install", "project", collision.digest, project, home), (error) => error instanceof InstallerError && error.code === "conflict");
    assert.equal(await readFile(join(project, ".opencode", "agents", "manager.md"), "utf8"), "user\n");

    const separate = join(directory, "separate");
    await mkdir(join(separate, ".opencode"), { recursive: true });
    symlinkSync(join(directory, "outside"), join(separate, ".opencode", "agents"));
    await assert.rejects(preview("install", "project", separate, home), (error) => error instanceof InstallerError && error.code === "unsafe_path");
    await writeFile(join(separate, ".opencode", ".agent-skills-opencode-manifest.json"), JSON.stringify({ schema_version: 1, package: "agent-skills-opencode", version: "0.1.0", files: { "../outside": { sha256: "0".repeat(64) } } }));
    await assert.rejects(preview("uninstall", "project", separate, home), (error) => error instanceof InstallerError && error.code === "unsafe_path");

    const nonregular = join(directory, "nonregular");
    await mkdir(join(nonregular, ".opencode", "agents", "manager.md"), { recursive: true });
    await assert.rejects(preview("install", "project", nonregular, home), (error) => error instanceof InstallerError && error.code === "unsafe_path");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("confirmed install is atomic per asset and idempotent", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    const { applied } = await install("project", project, home);
    const root = join(project, ".opencode");
    assert.equal(readdirSync(root).filter((name) => name.includes(".tmp")).length, 0);
    const manifest = join(root, ".agent-skills-opencode-manifest.json");
    const before = await readFile(manifest);
    const repeat = await preview("install", "project", project, home);
    assert.ok(repeat.operations.every((item) => item.operation === "unchanged"));
    await apply("install", "project", repeat.digest, project, home);
    assert.deepEqual(await readFile(manifest), before);
    assert.equal(applied.operations.filter((item) => item.operation === "create").length, 37);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("upgrade removes only an unchanged stale managed asset", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const root = join(project, ".opencode");
    const retired = join(root, "commands", "retired.md");
    const content = "retired\n";
    await writeFile(retired, content);
    const manifestPath = join(root, ".agent-skills-opencode-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.files["commands/retired.md"] = { sha256: createHash("sha256").update(content).digest("hex") };
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    const plan = await preview("install", "project", project, home);
    assert.equal(plan.operations.find((item) => item.path === "commands/retired.md").operation, "remove");
    await apply("install", "project", plan.digest, project, home);
    await assert.rejects(lstat(retired), { code: "ENOENT" });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("an applying manifest resumes an interrupted managed update", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const root = join(project, ".opencode");
    const manager = join(root, "agents", "manager.md");
    const previous = "previous managed version\n";
    await writeFile(manager, previous);
    const manifestPath = join(root, ".agent-skills-opencode-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const current = readFileSync(join(PACKAGE, "assets", "agents", "manager.md"));
    manifest.state = "applying";
    manifest.files["agents/manager.md"] = {
      sha256: createHash("sha256").update(current).digest("hex"),
      previous_sha256: createHash("sha256").update(previous).digest("hex")
    };
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    const plan = await preview("install", "project", project, home);
    assert.equal(plan.operations.find((item) => item.path === "agents/manager.md").operation, "update");
    await apply("install", "project", plan.digest, project, home);
    assert.deepEqual(await readFile(manager), current);
    assert.equal(JSON.parse(await readFile(manifestPath, "utf8")).state, undefined);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("uninstall removes only unchanged managed files and preserves user drift", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const changed = join(project, ".opencode", "commands", "askme.md");
    await writeFile(changed, "user change\n");
    const plan = await preview("uninstall", "project", project, home);
    assert.equal(plan.operations.filter((item) => item.operation === "remove").length, 36);
    assert.deepEqual(plan.operations.find((item) => item.path === "commands/askme.md").operation, "conflict");
    await apply("uninstall", "project", plan.digest, project, home);
    assert.equal(await readFile(changed, "utf8"), "user change\n");
    await assert.rejects(lstat(join(project, ".opencode", "agents", "manager.md")), { code: "ENOENT" });
    const manifest = JSON.parse(await readFile(join(project, ".opencode", ".agent-skills-opencode-manifest.json"), "utf8"));
    assert.deepEqual(Object.keys(manifest.files), ["commands/askme.md"]);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("runtime plugin has no lifecycle writes and receipt gate is enforced", async () => {
  const directory = temporary();
  try {
    const hooks = await plugin({});
    assert.ok(hooks.tool.route);
    assert.equal(hooks.config, undefined);
    await assert.rejects(hooks["tool.execute.before"]({ tool: "task", sessionID: "missing" }, { args: { agent: "worker" } }), /active routing receipt/);
    const worker = capable("worker", ["read", "write", "verify"], ["read", "edit", "bash"]);
    const routeInput = { category: "implementation", task: "Implement one scoped change", requirements: [], agents: [worker] };
    const decision = JSON.parse(await hooks.tool.route.execute({ action: "preview", ...routeInput }, { sessionID: "bound" }));
    await hooks.tool.route.execute({ action: "dispatch", ...routeInput, decision }, { sessionID: "bound" });
    await assert.rejects(hooks["tool.execute.before"]({ tool: "task", sessionID: "bound" }, { args: { subagent_type: "critic" } }), /does not match/);
    await hooks["tool.execute.before"]({ tool: "task", sessionID: "bound" }, { args: { subagent_type: "worker" } });
    const gate = new RoutingGate();
    const input = { category: "implementation", requirements: [], agents: [worker] };
    const selected = gate.preview(input);
    assert.equal(selected.agent, "worker");
    assert.throws(() => gate.dispatch(input, { ...selected, decision_digest: "stale" }), /stale/);
    gate.grant("session", gate.dispatch(input, selected));
    assert.throws(() => gate.consume("session", "critic"), /does not match/);
    gate.consume("session", "worker");
    assert.throws(() => gate.consume("session", "worker"), /active routing receipt/);
    const routing = resolveRouting({ category: "exploration", requirements: [], agents: [capable("mapper", ["read", "search"], ["read", "glob", "grep"]), { ...capable("architect", ["read", "search"], ["read", "glob", "grep"]), available: false }] });
    assert.equal(routing.agent, "mapper");
    assert.deepEqual(routing.alternatives, [{ agent: "architect", excluded_reasons: ["agent_unavailable"] }]);
    assert.equal(readdirSync(directory).length, 0);
    const packageJson = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
    for (const lifecycle of ["preinstall", "install", "postinstall", "prepack", "prepare"]) assert.equal(packageJson.scripts[lifecycle], undefined);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("CLI requires explicit scope and a tarball imports without portable skills", async () => {
  const invalid = spawnSync(process.execPath, [join(PACKAGE, "dist", "cli.js"), "install", "--dry-run"], { encoding: "utf8" });
  assert.equal(invalid.status, 2);
  assert.equal(JSON.parse(invalid.stdout).error.code, "invalid_input");
  const directory = temporary();
  try {
    const packed = JSON.parse(execFileSync("npm", ["pack", "--json", "--pack-destination", directory], { cwd: PACKAGE, encoding: "utf8" }));
    const tarball = join(directory, packed[0].filename);
    execFileSync("tar", ["-xzf", tarball, "-C", directory], { encoding: "utf8" });
    const unpacked = join(directory, "package");
    assert.equal(readdirSync(unpacked).includes("skills"), false);
    symlinkSync(join(PACKAGE, "node_modules"), join(unpacked, "node_modules"));
    const imported = await import(pathToFileURL(join(unpacked, "dist", "index.js")).href);
    assert.equal(typeof imported.default, "function");
    assert.equal(typeof imported.server, "function");
    assert.equal(typeof imported.apply, "undefined");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});
