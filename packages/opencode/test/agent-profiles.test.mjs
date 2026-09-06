import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { chmodSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import plugin from "../dist/index.js";

import {
  AgentProfileError,
  applyAgentProfileChange,
  availableModels,
  availableModelVariants,
  listAgentProfiles,
  previewAgentProfileChange,
} from "../dist/agent-profiles.js";
import { apply, preview } from "../dist/installer.js";
import {
  LifecycleError,
  appendPrivate,
  applyTransaction,
  consumeReceipt,
  deploymentRoot,
  lifecycleRoot,
  saveReceipt,
  sha256,
  withLifecycleLock,
} from "../dist/lifecycle.js";

const PACKAGE = resolve(import.meta.dirname, "..");
const REPOSITORY = resolve(PACKAGE, "../..");
const FIXED = ["architect", "critic", "manager", "mapper", "review", "worker"];

function temporary() {
  return mkdtempSync(join(tmpdir(), "skills-opencode-agents-"));
}

async function roots() {
  const directory = temporary();
  const project = join(directory, "project");
  const home = join(directory, "home");
  await Promise.all([mkdir(project), mkdir(home)]);
  return { directory, project, home, root: join(project, ".opencode") };
}

async function confirmedInstall(project, home) {
  const plan = await preview("install", "project", project, home);
  await apply("install", "project", plan.digest, project, home);
  return plan;
}

async function confirmedProfile(request, project, home, options) {
  const plan = await previewAgentProfileChange(request, "project", project, home);
  return {
    plan,
    result: await applyAgentProfileChange(request, "project", plan.digest, project, home, options),
  };
}

async function fileSnapshot(root) {
  const result = {};
  async function visit(directory, prefix = "") {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await visit(path, relative);
      else result[relative] = await readFile(path, "base64");
    }
  }
  try {
    await visit(root);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  return result;
}

test("inventory separates package-owned, managed, user-owned, drift, and collisions", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    await confirmedProfile(
      { action: "critic-add", name: "critic-security", model: "openai/gpt-5", variant: "high" },
      context.project,
      context.home,
    );
    await writeFile(join(context.root, "agents", "notes.md"), "user-owned\n");
    await writeFile(join(context.root, "agents", "manager.md"), "drift\n");

    const inventory = await listAgentProfiles("project", context.project, context.home);
    assert.equal(
      inventory.profiles.find((item) => item.name === "critic-security").ownership,
      "managed",
    );
    assert.equal(inventory.profiles.find((item) => item.name === "manager").state, "drift");
    assert.equal(inventory.profiles.find((item) => item.name === "notes").ownership, "user-owned");
    assert.deepEqual(inventory.drift, ["manager"]);
    assert.deepEqual(inventory.user_owned, ["notes"]);

    const collisionContext = await roots();
    try {
      await mkdir(join(collisionContext.root, "agents"), { recursive: true });
      await writeFile(join(collisionContext.root, "agents", "critic.md"), "user-owned\n");
      const collision = await listAgentProfiles(
        "project",
        collisionContext.project,
        collisionContext.home,
      );
      assert.deepEqual(collision.collisions, ["critic"]);
    } finally {
      rmSync(collisionContext.directory, { recursive: true, force: true });
    }
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("model catalog and variants use cached opencode commands without refresh", async () => {
  const directory = temporary();
  const executable = join(directory, "opencode");
  const originalPath = process.env.PATH;
  try {
    await writeFile(
      executable,
      `#!/bin/sh
if [ "$1" = "models" ] && [ "$3" = "--verbose" ]; then
  printf '%s\n' 'openai/gpt-5' '{"variants":{"none":{},"low":{},"high":{}}}'
else
  printf '%s\n' 'anthropic/claude' 'openai/gpt-5'
fi
`,
    );
    chmodSync(executable, 0o755);
    process.env.PATH = directory;
    assert.deepEqual(await availableModels(), ["anthropic/claude", "openai/gpt-5"]);
    assert.deepEqual(await availableModelVariants("openai/gpt-5"), ["none", "low", "high"]);
    process.env.PATH = join(directory, "missing");
    await assert.rejects(
      availableModels(),
      (error) =>
        error instanceof AgentProfileError &&
        error.code === "catalog_unavailable" &&
        /explicit provider\/model/.test(error.message),
    );
  } finally {
    if (originalPath === undefined) delete process.env.PATH;
    else process.env.PATH = originalPath;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("model and variant configuration survives package install", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const request = {
      action: "model-set",
      name: "manager",
      model: "openai/gpt-5",
      variant: "high",
    };
    const changed = await confirmedProfile(request, context.project, context.home);
    assert.equal(changed.result.requires_restart, true);
    assert.match(
      await readFile(join(context.root, "agents", "manager.md"), "utf8"),
      /model: openai\/gpt-5\nvariant: high/,
    );

    const upgrade = await preview("install", "project", context.project, context.home);
    await apply("install", "project", upgrade.digest, context.project, context.home);
    const config = JSON.parse(
      await readFile(join(context.root, ".skills-opencode", "agent-profiles.json"), "utf8"),
    );
    assert.deepEqual(config.fixed.manager, { model: "openai/gpt-5", variant: "high" });
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("additional critic atomically changes the exact manager and review pools", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const added = await confirmedProfile(
      { action: "critic-add", name: "critic-security", model: "anthropic/claude" },
      context.project,
      context.home,
    );
    assert.equal(added.result.requires_restart, true);
    assert.deepEqual(
      added.plan.operations
        .filter((item) => item.operation !== "unchanged")
        .map((item) => item.path),
      [
        ".skills-opencode/agent-profiles.json",
        ".skills-opencode/agent-profiles.manifest.json",
        "agents/critic-security.md",
        "agents/manager.md",
        "agents/review.md",
      ],
    );
    for (const name of ["manager", "review"]) {
      const content = await readFile(join(context.root, "agents", `${name}.md`), "utf8");
      assert.match(content, /critic: allow/);
      assert.match(content, /critic-security: allow/);
      assert.doesNotMatch(content, /critic-\*/);
    }
    const manifest = JSON.parse(
      await readFile(
        join(context.root, ".skills-opencode", "agent-profiles.manifest.json"),
        "utf8",
      ),
    );
    assert.deepEqual(manifest.critic_pool, ["critic", "critic-security"]);

    await assert.rejects(
      previewAgentProfileChange(
        { action: "critic-remove", name: "critic" },
        "project",
        context.project,
        context.home,
      ),
      (error) => error instanceof AgentProfileError && error.code === "immutable_profile",
    );
    await confirmedProfile(
      { action: "critic-remove", name: "critic-security" },
      context.project,
      context.home,
    );
    await assert.rejects(readFile(join(context.root, "agents", "critic-security.md")), {
      code: "ENOENT",
    });
    for (const name of ["manager", "review"])
      assert.doesNotMatch(
        await readFile(join(context.root, "agents", `${name}.md`), "utf8"),
        /critic-security/,
      );
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("exact-name collision blocks apply and preserves user-owned content", async () => {
  const context = await roots();
  try {
    await mkdir(join(context.root, "agents"), { recursive: true });
    const target = join(context.root, "agents", "critic-security.md");
    await writeFile(target, "user-owned\n");
    const request = { action: "critic-add", name: "critic-security", model: "openai/gpt-5" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    assert.equal(
      plan.operations.find((item) => item.path === "agents/critic-security.md").operation,
      "conflict",
    );
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home),
      (error) => error instanceof AgentProfileError && error.code === "collision",
    );
    assert.equal(await readFile(target, "utf8"), "user-owned\n");
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("receipts expire, are one-use, and reject stale inventory", async () => {
  const context = await roots();
  try {
    const state = lifecycleRoot("project", context.project, context.home);
    const root = deploymentRoot("project", context.project, context.home);
    const receipt = await saveReceipt(state, "test", "project", root, { value: 1 }, 1_000);
    await assert.rejects(
      consumeReceipt(
        state,
        { digest: receipt.digest, kind: "test", scope: "project", root },
        1_000 + 10 * 60 * 1000 + 1,
      ),
      (error) => error instanceof LifecycleError && error.code === "confirmation_expired",
    );
    const fresh = await saveReceipt(state, "test", "project", root, { value: 2 }, 2_000_000);
    assert.deepEqual(
      await consumeReceipt(
        state,
        { digest: fresh.digest, kind: "test", scope: "project", root },
        2_000_001,
      ),
      { value: 2 },
    );
    await assert.rejects(
      consumeReceipt(
        state,
        { digest: fresh.digest, kind: "test", scope: "project", root },
        2_000_002,
      ),
      (error) => error instanceof LifecycleError && error.code === "confirmation_consumed",
    );

    await confirmedInstall(context.project, context.home);
    const request = { action: "model-set", name: "worker", model: "openai/gpt-5" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    await writeFile(join(context.root, "agents", "notes.md"), "appeared after preview\n");
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home),
      (error) => error instanceof AgentProfileError && error.code === "stale_plan",
    );
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("concurrent apply permits only one transaction", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const request = { action: "model-set", name: "worker", model: "openai/gpt-5" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    const settled = await Promise.allSettled([
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home),
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home),
    ]);
    assert.equal(settled.filter((item) => item.status === "fulfilled").length, 1);
    assert.equal(settled.filter((item) => item.status === "rejected").length, 1);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("injected failure rolls back every published file and final validation", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const before = await fileSnapshot(context.root);
    const request = { action: "critic-add", name: "critic-security", model: "openai/gpt-5" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home, {
        afterPublish: (published) => (published === 2 ? "fail" : "continue"),
      }),
      (error) => error instanceof LifecycleError && error.code === "rolled_back",
    );
    assert.deepEqual(await fileSnapshot(context.root), before);

    const retry = await previewAgentProfileChange(
      request,
      "project",
      context.project,
      context.home,
    );
    await assert.rejects(
      applyAgentProfileChange(request, "project", retry.digest, context.project, context.home, {
        validateFinal: async () => {
          throw new Error("injected final validation failure");
        },
      }),
      (error) => error instanceof LifecycleError && error.code === "rolled_back",
    );
    assert.deepEqual(await fileSnapshot(context.root), before);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("interrupted transaction recovers before requiring a fresh plan", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const before = await fileSnapshot(context.root);
    const request = { action: "critic-add", name: "critic-security", model: "openai/gpt-5" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home, {
        afterPublish: (published) => (published === 2 ? "interrupt" : "continue"),
      }),
      (error) => error instanceof LifecycleError && error.code === "test_interruption",
    );
    await assert.rejects(
      previewAgentProfileChange(request, "project", context.project, context.home),
      (error) => error instanceof AgentProfileError && error.code === "recovered_transaction",
    );
    assert.deepEqual(await fileSnapshot(context.root), before);
    const fresh = await previewAgentProfileChange(
      request,
      "project",
      context.project,
      context.home,
    );
    assert.match(fresh.digest, /^[a-f0-9]{64}$/);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("recovery never overwrites a target changed after interruption", async () => {
  const context = await roots();
  try {
    await mkdir(context.root, { recursive: true });
    const state = lifecycleRoot("project", context.project, context.home);
    const mutation = {
      path: "agents/worker.md",
      operation: "write",
      content: Buffer.from("published\n"),
      mode: 0o600,
      expected: { absent: true },
    };
    await assert.rejects(
      applyTransaction(context.root, state, [mutation], {
        afterPublish: () => "interrupt",
      }),
      (error) => error instanceof LifecycleError && error.code === "test_interruption",
    );
    await writeFile(join(context.root, "agents", "worker.md"), "external change\n");
    await assert.rejects(
      previewAgentProfileChange({ action: "reconcile" }, "project", context.project, context.home),
      (error) => error instanceof LifecycleError && error.code === "recovery_conflict",
    );
    assert.equal(
      await readFile(join(context.root, "agents", "worker.md"), "utf8"),
      "external change\n",
    );
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

for (const changed of ["published", "unpublished"]) {
  test(`rollback preserves an externally changed ${changed} target`, async () => {
    const context = await roots();
    try {
      await mkdir(join(context.root, "agents"), { recursive: true });
      const first = join(context.root, "agents", "first.md");
      const second = join(context.root, "agents", "second.md");
      await writeFile(first, "first before\n");
      await writeFile(second, "second before\n");
      const mutations = [
        {
          path: "agents/first.md",
          operation: "write",
          content: Buffer.from("first transaction\n"),
          mode: 0o600,
          expected: { sha256: sha256(Buffer.from("first before\n")) },
        },
        {
          path: "agents/second.md",
          operation: "write",
          content: Buffer.from("second transaction\n"),
          mode: 0o600,
          expected: { sha256: sha256(Buffer.from("second before\n")) },
        },
      ];
      await assert.rejects(
        applyTransaction(
          context.root,
          lifecycleRoot("project", context.project, context.home),
          mutations,
          {
            afterPublish: (published) => {
              if (published !== 1) return "continue";
              writeFileSync(changed === "published" ? first : second, "external change\n");
              return "fail";
            },
          },
        ),
        (error) => error instanceof LifecycleError && error.code === "rollback_failed",
      );
      assert.equal(
        await readFile(changed === "published" ? first : second, "utf8"),
        "external change\n",
      );
      assert.equal(
        await readFile(changed === "published" ? second : first, "utf8"),
        changed === "published" ? "second before\n" : "first before\n",
      );
    } finally {
      rmSync(context.directory, { recursive: true, force: true });
    }
  });
}

test("rollback never removes a directory created by another process", async () => {
  const context = await roots();
  try {
    await mkdir(context.root, { recursive: true });
    const agents = join(context.root, "agents");
    await assert.rejects(
      applyTransaction(
        context.root,
        lifecycleRoot("project", context.project, context.home),
        [
          {
            path: "agents/worker.md",
            operation: "write",
            content: Buffer.from("transaction\n"),
            mode: 0o600,
            expected: { absent: true },
          },
        ],
        {
          beforePublish: () => mkdirSync(agents),
          afterPublish: () => "fail",
        },
      ),
      (error) => error instanceof LifecycleError && error.code === "rolled_back",
    );
    assert.equal((await lstat(agents)).isDirectory(), true);
    assert.deepEqual(readdirSync(agents), []);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("lock cleanup cannot replace a committed callback result", async () => {
  const context = await roots();
  const state = lifecycleRoot("project", context.project, context.home);
  try {
    const result = await withLifecycleLock(state, async () => {
      chmodSync(state, 0o500);
      return "committed";
    });
    assert.equal(result, "committed");
  } finally {
    chmodSync(state, 0o700);
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("competing stale-lock cleaners never enter concurrently", async () => {
  const context = await roots();
  const state = lifecycleRoot("project", context.project, context.home);
  const lock = join(state, "lifecycle.lock");
  let active = 0;
  let maximum = 0;
  try {
    await mkdir(lock, { recursive: true, mode: 0o700 });
    await writeFile(
      join(lock, "owner.json"),
      `${JSON.stringify({ pid: 2_147_483_647, released: false })}\n`,
      { mode: 0o600 },
    );
    const contender = () =>
      withLifecycleLock(state, async () => {
        active += 1;
        maximum = Math.max(maximum, active);
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 30));
        active -= 1;
        return "acquired";
      });
    const settled = await Promise.allSettled([contender(), contender()]);
    assert.equal(settled.filter((item) => item.status === "fulfilled").length, 1);
    assert.equal(maximum, 1);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("private append rejects an existing public file", async () => {
  const context = await roots();
  const path = join(context.directory, "public.jsonl");
  try {
    await writeFile(path, "existing\n", { mode: 0o644 });
    await assert.rejects(
      appendPrivate(path, { secret: true }),
      (error) => error instanceof LifecycleError && error.code === "unsafe_path",
    );
    assert.equal(await readFile(path, "utf8"), "existing\n");
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("explicit reconcile repairs only semantic-manifest-owned drift", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const manager = join(context.root, "agents", "manager.md");
    await writeFile(manager, "drift\n");
    const modelRequest = { action: "model-set", name: "worker", model: "openai/gpt-5" };
    const blocked = await previewAgentProfileChange(
      modelRequest,
      "project",
      context.project,
      context.home,
    );
    await assert.rejects(
      applyAgentProfileChange(
        modelRequest,
        "project",
        blocked.digest,
        context.project,
        context.home,
      ),
      (error) => error instanceof AgentProfileError && error.code === "drift",
    );
    const reconcile = { action: "reconcile" };
    const repaired = await confirmedProfile(reconcile, context.project, context.home);
    assert.equal(
      repaired.plan.operations.find((item) => item.path === "agents/manager.md").reason,
      "explicit managed profile reconcile",
    );
    assert.doesNotMatch(await readFile(manager, "utf8"), /^drift$/);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("profile final validation requires exact semantic metadata", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const manifestPath = join(context.root, ".skills-opencode", "agent-profiles.manifest.json");
    const request = { action: "reconcile" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home, {
        validateFinal: async () => {
          const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
          manifest.package_version = "concurrent-change";
          await writeFile(manifestPath, `${JSON.stringify(manifest)}\n`);
        },
      }),
      (error) => error instanceof LifecycleError && error.code === "rolled_back",
    );
    assert.equal(
      JSON.parse(await readFile(manifestPath, "utf8")).package_version,
      "concurrent-change",
    );
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("mode-only mutation is fully rolled back", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const manager = join(context.root, "agents", "manager.md");
    chmodSync(manager, 0o644);
    const request = { action: "reconcile" };
    const plan = await previewAgentProfileChange(request, "project", context.project, context.home);
    assert.equal(
      plan.operations.find((item) => item.path === "agents/manager.md").operation,
      "update",
    );
    await assert.rejects(
      applyAgentProfileChange(request, "project", plan.digest, context.project, context.home, {
        validateFinal: async () => {
          throw new Error("injected failure after mode update");
        },
      }),
      (error) => error instanceof LifecycleError && error.code === "rolled_back",
    );
    assert.equal((await lstat(manager)).mode & 0o777, 0o644);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("v1.0.0 ownership migrates only exact manifest and SHA-256 matches", async () => {
  const context = await roots();
  try {
    await mkdir(join(context.root, "agents"), { recursive: true });
    const files = {};
    for (const name of FIXED) {
      const content = execFileSync(
        "git",
        ["show", `v1.0.0:packages/opencode/assets/agents/${name}.md`],
        { cwd: REPOSITORY },
      );
      await writeFile(join(context.root, "agents", `${name}.md`), content);
      files[`agents/${name}.md`] = { sha256: sha256(content) };
    }
    await writeFile(
      join(context.root, ".skills-opencode-manifest.json"),
      `${JSON.stringify({ schema_version: 1, package: "@kisev/skills-opencode", version: "1.0.0", files }, null, 2)}\n`,
    );
    const migration = await preview("install", "project", context.project, context.home);
    assert.ok(
      migration.operations.some(
        (item) => item.path === "agents/manager.md" && item.reason === "v1.0.0 ownership transfer",
      ),
    );
    await apply("install", "project", migration.digest, context.project, context.home);
    const generic = JSON.parse(
      await readFile(join(context.root, ".skills-opencode-manifest.json"), "utf8"),
    );
    assert.equal(
      Object.keys(generic.files).some((path) => path.startsWith("agents/")),
      false,
    );
    const semantic = JSON.parse(
      await readFile(
        join(context.root, ".skills-opencode", "agent-profiles.manifest.json"),
        "utf8",
      ),
    );
    assert.deepEqual(Object.keys(semantic.profiles).sort(), FIXED);

    const mismatch = await roots();
    try {
      await mkdir(join(mismatch.root, "agents"), { recursive: true });
      await writeFile(join(mismatch.root, "agents", "manager.md"), "user drift\n");
      const badFiles = Object.fromEntries(
        FIXED.map((name) => [`agents/${name}.md`, { sha256: "0".repeat(64) }]),
      );
      await writeFile(
        join(mismatch.root, ".skills-opencode-manifest.json"),
        JSON.stringify({
          schema_version: 1,
          package: "@kisev/skills-opencode",
          version: "1.0.0",
          files: badFiles,
        }),
      );
      const blocked = await preview("install", "project", mismatch.project, mismatch.home);
      assert.ok(blocked.operations.some((item) => item.operation === "conflict"));
      await assert.rejects(
        apply("install", "project", blocked.digest, mismatch.project, mismatch.home),
      );
      assert.equal(
        await readFile(join(mismatch.root, "agents", "manager.md"), "utf8"),
        "user drift\n",
      );
    } finally {
      rmSync(mismatch.directory, { recursive: true, force: true });
    }
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("profile paths reject symlink parents and uninstall preserves configuration", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    await confirmedProfile(
      { action: "model-set", name: "worker", model: "openai/gpt-5" },
      context.project,
      context.home,
    );
    const uninstall = await preview("uninstall", "project", context.project, context.home);
    await apply("uninstall", "project", uninstall.digest, context.project, context.home);
    assert.equal(
      JSON.parse(
        await readFile(join(context.root, ".skills-opencode", "agent-profiles.json"), "utf8"),
      ).fixed.worker.model,
      "openai/gpt-5",
    );
    await assert.rejects(readFile(join(context.root, "agents", "worker.md")), { code: "ENOENT" });

    const unsafe = await roots();
    try {
      await mkdir(unsafe.root, { recursive: true });
      const outside = join(unsafe.directory, "outside");
      await mkdir(outside);
      execFileSync("ln", ["-s", outside, join(unsafe.root, "agents")]);
      await assert.rejects(
        listAgentProfiles("project", unsafe.project, unsafe.home),
        (error) => error instanceof LifecycleError && error.code === "unsafe_path",
      );
    } finally {
      rmSync(unsafe.directory, { recursive: true, force: true });
    }
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("uninstall preserves managed agent drift with semantic ownership", async () => {
  const context = await roots();
  try {
    await confirmedInstall(context.project, context.home);
    const manager = join(context.root, "agents", "manager.md");
    await writeFile(manager, "user drift\n");
    const plan = await preview("uninstall", "project", context.project, context.home);
    await apply("uninstall", "project", plan.digest, context.project, context.home);
    assert.equal(await readFile(manager, "utf8"), "user drift\n");
    const manifest = JSON.parse(
      await readFile(
        join(context.root, ".skills-opencode", "agent-profiles.manifest.json"),
        "utf8",
      ),
    );
    assert.deepEqual(Object.keys(manifest.profiles), ["manager"]);
  } finally {
    rmSync(context.directory, { recursive: true, force: true });
  }
});

test("direct CLI and package tool are thin non-LLM profile interfaces", async () => {
  const context = await roots();
  const executable = join(PACKAGE, "dist", "cli.js");
  const previousHome = process.env.HOME;
  const previousState = process.env.XDG_STATE_HOME;
  const environment = {
    ...process.env,
    HOME: context.home,
    XDG_STATE_HOME: join(context.home, ".state"),
  };
  const run = (arguments_) => {
    const result = spawnSync(process.execPath, [executable, ...arguments_], {
      cwd: context.project,
      env: environment,
      encoding: "utf8",
    });
    assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
    return JSON.parse(result.stdout);
  };
  try {
    let plan = run(["install", "--scope", "project", "--dry-run"]).plan;
    assert.equal(
      run(["install", "--scope", "project", "--confirm", plan.digest]).requires_restart,
      true,
    );
    plan = run([
      "agent",
      "configure",
      "manager",
      "--scope",
      "project",
      "--provider",
      "openai",
      "--model",
      "gpt-5",
      "--variant",
      "high",
      "--dry-run",
    ]).plan;
    run([
      "agent",
      "configure",
      "manager",
      "--scope",
      "project",
      "--provider",
      "openai",
      "--model",
      "gpt-5",
      "--variant",
      "high",
      "--confirm",
      plan.digest,
    ]);
    assert.equal(
      run(["agent", "list", "--scope", "project"]).inventory.profiles.find(
        (item) => item.name === "manager",
      ).variant,
      "high",
    );

    process.env.HOME = context.home;
    process.env.XDG_STATE_HOME = join(context.home, ".state");
    const hooks = await plugin({ directory: context.project });
    const listed = JSON.parse(
      await hooks.tool.agent_profiles.execute(
        { action: "list", scope: "project" },
        { sessionID: "profile" },
      ),
    );
    assert.equal(
      listed.inventory.profiles.find((item) => item.name === "manager").model,
      "openai/gpt-5",
    );
    const request = {
      action: "critic_add",
      phase: "preview",
      scope: "project",
      name: "critic-tool",
      model: "anthropic/claude",
    };
    const toolPlan = JSON.parse(
      await hooks.tool.agent_profiles.execute(request, { sessionID: "profile" }),
    ).plan;
    const applied = JSON.parse(
      await hooks.tool.agent_profiles.execute(
        { ...request, phase: "apply", confirmation_digest: toolPlan.digest },
        { sessionID: "profile" },
      ),
    );
    assert.equal(applied.requires_restart, true);
  } finally {
    if (previousHome === undefined) delete process.env.HOME;
    else process.env.HOME = previousHome;
    if (previousState === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previousState;
    rmSync(context.directory, { recursive: true, force: true });
  }
});
