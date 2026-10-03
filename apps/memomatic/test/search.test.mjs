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
  defaultSettings,
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

test("query and document formatting is configured separately from raw defaults", async (t) => {
  const inputs = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const input = JSON.parse(options.body).input;
    inputs.push(input);
    return Response.json({ data: input.map((text, index) => ({ index, embedding: [1, 0] })) });
  });
  const prefixed = normalizeSettings({
    embedding: {
      url: "http://localhost/embeddings",
      model: "embedding",
      queryPrefix: "query: ",
      documentPrefix: "passage: ",
    },
  });
  await embedTexts(prefixed, ["first", "second"], "document");
  await embedTexts(prefixed, ["what came first?"], "query");
  assert.deepEqual(inputs[0], ["passage: first", "passage: second"]);
  assert.deepEqual(inputs[1], ["query: what came first?"]);
  const silent = normalizeSettings({
    embedding: {
      url: "http://localhost/embeddings",
      model: "qwen3-embedding:4b",
      queryInstruction: "",
    },
  });
  await embedTexts(silent, ["raw question"], "query");
  assert.deepEqual(inputs[2], ["raw question"]);
});

test("service settings stay disabled by default and reject invalid endpoint options", () => {
  const defaults = defaultSettings();
  assert.equal(defaults.embedding, null);
  assert.equal(defaults.reranker, null);
  const configured = normalizeSettings({
    embedding: { url: "http://127.0.0.1:11434/v1/embeddings", model: "qwen3-embedding:4b" },
    reranker: { url: "http://127.0.0.1:8080/rerank", model: "reranker" },
  });
  assert.equal(configured.embedding.timeoutMs, 30000);
  assert.equal(configured.embedding.maxBatchTexts, 32);
  assert.equal(configured.embedding.maxTextChars, 8000);
  assert.equal(configured.embedding.queryPrefix, "");
  assert.equal(configured.embedding.documentPrefix, "");
  assert.equal(configured.embedding.bearerEnv, null);
  assert.equal(configured.reranker.timeoutMs, 30000);
  assert.equal(configured.reranker.candidates, 64);
  assert.equal(configured.reranker.minScore, 0);
  assert.equal(configured.reranker.maxDocuments, 64);
  assert.equal(configured.reranker.maxChars, 8000);
  assert.throws(
    () => normalizeSettings({ embedding: { url: "ftp://host/embeddings", model: "m" } }),
    /embedding\.url/,
  );
  assert.throws(
    () =>
      normalizeSettings({
        embedding: { url: "http://host/embeddings", model: "m", bearerEnv: "not an env name" },
      }),
    /bearerEnv/,
  );
  assert.throws(
    () =>
      normalizeSettings({ embedding: { url: "http://host/embeddings", model: "m", timeoutMs: 0 } }),
    /embedding\.timeoutMs/,
  );
  assert.throws(
    () =>
      normalizeSettings({
        embedding: { url: "http://host/embeddings", model: "m", maxTextChars: 10 },
      }),
    /maxTextChars/,
  );
  assert.throws(() => normalizeSettings({ embedding: { model: "missing-url" } }), /embedding\.url/);
  assert.throws(
    () => normalizeSettings({ reranker: { url: "http://host/rerank", model: "r", minScore: -1 } }),
    /reranker\.minScore/,
  );
  assert.throws(
    () => normalizeSettings({ reranker: { url: "http://host/rerank", model: "r", candidates: 0 } }),
    /reranker\.candidates/,
  );
});

