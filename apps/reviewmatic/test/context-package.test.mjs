import assert from "node:assert/strict";
import { mkdirSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { readJson, writeArtifact, writeJson } from "../dist/contract.js";
import {
  checkReview,
  recordDraftPackage,
  refreshReview,
  resumeReview,
  startReview,
} from "../dist/draft.js";
import {
  finalizeLocal,
  localBundle,
  prepareFollowup,
  recordLocalPackage,
  recordReview,
} from "../dist/local-review.js";
import { completeDraft, reviewFixture } from "./helpers/review-fixture.mjs";

function templateWith(started, edits = {}) {
  const template = readJson(started.context_package.template_path, "template");
  template.goal = { status: "known", text: "Bound the retry write behind an idempotency key." };
  template.acceptance_criteria = { status: "unknown", items: [] };
  for (const item of template.thread_registry ?? []) {
    item.summary = "A reviewer remarked on the retry path.";
    item.review_relevance = "The change touches this path; the remark is assessed directly.";
  }
  Object.assign(template, edits);
  writeJson(started.context_package.template_path, template);
  return template;
}

function pristineTemplate(started) {
  return structuredClone(readJson(started.context_package.template_path, "template"));
}

function writeTemplate(started, base, edits = {}) {
  const template = structuredClone(base);
  template.goal = { status: "known", text: "Bound the retry write behind an idempotency key." };
  template.acceptance_criteria = { status: "unknown", items: [] };
  for (const item of template.thread_registry ?? []) {
    item.summary = "A reviewer remarked on the retry path.";
    item.review_relevance = "The change touches this path; the remark is assessed directly.";
  }
  Object.assign(template, edits);
  writeJson(started.context_package.template_path, template);
  return recordDraftPackage(started.draft_path, started.context_package.template_path);
}

test("the MR package template exposes every collected thread and records with bindings", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(started.context_package.status, "pending");
  assert.equal(started.critic_task.context_package_path, null);
  const template = readJson(started.context_package.template_path, "template");
  assert.equal(template.schema, "portable-gitlab/context-package/v2");
  assert.deepEqual(template.goal, { status: "unknown" });
  assert.deepEqual(template.acceptance_criteria, { status: "unknown", items: [] });
  assert.equal(template.thread_registry.length, 1);
  assert.equal(template.thread_registry[0].id, "42");
  assert.equal(template.thread_registry[0].summary, "");
  assert.match(started.critic_task.instructions, /context package/);
  assert.match(started.context_package.record_command, /record-package --draft/);

  const requestsBefore = fixture.requestCount();
  const recorded = await writeTemplate(started, pristineTemplate(started));
  assert.equal(fixture.requestCount(), requestsBefore, "recording never contacts GitLab");
  assert.equal(recorded.status, "ok");
  assert.ok(recorded.digest);
  assert.ok(existsSync(recorded.artifact_path));
  assert.ok(recorded.artifact_path.startsWith(`${started.artifact_root}/artifacts/`));
  assert.ok(
    !recorded.artifact_path.startsWith(fixture.repo),
    "the package stays outside the checkout",
  );
  assert.equal(template.thread_registry.length, recorded.thread_registry_size);

  const resumed = await resumeReview(started.artifact_root);
  assert.equal(resumed.context_package.status, "recorded");
  assert.equal(resumed.context_package.package_digest, recorded.digest);
  assert.equal(resumed.critic_task.context_package_path, recorded.artifact_path);
});

