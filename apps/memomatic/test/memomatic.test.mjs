import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  mkdirSync,
  writeFileSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { parseEntryLine, entryLine } from "../dist/entries.js";
import { parseRules, isForbidden } from "../dist/rules.js";
import { visibilityForSource } from "../dist/visibility.js";
import { dropToInbox, processInbox, withRunLock } from "../dist/inbox.js";
import {
  openMemomatic,
  rebuildIndex,
  searchMemory,
  writeEntry,
  getEntry,
  forgetEntry,
  archiveOldEpisodic,
} from "../dist/service.js";
import { runDream, parseExtraction, parseConsolidation } from "../dist/dream.js";
import { handleMcpRequest } from "../dist/mcp.js";
import { stableIdFor } from "../dist/store.js";

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

test("cli --version reports the package version without touching state", () => {
  const { version } = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  const output = execFileSync(process.execPath, ["dist/cli.js", "--version"], {
    cwd: new URL("..", import.meta.url),
    encoding: "utf8",
    env: {
      ...process.env,
      XDG_STATE_HOME: join(tmpdir(), "memomatic-cli-version-must-not-exist"),
    },
  });
  assert.equal(output.trim(), version);
  assert.ok(!existsSync(join(tmpdir(), "memomatic-cli-version-must-not-exist")));
});

test("entry annotations roundtrip through parse and serialize", () => {
  const line = entryLine("Keep the gateway on loopback.", {
    importance: 9,
    key: "gateway-loopback",
    origin: "user",
    observed: "2026-09-26",
    pinned: true,
    project: "github.com/kisev/skills",
    source: "team-retro",
    trigger: ["gateway setup", "network safety"],
  });
  const parsed = parseEntryLine(line);
  assert.ok(parsed);
  assert.equal(parsed.text, "- Keep the gateway on loopback.");
  assert.equal(parsed.annotations.key, "gateway-loopback");
  assert.equal(parsed.annotations.importance, 9);
  assert.equal(parsed.annotations.pinned, true);
  assert.equal(parsed.annotations.project, "github.com/kisev/skills");
  assert.equal(parsed.annotations.source, "team-retro");
  assert.deepEqual(parsed.annotations.trigger, ["gateway setup", "network safety"]);
  assert.equal(visibilityForSource("team-retro"), "team");
  assert.equal(visibilityForSource("spec-manage"), "team");
  assert.equal(visibilityForSource("gitlab"), "team");
  assert.equal(visibilityForSource("people-journal"), "personal");
  assert.equal(visibilityForSource(null), "personal");
  assert.equal(
    parseEntryLine("- Bad <!-- source: UP_CASE --> <!-- origin: user -->")?.annotations.source,
    undefined,
  );
});

test("rules parsing extracts never-save topics and auto-clean", () => {
  const rules = parseRules(
    "# Memory rules\n\n- never-save: internal credentials\n- never-save: team private notes\n- auto-clean: older-than=90d scope=episodic\n- prose the service must ignore\n",
  );
  assert.deepEqual(rules.neverSave, ["internal credentials", "team private notes"]);
  assert.deepEqual(rules.autoClean, { olderThanDays: 90, scope: "episodic", source: undefined });
  assert.ok(isForbidden("Don't store INTERNAL CREDENTIALS here", rules));
  assert.ok(!isForbidden("ordinary engineering fact", rules));
  const sourced = parseRules("- auto-clean: older-than=30d scope=episodic source=stopit\n");
  assert.deepEqual(sourced.autoClean, { olderThanDays: 30, scope: "episodic", source: "stopit" });
});

