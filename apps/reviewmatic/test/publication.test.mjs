import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import {
  WorkflowError,
  canonical,
  privateDirectory,
  stateDirectory,
  writeBytes,
  writeJson,
} from "../dist/contract.js";
import {
  POSTCONDITION_DELAYS,
  SCHEMA,
  execute,
  interactiveRecovery,
  loadAction,
  makeCommand,
  notesSnapshot,
  observe,
  postcondition,
  publicationLock,
  validateGuard,
} from "../dist/publication.js";

const FAKE_GLAB = [
  "#!/usr/bin/env node",
  'const { appendFileSync, readFileSync, writeFileSync } = require("node:fs");',
  "const statePath = process.env.FAKE_GLAB_STATE;",
  "const callsPath = process.env.FAKE_GLAB_CALLS;",
  'if (!statePath) { process.stderr.write("FAKE_GLAB_STATE is not set\\n"); process.exit(1); }',
  "const argv = process.argv.slice(2);",
  'const apiIndex = argv.indexOf("api");',
  'if (apiIndex === -1) { process.stderr.write("expected glab api invocation\\n"); process.exit(1); }',
  "const rest = argv.slice(apiIndex + 1);",
  'let method = "GET";',
  'let endpoint = "";',
  "for (let i = 0; i < rest.length; i += 1) {",
  '  if (rest[i] === "--hostname" || rest[i] === "--header" || rest[i] === "--input") { i += 1; }',
  '  else if (rest[i] === "--method") { method = rest[i + 1]; endpoint = rest[i + 2]; i += 2; }',
  "}",
  'const cleanEndpoint = endpoint.split("?")[0];',
  'const stdinData = method === "GET" ? "" : readFileSync(0, "utf8");',
  'if (callsPath) { appendFileSync(callsPath, JSON.stringify({ method, endpoint: cleanEndpoint, stdin: stdinData }) + "\\n"); }',
  'const readState = () => JSON.parse(readFileSync(statePath, "utf8"));',
  "const writeState = (state) => writeFileSync(statePath, JSON.stringify(state));",
  'if (method === "GET") {',
  "  const state = readState();",
  '  if (cleanEndpoint === "user") { process.stdout.write(JSON.stringify(state.user)); process.exit(0); }',
  '  if (cleanEndpoint === "projects/10/merge_requests/2") { process.stdout.write(JSON.stringify(state.mr)); process.exit(0); }',
  '  if (cleanEndpoint === "projects/10/merge_requests/2/discussions") {',
  "    let notes = Object.entries(state.notes).map(([id, note]) => ({ id: Number(id), ...note }));",
  "    if (state.appearAfter !== undefined) {",
  "      state.gets = (state.gets ?? 0) + 1;",
  "      if (state.gets < state.appearAfter) { notes = notes.filter((note) => note.id !== state.extraNoteId); }",
  "      writeState(state);",
  "    }",
  "    const grouped = new Map();",
  "    for (const note of notes.sort((a, b) => a.id - b.id)) {",
  "      if (!grouped.has(note.discussion)) { grouped.set(note.discussion, []); }",
  "      grouped.get(note.discussion).push({ id: note.id, body: note.body, author: { id: note.author }, system: false, resolved: note.resolved, position: note.position ?? null });",
  "    }",
  "    const discussions = [...grouped.entries()].map(([id, notes]) => ({ id, individual_note: false, notes }));",
  "    process.stdout.write(JSON.stringify(discussions));",
  "    process.exit(0);",
  "  }",
  '  process.stderr.write("unexpected GET " + cleanEndpoint + "\\n");',
  "  process.exit(1);",
  "}",
  'const mode = process.env.FAKE_GLAB_MODE ?? "ok";',
  "const state = readState();",
  'const payload = JSON.parse(stdinData || "{}");',
  'if (mode === "fail") { process.stderr.write("HTTP 400 invalid body\\n"); process.exit(1); }',
  'if ("body" in payload) {',
  "  const ids = Object.keys(state.notes).map(Number);",
  "  const id = (ids.length === 0 ? 0 : Math.max(...ids)) + 1;",
  '  const discussion = cleanEndpoint.includes("/discussions/")',
  '    ? cleanEndpoint.split("/discussions/")[1].split("/")[0]',
  "    : `general-${id}`;",
  '  state.notes[String(id)] = { discussion, body: payload.body.replace(/\\n+$/, ""), author: state.user.id, resolved: null, position: payload.position ?? null };',
  '  if (mode !== "hide") { writeState(state); }',
  '} else if ("resolved" in payload) {',
  '  const discussion = cleanEndpoint.split("/discussions/")[1].split("/")[0];',
  "  for (const note of Object.values(state.notes)) {",
  "    if (note.discussion === discussion && note.resolved !== null) { note.resolved = payload.resolved; }",
  "  }",
  '  if (mode !== "hide") { writeState(state); }',
  '} else if ("labels" in payload) {',
  '  state.mr.labels = payload.labels.split(",").filter(Boolean);',
  '  if (mode !== "hide") { writeState(state); }',
  "}",
  'if (mode === "lost") { process.stderr.write("response lost\\n"); process.exit(1); }',
  'process.stdout.write("{}");',
  "",
].join("\n");

