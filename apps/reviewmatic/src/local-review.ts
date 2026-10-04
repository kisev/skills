import { existsSync, lstatSync, readFileSync, realpathSync, type Stats } from "node:fs";
import { resolve } from "node:path";
import {
  ARTIFACT_VERSION,
  MAX_BYTES,
  WorkflowError,
  artifactPayload,
  artifactSchema,
  digest,
  gitRead,
  isDigest,
  privateDirectory,
  readJson,
  regularFile,
  rejectEnvelopeWrapper,
  stateDirectory,
  writeArtifact,
  writeJson,
} from "./contract.js";
import { runnerAction } from "./context.js";
import { participantSelectionIssues, schemaIssues, upsertByIdentity } from "./draft.js";
import type { DraftIssue } from "./schema-issues.js";
import { contentDigest } from "./state-artifacts.js";
import {
  bindQuestionContexts,
  canonicalPackageDigest,
  collectAnswers,
  extractSupersededResults,
  isCurrentResult,
  localSectionDigests,
  narrativePackageDigest,
  packageTemplateForLocal,
  questionContextVersionList,
  questionContextVersions,
  questionReport,
  readPackagePointer,
  recordedPackage,
  supersedesDigest,
  validateAnswers,
  validatePackagePayload,
  validateVerifications,
  writeContextPackage,
} from "./context-package.js";

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function truthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === "string") return value.length > 0;
  if (typeof value === "number") return value !== 0;
  if (Array.isArray(value)) return value.length > 0;
  if (isObject(value)) return Object.keys(value).length > 0;
  return true;
}

function pythonGet(target: Record<string, unknown>, key: string): unknown {
  return Object.hasOwn(target, key) ? target[key] : null;
}

function compareCodePoints(left: string, right: string): number {
  const first = Array.from(left);
  const second = Array.from(right);
  const length = Math.min(first.length, second.length);
  for (let index = 0; index < length; index += 1) {
    const delta = (first[index].codePointAt(0) ?? 0) - (second[index].codePointAt(0) ?? 0);
    if (delta !== 0) return delta;
  }
  return first.length - second.length;
}

function addressedPayload(
  root: string,
  kind: string,
  digestValue: string,
): Record<string, unknown> {
  if (!isDigest(digestValue)) {
    throw new WorkflowError("local review artifact digest is invalid");
  }
  const [envelope, payload] = artifactPayload(
    `${root}/artifacts/${kind}/${digestValue}.json`,
    kind,
  );
  if (digest(envelope) !== digestValue) {
    throw new WorkflowError("local review artifact digest does not match its content");
  }
  return payload;
}

export function baseline(root: string): [string | null, Record<string, unknown> | null, string] {
  const pointer = `${root}/local-review.json`;
  let present = existsSync(pointer);
  if (!present) {
    try {
      present = lstatSync(pointer).isSymbolicLink();
    } catch {
      present = false;
    }
  }
  if (!present) {
    return [null, null, "no_previous_review"];
  }
  let digestValue: string;
  let report: Record<string, unknown>;
  try {
    const value = readJson(pointer, "local review pointer");
    const reviewDigest = pythonGet(value, "review_digest");
    if (typeof reviewDigest !== "string" || !isDigest(reviewDigest)) {
      throw new WorkflowError("local review pointer has no valid digest");
    }
    digestValue = reviewDigest;
    report = addressedPayload(root, "local_review_report", reviewDigest);
    validateReport(report);
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    return [null, null, "previous_review_unavailable"];
  }
  return [digestValue, report, "previous_review_available"];
}

function compatible(previous: Record<string, unknown>, current: Record<string, unknown>): boolean {
  return (
    previous.retrieval_complete === true &&
    current.retrieval_complete === true &&
    (["repo_root", "profile", "base_sha", "head_sha", "ref", "artifact_root"] as const).every(
      (key) => pythonGet(previous, key) === pythonGet(current, key),
    )
  );
}

type Opcode = ["equal" | "change", number, number, number, number];

function splitKeepEnds(value: string): string[] {
  const result: string[] = [];
  const pattern = /\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/g;
  let start = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    result.push(value.slice(start, match.index + match[0].length));
    start = match.index + match[0].length;
  }
  if (start < value.length) {
    result.push(value.slice(start));
  }
  return result;
}

function matchingBlocks(a: string[], b: string[]): Array<[number, number, number]> {
  const b2j = new Map<string, number[]>();
  b.forEach((line, index) => {
    const indices = b2j.get(line);
    if (indices === undefined) {
      b2j.set(line, [index]);
    } else {
      indices.push(index);
    }
  });
  if (b.length >= 200) {
    const ntest = Math.floor(b.length / 100) + 1;
    const popular: string[] = [];
    for (const [line, indices] of b2j) {
      if (indices.length > ntest) {
        popular.push(line);
      }
    }
    for (const line of popular) {
      b2j.delete(line);
    }
  }
  const findLongestMatch = (
    alo: number,
    ahi: number,
    blo: number,
    bhi: number,
  ): [number, number, number] => {
    let besti = alo;
    let bestj = blo;
    let bestsize = 0;
    let j2len = new Map<number, number>();
    for (let i = alo; i < ahi; i += 1) {
      const newj2len = new Map<number, number>();
      for (const j of b2j.get(a[i] as string) ?? []) {
        if (j < blo) continue;
        if (j >= bhi) break;
        const k = (j2len.get(j - 1) ?? 0) + 1;
        newj2len.set(j, k);
        if (k > bestsize) {
          besti = i - k + 1;
          bestj = j - k + 1;
          bestsize = k;
        }
      }
      j2len = newj2len;
    }
    while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) {
      besti -= 1;
      bestj -= 1;
      bestsize += 1;
    }
    while (
      besti + bestsize < ahi &&
      bestj + bestsize < bhi &&
      a[besti + bestsize] === b[bestj + bestsize]
    ) {
      bestsize += 1;
    }
    return [besti, bestj, bestsize];
  };
  const queue: Array<[number, number, number, number]> = [[0, a.length, 0, b.length]];
  const found: Array<[number, number, number]> = [];
  while (queue.length > 0) {
    const [alo, ahi, blo, bhi] = queue.pop() as [number, number, number, number];
    const match = findLongestMatch(alo, ahi, blo, bhi);
    if (match[2] > 0) {
      found.push(match);
      if (alo < match[0] && blo < match[1]) {
        queue.push([alo, match[0], blo, match[1]]);
      }
      if (match[0] + match[2] < ahi && match[1] + match[2] < bhi) {
        queue.push([match[0] + match[2], ahi, match[1] + match[2], bhi]);
      }
    }
  }
  found.sort((left, right) => left[0] - right[0] || left[1] - right[1] || left[2] - right[2]);
  const nonAdjacent: Array<[number, number, number]> = [];
  let i1 = 0;
  let j1 = 0;
  let k1 = 0;
  for (const [i2, j2, k2] of found) {
    if (i1 + k1 === i2 && j1 + k1 === j2) {
      k1 += k2;
    } else {
      if (k1 > 0) {
        nonAdjacent.push([i1, j1, k1]);
      }
      i1 = i2;
      j1 = j2;
      k1 = k2;
    }
  }
  if (k1 > 0) {
    nonAdjacent.push([i1, j1, k1]);
  }
  return nonAdjacent;
}

function opcodesFromBlocks(
  aLength: number,
  bLength: number,
  blocks: Array<[number, number, number]>,
): Opcode[] {
  const opcodes: Opcode[] = [];
  let aIndex = 0;
  let bIndex = 0;
  for (const [i, j, size] of blocks) {
    if (aIndex < i || bIndex < j) {
      opcodes.push(["change", aIndex, i, bIndex, j]);
    }
    opcodes.push(["equal", i, i + size, j, j + size]);
    aIndex = i + size;
    bIndex = j + size;
  }
  if (aIndex < aLength || bIndex < bLength) {
    opcodes.push(["change", aIndex, aLength, bIndex, bLength]);
  }
  return opcodes;
}

function groupedOpcodes(opcodes: Opcode[], n = 3): Opcode[][] {
  if (opcodes.length === 0) return [];
  const codes = opcodes.map((code) => [...code] as Opcode);
  const first = codes[0] as Opcode;
  if (first[0] === "equal" && first[2] - first[1] > n) {
    codes[0] = ["equal", first[2] - n, first[2], first[4] - n, first[4]];
  }
  const last = codes[codes.length - 1] as Opcode;
  if (last[0] === "equal" && last[2] - last[1] > n) {
    codes[codes.length - 1] = ["equal", last[1], last[1] + n, last[3], last[3] + n];
  }
  const groups: Opcode[][] = [];
  let group: Opcode[] = [];
  for (const code of codes) {
    if (code[0] === "equal" && code[2] - code[1] > 2 * n) {
      group.push([
        "equal",
        code[1],
        Math.min(code[2], code[1] + n),
        code[3],
        Math.min(code[4], code[3] + n),
      ]);
      groups.push(group);
      group = [
        ["equal", Math.max(code[1], code[2] - n), code[2], Math.max(code[3], code[4] - n), code[4]],
      ];
      continue;
    }
    group.push(code);
  }
  if (group.length > 0 && !(group.length === 1 && group[0][0] === "equal")) {
    groups.push(group);
  }
  return groups;
}

