// Exact-output fixture reassessment is not an agent/critic judgment.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { refreshReview } from "../../../../apps/reviewmatic/dist/draft.js";
import { readJson, artifactPayload, gitRead } from "../../../../apps/reviewmatic/dist/contract.js";
import { loadPlan } from "../../../../apps/reviewmatic/dist/tui/support.js";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const before = readJson(input.draft);
const plan = loadPlan(input.artifact_root);
const refreshed = await refreshReview(input.draft);
assert.equal(refreshed.status, "needs_reassessment", JSON.stringify(refreshed));
const next = readJson(refreshed.draft_path);
const [, evidence] = artifactPayload(next.evidence_path, "evidence_snapshot");
const [, context] = artifactPayload(next.context_path, "review_context");
assert.equal(evidence.head_sha, input.head);
assert.deepEqual(next.findings, before.findings);
assert.deepEqual(next.dispositions, before.dispositions);
assert.deepEqual(next.critics, []);
assert.deepEqual(readJson(input.draft), before);
assert.equal(loadPlan(input.artifact_root).planDigest, plan.planDigest);
const actual = String(
  gitRead(context.exact_git.repo_root, ["show", `${evidence.head_sha}:same.txt`]),
);
assert.equal(actual, input.expected);
const complete = actual === "before\nfixed first\nfixed second\nend\n";
assert.equal(complete, input.complete_fix);
assert.ok(refreshed.refresh_scope.changed_evidence_fields.length > 0);
console.log(
  JSON.stringify({
    status: refreshed.status,
    refreshed_draft_path: refreshed.draft_path,
    head: evidence.head_sha,
    exact_file: actual,
    complete_fix: complete,
    prior_plan_preserved: true,
    original_draft_preserved: true,
    new_receipts: [],
    refresh_scope: refreshed.refresh_scope,
    origin: "deterministic exact-output reassessment, not an agent or critic run",
  }),
);
