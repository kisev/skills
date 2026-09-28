import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import test from "node:test";
import { MemoryStore } from "../dist/store.js";
import { search, reindex } from "../dist/search.js";
import {
  normalizeSettings,
  embedTexts,
  embeddingFingerprint,
  MEMORY_QUERY_INSTRUCTION,
} from "../dist/settings.js";

function entry(id, text, extra = {}) {
  return {
    stableId: id,
    file: "/memory/MEMORY.md",
    line: 1,
    kind: "curated",
    key: id,
    text,
    trigger: [],
    importance: 5,
    pinned: false,
    project: null,
    origin: "agent",
    observedAt: Date.now(),
    status: null,
    source: "agent",
    ...extra,
  };
}
const vector = (similarity) => new Float32Array([similarity, Math.sqrt(1 - similarity ** 2)]);

test("retrieval gates precede ranking boosts; exact matches lead and explanations expose evidence", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "qwen3-embedding:4b" },
  });
  const calls = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    calls.push(JSON.parse(options.body).input);
    return Response.json({ data: [{ index: 0, embedding: [1, 0] }] });
  });
  store.replaceIndex(
    [
      entry("literal", "Bedrock persists routing receipts.", { project: "bedrock" }),
      entry("unrelated", "Run reviews in read-only mode.", { importance: 10, pinned: true }),
    ],
    [vector(0.6), vector(0.7)],
    embeddingFingerprint(settings),
  );
  const hits = await search(store, "bedrock", settings, { markSurfaced: false });
  assert.equal(hits[0].entry.stableId, "literal");
  assert.deepEqual(hits[0].explanation.matchedTokens, ["bedrock"]);
  assert.equal(hits[0].explanation.reason, "both");
  assert.ok(hits[0].explanation.relevance >= hits[0].explanation.semantic);
  assert.equal(calls[0][0], `Instruct: ${MEMORY_QUERY_INSTRUCTION}\nQuery:bedrock`);
  assert.equal(
    (await search(store, "bedrock", settings, { project: "bedrock", markSurfaced: false })).length,
    1,
  );

  store.replaceIndex(
    [entry("noise", "Highly important technical rule", { importance: 10, pinned: true })],
    [vector(0.204)],
    embeddingFingerprint(settings),
  );
  assert.deepEqual(await search(store, "Орхан", settings), []);
  assert.equal(store.usageFor("noise").surfaced, 0);
  store.replaceIndex(
    [entry("fix", "Correcting DNS restored database connectivity.")],
    [vector(0.6137)],
    embeddingFingerprint(settings),
  );
  assert.equal(
    (await search(store, "application cannot reach storage", settings))[0].explanation.reason,
    "semantic",
  );
  store.replaceIndex(
    [entry("noise", "Technical rule")],
    [vector(0.181)],
    embeddingFingerprint(settings),
  );
  assert.deepEqual(await search(store, "рецепт клубничного варенья", settings), []);
});

test("legacy and same-dimension different-model vectors require explicit reindex", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "first" },
  });
  store.replaceEntries([entry("one", "memory")]);
  await assert.rejects(search(store, "memory", settings), /run memomatic index/);
  store.replaceIndex([entry("one", "memory")], [vector(0.8)], embeddingFingerprint(settings));
  settings.embedding.model = "second";
  await assert.rejects(search(store, "memory", settings), /another model/);
});

test("failed embedding rebuild preserves the previous searchable index", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-search-"));
  const store = await MemoryStore.open(":memory:");
  t.after(() => {
    store.close();
    rmSync(root, { recursive: true, force: true });
  });
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test" },
  });
  store.replaceIndex([entry("old", "Previous verified memory")], [vector(0.8)], "old-fingerprint");
  mkdirSync(join(root, "memory"));
  writeFileSync(join(root, "MEMORY.md"), "- Replacement entry.\n");
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("offline");
  });
  await assert.rejects(
    reindex({ stateRoot: root, dailyDir: join(root, "memory") }, settings, store),
    /offline/,
  );
  assert.equal(store.allEntries()[0].stableId, "old");
  assert.equal(store.getMeta("embeddingFingerprint"), "old-fingerprint");
  assert.equal(store.vectors().length, 1);
});

test("a duplicate episodic key cannot overwrite the curated entry's vector", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-vector-identity-"));
  const store = await MemoryStore.open(":memory:");
  t.after(() => {
    store.close();
    rmSync(root, { recursive: true, force: true });
  });
  mkdirSync(join(root, "memory"));
  writeFileSync(join(root, "MEMORY.md"), "- Correct current fact. <!-- key: shared -->\n");
  writeFileSync(
    join(root, "memory/2020-01-01.md"),
    "- Different previous fact. <!-- key: shared -->\n",
  );
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test" },
  });
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(JSON.parse(options.body).input.length, 1);
    assert.match(JSON.parse(options.body).input[0], /Correct current fact/);
    return Response.json({ data: [{ index: 0, embedding: [1, 0] }] });
  });
  assert.equal(
    await reindex({ stateRoot: root, dailyDir: join(root, "memory") }, settings, store),
    1,
  );
  assert.match(store.allEntries()[0].text, /Correct current fact/);
});

test("embedding transport distinguishes documents and queries and rejects malformed responses", async (t) => {
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "qwen3-embedding:4b" },
  });
  let payload = {
    data: [
      { index: 1, embedding: [0, 1] },
      { index: 0, embedding: [1, 0] },
    ],
  };
  const inputs = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    inputs.push(JSON.parse(options.body).input);
    return Response.json(payload);
  });
  const result = await embedTexts(settings, ["first", "second"]);
  assert.deepEqual(inputs[0], ["first", "second"]);
  assert.deepEqual([...result[0]], [1, 0]);
  for (const data of [
    [
      { index: 0, embedding: [1, 0] },
      { index: 0, embedding: [1, 0] },
    ],
    [
      { index: 0, embedding: [1, 0] },
      { index: 1, embedding: [1] },
    ],
    [
      { index: 0, embedding: [0, 0] },
      { index: 1, embedding: [1, 0] },
    ],
  ]) {
    payload = { data };
    await assert.rejects(embedTexts(settings, ["first", "second"]), /embedding response/);
  }
});
