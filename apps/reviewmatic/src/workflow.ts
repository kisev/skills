import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import {
  artifactPayload,
  artifactRoot,
  collect,
  detailedFindingsAreValid,
  digest,
  emit,
  evidenceFromRoot,
  finalize as finalizeEvidence,
  finalizePayload,
  fingerprint,
  readJson,
  validateCritic,
  validateDecision,
  validateFinalizeReport,
  validateReleaseReadiness,
  WorkflowError,
  writeArtifact,
} from "./contract.js";
import {
  advanceProgress,
  beginReview,
  contentAddressedArtifact,
  contextsMatch,
  loadProgress,
  prepareContext,
  progressArtifact,
  refreshContext,
  reviewStatus,
  runnerAction,
  scaffoldReview,
  templateReview,
  reportReview,
  validateContextBinding,
  validateReviewVerdict,
} from "./context.js";

type Json = Record<string, unknown>;

export interface WorkflowArguments {
  command: string;
  artifactRoot?: string;
  evidence?: string;
  repoRoot?: string | null;
  incremental?: string;
  reviewMode?: string;
  locale?: string;
  kind?: string;
  input?: string;
  report?: string;
  criticReceipt?: string | null;
  finalizeReport?: string;
  context?: string;
  mode?: string;
  decision?: string;
  content?: string;
}

function resolvePath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return resolve(path);
  }
}

function pick(progress: Json, keys: readonly string[]): Json {
  const result: Json = {};
  for (const key of keys) result[key] = progress[key];
  return result;
}

export async function prepared(args: WorkflowArguments, bundle: Json): Promise<Json> {
  await beginReview(
    String(bundle.preview_artifact_path),
    String(bundle.preview_digest),
    String(bundle.artifact_root),
    args.repoRoot ?? null,
    args.reviewMode ?? "normal",
    args.locale ?? "en",
    args.incremental ?? "auto",
  );
  return {
    stage: "prepared",
    next_action: runnerAction(
      "context",
      [
        "--evidence",
        String(bundle.preview_artifact_path),
        "--repo-root",
        args.repoRoot != null ? resolvePath(args.repoRoot) : "<checkout>",
        "--incremental",
        args.incremental ?? "auto",
        "--review-mode",
        args.reviewMode ?? "normal",
        "--locale",
        args.locale ?? "en",
      ],
      args.repoRoot == null ? ["repo_root"] : [],
    ),
  };
}

export async function selected(root: string, stages: Set<string>): Promise<Json> {
  const status = await reviewStatus(root);
  const stage = (status.resume_stage ?? status.stage) as string;
  const progress = loadProgress(root);
  if (!stages.has(stage) || progress === null) {
    throw new WorkflowError(`review command is out of order; current stage is ${stage}`);
  }
  return progress;
}

export async function finalize(rootValue: string): Promise<Json> {
  const root = await artifactRoot(rootValue);
  const progress = await selected(root, new Set(["context_ready", "finalize_missing"]));
  let result = await finalizeEvidence(rootValue, "review-evidence.json");
  const { source, payload: evidence } = evidenceFromRoot(root, "review-evidence.json");
  result = finalizePayload(result, source, evidence, "evidence_snapshot");
  const [path, digestValue] = await writeArtifact(root, "finalize_report", result);
  const response: Json = {
    status: result.status,
    result: result,
    artifact_path: path,
    digest: digestValue,
    external_mutations: false,
  };
  if (result.status === "ok") {
    await advanceProgress(root, "decision_missing", {
      expectedStages: new Set(["context_ready", "finalize_missing"]),
      expected: pick(progress, [
        "evidence_path",
        "evidence_digest",
        "context_path",
        "context_digest",
        "critic_receipt_path",
        "critic_receipt_digest",
      ]),
      finalize_report_path: path,
      finalize_report_digest: digestValue,
      decision_path: null,
      decision_digest: null,
      plan_path: null,
      plan_digest: null,
    });
    response.stage = "decision_missing";
    response.next_action = runnerAction("template-review", [
      "--artifact-root",
      root,
      "--kind",
      "decision",
    ]);
  }
  return response;
}

