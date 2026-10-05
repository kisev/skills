// Probe TS vs Python validateV2Artifact verdict divergence over mutated artifacts.
// Usage: node probe-v2-divergence.mjs ; prints one JSON line per case.
import { registerHooks } from "node:module";
import { resolve as resolveTypeScript } from "./golden-ts-loader.mjs";

registerHooks({ resolve: resolveTypeScript });
const { validateV2Artifact } = await import(new URL("../src/contract.ts", import.meta.url).href);

const DIGEST = "a".repeat(64);
const SHA = "b".repeat(40);
const base = {
  evidence_snapshot: {
    schema: "portable-gitlab/evidence_snapshot/v2",
    schema_version: 2,
    kind: "evidence_snapshot",
    created_at: "2026-10-05T00:00:00+00:00",
    payload: {
      schema_version: 2,
      profile: "code-review",
      external_mutations: false,
      target: {
        url: "https://gitlab.com/g/p/-/merge_requests/1",
        hostname: "gitlab.com",
        project_path: "g/p",
        kind: "merge_requests",
        iid: 1,
      },
      project: { id: 1, path: "g/p" },
      object: { iid: 1, state: "opened" },
      labels: { items: [], complete: true, errors: [], pages: 0, truncated: false },
      changed_files: { items: [], complete: true, errors: [], pages: 0, truncated: false },
      commits: { items: [], complete: true, errors: [], pages: 0, truncated: false },
      pipelines: { items: [], complete: true, errors: [], pages: 0, truncated: false },
      discussions: { items: [], complete: true, errors: [], pages: 0, truncated: false },
      head_sha: SHA,
      base_sha: SHA,
      start_sha: SHA,
      artifact_root: "/tmp/artifacts",
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
  },
};

const cases = [];
const push = (name, kind, artifact) => cases.push({ name, kind, artifact });

// timestamp strictness battery
for (const created_at of [
  "2026-10-05",
  "20261005T000000",
  "2026-10-05 00:00:00",
  "2026-10-05T24:00:00+00:00",
  "2026-02-30T00:00:00+00:00",
]) {
  const artifact = structuredClone(base.evidence_snapshot);
  artifact.created_at = created_at;
  push(`created_at:${created_at}`, "evidence_snapshot", artifact);
}

for (const [name, mutation] of [
  [
    "component-pages-negative",
    (value) => {
      value.labels.pages = -1;
    },
  ],
  [
    "component-errors-not-strings",
    (value) => {
      value.labels.errors = [1];
    },
  ],
  [
    "components-incomplete-extra-key",
    (value) => {
      value.components_complete.extra = true;
    },
  ],
  [
    "retrieval-complete-string",
    (value) => {
      value.retrieval_complete = "true";
    },
  ],
  [
    "profile-empty",
    (value) => {
      value.profile = "";
    },
  ],
  [
    "head-sha-uppercase",
    (value) => {
      value.head_sha = value.head_sha.toUpperCase();
    },
  ],
  [
    "extra-envelope-key",
    (value) => {
      value.extra = 1;
    },
  ],
  [
    "envelope-version-1",
    (value) => {
      value.schema_version = 1;
    },
  ],
]) {
  const artifact = structuredClone(base.evidence_snapshot);
  mutation(artifact.payload);
  push(name, "evidence_snapshot", artifact);
}

const localReviewReport = (overrides = {}) => ({
  schema: "portable-gitlab/local_review_report/v2",
  schema_version: 2,
  kind: "local_review_report",
  created_at: "2026-10-05T00:00:00+00:00",
  payload: {
    evidence_digest: DIGEST,
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
push("lrr-baseline", "local_review_report", localReviewReport());
push(
  "lrr-bad-verdict",
  "local_review_report",
  localReviewReport({
    payload: { ...localReviewReport().payload, verdict: "excellent" },
  }),
);
push("lrr-foreign-field", "local_review_report", localReviewReport({ extra: 1 }));
push(
  "lrr-bad-check-status",
  "local_review_report",
  localReviewReport({
    payload: {
      ...localReviewReport().payload,
      checks: [{ name: "Freshness", status: "unknown", required: true, evidence: "x" }],
    },
  }),
);

const contextPackage = (overrides = {}) => ({
  schema: "portable-gitlab/context_package/v2",
  schema_version: 2,
  kind: "context_package",
  created_at: "2026-10-05T00:00:00+00:00",
  payload: {
    schema: "portable-gitlab/context-package/v2",
    mode: "mr",
    external_mutations: false,
    binding: { evidence_digest: DIGEST, evidence_path: "/tmp/artifacts/evidence.json" },
    goal: { status: "known", text: "Review the MR." },
    acceptance_criteria: { status: "known", items: ["No regressions"] },
  },
  ...overrides,
});
push("cp-baseline", "context_package", contextPackage());
push(
  "cp-bad-mode",
  "context_package",
  contextPackage({
    payload: { ...contextPackage().payload, mode: "repo" },
  }),
);
push(
  "cp-empty-acceptance",
  "context_package",
  contextPackage({
    payload: {
      ...contextPackage().payload,
      acceptance_criteria: { status: "known", items: [] },
    },
  }),
);

const verdict = (kind, artifact) => {
  try {
    validateV2Artifact(artifact, kind);
    return true;
  } catch {
    return false;
  }
};

for (const item of cases) {
  process.stdout.write(
    `${JSON.stringify({ name: item.name, kind: item.kind, artifact: item.artifact, ts_valid: verdict(item.kind, item.artifact) })}\n`,
  );
}
