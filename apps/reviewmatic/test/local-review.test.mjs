import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";
import { WorkflowError, writeArtifact, writeJson } from "../dist/contract.js";
import {
  baseline,
  emptyScopeReason,
  finalizeLocal,
  localBundle,
  prepareFollowup,
  recordReview,
  validateReport,
} from "../dist/local-review.js";

function isWorkflowError(message) {
  return (error) => {
    assert.ok(error instanceof WorkflowError);
    assert.match(error.message, message);
    return true;
  };
}

function git(repo, ...args) {
  const result = spawnSync("git", ["-C", repo, ...args], { encoding: "utf8" });
  assert.equal(result.status, 0, `git ${args.join(" ")} failed: ${result.stderr}`);
  return result.stdout.trim();
}

function finding() {
  return {
    id: "markdown-1",
    severity: "low",
    status: "open",
    summary: "Mixed Markdown is modified.",
    requirement: "Preserve mixed Markdown verbatim.",
    scenario: "A user includes an issue reference in a Markdown table.",
    evidence: "renderer('table #7') rewrites a protected value.",
    consequence: "The generated table is corrupted.",
    origin: "regression",
    minimum_fix: "Keep non-plain-text values unchanged.",
    blocking: true,
    rationale: "A small correction restores the explicitly agreed behavior.",
    decision_evidence: null,
    reopen_reason: null,
  };
}

function reportPayload() {
  return {
    evidence_digest: "a".repeat(64),
    previous_review_digest: null,
    mode: "full",
    task: {
      goal: "Link plain text without modifying mixed Markdown.",
      acceptance_criteria: ["Plain references link; mixed Markdown remains unchanged."],
      constraints: ["Do not implement a Markdown parser."],
      accepted_risks: ["Mixed Markdown may retain unlinked references."],
      deferred: [],
      decision_evidence: "User chose whole-value plain-text linking in the interview.",
    },
    task_change_reason: null,
    findings: [finding()],
    checks: [
      {
        name: "Renderer acceptance cases",
        status: "passed",
        required: true,
        evidence: "Plain text and protected input examples inspected.",
      },
    ],
    assessment: "A narrow renderer fix suffices. Patch impact; no new parser needed.",
    verdict: "not_ready",
    external_mutations: false,
  };
}

function repository(t) {
  const root = mkdtempSync(join(tmpdir(), "local-review-"));
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
  return repo;
}

async function prepare(repo, incremental = "auto") {
  const bundle = await localBundle(repo, "code-review", null);
  const root = bundle.artifact_root;
  const [path, digest] = await writeArtifact(root, "local_wip_snapshot", bundle);
  return [path, prepareFollowup(root, bundle, digest, incremental)];
}

async function initialReport(repo) {
  const [snapshot, context] = await prepare(repo);
  const report = reportPayload();
  report.evidence_digest = context.report_template.evidence_digest;
  return [snapshot, context, report];
}

async function record(snapshot, context, report) {
  const draft = context.draft_path;
  writeJson(draft, report);
  return recordReview(dirname(draft), snapshot, draft);
}

test("local fix cycle retains decisions and checks the delta", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  assert.equal(context.mode, "full");
  const saved = await record(snapshot, context, report);
  assert.equal(saved.verdict, "not_ready");

  const [, unchanged] = await prepare(repo);
  assert.equal(unchanged.mode, "unchanged");
  assert.deepEqual(unchanged.previous_report.task, report.task);
  assert.deepEqual(unchanged.report_template.checks, []);

  writeFileSync(join(repo, "renderer.txt"), "fixed\n");
  writeFileSync(join(repo, "example.txt"), "#7\n");
  const [fixedSnapshot, followup] = await prepare(repo);
  assert.equal(followup.mode, "incremental");
  assert.ok(followup.delta.unstaged.includes("fixed"));
  assert.equal(followup.delta.untracked[0].path, "example.txt");
  const fixed = followup.report_template;
  fixed.findings[0].status = "fixed";
  fixed.findings[0].blocking = false;
  fixed.findings[0].evidence = "Table remains unchanged.";
  fixed.checks = report.checks;
  fixed.assessment = report.assessment;
  fixed.verdict = "ready";
  const result = await record(fixedSnapshot, followup, fixed);
  assert.equal(result.verdict, "ready");
  const [, after] = await prepare(repo);
  assert.equal(after.mode, "unchanged");
  assert.equal(readFileSync(join(repo, "renderer.txt"), "utf8"), "fixed\n");
});

