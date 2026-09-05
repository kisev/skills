import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const packageRoot = resolve(import.meta.dirname, "..");
const temporary = mkdtempSync(join(tmpdir(), "agent-skills-opencode-smoke-"));
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
  const executable = join(project, "node_modules", ".bin", "agent-skills-opencode");
  const environment = { PATH: process.env.PATH ?? "", HOME: home, XDG_CONFIG_HOME: join(home, ".config"), XDG_STATE_HOME: join(home, ".state") };
  const dryRun = JSON.parse(run(executable, ["install", "--scope", "global", "--dry-run"], { cwd: project, env: environment }));
  assert.equal(dryRun.applied, false);
  run(executable, ["install", "--scope", "global", "--confirm", dryRun.plan.digest], { cwd: project, env: environment });
  await writeFile(join(project, "opencode.json"), JSON.stringify({ "$schema": "https://opencode.ai/config.json", plugin: ["agent-skills-opencode"] }));
  const opencodeEnvironment = { ...environment, OPENCODE_CONFIG: join(project, "opencode.json") };
  const agents = run(binary, ["agent", "list"], { cwd: project, env: opencodeEnvironment });
  assert.match(agents, /manager \(primary\)/);
  assert.match(agents, /review \(primary\)/);
  const config = run(binary, ["debug", "config"], { cwd: project, env: opencodeEnvironment });
  assert.match(config, /agent-skills-opencode/);
  const manifest = JSON.parse(await readFile(join(home, ".config", "opencode", ".agent-skills-opencode-manifest.json"), "utf8"));
  assert.equal(Object.keys(manifest.files).length, 71);
  assert.equal(Object.keys(manifest.files).filter((path) => path.startsWith("plugins/")).length, 8);
  process.stdout.write("Packed OpenCode installer smoke test passed\n");
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
