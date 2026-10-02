// Deterministic review decisions are fixture inputs, not observed agent/critic behavior.
import { readFileSync, writeFileSync } from "node:fs";
import {
  startReview,
  checkReview,
  finishReview,
  repairReview,
} from "../../../../apps/reviewmatic/dist/draft.js";
import {
  artifactPayload,
  readJson,
  writeJson,
} from "../../../../apps/reviewmatic/dist/contract.js";
import { completeDraft } from "../../../../apps/reviewmatic/test/helpers/review-fixture.mjs";
import { loadPlan } from "../../../../apps/reviewmatic/dist/tui/support.js";
import assert from "node:assert/strict";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const result =
  input.started ?? (await startReview({ url: input.url, repoRoot: input.repo, locale: "en" }));
if (result.status !== "ok") throw new Error(JSON.stringify(result));
if (input.require_pagination) {
  const [, evidence] = artifactPayload(result.evidence_path, "evidence_snapshot");
  assert.ok(evidence.labels.pages >= 2, "Reviewmatic must collect the second real catalog page");
  const names = new Set(evidence.labels.items.map((label) => label.name));
  for (let index = 0; index < 101; index += 1)
    assert.ok(names.has(`matrix-page-${String(index).padStart(3, "0")}`));
}
const draft = input.started
  ? readJson(result.draft_path)
  : completeDraft(readJson(result.draft_path), result);
draft.run_id = input.run;
draft.session_id = "deterministic-harness-" + input.run;
draft.critics[0].run_id = "deterministic-fixture-critic";
draft.critics[0].session_id = "deterministic-fixture-session";
draft.content.summary =
  "Synthetic placement and publication probes against the exact fixture head.";
draft.content.architecture_assessment =
  "The fixture contains only text fixtures and synthetic CI jobs.";
draft.content.checks = ["Deterministic harness input; no agent or critic invocation is claimed."];
draft.content.semver_assessment.sources = [
  "Exact synthetic repository and collected non-versioned harness tags/releases.",
];
draft.content.chat_assessment = {
  necessity: { status: "supported", rationale: "Exercise real-server publication transport." },
  relevance: { status: "current", rationale: "These are the current synthetic fixture positions." },
  change: "Change synthetic text outputs and exercise shell-CI evidence.",
};
draft.findings = [
  {
    id: "harness-grouped",
    severity: "low",
    summary: "Exercise grouped synthetic outputs",
    risk: "The two fixture outputs differ from the test's expected replacements.",
    evidence: [
      "grouped.txt and grouped-extra.txt line 2 contain new first and new second at the exact fixture head.",
    ],
    consequence: "The exact-output assertion would fail until both parts are applied.",
    relation_to_change: "The added line belongs to the synthetic diff.",
    minimum_fix: "Replace both independently applicable outputs.",
  },
];
draft.dispositions = [
  {
    id: "harness-grouped",
    decision: "accept",
    reason: "Synthetic expected-output contract, not a product defect.",
    dependencies: {
      paths: ["grouped.txt", "grouped-extra.txt"],
      thread_ids: [],
      metadata_fields: [],
      ci: false,
    },
  },
];
draft.content.finding_publications = [
  {
    finding_id: "harness-grouped",
    type: "general",
    path: null,
    line: null,
    old_line: null,
    body: "Both independent synthetic replacements are required for the complete expected output.",
    fix_mode: "suggestion",
    patch: null,
    suggestions: [
      {
        path: "grouped.txt",
        line: 2,
        body: "Harness grouped first\n\n```suggestion\nfixed first\n```",
      },
      {
        path: "grouped-extra.txt",
        line: 2,
        body: "Harness grouped second\n\n```suggestion\nfixed second\n```",
      },
    ],
    split_rationale:
      "Each line can be replaced independently; one application is not a complete fix.",
  },
];
for (const thread of draft.content.thread_decisions) {
  thread.assessment = "neutral";
  thread.rationale = "Synthetic placement probe, not a claimed code defect.";
  thread.outcome = thread.state === "open" ? "reply" : "no_publication";
  thread.proposed_response =
    thread.state === "open" ? "Harness reviewmatic reply; correction is still pending." : null;
}
for (const job of draft.ci_job_assessments) {
  job.classification = "process_gate";
  job.rationale =
    "The fixture explicitly executes exit 1 with allow_failure to exercise real failing traces.";
  job.trace_evidence = "HARNESS_FAILURE";
}
writeJson(result.draft_path, draft);
const checked = await checkReview(result.draft_path);
if (checked.status !== "ok") throw new Error(JSON.stringify(checked));
if (input.phase === "draft") {
  const output = { started: result, receipts: draft.critics, external_mutations: false };
  writeFileSync(input.output, JSON.stringify(output, null, 2));
  console.log(JSON.stringify(output));
  process.exit(0);
}
let ciRefresh = null;
if (input.phase === "ci-finish") {
  const before = readJson(result.draft_path);
  const refresh = await finishReview(result.draft_path);
  assert.equal(refresh.status, "refresh_required", JSON.stringify(refresh));
  const updated = readJson(result.draft_path);
  assert.deepEqual(updated.findings, before.findings);
  assert.deepEqual(updated.dispositions, before.dispositions);
  assert.deepEqual(updated.critics, before.critics);
  assert.equal(updated.evidence_digest, before.evidence_digest);
  assert.ok(updated.ci_snapshot);
  for (const job of updated.ci_job_assessments) {
    job.classification = "process_gate";
    job.rationale =
      "The new exact-head fixture pipeline deliberately executes exit 1 with allow_failure.";
    job.trace_evidence = "HARNESS_FAILURE";
  }
  updated.content.checks.push(
    "Refreshed exact-head CI evidence; code and fixture critic receipts were retained without restarting review.",
  );
  writeJson(result.draft_path, updated);
  ciRefresh = {
    status: refresh.status,
    original_evidence_digest: before.evidence_digest,
    ci_snapshot: updated.ci_snapshot,
    findings_retained: true,
    receipts_retained: true,
    repeated_start_review: false,
  };
}
const finished = await finishReview(result.draft_path);
if (finished.status !== "ok") throw new Error(JSON.stringify(finished));
const receipts = readJson(result.draft_path).critics;
const prior = loadPlan(result.artifact_root);
const repair = await repairReview(result.artifact_root, "presentation");
const repairedDraft = readJson(repair.draft_path);
repairedDraft.repair.rationale =
  "Retain findings, positions and fixture receipts; clarify the harness check text.";
repairedDraft.repair.checks = ["Compared source findings, suggested outputs and fixture receipts."];
repairedDraft.content.checks.push(
  "Presentation-only repair exercised without changing the synthetic outputs.",
);
writeJson(repair.draft_path, repairedDraft);
const repaired = await finishReview(repair.draft_path);
assert.equal(repaired.status, "ok", JSON.stringify(repaired));
const plan = loadPlan(result.artifact_root);
assert.deepEqual(plan.plan.findings, prior.plan.findings);
assert.deepEqual(plan.plan.review_source.critics, prior.plan.review_source.critics);
assert.deepEqual(plan.plan.finding_publications, prior.plan.finding_publications);
const output = {
  started: result,
  finished: repaired,
  receipts,
  repair: { prior_digest: prior.planDigest, digest: plan.planDigest },
  ci_refresh: ciRefresh,
  actions: plan.plan.publication_preview.actions,
};
writeFileSync(input.output, JSON.stringify(output, null, 2));
console.log(JSON.stringify(output));