function formatRangeUnified(start: number, stop: number): string {
  const beginning = start + 1;
  const length = stop - start;
  if (length === 1) return `${beginning}`;
  if (length === 0) return `${beginning - 1},0`;
  return `${beginning},${length}`;
}

function unifiedDiff(before: string, after: string, fromFile: string, toFile: string): string {
  const a = splitKeepEnds(before);
  const b = splitKeepEnds(after);
  const lines: string[] = [];
  for (const group of groupedOpcodes(opcodesFromBlocks(a.length, b.length, matchingBlocks(a, b)))) {
    if (lines.length === 0) {
      lines.push(`--- ${fromFile}\n`, `+++ ${toFile}\n`);
    }
    const first = group[0] as Opcode;
    const last = group[group.length - 1] as Opcode;
    lines.push(
      `@@ -${formatRangeUnified(first[1], last[2])} +${formatRangeUnified(first[3], last[4])} @@\n`,
    );
    for (const [tag, i1, i2, j1, j2] of group) {
      if (tag === "equal") {
        for (let index = i1; index < i2; index += 1) {
          lines.push(` ${a[index]}`);
        }
        continue;
      }
      for (let index = i1; index < i2; index += 1) {
        lines.push(`-${a[index]}`);
      }
      for (let index = j1; index < j2; index += 1) {
        lines.push(`+${b[index]}`);
      }
    }
  }
  return lines.join("");
}

function sectionDelta(
  previous: Record<string, unknown>,
  current: Record<string, unknown>,
): Record<string, unknown> {
  const delta: Record<string, unknown> = {};
  const previousSections = previous.sections as Record<string, Record<string, unknown>>;
  const currentSections = current.sections as Record<string, Record<string, unknown>>;
  for (const name of ["committed", "staged", "unstaged"]) {
    const before = previousSections[name] as Record<string, unknown>;
    const after = currentSections[name] as Record<string, unknown>;
    if (digest(before) !== digest(after)) {
      delta[name] = unifiedDiff(
        before.diff as string,
        after.diff as string,
        `previous/${name}`,
        `current/${name}`,
      );
    }
  }
  const previousItems = new Map(
    (
      (previousSections.untracked as Record<string, unknown>).items as Record<string, unknown>[]
    ).map((item) => [item.path as string, item]),
  );
  const afterItems = new Map(
    ((currentSections.untracked as Record<string, unknown>).items as Record<string, unknown>[]).map(
      (item) => [item.path as string, item],
    ),
  );
  const paths = [...new Set([...previousItems.keys(), ...afterItems.keys()])].sort(
    compareCodePoints,
  );
  const changed = paths
    .filter(
      (path) => digest(previousItems.get(path) ?? null) !== digest(afterItems.get(path) ?? null),
    )
    .map((path) => ({
      path: path,
      before: previousItems.get(path) ?? null,
      after: afterItems.get(path) ?? null,
    }));
  if (changed.length > 0) {
    delta.untracked = changed;
  }
  return delta;
}

// Pure computation behind prepareFollowup: baseline selection, reuse mode,
// section delta, and the report/package templates. No file is written, so
// read-only consumers (scope-review) can reconstruct the exact prepared view
// without mutating preparation state.
export function localFollowupPlan(
  root: string,
  bundle: Record<string, unknown>,
  digestValue: string,
  incremental: string,
): Record<string, unknown> {
  const [previousDigest, report, initialReason] = baseline(root);
  let reason = initialReason;
  let prior: Record<string, unknown> | null = null;
  if (report !== null) {
    try {
      prior = addressedPayload(root, "local_wip_snapshot", report.evidence_digest as string);
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
      reason = "previous_evidence_unavailable";
    }
  }
  const reusable = prior !== null && compatible(prior, bundle);
  const delta = reusable && prior !== null ? sectionDelta(prior, bundle) : {};
  let mode = "full";
  if (reusable && incremental === "auto") {
    mode = Object.keys(delta).length > 0 ? "incremental" : "unchanged";
    reason = Object.keys(delta).length > 0 ? "changed_local_evidence" : "unchanged_local_evidence";
  } else if (incremental === "off") {
    reason = "explicit_full_review";
  } else if (prior !== null && !reusable) {
    reason = "incompatible_boundary_or_incomplete_evidence";
  }
  const retained = reusable ? report : null;
  const packageTemplate = packageTemplateForLocal(
    bundle,
    digestValue,
    retained as Record<string, unknown> | null,
  );
  const template = {
    evidence_digest: digestValue,
    previous_review_digest: previousDigest,
    mode: mode,
    context_package: null,
    question_answers: [],
    question_verifications: [],
    task: retained
      ? structuredClone((retained as Record<string, unknown>).task)
      : {
          goal: "",
          acceptance_criteria: [],
          constraints: [],
          accepted_risks: [],
          deferred: [],
          decision_evidence: "",
        },
    task_change_reason: null,
    findings: retained ? structuredClone((retained as Record<string, unknown>).findings) : [],
    checks: [],
    assessment: "",
    verdict: "blocked",
    external_mutations: false,
  };
  const recorded = recordedPackage(root);
  const packageCurrent =
    recorded !== null &&
    recorded.payload.mode === "local" &&
    String((recorded.payload.binding as Record<string, unknown>).evidence_digest) === digestValue;
  const snapshotPath = `${root}/artifacts/local_wip_snapshot/${digestValue}.json`;
  return {
    mode: mode,
    reason: reason,
    baseline_compatible: reusable,
    previous_review_digest: previousDigest,
    previous_report: report,
    previous_evidence_digest: report ? report.evidence_digest : null,
    previous_ref: prior !== null ? pythonGet(prior, "ref") : null,
    delta: delta,
    report_template: template,
    draft_path: `${root}/local-review-draft.json`,
    context_package: {
      template_path: `${root}/local-context-package-input.json`,
      package_path: recorded === null ? null : recorded.path,
      package_digest: recorded === null ? null : recorded.digest,
      status: packageCurrent ? "recorded" : "pending",
      question_context_versions:
        packageCurrent && recorded !== null ? questionContextVersionList(recorded.payload) : null,
      record_command: runnerAction("record-package", [
        "--bundle",
        snapshotPath,
        "--input",
        `${root}/local-context-package-input.json`,
      ]).command,
    },
    package_template_payload: packageTemplate,
  };
}

export function prepareFollowup(
  root: string,
  bundle: Record<string, unknown>,
  digestValue: string,
  incremental: string,
): Record<string, unknown> {
  const plan = localFollowupPlan(root, bundle, digestValue, incremental);
  writeJson(
    `${root}/local-context-package-input.json`,
    plan.package_template_payload as Record<string, unknown>,
  );
  const { package_template_payload: _payload, ...followup } = plan;
  return followup;
}

// Selects the local review draft for the current snapshot: an existing draft
// bound to this exact evidence is reused verbatim (unfinished work survives),
// while a missing or stale draft is re-materialized from the pure follow-up
// plan, so runtime-owned fields always follow the current snapshot and
// baseline instead of a previous cycle's mechanical bindings.
export type LocalDraftSelection = {
  draft: Record<string, unknown>;
  materialized: boolean;
  plan: Record<string, unknown>;
};