test("accepted risk cannot reopen without a changed basis", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  report.findings[0].status = "accepted_risk";
  report.findings[0].blocking = false;
  report.findings[0].decision_evidence =
    "User explicitly accepts unlinked references in mixed Markdown.";
  report.verdict = "ready";
  await record(snapshot, context, report);
  const [nextSnapshot, followup] = await prepare(repo);
  const reopened = structuredClone(report);
  reopened.evidence_digest = followup.report_template.evidence_digest;
  reopened.previous_review_digest = followup.previous_review_digest;
  reopened.mode = "unchanged";
  reopened.verdict = "not_ready";
  reopened.findings[0].status = "open";
  reopened.findings[0].blocking = true;
  reopened.findings[0].reopen_reason = "Reviewer disagrees.";
  await assert.rejects(
    () => record(nextSnapshot, followup, reopened),
    isWorkflowError(/changed facts or a user decision/),
  );
  reopened.findings[0].evidence =
    "The renderer now deletes the table rather than leaving references unlinked.";
  reopened.findings[0].reopen_reason =
    "The new failure causes data loss outside the accepted limitation.";
  assert.equal((await record(nextSnapshot, followup, reopened)).verdict, "not_ready");
});

test("prior findings and the task boundary cannot silently disappear", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  const saved = await record(snapshot, context, report);
  const [nextSnapshot, followup] = await prepare(repo);
  const draft = structuredClone(report);
  draft.evidence_digest = followup.report_template.evidence_digest;
  draft.previous_review_digest = saved.digest;
  draft.mode = "unchanged";
  draft.task.constraints = [];
  await assert.rejects(
    () => record(nextSnapshot, followup, draft),
    isWorkflowError(/changed task boundary/),
  );
  draft.task = report.task;
  draft.findings = [];
  draft.verdict = "ready";
  await assert.rejects(() => record(nextSnapshot, followup, draft), isWorkflowError(/stable IDs/));
  assert.equal(baseline(dirname(context.draft_path))[0], saved.digest);
});

test("severity does not override acceptance or scope", () => {
  const report = reportPayload();
  validateReport(report);
  report.verdict = "ready";
  assert.throws(() => validateReport(report), isWorkflowError(/not_ready/));
  report.findings[0].severity = "high";
  report.findings[0].origin = "new_requirement";
  report.findings[0].blocking = false;
  report.findings[0].summary = "Replace relations using guarded delete and create.";
  validateReport(report);
  report.findings[0].blocking = true;
  report.verdict = "not_ready";
  assert.throws(() => validateReport(report), isWorkflowError(/scope expansion/));
  report.findings[0].decision_evidence = "User chose replacement instead of rejection.";
  validateReport(report);
});

test("required checks prevent a ready verdict", () => {
  for (const [status, verdict] of [
    ["not_run", "blocked"],
    ["failed", "not_ready"],
  ]) {
    const report = reportPayload();
    report.findings = [];
    report.checks[0].status = status;
    report.verdict = verdict;
    validateReport(report);
    report.verdict = "ready";
    assert.throws(() => validateReport(report), isWorkflowError(new RegExp(verdict)));
  }
});

test("stale or superseded review preserves the baseline", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  const saved = await record(snapshot, context, report);
  await assert.rejects(
    () => record(snapshot, context, report),
    isWorkflowError(/baseline changed/),
  );
  const [nextSnapshot, followup] = await prepare(repo);
  const draft = structuredClone(report);
  draft.evidence_digest = followup.report_template.evidence_digest;
  draft.previous_review_digest = saved.digest;
  draft.mode = "unchanged";
  writeFileSync(join(repo, "renderer.txt"), "changed after review\n");
  await assert.rejects(
    () => record(nextSnapshot, followup, draft),
    isWorkflowError(/evidence changed/),
  );
  assert.equal(baseline(dirname(context.draft_path))[0], saved.digest);
});

