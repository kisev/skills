import assert from "node:assert/strict";
import { mkdtempSync, rmSync, readFileSync, writeFileSync, utimesSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { createServer } from "node:http";
import test from "node:test";
import { openMemomatic } from "../dist/service.js";
import { planIngestion } from "../dist/ingestion.js";
import { runDream } from "../dist/dream.js";
import { reindex } from "../dist/search.js";
import { OpenCodeExecutor } from "../dist/executor.js";
import { withRunLock } from "../dist/inbox.js";

async function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "dream-incremental-"));
  for (const [key, value] of Object.entries({
    MEMOMATIC_HOME: join(root, "memory"),
    XDG_CONFIG_HOME: join(root, "config"),
    XDG_DATA_HOME: root,
    MEMOMATIC_CONFIG: undefined,
  })) {
    const prior = process.env[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
    t.after(() => {
      if (prior === undefined) delete process.env[key];
      else process.env[key] = prior;
    });
  }
  const context = await openMemomatic();
  context.settings.dream.maxChars = 256;
  context.settings.dream.idleMs = 0;
  const path = join(root, "sessions.db");
  const db = new DatabaseSync(path);
  db.exec(
    "CREATE TABLE session(id TEXT,title TEXT,directory TEXT,time_created INTEGER,time_updated INTEGER); CREATE TABLE message(id TEXT,session_id TEXT,data TEXT,time_created INTEGER); CREATE TABLE part(id TEXT,message_id TEXT,data TEXT,time_created INTEGER);",
  );
  db.prepare("INSERT INTO session VALUES (?,?,?,?,?)").run("s", "Session", "/project", 1, 1);
  const message = (id, text, time = 1) => {
    db.prepare("INSERT INTO message VALUES (?,?,?,?)").run(id, "s", '{"role":"user"}', time);
    db.prepare("INSERT INTO part VALUES (?,?,?,?)").run(
      `p-${id}`,
      id,
      JSON.stringify({ type: "text", text }),
      time,
    );
  };
  t.after(() => {
    db.close();
    context.store.close();
    rmSync(root, { recursive: true, force: true });
  });
  return { root, context, path, db, message };
}

test("message checkpoints capture old-session continuations, edits and the final tail", async (t) => {
  const { context, path, message, db } = await fixture(t);
  message("a", "A".repeat(800) + " FINAL DECISION");
  const plan = planIngestion(path, context.store, { before: 100, maxChars: 256 });
  assert.ok(plan.fragments.length > 3);
  assert.match(plan.fragments.at(-1).text, /FINAL DECISION/);
  for (const item of plan.fragments)
    for (const key of item.checkpointKeys) context.store.setMeta(key, item.id);
  assert.equal(
    planIngestion(path, context.store, { before: 100, maxChars: 256 }).fragments.length,
    0,
  );
  message("b", "Follow-up decision", 2);
  const continuation = planIngestion(path, context.store, { before: 100, maxChars: 256 });
  assert.equal(continuation.fragments.length, 1);
  assert.match(continuation.fragments[0].text, /Follow-up/);
  db.prepare("UPDATE part SET data=? WHERE id='p-a'").run(
    JSON.stringify({ type: "text", text: "Corrected initial decision" }),
  );
  assert.match(
    planIngestion(path, context.store, { before: 100, maxChars: 256 })
      .fragments.map((x) => x.text)
      .join("\n"),
    /Corrected/,
  );
  db.exec("UPDATE session SET time_updated=1000");
  assert.equal(
    planIngestion(path, context.store, { before: 100, maxChars: 256 }).fragments.length,
    0,
  );
});

test("unchanged modern session revisions skip reading message bodies", async (t) => {
  const { context, path, db } = await fixture(t);
  db.exec(
    "ALTER TABLE message ADD COLUMN time_updated INTEGER DEFAULT 1; ALTER TABLE part ADD COLUMN time_updated INTEGER DEFAULT 1;",
  );
  db.prepare("INSERT INTO message(id,session_id,data,time_created) VALUES (?,?,?,?)").run(
    "a",
    "s",
    '{"role":"user"}',
    1,
  );
  db.prepare("INSERT INTO part(id,message_id,data,time_created) VALUES (?,?,?,?)").run(
    "p-a",
    "a",
    '{"type":"text","text":"Decision"}',
    1,
  );
  const first = planIngestion(path, context.store, { before: 1000, maxChars: 256 });
  for (const fragment of first.fragments) {
    for (const key of fragment.checkpointKeys) context.store.setMeta(key, fragment.id);
    if (fragment.seal) context.store.setMeta(...fragment.seal);
  }
  const cached = planIngestion(path, context.store, { before: 1000, maxChars: 256 });
  assert.equal(cached.messages, 0);
  assert.equal(cached.cachedSessions, 1);
  db.prepare("UPDATE part SET data=?,time_updated=2 WHERE id='p-a'").run(
    '{"type":"text","text":"Changed decision"}',
  );
  assert.match(
    planIngestion(path, context.store, { before: 1000, maxChars: 256 }).fragments[0].text,
    /Changed decision/,
  );
});