export function selectLocalDraft(
  root: string,
  bundle: Record<string, unknown>,
  digestValue: string,
  incremental = "auto",
): LocalDraftSelection {
  const plan = localFollowupPlan(root, bundle, digestValue, incremental);
  const draftPath = `${root}/local-review-draft.json`;
  if (existsSync(draftPath)) {
    const draft = readJson(draftPath, "local review draft");
    if (pythonGet(draft, "evidence_digest") === digestValue) {
      return { draft: draft, materialized: false, plan: {} };
    }
    // A fresh preparation of identical evidence content (the envelope digest
    // changes through its creation stamp alone) adopts the unfinished draft:
    // runtime-owned fields follow the new snapshot while every agent section
    // survives, and the recorded package's authored content is carried into
    // the new template so re-recording stays mechanical.
    const currentDigest = pythonGet(draft, "evidence_digest");
    if (typeof currentDigest === "string" && isDigest(currentDigest)) {
      try {
        const prior = addressedPayload(root, "local_wip_snapshot", currentDigest);
        const sameBoundary =
          pythonGet(prior, "repo_root") === pythonGet(bundle, "repo_root") &&
          pythonGet(prior, "base_sha") === pythonGet(bundle, "base_sha") &&
          pythonGet(prior, "head_sha") === pythonGet(bundle, "head_sha") &&
          pythonGet(prior, "ref") === pythonGet(bundle, "ref");
        if (sameBoundary && Object.keys(sectionDelta(prior, bundle)).length === 0) {
          const adopted = structuredClone(draft);
          adopted.evidence_digest = digestValue;
          adopted.previous_review_digest = plan.previous_review_digest;
          adopted.mode = plan.mode;
          adopted.context_package = null;
          const recorded = recordedPackage(root);
          if (
            recorded !== null &&
            String((recorded.payload.binding as Record<string, unknown>).evidence_digest) ===
              currentDigest
          ) {
            const fresh = structuredClone(plan.package_template_payload as Record<string, unknown>);
            for (const key of [
              "goal",
              "acceptance_criteria",
              "background",
              "claims",
              "constraints",
              "prior_decisions",
              "questions",
              "supersedes",
            ])
              fresh[key] = structuredClone(recorded.payload[key] ?? fresh[key]);
            plan.package_template_payload = fresh;
            writeJson(`${root}/local-context-package-input.json`, fresh as Record<string, unknown>);
          }
          return { draft: adopted, materialized: true, plan: plan };
        }
      } catch {
        // A prior snapshot that cannot be read falls back to re-materializing.
      }
    }
  }
  const draft = structuredClone(plan.report_template) as Record<string, unknown>;
  const contextPackage = plan.context_package as Record<string, unknown>;
  if (contextPackage.status === "recorded") {
    draft.context_package = {
      path: contextPackage.package_path,
      digest: contextPackage.package_digest,
    };
  }
  // Historical superseded results are evidence, never mechanical bindings:
  // a stale draft's history survives the snapshot change.
  if (existsSync(draftPath)) {
    try {
      const stale = readJson(draftPath, "local review draft");
      const history = stale.superseded_question_results;
      if (Array.isArray(history) && history.length > 0) draft.superseded_question_results = history;
    } catch {
      // A unreadable stale draft is replaced, not trusted.
    }
  }
  return { draft: draft, materialized: true, plan: plan };
}

// Persists a selected draft. A re-materialized draft also refreshes the
// package template unless the on-disk template already binds this snapshot,
// in which case agent edits to it are preserved.
export function persistLocalDraft(
  root: string,
  digestValue: string,
  selection: LocalDraftSelection,
  draft: Record<string, unknown>,
): void {
  writeJson(`${root}/local-review-draft.json`, draft);
  if (!selection.materialized) return;
  const templatePath = `${root}/local-context-package-input.json`;
  let keep = false;
  if (existsSync(templatePath)) {
    try {
      const template = readJson(templatePath, "local context package template");
      const binding = pythonGet(template, "binding");
      keep = isObject(binding) && pythonGet(binding, "evidence_digest") === digestValue;
    } catch {
      keep = false;
    }
  }
  if (!keep) {
    writeJson(templatePath, selection.plan.package_template_payload as Record<string, unknown>);
  }
}

function validateFinding(finding: Record<string, unknown>): void {
  if (truthy(finding.blocking) && finding.status !== "open") {
    throw new WorkflowError("only open findings can block local acceptance");
  }
  if (finding.status === "accepted_risk" && !truthy(finding.decision_evidence)) {
    throw new WorkflowError("accepted risk requires the user's decision evidence");
  }
  if (
    truthy(finding.blocking) &&
    (finding.origin === "new_requirement" || finding.origin === "pre_existing") &&
    !truthy(finding.decision_evidence)
  ) {
    throw new WorkflowError("scope expansion requires explicit decision evidence");
  }
}

export function validateReport(report: Record<string, unknown>): void {
  const schema = artifactSchema();
  const defs = schema.$defs as Record<string, Record<string, unknown>>;
  const issues = schemaIssues(defs.local_review_payload as Record<string, unknown>, report, "$");
  if (issues.length > 0) {
    throw new WorkflowError(
      "local review report is invalid:\n" +
        issues.map((issue) => ` - ${issue.path}: ${issue.message}`).join("\n"),
    );
  }
  const findings = report.findings as Record<string, unknown>[];
  const ids = findings.map((finding) => finding.id);
  if (ids.length !== new Set(ids).size) {
    throw new WorkflowError("local review finding IDs must be unique");
  }
  for (const finding of findings) {
    validateFinding(finding);
  }
  const checks = report.checks as Record<string, unknown>[];
  if (checks.filter((check) => truthy(check.required)).length === 0) {
    throw new WorkflowError("local review must include required acceptance checks");
  }
  const expected = expectedLocalVerdict(findings, checks);
  if (report.verdict !== expected) {
    throw new WorkflowError(`local review verdict must be ${expected} for the recorded evidence`);
  }
}

function validateContinuity(
  report: Record<string, unknown>,
  previous: Record<string, unknown>,
): void {
  if (digest(report.task) !== digest(previous.task) && !truthy(report.task_change_reason)) {
    throw new WorkflowError(
      "changed task boundary requires decision evidence in task_change_reason",
    );
  }
  const findings = new Map(
    (report.findings as Record<string, unknown>[]).map((finding) => [
      finding.id as string,
      finding,
    ]),
  );
  for (const old of previous.findings as Record<string, unknown>[]) {
    const updated = findings.get(old.id as string);
    if (updated === undefined) {
      throw new WorkflowError("previous findings must retain their stable IDs and dispositions");
    }
    const reopened =
      updated.status === "open" &&
      (old.status !== "open" || (truthy(updated.blocking) && !truthy(old.blocking)));
    if (reopened) {
      const changedBasis =
        (["requirement", "scenario", "evidence"] as const).some(
          (key) => updated[key] !== old[key],
        ) ||
        (digest(report.task) !== digest(previous.task) && truthy(report.task_change_reason));
      const changedDecision =
        truthy(updated.decision_evidence) && updated.decision_evidence !== old.decision_evidence;
      if (!truthy(updated.reopen_reason) || !(changedBasis || changedDecision)) {
        throw new WorkflowError("reopening a finding requires changed facts or a user decision");
      }
    }
  }
}

function localSection(root: string, name: string, args: string[]): Record<string, unknown> {
  const value = gitRead(root, args) as string;
  return {
    name: name,
    diff: value,
    sha256: contentDigest(Buffer.from(value, "utf8")),
    complete: true,
    errors: [],
  };
}

function localUntracked(root: string): Record<string, unknown> {
  const raw = gitRead(root, ["ls-files", "--others", "--exclude-standard", "-z"], false) as Buffer;
  const encodedPaths: Buffer[] = [];
  let start = 0;
  for (let index = 0; index <= raw.length; index += 1) {
    if (index === raw.length || raw[index] === 0) {
      encodedPaths.push(raw.subarray(start, index));
      start = index + 1;
    }
  }
  const items: Record<string, unknown>[] = [];
  const errors: string[] = [];
  const recordIncomplete = (relative: string, reason: string, size?: number): void => {
    const item: Record<string, unknown> = { path: relative, complete: false, reason: reason };
    if (size !== undefined) {
      item.size = size;
    }
    items.push(item);
    errors.push(relative);
  };
  for (const encoded of encodedPaths) {
    if (encoded.length === 0) {
      continue;
    }
    const relative = encoded.toString("utf8");
    const candidate = `${root}/${relative}`;
    let meta: Stats;
    try {
      meta = lstatSync(candidate);
    } catch {
      recordIncomplete(relative, "unreadable");
      continue;
    }
    if (meta.isSymbolicLink()) {
      recordIncomplete(relative, "symlink");
      continue;
    }
    if (!meta.isFile()) {
      recordIncomplete(relative, "non_regular");
      continue;
    }
    if (meta.size > MAX_BYTES) {
      recordIncomplete(relative, "oversized", meta.size);
      continue;
    }
    let data: Buffer;
    try {
      data = readFileSync(candidate);
    } catch {
      recordIncomplete(relative, "unreadable");
      continue;
    }
    if (data.includes(0)) {
      recordIncomplete(relative, "binary", data.length);
      continue;
    }
    items.push({
      path: relative,
      size: data.length,
      sha256: contentDigest(data),
      complete: true,
    });
  }
  return { items: items, complete: errors.length === 0, errors: errors };
}

export function emptyScopeReason(bundle: Record<string, unknown>): string | null {
  if (bundle.retrieval_complete !== true) return null;
  const sections = bundle.sections as Record<string, Record<string, unknown>>;
  const untracked = sections.untracked as Record<string, unknown>;
  const uncommittedWorkEmpty =
    (sections.staged.diff as string).length === 0 &&
    (sections.unstaged.diff as string).length === 0 &&
    (untracked.items as Record<string, unknown>[]).length === 0;
  if (!uncommittedWorkEmpty) return null;
  if (bundle.ref === null || bundle.ref === undefined) return "no_uncommitted_changes";
  return (sections.committed.diff as string).length === 0 ? "no_changes_relative_to_ref" : null;
}

function shortRefCandidates(root: string, ref: string): string[] {
  const names = new Set([
    `refs/${ref}`,
    `refs/heads/${ref}`,
    `refs/tags/${ref}`,
    `refs/remotes/${ref}`,
  ]);
  return String(gitRead(root, ["for-each-ref", "--format=%(refname)"]))
    .split("\n")
    .filter((name) => names.has(name));
}

