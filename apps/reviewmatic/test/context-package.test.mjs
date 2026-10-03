import assert from "node:assert/strict";
import {
  mkdirSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { artifactPayload, readJson, writeArtifact, writeJson } from "../dist/contract.js";
import {
  checkReview,
  finishReview,
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

// Builds a critic answer bound to the meaningful-context version of the
// package currently recorded for the draft, the way a real critic copies the
// question's context_digest from its primary context.
function boundAnswer(draft, questionId, extra = {}) {
  const [, payload] = artifactPayload(draft.context_package_path, "context_package");
  const question = (payload.questions ?? []).find((item) => item.id === questionId);
  assert.ok(question, `question ${questionId} is not in the recorded package`);
  return {
    question_id: questionId,
    verdict: "confirmed",
    evidence: "Inspected the exact head.",
    context_digest: question.context_digest,
    ...extra,
  };
}

function boundVerification(draft, questionId, extra = {}) {
  const verification = {
    question_id: questionId,
    original: { run_id: "critic-run", session_id: "child-session", verdict: "not_verified" },
    verdict: "confirmed",
    evidence: "Inspected the exact head.",
    context_digest: boundAnswer(draft, questionId).context_digest,
    ...extra,
  };
  if (verification.evidence === undefined) delete verification.evidence;
  return verification;
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
        boundAnswer(draft, "q-retry", {
          evidence: "The exact head sets the key before write.",
        }),
      ],
    },
    {
      ...draft.critics[0],
      run_id: "critic-run-2",
      session_id: "critic-session-2",
      question_answers: [
        boundAnswer(draft, "q-retry", {
          verdict: "refuted",
          evidence: "The exact head leaves the write unkeyed.",
        }),
      ],
    },
    {
      ...draft.critics[0],
      run_id: "critic-run-3",
      session_id: "critic-session-3",
      question_answers: [
        boundAnswer(draft, "q-retry", {
          verdict: "not_verified",
          reason: "Could not trace the retry caller in the exact head.",
        }),
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
    boundVerification(verified, "q-retry", {
      original: { run_id: "critic-run-3", session_id: "critic-session-3", verdict: "not_verified" },
      verdict: "unresolved",
      evidence: undefined,
      reason: "No reachable retry caller exists in the exact head; the doubt stays explicit.",
    }),
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
    boundVerification(answered, "q-fast", {
      original: { run_id: "primary-run", session_id: "primary-session", verdict: "not_verified" },
      evidence: "The diff bounds one retry write with a concrete key.",
    }),
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
  const version = recorded.question_context_versions["q-renderer"];
  assert.ok(version, "recording reports the meaningful-context version per question");

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
      context_digest: version,
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
      question_answers: [boundAnswer(draft, "q-retry")],
    },
    { ...draft.critics[0], run_id: "critic-run-2", session_id: "critic-session-2" },
  ];
  writeJson(started.draft_path, draft);
  const missing = await checkReview(started.draft_path);
  assert.equal(missing.status, "invalid");
  assert.match(JSON.stringify(missing.errors), /critic-run-2\/critic-session-2 did not answer/);

  draft.critics[1].question_answers = [
    boundAnswer(draft, "q-retry", { evidence: "Independent read confirms the keyed write." }),
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
    boundAnswer(draft, "q-retry", { evidence: "Inspected idempotency key." }),
  ];
  writeJson(started.draft_path, draft);
  const before = await checkReview(started.draft_path);
  assert.equal(before.status, "ok", JSON.stringify(before.errors));
  const v1Answer = draft.critics[0].question_answers[0];

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
  assert.equal(
    history.answers[0].context_digest,
    v1Answer.context_digest,
    "history keeps the binding the answer was collected under",
  );

  const stale = await checkReview(started.draft_path);
  assert.equal(stale.status, "invalid");
  assert.match(JSON.stringify(stale.errors), /superseded context package/);

  updated.critics[0].question_answers = [
    boundAnswer(updated, "q-retry", { evidence: "Traced the revocation path in the exact head." }),
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
  const stillValid = await checkReview(started.draft_path);
  assert.equal(stillValid.status, "ok", JSON.stringify(stillValid.errors));
});

