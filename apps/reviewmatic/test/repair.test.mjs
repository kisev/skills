import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join } from "node:path";
import test from "node:test";
import {
  startReview,
  finishReview,
  checkReview,
  repairReview,
  refreshReview,
  schemaIssues,
} from "../dist/draft.js";
import { artifactPayload, artifactSchema, readJson, writeJson } from "../dist/contract.js";
import { reportReview } from "../dist/context.js";
import { codeFence, validateGitPatch } from "../dist/context.js";
import { suggestionsPatch } from "../dist/fixes.js";
import { loadPlan, planItems } from "../dist/tui/support.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

function finding(draft, grouped = false) {
  draft.findings = [
    {
      id: "fix-1",
      severity: "low",
      summary: "Preserve the agreed output",
      risk: "The output is wrong.",
      evidence: ["The exact file has the changed output."],
      consequence: "Consumers read wrong output.",
      relation_to_change: "Introduced here.",
      minimum_fix: "Correct the output.",
    },
  ];
  draft.dispositions = [
    {
      id: "fix-1",
      decision: "accept",
      reason: "Confirmed.",
      dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
    },
  ];
  draft.content.finding_publications = [
    {
      finding_id: "fix-1",
      type: grouped ? "general" : "line",
      path: grouped ? null : "review.txt",
      line: grouped ? null : 2,
      old_line: null,
      body: grouped
        ? "Correct the two independent outputs."
        : "Correct the output.\n\n```suggestion\ncorrect output\n```",
      fix_mode: "suggestion",
      patch: null,
      ...(grouped
        ? {
            suggestions: [
              { path: "review.txt", line: 1, body: "```suggestion\ncorrect base\n```" },
              { path: "review.txt", line: 2, body: "```suggestion\ncorrect output\n```" },
            ],
            split_rationale:
              "Either independent output can be corrected without changing the other.",
          }
        : {}),
    },
  ];
  return draft;
}

