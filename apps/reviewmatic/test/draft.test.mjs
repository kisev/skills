import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import { spawnSync } from "node:child_process";
import {
  startReview,
  resumeReview,
  checkReview,
  finishReview,
  schemaIssues,
} from "../dist/draft.js";
import { artifactPayload, artifactSchema, readJson, writeJson } from "../dist/contract.js";
import { loadProgress, reportReview } from "../dist/context.js";
import {
  loadPlan,
  planItems,
  selectedActions,
  itemText,
  amendBody,
  discoverArtifactRoot,
  sendItem,
} from "../dist/tui/support.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

test("schema diagnostics identify independent fields instead of a generic shape error", () => {
  const shared = JSON.parse(
    readFileSync(
      new URL(
        "../../../shared/references/portable_gitlab/artifact-contracts-v2.schema.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  assert.deepEqual(artifactSchema().$defs.critic_receipt, shared.$defs.critic_receipt);
  assert.deepEqual(
    schemaIssues(
      {
        type: "object",
        required: ["a", "b"],
        additionalProperties: false,
        properties: {
          a: { type: "string", minLength: 1 },
          b: { type: "array", items: { type: "string" } },
        },
      },
      { a: "", b: [3], unknown: true },
    ).map((item) => item.path),
    ["$.a", "$.b[0]", "$.unknown"],
  );
});

test("one draft completes remote review, validates locally, and retains real thread data", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo, locale: "ru" });
  assert.equal(started.status, "ok");
  assert.equal(started.critic_required, true);
  const root = started.artifact_root;
  const initialProgress = readFileSync(join(root, "review-current.json"));
  const requests = fixture.requestCount();
  const invalid = await checkReview(started.draft_path);
  assert.equal(invalid.status, "invalid");
  assert.ok(invalid.errors.some((item) => item.path === "$.run_id"));
  assert.ok(invalid.errors.some((item) => item.path === "$.content.summary"));
  assert.equal(fixture.requestCount(), requests);
  assert.deepEqual(readFileSync(join(root, "review-current.json")), initialProgress);
  assert.equal(existsSync(join(root, "artifacts", "review_decision")), false);
  const resumed = await resumeReview(root);
  assert.equal(resumed.draft_path, started.draft_path);
  assert.equal(fixture.requestCount(), requests);
  const inspection = readJson(started.inspection_path);
  const headFile = inspection.files.find((item) => item.side === "head");
  assert.equal(readFileSync(headFile.snapshot_path, "utf8"), "base\nreviewed change\n");
  const draft = await completeDraft(readJson(started.draft_path), started);
  writeJson(started.draft_path, draft);
  const checked = await checkReview(started.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal(fixture.requestCount(), requests);
  assert.deepEqual(readFileSync(join(root, "review-current.json")), initialProgress);
  assert.equal(existsSync(join(root, "artifacts", "review_plan")), false);
  const finished = await finishReview(started.draft_path);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  assert.ok(!finished.chat.includes("undefined"));
  assert.match(finished.chat, /Оформление MR.*готово/);
  assert.equal(loadProgress(root).stage, "plan_ready");
  assert.equal(discoverArtifactRoot(), root);
  assert.equal((await resumeReview(root)).stage, "plan_ready");
  const collected = fixture.requestCount() - requests;
  assert.equal(collected, 0, "finalization collects nothing; it is local-only");
  const bundle = loadPlan(root);
  const thread = planItems(bundle).find((item) => item.kind === "thread");
  assert.equal(thread.path, "review.txt");
  assert.equal(thread.line, 2);
  assert.match(thread.url, /#note_42$/);
  assert.match(itemText(thread), /Retry needs an idempotency key/);
  assert.match(itemText(thread), /exact reviewed code/);
  assert.deepEqual(
    thread.actions.map((item) => item.operation),
    ["reply", "resolve"],
  );
  assert.deepEqual(
    selectedActions(
      thread.actions,
      thread.actions.filter((item) => item.operation === "reply"),
    ).map((item) => item.operation),
    ["reply"],
  );
  assert.equal(readdirSync(join(root, "artifacts", "review_decision")).length, 1);
  const edited = await amendBody(
    bundle,
    thread.publicationId,
    "The checked retry path now behaves as intended. Closing.\n",
  );
  assert.notEqual(edited.planDigest, bundle.planDigest);
  assert.match(readFileSync(finished.markdown_path, "utf8"), /checked retry path/);
  assert.equal((await reportReview(root)).status, "ok");
  assert.match(planItems(edited).find((item) => item.kind === "thread").body, /checked retry path/);
  assert.equal(bundle.plan.publication_preview.actions[0].command, thread.actions[0].command);
  const selectedThread = planItems(edited).find((item) => item.kind === "thread");
  const replyOnly = {
    ...selectedThread,
    actions: selectedThread.actions.filter((item) => item.operation === "reply"),
  };
  const sent = await sendItem(edited, replyOnly, null);
  assert.equal(sent.results.length, 1);
  assert.equal(sent.results[0].status, "sent", JSON.stringify(sent.results));
  const afterReply = readJson(fixture.configPath);
  assert.notEqual(afterReply.resolved, true);
  assert.equal(afterReply.publishedNotes.length, 1);
  const resolved = await sendItem(
    edited,
    {
      ...selectedThread,
      actions: selectedThread.actions.filter((item) => item.operation === "resolve"),
    },
    null,
  );
  assert.equal(resolved.results.at(-1).status, "sent", JSON.stringify(resolved.results));
  assert.equal(readJson(fixture.configPath).resolved, true);
  assert.equal(readJson(fixture.configPath).publishedNotes.length, 1);
});

test("public guided CLI completes the same contract without low-level staging commands", async (t) => {
  const fixture = reviewFixture(t, { resolved: true });
  const cli = new URL("../dist/cli.js", import.meta.url).pathname;
  const run = (...args) => {
    const execution = spawnSync(process.execPath, [cli, ...args, "--json"], {
      encoding: "utf8",
      env: process.env,
    });
    assert.equal(execution.status, 0, execution.stderr + execution.stdout);
    return JSON.parse(execution.stdout);
  };
  const result = run("start-review", "--url", fixture.url, "--repo-root", fixture.repo);
  writeJson(result.draft_path, await completeDraft(readJson(result.draft_path), result));
  assert.equal(run("check-review", "--draft", result.draft_path).status, "ok");
  const finished = run("finish-review", "--draft", result.draft_path);
  assert.match(finished.chat, /runbook\.md/);
  assert.ok(!finished.chat.includes("undefined"));
});

test("fast, unchanged, and incremental modes keep their original critic and baseline rules", async (t) => {
  const fixture = reviewFixture(t, { resolved: true });
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo, reviewMode: "fast" });
  const fast = await completeDraft(readJson(first.draft_path), first);
  fast.critics = [];
  writeJson(first.draft_path, fast);
  assert.match(JSON.stringify((await checkReview(first.draft_path)).errors), /low-risk/);
  fast.low_risk = true;
  writeJson(first.draft_path, fast);
  assert.equal((await finishReview(first.draft_path)).status, "ok");
  const same = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(same.mode, "unchanged");
  const unchanged = await completeDraft(readJson(same.draft_path), same);
  unchanged.critics = [];
  writeJson(same.draft_path, unchanged);
  assert.equal((await finishReview(same.draft_path)).status, "ok");
  writeFileSync(join(fixture.repo, "review.txt"), "base\nreviewed change\nnew correction\n");
  fixture.git("commit", "-qam", "correction");
  writeFileSync(
    fixture.configPath,
    JSON.stringify({ ...fixture.config, headSha: fixture.git("rev-parse", "HEAD") }),
  );
  const changed = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(changed.mode, "incremental");
  assert.equal(typeof changed.critic_receipt_template.scope_digest, "string");
  const incremental = await completeDraft(readJson(changed.draft_path), changed);
  writeJson(changed.draft_path, incremental);
  const checked = await checkReview(changed.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal((await finishReview(changed.draft_path)).status, "ok");
});

test("publication errors are repairable in the same draft before any decision is frozen", async (t) => {
  const fixture = reviewFixture(t, { resolved: true });
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const draft = await completeDraft(readJson(result.draft_path), result);
  draft.findings = [
    {
      id: "primary-1",
      severity: "low",
      summary: "The correction needs a line",
      risk: "The old line remains.",
      evidence: [`The reviewed revision is ${fixture.headSha}.`],
      consequence: "The path remains incorrect.",
      relation_to_change: "This path is changed.",
      minimum_fix: "Correct the line.",
    },
  ];
  draft.dispositions = [
    {
      id: "primary-1",
      decision: "accept",
      reason: "Confirmed in the exact diff.",
      dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
    },
  ];
  draft.content.finding_publications = [
    {
      finding_id: "primary-1",
      type: "line",
      path: "review.txt",
      line: 2,
      old_line: null,
      body: "Correct the line.\n\n```suggestion\nbounded change\n```",
      fix_mode: "suggestion",
      patch: null,
    },
  ];
  draft.findings[0].summary += ` ${fixture.headSha.slice(0, 8)}`;
  writeJson(result.draft_path, draft);
  const invalid = await checkReview(result.draft_path);
  assert.equal(invalid.status, "invalid");
  assert.ok(
    invalid.errors.some((item) => /raw commit SHA/.test(item.message)),
    JSON.stringify(invalid.errors),
  );
  assert.equal(existsSync(join(result.artifact_root, "artifacts", "review_decision")), false);
  draft.findings[0].summary = "The correction needs a line";
  draft.findings[0].evidence = [
    "The exact changed line was inspected in the bound private evidence.",
  ];
  writeJson(result.draft_path, draft);
  const repaired = await checkReview(result.draft_path);
  assert.equal(repaired.status, "ok", JSON.stringify(repaired.errors));
  draft.content.chat_assessment.change += ` ${fixture.headSha.slice(0, 8)}`;
  writeJson(result.draft_path, draft);
  const invalidChat = await checkReview(result.draft_path);
  assert.equal(invalidChat.status, "invalid");
  assert.ok(invalidChat.errors.some((item) => item.path === "$.content.chat_assessment.change"));
  draft.content.chat_assessment.change = "The correction preserves the agreed behavior.";
  writeJson(result.draft_path, draft);
  const completed = await finishReview(result.draft_path);
  assert.equal(completed.status, "ok");
  const [, plan] = artifactPayload(completed.artifact_path, "review_plan");
  assert.equal(plan.thread_decisions[0].outcome, "no_publication");
  const thread = planItems(loadPlan(result.artifact_root)).find((item) => item.kind === "thread");
  assert.equal(thread.actions.length, 0);
  assert.match(itemText(thread), /Retry needs an idempotency key/);
  assert.match(itemText(thread), /No publication is proposed/);
});

test("chosen critic count, independent identities, and local finalization remain enforced", async (t) => {
  const fixture = reviewFixture(t);
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const draft = await completeDraft(readJson(result.draft_path), result);
  draft.critic_count = 2;
  writeJson(result.draft_path, draft);
  assert.match(JSON.stringify((await checkReview(result.draft_path)).errors), /critic_count/);
  draft.critics.push({ ...draft.critics[0], run_id: "critic-2", session_id: "child-2" });
  const candidate = {
    severity: "low",
    summary: "A related path needs separate documentation",
    risk: "Readers can miss the separate policy.",
    evidence: ["The existing related behavior was inspected."],
    consequence: "Operators can select an unsuitable policy.",
    relation_to_change: "The related policy is outside this change.",
    minimum_fix: "Document the policy separately.",
  };
  draft.critics[0].findings = [{ ...candidate, id: "critic-a-policy" }];
  draft.critics[1].findings = [
    {
      ...candidate,
      id: "critic-b-policy",
      summary: "A different related path needs separate documentation",
    },
  ];
  draft.dispositions = draft.critics
    .flatMap((receipt) => receipt.findings)
    .map((finding) => ({
      id: finding.id,
      decision: "reject",
      reason: "The policy is outside this MR and remains separately tracked.",
      dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
    }));
  writeJson(result.draft_path, draft);
  assert.equal((await checkReview(result.draft_path)).status, "ok");
  draft.critics[1].session_id = draft.session_id;
  writeJson(result.draft_path, draft);
  assert.match(JSON.stringify((await checkReview(result.draft_path)).errors), /identity/);
  draft.critics[1].session_id = "child-2";
  writeJson(result.draft_path, draft);
  writeFileSync(
    fixture.configPath,
    JSON.stringify({ ...fixture.config, noteBody: "The conversation changed after inspection" }),
  );
  const requests = fixture.requestCount();
  // Finalization is local: even when GitLab changed after inspection, the
  // plan stays bound to the reviewed evidence and no final GitLab request
  // runs. Drift is caught by the head check that guards every manual
  // publication block and by an explicit refresh-review.
  const final = await finishReview(result.draft_path);
  assert.equal(final.status, "ok", JSON.stringify(final));
  assert.equal(fixture.requestCount(), requests);
  assert.match(readFileSync(final.markdown_path, "utf8"), /current_head=\$\(glab api/);
  writeFileSync(fixture.configPath, JSON.stringify(fixture.config));
  const receiptPath = loadProgress(result.artifact_root).critic_receipt_path;
  const [, receipt] = artifactPayload(receiptPath, "critic_receipt");
  assert.deepEqual(
    receipt.contributors.map((item) => item.session_id),
    ["child-session", "child-2"],
  );
  assert.deepEqual(
    receipt.findings.map((item) => item.id),
    ["critic-a-policy", "critic-b-policy"],
  );
  const [, plan] = artifactPayload(final.artifact_path, "review_plan");
  assert.equal(plan.rejected_candidates.length, 2);
  assert.ok(plan.rejected_candidates.every((item) => item.paths.includes("review.txt")));
});