test("explicit audit keeps history and a changed head falls back", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  await record(snapshot, context, report);
  const [, full] = await prepare(repo, "off");
  assert.equal(full.mode, "full");
  assert.deepEqual(full.report_template.findings, report.findings);
  git(repo, "commit", "-am", "fix");
  const [, fallback] = await prepare(repo);
  assert.equal(fallback.mode, "full");
  assert.equal(fallback.reason, "incompatible_boundary_or_incomplete_evidence");
  assert.deepEqual(fallback.previous_report.task, report.task);
});

test("corrupt baseline or missing snapshot selects an explicit full review", async (t) => {
  const repo = repository(t);
  const [snapshot, context, report] = await initialReport(repo);
  const saved = await record(snapshot, context, report);
  unlinkSync(snapshot);
  const bundle = await localBundle(repo, "code-review", null);
  const missing = prepareFollowup(bundle.artifact_root, bundle, "b".repeat(64), "auto");
  assert.equal(missing.mode, "full");
  assert.equal(missing.reason, "previous_evidence_unavailable");
  writeJson(saved.artifact_path, { damaged: true });
  const [, corrupted] = await prepare(repo);
  assert.equal(corrupted.reason, "previous_review_unavailable");
});

test("followup detects staging and untracked changes", async (t) => {
  const repo = repository(t);
  const note = join(repo, "example.txt");
  const removed = join(repo, "removed.txt");
  writeFileSync(note, "before\n");
  writeFileSync(removed, "remove this example\n");
  const [snapshot, context, report] = await initialReport(repo);
  await record(snapshot, context, report);
  git(repo, "add", "renderer.txt");
  writeFileSync(note, "after\n");
  unlinkSync(removed);
  const [, followup] = await prepare(repo);
  assert.deepEqual(
    new Set(Object.keys(followup.delta)),
    new Set(["staged", "unstaged", "untracked"]),
  );
  const changes = new Map(followup.delta.untracked.map((item) => [item.path, item]));
  assert.notEqual(
    changes.get("example.txt").before.sha256,
    changes.get("example.txt").after.sha256,
  );
  assert.equal(changes.get("removed.txt").after, null);
});

test("committed and WIP sections track the comparison boundary", async (t) => {
  const repo = repository(t);
  const initial = await localBundle(repo, "code-review", null);
  assert.equal(initial.sections.committed.diff, "");
  assert.ok(initial.sections.unstaged.diff.includes("broken"));
  assert.equal(initial.sections.staged.diff, "");
  git(repo, "branch", "review-base");
  git(repo, "commit", "-am", "change");
  const withRef = await localBundle(repo, "code-review", "review-base");
  assert.ok(withRef.sections.committed.diff.includes("broken"));
  assert.notEqual(withRef.base_sha, withRef.head_sha);
  assert.equal(withRef.sections.staged.diff, "");
  assert.equal(withRef.sections.unstaged.diff, "");
  assert.equal(withRef.retrieval_complete, true);
  const withoutRef = await localBundle(repo, "code-review", null);
  assert.equal(withoutRef.sections.committed.diff, "");
  writeFileSync(join(repo, "renderer.txt"), "staged\n");
  git(repo, "add", "renderer.txt");
  const staged = await localBundle(repo, "code-review", null);
  assert.ok(staged.sections.staged.diff.includes("diff --git"));
  assert.equal(staged.sections.unstaged.diff, "");
  writeFileSync(join(repo, "renderer.txt"), "again\n");
  const unstaged = await localBundle(repo, "code-review", null);
  assert.ok(unstaged.sections.staged.diff.includes("diff --git"));
  assert.ok(unstaged.sections.unstaged.diff.includes("diff --git"));
});

test("changed comparison ref invalidates freshness", async (t) => {
  const repo = repository(t);
  git(repo, "branch", "review-base");
  git(repo, "commit", "-am", "change");
  const bundle = await localBundle(repo, "code-review", "review-base");
  const [path] = await writeArtifact(bundle.artifact_root, "local_wip_snapshot", bundle);
  git(repo, "branch", "-f", "review-base", "HEAD");
  const result = await finalizeLocal(path);
  assert.equal(result.status, "stale");
  assert.ok(Array.isArray(result.changed));
  assert.ok(result.changed.includes("base_sha"));
});