function initialState() {
  return {
    user: { id: 7, username: "reviewer" },
    mr: {
      id: 22,
      iid: 2,
      project_id: 10,
      state: "opened",
      diff_refs: {
        base_sha: "a".repeat(40),
        start_sha: "b".repeat(40),
        head_sha: "c".repeat(40),
      },
      author: { id: 8 },
      labels: [],
    },
    notes: {
      1: { discussion: "thread", body: "Please check", author: 8, resolved: false, position: null },
    },
  };
}

function workflowError(pattern) {
  return (error) => {
    assert.ok(error instanceof WorkflowError, `expected WorkflowError, got ${error}`);
    assert.match(error.message, pattern);
    return true;
  };
}

async function setup(t) {
  const tmp = mkdtempSync(join(tmpdir(), "publication-"));
  const previousStateHome = process.env.XDG_STATE_HOME;
  const previousPath = process.env.PATH;
  const previousMode = process.env.FAKE_GLAB_MODE;
  const previousGlabState = process.env.FAKE_GLAB_STATE;
  const previousGlabCalls = process.env.FAKE_GLAB_CALLS;
  process.env.XDG_STATE_HOME = join(tmp, "state");
  const bin = join(tmp, "bin");
  mkdirSync(bin, { recursive: true });
  const glabPath = join(bin, "glab");
  writeFileSync(glabPath, FAKE_GLAB);
  chmodSync(glabPath, 0o755);
  process.env.PATH = `${bin}:${previousPath}`;
  const statePath = join(tmp, "glab-state.json");
  const callsPath = join(tmp, "glab-calls.log");
  writeFileSync(statePath, JSON.stringify(initialState()));
  process.env.FAKE_GLAB_STATE = statePath;
  process.env.FAKE_GLAB_CALLS = callsPath;
  delete process.env.FAKE_GLAB_MODE;
  const originalDelays = [...POSTCONDITION_DELAYS];
  POSTCONDITION_DELAYS.splice(0, POSTCONDITION_DELAYS.length, 0, 0, 0);
  t.after(() => {
    POSTCONDITION_DELAYS.splice(0, POSTCONDITION_DELAYS.length, ...originalDelays);
    if (previousStateHome === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previousStateHome;
    process.env.PATH = previousPath;
    if (previousMode === undefined) delete process.env.FAKE_GLAB_MODE;
    else process.env.FAKE_GLAB_MODE = previousMode;
    if (previousGlabState === undefined) delete process.env.FAKE_GLAB_STATE;
    else process.env.FAKE_GLAB_STATE = previousGlabState;
    if (previousGlabCalls === undefined) delete process.env.FAKE_GLAB_CALLS;
    else process.env.FAKE_GLAB_CALLS = previousGlabCalls;
    rmSync(tmp, { recursive: true, force: true });
  });
  const target = { hostname: "gitlab.example", project_id: 10, kind: "merge_requests", iid: 2 };
  const root = await stateDirectory("code-review", target);
  const evidence = {
    project: { id: 10, hostname: "gitlab.example" },
    target: target,
    object: initialState().mr,
  };
  const context = {
    current_user_id: 7,
    current_user_username: "reviewer",
    evidence_digest: "d".repeat(64),
    discussions: [
      {
        id: "thread",
        notes: [{ id: 1, body: "Please check", author: { id: 8 }, resolved: false }],
      },
    ],
  };
  const readState = () => JSON.parse(readFileSync(statePath, "utf8"));
  const writeState = (state) => writeFileSync(statePath, JSON.stringify(state));
  const mutationCalls = () => {
    if (!existsSync(callsPath)) return [];
    return readFileSync(callsPath, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .filter((call) => call.method !== "GET");
  };
  return { tmp, root, evidence, context, readState, writeState, mutationCalls };
}

async function action(fixture, options = {}) {
  const { operation = "reply", proposed, dependencies = {} } = options;
  const base = "projects/10/merge_requests/2/discussions/thread";
  let value = {};
  let argv;
  let actionId;
  if (operation === "labels") {
    actionId = "labels:update";
    argv = ["glab", "mr", "update"];
    value = { proposed: proposed ?? ["type::bug"] };
  } else {
    actionId = `thread:one:r1:${operation}`;
    const directory = await privateDirectory(`${fixture.root}/artifacts/review_plan/bodies`);
    const body = join(directory, `${operation}.md`);
    writeFileSync(body, operation !== "note" ? "Verified result.\n" : "General summary.\n");
    if (operation === "reply") {
      argv = ["glab", "api", "--method", "POST", `${base}/notes`, "-F", `body=@${body}`];
    } else if (operation === "note") {
      argv = [
        "glab",
        "api",
        "--method",
        "POST",
        "projects/10/merge_requests/2/notes",
        "-F",
        `body=@${body}`,
      ];
    } else {
      argv = ["glab", "api", "--method", "PUT", base, "-F", "resolved=true"];
    }
  }
  const command = await makeCommand(
    fixture.root,
    fixture.evidence,
    fixture.context,
    actionId,
    argv,
    value,
    dependencies,
  );
  const tokens = command.split(/\s+/).filter(Boolean);
  const actionPath = tokens[tokens.indexOf("--action") + 1];
  return {
    actionPath,
    digest: tokens[tokens.length - 1],
    command: command,
    actionId: actionId,
    dependencies: dependencies,
  };
}

function finalizePlan(fixture, actions) {
  const assessmentItem = { status: "ok", rationale: "fine", recommendation: null };
  const plan = {
    profile: "code-review",
    external_mutations: false,
    evidence_digest: fixture.context.evidence_digest,
    context_digest: "e".repeat(64),
    decision_digest: "f".repeat(64),
    target: {
      hostname: "gitlab.example",
      project_id: 10,
      kind: "merge_requests",
      iid: 2,
    },
    role: "reviewer",
    mode: "normal",
    verdict: "not_ready",
    complete: true,
    summary: "summary",
    architecture_assessment: "architecture",
    semver_impact: "none",
    semver_rationale: "rationale",
    mr_metadata_assessment: {
      observed: { title: "Title", description: "", labels: [], workflow_state: "review" },
      assessment: {
        title: assessmentItem,
        description: assessmentItem,
        labels: assessmentItem,
        workflow_state: assessmentItem,
        overall: assessmentItem,
      },
    },
    publication_preview: {
      mr_state: "opened",
      warning: "No command was executed.",
      body_files: [],
      actions: actions.map((entry) => ({
        id: entry.actionId,
        kind: "thread",
        publication_id: null,
        operation: "reply",
        command: `reviewmatic publication apply --action ${entry.actionPath} --confirm ${entry.digest}`,
        path: null,
        line: null,
      })),
    },
    checks: [],
    findings: [],
    thread_decisions: [],
    markdown: "",
  };
  const envelope = {
    schema: "portable-gitlab/review_plan/v2",
    schema_version: 2,
    kind: "review_plan",
    created_at: new Date().toISOString(),
    payload: plan,
  };
  const content = canonical(envelope);
  const planDigest = createHash("sha256").update(content).digest("hex");
  const planPath = `${fixture.root}/artifacts/review_plan/${planDigest}.json`;
  mkdirSync(dirname(planPath), { recursive: true });
  writeBytes(planPath, content);
  writeJson(`${fixture.root}/review-current.json`, {
    stage: "plan_ready",
    plan_path: planPath,
    plan_digest: planDigest,
  });
  return planPath;
}

function validGuard(overrides = {}) {
  return {
    schema: SCHEMA,
    action_id: "thread:one:r1:reply",
    host: "gitlab.example",
    project_id: 10,
    mr_iid: 2,
    method: "POST",
    endpoint: "projects/10/merge_requests/2/discussions/thread/notes",
    payload: { body: "Verified result.\n" },
    body: { path: "/tmp/body.md", sha256: "a".repeat(64) },
    user: { id: 7, username: "reviewer" },
    mr: { id: 22, iid: 2 },
    labels: [],
    notes: {},
    dependency: null,
    evidence_digest: "d".repeat(64),
    expires_at: 4102444800,
    ...overrides,
  };
}

test("validate guard accepts the closed operation set and rejects everything else", () => {
  validateGuard(validGuard());
  validateGuard(
    validGuard({
      action_id: "labels:update",
      method: "PUT",
      endpoint: "projects/10/merge_requests/2",
      payload: { labels: "type::bug" },
      body: null,
    }),
  );
  validateGuard(
    validGuard({
      method: "PUT",
      endpoint: "projects/10/merge_requests/2/discussions/thread",
      payload: { resolved: true },
      body: null,
      dependency: "b".repeat(64),
    }),
  );
  validateGuard(
    validGuard({
      endpoint: "projects/10/issues",
      payload: { title: "Follow-up", description: "Details" },
      body: null,
    }),
  );
  validateGuard(
    validGuard({
      endpoint: "projects/10/merge_requests/2/discussions",
      payload: {
        body: "Line finding",
        position: {
          position_type: "text",
          base_sha: "a".repeat(40),
          start_sha: "b".repeat(40),
          head_sha: "c".repeat(40),
          new_path: "src/main.js",
          old_path: "src/main.js",
          new_line: 3,
        },
      },
      body: null,
    }),
  );
  assert.throws(
    () => validateGuard(validGuard({ schema: "code-review/publication/v0" })),
    workflowError(/legacy/),
  );
  assert.throws(() => validateGuard(validGuard({ host: "git lab" })), workflowError(/host/));
  assert.throws(() => validateGuard(validGuard({ project_id: true })), workflowError(/identity/));
  assert.throws(() => validateGuard(validGuard({ mr_iid: 0 })), workflowError(/identity/));
  assert.throws(() => validateGuard(validGuard({ endpoint: 5 })), workflowError(/request/));
  assert.throws(
    () => validateGuard(validGuard({ method: "DELETE" })),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () =>
      validateGuard(
        validGuard({
          method: "PUT",
          endpoint: "projects/10/merge_requests/2",
          payload: { labels: "type::bug", title: "x" },
        }),
      ),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () =>
      validateGuard(
        validGuard({
          method: "PUT",
          endpoint: "projects/10/merge_requests/2/discussions/thread",
          payload: { resolved: "true" },
          dependency: "b".repeat(64),
        }),
      ),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () =>
      validateGuard(
        validGuard({ endpoint: "projects/10/issues", payload: { title: "Follow-up" } }),
      ),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () =>
      validateGuard(
        validGuard({
          endpoint: "projects/10/merge_requests/2/discussions",
          payload: {
            body: "Line finding",
            position: {
              position_type: "text",
              base_sha: "a".repeat(40),
              start_sha: "b".repeat(40),
              head_sha: "c".repeat(40),
              new_path: "src/main.js",
              old_path: "src/main.js",
              new_line: 0,
            },
          },
        }),
      ),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () => validateGuard(validGuard({ notes: [] })),
    workflowError(/closed operation set/),
  );
  assert.throws(
    () => validateGuard(validGuard({ user: { id: "7", username: "reviewer" } })),
    workflowError(/identity is incomplete/),
  );
  assert.throws(
    () => validateGuard(validGuard({ expires_at: "4102444800" })),
    workflowError(/binding is incomplete/),
  );
});

test("make command renders a digest-confirmed apply command and records dependencies", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  assert.equal(
    reply.command,
    `reviewmatic publication apply --action ${reply.actionPath} --confirm ${reply.digest}`,
  );
  assert.equal(dependencies["thread:one:r1:reply"], reply.digest);
  const [, guard] = await loadAction(reply.actionPath, reply.digest);
  assert.equal(guard.endpoint, "projects/10/merge_requests/2/discussions/thread/notes");
  assert.equal(guard.method, "POST");
  assert.equal(guard.payload.body, "Verified result.\n");
  assert.equal(guard.body.path, `${fixture.root}/artifacts/review_plan/bodies/reply.md`);
  const labels = await action(fixture, { operation: "labels" });
  const [, labelsGuard] = await loadAction(labels.actionPath, labels.digest);
  assert.equal(labelsGuard.method, "PUT");
  assert.equal(labelsGuard.endpoint, "projects/10/merge_requests/2");
  assert.deepEqual(labelsGuard.payload, { labels: "type::bug" });
  await assert.rejects(
    action(fixture, { operation: "resolve", dependencies: {} }),
    workflowError(/explanation/),
  );
});

test("load action rejects invalid digests and tampered files", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  await assert.rejects(
    loadAction(reply.actionPath, "0".repeat(64)),
    workflowError(/path or digest is invalid/),
  );
  const original = readFileSync(reply.actionPath, "utf8");
  writeFileSync(reply.actionPath, `${original} `);
  await assert.rejects(loadAction(reply.actionPath, reply.digest), workflowError(/digest changed/));
  writeFileSync(reply.actionPath, original);
  writeFileSync(`${fixture.root}/artifacts/review_plan/bodies/reply.md`, "changed");
  await assert.rejects(loadAction(reply.actionPath, reply.digest), workflowError(/body changed/));
});