test("writeEntry queues to the inbox and processInbox moves entries into the corpus", async () => {
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
      source: "team-retro",
      text: "Release helper requires pnpm because the taskfile pins it.",
    });
    await assert.rejects(
      writeEntry(ctx, { origin: "agent", text: "The internal credentials are abc" }),
      /never-save/,
    );
    const inboxFiles = readdirSync(join(env.state, "memomatic", "inbox")).filter((name) =>
      name.endsWith(".md"),
    );
    assert.equal(inboxFiles.length, 1);
    assert.match(inboxFiles[0], /^team-retro-/);
    const dailyDir = join(env.state, "memomatic", "memory");
    assert.ok(!existsSync(dailyDir) || readdirSync(dailyDir).length === 0);
    const report = await processInbox(ctx);
    assert.equal(report.filesProcessed, 1);
    assert.equal(report.entriesAppended, 1);
    const files = readdirSync(dailyDir);
    assert.equal(files.length, 1);
    const body = readFileSync(join(dailyDir, files[0]), "utf8");
    assert.match(body, /Release helper requires pnpm/);
    assert.match(body, /source: team-retro/);
    assert.deepEqual(
      readdirSync(join(env.state, "memomatic", "inbox")).filter((name) => name.endsWith(".md")),
      [],
    );
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("processInbox deduplicates, supersedes by key, rejects invalid files, routes user targets", async () => {
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
    await dropToInbox(
      ctx.paths,
      [
        entryLine("Mirror fact about the pipelines profile", {
          key: "people-pipelines-42",
          origin: "agent",
          source: "people-journal",
        }),
      ],
      "people-journal",
    );
    let report = await processInbox(ctx);
    assert.equal(report.entriesAppended, 1);
    const dailyFiles = readdirSync(join(env.state, "memomatic", "memory"));
    const firstBody = readFileSync(join(env.state, "memomatic", "memory", dailyFiles[0]), "utf8");

    await dropToInbox(
      ctx.paths,
      [
        entryLine("Mirror fact about the pipelines profile", {
          key: "people-pipelines-42",
          origin: "agent",
          source: "people-journal",
        }),
        entryLine("Updated mirror fact about the pipelines profile", {
          key: "people-pipelines-42",
          origin: "agent",
          source: "people-journal",
        }),
      ],
      "people-journal",
    );
    report = await processInbox(ctx);
    assert.equal(report.entriesDuplicated, 1);
    assert.equal(report.entriesSuperseded, 1);
    assert.equal(report.entriesAppended, 0);
    const secondBody = readFileSync(join(env.state, "memomatic", "memory", dailyFiles[0]), "utf8");
    assert.ok(!/^.*- Mirror fact about the pipelines profile(?! Updated)/m.test(secondBody));
    assert.match(secondBody, /Updated mirror fact about the pipelines profile/);
    assert.equal(secondBody.split("\n").filter((line) => line.trim()).length, 1);
    void firstBody;

    await dropToInbox(ctx.paths, ["not an entry line", "# heading"], "docs-prepare");
    report = await processInbox(ctx);
    assert.equal(report.filesRejected, 1);
    assert.equal(report.linesInvalid, 2);
    assert.ok(
      readdirSync(join(env.state, "memomatic", "inbox", "rejected")).some((name) =>
        name.startsWith("docs-prepare-"),
      ),
    );

    await dropToInbox(
      ctx.paths,
      [
        entryLine("Store the internal credentials somewhere", {
          origin: "agent",
          source: "mattermost-triage",
        }),
      ],
      "mattermost-triage",
    );
    report = await processInbox(ctx);
    assert.equal(report.linesForbidden, 1);
    assert.equal(report.filesRejected, 1);

    await dropToInbox(
      ctx.paths,
      [
        entryLine("Preferred editor uses two-space indentation", {
          origin: "user",
          source: "user",
          target: "user",
        }),
      ],
      "user",
    );
    report = await processInbox(ctx);
    assert.equal(report.entriesAppended, 1);
    const userBody = readFileSync(join(env.state, "memomatic", "USER.md"), "utf8");
    assert.match(userBody, /two-space indentation/);
    assert.ok(!/target:/.test(userBody));
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("run lock serializes concurrent runs", async () => {
  const env = environment();
  try {
    const ctx = await context();
    await withRunLock(ctx.paths, async () => {
      await assert.rejects(
        withRunLock(ctx.paths, async () => "never"),
        /another memomatic run/,
      );
    });
    const result = await withRunLock(ctx.paths, async () => "done");
    assert.equal(result, "done");
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
    await processInbox(ctx);
    const { writeCorpusFile } = await import("../dist/corpus.js");
    const { dailyNotePath } = await import("../dist/corpus.js");
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
    await processInbox(ctx);
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
    const fallback = await runDream(dream, { name: "invalid", complete: async () => "not JSON" });
    assert.equal(fallback.appendOnlyFallback, true);
    assert.match(readFileSync(dream.paths.memoryFile, "utf8"), /deterministic gates/);
    dream.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("consolidation falls back to append-only when drop loss exceeds the bound", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const { writeCorpusFile } = await import("../dist/corpus.js");
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
    await processInbox(ctx);
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
    dream.store.setMeta("ingest-watermark", "123");
    const before = readFileSync(dream.paths.indexFile);
    const walBefore = readFileSync(`${dream.paths.indexFile}-wal`);
    const executor = {
      complete: async () =>
        JSON.stringify({ candidates: [{ key: null, reason: "r", text: "Dry run only." }] }),
      name: "fake",
    };
    const report = await runDream(dream, executor, { dryRun: true });
    assert.equal(report.dryRun, true);
    const dailyDir = join(env.state, "memomatic", "memory");
    assert.ok(!existsSync(dailyDir) || readdirSync(dailyDir).length === 0);
    assert.deepEqual(readFileSync(dream.paths.indexFile), before);
    assert.deepEqual(readFileSync(`${dream.paths.indexFile}-wal`), walBefore);
    assert.equal(dream.store.getMeta("ingest-watermark"), "123");
    await runDream(dream, null);
    assert.equal(dream.store.getMeta("ingest-watermark"), "123");
    dream.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("CLI previews do not create state, a database, or run locks", () => {
  const env = environment();
  try {
    for (const command of ["process", "dream"]) {
      execFileSync(process.execPath, ["dist/cli.js", command, "--dry-run"], {
        env: process.env,
        cwd: new URL("..", import.meta.url),
      });
      assert.equal(existsSync(env.state), false);
      assert.equal(existsSync(env.config), false);
    }
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("sessions skipped without a model remain available after model setup", async () => {
  const env = environment();
  try {
    const { DatabaseSync } = await import("node:sqlite");
    const data = join(env.root, "data", "opencode");
    mkdirSync(data, { recursive: true });
    const database = new DatabaseSync(join(data, "opencode.db"));
    database.exec(
      "CREATE TABLE session(id TEXT, title TEXT, directory TEXT, time_created INTEGER); CREATE TABLE message(session_id TEXT, data TEXT, time_created INTEGER);",
    );
    database
      .prepare("INSERT INTO session VALUES (?, ?, ?, ?)")
      .run("example", "A decision", env.root, 2000);
    database.prepare("INSERT INTO message VALUES (?, ?, ?)").run(
      "example",
      JSON.stringify({
        role: "user",
        parts: [{ type: "text", text: "Remember a standing decision." }],
      }),
      2000,
    );
    database.close();
    const ctx = await context();
    ctx.store.setMeta("ingest-watermark", "123");
    const skipped = await runDream(ctx, null);
    assert.equal(skipped.sessionsIngested, 0);
    assert.equal(ctx.store.getMeta("ingest-watermark"), "123");
    const processed = await runDream(ctx, {
      name: "fixture",
      complete: async () => '{"candidates":[]}',
    });
    assert.equal(processed.sessionsIngested, 1);
    assert.equal(ctx.store.getMeta("ingest-watermark"), "2000");
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("memory reads and deletes reject traversal, sibling roots, symlinks, and invalid lines", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const outside = join(env.state, "memomatic-sibling", "private.md");
    mkdirSync(join(env.state, "memomatic-sibling"));
    writeFileSync(outside, "private");
    symlinkSync(outside, join(ctx.paths.stateRoot, "link.md"));
    for (const file of ["../memomatic-sibling/private.md", outside, "link.md"]) {
      await assert.rejects(getEntry(ctx, file));
      await assert.rejects(forgetEntry(ctx, { file, line: 1 }));
      assert.equal(readFileSync(outside, "utf8"), "private");
    }
    writeFileSync(ctx.paths.memoryFile, "- safe\n");
    for (const line of [0, 1.5, NaN]) await assert.rejects(getEntry(ctx, "MEMORY.md", line));
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("auto-clean preserves unrelated, pinned, and fresh entries in the same daily file", async () => {
  const env = environment();
  try {
    const ctx = await context();
    ctx.rules.autoClean = { olderThanDays: 30, scope: "episodic", source: "stopit" };
    const { writeCorpusFile, dailyNotePath } = await import("../dist/corpus.js");
    const file = dailyNotePath(ctx.paths);
    const lines = [
      entryLine("remove", { observed: "2020-01-01", source: "stopit" }),
      entryLine("other source", { observed: "2020-01-01", source: "user" }),
      entryLine("pinned", { observed: "2020-01-01", source: "stopit", pinned: true }),
      entryLine("fresh", { observed: new Date().toISOString().slice(0, 10), source: "stopit" }),
    ];
    await writeCorpusFile(ctx.paths, file, `${lines.join("\n")}\n`);
    await rebuildIndex(ctx);
    await archiveOldEpisodic(ctx);
    assert.equal(readFileSync(file, "utf8"), `${lines.slice(1).join("\n")}\n`);
    await rebuildIndex(ctx);
    assert.deepEqual(await archiveOldEpisodic(ctx), []);
    ctx.store.close();
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("memory_get marks useful and archive respects auto-clean rules", async () => {
  const env = environment();
  try {
    const ctx = await context();
    const { writeCorpusFile, dailyNotePath } = await import("../dist/corpus.js");
    const old = new Date(Date.now() - 120 * 86_400_000);
    const file = dailyNotePath(ctx.paths, old);
    const stopitFile = dailyNotePath(ctx.paths, new Date(old.getTime() - 86_400_000));
    await writeCorpusFile(
      ctx.paths,
      file,
      `${entryLine("Old episodic note subject to cleanup", {
        key: "old-note",
        observed: old.toISOString().slice(0, 10),
        origin: "agent",
      })}\n`,
    );
    await writeCorpusFile(
      ctx.paths,
      stopitFile,
      `${entryLine("Old stopit handoff distillate subject to cleanup", {
        key: "old-stopit",
        observed: old.toISOString().slice(0, 10),
        origin: "agent",
        source: "stopit",
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
      "- auto-clean: older-than=90d scope=episodic source=stopit\n",
      "utf8",
    );
    const scoped = await context();
    const scopedArchived = await archiveOldEpisodic(scoped);
    assert.equal(scopedArchived.length, 1);
    assert.ok(scopedArchived[0].endsWith(".md"));
    assert.ok(!existsSync(stopitFile));
    assert.ok(existsSync(file));
    scoped.store.close();

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

test("MCP exposes the complete explicit memory lifecycle without plugin hooks", async () => {
  const env = environment();
  try {
    const ctx = await context();
    await writeEntry(ctx, { origin: "agent", text: "MCP contract keeps tool names functional." });
    await processInbox(ctx);
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
    assert.equal(payload[0].source, "agent");
    assert.equal(payload[0].visibility, "personal");
    const entry = { file: payload[0].file, line: payload[0].line };
    const get = JSON.parse(
      await handleMcpRequest({
        id: 4,
        method: "tools/call",
        params: { arguments: entry, name: "memory_get" },
      }),
    );
    assert.match(JSON.parse(get.result.content[0].text).content, /tool names functional/);
    const forget = JSON.parse(
      await handleMcpRequest({
        id: 5,
        method: "tools/call",
        params: { arguments: entry, name: "memory_forget" },
      }),
    );
    assert.equal(JSON.parse(forget.result.content[0].text).forgotten, true);
    const afterForget = JSON.parse(
      await handleMcpRequest({
        id: 6,
        method: "tools/call",
        params: { arguments: { query: "functional tool names" }, name: "memory_search" },
      }),
    );
    assert.deepEqual(JSON.parse(afterForget.result.content[0].text), []);
    const write = JSON.parse(
      await handleMcpRequest({
        id: 3,
        method: "tools/call",
        params: {
          arguments: {
            origin: "agent",
            source: "team-retro",
            text: "MCP write queues an inbox drop.",
          },
          name: "memory_write",
        },
      }),
    );
    const writePayload = JSON.parse(write.result.content[0].text);
    assert.equal(writePayload.queued, true);
    assert.match(writePayload.flushHint, /memomatic process/);
  } finally {
    rmSync(env.root, { force: true, recursive: true });
  }
});

test("forgetting preserves surviving vectors and line references without embedding access", async () => {
  const env = environment();
  try {
    const ctx = await context();
    writeFileSync(
      ctx.paths.memoryFile,
      "- Remove this fact. <!-- key: remove -->\n- Keep this fact. <!-- key: keep -->\n",
    );
    await rebuildIndex(ctx);
    for (const entry of ctx.store.allEntries())
      ctx.store.setVector(entry.stableId, new Float32Array([1, 0]));
    ctx.settings.embedding = { url: "http://127.0.0.1:1/v1/embeddings", model: "unavailable" };
    await withRunLock(ctx.paths, async () => {
      await assert.rejects(
        forgetEntry(ctx, { file: "MEMORY.md", line: 1 }),
        /another memomatic run/,
      );
    });
    await forgetEntry(ctx, { file: "MEMORY.md", line: 1 });
    assert.deepEqual(
      ctx.store.allEntries().map((entry) => [entry.key, entry.line]),
      [["keep", 1]],
    );
    assert.deepEqual(
      ctx.store.vectors().map((row) => row.stableId),
      ["key:keep"],
    );
    assert.match((await getEntry(ctx, "MEMORY.md", 1)).content, /Keep this fact/);
    ctx.store.close();
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
