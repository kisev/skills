import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import memomatic from "../dist/plugins/memomatic.js";
import { parseEntryLine, entryLine } from "../dist/memomatic/entries.js";
import { parseRules, isForbidden } from "../dist/memomatic/rules.js";
import {
  openMemomatic,
  rebuildIndex,
  searchMemory,
  writeEntry,
  getEntry,
  archiveOldEpisodic,
} from "../dist/memomatic/service.js";
import { runDream, parseExtraction, parseConsolidation } from "../dist/memomatic/dream.js";
import { handleMcpRequest } from "../dist/memomatic/mcp.js";
import { stableIdFor } from "../dist/memomatic/store.js";

function environment() {
  const root = mkdtempSync(join(tmpdir(), "memomatic-test-"));
  const state = join(root, "state");
  const config = join(root, "config");
  process.env.XDG_STATE_HOME = state;
  process.env.XDG_CONFIG_HOME = config;
  process.env.XDG_DATA_HOME = join(root, "data");
  return { root, state, config };
}

async function context() {
  return openMemomatic();
}

test("entry annotations roundtrip through parse and serialize", () => {
  const line = entryLine("Keep the gateway on loopback.", {
    importance: 9,
    key: "gateway-loopback",
    origin: "user",
    observed: "2026-09-26",
    pinned: true,
    project: "github.com/kisev/skills",
    trigger: ["gateway setup", "network safety"],
  });
  const parsed = parseEntryLine(line);
  assert.ok(parsed);
  assert.equal(parsed.text, "- Keep the gateway on loopback.");
  assert.equal(parsed.annotations.key, "gateway-loopback");
  assert.equal(parsed.annotations.importance, 9);
  assert.equal(parsed.annotations.pinned, true);
  assert.equal(parsed.annotations.project, "github.com/kisev/skills");
  assert.deepEqual(parsed.annotations.trigger, ["gateway setup", "network safety"]);
});

test("rules parsing extracts never-save topics and auto-clean", () => {
  const rules = parseRules(
    "# Memory rules\n\n- never-save: internal credentials\n- never-save: team private notes\n- auto-clean: older-than=90d scope=episodic\n- prose the service must ignore\n",
  );
  assert.deepEqual(rules.neverSave, ["internal credentials", "team private notes"]);
  assert.deepEqual(rules.autoClean, { olderThanDays: 90, scope: "episodic" });
  assert.ok(isForbidden("Don't store INTERNAL CREDENTIALS here", rules));
  assert.ok(!isForbidden("ordinary engineering fact", rules));
});

