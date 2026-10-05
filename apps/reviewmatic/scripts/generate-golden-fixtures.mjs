// Generate (or byte-check) the committed golden parity fixtures that the
// reviewmatic Python port asserts against. The expected values are computed
// with the real TypeScript CLI sources through the resolve hook, so any drift
// between the two implementations turns the Python parity tests red.
//
// Prerequisite: `apps/reviewmatic/src/generated/artifact-schema.ts` exists
// (run `node scripts/materialize_cli_runtime.mjs` once in a fresh checkout).
// `--check` regenerates in memory and fails on any byte difference.
import { registerHooks } from "node:module";
import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { resolve as resolveTypeScript } from "./golden-ts-loader.mjs";

registerHooks({ resolve: resolveTypeScript });

const scriptDir = import.meta.dirname;
const goldenDir = resolve(scriptDir, "../../reviewmatic-py/tests/golden");
const sourceDir = resolve(scriptDir, "../src/generated");
if (!existsSync(join(sourceDir, "artifact-schema.ts")))
  throw new Error(
    "materialized TypeScript sources are missing; run node scripts/materialize_cli_runtime.mjs",
  );

const { digest, labelIntentIsValid, validateV2Artifact } = await import(
  new URL("../src/contract.ts", import.meta.url).href
);
const { assessmentIsValid, evidenceIsValid } = await import(
  new URL("../src/review-semver.ts", import.meta.url).href
);
const { analysisFingerprint, draftGaps } = await import(
  new URL("../src/draft.ts", import.meta.url).href
);
const { bindQuestionContexts, extractSupersededResults } = await import(
  new URL("../src/context-package.ts", import.meta.url).href
);

const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);

const component = () => ({ items: [], complete: true, errors: [], pages: 0, truncated: false });

const localReviewReport = (overrides = {}) => ({
  schema: "portable-gitlab/local_review_report/v2",
  schema_version: 2,
  kind: "local_review_report",
  created_at: "2026-10-05T00:00:00+00:00",
  payload: {
    evidence_digest: SHA_A,
    previous_review_digest: null,
    mode: "full",
    task: {
      goal: "Review the local WIP changes.",
      acceptance_criteria: ["No blocking findings remain."],
      constraints: [],
      accepted_risks: [],
      deferred: [],
      decision_evidence: "Recorded decision receipt.",
    },
    task_change_reason: null,
    findings: [],
    checks: [
      {
        name: "Freshness",
        status: "passed",
        required: true,
        evidence: "HEAD digest matches the recorded bundle.",
      },
    ],
    assessment: "Ready for review finalization.",
    verdict: "ready",
    external_mutations: false,
  },
  ...overrides,
});

const evidenceSnapshot = (overrides = {}) => ({
  schema: "portable-gitlab/evidence_snapshot/v2",
  schema_version: 2,
  kind: "evidence_snapshot",
  created_at: "2026-10-05T00:00:00+00:00",
  payload: {
    schema_version: 2,
    profile: "code-review",
    external_mutations: false,
    target: {
      url: "https://gitlab.com/group/project/-/merge_requests/1",
      hostname: "gitlab.com",
      project_path: "group/project",
      kind: "merge_requests",
      iid: 1,
    },
    project: { id: 1, path: "group/project" },
    object: { iid: 1, state: "opened" },
    labels: component(),
    changed_files: component(),
    commits: component(),
    pipelines: component(),
    discussions: component(),
    head_sha: SHA_A,
    base_sha: SHA_B,
    start_sha: SHA_A,
    artifact_root: "/tmp/reviewmatic-artifacts",
    prepared_at: "2026-10-05T00:00:00+00:00",
    components_complete: {
      project: true,
      labels: true,
      object: true,
      changed_files: true,
      commits: true,
      pipelines: true,
      discussions: true,
    },
    retrieval_complete: true,
  },
  ...overrides,
});

const labelIntent = (changeType) => ({
  change_type: changeType,
  workflow_state: "review",
  urgency: "urgent",
  impact: "high",
  compatibility: "minor",
  origin: "external",
});

const semverEvidence = (overrides = {}) => ({
  target_branch: "main",
  target_sha: SHA_B,
  releases: component(),
  tags: component(),
  errors: [],
  ...overrides,
});

const semverAssessment = (overrides = {}) => ({
  mode: "release",
  policy: "Stable v1 tags are published by the documented release job.",
  sources: ["docs/releases.md at the target revision", "GitLab release v1.4.0"],
  baseline: { name: "v1.4.0", sha: SHA_A, source: "releases" },
  target_branch: "main",
  target_sha: SHA_B,
  target_revision: "current",
  fallback_reason: null,
  release_impact: "major",
  release_rationale: "Target already removes a released API; the MR fixes a compatible bug.",
  ...overrides,
});