test("digest body expiry and unfinalized plan fail before mutation", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  await assert.rejects(execute(reply.actionPath, "0".repeat(64)), workflowError(/invalid/));
  await assert.rejects(execute(reply.actionPath, reply.digest), workflowError(/progress/));
  finalizePlan(fixture, [reply]);
  const [, guard] = await loadAction(reply.actionPath, reply.digest);
  const expired = { ...guard, expires_at: 1000 };
  const content = canonical(expired);
  const expiredDigest = createHash("sha256").update(content).digest("hex");
  const expiredPath = `${fixture.root}/artifacts/publication_actions/${expiredDigest}.json`;
  writeBytes(expiredPath, content);
  finalizePlan(fixture, [
    { actionId: reply.actionId, actionPath: expiredPath, digest: expiredDigest },
  ]);
  await assert.rejects(execute(expiredPath, expiredDigest), workflowError(/expired/));
  writeFileSync(`${fixture.root}/artifacts/review_plan/bodies/reply.md`, "changed");
  await assert.rejects(execute(reply.actionPath, reply.digest), workflowError(/body changed/));
  assert.equal(fixture.mutationCalls().length, 0);
});

test("reply then close requires receipt and rejects replay", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  const close = await action(fixture, { operation: "resolve", dependencies });
  finalizePlan(fixture, [reply, close]);
  await assert.rejects(execute(close.actionPath, close.digest), workflowError(/explanation/));
  assert.equal(fixture.mutationCalls().length, 0);
  assert.equal((await execute(reply.actionPath, reply.digest)).status, "applied");
  assert.equal((await execute(close.actionPath, close.digest)).status, "applied");
  const state = fixture.readState();
  state.notes["1"].resolved = false;
  fixture.writeState(state);
  assert.equal((await execute(close.actionPath, close.digest)).status, "already_applied");
  assert.equal(fixture.mutationCalls().length, 2);
});