// Revision expressions such as `dup~0` resolve through the ambiguous short
// name without warning, so ambiguity is decided for the expression's base
// name, not only for a literal refname.
function comparisonBaseName(ref: string): string {
  return ref.split(/[~^:@]/, 1)[0];
}

function comparisonBase(root: string, ref: string): string {
  if (!ref.startsWith("refs/")) {
    const base = comparisonBaseName(ref);
    const candidates = base === "" || base === "HEAD" ? [] : shortRefCandidates(root, base);
    if (candidates.length > 1) {
      throw new WorkflowError(
        `comparison ref '${ref}' is ambiguous in the local checkout (${candidates.join(", ")}); ` +
          "ask which revision to use or pass one full refname; the runner does not fetch or choose for you",
      );
    }
  }
  try {
    gitRead(root, ["rev-parse", "--verify", "--quiet", `${ref}^{commit}`]);
  } catch {
    throw new WorkflowError(
      `comparison ref '${ref}' was not found or is not a commit in the local checkout; ` +
        "pass an existing local revision; the runner does not fetch or substitute one",
    );
  }
  try {
    return String(gitRead(root, ["merge-base", ref, "HEAD"])).trim();
  } catch {
    throw new WorkflowError(
      `no common merge base between '${ref}' and HEAD in the local checkout; ` +
        "ask how to proceed instead of falling back; the runner does not fetch",
    );
  }
}

export async function localBundle(
  repoRoot: string,
  profile: string,
  ref: string | null,
): Promise<Record<string, unknown>> {
  let rawStat: Stats | undefined;
  try {
    rawStat = lstatSync(repoRoot);
  } catch {
    rawStat = undefined;
  }
  if (rawStat?.isSymbolicLink()) {
    throw new WorkflowError("repo root must not be a symbolic link");
  }
  let root: string;
  try {
    root = realpathSync(repoRoot);
  } catch {
    root = resolve(repoRoot);
  }
  if (!existsSync(`${root}/.git`)) {
    throw new WorkflowError("repo root must be a real Git checkout");
  }
  let head: string;
  try {
    head = String(gitRead(root, ["rev-parse", "HEAD"])).trim();
  } catch {
    throw new WorkflowError(
      "the checkout has no readable HEAD; the repository needs at least one commit",
    );
  }
  const base = ref ? comparisonBase(root, ref) : head;
  const staged = localSection(root, "staged", [
    "diff",
    "--cached",
    "--binary",
    "--find-renames",
    "--",
  ]);
  const unstaged = localSection(root, "unstaged", ["diff", "--binary", "--find-renames", "--"]);
  const untracked = localUntracked(root);
  const committed = ref
    ? localSection(root, "committed", ["diff", "--binary", "--find-renames", base, head, "--"])
    : localSection(root, "committed", ["diff", "--binary", "--find-renames", "HEAD", "HEAD", "--"]);
  const identity = { hostname: "local", project_path: root, kind: "local", iid: 1 };
  const artifact = await stateDirectory(profile, identity);
  const sections: Record<string, Record<string, unknown>> = {
    committed: committed,
    staged: staged,
    unstaged: unstaged,
    untracked: untracked,
  };
  return {
    schema_version: ARTIFACT_VERSION,
    profile: profile,
    external_mutations: false,
    repo_root: root,
    base_sha: base,
    head_sha: head,
    ref: ref,
    sections: sections,
    artifact_root: artifact,
    retrieval_complete: Object.values(sections).every((section) => truthy(section.complete)),
  };
}

export async function finalizeLocal(bundleFile: string): Promise<Record<string, unknown>> {
  const [, baselinePayload] = artifactPayload(bundleFile, "local_wip_snapshot");
  const root = baselinePayload.repo_root;
  if (typeof root !== "string") {
    throw new WorkflowError("local evidence identity is incomplete");
  }
  const ref = pythonGet(baselinePayload, "ref");
  if (ref !== null && typeof ref !== "string") {
    throw new WorkflowError("local evidence ref is invalid");
  }
  const profile = Object.hasOwn(baselinePayload, "profile")
    ? baselinePayload.profile
    : "code-review";
  const current = await localBundle(root, String(profile), ref as string | null);
  const changed = (
    ["base_sha", "head_sha", "ref", "sections", "retrieval_complete"] as const
  ).filter((key) => digest(pythonGet(baselinePayload, key)) !== digest(pythonGet(current, key)));
  return {
    status: changed.length === 0 && truthy(current.retrieval_complete) ? "ok" : "stale",
    changed: changed,
    head_sha: current.head_sha,
    complete: current.retrieval_complete,
  };
}

// Records the agent-authored context package for a prepared local snapshot.
// Purely mechanical validation and binding; no network, fetch, or worktree.
export async function recordLocalPackage(
  bundlePath: string,
  inputPath: string,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  const root = String(bundle.artifact_root);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError("context package requires the canonical immutable local snapshot");
  }
  const input = readJson(regularFile(inputPath, "context package input"), "context package input");
  validatePackagePayload(input, {
    mode: "local",
    evidenceDigest: digestValue,
    artifactRoot: root,
    repoRoot: String(bundle.repo_root),
    headSha: String(bundle.head_sha),
    ref: pythonGet(bundle, "ref") as string | null,
    sections: localSectionDigests(bundle),
  });
  // Stamp the meaningful-context version onto every question before the
  // package becomes immutable; report answers carry the stamp they saw.
  bindQuestionContexts(input);
  supersedesDigest(root, input.supersedes);
  const previousPointer = readPackagePointer(root);
  const [path, packageDigest] = await writeContextPackage(root, input);
  // Bind the recorded package into the draft selected for this snapshot,
  // materializing it when needed; the agent never copies package paths or
  // digests by hand, in either order of record-package and record-input.
  const selection = selectLocalDraft(root, bundle, digestValue);
  const superseded = retireSupersededResults(selection.draft, previousPointer, input);
  selection.draft.context_package = { path: path, digest: packageDigest };
  const panelTasks = isObject(selection.draft.participants)
    ? localPanelCriticTasks(selection.draft, bundlePath)
    : null;
  persistLocalDraft(root, digestValue, selection, selection.draft);
  return {
    status: "ok",
    artifact_path: path,
    digest: packageDigest,
    canonical_digest: canonicalPackageDigest(input),
    background_digest: narrativePackageDigest(input),
    question_context_versions: questionContextVersionList(input),
    question_summary: questionReport((input.questions as Record<string, unknown>[]) ?? [], [], []),
    superseded_questions: superseded,
    critic_task: {
      launch: "now",
      mode: "local",
      context_package: {
        path: path,
        digest: packageDigest,
        question_context_versions: questionContextVersionList(input),
      },
      inputs: {
        repo_root: bundle.repo_root,
        bundle_path: bundlePath,
      },
      response_contract: {
        answers_field: "$.question_answers",
        import_command: runnerAction("record-input", [
          "--bundle",
          bundlePath,
          "--input",
          "<local-review-input.json>",
        ]),
        rules:
          "Every question_answer copies that question's context_digest listed above and carries the critic's real run/session identity. The primary imports answers (and any critic findings) with record-input without rewriting them.",
      },
      instructions:
        "Launch the independent local critic now, alongside primary inspection, and join before finalize-local. The critic reads the recorded package as its primary task context and the working tree exactly as committed/staged/unstaged in the snapshot.",
    },
    ...(panelTasks !== null
      ? {
          critic_tasks: panelTasks,
          arbitrator_task_hint:
            "After every selected critic receipt is imported, the record-critic response returns the ready local arbitrator task; import its receipt with record-arbitration",
        }
      : {}),
    external_mutations: false,
  };
}

// Mechanical assembly for the local review draft. Works on the prepared local
// report template exactly like record-input works on the MR draft: semantic
// sections only, machine bindings preserved, no verdict invented.
const LOCAL_SECTIONS = [
  "task",
  "task_change_reason",
  "findings",
  "checks",
  "assessment",
  "verdict",
  "question_answers",
  "question_verifications",
] as const;

function localGaps(report: Record<string, unknown>): Record<string, unknown> {
  const checks = (report.checks as Record<string, unknown>[] | undefined) ?? [];
  const required = checks.filter((check) => check.required === true);
  const binding = report.context_package as Record<string, unknown> | null;
  return {
    checks_required_total: required.length,
    checks_not_run: required.filter((check) => check.status === "not_run").length,
    checks_failed: required.filter((check) => check.status === "failed").length,
    assessment_empty:
      typeof report.assessment !== "string" || report.assessment === "" ? ["$.assessment"] : [],
    context_package:
      binding === null ? ["not recorded; run record-package --bundle before finalize-local"] : [],
    question_answers: ((report.question_answers as Record<string, unknown>[]) ?? []).length,
    question_verifications: ((report.question_verifications as Record<string, unknown>[]) ?? [])
      .length,
  };
}