const contextPackagePayload = (mode = "mr", includeRegistry = mode === "mr") => {
  const payload = {
    schema: "portable-gitlab/context-package/v2",
    mode,
    binding: {
      evidence_digest: SHA_A,
      artifact_root: "/tmp/reviewmatic-artifacts",
      repo_root: "/tmp/reviewmatic-checkout",
      base_sha: SHA_B,
      head_sha: SHA_B,
      start_sha: SHA_B,
    },
    goal: { status: "known", text: "Review the merge request delta." },
    acceptance_criteria: { status: "known", items: ["No blocking findings remain."] },
    background: "The MR fixes the recorded regression.",
    claims: [],
    constraints: [],
    prior_decisions: [],
    questions: [],
    ...(includeRegistry ? { thread_registry: [] } : {}),
    supersedes: null,
    external_mutations: false,
  };
  return payload;
};

const contextPackage = (payload = contextPackagePayload()) => ({
  schema: "portable-gitlab/context_package/v2",
  schema_version: 2,
  kind: "context_package",
  created_at: "2026-10-05T00:00:00+00:00",
  payload,
});

// Draft state-machine transitions. The inputs are plain data; the outputs are
// emitted by the real TypeScript transition functions so the Python port
// reproduces the exact gap report, the exact retirement of stale results into
// history, and the exact CI-only versus material analysis fingerprint.
const draftBase = (overrides = {}) => ({
  findings: [],
  critics: [],
  dispositions: [],
  critic_count: 1,
  ci_job_assessments: [],
  run_id: "primary-run",
  session_id: "primary-session",
  context_package_path: "/tmp/reviewmatic-artifacts/artifacts/context_package/package.json",
  content: {
    summary: "The bounded change meets the agreed contract.",
    architecture_assessment: "Existing ownership is preserved.",
    semver_rationale: "Backward-compatible correction.",
    chat_assessment: { necessity: { status: "supported", rationale: "Unbounded timeout." } },
    mr_metadata_assessment: { title: { status: "ok", rationale: "Sufficient." } },
    label_assessments: [],
    thread_decisions: [],
  },
  ...overrides,
});

const criticFinding = (id) => ({ id, severity: "medium", summary: `Finding ${id}` });

const panelDraft = (overrides = {}) =>
  draftBase({
    critic_count: 2,
    findings: [criticFinding("own-1")],
    critics: [
      { run_id: "run-a", session_id: "session-a", findings: [criticFinding("critic-a-1")] },
    ],
    dispositions: [{ id: "own-1", decision: "accept" }],
    participants: {
      critics: [
        { name: "critic-general", receipt: { run_id: "run-a", session_id: "session-a" } },
        { name: "critic-plain" },
      ],
      arbitrator: { name: "arb-main" },
    },
    ...overrides,
  });

const supersedeQuestion = (id, subject) => ({
  id,
  subject,
  source: "Discussion 42 of the collected evidence",
  critic: true,
});

const boundPackage = (questions, overrides = {}) => {
  const payload = { ...contextPackagePayload(), questions, ...overrides };
  bindQuestionContexts(payload);
  return payload;
};

const boundResult = (payload, questionId, extra = {}) => ({
  question_id: questionId,
  verdict: "confirmed",
  evidence: "Inspected the exact head.",
  context_digest: payload.questions.find((item) => item.id === questionId).context_digest,
  ...extra,
});

const retirementInput = (previousPayload, nextPayload, answers, verifications = []) => ({
  previous:
    previousPayload === null ? null : { payload: previousPayload, digest: digest(previousPayload) },
  next: nextPayload,
  answers,
  verifications,
});

const retireBefore = boundPackage([supersedeQuestion("q-retry", "Does the head set the key?")]);
const retireAfter = boundPackage([
  supersedeQuestion("q-retry", "Is credential revocation enforced when a key is reused?"),
]);
const twoBefore = boundPackage([
  supersedeQuestion("q-retry", "Does the head set the key?"),
  supersedeQuestion("q-caller", "Do existing callers pass a stable key?"),
]);
const twoAfter = boundPackage([
  supersedeQuestion("q-retry", "Is credential revocation enforced when a key is reused?"),
  supersedeQuestion("q-caller", "Do existing callers pass a stable key?"),
]);
const decisionBefore = boundPackage([supersedeQuestion("q-stable", "Is the boundary kept?")], {
  prior_decisions: [{ id: "deferral", decision: "Revocation is deferred.", source: "User" }],
});
const decisionAfter = boundPackage([supersedeQuestion("q-stable", "Is the boundary kept?")], {
  prior_decisions: [
    { id: "deferral", decision: "Revocation is deferred.", source: "User" },
    { id: "correction", decision: "The deferral is withdrawn.", source: "User" },
  ],
});

