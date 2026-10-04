import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  checkReview,
  finishReview,
  recordDraftCritic,
  recordDraftInput,
  recordDraftPackage,
  startReview,
} from "../dist/draft.js";
import { digest, readJson, writeJson } from "../dist/contract.js";
import {
  finalizeLocal,
  localBundle,
  prepareFollowup,
  recordLocalInput,
  recordLocalPackage,
  recordReview,
} from "../dist/local-review.js";
import { scopeForRoot } from "../dist/scope.js";
import { reviewFixture } from "./helpers/review-fixture.mjs";

const cli = new URL("../dist/cli.js", import.meta.url).pathname;

function spawn(args) {
  return spawnSync(process.execPath, [cli, ...args], { encoding: "utf8" });
}

function finding() {
  return {
    id: "primary-retry",
    severity: "low",
    summary: "The retry path repeats a write without an idempotency key.",
    risk: "A retried request can duplicate a side effect.",
    evidence: ["review.txt:2 repeats the write on the retry branch."],
    consequence: "Duplicated writes surface as duplicated records downstream.",
    relation_to_change: "The change touches exactly this retry path.",
    minimum_fix: "Bind the retried write behind an idempotency key.",
  };
}

function receiptResponse(versions) {
  return {
    schema: "portable-gitlab/critic-receipt/v2",
    evidence_digest: null,
    run_id: "critic-run-7",
    session_id: "critic-session-7",
    findings: [
      {
        id: "critic-nit",
        severity: "low",
        summary: "The retry comment wording is ambiguous.",
        risk: "A maintainer may misread the retry contract.",
        evidence: ["review.txt:2 comment says retry loosely."],
        consequence: "Slower future maintenance.",
        relation_to_change: "The comment is part of the change.",
        minimum_fix: "Name the idempotency key in the comment.",
      },
    ],
    question_answers: [
      {
        question_id: "q-idempotency",
        verdict: "confirmed",
        evidence: "The exact head binds writes behind the key.",
        context_digest: versions["q-idempotency"],
      },
    ],
    external_mutations: false,
  };
}

async function preparedReview(t) {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo, locale: "en" });
  assert.equal(started.status, "ok");
  const template = readJson(started.context_package.template_path, "package template");
  template.goal = { status: "known", text: "Bound the retry write behind an idempotency key." };
  template.acceptance_criteria = { status: "unknown", items: [] };
  for (const item of template.thread_registry) {
    item.summary = "A reviewer remarked on the retry path.";
    item.review_relevance = "The change touches this path.";
  }
  template.questions = [
    {
      id: "q-idempotency",
      subject: "Does the exact head bind retried writes behind the idempotency key?",
      source: "Primary inspection of the committed diff.",
      critic: true,
    },
  ];
  writeJson(started.context_package.template_path, template);
  const recorded = await recordDraftPackage(
    started.draft_path,
    started.context_package.template_path,
  );
  assert.equal(recorded.status, "ok");
  return { fixture, started, recorded };
}

test("record-package returns the ready critic task with exact inputs and import contract", async (t) => {
  const { started, recorded } = await preparedReview(t);
  const task = recorded.critic_task;
  assert.equal(task.launch, "now");
  assert.equal(task.context_package.path, recorded.artifact_path);
  assert.equal(task.context_package.digest, recorded.digest);
  assert.match(task.context_package.question_context_versions["q-idempotency"], /^[0-9a-f]{64}$/);
  assert.equal(task.inputs.evidence_path, started.evidence_path);
  assert.equal(task.inputs.context_path, started.context_path);
  assert.equal(task.inputs.inspection_path, started.inspection_path);
  assert.match(task.response_contract.import_command.command, /^reviewmatic record-critic/);
  assert.equal(task.response_contract.template.schema, "portable-gitlab/critic-receipt/v2");
});

test("start-review returns the prepared scope overview with author claims flagged", async (t) => {
  const { fixture, started } = await preparedReview(t);
  const requests = fixture.requestCount();
  const scope = started.scope;
  assert.equal(scope.mode, "mr");
  assert.equal(scope.target.title, "Current merge request title");
  assert.equal(scope.description.source, "author_text");
  assert.equal(scope.description.text, "Current description");
  assert.match(scope.claim_notice, /author or participant claims/);
  assert.deepEqual(scope.changed_files.paths, ["review.txt"]);
  assert.equal(scope.discussions.threads[0].id, "discussion-42");
  assert.equal(scope.discussions.threads[0].position.path, "review.txt");
  assert.equal(scope.completeness.retrieval_complete, true);
  assert.equal(scope.inputs.inspection.diff_path, readJson(started.inspection_path).diff_path);
  assert.equal(scope.inputs.repo_root, started.review_worktree.path);
  assert.equal(fixture.requestCount(), requests);

  const printed = spawn(["scope-review", "--artifact-root", started.artifact_root]);
  assert.equal(printed.status, 0, printed.stderr);
  const emitted = JSON.parse(printed.stdout);
  assert.equal(emitted.status, "ok");
  assert.equal(emitted.scope.mode, "mr");
  assert.equal(emitted.scope.inputs.evidence_path, started.evidence_path);
  assert.equal(fixture.requestCount(), requests);
});

