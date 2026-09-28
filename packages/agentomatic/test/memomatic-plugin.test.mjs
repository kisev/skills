import assert from "node:assert/strict";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import memomatic from "../dist/plugins/memomatic.js";
import { entryLine, openMemomatic, writeCorpusFile, processInbox } from "@kisev/memomatic";

test("plugin exposes memory tools and injects system context", async () => {
  const root = mkdtempSync(join(tmpdir(), "agentomatic-memomatic-"));
  process.env.XDG_STATE_HOME = join(root, "state");
  process.env.XDG_CONFIG_HOME = join(root, "config");
  process.env.XDG_DATA_HOME = join(root, "data");
  try {
    const ctx = await openMemomatic();
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

    const queued = JSON.parse(
      await hooks.tool.memory_write.execute({
        source: "team-retro",
        text: "Plugin queues skill-sourced memory drops.",
      }),
    );
    const inboxFiles = readdirSync(join(root, "state", "memomatic", "inbox")).filter((name) =>
      name.endsWith(".md"),
    );
    assert.equal(inboxFiles.length, 1);
    assert.match(inboxFiles[0], /^team-retro-/);
    assert.match(String(queued), /inbox/);
    const flush = await openMemomatic();
    await processInbox(flush);
    flush.store.close();
    const hits = JSON.parse(
      await hooks.tool.memory_search.execute({ query: "Plugin queues skill-sourced memory drops" }),
    );
    assert.ok(hits.some((hit) => hit.source === "team-retro" && hit.visibility === "team"));

    const noSession = { system: [] };
    await hooks["experimental.chat.system.transform"]({ sessionID: "missing" }, noSession);
    assert.equal(noSession.system.length, 1);

    const disabled = await memomatic({ enabled: false });
    assert.deepEqual(disabled, {});
  } finally {
    rmSync(root, { force: true, recursive: true });
  }
});