test("writeEntry rejects never-save topics and writes episodic entries", async () => {
  const env = environment();
  try {
    const { mkdirSync, writeFileSync } = await import("node:fs");
    mkdirSync(join(env.config, "memomatic"), { recursive: true });
    writeFileSync(
      join(env.config, "memomatic", "MEMORY_RULES.md"),
      "- never-save: internal credentials\n",
      "utf8",
    );
    const ctx = await context();
    await writeEntry(ctx, {
      origin: "agent",
      text: "Release helper requires pnpm because the taskfile pins it.",
    });
    await assert.rejects(
      writeEntry(ctx, { origin: "agent", text: "The internal credentials are abc" }),
      /never-save/,
    );
    const files = readdirSync(join(env.state, "memomatic", "memory"));
    assert.equal(files.length, 1);
    const body = readFileSync(join(env.state, "memomatic", "memory", files[0]), "utf8");
    assert.match(body, /Release helper requires pnpm/);
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("search ranks pinned and curated above decaying episodic entries", async () => {
  const env = environment();
  try {
    const ctx = await context();
    await writeEntry(ctx, {
      observed: undefined,
      origin: "agent",
      text: "Loopback binding decision about deploy gateway targets",
    });
    const { writeCorpusFile } = await import("../dist/memomatic/corpus.js");
    const { dailyNotePath } = await import("../dist/memomatic/corpus.js");
    const old = new Date(Date.now() - 120 * 86_400_000);
    const pinnedLine = entryLine("Pinned loopback binding rule for the deploy gateway", {
      key: "pinned-loopback",
      observed: old.toISOString().slice(0, 10),
      origin: "agent",
      pinned: true,
    });
    const decayedLine = entryLine("Decayed loopback binding note about the deploy gateway", {
      key: "decayed-loopback",
      observed: old.toISOString().slice(0, 10),
      origin: "agent",
    });
    const daily = dailyNotePath(ctx.paths, old);
    await writeCorpusFile(ctx.paths, daily, `${pinnedLine}\n${decayedLine}\n`);
    await writeCorpusFile(
      ctx.paths,
      ctx.paths.memoryFile,
      `${entryLine("Curated loopback binding decision for the deploy gateway", {
        key: "curated-loopback",
        origin: "user",
      })}\n`,
    );
    await rebuildIndex(ctx);
    const hits = await searchMemory(ctx, "loopback gateway deploy");
    const keys = hits.map((hit) => hit.entry.key);
    assert.ok(keys.includes("curated-loopback"));
    assert.ok(keys.includes("pinned-loopback"));
    assert.ok(!keys.includes("decayed-loopback"));
    assert.ok(!keys.includes(undefined));
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("usage signals and gates drive promotion, then dream consolidates", async () => {
  const env = environment();
  try {
    const ctx = await context();
    await writeEntry(ctx, {
      key: "pnpm-release-helper",
      origin: "agent",
      text: "Package validation runs through the release helper because it verifies versions.",
    });
    await rebuildIndex(ctx);
    const entry = ctx.store.allEntries().find((item) => item.key === "pnpm-release-helper");
    assert.ok(entry);
    ctx.store.markSurfaced([entry.stableId], "release helper pnpm");
    ctx.store.markSurfaced([entry.stableId], "how do we validate package versions");
    ctx.store.markUseful([entry.stableId]);
    ctx.store.markUseful([entry.stableId]);
    ctx.store.close();

    let consolidationCalls = 0;
    const executor = {
      complete: async (request) => {
        if (request.prompt.includes("Current MEMORY.md")) {
          consolidationCalls += 1;
          const key =
            consolidationCalls === 1
              ? "memory-consolidation-policy"
              : "memory-consolidation-policy-v2";
          return JSON.stringify({
            operations: [
              {
                line: `- Memory consolidation follows the dream sweep with deterministic gates. <!-- key: ${key} --> <!-- origin: user --> <!-- observed: 2026-09-26 -->`,
                op: "add",
              },
            ],
          });
        }
        return JSON.stringify({
          candidates: [
            {
              key: "memory-consolidation-policy",
              reason: "repeated decision",
              text: "Memory consolidation follows the dream sweep with deterministic gates.",
            },
          ],
        });
      },
      name: "fake",
    };
    const dream = await context();
    const report = await runDream(dream, executor);
    assert.equal(report.appendOnlyFallback, false);
    assert.equal(report.promoted.length, 1);
    assert.match(report.promoted[0], /deterministic gates/);
    const memory = readFileSync(join(env.state, "memomatic", "MEMORY.md"), "utf8");
    assert.match(memory, /deterministic gates/);
    const dreams = readFileSync(join(env.state, "memomatic", "DREAMS.md"), "utf8");
    assert.match(dreams, /promoted: 1/);
    const historyDir = join(env.state, "memomatic", "history");
    assert.ok(!existsSync(historyDir));
    const second = await runDream(dream, executor);
    assert.equal(second.promoted.length, 1);
    assert.ok(existsSync(historyDir));
    assert.ok(readdirSync(historyDir).length >= 1);
    dream.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("consolidation falls back to append-only when drop loss exceeds the bound", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const { writeCorpusFile } = await import("../dist/memomatic/corpus.js");
    await writeCorpusFile(
      ctx.paths,
      ctx.paths.memoryFile,
      [
        entryLine("First standing decision", { key: "first", origin: "user" }),
        entryLine("Second standing decision", { key: "second", origin: "user" }),
        entryLine("Third standing decision", { key: "third", origin: "user" }),
        entryLine("Fourth standing decision", { key: "fourth", origin: "user" }),
      ].join("\n") + "\n",
    );
    await writeEntry(ctx, {
      key: "fifth",
      origin: "agent",
      text: "Fifth episodic decision about promotion bounds.",
    });
    await rebuildIndex(ctx);
    const entry = ctx.store.allEntries().find((item) => item.key === "fifth");
    ctx.store.markSurfaced([entry.stableId], "promotion bounds one");
    ctx.store.markSurfaced([entry.stableId], "promotion bounds two");
    ctx.store.markUseful([entry.stableId]);
    ctx.store.markUseful([entry.stableId]);
    ctx.store.close();

    const executor = {
      complete: async () =>
        JSON.stringify({
          operations: [
            { key: "first", op: "drop" },
            { key: "second", op: "drop" },
            {
              line: entryLine("Consolidated promotion bounds entry", {
                key: "fifth",
                origin: "user",
              }),
              op: "add",
            },
          ],
        }),
      name: "fake",
    };
    const dream = await context();
    const report = await runDream(dream, executor);
    assert.equal(report.appendOnlyFallback, true);
    assert.deepEqual(report.dropped, []);
    assert.equal(report.promoted.length, 1);
    const memory = readFileSync(join(env.state, "memomatic", "MEMORY.md"), "utf8");
    assert.match(memory, /First standing decision/);
    assert.match(memory, /Consolidated promotion bounds entry/);
    dream.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("dry-run dream writes nothing", async () => {
  const env = environment();
  try {
    const dream = await context();
    const executor = {
      complete: async () =>
        JSON.stringify({ candidates: [{ key: null, reason: "r", text: "Dry run only." }] }),
      name: "fake",
    };
    const report = await runDream(dream, executor, { dryRun: true });
    assert.equal(report.dryRun, true);
    const dailyDir = join(env.state, "memomatic", "memory");
    assert.ok(!existsSync(dailyDir) || readdirSync(dailyDir).length === 0);
    dream.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("memory_get marks useful and archive respects auto-clean rules", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const { writeCorpusFile, dailyNotePath } = await import("../dist/memomatic/corpus.js");
    const old = new Date(Date.now() - 120 * 86_400_000);
    const file = dailyNotePath(ctx.paths, old);
    await writeCorpusFile(
      ctx.paths,
      file,
      `${entryLine("Old episodic note subject to cleanup", {
        key: "old-note",
        observed: old.toISOString().slice(0, 10),
        origin: "agent",
      })}\n`,
    );
    await rebuildIndex(ctx);
    const relative = file.replace(`${ctx.paths.stateRoot}/`, "");
    const fetched = await getEntry(ctx, relative, 1);
    assert.match(fetched.content, /Old episodic note/);
    const entry = ctx.store.allEntries().find((item) => item.key === "old-note");
    assert.equal(ctx.store.usageFor(entry.stableId).useful, 1);

    assert.deepEqual(await archiveOldEpisodic(ctx), []);
    const { writeFileSync, mkdirSync } = await import("node:fs");
    mkdirSync(join(env.config, "memomatic"), { recursive: true });
    writeFileSync(
      join(env.config, "memomatic", "MEMORY_RULES.md"),
      "- auto-clean: older-than=90d scope=episodic\n",
      "utf8",
    );
    const fresh = await context();
    const archived = await archiveOldEpisodic(fresh);
    assert.equal(archived.length, 1);
    assert.ok(
      readdirSync(join(env.state, "memomatic", "archive")).includes("120-days-ago.md") ||
        archived[0].endsWith(".md"),
    );
    fresh.store.close();
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("mcp server lists tools and answers a search call", async () => {
  const env = environment();
  try {
    const ctx = await context();
    await writeEntry(ctx, { origin: "agent", text: "MCP contract keeps tool names functional." });
    await rebuildIndex(ctx);
    ctx.store.close();
    const list = JSON.parse(await handleMcpRequest({ id: 1, method: "tools/list" }));
    assert.deepEqual(list.result.tools.map((tool) => tool.name).sort(), [
      "memory_forget",
      "memory_get",
      "memory_search",
      "memory_write",
    ]);
    const call = JSON.parse(
      await handleMcpRequest({
        id: 2,
        method: "tools/call",
        params: { arguments: { query: "functional tool names" }, name: "memory_search" },
      }),
    );
    const payload = JSON.parse(call.result.content[0].text);
    assert.ok(payload.length >= 1);
    assert.match(payload[0].snippet, /tool names functional/);
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("plugin exposes memory tools and injects system context", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const { writeCorpusFile } = await import("../dist/memomatic/corpus.js");
    await writeCorpusFile(
      ctx.paths,
      ctx.paths.memoryFile,
      `${entryLine("Curated fact injected at session start", { key: "injected", origin: "user" })}\n`,
    );
    ctx.store.close();
    const hooks = await memomatic({ enabled: true });
    assert.deepEqual(Object.keys(hooks.tool).sort(), [
      "memory_forget",
      "memory_get",
      "memory_search",
      "memory_write",
    ]);
    const output = { system: [] };
    await hooks["experimental.chat.system.transform"]({}, output);
    assert.equal(output.system.length, 1);
    assert.match(output.system[0], /Curated fact injected at session start/);
    assert.match(output.system[0], /memory_search/);
    const disabled = await memomatic({ enabled: false });
    assert.deepEqual(disabled, {});
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("stable ids prefer keys and fall back to content digests", () => {
  assert.equal(stableIdFor("a.md", "text", "key-one"), "key:key-one");
  assert.match(stableIdFor("a.md", "text", null), /^sha:[0-9a-f]{24}$/);
});

test("extraction and consolidation parsers reject malformed payloads partially", () => {
  assert.deepEqual(
    parseExtraction(JSON.stringify({ candidates: [{ text: "ok" }, { text: "" }, "junk"] })),
    [{ key: null, reason: "", text: "ok" }],
  );
  assert.deepEqual(
    parseConsolidation(
      JSON.stringify({
        operations: [
          { line: "- Valid entry", op: "add" },
          { line: "not an entry", op: "add" },
          { key: "k", op: "drop" },
          { op: "bogus" },
        ],
      }),
    ),
    [
      { line: "- Valid entry", op: "add" },
      { key: "k", op: "drop" },
    ],
  );
});
