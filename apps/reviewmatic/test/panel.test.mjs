import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  checkReview,
  finishReview,
  recordDraftArbitration,
  recordDraftCritic,
  recordDraftInput,
  recordDraftPackage,
  recordDraftParticipants,
  refreshReview,
  resumeReview,
  startReview,
} from "../dist/draft.js";
import { readJson, writeJson } from "../dist/contract.js";
import { reviewFixture } from "./helpers/review-fixture.mjs";
import { loadPlan } from "../dist/tui/support.js";

// The orchestrated panel: one recorded selection, parallel independent critic
// receipts, one arbitration receipt, local finalization, and a runbook that
// keeps every candidate with its verdict.

let inputDirectory = ".";

function writeInput(value, name = "input.json") {
  const path = join(inputDirectory, `${process.pid}-${name}`);
  writeJson(path, value);
  return path;
}

function criticFinding(id, summary, severity = "medium") {
  return {
    id,
    severity,
    summary,
    risk: "A retried request can duplicate a side effect.",
    evidence: ["review.txt:2 repeats the write on the retry branch."],
    consequence: "Duplicated writes surface as duplicated records downstream.",
    relation_to_change: "The change touches exactly this retry path.",
    minimum_fix: "Bind the retried write behind an idempotency key.",
  };
}

async function panelPrepared(t, overrides = {}) {
  const fixture = reviewFixture(t, overrides);
  inputDirectory = fixture.tmp;
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
  return { fixture, started };
}

function participantsSelection() {
  return {
    critics: [
      { name: "critic-general", profile: "critic-general", provider: "openai", model: "gpt-x" },
      { name: "critic-plain" },
    ],
    arbitrator: { name: "arb-main", provider: "zai", model: "glm-x" },
  };
}

function criticReceipt(evidenceDigest, runId, sessionId, findings, answers) {
  return {
    schema: "portable-gitlab/critic-receipt/v2",
    evidence_digest: evidenceDigest,
    run_id: runId,
    session_id: sessionId,
    findings,
    question_answers: answers,
    external_mutations: false,
  };
}

function answer(versions, verdict, evidence) {
  return {
    question_id: "q-idempotency",
    verdict,
    evidence,
    context_digest: versions["q-idempotency"],
  };
}

function arbitrationBody(draft, versions, options = {}) {
  const content = draft.content;
  const { minimal = false } = options;
  return {
    schema: "code-review/arbitration/v1",
    evidence_digest: draft.evidence_digest,
    run_id: "arb-run",
    session_id: "arb-session",
    arbitrator: { name: "arb-main", provider: "zai", model: "glm-x" },
    external_mutations: false,
    findings: minimal
      ? []
      : [
          {
            id: "arb-merged-key",
            severity: "high",
            summary: "The retried write needs one shared idempotency key across both call sites.",
            risk: "Either call site can still duplicate the side effect.",
            evidence: ["review.txt:2 repeats the write on the retry branch."],
            consequence: "Duplicated writes surface as duplicated records downstream.",
            relation_to_change: "The change introduces the retry path.",
            minimum_fix: "Bind both retried writes behind one idempotency key.",
          },
        ],
    dispositions: minimal
      ? []
      : [
          {
            id: "critic-a-key",
            decision: "accept",
            reason: "The exact head repeats the write; the evidence was re-read in the worktree.",
            dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
          },
          {
            id: "critic-a-dup",
            decision: "reject",
            reason: "Duplicates critic-b-key: the same retried write on the same line.",
            dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
            duplicate_of: "critic-b-key",
          },
          {
            id: "critic-b-key",
            decision: "accept",
            reason: "Confirmed against the exact head snapshot.",
            dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
          },
          {
            id: "critic-b-refuted",
            decision: "reject",
            reason: "The named helper exists at the exact head; the concern does not reproduce.",
            dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
          },
          {
            id: "arb-merged-key",
            decision: "accept",
            reason: "Arbitrator-authored merge of both partial key findings.",
            dependencies: { paths: ["review.txt"], thread_ids: [], metadata_fields: [], ci: false },
          },
        ],
    ci_job_assessments: draft.ci_job_assessments,
    owner_decision_reasons: [],
    question_verifications: [
      {
        question_id: "q-idempotency",
        original: {
          run_id: "run-a",
          session_id: "session-a",
          verdict: "confirmed",
        },
        verdict: "confirmed",
        evidence: "The exact head binds the retried write behind the key.",
        context_digest: versions ? versions["q-idempotency"] : undefined,
      },
    ],
    content: minimal
      ? {}
      : {
          summary: "The bounded change meets the agreed contract.",
          architecture_assessment: "Existing ownership is preserved.",
          chat_assessment: {
            necessity: { status: "supported", rationale: "The existing timeout is unbounded." },
            relevance: { status: "current", rationale: "The current runner uses this path." },
            change: "Bound the check.",
          },
          semver_impact: "patch",
          semver_rationale: "Backward-compatible correction.",
          semver_assessment: {
            ...content.semver_assessment,
            policy: "No publication configuration is available.",
            sources: ["Fixture repository and empty release catalog"],
            fallback_reason: "No published release can be established.",
          },
          checks: ["Inspected the exact committed diff; external tests were not run."],
          mr_metadata_assessment: Object.fromEntries(
            Object.keys(content.mr_metadata_assessment).map((field) => [
              field,
              {
                status: "ok",
                rationale: "The observed metadata is sufficient.",
                recommendation: null,
              },
            ]),
          ),
          label_assessments: content.label_assessments.map((item) => ({
            name: item.name,
            status: item.name === "semver::patch" ? "applicable" : "inapplicable",
            rationale: "Matches the assessed patch contribution.",
          })),
          previous_finding_assessments: [],
          recommended_issues: [],
          thread_decisions: content.thread_decisions.map((thread) => ({
            id: thread.id,
            assessment: "fixed",
            rationale: "The exact reviewed code already addresses the remark.",
            outcome: thread.state === "resolved" ? "no_publication" : "resolve",
            proposed_response:
              thread.state === "resolved" ? null : "The exact reviewed code now handles this path.",
            fix_mode: "not_required",
            patch: null,
            fixing_commit: null,
          })),
          finding_publications: [
            {
              finding_id: "critic-a-key",
              type: "line",
              path: "review.txt",
              line: 2,
              old_line: null,
              body: "Bind the retried write behind the idempotency key.\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
              fix_mode: "suggestion",
              patch: null,
            },
            {
              finding_id: "critic-b-key",
              type: "line",
              path: "review.txt",
              line: 2,
              old_line: null,
              body: "Bind the retried write behind the idempotency key.\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
              fix_mode: "suggestion",
              patch: null,
            },
            {
              finding_id: "arb-merged-key",
              type: "line",
              path: "review.txt",
              line: 2,
              old_line: null,
              body: "Bind both retried writes behind one idempotency key.\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
              fix_mode: "suggestion",
              patch: null,
            },
          ],
        },
  };
}