// Stable canonical form for comparing stored and resent results: object key
// order must never decide whether a repeated result is a duplicate.
function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (isObject(value)) {
    return Object.fromEntries(
      Object.keys(value)
        .sort(compareCodePoints)
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

// Full identity of one collected result: the question, the meaningful-context
// version it was produced against, and the authoring run/session. Critic
// answers additionally keep the critic's own identity, while a primary
// verification is identified by the preserved original answer it verifies.
function resultIdentity(
  section: "question_answers" | "question_verifications",
  item: unknown,
): string | null {
  if (!isObject(item)) return null;
  const origin = section === "question_answers" ? item : item.original;
  if (!isObject(origin)) return null;
  const parts = [item.question_id, item.context_digest, origin.run_id, origin.session_id];
  if (parts.some((part) => typeof part !== "string" || part.length === 0)) return null;
  return parts.join("\u0000");
}

// Merges sequentially imported critic answers (and the primary's
// verifications) into the stored list instead of replacing it: a repeated
// identical result is not duplicated, a different result with the same critic
// identity and context version is rejected while the original is preserved,
// and the primary may revise its own verification in place. Every other entry
// survives regardless of order or disagreement.
function mergeResultEntries(
  current: Record<string, unknown>[],
  incoming: Record<string, unknown>[],
  section: "question_answers" | "question_verifications",
  issues: Array<{ path: string; message: string }>,
): Record<string, unknown>[] {
  const result = structuredClone(current);
  const positions = new Map<string, number>();
  for (const [index, item] of result.entries()) {
    const identity = resultIdentity(section, item);
    if (identity !== null && !positions.has(identity)) positions.set(identity, index);
  }
  for (const [index, item] of incoming.entries()) {
    const identity = resultIdentity(section, item);
    if (identity === null) continue; // the schema issues already name the entry
    const stored = positions.has(identity) ? result[positions.get(identity) as number] : undefined;
    if (stored === undefined) {
      positions.set(identity, result.length);
      result.push(item);
      continue;
    }
    if (digest(stableValue(stored)) === digest(stableValue(item))) continue;
    if (section === "question_verifications") {
      result[positions.get(identity) as number] = item;
      continue;
    }
    const question = String(item.question_id);
    issues.push({
      path: `$.question_answers[${index}]`,
      message:
        `An answer for question ${question} with this critic run/session identity and context ` +
        "version is already recorded with a different result; the original is preserved. Import " +
        "the other critic's result under its own identity, or record the primary resolution in " +
        "question_verifications preserving the original answer",
    });
  }
  return result;
}

export async function recordLocalInput(
  bundlePath: string,
  inputPath: string,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  const root = String(bundle.artifact_root);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError("record-input requires the canonical immutable local snapshot");
  }
  const draftPath = `${root}/local-review-draft.json`;
  const input = readJson(regularFile(inputPath, "local draft input"), "local draft input");
  rejectEnvelopeWrapper(input, "local draft input");
  const defs = artifactSchema().$defs as Record<string, Record<string, unknown>>;
  const properties = (defs.local_review_payload as Record<string, unknown>).properties as Record<
    string,
    Record<string, unknown>
  >;
  // Form is checked before any list is iterated or any field is read, so a
  // malformed section can only produce addressed diagnostics, never a crash.
  const issues: Array<{ path: string; message: string }> = [];
  const sections: Array<[string, unknown]> = [];
  const selection = selectLocalDraft(root, bundle, digestValue);
  // In panel mode the orchestrating session owns no review semantics: the
  // arbitrator's receipt carries findings, checks, assessment, verdict, and
  // answer resolutions; record-input still carries the task boundary.
  if (isObject(selection.draft.participants)) {
    for (const key of Object.keys(input))
      if (!["task", "task_change_reason"].includes(key))
        issues.push({
          path: `$.${key}`,
          message:
            "This local review runs as a panel: findings, checks, assessment, verdict, and answers belong to the arbitrator; import them with record-arbitration",
        });
  }
  for (const [key, value] of Object.entries(input)) {
    const field = `$.${key}`;
    const schema = properties[key];
    if (schema === undefined || !(LOCAL_SECTIONS as readonly string[]).includes(key)) {
      issues.push({
        path: field,
        message: `Unknown section; allowed sections are ${LOCAL_SECTIONS.join(", ")}`,
      });
      continue;
    }
    const sectionIssues = schemaIssues(schema, value, field);
    issues.push(...sectionIssues);
    // Shape must pass before any list is iterated or any entry field is read.
    if (sectionIssues.length === 0) sections.push([key, value]);
  }
  if (issues.length > 0) {
    return {
      status: "invalid",
      draft_path: draftPath,
      errors: issues,
      note: "Nothing was applied and the local draft is unchanged. Fix the named fields in the input file and run record-input again.",
      external_mutations: false,
    };
  }
  const next = structuredClone(selection.draft);
  const applied: Record<string, unknown> = {};
  for (const [key, value] of sections) {
    if (key === "findings")
      next.findings = upsertByIdentity(
        (next.findings as Record<string, unknown>[]) ?? [],
        value as Record<string, unknown>[],
        (item) => String(item.id),
      );
    else if (key === "checks")
      next.checks = upsertByIdentity(
        (next.checks as Record<string, unknown>[]) ?? [],
        value as Record<string, unknown>[],
        (item) => String(item.name),
      );
    else if (key === "question_answers" || key === "question_verifications")
      next[key] = mergeResultEntries(
        (next[key] as Record<string, unknown>[]) ?? [],
        value as Record<string, unknown>[],
        key,
        issues,
      );
    else next[key] = value;
    applied[key] = Array.isArray(value) ? value.length : value;
  }
  if (issues.length > 0) {
    return {
      status: "invalid",
      draft_path: draftPath,
      errors: issues,
      note: "Nothing was applied and the local draft is unchanged. Fix the named fields in the input file and run record-input again.",
      external_mutations: false,
    };
  }
  persistLocalDraft(root, digestValue, selection, next);
  return {
    status: "ok",
    draft_path: draftPath,
    applied,
    pending: localGaps(next),
    next_action: runnerAction("finalize-local", ["--bundle", bundlePath, "--report", draftPath]),
    external_mutations: false,
  };
}

// ---------- Local review panel ----------
//
// The local WIP flow runs the same panel process as the remote MR flow: one
// recorded selection, parallel independent local critics, and one arbitrator
// whose receipt carries the merged findings and the consolidated report
// fields. The finalized report artifact stays schema-identical; receipts and
// arbitration are preserved as companions under local-panel/.

const LOCAL_PANEL_DIR = "local-panel";
const localProperties = (
  (artifactSchema().$defs as Record<string, unknown>).local_review_payload as Record<
    string,
    unknown
  >
).properties as Record<string, Record<string, unknown>>;
const localFindingItems = (localProperties.findings as Record<string, unknown>).items as Record<
  string,
  unknown
>;
const localCheckItems = (localProperties.checks as Record<string, unknown>).items as Record<
  string,
  unknown
>;
const localCriticReceiptSchema: Record<string, unknown> = {
  type: "object",
  required: ["schema", "evidence_digest", "run_id", "session_id", "findings", "external_mutations"],
  additionalProperties: false,
  properties: {
    schema: { const: "code-review/local-critic-receipt/v1" },
    evidence_digest: { $ref: "#/$defs/digest" },
    run_id: { type: "string", minLength: 1 },
    session_id: { type: "string", minLength: 1 },
    findings: { type: "array", items: localFindingItems },
    question_answers: { type: "array", items: { $ref: "#/$defs/context_answer_ref" } },
    external_mutations: { const: false },
  },
};
const localArbitrationSchema: Record<string, unknown> = {
  type: "object",
  required: [
    "schema",
    "evidence_digest",
    "run_id",
    "session_id",
    "external_mutations",
    "findings",
    "dispositions",
    "checks",
    "assessment",
    "verdict",
  ],
  additionalProperties: false,
  properties: {
    schema: { const: "code-review/local-arbitration/v1" },
    evidence_digest: { $ref: "#/$defs/digest" },
    run_id: { type: "string", minLength: 1 },
    session_id: { type: "string", minLength: 1 },
    arbitrator: { type: "object" },
    external_mutations: { const: false },
    findings: { type: "array", items: localFindingItems },
    dispositions: {
      type: "array",
      items: {
        type: "object",
        required: ["id", "decision", "reason"],
        additionalProperties: false,
        properties: {
          id: { type: "string", minLength: 1 },
          decision: { enum: ["accept", "reject"] },
          reason: { type: "string", minLength: 1 },
          duplicate_of: { type: "string", minLength: 1 },
        },
      },
    },
    question_verifications: { type: "array", items: { $ref: "#/$defs/context_verification" } },
    checks: { type: "array", items: localCheckItems },
    assessment: { type: "string", minLength: 1 },
    verdict: { enum: ["ready", "not_ready", "blocked"] },
  },
};

function localPanelComplete(draft: Record<string, unknown>): boolean {
  if (!isObject(draft.participants)) return false;
  const critics = (draft.participants as Record<string, unknown>).critics as
    | Record<string, unknown>[]
    | undefined;
  if (!Array.isArray(critics)) return false;
  const receipts = (draft.critics as Record<string, unknown>[] | undefined) ?? [];
  return receipts.length === critics.length && critics.every((item) => isObject(item.receipt));
}

function localPanelCriticTasks(
  draft: Record<string, unknown>,
  bundlePath: string,
): Record<string, unknown>[] {
  const critics = ((draft.participants as Record<string, unknown>).critics ?? []) as Record<
    string,
    unknown
  >[];
  return critics.map((critic) => ({
    participant: String(critic.name),
    profile: critic.profile ?? null,
    provider: critic.provider ?? null,
    model: critic.model ?? null,
    receipt_schema: "code-review/local-critic-receipt/v1",
    template: {
      schema: "code-review/local-critic-receipt/v1",
      evidence_digest: draft.evidence_digest,
      run_id: "",
      session_id: "",
      findings: [],
      question_answers: [],
      external_mutations: false,
    },
    import_command: runnerAction("record-critic", [
      "--bundle",
      bundlePath,
      "--input",
      "<local-critic-response.json>",
      "--participant",
      String(critic.name),
    ]),
    rules:
      "One receipt per selected critic: a complete independent local review with findings in the local report shape and one question_answers entry per critic-assigned question, every answer copying that question's context_digest. Critics run in parallel, never see each other's output, and read the working tree exactly as committed, staged, and untracked in the recorded snapshot without recollecting anything.",
  }));
}

// Materializes the local arbitrator's input and returns its launch task once
// every selected critic receipt is imported and bound.
function syncLocalArbitrationInput(
  draft: Record<string, unknown>,
  root: string,
  bundlePath: string,
): Record<string, unknown> | null {
  if (!localPanelComplete(draft)) return null;
  const binding = draft.context_package as Record<string, unknown> | null;
  if (!isObject(binding)) return null;
  const [, packagePayload] = artifactPayload(String(binding.path), "context_package");
  const questions = (packagePayload.questions as Record<string, unknown>[]) ?? [];
  const { answers, contradictions } = collectAnswers(
    (draft.critics as Record<string, unknown>[]) ?? [],
  );
  const verifications = (draft.question_verifications as Record<string, unknown>[]) ?? [];
  const inputPath = `${root}/local-arbitration-input.json`;
  writeJson(inputPath, {
    schema: "code-review/local-arbitration-input/v1",
    evidence_digest: draft.evidence_digest,
    context_package: {
      path: binding.path,
      digest: binding.digest,
      question_context_versions: questionContextVersionList(packagePayload),
    },
    inputs: { bundle_path: bundlePath, repo_root: draft.repo_root ?? null },
    participants: structuredClone(draft.participants),
    previous_findings: structuredClone(draft.findings ?? []),
    task: structuredClone(draft.task ?? null),
    critic_receipts: structuredClone(draft.critics ?? []),
    question_report: questionReport(questions, answers, verifications),
    contradictions,
    response_contract: {
      receipt_schema: "code-review/local-arbitration/v1",
      import_command: runnerAction("record-arbitration", [
        "--bundle",
        bundlePath,
        "--input",
        "<local-arbitration-receipt.json>",
      ]),
      rules:
        "One receipt with a verdict for every critic finding and every merged finding, targeted evidence checks for contradictions, merged findings that retain prior stable IDs, and the consolidated checks, assessment, and verdict.",
    },
  });
  return {
    launch: "now_after_every_critic_receipt",
    input_path: inputPath,
    instructions:
      "Launch the selected local arbitrator subagent now. It receives the arbitration input, the recorded package, and the snapshot's working-tree state. It confirms or refutes every critic finding with a concrete reason, resolves contradictions with targeted checks, merges duplicates without losing authors, keeps prior finding IDs stable, and records the consolidated checks, assessment, and verdict. It never starts a new defect search from scratch and never modifies the working tree.",
  };
}

export async function recordLocalParticipants(
  bundlePath: string,
  inputPath: string,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  const root = String(bundle.artifact_root);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError(
      "participant selection requires the canonical immutable local snapshot",
    );
  }
  const input = readJson(regularFile(inputPath, "participant selection"), "participant selection");
  rejectEnvelopeWrapper(input, "participant selection");
  const selection = selectLocalDraft(root, bundle, digestValue);
  const draft = selection.draft;
  if (!["full", "incremental"].includes(String(draft.mode)))
    throw new WorkflowError(
      "record-participants applies to full and incremental local reviews; unchanged local evidence needs no panel",
    );
  if (((draft.critics as unknown[]) ?? []).length > 0)
    throw new WorkflowError(
      "Participants are fixed once critic receipts exist; prepare the snapshot again to select a new panel",
    );
  if (isObject(draft.arbitration))
    throw new WorkflowError(
      "An arbitration receipt is already recorded; prepare the snapshot again to select a new panel",
    );
  const errors = participantSelectionIssues(input);
  if (errors.length > 0)
    return {
      status: "invalid",
      draft_path: `${root}/local-review-draft.json`,
      errors,
      note: "The selection was not recorded and the local draft is unchanged.",
      external_mutations: false,
    };
  draft.participants = structuredClone(input);
  draft.critic_count = ((input.critics as unknown[]) ?? []).length;
  draft.critics = [];
  persistLocalDraft(root, digestValue, selection, draft);
  const packageRecorded = isObject(draft.context_package);
  return {
    status: "ok",
    draft_path: `${root}/local-review-draft.json`,
    participants: draft.participants,
    critic_count: draft.critic_count,
    ...(packageRecorded
      ? { critic_tasks: localPanelCriticTasks(draft, bundlePath) }
      : {
          critic_tasks_hint:
            "Record the context package next; its response returns one ready critic task per selected participant",
        }),
    arbitrator_task_hint:
      "After every critic receipt is imported, the record-critic response returns the ready local arbitrator task",
    external_mutations: false,
  };
}