async function ready(t, grouped = false) {
  const fixture = reviewFixture(t, { resolved: true });
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  writeJson(
    result.draft_path,
    finding(completeDraft(readJson(result.draft_path), result), grouped),
  );
  const finished = await finishReview(result.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  return { fixture, result, finished };
}

test("SemVer diagnostic identifies invalid object keys rather than suggesting null fallback", () => {
  const schema = artifactSchema();
  const issues = schemaIssues(schema.$defs.semver_assessment, {
    mode: "release",
    policy: "Tags",
    sources: ["catalog"],
    baseline: { name: "v1.0.0", commit: "a".repeat(40), source: "tags" },
    target_branch: "main",
    target_sha: "b".repeat(40),
    target_revision: "current",
    fallback_reason: null,
    release_impact: "patch",
    release_rationale: "Existing fix.",
  });
  assert.ok(issues.some((item) => item.path.endsWith("baseline.sha")));
  assert.ok(issues.some((item) => item.path.endsWith("baseline.commit")));
  assert.ok(
    !issues.some((item) => item.path.endsWith("baseline") && item.message.includes('"null"')),
  );
});

test("Markdown patch fences cannot be closed by nested documentation fences", () => {
  const value = "git apply <<'PATCH'\n context\n ```\n+```yaml\n+x: true\n+```\nPATCH";
  const rendered = codeFence(value, "sh");
  assert.ok(rendered.startsWith("````sh\n"));
  assert.ok(rendered.endsWith("\n````"));
  assert.equal(rendered.slice("````sh\n".length, -"\n````".length), value);
});

test("bounded suggestions preserve files without a final newline", (t) => {
  const fixture = reviewFixture(t);
  writeFileSync(join(fixture.repo, "review.txt"), "base\nreviewed change");
  fixture.git("commit", "-qam", "remove final newline");
  const head = fixture.git("rev-parse", "HEAD");
  const patch = suggestionsPatch(fixture.repo, head, [
    { path: "review.txt", line: 2, body: "```suggestion:-1+0\ncorrect base\ncorrect output\n```" },
  ]);
  const result = {};
  validateGitPatch(fixture.repo, head, patch, result);
  assert.equal(
    execFileSync("git", ["-C", fixture.repo, "show", `${result.tree}:review.txt`], {
      encoding: "utf8",
    }),
    "correct base\ncorrect output",
  );
});

test("related suggestions keep one finding, separate anchored actions, and reject overlapping parts", async (t) => {
  const { result, finished } = await ready(t, true);
  const [, plan] = artifactPayload(finished.artifact_path, "review_plan");
  assert.equal(plan.findings.length, 1);
  const actions = plan.publication_preview.actions.filter((item) => item.kind === "finding");
  assert.equal(actions.length, 2);
  assert.ok(actions.every((item) => item.command.startsWith("glab api")));
  assert.equal(
    planItems(loadPlan(result.artifact_root)).filter((item) => item.key.includes("@suggestion-"))
      .length,
    2,
  );
  const repair = await repairReview(result.artifact_root, "fix");
  const draft = readJson(repair.draft_path);
  draft.repair.rationale = "Check the replacement only.";
  draft.repair.checks = ["Reviewed consumers of both independent outputs."];
  draft.content.finding_publications[0].suggestions[1].line = 1;
  writeJson(repair.draft_path, draft);
  assert.match(JSON.stringify((await checkReview(repair.draft_path)).errors), /overlap/);
});

test("presentation repair preserves the critic and equates patch and suggestion without a new review", async (t) => {
  const { fixture, result, finished } = await ready(t);
  const before = loadPlan(result.artifact_root);
  const repair = await repairReview(result.artifact_root, "presentation");
  const draft = readJson(repair.draft_path);
  draft.repair.rationale =
    "Same assertions and same resulting file; only the fix representation changes.";
  draft.repair.checks = ["Compared old and new prose and all resulting files/modes."];
  Object.assign(draft.content.finding_publications[0], {
    fix_mode: "patch",
    body: "Correct the output.",
    patch_reason: "Representation equivalence regression fixture.",
    patch:
      "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n@@ -1,2 +1,2 @@\n base\n-reviewed change\n+correct output\n",
  });
  writeJson(repair.draft_path, draft);
  const reads = fixture.requestCount();
  assert.equal((await checkReview(repair.draft_path)).status, "ok");
  assert.equal(fixture.requestCount(), reads);
  const repaired = await finishReview(repair.draft_path);
  assert.equal(repaired.status, "ok", JSON.stringify(repaired));
  const after = loadPlan(result.artifact_root);
  assert.notEqual(after.planDigest, before.planDigest);
  assert.deepEqual(after.plan.review_source.critics, before.plan.review_source.critics);
  assert.equal(readFileSync(finished.artifact_path).length > 0, true);
  assert.equal((await reportReview(result.artifact_root)).status, "ok");
  assert.equal(
    (readFileSync(repaired.markdown_path, "utf8").match(/git apply <<'PATCH_/g) ?? []).length,
    1,
  );
});

test("changed fix needs targeted checks but not a new critic; changed decisions do", async (t) => {
  const { result } = await ready(t);
  const presentation = await repairReview(result.artifact_root, "presentation");
  const wrong = readJson(presentation.draft_path);
  wrong.repair.rationale = "New code.";
  wrong.repair.checks = ["Checked output."];
  wrong.content.finding_publications[0].body = "```suggestion\nnew output\n```";
  writeJson(presentation.draft_path, wrong);
  assert.match(
    JSON.stringify((await checkReview(presentation.draft_path)).errors),
    /results differ/,
  );
  const fix = await repairReview(result.artifact_root, "fix");
  const draft = readJson(fix.draft_path);
  draft.repair.rationale = "Same confirmed problem, a different complete correction.";
  draft.repair.checks = ["Inspected the affected consumer and verified the new output."];
  draft.content.finding_publications[0].body = "```suggestion\nnew output\n```";
  writeJson(fix.draft_path, draft);
  assert.equal((await finishReview(fix.draft_path)).status, "ok");
  const decision = await repairReview(result.artifact_root, "decision");
  const changed = readJson(decision.draft_path);
  changed.repair.rationale = "Reassessed the release consequence.";
  changed.repair.checks = ["Reviewed affected decision."];
  changed.owner_decision_reasons = ["Owner must choose the supported behavior."];
  writeJson(decision.draft_path, changed);
  assert.match(JSON.stringify((await checkReview(decision.draft_path)).errors), /new independent/);
  changed.critics.push({
    ...changed.critics[0],
    run_id: "targeted-review-run",
    session_id: "targeted-review-session",
    findings: [],
  });
  changed.critic_count += 1;
  writeJson(decision.draft_path, changed);
  assert.equal((await finishReview(decision.draft_path)).status, "ok");
});

test("CI-only refresh retains original critique and finishes after a targeted CI assessment", async (t) => {
  const fixture = reviewFixture(t, { resolved: true, pipelineStatus: "running" });
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const draft = completeDraft(readJson(result.draft_path), result);
  writeJson(result.draft_path, draft);
  writeJson(fixture.configPath, { ...fixture.config, pipelineStatus: "success" });
  assert.equal((await finishReview(result.draft_path)).status, "refresh_required");
  const refreshed = readJson(result.draft_path);
  assert.deepEqual(refreshed.critics, draft.critics);
  assert.equal(refreshed.evidence_digest, draft.evidence_digest);
  refreshed.content.checks = ["CI in the refreshed immutable snapshot is successful."];
  writeJson(result.draft_path, refreshed);
  const final = await finishReview(result.draft_path);
  assert.equal(final.status, "ok", JSON.stringify(final));
  assert.match(readFileSync(final.markdown_path, "utf8"), /CI in the assessed snapshot: success/);
  assert.equal((await reportReview(result.artifact_root)).status, "ok");
});

test("material refresh preserves findings and decisions without rebinding critic receipts", async (t) => {
  const fixture = reviewFixture(t);
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const draft = finding(completeDraft(readJson(result.draft_path), result));
  writeJson(result.draft_path, draft);
  writeJson(fixture.configPath, {
    ...fixture.config,
    noteBody: "New context about the same problem",
  });
  const next = await refreshReview(result.draft_path);
  assert.equal(next.status, "needs_reassessment");
  const retained = readJson(next.draft_path);
  assert.deepEqual(retained.findings, draft.findings);
  assert.deepEqual(retained.dispositions, draft.dispositions);
  assert.deepEqual(retained.critics, []);
  assert.deepEqual(readJson(result.draft_path).critics, draft.critics);
});

test("an unfinished refreshed review does not hide the last finalized manual plan", async (t) => {
  const { fixture, result, finished } = await ready(t);
  const old = loadPlan(result.artifact_root);
  writeJson(fixture.configPath, { ...fixture.config, noteBody: "New conversation evidence" });
  const refreshed = await refreshReview(result.draft_path);
  assert.equal(refreshed.status, "needs_reassessment");
  const requests = fixture.requestCount();
  assert.equal(loadPlan(result.artifact_root).planDigest, old.planDigest);
  assert.equal(fixture.requestCount(), requests);
  assert.equal(readFileSync(finished.markdown_path, "utf8").length > 0, true);
});

test("incomplete repair preserves the current plan and historical plans cannot be repaired", async (t) => {
  const { result } = await ready(t);
  const original = loadPlan(result.artifact_root);
  const repair = await repairReview(result.artifact_root, "fix");
  assert.equal((await finishReview(repair.draft_path)).status, "invalid");
  assert.equal(loadPlan(result.artifact_root).planDigest, original.planDigest);
  const { writeArtifact } = await import("../dist/contract.js");
  const historical = { ...original.plan, review_contract_version: 6 };
  delete historical.review_source;
  const [path, digest] = await writeArtifact(result.artifact_root, "review_plan", historical);
  writeJson(join(result.artifact_root, "review-current.json"), {
    ...original.progress,
    plan_path: path,
    plan_digest: digest,
  });
  await assert.rejects(repairReview(result.artifact_root, "presentation"), /historical/);
  assert.ok(planItems(loadPlan(result.artifact_root)).every((item) => item.actions.length === 0));
});