async function panelRunning(t, overrides = {}) {
  const { fixture, started } = await panelPrepared(t, overrides);
  const draftPath = started.draft_path;
  await recordDraftParticipants(draftPath, writeInput(participantsSelection()));
  const recordedPackage = await recordDraftPackage(
    draftPath,
    started.context_package.template_path,
  );
  assert.equal(recordedPackage.status, "ok");
  await recordDraftInput(
    draftPath,
    writeInput({
      run_id: "orchestrator-run",
      session_id: "orchestrator-session",
    }),
  );
  return { fixture, started, draftPath, recordedPackage };
}

test("panel review runs selection, parallel critics, arbitration, and local finalization", async (t) => {
  const { fixture, started, draftPath, recordedPackage } = await panelRunning(t);
  const requests = fixture.requestCount();

  const inspection = readJson(started.inspection_path, "inspection index");
  assert.equal(inspection.file_relations.complete, true);
  assert.ok(Array.isArray(inspection.file_relations.entries));
  const relation = inspection.file_relations.entries.find((item) => item.path === "review.txt");
  assert.ok(relation, "changed paths receive a relation entry");
  assert.deepEqual(relation.referenced_by, ["index.txt"]);
  assert.match(String(inspection.file_relations.notice), /not a semantic dependency map/);

  assert.equal(recordedPackage.critic_tasks.length, 2);
  assert.deepEqual(
    recordedPackage.critic_tasks.map((task) => task.participant),
    ["critic-general", "critic-plain"],
  );
  assert.match(
    recordedPackage.critic_tasks[0].import_command.command,
    /--participant critic-general/,
  );
  assert.equal(recordedPackage.critic_tasks[1].profile, null);

  const restricted = await recordDraftInput(
    draftPath,
    writeInput(
      {
        findings: [criticFinding("host-own-pass", "The orchestrator adds its own finding.")],
      },
      "restricted.json",
    ),
  );
  assert.equal(restricted.status, "invalid");
  assert.ok(
    restricted.errors.some((issue) => issue.path === "$.findings" && /panel/.test(issue.message)),
  );

  const versions = recordedPackage.question_context_versions;
  const draft = readJson(draftPath, "draft");
  const unbound = await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(
        draft.evidence_digest,
        "run-a",
        "session-a",
        [criticFinding("critic-a-key", "A")],
        [answer(versions, "confirmed", "The key exists.")],
      ),
      "critic-a.json",
    ),
  );
  assert.equal(unbound.status, "invalid");
  assert.ok(unbound.errors.some((issue) => issue.path === "$.participant"));

  await assert.rejects(
    recordDraftArbitration(draftPath, writeInput(arbitrationBody(draft, versions), "early.json")),
    /Every selected critic receipt must be imported/,
  );

  const criticA = await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(
        draft.evidence_digest,
        "run-a",
        "session-a",
        [
          criticFinding("critic-a-key", "The retry path repeats a write."),
          criticFinding("critic-a-dup", "Retried write lacks a key."),
        ],
        [answer(versions, "confirmed", "The exact head binds writes behind the key.")],
      ),
      "critic-a.json",
    ),
    "critic-general",
  );
  assert.equal(criticA.status, "ok", JSON.stringify(criticA.errors));
  assert.equal(criticA.arbitrator_task, undefined);
  const criticB = await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(
        draft.evidence_digest,
        "run-b",
        "session-b",
        [
          criticFinding("critic-b-key", "Retried write lacks a key."),
          criticFinding("critic-b-refuted", "Missing helper for the retry path."),
        ],
        [answer(versions, "refuted", "The retry branch still writes without the key.")],
      ),
      "critic-b.json",
    ),
    "critic-plain",
  );
  assert.equal(criticB.status, "ok", JSON.stringify(criticB.errors));
  assert.ok(criticB.arbitrator_task);
  assert.equal(criticB.arbitrator_task.launch, "now_after_every_critic_receipt");
  const arbitrationInput = readJson(criticB.arbitrator_task.input_path, "arbitration input");
  assert.equal(arbitrationInput.critic_receipts.length, 2);
  assert.deepEqual(arbitrationInput.contradictions, ["q-idempotency"]);
  assert.match(arbitrationInput.response_contract.import_command.command, /record-arbitration/);
  assert.equal(arbitrationInput.participants.critics[0].name, "critic-general");

  const wrongArb = arbitrationBody(readJson(draftPath, "draft"), versions);
  wrongArb.arbitrator = { name: "critic-plain" };
  const wrong = await recordDraftArbitration(draftPath, writeInput(wrongArb, "wrong-arb.json"));
  assert.equal(wrong.status, "invalid");
  assert.ok(
    wrong.errors.some((issue) => issue.path === "$.arbitrator.name"),
    JSON.stringify(wrong.errors),
  );

  const noResolution = arbitrationBody(readJson(draftPath, "draft"), versions);
  noResolution.question_verifications = [];
  const blocked = await recordDraftArbitration(
    draftPath,
    writeInput(noResolution, "no-resolution.json"),
  );
  assert.equal(blocked.status, "invalid");
  assert.ok(
    blocked.errors.some(
      (issue) => issue.path === "$.question_verifications" && /q-idempotency/.test(issue.message),
    ),
  );

  const imported = await recordDraftArbitration(
    draftPath,
    writeInput(arbitrationBody(readJson(draftPath, "draft"), versions), "arbitration.json"),
  );
  assert.equal(imported.status, "ok", JSON.stringify(imported.errors));
  assert.equal(imported.imported.verdicts, 5);

  const checked = await checkReview(draftPath);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal(fixture.requestCount(), requests, "recording and validation stay local");

  const finished = await finishReview(draftPath);
  assert.equal(finished.status, "ok", JSON.stringify(finished));
  assert.equal(fixture.requestCount(), requests, "finalization is local-only");

  const book = readFileSync(finished.markdown_path, "utf8");
  assert.match(book, /## Review panel/);
  assert.match(
    book,
    /critic `critic-general` — profile: critic-general · provider: openai · model: gpt-x/,
  );
  assert.match(book, /arbitrator `arb-main` — provider: zai · model: glm-x/);
  assert.match(book, /## Arbitration verdicts/);
  assert.match(book, /`critic-b-refuted`[\s\S]*?refuted/);
  assert.match(book, /duplicate of `critic-b-key`/);
  assert.match(book, /Raised by: critic-general/);
  assert.match(book, /Merged by the arbitrator from: `critic-a-dup`/);
  assert.match(book, /current_head=\$\(glab api/);

  const bundle = loadPlan(started.artifact_root);
  const bodies = bundle.plan.publication_preview.body_files.map((item) => item.content).join("\n");
  for (const internal of ["critic-general", "critic-plain", "arb-main", "zai", "glm-x", "gpt-x"])
    assert.ok(!bodies.includes(internal), `${internal} must stay out of GitLab bodies`);
  assert.ok(
    bundle.plan.review_source.participants.critics.every((critic) => critic.receipt),
    "participant receipt bindings survive into the plan",
  );
  assert.equal(bundle.plan.review_source.arbitration.session_id, "arb-session");

  // The head guard stops a publication block before any write when the MR
  // moved after the review.
  const block = [...book.matchAll(/```shell\n([\s\S]*?)\n```/g)]
    .map((match) => match[1])
    .find((body) => body.includes("/discussions/discussion-42/notes"));
  writeFileSync(
    fixture.configPath,
    JSON.stringify({ ...fixture.config, headSha: fixture.baseSha }),
  );
  const moved = spawnSync("sh", ["-c", block], { encoding: "utf8", env: process.env });
  assert.notEqual(moved.status, 0);
  assert.match(moved.stderr, /head differs|nothing was published/);
  const config = readJson(fixture.configPath);
  assert.equal((config.publishedNotes ?? []).length, 0);
});

test("panel selections are fixed once receipts exist and arbitration cannot be silently replaced", async (t) => {
  const { fixture, started, draftPath } = await panelRunning(t, { resolved: true });
  const pointer = readJson(join(started.artifact_root, "context-package.json"), "pointer");
  const packagePayload = readJson(pointer.package_path, "package").payload;
  const versions = Object.fromEntries(
    packagePayload.questions.map((question) => [question.id, question.context_digest]),
  );
  const current = readJson(draftPath, "draft");
  const answers = [answer(versions, "confirmed", "The exact head binds writes behind the key.")];
  await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(current.evidence_digest, "run-a", "session-a", [], answers),
      "critic-a.json",
    ),
    "critic-general",
  );
  await assert.rejects(
    recordDraftParticipants(draftPath, writeInput(participantsSelection(), "again.json")),
    /fixed once critic receipts exist/,
  );
  const doubleBinding = await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(current.evidence_digest, "run-a", "session-a", [], answers),
      "critic-a2.json",
    ),
    "critic-plain",
  );
  assert.equal(doubleBinding.status, "invalid");
  assert.ok(doubleBinding.errors.some((issue) => issue.path === "$.participant"));
  await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(current.evidence_digest, "run-b", "session-b", [], answers),
      "critic-b.json",
    ),
    "critic-plain",
  );
  const receipt = arbitrationBody(readJson(draftPath, "draft"), versions, { minimal: true });
  const imported = await recordDraftArbitration(draftPath, writeInput(receipt, "arbitration.json"));
  assert.equal(imported.status, "ok", JSON.stringify(imported.errors));
  await assert.rejects(
    recordDraftArbitration(
      draftPath,
      writeInput(arbitrationBody(readJson(draftPath, "draft"), versions), "replace.json"),
    ),
    /already recorded/,
  );
  void fixture;
});

