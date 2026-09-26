import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import memomatic from "../dist/plugins/memomatic.js";
import { entryLine, openMemomatic, writeCorpusFile } from "@kisev/memomatic";

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
    const disabled = await memomatic({ enabled: false });
    assert.deepEqual(disabled, {});
  } finally {
    rmSync(root, { force: true, recursive: true });
  }
});
