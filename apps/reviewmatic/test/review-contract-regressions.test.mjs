import assert from "node:assert/strict";
import { statSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  startReview,
  resumeReview,
  checkReview,
  finishReview,
  DRAFT_SCHEMA,
  schemaIssues,
} from "../dist/draft.js";
import {
  artifactPayload,
  artifactSchema,
  readJson,
  writeJson,
  writeArtifact,
} from "../dist/contract.js";
import {
  validateUserConfirmation,
  validateFindingPublications,
  scaffoldReview,
} from "../dist/context.js";
import { loadPlan, planItems, sendItem, amendBody } from "../dist/tui/support.js";
import { repairReview } from "../dist/draft.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

const finding = (id, severity = "high") => ({
  id,
  severity,
  summary: "Retry repeats a write",
  risk: "A retry repeats the external operation.",
  evidence: ["The exact retry path has no request key."],
  consequence: "A caller can receive a duplicate charge.",
  relation_to_change: "The changed retry path reaches this write.",
  minimum_fix: "Reuse the request key.",
});
const disposition = (id, extra = {}) => ({
  id,
  decision: "accept",
  reason: "Verified against the exact head.",
  dependencies: { paths: ["review.txt"], thread_ids: ["42"], metadata_fields: [], ci: false },
  ...extra,
});

const safePatch =
  "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n@@ -1,2 +1,2 @@\n base\n-reviewed change\n+keyed retry\n";
async function lowLevel(t, overrides = {}) {
  const state = await prepared(t, overrides);
  const root = state.result.artifact_root;
  const progress = readJson(`${root}/review-current.json`);
  const [, receiptDigest] = await writeArtifact(root, "critic_receipt", state.draft.critics[0]);
  const threads = state.draft.content.thread_decisions
    .filter((thread) => thread.state === "open")
    .map((thread) => ({ id: `thread:${thread.id}` }));
  const decision = {
    schema: "portable-gitlab/review-decision/v2",
    evidence_digest: state.draft.evidence_digest,
    context_digest: state.draft.context_digest,
    finalize_digest: "0".repeat(64),
    critic_receipt_digest: receiptDigest,
    mode: state.result.mode,
    external_mutations: false,
    run_id: state.draft.run_id,
    session_id: state.draft.session_id,
    low_risk: false,
    verdict: "ready",
    findings: [],
    accepted_findings: [],
    critic_findings: [],
    unresolved_threads: threads,
    responses: threads.map((thread) => ({
      id: thread.id,
      decision: "accept",
      reason: "The complete discussion was inspected.",
    })),
    blocking_findings: false,
    blocking_finding_ids: [],
    blocking_thread_ids: [],
    ci_job_assessments: [],
    owner_decision_reasons: [],
  };
  const content = {
    ...structuredClone(state.draft.content),
    findings: [],
    rejected_candidates: [],
  };
  const contentPath = `${state.fixture.tmp}/low-level-content.json`;
  const scaffold = async (dryRun = false) => {
    writeJson(contentPath, content);
    const [decisionPath] = await writeArtifact(root, "review_decision", decision);
    return scaffoldReview(
      state.result.evidence_path,
      state.result.context_path,
      decisionPath,
      contentPath,
      dryRun
        ? {
            decision: structuredClone(decision),
            content: structuredClone(content),
            dryRun: true,
            freshnessChecked: true,
          }
        : undefined,
    );
  };
  return { ...state, root, progress, decision, content, scaffold };
}