test("the documented vLLM-style embedding and rerank contract drives final ranking", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    embedding: {
      url: "http://127.0.0.1:8080/v1/embeddings",
      model: "embedding",
      queryPrefix: "query: ",
      documentPrefix: "passage: ",
    },
    reranker: { url: "http://127.0.0.1:8080/rerank", model: "reranker" },
  });
  const dimension = 2048;
  const basis = (position) => {
    const values = new Array(dimension).fill(0);
    values[position] = 1;
    return values;
  };
  const query = "pg failover";
  const paraphrase = "Database switchover runbook keeps the replica promotion safe.";
  const literal = "The pg failover checklist lives in the ops wiki.";
  const vectors = new Map([
    [`query: ${query}`, basis(0)],
    [`passage: ${paraphrase}`, basis(0)],
    [`passage: ${literal}`, basis(1)],
  ]);
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push({ url: String(url), body });
    if (String(url) === settings.embedding.url) {
      assert.equal(body.model, "embedding");
      assert.equal(body.encoding_format, "float");
      return Response.json({
        data: body.input.map((text, index) => ({ index, embedding: vectors.get(text) })).reverse(),
      });
    }
    assert.equal(String(url), settings.reranker.url);
    assert.equal(body.model, "reranker");
    assert.equal(body.query, query);
    assert.ok(body.documents.every((document) => !document.startsWith("passage: ")));
    assert.equal(body.top_n, body.documents.length);
    const results = body.documents.map((document, index) => ({
      index,
      relevance_score: document.includes("switchover") ? 0.92 : 0.35,
    }));
    return Response.json({ results: results.reverse() });
  });
  store.replaceIndex(
    [entry("literal", literal), entry("paraphrase", paraphrase)],
    [new Float32Array(basis(1)), new Float32Array(basis(0))],
    embeddingFingerprint(settings),
  );
  assert.equal(store.vectors()[0].dim, dimension);
  const hits = await search(store, query, settings, { markSurfaced: false });
  // The reranker owns the final order; the exact literal match no longer leads.
  assert.deepEqual(
    hits.map((hit) => hit.entry.key),
    ["paraphrase", "literal"],
  );
  assert.equal(hits[0].explanation.reason, "rerank");
  assert.equal(hits[0].score, 0.92);
  assert.equal(hits[1].score, 0.35);
  assert.ok(hits[0].explanation.rerank.candidates >= 2);
  assert.equal(hits[0].explanation.relevance, 0.92);
  assert.deepEqual(calls[0].body.input, [`query: ${query}`]);
});

test("bearerEnv authenticates both services without leaking the token", async (t) => {
  process.env.MEMOMATIC_TEST_BEARER = "secret-token-value";
  t.after(() => delete process.env.MEMOMATIC_TEST_BEARER);
  const settings = normalizeSettings({
    embedding: {
      url: "http://127.0.0.1:8080/v1/embeddings",
      model: "embedding",
      bearerEnv: "MEMOMATIC_TEST_BEARER",
    },
    reranker: {
      url: "http://127.0.0.1:8080/rerank",
      model: "reranker",
      bearerEnv: "MEMOMATIC_TEST_BEARER",
    },
  });
  const authorizations = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    authorizations.push(options.headers.authorization);
    if (String(url) === settings.embedding.url)
      return Response.json({ data: [{ index: 0, embedding: [1, 0] }] });
    return new Response("invalid credentials", { status: 401 });
  });
  const [vector] = await embedTexts(settings, ["text"]);
  assert.deepEqual([...vector], [1, 0]);
  assert.deepEqual(authorizations, ["Bearer secret-token-value"]);
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  store.replaceIndex([entry("one", "memory note")], [vector], embeddingFingerprint(settings));
  try {
    await search(store, "memory", settings);
    assert.fail("expected the reranker rejection to propagate");
  } catch (error) {
    assert.match(error.message, /reranker request failed: 401/);
    assert.ok(!error.message.includes("secret-token-value"));
  }
  delete process.env.MEMOMATIC_TEST_BEARER;
  await assert.rejects(
    embedTexts(settings, ["text"]),
    /embedding bearerEnv "MEMOMATIC_TEST_BEARER" is not set/,
  );
});

test("configured timeouts admit slow cold starts and report explicit timeouts", async (t) => {
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test", timeoutMs: 25 },
  });
  t.mock.method(
    globalThis,
    "fetch",
    (_url, options) =>
      new Promise((_, reject) => {
        options.signal.addEventListener("abort", () => reject(options.signal.reason));
      }),
  );
  await assert.rejects(embedTexts(settings, ["text"]), /embedding request timed out after 25ms/);
});

test("long texts are chunked, pooled per input and bounded per request", async (t) => {
  const settings = normalizeSettings({
    embedding: {
      url: "http://localhost/embeddings",
      model: "test",
      maxTextChars: 500,
      maxBatchTexts: 8,
    },
  });
  const batches = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const input = JSON.parse(options.body).input;
    const base = batches.reduce((sum, batch) => sum + batch.length, 0);
    batches.push(input);
    return Response.json({
      data: input.map((text, index) => ({ index, embedding: [base + index + 1, 1] })),
    });
  });
  const long = "sentence about memory. ".repeat(200);
  assert.ok(long.length > 1000);
  const [pooled] = await embedTexts(settings, [long], "document");
  assert.ok(batches.length >= 2);
  const flat = batches.flat();
  assert.ok(flat.length >= 2);
  for (const batch of batches) for (const text of batch) assert.ok(text.length <= 500);
  const expected = flat.reduce((sum, _text, index) => sum + index + 1, 0) / flat.length;
  assert.ok(Math.abs(pooled[0] - expected) < 1e-6);
  assert.equal(pooled[1], 1);
});