test("record-input applies semantic sections mechanically and preserves machine fields", async (t) => {
  const { started, recorded } = await preparedReview(t);
  const draftPath = started.draft_path;
  const before = readJson(draftPath, "draft");
  const beforeDigest = digest(before);

  const invalid = await recordDraftInput(
    draftPath,
    writeInput(t, {
      unknown_section: [1],
      content: { summary: "", issue_templates: [] },
      findings: [{ id: "broken" }],
    }),
  );
  assert.equal(invalid.status, "invalid");
  const paths = invalid.errors.map((issue) => issue.path);
  assert.ok(paths.includes("$.unknown_section"));
  assert.ok(paths.includes("$.content.issue_templates"));
  assert.ok(paths.includes("$.content.summary"));
  assert.ok(paths.includes("$.findings[0].severity"));
  const envelopePath = writeInput(t, {
    schema: "portable-gitlab/analysis_report/v2",
    payload: { findings: [] },
  });
  await assert.rejects(
    () => recordDraftInput(draftPath, envelopePath),
    /envelope wrapper.*pass the object stored in the payload field/s,
  );
  assert.equal(
    digest(readJson(draftPath, "draft")),
    beforeDigest,
    "failed inputs never touch the draft",
  );

  const first = await recordDraftInput(
    draftPath,
    writeInput(t, {
      run_id: "primary-run-9",
      session_id: "primary-session-9",
      findings: [finding()],
    }),
  );
  assert.equal(first.status, "ok");
  assert.deepEqual(first.applied, {
    run_id: "primary-run-9",
    session_id: "primary-session-9",
    findings: 1,
  });
  assert.deepEqual(first.pending.dispositions_missing_for, ["primary-retry"]);
  const afterFirst = readJson(draftPath, "draft");
  assert.equal(afterFirst.evidence_digest, before.evidence_digest);
  assert.equal(afterFirst.context_package_path, before.context_package_path);
  assert.deepEqual(afterFirst.critics, []);

  const preparedThreads = readJson(draftPath, "draft").content.thread_decisions;
  const threadDecisions = preparedThreads.map((thread) => ({
    id: thread.id,
    assessment: "fixed",
    rationale: "The exact reviewed code already addresses the remark.",
    outcome: thread.state === "resolved" ? "no_publication" : "resolve",
    proposed_response:
      thread.state === "resolved" ? null : "The exact reviewed code now handles this path.",
  }));
  const content = readJson(draftPath, "draft").content;
  const semver = content.semver_assessment;
  semver.policy = "No publication configuration is available.";
  semver.sources = ["Fixture repository and empty release catalog"];
  semver.fallback_reason = "No published release can be established.";
  const second = await recordDraftInput(
    draftPath,
    writeInput(t, {
      dispositions: [
        {
          id: "primary-retry",
          decision: "accept",
          reason: "The exact retry path repeats a write.",
          dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
        },
      ],
      content: {
        summary: "The bounded change meets the agreed contract.",
        architecture_assessment: "Existing ownership is preserved.",
        chat_assessment: {
          necessity: { status: "supported", rationale: "The existing timeout is unbounded." },
          relevance: { status: "current", rationale: "The current runner uses this path." },
          change: "Bound the check.",
        },
        semver_impact: "patch",
        semver_rationale: "Backward-compatible correction.",
        semver_assessment: semver,
        mr_metadata_assessment: Object.fromEntries(
          Object.entries(content.mr_metadata_assessment).map(([key, value]) => [
            key,
            { ...value, status: "ok", rationale: "The observed metadata is sufficient." },
          ]),
        ),
        label_assessments: content.label_assessments.map((item) => ({
          ...item,
          status: item.name === "semver::patch" ? "applicable" : "inapplicable",
          rationale: "Matches the assessed patch contribution.",
        })),
        thread_decisions: threadDecisions,
        checks: ["Inspected the exact committed diff; external tests were not run."],
      },
    }),
  );
  assert.equal(second.status, "ok", JSON.stringify(second.errors));
  assert.deepEqual(second.pending.dispositions_missing_for, []);
  assert.deepEqual(second.pending.identity_missing, []);
  assert.deepEqual(second.pending.context_package, []);
  assert.deepEqual(second.pending.critics_expected, [
    "1 of 1 independent critic receipts are still expected",
  ]);
  assert.equal(second.pending.labels_unresolved, 0);
});