test("later reply blocks closure", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  const close = await action(fixture, { operation: "resolve", dependencies });
  finalizePlan(fixture, [reply, close]);
  await execute(reply.actionPath, reply.digest);
  const state = fixture.readState();
  state.notes["3"] = { ...state.notes["2"], author: 8, body: "Not fixed" };
  fixture.writeState(state);
  await assert.rejects(execute(close.actionPath, close.digest), workflowError(/changed/));
  assert.equal(fixture.mutationCalls().length, 1);
});

test("label drift does not block note actions", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  const note = await action(fixture, { operation: "note" });
  finalizePlan(fixture, [reply, note]);
  const state = fixture.readState();
  state.mr.labels = ["semver::patch", "type::bug"];
  fixture.writeState(state);
  assert.equal((await execute(reply.actionPath, reply.digest)).status, "applied");
  assert.equal((await execute(note.actionPath, note.digest)).status, "applied");
  assert.equal(fixture.mutationCalls().length, 2);
});

test("manually applied labels complete without write", async (t) => {
  const fixture = await setup(t);
  const labels = await action(fixture, { operation: "labels" });
  finalizePlan(fixture, [labels]);
  const state = fixture.readState();
  state.mr.labels = ["type::bug"];
  fixture.writeState(state);
  const result = await execute(labels.actionPath, labels.digest);
  assert.equal(result.status, "already_applied");
  assert.equal(result.mutation_outcome, "applied");
  assert.equal(result.external_mutations, false);
  assert.equal((await execute(labels.actionPath, labels.digest)).status, "already_applied");
  assert.equal(fixture.mutationCalls().length, 0);
});

