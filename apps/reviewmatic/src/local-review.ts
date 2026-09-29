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
  readJson,
  schemaValid,
  stateDirectory,
  writeArtifact,
  writeJson,
} from "./contract.js";
import { contentDigest } from "./state-artifacts.js";

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

export function prepareFollowup(
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
  const template = {
    evidence_digest: digestValue,
    previous_review_digest: previousDigest,
    mode: mode,
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
  return {
    mode: mode,
    reason: reason,
    baseline_compatible: reusable,
    previous_review_digest: previousDigest,
    previous_report: report,
    previous_evidence_digest: report ? report.evidence_digest : null,
    delta: delta,
    report_template: template,
    draft_path: `${root}/local-review-draft.json`,
  };
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
  if (!schemaValid(defs.local_review_payload as Record<string, unknown>, report, schema)) {
    throw new WorkflowError("local review report is schema-invalid");
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
  const required = checks.filter((check) => truthy(check.required));
  if (required.length === 0) {
    throw new WorkflowError("local review must include required acceptance checks");
  }
  let expected: string;
  if (required.some((check) => check.status === "not_run")) {
    expected = "blocked";
  } else if (
    required.some((check) => check.status === "failed") ||
    findings.some((finding) => truthy(finding.blocking))
  ) {
    expected = "not_ready";
  } else {
    expected = "ready";
  }
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
  const head = String(gitRead(root, ["rev-parse", "HEAD"])).trim();
  const base = ref ? String(gitRead(root, ["merge-base", ref, "HEAD"])).trim() : head;
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
  const report = readJson(reportPath, "local review draft");
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
  if ((await finalizeLocal(bundlePath)).status !== "ok") {
    throw new WorkflowError("local evidence changed before report finalization");
  }
  const [path, reportDigest] = await writeArtifact(root, "local_review_report", report);
  writeJson(`${root}/local-review.json`, { review_digest: reportDigest });
  return {
    artifact_path: path,
    digest: reportDigest,
    mode: report.mode,
    verdict: report.verdict,
  };
}