test("record-critic imports a receipt verbatim and rejects stale answers without rebinding", async (t) => {
  const { started, recorded } = await preparedReview(t);
  const draftPath = started.draft_path;
  await recordDraftInput(
    draftPath,
    writeInput(t, {
      run_id: "primary-run-9",
      session_id: "primary-session-9",
      findings: [finding()],
      dispositions: [
        {
          id: "primary-retry",
          decision: "accept",
          reason: "The exact retry path repeats a write.",
          dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
        },
      ],
    }),
  );
  const versions = recorded.question_context_versions;

  const stale = await recordDraftCritic(
    draftPath,
    writeInput(t, {
      ...receiptResponse(versions),
      evidence_digest: readJson(draftPath, "draft").evidence_digest,
      question_answers: [
        {
          question_id: "q-idempotency",
          verdict: "confirmed",
          context_digest: "0".repeat(64),
        },
      ],
    }),
  );
  assert.equal(stale.status, "invalid");
  const staleIssue = stale.errors.find(
    (issue) => issue.path === "$.question_answers[0].context_digest",
  );
  assert.match(staleIssue.message, new RegExp(versions["q-idempotency"]));
  assert.match(staleIssue.message, /Do not rebind an old answer/);
  assert.deepEqual(readJson(draftPath, "draft").critics, []);

  const imported = await recordDraftCritic(
    draftPath,
    writeInput(t, {
      ...receiptResponse(versions),
      evidence_digest: readJson(draftPath, "draft").evidence_digest,
    }),
  );
  assert.equal(imported.status, "ok");
  assert.equal(imported.source_envelope_unwrapped, false);
  assert.deepEqual(imported.pending_critic_questions, []);
  const draft = readJson(draftPath, "draft");
  assert.equal(draft.critics.length, 1);
  assert.equal(
    draft.critics[0].findings[0].summary,
    "The retry comment wording is ambiguous.",
    "critic findings are preserved verbatim",
  );
  assert.equal(draft.critics[0].question_answers[0].context_digest, versions["q-idempotency"]);
  assert.equal(draft.critics[0].run_id, "critic-run-7");
  assert.equal(
    draft.dispositions.length,
    1,
    "the runtime never creates dispositions for critic findings",
  );
  assert.match(imported.dispositions, /record-input/);

  const duplicate = await recordDraftCritic(
    draftPath,
    writeInput(t, {
      ...receiptResponse(versions),
      evidence_digest: readJson(draftPath, "draft").evidence_digest,
      session_id: "critic-session-other",
    }),
  );
  assert.equal(duplicate.status, "invalid");
  assert.ok(
    duplicate.errors.some((issue) => issue.path === "$.findings[0].id"),
    "a colliding critic finding id is named",
  );
});

test("a wrapped review_report envelope is unwrapped mechanically during import", async (t) => {
  const { started, recorded } = await preparedReview(t);
  const draftPath = started.draft_path;
  await recordDraftInput(
    draftPath,
    writeInput(t, {
      run_id: "primary-run-9",
      session_id: "primary-session-9",
    }),
  );
  const imported = await recordDraftCritic(
    draftPath,
    writeInput(t, {
      schema: "portable-gitlab/review_report/v2",
      kind: "review_report",
      payload: {
        ...receiptResponse(recorded.question_context_versions),
        evidence_digest: readJson(draftPath, "draft").evidence_digest,
      },
    }),
  );
  assert.equal(imported.status, "ok", JSON.stringify(imported.errors));
  assert.equal(imported.source_envelope_unwrapped, true);
  assert.equal(readJson(draftPath, "draft").critics.length, 1);
});