test("foreign label change blocks label update", async (t) => {
  const fixture = await setup(t);
  const labels = await action(fixture, { operation: "labels" });
  finalizePlan(fixture, [labels]);
  const state = fixture.readState();
  state.mr.labels = ["semver::patch"];
  fixture.writeState(state);
  await assert.rejects(
    execute(labels.actionPath, labels.digest),
    workflowError(/labels changed outside the plan/),
  );
  assert.equal(fixture.mutationCalls().length, 0);
});

test("manually posted reply completes and unblocks state change", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  const close = await action(fixture, { operation: "resolve", dependencies });
  finalizePlan(fixture, [reply, close]);
  const state = fixture.readState();
  state.notes["9"] = {
    discussion: "thread",
    body: "Verified result.\n",
    author: 7,
    resolved: null,
    position: null,
  };
  fixture.writeState(state);
  const result = await execute(reply.actionPath, reply.digest);
  assert.equal(result.status, "already_applied");
  assert.equal(result.external_mutations, false);
  assert.equal((await execute(close.actionPath, close.digest)).status, "applied");
  assert.equal(fixture.mutationCalls().length, 1);
});

test("manually resolved thread completes without write", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  const close = await action(fixture, { operation: "resolve", dependencies });
  finalizePlan(fixture, [reply, close]);
  await execute(reply.actionPath, reply.digest);
  const state = fixture.readState();
  state.notes["1"].resolved = true;
  fixture.writeState(state);
  const result = await execute(close.actionPath, close.digest);
  assert.equal(result.status, "already_applied");
  assert.equal(result.external_mutations, false);
  assert.equal(fixture.mutationCalls().length, 1);
});