export async function recordLocalCritic(
  bundlePath: string,
  inputPath: string,
  participant: string | null = null,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  const root = String(bundle.artifact_root);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError("record-critic requires the canonical immutable local snapshot");
  }
  const input = readJson(
    regularFile(inputPath, "local critic receipt input"),
    "local critic receipt input",
  );
  rejectEnvelopeWrapper(input, "local critic receipt input");
  const selection = selectLocalDraft(root, bundle, digestValue);
  const draft = selection.draft;
  if (!isObject(draft.participants))
    throw new WorkflowError(
      "record-critic requires a recorded panel; run record-participants first",
    );
  const critics = (draft.participants as Record<string, unknown>).critics as Record<
    string,
    unknown
  >[];
  const errors: DraftIssue[] = schemaIssues(localCriticReceiptSchema, input, "$", artifactSchema());
  if (errors.length === 0) {
    for (const field of ["run_id", "session_id"] as const)
      if (typeof input[field] !== "string" || (input[field] as string) === "")
        errors.push({
          path: `$.${field}`,
          message: `Expected the critic's real native ${field} identity; a fabricated identity is rejected`,
        });
    if (input.evidence_digest !== draft.evidence_digest)
      errors.push({
        path: "$.evidence_digest",
        message: `The receipt binds different evidence; this snapshot requires ${String(draft.evidence_digest)}. Do not rebind the receipt`,
      });
  }
  let selected: Record<string, unknown> | null = null;
  if (participant === null) {
    errors.push({
      path: "$.participant",
      message:
        "This local review runs as a panel; pass --participant with the selected critic name so the receipt is bound to its participant",
    });
  } else {
    selected = critics.find((item) => String(item.name) === participant) ?? null;
    if (selected === null) {
      errors.push({
        path: "$.participant",
        message: `Unknown participant ${participant}; the selected critics are ${critics
          .map((item) => String(item.name))
          .join(", ")}`,
      });
    } else if (isObject(selected.receipt)) {
      errors.push({
        path: "$.participant",
        message: `Participant ${participant} already has an imported receipt; each selected critic is imported exactly once`,
      });
    } else if (
      critics.some(
        (item) =>
          isObject(item.receipt) &&
          (String((item.receipt as Record<string, unknown>).run_id) === String(input.run_id) ||
            String((item.receipt as Record<string, unknown>).session_id) ===
              String(input.session_id)),
      )
    ) {
      errors.push({
        path: "$.participant",
        message: `This receipt identity is already bound to another selected critic; participant ${participant} needs its own subagent run`,
      });
    }
  }
  if (errors.length === 0 && isObject(draft.context_package)) {
    const [, packagePayload] = artifactPayload(
      String((draft.context_package as Record<string, unknown>).path),
      "context_package",
    );
    const versions = questionContextVersions(packagePayload);
    for (const [index, item] of (
      (input.question_answers as Record<string, unknown>[]) ?? []
    ).entries()) {
      if (!isObject(item)) continue;
      const id = String(item.question_id);
      if (!versions.has(id))
        errors.push({
          path: `$.question_answers[${index}].question_id`,
          message: `Unknown question ${id}; the recorded package contains questions ${[...versions.keys()].join(", ") || "none"}`,
        });
      else if (!isCurrentResult(item, versions))
        errors.push({
          path: `$.question_answers[${index}].context_digest`,
          message: `Stale answer: it binds context version ${String(item.context_digest)} but the current package version of question ${id} is ${versions.get(id)}`,
        });
    }
  }
  if (errors.length === 0) {
    const known = new Set([
      ...((draft.findings as Record<string, unknown>[]) ?? []).map((item) => String(item.id)),
      ...((draft.critics as Record<string, unknown>[]) ?? []).flatMap((receipt) =>
        ((receipt.findings as Record<string, unknown>[]) ?? []).map((item) => String(item.id)),
      ),
    ]);
    for (const [index, item] of ((input.findings as Record<string, unknown>[]) ?? []).entries())
      if (isObject(item) && known.has(String(item.id)))
        errors.push({
          path: `$.findings[${index}].id`,
          message: `Finding id ${String(item.id)} already exists in this review; use a distinct id`,
        });
  }
  if (errors.length > 0)
    return {
      status: "invalid",
      draft_path: `${root}/local-review-draft.json`,
      errors,
      note: "The receipt was not imported and the local draft is unchanged.",
      external_mutations: false,
    };
  if (selected !== null)
    selected.receipt = { run_id: String(input.run_id), session_id: String(input.session_id) };
  draft.critics = [...((draft.critics as unknown[]) ?? []), structuredClone(input)];
  persistLocalDraft(root, digestValue, selection, draft);
  const arbitratorTask =
    !isObject(draft.arbitration) && localPanelComplete(draft)
      ? syncLocalArbitrationInput(draft, root, bundlePath)
      : null;
  return {
    status: "ok",
    draft_path: `${root}/local-review-draft.json`,
    imported: {
      findings: ((input.findings as unknown[]) ?? []).length,
      answers: ((input.question_answers as unknown[]) ?? []).length,
    },
    critics_recorded: (draft.critics as unknown[]).length,
    ...(arbitratorTask !== null ? { arbitrator_task: arbitratorTask } : {}),
    next_action: runnerAction("record-arbitration", ["--bundle", bundlePath, "--input", "<file>"]),
    external_mutations: false,
  };
}

