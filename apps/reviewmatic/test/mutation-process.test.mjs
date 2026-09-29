import assert from "node:assert/strict";
import test from "node:test";
import {
  MutationNotAttempted,
  MutationOutcomeUnknown,
  runMutationProcess,
} from "../dist/mutation-process.js";

test("successful mutation run captures stdout, stderr, and exit code", async () => {
  const result = await runMutationProcess(
    ["sh", "-c", "printf ok; printf err 1>&2"],
    Buffer.alloc(0),
  );
  assert.equal(result.code, 0);
  assert.equal(result.stdout.toString("utf8"), "ok");
  assert.equal(result.stderr.toString("utf8"), "err");
});

test("mutation stdin payload reaches the child", async () => {
  const result = await runMutationProcess(["cat"], Buffer.from("payload\n"));
  assert.equal(result.code, 0);
  assert.equal(result.stdout.toString("utf8"), "payload\n");
});

test("nonzero exit code is reported without raising", async () => {
  const result = await runMutationProcess(["sh", "-c", "exit 3"], Buffer.alloc(0));
  assert.equal(result.code, 3);
});

test("timeout raises mutation outcome unknown", async () => {
  await assert.rejects(
    runMutationProcess(["sh", "-c", "sleep 5"], Buffer.alloc(0), { timeoutMs: 200 }),
    (error) => {
      assert.ok(error instanceof MutationOutcomeUnknown);
      assert.equal(error.message, "GitLab mutation timed out; inspect the target");
      return true;
    },
  );
});

test("output limit raises mutation outcome unknown", async () => {
  await assert.rejects(
    runMutationProcess(
      ["sh", "-c", "dd if=/dev/zero bs=1024 count=64 status=none"],
      Buffer.alloc(0),
      {
        outputLimit: 1024,
        timeoutMs: 10_000,
      },
    ),
    (error) => {
      assert.ok(error instanceof MutationOutcomeUnknown);
      assert.equal(
        error.message,
        "GitLab mutation output exceeds the size limit; inspect the target",
      );
      return true;
    },
  );
});

test("missing binary raises mutation not attempted", async () => {
  await assert.rejects(
    runMutationProcess(["reviewmatic-nonexistent-binary-4f2a"], Buffer.alloc(0)),
    (error) => {
      assert.ok(error instanceof MutationNotAttempted);
      assert.equal(error.message, "GitLab mutation was not attempted; retry is safe");
      return true;
    },
  );
});
