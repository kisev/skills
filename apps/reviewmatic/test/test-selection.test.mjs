import assert from "node:assert/strict";
import { readdirSync } from "node:fs";
import test from "node:test";
import { backendTests, experimentalTests } from "../scripts/test-selection.mjs";

test("default gate excludes only the three experimental interface suites", () => {
  assert.deepEqual([...experimentalTests].sort(), [
    "tui-app.test.mjs",
    "tui-pty.test.mjs",
    "tui-support.test.mjs",
  ]);
  const names = readdirSync(new URL("./", import.meta.url), { recursive: true });
  for (const name of experimentalTests) assert.ok(names.includes(name), name);
  assert.deepEqual(
    backendTests(names),
    names.filter((name) => name.endsWith(".test.mjs") && !experimentalTests.has(name)).sort(),
  );
  for (const name of [
    "publication.test.mjs",
    "draft.test.mjs",
    "repair.test.mjs",
    "worktree.test.mjs",
  ])
    assert.ok(backendTests(names).includes(name), name);
  assert.ok(
    backendTests(["new-backend.test.mjs", "tui-backend.test.mjs"]).includes("tui-backend.test.mjs"),
  );
  assert.deepEqual(backendTests(["nested/new-backend.test.mjs", "tui-app.test.mjs"]), [
    "nested/new-backend.test.mjs",
  ]);
});