test("a dropped thread blocks recording and answers keep critic authorship", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const base = pristineTemplate(started);
  await assert.rejects(
    writeTemplate(started, base, { thread_registry: [] }),
    /missing collected threads/,
  );
  await assert.rejects(
    writeTemplate(started, base, {
      claims: [
        {
          id: "claim-a",
          kind: "author_claim",
          statement: "s",
          sources: ["MR description"],
          disputed_by: ["claim-z"],
        },
      ],
    }),
    /disputes unknown claim/,
  );

  await writeTemplate(started, base, {
    claims: [
      {
        id: "claim-description",
        kind: "author_claim",
        statement: "The description says the retry is already safe.",
        sources: ["MR description section 'Behavior'"],
      },
      {
        id: "claim-agreed",
        kind: "agreed_requirement",
        statement: "Retries must stay idempotent.",
        sources: ["Discussion 42 reviewer request"],
        disputed_by: ["claim-description"],
      },
    ],
    questions: [
      {
        id: "q-retry",
        subject: "Does the exact head always set the idempotency key?",
        source: "Discussion 42 of the collected evidence",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  draft.critic_count = 3;
  draft.critics = [
    {
      ...draft.critics[0],
      run_id: "critic-run-1",
      session_id: "critic-session-1",
      question_answers: [
        {
          question_id: "q-retry",
          verdict: "confirmed",
          evidence: "The exact head sets the key before write.",
        },
      ],
    },
    {
      ...draft.critics[0],
      run_id: "critic-run-2",
      session_id: "critic-session-2",
      question_answers: [
        {
          question_id: "q-retry",
          verdict: "refuted",
          evidence: "The exact head leaves the write unkeyed.",
        },
      ],
    },
    {
      ...draft.critics[0],
      run_id: "critic-run-3",
      session_id: "critic-session-3",
      question_answers: [
        {
          question_id: "q-retry",
          verdict: "not_verified",
          reason: "Could not trace the retry caller in the exact head.",
        },
      ],
    },
  ];
  writeJson(started.draft_path, draft);

  const unverified = await checkReview(started.draft_path);
  assert.equal(unverified.status, "invalid");
  assert.match(
    JSON.stringify(unverified.errors),
    /question_verifications entry that preserves the original answer/,
  );

  const verified = readJson(started.draft_path, "draft");
  verified.question_verifications = [
    {
      question_id: "q-retry",
      original: { run_id: "critic-run-3", session_id: "critic-session-3", verdict: "not_verified" },
      verdict: "unresolved",
      reason: "No reachable retry caller exists in the exact head; the doubt stays explicit.",
    },
  ];
  writeJson(started.draft_path, verified);
  const ok = await checkReview(started.draft_path);
  assert.equal(ok.status, "ok");
  assert.equal(ok.question_status.contradicted, 1);
  assert.equal(ok.question_status.unverified, 1);
  assert.equal(ok.question_status.unresolved, 1);
  assert.equal(ok.question_status.assigned, 1);

  const wrongOriginal = readJson(started.draft_path, "draft");
  wrongOriginal.question_verifications[0].original = {
    run_id: "critic-run-3",
    session_id: "critic-session-3",
    verdict: "confirmed",
  };
  writeJson(started.draft_path, wrongOriginal);
  const rejected = await checkReview(started.draft_path);
  assert.equal(rejected.status, "invalid");
  assert.match(JSON.stringify(rejected.errors), /does not match any retained critic answer/);
});

test("without a critic the primary answers assigned questions itself", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({
    url: fixture.url,
    repoRoot: fixture.repo,
    reviewMode: "fast",
  });
  templateWith(started, {
    questions: [
      {
        id: "q-fast",
        subject: "Is the fast scope really low risk?",
        source: "User request",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  draft.critic_count = 0;
  draft.critics = [];
  draft.low_risk = true;
  writeJson(started.draft_path, draft);
  const missing = await checkReview(started.draft_path);
  assert.equal(missing.status, "invalid");
  assert.match(JSON.stringify(missing.errors), /assigned without a critic/);

  const answered = readJson(started.draft_path, "draft");
  answered.question_verifications = [
    {
      question_id: "q-fast",
      original: { run_id: "primary-run", session_id: "primary-session", verdict: "not_verified" },
      verdict: "confirmed",
      evidence: "The diff bounds one retry write with a concrete key.",
    },
  ];
  writeJson(started.draft_path, answered);
  const ok = await checkReview(started.draft_path);
  assert.equal(ok.status, "ok");
});

test("an unknown goal stays explicit and known claims require text", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const base = pristineTemplate(started);
  const recorded = await writeTemplate(started, base, { goal: { status: "unknown" } });
  assert.equal(recorded.status, "ok");
  await assert.rejects(writeTemplate(started, base, { goal: { status: "known" } }), /goal/);
});

test("editing the background never changes the canonical digest", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const base = pristineTemplate(started);
  const first = await writeTemplate(started, base, {
    background: "Original conversation background.",
  });
  const second = await writeTemplate(started, base, {
    background: "Rewritten narrative, same facts.",
  });
  assert.notEqual(first.digest, second.digest);
  assert.equal(first.canonical_digest, second.canonical_digest);
  assert.notEqual(first.background_digest, second.background_digest);

  const third = await writeTemplate(started, base, { supersedes: second.digest });
  assert.equal(third.status, "ok");
  await assert.rejects(
    writeTemplate(started, base, { supersedes: "0".repeat(64) }),
    /supersedes must name the currently recorded package/,
  );
});

test("refresh reports the previous package and its stale threads", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  await writeTemplate(started, pristineTemplate(started));
  fixture.config.resolved = true;
  writeFileSync(fixture.configPath, JSON.stringify(fixture.config));
  const refreshed = await refreshReview(started.draft_path);
  assert.equal(refreshed.status, "needs_reassessment");
  assert.equal(refreshed.previous_context_package.stale_threads.length, 1);
  assert.match(refreshed.context_package.record_command, /record-package --draft/);
  const next = readJson(refreshed.draft_path, "draft");
  assert.equal(next.context_package_path, null);
  assert.deepEqual(next.question_verifications, []);
});

test("the local package binds the prepared snapshot and gates finalization", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "local-package-"));
  const originalStateHome = process.env.XDG_STATE_HOME;
  t.after(() => {
    process.env.XDG_STATE_HOME = originalStateHome;
    rmSync(root, { recursive: true, force: true });
  });
  process.env.XDG_STATE_HOME = join(root, "state");
  const repo = join(root, "checkout");
  const git = (...args) => {
    const result = spawnSync("git", ["-C", repo, ...args], { encoding: "utf8" });
    assert.equal(result.status, 0, `git ${args.join(" ")} failed: ${result.stderr}`);
    return result.stdout.trim();
  };
  mkdirSync(repo);
  git("init", "--quiet");
  git("config", "commit.gpgsign", "false");
  git("config", "user.email", "test@example.invalid");
  git("config", "user.name", "Test");
  writeFileSync(join(repo, "renderer.txt"), "base\n");
  git("add", ".");
  git("commit", "-qm", "base");
  writeFileSync(join(repo, "renderer.txt"), "broken\n");

  const bundle = await localBundle(repo, "code-review", null);
  const [snapshot, digestValue] = await writeArtifact(
    bundle.artifact_root,
    "local_wip_snapshot",
    bundle,
  );
  const followup = prepareFollowup(bundle.artifact_root, bundle, digestValue, "auto");
  const template = readJson(followup.context_package.template_path, "template");
  assert.equal(template.mode, "local");
  assert.equal(template.binding.sections.committed.length, 64);
  assert.equal(template.binding.ref, null);
  assert.equal(template.thread_registry, undefined);
  assert.deepEqual(template.goal, { status: "unknown" });
  assert.ok(followup.context_package.record_command.includes("record-package --bundle"));

  template.goal = {
    status: "known",
    text: "Link plain text without modifying mixed Markdown.",
  };
  template.acceptance_criteria = { status: "known", items: ["Plain references link."] };
  template.questions = [
    {
      id: "q-renderer",
      subject: "Does the staged renderer change touch protected values?",
      source: "Local conversation with the author",
      critic: true,
    },
  ];
  writeJson(followup.context_package.template_path, template);
  const recorded = await recordLocalPackage(snapshot, followup.context_package.template_path);
  assert.equal(recorded.status, "ok");
  assert.ok(!recorded.artifact_path.startsWith(repo), "the package stays outside the checkout");

  const report = {
    evidence_digest: digestValue,
    previous_review_digest: null,
    mode: "full",
    context_package: null,
    question_answers: [],
    question_verifications: [],
    task: {
      goal: "Link plain text without modifying mixed Markdown.",
      acceptance_criteria: ["Plain references link."],
      constraints: [],
      accepted_risks: [],
      deferred: [],
      decision_evidence: "User chose plain-text linking.",
    },
    task_change_reason: null,
    findings: [],
    checks: [{ name: "renderer", status: "passed", required: true, evidence: "inspected" }],
    assessment: "narrow",
    verdict: "ready",
    external_mutations: false,
  };
  const draft = followup.draft_path;
  const parent = dirname(draft);
  writeJson(draft, report);
  await assert.rejects(
    recordReview(parent, snapshot, draft),
    /must bind the recorded context package/,
  );

  report.context_package = { path: recorded.artifact_path, digest: recorded.digest };
  writeJson(draft, report);
  await assert.rejects(
    recordReview(parent, snapshot, draft),
    /question q-renderer is assigned to critics but no critic answer or primary verification covers it/,
  );

  report.question_verifications = [
    {
      question_id: "q-renderer",
      original: { run_id: "local-primary", session_id: "local-session", verdict: "not_verified" },
      verdict: "confirmed",
      evidence: "The staged diff only rewrites plain text values.",
    },
  ];
  writeJson(draft, report);
  const saved = await recordReview(parent, snapshot, draft);
  assert.equal(saved.verdict, "ready");
  const finalized = await finalizeLocal(snapshot);
  assert.equal(finalized.status, "ok");

  writeFileSync(join(repo, "renderer.txt"), "changed\n");
  const nextBundle = await localBundle(repo, "code-review", null);
  const [nextSnapshot, nextDigest] = await writeArtifact(
    nextBundle.artifact_root,
    "local_wip_snapshot",
    nextBundle,
  );
  assert.notEqual(nextDigest, digestValue);
  const next = prepareFollowup(nextBundle.artifact_root, nextBundle, nextDigest, "auto");
  assert.equal(next.context_package.status, "pending");
  assert.equal(next.context_package.package_path, recorded.artifact_path);
  const staleReport = structuredClone(report);
  staleReport.evidence_digest = nextDigest;
  staleReport.previous_review_digest = saved.digest;
  staleReport.mode = "incremental";
  writeJson(draft, staleReport);
  await assert.rejects(
    recordReview(parent, nextSnapshot, draft),
    /does not bind the selected evidence digest|does not match the prepared snapshot/,
  );
});