test("the new interface completes the full MR cycle without manual machine assembly", async (t) => {
  const { fixture, started, recorded } = await preparedReview(t);
  const draftPath = started.draft_path;
  await recordDraftInput(
    draftPath,
    writeInput(t, {
      run_id: "primary-run-9",
      session_id: "primary-session-9",
      low_risk: false,
      findings: [finding()],
      dispositions: [
        {
          id: "primary-retry",
          decision: "accept",
          reason: "The exact retry path repeats a write.",
          dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
        },
        {
          id: "critic-nit",
          decision: "reject",
          reason: "Wording preference without a concrete consequence; covered by primary-retry.",
          duplicate_of: "primary-retry",
          dependencies: { paths: [], thread_ids: [], metadata_fields: [], ci: false },
        },
      ],
      content: {
        summary: "The bounded change meets the agreed contract.",
        architecture_assessment: "Existing ownership is preserved.",
        chat_assessment: {
          necessity: { status: "supported", rationale: "The existing timeout is unbounded." },
          relevance: { status: "current", rationale: "The current runner uses this path." },
          change: "Bound the check.",
        },
        semver_impact: "patch",
        semver_rationale: "Backward-compatible correction.",
        semver_assessment: (() => {
          const semver = readJson(draftPath, "draft").content.semver_assessment;
          semver.policy = "No publication configuration is available.";
          semver.sources = ["Fixture repository and empty release catalog"];
          semver.fallback_reason = "No published release can be established.";
          return semver;
        })(),
        mr_metadata_assessment: Object.fromEntries(
          Object.entries(readJson(draftPath, "draft").content.mr_metadata_assessment).map(
            ([key, value]) => [
              key,
              { ...value, status: "ok", rationale: "The observed metadata is sufficient." },
            ],
          ),
        ),
        label_assessments: readJson(draftPath, "draft").content.label_assessments.map((item) => ({
          name: item.name,
          status: item.name === "semver::patch" ? "applicable" : "inapplicable",
          rationale: "Matches the assessed patch contribution.",
        })),
        thread_decisions: readJson(draftPath, "draft").content.thread_decisions.map((thread) => ({
          id: thread.id,
          assessment: "fixed",
          rationale: "The exact reviewed code already addresses the remark.",
          outcome: thread.state === "resolved" ? "no_publication" : "resolve",
          proposed_response:
            thread.state === "resolved" ? null : "The exact reviewed code now handles this path.",
        })),
        finding_publications: [
          {
            finding_id: "primary-retry",
            type: "line",
            path: "review.txt",
            line: 2,
            old_line: null,
            body: "Bind the retried write behind the idempotency key.\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
            fix_mode: "suggestion",
            patch: null,
          },
        ],
        checks: ["Inspected the exact committed diff; external tests were not run."],
      },
    }),
  );
  await recordDraftCritic(
    draftPath,
    writeInput(t, {
      ...receiptResponse(recorded.question_context_versions),
      evidence_digest: readJson(draftPath, "draft").evidence_digest,
    }),
  );
  const checked = await checkReview(draftPath);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  const requests = fixture.requestCount();
  const finished = await finishReview(draftPath);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  assert.match(finished.chat, /review/);
  assert.ok(fixture.requestCount() - requests > 0, "one freshness cycle");
  assert.match(readFileSync(finished.markdown_path, "utf8"), /reviewed change|retry/);
});

test("record-input rejects an unwritable shape at the CLI boundary without touching the draft", async (t) => {
  const { started } = await preparedReview(t);
  const before = readFileSync(started.draft_path);
  const broken = spawn([
    "record-input",
    "--draft",
    started.draft_path,
    "--input",
    writeInput(t, { verdict: "ready" }),
  ]);
  assert.equal(broken.status, 2);
  const emitted = JSON.parse(broken.stdout);
  assert.equal(emitted.status, "invalid");
  assert.ok(emitted.errors.some((issue) => issue.path === "$.verdict"));
  assert.deepEqual(readFileSync(started.draft_path), before);
});