test("aborted extraction reuses completed response and commits each fragment once", async (t) => {
  const { context, path, message } = await fixture(t);
  message("a", "Decision ".repeat(80));
  const controller = new AbortController();
  let calls = 0;
  const executor = {
    name: "fake",
    async complete() {
      calls++;
      if (calls === 1) controller.abort(new Error("interrupted"));
      return JSON.stringify({
        candidates: [{ text: "Retain this durable result", key: "result" }],
      });
    },
  };
  await assert.rejects(
    runDream(context, executor, { databaseFile: path, signal: controller.signal }),
    /interrupted/,
  );
  const afterAbort = calls;
  const plan = planIngestion(path, context.store, { before: Date.now(), maxChars: 256 });
  const report = await runDream(context, executor, { databaseFile: path });
  assert.equal(calls - afterAbort, plan.fragments.length - 1);
  assert.equal(report.ingestion.remaining, 0);
  const before = calls;
  await runDream(context, executor, { databaseFile: path });
  assert.equal(calls, before);
  const corpus = readFileSync(
    join(context.paths.dailyDir, new Date().toISOString().slice(0, 10) + ".md"),
    "utf8",
  );
  assert.equal(corpus.split("Retain this durable result").length - 1, 1);
});

test("discussing the internal marker does not hide a normal session", async (t) => {
  const { context, path, message } = await fixture(t);
  message("a", "Explain how the [memomatic-internal] marker works.");
  assert.equal(
    planIngestion(path, context.store, { before: 1000, maxChars: 256 }).fragments.length,
    1,
  );
});

test("embedding cache processes only changed documents, and force deliberately bypasses it", async (t) => {
  const { context } = await fixture(t);
  let inputs = [];
  context.settings.embedding = { url: "http://localhost/embeddings", model: "test" };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const batch = JSON.parse(options.body).input;
    inputs.push(...batch);
    return Response.json({ data: batch.map((_, index) => ({ index, embedding: [1, 0] })) });
  });
  writeFileSync(context.paths.memoryFile, "- First. <!-- key: first -->\n");
  await reindex(context.paths, context.settings, context.store);
  assert.equal(inputs.length, 1);
  await reindex(context.paths, context.settings, context.store);
  assert.equal(inputs.length, 1);
  writeFileSync(
    context.paths.memoryFile,
    "- First. <!-- key: first -->\n- Second. <!-- key: second -->\n",
  );
  await reindex(context.paths, context.settings, context.store);
  assert.equal(inputs.length, 2);
  await reindex(context.paths, context.settings, context.store, { force: true });
  assert.equal(inputs.length, 4);
});

test("a live long-running lock cannot be stolen after the former 30-minute expiry", async (t) => {
  const { context } = await fixture(t);
  await withRunLock(context.paths, async () => {
    utimesSync(context.paths.runLockFile, 0, 0);
    await assert.rejects(
      withRunLock(context.paths, async () => assert.fail("stole live lock")),
      /another memomatic run/,
    );
  });
  assert.equal(existsSync(context.paths.runLockFile), false);
});

test("model timeout aborts the session without stopping an externally owned server", async (t) => {
  let aborts = 0;
  const server = createServer(async (req, res) => {
    for await (const _chunk of req) {
    }
    res.setHeader("Content-Type", "application/json");
    if (req.url === "/session") res.end('{"id":"s"}');
    else if (req.url.endsWith("/abort")) {
      aborts++;
      res.end("true");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => {
    server.closeAllConnections();
    server.close();
  });
  const events = [];
  const executor = new OpenCodeExecutor({
    model: "provider/model",
    variant: null,
    url: `http://127.0.0.1:${server.address().port}`,
    timeoutMs: 80,
    retries: 1,
    observe: (event) => events.push(event),
  });
  await assert.rejects(executor.complete({ system: "system", prompt: "prompt" }), /2 attempt/);
  assert.equal(aborts, 2);
  assert.ok(events.some((event) => event.phase === "model.retry"));
  await executor.close();
  assert.equal(server.listening, true);
});