test("a late answer for the previous package cannot certify the changed question", async (t) => {
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
  // A real background critic can finish after the primary records a changed
  // package: the receipt is still on its way when the supersession happens.
  const pendingV1 = {
    ...draft.critics[0],
    question_answers: [
      boundAnswer(draft, "q-retry", {
        evidence: "Inspected the idempotency key only, before the package changed.",
      }),
    ],
  };
  draft.critics = [];
  writeJson(started.draft_path, draft);
  const v1 = draft.context_package_digest;
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = v1;
  template.questions = [
    {
      id: "q-retry",
      subject: "Is credential revocation enforced when a key is reused?",
      source: "Discussion 42 of the collected evidence",
      critic: true,
    },
  ];
  writeJson(started.context_package.template_path, template);
  const recorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.deepEqual(
    recorded.superseded_questions,
    [],
    "nothing was attached when the package changed",
  );

  // The late V1 receipt arrives and is added to the current draft unchanged.
  const updated = readJson(started.draft_path, "draft");
  updated.critics = [pendingV1];
  writeJson(started.draft_path, updated);
  const checked = await checkReview(started.draft_path);
  assert.equal(checked.status, "invalid", "the stale V1 receipt was accepted for V2");
  assert.match(JSON.stringify(checked.errors), /is bound to context digest/);
  assert.match(JSON.stringify(checked.errors), /q-retry/);
  const finished = await finishReview(started.draft_path);
  assert.equal(finished.status, "invalid", "finalization refused the stale receipt");
  assert.equal(finished.artifact_path, undefined);

  // Recovery: archive the late answer with its original binding and authorship,
  // then answer the current question with a freshly bound receipt.
  updated.superseded_question_results = [
    {
      context_digest: pendingV1.question_answers[0].context_digest,
      package_digest: v1,
      answers: [
        {
          ...pendingV1.question_answers[0],
          run_id: pendingV1.run_id,
          session_id: pendingV1.session_id,
        },
      ],
      verifications: [],
    },
  ];
  updated.critics = [
    {
      ...pendingV1,
      question_answers: [
        boundAnswer(updated, "q-retry", {
          evidence: "Traced the revocation path in the exact head.",
        }),
      ],
    },
  ];
  writeJson(started.draft_path, updated);
  const recovered = await checkReview(started.draft_path);
  assert.equal(recovered.status, "ok", JSON.stringify(recovered.errors));
  const done = await finishReview(started.draft_path);
  assert.equal(done.status, "ok", JSON.stringify(done));
  const finalDraft = readJson(started.draft_path, "draft");
  assert.equal(finalDraft.superseded_question_results.length, 1, "history is retained");
  assert.equal(finalDraft.superseded_question_results[0].answers[0].run_id, "critic-run");
  assert.notEqual(
    finalDraft.superseded_question_results[0].answers[0].context_digest,
    finalDraft.critics[0].question_answers[0].context_digest,
  );
});

test("an answer without a context binding is retired by re-recording, never counted", async (t) => {
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
      evidence: "Collected before binding existed.",
    },
  ];
  writeJson(started.draft_path, draft);
  const unbound = await checkReview(started.draft_path);
  assert.equal(unbound.status, "invalid");
  assert.match(JSON.stringify(unbound.errors), /has no context binding/);

  // Re-recording the current package retires the unbound result into history.
  const recorded = readJson(started.draft_path, "draft").context_package_digest;
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = recorded;
  writeJson(started.context_package.template_path, template);
  const rerecorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.deepEqual(rerecorded.superseded_questions, ["q-retry"]);
  const updated = readJson(started.draft_path, "draft");
  assert.deepEqual(updated.critics[0].question_answers, []);
  assert.equal(updated.superseded_question_results.length, 1);
  assert.equal(
    updated.superseded_question_results[0].answers[0].evidence,
    "Collected before binding existed.",
  );

  const demanded = await checkReview(started.draft_path);
  assert.equal(demanded.status, "invalid");
  assert.match(JSON.stringify(demanded.errors), /superseded context package/);

  updated.critics[0].question_answers = [boundAnswer(updated, "q-retry")];
  writeJson(started.draft_path, updated);
  const recovered = await checkReview(started.draft_path);
  assert.equal(recovered.status, "ok", JSON.stringify(recovered.errors));
  assert.equal(readJson(started.draft_path, "draft").superseded_question_results.length, 1);
});