const analysisEvidence = (objectOverrides = {}, pipelines = { items: [] }) => ({
  ...evidenceSnapshot().payload,
  object: {
    iid: 1,
    state: "opened",
    title: "Bound retry",
    labels: [],
    sha: SHA_A,
    has_conflicts: false,
    updated_at: "2026-10-05T00:00:00Z",
    head_pipeline: { id: 1, status: "running" },
    pipeline: { id: 1, status: "running" },
    latest_build_started_at: "2026-10-05T00:00:00Z",
    latest_build_finished_at: null,
    ...objectOverrides,
  },
  pipelines: { ...component(), ...pipelines },
});

const artifactValidity = (artifact, kind) => {
  try {
    validateV2Artifact(artifact, kind);
    return true;
  } catch {
    return false;
  }
};

const cases = [
  {
    name: "canonical-scalars",
    kind: "canonical_digest",
    expectValid: true,
    input: {
      text: "кириллица and emoji \u{1F600}",
      escaped: 'quote " backslash \\ newline \n tab \t control \u0001',
      integer: 0,
      negative: -12,
      decimal: 3.5,
      truthy: true,
      falsy: false,
      nothing: null,
    },
  },
  {
    name: "canonical-key-order",
    kind: "canonical_digest",
    expectValid: true,
    input: {
      zeta: 1,
      alpha: { b: 2, a: 1, Я: 3, omega: 4 },
      middle: [{ second: true, first: false }, "", [], {}],
    },
  },
  {
    name: "canonical-unicode-order",
    kind: "canonical_digest",
    expectValid: true,
    input: Object.fromEntries(
      ["\u00e9t\u00e9", "e\u0301clair", "\u{1F600}lead", "zeta", "ALPHA", "alpha"].map(
        (key, index) => [`k${index}`, key],
      ),
    ),
  },
  {
    name: "canonical-containers",
    kind: "canonical_digest",
    expectValid: true,
    input: { list: [1, [2, [3, null]], [], {}], nested: { deep: { deeper: { empty: {} } } } },
  },
  {
    name: "artifact-local-review-report-valid",
    kind: "artifact_validation_v2",
    input: { kind: "local_review_report", artifact: localReviewReport() },
    expectValid: true,
  },
  {
    name: "artifact-local-review-report-foreign-field",
    kind: "artifact_validation_v2",
    input: { kind: "local_review_report", artifact: localReviewReport({ extra: 1 }) },
    expectValid: false,
  },
  {
    name: "artifact-local-review-report-legacy-version",
    kind: "artifact_validation_v2",
    input: { kind: "local_review_report", artifact: localReviewReport({ schema_version: 1 }) },
    expectValid: false,
  },
  {
    name: "artifact-local-review-report-invalid-timestamp",
    kind: "artifact_validation_v2",
    input: {
      kind: "local_review_report",
      artifact: localReviewReport({ created_at: "2026-13-45T99:00:00Z" }),
    },
    expectValid: false,
  },
  {
    name: "artifact-evidence-snapshot-valid",
    kind: "artifact_validation_v2",
    input: { kind: "evidence_snapshot", artifact: evidenceSnapshot() },
    expectValid: true,
  },
  {
    name: "artifact-kind-mismatch",
    kind: "artifact_validation_v2",
    input: { kind: "evidence_snapshot", artifact: localReviewReport() },
    expectValid: false,
  },
  {
    name: "artifact-context-package-valid",
    kind: "artifact_validation_v2",
    input: { kind: "context_package", artifact: contextPackage() },
    expectValid: true,
  },
  {
    name: "artifact-context-package-local-mode",
    kind: "artifact_validation_v2",
    input: { kind: "context_package", artifact: contextPackage(contextPackagePayload("local")) },
    expectValid: true,
  },
  {
    name: "artifact-context-package-mr-needs-registry",
    kind: "artifact_validation_v2",
    input: {
      kind: "context_package",
      artifact: contextPackage(contextPackagePayload("mr", false)),
    },
    expectValid: false,
  },
  {
    name: "artifact-context-package-unbound-evidence",
    kind: "artifact_validation_v2",
    input: {
      kind: "context_package",
      artifact: contextPackage({
        ...contextPackagePayload(),
        binding: { ...contextPackagePayload().binding, evidence_digest: "not-a-digest" },
      }),
    },
    expectValid: false,
  },
  {
    name: "semver-evidence-valid",
    kind: "semver_evidence",
    input: semverEvidence(),
    expectValid: true,
  },
  {
    name: "semver-evidence-incomplete-component",
    kind: "semver_evidence",
    input: semverEvidence({ tags: { items: [], complete: false, errors: [], pages: 0 } }),
    expectValid: false,
  },
  {
    name: "semver-assessment-release",
    kind: "semver_assessment",
    input: semverAssessment(),
    expectValid: true,
  },
  {
    name: "semver-assessment-fallback",
    kind: "semver_assessment",
    input: semverAssessment({
      mode: "target_fallback",
      sources: ["README.md and CI configuration at the reviewed head; empty release catalog"],
      baseline: null,
      target_revision: "mr_snapshot",
      fallback_reason: "No confirmed publication baseline is available.",
      release_impact: null,
      release_rationale: null,
    }),
    expectValid: true,
  },
  {
    name: "semver-assessment-missing-baseline",
    kind: "semver_assessment",
    input: semverAssessment({ baseline: null }),
    expectValid: false,
  },
  {
    name: "label-intent-valid",
    kind: "label_intent",
    input: labelIntent("bug"),
    expectValid: true,
  },
  {
    name: "label-intent-unknown-value",
    kind: "label_intent",
    input: labelIntent("sideways"),
    expectValid: false,
  },
  {
    name: "label-intent-extra-role",
    kind: "label_intent",
    input: { ...labelIntent("bug"), priority: "urgent" },
    expectValid: false,
  },
  {
    name: "draft-gaps-fresh",
    kind: "draft_gaps",
    expectValid: true,
    input: draftBase({
      run_id: "",
      session_id: "",
      context_package_path: null,
      critic_count: 2,
      findings: [criticFinding("own-1")],
      ci_job_assessments: [{ job: "build", classification: "unknown" }],
      content: {
        summary: "",
        architecture_assessment: "",
        semver_rationale: "",
        chat_assessment: { necessity: { status: "unconfirmed", rationale: "" } },
        mr_metadata_assessment: { title: { status: "unverified", rationale: "" } },
        label_assessments: [{ name: "semver::patch", status: "unresolved", rationale: "" }],
        thread_decisions: [{ id: "42", rationale: "" }],
      },
    }),
  },
  {
    name: "draft-gaps-complete",
    kind: "draft_gaps",
    expectValid: true,
    input: draftBase({
      findings: [criticFinding("own-1")],
      dispositions: [{ id: "own-1", decision: "accept" }],
    }),
  },
  {
    name: "draft-gaps-panel-awaiting-receipt",
    kind: "draft_gaps",
    expectValid: true,
    input: panelDraft(),
  },
  {
    name: "draft-gaps-panel-awaiting-arbitration",
    kind: "draft_gaps",
    expectValid: true,
    input: panelDraft({
      critics: [
        { run_id: "run-a", session_id: "session-a", findings: [criticFinding("critic-a-1")] },
        { run_id: "run-b", session_id: "session-b", findings: [] },
      ],
      participants: {
        critics: [
          { name: "critic-general", receipt: { run_id: "run-a", session_id: "session-a" } },
          { name: "critic-plain", receipt: { run_id: "run-b", session_id: "session-b" } },
        ],
        arbitrator: { name: "arb-main" },
      },
    }),
  },
  {
    name: "retirement-edited-question",
    kind: "superseded_results",
    expectValid: true,
    input: retirementInput(retireBefore, retireAfter, [boundResult(retireBefore, "q-retry")]),
  },
  {
    name: "retirement-keeps-unaffected-question",
    kind: "superseded_results",
    expectValid: true,
    input: retirementInput(
      twoBefore,
      twoAfter,
      [boundResult(twoBefore, "q-retry"), boundResult(twoBefore, "q-caller")],
      [boundResult(twoBefore, "q-retry", { original: { run_id: "run-a", session_id: "s-a" } })],
    ),
  },
  {
    name: "retirement-prior-decision-change",
    kind: "superseded_results",
    expectValid: true,
    input: retirementInput(decisionBefore, decisionAfter, [
      boundResult(decisionBefore, "q-stable"),
    ]),
  },
  {
    name: "retirement-unbound-answer-without-previous",
    kind: "superseded_results",
    expectValid: true,
    input: retirementInput(null, retireAfter, [
      { question_id: "q-retry", verdict: "confirmed", evidence: "Collected before binding." },
    ]),
  },
  {
    name: "retirement-nothing-stale",
    kind: "superseded_results",
    expectValid: true,
    input: retirementInput(retireAfter, retireAfter, [boundResult(retireAfter, "q-retry")]),
  },
  {
    name: "analysis-fingerprint-ci-only-drift",
    kind: "analysis_fingerprint",
    expectValid: true,
    input: analysisEvidence(
      {
        updated_at: "2026-10-05T01:00:00Z",
        head_pipeline: { id: 2, status: "success" },
        pipeline: { id: 2, status: "success" },
        latest_build_started_at: "2026-10-05T01:00:00Z",
        latest_build_finished_at: "2026-10-05T01:00:10Z",
      },
      { items: [{ id: 2, status: "success" }] },
    ),
  },
  {
    name: "analysis-fingerprint-material-change",
    kind: "analysis_fingerprint",
    expectValid: true,
    input: analysisEvidence({ title: "Other scope", labels: ["blocking"], has_conflicts: true }),
  },
];