test("postcondition matches gitlab normalized body", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  const [, guard] = await loadAction(reply.actionPath, reply.digest);
  const snapshot = notesSnapshot(fixture.context.discussions);
  const note = {
    discussion: "thread",
    body: guard.payload.body.replace(/\n+$/, ""),
    author: guard.user.id,
    resolved: null,
    position: null,
  };
  const observed = { mr: fixture.evidence.object, notes: { ...snapshot, 5: note } };
  const effect = postcondition(guard, observed, { notes: snapshot });
  assert.deepEqual(effect, { note_id: "5", note: note });
});

test("pending unknown suspends only its own action", async (t) => {
  const fixture = await setup(t);
  const dependencies = {};
  const reply = await action(fixture, { dependencies });
  const close = await action(fixture, { operation: "resolve", dependencies });
  const labels = await action(fixture, { operation: "labels" });
  finalizePlan(fixture, [reply, close, labels]);
  process.env.FAKE_GLAB_MODE = "hide";
  const blocked = await execute(reply.actionPath, reply.digest);
  assert.equal(blocked.status, "blocked");
  assert.equal(blocked.mutation_outcome, "unknown");
  delete process.env.FAKE_GLAB_MODE;
  assert.equal((await execute(labels.actionPath, labels.digest)).status, "applied");
  await assert.rejects(execute(close.actionPath, close.digest), workflowError(/explanation/));
  const replay = await execute(reply.actionPath, reply.digest);
  assert.equal(replay.status, "blocked");
  assert.match(replay.inspect_command, /inspect --action/);
  assert.equal(fixture.mutationCalls().length, 2);
});

test("legacy pending ledger is migrated", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  finalizePlan(fixture, [reply]);
  process.env.FAKE_GLAB_MODE = "hide";
  await execute(reply.actionPath, reply.digest);
  delete process.env.FAKE_GLAB_MODE;
  const state = fixture.readState();
  state.notes["2"] = {
    discussion: "thread",
    body: "Verified result.",
    author: 7,
    resolved: null,
    position: null,
  };
  fixture.writeState(state);
  const ledgerPath = `${fixture.root}/code-review-publication/ledger.json`;
  const ledger = JSON.parse(readFileSync(ledgerPath, "utf8"));
  writeFileSync(
    ledgerPath,
    JSON.stringify({ receipts: ledger.receipts, pending: ledger.pendings[0] }),
  );
  const inspected = await execute(reply.actionPath, reply.digest, { inspect: true });
  assert.equal(inspected.status, "applied");
  assert.equal(fixture.mutationCalls().length, 1);
});