// The derived local verdict for a set of findings and checks; shared by the
// report validator and the arbitration import so the arbitrator's verdict can
// never disagree with the recorded evidence.
function expectedLocalVerdict(
  findings: Record<string, unknown>[],
  checks: Record<string, unknown>[],
): string {
  const required = checks.filter((check) => truthy(check.required));
  if (required.length === 0) return "blocked";
  if (required.some((check) => check.status === "not_run")) return "blocked";
  if (
    required.some((check) => check.status === "failed") ||
    findings.some((finding) => truthy(finding.blocking))
  )
    return "not_ready";
  return "ready";
}

export async function recordLocalArbitration(
  bundlePath: string,
  inputPath: string,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  const root = String(bundle.artifact_root);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError("record-arbitration requires the canonical immutable local snapshot");
  }
  const input = readJson(
    regularFile(inputPath, "local arbitration receipt input"),
    "local arbitration receipt input",
  );
  rejectEnvelopeWrapper(input, "local arbitration receipt input");
  const selection = selectLocalDraft(root, bundle, digestValue);
  const draft = selection.draft;
  if (!isObject(draft.participants))
    throw new WorkflowError(
      "record-arbitration requires a recorded panel; run record-participants first",
    );
  if (!localPanelComplete(draft))
    throw new WorkflowError(
      "Every selected critic receipt must be imported and bound before arbitration",
    );
  if (isObject(draft.arbitration))
    throw new WorkflowError(
      "An arbitration receipt is already recorded; prepare the snapshot again to change decisions",
    );
  const errors: DraftIssue[] = schemaIssues(localArbitrationSchema, input, "$", artifactSchema());
  if (errors.length === 0) {
    for (const field of ["run_id", "session_id"] as const)
      if (typeof input[field] !== "string" || (input[field] as string) === "")
        errors.push({
          path: `$.${field}`,
          message: `Expected the arbitrator's real native ${field} identity; a fabricated identity is rejected`,
        });
    if (input.evidence_digest !== draft.evidence_digest)
      errors.push({
        path: "$.evidence_digest",
        message: `The receipt binds different evidence; this snapshot requires ${String(draft.evidence_digest)}. Do not rebind the receipt`,
      });
    const identities = new Set(
      ((draft.critics as Record<string, unknown>[]) ?? []).flatMap((item) => [
        String(item.run_id),
        String(item.session_id),
      ]),
    );
    if (identities.has(String(input.run_id)) || identities.has(String(input.session_id)))
      errors.push({
        path: "$.session_id",
        message: "The arbitrator identity must differ from every critic",
      });
  }
  if (errors.length === 0) {
    // Coverage: one verdict per critic finding and per new arbitrator finding.
    // A merged finding may carry an accepted critic finding's id forward; the
    // report keeps stable IDs that way.
    const criticIds = new Set<string>();
    for (const receipt of (draft.critics as Record<string, unknown>[]) ?? [])
      for (const item of ((receipt.findings as Record<string, unknown>[]) ?? []) as Record<
        string,
        unknown
      >[]) {
        if (criticIds.has(String(item.id)))
          errors.push({
            path: "$.dispositions",
            message: `Finding id ${String(item.id)} appears in more than one critic receipt; use distinct ids`,
          });
        criticIds.add(String(item.id));
      }
    const dispositions = (input.dispositions as Record<string, unknown>[]) ?? [];
    const accepted = new Set(
      dispositions.filter((item) => item.decision === "accept").map((item) => String(item.id)),
    );
    const mergedIds: string[] = [];
    for (const item of (input.findings as Record<string, unknown>[]) ?? []) {
      const id = String(item.id);
      if (mergedIds.includes(id))
        errors.push({
          path: "$.findings",
          message: `Duplicate merged finding id ${id}; each report finding needs a distinct id`,
        });
      if (criticIds.has(id) && !accepted.has(id))
        errors.push({
          path: "$.findings",
          message: `Finding id ${id} is a rejected critic finding; a merged report finding cannot carry it forward`,
        });
      mergedIds.push(id);
    }
    const candidates = new Set([...criticIds, ...mergedIds.filter((id) => !criticIds.has(id))]);
    const verdictIds = dispositions.map((item) => String(item.id));
    const missing = [...candidates].filter((id) => !verdictIds.includes(id));
    const unknown = verdictIds.filter((id) => !candidates.has(id));
    if (new Set(verdictIds).size !== verdictIds.length)
      errors.push({
        path: "$.dispositions",
        message:
          "Each candidate finding receives exactly one verdict; duplicate disposition ids are rejected",
      });
    if (missing.length > 0)
      errors.push({
        path: "$.dispositions",
        message: `No verdict for finding ids ${missing.join(", ")}`,
      });
    if (unknown.length > 0)
      errors.push({
        path: "$.dispositions",
        message: `Dispositions name unknown finding ids ${unknown.join(", ")}`,
      });
    for (const [index, item] of dispositions.entries())
      if (
        item.duplicate_of !== undefined &&
        (item.decision !== "reject" ||
          !accepted.has(String(item.duplicate_of)) ||
          String(item.duplicate_of) === String(item.id))
      )
        errors.push({
          path: `$.dispositions[${index}].duplicate_of`,
          message: "duplicate_of must name an accepted canonical finding",
        });
    const derived = expectedLocalVerdict(
      (input.findings as Record<string, unknown>[]) ?? [],
      (input.checks as Record<string, unknown>[]) ?? [],
    );
    if (input.verdict !== derived)
      errors.push({
        path: "$.verdict",
        message: `The verdict must be ${derived} for the recorded findings and checks`,
      });
  }
  if (errors.length === 0 && isObject(draft.context_package)) {
    const [, packagePayload] = artifactPayload(
      String((draft.context_package as Record<string, unknown>).path),
      "context_package",
    );
    const versions = questionContextVersions(packagePayload);
    const questionIds = new Set(
      ((packagePayload.questions as Record<string, unknown>[]) ?? []).map((item) =>
        String(item.id),
      ),
    );
    const { answers, contradictions } = collectAnswers(
      (draft.critics as Record<string, unknown>[]) ?? [],
    );
    try {
      validateVerifications(
        (input.question_verifications as Record<string, unknown>[]) ?? [],
        questionIds,
        versions,
        answers,
      );
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
      errors.push({ path: "$.question_verifications", message: error.message });
    }
    const resolved = new Set(
      ((input.question_verifications as Record<string, unknown>[]) ?? []).map((item) =>
        String(item.question_id),
      ),
    );
    const unresolved = contradictions.filter((id) => !resolved.has(id));
    if (unresolved.length > 0)
      errors.push({
        path: "$.question_verifications",
        message: `Critics disagree on ${unresolved.join(", ")}; the arbitrator must resolve every contradiction with one targeted question_verifications entry each`,
      });
  }
  if (errors.length > 0)
    return {
      status: "invalid",
      draft_path: `${root}/local-review-draft.json`,
      errors,
      note: "The arbitration receipt was not imported and the local draft is unchanged.",
      external_mutations: false,
    };
  const next = structuredClone(draft);
  next.findings = structuredClone(input.findings);
  next.checks = structuredClone(input.checks);
  next.assessment = input.assessment;
  next.verdict = input.verdict;
  const mergeIssues: Array<{ path: string; message: string }> = [];
  next.question_verifications = mergeResultEntries(
    (next.question_verifications as Record<string, unknown>[]) ?? [],
    (input.question_verifications as Record<string, unknown>[]) ?? [],
    "question_verifications",
    mergeIssues,
  );
  next.arbitration = structuredClone(input);
  persistLocalDraft(root, digestValue, selection, next);
  return {
    status: "ok",
    draft_path: `${root}/local-review-draft.json`,
    imported: {
      merged_findings: ((input.findings as unknown[]) ?? []).length,
      verdicts: ((input.dispositions as unknown[]) ?? []).length,
    },
    next_action: runnerAction("finalize-local", [
      "--bundle",
      bundlePath,
      "--report",
      `${root}/local-review-draft.json`,
    ]),
    external_mutations: false,
  };
}