test("local record-input completes the prepared template and finalizes without GitLab", async (t) => {
  const { execFileSync } = await import("node:child_process");
  const tmp = mkdtempSync(join(tmpdir(), "reviewmatic-local-input-"));
  const originalStateHome = process.env.XDG_STATE_HOME;
  t.after(() => {
    if (originalStateHome !== undefined) process.env.XDG_STATE_HOME = originalStateHome;
    else delete process.env.XDG_STATE_HOME;
    rmSync(tmp, { recursive: true, force: true });
  });
  process.env.XDG_STATE_HOME = join(tmp, "state");
  const repo = join(tmp, "repository");
  const { mkdirSync } = await import("node:fs");
  mkdirSync(repo);
  execFileSync("git", ["init", "--quiet", "--initial-branch=main", repo]);
  execFileSync("git", ["-C", repo, "config", "user.email", "author@example.invalid"]);
  execFileSync("git", ["-C", repo, "config", "user.name", "Local Author"]);
  execFileSync("git", ["-C", repo, "config", "commit.gpgsign", "false"]);
  writeFileSync(join(repo, "local.txt"), "base\n");
  execFileSync("git", ["-C", repo, "add", "local.txt"]);
  execFileSync("git", ["-C", repo, "commit", "-qm", "base"]);
  writeFileSync(join(repo, "local.txt"), "base\nchanged\n");
  writeFileSync(join(repo, "notes.txt"), "untracked\n");
  const bundle = await localBundle(repo, "code-review", null);
  const root = String(bundle.artifact_root);
  const { writeArtifact } = await import("../dist/contract.js");
  const [bundlePath] = await writeArtifact(root, "local_wip_snapshot", bundle);
  const followup = prepareFollowup(root, bundle, digest(readJson(bundlePath, "evidence")), "auto");
  const template = readJson(followup.context_package.template_path, "local package template");
  template.questions = [
    {
      id: "q-local-scope",
      subject: "Do unstaged edits belong to the same task boundary?",
      source: "Primary inspection of the working tree.",
      critic: true,
    },
  ];
  writeJson(followup.context_package.template_path, template);
  const invalid = await recordLocalInput(bundlePath, writeInput(t, { mode: "full" }));
  assert.equal(invalid.status, "invalid");
  assert.ok(invalid.errors.some((issue) => issue.path === "$.mode"));

  const applied = await recordLocalInput(
    bundlePath,
    writeInput(t, {
      task: {
        goal: "Rename the local flag without touching mixed output.",
        acceptance_criteria: ["The flag rename is complete."],
        constraints: [],
        accepted_risks: [],
        deferred: [],
        decision_evidence: "The requester confirmed the rename boundary in the task interview.",
      },
      findings: [
        {
          id: "local-flag",
          severity: "low",
          status: "open",
          summary: "The renamed flag misses one call site.",
          requirement: "Every call site uses the new flag.",
          scenario: "A script passes the old flag name.",
          evidence: "scripts/run.sh still passes --old-flag.",
          consequence: "The script silently ignores the rename.",
          origin: "regression",
          minimum_fix: "Update the call site.",
          blocking: false,
          rationale: "A one-line correction restores the behavior.",
          decision_evidence: null,
          reopen_reason: null,
        },
      ],
      checks: [
        {
          name: "Call sites",
          status: "passed",
          required: true,
          evidence: "grep found no old flag.",
        },
      ],
      assessment: "The rename is complete and safe to accept.",
      verdict: "ready",
    }),
  );
  assert.equal(applied.status, "ok", JSON.stringify(applied.errors));
  const draftPath = applied.draft_path;
  assert.ok(existsSync(draftPath));
  const draft = readJson(draftPath, "local draft");
  assert.equal(draft.mode, followup.mode);
  assert.equal(draft.evidence_digest, digest(readJson(bundlePath, "evidence")));
  assert.equal(draft.findings[0].id, "local-flag");

  const recorded = await recordLocalPackage(bundlePath, followup.context_package.template_path);
  assert.equal(recorded.status, "ok");
  assert.match(recorded.critic_task.response_contract.import_command.command, /record-input/);
  assert.equal(
    recorded.critic_task.context_package.question_context_versions["q-local-scope"],
    recorded.question_context_versions["q-local-scope"],
  );
  const answered = await recordLocalInput(
    bundlePath,
    writeInput(t, {
      question_answers: [
        {
          question_id: "q-local-scope",
          verdict: "confirmed",
          evidence: "The unstaged edit continues the same rename; no boundary change is visible.",
          run_id: "critic-run-local",
          session_id: "critic-session-local",
          context_digest: recorded.question_context_versions["q-local-scope"],
        },
      ],
    }),
  );
  assert.equal(answered.status, "ok", JSON.stringify(answered.errors));
  const fresh = await finalizeLocal(bundlePath);
  assert.equal(fresh.status, "ok");
  const review = await recordReview(root, bundlePath, draftPath);
  assert.equal(review.mode, followup.mode);
  assert.equal(review.verdict, "ready");
  assert.ok(!existsSync(join(root, "gitlab")), "local mode never creates GitLab state");
});

test("canonical schema failures name the offending fields, not just the schema", async (t) => {
  const fixture = reviewFixture(t);
  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo, locale: "en" });
  const template = readJson(started.context_package.template_path, "package template");
  await assert.rejects(
    () => recordDraftPackage(started.draft_path, started.context_package.template_path),
    (error) => {
      assert.ok(error instanceof Error);
      assert.match(error.message, /canonical schema:\n - \$/);
      return true;
    },
  );
});