test("re-recording an edited question keeps answers for unaffected questions", async (t) => {
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
      {
        id: "q-caller",
        subject: "Do existing callers pass a stable key?",
        source: "Primary inspection of the retry callers",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  draft.critics[0].question_answers = [
    boundAnswer(draft, "q-retry", { evidence: "Inspected idempotency key." }),
    boundAnswer(draft, "q-caller", { evidence: "Both callers build the key from the request." }),
  ];
  writeJson(started.draft_path, draft);
  const before = await checkReview(started.draft_path);
  assert.equal(before.status, "ok", JSON.stringify(before.errors));
  const unaffected = draft.critics[0].question_answers[1];

  const recorded = readJson(started.draft_path, "draft").context_package_digest;
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = recorded;
  template.questions[0].subject = "Is credential revocation enforced when a key is reused?";
  writeJson(started.context_package.template_path, template);
  const rerecorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.deepEqual(rerecorded.superseded_questions, ["q-retry"]);

  const updated = readJson(started.draft_path, "draft");
  assert.deepEqual(updated.critics[0].question_answers, [unaffected]);
  const stale = await checkReview(started.draft_path);
  assert.equal(stale.status, "invalid");
  assert.match(JSON.stringify(stale.errors), /superseded context package/);

  updated.critics[0].question_answers = [
    ...updated.critics[0].question_answers,
    boundAnswer(updated, "q-retry", { evidence: "Traced the revocation path." }),
  ];
  writeJson(started.draft_path, updated);
  const fresh = await checkReview(started.draft_path);
  assert.equal(fresh.status, "ok", JSON.stringify(fresh.errors));
  assert.equal(
    readJson(started.draft_path, "draft").critics[0].question_answers[0].context_digest,
    unaffected.context_digest,
    "the unaffected answer keeps its original binding",
  );
});

test("a significant prior decision change supersedes answers for the same question", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  templateWith(started, {
    prior_decisions: [
      {
        id: "scope-deferral",
        decision: "Credential revocation is deferred; this review checks idempotency only.",
        source: "Earlier user decision in the supplied conversation.",
      },
    ],
    questions: [
      {
        id: "q-stable",
        subject: "Does retry satisfy the agreed safety boundary?",
        source: "Isolated test conversation",
        critic: true,
      },
    ],
  });
  const draft = await completeDraft(readJson(started.draft_path), started);
  const v1Answer = boundAnswer(draft, "q-stable", {
    evidence: "Checked idempotency under the originally agreed boundary.",
  });
  const v1Version = v1Answer.context_digest;
  writeJson(started.draft_path, draft);

  // The user withdraws the exception. The question keeps its ID and subject;
  // the significant agreed decision still changes the version it depends on.
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = readJson(started.draft_path, "draft").context_package_digest;
  template.prior_decisions.push({
    id: "scope-correction",
    decision: "The deferral is withdrawn; credential revocation is required in this review.",
    source: "Explicit later user correction in the supplied conversation.",
  });
  writeJson(started.context_package.template_path, template);
  const v2 = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(v2.superseded_questions, []);
  assert.notEqual(
    v2.question_context_versions["q-stable"],
    v1Version,
    "the agreed decision change moves the question version",
  );

  // The late V1 answer arrives with its original binding and cannot close V2.
  const updated = readJson(started.draft_path, "draft");
  const { run_id: _run, session_id: _session, ...lateAnswer } = v1Answer;
  updated.critics[0].question_answers = [lateAnswer];
  writeJson(started.draft_path, updated);
  const checked = await checkReview(started.draft_path);
  assert.equal(checked.status, "invalid");
  assert.match(JSON.stringify(checked.errors), /is bound to context digest/);
  const finished = await finishReview(started.draft_path);
  assert.equal(finished.status, "invalid", "the stale answer must not finalize to ready");
  assert.equal(finished.artifact_path, undefined);

  // Documented recovery: re-record the current package; the stale answer moves
  // to history with its authorship and the binding it was collected under.
  template.supersedes = v2.digest;
  writeJson(started.context_package.template_path, template);
  const v3 = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(v3.superseded_questions, ["q-stable"]);
  const recovered = readJson(started.draft_path, "draft");
  assert.deepEqual(recovered.critics[0].question_answers, []);
  assert.equal(recovered.superseded_question_results.length, 1);
  const history = recovered.superseded_question_results[0];
  assert.equal(history.answers.length, 1);
  assert.equal(history.answers[0].evidence, v1Answer.evidence);
  assert.equal(history.answers[0].run_id, "critic-run");
  assert.equal(history.answers[0].session_id, "child-session");
  assert.equal(history.answers[0].context_digest, v1Version);

  const demanded = await checkReview(started.draft_path);
  assert.equal(demanded.status, "invalid");
  assert.match(JSON.stringify(demanded.errors), /superseded context package/);

  // A fresh bound answer finalizes; the finalized receipt carries only the
  // complete fresh evidence, never the retired one.
  recovered.critics[0].question_answers = [
    boundAnswer(recovered, "q-stable", {
      evidence: "Traced credential revocation under the corrected scope.",
    }),
  ];
  writeJson(started.draft_path, recovered);
  const done = await finishReview(started.draft_path);
  assert.equal(done.status, "ok", JSON.stringify(done));
  const [, receipt] = artifactPayload(
    join(
      started.artifact_root,
      "artifacts",
      "critic_receipt",
      readdirSync(join(started.artifact_root, "artifacts", "critic_receipt"))[0],
    ),
    "critic_receipt",
  );
  assert.equal(receipt.question_answers.length, 1);
  assert.equal(
    receipt.question_answers[0].evidence,
    "Traced credential revocation under the corrected scope.",
  );
  assert.equal(
    receipt.question_answers[0].context_digest,
    v3.question_context_versions["q-stable"],
  );
  const finalDraft = readJson(started.draft_path, "draft");
  assert.equal(finalDraft.superseded_question_results.length, 1, "history is retained");
});

