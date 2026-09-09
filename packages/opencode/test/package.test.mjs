import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync } from "node:fs";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

for (const variable of ["GIT_WORK_TREE", "GIT_INDEX_FILE"]) delete process.env[variable];

import plugin, {
  COMMAND_REGISTRY,
  ExecutionCardLifecycle,
  RoutingGate,
  renderCommand,
  resolveRouting,
  validateExecutionCard,
  worktreeCreate,
  worktreeRecover,
  worktreeRelease,
  worktreeStatus,
} from "../dist/index.js";
import backgroundAttempts from "../dist/plugins/background-attempts.js";
import scheduler from "../dist/plugins/schedule.js";
import autonomyPolicy from "../dist/plugins/autonomy-policy.js";
import zedBell from "../dist/plugins/zed-bell.js";
import zedClickablePaths from "../dist/plugins/zed-clickable-paths.js";
import { InstallerError, apply, preview } from "../dist/installer.js";
import { applyReconcile, previewReconcile, ReconcileError } from "../dist/reconcile.js";
import { lifecycleRoot } from "../dist/lifecycle.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const REPOSITORY = resolve(PACKAGE, "../..");

function temporary() {
  return mkdtempSync(join(tmpdir(), "skills-opencode-test-"));
}

function capable(agent, capabilities, tools) {
  return { agent, available: true, capabilities, tools };
}

async function install(scope, cwd, home) {
  const plan = await preview("install", scope, cwd, home);
  return { plan, applied: await apply("install", scope, plan.digest, cwd, home) };
}