test("record-input updates an existing thread by id semantically and rejects forged machine bindings", async (t) => {
  const { started } = await preparedReview(t);
  const draftPath = started.draft_path;
  const before = readJson(draftPath, "draft");
  const thread = before.content.thread_decisions[0];
  const machine = {
    url: thread.url,
    state: thread.state,
    last_note_id: thread.last_note_id,
    last_note_body_sha256: thread.last_note_body_sha256,
    thread_sha256: thread.thread_sha256,
  };

  // A semantic update carries the id and the decision fields only.
  const applied = await recordDraftInput(
    draftPath,
    writeInput(t, {
      content: {
        thread_decisions: [
          {
            id: thread.id,
            assessment: "fixed",
            rationale: "The exact reviewed code already addresses the remark.",
            outcome: "resolve",
            proposed_response: "The exact reviewed code now handles this path.",
          },
        ],
      },
    }),
  );
  assert.equal(applied.status, "ok", JSON.stringify(applied.errors));
  const updated = readJson(draftPath, "draft").content.thread_decisions[0];
  for (const [field, value] of Object.entries(machine))
    assert.deepEqual(updated[field], value, `${field} stays with the runtime`);
  assert.equal(updated.assessment, "fixed");
  assert.equal(updated.rationale, "The exact reviewed code already addresses the remark.");

  // An unknown thread id cannot smuggle a hand-assembled record in.
  const unknown = await recordDraftInput(
    draftPath,
    writeInput(t, {
      content: {
        thread_decisions: [
          { id: "not-collected", assessment: "fixed", rationale: "x", outcome: "resolve" },
        ],
      },
    }),
  );
  assert.equal(unknown.status, "invalid");
  assert.ok(
    unknown.errors.some((issue) => issue.path === "$.content.thread_decisions[0].url"),
    "a new thread record still requires the full prepared shape",
  );

  // A machine field that disagrees with the prepared binding is rejected and
  // the draft keeps the previously applied decision unchanged.
  const draftBefore = readFileSync(draftPath);
  const forged = await recordDraftInput(
    draftPath,
    writeInput(t, {
      content: {
        thread_decisions: [
          { id: thread.id, assessment: "neutral", url: "https://forged.example/t" },
        ],
      },
    }),
  );
  assert.equal(forged.status, "invalid");
  const forgedIssue = forged.errors.find(
    (issue) => issue.path === "$.content.thread_decisions[0].url",
  );
  assert.match(forgedIssue.message, /Runtime-owned thread binding/);
  assert.match(forgedIssue.message, new RegExp(thread.url.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.deepEqual(readFileSync(draftPath), draftBefore);
  const preserved = readJson(draftPath, "draft").content.thread_decisions[0];
  assert.equal(preserved.assessment, "fixed", "the previously applied decision survives");
  assert.equal(preserved.url, machine.url);
});

test("malformed list shapes return addressed diagnostics and never touch the draft", async (t) => {
  const { started, recorded } = await preparedReview(t);
  const draftPath = started.draft_path;
  const before = readFileSync(draftPath);
  for (const value of [null, {}, [null]]) {
    const local = await recordDraftInput(draftPath, writeInput(t, { findings: value }));
    assert.equal(local.status, "invalid", JSON.stringify(value));
    const itemLevel = Array.isArray(value);
    assert.ok(
      local.errors.some((issue) =>
        itemLevel ? issue.path === "$.findings[0]" : issue.path === "$.findings",
      ),
      `findings ${JSON.stringify(value)} names the offending path`,
    );
    const threads = await recordDraftInput(
      draftPath,
      writeInput(t, { content: { thread_decisions: value } }),
    );
    assert.equal(threads.status, "invalid");
    assert.ok(
      threads.errors.some((issue) => issue.path.startsWith("$.content.thread_decisions")),
      `thread_decisions ${JSON.stringify(value)} names the offending path`,
    );
    assert.deepEqual(readFileSync(draftPath), before, "the draft is unchanged after each error");
  }
  const critic = await recordDraftCritic(
    draftPath,
    writeInput(t, {
      ...recorded.critic_task.response_contract.template,
      run_id: "critic-run-shape",
      session_id: "critic-session-shape",
      findings: [null],
    }),
  );
  assert.equal(critic.status, "invalid");
  assert.ok(critic.errors.some((issue) => issue.path === "$.findings[0]"));
  assert.deepEqual(readFileSync(draftPath), before);
});

test("the documented local cycle keeps original critic answers across sequential imports", async (t) => {
  const { execFileSync } = await import("node:child_process");
  const tmp = mkdtempSync(join(tmpdir(), "reviewmatic-local-cycle-"));
  t.after(() => {
    process.env.XDG_STATE_HOME = originalStateHome;
    rmSync(tmp, { recursive: true, force: true });
  });
  const originalStateHome = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = join(tmp, "state");
  const repo = join(tmp, "repository");
  mkdirSync(repo);
  execFileSync("git", ["init", "--quiet", "--initial-branch=main", repo]);
  execFileSync("git", ["-C", repo, "config", "user.email", "author@example.invalid"]);
  execFileSync("git", ["-C", repo, "config", "user.name", "Local Author"]);
  execFileSync("git", ["-C", repo, "config", "commit.gpgsign", "false"]);
  writeFileSync(join(repo, "review.txt"), "base\n");
  execFileSync("git", ["-C", repo, "add", "review.txt"]);
  execFileSync("git", ["-C", repo, "commit", "-qm", "base"]);
  writeFileSync(join(repo, "review.txt"), "base\nreviewed change\nlocal edit\n");

  const prepared = spawn(["prepare-local", "--repo-root", repo]);
  assert.equal(prepared.status, 0, prepared.stderr);
  const emitted = JSON.parse(prepared.stdout);
  const bundlePath = emitted.bundle;
  const root = emitted.scope_overview.inputs.artifact_root;

  // Documented order: record-package before record-input; the draft already
  // exists and binds the recorded package without any manual field copying.
  const template = readJson(emitted.review.context_package.template_path, "local package template");
  template.questions = [{ id: "q", subject: "Is retry bounded?", source: "Task", critic: true }];
  writeJson(emitted.review.context_package.template_path, template);
  const packaged = spawn([
    "record-package",
    "--bundle",
    bundlePath,
    "--input",
    emitted.review.context_package.template_path,
  ]);
  assert.equal(packaged.status, 0, packaged.stderr);
  const packageResult = JSON.parse(packaged.stdout);
  const versions = packageResult.question_context_versions;

  const filled = spawn([
    "record-input",
    "--bundle",
    bundlePath,
    "--input",
    writeInput(t, {
      task: {
        goal: "Bound retry",
        acceptance_criteria: ["Bounded"],
        constraints: [],
        accepted_risks: [],
        deferred: [],
        decision_evidence: "Fixture task",
      },
      checks: [
        {
          name: "Fixture read-only inspection",
          status: "passed",
          required: true,
          evidence: "Inspected",
        },
      ],
      assessment: "Inspected",
      verdict: "ready",
    }),
  ]);
  assert.equal(filled.status, 0, filled.stderr);
  const draftPath = JSON.parse(filled.stdout).draft_path;
  assert.equal(
    readJson(draftPath, "local draft").context_package.path,
    packageResult.artifact_path,
    "record-package binds into the draft prepared for this snapshot",
  );

  const answer = (id, verdict, evidence) => ({
    question_id: "q",
    context_digest: versions.q,
    run_id: id,
    session_id: id,
    verdict,
    ...evidence,
  });
  const importAnswer = async (entry) => {
    const result = await recordLocalInput(bundlePath, writeInput(t, { question_answers: [entry] }));
    return result;
  };
  assert.equal(
    (await importAnswer(answer("critic-one", "not_verified", { reason: "Cannot verify" }))).status,
    "ok",
  );
  assert.equal(
    (await importAnswer(answer("critic-two", "refuted", { evidence: "Refuted by trace" }))).status,
    "ok",
  );
  let stored = readJson(draftPath, "local draft").question_answers;
  assert.deepEqual(
    stored.map((item) => `${item.run_id}:${item.verdict}`),
    ["critic-one:not_verified", "critic-two:refuted"],
    "the second import keeps the first critic's original answer",
  );

  // A repeat of the same result is not duplicated.
  assert.equal(
    (await importAnswer(answer("critic-two", "refuted", { evidence: "Refuted by trace" }))).status,
    "ok",
  );
  stored = readJson(draftPath, "local draft").question_answers;
  assert.equal(stored.length, 2);

  // A different result under the same identity is rejected, not merged away.
  const before = readFileSync(draftPath);
  const conflict = await importAnswer(answer("critic-two", "confirmed", { evidence: "Rewritten" }));
  assert.equal(conflict.status, "invalid");
  assert.deepEqual(
    conflict.errors.map((issue) => issue.path),
    ["$.question_answers[0]"],
  );
  assert.deepEqual(readFileSync(draftPath), before);
  assert.deepEqual(
    readJson(draftPath, "local draft").question_answers.map(
      (item) => `${item.run_id}:${item.verdict}`,
    ),
    ["critic-one:not_verified", "critic-two:refuted"],
  );

  // The preserved not_verified answer still demands a primary verification.
  await assert.rejects(
    () => recordReview(root, bundlePath, draftPath),
    /critic answer for q is not_verified/,
  );
  const verified = await recordLocalInput(
    bundlePath,
    writeInput(t, {
      question_verifications: [
        {
          question_id: "q",
          context_digest: versions.q,
          verdict: "confirmed",
          evidence: "Primary traced the bounded retry",
          original: { run_id: "critic-one", session_id: "critic-one", verdict: "not_verified" },
        },
      ],
    }),
  );
  assert.equal(verified.status, "ok", JSON.stringify(verified.errors));
  const finalized = await recordReview(root, bundlePath, draftPath);
  assert.equal(finalized.verdict, "ready");
  assert.equal(finalized.question_summary.unverified, 0);
  assert.deepEqual(
    readJson(draftPath, "local draft").question_answers.map((item) => item.run_id),
    ["critic-one", "critic-two"],
    "finalization keeps both independent answers",
  );
});

test("a repeated local scope-review restores the task, baseline, and exact paths without mutation", async (t) => {
  const { execFileSync } = await import("node:child_process");
  const tmp = mkdtempSync(join(tmpdir(), "reviewmatic-local-scope-"));
  t.after(() => {
    process.env.XDG_STATE_HOME = originalStateHome;
    rmSync(tmp, { recursive: true, force: true });
  });
  const originalStateHome = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = join(tmp, "state");
  const repo = join(tmp, "repository");
  mkdirSync(repo);
  execFileSync("git", ["init", "--quiet", "--initial-branch=main", repo]);
  execFileSync("git", ["-C", repo, "config", "user.email", "author@example.invalid"]);
  execFileSync("git", ["-C", repo, "config", "user.name", "Local Author"]);
  execFileSync("git", ["-C", repo, "config", "commit.gpgsign", "false"]);
  writeFileSync(join(repo, "review.txt"), "base\n");
  execFileSync("git", ["-C", repo, "add", "review.txt"]);
  execFileSync("git", ["-C", repo, "commit", "-qm", "base"]);

  // First run: no scope exists yet.
  const empty = spawn(["prepare-local", "--repo-root", repo]);
  assert.equal(empty.status, 2, empty.stderr);
  assert.equal(JSON.parse(empty.stdout).status, "empty_scope");

  // Unfinished draft: the task and paths survive a read-only reprint.
  writeFileSync(join(repo, "review.txt"), "base\nedited\n");
  const prepared = spawn(["prepare-local", "--repo-root", repo]);
  assert.equal(prepared.status, 0, prepared.stderr);
  const first = JSON.parse(prepared.stdout);
  const root = first.scope_overview.inputs.artifact_root;
  const draftPath = first.review.draft_path;
  await recordLocalInput(
    first.bundle,
    writeInput(t, {
      task: {
        goal: "Bound retry",
        acceptance_criteria: ["Bounded"],
        constraints: [],
        accepted_risks: [],
        deferred: [],
        decision_evidence: "Fixture task",
      },
    }),
  );
  const draftBefore = readJson(draftPath, "local draft");
  const reprepare = spawn(["prepare-local", "--repo-root", repo]);
  assert.equal(reprepare.status, 0, reprepare.stderr);
  const redrafted = readJson(draftPath, "local draft");
  assert.equal(redrafted.evidence_digest, JSON.parse(reprepare.stdout).digest);
  assert.deepEqual(redrafted.task, draftBefore.task, "the same content never resets the draft");
  const templateBytes = readFileSync(first.review.context_package.template_path);
  const reprint = spawn(["scope-review", "--artifact-root", root]);
  assert.equal(reprint.status, 0, reprint.stderr);
  const scope = JSON.parse(reprint.stdout).scope;
  assert.equal(scope.task.goal, "Bound retry");
  assert.equal(scope.inputs.draft_path, draftPath);
  assert.equal(scope.inputs.context_package_template, first.review.context_package.template_path);
  assert.deepEqual(
    readJson(draftPath, "local draft"),
    redrafted,
    "reprint never rewrites the draft",
  );
  assert.deepEqual(
    readFileSync(first.review.context_package.template_path),
    templateBytes,
    "reprint never rewrites the package template",
  );

  // Finalized baseline: the reprint still exposes the recorded baseline. The
  // cycle continues on the re-prepared snapshot the runtime selected.
  const current = JSON.parse(reprepare.stdout);
  const template = readJson(current.review.context_package.template_path, "template");
  writeJson(current.review.context_package.template_path, template);
  const packaged = spawn([
    "record-package",
    "--bundle",
    current.bundle,
    "--input",
    current.review.context_package.template_path,
  ]);
  assert.equal(packaged.status, 0, packaged.stderr);
  await recordLocalInput(
    current.bundle,
    writeInput(t, {
      checks: [{ name: "Inspection", status: "passed", required: true, evidence: "Inspected" }],
      assessment: "Inspected",
      verdict: "ready",
    }),
  );
  const finished = spawn(["finalize-local", "--bundle", current.bundle, "--report", draftPath]);
  assert.equal(finished.status, 0, finished.stderr);
  assert.equal(JSON.parse(finished.stdout).review.verdict, "ready");
  const baseline = spawn(["scope-review", "--artifact-root", root]);
  assert.equal(baseline.status, 0, baseline.stderr);
  const baselineScope = JSON.parse(baseline.stdout).scope;
  assert.equal(baselineScope.previous_review.digest, JSON.parse(finished.stdout).review.digest);
  assert.equal(baselineScope.previous_review.mode, "unchanged");

  // Next snapshot: the runtime rebinds its own fields; unfinished prior work
  // on the same snapshot was never lost and the new draft follows the new
  // evidence digest without manual repair.
  writeFileSync(join(repo, "review.txt"), "base\nedited twice\n");
  const next = spawn(["prepare-local", "--repo-root", repo]);
  assert.equal(next.status, 0, next.stderr);
  const second = JSON.parse(next.stdout);
  assert.equal(second.digest, second.review.report_template.evidence_digest);
  assert.equal(second.review.report_template.evidence_digest !== first.digest, true);
  assert.deepEqual(second.review.report_template.task.goal, "Bound retry");
  await recordLocalInput(second.bundle, writeInput(t, { assessment: "Rechecked updated source" }));
  const redraft = readJson(draftPath, "local draft");
  assert.equal(redraft.evidence_digest, second.digest);
  assert.equal(redraft.mode, "incremental");
  assert.equal(redraft.assessment, "Rechecked updated source");
});

function writeInput(t, value) {
  const seen = [];
  const scan = (value, where) => {
    if (value === undefined) {
      seen.push(where);
      return;
    }
    if (Array.isArray(value)) value.forEach((item, index) => scan(item, `${where}[${index}]`));
    else if (value && typeof value === "object")
      Object.entries(value).forEach(([key, item]) => scan(item, `${where}.${key}`));
  };
  scan(value, "$");
  if (seen.length > 0) throw new Error(`undefined input values at ${seen.join(", ")}`);
  const path = join(mkdtempSync(join(tmpdir(), "reviewmatic-input-")), "input.json");
  t.after(() => rmSync(path, { force: true }));
  writeJson(path, value);
  return path;
}
