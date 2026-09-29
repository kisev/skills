import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import core from "../dist/index.js";
import rtk from "../dist/plugins/rtk.js";
import rules from "../dist/plugins/rules-injector.js";
import bell from "../dist/plugins/zed-bell.js";

function host(directory = "/project", options = {}) {
  const hooks = {};
  const tools = new Map();
  let emit;
  let aborted = false;
  const context = {
    location: { directory },
    options,
    agent: {
      list: async () => ({
        data: [
          {
            id: "mapper",
            name: "Mapper",
            permissions: [{ action: "edit", resource: "*", effect: "deny" }],
          },
        ],
      }),
    },
    tool: {
      hook: async (name, callback) => {
        hooks[name] = callback;
      },
      transform: async (callback) => callback({ add: (tool) => tools.set(tool.name, tool) }),
    },
    session: {
      hook: async (name, callback) => {
        hooks[name] = callback;
      },
      get: async () => ({ location: { directory } }),
    },
    event: {
      subscribe: async function* ({ signal }) {
        signal.addEventListener(
          "abort",
          () => {
            aborted = true;
            emit?.();
          },
          { once: true },
        );
        while (!signal.aborted) {
          const event = await new Promise((resolve) => {
            emit = resolve;
          });
          if (event) yield event;
        }
      },
    },
  };
  return { context, hooks, tools, emit: (event) => emit(event), aborted: () => aborted };
}

test("all entrypoints expose independently callable V1 and V2 implementations", async () => {
  for (const plugin of [core, rtk, rules, bell]) {
    assert.equal(typeof plugin.id, "string");
    assert.equal(typeof plugin.setup, "function");
    assert.equal(typeof plugin.server, "function");
    const hooks = await plugin.server({ directory: "/project" }, { enabled: false });
    assert.equal(typeof hooks, "object");
  }
});

test("V2 route uses host IDs, applies schema defaults, and enforces one-use receipts", async () => {
  const { context, hooks, tools } = host();
  await core.setup(context);
  assert.deepEqual([...tools.keys()], ["route"]);
  const route = tools.get("route");
  const input = route.input.parse({
    action: "preview",
    category: "exploration",
    task: "Inspect files",
  });
  assert.deepEqual(input.requirements, []);
  assert.throws(() => route.input.parse({ ...input, action: "unknown" }));
  const decision = JSON.parse((await route.execute(input, { sessionID: "s" })).content);
  assert.equal(decision.agent, "mapper");
  await assert.rejects(
    hooks["execute.before"]({ tool: "subagent", sessionID: "s", input: { agent: "mapper" } }),
    /active routing receipt/,
  );
  await route.execute({ ...input, action: "dispatch", decision }, { sessionID: "s" });
  await assert.rejects(
    hooks["execute.before"]({ tool: "subagent", sessionID: "s", input: { agent: "review" } }),
    /does not match/,
  );
  await hooks["execute.before"]({ tool: "subagent", sessionID: "s", input: { agent: "mapper" } });
  await assert.rejects(
    hooks["execute.before"]({ tool: "subagent", sessionID: "s", input: { agent: "mapper" } }),
    /receipt/,
  );
  await assert.rejects(
    hooks["execute.after"]({
      tool: "subagent",
      sessionID: "s",
      input: { agent: "mapper" },
      status: "completed",
      result: { content: "invalid report" },
    }),
    /JSON structured report/,
  );
});

test("V2 RTK compresses text and preserves files, output, metadata, and failures", async () => {
  const { context, hooks } = host("/project", { statsPath: null, run: async () => "compressed" });
  await rtk.setup(context);
  const file = { type: "file", uri: "file:///artifact", mime: "text/plain" };
  const event = {
    tool: "shell",
    sessionID: "s",
    input: { command: "git log" },
    status: "completed",
    result: {
      content: [{ type: "text", text: "x".repeat(9000) }, file],
      output: { code: 0 },
      metadata: { exit: 0 },
    },
  };
  await hooks["execute.after"](event);
  assert.match(event.result.content[0].text, /^compressed\n\[rtk:/);
  assert.deepEqual(event.result.content[1], file);
  assert.deepEqual(event.result.output, { code: 0 });
  assert.deepEqual(event.result.metadata, { exit: 0 });
  const failure = { ...event, status: "error", error: { message: "failed" } };
  await hooks["execute.after"](failure);
  assert.deepEqual(failure.error, { message: "failed" });
  const disabled = host("/project", { enabled: false });
  await rtk.setup(disabled.context);
  assert.deepEqual(disabled.hooks, {});
});

test("V2 rules use session directory and replay after compaction, with subscription cleanup", async () => {
  const directory = await mkdtemp(join(tmpdir(), "agentomatic-v2-rules-"));
  try {
    const sessionDirectory = join(directory, "session");
    await mkdir(join(sessionDirectory, "nested"), { recursive: true });
    await writeFile(join(sessionDirectory, "nested", "AGENTS.md"), "Nested rules");
    const state = host(join(directory, "other"));
    state.context.session.get = async () => ({ location: { directory: sessionDirectory } });
    const cleanup = await rules.setup(state.context);
    const event = {
      tool: "read",
      sessionID: "s",
      input: { path: "nested/file.ts" },
      status: "completed",
      result: { content: "file content" },
    };
    await state.hooks["execute.after"](event);
    assert.match(event.result.content, /Nested rules/);
    state.emit({ type: "session.compacted", data: { sessionID: "s" } });
    await new Promise((resolve) => setImmediate(resolve));
    const system = [{ type: "text", text: "Original system" }];
    await state.hooks.context({ sessionID: "s", system });
    assert.match(system[1].text, /Nested rules/);
    await state.hooks.context({ sessionID: "s", system });
    assert.equal(system.length, 2);
    await cleanup();
    assert.equal(state.aborted(), true);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("V2 bell is disabled by default and cleans up an enabled subscription", async () => {
  const disabled = host();
  assert.equal(await bell.setup(disabled.context), undefined);
  const enabled = host("/project", { enabled: true });
  const cleanup = await bell.setup(enabled.context);
  await cleanup();
  assert.equal(enabled.aborted(), true);
});
