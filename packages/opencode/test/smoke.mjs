import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const packageRoot = resolve(import.meta.dirname, "..");
const temporary = mkdtempSync(join(tmpdir(), "skills-opencode-smoke-"));
const binary = process.env.OPENCODE_BINARY ?? "opencode";

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
  const packed = JSON.parse(execFileSync("npm", ["pack", "--json", "--pack-destination", temporary], { cwd: packageRoot, encoding: "utf8" }));
  const tarball = join(temporary, packed[0].filename);
  execFileSync("npm", ["install", "--ignore-scripts", tarball], { cwd: project, encoding: "utf8" });
  const executable = join(project, "node_modules", ".bin", "skills-opencode");
  const environment = { PATH: process.env.PATH ?? "", HOME: home, XDG_CONFIG_HOME: join(home, ".config"), XDG_STATE_HOME: join(home, ".state") };
  const cli = (arguments_) => JSON.parse(run(executable, [...arguments_, "--json"], { cwd: project, env: environment }));
  const humanPreview = run("npm", ["exec", "--", "skills-opencode", "install", "--scope", "global", "--dry-run"], { cwd: project, env: environment });
  const confirmation = humanPreview.split("\n").find((line) => line.startsWith("  npm exec -- skills-opencode install "))?.trim().split(" ");
  assert.ok(confirmation);
  const humanApply = run(confirmation[0], confirmation.slice(1), { cwd: project, env: environment });
  assert.match(humanApply, /Applied changes:/);
  assert.match(humanApply, /Restart required: yes/);
  const dryRun = cli(["install", "--scope", "global", "--dry-run"]);
  assert.equal(dryRun.applied, false);
  assert.equal(dryRun.plan.requires_restart, false);
  assert.equal(cli(["install", "--scope", "global", "--confirm", dryRun.plan.digest]).requires_restart, false);
  const modelPlan = cli(["agent", "model-set", "manager", "--scope", "global", "--model", "opencode/gpt-5-nano", "--variant", "high", "--dry-run"]);
  assert.equal(cli(["agent", "model-set", "manager", "--scope", "global", "--model", "opencode/gpt-5-nano", "--variant", "high", "--confirm", modelPlan.plan.digest]).requires_restart, true);
  const criticPlan = cli(["critic", "add", "smoke", "--scope", "global", "--model", "opencode/gpt-5-nano", "--dry-run"]);
  cli(["critic", "add", "smoke", "--scope", "global", "--model", "opencode/gpt-5-nano", "--confirm", criticPlan.plan.digest]);
  const inventory = cli(["agent", "list", "--scope", "global"]).inventory;
  assert.equal(inventory.profiles.find((item) => item.name === "manager").variant, "high");
  assert.equal(inventory.profiles.find((item) => item.name === "critic-smoke").ownership, "managed");
  await writeFile(join(project, "opencode.json"), JSON.stringify({ "$schema": "https://opencode.ai/config.json", plugin: ["@kisev/skills-opencode"] }));
  const opencodeEnvironment = { ...environment, OPENCODE_CONFIG: join(project, "opencode.json") };
  const agents = run(binary, ["agent", "list"], { cwd: project, env: opencodeEnvironment });
  assert.match(agents, /manager \(primary\)/);
  assert.match(agents, /review \(primary\)/);
  const config = run(binary, ["debug", "config"], { cwd: project, env: opencodeEnvironment });
  assert.match(config, /@kisev\/skills-opencode/);
  const manifest = JSON.parse(await readFile(join(home, ".config", "opencode", ".skills-opencode-manifest.json"), "utf8"));
  assert.equal(Object.keys(manifest.files).length, 69);
  assert.equal(Object.keys(manifest.files).some((path) => path.startsWith("agents/")), false);
  assert.equal(Object.keys(manifest.files).filter((path) => path.startsWith("plugins/")).length, 8);
  const semantic = JSON.parse(await readFile(join(home, ".config", "opencode", ".skills-opencode", "agent-profiles.manifest.json"), "utf8"));
  assert.deepEqual(semantic.critic_pool, ["critic", "critic-smoke"]);
  process.stdout.write("Packed OpenCode installer smoke test passed\n");
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
