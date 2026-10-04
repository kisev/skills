import assert from "node:assert/strict";
import { chmodSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { shellJoin, commandArgv, sendCommand } from "../dist/publication.js";
import { startReview, finishReview } from "../dist/draft.js";
import { loadPlan, planItems, sendItem } from "../dist/tui/support.js";
import { readJson, writeJson } from "../dist/contract.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

test("direct commands preserve arguments and never evaluate shell content", () => {
  const argv = [
    "glab",
    "api",
    "--hostname",
    "gitlab.example",
    "-f",
    "body=it's $(not a command); one\ntwo",
  ];
  assert.deepEqual(commandArgv(shellJoin(argv)), argv);
  assert.throws(() => commandArgv("reviewmatic publication apply --action old"), /historical/);
});

test("manual sends verify the MR head, make one write, can fail and repeat, and keep no publication state", async (t) => {
  const fixture = reviewFixture(t);
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  writeJson(result.draft_path, await completeDraft(readJson(result.draft_path), result));
  await finishReview(result.draft_path);
  const bundle = loadPlan(result.artifact_root);
  const item = planItems(bundle).find((item) => item.kind === "thread");
  item.actions = item.actions.filter((action) => action.operation === "reply");
  const requests = fixture.requestCount();
  writeJson(fixture.configPath, { ...fixture.config, mutationError: "connection reset" });
  const failed = await sendItem(bundle, item, null);
  assert.equal(failed.results[0].code, 1);
  assert.match(failed.results[0].error, /connection reset/);
  writeJson(fixture.configPath, fixture.config);
  assert.equal((await sendItem(bundle, item, null)).results[0].status, "sent");
  assert.equal((await sendItem(bundle, item, null)).results[0].status, "sent");
  assert.equal(readJson(fixture.configPath).publishedNotes.length, 2);
  // Each send performs its head check (one GET) plus exactly one write.
  assert.equal(fixture.requestCount() - requests, 6);
  assert.equal(existsSync(join(result.artifact_root, "code-review-publication")), false);
  assert.equal(existsSync(join(result.artifact_root, "artifacts", "publication_actions")), false);
  const book = readFileSync(join(result.artifact_root, "runbook.md"), "utf8");
  assert.match(book, /glab api/);
  assert.ok(!book.includes("reviewmatic publication"));
});

test("cancelling a slow request keeps the event loop responsive and does not block a subsequent send", async (t) => {
  const fixture = reviewFixture(t);
  const binary = join(fixture.tmp, "bin", "glab");
  writeFileSync(binary, "#!/usr/bin/env node\nsetTimeout(() => process.exit(0), 20000);\n");
  chmodSync(binary, 0o755);
  const controller = new AbortController();
  const pending = sendCommand("glab api example", controller.signal);
  let responsive = false;
  setTimeout(() => {
    responsive = true;
    controller.abort();
  }, 20);
  await assert.rejects(pending, /cancelled/);
  assert.equal(responsive, true);
  writeFileSync(binary, "#!/usr/bin/env node\nprocess.exit(0);\n");
  assert.equal((await sendCommand("glab api example")).code, 0);
});
