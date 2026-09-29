import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { WorkflowError, allowedEndpoint, component } from "../dist/contract.js";
import { labelCatalog, validateLabelAssessments } from "../dist/label-assessment.js";
import {
  collect,
  evidenceIsValid,
  reportLines,
  template,
  validate,
} from "../dist/review-semver.js";

function isWorkflowError(message) {
  return (error) => {
    assert.ok(error instanceof WorkflowError);
    assert.match(error.message, message);
    return true;
  };
}

function temporaryDirectory(t) {
  const root = mkdtempSync(join(tmpdir(), "review-semver-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function git(repo, ...args) {
  const result = spawnSync("git", ["-C", repo, ...args], { encoding: "utf8" });
  assert.equal(result.status, 0, `git ${args.join(" ")} failed: ${result.stderr}`);
  return result.stdout.trim();
}

function fallbackAssessment(targetSha = "b") {
  return {
    mode: "target_fallback",
    policy: "No publication policy could be established from repository documentation or CI.",
    sources: ["README.md and CI configuration at the reviewed head; empty release catalog"],
    baseline: null,
    target_branch: "main",
    target_sha: targetSha,
    target_revision: "mr_snapshot",
    fallback_reason: "No confirmed publication baseline is available.",
    release_impact: null,
    release_rationale: null,
  };
}

function releaseAssessment(releaseSha = "a", targetSha = "b") {
  return {
    ...fallbackAssessment(targetSha),
    mode: "release",
    policy: "Stable v1 tags are published by the documented release job.",
    sources: ["docs/releases.md at the target revision", "GitLab release v1.4.0"],
    baseline: { name: "v1.4.0", sha: releaseSha, source: "releases" },
    target_revision: "current",
    fallback_reason: null,
    release_impact: "major",
    release_rationale: "Target already removes a released API; the MR fixes a compatible bug.",
  };
}

function releaseContext(t) {
  const repo = temporaryDirectory(t);
  git(repo, "init", "--quiet");
  git(repo, "config", "commit.gpgsign", "false");
  for (const value of ["released API\n", "pending breaking change\n"]) {
    writeFileSync(join(repo, "api.txt"), value);
    git(repo, "add", "api.txt");
    git(
      repo,
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.invalid",
      "commit",
      "-qm",
      "Change API",
    );
  }
  const target = git(repo, "rev-parse", "HEAD");
  const released = git(repo, "rev-parse", "HEAD~1");
  const catalog = component([{ tag_name: "v1.4.0", commit: { id: released } }]);
  const evidence = { start_sha: target, object: { target_branch: "main" } };
  const context = {
    exact_git: { repo_root: repo },
    release_evidence: {
      target_branch: "main",
      target_sha: target,
      releases: catalog,
      tags: component(),
      errors: [],
    },
  };
  return { evidence, context, assessment: releaseAssessment(released, target) };
}

function semverLabelEvidence(names) {
  return {
    object: { labels: [] },
    labels: component(
      names.map(([name, description]) => ({ name: name, description: description })),
    ),
  };
}

function assessmentItems(names, statusByName) {
  return names.map((name) => ({
    name: name,
    status: statusByName[name],
    rationale: `${name} rationale.`,
  }));
}

test("release major assessment keeps a patch MR label", (t) => {
  const { evidence, context, assessment } = releaseContext(t);
  assert.deepEqual(validate(assessment, evidence, context), assessment);
  const labelsEvidence = semverLabelEvidence([
    ["semver::major", "Breaking compatibility"],
    ["semver::patch", "Backward-compatible fix"],
  ]);
  const labels = validateLabelAssessments(
    labelsEvidence,
    assessmentItems(
      labelsEvidence.labels.items.map((item) => item.name),
      {
        "semver::major": "inapplicable",
        "semver::patch": "applicable",
      },
    ),
    "patch",
  );
  assert.deepEqual(labels.add, ["semver::patch"]);
  assert.deepEqual(labels.semver, {
    impact: "patch",
    candidates: ["semver::patch"],
    selected: "semver::patch",
  });
  assert.deepEqual(labels.proposed, ["semver::patch"]);
  assert.equal(labels.complete, true);
  const content = {
    semver_impact: "patch",
    semver_rationale: "Compatible fix.",
    semver_assessment: assessment,
  };
  const report = reportLines(content, "en").join("\n");
  assert.match(report, /MR contribution \/ label:\*\* PATCH/);
  assert.match(report, /Next release:\*\* MAJOR/);
  assert.ok(report.includes("v1.4.0"));
  assert.ok(!report.includes(assessment.baseline.sha));
});

test("minor and patch semver impacts map onto the matching compatibility label", () => {
  const catalogNames = [
    ["semver::major", "Breaking compatibility"],
    ["semver::minor", "New backward-compatible capability"],
    ["semver::patch", "Backward-compatible fix"],
  ];
  for (const impact of ["minor", "patch"]) {
    const labelsEvidence = semverLabelEvidence(catalogNames);
    const statusByName = Object.fromEntries(
      catalogNames.map(([name]) => [
        name,
        name === `semver::${impact}` ? "applicable" : "unresolved",
      ]),
    );
    const labels = validateLabelAssessments(
      labelsEvidence,
      assessmentItems(
        catalogNames.map(([name]) => name),
        statusByName,
      ),
      impact,
    );
    assert.deepEqual(labels.add, [`semver::${impact}`]);
    assert.deepEqual(labels.semver.candidates, [`semver::${impact}`]);
    assert.equal(labels.semver.selected, `semver::${impact}`);
    assert.deepEqual(
      labels.unresolved,
      catalogNames
        .filter(([name]) => name !== `semver::${impact}`)
        .map(([name]) => name)
        .sort((left, right) => left.toLowerCase().localeCompare(right.toLowerCase())),
    );
  }
});

test("label assessments reject invalid shapes and incomplete coverage", () => {
  const evidence = semverLabelEvidence([
    ["semver::major", "Breaking compatibility"],
    ["semver::patch", "Backward-compatible fix"],
  ]);
  const valid = assessmentItems(
    evidence.labels.items.map((item) => item.name),
    {
      "semver::major": "unresolved",
      "semver::patch": "applicable",
    },
  );
  assert.throws(
    () => validateLabelAssessments(evidence, { name: "semver::patch" }, "patch"),
    isWorkflowError(/label assessments must be an array/),
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        evidence,
        [{ name: "semver::patch", status: "applicable" }],
        "patch",
      ),
    isWorkflowError(/label assessment is invalid/),
  );
  assert.throws(
    () => validateLabelAssessments(evidence, valid.slice(0, 1), "patch"),
    isWorkflowError(/label assessments must cover the complete project catalog/),
  );
  assert.throws(
    () => validateLabelAssessments(evidence, [...valid, valid[0]], "patch"),
    isWorkflowError(/label assessment is invalid/),
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        { object: { labels: [] }, labels: component([], { complete: false }) },
        [],
        "patch",
      ),
    isWorkflowError(/project label catalog is incomplete/),
  );
  const duplicateNames = {
    object: { labels: [] },
    labels: component([
      { name: "semver::major", description: "Breaking compatibility" },
      { name: "semver::patch", description: "Backward-compatible fix" },
      { name: "semver::patch", description: "Another fix label" },
    ]),
  };
  assert.throws(
    () => labelCatalog(duplicateNames),
    isWorkflowError(/project label catalog contains duplicate names/),
  );
});

