import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  ARTIFACT_VERSION,
  WorkflowError,
  allowedEndpoint,
  artifactPayload,
  artifactRoot,
  capabilities,
  canonical,
  codeReviewChatLabels,
  detailedFindingsAreValid,
  digest,
  duplicateDetailedFindingIds,
  collect,
  emit,
  evidenceFromRoot,
  finalize,
  glabText,
  findingPublicationsAreValid,
  findingsAreValid,
  fingerprint,
  finalizePayload,
  glabJson,
  isDigest,
  labelSemantics,
  mrMetadataAssessmentIsValid,
  parseProject,
  parseSemver,
  parseTarget,
  parseGlabTrace,
  redact,
  reviewLabels,
  reviewPublicationPreviewIsValid,
  selectExactPipeline,
  splitGlabTraceResponse,
  stateDirectory,
  templateHeadings,
  threadDecisionsAreValid,
  traceExcerpt,
  validateCritic,
  validateDecision,
  validateFinalizeReport,
  writeArtifact,
  writeCompanion,
  writeJson,
} from "../dist/contract.js";

const DIGEST = "a".repeat(64);
const CREATED_AT = "2026-09-14T00:00:00Z";
const REPOSITORY_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

function temporaryDirectory(t) {
  const root = mkdtempSync(join(tmpdir(), "contract-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function withStateHome(t) {
  const root = temporaryDirectory(t);
  const previous = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = join(root, "state");
  t.after(() => {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
  });
  return root;
}

function isWorkflowError(message) {
  return (error) => {
    assert.ok(error instanceof WorkflowError);
    assert.match(error.message, message);
    return true;
  };
}

function pythonRun(script, input = "") {
  const run = spawnSync("python3", ["-c", script], {
    input,
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
  });
  if (run.error !== undefined || run.status !== 0) return null;
  return run.stdout;
}

function component() {
  return { items: [], complete: true, errors: [], pages: 1, truncated: false };
}

function detailedFinding(overrides = {}) {
  return {
    id: "finding-1",
    severity: "low",
    summary: "The contract example is concrete.",
    risk: "Schema drift can invalidate emitted artifacts.",
    evidence: ["tests/test_json_schemas.py"],
    consequence: "A consumer could reject an artifact.",
    relation_to_change: "The schema is part of the maintained contract.",
    minimum_fix: "Keep the producer and schema aligned.",
    ...overrides,
  };
}

function incrementalState(mode = "full") {
  const delta = {
    from_head: null,
    to_head: "c",
    changed_paths: [],
    changed_thread_ids: [],
    unchanged_thread_ids: [],
    changed_note_ids: [],
    unchanged_note_ids: [],
    metadata_fields: [],
    pipelines_changed: false,
  };
  return {
    contract_version: 1,
    requested: "auto",
    mode: mode,
    reason: "no compatible finalized baseline exists",
    incremental_baseline: { plan_path: null, plan_digest: null, state_digest: null },
    previous_findings: [],
    previous_finding_publications: [],
    previous_recommended_issues: [],
    previous_finding_ledger: [],
    previous_publication_ledger: [],
    previous_thread_decisions: [],
    previous_rejected_candidates: [],
    reconsidered_rejected_candidates: [],
    incremental_delta: delta,
    incremental_delta_digest: digest(delta),
    critic_required: false,
    fallback_reasons: [],
  };
}

function evidencePayload() {
  return {
    schema_version: ARTIFACT_VERSION,
    profile: "code-review",
    external_mutations: false,
    target: {},
    project: {},
    object: {},
    labels: component(),
    changed_files: component(),
    commits: component(),
    pipelines: component(),
    discussions: component(),
    head_sha: "c",
    base_sha: "a",
    start_sha: "b",
    artifact_root: "/tmp/portable-artifacts",
    prepared_at: CREATED_AT,
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
  };
}

function contextPayload() {
  return {
    schema_version: ARTIFACT_VERSION,
    profile: "code-review",
    external_mutations: false,
    evidence_digest: DIGEST,
    target: {},
    role: "reviewer",
    current_user_id: 23,
    current_user_username: "reviewer",
    mr_author_username: "author",
    discussions: [],
    notes: [],
    issue_templates: [],
    counts: {
      discussions: 0,
      notes: 0,
      content_notes: 0,
      system_notes: 0,
      open_resolvable: 0,
      resolved_resolvable: 0,
      plain_discussions: 0,
    },
    exact_git: {
      repo_root: "/tmp/repository",
      refs: {},
      changed_paths: [],
      diff_sha256: null,
      complete: true,
      errors: [],
    },
    incremental: incrementalState(),
    complete: true,
    errors: [],
    artifact_root: "/tmp/portable-artifacts",
    prepared_at: CREATED_AT,
  };
}

function labelReviewPayload() {
  const catalog = [{ name: "semver::patch", description: "Backward-compatible fix" }];
  return {
    complete: true,
    catalog_sha256: digest(catalog),
    catalog,
    assessments: [
      {
        name: "semver::patch",
        description: "Backward-compatible fix",
        status: "applicable",
        rationale: "The fix has patch SemVer impact.",
        current: false,
      },
    ],
    current: [],
    add: ["semver::patch"],
    remove: [],
    proposed: ["semver::patch"],
    unresolved: [],
    semver: { impact: "patch", candidates: ["semver::patch"], selected: "semver::patch" },
  };
}

function reviewPlanPayload() {
  return {
    profile: "code-review",
    review_contract_version: 5,
    external_mutations: false,
    evidence_digest: DIGEST,
    context_digest: DIGEST,
    decision_digest: DIGEST,
    target: {},
    role: "reviewer",
    mode: "deep",
    locale: "en",
    incremental: incrementalState(),
    verdict: "ready",
    complete: true,
    summary: "The concrete contract example is valid.",
    architecture_assessment: "The existing ownership boundary is preserved.",
    semver_impact: "patch",
    semver_rationale: "The fix changes behavior without changing the public API.",
    label_review: labelReviewPayload(),
    mr_metadata_assessment: {
      observed: {
        title: "Fix schema drift",
        description: "Align the producer and schema.",
        labels: ["type::bug"],
        workflow_state: "merged",
      },
      assessment: {
        title: {
          status: "ok",
          rationale: "The title metadata is sufficient.",
          recommendation: null,
        },
        description: {
          status: "ok",
          rationale: "The description metadata is sufficient.",
          recommendation: null,
        },
        labels: {
          status: "ok",
          rationale: "The labels metadata is sufficient.",
          recommendation: null,
        },
        workflow_state: {
          status: "ok",
          rationale: "The workflow_state metadata is sufficient.",
          recommendation: null,
        },
        overall: {
          status: "ok",
          rationale: "The overall metadata is sufficient.",
          recommendation: null,
        },
      },
    },
    chat_assessment: {
      necessity: { status: "supported", rationale: "The defect is confirmed." },
      relevance: { status: "current", rationale: "The exact head is current." },
      change: "The change fixes the reviewed behavior.",
    },
    publication_preview: {
      mr_state: "merged",
      warning: "Actions are prepared but were not executed.",
      body_files: [],
      actions: [],
    },
    presentation: codeReviewPresentationFixture(),
    checks: ["task check"],
    findings: [detailedFinding()],
    finding_publications: [],
    previous_finding_assessments: [],
    recommended_issues: [],
    finding_ledger: [],
    publication_ledger: [],
    rejected_candidates: [],
    rejected_candidate_assessments: [],
    rejected_candidate_ledger: [],
    thread_decisions: [],
    markdown: "# Review plan",
  };
}

function codeReviewPresentationFixture() {
  return {
    title: "Code review publication plan",
    incremental_notice: null,
    target_label: "Target",
    role_label: "Role",
    role_value: "reviewer",
    verdict_label: "Verdict",
    verdict_value: "ready",
    metadata_heading: "MR metadata",
    labels_heading: "Project labels",
    previous_findings_heading: "Previous findings",
    open_threads_heading: "Open threads",
    closed_threads_heading: "Closed threads",
    local_fixes_heading: "Local fixes",
    new_findings_heading: "Findings",
    recommended_issues_heading: "Recommended issues",
    checked_heading: "Reviewed without publication",
    architecture_heading: "Architecture",
    semver_heading: "SemVer",
    checks_heading: "Checks",
    publication_heading: "Manual publication",
    no_items: "None.",
    publication_warning: "No command was executed.",
    evidence_label: "Evidence",
    relation_label: "Relation to change",
    severity_labels: { critical: "Critical", high: "High", medium: "Medium", low: "Low" },
    recovery_label: "If the response succeeds but the state change fails, run only:",
    previous_table_headers: ["ID", "Previous status", "Current status", "Rationale", "Action"],
  };
}

function criticPayload() {
  return {
    schema: "portable-gitlab/critic-receipt/v2",
    evidence_digest: DIGEST,
    run_id: "critic-run",
    session_id: "critic-session",
    scope_digest: DIGEST,
    target_finding_ids: [],
    findings: [
      detailedFinding({
        id: "rejected-1",
        summary: "The broader cleanup is not part of this change.",
      }),
    ],
    external_mutations: false,
  };
}

function decisionPayload() {
  return {
    schema: "portable-gitlab/review-decision/v2",
    evidence_digest: DIGEST,
    finalize_digest: DIGEST,
    context_digest: DIGEST,
    critic_receipt_digest: DIGEST,
    mode: "deep",
    external_mutations: false,
    run_id: "review-run",
    session_id: "review-session",
    verdict: "ready",
    low_risk: true,
    blocking_findings: false,
    blocking_finding_ids: [],
    owner_decision_reasons: [],
    findings: [detailedFinding()],
    unresolved_threads: [],
    responses: [
      { id: "finding-1", decision: "accept", reason: "confirmed" },
      { id: "rejected-1", decision: "reject", reason: "outside the changed contract" },
    ],
  };
}

test("canonical digests match python3 byte-for-byte", (t) => {
  const values = [
    { b: 1, a: "plain" },
    { ключ: "значение", nested: { z: "日本語", y: ["α", "ω"] } },
    ["array", ["nested", []], 0, -17, true, false, null],
    { control: "line\nbreak\ttab\u0001bell", empty: "" },
    "",
    { deep: { deeper: { deepest: { leaf: "🚀" } } } },
    { unicode_key_é: "é" },
  ];
  const output = pythonRun(
    [
      "import sys, json, hashlib",
      "for value in json.load(sys.stdin):",
      '    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\\n"',
      "    print(hashlib.sha256(data.encode()).hexdigest())",
    ].join("\n"),
    JSON.stringify(values),
  );
  if (output === null) t.skip("python3 is unavailable");
  const expected = output.trim().split("\n");
  for (let index = 0; index < values.length; index += 1) {
    assert.equal(digest(values[index]), expected[index]);
    assert.equal(canonical(values[index]).toString("utf8").endsWith("\n"), true);
  }
});

test("redact covers every secret pattern family", (t) => {
  const cases = new Map([
    ["api token = secret1,", "api token=[REDACTED],"],
    ['{"password": "hunter2"}', '{"password": "[REDACTED]"}'],
    ["Authorization: Bearer abc123\nnext", "Authorization: [REDACTED]\nnext"],
    ["AWS_SECRET_ACCESS_KEY=deadbeef done", "AWS_SECRET_ACCESS_KEY=[REDACTED] done"],
    [
      "see https://alice:hunter@gitlab.example/x now",
      "see https://[REDACTED]@gitlab.example/x now",
    ],
    [
      "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----",
      "[REDACTED PRIVATE KEY]",
    ],
    ["plain text without secrets", "plain text without secrets"],
  ]);
  const script = [
    "import sys, json",
    `sys.path.insert(0, ${JSON.stringify(REPOSITORY_ROOT)})`,
    "from shared.references.portable_gitlab import contract",
    "print(json.dumps([contract.redact(value) for value in json.load(sys.stdin)]))",
  ].join("\n");
  const output = pythonRun(script, JSON.stringify([...cases.keys()]));
  for (const [inputValue, expected] of cases.entries()) {
    assert.equal(redact(inputValue), expected);
  }
  if (output !== null) assert.deepEqual(JSON.parse(output), [...cases.values()]);
});

test("emit prints sorted python-compatible JSON with a trailing newline", () => {
  const original = process.stdout.write.bind(process.stdout);
  let captured = "";
  process.stdout.write = (chunk) => {
    captured += chunk;
    return true;
  };
  try {
    emit({ b: 1, a: "x" });
  } finally {
    process.stdout.write = original;
  }
  assert.equal(captured, '{"a": "x", "b": 1}\n');
});

test("capabilities emits the code-review profile shape", () => {
  const original = process.stdout.write.bind(process.stdout);
  let captured = "";
  process.stdout.write = (chunk) => {
    captured += chunk;
    return true;
  };
  let code = -1;
  try {
    code = capabilities("code-review");
  } finally {
    process.stdout.write = original;
  }
  assert.equal(code, 0);
  assert.match(captured, /^\{"destructive_flags": \[\], "dry_run": true, /);
  const value = JSON.parse(captured);
  assert.deepEqual(Object.keys(value).sort(), [
    "destructive_flags",
    "dry_run",
    "external_mutations",
    "external_tools",
    "mutation",
    "payload_version",
    "profile",
    "schema_version",
    "state_protocol",
  ]);
  assert.equal(value.profile, "code-review");
  assert.equal(value.schema_version, 1);
  assert.equal(value.payload_version, "2.0.0");
  assert.equal(value.mutation, "local-write");
  assert.equal(value.dry_run, true);
  assert.equal(value.external_mutations, false);
  assert.equal(value.state_protocol, "private-content-addressed-artifacts");
  assert.deepEqual(value.destructive_flags, []);
  assert.equal(typeof value.external_tools.glab, "boolean");
  assert.equal(typeof value.external_tools.git, "boolean");
});

test("parse target accepts exact issue and merge request URLs", () => {
  const target = parseTarget(
    "https://gitlab.example/group/proj/-/merge_requests/7/",
    new Set(["merge_requests"]),
  );
  assert.deepEqual(target, {
    url: "https://gitlab.example/group/proj/-/merge_requests/7/",
    hostname: "gitlab.example",
    project_path: "group/proj",
    kind: "merge_requests",
    iid: 7,
  });
  const issue = parseTarget(
    "https://GitLab.example/group/proj/-/issues/12",
    new Set(["issues", "merge_requests"]),
  );
  assert.equal(issue.kind, "issues");
  assert.equal(issue.hostname, "gitlab.example");
  assert.equal(issue.iid, 12);
});

test("parse target rejects unsafe or mismatched URLs", () => {
  const expected = new Set(["merge_requests"]);
  assert.throws(
    () => parseTarget("https://gitlab.example/g/p/-/issues/1", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
  assert.throws(
    () => parseTarget("https://gitlab.example/g/p/-/merge_requests/1?x=1", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
  assert.throws(
    () => parseTarget("https://gitlab.example/g/p/-/merge_requests/1#frag", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
  assert.throws(
    () => parseTarget("http://gitlab.example/g/p/-/merge_requests/1", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
  assert.throws(
    () => parseTarget("https://user:pw@gitlab.example/g/p/-/merge_requests/1", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
  assert.throws(
    () => parseTarget("https://gitlab.example/g/../p/-/merge_requests/1", expected),
    isWorkflowError(/project path is unsafe/),
  );
  assert.throws(
    () => parseTarget("https://gitlab.example/g/./p/-/merge_requests/1", expected),
    isWorkflowError(/project path is unsafe/),
  );
  assert.throws(
    () => parseTarget("https://gitlab.example/g/p/-/merge_requests/0", expected),
    isWorkflowError(/exact HTTPS GitLab/),
  );
});

test("parse project accepts and rejects exact project URLs", () => {
  const project = parseProject("https://gitlab.example/group/proj/");
  assert.deepEqual(project, {
    url: "https://gitlab.example/group/proj",
    hostname: "gitlab.example",
    project_path: "group/proj",
    kind: "new_issue",
    iid: 0,
  });
  assert.throws(
    () => parseProject("https://gitlab.example/-/proj"),
    isWorkflowError(/exact HTTPS GitLab project URL/),
  );
  assert.throws(
    () => parseProject("https://gitlab.example/only"),
    isWorkflowError(/exact HTTPS GitLab project URL/),
  );
  assert.throws(
    () => parseProject("https://gitlab.example/group/../proj"),
    isWorkflowError(/exact HTTPS GitLab project URL/),
  );
  assert.throws(
    () => parseProject("http://gitlab.example/group/proj"),
    isWorkflowError(/exact HTTPS GitLab project URL/),
  );
  assert.throws(
    () => parseProject("https://user@gitlab.example/group/proj"),
    isWorkflowError(/exact HTTPS GitLab project URL/),
  );
});

test("state directory derives the canonical content-addressed path", async (t) => {
  withStateHome(t);
  const home = process.env.XDG_STATE_HOME;
  const target = { hostname: "gitlab.example", project_id: 42, kind: "merge_requests", iid: 7 };
  const identity = "gitlab.example:42:merge_requests:7";
  const expected = `${home}/agent-skills/gitlab/${createHash("sha256").update(identity).digest("hex").slice(0, 32)}`;
  assert.equal(await stateDirectory("code-review", target), expected);
  assert.equal(statSync(expected).mode & 0o777, 0o700);
  const byPath = await stateDirectory("code-review", {
    hostname: "gitlab.example",
    project_path: "group/proj",
    kind: "merge_requests",
    iid: 7,
  });
  const pathIdentity = "gitlab.example:group/proj:merge_requests:7";
  assert.equal(
    byPath,
    `${home}/agent-skills/gitlab/${createHash("sha256").update(pathIdentity).digest("hex").slice(0, 32)}`,
  );
  await assert.rejects(
    stateDirectory("unknown-profile", target),
    isWorkflowError(/workflow profile is unsafe/),
  );
});

test("artifact root enforces the canonical collection layout", async (t) => {
  const root = withStateHome(t);
  const home = process.env.XDG_STATE_HOME;
  const digest32 = "b".repeat(32);
  const canonicalRoot = `${home}/agent-skills/gitlab/${digest32}`;
  assert.equal(await artifactRoot(canonicalRoot), canonicalRoot);
  const legacyRoot = `${home}/agent-skills/task-triage/${"c".repeat(20)}`;
  assert.equal(await artifactRoot(legacyRoot), legacyRoot);
  await assert.rejects(
    artifactRoot(`${home}/agent-skills`),
    isWorkflowError(/outside canonical GitLab collection state/),
  );
  await assert.rejects(
    artifactRoot(`${home}/agent-skills/gitlab/${digest32}/nested`),
    isWorkflowError(/artifact root is unsafe/),
  );
  await assert.rejects(
    artifactRoot(`${home}/elsewhere/${digest32}`),
    isWorkflowError(/outside canonical GitLab collection state/),
  );
  await assert.rejects(
    artifactRoot(`${home}/agent-skills/task_triage/${"c".repeat(20)}`),
    isWorkflowError(/outside canonical GitLab collection state/),
  );
  assert.equal(existsSync(`${root}/state/agent-skills/gitlab`), true);
});

test("write artifact roundtrips every code-review kind", async (t) => {
  withStateHome(t);
  const target = { hostname: "gitlab.example", project_id: 42, kind: "merge_requests", iid: 7 };
  const root = await stateDirectory("code-review", target);
  const kinds = new Map([
    ["evidence_snapshot", evidencePayload()],
    ["review_context", contextPayload()],
    ["critic_receipt", criticPayload()],
    ["review_decision", decisionPayload()],
    ["review_plan", reviewPlanPayload()],
    [
      "finalize_report",
      {
        status: "ok",
        changed: [],
        complete: true,
        head_sha: "c",
        evidence_digest: DIGEST,
        evidence_kind: "evidence_snapshot",
        evidence_fingerprint_digest: DIGEST,
        external_mutations: false,
      },
    ],
  ]);
  for (const [kind, payload] of kinds.entries()) {
    const [path, digestValue] = await writeArtifact(root, kind, payload);
    assert.equal(digestValue.length, 64);
    assert.equal(path, `${root}/artifacts/${kind}/${digestValue}.json`);
    assert.equal(statSync(path).mode & 0o777, 0o600);
    assert.equal(statSync(dirname(path)).mode & 0o777, 0o700);
    const [document, recovered] = artifactPayload(path, kind);
    assert.equal(document.schema, `portable-gitlab/${kind}/v2`);
    assert.deepEqual(recovered, payload);
  }
});

test("artifact payload rejects tampered envelopes", async (t) => {
  withStateHome(t);
  const root = await stateDirectory("code-review", {
    hostname: "gitlab.example",
    project_id: 1,
    kind: "merge_requests",
    iid: 1,
  });
  const [path] = await writeArtifact(root, "evidence_snapshot", evidencePayload());
  const original = readFileSync(path, "utf8");

  const kindTampered = JSON.parse(original);
  kindTampered.kind = "review_plan";
  writeFileSync(path, JSON.stringify(kindTampered));
  assert.throws(
    () => artifactPayload(path, "evidence_snapshot"),
    isWorkflowError(/artifact schema is invalid/),
  );

  const timestampTampered = JSON.parse(original);
  timestampTampered.created_at = "not-a-date";
  writeFileSync(path, JSON.stringify(timestampTampered));
  assert.throws(
    () => artifactPayload(path, "evidence_snapshot"),
    isWorkflowError(/does not satisfy the canonical schema/),
  );

  const payloadTampered = JSON.parse(original);
  delete payloadTampered.payload.profile;
  writeFileSync(path, JSON.stringify(payloadTampered));
  assert.throws(
    () => artifactPayload(path, "evidence_snapshot"),
    isWorkflowError(/does not satisfy the canonical schema/),
  );

  writeFileSync(path, original);
  const [, recovered] = artifactPayload(path, "evidence_snapshot");
  assert.equal(recovered.profile, "code-review");

  const v1 = JSON.parse(original);
  v1.schema_version = 1;
  writeFileSync(path, JSON.stringify(v1));
  const [v1Document, v1Payload] = artifactPayload(path, "evidence_snapshot");
  assert.equal(v1Document.schema_version, 1);
  assert.equal(v1Payload, v1Document);
});

test("write companion is immutable and conflict-checked", (t) => {
  const root = temporaryDirectory(t);
  const path = join(root, "plan.md");
  const [resolved, digestValue] = writeCompanion(path, "body\n");
  assert.equal(resolved, path);
  assert.equal(digestValue, createHash("sha256").update("body\n").digest("hex"));
  const [again, againDigest] = writeCompanion(path, "body\n");
  assert.equal(againDigest, digestValue);
  assert.throws(
    () => writeCompanion(path, "different\n"),
    isWorkflowError(/immutable Markdown companion conflict/),
  );
});

test("findings validators separate legacy and detailed shapes", () => {
  const detailed = detailedFinding();
  const legacy = { id: "finding-1" };
  assert.equal(findingsAreValid([detailed]), true);
  assert.equal(findingsAreValid([legacy]), true);
  assert.equal(findingsAreValid([{ id: "" }]), false);
  assert.equal(detailedFindingsAreValid([detailed]), true);
  assert.equal(detailedFindingsAreValid([legacy]), false);
  assert.equal(detailedFindingsAreValid([detailedFinding({ severity: "unknown" })]), false);
  assert.equal(detailedFindingsAreValid([detailedFinding({ evidence: [] })]), false);
  assert.equal(detailedFindingsAreValid([detailedFinding({ risk: "" })]), false);
  assert.deepEqual(duplicateDetailedFindingIds([detailed, detailedFinding({ id: "finding-2" })]), [
    ["finding-1", "finding-2"],
  ]);
  assert.deepEqual(
    duplicateDetailedFindingIds([
      detailed,
      detailedFinding({ id: "finding-2", risk: "Different risk." }),
    ]),
    [],
  );
});

test("thread decisions validate shape, outcome, and patch bindings", () => {
  const current = {
    id: "thread:abc",
    url: "https://gitlab.example/g/p/-/merge_requests/1#note_1",
    state: "open",
    assessment: "accepted",
    rationale: "The finding is confirmed.",
    outcome: "reply",
    proposed_response: "Agreed.",
    last_note_id: 5,
    last_note_body_sha256: DIGEST,
    thread_sha256: DIGEST,
  };
  assert.equal(threadDecisionsAreValid([current]), true);
  const structured = { ...current, suggestion_applicable: true };
  assert.equal(threadDecisionsAreValid([structured]), true);
  const openSilent = { ...current, outcome: "no_publication" };
  assert.equal(threadDecisionsAreValid([openSilent]), false);
  const resolvedSilent = { ...openSilent, state: "resolved" };
  assert.equal(threadDecisionsAreValid([resolvedSilent]), true);
  const patch = "diff --git a/f b/f\n";
  const materialized = {
    ...current,
    state: "resolved",
    assessment: "fixed",
    outcome: "local_fix",
    proposed_response: null,
    fix_mode: "patch",
    patch,
    fixing_commit: null,
    patch_path: "/tmp/artifacts/f.patch",
    patch_sha256: createHash("sha256").update(patch).digest("hex"),
  };
  assert.equal(threadDecisionsAreValid([materialized]), true);
  assert.equal(threadDecisionsAreValid([{ ...materialized, patch: "other diff\n" }]), false);
  assert.equal(threadDecisionsAreValid([{ ...materialized, patch_path: "relative.patch" }]), false);
  const suggestion = {
    ...materialized,
    fix_mode: "suggestion",
    patch: null,
    patch_path: null,
    patch_sha256: null,
  };
  assert.equal(threadDecisionsAreValid([suggestion]), true);
  assert.equal(threadDecisionsAreValid([{ ...suggestion, patch: "leftover diff\n" }]), false);
});

test("finding publications validate fix bindings", () => {
  const patch = "diff --git a/f b/f\n";
  const patchDigest = createHash("sha256").update(patch).digest("hex");
  const legacy = {
    finding_id: "finding-1",
    revision: 1,
    type: "general",
    path: null,
    line: null,
    old_line: null,
    body: "Finding body",
  };
  assert.equal(findingPublicationsAreValid([legacy]), true);
  assert.equal(findingPublicationsAreValid([legacy], true), false);
  const fixed = {
    ...legacy,
    fix_mode: "patch",
    patch,
    patch_path: "/tmp/artifacts/f.patch",
    patch_sha256: patchDigest,
  };
  assert.equal(findingPublicationsAreValid([fixed], true), true);
  assert.equal(findingPublicationsAreValid([{ ...fixed, patch: "tampered\n" }], true), false);
  assert.equal(findingPublicationsAreValid([{ ...fixed, revision: 0 }], true), false);
  assert.equal(findingPublicationsAreValid([{ ...fixed, type: "inline" }], true), false);
});

test("label semantics resolve aliases through names and descriptions", (t) => {
  assert.deepEqual(labelSemantics({ name: "type::bug" }), ["change_type", "bug"]);
  assert.deepEqual(labelSemantics({ name: "priority::p1" }), ["urgency", "urgent"]);
  assert.deepEqual(labelSemantics({ name: "semver/patch" }), ["compatibility", "patch"]);
  assert.deepEqual(labelSemantics({ name: "state=in_progress" }), [
    "workflow_state",
    "in_progress",
  ]);
  assert.deepEqual(
    labelSemantics({ name: "x", description: "Semantic-Role: kind; Semantic-Value: defect" }),
    ["change_type", "bug"],
  );
  assert.equal(labelSemantics({ name: "unknown::bug" }), null);
  assert.equal(labelSemantics({ name: "one-part" }), null);
  assert.equal(
    labelSemantics({ name: "x", description: "semantic-role: kind; semantic-value: nonsense" }),
    null,
  );
  assert.equal(labelSemantics({ name: "" }), null);
  assert.equal(labelSemantics("not-a-dict"), null);
  const script = [
    "import sys",
    `sys.path.insert(0, ${JSON.stringify(REPOSITORY_ROOT)})`,
    "from shared.references.portable_gitlab import contract",
    "import json",
    "print(json.dumps([contract.label_semantics(value) and list(contract.label_semantics(value)) for value in [",
    '    {"name": "type::bug"}, {"name": "priority::p1"}, {"name": "semver/patch"}, {"name": "state=in_progress"},',
    '    {"name": "x", "description": "Semantic-Role: kind; Semantic-Value: defect"}, {"name": "unknown::bug"}]]))',
  ].join("\n");
  const output = pythonRun(script);
  if (output === null) t.skip("python3 is unavailable");
  const expected = JSON.parse(output);
  for (const [index, value] of [
    ["change_type", "bug"],
    ["urgency", "urgent"],
    ["compatibility", "patch"],
    ["workflow_state", "in_progress"],
    ["change_type", "bug"],
    null,
  ].entries()) {
    const actual = labelSemantics(
      [
        { name: "type::bug" },
        { name: "priority::p1" },
        { name: "semver/patch" },
        { name: "state=in_progress" },
        { name: "x", description: "Semantic-Role: kind; Semantic-Value: defect" },
        { name: "unknown::bug" },
      ][index],
    );
    assert.deepEqual(actual === null ? null : [...actual], expected[index]);
    assert.deepEqual(actual === null ? null : [...actual], value);
  }
});

test("review labels derive a semantic delta from catalog and intent", () => {
  const bundle = {
    labels: {
      items: [{ name: "kind::feature" }, { name: "type::bug" }, { name: "ambiguous" }],
      complete: true,
    },
    object: { labels: ["kind::feature"] },
  };
  const intent = {
    change_type: "bug",
    workflow_state: null,
    urgency: null,
    impact: null,
    compatibility: null,
    origin: null,
  };
  const review = reviewLabels(bundle, intent);
  assert.equal(review.complete, true);
  assert.deepEqual(review.current, ["kind::feature"]);
  assert.deepEqual(review.add, ["type::bug"]);
  assert.deepEqual(review.remove, ["kind::feature"]);
  assert.deepEqual(review.proposed, ["type::bug"]);
  const changeDecision = review.decisions.find((decision) => decision.role === "change_type");
  assert.equal(changeDecision.action, "change");
  assert.equal(changeDecision.desired_label, "type::bug");
  const keepDecision = review.decisions.find((decision) => decision.role === "workflow_state");
  assert.equal(keepDecision.action, "keep");
  assert.equal(keepDecision.intent, null);
  const incomplete = reviewLabels(
    { labels: { items: [], complete: false }, object: { labels: [] } },
    intent,
  );
  assert.equal(incomplete.complete, false);
  assert.deepEqual(incomplete.unresolved, ["change_type=bug: project label catalog is incomplete"]);
  assert.throws(
    () => reviewLabels({ labels: { items: [] }, object: { labels: "nope" } }, intent),
    isWorkflowError(/current MR labels are invalid/),
  );
});

test("publication preview accepts a structured action plan", () => {
  const bodyContent = "Finding body\n";
  const bodyDigest = createHash("sha256").update(bodyContent).digest("hex");
  const spec = {
    schema: "code-review/publication-action/v1",
    preflight_sha256: DIGEST,
    operation: "create_general",
    publication: { id: "finding-1", revision: 1, kind: "finding" },
    body: { path: "/tmp/portable-artifacts/finding-1.md", sha256: bodyDigest },
    expected: { thread: null, note: null, prior_marker: null, issue: null },
    mutation: { path: null, line: null, old_line: null },
  };
  const preview = {
    mr_state: "merged",
    warning: "Actions are prepared but were not executed.",
    preflight_path: "/tmp/portable-artifacts/preflight.json",
    preflight_sha256: DIGEST,
    body_files: [
      {
        publication_id: "finding-1",
        revision: 1,
        kind: "finding",
        path: "/tmp/portable-artifacts/finding-1.md",
        sha256: bodyDigest,
        content: bodyContent,
      },
    ],
    actions: [
      {
        id: "finding:finding-1:r1:create_general",
        sha256: digest(spec),
        kind: "finding",
        publication_id: "finding-1",
        revision: 1,
        operation: "create_general",
        command: "glab api --method POST projects/1/merge_requests/1/discussions",
        spec,
      },
    ],
  };
  assert.equal(reviewPublicationPreviewIsValid(preview), true);
  assert.equal(reviewPublicationPreviewIsValid({ ...preview, preflight_sha256: "nope" }), false);
  assert.equal(
    reviewPublicationPreviewIsValid({
      ...preview,
      actions: [...preview.actions, JSON.parse(JSON.stringify(preview.actions[0]))],
    }),
    false,
  );
  const specMismatch = JSON.parse(JSON.stringify(spec));
  specMismatch.operation = "create_line";
  const withMismatch = JSON.parse(JSON.stringify(preview));
  withMismatch.actions[0].spec = specMismatch;
  assert.equal(reviewPublicationPreviewIsValid(withMismatch), false);
});

test("metadata assessment validates observed fields", () => {
  const valid = {
    observed: {
      title: "Fix schema drift",
      description: null,
      labels: ["type::bug"],
      workflow_state: "merged",
    },
    assessment: {
      title: { status: "ok", rationale: "sufficient", recommendation: null },
      description: { status: "needs_change", rationale: "missing", recommendation: "describe it" },
      labels: { status: "unverified", rationale: "unknown", recommendation: null },
      workflow_state: { status: "ok", rationale: "sufficient", recommendation: null },
      overall: { status: "ok", rationale: "sufficient", recommendation: null },
    },
  };
  assert.equal(mrMetadataAssessmentIsValid(valid), true);
  assert.equal(
    mrMetadataAssessmentIsValid({ ...valid, observed: { ...valid.observed, title: 5 } }),
    false,
  );
  assert.equal(
    mrMetadataAssessmentIsValid({
      ...valid,
      assessment: {
        ...valid.assessment,
        overall: { status: "unknown", rationale: "x", recommendation: null },
      },
    }),
    false,
  );
});

test("semver parsing follows the portable contract", () => {
  assert.deepEqual(parseSemver("1.2.3"), [1, 2, 3, [], []]);
  assert.deepEqual(parseSemver("1.2.3-rc.1+build.5"), [1, 2, 3, ["rc", "1"], ["build", "5"]]);
  assert.deepEqual(parseSemver("0.0.0"), [0, 0, 0, [], []]);
  assert.equal(parseSemver("01.2.3"), null);
  assert.equal(parseSemver("1.2"), null);
  assert.equal(parseSemver("1.2.3-"), null);
  assert.equal(parseSemver("1.2.3+"), null);
  assert.equal(parseSemver("1.2.3-rc..1"), null);
  assert.equal(parseSemver("1.2.3-01"), null);
  assert.equal(parseSemver(" 1.2.3"), null);
  assert.equal(parseSemver(42), null);
});

test("endpoint allowlist accepts collection endpoints only", () => {
  assert.equal(allowedEndpoint("user"), true);
  assert.equal(allowedEndpoint("projects/5/issues/7/discussions"), true);
  assert.equal(allowedEndpoint("projects/5/merge_requests/7?per_page=100&page=2"), true);
  assert.equal(allowedEndpoint("projects/5/jobs/9/trace"), true);
  assert.equal(allowedEndpoint("projects/5/pipelines/3/jobs?per_page=100&page=1"), true);
  assert.equal(allowedEndpoint("projects/5/releases"), true);
  assert.equal(allowedEndpoint("projects/5/repository/branches/main"), true);
  assert.equal(allowedEndpoint("user/extra"), false);
  assert.equal(allowedEndpoint("projects/5/merge_requests/7/unknown"), false);
  assert.equal(allowedEndpoint("../projects/5"), false);
  assert.equal(allowedEndpoint("projects/five"), true);
});

test("glab json rejects non-allowlisted endpoints before any glab call", () => {
  assert.throws(
    () => glabJson("gitlab.example", "projects/1/unknown"),
    isWorkflowError(/outside the collection allowlist/),
  );
  assert.throws(
    () => glabJson("GitLab..Example", "user"),
    isWorkflowError(/outside the collection allowlist/),
  );
});

test("trace parsing splits headers and applies range completeness", () => {
  const response = Buffer.from("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\ntrace body\n");
  const [headerBytes, body] = splitGlabTraceResponse(response);
  assert.equal(headerBytes.toString("latin1"), "HTTP/1.1 200 OK\r\nContent-Type: text/plain");
  assert.equal(body.toString("utf8"), "trace body\n");
  const parsed = parseGlabTrace(response);
  assert.equal(parsed.text, "trace body\n");
  assert.equal(parsed.complete, true);
  const partial = Buffer.from("HTTP/1.1 206\r\ncontent-range: bytes 5-9/20\r\n\r\nabcde");
  const partialParsed = parseGlabTrace(partial);
  assert.equal(partialParsed.complete, false);
  const whole = Buffer.from("HTTP/1.1 206\r\nContent-Range: bytes 0-4/5\r\n\r\nabcde");
  assert.equal(parseGlabTrace(whole).complete, true);
  const dropped = parseGlabTrace(Buffer.from("HTTP/1.1 200\r\n\r\nbody"), true);
  assert.equal(dropped.complete, false);
  assert.throws(
    () => parseGlabTrace(Buffer.from("garbage")),
    isWorkflowError(/headers are unavailable/),
  );
  assert.throws(
    () => parseGlabTrace(Buffer.from("HTTP/1.1 404 Not Found\r\n\r\n")),
    isWorkflowError(/returned HTTP 404/),
  );
  const preferLf = splitGlabTraceResponse(Buffer.from("HTTP/1.1 200\nX: 1\n\nbody"));
  assert.equal(preferLf[1].toString("utf8"), "body");
});

test("trace excerpt strips ANSI, redacts, and keeps the bounded tail", () => {
  const noisy = "\x1b[31merror\x1b[0m: token=abc123\n";
  const excerpt = traceExcerpt(noisy, true);
  assert.equal(excerpt.complete, true);
  assert.equal(excerpt.truncated, false);
  assert.equal(excerpt.excerpt, "error: token=[REDACTED]\n");
  assert.equal(excerpt.sha256, createHash("sha256").update(noisy).digest("hex"));
  const big = "x".repeat(70 * 1024);
  const truncated = traceExcerpt(big, true);
  assert.equal(truncated.truncated, true);
  assert.equal(truncated.excerpt.length, 64 * 1024);
  assert.equal(truncated.excerpt, big.slice(-64 * 1024));
  assert.equal(traceExcerpt("short", false).complete, false);
});

test("select exact pipeline picks the newest pipeline for the head", () => {
  const pipelines = {
    items: [
      { id: 11, sha: "aaa" },
      { id: 17, sha: "ccc" },
      { id: 14, sha: "ccc" },
      { id: "bogus", sha: "ccc" },
    ],
  };
  const selected = selectExactPipeline(pipelines, "ccc");
  assert.equal(selected.id, 17);
  assert.equal(selectExactPipeline(pipelines, "zzz"), null);
  assert.equal(selectExactPipeline({ items: "nope" }, "ccc"), null);
});

test("template headings and chat labels follow the contract", () => {
  assert.deepEqual(templateHeadings("## A\nplain\n### B x\n#no\n#### C\n"), [
    "## A",
    "### B x",
    "#### C",
  ]);
  const en = codeReviewChatLabels("en");
  assert.equal(en.title, "### MR assessment");
  assert.equal(en.metadata_values.ok, "ready");
  const ru = codeReviewChatLabels("ru");
  assert.equal(ru.title, "### Оценка MR");
  assert.throws(
    () => codeReviewChatLabels("de"),
    isWorkflowError(/review locale must be en or ru/),
  );
});

test("validate critic binds evidence and scope", () => {
  const receipt = JSON.parse(JSON.stringify(criticPayload()));
  validateCritic(receipt, DIGEST, DIGEST);
  const bare = JSON.parse(JSON.stringify(receipt));
  delete bare.scope_digest;
  delete bare.target_finding_ids;
  validateCritic(bare, DIGEST);
  assert.throws(
    () => validateCritic(receipt, "b".repeat(64)),
    isWorkflowError(/schema-invalid or does not bind evidence/),
  );
  assert.throws(
    () => validateCritic({ ...receipt, scope_digest: "c".repeat(64) }, DIGEST, DIGEST),
    isWorkflowError(/schema-invalid or does not bind evidence/),
  );
  assert.throws(
    () => validateCritic({ ...receipt, run_id: "" }, DIGEST),
    isWorkflowError(/independent run identity/),
  );
});

test("validate decision accounts for findings and threads", () => {
  const report = JSON.parse(JSON.stringify(decisionPayload()));
  const receipt = JSON.parse(JSON.stringify(criticPayload()));
  validateDecision(report, DIGEST, receipt, "deep", DIGEST, DIGEST);
  assert.throws(
    () =>
      validateDecision({ ...report, verdict: "unknown" }, DIGEST, receipt, "deep", DIGEST, DIGEST),
    isWorkflowError(/schema-invalid/),
  );
  assert.throws(
    () => validateDecision({ ...report, responses: [] }, DIGEST, receipt, "deep", DIGEST, DIGEST),
    isWorkflowError(/does not account for every finding/),
  );
  const noCriticReport = JSON.parse(JSON.stringify(report));
  delete noCriticReport.critic_receipt_digest;
  noCriticReport.responses = noCriticReport.responses.filter(
    (response) => response.id === "finding-1",
  );
  assert.throws(
    () => validateDecision({ ...noCriticReport, mode: "normal" }, DIGEST, null, "normal"),
    isWorkflowError(/independent critic receipt/),
  );
  assert.throws(
    () =>
      validateDecision({ ...noCriticReport, mode: "fast", low_risk: false }, DIGEST, null, "fast"),
    isWorkflowError(/confirmed low-risk scope/),
  );
  validateDecision({ ...noCriticReport, mode: "fast", low_risk: true }, DIGEST, null, "fast");
  assert.throws(
    () =>
      validateDecision(
        { ...report, blocking_findings: true },
        DIGEST,
        receipt,
        "deep",
        DIGEST,
        DIGEST,
      ),
    isWorkflowError(/blocking findings prohibit ready/),
  );
  const withThreads = {
    ...report,
    unresolved_threads: [{ id: "thread:note-1" }],
    responses: [...report.responses, { id: "thread:note-1", decision: "reject", reason: "stale" }],
  };
  validateDecision(withThreads, DIGEST, receipt, "deep", DIGEST, DIGEST);
  const badNamespace = {
    ...withThreads,
    unresolved_threads: [{ id: "finding-1" }],
  };
  assert.throws(
    () => validateDecision(badNamespace, DIGEST, receipt, "deep", DIGEST, DIGEST),
    isWorkflowError(/namespace-safe/),
  );
  const duplicate = detailedFinding({ id: "finding-2" });
  const duplicates = {
    ...report,
    findings: [detailedFinding(), duplicate],
    responses: [...report.responses, { id: "finding-2", decision: "accept", reason: "same" }],
  };
  assert.throws(
    () => validateDecision(duplicates, DIGEST, receipt, "deep", DIGEST, DIGEST),
    isWorkflowError(/structurally duplicate findings/),
  );
});

test("finalize payload binds the evidence fingerprint and validates", async (t) => {
  withStateHome(t);
  const root = await stateDirectory("code-review", {
    hostname: "gitlab.example",
    project_id: 9,
    kind: "merge_requests",
    iid: 3,
  });
  const evidence = evidencePayload();
  const [evidencePath] = await writeArtifact(root, "evidence_snapshot", evidence);
  const result = { status: "ok", changed: [], complete: true, head_sha: "c" };
  const reportPayload = finalizePayload(result, evidencePath, evidence, "evidence_snapshot");
  assert.equal(reportPayload.external_mutations, false);
  assert.equal(reportPayload.evidence_kind, "evidence_snapshot");
  assert.equal(
    reportPayload.evidence_digest,
    createHash("sha256").update(readFileSync(evidencePath)).digest("hex"),
  );
  assert.equal(reportPayload.evidence_fingerprint_digest, digest(fingerprint(evidence)));
  const [reportPath] = await writeArtifact(root, "finalize_report", reportPayload);
  const [report, reportDigest] = validateFinalizeReport(reportPath, evidencePath, evidence);
  assert.equal(report.status, "ok");
  assert.equal(reportDigest, createHash("sha256").update(readFileSync(reportPath)).digest("hex"));
  const stalePayload = { ...reportPayload, status: "stale" };
  const [stalePath] = await writeArtifact(root, "finalize_report", stalePayload);
  assert.throws(
    () => validateFinalizeReport(stalePath, evidencePath, evidence),
    isWorkflowError(/stale, incomplete, or does not bind exact evidence/),
  );
  const mismatchedEvidence = evidencePayload();
  const [otherPath] = await writeArtifact(root, "evidence_snapshot", mismatchedEvidence);
  assert.throws(
    () => validateFinalizeReport(reportPath, otherPath, evidence),
    isWorkflowError(/stale, incomplete, or does not bind exact evidence/),
  );
});

test("evidence from root resolves pointers and legacy bundles", async (t) => {
  withStateHome(t);
  const root = await stateDirectory("code-review", {
    hostname: "gitlab.example",
    project_id: 4,
    kind: "merge_requests",
    iid: 2,
  });
  const evidence = evidencePayload();
  const [evidencePath, evidenceDigest] = await writeArtifact(root, "evidence_snapshot", evidence);
  writeJson(`${root}/review-evidence.json`, {
    evidence_path: evidencePath,
    evidence_digest: evidenceDigest,
  });
  const resolved = evidenceFromRoot(root, "review-evidence.json");
  assert.equal(resolved.source, evidencePath);
  assert.equal(resolved.payload.profile, "code-review");

  writeJson(`${root}/current.json`, {
    evidence_path: evidencePath,
    evidence_digest: evidenceDigest,
  });
  assert.equal(evidenceFromRoot(root).source, evidencePath);

  const escaping = JSON.parse(readFileSync(`${root}/review-evidence.json`, "utf8"));
  escaping.evidence_path = `${dirname(root)}/other/${evidenceDigest}.json`;
  writeJson(`${root}/review-evidence.json`, escaping);
  assert.throws(
    () => evidenceFromRoot(root, "review-evidence.json"),
    isWorkflowError(/escapes collection root/),
  );

  rmSync(`${root}/review-evidence.json`);
  rmSync(`${root}/current.json`);
  assert.throws(() => evidenceFromRoot(root), isWorkflowError(/artifact is unavailable/));
  const legacy = JSON.parse(readFileSync(evidencePath, "utf8"));
  writeFileSync(`${root}/bundle.json`, JSON.stringify(legacy));
  assert.equal(evidenceFromRoot(root).source, `${root}/bundle.json`);
  assert.throws(
    () => evidenceFromRoot(root, "unexpected.json"),
    isWorkflowError(/pointer name is invalid/),
  );
});

test("write json atomically replaces pointer state", (t) => {
  const root = temporaryDirectory(t);
  const pointer = join(root, "current.json");
  writeJson(pointer, { a: 1 });
  writeJson(pointer, { b: 2 });
  assert.deepEqual(JSON.parse(readFileSync(pointer, "utf8")), { b: 2 });
  assert.equal(readdirSync(root).length, 1);
  assert.equal(statSync(pointer).mode & 0o777, 0o600);
});

test("fingerprint keeps the canonical comparison order", () => {
  const bundle = {
    profile: "code-review",
    target: { iid: 1 },
    head_sha: "c",
    base_sha: "a",
    start_sha: "b",
    object: { state: "opened" },
    labels: component(),
    discussions: component(),
    changed_files: component(),
    commits: component(),
    pipelines: component(),
    retrieval_complete: true,
    prepared_at: CREATED_AT,
  };
  const value = fingerprint(bundle);
  assert.deepEqual(Object.keys(value), [
    "target",
    "head_sha",
    "base_sha",
    "start_sha",
    "object",
    "labels",
    "discussions",
    "changed_files",
    "commits",
    "pipelines",
    "retrieval_complete",
  ]);
  const mrBundle = { ...bundle, profile: "mr-prepare", project: { id: 1 } };
  assert.deepEqual(Object.keys(fingerprint(mrBundle)), ["mr_project", ...Object.keys(value)]);
  assert.equal(isDigest(digest(value)), true);
});

test("glab text streams a bounded trace through a child process", async (t) => {
  const root = temporaryDirectory(t);
  const glabDir = join(root, "bin");
  mkdirSync(glabDir, { recursive: true });
  const glabPath = join(glabDir, "glab");
  writeFileSync(
    glabPath,
    [
      "#!/usr/bin/env node",
      'process.stdout.write("HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\n\\r\\ntrace body\\n");',
      "",
    ].join("\n"),
  );
  chmodSync(glabPath, 0o755);
  const previousPath = process.env.PATH;
  process.env.PATH = `${glabDir}:${previousPath}`;
  t.after(() => {
    process.env.PATH = previousPath;
  });
  const result = await glabText("gitlab.example", "projects/5/jobs/9/trace");
  assert.equal(result.text, "trace body\n");
  assert.equal(result.complete, true);
});

test("glab text reports a failed trace request", async (t) => {
  const root = temporaryDirectory(t);
  const glabDir = join(root, "bin");
  mkdirSync(glabDir, { recursive: true });
  const glabPath = join(glabDir, "glab");
  writeFileSync(
    glabPath,
    ["#!/usr/bin/env node", 'process.stderr.write("boom");', "process.exit(3);", ""].join("\n"),
  );
  chmodSync(glabPath, 0o755);
  const previousPath = process.env.PATH;
  process.env.PATH = `${glabDir}:${previousPath}`;
  t.after(() => {
    process.env.PATH = previousPath;
  });
  await assert.rejects(
    glabText("gitlab.example", "projects/5/jobs/9/trace"),
    isWorkflowError(/failed with status 3/),
  );
});

test("collect gathers evidence and finalize confirms freshness", async (t) => {
  const stateRoot = withStateHome(t);
  const glabDir = join(stateRoot, "bin");
  mkdirSync(glabDir, { recursive: true });
  const headSha = "c".repeat(40);
  const baseSha = "a".repeat(40);
  const startSha = "b".repeat(40);
  const diffRefs = { head_sha: headSha, base_sha: baseSha, start_sha: startSha };
  const responses = new Map([
    ["projects/group%2Fproj", { id: 42 }],
    ["projects/42/labels", []],
    ["projects/42/merge_requests/7", { iid: 7, diff_refs: diffRefs }],
    ["projects/42/merge_requests/7/discussions", []],
    [
      "projects/42/merge_requests/7/changes",
      { overflow: false, changes: [], changes_count: "0", diff_refs: diffRefs },
    ],
    ["projects/42/merge_requests/7/commits", [{ id: headSha }]],
    ["projects/42/merge_requests/7/pipelines", [{ id: 5, sha: headSha, status: "success" }]],
    ["projects/42/pipelines/5/jobs", []],
    ["projects/42/pipelines/5/bridges", []],
  ]);
  const glabPath = join(glabDir, "glab");
  const script = [
    "#!/usr/bin/env node",
    "const endpoint = process.argv[process.argv.length - 1].split('?')[0];",
    `const responses = ${JSON.stringify([...responses.entries()])};`,
    "const match = responses.find(([prefix]) => endpoint === prefix);",
    "if (match === undefined) { process.stderr.write('unexpected ' + endpoint); process.exit(1); }",
    "process.stdout.write(JSON.stringify(match[1]));",
    "",
  ].join("\n");
  writeFileSync(glabPath, script);
  chmodSync(glabPath, 0o755);
  const previousPath = process.env.PATH;
  process.env.PATH = `${glabDir}:${previousPath}`;
  t.after(() => {
    process.env.PATH = previousPath;
  });

  const target = parseTarget(
    "https://gitlab.example/group/proj/-/merge_requests/7",
    new Set(["merge_requests"]),
  );
  const bundle = await collect(target, "code-review");
  assert.equal(bundle.retrieval_complete, true);
  assert.equal(bundle.head_sha, headSha);
  assert.equal(bundle.components_complete.pipelines, true);
  const root = bundle.artifact_root;
  const pointerPath = join(root, "review-evidence.json");
  writeJson(pointerPath, {
    evidence_path: bundle.preview_artifact_path,
    evidence_digest: bundle.preview_digest,
  });
  const [, payload] = artifactPayload(bundle.preview_artifact_path, "evidence_snapshot");
  assert.equal(payload.profile, "code-review");
  assert.deepEqual(payload.target.project_id, 42);

  const result = await finalize(root, "review-evidence.json");
  assert.equal(result.status, "ok");
  assert.deepEqual(result.changed, []);
  assert.equal(result.complete, true);
  assert.equal(
    result.evidence_digest,
    createHash("sha256").update(readFileSync(bundle.preview_artifact_path)).digest("hex"),
  );
});
