// Material refresh is tested without fabricating a newly bound critic receipt.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { refreshReview } from "../../../../apps/reviewmatic/dist/draft.js";
import { readJson } from "../../../../apps/reviewmatic/dist/contract.js";
import { loadPlan } from "../../../../apps/reviewmatic/dist/tui/support.js";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const before = readJson(input.draft);
const prior = loadPlan(input.artifact_root);
const refreshed = await refreshReview(input.draft);
assert.equal(refreshed.status, "needs_reassessment", JSON.stringify(refreshed));
const next = readJson(refreshed.draft_path);
assert.deepEqual(next.findings, before.findings);
assert.deepEqual(next.dispositions, before.dispositions);
assert.deepEqual(next.critics, []);
assert.deepEqual(readJson(input.draft), before);
assert.equal(loadPlan(input.artifact_root).planDigest, prior.planDigest);
assert.notEqual(next.evidence_digest, before.evidence_digest);
assert.ok(refreshed.refresh_scope.changed_evidence_fields.includes("discussions"));
const output = {
  status: refreshed.status,
  refresh_scope: refreshed.refresh_scope,
  previous_draft_path: input.draft,
  refreshed_draft_path: refreshed.draft_path,
  retained_plan_digest: prior.planDigest,
  findings_retained: true,
  original_receipts_preserved: true,
  new_receipts: [],
  receipt_origin: "deterministic fixture, not a real critic run",
  external_mutations: false,
};
writeFileSync(input.output, JSON.stringify(output, null, 2));
console.log(JSON.stringify(output));