test("every selected critic must answer each assigned question", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  templateWith(started, {
    questions: [
      {
        id: "q-retry",
        subject: "Does the exact head always set the idempotency key?",
        source: "Discussion 42 of the collected evidence",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  draft.critic_count = 2;
  draft.critics = [
    {
      ...draft.critics[0],
      run_id: "critic-run-1",
      session_id: "critic-session-1",
      question_answers: [
        {
          question_id: "q-retry",
          verdict: "confirmed",
          evidence: "The exact head sets the key before write.",
        },
      ],
    },
    { ...draft.critics[0], run_id: "critic-run-2", session_id: "critic-session-2" },
  ];
  writeJson(started.draft_path, draft);
  const missing = await checkReview(started.draft_path);
  assert.equal(missing.status, "invalid");
  assert.match(JSON.stringify(missing.errors), /critic-run-2\/critic-session-2 did not answer/);

  draft.critics[1].question_answers = [
    {
      question_id: "q-retry",
      verdict: "confirmed",
      evidence: "Independent read confirms the keyed write.",
    },
  ];
  writeJson(started.draft_path, draft);
  const answered = await checkReview(started.draft_path);
  assert.equal(answered.status, "ok", JSON.stringify(answered.errors));
});

test("an edited question supersedes answers collected for the previous wording", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  templateWith(started, {
    questions: [
      {
        id: "q-retry",
        subject: "Does the exact head always set the idempotency key?",
        source: "Discussion 42 of the collected evidence",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  draft.critics[0].question_answers = [
    {
      question_id: "q-retry",
      verdict: "confirmed",
      evidence: "Inspected idempotency key.",
    },
  ];
  writeJson(started.draft_path, draft);
  const before = await checkReview(started.draft_path);
  assert.equal(before.status, "ok", JSON.stringify(before.errors));

  // The agent changes the question subject under the stable ID and re-records.
  const v1Digest = readJson(started.draft_path, "draft").context_package_digest;
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = v1Digest;
  template.questions = [
    {
      id: "q-retry",
      subject: "Is credential revocation enforced when a key is reused?",
      source: "Discussion 42 of the collected evidence",
      critic: true,
    },
  ];
  writeJson(started.context_package.template_path, template);
  const rerecorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.deepEqual(rerecorded.superseded_questions, ["q-retry"]);

  const updated = readJson(started.draft_path, "draft");
  assert.deepEqual(updated.critics[0].question_answers, []);
  assert.equal(updated.superseded_question_results.length, 1);
  const history = updated.superseded_question_results[0];
  assert.equal(history.package_digest, v1Digest);
  assert.equal(history.answers.length, 1);
  assert.equal(history.answers[0].evidence, "Inspected idempotency key.");
  assert.equal(history.answers[0].run_id, "critic-run");
  assert.equal(history.answers[0].session_id, "child-session");

  const stale = await checkReview(started.draft_path);
  assert.equal(stale.status, "invalid");
  assert.match(JSON.stringify(stale.errors), /superseded context package/);

  updated.critics[0].question_answers = [
    {
      question_id: "q-retry",
      verdict: "confirmed",
      evidence: "Traced the revocation path in the exact head.",
    },
  ];
  writeJson(started.draft_path, updated);
  const fresh = await checkReview(started.draft_path);
  assert.equal(fresh.status, "ok", JSON.stringify(fresh.errors));
  const after = readJson(started.draft_path, "draft");
  assert.equal(after.superseded_question_results.length, 1, "history is retained");

  // A representation-only edit never invalidates collected results.
  const current = readJson(started.draft_path, "draft").context_package_digest;
  const narrative = readJson(started.context_package.template_path, "template");
  narrative.supersedes = current;
  narrative.background = "Rewritten narrative, same facts.";
  writeJson(started.context_package.template_path, narrative);
  const kept = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(kept.superseded_questions, []);
  const finalDraft = readJson(started.draft_path, "draft");
  assert.equal(finalDraft.critics[0].question_answers.length, 1);
  assert.equal(finalDraft.superseded_question_results.length, 1);
});