test("a chunked entry keeps one vector and surfaces once", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-chunk-"));
  const store = await MemoryStore.open(":memory:");
  t.after(() => {
    store.close();
    rmSync(root, { recursive: true, force: true });
  });
  mkdirSync(join(root, "memory"));
  writeFileSync(join(root, "MEMORY.md"), `- ${"detail ".repeat(800)}\n`);
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test", maxTextChars: 1000 },
  });
  const batches = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const input = JSON.parse(options.body).input;
    batches.push(input);
    return Response.json({ data: input.map((text, index) => ({ index, embedding: [1, 0] })) });
  });
  assert.equal(
    await reindex({ stateRoot: root, dailyDir: join(root, "memory") }, settings, store),
    1,
  );
  assert.ok(batches[0].length >= 5);
  batches.length = 0;
  assert.equal(store.vectors().length, 1);
  assert.equal((await search(store, "detail", settings, { markSurfaced: false })).length, 1);
  assert.deepEqual(batches.length, 1);
});

test("reranker documents stay inside the combined budget and aggregate per entry", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    reranker: {
      url: "http://localhost/rerank",
      model: "reranker",
      maxChars: 2000,
      maxDocuments: 4,
    },
  });
  const long = "fragment text. ".repeat(300);
  store.replaceIndex([entry("long", long), entry("short", "short note")], null, "");
  const bodies = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const body = JSON.parse(options.body);
    bodies.push(body);
    const results = body.documents.map((document, index) => ({
      index,
      relevance_score: document.length > 100 ? (index === 0 ? 0.8 : 0.4) : 0.6,
    }));
    return Response.json({ results });
  });
  const hits = await search(store, "note fragment check", settings, { markSurfaced: false });
  assert.equal(bodies.length, 2);
  const documents = bodies.flatMap((body) => body.documents);
  assert.ok(documents.length >= 6);
  const budget = 2000 - 1024 - "note fragment check".length;
  for (const document of documents) assert.ok(document.length <= budget);
  assert.deepEqual(
    bodies.map((body) => body.query),
    ["note fragment check", "note fragment check"],
  );
  assert.deepEqual(
    hits.map((hit) => hit.entry.key),
    ["long", "short"],
  );
  assert.equal(hits[0].score, 0.8);
  assert.equal(hits[1].score, 0.6);
});

test("the reranker widens candidate collection beyond the strict gates within bounds", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test" },
    reranker: { url: "http://localhost/rerank", model: "reranker", candidates: 3 },
  });
  const lexical = ["alpha one", "alpha two", "alpha three", "alpha four", "alpha five"];
  const entries = lexical.map((text, index) => entry(`lex${index}`, text));
  entries.push(entry("weak", "completely different wording"));
  store.replaceIndex(
    entries,
    [...entries.map((_, index) => (index < 5 ? vector(0.04) : vector(0.3)))],
    embeddingFingerprint(settings),
  );
  const documents = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const body = JSON.parse(options.body);
    if (body.input) return Response.json({ data: [{ index: 0, embedding: [1, 0] }] });
    documents.push(...body.documents);
    return Response.json({
      results: body.documents.map((document, index) => ({ index, relevance_score: 0.5 })),
    });
  });
  const hits = await search(store, "alpha", settings, { markSurfaced: false });
  // Four candidates: three lexical plus the weak semantic match that would
  // fail minSemanticScore in the gated path.
  assert.equal(documents.length, 4);
  assert.ok(documents.includes("completely different wording"));
  assert.equal(hits.length, 4);
  assert.ok(hits.every((hit) => hit.explanation.reason === "rerank"));
  // Without the reranker the same store applies the strict gates instead.
  const gated = await search(
    store,
    "alpha",
    normalizeSettings({
      embedding: { url: "http://localhost/embeddings", model: "test" },
    }),
    { markSurfaced: false },
  );
  assert.equal(gated.length, 5);
  assert.ok(!gated.some((hit) => hit.entry.key === "weak"));
});