test("registry generates exactly thirty-three thin command assets", () => {
  assert.equal(COMMAND_REGISTRY.length, 33);
  assert.equal(new Set(COMMAND_REGISTRY.map(({ name }) => name)).size, 33);
  const skills = new Set(readdirSync(join(REPOSITORY, "skills")));
  for (const entry of COMMAND_REGISTRY) {
    if (entry.skill) assert.ok(skills.has(entry.skill), entry.skill);
    const rendered = renderCommand(entry);
    assert.match(rendered, entry.packageTool ? /package tool/ : /native Skill tool/);
    assert.match(rendered, /untrusted input/);
    assert.match(rendered, /\$ARGUMENTS/);
    if (entry.skill)
      assert.ok(rendered.includes(`Required skill \`${entry.skill}\` is not installed`));
    assert.doesNotMatch(rendered, /python|runner|curl|fetch\(/i);
    assert.equal(
      readFileSync(join(PACKAGE, "dist", "assets", "commands", `${entry.name}.md`), "utf8"),
      rendered,
    );
  }
  for (const expected of ["code-explain", "goal", "lsp-report", "spec-manage", "team-sprint-start"])
    assert.ok(COMMAND_REGISTRY.some((entry) => entry.skill === expected));
  assert.deepEqual(
    COMMAND_REGISTRY.filter((entry) => entry.skill === "goal").map((entry) => entry.name),
    ["goal"],
  );
  for (const forbidden of [
    "goal-list",
    "goal-pause",
    "goal-prepare",
    "goal-remove",
    "goal-show",
    "goal-start",
  ])
    assert.ok(!COMMAND_REGISTRY.some((entry) => entry.name === forbidden));
  assert.ok(!COMMAND_REGISTRY.some((entry) => entry.skill === "agent-profiles"));
  assert.deepEqual(
    COMMAND_REGISTRY.filter((entry) => entry.packageTool)
      .map((entry) => entry.name)
      .sort(),
    ["agent-profiles", "capabilities", "doctor", "reconcile"],
  );
});

test("generated asset drift rejects obsolete files", async () => {
  const directory = temporary();
  try {
    execFileSync("node", ["dist/generate-assets.js", "--root", directory], { cwd: PACKAGE });
    await writeFile(join(directory, "obsolete.md"), "stale\n");
    const result = spawnSync("node", ["dist/generate-assets.js", "--check", "--root", directory], {
      cwd: PACKAGE,
      encoding: "utf8",
    });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /unexpected generated asset: obsolete\.md/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("agent assets contain six contract-bound profiles without model selection", () => {
  const agents = readdirSync(join(PACKAGE, "dist", "assets", "agents"))
    .filter((name) => name.endsWith(".md"))
    .sort();
  assert.deepEqual(agents, [
    "architect.md",
    "critic.md",
    "manager.md",
    "mapper.md",
    "review.md",
    "worker.md",
  ]);
  for (const name of agents) {
    const content = readFileSync(join(PACKAGE, "dist", "assets", "agents", name), "utf8");
    const frontmatter = content.slice(0, content.indexOf("---", 4));
    assert.doesNotMatch(frontmatter, /^(model|provider):/m);
    assert.doesNotMatch(content, /~\/\.config\/opencode/i);
    assert.match(frontmatter, /permission:/);
  }
  assert.match(
    readFileSync(join(PACKAGE, "dist", "assets", "agents", "mapper.md"), "utf8"),
    /mapper_report/,
  );
  assert.match(
    readFileSync(join(PACKAGE, "dist", "assets", "agents", "architect.md"), "utf8"),
    /execution_card/,
  );
  assert.match(
    readFileSync(join(PACKAGE, "dist", "assets", "agents", "worker.md"), "utf8"),
    /worker_report/,
  );
  assert.match(
    readFileSync(join(PACKAGE, "dist", "assets", "agents", "critic.md"), "utf8"),
    /critic_report/,
  );
  const manager = readFileSync(join(PACKAGE, "dist", "assets", "agents", "manager.md"), "utf8");
  const critic = readFileSync(join(PACKAGE, "dist", "assets", "agents", "critic.md"), "utf8");
  const review = readFileSync(join(PACKAGE, "dist", "assets", "agents", "review.md"), "utf8");
  assert.match(manager, /fresh Markdown preview and fresh approval/);
  assert.match(manager, /never ask worker to diagnose or fix critic findings/);
  assert.match(critic, /Do not edit files,[\s\S]*direct worker remediation/);
  assert.match(review, /exact[\s\S]*task allowlist/);
  assert.doesNotMatch(`${manager}\n${review}`, /critic-\*/);
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
    assert.equal(first.operations.filter((item) => item.operation === "create").length, 49);
    await assert.rejects(lstat(join(home, ".config")), { code: "ENOENT" });
    await install("global", project, home);
    assert.equal(readdirSync(join(home, ".config", "opencode", "agents")).length, 6);
    assert.equal(readdirSync(join(home, ".config", "opencode", "commands")).length, 33);
    assert.equal(readdirSync(join(home, ".config", "opencode", "plugins")).length, 7);
    for (const name of ["background-attempts", "schedule", "autonomy-policy"]) {
      const installed = await readFile(
        join(home, ".config", "opencode", "plugins", `${name}.js`),
        "utf8",
      );
      const packaged = await readFile(
        join(PACKAGE, "dist", "assets", "plugins", `${name}.js`),
        "utf8",
      );
      assert.equal(installed, packaged);
      assert.match(installed, /plugin\(input, \{ enabled: false \}\)/);
      assert.doesNotMatch(installed, /enabled: true/);
    }
    await assert.rejects(lstat(join(home, ".config", "opencode", "opencode.json")), {
      code: "ENOENT",
    });
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
    await assert.rejects(
      apply("install", "project", stale.digest, project, home),
      (error) => error instanceof InstallerError && error.code === "stale_plan",
    );
    const collision = await preview("install", "project", project, home);
    assert.deepEqual(
      collision.operations.find((item) => item.path === "agents/manager.md"),
      {
        path: "agents/manager.md",
        operation: "conflict",
        reason: "exact-name user-owned collision",
      },
    );
    await assert.rejects(
      apply("install", "project", collision.digest, project, home),
      (error) => error instanceof InstallerError && error.code === "conflict",
    );
    assert.equal(
      await readFile(join(project, ".opencode", "agents", "manager.md"), "utf8"),
      "user\n",
    );

    const separate = join(directory, "separate");
    await mkdir(join(separate, ".opencode"), { recursive: true });
    symlinkSync(join(directory, "outside"), join(separate, ".opencode", "agents"));
    await assert.rejects(
      preview("install", "project", separate, home),
      (error) => error instanceof InstallerError && error.code === "unsafe_path",
    );
    await writeFile(
      join(separate, ".opencode", ".skills-opencode-manifest.json"),
      JSON.stringify({
        schema_version: 1,
        package: "@kisev/skills-opencode",
        version: "1.0.0",
        files: { "../outside": { sha256: "0".repeat(64) } },
      }),
    );
    await assert.rejects(
      preview("uninstall", "project", separate, home),
      (error) => error instanceof InstallerError && error.code === "unsafe_path",
    );

    const nonregular = join(directory, "nonregular");
    await mkdir(join(nonregular, ".opencode", "agents", "manager.md"), { recursive: true });
    await assert.rejects(
      preview("install", "project", nonregular, home),
      (error) => error instanceof InstallerError && error.code === "unsafe_path",
    );
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
    const manifest = join(root, ".skills-opencode-manifest.json");
    const before = await readFile(manifest);
    const repeat = await preview("install", "project", project, home);
    assert.ok(repeat.operations.every((item) => item.operation === "unchanged"));
    await apply("install", "project", repeat.digest, project, home);
    assert.deepEqual(await readFile(manifest), before);
    assert.equal(applied.operations.filter((item) => item.operation === "create").length, 49);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("installer final validation covers unchanged generic assets", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const target = join(project, ".opencode", "commands", "askme.md");
    const plan = await preview("install", "project", project, home);
    await assert.rejects(
      apply("install", "project", plan.digest, project, home, {
        validateFinal: async () => writeFile(target, "concurrent user change\n"),
      }),
      (error) => error instanceof InstallerError && error.code === "rolled_back",
    );
    assert.equal(await readFile(target, "utf8"), "concurrent user change\n");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("installer final validation requires the exact generic manifest", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const manifestPath = join(project, ".opencode", ".skills-opencode-manifest.json");
    const plan = await preview("install", "project", project, home);
    await assert.rejects(
      apply("install", "project", plan.digest, project, home, {
        validateFinal: async () => {
          const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
          manifest.version = "concurrent-change";
          await writeFile(manifestPath, `${JSON.stringify(manifest)}\n`);
        },
      }),
      (error) => error instanceof InstallerError && error.code === "rolled_back",
    );
    assert.equal(JSON.parse(await readFile(manifestPath, "utf8")).version, "concurrent-change");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("package-only upgrade requires restart while same-version reinstall does not", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const root = join(project, ".opencode");
    const genericPath = join(root, ".skills-opencode-manifest.json");
    const semanticPath = join(root, ".skills-opencode", "agent-profiles.manifest.json");
    const generic = JSON.parse(await readFile(genericPath, "utf8"));
    const semantic = JSON.parse(await readFile(semanticPath, "utf8"));
    const expectedVersion = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8")).version;
    generic.version = "previous-version";
    semantic.package_version = "previous-version";
    await writeFile(genericPath, `${JSON.stringify(generic)}\n`);
    await writeFile(semanticPath, `${JSON.stringify(semantic)}\n`);

    const upgrade = await preview("install", "project", project, home);
    assert.equal(upgrade.requires_restart, true);
    assert.ok(
      upgrade.operations
        .filter((item) => item.operation !== "unchanged")
        .every((item) => item.path.startsWith(".skills-opencode")),
    );
    await apply("install", "project", upgrade.digest, project, home);
    assert.equal(JSON.parse(await readFile(genericPath, "utf8")).version, expectedVersion);
    assert.equal(JSON.parse(await readFile(semanticPath, "utf8")).package_version, expectedVersion);

    const repeat = await preview("install", "project", project, home);
    assert.equal(repeat.requires_restart, false);
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
    const manifestPath = join(root, ".skills-opencode-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    manifest.files["commands/retired.md"] = {
      sha256: createHash("sha256").update(content).digest("hex"),
    };
    await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
    const plan = await preview("install", "project", project, home);
    assert.equal(
      plan.operations.find((item) => item.path === "commands/retired.md").operation,
      "remove",
    );
    await apply("install", "project", plan.digest, project, home);
    await assert.rejects(lstat(retired), { code: "ENOENT" });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("upgrade retires unchanged goal lifecycle assets and preserves modified ones as conflicts", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await Promise.all([mkdir(project), mkdir(home)]);
    await install("project", project, home);
    const root = join(project, ".opencode");
    const manifestPath = join(root, ".skills-opencode-manifest.json");
    const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
    const retired = {
      "commands/goal-start.md": "legacy command\n",
      "plugins/goal-loop.js": "legacy plugin\n",
    };
    for (const [relativePath, content] of Object.entries(retired)) {
      const target = join(root, relativePath);
      await mkdir(resolve(target, ".."), { recursive: true });
      await writeFile(target, content);
      manifest.files[relativePath] = { sha256: createHash("sha256").update(content).digest("hex") };
    }
    await writeFile(manifestPath, `${JSON.stringify(manifest)}\n`);
    const removal = await preview("install", "project", project, home);
    assert.equal(
      removal.operations.find((item) => item.path === "commands/goal-start.md")?.operation,
      "archive-pending",
    );
    assert.equal(
      removal.operations.find((item) => item.path === "plugins/goal-loop.js")?.operation,
      "remove",
    );
    await apply("install", "project", removal.digest, project, home);
    assert.equal(await readFile(join(root, "commands/goal-start.md"), "utf8"), retired["commands/goal-start.md"]);
    await assert.rejects(lstat(join(root, "plugins/goal-loop.js")), { code: "ENOENT" });

    const modifiedPath = "commands/goal-prepare.md";
    const original = "legacy managed command\n";
    const modified = "user modified command\n";
    const target = join(root, modifiedPath);
    await writeFile(target, modified);
    const current = JSON.parse(await readFile(manifestPath, "utf8"));
    current.files[modifiedPath] = { sha256: createHash("sha256").update(original).digest("hex") };
    await writeFile(manifestPath, `${JSON.stringify(current)}\n`);
    const conflict = await preview("install", "project", project, home);
    assert.deepEqual(
      conflict.operations.find((item) => item.path === modifiedPath),
      {
        path: modifiedPath,
        operation: "conflict",
        reason: "managed_file_changed",
        sha256: createHash("sha256").update(modified).digest("hex"),
      },
    );
    await assert.rejects(
      apply("install", "project", conflict.digest, project, home),
      (error) => error instanceof InstallerError && error.code === "conflict",
    );
    assert.equal(await readFile(target, "utf8"), modified);
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
    assert.ok(plan.operations.filter((item) => item.operation === "remove").length >= 40);
    assert.deepEqual(
      plan.operations.find((item) => item.path === "commands/askme.md").operation,
      "conflict",
    );
    await apply("uninstall", "project", plan.digest, project, home);
    assert.equal(await readFile(changed, "utf8"), "user change\n");
    await assert.rejects(lstat(join(project, ".opencode", "agents", "manager.md")), {
      code: "ENOENT",
    });
    const manifest = JSON.parse(
      await readFile(join(project, ".opencode", ".skills-opencode-manifest.json"), "utf8"),
    );
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
    await assert.rejects(
      hooks["tool.execute.before"](
        { tool: "task", sessionID: "missing" },
        { args: { agent: "worker" } },
      ),
      /active routing receipt/,
    );
    const worker = capable("worker", ["read", "write", "verify"], ["read", "edit", "bash"]);
    const routeInput = {
      category: "implementation",
      task: "Implement one scoped change",
      requirements: [],
      agents: [worker],
    };
    const decision = JSON.parse(
      await hooks.tool.route.execute({ action: "preview", ...routeInput }, { sessionID: "bound" }),
    );
    await hooks.tool.route.execute(
      { action: "dispatch", ...routeInput, decision },
      { sessionID: "bound" },
    );
    await assert.rejects(
      hooks["tool.execute.before"](
        { tool: "task", sessionID: "bound" },
        { args: { subagent_type: "critic" } },
      ),
      /does not match/,
    );
    await hooks["tool.execute.before"](
      { tool: "task", sessionID: "bound" },
      { args: { subagent_type: "worker" } },
    );
    const gate = new RoutingGate();
    const input = { category: "implementation", requirements: [], agents: [worker] };
    const selected = gate.preview(input);
    assert.equal(selected.agent, "worker");
    assert.throws(() => gate.dispatch(input, { ...selected, decision_digest: "stale" }), /stale/);
    gate.grant("session", gate.dispatch(input, selected));
    assert.throws(() => gate.consume("session", "critic"), /does not match/);
    gate.consume("session", "worker");
    assert.throws(() => gate.consume("session", "worker"), /active routing receipt/);
    const routing = resolveRouting({
      category: "exploration",
      requirements: [],
      agents: [
        capable("mapper", ["read", "search"], ["read", "glob", "grep"]),
        { ...capable("architect", ["read", "search"], ["read", "glob", "grep"]), available: false },
      ],
    });
    assert.equal(routing.agent, "mapper");
    assert.deepEqual(routing.alternatives, [
      { agent: "architect", excluded_reasons: ["agent_unavailable"] },
    ]);
    assert.equal(readdirSync(directory).length, 0);
    const packageJson = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
    for (const lifecycle of ["preinstall", "install", "postinstall", "prepack", "prepare"])
      assert.equal(packageJson.scripts[lifecycle], undefined);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("routing receipts bind task requirements card agent revision and expiry", () => {
  const worker = capable("worker", ["read", "write", "verify"], ["read", "edit", "bash"]);
  const card = {
    status: "READY",
    card_id: "card-1",
    revision: 1,
    objective: "Implement the change",
    changed_behavior: ["The requested behavior changes."],
    risks: ["No confirmed risks."],
    write_set: ["src/example.ts"],
    control_markers: [{ path: "src/example.ts", expected: "marker" }],
    decisions: ["Use the existing pattern."],
    steps: [{ path: "src/example.ts", operation: "apply the change" }],
    acceptance_criteria: ["The behavior is implemented."],
    checks: ["npm test"],
    boundaries: { forbidden_paths: ["src/other.ts"] },
  };
  const input = {
    category: "implementation",
    task: "Implement the change",
    requirements: ["verify"],
    agents: [worker],
    execution_card: card,
  };
  const gate = new RoutingGate();
  const decision = gate.dispatch(input, gate.preview(input));
  gate.grant("bound", decision, { task: input.task, requirements: input.requirements, card });
  assert.throws(
    () =>
      gate.consume("bound", "worker", {
        task: "Changed task",
        requirements: input.requirements,
        card,
      }),
    /task/,
  );

  gate.grant("requirements", decision, {
    task: input.task,
    requirements: input.requirements,
    card,
  });
  assert.throws(
    () =>
      gate.consume("requirements", "worker", { task: input.task, requirements: ["read"], card }),
    /requirements/,
  );

  gate.grant("card", decision, { task: input.task, requirements: input.requirements, card });
  assert.throws(
    () =>
      gate.consume("card", "worker", {
        task: input.task,
        requirements: input.requirements,
        card: { ...card, revision: 2 },
      }),
    /execution card/,
  );

  gate.grant("agent", decision, { task: input.task, requirements: input.requirements, card });
  assert.throws(
    () =>
      gate.consume("agent", "critic", { task: input.task, requirements: input.requirements, card }),
    /agent/,
  );

  assert.throws(() => gate.dispatch({ ...input, task: "Changed task" }, decision), /stale/);
  gate.cancel("agent");
  assert.throws(() => gate.consume("agent", "worker"), /active routing receipt/);

  gate.grant("expiry", decision, { task: input.task, requirements: input.requirements, card });
  const now = Date.now;
  Date.now = () => now() + 11 * 60 * 1000;
  try {
    assert.throws(
      () =>
        gate.consume("expiry", "worker", {
          task: input.task,
          requirements: input.requirements,
          card,
        }),
      /expired/,
    );
  } finally {
    Date.now = now;
  }
});

test("execution card validation and lifecycle reject malformed and replay transitions", () => {
  const card = {
    status: "READY",
    card_id: "card-1",
    revision: 1,
    objective: "Implement the change",
    changed_behavior: ["The requested behavior changes."],
    risks: ["No confirmed risks."],
    write_set: ["src/example.ts"],
    control_markers: [{ path: "src/example.ts", expected: "marker" }],
    decisions: ["Use the existing pattern."],
    steps: [{ path: "src/example.ts", operation: "apply the change" }],
    acceptance_criteria: ["The behavior is implemented."],
    checks: ["npm test"],
    boundaries: { forbidden_paths: ["src/other.ts"] },
  };
  assert.equal(validateExecutionCard(card).valid, true);
  assert.equal(validateExecutionCard({ ...card, objective: "" }).failedField, "objective");
  assert.equal(
    validateExecutionCard({ ...card, steps: [{ path: "src/other.ts", operation: "escape" }] })
      .failedField,
    "steps",
  );
  assert.equal(
    validateExecutionCard({ ...card, boundaries: { forbidden_paths: ["src/example.ts"] } })
      .failedField,
    "boundaries",
  );

  const lifecycle = new ExecutionCardLifecycle(card);
  assert.equal(lifecycle.transition("RUNNING", { card_id: "card-1", revision: 1 }), "RUNNING");
  assert.equal(lifecycle.transition("COMPLETED", { card_id: "card-1", revision: 1 }), "COMPLETED");
  assert.equal(lifecycle.transition("APPROVED", { card_id: "card-1", revision: 1 }), "APPROVED");
  assert.throws(
    () => lifecycle.transition("RUNNING", { card_id: "card-1", revision: 1 }),
    /transition/,
  );
  assert.throws(
    () =>
      new ExecutionCardLifecycle({ ...card, revision: 2 }).transition("RUNNING", {
        card_id: "card-1",
        revision: 1,
      }),
    /identity/,
  );
});

test("stateful and Zed plugins are opt-in and create no disabled runtime", async () => {
  const directory = temporary();
  try {
    assert.deepEqual(await backgroundAttempts({}), {});
    assert.deepEqual(await scheduler({}), {});
    assert.deepEqual(await autonomyPolicy({}), {});
    assert.deepEqual(await zedBell(), {});
    assert.deepEqual(await zedClickablePaths(), {});
    assert.equal(readdirSync(directory).length, 0);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("autonomy policy enforces classifications, always-ask, session limits, hourly windows, and fail-closed config", async () => {
  const directory = temporary();
  const originalState = process.env.XDG_STATE_HOME;
  try {
    process.env.XDG_STATE_HOME = join(directory, "state");
    const project = join(directory, "project");
    await mkdir(join(project, ".opencode"), { recursive: true });
    const policy = {
      schema_version: 1,
      max_mutations_per_session: 1,
      max_mutations_per_hour: 1,
      on_exhausted: "ask_pause",
      classifications: [
        { tool: "read", operation: "inspect", class: "read" },
        { tool: "edit", operation: "write", class: "mutate" },
        { tool: "edit", operation: "delete", class: "mutate" },
      ],
      always_ask: [{ tool: "edit", operation: "delete", class: "mutate" }],
    };
    await writeFile(join(project, ".opencode", "autonomy-policy.json"), JSON.stringify(policy));
    let now = 0;
    const hooks = await autonomyPolicy({ directory: project }, { enabled: true, now: () => now });
    const inspect = hooks["permission.ask"];
    const read = { status: "allow" };
    await inspect(
      { permission: "read", tool: "read", sessionID: "s", metadata: { operation: "inspect" } },
      read,
    );
    assert.equal(read.status, "allow");
    const write = { status: "allow" };
    await inspect(
      { permission: "edit", tool: "edit", sessionID: "s", metadata: { operation: "write" } },
      write,
    );
    assert.equal(write.status, "allow");
    const limited = { status: "allow" };
    await inspect(
      { permission: "edit", tool: "edit", sessionID: "s", metadata: { operation: "write" } },
      limited,
    );
    assert.equal(limited.status, "ask");
    const alwaysAsk = { status: "allow" };
    await inspect(
      { permission: "edit", tool: "edit", sessionID: "other", metadata: { operation: "delete" } },
      alwaysAsk,
    );
    assert.equal(alwaysAsk.status, "ask");
    now = 3_600_001;
    const nextHour = { status: "allow" };
    await inspect(
      { permission: "edit", tool: "edit", sessionID: "new", metadata: { operation: "write" } },
      nextHour,
    );
    assert.equal(nextHour.status, "allow");

    await writeFile(
      join(project, ".opencode", "autonomy-policy.json"),
      JSON.stringify({ schema_version: 1 }),
    );
    const invalid = await autonomyPolicy({ directory: project }, { enabled: true });
    const failClosed = { status: "allow" };
    await invalid["permission.ask"](
      { permission: "edit", tool: "edit", sessionID: "invalid", metadata: { operation: "write" } },
      failClosed,
    );
    assert.equal(failClosed.status, "ask");
  } finally {
    if (originalState === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = originalState;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("background attempts enforce parent concurrency and stale cancellation", async () => {
  const directory = temporary();
  const originalState = process.env.XDG_STATE_HOME;
  try {
    process.env.XDG_STATE_HOME = join(directory, "state");
    const project = join(directory, "project");
    await mkdir(project);
    execFileSync("git", ["init", "-q", project]);
    await writeFile(join(project, "README.md"), "test\n");
    execFileSync("git", ["-C", project, "add", "README.md"]);
    execFileSync("git", [
      "-C",
      project,
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.invalid",
      "commit",
      "-qm",
      "initial",
    ]);
    const client = {
      session: {
        create: async () => ({ id: `child-${Math.random()}` }),
        prompt: async () => undefined,
        abort: async () => true,
      },
    };
    const hooks = await backgroundAttempts({ client, directory: project }, { enabled: true });
    const decision = resolveRouting({
      category: "implementation",
      task: "one",
      requirements: [],
      agents: [capable("worker", ["read", "write", "verify"], ["read", "edit", "bash"])],
    });
    const first = JSON.parse(
      await hooks.tool.background_attempts.execute(
        { action: "start", task: "one", category: "implementation", decision },
        { sessionID: "parent" },
      ),
    );
    const secondDecision = resolveRouting({
      category: "implementation",
      task: "two",
      requirements: [],
      agents: [capable("worker", ["read", "write", "verify"], ["read", "edit", "bash"])],
    });
    const second = JSON.parse(
      await hooks.tool.background_attempts.execute(
        { action: "start", task: "two", category: "implementation", decision: secondDecision },
        { sessionID: "parent" },
      ),
    );
    const firstStatus = JSON.parse(
      await hooks.tool.background_attempts.execute(
        { action: "status", attempt_id: first.attempt_id },
        { sessionID: "parent" },
      ),
    );
    const secondStatus = JSON.parse(
      await hooks.tool.background_attempts.execute(
        { action: "status", attempt_id: second.attempt_id },
        { sessionID: "parent" },
      ),
    );
    assert.equal(firstStatus.status, "running");
    assert.equal(secondStatus.status, "queued");
    await assert.rejects(
      hooks.tool.background_attempts.execute(
        {
          action: "cancel",
          attempt_id: first.attempt_id,
          expected_revision: 0,
          expected_status: "running",
        },
        { sessionID: "parent" },
      ),
      /changed since cancellation preview/,
    );
    const cancelled = JSON.parse(
      await hooks.tool.background_attempts.execute(
        {
          action: "cancel",
          attempt_id: first.attempt_id,
          expected_revision: 1,
          expected_status: "running",
        },
        { sessionID: "parent" },
      ),
    );
    assert.equal(cancelled.status, "cancelled");
  } finally {
    if (originalState === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = originalState;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("scheduler seeds slots and does not replay missed intervals", async () => {
  const directory = temporary();
  const originalState = process.env.XDG_STATE_HOME;
  try {
    process.env.XDG_STATE_HOME = join(directory, "state");
    const project = join(directory, "project");
    await mkdir(project);
    const digest = createHash("sha256").update(resolve(project)).digest("hex");
    const definitions = join(
      process.env.XDG_STATE_HOME,
      "opencode",
      "skills",
      "schedule",
      digest,
      "definitions",
    );
    await mkdir(definitions, { recursive: true });
    await writeFile(
      join(definitions, "hourly.json"),
      JSON.stringify({
        schema_version: 1,
        id: "hourly",
        name: "Hourly",
        schedule: "every: 1h",
        agent: "worker",
        model: "model",
        token_budget: 0,
        max_runtime: 60,
        prompt: "inspect",
        enabled: true,
      }),
    );
    let current = 0;
    let starts = 0;
    const hooks = await scheduler(
      {
        client: {
          session: {
            create: async () => {
              starts += 1;
              return { id: "scheduled" };
            },
            prompt: async () => undefined,
          },
        },
        directory: project,
      },
      { enabled: true, clock: () => current },
    );
    await hooks.event({ event: { type: "session.created" } });
    current = 24 * 60 * 60 * 1000;
    await hooks.event({ event: { type: "session.created" } });
    assert.equal(starts, 1);
    await hooks.event({ event: { type: "session.created" } });
    assert.equal(starts, 1);
  } finally {
    if (originalState === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = originalState;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("managed worktree lifecycle rejects unknown and dirty paths without deleting state", async () => {
  const directory = temporary();
  const originalState = process.env.XDG_STATE_HOME;
  try {
    process.env.XDG_STATE_HOME = join(directory, "state");
    const project = join(directory, "project");
    await mkdir(project);
    execFileSync("git", ["init", "-q", project]);
    await writeFile(join(project, "README.md"), "test\n");
    execFileSync("git", ["-C", project, "add", "README.md"]);
    execFileSync("git", [
      "-C",
      project,
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.invalid",
      "commit",
      "-qm",
      "initial",
    ]);
    const unknown = join(directory, "unknown");
    await mkdir(unknown);
    await assert.rejects(
      worktreeCreate({ project, workspace_id: "unknown", path: unknown }),
      /unknown/,
    );
    const first = await worktreeCreate({ project, workspace_id: "managed" });
    const repeated = await worktreeCreate({ project, workspace_id: "managed" });
    assert.equal(repeated.path, first.path);
    await writeFile(join(first.path, "changed.txt"), "dirty\n");
    assert.equal((await worktreeStatus(project, "managed")).status, "blocked");
    assert.equal((await worktreeRelease(project, "managed")).status, "blocked");
    assert.equal((await worktreeRecover(project)).blocked, 1);
  } finally {
    if (originalState === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = originalState;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("package catalog and doctor tools are strictly observational", async () => {
  const hooks = await plugin({});
  const catalog = JSON.parse(await hooks.tool.capabilities.execute({}, { sessionID: "bound" }));
  const doctor = JSON.parse(await hooks.tool.doctor.execute({}, { sessionID: "bound" }));
  assert.deepEqual(catalog.replacements, ["capabilities", "doctor", "reconcile", "agent_profiles"]);
  assert.equal(doctor.mutations, false);
  assert.ok(!catalog.skills.includes("agent-profiles"));
});

test("published package metadata and tarball expose only the OpenCode integration", async () => {
  const packageJson = JSON.parse(readFileSync(join(PACKAGE, "package.json"), "utf8"));
  assert.equal(packageJson.name, "@kisev/skills-opencode");
  assert.equal(packageJson.version, "2.0.0");
  assert.equal(packageJson.license, "MIT");
  assert.equal(packageJson.repository.type, "git");
  assert.equal(packageJson.repository.url, "git+https://github.com/kisev/skills.git");
  assert.equal(packageJson.repository.directory, "packages/opencode");
  assert.equal(packageJson.homepage, "https://github.com/kisev/skills#readme");
  assert.equal(packageJson.bugs.url, "https://github.com/kisev/skills/issues");
  assert.deepEqual(packageJson.files, ["dist", "README.md"]);
  assert.equal(packageJson.engines.node, ">=22");
  assert.equal(packageJson.exports["."].import, "./dist/index.js");
  assert.equal(packageJson.bin["skills-opencode"], "./dist/cli.js");
  const invalid = spawnSync(
    process.execPath,
    [join(PACKAGE, "dist", "cli.js"), "install", "--dry-run", "--json"],
    { encoding: "utf8" },
  );
  assert.equal(invalid.status, 2);
  assert.equal(JSON.parse(invalid.stdout).error.code, "invalid_input");
  const humanInvalid = spawnSync(
    process.execPath,
    [join(PACKAGE, "dist", "cli.js"), "install", "--dry-run"],
    { encoding: "utf8" },
  );
  assert.equal(humanInvalid.status, 2);
  assert.equal(humanInvalid.stdout, "");
  assert.match(humanInvalid.stderr, /^Error \[invalid_input\]:/);
  const hostileArgument = "bad\u001b[31m\u0085\u061c\u2028\u2029\u202e\ufeff";
  const hostileInvalid = spawnSync(
    process.execPath,
    [join(PACKAGE, "dist", "cli.js"), "install", hostileArgument],
    { encoding: "utf8" },
  );
  assert.equal(hostileInvalid.status, 2);
  for (const escaped of ["\\x1b", "\\x85", "\\u061c", "\\u2028", "\\u2029", "\\u202e", "\\ufeff"])
    assert.ok(hostileInvalid.stderr.includes(escaped), escaped);
  for (const code of [0x1b, 0x85, 0x061c, 0x2028, 0x2029, 0x202e, 0xfeff])
    assert.equal(hostileInvalid.stderr.includes(String.fromCodePoint(code)), false);
  const directory = temporary();
  try {
    const packed = JSON.parse(
      execFileSync("npm", ["pack", "--json", "--pack-destination", directory], {
        cwd: PACKAGE,
        encoding: "utf8",
      }),
    );
    const tarball = join(directory, packed[0].filename);
    const filenames = execFileSync("tar", ["-tzf", tarball], { encoding: "utf8" })
      .trim()
      .split("\n");
    assert.ok(filenames.includes("package/package.json"));
    assert.ok(filenames.includes("package/README.md"));
    assert.ok(filenames.some((name) => name.startsWith("package/dist/")));
    for (const forbidden of [
      "package/test/",
      "package/tests/",
      "package/node_modules/",
      "package/skills/",
    ]) {
      assert.equal(
        filenames.some((name) => name.startsWith(forbidden)),
        false,
        forbidden,
      );
    }
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

test("reconcile blocks irreversible cleanup for archive-pending assets", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    const root = join(project, ".agents", "skills", "attempt");
    await mkdir(home);
    const retired = execFileSync(
      "git",
      ["show", "5f09d504758b0e99ad9c0306df796411fbcf0f4a:skills/attempt/SKILL.md"],
      { cwd: REPOSITORY },
    );
    await mkdir(root, { recursive: true });
    await writeFile(join(root, "SKILL.md"), retired);
    const plan = await previewReconcile("project", project, home);
    assert.equal(plan.operations.length, 0);
    assert.equal(plan["archive-pending"].length, 1);
    await assert.rejects(
      applyReconcile("project", plan.digest, project, home),
      (error) => error.code === "archive_pending",
    );
    assert.deepEqual(await readFile(join(root, "SKILL.md")), retired);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("reconcile leaves historical goal and multi-run state byte-for-byte unchanged", async () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    const root = join(project, ".opencode");
    const state = join(home, ".local", "state", "opencode", "skills");
    const historical = execFileSync(
      "git",
      ["show", "v1.2.0:packages/opencode/assets/commands/goal-start.md"],
      { cwd: REPOSITORY },
    );
    const stateFiles = new Map([
      [join(state, "goal", "historical.json"), Buffer.from('{"status":"historical-goal"}\n')],
      [join(state, "multi-run", "historical.json"), Buffer.from('{"status":"historical-group"}\n')],
    ]);
    await mkdir(join(root, "commands"), { recursive: true });
    await mkdir(home);
    for (const [path, content] of stateFiles) {
      await mkdir(resolve(path, ".."), { recursive: true });
      await writeFile(path, content);
    }
    await writeFile(join(root, "commands", "goal-start.md"), historical);
    await writeFile(
      join(root, ".skills-opencode-manifest.json"),
      JSON.stringify({
        schema_version: 1,
        package: "@kisev/skills-opencode",
        version: "1.2.0",
        files: {
          "commands/goal-start.md": {
            sha256: createHash("sha256").update(historical).digest("hex"),
          },
        },
      }),
    );
    const plan = await previewReconcile("project", project, home);
    assert.equal(plan.diagnostic_state_only.length, 2);
    assert.equal(plan["archive-pending"].length, 1);
    await assert.rejects(
      applyReconcile("project", plan.digest, project, home),
      (error) => error.code === "archive_pending",
    );
    assert.deepEqual(await readFile(join(root, "commands", "goal-start.md")), historical);
    for (const [path, content] of stateFiles) assert.deepEqual(await readFile(path), content);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("reconcile CLI returns stable JSON and a ready confirmation command", () => {
  const directory = temporary();
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    mkdirSync(project);
    mkdirSync(home);
    const env = {
      ...process.env,
      HOME: home,
      XDG_CONFIG_HOME: join(home, ".config"),
      XDG_STATE_HOME: join(home, ".state"),
    };
    const json = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist", "cli.js"), "reconcile", "--scope", "project", "--dry-run", "--json"],
      { cwd: project, env, encoding: "utf8" },
    );
    assert.equal(json.status, 0);
    const parsed = JSON.parse(json.stdout);
    assert.equal(parsed.status, "ok");
    assert.equal(parsed.applied, false);
    assert.equal(parsed.plan.domain, "reconcile");
    const human = spawnSync(
      process.execPath,
      [join(PACKAGE, "dist", "cli.js"), "reconcile", "--scope", "project", "--dry-run"],
      { cwd: project, env, encoding: "utf8" },
    );
    assert.equal(human.status, 0);
    assert.match(
      human.stdout,
      /npm exec -- skills-opencode reconcile --scope project --confirm [a-f0-9]{64}/,
    );
    const invalid = spawnSync(
      process.execPath,
      [
        join(PACKAGE, "dist", "cli.js"),
        "reconcile",
        "--scope",
        "project",
        "--dry-run",
        "--confirm",
        "0".repeat(64),
        "--json",
      ],
      { cwd: project, env, encoding: "utf8" },
    );
    assert.equal(invalid.status, 2);
    assert.equal(JSON.parse(invalid.stdout).error.code, "invalid_input");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

test("reconcile receipts reject stale, tampered, expired, and replayed confirmations", async () => {
  const directory = temporary();
  const originalNow = Date.now;
  try {
    const project = join(directory, "project");
    const home = join(directory, "home");
    await mkdir(project);
    await mkdir(home);
    const stale = await previewReconcile("project", project, home);
    await mkdir(join(project, ".agents", "skills", "unknown"), { recursive: true });
    await writeFile(
      join(project, ".agents", "skills", "unknown", "SKILL.md"),
      "changed after preview\n",
    );
    await assert.rejects(
      applyReconcile("project", stale.digest, project, home),
      (error) => error instanceof ReconcileError && error.code === "stale_plan",
    );

    const tamperedProject = join(directory, "tampered-project");
    await mkdir(tamperedProject);
    const tampered = await previewReconcile("project", tamperedProject, home);
    const receiptPath = join(lifecycleRoot("project", tamperedProject, home), "receipt.json");
    const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
    receipt.digest = "0".repeat(64);
    await writeFile(receiptPath, JSON.stringify(receipt));
    await assert.rejects(
      applyReconcile("project", tampered.digest, tamperedProject, home),
      (error) => error instanceof ReconcileError && error.code === "invalid_receipt",
    );

    const expiredProject = join(directory, "expired-project");
    await mkdir(expiredProject);
    Date.now = () => 0;
    const expired = await previewReconcile("project", expiredProject, home);
    Date.now = originalNow;
    await assert.rejects(
      applyReconcile("project", expired.digest, expiredProject, home),
      (error) => error instanceof ReconcileError && error.code === "confirmation_expired",
    );

    const replayProject = join(directory, "replay-project");
    await mkdir(replayProject);
    const replay = await previewReconcile("project", replayProject, home);
    await applyReconcile("project", replay.digest, replayProject, home);
    await assert.rejects(
      applyReconcile("project", replay.digest, replayProject, home),
      (error) => error instanceof ReconcileError && error.code === "confirmation_consumed",
    );
  } finally {
    Date.now = originalNow;
    rmSync(directory, { recursive: true, force: true });
  }
});
