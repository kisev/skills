import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { readJson, writeArtifact, writeJson } from "../dist/contract.js";
import {
  localBundle,
  prepareFollowup,
  recordLocalArbitration,
  recordLocalCritic,
  recordLocalInput,
  recordLocalPackage,
  recordLocalParticipants,
  recordReview,
} from "../dist/local-review.js";

// The local WIP panel: one recorded selection, parallel local critics, one
// arbitration receipt, and a schema-identical finalized report with the
// receipts preserved as companions.

function git(repo, ...args) {
  const result = spawnSync("git", ["-C", repo, ...args], { encoding: "utf8" });
  assert.equal(result.status, 0, `git ${args.join(" ")} failed: ${result.stderr}`);
  return result.stdout.trim();
}

function repository(t) {
  const root = mkdtempSync(join(tmpdir(), "local-panel-"));
  const originalStateHome = process.env.XDG_STATE_HOME;
  t.after(() => {
    process.env.XDG_STATE_HOME = originalStateHome;
    rmSync(root, { recursive: true, force: true });
  });
  process.env.XDG_STATE_HOME = join(root, "state");
  const repo = join(root, "checkout");
  mkdirSync(repo);
  git(repo, "init", "--quiet");
  git(repo, "config", "commit.gpgsign", "false");
  git(repo, "config", "user.email", "test@example.invalid");
  git(repo, "config", "user.name", "Test");
  writeFileSync(join(repo, "renderer.txt"), "base\n");
  git(repo, "add", ".");
  git(repo, "commit", "-qm", "base");
  writeFileSync(join(repo, "renderer.txt"), "broken\n");
  return { repo, root };
}

function localFinding(id, summary, blocking = true) {
  return {
    id,
    severity: blocking ? "high" : "low",
    status: "open",
    summary,
    requirement: "Preserve mixed Markdown verbatim.",
    scenario: "A user includes an issue reference in a Markdown table.",
    evidence: "renderer('table #7') rewrites a protected value.",
    consequence: "The generated table is corrupted.",
    origin: "regression",
    minimum_fix: "Keep non-plain-text values unchanged.",
    blocking,
    rationale: "A small correction restores the explicitly agreed behavior.",
    decision_evidence: null,
    reopen_reason: null,
  };
}

function localCriticReceipt(evidenceDigest, runId, sessionId, findings, answers) {
  return {
    schema: "code-review/local-critic-receipt/v1",
    evidence_digest: evidenceDigest,
    run_id: runId,
    session_id: sessionId,
    findings,
    question_answers: answers,
    external_mutations: false,
  };
}

