import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("help and status never start a model, index, or create state; malformed arguments fail early", () => {
  const root = mkdtempSync(join(tmpdir(), "memory-cli-"));
  const state = join(root, "state");
  const run = (args, input) =>
    spawnSync(process.execPath, [new URL("../dist/cli.js", import.meta.url).pathname, ...args], {
      encoding: "utf8",
      input,
      env: { ...process.env, MEMOMATIC_HOME: state, XDG_CONFIG_HOME: join(root, "config") },
    });
  try {
    for (const args of [
      [],
      ["--help"],
      ["dream", "--help"],
      ["index", "--help"],
      ["status", "--json"],
    ]) {
      const result = run(args);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(existsSync(state), false);
    }
    const help = run(["dream", "--help"]).stdout;
    for (const value of [
      "--timeout",
      "MEMOMATIC_TIMEOUT",
      "--max-sessions",
      "--progress",
      "--model",
    ])
      assert.ok(help.includes(value), value);
    for (const args of [
      ["dream", "--unknown"],
      ["dream", "--timeout", "bogus"],
      ["dream", "--chunk-chars", "0"],
      ["dream", "--model", "bad"],
    ]) {
      assert.notEqual(run(args).status, 0);
      assert.equal(existsSync(state), false);
    }
    const config = join(root, "settings.json");
    writeFileSync(config, JSON.stringify({ logFormat: "json", dream: { model: null } }));
    const result = run(["--config", config, "dream", "--dry-run", "--json"]);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).dryRun, true);
    assert.ok(
      result.stderr
        .split("\n")
        .filter(Boolean)
        .every((line) => JSON.parse(line).phase),
    );
    assert.equal(existsSync(state), false);
    const mcp = run(["mcp-serve"], '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n');
    assert.equal(JSON.parse(mcp.stdout).result.tools.length, 4);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