test("fast mode rejects a panel and the resume overview reports an unrecorded panel", async (t) => {
  const { fixture } = await panelPrepared(t, { resolved: true });
  const fast = await startReview({
    url: fixture.url,
    repoRoot: fixture.repo,
    reviewMode: "fast",
  });
  await assert.rejects(
    recordDraftParticipants(fast.draft_path, writeInput(participantsSelection())),
    /fast and unchanged reviews run without a panel/,
  );
  const resumed = await resumeReview(fast.artifact_root);
  assert.equal(resumed.panel.recorded, false);
  assert.equal(resumed.panel.required, false);
  assert.match(resumed.panel.record_command, /record-participants/);
});

test("refresh-review carries the panel selection without receipt bindings", async (t) => {
  const { fixture, started, draftPath, recordedPackage } = await panelRunning(t);
  const versions = recordedPackage.question_context_versions;
  const current = readJson(draftPath, "draft");
  const answers = [answer(versions, "confirmed", "The exact head binds writes behind the key.")];
  await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(current.evidence_digest, "run-a", "session-a", [], answers),
      "critic-a.json",
    ),
    "critic-general",
  );
  await recordDraftCritic(
    draftPath,
    writeInput(
      criticReceipt(current.evidence_digest, "run-b", "session-b", [], answers),
      "critic-b.json",
    ),
    "critic-plain",
  );
  const receipt = arbitrationBody(readJson(draftPath, "draft"), versions, { minimal: true });
  assert.equal(
    (await recordDraftArbitration(draftPath, writeInput(receipt, "arbitration.json"))).status,
    "ok",
  );
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, noteBody: "New context" }));
  const refreshed = await refreshReview(draftPath);
  assert.equal(refreshed.status, "needs_reassessment");
  const next = readJson(refreshed.draft_path, "draft");
  assert.equal(next.participants.critics.length, 2);
  assert.ok(next.participants.critics.every((critic) => critic.receipt === undefined));
  assert.equal(next.critic_count, 2);
  assert.equal(next.arbitration, undefined);
  assert.equal(next.findings.length, 0);
  assert.equal(readJson(draftPath, "draft").critics.length, 2);
});
