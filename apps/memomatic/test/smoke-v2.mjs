import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { OpenCodeExecutor } from "../dist/executor.js";
import { planIngestion } from "../dist/ingestion.js";
import { MemoryStore } from "../dist/store.js";

const binary = process.env.OPENCODE_BINARY;
assert.ok(binary, "Set OPENCODE_BINARY to the pinned V2 executable");
const root = mkdtempSync(join(tmpdir(), "memomatic-smoke-v2-"));
const overrides = {
  HOME: root,
  XDG_CONFIG_HOME: join(root, "config"),
  XDG_DATA_HOME: join(root, "data"),
  XDG_STATE_HOME: join(root, "state"),
  XDG_CACHE_HOME: join(root, "cache"),
  OPENCODE_DISABLE_MODELS_FETCH: "true",
  OPENCODE_CONFIG_DIR: join(root, "config/opencode"),
  OPENCODE_CONFIG: undefined,
  OPENCODE_CONFIG_CONTENT: undefined,
  OPENCODE_DB: undefined,
  OPENCODE_PASSWORD: undefined,
  OPENCODE_SERVER_PASSWORD: undefined,
};
const saved = Object.fromEntries(Object.keys(overrides).map((key) => [key, process.env[key]]));
let executor;
try {
  for (const [key, value] of Object.entries(overrides)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  mkdirSync(join(root, "config/opencode"), { recursive: true });
  executor = new OpenCodeExecutor({
    binary,
    model: "memomatic-unavailable/no-model",
    variant: null,
    retries: 0,
    timeoutMs: 10000,
  });
  await executor.initialize();
  const signal = AbortSignal.timeout(15000);
  const created = await executor.request(
    "/api/session",
    {
      title: "Native V2 memory fixture",
      agent: "memomatic",
      location: { directory: executor.directory },
      permissions: [{ action: "*", resource: "*", effect: "deny" }],
    },
    signal,
  );
  const id = created.data.id;
  await executor.request(
    `/api/experimental/session/${id}/instructions/entries/memomatic`,
    { value: "Fixture extraction instructions" },
    signal,
    "PUT",
  );
  const denied = await executor.request(
    `/api/session/${id}/permission`,
    { action: "shell", resources: ["echo fixture"] },
    signal,
  );
  assert.equal(denied.data.effect, "deny");
  // This deliberately unavailable provider validates the V2 route without a model call.
  await assert.rejects(
    executor.complete({ system: "No tools.", prompt: "Fixture input." }),
    /model request.*HTTP 503/,
  );
  await executor.close();
  executor = undefined;
  const path = join(root, "data/opencode/opencode.db");
  const db = new DatabaseSync(path);
  db.prepare("UPDATE session_v2 SET time_created=1,time_updated=1 WHERE id=?").run(id);
  const insert = db.prepare(
    "INSERT INTO session_message(id,session_id,type,seq,time_created,time_updated,data) VALUES (?,?,?,?,?,?,?)",
  );
  insert.run(
    "msg_fixture_user",
    id,
    "user",
    1,
    1,
    1,
    JSON.stringify({ text: "A durable native V2 decision." }),
  );
  insert.run(
    "msg_fixture_assistant",
    id,
    "assistant",
    2,
    2,
    2,
    JSON.stringify({
      content: [
        { type: "reasoning", text: "Never ingest reasoning" },
        { type: "text", text: "Confirmed native outcome." },
      ],
    }),
  );
  db.close();
  const before = readFileSync(path);
  const store = await MemoryStore.open(":memory:");
  try {
    const plan = planIngestion(path, store, { before: Date.now() + 1000, maxChars: 256 });
    assert.equal(plan.sessions, 1);
    const text = plan.fragments.map((entry) => entry.text).join("\n");
    assert.match(text, /A durable native V2 decision/);
    assert.match(text, /Confirmed native outcome/);
    assert.doesNotMatch(text, /Never ingest reasoning/);
    assert.deepEqual(readFileSync(path), before);
    for (const fragment of plan.fragments) {
      for (const key of fragment.checkpointKeys) store.setMeta(key, fragment.id);
      if (fragment.seal) store.setMeta(...fragment.seal);
    }
    assert.equal(
      planIngestion(path, store, { before: Date.now() + 1000, maxChars: 256 }).fragments.length,
      0,
    );
  } finally {
    store.close();
  }
  process.stdout.write(
    "Memomatic native OpenCode V2 HTTP, tool denial, and read-only database smoke test passed\n",
  );
} finally {
  await executor?.close();
  for (const [key, value] of Object.entries(saved)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  rmSync(root, { recursive: true, force: true });
}