test("mixed-version recovery keeps fresh results and retires only the stale entry", async (t) => {
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
    boundAnswer(draft, "q-retry", { evidence: "Critic A inspected the idempotency key under V1." }),
  ];
  writeJson(started.draft_path, draft);

  // The subject changes under the stable ID; critic A's V1 answer retires.
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = readJson(started.draft_path, "draft").context_package_digest;
  template.questions[0].subject = "Is credential revocation enforced when a key is reused?";
  writeJson(started.context_package.template_path, template);
  const v2 = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(v2.superseded_questions, ["q-retry"]);

  // Critic B already returns a fresh V2 answer that the primary targets.
  const updated = readJson(started.draft_path, "draft");
  const v1Version = updated.superseded_question_results[0].answers[0].context_digest;
  const freshAnswer = boundAnswer(updated, "q-retry", {
    verdict: "not_verified",
    evidence: undefined,
    reason: "Critic B could not trace the revocation path in time.",
  });
  delete freshAnswer.evidence;
  const freshVerification = boundVerification(updated, "q-retry", {
    original: { run_id: "critic-run-b", session_id: "critic-session-b", verdict: "not_verified" },
    evidence: "Primary traced the revocation path in the exact head.",
  });
  updated.critics = [
    updated.critics[0],
    {
      ...updated.critics[0],
      run_id: "critic-run-b",
      session_id: "critic-session-b",
      question_answers: [freshAnswer],
    },
  ];
  updated.critic_count = 2;
  updated.question_verifications = [freshVerification];
  writeJson(started.draft_path, updated);

  // The late V1 answer from critic A arrives on top.
  updated.critics[0].question_answers = [
    {
      question_id: "q-retry",
      verdict: "confirmed",
      evidence: "Critic A inspected the idempotency key under V1, late.",
      context_digest: v1Version,
    },
  ];
  writeJson(started.draft_path, updated);

  // Documented recovery: re-record the current package.
  template.supersedes = v2.digest;
  writeJson(started.context_package.template_path, template);
  const v3 = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(v3.superseded_questions, ["q-retry"]);

  const after = readJson(started.draft_path, "draft");
  assert.deepEqual(
    after.critics[0].question_answers,
    [],
    "only critic A's stale late answer leaves the active results",
  );
  assert.deepEqual(after.critics[1].question_answers, [freshAnswer], "critic B's answer is intact");
  assert.deepEqual(after.question_verifications, [freshVerification]);
  assert.equal(after.superseded_question_results.length, 2);
  const lateHistory = after.superseded_question_results[1];
  assert.deepEqual(
    lateHistory.answers.map((item) => item.evidence),
    ["Critic A inspected the idempotency key under V1, late."],
  );
  assert.equal(lateHistory.answers[0].run_id, "critic-run");
  assert.equal(lateHistory.answers[0].session_id, "child-session");
  assert.equal(lateHistory.answers[0].context_digest, v1Version);
  assert.deepEqual(lateHistory.verifications, []);

  // A repeated recovery neither duplicates history nor drops fresh results.
  template.supersedes = v3.digest;
  template.background = "Presentation-only narrative revision.";
  writeJson(started.context_package.template_path, template);
  const v4 = await recordDraftPackage(started.draft_path, started.context_package.template_path);
  assert.deepEqual(v4.superseded_questions, []);
  const stable = readJson(started.draft_path, "draft");
  assert.equal(stable.superseded_question_results.length, 2);
  assert.deepEqual(stable.critics[1].question_answers, [freshAnswer]);
  assert.deepEqual(stable.question_verifications, [freshVerification]);

  // Critic A still owes a fresh answer for the assigned question; the retired
  // V1 answer never counts as the required current one.
  const demanded = await checkReview(started.draft_path);
  assert.equal(demanded.status, "invalid");
  assert.match(JSON.stringify(demanded.errors), /critic-run\/child-session did not answer/);

  stable.critics[0].question_answers = [
    boundAnswer(stable, "q-retry", { evidence: "Critic A traced revocation under V2." }),
  ];
  writeJson(started.draft_path, stable);
  const done = await finishReview(started.draft_path);
  assert.equal(done.status, "ok", JSON.stringify(done));
  const [, receipt] = artifactPayload(
    join(
      started.artifact_root,
      "artifacts",
      "critic_receipt",
      readdirSync(join(started.artifact_root, "artifacts", "critic_receipt"))[0],
    ),
    "critic_receipt",
  );
  const receiptEvidence = receipt.question_answers.map((item) => item.evidence);
  assert.ok(
    receiptEvidence.includes("Critic A traced revocation under V2."),
    "the finalized receipt carries the fresh answers",
  );
  assert.ok(
    !receiptEvidence.some(
      (evidence) => typeof evidence === "string" && evidence.includes("under V1"),
    ),
    "the retired stale evidence never ships as an active answer",
  );
  assert.equal(
    readJson(started.draft_path, "draft").superseded_question_results.length,
    2,
    "history is retained after finalization",
  );
});