test("the configured reranker threshold drops weak relevance and surfaces nothing", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    reranker: { url: "http://localhost/rerank", model: "reranker", minScore: 0.5 },
  });
  store.replaceIndex([entry("one", "note about indexing")], null, "");
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const body = JSON.parse(options.body);
    return Response.json({
      results: body.documents.map((document, index) => ({ index, relevance_score: 0.2 })),
    });
  });
  assert.deepEqual(await search(store, "note", settings), []);
  assert.equal(store.usageFor("one").surfaced, 0);
});

test("candidate-free queries skip the reranker request entirely", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    reranker: { url: "http://localhost/rerank", model: "reranker" },
  });
  store.replaceIndex([entry("one", "note about indexing")], null, "");
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push(String(url));
    const body = JSON.parse(options.body);
    return Response.json({
      results: body.documents.map((document, index) => ({ index, relevance_score: 0.9 })),
    });
  });
  assert.deepEqual(await search(store, "unrelated words", settings, { markSurfaced: false }), []);
  assert.deepEqual(calls, []);
});

test("reranker failures and malformed payloads surface without fallback", async (t) => {
  const store = await MemoryStore.open(":memory:");
  t.after(() => store.close());
  const settings = normalizeSettings({
    reranker: { url: "http://localhost/rerank", model: "reranker" },
  });
  store.replaceIndex([entry("one", "note about indexing")], null, "");
  let payload;
  let status = 200;
  t.mock.method(globalThis, "fetch", async () =>
    status === 200 ? Response.json(payload) : new Response("exploded", { status }),
  );
  for (const broken of [
    { results: "junk" },
    {},
    { results: [{ index: 9, relevance_score: 0.5 }] },
    { results: [{ index: 0, relevance_score: "0.5" }] },
    {
      results: [
        { index: 0, relevance_score: 0.5 },
        { index: 0, relevance_score: 0.4 },
      ],
    },
  ]) {
    status = 200;
    payload = broken;
    await assert.rejects(
      search(store, "note", settings, { markSurfaced: false }),
      /reranker response/,
    );
  }
  status = 500;
  await assert.rejects(
    search(store, "note", settings, { markSurfaced: false }),
    /reranker request failed: 500/,
  );
});

test("document-format changes invalidate vectors; reranker changes reuse them", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "memomatic-format-"));
  const store = await MemoryStore.open(":memory:");
  t.after(() => {
    store.close();
    rmSync(root, { recursive: true, force: true });
  });
  mkdirSync(join(root, "memory"));
  writeFileSync(join(root, "MEMORY.md"), "- Stable memory note.\n");
  const paths = { stateRoot: root, dailyDir: join(root, "memory") };
  const settings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test", documentPrefix: "passage: " },
  });
  let embeddingInputs = [];
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    const body = JSON.parse(options.body);
    if (body.input) {
      embeddingInputs.push(...body.input);
      return Response.json({
        data: body.input.map((text, index) => ({ index, embedding: [1, 0] })),
      });
    }
    return Response.json({
      results: (body.documents ?? []).map((document, index) => ({ index, relevance_score: 0.7 })),
    });
  });
  assert.equal(await reindex(paths, settings, store), 1);
  assert.deepEqual(embeddingInputs, ["passage: - Stable memory note."]);
  embeddingInputs = [];
  assert.equal((await search(store, "memory", settings, { markSurfaced: false })).length, 1);
  // Only the raw query is embedded; document vectors stay cached.
  assert.deepEqual(embeddingInputs, ["memory"]);
  // A reranker-only change never recomputes document vectors.
  const rerankedSettings = normalizeSettings({
    embedding: { url: "http://localhost/embeddings", model: "test", documentPrefix: "passage: " },
    reranker: { url: "http://localhost/rerank", model: "reranker" },
  });
  const reranked = await search(store, "memory", rerankedSettings, { markSurfaced: false });
  assert.equal(reranked.length, 1);
  assert.equal(reranked[0].explanation.reason, "rerank");
  assert.deepEqual(embeddingInputs, ["memory", "memory"]);
  // Changing document processing invalidates the stored vectors before any request.
  rerankedSettings.embedding.documentPrefix = "doc: ";
  await assert.rejects(search(store, "memory", rerankedSettings), /run memomatic index/);
  assert.equal(embeddingInputs.length, 2);
  embeddingInputs = [];
  assert.equal(await reindex(paths, rerankedSettings, store), 1);
  assert.deepEqual(embeddingInputs, ["doc: - Stable memory note."]);
  assert.equal(
    (await search(store, "memory", rerankedSettings, { markSurfaced: false })).length,
    1,
  );
});