const validators = {
  canonical_digest: () => true,
  artifact_validation_v2: (input) => artifactValidity(input.artifact, input.kind),
  semver_evidence: (input) => evidenceIsValid(input),
  semver_assessment: (input) => assessmentIsValid(input),
  label_intent: (input) => labelIntentIsValid(input),
  draft_gaps: () => true,
  superseded_results: () => true,
  analysis_fingerprint: () => true,
};

// Transition outputs emitted by the TypeScript functions, keyed by fixture kind.
const outputs = {
  draft_gaps: (input) => draftGaps(structuredClone(input)),
  superseded_results: (input) => {
    const result = extractSupersededResults(
      input.previous,
      structuredClone(input.next),
      structuredClone(input.answers),
      structuredClone(input.verifications),
    );
    return result === null
      ? null
      : {
          entry: result.entry,
          question_ids: result.questionIds,
          answers: result.answers,
          verifications: result.verifications,
        };
  },
  analysis_fingerprint: (input) => analysisFingerprint(structuredClone(input)),
};

const expectedDigest = (value) => {
  const computed = digest(value);
  if (!/^[a-f0-9]{64}$/.test(computed)) throw new Error(`unexpected digest: ${computed}`);
  return computed;
};

const render = () =>
  cases.map((item) => {
    const valid = validators[item.kind](item.input);
    if (valid !== item.expectValid)
      throw new Error(`fixture ${item.name}: TypeScript validity ${valid} contradicts the case`);
    const pythonValid = item.expectPythonValid ?? item.expectValid;
    const expected = {
      digest: expectedDigest(item.input),
      valid,
      python_valid: pythonValid,
    };
    if (valid !== pythonValid) {
      if (typeof item.divergenceReason !== "string" || item.divergenceReason.length === 0) {
        throw new Error(`fixture ${item.name}: divergence requires a divergence_reason`);
      }
      expected.divergence_reason = item.divergenceReason;
    }
    if (outputs[item.kind] !== undefined) expected.output = outputs[item.kind](item.input);
    return {
      name: item.name,
      kind: item.kind,
      input: item.input,
      expected,
    };
  });

