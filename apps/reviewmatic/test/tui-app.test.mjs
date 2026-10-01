import assert from "node:assert/strict";
import { PassThrough } from "node:stream";
import { stripVTControlCharacters } from "node:util";
import test from "node:test";
import React from "react";
import { render } from "ink";
import { ReviewApp } from "../dist/tui/app.js";
import { stringsFor } from "../dist/tui/strings.js";

const tick = () => new Promise((resolve) => setTimeout(resolve, 40));

function terminal(t, { readonly = true } = {}) {
  const previous = { rows: process.stdout.rows, columns: process.stdout.columns };
  process.stdout.rows = 18;
  process.stdout.columns = 50;
  const stdin = new PassThrough();
  stdin.isTTY = true;
  stdin.setRawMode = () => {};
  stdin.ref = () => {};
  stdin.unref = () => {};
  const stdout = new PassThrough();
  stdout.isTTY = true;
  stdout.columns = 50;
  stdout.rows = 18;
  const frames = [];
  stdout.on("data", (data) => frames.push(stripVTControlCharacters(data.toString())));
  let current;
  const requests = [];
  const items = Array.from({ length: 40 }, (_, index) => ({
    key: `thread-${index}`,
    kind: "thread",
    title: `Remark ${index}`,
    path: "src/file.ts",
    line: index + 1,
    publicationId: `thread-${index}`,
    body: readonly ? null : "Draft reply",
    url: `https://gitlab.example/g/p/-/merge_requests/7#note_${index}`,
    conversation: [
      {
        author: { username: "reviewer" },
        body: `Full original discussion ${index}\n${"long line ".repeat(60)}`,
        system: false,
      },
    ],
    detail: {
      state: "resolved",
      outcome: readonly ? "no_publication" : "reply",
      assessment: "fixed",
      rationale: "Confirmed against the exact committed code.",
      fix_mode: "not_required",
    },
    actions: readonly
      ? []
      : [
          {
            id: `reply-${index}`,
            operation: "reply",
            publication_id: `thread-${index}`,
            command: "invalid-action",
            kind: "thread",
            path: null,
            line: null,
          },
        ],
  }));
  const initial = {
    bundle: {
      plan: { verdict: "ready", target: { url: "https://gitlab.example/g/p/-/merge_requests/7" } },
    },
    items,
    view: "overview",
    index: 0,
    offset: 0,
    statuses: {},
    messages: [],
    busy: false,
    worktree: null,
    editedBodies: {},
  };
  const instance = render(
    React.createElement(ReviewApp, {
      initial,
      strings: stringsFor("en"),
      persist: (state) => {
        current = state;
      },
      request: (request) => requests.push(request),
    }),
    {
      stdin,
      stdout,
      stderr: new PassThrough(),
      patchConsole: false,
      exitOnCtrlC: false,
      maxFps: 100,
    },
  );
  t.after(() => {
    instance.unmount();
    stdin.end();
    stdout.end();
    process.stdout.rows = previous.rows;
    process.stdout.columns = previous.columns;
  });
  return {
    frames,
    screen: () => frames.filter((frame) => frame.includes("reviewmatic")).at(-1) ?? "",
    requests,
    state: () => current,
    key: async (key) => {
      stdin.write(key);
      await tick();
    },
  };
}

test("bounded overview, complete discussion, resize, and next-item navigation in Ink", async (t) => {
  const terminalState = terminal(t);
  await tick();
  assert.ok(!terminalState.screen().includes("Remark 39"));
  await terminalState.key("\r");
  assert.equal(terminalState.state().view, "detail");
  assert.match(terminalState.screen(), /Full original discussion 0/);
  assert.match(terminalState.screen(), /https:\/\/gitlab.example/);
  assert.deepEqual(terminalState.state().statuses, {});
  await terminalState.key("\x1b[6~");
  assert.ok(terminalState.state().offset > 0);
  process.stdout.columns = 35;
  process.stdout.rows = 16;
  process.stdout.emit("resize");
  await tick();
  await terminalState.key("\x1b[C");
  assert.equal(terminalState.state().index, 1);
  assert.equal(terminalState.state().offset, 0);
  assert.equal(terminalState.state().view, "detail");
  await terminalState.key("s");
  assert.deepEqual(terminalState.state().statuses, {});
  await terminalState.key("\x1b");
  assert.equal(terminalState.state().view, "overview");
  await terminalState.key("q");
  assert.equal(terminalState.requests.at(-1).kind, "quit");
});

test("opening or pressing Enter does not publish; sending requires explicit confirmation", async (t) => {
  const terminalState = terminal(t, { readonly: false });
  await tick();
  await terminalState.key("\r");
  await terminalState.key("\r");
  assert.deepEqual(terminalState.state().statuses, {});
  await terminalState.key("s");
  assert.match(terminalState.screen(), /y confirm/);
  assert.deepEqual(terminalState.state().statuses, {});
  await terminalState.key("n");
  assert.equal(terminalState.state().view, "detail");
  assert.deepEqual(terminalState.state().statuses, {});
  await terminalState.key("e");
  assert.equal(terminalState.requests.at(-1).kind, "edit");
  assert.equal(terminalState.requests.at(-1).target.body, "Draft reply");
});