test("low-level scaffold derives omitted thread blockers and rejects contradictory verdicts", async (t) => {
  const { root, progress, decision, content, scaffold } = await lowLevel(t);
  Object.assign(content.thread_decisions[0], {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    rationale: "The exact retry path still duplicates writes.",
    fix_mode: "suggestion",
    proposed_response: "Reuse the key.\n\n```suggestion\nkeyed retry\n```",
  });
  delete decision.blocking_thread_ids;
  await assert.rejects(scaffold(), /verdict does not match/);
  decision.blocking_thread_ids = [];
  await assert.rejects(scaffold(), /blocking_thread_ids do not match/);
  delete decision.blocking_thread_ids;
  decision.verdict = "not_ready";
  const accepted = await scaffold(true);
  assert.equal(accepted.status, "ok");
  assert.match(accepted.payload.summary, /still duplicates writes/);
  assert.match(accepted.payload.markdown, /Blocks merge/);
  assert.ok(!accepted.payload.summary.includes("No blocking findings"));
  assert.deepEqual(readJson(`${root}/review-current.json`), progress);
  content.thread_decisions[0].severity = "low";
  decision.verdict = "ready";
  assert.equal((await scaffold(true)).status, "ok");
});

for (const owner of ["finding", "thread"])
  test(`low-level scaffold rejects an available safe suggestion for ${owner} patch`, async (t) => {
    const { root, progress, decision, content, scaffold } = await lowLevel(t, { resolved: true });
    decision.verdict = "not_ready";
    const fix = {
      fix_mode: "patch",
      patch: safePatch,
      patch_reason: "Keep the complete correction together.",
    };
    if (owner === "finding") {
      const candidate = finding("primary-retry");
      decision.findings = [candidate];
      decision.accepted_findings = [candidate];
      decision.blocking_findings = true;
      decision.blocking_finding_ids = [candidate.id];
      decision.responses = [
        { id: candidate.id, decision: "accept", reason: "Confirmed on the exact head." },
      ];
      content.findings = [candidate];
      content.finding_publications = [
        {
          ...fix,
          finding_id: candidate.id,
          type: "line",
          path: "review.txt",
          line: 2,
          old_line: null,
          body: "Reuse the request key.",
        },
      ];
    } else {
      decision.blocking_thread_ids = ["42"];
      Object.assign(content.thread_decisions[0], {
        ...fix,
        severity: "medium",
        assessment: "accepted",
        outcome: "reopen",
        proposed_response: "Reuse the request key.",
      });
    }
    await assert.rejects(scaffold(), /safe bounded suggestion is available/);
    assert.deepEqual(readJson(`${root}/review-current.json`), progress);
  });