test("local panel completes selection, critics, arbitration, and a schema-identical report", async (t) => {
  const { repo, root } = repository(t);
  const bundle = await localBundle(repo, "code-review", null);
  const artifactRootPath = bundle.artifact_root;
  const [snapshot, digestValue] = await writeArtifact(
    artifactRootPath,
    "local_wip_snapshot",
    bundle,
  );
  const context = prepareFollowup(artifactRootPath, bundle, digestValue, "auto");
  const draftPath = context.draft_path;
  const templatePath = context.context_package.template_path;
  const template = readJson(templatePath, "template");
  template.goal = { status: "known", text: "Link plain text without modifying mixed Markdown." };
  template.acceptance_criteria = { status: "known", items: ["Plain references link."] };
  template.questions = [
    {
      id: "q-renderer",
      subject: "Does the staged renderer change touch protected values?",
      source: "Local conversation with the author",
      critic: true,
    },
  ];
  writeJson(templatePath, template);

  const selection = await recordLocalParticipants(
    snapshot,
    writeJsonInput(root, "selection.json", {
      critics: [{ name: "critic-local", profile: "critic-general" }, { name: "critic-second" }],
      arbitrator: { name: "arb-local" },
    }),
  );
  assert.equal(selection.status, "ok", JSON.stringify(selection));
  assert.equal(selection.critic_count, 2);
  const recorded = await recordLocalPackage(snapshot, templatePath);
  assert.equal(recorded.status, "ok");
  assert.equal(recorded.critic_tasks.length, 2);
  assert.match(recorded.critic_tasks[0].import_command.command, /--participant critic-local/);

  const task = await recordLocalInput(
    snapshot,
    writeJsonInput(root, "task.json", {
      task: {
        goal: "Link plain text without modifying mixed Markdown.",
        acceptance_criteria: ["Plain references link; mixed Markdown remains unchanged."],
        constraints: ["Do not implement a Markdown parser."],
        accepted_risks: [],
        deferred: [],
        decision_evidence: "User chose whole-value plain-text linking in the interview.",
      },
    }),
  );
  assert.equal(task.status, "ok", JSON.stringify(task.errors));
  const restricted = await recordLocalInput(
    snapshot,
    writeJsonInput(root, "restricted.json", {
      findings: [localFinding("host-pass", "Orchestrator finding")],
    }),
  );
  assert.equal(restricted.status, "invalid");
  assert.ok(
    restricted.errors.some((issue) => issue.path === "$.findings" && /panel/.test(issue.message)),
  );

  const versions = recorded.question_context_versions;
  const answer = (verdict, evidence) => ({
    question_id: "q-renderer",
    verdict,
    evidence,
    context_digest: versions["q-renderer"],
  });
  const draft = readJson(draftPath, "draft");
  const unbound = await recordLocalCritic(
    snapshot,
    writeJsonInput(
      root,
      "critic-a.json",
      localCriticReceipt(
        draft.evidence_digest,
        "run-a",
        "session-a",
        [localFinding("local-critic-a", "Renderer rewrites protected table values.")],
        [answer("confirmed", "Protected values stay untouched.")],
      ),
    ),
  );
  assert.equal(unbound.status, "invalid");
  assert.ok(unbound.errors.some((issue) => issue.path === "$.participant"));

  const criticA = await recordLocalCritic(
    snapshot,
    writeJsonInput(
      root,
      "critic-a.json",
      localCriticReceipt(
        draft.evidence_digest,
        "run-a",
        "session-a",
        [localFinding("local-critic-a", "Renderer rewrites protected table values.")],
        [answer("confirmed", "Protected values stay untouched.")],
      ),
    ),
    "critic-local",
  );
  assert.equal(criticA.status, "ok", JSON.stringify(criticA.errors));
  assert.equal(criticA.arbitrator_task, undefined);
  const criticB = await recordLocalCritic(
    snapshot,
    writeJsonInput(
      root,
      "critic-b.json",
      localCriticReceipt(
        draft.evidence_digest,
        "run-b",
        "session-b",
        [
          localFinding("local-critic-b", "Protected table values are rewritten."),
          localFinding("local-critic-noise", "An unrelated formatting remark."),
        ],
        [answer("refuted", "The staged diff rewrites protected values.")],
      ),
    ),
    "critic-second",
  );
  assert.equal(criticB.status, "ok", JSON.stringify(criticB.errors));
  assert.ok(criticB.arbitrator_task);
  const arbitrationInput = readJson(criticB.arbitrator_task.input_path, "arbitration input");
  assert.equal(arbitrationInput.critic_receipts.length, 2);
  assert.deepEqual(arbitrationInput.contradictions, ["q-renderer"]);

  const arbitration = {
    schema: "code-review/local-arbitration/v1",
    evidence_digest: draft.evidence_digest,
    run_id: "arb-run",
    session_id: "arb-session",
    arbitrator: { name: "arb-local" },
    external_mutations: false,
    findings: [
      {
        ...localFinding("local-critic-a", "Renderer rewrites protected table values.", false),
        status: "open",
        severity: "low",
      },
    ],
    dispositions: [
      {
        id: "local-critic-a",
        decision: "accept",
        reason: "Confirmed against the staged diff in the working tree.",
      },
      {
        id: "local-critic-b",
        decision: "reject",
        reason: "Duplicates local-critic-a.",
        duplicate_of: "local-critic-a",
      },
      {
        id: "local-critic-noise",
        decision: "reject",
        reason: "The remark describes intended behavior.",
      },
    ],
    question_verifications: [
      {
        question_id: "q-renderer",
        original: { run_id: "run-a", session_id: "session-a", verdict: "confirmed" },
        verdict: "confirmed",
        evidence: "Re-read the staged diff: protected values stay untouched.",
        context_digest: versions["q-renderer"],
      },
    ],
    checks: [
      {
        name: "Renderer acceptance cases",
        status: "passed",
        required: true,
        evidence: "Plain text and protected input examples inspected.",
      },
    ],
    assessment: "The staged change meets the agreed boundary after the merged correction.",
    verdict: "ready",
  };
  const noResolution = {
    ...arbitration,
    question_verifications: [],
  };
  const blocked = await recordLocalArbitration(
    snapshot,
    writeJsonInput(root, "blocked.json", noResolution),
  );
  assert.equal(blocked.status, "invalid");
  assert.ok(
    blocked.errors.some(
      (issue) => issue.path === "$.question_verifications" && /q-renderer/.test(issue.message),
    ),
    JSON.stringify(blocked.errors),
  );

  const wrongVerdict = { ...arbitration, verdict: "not_ready" };
  const mismatch = await recordLocalArbitration(
    snapshot,
    writeJsonInput(root, "mismatch.json", wrongVerdict),
  );
  assert.equal(mismatch.status, "invalid");
  assert.ok(mismatch.errors.some((issue) => issue.path === "$.verdict"));

  const imported = await recordLocalArbitration(
    snapshot,
    writeJsonInput(root, "arbitration.json", arbitration),
  );
  assert.equal(imported.status, "ok", JSON.stringify(imported.errors));
  const saved = await recordReview(artifactRootPath, snapshot, draftPath);
  assert.equal(saved.verdict, "ready");
  assert.equal(saved.question_summary.contradicted, 1);

  const reportEnvelope = readJson(join(artifactRootPath, "local-review.json"), "pointer");
  const [, report] = (() => {
    const value = readJson(
      join(
        artifactRootPath,
        "artifacts",
        "local_review_report",
        `${reportEnvelope.review_digest}.json`,
      ),
      "report",
    );
    return [value, value.payload];
  })();
  assert.equal(report.participants, undefined);
  assert.equal(report.critics, undefined);
  assert.equal(report.arbitration, undefined);
  assert.deepEqual(
    report.findings.map((item) => item.id),
    ["local-critic-a"],
  );

  const panelDir = join(artifactRootPath, "local-panel");
  assert.equal(existsSync(join(panelDir, `critics-${digestValue.slice(0, 16)}.json`)), true);
  assert.equal(existsSync(join(panelDir, `arbitration-${digestValue.slice(0, 16)}.json`)), true);
  const companions = readJson(
    join(panelDir, `arbitration-${digestValue.slice(0, 16)}.json`),
    "arbitration",
  );
  assert.equal(companions.dispositions.length, 3);

  // Freshness stays enforced: a changed working tree blocks a repeated
  // finalization against the same snapshot.
  writeFileSync(join(repo, "renderer.txt"), "changed again\n");
  await assert.rejects(
    recordReview(artifactRootPath, snapshot, draftPath),
    /baseline changed|changed before report finalization/,
  );
});

function writeJsonInput(root, name, value) {
  const path = join(root, `panel-${name}`);
  writeJson(path, value);
  return path;
}