// Local counterpart of the draft package guard: re-recording a canonically
// changed package moves the report's answers and verifications collected for
// the previous questions into the report's historical section so that
// finalization cannot count them against the current questions. Exactly the
// entries selected by their own binding move; fresh results for the same
// question stay in place.
function retireSupersededResults(
  report: Record<string, unknown>,
  pointer: Record<string, unknown> | null,
  input: Record<string, unknown>,
): string[] {
  let previous: { payload: Record<string, unknown>; digest: string } | null = null;
  if (pointer !== null) {
    try {
      const [, payload] = artifactPayload(String(pointer.package_path), "context_package");
      previous = { payload: payload, digest: String(pointer.package_digest) };
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
    }
  }
  const answers = (report.question_answers as Record<string, unknown>[] | undefined) ?? [];
  const verifications =
    (report.question_verifications as Record<string, unknown>[] | undefined) ?? [];
  const superseded = extractSupersededResults(previous, input, answers, verifications);
  if (superseded === null) return [];
  const versions = questionContextVersions(input);
  const current = (item: Record<string, unknown>): boolean => isCurrentResult(item, versions);
  report.question_answers = answers.filter(current);
  report.question_verifications = verifications.filter(current);
  report.superseded_question_results = [
    ...((report.superseded_question_results as Record<string, unknown>[] | undefined) ?? []),
    superseded.entry,
  ];
  return superseded.questionIds;
}

function validateLocalPackage(
  report: Record<string, unknown>,
  root: string,
  bundle: Record<string, unknown>,
  digestValue: string,
): Record<string, unknown> {
  const binding = report.context_package;
  if (
    !isObject(binding) ||
    typeof binding.path !== "string" ||
    !isDigest(binding.digest as string)
  ) {
    throw new WorkflowError(
      "local review must bind the recorded context package; complete the returned template and run record-package",
    );
  }
  const pointer = readPackagePointer(root);
  if (
    pointer === null ||
    String(pointer.package_path) !== resolve(binding.path) ||
    String(pointer.package_digest) !== binding.digest
  ) {
    throw new WorkflowError(
      "local review package binding does not match the recorded context package; run record-package again",
    );
  }
  const [, packagePayload] = artifactPayload(String(binding.path), "context_package");
  validatePackagePayload(packagePayload, {
    mode: "local",
    evidenceDigest: digestValue,
    artifactRoot: root,
    repoRoot: String(bundle.repo_root),
    headSha: String(bundle.head_sha),
    ref: pythonGet(bundle, "ref") as string | null,
    sections: localSectionDigests(bundle),
  });
  const questions = (packagePayload.questions as Record<string, unknown>[]) ?? [];
  const questionIds = new Set(questions.map((item) => String(item.id)));
  const versions = questionContextVersions(packagePayload);
  const answers = (report.question_answers as Record<string, unknown>[] | undefined) ?? [];
  validateAnswers(answers, questionIds, versions, "$.question_answers");
  const verifications =
    (report.question_verifications as Record<string, unknown>[] | undefined) ?? [];
  validateVerifications(verifications, questionIds, versions, answers);
  const answered = new Set(answers.map((item) => String(item.question_id)));
  const covered = (id: string): boolean =>
    answered.has(id) || verifications.some((item) => String(item.question_id) === id);
  for (const entry of (report.superseded_question_results as
    | Record<string, unknown>[]
    | undefined) ?? []) {
    for (const answer of (entry.answers as Record<string, unknown>[] | undefined) ?? []) {
      const id = String(answer.question_id);
      if (questionIds.has(id) && !covered(id)) {
        throw new WorkflowError(
          `question ${id} was answered against a superseded context package ` +
            `(context digest ${String(entry.context_digest)}); the current package changed it, ` +
            `so it needs a fresh critic answer or primary verification`,
        );
      }
    }
  }
  for (const question of questions) {
    if (question.critic !== true) continue;
    const id = String(question.id);
    if (!covered(id)) {
      throw new WorkflowError(
        `question ${id} is assigned to critics but no critic answer or primary verification covers it`,
      );
    }
  }
  for (const answer of answers) {
    if (answer.verdict !== "not_verified") continue;
    const preserved = verifications.some(
      (item) =>
        String(item.question_id) === String(answer.question_id) &&
        isObject(item.original) &&
        String((item.original as Record<string, unknown>).run_id) === String(answer.run_id) &&
        String((item.original as Record<string, unknown>).session_id) === String(answer.session_id),
    );
    if (!preserved) {
      throw new WorkflowError(
        `critic answer for ${String(answer.question_id)} is not_verified; add one question_verifications entry that preserves the original answer`,
      );
    }
  }
  return questionReport(questions, answers, verifications);
}

export async function recordReview(
  root: string,
  bundlePath: string,
  reportPath: string,
): Promise<Record<string, unknown>> {
  const [, bundle] = artifactPayload(bundlePath, "local_wip_snapshot");
  const envelope = readJson(bundlePath, "local evidence");
  const digestValue = digest(envelope);
  if (realpathSync(bundlePath) !== `${root}/artifacts/local_wip_snapshot/${digestValue}.json`) {
    throw new WorkflowError("local review requires its canonical immutable snapshot");
  }
  const draft = readJson(reportPath, "local review draft");
  let report = draft;
  // A local panel review finalizes only after arbitration. The report
  // artifact stays schema-identical: receipt answers and the arbitrator's
  // verifications merge in as coverage evidence, while the receipts, the
  // selection, and the arbitration receipt itself are preserved verbatim as
  // companions under local-panel/.
  let panel = null;
  if (isObject(draft.participants)) {
    if (!localPanelComplete(draft))
      throw new WorkflowError(
        "Every selected local critic receipt must be imported and bound before finalization",
      );
    if (!isObject(draft.arbitration))
      throw new WorkflowError(
        "A local panel review requires the arbitration receipt; import it with record-arbitration before finalization",
      );
    panel = {
      participants: draft.participants,
      critics: draft.critics,
      arbitration: draft.arbitration,
    };
    const { participants, critics, arbitration, critic_count, ...payload } = draft;
    void participants;
    void critics;
    void arbitration;
    void critic_count;
    report = {
      ...payload,
      question_answers: collectAnswers(draft.critics as Record<string, unknown>[]).answers,
      question_verifications: structuredClone(
        (draft.arbitration as Record<string, unknown>).question_verifications ?? [],
      ),
    };
  }
  validateReport(report);
  if (report.evidence_digest !== digestValue) {
    throw new WorkflowError("local review does not bind the current snapshot");
  }
  const followup = prepareFollowup(
    root,
    bundle,
    digestValue,
    report.mode === "full" ? "off" : "auto",
  );
  if (report.previous_review_digest !== followup.previous_review_digest) {
    throw new WorkflowError("local review baseline changed; prepare again");
  }
  if (report.mode !== followup.mode) {
    throw new WorkflowError("local review mode does not match the available baseline");
  }
  if (followup.baseline_compatible === true) {
    validateContinuity(report, followup.previous_report as Record<string, unknown>);
  }
  const questionSummary = validateLocalPackage(report, root, bundle, digestValue);
  if ((await finalizeLocal(bundlePath)).status !== "ok") {
    throw new WorkflowError("local evidence changed before report finalization");
  }
  if (panel !== null) {
    const directory = await privateDirectory(`${root}/${LOCAL_PANEL_DIR}`);
    const suffix = digestValue.slice(0, 16);
    writeJson(`${directory}/participants-${suffix}.json`, panel.participants);
    writeJson(`${directory}/critics-${suffix}.json`, panel.critics);
    writeJson(`${directory}/arbitration-${suffix}.json`, panel.arbitration);
  }
  const [path, reportDigest] = await writeArtifact(root, "local_review_report", report);
  writeJson(`${root}/local-review.json`, { review_digest: reportDigest });
  return {
    artifact_path: path,
    digest: reportDigest,
    mode: report.mode,
    verdict: report.verdict,
    question_summary: questionSummary,
  };
}