test("an author's local patch remains valid even when a bounded suggestion exists", async (t) => {
  const { result, draft } = await prepared(t, { resolved: true, mrAuthor: "reviewer" });
  draft.findings = [finding("primary-retry")];
  draft.dispositions = [disposition("primary-retry")];
  draft.content.finding_publications = [
    {
      finding_id: "primary-retry",
      type: "local_fix",
      path: null,
      line: null,
      old_line: null,
      body: "Reuse the request key.",
      fix_mode: "patch",
      patch: safePatch,
      patch_reason: "The author applies a validated local patch.",
    },
  ];
  writeJson(result.draft_path, draft);
  const finished = await finishReview(result.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  assert.equal(loadPlan(result.artifact_root).plan.role, "author");
  assert.ok(
    !loadPlan(result.artifact_root).plan.publication_preview.actions.some(
      (action) => action.kind === "finding",
    ),
  );
});

test("routing-only replies are editable without changing positioned suggestions and survive repair", async (t) => {
  const { fixture, result, draft } = await prepared(t, { positionHead: "a".repeat(40) });
  const thread = draft.content.thread_decisions[0];
  Object.assign(thread, {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    fix_mode: "suggestion",
    proposed_response: "The existing request key must cover this retry.",
    suggestions: [
      {
        path: "review.txt",
        line: 2,
        body: "Reuse the request key.\n\n```suggestion\nkeyed retry\n```",
      },
    ],
  });
  writeJson(result.draft_path, draft);
  assert.equal((await finishReview(result.draft_path)).status, "ok");
  const before = loadPlan(result.artifact_root);
  const requests = fixture.requestCount();
  const edited = await amendBody(
    before,
    "thread-42",
    "The correction is proposed on the current lines in a separate thread.",
  );
  assert.deepEqual(
    edited.plan.thread_decisions[0].suggestions,
    before.plan.thread_decisions[0].suggestions,
  );
  assert.equal(
    edited.plan.review_source.content.thread_decisions[0].proposed_response,
    thread.proposed_response,
  );
  assert.match(
    edited.plan.review_source.content.thread_decisions[0].routing_response,
    /separate thread/,
  );
  assert.match(
    planItems(edited).find((item) => item.publicationId === "thread-42").body,
    /separate thread/,
  );
  await assert.rejects(
    amendBody(edited, "thread-42", "```suggestion\nunverified replacement\n```"),
    /routing-only reply must remain prose/,
  );
  const part = planItems(edited).find((item) => item.publicationId.includes("@suggestion"));
  await assert.rejects(
    amendBody(
      edited,
      part.publicationId,
      part.body.replace("keyed retry", "unverified replacement"),
    ),
    /Changed suggestion code/,
  );
  const repair = await repairReview(result.artifact_root, "presentation");
  const source = readJson(repair.draft_path);
  source.repair.rationale = "Preserve the edited routing reply and the exact suggestion result.";
  source.repair.checks = ["Compared the routing reply and unchanged suggestion bytes."];
  writeJson(repair.draft_path, source);
  const finished = await finishReview(repair.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  assert.match(
    loadPlan(result.artifact_root).plan.markdown,
    /correction is proposed on the current lines in a separate thread/,
  );
  assert.deepEqual(
    loadPlan(result.artifact_root).plan.thread_decisions[0].suggestions,
    thread.suggestions,
  );
  assert.equal(fixture.requestCount(), requests);
});

test("a later user-proposed patch and prior confirmation use the complete chronology", () => {
  const context = { current_user_username: "reviewer" };
  const source = {
    root_note_id: 42,
    notes: [
      { id: 42, author: { username: "reviewer" }, body: "Retries duplicate writes." },
      { id: 43, author: { username: "reviewer" }, body: "```diff\n-keyless\n+keyed\n```" },
      { id: 44, author: { username: "maintainer" }, body: "Applied and closed." },
      { id: 45, author: { username: "reviewer" }, body: "Checked, the retry reuses the key." },
    ],
  };
  const decision = {
    assessment: "fixed",
    outcome: "no_publication",
    user_confirmation: { status: "required", evidence_note_ids: [] },
  };
  assert.throws(
    () => validateUserConfirmation(decision, source, context),
    /still needs their confirmation/,
  );
  decision.user_confirmation = { status: "confirmed", evidence_note_ids: [45] };
  assert.doesNotThrow(() => validateUserConfirmation(decision, source, context));
  decision.outcome = "reply";
  assert.throws(() => validateUserConfirmation(decision, source, context), /already confirmed fix/);
  decision.user_confirmation.new_circumstances =
    "A new failure path was verified after the confirmation.";
  assert.doesNotThrow(() => validateUserConfirmation(decision, source, context));
  decision.user_confirmation.evidence_note_ids = [44];
  assert.throws(
    () => validateUserConfirmation(decision, source, context),
    /user's later confirmation/,
  );
});
async function prepared(t, overrides = {}) {
  const fixture = reviewFixture(t, overrides);
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  return { fixture, result, draft: await completeDraft(readJson(result.draft_path), result) };
}
function linkedDefect(draft) {
  const thread = draft.content.thread_decisions[0];
  Object.assign(thread, {
    assessment: "accepted",
    severity: "high",
    outcome: thread.state === "resolved" ? "reopen" : "reply",
    rationale: "The retry still repeats a write on the exact head.",
    proposed_response: "Reuse the key.\n\n```suggestion\nkeyed retry\n```",
    fix_mode: "suggestion",
  });
  draft.content.finding_publications = [
    {
      finding_id: "critic-retry",
      type: "existing_thread",
      thread_id: "42",
      path: null,
      line: null,
      old_line: null,
      body: "The existing discussion owns this fix.",
      fix_mode: "not_required",
      patch: null,
    },
  ];
}

test("verdict, effective severity and existing-thread dedup preserve the original receipt", async (t) => {
  const { result, draft } = await prepared(t, { resolved: true });
  draft.critics[0].findings = [finding("critic-retry")];
  draft.findings = [finding("primary-retry")];
  draft.dispositions = [
    disposition("primary-retry", {
      decision: "reject",
      duplicate_of: "critic-retry",
      reason: "Same defect as the accepted critic finding.",
    }),
    disposition("critic-retry", {
      severity_override: {
        original_severity: "high",
        severity: "medium",
        reason: "Only callers enabling retry are affected.",
      },
    }),
  ];
  linkedDefect(draft);
  const receipt = structuredClone(draft.critics[0]);
  draft.content.summary = "This deliberately stale prose says ready to merge.";
  writeJson(result.draft_path, draft);
  const checked = await checkReview(result.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  const finished = await finishReview(result.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  const [, plan] = artifactPayload(finished.artifact_path, "review_plan");
  assert.equal(plan.verdict, "not_ready");
  assert.equal(plan.findings[0].severity, "medium");
  assert.equal(plan.thread_decisions[0].severity, "medium");
  assert.ok(!plan.summary.includes("deliberately stale"));
  assert.deepEqual(plan.review_source.critics[0], receipt);
  assert.equal(
    plan.publication_preview.actions.filter((action) => action.kind === "finding").length,
    0,
  );
  assert.deepEqual(
    plan.publication_preview.actions
      .filter((action) => action.kind === "thread")
      .map((action) => action.operation),
    ["reply", "reopen"],
  );
  const markdown = plan.markdown;
  assert.ok(markdown.indexOf("Merge impact") < markdown.indexOf("## MR metadata"));
  assert.ok(markdown.indexOf("Architecture assessment") < markdown.indexOf("## MR metadata"));
  assert.ok(markdown.indexOf("MR contribution") < markdown.indexOf("## MR metadata"));
  assert.match(markdown, /1 blocking findings/);
  assert.match(markdown, /Blocks merge/);
  assert.match(
    markdown,
    /# Publish reply:\n.* &&\n# After successful publication, reopen the thread:\n/,
  );
});

test("a user's suggestion closed by somebody else still requires their confirmation", async (t) => {
  const { fixture, result, draft } = await prepared(t, {
    resolved: true,
    rootAuthor: "reviewer",
    resolvedBy: { username: "maintainer" },
    noteBody: "The retry duplicates writes.\n\n```suggestion\nkeyed retry\n```",
    replies: [
      { id: 43, system: false, author: { username: "maintainer" }, body: "Applied and closing." },
    ],
  });
  assert.equal(draft.content.thread_decisions[0].user_confirmation.status, "required");
  writeJson(result.draft_path, draft);
  let checked = await checkReview(result.draft_path);
  assert.ok(
    checked.errors.some(
      (error) =>
        error.path.endsWith(".user_confirmation") &&
        /another participant resolved/.test(error.message),
    ),
  );
  draft.content.thread_decisions[0].outcome = "reply";
  draft.content.thread_decisions[0].proposed_response =
    "Thanks, the exact retry path now reuses the key.";
  writeJson(result.draft_path, draft);
  checked = await checkReview(result.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal((await finishReview(result.draft_path)).status, "ok");
  writeFileSync(
    fixture.configPath,
    JSON.stringify({
      ...fixture.config,
      replies: [
        ...fixture.config.replies,
        {
          id: 44,
          system: false,
          author: { username: "reviewer" },
          body: "Checked the correction, thanks.",
        },
      ],
    }),
  );
  const next = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const confirmed = await completeDraft(readJson(next.draft_path), next);
  confirmed.content.thread_decisions[0].user_confirmation = {
    status: "confirmed",
    evidence_note_ids: [44],
  };
  writeJson(next.draft_path, confirmed);
  checked = await checkReview(next.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal((await finishReview(next.draft_path)).status, "ok");
  assert.equal(
    loadPlan(next.artifact_root).plan.publication_preview.actions.filter(
      (action) => action.kind === "thread",
    ).length,
    0,
  );
  assert.match(loadPlan(next.artifact_root).plan.markdown, /exact reviewed code already addresses/);
});

test("grouped suggestions use the original position or link a new positioned thread", async (t) => {
  const { result, draft } = await prepared(t);
  const thread = draft.content.thread_decisions[0];
  Object.assign(thread, {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    fix_mode: "suggestion",
    proposed_response: "Shared explanation must not be repeated.",
    suggestions: [
      { path: "review.txt", line: 2, body: "Reuse the key.\n\n```suggestion\nkeyed retry\n```" },
    ],
  });
  writeJson(result.draft_path, draft);
  assert.equal((await finishReview(result.draft_path)).status, "ok");
  let plan = loadPlan(result.artifact_root).plan;
  assert.equal(
    plan.verdict,
    "not_ready",
    "a defect cannot disappear just because it belongs to a thread",
  );
  assert.deepEqual(
    plan.publication_preview.actions
      .filter((action) => action.kind === "thread")
      .map((action) => action.operation),
    ["reply"],
  );
  assert.match(plan.publication_preview.body_files[0].content, /```suggestion/);
  const { fixture } = await prepared(t, { positionHead: "a".repeat(40) });
  const other = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const stalePosition = await completeDraft(readJson(other.draft_path), other);
  Object.assign(stalePosition.content.thread_decisions[0], {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    fix_mode: "suggestion",
    proposed_response: "Shared explanation must not be repeated.",
    suggestions: thread.suggestions,
  });
  writeJson(other.draft_path, stalePosition);
  const finished = await finishReview(other.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  plan = loadPlan(other.artifact_root).plan;
  const bodies = plan.publication_preview.body_files;
  assert.ok(
    !bodies
      .find((body) => body.publication_id === "thread-42")
      .content.includes("Shared explanation"),
  );
  assert.match(
    bodies.find((body) => body.publication_id.includes("@suggestion")).content,
    /Original thread: \[42\]\(https:/,
  );
});

test("input package has the exact draft schema and examples; validation gathers independent errors without reads", async (t) => {
  const { fixture, result, draft } = await prepared(t);
  const schema = readJson(result.draft_schema_path);
  assert.throws(
    () =>
      validateFindingPublications(
        [{ ...result.input_examples.suggestion, thread_id: "42" }],
        new Set(["primary-retry"]),
      ),
    /valid only with type=existing_thread/,
  );
  assert.deepEqual(schema.$defs, artifactSchema().$defs);
  assert.deepEqual(schemaIssues(DRAFT_SCHEMA, draft), []);
  for (const [name, value] of Object.entries(result.input_examples)) {
    const shape =
      name === "disposition"
        ? DRAFT_SCHEMA.properties.dispositions.items
        : name === "severity_override"
          ? DRAFT_SCHEMA.properties.dispositions.items.properties.severity_override
          : name === "follow_up"
            ? DRAFT_SCHEMA.properties.content.properties.recommended_issues.items
            : name === "thread_decision"
              ? DRAFT_SCHEMA.properties.content.properties.thread_decisions.items
              : DRAFT_SCHEMA.properties.content.properties.finding_publications.items;
    // A thread decision example is a semantic update of one prepared thread:
    // it validates as the merged record the runtime assembles, never as a
    // standalone full record with hand-copied machine bindings.
    const preparedThread =
      draft.content.thread_decisions.find((item) => item.id === value.id) ??
      draft.content.thread_decisions[0];
    const candidate =
      name === "thread_decision" ? { ...preparedThread, ...value, id: preparedThread.id } : value;
    assert.deepEqual(schemaIssues(shape, candidate), [], name);
  }
  writeJson(result.draft_path, draft);
  const count = fixture.requestCount();
  assert.equal((await checkReview(result.draft_path)).status, "ok");
  const mtime = statSync(result.inspection_path).mtimeMs;
  assert.equal((await resumeReview(result.artifact_root)).inspection_path, result.inspection_path);
  assert.equal(statSync(result.inspection_path).mtimeMs, mtime);
  assert.equal(fixture.requestCount(), count);
  draft.content.summary = "";
  draft.critics[0].findings = [finding("critic-retry")];
  draft.critics[0].findings[0].evidence = [`Head ${fixture.headSha}`];
  draft.content.finding_publications = [
    {
      finding_id: "critic-retry",
      type: "line",
      path: "review.txt",
      line: 2,
      old_line: null,
      body: "Correct.\n\n```suggestion:-4+0\nfixed\n```",
      fix_mode: "suggestion",
      patch: null,
    },
  ];
  writeJson(result.draft_path, draft);
  const invalid = await checkReview(result.draft_path);
  assert.equal(invalid.status, "invalid");
  for (const path of [
    "$.content.summary",
    "$.critics[0].findings[0].evidence[0]",
    "$.content.finding_publications[0].body",
  ])
    assert.ok(
      invalid.errors.some((error) => error.path === path),
      JSON.stringify(invalid.errors),
    );
  assert.equal(fixture.requestCount(), count);
  Object.assign(draft.content.thread_decisions[0], {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    fix_mode: "suggestion",
    proposed_response: "The parts are separate corrections.",
    split_rationale: "The changes have independent consumers.",
    suggestions: [
      { path: "review.txt", line: 1, body: "```suggestion:-2+0\nfixed\n```" },
      { path: "review.txt", line: 2, body: "```suggestion:-0+4\nfixed\n```" },
    ],
  });
  writeJson(result.draft_path, draft);
  const invalidParts = await checkReview(result.draft_path);
  for (const index of [0, 1])
    assert.ok(
      invalidParts.errors.some(
        (error) =>
          error.path === `$.content.thread_decisions[0].suggestions[${index}].body` &&
          /expected a non-overlapping range within/.test(error.message),
      ),
      JSON.stringify(invalidParts.errors),
    );
  assert.equal(fixture.requestCount(), count);
  assert.match(result.critic_task.instructions, /Launch immediately.*background.*alongside/);
  assert.match(result.critic_task.instructions, /never manually transcribed/);
  assert.equal(result.critic_task.launch_when, "evidence_ready");
  assert.equal(result.critic_task.preferred_execution, "native_background");
  assert.equal(result.critic_task.join_before, "check-review");
  assert.equal(result.critic_task.draft_schema_path, result.draft_schema_path);
});

test("follow-ups are concise proposals, not issue publication or mandatory MR fixes", async (t) => {
  const { result, draft } = await prepared(t, { resolved: true });
  draft.content.recommended_issues = [result.input_examples.follow_up];
  writeJson(result.draft_path, draft);
  const finished = await finishReview(result.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  const plan = loadPlan(result.artifact_root).plan;
  assert.equal(plan.verdict, "ready");
  assert.ok(!plan.publication_preview.actions.some((action) => action.kind === "issue"));
  assert.match(plan.markdown, /Non-blocking operational improvement/);
  assert.ok(!plan.markdown.includes("description=@"));
});

test("patch reasons precede thread patches and an available safe suggestion rejects fallback", async (t) => {
  const { result, draft } = await prepared(t);
  const thread = draft.content.thread_decisions[0];
  Object.assign(thread, {
    assessment: "accepted",
    severity: "medium",
    outcome: "reply",
    fix_mode: "patch",
    proposed_response: "Add the missing policy file.",
    patch_reason: "A new file has no existing suggestion anchor.",
    patch:
      "diff --git a/policy.txt b/policy.txt\nnew file mode 100644\n--- /dev/null\n+++ b/policy.txt\n@@ -0,0 +1 @@\n+keyed retries\n",
  });
  writeJson(result.draft_path, draft);
  const finished = await finishReview(result.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  const body = loadPlan(result.artifact_root).plan.publication_preview.body_files[0].content;
  assert.ok(body.indexOf(thread.patch_reason) < body.indexOf("git apply"));
  thread.patch =
    "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n@@ -1,2 +1,2 @@\n base\n-reviewed change\n+keyed retry\n";
  writeJson(result.draft_path, draft);
  assert.ok(
    (await checkReview(result.draft_path)).errors.some(
      (error) =>
        error.path.endsWith(".patch_reason") && /safe bounded suggestion/.test(error.message),
    ),
  );
});

for (const completed of [true, false])
  test(`ordinary comment uses returned discussion identity, completed=${completed}`, async (t) => {
    const { fixture, result, draft } = await prepared(t, { plain: true, returnedResolvable: true });
    if (!completed)
      Object.assign(draft.content.thread_decisions[0], {
        assessment: "question",
        rationale: "The policy question is still unanswered.",
        proposed_response: "Does this policy cover retries?",
      });
    writeJson(result.draft_path, draft);
    assert.equal((await finishReview(result.draft_path)).status, "ok");
    const bundle = loadPlan(result.artifact_root);
    const item = planItems(bundle).find((item) => item.kind === "thread");
    const sent = await sendItem(bundle, item, null);
    assert.equal(sent.results[0].status, "sent", JSON.stringify(sent));
    assert.equal(readJson(fixture.configPath).createdResolved, completed ? true : undefined);
    if (completed) {
      writeFileSync(fixture.configPath, JSON.stringify(fixture.config));
      const block = [...bundle.plan.markdown.matchAll(/```shell\n([\s\S]*?)\n```/g)].find((match) =>
        match[1].includes("response=$("),
      )[1];
      assert.match(block, /discussion_id=.*jq/);
      const run = spawnSync("sh", ["-c", block], { encoding: "utf8", env: process.env });
      assert.equal(run.status, 0, run.stderr);
      assert.equal(readJson(fixture.configPath).createdResolved, true);
      writeFileSync(
        fixture.configPath,
        JSON.stringify({ ...fixture.config, mutationError: "Synthetic POST failure" }),
      );
      const failed = spawnSync("sh", ["-c", block], { encoding: "utf8", env: process.env });
      assert.notEqual(failed.status, 0);
      assert.equal(readJson(fixture.configPath).createdResolved, undefined);
    }
  });

test("thread state changes follow a successful reply in the same annotated shell block", async (t) => {
  const { fixture, result, draft } = await prepared(t);
  writeJson(result.draft_path, draft);
  assert.equal((await finishReview(result.draft_path)).status, "ok");
  const bundle = loadPlan(result.artifact_root);
  const item = planItems(bundle).find((item) => item.kind === "thread");
  await assert.rejects(
    sendItem(
      bundle,
      { ...item, actions: item.actions.filter((action) => action.operation === "resolve") },
      null,
    ),
    /reply successfully/,
  );
  const block = [...bundle.plan.markdown.matchAll(/```shell\n([\s\S]*?)\n```/g)].find((match) =>
    match[1].includes("/discussion-42/notes"),
  )[1];
  assert.match(
    block,
    /# Publish reply:\n.* &&\n# After successful publication, resolve the thread:\n/,
  );
  writeFileSync(
    fixture.configPath,
    JSON.stringify({ ...fixture.config, mutationError: "Synthetic POST failure" }),
  );
  const failed = spawnSync("sh", ["-c", block], { encoding: "utf8", env: process.env });
  assert.notEqual(failed.status, 0);
  assert.notEqual(readJson(fixture.configPath).resolved, true);
  writeFileSync(fixture.configPath, JSON.stringify(fixture.config));
  const sent = spawnSync("sh", ["-c", block], { encoding: "utf8", env: process.env });
  assert.equal(sent.status, 0, sent.stderr);
  assert.equal(readJson(fixture.configPath).resolved, true);
});