test("empty local scope stops with an explicit reason instead of a review", async (t) => {
  const repo = repository(t);
  git(repo, "checkout", "--", "renderer.txt");
  let bundle = await localBundle(repo, "code-review", null);
  assert.equal(bundle.retrieval_complete, true);
  assert.equal(emptyScopeReason(bundle), "no_uncommitted_changes");

  git(repo, "branch", "merge-target");
  const withRef = await localBundle(repo, "code-review", "merge-target");
  assert.equal(withRef.sections.committed.diff, "");
  assert.equal(emptyScopeReason(withRef), "no_changes_relative_to_ref");

  writeFileSync(join(repo, "renderer.txt"), "wip\n");
  const wip = await localBundle(repo, "code-review", "merge-target");
  assert.equal(emptyScopeReason(wip), null);
  git(repo, "commit", "-qam", "accepted work");
  const committed = await localBundle(repo, "code-review", "merge-target");
  assert.ok(committed.sections.committed.diff.includes("diff --git"));
  assert.equal(emptyScopeReason(committed), null);
});

test("staged and unstaged sections stay separate when their changes cancel out", async (t) => {
  const repo = repository(t);
  writeFileSync(join(repo, "renderer.txt"), "broken\n");
  git(repo, "add", "renderer.txt");
  writeFileSync(join(repo, "renderer.txt"), "base\n");
  const bundle = await localBundle(repo, "code-review", null);
  assert.ok(bundle.sections.staged.diff.includes("+broken"));
  assert.ok(bundle.sections.unstaged.diff.includes("+base"));
  assert.equal(bundle.sections.committed.diff, "");
  assert.equal(emptyScopeReason(bundle), null);
});

test("missing, ambiguous, or unrelated comparison refs stop with concrete reasons", async (t) => {
  const repo = repository(t);
  await assert.rejects(
    () => localBundle(repo, "code-review", "missing-branch"),
    isWorkflowError(/comparison ref 'missing-branch' was not found/),
  );
  git(repo, "branch", "dup");
  git(repo, "-c", "tag.gpgsign=false", "tag", "-m", "duplicate name", "dup");
  await assert.rejects(
    () => localBundle(repo, "code-review", "dup"),
    isWorkflowError(/comparison ref 'dup' is ambiguous.*refs\/heads\/dup.*refs\/tags\/dup/),
  );
  const unambiguous = await localBundle(repo, "code-review", "refs/heads/dup");
  assert.equal(unambiguous.retrieval_complete, true);
  const originalBranch = git(repo, "rev-parse", "--abbrev-ref", "HEAD");
  git(repo, "checkout", "-q", "--orphan", "isolated");
  git(repo, "commit", "-q", "-m", "isolated", "--allow-empty");
  git(repo, "checkout", "-q", originalBranch);
  await assert.rejects(
    () => localBundle(repo, "code-review", "isolated"),
    isWorkflowError(/no common merge base between 'isolated' and HEAD/),
  );
});

test("a repeated run keeps the agreed comparison boundary", async (t) => {
  const repo = repository(t);
  git(repo, "branch", "merge-target");
  const bundle = await localBundle(repo, "code-review", "merge-target");
  const root = bundle.artifact_root;
  const [snapshot, digestValue] = await writeArtifact(root, "local_wip_snapshot", bundle);
  const first = prepareFollowup(root, bundle, digestValue, "auto");
  assert.equal(first.mode, "full");
  const report = reportPayload();
  report.evidence_digest = digestValue;
  writeJson(first.draft_path, report);
  await recordReview(dirname(first.draft_path), snapshot, first.draft_path);

  const again = await localBundle(repo, "code-review", "merge-target");
  const [, againDigest] = await writeArtifact(root, "local_wip_snapshot", again);
  const second = prepareFollowup(root, again, againDigest, "auto");
  assert.equal(second.mode, "unchanged");
  assert.equal(second.previous_ref, "merge-target");

  const drifted = await localBundle(repo, "code-review", null);
  const [, driftedDigest] = await writeArtifact(root, "local_wip_snapshot", drifted);
  const third = prepareFollowup(root, drifted, driftedDigest, "auto");
  assert.equal(third.mode, "full");
  assert.equal(third.reason, "incompatible_boundary_or_incomplete_evidence");
  assert.equal(third.previous_ref, "merge-target");
});