test("ambiguous attempt blocks replay and read only inspection can confirm", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  finalizePlan(fixture, [reply]);
  process.env.FAKE_GLAB_MODE = "hide";
  const result = await execute(reply.actionPath, reply.digest);
  assert.equal(result.mutation_outcome, "unknown");
  assert.equal(result.external_mutations, true);
  const blocked = await execute(reply.actionPath, reply.digest);
  assert.equal(blocked.status, "blocked");
  assert.match(blocked.inspect_command, /inspect --action/);
  delete process.env.FAKE_GLAB_MODE;
  const state = fixture.readState();
  state.notes["2"] = {
    discussion: "thread",
    body: "Verified result.",
    author: 7,
    resolved: null,
    position: null,
  };
  fixture.writeState(state);
  const inspected = await execute(reply.actionPath, reply.digest, { inspect: true });
  assert.equal(inspected.status, "applied");
  assert.equal(inspected.external_mutations, false);
  assert.equal(fixture.mutationCalls().length, 1);
});

test("nonzero process with proven effect is successful", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  finalizePlan(fixture, [reply]);
  process.env.FAKE_GLAB_MODE = "lost";
  const result = await execute(reply.actionPath, reply.digest);
  assert.equal(result.status, "applied");
  assert.equal(result.external_mutations, true);
  assert.equal(fixture.mutationCalls().length, 1);
});

test("failed process preserves diagnostic and explicit retry", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  finalizePlan(fixture, [reply]);
  process.env.FAKE_GLAB_MODE = "fail";
  const result = await execute(reply.actionPath, reply.digest);
  assert.equal(result.status, "blocked");
  assert.match(result.error, /HTTP 400 invalid body/);
  assert.match(result.inspect_command, /inspect --action/);
  assert.match(result.retry_command, /retry --action/);
  assert.match(result.retry_warning, /duplicate/);
  delete process.env.FAKE_GLAB_MODE;
  const retried = await execute(reply.actionPath, reply.digest, { retry: true });
  assert.equal(retried.status, "applied");
  assert.equal(fixture.mutationCalls().length, 2);
});

test("postcondition polling accepts delayed effect", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  finalizePlan(fixture, [reply]);
  const state = fixture.readState();
  state.gets = 0;
  state.appearAfter = 4;
  state.extraNoteId = 2;
  fixture.writeState(state);
  const result = await execute(reply.actionPath, reply.digest);
  assert.equal(result.status, "applied");
  assert.equal(fixture.mutationCalls().length, 1);
  assert.equal(fixture.readState().gets, 4);
});

test("observe rejects changed identity and head", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  const [, guard] = await loadAction(reply.actionPath, reply.digest);
  const state = fixture.readState();
  state.user = { id: 9, username: "another" };
  fixture.writeState(state);
  assert.throws(() => observe(guard), workflowError(/user changed/));
  const restored = fixture.readState();
  restored.user = { id: 7, username: "reviewer" };
  restored.mr = {
    ...restored.mr,
    diff_refs: {
      base_sha: "a".repeat(40),
      start_sha: "b".repeat(40),
      head_sha: "f".repeat(40),
    },
  };
  fixture.writeState(restored);
  assert.throws(() => observe(guard), workflowError(/refs/));
});

test("publication lock excludes concurrent runners", async (t) => {
  const fixture = await setup(t);
  const lock = await publicationLock(fixture.root);
  await assert.rejects(
    publicationLock(fixture.root),
    workflowError(/another publication is running/),
  );
  lock.release();
  const second = await publicationLock(fixture.root);
  second.release();
});

test("execute rejects combining inspect and retry", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  await assert.rejects(
    execute(reply.actionPath, reply.digest, { inspect: true, retry: true }),
    workflowError(/mode is invalid/),
  );
});

test("interactive recovery returns blocked results without a terminal", async (t) => {
  const fixture = await setup(t);
  const reply = await action(fixture);
  const blocked = {
    status: "blocked",
    mutation_outcome: "unknown",
    external_mutations: true,
    error: "publication postcondition is unverified",
    inspect_command: `reviewmatic publication inspect --action ${reply.actionPath} --confirm ${reply.digest}`,
  };
  const recovered = await interactiveRecovery(reply.actionPath, reply.digest, blocked);
  assert.equal(recovered, blocked);
});