export async function record(args: WorkflowArguments): Promise<Json> {
  const [evidenceDoc, evidence] = artifactPayload(args.evidence!, "evidence_snapshot");
  const evidenceDigest = digest(evidenceDoc);
  const root = await artifactRoot(String(evidence.artifact_root));
  const value = readJson(args.input!, "artifact input");
  let progress: Json | null = null;
  if (args.kind !== "critic_receipt") {
    if (args.kind === "release_readiness") {
      validateReleaseReadiness(value, evidence, evidenceDigest);
    } else if (
      value.schema !== "portable-gitlab/analysis-report/v2" ||
      value.evidence_digest !== evidenceDigest
    ) {
      throw new WorkflowError("analysis report does not bind evidence");
    }
    if (args.kind === "analysis_report" && !detailedFindingsAreValid(value.findings)) {
      throw new WorkflowError("new code review findings require complete structured evidence");
    }
  } else {
    progress = await selected(root, new Set(["critic_missing"]));
    if (realpathSync(args.evidence!) !== progress.evidence_path) {
      throw new WorkflowError("critic receipt does not bind selected evidence");
    }
    const artifact = progressArtifact(root, progress, "context", "review_context");
    if (artifact === null) {
      throw new WorkflowError("critic receipt requires the selected review context");
    }
    const scope =
      progress.mode === "incremental"
        ? ((artifact[1].incremental as Json).incremental_delta_digest as string)
        : null;
    validateCritic(value, evidenceDigest, scope);
    if (!detailedFindingsAreValid(value.findings)) {
      throw new WorkflowError("critic findings require complete structured evidence");
    }
  }
  const [path, digestValue] = await writeArtifact(root, args.kind!, value);
  const response: Json = {
    status: "ok",
    artifact_path: path,
    digest: digestValue,
    external_mutations: false,
  };
  if (args.kind === "critic_receipt") {
    await advanceProgress(root, "finalize_missing", {
      expectedStages: new Set(["context_ready"]),
      expected: pick(progress!, [
        "evidence_path",
        "evidence_digest",
        "context_path",
        "context_digest",
      ]),
      critic_receipt_path: path,
      critic_receipt_digest: digestValue,
      finalize_report_path: null,
      finalize_report_digest: null,
      decision_path: null,
      decision_digest: null,
      plan_path: null,
      plan_digest: null,
    });
    response.stage = "finalize_missing";
    response.next_action = runnerAction("finalize", ["--artifact-root", root]);
  }
  return response;
}