test("semver impact requires the matching compatibility label and forbids incompatible ones", () => {
  const catalogNames = [
    ["semver::major", "Breaking compatibility"],
    ["semver::minor", "New backward-compatible capability"],
    ["semver::patch", "Backward-compatible fix"],
  ];
  const evidence = semverLabelEvidence(catalogNames);
  assert.throws(
    () =>
      validateLabelAssessments(
        evidence,
        assessmentItems(
          catalogNames.map(([name]) => name),
          {
            "semver::major": "unresolved",
            "semver::minor": "unresolved",
            "semver::patch": "inapplicable",
          },
        ),
        "patch",
      ),
    isWorkflowError(/SemVer impact requires the matching compatibility label/),
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        evidence,
        assessmentItems(
          catalogNames.map(([name]) => name),
          {
            "semver::major": "applicable",
            "semver::minor": "unresolved",
            "semver::patch": "applicable",
          },
        ),
        "patch",
      ),
    isWorkflowError(/an incompatible SemVer label cannot be assessed as applicable/),
  );
});

test("ambiguous compatibility labels must remain unresolved", () => {
  const evidence = {
    object: { labels: [] },
    labels: component([
      { name: "semver::patch", description: "Backward-compatible fix" },
      { name: "compatibility::fix", description: "Another patch label" },
    ]),
  };
  const names = ["semver::patch", "compatibility::fix"];
  assert.equal(
    validateLabelAssessments(
      evidence,
      assessmentItems(names, {
        "semver::patch": "unresolved",
        "compatibility::fix": "unresolved",
      }),
      "patch",
    ).semver.selected,
    null,
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        evidence,
        assessmentItems(names, {
          "semver::patch": "applicable",
          "compatibility::fix": "unresolved",
        }),
        "patch",
      ),
    isWorkflowError(/ambiguous SemVer compatibility labels must remain unresolved/),
  );
});