test("primary verifications follow their question's context version", async (t) => {
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
  draft.question_verifications = [boundVerification(draft, "q-fast")];
  writeJson(started.draft_path, draft);
  const before = await checkReview(started.draft_path);
  assert.equal(before.status, "ok", JSON.stringify(before.errors));
  const originalVerification = draft.question_verifications[0];

  // A verification attached when the question changes retires into history.
  const v1 = draft.context_package_digest;
  const template = readJson(started.context_package.template_path, "template");
  template.supersedes = v1;
  template.questions[0].subject = "Is the fast scope free of blocking findings?";
  writeJson(started.context_package.template_path, template);
  const recorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.deepEqual(recorded.superseded_questions, ["q-fast"]);
  const updated = readJson(started.draft_path, "draft");
  assert.deepEqual(updated.question_verifications, []);
  assert.equal(updated.superseded_question_results[0].verifications.length, 1);
  assert.equal(
    updated.superseded_question_results[0].verifications[0].context_digest,
    originalVerification.context_digest,
    "history keeps the binding the verification was performed under",
  );

  // A late verification still bound to the previous version is rejected.
  updated.question_verifications = [boundVerification(draft, "q-fast")];
  writeJson(started.draft_path, updated);
  const late = await checkReview(started.draft_path);
  assert.equal(late.status, "invalid");
  assert.match(JSON.stringify(late.errors), /is bound to context digest/);

  updated.question_verifications = [boundVerification(updated, "q-fast")];
  writeJson(started.draft_path, updated);
  const fresh = await checkReview(started.draft_path);
  assert.equal(fresh.status, "ok", JSON.stringify(fresh.errors));
  assert.equal(readJson(started.draft_path, "draft").superseded_question_results.length, 1);
});
