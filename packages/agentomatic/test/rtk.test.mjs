import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import rtk, {
  emptyRtkStats,
  readRtkStats,
  rtkCharsSaved,
  rtkStatsPath,
  rtkTokensSavedEstimate,
} from "../dist/plugins/rtk.js";

const LONG = "x".repeat(9_000);

function statsFile() {
  const directory = mkdtempSync(join(tmpdir(), "agentomatic-rtk-"));
  return { directory, path: join(directory, "stats.json") };
}

async function hook(payload, command, options) {
  const hooks = await rtk(options);
  return hooks["tool.execute.after"]({ tool: "bash", args: { command } }, payload);
}

test("rtk hook compresses eligible output and records compressed-rtk stats", async () => {
  const item = statsFile();
  try {
    const payload = { output: LONG.slice() };
    await hook(payload, "git log", { run: async () => "short", statsPath: item.path });
    assert.match(
      payload.output,
      /^short\n\[rtk: compressed method=rtk\/git-log; sizes=9000->5; evidence_complete=false; loss=possible\]$/,
    );
    const stats = await readRtkStats(item.path);
    assert.equal(stats.counters["compressed-rtk"], 1);
    assert.equal(stats.counters["below-threshold"], 0);
    assert.equal(stats.chars_original, 9_000);
    assert.equal(stats.chars_final, 5);
    assert.equal(rtkCharsSaved(stats), 8_995);
    assert.equal(rtkTokensSavedEstimate(stats), 2_249);
    assert.equal(stats.recent.length, 1);
    assert.equal(stats.recent[0].method, "compressed-rtk");
    assert.ok(stats.updated_at);
    assert.equal(readFileSync(item.path, "utf8").includes("x".repeat(64)), false);
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});

test("rtk hook counts ineligible, unavailable, and non-shortening rtk results", async () => {
  const item = statsFile();
  try {
    const ineligible = { output: LONG.slice() };
    await hook(ineligible, "npm test", { run: async () => "short", statsPath: item.path });
    assert.match(ineligible.output, /method=head\+tail/);
    const unavailable = { output: LONG.slice() };
    await hook(unavailable, "git diff", { run: async () => undefined, statsPath: item.path });
    assert.match(unavailable.output, /method=head\+tail/);
    const notShorter = { output: LONG.slice() };
    await hook(notShorter, "git status", {
      run: async () => `y${LONG}`,
      statsPath: item.path,
    });
    assert.match(notShorter.output, /method=head\+tail/);
    const stats = await readRtkStats(item.path);
    assert.equal(stats.counters.ineligible, 1);
    assert.equal(stats.counters["rtk-unavailable"], 1);
    assert.equal(stats.counters["truncated-head-tail"], 1);
    assert.equal(stats.counters["compressed-rtk"], 0);
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});

test("rtk hook leaves below-threshold output untouched and counts it", async () => {
  const item = statsFile();
  try {
    const payload = { output: "ok" };
    await hook(payload, "pytest", { run: async () => "nope", statsPath: item.path });
    assert.equal(payload.output, "ok");
    const stats = await readRtkStats(item.path);
    assert.equal(stats.counters["below-threshold"], 1);
    assert.equal(stats.chars_original, 0);
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});

test("rtk stats cap recent events and ignore non-bash tools", async () => {
  const item = statsFile();
  try {
    for (let index = 0; index < 25; index += 1)
      await hook({ output: "ok" }, "pytest tests/", { statsPath: item.path });
    const edited = { output: "oldString not found" };
    const hooks = await rtk({ statsPath: item.path });
    await hooks["tool.execute.after"]({ tool: "edit" }, edited);
    assert.equal(edited.output, "oldString not found\nSTOP. Read the file before retrying Edit.");
    const stats = await readRtkStats(item.path);
    assert.equal(stats.counters["below-threshold"], 25);
    assert.ok(stats.recent.length <= 20);
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});

test("rtk stats failures stay fail-open and optional stats disable persistence", async () => {
  const item = statsFile();
  try {
    const blocked = join(item.directory, "file.txt", "stats.json");
    writeFileSync(join(item.directory, "file.txt"), "file\n");
    const payload = { output: LONG.slice() };
    await hook(payload, "git log", { run: async () => "short", statsPath: blocked });
    assert.match(payload.output, /method=rtk\/git-log/);
    const disabled = { output: LONG.slice() };
    await hook(disabled, "git log", { run: async () => "short", statsPath: null });
    assert.match(disabled.output, /method=rtk\/git-log/);
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});

test("readRtkStats validates shape and rtkStatsPath stays inside the rtk state root", async () => {
  const item = statsFile();
  try {
    writeFileSync(item.path, "{not-json\n");
    assert.equal(await readRtkStats(item.path), undefined);
    writeFileSync(item.path, `${JSON.stringify({ schema_version: 2 })}\n`);
    assert.equal(await readRtkStats(item.path), undefined);
    const base = emptyRtkStats();
    base.counters["compressed-rtk"] = 3;
    base.chars_original = 100;
    base.chars_final = 40;
    writeFileSync(item.path, `${JSON.stringify(base)}\n`);
    const stats = await readRtkStats(item.path);
    assert.equal(stats.counters["compressed-rtk"], 3);
    assert.equal(rtkCharsSaved(stats), 60);
    assert.equal(rtkTokensSavedEstimate(stats), 15);
    assert.ok(dirname(rtkStatsPath()).endsWith(join("opencode", "skills", "rtk")));
  } finally {
    rmSync(item.directory, { recursive: true, force: true });
  }
});
