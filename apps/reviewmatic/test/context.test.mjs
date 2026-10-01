import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
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
import { basename, join } from "node:path";
import test from "node:test";
import { VERSION } from "../dist/version.js";
import { FAKE_GLAB } from "./helpers/review-fixture.mjs";
import {
  WorkflowError,
  collect,
  finalize,
  finalizePayload,
  parseTarget,
  readJson,
  reviewPublicationPreviewIsValid,
  writeArtifact,
  writeJson,
} from "../dist/contract.js";
import {
  PROGRESS_NAME,
  BASELINE_NAME,
  advanceProgress,
  beginReview,
  emptyProgress,
  loadProgress,
  prepareContext,
  progressPath,
  publishReviewState,
  rejectVisibleRawRefs,
  reportReview,
  reviewStatus,
  runnerAction,
  scaffoldReview,
  templateReview,
  validateFindingPublications,
  validateReviewVerdict,
} from "../dist/context.js";

function workflowError(pattern) {
  return (error) => {
    assert.ok(error instanceof WorkflowError, `expected WorkflowError, got ${error}`);
    assert.match(error.message, pattern);
    return true;
  };
}

function git(repo, ...args) {
  const result = spawnSync("git", ["-C", repo, ...args], { encoding: "utf8" });
  assert.equal(result.status, 0, `git ${args.join(" ")} failed: ${result.stderr}`);
  return result.stdout.trim();
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

test("runner action renders reviewmatic CLI invocations", () => {
  const action = runnerAction(
    "context",
    ["--evidence", "/tmp/evidence.json", "--repo-root", "<checkout>"],
    ["repo_root"],
  );
  assert.equal(action.argv[0], "reviewmatic");
  assert.equal(action.argv[1], "context");
  assert.equal(
    action.command,
    "reviewmatic context --evidence /tmp/evidence.json --repo-root '<checkout>'",
  );
  assert.deepEqual(action.required_inputs, ["repo_root"]);
});

test("progress machine rejects invalid transitions", async (t) => {
  const tmp = mkdtempSync(join(tmpdir(), "review-progress-"));
  t.after(() => rmSync(tmp, { recursive: true, force: true }));
  const root = join(tmp, "state");
  mkdirSync(root, { recursive: true });
  const progress = emptyProgress(
    `${root}/artifacts/evidence_snapshot/${"b".repeat(64)}.json`,
    "b".repeat(64),
    { mode: "normal", locale: "en" },
  );
  progress.stage = "prepared";
  writeJson(progressPath(root), progress);
  await assert.rejects(
    advanceProgress(root, "decision_missing", {
      expectedStages: new Set(["context_ready", "finalize_missing"]),
    }),
    workflowError(/changed during transition/),
  );
  await assert.rejects(
    advanceProgress(root, "context_ready", { mystery_field: 1 }),
    workflowError(/unknown fields/),
  );
  await assert.rejects(
    advanceProgress(root, "finished", {}),
    workflowError(/progress stage is invalid/),
  );
  const broken = { ...progress, context_digest: "b".repeat(64) };
  writeJson(progressPath(root), broken);
  assert.throws(() => loadProgress(root), /artifact binding is incomplete/);
  writeJson(progressPath(root), { schema: "code-review/progress/v1" });
  assert.throws(() => loadProgress(root), /invalid shape/);
});

test("line finding publications require exactly one suggestion block", () => {
  const invalid = {
    finding_id: "finding-1",
    type: "line",
    path: "src/example.py",
    line: 7,
    old_line: null,
    body: "Replace this line.",
    fix_mode: "suggestion",
    patch: null,
  };
  assert.throws(
    () => validateFindingPublications([invalid], new Set(["finding-1"])),
    /suggestion fix requires one suggestion and no patch/,
  );
  const valid = {
    ...invalid,
    body: "Use the bounded value.\n\n```suggestion:-1+1\nvalue = bounded\n```",
  };
  assert.deepEqual(validateFindingPublications([valid], new Set(["finding-1"])), [valid]);
  const general = {
    ...invalid,
    type: "general",
    path: null,
    line: null,
    old_line: null,
    body: "Apply the complete fix.",
    fix_mode: "patch",
    patch:
      "diff --git a/src/example.py b/src/example.py\n" +
      "--- a/src/example.py\n" +
      "+++ b/src/example.py\n" +
      "@@ -1 +1 @@\n" +
      "-old\n" +
      "+new\n",
  };
  assert.deepEqual(validateFindingPublications([general], new Set(["finding-1"])), [general]);
});

test("review verdict keeps low findings non-blocking and gates CI classifications", () => {
  const low = {
    id: "docs-1",
    severity: "low",
    summary: "Documentation is incomplete",
    risk: "Readers can miss an option.",
    evidence: ["README omits the option."],
    consequence: "Adoption can take longer.",
    relation_to_change: "The change adds the option.",
    minimum_fix: "Document the option.",
  };
  const evidence = {
    head_sha: "c",
    pipelines: { complete: true, items: [{ id: 1, sha: "c", status: "failed" }] },
  };
  const report = {
    verdict: "blocked",
    blocking_findings: false,
    blocking_finding_ids: [],
    owner_decision_reasons: ["The exact-head pipeline failed."],
  };
  validateReviewVerdict(report, [low], evidence);
  assert.throws(
    () => validateReviewVerdict({ ...report, verdict: "not_ready" }, [low], evidence),
    /does not match findings/,
  );
  assert.throws(
    () =>
      validateReviewVerdict(
        {
          verdict: "not_ready",
          blocking_findings: true,
          blocking_finding_ids: ["docs-1"],
          owner_decision_reasons: [],
        },
        [low],
        evidence,
      ),
    /non-low finding must be blocking/,
  );
  const high = { ...low, id: "runtime-1", severity: "high" };
  const successful = {
    ...evidence,
    pipelines: { complete: true, items: [{ id: 2, sha: "c", status: "success" }] },
  };
  assert.throws(
    () =>
      validateReviewVerdict(
        {
          verdict: "ready",
          blocking_findings: false,
          blocking_finding_ids: [],
          owner_decision_reasons: [],
        },
        [high],
        successful,
      ),
    /non-low finding must be blocking/,
  );
  const jobEvidence = {
    head_sha: "c",
    pipelines: {
      complete: true,
      items: [
        {
          id: 2,
          sha: "c",
          status: "failed",
          job_evidence: {
            complete: true,
            errors: [],
            truncated: false,
            pipelines: [
              {
                project_id: 19,
                pipeline_id: 2,
                jobs: [
                  {
                    project_id: 19,
                    pipeline_id: 2,
                    id: 7,
                    status: "failed",
                    trace: {
                      complete: true,
                      truncated: false,
                      excerpt: "Merge request requires two approvals.",
                      sha256: "a".repeat(64),
                    },
                  },
                ],
              },
            ],
          },
        },
      ],
    },
  };
  const processGate = {
    project_id: 19,
    pipeline_id: 2,
    job_id: 7,
    classification: "process_gate",
    rationale: "The job enforces the approval policy rather than code quality.",
    trace_evidence: "requires two approvals",
  };
  validateReviewVerdict(
    {
      verdict: "ready",
      blocking_findings: false,
      blocking_finding_ids: [],
      owner_decision_reasons: [],
      ci_job_assessments: [processGate],
    },
    [low],
    jobEvidence,
  );
  assert.throws(
    () =>
      validateReviewVerdict(
        {
          verdict: "ready",
          blocking_findings: false,
          blocking_finding_ids: [],
          owner_decision_reasons: [],
          ci_job_assessments: [
            {
              ...processGate,
              classification: "code_failure",
              rationale: "The test assertion failed.",
            },
          ],
        },
        [low],
        jobEvidence,
      ),
    /owner decision reason|does not match findings/,
  );
  const rawHead = "a".repeat(40);
  assert.throws(
    () => rejectVisibleRawRefs(`Changed behavior at ${rawHead}`, { head_sha: rawHead }),
    /raw commit SHA/,
  );
  const previousHead = "b".repeat(40);
  assert.throws(
    () =>
      rejectVisibleRawRefs(
        `Compared from ${previousHead}`,
        { head_sha: rawHead },
        {
          incremental: { incremental_delta: { from_head: previousHead, to_head: rawHead } },
        },
      ),
    /raw commit SHA/,
  );
});

test("publish review state writes and rolls back atomically", async (t) => {
  const tmp = mkdtempSync(join(tmpdir(), "review-publish-"));
  t.after(() => {
    chmodSync(tmp, 0o700);
    rmSync(tmp, { recursive: true, force: true });
  });
  const root = tmp;
  chmodSync(root, 0o700);
  const markdown = join(root, "review-publication.md");
  const baseline = join(root, BASELINE_NAME);
  const progress = emptyProgress(
    `${root}/artifacts/evidence_snapshot/${"b".repeat(64)}.json`,
    "b".repeat(64),
    { mode: "normal", locale: "en" },
  );
  progress.stage = "content_missing";
  writeJson(progressPath(root), progress);
  const baselineDigest = () => (existsSync(baseline) ? sha256(readFileSync(baseline)) : null);

  writeFileSync(markdown, "old review\n");
  writeFileSync(baseline, '{"old":true}\n');
  const progressBytes = readFileSync(progressPath(root));
  await assert.rejects(
    publishReviewState(
      root,
      "new review\n",
      `${root}/artifacts/review_plan/${"a".repeat(64)}.json`,
      "a".repeat(64),
      { url: "https://gitlab.example/group/project/-/merge_requests/7" },
      "0".repeat(64),
      { stage: "content_missing" },
    ),
    workflowError(/baseline changed before publication/),
  );
  assert.equal(readFileSync(markdown, "utf8"), "old review\n");
  assert.equal(readFileSync(baseline, "utf8"), '{"old":true}\n');
  assert.deepEqual(readFileSync(progressPath(root)), progressBytes);

  writeFileSync(markdown, "new review\n");
  rmSync(baseline);
  chmodSync(root, 0o500);
  await assert.rejects(() =>
    publishReviewState(
      root,
      "new review\n",
      `${root}/artifacts/review_plan/${"a".repeat(64)}.json`,
      "a".repeat(64),
      { url: "https://gitlab.example/group/project/-/merge_requests/7" },
      baselineDigest(),
      { stage: "content_missing" },
    ),
  );
  chmodSync(root, 0o700);
  assert.equal(readFileSync(markdown, "utf8"), "new review\n");
  assert.deepEqual(readFileSync(progressPath(root)), progressBytes);

  const [path, digest] = await publishReviewState(
    root,
    "final review\n",
    `${root}/artifacts/review_plan/${"a".repeat(64)}.json`,
    "a".repeat(64),
    { url: "https://gitlab.example/group/project/-/merge_requests/7" },
    null,
    { stage: "content_missing" },
  );
  assert.equal(basename(path), "review-publication.md");
  assert.equal(digest, sha256("final review\n"));
  const written = readJson(join(root, BASELINE_NAME), "baseline");
  assert.equal(written.contract_version, 1);
  assert.equal(readJson(progressPath(root), "progress").stage, "plan_ready");
});

test("review state machine happy path with fake glab", async (t) => {
  const tmp = mkdtempSync(join(tmpdir(), "review-context-"));
  const previousStateHome = process.env.XDG_STATE_HOME;
  const previousPath = process.env.PATH;
  const previousConfig = process.env.FAKE_GLAB_CONFIG;
  process.env.XDG_STATE_HOME = join(tmp, "state");
  t.after(() => {
    if (previousStateHome === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previousStateHome;
    process.env.PATH = previousPath;
    if (previousConfig === undefined) delete process.env.FAKE_GLAB_CONFIG;
    else process.env.FAKE_GLAB_CONFIG = previousConfig;
    rmSync(tmp, { recursive: true, force: true });
  });
  const repo = join(tmp, "repository");
  mkdirSync(repo);
  git(repo, "init", "--quiet");
  git(repo, "config", "commit.gpgsign", "false");
  git(repo, "config", "user.email", "reviewer@example.invalid");
  git(repo, "config", "user.name", "Example Reviewer");
  writeFileSync(join(repo, "review.txt"), "base\n");
  git(repo, "add", "review.txt");
  git(repo, "commit", "-qm", "base");
  const baseSha = git(repo, "rev-parse", "HEAD");
  writeFileSync(join(repo, "review.txt"), "base\nreviewed change\n");
  git(repo, "commit", "-qam", "change");
  const headSha = git(repo, "rev-parse", "HEAD");
  const bin = join(tmp, "bin");
  mkdirSync(bin);
  const glabPath = join(bin, "glab");
  writeFileSync(glabPath, FAKE_GLAB);
  chmodSync(glabPath, 0o755);
  process.env.PATH = `${bin}:${previousPath}`;
  const configPath = join(tmp, "glab-config.json");
  writeFileSync(
    configPath,
    JSON.stringify({ baseSha, startSha: baseSha, headSha, changedPath: "review.txt" }),
  );
  process.env.FAKE_GLAB_CONFIG = configPath;

  const target = parseTarget(
    "https://gitlab.example/group/project/-/merge_requests/7",
    new Set(["merge_requests"]),
  );
  const bundle = await collect(target, "code-review", { persist: true });
  assert.equal(bundle.retrieval_complete, true);
  const evidencePath = bundle.preview_artifact_path;
  const evidenceDigest = bundle.preview_digest;
  const root = bundle.artifact_root;

  await beginReview(evidencePath, evidenceDigest, root, repo, "deep", "en", "auto");
  const contextResult = await prepareContext(evidencePath, repo, "auto", "deep", "en");
  assert.equal(contextResult.status, "ok");
  assert.equal(contextResult.stage, "context_ready");
  assert.equal(contextResult.role, "reviewer");
  assert.equal(contextResult.counts.open_resolvable, 1);
  assert.equal(contextResult.incremental.mode, "full");
  assert.equal(contextResult.next_action.argv[0], "reviewmatic");
  assert.equal(contextResult.next_action.argv[1], "template-review");
  assert.match(
    contextResult.next_action.command,
    /^reviewmatic template-review --artifact-root \S+ --kind critic$/,
  );
  const contextPath = contextResult.artifact_path;
  const contextDigest = contextResult.digest;

  const status1 = await reviewStatus(root);
  assert.equal(status1.stage, "critic_missing");
  assert.equal(status1.resume_stage, null);
  assert.match(status1.next_action.command, /^reviewmatic template-review /);

  const critic = await templateReview(root, "critic");
  assert.equal(critic.stage, "critic_missing");
  const criticDraft = readJson(critic.template_path, "critic template");
  assert.equal(criticDraft.run_id, "");
  assert.equal(criticDraft.evidence_digest, evidenceDigest);
  assert.match(critic.next_action.command, /^reviewmatic record-artifact /);

  const primaryFinding = {
    id: "primary-1",
    severity: "high",
    summary: "Retry can repeat the external operation",
    risk: "A retry can execute the operation twice.",
    evidence: ["The current retry path calls the provider before reserving an ID."],
    consequence: "Users can observe duplicate side effects.",
    relation_to_change: "The reviewed change adds the retry path.",
    minimum_fix: "Persist an idempotency key before the external call.",
  };
  const criticFinding = {
    id: "critic-1",
    severity: "medium",
    summary: "Retry failure is not observable",
    risk: "Operators cannot distinguish retry exhaustion.",
    evidence: [`The exact reviewed SHA is ${headSha}.`],
    consequence: "Incident diagnosis takes longer.",
    relation_to_change: "The new retry path emits no terminal signal.",
    minimum_fix: "Emit the existing terminal retry metric.",
  };
  const receipt = {
    schema: "portable-gitlab/critic-receipt/v2",
    external_mutations: false,
    evidence_digest: evidenceDigest,
    run_id: "critic-run",
    session_id: "critic-session",
    findings: [criticFinding],
  };
  const [receiptPath, receiptDigest] = await writeArtifact(root, "critic_receipt", receipt);
  const progress1 = loadProgress(root);
  await advanceProgress(root, "finalize_missing", {
    expectedStages: new Set(["context_ready"]),
    expected: {
      evidence_path: progress1.evidence_path,
      evidence_digest: progress1.evidence_digest,
      context_path: progress1.context_path,
      context_digest: progress1.context_digest,
    },
    critic_receipt_path: receiptPath,
    critic_receipt_digest: receiptDigest,
    finalize_report_path: null,
    finalize_report_digest: null,
    decision_path: null,
    decision_digest: null,
    plan_path: null,
    plan_digest: null,
  });

  const finalizeResult = finalizePayload(
    await finalize(root, "review-evidence.json"),
    evidencePath,
    bundle,
    "evidence_snapshot",
  );
  assert.equal(finalizeResult.status, "ok");
  const [finalizePath, finalizeDigest] = await writeArtifact(
    root,
    "finalize_report",
    finalizeResult,
  );
  const progress2 = loadProgress(root);
  await advanceProgress(root, "decision_missing", {
    expectedStages: new Set(["context_ready", "finalize_missing"]),
    expected: {
      evidence_path: progress2.evidence_path,
      evidence_digest: progress2.evidence_digest,
      context_path: progress2.context_path,
      context_digest: progress2.context_digest,
      critic_receipt_path: progress2.critic_receipt_path,
      critic_receipt_digest: progress2.critic_receipt_digest,
    },
    finalize_report_path: finalizePath,
    finalize_report_digest: finalizeDigest,
    decision_path: null,
    decision_digest: null,
    plan_path: null,
    plan_digest: null,
  });

  const decision = await templateReview(root, "decision");
  const decisionDraft = readJson(decision.template_path, "decision template");
  assert.equal(decisionDraft.context_digest, contextDigest);
  assert.deepEqual(decisionDraft.unresolved_threads, [{ id: "thread:42" }]);
  assert.equal(decisionDraft.verdict, "not_ready");
  assert.deepEqual(decisionDraft.responses, [
    { id: "critic-1", decision: "accept", reason: "" },
    { id: "thread:42", decision: "accept", reason: "" },
  ]);

  const decisionReport = {
    schema: "portable-gitlab/review-decision/v2",
    mode: "deep",
    external_mutations: false,
    evidence_digest: evidenceDigest,
    finalize_digest: finalizeDigest,
    context_digest: contextDigest,
    critic_receipt_digest: receiptDigest,
    verdict: "not_ready",
    blocking_findings: true,
    blocking_finding_ids: ["primary-1"],
    owner_decision_reasons: [],
    run_id: "primary-run",
    session_id: "primary-session",
    findings: [primaryFinding],
    unresolved_threads: [{ id: "thread:42" }],
    responses: [
      { id: "primary-1", decision: "accept", reason: "confirmed" },
      { id: "critic-1", decision: "reject", reason: "outside the changed contract" },
      { id: "thread:42", decision: "accept", reason: "still open" },
    ],
  };
  validateReviewVerdict(decisionReport, [primaryFinding], bundle);
  const decisionPayload = {
    ...decisionReport,
    critic_findings: [criticFinding],
    accepted_findings: [primaryFinding],
    critic_target_finding_ids: [],
  };
  const [decisionPath, decisionDigest] = await writeArtifact(
    root,
    "review_decision",
    decisionPayload,
  );
  const progress3 = loadProgress(root);
  await advanceProgress(root, "content_missing", {
    expectedStages: new Set(["decision_missing"]),
    expected: {
      evidence_path: progress3.evidence_path,
      evidence_digest: progress3.evidence_digest,
      context_path: progress3.context_path,
      context_digest: progress3.context_digest,
      critic_receipt_path: progress3.critic_receipt_path,
      critic_receipt_digest: progress3.critic_receipt_digest,
      finalize_report_path: progress3.finalize_report_path,
      finalize_report_digest: progress3.finalize_report_digest,
    },
    decision_path: decisionPath,
    decision_digest: decisionDigest,
    plan_path: null,
    plan_digest: null,
  });

  const content = await templateReview(root, "content");
  assert.equal(content.stage, "content_missing");
  const templateContent = readJson(content.template_path, "content template");
  assert.ok(!("presentation" in templateContent));
  assert.equal(templateContent.thread_decisions.length, 1);
  assert.equal(templateContent.label_assessments.length, 4);
  assert.equal(templateContent.rejected_candidates.length, 1);
  assert.equal(templateContent.rejected_candidates[0].id, "critic-1");
  assert.equal(templateContent.semver_assessment.mode, "target_fallback");

  const reviewContent = {
    locale: "en",
    chat_assessment: {
      necessity: { status: "supported", rationale: "The retry defect is confirmed." },
      relevance: { status: "current", rationale: "The exact reviewed head is current." },
      change:
        "The MR adds retry behavior but does not reserve an idempotency key before the external call.",
    },
    summary: "The change is small and preserves the reviewed contract.",
    architecture_assessment: "The responsibility remains with its existing owner.",
    semver_impact: "patch",
    semver_rationale: "The fix changes behavior without changing the public API.",
    semver_assessment: {
      ...templateContent.semver_assessment,
      policy: "No release policy was found in the fixture.",
      sources: ["Fixture repository and empty release catalog"],
      fallback_reason: "No confirmed release is available.",
    },
    mr_metadata_assessment: {
      title: {
        status: "needs_change",
        rationale: "The title does not identify the affected behavior.",
        recommendation: "Name the affected retry behavior.",
      },
      description: {
        status: "ok",
        rationale: "The description states the intended behavior.",
        recommendation: null,
      },
      labels: {
        status: "needs_change",
        rationale: "The MR has no labels.",
        recommendation: "Apply the project-required labels.",
      },
      workflow_state: {
        status: "ok",
        rationale: "The MR is open and remains commentable.",
        recommendation: null,
      },
      overall: {
        status: "needs_change",
        rationale: "Title and labels need clearer release metadata.",
        recommendation: "Correct metadata independently of code findings.",
      },
    },
    label_assessments: [
      {
        name: "next-compatible",
        status: "inapplicable",
        rationale: "The change is a patch, not a minor release.",
      },
      {
        name: "semver::major",
        status: "inapplicable",
        rationale: "The change is backward compatible.",
      },
      {
        name: "semver::patch",
        status: "applicable",
        rationale: "The reviewed fix has patch SemVer impact.",
      },
      {
        name: "ship-ready",
        status: "inapplicable",
        rationale: "This MR is not a release publication.",
      },
    ],
    checks: ["Compared the exact base and head revisions."],
    findings: [primaryFinding],
    finding_publications: [
      {
        finding_id: "primary-1",
        type: "general",
        path: null,
        line: null,
        old_line: null,
        body: "You need to reserve an idempotency key before the external call.",
        fix_mode: "patch",
        patch:
          "diff --git a/review.txt b/review.txt\n" +
          "--- a/review.txt\n" +
          "+++ b/review.txt\n" +
          "@@ -1,2 +1,3 @@\n" +
          " base\n" +
          " reviewed change\n" +
          "+reserve idempotency key\n",
      },
    ],
    previous_finding_assessments: [],
    issue_templates: [],
    recommended_issues: [
      {
        id: "issue-1",
        title: "Track retry exhaustion observability",
        problem: "The broader retry subsystem lacks a terminal signal.",
        risk: "Operators cannot distinguish retry exhaustion.",
        evidence: ["The existing subsystem has no terminal metric."],
        reason_out_of_scope: "The subsystem is not changed by this MR.",
        minimum_fix: "Add the existing terminal retry metric separately.",
        body: "Track a terminal metric for retry exhaustion in the broader subsystem.",
        template_path: null,
      },
    ],
    rejected_candidates: [
      {
        id: "critic-1",
        source: "critic",
        finding: criticFinding,
        reason: "The broader observability gap is outside this MR.",
        paths: ["review.txt"],
        thread_ids: [],
        metadata_fields: [],
        ci: false,
      },
    ],
    rejected_candidate_assessments: [],
    thread_decisions: [
      {
        id: "42",
        url: "https://gitlab.example/group/project/-/merge_requests/7#note_42",
        state: "open",
        assessment: "fixed",
        rationale: "The existing thread can be acknowledged and resolved.",
        outcome: "resolve",
        proposed_response: "I tracked the remaining risk in the current finding. Closing.",
        fix_mode: "not_required",
        patch: null,
        fixing_commit: null,
        last_note_id: 42,
        last_note_body_sha256: sha256("Retry needs an idempotency key"),
        thread_sha256: templateContent.thread_decisions[0].thread_sha256,
      },
    ],
  };
  const contentPath = join(tmp, "review-content.json");
  writeFileSync(contentPath, JSON.stringify(reviewContent));

  const invalidState = structuredClone(reviewContent);
  invalidState.thread_decisions[0] = {
    ...invalidState.thread_decisions[0],
    state: "resolved",
    outcome: "no_publication",
    proposed_response: null,
  };
  const invalidStatePath = join(tmp, "invalid-state.json");
  writeFileSync(invalidStatePath, JSON.stringify(invalidState));
  await assert.rejects(
    scaffoldReview(evidencePath, contextPath, decisionPath, invalidStatePath),
    workflowError(/thread decision state does not match review context/),
  );
  const invalidAccepted = structuredClone(reviewContent);
  invalidAccepted.thread_decisions[0] = {
    ...invalidAccepted.thread_decisions[0],
    assessment: "accepted",
    outcome: "reply",
    fix_mode: "not_required",
  };
  const invalidAcceptedPath = join(tmp, "invalid-accepted.json");
  writeFileSync(invalidAcceptedPath, JSON.stringify(invalidAccepted));
  await assert.rejects(
    scaffoldReview(evidencePath, contextPath, decisionPath, invalidAcceptedPath),
    workflowError(/an accepted thread requires a validated code fix/),
  );

  const plan = await scaffoldReview(evidencePath, contextPath, decisionPath, contentPath);
  assert.equal(plan.status, "ok");
  assert.equal(plan.stage, "plan_ready");
  assert.equal(basename(plan.markdown_path), "review-publication.md");
  assert.ok(existsSync(plan.markdown_path));
  const markdown = readFileSync(plan.markdown_path, "utf8");
  for (const section of [
    "# Code review publication plan",
    "## MR metadata",
    "## Project labels",
    "## Previous findings",
    "## Open threads",
    "## Closed threads",
    "## Local fixes",
    "## New findings",
    "## Recommended issues",
    "## Reviewed without publication",
    "## Architecture assessment",
    "## SemVer impact",
    "## Checks",
    "git apply <<'PATCH_",
    `code-review: ${VERSION} · contract: 6`,
    "Retry can repeat the external operation",
    "https://gitlab.example/group/project/-/merge_requests/7#note_42",
  ]) {
    assert.ok(markdown.includes(section), `markdown must contain ${section}`);
  }
  assert.ok(!markdown.includes(baseSha));
  assert.ok(!markdown.includes(headSha));
  assert.ok(!markdown.includes("marker-run"));
  assert.equal(plan.publication_body_paths.length, 3);
  const bodies = plan.publication_body_paths.map((path) => readFileSync(path, "utf8"));
  assert.ok(bodies.every((body) => !body.includes("<!-- code-review:id=")));
  const patchBody = bodies.find((body) => body.includes("diff --git"));
  assert.ok(patchBody.includes("```sh\n"));
  assert.ok(patchBody.includes("git apply <<'PATCH_"));
  assert.ok(!patchBody.includes("marker-run"));
  assert.equal(plan.publication_commands.length, 5);
  assert.ok(
    plan.publication_commands.every((command) =>
      command.startsWith("reviewmatic publication apply --action "),
    ),
  );
  assert.ok(plan.publication_commands.every((command) => command.includes(" --confirm ")));
  const planDocument = readJson(plan.artifact_path, "review plan");
  const payload = planDocument.payload;
  assert.equal(payload.review_contract_version, 6);
  assert.equal(payload.label_review.semver.selected, "semver::patch");
  assert.ok(reviewPublicationPreviewIsValid(payload.publication_preview));
  const threadActions = payload.publication_preview.actions.filter(
    (item) => item.kind === "thread",
  );
  assert.deepEqual(
    threadActions.map((item) => item.operation),
    ["reply", "resolve"],
  );
  const labelAction = payload.publication_preview.actions.find((item) => item.kind === "labels");
  const guardedAction = (command) => {
    const tokens = command.split(" ");
    const actionPath = tokens[tokens.indexOf("--action") + 1];
    const confirm = tokens[tokens.indexOf("--confirm") + 1];
    assert.equal(basename(actionPath), `${confirm}.json`);
    return JSON.parse(readFileSync(actionPath, "utf8"));
  };
  const labelGuard = guardedAction(labelAction.command);
  assert.equal(labelGuard.method, "PUT");
  assert.ok(labelGuard.payload.labels.includes("semver::patch"));
  const replyGuard = guardedAction(threadActions[0].command);
  assert.equal(replyGuard.method, "POST");
  assert.ok(replyGuard.endpoint.endsWith("/notes"));
  const closeGuard = guardedAction(threadActions[1].command);
  assert.equal(closeGuard.method, "PUT");
  assert.deepEqual(closeGuard.payload, { resolved: true });
  assert.ok(closeGuard.dependency);
  assert.equal(loadProgress(root).stage, "plan_ready");

  const status2 = await reviewStatus(root);
  assert.equal(status2.stage, "plan_ready");
  assert.equal(status2.status, "ok");
  assert.equal(status2.publication_plan_path, plan.markdown_path);

  const report = await reportReview(root);
  assert.equal(report.status, "ok");
  assert.equal(report.stage, "plan_ready");
  assert.ok(report.chat.includes("### MR assessment"));
  assert.ok(report.chat.includes(plan.markdown_path));
  assert.ok(!report.chat.includes(primaryFinding.summary));
  assert.equal(report.next_action, null);

  const bundle2 = await collect(target, "code-review", { persist: true });
  await beginReview(
    bundle2.preview_artifact_path,
    bundle2.preview_digest,
    root,
    repo,
    "deep",
    "en",
    "auto",
  );
  const context2 = await prepareContext(bundle2.preview_artifact_path, repo, "auto", "deep", "en");
  assert.equal(context2.incremental.mode, "unchanged");
  assert.equal(context2.incremental.critic_required, false);
  assert.equal(context2.review_mode, "unchanged");
  const context2Payload = readJson(context2.artifact_path, "review context").payload;
  assert.equal(context2Payload.incremental.mode, "unchanged");
  assert.equal(context2Payload.incremental.previous_findings.length, 1);
  assert.equal(context2Payload.incremental.previous_findings[0].id, "primary-1");
  assert.equal(context2Payload.incremental.previous_recommended_issues.length, 1);
  assert.equal(context2Payload.incremental.previous_recommended_issues[0].id, "issue-1");
  assert.match(context2.next_action.command, /^reviewmatic finalize /);
});
