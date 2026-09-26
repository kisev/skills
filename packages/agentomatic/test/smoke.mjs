import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const packageRoot = resolve(import.meta.dirname, "..");
const temporary = mkdtempSync(join(tmpdir(), "agentomatic-smoke-"));
const binary = process.env.OPENCODE_BINARY ?? "opencode";
const selection = [
  "--commands",
  "agents-md",
  "--agents",
  "manager,architect,mapper,worker,review,critic",
  "--plugins",
  "none",
];

function run(command, arguments_, options = {}) {
  const result = spawnSync(command, arguments_, { encoding: "utf8", ...options });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
  return result.stdout;
}

try {
  const project = join(temporary, "project");
  const home = join(temporary, "home");
  await mkdir(project);
  await mkdir(home);
  await writeFile(join(project, "package.json"), '{"private":true}\n');
  const packed = process.env.PACKAGE_TARBALL
    ? null
    : JSON.parse(
        execFileSync("npm", ["pack", "--json", "--pack-destination", temporary], {
          cwd: packageRoot,
          encoding: "utf8",
        }),
      );
  const tarball = process.env.PACKAGE_TARBALL ?? join(temporary, packed[0].filename);
  execFileSync("npm", ["install", "--ignore-scripts", tarball], { cwd: project, encoding: "utf8" });
  const executable = join(project, "node_modules", ".bin", "agentomatic");
  const environment = {
    PATH: process.env.PATH ?? "",
    HOME: home,
    XDG_CONFIG_HOME: join(home, ".config"),
    XDG_STATE_HOME: join(home, ".state"),
  };
  const cli = (arguments_) =>
    JSON.parse(run(executable, [...arguments_, "--json"], { cwd: project, env: environment }));
  const dryRun = cli(["install", "--global", ...selection, "--dry-run"]);
  assert.equal(dryRun.applied, false);
  assert.equal(dryRun.plan.requires_restart, true);
  assert.equal(
    cli(["install", "--global", ...selection, "--confirm", dryRun.plan.digest]).requires_restart,
    true,
  );
  const doctor = spawnSync(executable, ["doctor", "--global", "--json"], {
    cwd: project,
    env: environment,
    encoding: "utf8",
  });
  assert.ok([1, 2].includes(doctor.status));
  assert.equal(JSON.parse(doctor.stdout).mutations, false);
  assert.equal(JSON.parse(doctor.stdout).scope, "global");
  const modelPlan = cli([
    "agent",
    "model-set",
    "manager",
    "--global",
    "--model",
    "opencode/gpt-5-nano",
    "--variant",
    "high",
    "--dry-run",
  ]);
  assert.equal(
    cli([
      "agent",
      "model-set",
      "manager",
      "--global",
      "--model",
      "opencode/gpt-5-nano",
      "--variant",
      "high",
      "--confirm",
      modelPlan.plan.digest,
    ]).requires_restart,
    true,
  );
  const criticPlan = cli([
    "critic",
    "add",
    "smoke",
    "--global",
    "--model",
    "opencode/gpt-5-nano",
    "--dry-run",
  ]);
  cli([
    "critic",
    "add",
    "smoke",
    "--global",
    "--model",
    "opencode/gpt-5-nano",
    "--confirm",
    criticPlan.plan.digest,
  ]);
  const inventory = cli(["agent", "list", "--global"]).inventory;
  assert.equal(inventory.profiles.find((item) => item.name === "manager").variant, "high");
  assert.equal(
    inventory.profiles.find((item) => item.name === "critic-smoke").ownership,
    "managed",
  );
  await writeFile(
    join(project, "opencode.json"),
    JSON.stringify({
      $schema: "https://opencode.ai/config.json",
      plugin: ["@kisev/agentomatic"],
    }),
  );
  const opencodeEnvironment = { ...environment, OPENCODE_CONFIG: join(project, "opencode.json") };
  const agents = run(binary, ["agent", "list"], { cwd: project, env: opencodeEnvironment });
  assert.match(agents, /manager \(primary\)/);
  assert.match(agents, /review \(all\)/);
  const config = run(binary, ["debug", "config"], { cwd: project, env: opencodeEnvironment });
  assert.match(config, /@kisev\/agentomatic/);
  const manifest = JSON.parse(
    await readFile(join(home, ".config", "opencode", ".agentomatic-manifest.json"), "utf8"),
  );
  assert.equal(Object.keys(manifest.files).length, 2);
  assert.equal(
    Object.keys(manifest.files).some((path) => path.startsWith("agents/")),
    false,
  );
  assert.equal(Object.keys(manifest.files).filter((path) => path.startsWith("plugins/")).length, 0);
  assert.equal("commands/rtk-stats.md" in manifest.files, true);
  const semantic = JSON.parse(
    await readFile(
      join(home, ".config", "opencode", ".agentomatic", "agent-profiles.manifest.json"),
      "utf8",
    ),
  );
  assert.deepEqual(semantic.critic_pool, ["critic", "critic-smoke"]);
  process.stdout.write("Packed OpenCode installer smoke test passed\n");
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
