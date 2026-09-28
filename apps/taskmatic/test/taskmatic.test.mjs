import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync, readFileSync, writeFileSync, symlinkSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import {
  Store,
  ttl,
  rootPath,
  filterCards,
  TOOLS,
  callTool,
  dispatchMcp,
  exportAll,
  renderPage,
  serve,
} from "../dist/index.js";

import test from "node:test";
const CLI = new URL("../dist/cli.js", import.meta.url);
async function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "taskmatic-ts-"));
  const store = await Store.open(join(root, "state"));
  t.after(() => {
    store.close();
    rmSync(root, { recursive: true, force: true });
  });
  return { root, store };
}
test("card lifecycle preserves relations, labels, notes, selective edits and bounded activity", async (t) => {
  const { store } = await fixture(t);
  const parent = store.mutate("create", {
    title: "Parent",
    priority: "high",
    labels: ["b", "a", "b"],
    notes: "keep",
  });
  const child = store.mutate("create", { title: "Child", board: "ops", parent: parent.id });
  assert.deepEqual(store.read(parent.id).children, [child.id]);
  assert.deepEqual(parent.labels, ["a", "b"]);
  const edited = store.mutate("edit", { id: parent.id, title: "Changed", assignee: "alice" });
  assert.equal(edited.notes, "keep");
  assert.equal(edited.priority, "high");
  assert.equal(store.mutate("edit", { id: parent.id, assignee: null }).assignee, null);
  assert.throws(() => store.mutate("edit", { id: parent.id }), /requires/);
  for (let i = 0; i < 22; i++) store.mutate("note", { id: child.id, text: `Progress ${i}` });
  assert.equal(store.read(child.id).activity.length, 20);
  assert.equal(store.mutate("move", { id: child.id, status: "review" }).status, "review");
  assert.equal(filterCards(store.snapshot(), { board: "ops", status: "review" })[0].id, child.id);
  for (const args of [
    { title: "" },
    { title: "a\nb" },
    { title: "x", board: "../bad" },
    { title: "x", priority: "bogus" },
    { title: "x", parent: "deadbeef" },
    { title: "x", labels: [""] },
  ])
    assert.throws(() => store.mutate("create", args));
  assert.throws(() => store.mutate("move", { id: parent.id, status: "archived" }));
  assert.throws(() => store.mutate("note", { id: parent.id, text: " " }));
  assert.throws(() => store.mutate("note", { id: parent.id, text: "x".repeat(8001) }));
});
test("claims are atomic across connections; expiry, heartbeat, release and completion retain semantics", async (t) => {
  const { store } = await fixture(t);
  const second = await Store.open(store.root);
  t.after(() => second.close());
  const card = store.mutate("create", { title: "Work" });
  assert.equal(
    store.mutate("claim", { id: card.id, agent: "one", ttl_seconds: 60 }).status,
    "doing",
  );
  assert.throws(() => second.mutate("claim", { id: card.id, agent: "two" }), /claimed/);
  assert.throws(() => second.mutate("release", { id: card.id, agent: "two" }), /claimed/);
  assert.throws(() => second.mutate("heartbeat", { id: card.id, agent: "two" }), /not held/);
  assert.ok(
    store.mutate("heartbeat", { id: card.id, agent: "one", ttl_seconds: 600 })
      .claim_remaining_seconds > 590,
  );
  store.db
    .prepare("UPDATE cards SET claim_expires_at='2000-01-01T00:00:00Z' WHERE id=?")
    .run(card.id);
  assert.equal(second.read(card.id).claim_state, "expired");
  assert.equal(second.mutate("claim", { id: card.id, agent: "two" }).claimed_by, "two");
  assert.equal(second.mutate("complete", { id: card.id }).claimed_by, null);
  assert.throws(() => store.mutate("claim", { id: card.id, agent: " " }));
  for (const invalid of [0, -1, 2592001, "30x", "", NaN]) assert.throws(() => ttl(invalid));
  assert.equal(ttl("30m"), 1800);
  assert.equal(ttl("2h"), 7200);
  assert.equal(ttl("1d"), 86400);
});
test("SQLite v1 from the Python implementation opens without data or schema migration", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "taskmatic-legacy-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const python = spawnSync(
    "python3",
    [
      "-c",
      `
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.executescript("""
CREATE TABLE boards(slug TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE cards(id TEXT PRIMARY KEY,board TEXT NOT NULL REFERENCES boards(slug),title TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'todo',priority TEXT NOT NULL DEFAULT 'normal',labels TEXT NOT NULL DEFAULT '[]',assignee TEXT,parent TEXT REFERENCES cards(id),linked TEXT,claimed_by TEXT,claim_expires_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX cards_board_status ON cards(board,status);
CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,card TEXT NOT NULL REFERENCES cards(id),kind TEXT NOT NULL,actor TEXT NOT NULL,at TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '');
CREATE INDEX events_card ON events(card,id);
INSERT INTO boards VALUES ('main','Existing','2020-01-01T00:00:00Z','2020-01-01T00:00:00Z');
INSERT INTO cards VALUES ('0123abcd','main','Old card','Retain notes','doing','high','["legacy"]','alice',NULL,'REF-1','worker','2099-01-01T00:00:00Z','2020-01-01T00:00:00Z','2020-01-01T00:00:00Z');
INSERT INTO events(card,kind,actor,at,detail) VALUES ('0123abcd','note','alice','2020-01-01T00:00:00Z','Retain event');
PRAGMA user_version=1;
""")
c.commit();c.close()
`,
      join(root, "taskmatic.db"),
    ],
    { encoding: "utf8" },
  );
  assert.equal(python.status, 0, python.stderr);
  const store = await Store.open(root);
  try {
    const card = store.read("0123abcd");
    assert.equal(card.notes, "Retain notes");
    assert.equal(card.activity[0].detail, "Retain event");
    assert.equal(card.claimed_by, "worker");
    assert.equal(card.claim_state, "held");
    assert.equal(card.linked, "REF-1");
    assert.deepEqual(card.labels, ["legacy"]);
    store.mutate("edit", { id: card.id, title: "Updated" });
    assert.equal(store.db.prepare("PRAGMA user_version").get().user_version, 1);
  } finally {
    store.close();
  }
});
test("MCP preserves tool names, lifecycle, errors and notification behavior", async (t) => {
  const { store } = await fixture(t);
  assert.deepEqual(
    TOOLS.map((tool) => tool.name),
    [
      "boards",
      "list",
      "read",
      "create",
      "edit",
      "move",
      "claim",
      "heartbeat",
      "release",
      "complete",
      "note",
    ].map((name) => `taskmatic_${name}`),
  );
  assert.equal(
    (await dispatchMcp(store, { id: 1, method: "initialize" })).result.serverInfo.name,
    "taskmatic",
  );
  assert.equal(await dispatchMcp(store, { method: "notifications/initialized" }), null);
  assert.deepEqual((await dispatchMcp(store, { id: 2, method: "ping" })).result, {});
  assert.equal((await dispatchMcp(store, { id: 3, method: "bogus" })).error.code, -32601);
  const created = await callTool(store, "taskmatic_create", { title: "MCP work" });
  assert.equal(created.isError, false);
  const id = created.structuredContent.id;
  assert.equal((await callTool(store, "taskmatic_claim", { id, agent: "one" })).isError, false);
  assert.equal((await callTool(store, "taskmatic_claim", { id, agent: "two" })).isError, true);
  assert.equal((await callTool(store, "taskmatic_read", { id })).structuredContent.id, id);
  assert.equal((await callTool(store, "taskmatic_edit", { id, assignee: null })).isError, false);
  assert.equal((await callTool(store, "taskmatic_note", { id, text: "done" })).isError, false);
  assert.equal(
    (await callTool(store, "taskmatic_complete", { id })).structuredContent.status,
    "done",
  );
  assert.equal(
    (await callTool(store, "taskmatic_boards", {})).structuredContent.boards[0].cards,
    1,
  );
  for (const args of [
    { id, agent: "one", ttl_seconds: 0 },
    { id, agent: "one", ttl_seconds: 1.5 },
    { id, agent: "one", unexpected: true },
  ])
    assert.equal((await callTool(store, "taskmatic_claim", args)).isError, true);
});
test("exports are escaped, private, idempotent and remove stale card filenames", async (t) => {
  const { store } = await fixture(t);
  const card = store.mutate("create", { title: "Old title", notes: "Notes" });
  await exportAll(store);
  const old = join(store.root, "export/boards/main/cards", `${card.id}-old-title.md`);
  assert.ok(existsSync(old));
  assert.match(readFileSync(old, "utf8"), /Notes/);
  store.mutate("edit", { id: card.id, title: "New title" });
  await exportAll(store);
  assert.equal(existsSync(old), false);
  const updated = join(store.root, "export/boards/main/cards", `${card.id}-new-title.md`);
  const first = readFileSync(updated, "utf8");
  await exportAll(store);
  assert.equal(readFileSync(updated, "utf8"), first);
  store.mutate("create", { title: "</script><b>markup</b>" });
  const page = await renderPage(store.snapshot());
  assert.ok(!page.includes("</script><b>"));
  assert.ok(page.includes("\\u003c/script>"));
});
test("web is loopback-only, read-only, live and does not create a missing store", async (t) => {
  const { store, root } = await fixture(t);
  await assert.rejects(serve(join(root, "absent"), "127.0.0.1", 0));
  assert.equal(existsSync(join(root, "absent")), false);
  await assert.rejects(serve(store.root, "0.0.0.0", 0), /loopback/);
  const server = await serve(store.root, "127.0.0.1", 0);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const url = `http://127.0.0.1:${server.address().port}`;
  assert.equal((await fetch(url)).status, 200);
  assert.equal((await fetch(url, { method: "POST" })).status, 405);
  assert.equal((await fetch(`${url}/unknown`)).status, 404);
  store.mutate("create", { title: "Added after startup" });
  const response = await fetch(`${url}/snapshot.json`);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal((await response.json()).cards[0].title, "Added after startup");
});
test("CLI contract, stdin notes and stdio MCP work without shell wrappers", async (t) => {
  const { root } = await fixture(t);
  const home = join(root, "cli-state");
  const run = (args, input) =>
    spawnSync(process.execPath, [CLI.pathname, ...args], {
      encoding: "utf8",
      input,
      env: { ...process.env, TASKMATIC_HOME: home },
    });
  for (const option of ["--help", "--version"]) assert.equal(run([option]).status, 0);
  assert.equal(existsSync(home), false);
  const created = run(["add", "CLI task", "--notes-file", "-", "--json"], "from stdin");
  assert.equal(created.status, 0, created.stderr);
  const card = JSON.parse(created.stdout);
  assert.equal(card.notes, "from stdin");
  assert.equal(run(["edit", card.id, "--assignee", "alice"]).status, 0);
  assert.equal(
    JSON.parse(run(["edit", card.id, "--clear-assignee", "--json"]).stdout).assignee,
    null,
  );
  const mcp = run(["mcp"], `${JSON.stringify({ id: 1, method: "tools/list" })}\n`);
  assert.equal(JSON.parse(mcp.stdout).result.tools.length, 11);
  assert.equal(run(["bogus"]).status, 2);
  assert.throws(() => rootPath("relative"));
  const target = join(root, "target");
  writeFileSync(target, "untouched");
  symlinkSync(target, join(home, "taskmatic.db-journal"));
  await assert.rejects(Store.open(home), /Symlink/);
});
