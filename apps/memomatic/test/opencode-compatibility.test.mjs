import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import test from "node:test";
import { OpenCodeExecutor } from "../dist/executor.js";
import { loadRecentSessions } from "../dist/ingest.js";

test("OpenCode executor sends a positional prompt and reads only text events", async () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-executor-"));
  try {
    const binary = join(root, "opencode");
    writeFileSync(
      binary,
      `#!${process.execPath}
const assert = require("node:assert/strict");
assert.deepEqual(process.argv.slice(2), ["run", "--agent", "build", "--format", "json", "--model", "provider/model", "--variant", "fast", "--", "[memomatic-internal] System\\n\\nPrompt"]);
console.log(JSON.stringify({type: "tool_use", part: {text: '{"wrong":true}'}}));
console.log(JSON.stringify({type: "text", part: {text: '{"candidates":[]}'}}));
console.log(JSON.stringify({type: "step_finish", part: {cost: 0}}));
`,
      { mode: 0o700 },
    );
    const executor = new OpenCodeExecutor({ binary, model: "provider/model", variant: "fast" });
    assert.equal(
      await executor.complete({ system: "System", prompt: "Prompt" }),
      '{"candidates":[]}',
    );
    writeFileSync(
      binary,
      `#!${process.execPath}
console.log(JSON.stringify({type: "error", error: {message: "unavailable"}}));
`,
      { mode: 0o700 },
    );
    await assert.rejects(
      executor.complete({ system: "System", prompt: "Prompt" }),
      /no parsable JSON twice/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("session ingestion reads the normalized OpenCode part table", () => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-ingest-"));
  const file = join(root, "opencode.db");
  try {
    const db = new DatabaseSync(file);
    db.exec(`
      CREATE TABLE session(id TEXT, title TEXT, directory TEXT, time_created INTEGER);
      CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, time_created INTEGER);
      CREATE TABLE part(id TEXT, message_id TEXT, data TEXT, time_created INTEGER);
    `);
    const session = db.prepare("INSERT INTO session VALUES (?, ?, ?, ?)");
    const message = db.prepare("INSERT INTO message VALUES (?, ?, ?, ?)");
    const part = db.prepare("INSERT INTO part VALUES (?, ?, ?, ?)");
    session.run("normal", "Decision", "/workspace", 100);
    session.run("internal", "Dream", "/workspace", 200);
    message.run("user", "normal", '{"role":"user"}', 100);
    message.run("assistant", "normal", '{"role":"assistant"}', 101);
    message.run("dream", "internal", '{"role":"user"}', 200);
    part.run("b", "user", '{"type":"text","text":"Second"}', 102);
    part.run("a", "user", '{"type":"text","text":"First"}', 101);
    part.run("c", "user", '{"type":"tool","text":"Do not ingest"}', 103);
    part.run("d", "user", "invalid JSON", 104);
    part.run("e", "assistant", '{"type":"text","text":"Answer"}', 105);
    part.run("f", "dream", '{"type":"text","text":"[memomatic-internal] Extraction"}', 200);
    db.close();
    const sessions = loadRecentSessions(file, 0);
    assert.equal(sessions.length, 1);
    assert.deepEqual(sessions[0].messages, [
      { role: "user", text: "First\nSecond" },
      { role: "assistant", text: "Answer" },
    ]);
    assert.deepEqual(loadRecentSessions(file, 100), []);
    assert.equal(
      loadRecentSessions(file, 0, { maxSessions: 20, maxCharsPerSession: 5 })[0].messages[0].text,
      "First",
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