test("local preparation works without remotes and preserves HEAD, index, and tree", async (t) => {
  const repo = repository(t);
  assert.equal(git(repo, "remote"), "");
  const headBefore = git(repo, "rev-parse", "HEAD");
  const indexBefore = readFileSync(join(repo, ".git", "index"));
  const statusBefore = git(repo, "status", "--porcelain");
  const bundle = await localBundle(repo, "code-review", null);
  const [path] = await writeArtifact(bundle.artifact_root, "local_wip_snapshot", bundle);
  assert.equal(git(repo, "rev-parse", "HEAD"), headBefore);
  assert.deepEqual(readFileSync(join(repo, ".git", "index")), indexBefore);
  assert.equal(git(repo, "status", "--porcelain"), statusBefore);
  assert.equal(existsSync(`${repo}.worktrees`), false);
  assert.ok(!path.startsWith(repo));
  assert.ok(!String(bundle.artifact_root).startsWith(repo));
});

test("an existing linked worktree is reviewed in place", async (t) => {
  const repo = repository(t);
  const nested = join(dirname(repo), "linked-checkout");
  git(repo, "worktree", "add", "-q", nested, "-b", "topic");
  writeFileSync(join(nested, "renderer.txt"), "touched in the worktree\n");
  writeFileSync(join(nested, "note.txt"), "untracked\n");
  const bundle = await localBundle(nested, "code-review", null);
  assert.equal(bundle.repo_root, realpathSync(nested));
  assert.ok(bundle.sections.unstaged.diff.includes("touched in the worktree"));
  assert.deepEqual(
    bundle.sections.untracked.items.map((item) => item.path),
    ["note.txt"],
  );
  assert.equal(bundle.retrieval_complete, true);
});

test("untracked symlinks and unreadable files mark the evidence incomplete", async (t) => {
  const repo = repository(t);
  symlinkSync("renderer.txt", join(repo, "link.txt"));
  writeFileSync(join(repo, "note.txt"), "private\n");
  chmodSync(join(repo, "note.txt"), 0o000);
  const bundle = await localBundle(repo, "code-review", null);
  const items = new Map(bundle.sections.untracked.items.map((item) => [item.path, item]));
  assert.deepEqual(items.get("link.txt"), {
    path: "link.txt",
    complete: false,
    reason: "symlink",
  });
  if (process.getuid !== undefined && process.getuid() !== 0) {
    assert.deepEqual(items.get("note.txt"), {
      path: "note.txt",
      complete: false,
      reason: "unreadable",
    });
  }
  assert.ok(bundle.sections.untracked.errors.includes("link.txt"));
  assert.equal(bundle.sections.untracked.complete, false);
  assert.equal(bundle.retrieval_complete, false);
});

test("finalize-local rejects non-repository and symlinked roots", async (t) => {
  const repo = repository(t);
  const bundle = await localBundle(repo, "code-review", null);
  const [path] = await writeArtifact(bundle.artifact_root, "local_wip_snapshot", bundle);
  assert.equal((await finalizeLocal(path)).status, "ok");
  const plain = mkdtempSync(join(tmpdir(), "local-review-plain-"));
  t.after(() => rmSync(plain, { recursive: true, force: true }));
  await assert.rejects(
    () => localBundle(plain, "code-review", null),
    isWorkflowError(/repo root must be a real Git checkout/),
  );
  const linked = mkdtempSync(join(tmpdir(), "local-review-linked-"));
  t.after(() => rmSync(linked, { recursive: true, force: true }));
  symlinkSync(repo, join(linked, "repo"));
  await assert.rejects(
    () => localBundle(join(linked, "repo"), "code-review", null),
    isWorkflowError(/repo root must not be a symbolic link/),
  );
});
