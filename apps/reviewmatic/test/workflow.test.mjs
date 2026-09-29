import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { WorkflowError } from "../dist/contract.js";
import { dispatch } from "../dist/workflow.js";

async function captureStdout(fn) {
  const chunks = [];
  const original = process.stdout.write.bind(process.stdout);
  process.stdout.write = (chunk) => {
    chunks.push(String(chunk));
    return true;
  };
  try {
    return [await fn(), chunks.join("")];
  } finally {
    process.stdout.write = original;
  }
}

test("workflow dispatch rejects out-of-order commands with exact stage errors", async (t) => {
  const home = mkdtempSync(join(tmpdir(), "reviewmatic-workflow-"));
  const previous = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = home;
  t.after(() => {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
    rmSync(home, { recursive: true, force: true });
  });
  const root = join(home, "agent-skills", "gitlab", "d".repeat(32));
  await assert.rejects(
    dispatch({ command: "finalize", artifactRoot: root }),
    (error) =>
      error instanceof WorkflowError &&
      error.message === "review command is out of order; current stage is prepared",
  );
  const [code, output] = await captureStdout(() =>
    dispatch({ command: "status", artifactRoot: root }),
  );
  assert.equal(code, 0);
  const payload = JSON.parse(output);
  assert.equal(payload.status, "incomplete");
  assert.equal(payload.stage, "stale");
  assert.equal(payload.resume_stage, "prepared");
  const [nextCode, nextOutput] = await captureStdout(() =>
    dispatch({ command: "next", artifactRoot: root }),
  );
  assert.equal(nextCode, 0);
  assert.equal(JSON.parse(nextOutput).stage, "stale");
});

test("workflow dispatch leaves contract-owned commands to the caller", async () => {
  assert.equal(await dispatch({ command: "prepare" }), null);
  assert.equal(await dispatch({ command: "prepare-local" }), null);
  assert.equal(await dispatch({ command: "finalize-local" }), null);
  assert.equal(await dispatch({ command: "assess-mode" }), null);
  assert.equal(await dispatch({ command: "publication" }), null);
  assert.equal(await dispatch({ command: "marker-run" }), null);
  assert.equal(await dispatch({ command: "unknown-command" }), null);
});