// Fixtures carry the repository JSON formatting, exactly like the
// materialized TypeScript schema does.
const serialize = (fixtures) =>
  fixtures.map((item) =>
    execFileSync("oxfmt", ["--stdin-filepath", "fixture.json"], {
      input: `${JSON.stringify(item, null, 2)}\n`,
      encoding: "utf8",
    }),
  );

const check = process.argv.includes("--check");
const rendered = serialize(render());
if (check) {
  const drifted = [];
  for (const [index, item] of rendered.entries()) {
    const path = join(goldenDir, `${cases[index].name}.json`);
    let current = null;
    try {
      current = await readFile(path, "utf8");
    } catch {
      current = null;
    }
    if (current !== item) drifted.push(path);
  }
  if (drifted.length > 0)
    throw new Error(
      `golden parity fixtures drifted; regenerate with task reviewmatic-py:fixtures: ${drifted.join(", ")}`,
    );
  console.log(`golden parity fixtures match (${rendered.length} files).`);
} else {
  await mkdir(goldenDir, { recursive: true });
  const declared = new Set(cases.map((item) => `${item.name}.json`));
  for (const entry of await readdir(goldenDir))
    if (!declared.has(entry))
      throw new Error(`unexpected golden fixture file: ${join(goldenDir, entry)}`);
  for (const [index, item] of rendered.entries()) {
    const path = join(goldenDir, `${cases[index].name}.json`);
    await mkdir(dirname(path), { recursive: true });
    const temporary = `${path}.${process.pid}.tmp`;
    await writeFile(temporary, item);
    await rename(temporary, path);
  }
  console.log(`rendered ${rendered.length} golden parity fixtures into ${goldenDir}`);
}
