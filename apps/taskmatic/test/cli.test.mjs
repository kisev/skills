import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
test("command help and flag/env/config precedence are non-mutating and scoped", () => {
  const root = mkdtempSync(join(tmpdir(), "taskmatic-cli-"));
  const config = join(root, "config.json");
  const fromFile = join(root, "file");
  const fromEnv = join(root, "env");
  const fromCli = join(root, "cli");
  writeFileSync(config, JSON.stringify({ home: fromFile }));
  const run = (args, env = {}) => {
    const environment = { ...process.env };
    delete environment.TASKMATIC_HOME;
    return spawnSync(
      process.execPath,
      [new URL("../dist/cli.js", import.meta.url).pathname, ...args],
      { encoding: "utf8", env: { ...environment, ...env } },
    );
  };
  try {
    const help = run(["claim", "--help"]);
    assert.equal(help.status, 0);
    assert.match(help.stdout, /TASKMATIC_TTL/);
    assert.ok(!help.stdout.includes("--labels"));
    assert.equal(run(["--config", config, "path"]).stdout.trim(), fromFile);
    assert.equal(
      run(["--config", config, "path"], { TASKMATIC_HOME: fromEnv }).stdout.trim(),
      fromEnv,
    );
    assert.equal(
      run(["--home", fromCli, "--config", config, "path"], {
        TASKMATIC_HOME: fromEnv,
      }).stdout.trim(),
      fromCli,
    );
    assert.equal(existsSync(fromFile), false);
    assert.equal(existsSync(fromEnv), false);
    assert.equal(existsSync(fromCli), false);
    assert.equal(run(["boards", "--priority", "high"]).status, 2);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
