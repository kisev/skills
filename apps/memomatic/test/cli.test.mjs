import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";

test("help and status never start a model, index, or create state; malformed arguments fail early", () => {
  const root = mkdtempSync(join(tmpdir(), "memory-cli-"));
  const state = join(root, "state");
  const run = (args, input) =>
    spawnSync(process.execPath, [new URL("../dist/cli.js", import.meta.url).pathname, ...args], {
      encoding: "utf8",
      input,
      env: {
        ...process.env,
        MEMOMATIC_HOME: state,
        XDG_CONFIG_HOME: join(root, "config"),
        XDG_DATA_HOME: join(root, "data"),
      },
    });
  try {
    for (const args of [
      [],
      ["--help"],
      ["dream", "--help"],
      ["sessions", "--help"],
      ["index", "--help"],
      ["status", "--json"],
    ]) {
      const result = run(args);
      assert.equal(result.status, 0, result.stderr);
      assert.equal(existsSync(state), false);
    }
    const dreamHelp = run(["dream", "--help"]).stdout;
    for (const value of ["--timeout", "MEMOMATIC_TIMEOUT", "--progress", "--model"])
      assert.ok(dreamHelp.includes(value), value);
    for (const gone of ["--max-sessions", "--chunk-chars", "--idle", "--database"])
      assert.equal(dreamHelp.includes(gone), false, gone);
    const sessionsHelp = run(["sessions", "--help"]).stdout;
    for (const value of [
      "--timeout",
      "MEMOMATIC_TIMEOUT",
      "--max-sessions",
      "--chunk-chars",
      "--idle",
      "--database",
      "--model",
    ])
      assert.ok(sessionsHelp.includes(value), value);
    for (const args of [
      ["dream", "--unknown"],
      ["sessions", "--unknown"],
      ["dream", "--timeout", "bogus"],
      ["sessions", "--timeout", "bogus"],
      ["sessions", "--chunk-chars", "0"],
      ["sessions", "--model", "bad"],
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

test("status reports the queue: inbox files, session backlog and promotion candidates", () => {
  const root = mkdtempSync(join(tmpdir(), "memory-status-"));
  const state = join(root, "state");
  const data = join(root, "data", "opencode");
  mkdirSync(data, { recursive: true });
  const database = new DatabaseSync(join(data, "opencode.db"));
  database.exec(
    "CREATE TABLE session(id TEXT, title TEXT, directory TEXT, time_created INTEGER); CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, time_created INTEGER); CREATE TABLE part(id TEXT, message_id TEXT, data TEXT, time_created INTEGER);",
  );
  database.prepare("INSERT INTO session VALUES (?,?,?,?)").run("s", "Backlog", root, 1000);
  database.prepare("INSERT INTO message VALUES (?,?,?,?)").run("m", "s", '{"role":"user"}', 1000);
  database
    .prepare("INSERT INTO part VALUES (?,?,?,?)")
    .run("p", "m", JSON.stringify({ type: "text", text: "A queued decision." }), 1000);
  database.close();
  mkdirSync(join(state, "memomatic", "inbox"), { recursive: true });
  writeFileSync(join(state, "memomatic", "inbox", "user-test.md"), "- Queued entry.\n");
  try {
    const result = spawnSync(
      process.execPath,
      [new URL("../dist/cli.js", import.meta.url).pathname, "status", "--json"],
      {
        encoding: "utf8",
        env: {
          ...process.env,
          MEMOMATIC_HOME: join(state, "memomatic"),
          XDG_CONFIG_HOME: join(root, "config"),
          XDG_DATA_HOME: join(root, "data"),
        },
      },
    );
    assert.equal(result.status, 0, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.queue.inboxFiles, 1);
    assert.equal(report.queue.sessions.sessions, 1);
    assert.equal(report.queue.sessions.fragments, 1);
    assert.equal(report.queue.promotionCandidates, 0);
    assert.equal(report.lastRun.dream, null);
    assert.equal(report.lastRun.sessions, null);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("status without an OpenCode database reports no session backlog", () => {
  const root = mkdtempSync(join(tmpdir(), "memory-status-empty-"));
  try {
    const result = spawnSync(
      process.execPath,
      [new URL("../dist/cli.js", import.meta.url).pathname, "status", "--json"],
      {
        encoding: "utf8",
        env: {
          ...process.env,
          MEMOMATIC_HOME: join(root, "state", "memomatic"),
          XDG_CONFIG_HOME: join(root, "config"),
          XDG_DATA_HOME: join(root, "data"),
        },
      },
    );
    assert.equal(result.status, 0, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.queue.inboxFiles, 0);
    assert.equal(report.queue.sessions, null);
    assert.equal(report.queue.promotionCandidates, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