export async function decide(args: WorkflowArguments): Promise<Json> {
  const [evidenceDoc, evidence] = artifactPayload(args.evidence!, "evidence_snapshot");
  const evidenceDigest = digest(evidenceDoc);
  const root = await artifactRoot(String(evidence.artifact_root));
  const progress = await selected(root, new Set(["decision_missing"]));
  if (
    (
      [
        [args.evidence ?? null, "evidence_path"],
        [args.context ?? null, "context_path"],
        [args.finalizeReport ?? null, "finalize_report_path"],
        [args.criticReceipt ?? null, "critic_receipt_path"],
      ] as Array<[string | null, string]>
    ).some(([actual, key]) => (actual === null ? null : resolvePath(actual)) !== progress[key]) ||
    args.mode !== progress.mode
  ) {
    throw new WorkflowError("finalize-review arguments do not match the selected review progress");
  }
  const current = await collect(evidence.target as Json, "code-review", { persist: false });
  if (
    current.retrieval_complete !== true ||
    digest(fingerprint(evidence)) !== digest(fingerprint(current))
  ) {
    throw new WorkflowError("evidence is stale or incomplete at final review");
  }
  const [, selectedContext, contextDigest] = await validateContextBinding(
    args.context!,
    args.evidence!,
  );
  const freshContext = await refreshContext(selectedContext, args.evidence!);
  if (
    selectedContext.complete !== true ||
    freshContext.complete !== true ||
    !contextsMatch(selectedContext, freshContext)
  ) {
    throw new WorkflowError("review context is stale or incomplete at final review");
  }
  const [, finalizeDigest] = validateFinalizeReport(args.finalizeReport!, args.evidence!, evidence);
  const report = readJson(args.report!, "review decision");
  let receipt: Json | null = null;
  let receiptDigest: string | null = null;
  if (args.criticReceipt != null) {
    [, receipt, receiptDigest] = contentAddressedArtifact(
      args.criticReceipt,
      root,
      "critic_receipt",
    );
    const scope =
      args.mode === "incremental"
        ? ((receipt.incremental as Json).incremental_delta_digest as string)
        : null;
    validateCritic(receipt, evidenceDigest, scope);
    if (!detailedFindingsAreValid(receipt.findings)) {
      throw new WorkflowError("critic findings require complete structured evidence");
    }
    if (receipt.run_id === report.run_id || receipt.session_id === report.session_id) {
      throw new WorkflowError("critic receipt is not independent of the primary review");
    }
  }
  if (!detailedFindingsAreValid(report.findings)) {
    throw new WorkflowError("review findings require complete structured evidence");
  }
  validateDecision(report, evidenceDigest, receipt, args.mode!, contextDigest, receiptDigest);
  if (report.finalize_digest !== finalizeDigest) {
    throw new WorkflowError("review decision does not bind exact finalize report");
  }
  if (
    evidence.retrieval_complete !== true ||
    (report.verdict === "ready" && report.blocking_findings)
  ) {
    throw new WorkflowError("incomplete evidence or unresolved blocking findings prohibit ready");
  }
  const criticFindings = receipt !== null ? (receipt.findings as Json[]) : [];
  const candidates = [...(report.findings as Json[]), ...criticFindings];
  const ids = candidates.map((item) => item.id);
  const idPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
  if (new Set(ids).size !== ids.length || ids.some((item) => !idPattern.test(String(item)))) {
    throw new WorkflowError("primary and critic finding IDs must be unique");
  }
  const responses = new Map((report.responses as Json[]).map((item) => [item.id, item]));
  const accepted = candidates.filter((item) => responses.get(item.id)!.decision === "accept");
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  accepted.sort((left, right) => order[left.severity as string] - order[right.severity as string]);
  validateReviewVerdict(report, accepted, evidence);
  const payload: Json = {
    ...report,
    critic_findings: criticFindings,
    accepted_findings: accepted,
    critic_target_finding_ids:
      receipt !== null ? ((receipt.target_finding_ids as Json[] | undefined) ?? []) : [],
  };
  const [path, digestValue] = await writeArtifact(root, "review_decision", payload);
  await advanceProgress(root, "content_missing", {
    expectedStages: new Set(["decision_missing"]),
    expected: pick(progress, [
      "evidence_path",
      "evidence_digest",
      "context_path",
      "context_digest",
      "critic_receipt_path",
      "critic_receipt_digest",
      "finalize_report_path",
      "finalize_report_digest",
    ]),
    decision_path: path,
    decision_digest: digestValue,
    plan_path: null,
    plan_digest: null,
  });
  return {
    status: "ok",
    artifact_path: path,
    digest: digestValue,
    external_mutations: false,
    stage: "content_missing",
    next_action: runnerAction("template-review", ["--artifact-root", root, "--kind", "content"]),
  };
}

export async function dispatch(args: WorkflowArguments): Promise<number | null> {
  let result: Json;
  if (args.command === "context") {
    result = await prepareContext(
      args.evidence!,
      args.repoRoot!,
      args.incremental ?? "auto",
      args.reviewMode ?? "normal",
      args.locale ?? "en",
    );
  } else if (args.command === "status" || args.command === "next") {
    result = await reviewStatus(args.artifactRoot!);
    emit(result);
    return 0;
  } else if (args.command === "template-review") {
    result = await templateReview(args.artifactRoot!, args.kind!);
  } else if (args.command === "report-review") {
    result = await reportReview(args.artifactRoot!);
    emit(result);
    return result.status === "ok" ? 0 : 4;
  } else if (args.command === "finalize") {
    result = await finalize(args.artifactRoot!);
  } else if (args.command === "record-artifact") {
    result = await record(args);
  } else if (args.command === "finalize-review") {
    result = await decide(args);
  } else if (args.command === "scaffold-review") {
    const [, evidence] = artifactPayload(args.evidence!, "evidence_snapshot");
    const progress = await selected(
      await artifactRoot(String(evidence.artifact_root)),
      new Set(["content_missing"]),
    );
    if (
      (
        [
          [args.evidence!, "evidence_path"],
          [args.context!, "context_path"],
          [args.decision!, "decision_path"],
        ] as Array<[string, string]>
      ).some(([actual, key]) => resolvePath(actual) !== progress[key])
    ) {
      throw new WorkflowError(
        "scaffold-review arguments do not match the selected review progress",
      );
    }
    result = await scaffoldReview(args.evidence!, args.context!, args.decision!, args.content!);
  } else {
    return null;
  }
  emit(result);
  return (result.status === undefined ? "ok" : result.status) === "ok" ? 0 : 2;
}