test("current MR labels must match the complete catalog without duplicates", () => {
  const catalogNames = [["semver::patch", "Backward-compatible fix"]];
  const labelsEvidence = semverLabelEvidence(catalogNames);
  const items = assessmentItems(
    catalogNames.map(([name]) => name),
    { "semver::patch": "applicable" },
  );
  assert.deepEqual(
    validateLabelAssessments(
      { ...labelsEvidence, object: { labels: ["semver::patch"] } },
      items,
      "patch",
    ).remove,
    [],
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        { ...labelsEvidence, object: { labels: ["unknown"] } },
        items,
        "patch",
      ),
    isWorkflowError(/current MR labels do not match the complete catalog/),
  );
  assert.throws(
    () =>
      validateLabelAssessments(
        { ...labelsEvidence, object: { labels: ["semver::patch", "semver::patch"] } },
        items,
        "patch",
      ),
    isWorkflowError(/current MR labels do not match the complete catalog/),
  );
  assert.throws(
    () => validateLabelAssessments({ ...labelsEvidence, object: {} }, items, "patch"),
    isWorkflowError(/current MR labels are unavailable/),
  );
});

test("release assessment rejects unbound evidence", (t) => {
  const cases = ["missing", "moved", "incomplete", "upcoming", "target"];
  for (const caseName of cases) {
    const { evidence, context, assessment } = releaseContext(t);
    const catalog = context.release_evidence.releases;
    if (caseName === "missing") {
      catalog.items = [];
    } else if (caseName === "moved") {
      catalog.items[0].commit.id = assessment.target_sha;
    } else if (caseName === "incomplete") {
      catalog.complete = false;
    } else if (caseName === "upcoming") {
      catalog.items[0].upcoming_release = true;
    } else {
      context.release_evidence.target_sha = assessment.baseline.sha;
    }
    assert.throws(
      () => validate(assessment, evidence, context),
      isWorkflowError(/SemVer/),
      caseName,
    );
  }
});

test("unknown policy is an explicit fallback without release claim", () => {
  const evidence = { start_sha: "b", object: { target_branch: "main" } };
  const context = { release_evidence: { target_branch: "main", target_sha: null } };
  const assessment = fallbackAssessment();
  assert.deepEqual(validate(assessment, evidence, context), assessment);
  const content = {
    semver_impact: "patch",
    semver_rationale: "Compatible fix.",
    semver_assessment: assessment,
  };
  for (const [locale, expected] of [
    ["en", "target-branch fallback"],
    ["ru", "fallback относительно целевой ветки"],
  ]) {
    const report = reportLines(content, locale).join("\n");
    assert.ok(report.includes(expected));
    assert.ok(report.includes("main"));
    assert.ok(!report.includes("Next release") && !report.includes("Будущий релиз"));
    assert.ok(report.includes(assessment.fallback_reason));
  }
  for (const invalid of [
    { ...assessment, fallback_reason: "" },
    { ...assessment, release_impact: "patch" },
    { ...assessment, baseline: { name: "main", sha: "b", source: "tags" } },
    { ...assessment, sources: [] },
  ]) {
    assert.throws(() => validate(invalid, evidence, context), isWorkflowError(/SemVer/));
  }
});

test("current target falls back when the commit is unavailable locally", (t) => {
  const { evidence, context } = releaseContext(t);
  const unavailable = "f".repeat(40);
  context.release_evidence.target_sha = unavailable;
  const assessment = fallbackAssessment(evidence.start_sha);

  assert.equal(template(evidence, context).target_revision, "mr_snapshot");
  assert.deepEqual(validate(assessment, evidence, context), assessment);

  const current = { ...assessment, target_sha: unavailable, target_revision: "current" };
  assert.throws(() => validate(current, evidence, context), isWorkflowError(/SemVer/));
});

test("release-only commit need not be a target ancestor", (t) => {
  const { evidence, context, assessment } = releaseContext(t);
  const repo = context.exact_git.repo_root;
  const parent = assessment.baseline.sha;
  const tree = git(repo, "rev-parse", `${parent}^{tree}`);
  const release = spawnSync(
    "git",
    [
      "-C",
      repo,
      "-c",
      "user.name=Test",
      "-c",
      "user.email=test@example.invalid",
      "commit-tree",
      tree,
      "-p",
      parent,
      "-m",
      "Release bookkeeping",
    ],
    { encoding: "utf8" },
  );
  assert.equal(release.status, 0, release.stderr);
  assessment.baseline.sha = release.stdout.trim();
  context.release_evidence.releases.items[0].commit.id = release.stdout.trim();
  assert.deepEqual(validate(assessment, evidence, context), assessment);
});

test("collection keeps catalog failures non-blocking", () => {
  const result = collect({
    project: { hostname: "GitLab..Example", id: 19 },
    object: { target_branch: "release/1.x" },
  });
  assert.equal(evidenceIsValid(result), true);
  assert.equal(result.target_branch, "release/1.x");
  assert.equal(result.target_sha, null);
  assert.equal(result.releases.complete, false);
  assert.equal(result.tags.complete, false);
  assert.equal(result.errors.length, 1);
  assert.equal(allowedEndpoint("projects/19/repository/branches/release%2F1.x"), true);
  assert.equal(allowedEndpoint("projects/19/releases?per_page=100&page=2"), true);
  assert.equal(allowedEndpoint("projects/19/repository/tags?per_page=100&page=2"), true);
  assert.equal(allowedEndpoint("projects/19/repository/branches/main/protect"), false);
});
