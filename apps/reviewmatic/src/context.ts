import { spawnSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import {
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  writeSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, isAbsolute, resolve as pathResolve } from "node:path";
import {
  ARTIFACT_VERSION,
  MAX_BYTES,
  WorkflowError,
  artifactPayload,
  artifactRoot,
  codeReviewChatLabels,
  codeReviewPresentation,
  collect,
  detailedFindingsAreValid,
  digest,
  duplicateDetailedFindingIds,
  exactKeys,
  fingerprint,
  gitRead,
  glabJson,
  isDigest,
  markedPreview,
  mrMetadataAssessmentIsValid,
  nonemptyString,
  paginated,
  privateDirectory,
  readJson,
  redact,
  regularFile,
  reviewActionLabels,
  reviewMetadataLabels,
  reviewPublicationPreviewIsValid,
  selectExactPipeline,
  templateHeadings,
  threadDecisionsAreValid,
  validateCritic,
  validateFinalizeReport,
  writeArtifact,
  writeCompanion,
  writeJson,
} from "./contract.js";
import { labelCatalog, validateLabelAssessments } from "./label-assessment.js";
import { makeCommand, shellQuote } from "./publication.js";
import { suggestionBody, suggestionParts, suggestionsPatch } from "./fixes.js";
import {
  collect as semverCollect,
  reportLines as semverReportLines,
  template as semverTemplate,
  validate as semverValidate,
} from "./review-semver.js";
import { markdownBody, renderMutationCommand, versionedMarkdown } from "./state-artifacts.js";
import { VERSION } from "./version.js";

type Json = Record<string, unknown>;

export const INCREMENTAL_CONTRACT_VERSION = 1;
export const REVIEW_CONTRACT_VERSION = 7;
export const BASELINE_NAME = "review-baseline.json";
export const PROGRESS_NAME = "review-current.json";
export const REVIEW_EVIDENCE_NAME = "review-evidence.json";
export const REVIEW_STAGES = new Set([
  "prepared",
  "context_ready",
  "critic_missing",
  "finalize_missing",
  "decision_missing",
  "content_missing",
  "plan_ready",
  "stale",
]);
export const REVIEW_MODES = new Set(["fast", "normal", "deep", "incremental", "unchanged"]);
export const SUPPORTED_LOCALES = new Set(["en", "ru"]);

const SUGGESTION_RE = /^```suggestion(?::-(\d+)\+(\d+))?\r?\n([\s\S]*?)^```[ \t]*$/gm;
const SUGGESTION_OPENER_RE = /^```suggestion[^\r\n]*$/gm;
const IMMUTABLE_GITLAB_COMMIT_URL_RE = /^https:\/\/[^/]+\/.+\/-\/commits?\/[0-9a-f]{40}$/i;
const PREVIOUS_FINDING_STATUSES = new Set([
  "active",
  "fixed",
  "withdrawn",
  "changed",
  "unverified",
]);
const LOCK_ACQUIRE_ATTEMPTS = 20;
const LOCK_ACQUIRE_DELAY_MS = 50;

function isDict(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPlainInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function keySet(value: Json): Set<string> {
  return new Set(Object.keys(value));
}

function setsEqual(left: Set<unknown>, right: Set<unknown>): boolean {
  if (left.size !== right.size) return false;
  for (const item of left) if (!right.has(item)) return false;
  return true;
}

function isErrnoException(value: unknown): value is NodeJS.ErrnoException {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof (value as NodeJS.ErrnoException).code === "string"
  );
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

function sortedStrings(values: string[]): string[] {
  return [...values].sort(compareCodePoints);
}

function jsonEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return (
      left.length === right.length && left.every((item, index) => jsonEqual(item, right[index]))
    );
  }
  if (isDict(left) && isDict(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && jsonEqual(left[key], right[key]))
    );
  }
  return false;
}

function pyStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "string") return value;
  return String(value);
}

function pyRepr(value: unknown): string {
  if (typeof value === "string") return `'${value}'`;
  return pyStr(value);
}

const PY_STRING_ESCAPES: Record<string, string> = {
  '"': '\\"',
  "\\": "\\\\",
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
};

function pyQuote(value: string): string {
  let quoted = '"';
  for (const character of value) {
    const escape = PY_STRING_ESCAPES[character];
    if (escape !== undefined) {
      quoted += escape;
      continue;
    }
    const code = character.codePointAt(0) ?? 0;
    if (code < 0x20) {
      quoted += `\\u${code.toString(16).padStart(4, "0")}`;
      continue;
    }
    quoted += character;
  }
  return `${quoted}"`;
}

function pyJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return pyQuote(value);
  if (Array.isArray(value)) return `[${value.map((entry) => pyJson(entry)).join(", ")}]`;
  if (isDict(value)) {
    const keys = Object.keys(value).sort(compareCodePoints);
    return `{${keys.map((key) => `${pyQuote(key)}: ${pyJson(value[key])}`).join(", ")}}`;
  }
  throw new Error("unsupported JSON value for Python serialization");
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function sha256Bytes(value: Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function shlexQuote(token: string): string {
  if (token.length === 0) return "''";
  if (/[^\w@%+=:,./-]/.test(token)) return `'${token.replace(/'/g, "'\\''")}'`;
  return token;
}

function shlexJoin(tokens: string[]): string {
  return tokens.map(shlexQuote).join(" ");
}

function resolvePath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return pathResolve(path);
  }
}

function pathExists(path: string): boolean {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
}

function isSymlink(path: string): boolean {
  try {
    return lstatSync(path).isSymbolicLink();
  } catch {
    return false;
  }
}

function pathIsRelativeTo(path: string, root: string): boolean {
  if (path === root) return true;
  return path.startsWith(`${root}/`);
}

function pySplitLines(value: string): string[] {
  return value.split(/\r\n|\n|\r|\v|\f|\x1c|\x1d|\x1e|\x85|\u2028|\u2029/);
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolvePromise) => {
    setTimeout(resolvePromise, milliseconds);
  });
}

function posixRelative(value: string, prefix: string): string {
  if (!value.startsWith(prefix)) {
    throw new WorkflowError("Git patch has an invalid file header");
  }
  const rest = value.slice(prefix.length);
  const parts = rest.split("/").filter((part) => part !== "");
  if (rest.startsWith("/") || parts.length === 0 || parts.includes("..")) {
    throw new WorkflowError("Git patch path escapes the repository");
  }
  return parts.join("/");
}

export function runnerAction(
  command: string,
  args: readonly string[],
  requiredInputs: readonly string[] = [],
): Json {
  const argv = ["reviewmatic", command, ...args];
  return {
    command: shlexJoin(argv),
    argv: argv,
    required_inputs: [...requiredInputs],
  };
}

function patchRepository(context: Json): string {
  const exactGit = context.exact_git;
  if (!isDict(exactGit) || typeof exactGit.repo_root !== "string") {
    throw new WorkflowError("review checkout is unavailable for patch commands");
  }
  const root = exactGit.repo_root;
  if (!isAbsolute(root) || realpathSync(root) !== root) {
    throw new WorkflowError("review checkout path is unsafe");
  }
  return root;
}

function renderPatchCheck(context: Json, fix: Json): string {
  const patch = fix.patch as string;
  const patchDigest = sha256Text(patch);
  const delimiter = `PATCH_CHECK_${patchDigest.slice(0, 16).toUpperCase()}`;
  const command = shlexJoin(["git", "-C", patchRepository(context), "apply", "--check"]);
  return `${command} <<'${delimiter}'\n${patch.replace(/\s+$/, "")}\n${delimiter}`;
}

// Every block that creates a comment or discussion or changes thread state
// starts by verifying that the current MR head still matches the reviewed
// head. A failed request, a malformed response, or a moved head stops the
// block before anything is written; the check runs at manual execution time,
// never during runbook preparation. The reviewed head itself stays out of
// prose: the guard compares the SHA-256 digest of the head string.
function headGuard(evidence: Json, locale: string): string {
  const project = evidence.project as Json;
  const target = evidence.target as Json;
  const endpoint = `projects/${project.id}/merge_requests/${target.iid}`;
  const expected = sha256Text(String(evidence.head_sha));
  const ru = locale === "ru";
  const label = ru
    ? "Проверка head: блок останавливается до любой записи, если запрос не прошёл, ответ некорректен или head MR изменился после ревью"
    : "Head check: this block stops before writing anything when the request fails, the response is malformed, or the MR head moved after the review";
  const stop = ru
    ? "head MR отличается от рассмотренного; ничего не опубликовано. Обновите ревью и возьмите команды из нового плана"
    : "The MR head differs from the reviewed head; nothing was published. Refresh the review and use the new plan's commands";
  return [
    `# ${label}`,
    `current_head=$(glab api ${shellQuote(endpoint)} | jq -r ".sha") &&`,
    `[ "$(printf '%s' "$current_head" | sha256sum | cut -d' ' -f1)" = "${expected}" ] || { echo ${shellQuote(stop)} >&2; false; } &&`,
  ].join("\n");
}

// Operations whose shell blocks must be head-guarded: anything that creates a
// comment or discussion or changes thread state on the merge request.
function operationIsHeadGuarded(operation: string): boolean {
  return ["create_general", "create_line", "reply", "resolve", "reopen"].includes(operation);
}

export function renderPublicationPatchCommand(fix: Json): string {
  const patch = fix.patch as string;
  const patchDigest = sha256Text(patch);
  const delimiter = `PATCH_${patchDigest.slice(0, 16).toUpperCase()}`;
  return `git apply <<'${delimiter}'\n${patch.replace(/\s+$/, "")}\n${delimiter}`;
}

async function renderPatchCommand(evidence: Json, context: Json, fix: Json): Promise<string> {
  const patch = fix.patch as string;
  const patchDigest = sha256Text(patch);
  const delimiter = `PATCH_${patchDigest.slice(0, 16).toUpperCase()}`;
  const target = evidence.target as Json;
  const repoRoot = patchRepository(context);
  const command = await renderMutationCommand(["git", "-C", repoRoot, "apply"], {
    skill: "code-review",
    action: `patch:${patchDigest}`,
    binding: digest({
      target: target,
      head_sha: evidence.head_sha,
      patch_sha256: patchDigest,
      repo_root: repoRoot,
    }),
    stdinSha256: patchDigest,
    cwd: repoRoot,
    gitHead: evidence.head_sha as string,
  });
  return `${command} <<'${delimiter}'\n${patch.replace(/\s+$/, "")}\n${delimiter}`;
}

export function emptyProgress(
  evidencePath: string,
  evidenceDigest: string,
  options: {
    repoRoot?: string | null;
    mode?: string | null;
    locale?: string | null;
    incremental?: string;
  } = {},
): Json {
  return {
    schema: "code-review/progress/v1",
    stage: "prepared",
    evidence_path: evidencePath,
    evidence_digest: evidenceDigest,
    repo_root: options.repoRoot ?? null,
    context_path: null,
    context_digest: null,
    mode: options.mode ?? null,
    locale: options.locale ?? null,
    incremental: options.incremental ?? "auto",
    critic_receipt_path: null,
    critic_receipt_digest: null,
    finalize_report_path: null,
    finalize_report_digest: null,
    decision_path: null,
    decision_digest: null,
    plan_path: null,
    plan_digest: null,
    updated_at: new Date().toISOString(),
  };
}

export function validateProgress(value: unknown, root: string): Json {
  const required = keySet(emptyProgress(`${root}/placeholder`, "0".repeat(64)));
  if (!isDict(value) || !setsEqual(keySet(value), required)) {
    throw new WorkflowError("code-review progress has an invalid shape");
  }
  const repoRoot = value.repo_root ?? null;
  if (
    value.schema !== "code-review/progress/v1" ||
    !REVIEW_STAGES.has(value.stage as string) ||
    !isDigest(value.evidence_digest) ||
    ((value.mode ?? null) !== null && !REVIEW_MODES.has(value.mode as string)) ||
    ((value.locale ?? null) !== null && !SUPPORTED_LOCALES.has(value.locale as string)) ||
    !["auto", "off"].includes(value.incremental as string) ||
    (repoRoot !== null && (!nonemptyString(repoRoot) || !isAbsolute(repoRoot as string))) ||
    !nonemptyString(value.updated_at)
  ) {
    throw new WorkflowError("code-review progress is invalid");
  }
  for (const prefix of [
    "evidence",
    "context",
    "critic_receipt",
    "finalize_report",
    "decision",
    "plan",
  ]) {
    const pathValue = value[`${prefix}_path`] ?? null;
    const digestValue = value[`${prefix}_digest`] ?? null;
    if ((pathValue === null) !== (digestValue === null)) {
      throw new WorkflowError("code-review progress artifact binding is incomplete");
    }
    if (pathValue === null) continue;
    if (
      typeof pathValue !== "string" ||
      !isAbsolute(pathValue) ||
      !pathIsRelativeTo(pathValue, root) ||
      !isDigest(digestValue)
    ) {
      throw new WorkflowError("code-review progress artifact binding is unsafe");
    }
  }
  return value;
}

export function progressPath(root: string): string {
  return `${root}/${PROGRESS_NAME}`;
}

export function reviewEvidenceFromRoot(root: string): [string, Json] {
  const pointer = exactKeys(
    readJson(`${root}/${REVIEW_EVIDENCE_NAME}`, "current review evidence"),
    new Set(["evidence_path", "evidence_digest"]),
    "current review evidence",
  );
  const digestValue = pointer.evidence_digest;
  if (!isDigest(digestValue)) {
    throw new WorkflowError("current review evidence digest is invalid");
  }
  const source = regularFile(String(pointer.evidence_path), "review evidence");
  const expected = `${root}/artifacts/evidence_snapshot/${digestValue}.json`;
  if (source !== expected || sha256Bytes(readFileSync(source)) !== digestValue) {
    throw new WorkflowError("current review evidence binding changed");
  }
  const [, evidence] = artifactPayload(source, "evidence_snapshot");
  if (evidence.profile !== "code-review") {
    throw new WorkflowError("current review evidence has the wrong profile");
  }
  return [source, evidence];
}

export function loadProgress(root: string): Json | null {
  const path = progressPath(root);
  if (!pathExists(path) && !isSymlink(path)) return null;
  return validateProgress(readJson(path, "code-review progress"), root);
}

async function reviewStateLock(root: string): Promise<() => void> {
  const lockPath = `${root}/.review-state.lock`;
  if (isSymlink(lockPath)) {
    throw new WorkflowError("review state lock must not be a symbolic link");
  }
  let descriptor: number | null = null;
  for (let attempt = 0; attempt < LOCK_ACQUIRE_ATTEMPTS; attempt += 1) {
    try {
      descriptor = openSync(lockPath, "wx", 0o600);
      break;
    } catch (error) {
      if (isErrnoException(error) && error.code === "EEXIST") {
        if (attempt < LOCK_ACQUIRE_ATTEMPTS - 1) await sleep(LOCK_ACQUIRE_DELAY_MS);
        continue;
      }
      throw error;
    }
  }
  if (descriptor === null) {
    throw new WorkflowError("another review state update is running");
  }
  try {
    writeSync(descriptor, Buffer.from(`${process.pid}\n`, "utf8"));
  } finally {
    closeSync(descriptor);
  }
  return () => {
    try {
      rmSync(lockPath, { force: true });
    } catch {
      undefined;
    }
  };
}

function replacePrivateBytes(path: string, content: Buffer): void {
  const temporary = `${dirname(path)}/.${basename(path)}.${randomBytes(8).toString("hex")}.tmp`;
  try {
    const descriptor = openSync(temporary, "wx", 0o600);
    try {
      writeSync(descriptor, content);
      fsyncSync(descriptor);
    } finally {
      closeSync(descriptor);
    }
    renameSync(temporary, path);
  } finally {
    rmSync(temporary, { force: true });
  }
}

function fsyncDirectory(path: string): void {
  const descriptor = openSync(path, "r");
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

export async function beginReview(
  evidencePath: string,
  evidenceDigest: string,
  artifactRootValue: string,
  repoRoot: string | null = null,
  mode = "normal",
  locale = "en",
  incremental = "auto",
): Promise<Json> {
  const root = await artifactRoot(artifactRootValue);
  const source = regularFile(evidencePath, "review evidence");
  const expected = `${root}/artifacts/evidence_snapshot/${evidenceDigest}.json`;
  if (source !== expected || sha256Bytes(readFileSync(source)) !== evidenceDigest) {
    throw new WorkflowError("review evidence cannot initialize progress");
  }
  if (
    !["fast", "normal", "deep"].includes(mode) ||
    !SUPPORTED_LOCALES.has(locale) ||
    !["auto", "off"].includes(incremental)
  ) {
    throw new WorkflowError("review mode or locale cannot initialize progress");
  }
  const resolvedRepo = repoRoot !== null ? resolvePath(repoRoot) : null;
  const value = emptyProgress(source, evidenceDigest, {
    repoRoot: resolvedRepo,
    mode: mode,
    locale: locale,
    incremental: incremental,
  });
  const currentPath = `${root}/${REVIEW_EVIDENCE_NAME}`;
  const statePath = progressPath(root);
  const release = await reviewStateLock(root);
  try {
    if (isSymlink(currentPath) || isSymlink(statePath)) {
      throw new WorkflowError("review current-state paths must not be symbolic links");
    }
    const previousCurrent = pathExists(currentPath) ? readFileSync(currentPath) : null;
    const previousProgress = pathExists(statePath) ? readFileSync(statePath) : null;
    try {
      writeJson(statePath, value);
      writeJson(currentPath, {
        evidence_path: source,
        evidence_digest: evidenceDigest,
      });
    } catch (error) {
      if (!(error instanceof WorkflowError) && !isErrnoException(error)) throw error;
      for (const [path, previous] of [
        [statePath, previousProgress],
        [currentPath, previousCurrent],
      ] as [string, Buffer | null][]) {
        if (previous === null) {
          rmSync(path, { force: true });
        } else {
          replacePrivateBytes(path, previous);
        }
      }
      throw error;
    }
  } finally {
    release();
  }
  return value;
}

export async function advanceProgress(
  root: string,
  stage: string,
  kwargs: { expectedStages?: Set<string>; expected?: Json } & Json = {},
): Promise<Json> {
  if (!REVIEW_STAGES.has(stage)) {
    throw new WorkflowError("code-review progress stage is invalid");
  }
  const expectedStages = kwargs.expectedStages;
  const expected = kwargs.expected;
  const changes: Json = {};
  for (const [key, item] of Object.entries(kwargs)) {
    if (key !== "expectedStages" && key !== "expected") changes[key] = item;
  }
  const release = await reviewStateLock(root);
  try {
    const path = progressPath(root);
    let current: Json;
    if (pathExists(path) || isSymlink(path)) {
      current = validateProgress(readJson(path, "code-review progress"), root);
    } else {
      const [evidencePath] = reviewEvidenceFromRoot(root);
      const evidenceDigest = sha256Bytes(readFileSync(evidencePath));
      current = emptyProgress(evidencePath, evidenceDigest);
    }
    if (expectedStages !== undefined && !expectedStages.has(current.stage as string)) {
      throw new WorkflowError("code-review progress changed during transition");
    }
    if (
      expected !== undefined &&
      (!Object.keys(expected).every((key) => key in current) ||
        Object.entries(expected).some(([key, item]) => current[key] !== item))
    ) {
      throw new WorkflowError("code-review progress binding changed during transition");
    }
    const unknown = Object.keys(changes).filter((key) => !(key in current));
    if (unknown.length > 0) {
      throw new WorkflowError("code-review progress update has unknown fields");
    }
    const value: Json = {
      ...current,
      ...changes,
      stage: stage,
      updated_at: new Date().toISOString(),
    };
    validateProgress(value, root);
    writeJson(path, value);
    return value;
  } finally {
    release();
  }
}

function localizedPresentation(
  locale: string,
  role: string,
  verdict: string,
  incrementalMode: string,
): Json {
  return codeReviewPresentation(locale, role, verdict, incrementalMode);
}

function repositoryRoot(value: string): string {
  if (isSymlink(value)) {
    throw new WorkflowError("repository root must not be a symbolic link");
  }
  const root = resolvePath(value);
  if (!existsSync(`${root}/.git`)) {
    throw new WorkflowError("repository root must be a Git checkout");
  }
  const inside = String(gitRead(root, ["rev-parse", "--is-inside-work-tree"])).trim();
  if (inside !== "true") {
    throw new WorkflowError("repository root must be a Git checkout");
  }
  return root;
}

async function evidenceContext(evidenceValue: string): Promise<[string, Json, string, string]> {
  const source = regularFile(evidenceValue, "review evidence");
  const [, evidence] = artifactPayload(source, "evidence_snapshot");
  if (evidence.profile !== "code-review") {
    throw new WorkflowError("review context requires code-review evidence");
  }
  const root = await artifactRoot(String(evidence.artifact_root ?? ""));
  const evidenceDigest = sha256Bytes(readFileSync(source));
  const expected = `${root}/artifacts/evidence_snapshot/${evidenceDigest}.json`;
  if (source !== expected) {
    throw new WorkflowError("review evidence is not content-addressed");
  }
  return [source, evidence, root, evidenceDigest];
}

function stableId(value: unknown): [number, number | string] {
  if (typeof value === "boolean") {
    throw new WorkflowError("GitLab note or discussion has no stable ID");
  }
  if (isPlainInt(value)) return [0, value];
  if (typeof value === "string" && value.length > 0 && /^\p{Nd}+$/u.test(value)) {
    return [0, Number(value)];
  }
  if (typeof value === "string" && value.length > 0) return [1, value];
  throw new WorkflowError("GitLab note or discussion has no stable ID");
}

function compareStableIds(left: unknown, right: unknown): number {
  const [leftRank, leftValue] = stableId(left);
  const [rightRank, rightValue] = stableId(right);
  if (leftRank !== rightRank) return leftRank - rightRank;
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    return leftValue - rightValue;
  }
  return compareCodePoints(leftValue as string, rightValue as string);
}

function deduplicate(values: unknown[], label: string): Json[] {
  const unique = new Map<unknown, Json>();
  for (const value of values) {
    if (!isDict(value)) {
      throw new WorkflowError(`GitLab ${label} entry is not an object`);
    }
    const itemId = value.id;
    stableId(itemId);
    if (!unique.has(itemId)) unique.set(itemId, value);
  }
  return [...unique.values()].sort((left, right) => compareStableIds(left.id, right.id));
}

function username(value: unknown): string | null {
  if (!isDict(value)) return null;
  const result = value.username;
  return typeof result === "string" && result.length > 0 ? result : null;
}

function discussionSignature(value: Json): string {
  const notes: Json[] = [];
  for (const note of ((value.notes as unknown[]) ?? []) as unknown[]) {
    if (!isDict(note)) continue;
    notes.push({
      id: note.id,
      body: note.body,
      author: username(note.author),
      resolved: note.resolved,
      resolved_by: username(note.resolved_by),
      position: note.position,
    });
  }
  return pyJson({
    id: value.id,
    resolved: value.root_resolved,
    position: value.root_position,
    notes: notes,
  });
}

export async function baselinePointer(root: string): Promise<[Json, Json] | null> {
  const pointerPath = `${root}/${BASELINE_NAME}`;
  if (!pathExists(pointerPath)) return null;
  const pointer = readJson(pointerPath, "code-review baseline");
  if (
    !setsEqual(
      keySet(pointer),
      new Set([
        "contract_version",
        "target",
        "plan_path",
        "plan_digest",
        "markdown_path",
        "markdown_digest",
        "updated_at",
      ]),
    )
  ) {
    throw new WorkflowError("code-review baseline has an invalid shape");
  }
  if (pointer.contract_version !== INCREMENTAL_CONTRACT_VERSION) {
    throw new WorkflowError("code-review baseline contract is incompatible");
  }
  const planPath = String(pointer.plan_path ?? "");
  const planDigest = pointer.plan_digest;
  if (!isDigest(planDigest)) {
    throw new WorkflowError("code-review baseline digest is invalid");
  }
  const expected = `${root}/artifacts/review_plan/${planDigest}.json`;
  if (resolvePath(planPath) !== resolvePath(expected)) {
    throw new WorkflowError("code-review baseline plan path is invalid");
  }
  const [, plan] = artifactPayload(planPath, "review_plan");
  if (sha256Bytes(readFileSync(planPath)) !== planDigest) {
    throw new WorkflowError("code-review baseline plan digest changed");
  }
  if (
    plan.complete !== true ||
    ![1, 2, 3, 4, 5, 6, REVIEW_CONTRACT_VERSION].includes(plan.review_contract_version as number) ||
    !jsonEqual(plan.target, pointer.target)
  ) {
    throw new WorkflowError("code-review baseline is incomplete or incompatible");
  }
  const markdownPath = String(pointer.markdown_path ?? "");
  if (
    ![`${root}/review-publication.md`, `${root}/runbook.md`].includes(markdownPath) ||
    !isDigest(pointer.markdown_digest)
  ) {
    throw new WorkflowError("code-review baseline Markdown identity is invalid");
  }
  const source = regularFile(markdownPath, "code-review baseline Markdown");
  let markdown: string;
  try {
    markdown = (await markdownBody(source)).toString("utf8");
  } catch (error) {
    if (!isErrnoException(error)) throw error;
    throw new WorkflowError("code-review baseline Markdown is unreadable");
  }
  if (sha256Text(markdown) !== pointer.markdown_digest) {
    throw new WorkflowError("code-review baseline Markdown digest changed");
  }
  if (plan.markdown !== markdown) {
    throw new WorkflowError("code-review baseline Markdown body changed");
  }
  return [pointer, plan];
}

function artifactForDigest(root: string, kind: string, digestValue: unknown): [string, Json] {
  if (!isDigest(digestValue)) {
    throw new WorkflowError(`baseline ${kind} digest is invalid`);
  }
  const path = `${root}/artifacts/${kind}/${digestValue}.json`;
  const source = regularFile(path, `baseline ${kind}`);
  if (source !== resolvePath(path) || sha256Bytes(readFileSync(source)) !== digestValue) {
    throw new WorkflowError(`baseline ${kind} content address changed`);
  }
  const [, payload] = artifactPayload(source, kind);
  return [source, payload];
}

function rejectedCandidateIsAffected(candidate: Json, delta: Json): boolean {
  const paths = (candidate.paths as string[]) ?? [];
  const threadIds = (candidate.thread_ids as string[]) ?? [];
  const metadataFields = (candidate.metadata_fields as string[]) ?? [];
  const deltaPaths = (delta.changed_paths as string[]) ?? [];
  const deltaThreads = (delta.changed_thread_ids as string[]) ?? [];
  const deltaNotes = (delta.changed_note_ids as string[]) ?? [];
  const deltaMetadata = (delta.metadata_fields as string[]) ?? [];
  return Boolean(
    paths.some((item) => deltaPaths.includes(item)) ||
    threadIds.some((item) => deltaThreads.includes(item) || deltaNotes.includes(item)) ||
    metadataFields.some((item) => deltaMetadata.includes(item)) ||
    (candidate.ci === true && delta.pipelines_changed === true),
  );
}

async function incrementalContext(
  evidence: Json,
  context: Json,
  root: string,
  requested: string,
): Promise<Json> {
  const baselineStatePath = `${root}/${BASELINE_NAME}`;
  let baselineStateDigest: string | null = null;
  let baselineStateError: string | null = null;
  if (pathExists(baselineStatePath) || isSymlink(baselineStatePath)) {
    try {
      baselineStateDigest = sha256Bytes(
        readFileSync(regularFile(baselineStatePath, "code-review baseline state")),
      );
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
      baselineStateError = error.message;
    }
  }
  const emptyDelta: Json = {
    from_head: null,
    to_head: evidence.head_sha ?? null,
    changed_paths: [],
    changed_thread_ids: [],
    unchanged_thread_ids: [],
    changed_note_ids: [],
    unchanged_note_ids: [],
    metadata_fields: [],
    pipelines_changed: false,
  };
  const empty: Json = {
    contract_version: INCREMENTAL_CONTRACT_VERSION,
    requested: requested,
    mode: "full",
    reason:
      requested === "off"
        ? "incremental review was explicitly disabled"
        : baselineStateError !== null
          ? "incremental review requires a full-review fallback"
          : "no compatible finalized baseline exists",
    incremental_baseline: {
      plan_path: null,
      plan_digest: null,
      state_digest: baselineStateDigest,
    },
    previous_findings: [],
    previous_finding_publications: [],
    previous_recommended_issues: [],
    previous_finding_ledger: [],
    previous_publication_ledger: [],
    previous_thread_decisions: [],
    previous_rejected_candidates: [],
    reconsidered_rejected_candidates: [],
    incremental_delta: emptyDelta,
    incremental_delta_digest: digest(emptyDelta),
    critic_required: false,
    fallback_reasons: baselineStateError !== null ? [baselineStateError] : [],
  };
  if (requested === "off" || baselineStateError !== null) return empty;
  try {
    const baseline = await baselinePointer(root);
    if (baseline === null) return empty;
    const [pointer, plan] = baseline;
    const [, oldEvidence] = artifactForDigest(root, "evidence_snapshot", plan.evidence_digest);
    const [, oldContext] = artifactForDigest(root, "review_context", plan.context_digest);
    const failures: string[] = [];
    if (plan.review_contract_version !== REVIEW_CONTRACT_VERSION) {
      failures.push("baseline review contract predates release-aware SemVer");
    }
    if (!jsonEqual(oldContext.release_evidence, context.release_evidence)) {
      failures.push("release evidence or target branch changed");
    }
    if (
      oldContext.evidence_digest !== plan.evidence_digest ||
      !jsonEqual(oldContext.target, plan.target) ||
      !jsonEqual(oldEvidence.target, plan.target) ||
      !jsonEqual(plan.target, pointer.target)
    ) {
      failures.push("baseline artifact bindings changed");
    }
    if (!jsonEqual(pointer.target, evidence.target)) {
      failures.push("target identity changed");
    }
    if (oldContext.current_user_username !== context.current_user_username) {
      failures.push("current GitLab user changed");
    }
    if (oldContext.role !== context.role) {
      failures.push("review role changed");
    }
    if (oldEvidence.retrieval_complete !== true || oldContext.complete !== true) {
      failures.push("baseline evidence is incomplete");
    }
    const currentExactGit = context.exact_git;
    if (
      evidence.retrieval_complete !== true ||
      context.complete !== true ||
      !isDict(currentExactGit) ||
      currentExactGit.complete !== true
    ) {
      failures.push("current evidence is incomplete");
    }
    for (const key of ["base_sha", "start_sha"]) {
      if (!jsonEqual(oldEvidence[key] ?? null, evidence[key] ?? null)) {
        failures.push(`${key} changed`);
      }
    }
    const oldHead = oldEvidence.head_sha ?? null;
    const currentHead = evidence.head_sha ?? null;
    const repoRoot = String((context.exact_git as Json).repo_root);
    if (typeof oldHead !== "string" || typeof currentHead !== "string") {
      failures.push("head SHA is unavailable");
    } else if (oldHead !== currentHead) {
      let mergeBase: string | undefined;
      try {
        mergeBase = String(gitRead(repoRoot, ["merge-base", oldHead, currentHead])).trim();
      } catch (error) {
        if (!(error instanceof WorkflowError)) throw error;
        failures.push("head ancestry cannot be verified");
      }
      if (mergeBase !== undefined && mergeBase.toLowerCase() !== oldHead.toLowerCase()) {
        failures.push("current head is not a descendant of the baseline head");
      }
    }
    if (failures.length > 0) {
      return {
        ...empty,
        reason: "incremental review requires a full-review fallback",
        fallback_reasons: failures,
      };
    }
    let changedPaths: string[] = [];
    if (oldHead !== currentHead) {
      const rawPaths = gitRead(
        repoRoot,
        [
          "diff",
          "--name-only",
          "--find-renames",
          "-z",
          oldHead as string,
          currentHead as string,
          "--",
        ],
        false,
      ) as Buffer;
      if (!Buffer.isBuffer(rawPaths)) {
        throw new WorkflowError("incremental changed paths are invalid");
      }
      changedPaths = sortedStrings(
        rawPaths
          .toString("utf8")
          .split("\0")
          .filter((item) => item.length > 0),
      );
    }
    const oldThreads = new Map<string, Json>();
    for (const item of (oldContext.discussions as Json[]) ?? []) {
      oldThreads.set(String(item.id), item);
    }
    const currentThreads = new Map<string, Json>();
    for (const item of (context.discussions as Json[]) ?? []) {
      currentThreads.set(String(item.id), item);
    }
    const removed = sortedStrings(
      [...oldThreads.keys()].filter((threadId) => !currentThreads.has(threadId)),
    );
    if (removed.length > 0) {
      return {
        ...empty,
        reason: "incremental review requires a full-review fallback",
        fallback_reasons: ["one or more baseline discussions disappeared"],
      };
    }
    const changedThreads = sortedStrings(
      [...currentThreads.entries()]
        .filter(
          ([threadId, thread]) =>
            !oldThreads.has(threadId) ||
            discussionSignature(oldThreads.get(threadId) as Json) !== discussionSignature(thread),
        )
        .map(([threadId]) => threadId),
    );
    const unchangedThreads = sortedStrings(
      [...oldThreads.keys()].filter(
        (threadId) => currentThreads.has(threadId) && !changedThreads.includes(threadId),
      ),
    );
    const oldNotes = new Map<string, Json>();
    for (const item of (oldContext.notes as Json[]) ?? []) {
      if (item.system !== true) oldNotes.set(String(item.id), item);
    }
    const currentNotes = new Map<string, Json>();
    for (const item of (context.notes as Json[]) ?? []) {
      if (item.system !== true) currentNotes.set(String(item.id), item);
    }
    if ([...oldNotes.keys()].some((noteId) => !currentNotes.has(noteId))) {
      return {
        ...empty,
        reason: "incremental review requires a full-review fallback",
        fallback_reasons: ["one or more baseline notes disappeared"],
      };
    }
    const changedNotes = sortedStrings(
      [...currentNotes.entries()]
        .filter(
          ([noteId, note]) =>
            !oldNotes.has(noteId) || pyJson(oldNotes.get(noteId)) !== pyJson(note),
        )
        .map(([noteId]) => noteId),
    );
    const unchangedNotes = sortedStrings(
      [...oldNotes.keys()].filter(
        (noteId) => currentNotes.has(noteId) && !changedNotes.includes(noteId),
      ),
    );
    const oldObject = (oldEvidence.object as Json) ?? {};
    const currentObject = (evidence.object as Json) ?? {};
    const ignoredMetadata = new Set([
      "created_at",
      "updated_at",
      "diff_refs",
      "sha",
      "merge_commit_sha",
      "squash_commit_sha",
      "_links",
    ]);
    const metadataKeys = sortedStrings(
      [...new Set([...Object.keys(oldObject), ...Object.keys(currentObject)])].filter(
        (key) => !ignoredMetadata.has(key),
      ),
    );
    const metadataFields = metadataKeys.filter(
      (key) => !jsonEqual(oldObject[key] ?? null, currentObject[key] ?? null),
    );
    if (!jsonEqual(oldEvidence.labels, evidence.labels)) {
      metadataFields.push("label_catalog");
      metadataFields.sort(compareCodePoints);
    }
    const pipelinesChanged = !jsonEqual(oldEvidence.pipelines, evidence.pipelines);
    const changed = Boolean(
      changedPaths.length > 0 ||
      changedThreads.length > 0 ||
      changedNotes.length > 0 ||
      metadataFields.length > 0 ||
      pipelinesChanged,
    );
    const delta: Json = {
      from_head: oldHead,
      to_head: currentHead,
      changed_paths: changedPaths,
      changed_thread_ids: changedThreads,
      unchanged_thread_ids: unchangedThreads,
      changed_note_ids: changedNotes,
      unchanged_note_ids: unchangedNotes,
      metadata_fields: metadataFields,
      pipelines_changed: pipelinesChanged,
    };
    const findingLedger = (plan.finding_ledger as Json[]) ?? [];
    const previousFindings = findingLedger
      .filter((item) => item.kind === "finding")
      .map((item) => (item.record as Json).finding as Json);
    const previousFindingPublications = findingLedger
      .filter((item) => item.kind === "finding")
      .map((item) => (item.record as Json).publication as Json);
    const previousRecommendedIssues = findingLedger
      .filter((item) => item.kind === "issue")
      .map((item) => (item.record as Json).issue as Json);
    const rejectedCandidates = (plan.rejected_candidate_ledger as Json[]) ?? [];
    return {
      ...empty,
      mode: changed ? "incremental" : "unchanged",
      reason: changed
        ? "compatible finalized baseline and changed MR evidence"
        : "the MR has not changed since the finalized baseline",
      incremental_baseline: {
        plan_path: pointer.plan_path,
        plan_digest: pointer.plan_digest,
        state_digest: baselineStateDigest,
      },
      previous_findings: previousFindings,
      previous_finding_publications: previousFindingPublications,
      previous_recommended_issues: previousRecommendedIssues,
      previous_finding_ledger: findingLedger,
      previous_publication_ledger: [],
      previous_thread_decisions: plan.thread_decisions ?? [],
      previous_rejected_candidates: rejectedCandidates,
      reconsidered_rejected_candidates: rejectedCandidates.filter((item) =>
        rejectedCandidateIsAffected(item, delta),
      ),
      incremental_delta: delta,
      incremental_delta_digest: digest(delta),
      critic_required: changed,
    };
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    return {
      ...empty,
      reason: "incremental review requires a full-review fallback",
      fallback_reasons: [error.message],
    };
  }
}

function annotateDiscussion(value: Json, webUrl: string): Json {
  const notes = value.notes;
  if (!Array.isArray(notes) || notes.length === 0 || !isDict(notes[0])) {
    throw new WorkflowError(`discussion ${pyRepr(value.id)} has no root note`);
  }
  const root = notes[0] as Json;
  const noteId = root.id;
  stableId(noteId);
  const position = isDict(root.position) ? root.position : null;
  return {
    ...value,
    root_note_id: noteId,
    root_note_url: `${webUrl}#note_${pyStr(noteId)}`,
    root_author_username: username(root.author),
    root_resolved_by_username: username(root.resolved_by),
    root_resolvable: root.resolvable === true,
    root_resolved: root.resolved === true,
    root_system: root.system === true,
    root_position: position,
    root_position_head_sha: position !== null ? (position.head_sha ?? null) : null,
  };
}

function serverChangedPaths(evidence: Json): Set<string> {
  const changed = evidence.changed_files;
  if (!isDict(changed) || changed.complete !== true) {
    throw new WorkflowError("GitLab changed-files evidence is incomplete");
  }
  const paths = new Set<string>();
  for (const value of (changed.items as unknown[]) ?? []) {
    if (!isDict(value)) {
      throw new WorkflowError("GitLab changed-files entry is invalid");
    }
    const path = value.new_path || value.old_path;
    if (typeof path !== "string" || path.length === 0) {
      throw new WorkflowError("GitLab changed-files entry has no path");
    }
    paths.add(path);
  }
  return paths;
}

function exactGitContext(repoRoot: string, evidence: Json): Json {
  const root = repositoryRoot(repoRoot);
  const errors: string[] = [];
  const refs: Json = {};
  for (const name of ["base_sha", "start_sha", "head_sha"]) {
    const value = evidence[name];
    if (typeof value !== "string" || value.length === 0) {
      errors.push(`${name} is unavailable`);
      continue;
    }
    let resolved: string;
    try {
      resolved = String(gitRead(root, ["rev-parse", "--verify", `${value}^{commit}`])).trim();
    } catch (error) {
      if (!(error instanceof WorkflowError)) throw error;
      errors.push(`${name} is unavailable in the local repository`);
      continue;
    }
    if (resolved.toLowerCase() !== value.toLowerCase()) {
      errors.push(`${name} does not resolve exactly`);
      continue;
    }
    refs[name] = resolved;
  }
  if (!setsEqual(keySet(refs), new Set(["base_sha", "start_sha", "head_sha"]))) {
    return {
      repo_root: root,
      refs: refs,
      changed_paths: [],
      diff_sha256: null,
      complete: false,
      errors: errors,
    };
  }
  const mergeBase = String(
    gitRead(root, ["merge-base", refs.start_sha as string, refs.head_sha as string]),
  ).trim();
  if (mergeBase.toLowerCase() !== (refs.base_sha as string).toLowerCase()) {
    errors.push("local merge-base does not match evidence base_sha");
  }
  const rawPaths = gitRead(
    root,
    [
      "diff",
      "--name-only",
      "--find-renames",
      "-z",
      refs.base_sha as string,
      refs.head_sha as string,
      "--",
    ],
    false,
  ) as Buffer;
  if (!Buffer.isBuffer(rawPaths)) {
    throw new WorkflowError("local changed paths are invalid");
  }
  const changedPaths = sortedStrings(
    rawPaths
      .toString("utf8")
      .split("\0")
      .filter((item) => item.length > 0),
  );
  try {
    const expectedPaths = serverChangedPaths(evidence);
    if (!setsEqual(new Set(changedPaths), expectedPaths)) {
      errors.push("local changed paths do not match GitLab evidence");
    }
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    errors.push(error.message);
  }
  const diff = gitRead(
    root,
    ["diff", "--binary", "--find-renames", refs.base_sha as string, refs.head_sha as string, "--"],
    false,
  ) as Buffer;
  if (!Buffer.isBuffer(diff)) {
    throw new WorkflowError("local exact diff is invalid");
  }
  let diffDigest: string | null;
  if (diff.length > MAX_BYTES) {
    errors.push("local exact diff exceeds the size limit");
    diffDigest = null;
  } else {
    diffDigest = sha256Bytes(diff);
  }
  return {
    repo_root: root,
    refs: refs,
    changed_paths: changedPaths,
    diff_sha256: diffDigest,
    complete: errors.length === 0,
    errors: errors,
  };
}

function projectIssueTemplates(exactGit: Json): Json[] {
  if (exactGit.complete !== true) {
    throw new WorkflowError("exact Git context is unavailable for issue templates");
  }
  const refs = exactGit.refs as Json;
  const root = exactGit.repo_root as string;
  const headSha = refs.head_sha as string;
  const rawPaths = gitRead(
    root,
    ["ls-tree", "-r", "--name-only", "-z", headSha, "--", ".gitlab/issue_templates"],
    false,
  ) as Buffer;
  if (!Buffer.isBuffer(rawPaths)) {
    throw new WorkflowError("project issue template paths are invalid");
  }
  const paths = rawPaths
    .toString("utf8")
    .split("\0")
    .filter((item) => item.length > 0);
  const templates: Json[] = [];
  for (const path of paths) {
    const name = path.startsWith(".gitlab/issue_templates/")
      ? path.slice(".gitlab/issue_templates/".length)
      : path;
    if (name === path || name.length === 0 || name.includes("/") || !name.endsWith(".md")) {
      throw new WorkflowError("project issue template path is invalid");
    }
    const body = String(gitRead(root, ["show", `${headSha}:${path}`]));
    if (!nonemptyString(body) || Buffer.byteLength(body, "utf8") > MAX_BYTES) {
      throw new WorkflowError("project issue template content is invalid");
    }
    templates.push({
      path: path,
      body: body,
      headings: templateHeadings(body),
    });
  }
  return templates;
}

async function collectContext(
  evidence: Json,
  evidenceDigest: string,
  repoRoot: string,
  incremental = "auto",
): Promise<Json> {
  if (!["auto", "off"].includes(incremental)) {
    throw new WorkflowError("incremental selection must be auto or off");
  }
  const project = evidence.project;
  const target = evidence.target;
  const objectValue = evidence.object;
  const discussionsComponent = evidence.discussions;
  if (
    !isDict(project) ||
    !isPlainInt(project.id) ||
    typeof project.hostname !== "string" ||
    !isDict(target) ||
    !isDict(objectValue) ||
    !isDict(discussionsComponent)
  ) {
    throw new WorkflowError("review evidence identity is incomplete");
  }
  const authorUsername = username(objectValue.author);
  const webUrl = objectValue.web_url || target.url;
  if (authorUsername === null || typeof webUrl !== "string" || webUrl.length === 0) {
    throw new WorkflowError("MR author or web URL is unavailable");
  }
  const currentUser = glabJson(project.hostname as string, "user");
  const currentUsername = username(currentUser);
  const currentUserId = isDict(currentUser) ? currentUser.id : null;
  if (currentUsername === null || !isPlainInt(currentUserId) || currentUserId < 1) {
    throw new WorkflowError("current GitLab identity is unavailable");
  }
  const role = currentUsername === authorUsername ? "author" : "reviewer";
  const notesComponent = paginated(
    project.hostname as string,
    `projects/${project.id}/merge_requests/${target.iid}/notes?sort=asc`,
  );
  const errors: string[] = (notesComponent.errors as string[]).map((value) => redact(value));
  if (discussionsComponent.complete !== true) {
    errors.push(...((discussionsComponent.errors as string[]) ?? []).map((value) => redact(value)));
  }
  let discussions: Json[] = [];
  let notes: Json[] = [];
  try {
    discussions = (
      deduplicate((discussionsComponent.items as unknown[]) ?? [], "discussion") as Json[]
    ).map((value) => annotateDiscussion(value, webUrl as string));
    const nestedNotes = discussions.flatMap(
      (discussion) => ((discussion.notes as unknown[]) ?? []) as unknown[],
    );
    notes = deduplicate([...nestedNotes, ...((notesComponent.items as unknown[]) ?? [])], "note");
    notes = notes.map((note) => ({ ...note, note_url: `${webUrl}#note_${pyStr(note.id)}` }));
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    errors.push(error.message);
    discussions = [];
    notes = [];
  }
  const exactGit = exactGitContext(repoRoot, evidence);
  errors.push(...(exactGit.errors as string[]));
  let issueTemplates: Json[] = [];
  try {
    issueTemplates = projectIssueTemplates(exactGit);
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    errors.push(error.message);
    issueTemplates = [];
  }
  const contentNotes = notes.filter((note) => note.system !== true);
  const systemNotes = notes.filter((note) => note.system === true);
  const counts: Json = {
    discussions: discussions.length,
    notes: notes.length,
    content_notes: contentNotes.length,
    system_notes: systemNotes.length,
    open_resolvable: discussions.filter(
      (item) =>
        item.root_resolvable === true && item.root_resolved === false && item.root_system === false,
    ).length,
    resolved_resolvable: discussions.filter(
      (item) =>
        item.root_resolvable === true && item.root_resolved === true && item.root_system === false,
    ).length,
    plain_discussions: discussions.filter(
      (item) => item.root_resolvable === false && item.root_system === false,
    ).length,
  };
  const result: Json = {
    schema_version: ARTIFACT_VERSION,
    profile: "code-review",
    external_mutations: false,
    evidence_digest: evidenceDigest,
    target: target,
    role: role,
    current_user_id: currentUserId,
    current_user_username: currentUsername,
    mr_author_username: authorUsername,
    discussions: discussions,
    notes: notes,
    issue_templates: issueTemplates,
    release_evidence: semverCollect(evidence),
    counts: counts,
    exact_git: exactGit,
    complete:
      evidence.retrieval_complete === true &&
      notesComponent.complete === true &&
      errors.length === 0,
    errors: errors,
    artifact_root: evidence.artifact_root,
    prepared_at: new Date().toISOString(),
  };
  const root = await artifactRoot(String(evidence.artifact_root));
  const selection = await incrementalContext(evidence, result, root, incremental);
  result.incremental = selection;
  return result;
}

export async function prepareContext(
  evidenceValue: string,
  repoRoot: string,
  incremental = "auto",
  reviewMode = "normal",
  locale = "en",
): Promise<Json> {
  if (!["fast", "normal", "deep"].includes(reviewMode)) {
    throw new WorkflowError("review mode must be fast, normal, or deep");
  }
  if (!SUPPORTED_LOCALES.has(locale)) {
    throw new WorkflowError("review locale must be en or ru");
  }
  const [evidencePath, evidence, root, evidenceDigest] = await evidenceContext(evidenceValue);
  const [currentEvidencePath] = reviewEvidenceFromRoot(root);
  if (currentEvidencePath !== evidencePath) {
    throw new WorkflowError("review context requires the current evidence snapshot");
  }
  const context = await collectContext(evidence, evidenceDigest, repoRoot, incremental);
  const [path, contextDigest] = await writeArtifact(root, "review_context", context);
  const incrementalValue = context.incremental as Json;
  const delta = incrementalValue.incremental_delta as Json;
  const selectedMode = ["incremental", "unchanged"].includes(incrementalValue.mode as string)
    ? (incrementalValue.mode as string)
    : reviewMode;
  const criticRequired = ["normal", "deep", "incremental"].includes(selectedMode);
  const exactGit = context.exact_git as Json;
  const resolvedRepo = exactGit.repo_root as string;
  let nextAction: Json;
  let stage: string;
  if (context.complete === true) {
    await advanceProgress(root, "context_ready", {
      expectedStages: new Set(["prepared"]),
      expected: { evidence_path: evidencePath, evidence_digest: evidenceDigest },
      repo_root: resolvedRepo,
      context_path: path,
      context_digest: contextDigest,
      mode: selectedMode,
      locale: locale,
      incremental: incremental,
      critic_receipt_path: null,
      critic_receipt_digest: null,
      finalize_report_path: null,
      finalize_report_digest: null,
      decision_path: null,
      decision_digest: null,
      plan_path: null,
      plan_digest: null,
    });
    nextAction = criticRequired
      ? runnerAction("template-review", ["--artifact-root", root, "--kind", "critic"])
      : runnerAction("finalize", ["--artifact-root", root]);
    stage = "context_ready";
  } else {
    await advanceProgress(root, "prepared", {
      expectedStages: new Set(["prepared"]),
      expected: { evidence_path: evidencePath, evidence_digest: evidenceDigest },
      repo_root: resolvedRepo,
      context_path: null,
      context_digest: null,
      mode: reviewMode,
      locale: locale,
      incremental: incremental,
      critic_receipt_path: null,
      critic_receipt_digest: null,
      finalize_report_path: null,
      finalize_report_digest: null,
      decision_path: null,
      decision_digest: null,
      plan_path: null,
      plan_digest: null,
    });
    nextAction = runnerAction("context", [
      "--evidence",
      evidencePath,
      "--repo-root",
      resolvedRepo,
      "--incremental",
      incremental,
      "--review-mode",
      reviewMode,
      "--locale",
      locale,
    ]);
    stage = "prepared";
  }
  return {
    status: context.complete === true ? "ok" : "incomplete",
    summary: {
      tldr: "Collected role, threads, notes, and exact local Git context.",
      scope: [String((context.target as Json).url ?? "")],
      risks: context.complete === true ? [] : context.errors,
      checks: ["current GitLab user", "thread completeness", "exact local SHAs"],
    },
    artifact_path: path,
    digest: contextDigest,
    role: context.role,
    counts: context.counts,
    incremental: {
      mode: incrementalValue.mode,
      reason: incrementalValue.reason,
      critic_required: criticRequired,
      incremental_delta_digest: incrementalValue.incremental_delta_digest,
      changed_paths: delta.changed_paths,
      changed_threads: (delta.changed_thread_ids as string[]).length,
      changed_notes: (delta.changed_note_ids as string[]).length,
      metadata_fields: delta.metadata_fields,
      pipelines_changed: delta.pipelines_changed,
      fallback_reasons: incrementalValue.fallback_reasons,
      publication_plan_path: null,
    },
    review_mode: selectedMode,
    locale: locale,
    stage: stage,
    next_action: nextAction,
    complete: context.complete,
    external_mutations: false,
  };
}

export async function validateContextBinding(
  contextValue: string,
  evidenceValue: string,
): Promise<[string, Json, string]> {
  const [, evidence, root, evidenceDigest] = await evidenceContext(evidenceValue);
  const path = regularFile(contextValue, "review context");
  const contextDigest = sha256Bytes(readFileSync(path));
  const expected = `${root}/artifacts/review_context/${contextDigest}.json`;
  if (path !== expected) {
    throw new WorkflowError("review context is not content-addressed");
  }
  const [, context] = artifactPayload(path, "review_context");
  if (context.evidence_digest !== evidenceDigest || !jsonEqual(context.target, evidence.target)) {
    throw new WorkflowError("review context does not bind the review evidence");
  }
  return [path, context, contextDigest];
}

function contextFingerprint(context: Json): Json {
  const result: Json = {};
  for (const [key, value] of Object.entries(context)) {
    if (key !== "artifact_root" && key !== "prepared_at") result[key] = value;
  }
  return result;
}

export function contextsMatch(expected: Json, current: Json): boolean {
  const currentValue = contextFingerprint(current);
  if (!("incremental" in expected)) delete currentValue.incremental;
  return jsonEqual(contextFingerprint(expected), currentValue);
}

export async function refreshContext(context: Json, evidenceValue: string): Promise<Json> {
  const [, evidence, , evidenceDigest] = await evidenceContext(evidenceValue);
  const exactGit = context.exact_git;
  const repoRoot = isDict(exactGit) ? exactGit.repo_root : null;
  if (typeof repoRoot !== "string") {
    throw new WorkflowError("review context repository root is unavailable");
  }
  const incremental = context.incremental;
  const requested = isDict(incremental) ? (incremental.requested as string) : "auto";
  return collectContext(evidence, evidenceDigest, repoRoot, String(requested));
}

export function contentAddressedArtifact(
  value: string,
  root: string,
  kind: string,
): [string, Json, string] {
  const path = regularFile(value, kind.replace(/_/g, " "));
  const artifactDigest = sha256Bytes(readFileSync(path));
  const expected = `${root}/artifacts/${kind}/${artifactDigest}.json`;
  if (path !== expected) {
    throw new WorkflowError(`${kind.replace(/_/g, " ")} is not content-addressed`);
  }
  const [, payload] = artifactPayload(path, kind);
  return [path, payload, artifactDigest];
}

function markdownCell(value: unknown): string {
  return pyStr(value).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

export function codeFence(value: string, language = ""): string {
  const runs = value.match(/`+/g) ?? [];
  const fence = "`".repeat(Math.max(3, ...runs.map((run) => run.length + 1)));
  return `${fence}${language}\n${value.trimEnd()}\n${fence}`;
}

export function metadataAssessment(evidence: Json, assessment: unknown): Json {
  const objectValue = evidence.object;
  if (!isDict(objectValue)) {
    throw new WorkflowError("MR metadata is unavailable");
  }
  const title = objectValue.title;
  const description = objectValue.description ?? null;
  const labels = objectValue.labels;
  const state = objectValue.state;
  if (
    typeof title !== "string" ||
    (description !== null && typeof description !== "string") ||
    !Array.isArray(labels) ||
    !labels.every((item) => typeof item === "string") ||
    !nonemptyString(state)
  ) {
    throw new WorkflowError("MR title, description, labels, or workflow state is invalid");
  }
  const result: Json = {
    observed: {
      title: title,
      description: description,
      labels: labels,
      workflow_state: state,
    },
    assessment: assessment,
  };
  if (!mrMetadataAssessmentIsValid(result)) {
    throw new WorkflowError("MR metadata assessment is invalid");
  }
  return result;
}

const PRESENTATION_KEYS = new Set([
  "title",
  "incremental_notice",
  "target_label",
  "role_label",
  "role_value",
  "verdict_label",
  "verdict_value",
  "metadata_heading",
  "labels_heading",
  "previous_findings_heading",
  "open_threads_heading",
  "closed_threads_heading",
  "local_fixes_heading",
  "new_findings_heading",
  "recommended_issues_heading",
  "checked_heading",
  "architecture_heading",
  "semver_heading",
  "checks_heading",
  "publication_heading",
  "no_items",
  "publication_warning",
  "previous_table_headers",
  "evidence_label",
  "relation_label",
  "severity_labels",
  "recovery_label",
]);

function validatePresentation(value: unknown, incrementalMode: string): Json {
  if (!isDict(value) || !setsEqual(keySet(value), PRESENTATION_KEYS)) {
    throw new WorkflowError("review presentation is invalid");
  }
  const scalarKeys = [...PRESENTATION_KEYS].filter(
    (key) =>
      key !== "incremental_notice" && key !== "previous_table_headers" && key !== "severity_labels",
  );
  if (!scalarKeys.every((key) => nonemptyString(value[key]))) {
    throw new WorkflowError("review presentation labels must be non-empty");
  }
  const notice = value.incremental_notice ?? null;
  if (incrementalMode === "incremental") {
    if (!nonemptyString(notice)) {
      throw new WorkflowError("incremental review requires a localized notice");
    }
  } else if (notice !== null) {
    throw new WorkflowError("full review must not claim incremental review");
  }
  const headers = value.previous_table_headers;
  if (
    !Array.isArray(headers) ||
    headers.length !== 5 ||
    !headers.every((item) => nonemptyString(item))
  ) {
    throw new WorkflowError("previous finding table headers are invalid");
  }
  const severityLabels = value.severity_labels;
  if (
    !isDict(severityLabels) ||
    !setsEqual(keySet(severityLabels), new Set(["critical", "high", "medium", "low"])) ||
    !Object.values(severityLabels).every((item) => nonemptyString(item))
  ) {
    throw new WorkflowError("localized severity labels are invalid");
  }
  return value;
}

export function validateChatAssessment(value: unknown): Json {
  if (!isDict(value) || !setsEqual(keySet(value), new Set(["necessity", "relevance", "change"]))) {
    throw new WorkflowError("review chat assessment is invalid");
  }
  const necessity = value.necessity;
  const relevance = value.relevance;
  if (
    !isDict(necessity) ||
    !setsEqual(keySet(necessity), new Set(["status", "rationale"])) ||
    !["supported", "doubtful", "unconfirmed"].includes(necessity.status as string) ||
    !nonemptyString(necessity.rationale) ||
    !isDict(relevance) ||
    !setsEqual(keySet(relevance), new Set(["status", "rationale"])) ||
    !["current", "partly_outdated", "outdated"].includes(relevance.status as string) ||
    !nonemptyString(relevance.rationale) ||
    !nonemptyString(value.change)
  ) {
    throw new WorkflowError("review chat assessment is invalid");
  }
  return value;
}

function suggestionBlocks(body: string): RegExpMatchArray[] {
  const matches = [...body.matchAll(SUGGESTION_RE)];
  const openers = body.match(SUGGESTION_OPENER_RE) ?? [];
  if (openers.length !== matches.length) {
    throw new WorkflowError("GitLab suggestion syntax is malformed");
  }
  return matches;
}

export function validateSuggestion(
  body: string,
  options: {
    repoRoot?: string | null;
    headSha?: string | null;
    path?: string | null;
    line?: number | null;
  } = {},
): void {
  const matches = suggestionBlocks(body);
  if (matches.length !== 1) {
    throw new WorkflowError("suggestion fix requires exactly one suggestion block");
  }
  const match = matches[0];
  const before = match[1] === undefined ? 0 : Number(match[1]);
  const after = match[2] === undefined ? 0 : Number(match[2]);
  if (before > 100 || after > 100 || before + after + 1 > 201) {
    throw new WorkflowError("GitLab suggestion range exceeds the supported limit");
  }
  const { repoRoot, headSha, path, line } = options;
  if (
    repoRoot === undefined ||
    repoRoot === null ||
    headSha === undefined ||
    headSha === null ||
    path === undefined ||
    path === null ||
    line === undefined ||
    line === null
  ) {
    return;
  }
  let source: string | Buffer;
  try {
    source = gitRead(repoRoot, ["show", `${headSha}:${path}`]);
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    throw new WorkflowError("suggestion path is unavailable at the reviewed head");
  }
  const lineCount = pySplitLines(String(source)).length;
  if (line - before < 1 || line + after > lineCount) {
    throw new WorkflowError("GitLab suggestion range escapes the reviewed file");
  }
}

function patchTokens(value: string): string[] {
  const result: string[] = [];
  let index = 0;
  while (index < value.length) {
    while (index < value.length && /\s/.test(value[index])) index += 1;
    if (index === value.length) break;
    if (value[index] !== '"') {
      let end = index;
      while (end < value.length && !/\s/.test(value[end])) end += 1;
      result.push(value.slice(index, end));
      index = end;
      continue;
    }
    index += 1;
    const decoded: number[] = [];
    while (index < value.length && value[index] !== '"') {
      if (value[index] !== "\\") {
        for (const byte of Buffer.from(value[index] as string, "utf8")) decoded.push(byte);
        index += 1;
        continue;
      }
      index += 1;
      if (index === value.length) {
        throw new WorkflowError("Git patch has an invalid quoted path");
      }
      if (/[0-7]/.test(value[index] as string)) {
        let end = index;
        while (end < Math.min(index + 3, value.length) && /[0-7]/.test(value[end] as string)) {
          end += 1;
        }
        const octet = Number.parseInt(value.slice(index, end), 8);
        if (octet === 0 || octet > 0o377) {
          throw new WorkflowError("Git patch quoted path is unsafe");
        }
        decoded.push(octet);
        index = end;
        continue;
      }
      const escapes: Record<string, number> = {
        a: 7,
        b: 8,
        t: 9,
        n: 10,
        v: 11,
        f: 12,
        r: 13,
        '"': 34,
        "\\": 92,
      };
      if (!((value[index] as string) in escapes)) {
        throw new WorkflowError("Git patch has an invalid quoted path");
      }
      decoded.push(escapes[value[index] as string]);
      index += 1;
    }
    if (index === value.length) {
      throw new WorkflowError("Git patch has an unterminated quoted path");
    }
    index += 1;
    const bytes = Buffer.from(decoded);
    const text = bytes.toString("utf8");
    if (!bytes.equals(Buffer.from(text, "utf8"))) {
      throw new WorkflowError("Git patch path is not UTF-8");
    }
    result.push(text);
  }
  return result;
}

function patchPaths(patch: string): string[] {
  if (
    !patch.endsWith("\n") ||
    Buffer.byteLength(patch, "utf8") > MAX_BYTES ||
    patch.includes("\x00") ||
    patch.includes("GIT binary patch") ||
    patch.includes("Binary files ") ||
    /^index /m.test(patch) ||
    /^(?:old mode|new mode|new file mode|deleted file mode) (?:120000|160000)$/m.test(patch)
  ) {
    throw new WorkflowError("Git patch is unsafe or exceeds the size limit");
  }
  const paths: string[] = [];
  let current: [string, string] | null = null;
  let oldHeader: string | null = null;
  let newHeader: string | null = null;

  const finishDiff = (): void => {
    if (current === null) return;
    if (oldHeader === null || newHeader === null) {
      throw new WorkflowError("Git patch file headers are incomplete");
    }
    const [oldPath, newPath] = current;
    if (
      !["/dev/null", `a/${oldPath}`].includes(oldHeader) ||
      !["/dev/null", `b/${newPath}`].includes(newHeader)
    ) {
      throw new WorkflowError("Git patch file headers disagree");
    }
  };

  for (const rawLine of patch.split("\n")) {
    if (
      rawLine.startsWith("rename from ") ||
      rawLine.startsWith("rename to ") ||
      rawLine.startsWith("copy from ") ||
      rawLine.startsWith("copy to ")
    ) {
      throw new WorkflowError("Git patch renames and copies are unsupported");
    }
    if (rawLine.startsWith("--- ") || rawLine.startsWith("+++ ")) {
      const values = patchTokens(rawLine.slice(4));
      if (
        values.length !== 1 ||
        (values[0] !== "/dev/null" &&
          !values[0].startsWith(rawLine.startsWith("--- ") ? "a/" : "b/"))
      ) {
        throw new WorkflowError("Git patch file path escapes the repository");
      }
      if (rawLine.startsWith("--- ")) oldHeader = values[0];
      else newHeader = values[0];
    }
    if (!rawLine.startsWith("diff --git ")) continue;
    finishDiff();
    const parts = patchTokens(rawLine.slice("diff --git ".length));
    if (parts.length !== 2) {
      throw new WorkflowError("Git patch has an invalid diff header");
    }
    const oldPath = posixRelative(parts[0], "a/");
    const newPath = posixRelative(parts[1], "b/");
    if (oldPath !== newPath) {
      throw new WorkflowError("Git patch renames are unsupported");
    }
    current = [oldPath, newPath];
    oldHeader = null;
    newHeader = null;
    paths.push(oldPath);
  }
  finishDiff();
  if (paths.length === 0) {
    throw new WorkflowError("Git patch contains no file diff");
  }
  return sortedStrings([...new Set(paths)]);
}

function splitAsciiWhitespace(value: string): string[] {
  return value.split(/[ \t\n\r\f\v]+/).filter((item) => item.length > 0);
}

export function validateGitPatch(
  repoRoot: string,
  headSha: string,
  patch: string,
  result?: { tree?: string },
): string[] {
  const paths = patchPaths(patch);
  for (const path of paths) {
    const treeEntry = String(gitRead(repoRoot, ["ls-tree", headSha, "--", path])).trim();
    if (treeEntry.startsWith("120000 ") || treeEntry.startsWith("160000 ")) {
      throw new WorkflowError("Git patch cannot modify symlinks or submodules");
    }
  }
  let inspectedStdout: Buffer;
  const temporary = mkdtempSync(`${tmpdir()}/code-review-patch-`);
  try {
    const environment = { ...process.env, GIT_INDEX_FILE: `${temporary}/index` };
    const readTree = spawnSync("git", ["-C", repoRoot, "read-tree", headSha], {
      env: environment,
      timeout: 45_000,
    });
    if (readTree.error !== undefined || readTree.status !== 0) {
      throw new WorkflowError("reviewed head cannot initialize Git patch validation");
    }
    const applyCommand = ["git", "-C", repoRoot, "apply", "--cached", "--whitespace=nowarn", "-"];
    const checked = spawnSync("git", [...applyCommand.slice(1, -1), "--check", "-"], {
      env: environment,
      input: Buffer.from(patch, "utf8"),
      timeout: 45_000,
    });
    if (checked.error !== undefined) {
      throw new WorkflowError("Git patch validation could not be completed");
    }
    if (checked.status !== 0) {
      throw new WorkflowError("Git patch does not apply to the exact reviewed head");
    }
    const applied = spawnSync("git", applyCommand.slice(1), {
      env: environment,
      input: Buffer.from(patch, "utf8"),
      timeout: 45_000,
    });
    if (applied.error !== undefined || applied.status !== 0) {
      throw new WorkflowError("Git patch cannot be inspected safely");
    }
    const inspected = spawnSync(
      "git",
      ["-C", repoRoot, "diff-index", "--cached", "--raw", "-z", headSha, "--"],
      { env: environment, timeout: 45_000 },
    );
    if (inspected.error !== undefined || inspected.status !== 0) {
      throw new WorkflowError("Git patch effective paths cannot be inspected");
    }
    inspectedStdout = inspected.stdout as Buffer;
    if (result !== undefined) {
      const tree = spawnSync("git", ["-C", repoRoot, "write-tree"], {
        env: environment,
        encoding: "utf8",
        timeout: 45_000,
      });
      if (tree.status !== 0 || tree.error)
        throw new WorkflowError("Cannot compare complete fix result");
      result.tree = tree.stdout.trim();
    }
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  const values = inspectedStdout.toString("latin1").split("\0");
  const effectivePaths: string[] = [];
  let index = 0;
  while (index < values.length && values[index].length > 0) {
    const metadata = splitAsciiWhitespace(values[index] as string);
    if (metadata.length !== 5 || !metadata[0].startsWith(":")) {
      throw new WorkflowError("Git patch effective diff is invalid");
    }
    const oldMode = (metadata[0] as string).slice(1);
    const newMode = metadata[1] as string;
    const status = metadata[4] as string;
    if (
      oldMode === "120000" ||
      oldMode === "160000" ||
      newMode === "120000" ||
      newMode === "160000"
    ) {
      throw new WorkflowError("Git patch cannot modify symlinks or submodules");
    }
    if (status.startsWith("R") || status.startsWith("C")) {
      throw new WorkflowError("Git patch renames and copies are unsupported");
    }
    index += 1;
    if (index >= values.length || (values[index] as string).length === 0) {
      throw new WorkflowError("Git patch effective path is unavailable");
    }
    const bytes = Buffer.from(values[index] as string, "latin1");
    const effectivePath = bytes.toString("utf8");
    if (!bytes.equals(Buffer.from(effectivePath, "utf8"))) {
      throw new WorkflowError("Git patch effective path is not UTF-8");
    }
    const parts = effectivePath.split("/").filter((part) => part !== "");
    if (effectivePath.startsWith("/") || parts.length === 0 || parts.includes("..")) {
      throw new WorkflowError("Git patch effective path escapes the repository");
    }
    effectivePaths.push(parts.join("/"));
    index += 1;
  }
  if (!jsonEqual(sortedStrings([...new Set(effectivePaths)]), paths)) {
    throw new WorkflowError("Git patch declared and effective paths disagree");
  }
  return paths;
}

function changedDiffLines(
  repoRoot: string,
  baseSha: string,
  headSha: string,
  path: string,
): [Set<number>, Set<number>] {
  const diff = String(gitRead(repoRoot, ["diff", "--unified=3", baseSha, headSha, "--", path]));
  const oldLines = new Set<number>();
  const newLines = new Set<number>();
  const pattern = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/gm;
  for (const match of diff.matchAll(pattern)) {
    const oldStart = Number(match[1]);
    const newStart = Number(match[3]);
    const oldCount = match[2] === undefined ? 1 : Number(match[2]);
    const newCount = match[4] === undefined ? 1 : Number(match[4]);
    for (let value = oldStart; value < oldStart + oldCount; value += 1) oldLines.add(value);
    for (let value = newStart; value < newStart + newCount; value += 1) newLines.add(value);
  }
  return [oldLines, newLines];
}

export function expectedThreadBindings(context: Json): Record<string, Json> {
  const discussions = (context.discussions as Json[]) ?? [];
  const expected: Record<string, Json> = {};
  for (const item of discussions) {
    if (item.root_system === true) continue;
    const meaningful = ((item.notes as unknown[]) ?? []).filter(
      (note) => isDict(note) && note.system !== true && typeof note.body === "string",
    ) as Json[];
    if (meaningful.length === 0) {
      throw new WorkflowError("non-system discussion has no meaningful note");
    }
    const lastNote = meaningful[meaningful.length - 1] as Json;
    expected[String(item.root_note_id)] = {
      ...item,
      state:
        item.root_resolved === true ? "resolved" : item.root_resolvable === true ? "open" : "plain",
      url: item.root_note_url,
      last_note_id: lastNote.id,
      last_note_body_sha256: sha256Text(lastNote.body as string),
      thread_sha256: sha256Text(discussionSignature(item)),
    };
  }
  const discussionNoteIds = new Set<string>();
  for (const discussion of discussions) {
    for (const note of (discussion.notes as unknown[]) ?? []) {
      discussionNoteIds.add(String((note as Json).id));
    }
  }
  for (const note of (context.notes as Json[]) ?? []) {
    const noteId = String(note.id);
    if (note.system !== true && !discussionNoteIds.has(noteId)) {
      const body = note.body ?? null;
      if (typeof body !== "string") {
        throw new WorkflowError("non-system note body is invalid");
      }
      expected[noteId] = {
        root_note_url: note.note_url,
        state: "plain",
        url: note.note_url,
        last_note_id: note.id,
        last_note_body_sha256: sha256Text(body),
        thread_sha256: sha256Text(pyJson(note)),
      };
    }
  }
  return expected;
}

export function validatePatchFallback(fix: Json, context: Json, evidence: Json): void {
  if (fix.fix_mode !== "patch" || fix.type === "local_fix" || fix.outcome === "local_fix") return;
  if (!nonemptyString(fix.patch_reason))
    throw new WorkflowError(
      "Expected a concrete patch_reason explaining technical impossibility or unsafe division",
    );
  const repo = String((context.exact_git as Json).repo_root);
  const head = String(evidence.head_sha);
  const result: { tree?: string } = {};
  validateGitPatch(repo, head, String(fix.patch), result);
  const paths = patchPaths(String(fix.patch));
  const hunks = [
    ...String(fix.patch).matchAll(
      /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n([\s\S]*?)(?=^@@ |^diff --git |$(?![\s\S]))/gm,
    ),
  ];
  if (paths.length !== 1 || hunks.length !== 1) return;
  const hunk = hunks[0];
  const count = Number(hunk[2] ?? 1),
    start = Number(hunk[1]);
  if (count > 201) return;
  const [, visible] = changedDiffLines(repo, String(evidence.base_sha), head, paths[0]);
  let replacement = hunk[5]
    .split("\n")
    .filter((row) => row.startsWith(" ") || row.startsWith("+"))
    .map((row) => row.slice(1))
    .join("\n");
  let line: number | undefined,
    before = 0,
    after = 0;
  if (count === 0) {
    line = Math.max(1, start);
    if (!visible.has(line)) return;
    let source: string;
    try {
      source = String(gitRead(repo, ["show", `${head}:${paths[0]}`])).split("\n")[line - 1];
    } catch (error) {
      if (error instanceof WorkflowError) return;
      throw error;
    }
    replacement = start === 0 ? `${replacement}\n${source}` : `${source}\n${replacement}`;
  } else {
    line = [...visible].find(
      (value) =>
        value >= start &&
        value < start + count &&
        value - start <= 100 &&
        start + count - value - 1 <= 100,
    );
    if (line === undefined) return;
    before = line - start;
    after = start + count - line - 1;
  }
  const suggestion = {
    path: paths[0],
    line,
    body: `\`\`\`suggestion:-${before}+${after}\n${replacement}\n\`\`\``,
  };
  const suggested: { tree?: string } = {};
  try {
    validateGitPatch(repo, head, suggestionsPatch(repo, head, [suggestion]), suggested);
  } catch (error) {
    if (error instanceof WorkflowError) return;
    throw error;
  }
  if (suggested.tree === result.tree)
    throw new WorkflowError(
      "A safe bounded suggestion is available on the exact visible head; use fix_mode=suggestion instead of patch",
    );
}

function validateFixingCommit(value: unknown): void {
  if (value === null || value === undefined) return;
  if (
    !isDict(value) ||
    !setsEqual(keySet(value), new Set(["title", "url"])) ||
    !nonemptyString(value.title) ||
    typeof value.url !== "string" ||
    IMMUTABLE_GITLAB_COMMIT_URL_RE.test(value.url) !== true
  ) {
    throw new WorkflowError("fixing commit attribution is invalid");
  }
}

export function validateThreadFix(
  item: Json,
  source: Json,
  repoRoot: string,
  headSha: string,
  baseSha: string,
): void {
  const fixMode = item.fix_mode;
  if (
    item.routing_response !== undefined &&
    (!Array.isArray(item.suggestions) ||
      !nonemptyString(item.routing_response) ||
      /^```suggestion|^diff --git |git\s+apply\s*(?:<<|--)/m.test(String(item.routing_response)))
  )
    throw new WorkflowError("routing_response requires grouped suggestions and prose only");
  if (!["suggestion", "patch", "not_required"].includes(fixMode as string)) {
    throw new WorkflowError("thread fix mode is invalid");
  }
  const response = item.proposed_response ?? null;
  const suggestionCount = typeof response === "string" ? suggestionBlocks(response).length : 0;
  if (item.suggestions !== undefined) {
    if (
      fixMode !== "suggestion" ||
      item.outcome === "no_publication" ||
      item.outcome === "local_fix" ||
      suggestionCount !== 0 ||
      item.patch !== null
    )
      throw new WorkflowError(
        "Related thread suggestions require a published prose response and no patch",
      );
    const parts = suggestionParts(item);
    for (const part of parts) {
      validateSuggestion(part.body, { repoRoot, headSha, path: part.path, line: part.line });
      const [, lines] = changedDiffLines(repoRoot, baseSha, headSha, part.path);
      if (!lines.has(part.line))
        throw new WorkflowError("Thread suggestion position is outside the exact visible diff");
      validateGitPatch(repoRoot, headSha, suggestionsPatch(repoRoot, headSha, [part]));
    }
    validateGitPatch(repoRoot, headSha, suggestionsPatch(repoRoot, headSha, parts));
    return;
  }
  const position = source.root_position ?? null;
  const currentNewLine = Boolean(
    isDict(position) &&
    typeof position.new_path === "string" &&
    isPlainInt(position.new_line) &&
    position.head_sha === headSha,
  );
  if (
    fixMode === "suggestion" &&
    (["no_publication", "local_fix"].includes(item.outcome as string) ||
      !currentNewLine ||
      suggestionCount !== 1 ||
      (item.patch ?? null) !== null)
  ) {
    throw new WorkflowError(
      "an applicable current-line thread fix requires exactly one suggestion block",
    );
  }
  if (fixMode === "suggestion") {
    const exactPosition = position as Json;
    validateSuggestion(response as string, {
      repoRoot: repoRoot,
      headSha: headSha,
      path: exactPosition.new_path as string,
      line: exactPosition.new_line as number,
    });
    validateGitPatch(
      repoRoot,
      headSha,
      suggestionsPatch(repoRoot, headSha, [
        {
          path: String(exactPosition.new_path),
          line: Number(exactPosition.new_line),
          body: String(response),
        },
      ]),
    );
  }
  if (
    fixMode === "patch" &&
    (item.outcome === "no_publication" || !nonemptyString(item.patch) || suggestionCount !== 0)
  ) {
    throw new WorkflowError("thread patch fix is invalid");
  }
  if (fixMode === "patch") {
    if (!nonemptyString(item.patch_reason))
      throw new WorkflowError("Thread patch fallback requires a concrete patch_reason");
    if (/^diff --git |git\s+apply\s*(?:<<|--)/m.test(String(response)))
      throw new WorkflowError(
        "Thread patch response must be prose only; the runner owns the patch block",
      );
    validateGitPatch(repoRoot, headSha, item.patch as string);
  }
  if (fixMode === "not_required" && ((item.patch ?? null) !== null || suggestionCount !== 0)) {
    throw new WorkflowError("a thread without a code fix cannot contain suggestion or patch");
  }
  if (item.outcome === "no_publication" && fixMode !== "not_required") {
    throw new WorkflowError("a non-published thread cannot claim a code fix");
  }
  if (item.outcome === "local_fix" && fixMode !== "patch") {
    throw new WorkflowError("a local thread fix requires a Git patch");
  }
}

export function validateFindingPublications(value: unknown, findingIds: Set<string>): Json[] {
  const keys = new Set([
    "finding_id",
    "type",
    "path",
    "line",
    "old_line",
    "body",
    "fix_mode",
    "patch",
  ]);
  if (!Array.isArray(value)) {
    throw new WorkflowError("finding publications must be an array");
  }
  const result: Json[] = [];
  const seen = new Set<string>();
  for (const entry of value) {
    const item = entry as Json;
    if (!isDict(item)) throw new WorkflowError("finding publication is invalid");
    const baseKeys = keySet(item);
    for (const key of ["suggestions", "split_rationale", "patch_reason", "thread_id"])
      baseKeys.delete(key);
    if (!isDict(item) || !setsEqual(baseKeys, keys)) {
      throw new WorkflowError("finding publication is invalid");
    }
    const findingId = item.finding_id;
    const publicationType = item.type;
    const path = item.path ?? null;
    const line = item.line ?? null;
    const oldLine = item.old_line ?? null;
    if (publicationType !== "existing_thread" && item.thread_id !== undefined)
      throw new WorkflowError(
        "thread_id is valid only with type=existing_thread; other finding fixes must omit it",
      );
    if (publicationType === "existing_thread") {
      if (
        !nonemptyString(findingId) ||
        !findingIds.has(String(findingId)) ||
        seen.has(String(findingId)) ||
        !nonemptyString(item.thread_id) ||
        !nonemptyString(item.body) ||
        item.fix_mode !== "not_required" ||
        item.patch !== null ||
        path !== null ||
        line !== null ||
        oldLine !== null ||
        item.suggestions !== undefined
      )
        throw new WorkflowError(
          "existing_thread requires thread_id, prose body, not_required, and null patch/positions; the thread owns the fix",
        );
      seen.add(String(findingId));
      result.push(item);
      continue;
    }
    if (
      !nonemptyString(findingId) ||
      !findingIds.has(findingId as string) ||
      seen.has(findingId as string) ||
      !["general", "line", "local_fix"].includes(publicationType as string) ||
      !nonemptyString(item.body) ||
      !["suggestion", "patch"].includes(item.fix_mode as string)
    ) {
      throw new WorkflowError("finding publication identity or body is invalid");
    }
    const fixMode = item.fix_mode as string;
    const patch = item.patch ?? null;
    const suggestionCount = suggestionBlocks(item.body as string).length;
    const grouped = item.suggestions !== undefined;
    if (grouped) {
      suggestionParts(item);
      if (fixMode !== "suggestion" || suggestionCount !== 0)
        throw new WorkflowError("Grouped suggestion body must be prose; parts own their blocks");
    }
    if (fixMode === "patch") {
      if (!nonemptyString(patch) || suggestionCount !== 0) {
        throw new WorkflowError("patch fix requires a patch and forbids suggestion");
      }
      patchPaths(patch as string);
      if (/^diff --git |git\s+apply\s*(?:<<|--)/m.test(String(item.body)))
        throw new WorkflowError("Patch body must be prose only; put the unified diff in patch");
    } else if (patch !== null || (!grouped && suggestionCount !== 1)) {
      throw new WorkflowError("suggestion fix requires one suggestion and no patch");
    }
    if (publicationType === "general" || publicationType === "local_fix") {
      if (path !== null || line !== null || oldLine !== null) {
        throw new WorkflowError("non-line finding fix cannot have a line");
      }
      if (fixMode !== "patch" && !grouped) {
        throw new WorkflowError("general and local finding fixes require a Git patch");
      }
    } else if (
      !nonemptyString(path) ||
      (line === null) === (oldLine === null) ||
      [line, oldLine].some((number) => number !== null && (!isPlainInt(number) || number < 1))
    ) {
      throw new WorkflowError("line finding publication position is invalid");
    } else if (oldLine !== null && fixMode !== "patch") {
      throw new WorkflowError("deleted-line finding fixes require a Git patch");
    } else if (fixMode === "suggestion" && !grouped) {
      validateSuggestion(item.body as string);
    }
    seen.add(findingId as string);
    result.push(item);
  }
  return result;
}

function validatePreviousAssessments(
  value: unknown,
  previousFindings: Json[],
  previousIssues: Json[],
): Json[] {
  const keys = new Set([
    "id",
    "kind",
    "status",
    "previous_status",
    "current_status",
    "rationale",
    "action",
    "publication_action",
    "publication_body",
    "critic_required",
  ]);
  if (!Array.isArray(value)) {
    throw new WorkflowError("previous finding assessments must be an array");
  }
  const expected: Record<string, string> = {};
  for (const item of previousFindings) expected[String(item.id)] = "finding";
  for (const item of previousIssues) expected[String(item.id)] = "issue";
  const actual: Record<string, Json> = {};
  for (const entry of value) {
    const item = entry as Json;
    if (!isDict(item) || !setsEqual(keySet(item), keys)) {
      throw new WorkflowError("previous finding assessment is invalid");
    }
    const itemId: string = String(item.id);
    const action = item.publication_action;
    const body = item.publication_body ?? null;
    if (
      !nonemptyString(itemId) ||
      itemId in actual ||
      !["finding", "issue"].includes(item.kind as string) ||
      !PREVIOUS_FINDING_STATUSES.has(item.status as string) ||
      typeof item.critic_required !== "boolean" ||
      (["changed", "unverified"].includes(item.status as string) &&
        item.critic_required !== true) ||
      !["previous_status", "current_status", "rationale", "action"].every((key) =>
        nonemptyString(item[key]),
      ) ||
      !["no_publication", "reply", "resolve", "reopen", "update_issue"].includes(
        action as string,
      ) ||
      (item.kind === "issue" && !["no_publication", "update_issue"].includes(action as string)) ||
      (item.kind === "finding" && action === "update_issue") ||
      (action === "resolve" && !["fixed", "withdrawn"].includes(item.status as string)) ||
      (action === "reopen" &&
        !["active", "changed", "unverified"].includes(item.status as string)) ||
      (action === "no_publication" && body !== null) ||
      (action !== "no_publication" && !nonemptyString(body))
    ) {
      throw new WorkflowError("previous finding assessment is invalid");
    }
    actual[itemId as string] = item;
  }
  if (
    !setsEqual(new Set(Object.keys(actual)), new Set(Object.keys(expected))) ||
    Object.entries(expected).some(([itemId, kind]) => actual[itemId].kind !== kind)
  ) {
    throw new WorkflowError("every previous finding and issue requires one assessment");
  }
  return Object.values(actual);
}

function validateRecommendedIssues(value: unknown, _issueTemplates: Json[]): Json[] {
  const keys = new Set([
    "id",
    "title",
    "problem",
    "risk",
    "evidence",
    "reason_out_of_scope",
    "minimum_fix",
    "importance",
    "existing_task",
  ]);
  if (!Array.isArray(value)) {
    throw new WorkflowError("recommended issues must be an array");
  }
  const result: Json[] = [];
  const seen = new Set<string>();
  for (const entry of value) {
    const item = entry as Json;
    const legacyKeys = new Set(
      [...keys]
        .filter((key) => !["importance", "existing_task"].includes(key))
        .concat(["body", "template_path"]),
    );
    if (!isDict(item) || (!setsEqual(keySet(item), keys) && !setsEqual(keySet(item), legacyKeys))) {
      throw new WorkflowError("recommended issue is invalid");
    }
    const itemId = item.id;
    if (
      !nonemptyString(itemId) ||
      seen.has(itemId as string) ||
      ![
        "title",
        "problem",
        "risk",
        "reason_out_of_scope",
        "minimum_fix",
        "importance" in item ? "importance" : "body",
      ].every((key) => nonemptyString(item[key])) ||
      !Array.isArray(item.evidence) ||
      (item.evidence as unknown[]).length === 0 ||
      !(item.evidence as unknown[]).every((subItem) => nonemptyString(subItem))
    ) {
      throw new WorkflowError("recommended issue content is invalid");
    }
    if (
      item.existing_task !== undefined &&
      item.existing_task !== null &&
      !nonemptyString(item.existing_task)
    )
      throw new WorkflowError("recommended issue existing_task must be a task reference or null");
    seen.add(itemId as string);
    result.push(item);
  }
  return result;
}

function validateRejectedCandidates(value: unknown, decision: Json): Json[] {
  const keys = new Set([
    "id",
    "source",
    "finding",
    "reason",
    "paths",
    "thread_ids",
    "metadata_fields",
    "ci",
  ]);
  if (!Array.isArray(value)) {
    throw new WorkflowError("rejected candidates must be an array");
  }
  const primary = new Map<string, Json>();
  for (const item of (decision.findings as Json[]) ?? []) primary.set(String(item.id), item);
  const critic = new Map<string, Json>();
  for (const item of (decision.critic_findings as Json[]) ?? []) critic.set(String(item.id), item);
  const responses = new Map<string, Json>();
  for (const item of (decision.responses as Json[]) ?? []) responses.set(String(item.id), item);
  const result: Json[] = [];
  const seen = new Set<string>();
  for (const entry of value) {
    const item = entry as Json;
    if (!isDict(item) || !setsEqual(keySet(item), keys)) {
      throw new WorkflowError("rejected candidate is invalid");
    }
    const itemId = String(item.id);
    const source = item.source;
    const expected = source === "primary" ? primary.get(itemId) : critic.get(itemId);
    if (
      !nonemptyString(item.id) ||
      seen.has(itemId) ||
      !["primary", "critic"].includes(source as string) ||
      !jsonEqual(item.finding, expected ?? null) ||
      !nonemptyString(item.reason) ||
      ((responses.get(itemId) ?? ({} as Json)).decision ?? null) !== "reject" ||
      !["paths", "thread_ids", "metadata_fields"].every(
        (key) =>
          Array.isArray(item[key]) &&
          (item[key] as unknown[]).every((sub) => typeof sub === "string"),
      ) ||
      typeof item.ci !== "boolean"
    ) {
      throw new WorkflowError("rejected candidate is invalid");
    }
    seen.add(itemId);
    result.push(item);
  }
  const rejectedIds = new Set<string>();
  for (const itemId of new Set([...primary.keys(), ...critic.keys()])) {
    if (((responses.get(itemId) ?? ({} as Json)).decision ?? null) === "reject") {
      rejectedIds.add(itemId);
    }
  }
  if (!setsEqual(seen, rejectedIds)) {
    throw new WorkflowError("every rejected primary and critic candidate must be retained");
  }
  return result;
}

function validateRejectedCandidateAssessments(value: unknown, reconsidered: Json[]): Json[] {
  if (!Array.isArray(value)) {
    throw new WorkflowError("rejected candidate assessments must be an array");
  }
  const expected = new Set(reconsidered.map((item) => String(item.id)));
  const actual: Record<string, Json> = {};
  for (const entry of value) {
    const item = entry as Json;
    if (
      !isDict(item) ||
      !setsEqual(keySet(item), new Set(["id", "decision", "reason"])) ||
      !nonemptyString(item.id) ||
      !["still_rejected", "promoted"].includes(item.decision as string) ||
      !nonemptyString(item.reason) ||
      (item.id as string) in actual
    ) {
      throw new WorkflowError("rejected candidate assessment is invalid");
    }
    actual[item.id as string] = item;
  }
  if (!setsEqual(new Set(Object.keys(actual)), expected)) {
    throw new WorkflowError("every affected rejected candidate requires one assessment");
  }
  return Object.values(actual);
}

function previousRevisions(incremental: Json): Record<string, number> {
  const result: Record<string, number> = {};
  for (const item of (incremental.previous_finding_ledger as Json[]) ?? []) {
    const itemId = item.id;
    const revision = item.revision;
    if (nonemptyString(itemId) && isPlainInt(revision)) {
      result[itemId as string] = Math.max(result[itemId as string] ?? 0, revision);
    }
  }
  for (const key of ["previous_finding_publications", "previous_recommended_issues"]) {
    for (const item of (incremental[key] as Json[]) ?? []) {
      const itemId = item.finding_id || item.id;
      const revision = item.revision;
      if (nonemptyString(itemId) && isPlainInt(revision)) {
        result[itemId as string] = Math.max(result[itemId as string] ?? 0, revision);
      }
    }
  }
  return result;
}

function findingRevisions(
  incremental: Json,
  assessments: Json[],
  currentIds: Set<string>,
): Record<string, number> {
  const previous = previousRevisions(incremental);
  const assessmentById = new Map<string, Json>(
    assessments.map((item) => [item.id as string, item]),
  );
  const revisions: Record<string, number> = {};
  for (const findingId of currentIds) {
    const priorRevision = previous[findingId] ?? 0;
    if (priorRevision === 0) {
      revisions[findingId] = 1;
      continue;
    }
    const status = (assessmentById.get(findingId) as Json).status;
    revisions[findingId] = priorRevision + (status === "changed" ? 1 : 0);
  }
  return revisions;
}

async function structuredPublicationPreview(
  evidence: Json,
  context: Json,
  root: string,
  findings: Json[],
  findingSpecs: Json[],
  assessments: Json[],
  threadDecisions: Json[],
  recommendedIssues: Json[],
  labelReview: Json,
  dryRun = false,
  locale = "en",
): Promise<[Json, Json[], Json[], Json[]]> {
  const bodyDirectory = `${root}/artifacts/review_plan/bodies`;
  const patchDirectory = `${root}/artifacts/review_plan/patches`;
  if (!dryRun) {
    await privateDirectory(bodyDirectory);
    await privateDirectory(patchDirectory);
  }
  const bodyFiles: Json[] = [];
  const actions: Json[] = [];
  const incremental = context.incremental as Json;
  const previous = previousRevisions(incremental);
  const previousAllowed = new Set(Object.keys(previous));
  const assessmentById = new Map<string, Json>(assessments.map((item) => [String(item.id), item]));
  const findingIds = new Set<string>(findings.map((item) => String(item.id)));
  const revisions = findingRevisions(incremental, assessments, findingIds);
  const discussionByRoot = new Map<string, Json>(
    ((context.discussions as Json[]) ?? [])
      .filter((item) => item.root_system === false)
      .map((item) => [String(item.root_note_id), item]),
  );
  const project = evidence.project as Json;
  const target = evidence.target as Json;
  const hostname = project.hostname as string;
  const endpoint = `projects/${project.id}/merge_requests/${target.iid}`;
  const repositoryUrl = String((evidence.object as Json).web_url).split("/-/merge_requests/", 1)[0];
  const publicationDependencies: Record<string, string> = {};

  const markedCommand = async (
    argv: string[],
    actionId: string,
    value: Json,
    stdinSha256: string | null = null,
  ): Promise<string> =>
    dryRun
      ? argv.map(shellQuote).join(" ")
      : makeCommand(
          root,
          evidence,
          context,
          actionId,
          argv,
          value,
          publicationDependencies,
          stdinSha256,
        );

  const enrichFix = (ownerKind: string, ownerId: string, item: Json): Json => {
    const patch = item.patch ?? null;
    if (item.fix_mode !== "patch") return { ...item, patch_path: null, patch_sha256: null };
    if (typeof patch !== "string") {
      throw new WorkflowError("patch fix content is unavailable");
    }
    const identity = sha256Text(`${ownerKind}:${ownerId}`).slice(0, 12);
    const patchDigest = sha256Text(patch);
    const destination = `${patchDirectory}/${identity}-${patchDigest}.patch`;
    const [patchPath, actualDigest] = dryRun
      ? [destination, patchDigest]
      : writeCompanion(destination, patch);
    return { ...item, patch_path: patchPath, patch_sha256: actualDigest };
  };

  const bodyWithFix = (body: string, fix: Json): string => {
    if (fix.fix_mode !== "patch") return body;
    return `${body.replace(/\s+$/, "")}\n\n${fix.patch_reason}\n\n${codeFence(renderPublicationPatchCommand(fix), "sh")}`;
  };

  const enrichedThreads = threadDecisions.map((item) => enrichFix("thread", String(item.id), item));

  const threadExpectation = (source: Json): Json => {
    const meaningful = ((source.notes as unknown[]) ?? []).filter(
      (note) => isDict(note) && note.system !== true && typeof note.body === "string",
    ) as Json[];
    if (meaningful.length === 0) {
      throw new WorkflowError("publication thread has no meaningful note");
    }
    const latest = meaningful[meaningful.length - 1] as Json;
    const position = source.root_position ?? null;
    return {
      discussion_id: source.root_resolvable === true ? source.id : null,
      root_note_id: source.root_note_id,
      resolvable: source.root_resolvable === true,
      resolved: source.root_resolved === true,
      last_note_id: latest.id,
      last_note_body_sha256: sha256Text(latest.body as string),
      path: isDict(position) ? position.new_path || position.old_path : null,
      line: isDict(position) ? position.new_line || position.old_line : null,
    };
  };

  const addBodyAction = async (
    publicationId: string,
    revision: number,
    kind: string,
    operation: string,
    rawBody: string,
    options: { mutation?: Json | null; thread?: Json | null } = {},
  ): Promise<void> => {
    const { mutation = null, thread = null } = options;
    const body = `${rawBody.replace(/\s+$/, "")}\n`;
    const identityDigest = sha256Text(publicationId).slice(0, 12);
    const contentDigestValue = sha256Text(body).slice(0, 12);
    const destination = `${bodyDirectory}/${identityDigest}-${contentDigestValue}.md`;
    const [bodyPath, bodyDigest] = dryRun
      ? [destination, sha256Text(body)]
      : writeCompanion(destination, body);
    bodyFiles.push({
      publication_id: publicationId,
      revision: revision,
      kind: kind,
      path: bodyPath,
      content: body,
    });
    const mutationValue = mutation ?? ({} as Json);
    const publicationOperation = ["resolve", "reopen"].includes(operation) ? "reply" : operation;
    const actionId = `${kind}:${publicationId}:r${revision}:${publicationOperation}`;
    let command: string;
    if (publicationOperation === "create_line") {
      const path = mutationValue.path as string;
      const line = mutationValue.line || mutationValue.old_line;
      const lineOption = (mutationValue.line ?? null) !== null ? "--line" : "--old-line";
      command = await markedCommand(
        [
          "glab",
          "mr",
          "note",
          "create",
          String(target.iid),
          "--repo",
          repositoryUrl,
          "--file",
          path,
          lineOption,
          String(line),
        ],
        actionId,
        { body_sha256: bodyDigest },
        bodyDigest,
      );
    } else if (publicationOperation === "create_general") {
      command = await markedCommand(
        [
          "glab",
          "api",
          "--hostname",
          hostname,
          "--method",
          "POST",
          `${endpoint}/discussions`,
          "--silent",
          "-F",
          `body=@${bodyPath}`,
        ],
        actionId,
        { body_sha256: bodyDigest },
      );
    } else if (operation === "create_issue") {
      const issueEndpoint = `projects/${project.id}/issues`;
      const issueTitle = (mutation as Json).title as string;
      command = await markedCommand(
        [
          "glab",
          "api",
          "--hostname",
          hostname,
          "--method",
          "POST",
          issueEndpoint,
          "-f",
          `title=${issueTitle}`,
          "--silent",
          "-F",
          `description=@${bodyPath}`,
        ],
        actionId,
        { body_sha256: bodyDigest, title: issueTitle },
      );
    } else {
      const discussionId = thread !== null ? (thread.discussion_id ?? null) : null;
      if (discussionId === null) {
        command = await markedCommand(
          [
            "glab",
            "api",
            "--hostname",
            hostname,
            "--method",
            "POST",
            `${endpoint}/discussions`,
            "-F",
            `body=@${bodyPath}`,
          ],
          actionId,
          { body_sha256: bodyDigest },
        );
      } else {
        const discussionEndpoint = `${endpoint}/discussions/${discussionId}`;
        command = await markedCommand(
          [
            "glab",
            "api",
            "--hostname",
            hostname,
            "--method",
            "POST",
            `${discussionEndpoint}/notes`,
            "--silent",
            "-F",
            `body=@${bodyPath}`,
          ],
          actionId,
          { body_sha256: bodyDigest },
        );
      }
    }
    actions.push({
      id: actionId,
      kind: kind,
      publication_id: publicationId,
      operation: publicationOperation,
      command: command,
      path: mutationValue.path || (thread !== null ? thread.path : null) || null,
      line:
        mutationValue.line ||
        mutationValue.old_line ||
        (thread !== null ? thread.line : null) ||
        null,
    });
    if (operation === "resolve" || operation === "reopen") {
      if (thread === null || (thread.discussion_id ?? null) === null) {
        throw new WorkflowError("thread state action requires a discussion");
      }
      const discussionEndpoint = `${endpoint}/discussions/${thread.discussion_id}`;
      const resolved = operation === "resolve" ? "true" : "false";
      actions.push({
        id: `${kind}:${publicationId}:r${revision}:${operation}`,
        kind: kind,
        publication_id: publicationId,
        operation: operation,
        command: await markedCommand(
          [
            "glab",
            "api",
            "--hostname",
            hostname,
            "--method",
            "PUT",
            discussionEndpoint,
            "--silent",
            "-F",
            `resolved=${resolved}`,
          ],
          `${kind}:${publicationId}:r${revision}:${operation}`,
          { resolved: resolved },
        ),
        path: mutationValue.path || (thread !== null ? thread.path : null) || null,
        line:
          mutationValue.line ||
          mutationValue.old_line ||
          (thread !== null ? thread.line : null) ||
          null,
      });
    }
  };

  const specById = new Map<string, Json>(
    findingSpecs.map((item) => [
      String(item.finding_id),
      enrichFix("finding", String(item.finding_id), item),
    ]),
  );
  const enrichedFindings: Json[] = [];
  for (const finding of findings) {
    const findingId = String(finding.id);
    const revision = revisions[findingId];
    const publicationSpec = specById.get(findingId);
    if (publicationSpec === undefined) {
      throw new WorkflowError("every actionable finding requires a concrete fix");
    }
    enrichedFindings.push({ ...publicationSpec, revision: revision });
    const assessment = assessmentById.get(findingId) ?? null;
    if (previousAllowed.has(findingId) && assessment?.publication_action === "no_publication")
      continue;
    if (context.role === "author" || publicationSpec.type === "existing_thread") continue;
    if (publicationSpec.suggestions !== undefined) {
      const parts = suggestionParts(publicationSpec);
      for (const [index, part] of parts.entries()) {
        await addBodyAction(
          `${findingId}@suggestion-${index + 1}`,
          revision,
          "finding",
          "create_line",
          suggestionBody(String(publicationSpec.body), part),
          { mutation: { path: part.path, line: part.line, old_line: null } },
        );
      }
      continue;
    }
    const operation = publicationSpec.type === "general" ? "create_general" : "create_line";
    await addBodyAction(
      findingId,
      revision,
      "finding",
      operation,
      bodyWithFix(publicationSpec.body as string, publicationSpec),
      {
        mutation: {
          path: publicationSpec.path,
          line: publicationSpec.line,
          old_line: publicationSpec.old_line,
        },
      },
    );
  }

  const previousIssueById = new Map<string, Json>(
    ((incremental.previous_recommended_issues as Json[]) ?? []).map((item) => [
      String(item.id),
      item,
    ]),
  );
  const enrichedIssues: Json[] = [];
  for (const assessment of assessments) {
    if (assessment.kind === "issue" && assessment.publication_action === "update_issue") {
      throw new WorkflowError(
        "a published recommended issue cannot be updated; record no_publication and explain the outcome in the assessment rationale",
      );
    }
  }
  for (const issueValue of recommendedIssues) {
    const issueId = String(issueValue.id);
    const prior = previousIssueById.get(issueId) ?? null;
    const assessment = assessmentById.get(issueId) ?? null;
    const previousRevision = Math.max(
      prior !== null ? (prior.revision as number) : 0,
      previous[issueId] ?? 0,
    );
    const revision =
      previousRevision === 0
        ? 1
        : previousRevision + (assessment !== null && assessment.status === "changed" ? 1 : 0);
    enrichedIssues.push({ ...issueValue, revision: revision });
    // Follow-ups are proposals only. Full task preparation is a separate skill.
  }

  for (const decision of enrichedThreads) {
    const operation = decision.outcome as string;
    if (operation === "no_publication" || operation === "local_fix") continue;
    const rootNoteId = String(decision.id);
    const publicationId = `thread-${rootNoteId}`;
    const revision = 1;
    const discussion = discussionByRoot.get(rootNoteId) ?? null;
    if (["resolve", "reopen"].includes(operation) && discussion === null) {
      throw new WorkflowError("a plain note cannot change thread state");
    }
    let response = decision.proposed_response as string;
    if (decision.suggestions !== undefined) {
      const position = discussion?.root_position as Json | undefined;
      const parts = suggestionParts(decision);
      const matching = parts.find(
        (part) =>
          position !== undefined &&
          position.head_sha === evidence.head_sha &&
          part.path === position.new_path &&
          part.line === position.new_line,
      );
      response = matching
        ? suggestionBody(response, matching)
        : String(
            decision.routing_response ??
              (locale === "ru"
                ? "Исправление предложено отдельным positioned thread на актуальных строках."
                : "The fix is proposed in a separate positioned thread on the current lines."),
          );
    }
    await addBodyAction(
      publicationId,
      revision,
      "thread",
      operation,
      bodyWithFix(response, decision),
      {
        mutation: {
          desired_resolved: operation === "resolve" ? true : operation === "reopen" ? false : null,
        },
        thread: discussion !== null ? threadExpectation(discussion) : null,
      },
    );
  }

  for (const decision of enrichedThreads) {
    if (decision.suggestions === undefined) continue;
    const parts = suggestionParts(decision);
    const position = discussionByRoot.get(String(decision.id))?.root_position as Json | undefined;
    for (const [index, part] of parts.entries()) {
      if (
        position !== undefined &&
        position.head_sha === evidence.head_sha &&
        part.path === position.new_path &&
        part.line === position.new_line
      )
        continue;
      await addBodyAction(
        `thread-${decision.id}@suggestion-${index + 1}`,
        1,
        "thread",
        "create_line",
        `${suggestionBody(String(decision.proposed_response), part)}\n\n${locale === "ru" ? "Исходный thread" : "Original thread"}: [${decision.id}](${decision.url})`,
        { mutation: { path: part.path, line: part.line, old_line: null } },
      );
    }
  }

  if ((labelReview.add as string[]).length > 0 || (labelReview.remove as string[]).length > 0) {
    const actionId = "labels:update";
    const labelArgv = ["glab", "mr", "update", String(target.iid), "--repo", repositoryUrl];
    if ((labelReview.add as string[]).length > 0) {
      labelArgv.push("--label", (labelReview.add as string[]).join(","));
    }
    if ((labelReview.remove as string[]).length > 0) {
      labelArgv.push("--unlabel", (labelReview.remove as string[]).join(","));
    }
    const labelCommand = await markedCommand(labelArgv, actionId, labelReview);
    actions.push({
      id: actionId,
      kind: "labels",
      publication_id: null,
      operation: "update_labels",
      command: labelCommand,
      path: null,
      line: null,
    });
  }

  const identities = actions.map((item) => item.id);
  if (identities.length !== new Set(identities).size) {
    throw new WorkflowError("publication action IDs must be unique");
  }
  const result: Json = {
    mr_state: (evidence.object as Json).state,
    warning: "manual publication; no command was executed",
    body_files: bodyFiles,
    actions: actions,
  };
  if (!reviewPublicationPreviewIsValid(result)) {
    throw new WorkflowError("structured review publication preview is invalid");
  }
  return [result, enrichedFindings, enrichedIssues, enrichedThreads];
}

export async function reviewMarkdown(
  evidence: Json,
  context: Json,
  decision: Json,
  content: Json,
  metadata: Json,
  publication: Json,
): Promise<string> {
  const assessment = metadata.assessment as Record<string, Json>;
  const presentation = content.presentation as Json;
  const previous = content.previous_finding_assessments as Json[];
  const findingPublications = new Map<string, Json>();
  for (const item of content.finding_publications as Json[]) {
    findingPublications.set(item.finding_id as string, item);
  }
  const recommendedIssues = content.recommended_issues as Json[];
  const bodies = new Map<string, Json>();
  for (const item of publication.body_files as Json[]) {
    bodies.set(item.publication_id as string, item);
  }
  const publicationActions = publication.actions as Json[];
  const blockingThreads = new Set(
    blockingThreadIds(content.thread_decisions as Json[], content.finding_publications as Json[]),
  );
  const actionsByPublication = new Map<string, Json[]>();
  for (const item of publicationActions) {
    const publicationId =
      typeof item.publication_id === "string"
        ? item.publication_id.split("@suggestion-")[0]
        : item.publication_id;
    if (publicationId !== null && publicationId !== undefined) {
      const existing = actionsByPublication.get(String(publicationId)) ?? [];
      existing.push(item);
      actionsByPublication.set(String(publicationId), existing);
    }
  }
  const lines: string[] = [
    `# ${presentation.title}`,
    "",
    ...((presentation.incremental_notice ?? null) !== null
      ? [presentation.incremental_notice as string, ""]
      : []),
    `- ${presentation.target_label}: ${pyStr((context.target as Json).url ?? null)}`,
    `- ${presentation.role_label}: ${presentation.role_value}`,
    `- ${presentation.verdict_label}: ${presentation.verdict_value}`,
    `- code-review: ${VERSION} · contract: ${REVIEW_CONTRACT_VERSION}`,
    `- ${presentation.publication_warning}`,
    "",
    content.summary as string,
    "",
    `**${content.locale === "ru" ? "Влияние на слияние" : "Merge impact"}:** ${(content.findings as Json[]).filter((finding) => finding.severity !== "low").length} ${content.locale === "ru" ? "блокирующих находок" : "blocking findings"}.`,
    `**${content.locale === "ru" ? "Технические блокеры" : "Technical blockers"}:**`,
    ...(content.findings as Json[])
      .filter((finding) => finding.severity !== "low")
      .map(
        (finding) =>
          `- ${finding.summary}: ${(presentation.severity_labels as Json)[String(finding.severity)]}`,
      ),
    ...(content.thread_decisions as Json[])
      .filter((thread) => blockingThreads.has(String(thread.id)))
      .map((thread) => `- [${thread.id}](${thread.url}): ${thread.rationale}`),
    ...((decision.ci_job_assessments ?? []) as Json[])
      .filter((job) => job.classification !== "process_gate")
      .map((job) => `- CI: ${job.rationale}`),
    `**${content.locale === "ru" ? "Процессные ограничения и решения владельца" : "Process gates and owner decisions"}:**`,
    ...((decision.owner_decision_reasons ?? []) as string[]).map((reason) => `- ${reason}`),
    ...((decision.ci_job_assessments ?? []) as Json[])
      .filter((job) => job.classification === "process_gate")
      .map((job) => `- CI: ${job.rationale}`),
    "",
    `**${presentation.architecture_heading}:** ${content.architecture_assessment}`,
    ...semverReportLines(content, content.locale as string),
    "",
    `## ${presentation.metadata_heading}`,
    "",
  ];
  for (const field of ["title", "description", "workflow_state", "overall"]) {
    const item = assessment[field];
    const labels = reviewMetadataLabels(content.locale as string);
    const text = item.recommendation || item.rationale;
    lines.push(`- **${labels[field]}:** ${text}`);
  }
  lines.push("");

  const panelSource = content.review_source as Json | undefined;
  const participants = isDict(panelSource?.participants)
    ? (panelSource.participants as Json)
    : null;
  const arbitrationSource =
    participants !== null && isDict(panelSource?.arbitration)
      ? (panelSource.arbitration as Json)
      : null;
  const panelReceipts =
    participants !== null && Array.isArray(panelSource?.critics)
      ? (panelSource.critics as Json[])
      : [];
  const participantForReceipt = (receipt: Json): string | null => {
    if (participants === null) return null;
    const critic = ((participants.critics as Json[]) ?? []).find(
      (item) =>
        isDict(item.receipt) &&
        String(item.receipt.run_id) === String(receipt.run_id) &&
        String(item.receipt.session_id) === String(receipt.session_id),
    );
    return critic === undefined ? null : String(critic.name);
  };
  const raisedBy = (findingId: string): string | null => {
    const receipt = panelReceipts.find((item) =>
      (((item.findings as Json[]) ?? []) as Json[]).some(
        (finding) => String(finding.id) === findingId,
      ),
    );
    if (receipt === undefined) return null;
    const name = participantForReceipt(receipt);
    return name !== null
      ? `${name} (${String(receipt.run_id)}/${String(receipt.session_id)})`
      : `${String(receipt.run_id)}/${String(receipt.session_id)}`;
  };
  if (participants !== null) {
    const ru = content.locale === "ru";
    lines.push(`## ${ru ? "Состав ревью" : "Review panel"}`, "");
    for (const critic of participants.critics as Json[]) {
      const details = [
        ...(critic.profile !== undefined ? [`profile: ${String(critic.profile)}`] : []),
        ...(critic.provider !== undefined ? [`provider: ${String(critic.provider)}`] : []),
        ...(critic.model !== undefined ? [`model: ${String(critic.model)}`] : []),
      ].join(" · ");
      lines.push(
        `- ${ru ? "критик" : "critic"} \`${String(critic.name)}\`${details === "" ? "" : ` — ${details}`}`,
      );
    }
    const arb = participants.arbitrator as Json;
    const arbDetails = [
      ...(arb.profile !== undefined ? [`profile: ${String(arb.profile)}`] : []),
      ...(arb.provider !== undefined ? [`provider: ${String(arb.provider)}`] : []),
      ...(arb.model !== undefined ? [`model: ${String(arb.model)}`] : []),
    ].join(" · ");
    lines.push(
      `- ${ru ? "арбитр" : "arbitrator"} \`${String(arb.name)}\`${arbDetails === "" ? "" : ` — ${arbDetails}`}`,
      "",
      ru
        ? "Состав и конфигурации участников приведены только в этом приватном ранбуке и никогда не попадают в публикуемые тексты GitLab."
        : "The panel composition and configurations live only in this private runbook and never enter published GitLab texts.",
      "",
    );
  }

  const labelReview = content.label_review as Json;
  const shownActions = new Set<string>();
  lines.push(`## ${presentation.labels_heading}`, "");
  for (const field of ["add", "remove"]) {
    const values = labelReview[field] as string[];
    const rendered =
      values.length > 0 ? values.map((value) => `\`${value}\``).join(", ") : presentation.no_items;
    lines.push(`- ${reviewActionLabels(content.locale as string)[field]}: ${rendered}`);
  }
  const labelAction = publicationActions.find((item) => item.kind === "labels") ?? null;
  if (labelAction !== null) {
    shownActions.add(labelAction.id as string);
    lines.push("", "```shell", labelAction.command as string, "```");
  }
  lines.push("");

  lines.push(`## ${presentation.previous_findings_heading}`, "");
  if (previous.length === 0) {
    lines.push(presentation.no_items as string, "");
  } else {
    const ru = content.locale === "ru";
    const headers = ru ? ["Находка", "Результат", "Действие"] : ["Finding", "Result", "Action"];
    lines.push(`| ${headers.join(" | ")} |`, `|${headers.map(() => "---").join("|")}|`);
    for (const item of previous) {
      const record = (content.findings as Json[]).find((finding) => finding.id === item.id);
      const prior = ((context.incremental as Json)?.previous_findings as Json[] | undefined)?.find(
        (finding) => finding.id === item.id,
      );
      const statuses: Record<string, string> = ru
        ? {
            active: "Актуально",
            changed: "Уточнено",
            fixed: "Исправлено",
            withdrawn: "Снято",
            unverified: "Не проверено",
          }
        : {
            active: "Active",
            changed: "Updated",
            fixed: "Fixed",
            withdrawn: "Withdrawn",
            unverified: "Unverified",
          };
      const name = String(record?.summary ?? prior?.summary ?? item.current_status);
      const actions: Record<string, string> = ru
        ? {
            no_publication: "Нет",
            reply: "Ответ",
            resolve: "Закрыть",
            reopen: "Открыть",
            update_issue: "Обновить задачу",
          }
        : {
            no_publication: "None",
            reply: "Reply",
            resolve: "Resolve",
            reopen: "Reopen",
            update_issue: "Update issue",
          };
      lines.push(
        `| ${[
          name.length > 80 ? `${name.slice(0, 77)}...` : name,
          statuses[String(item.status)],
          actions[String(item.publication_action)],
        ]
          .map((value) => markdownCell(value))
          .join(" | ")} |`,
      );
    }
    lines.push("");
    for (const item of previous.filter((item) => item.publication_action === "no_publication"))
      lines.push(`- ${item.current_status}: ${item.rationale}`);
    if (previous.some((item) => item.publication_action === "no_publication")) lines.push("");
  }

  const addFix = async (fix: Json): Promise<void> => {
    if (fix.fix_mode === "suggestion") return;
    if (fix.fix_mode !== "patch") return;
    lines.push(
      String(fix.patch_reason),
      "",
      "```sh",
      renderPatchCheck(context, fix),
      "```",
      "",
      "```sh",
      await renderPatchCommand(evidence, context, fix),
      "```",
      "",
    );
  };

  const addAction = (action: Json): void => {
    if (shownActions.has(action.id as string)) return;
    const publicationId = action.publication_id ?? null;
    const body = publicationId !== null ? (bodies.get(String(publicationId)) ?? null) : null;
    shownActions.add(action.id as string);
    if (body !== null && !["resolve", "reopen"].includes(action.operation as string)) {
      lines.push(markedPreview(`PUBLICATION ${publicationId} BODY`, body.content as string), "");
    }
    const label = reviewActionLabels(content.locale as string)[
      ["resolve", "reopen"].includes(action.operation as string)
        ? (action.operation as string)
        : "reply"
    ];
    const stateAction = (actionsByPublication.get(String(publicationId)) ?? []).find(
      (candidate) =>
        ["resolve", "reopen"].includes(String(candidate.operation)) &&
        !shownActions.has(String(candidate.id)),
    );
    const thread = (content.thread_decisions as Json[]).find(
      (thread) => `thread-${thread.id}` === publicationId,
    );
    const guard = operationIsHeadGuarded(String(action.operation))
      ? `${headGuard(evidence, String(content.locale))}\n`
      : "";
    let command = `${guard}# ${label}\n${action.command}`;
    if (stateAction && !["resolve", "reopen"].includes(String(action.operation))) {
      shownActions.add(String(stateAction.id));
      command += ` &&\n# ${reviewActionLabels(String(content.locale))[String(stateAction.operation)]}\n${stateAction.command}`;
    } else if (
      thread &&
      thread.state === "plain" &&
      ["fixed", "false_positive", "duplicate", "not_related"].includes(String(thread.assessment))
    ) {
      const project = evidence.project as Json;
      const endpoint = `projects/${project.id}/merge_requests/${(evidence.target as Json).iid}/discussions`;
      command = `${guard}# ${label}\nresponse=$(${action.command}) &&\n# ${content.locale === "ru" ? "Проверить разрешимость нового discussion" : "Check the returned discussion's resolvability"}\nif printf '%s' "$response" | jq -e '.notes | any(.resolvable == true)' >/dev/null; then\n  # ${content.locale === "ru" ? "Получить реальный discussion ID" : "Read the actual discussion ID"}\n  discussion_id=$(printf '%s' "$response" | jq -er '.id | select(type == "string" and test("^[A-Za-z0-9_-]+$"))') &&\n  # ${content.locale === "ru" ? "Закрыть только завершённое обсуждение после ответа" : "Resolve only a completed discussion after its reply"}\n  glab api --hostname ${shellQuote(String(project.hostname))} --method PUT "${endpoint}/$discussion_id" --silent -F resolved=true\nfi`;
    }
    lines.push(label, "", "```shell", command, "```");
    lines.push("");
  };

  const addPublicationAction = (publicationId: string): void => {
    for (const action of actionsByPublication.get(publicationId) ?? []) addAction(action);
  };

  const threadDecisions = content.thread_decisions as Json[];
  const impact = (severity: unknown): string =>
    severity === "low"
      ? content.locale === "ru"
        ? "Не блокирует слияние"
        : "Does not block merge"
      : content.locale === "ru"
        ? "Блокирует слияние"
        : "Blocks merge";
  const assessments: Record<string, string> =
    content.locale === "ru"
      ? {
          fixed: "Исправлено",
          false_positive: "Ложное срабатывание",
          duplicate: "Дубликат",
          not_related: "Вне изменений",
          question: "Вопрос",
          neutral: "Не требует действий",
        }
      : {
          fixed: "Fixed",
          false_positive: "False positive",
          duplicate: "Duplicate",
          not_related: "Outside the change",
          question: "Question",
          neutral: "No action needed",
        };
  const threadResult = (item: Json): string => {
    const linked = (content.findings as Json[]).find(
      (finding) => findingPublications.get(String(finding.id))?.thread_id === item.id,
    );
    const severity = linked?.severity ?? item.severity ?? "medium";
    return item.assessment === "accepted"
      ? `${(presentation.severity_labels as Json)[String(severity)]} · ${impact(severity)}`
      : `${content.locale === "ru" ? "Результат проверки" : "Check result"}: ${assessments[String(item.assessment)]}`;
  };

  const addThreadSection = (heading: string, items: Json[]): void => {
    lines.push(`## ${heading}`, "");
    if (items.length === 0) {
      lines.push(presentation.no_items as string, "");
      return;
    }
    for (const item of items) {
      lines.push(
        `### [${item.id}](${item.url})`,
        "",
        threadResult(item),
        "",
        item.rationale as string,
        "",
      );
      addPublicationAction(`thread-${item.id}`);
    }
  };

  addThreadSection(
    presentation.open_threads_heading as string,
    threadDecisions.filter(
      (item) =>
        item.state !== "resolved" &&
        !["no_publication", "local_fix"].includes(item.outcome as string),
    ),
  );
  addThreadSection(
    presentation.closed_threads_heading as string,
    threadDecisions.filter(
      (item) =>
        item.state === "resolved" &&
        !["no_publication", "local_fix"].includes(item.outcome as string),
    ),
  );

  const findings = content.findings as Json[];
  const localThreads = threadDecisions.filter((item) => item.outcome === "local_fix");
  lines.push(`## ${presentation.local_fixes_heading}`, "");
  if (localThreads.length === 0 && (context.role !== "author" || findings.length === 0)) {
    lines.push(presentation.no_items as string, "");
  }
  for (const item of localThreads) {
    lines.push(
      `### [${item.id}](${item.url})`,
      "",
      threadResult(item),
      "",
      item.rationale as string,
      "",
      item.proposed_response as string,
      "",
    );
    await addFix(item);
  }
  if (context.role === "author") {
    for (const finding of findings) {
      const publicationSpec = findingPublications.get(finding.id as string) as Json;
      lines.push(
        `### ${finding.summary}`,
        "",
        `\`${finding.id}\` · ${(presentation.severity_labels as Json)[finding.severity as string]} · ${finding.severity === "low" ? (content.locale === "ru" ? "Не блокирует слияние" : "Does not block merge") : content.locale === "ru" ? "Блокирует слияние" : "Blocks merge"}`,
        "",
        finding.risk as string,
        "",
        finding.minimum_fix as string,
        "",
      );
      await addFix(publicationSpec);
    }
  }

  lines.push(`## ${presentation.new_findings_heading}`, "");
  const previousIds = new Set(previous.map((item) => String(item.id)));
  const reviewerFindings =
    context.role === "reviewer" ? findings.filter((item) => !previousIds.has(String(item.id))) : [];
  if (reviewerFindings.length === 0) {
    lines.push(presentation.no_items as string, "");
  }
  for (const finding of reviewerFindings) {
    const ru = content.locale === "ru";
    const author = raisedBy(String(finding.id));
    const mergedFrom =
      arbitrationSource !== null
        ? ((arbitrationSource.dispositions as Json[]) ?? [])
            .filter(
              (item) =>
                item.duplicate_of !== undefined && String(item.duplicate_of) === String(finding.id),
            )
            .map((item) => String(item.id))
        : [];
    lines.push(
      `### ${finding.summary}`,
      "",
      `\`${finding.id}\` · ${(presentation.severity_labels as Json)[finding.severity as string]} · ${finding.severity === "low" ? (ru ? "Не блокирует слияние" : "Does not block merge") : ru ? "Блокирует слияние" : "Blocks merge"}`,
      ...(author !== null ? [`${ru ? "Автор" : "Raised by"}: ${author}`] : []),
      ...(mergedFrom.length > 0
        ? [
            `${ru ? "Объединено арбитром из" : "Merged by the arbitrator from"}: ${mergedFrom.map((id) => `\`${id}\``).join(", ")}`,
          ]
        : []),
      "",
      finding.risk as string,
      "",
      finding.consequence as string,
      "",
      `**${presentation.evidence_label}**`,
      "",
      ...(finding.evidence as string[]).map((value) => `- ${value}`),
      "",
      `**${presentation.relation_label}**`,
      "",
      finding.relation_to_change as string,
      "",
      finding.minimum_fix as string,
      "",
    );
    if (findingPublications.has(finding.id as string)) {
      const spec = findingPublications.get(String(finding.id))!;
      if (spec.type === "existing_thread") {
        const thread = (content.thread_decisions as Json[]).find(
          (thread) => thread.id === spec.thread_id,
        )!;
        lines.push(
          `[${ru ? "Фикс в исходном thread" : "Fix in the existing thread"}](${thread.url}): ${spec.body}`,
          "",
        );
      }
      addPublicationAction(String(finding.id));
    }
  }

  // Every detected candidate stays visible with the arbitrator's conclusion,
  // including refuted and duplicate ones; a disagreement never hides a finding.
  if (participants !== null) {
    const ru = content.locale === "ru";
    lines.push(`## ${ru ? "Вердикты арбитра" : "Arbitration verdicts"}`, "");
    const verdicts = new Map(
      (((arbitrationSource?.dispositions as Json[]) ?? []) as Json[]).map((item) => [
        String(item.id),
        item,
      ]),
    );
    const verdictText = (findingId: string): string => {
      const disposition = verdicts.get(findingId);
      if (disposition === undefined) return ru ? "нет вердикта" : "no verdict";
      const override = disposition.severity_override as Json | undefined;
      if (disposition.decision === "accept")
        return override === undefined
          ? ru
            ? "принято"
            : "accepted"
          : ru
            ? `принято с изменением критичности на ${(presentation.severity_labels as Json)[String(override.severity)]} (было ${(presentation.severity_labels as Json)[String(override.original_severity)]})`
            : `accepted with severity override to ${(presentation.severity_labels as Json)[String(override.severity)]} (was ${(presentation.severity_labels as Json)[String(override.original_severity)]})`;
      if (disposition.duplicate_of !== undefined)
        return `${ru ? "дубликат находки" : "duplicate of"} \`${String(disposition.duplicate_of)}\``;
      return ru ? "опровергнуто" : "refuted";
    };
    const candidates: Array<{ id: string; summary: string; author: string | null }> = [];
    for (const receipt of panelReceipts)
      for (const item of ((receipt.findings as Json[]) ?? []) as Json[]) {
        const author = raisedBy(String(item.id));
        candidates.push({
          id: String(item.id),
          summary: String(item.summary ?? item.id),
          author:
            author === null ? `${String(receipt.run_id)}/${String(receipt.session_id)}` : author,
        });
      }
    const mergedFindings = ((arbitrationSource?.findings as Json[]) ?? []) as Json[];
    if (candidates.length === 0 && mergedFindings.length === 0) {
      lines.push(presentation.no_items as string, "");
    }
    for (const candidate of candidates) {
      const disposition = verdicts.get(candidate.id);
      lines.push(
        `- \`${candidate.id}\` · ${candidate.author}: **${verdictText(candidate.id)}** — ${candidate.summary}`,
        `  ${String(disposition?.reason ?? (ru ? "основание не приведено" : "no reason recorded"))}`,
      );
    }
    for (const finding of mergedFindings) {
      lines.push(
        `- \`${String(finding.id)}\` · ${ru ? "объединённая находка арбитра" : "arbitrator merged finding"}: **${ru ? "принято" : "accepted"}** — ${String(finding.summary)}`,
      );
    }
    if (candidates.length > 0 || mergedFindings.length > 0) lines.push("");
  }

  const existingFindings =
    context.role === "reviewer" ? findings.filter((item) => previousIds.has(String(item.id))) : [];
  if (existingFindings.length > 0) {
    lines.push(
      `## ${content.locale === "ru" ? "Действия по прежним находкам" : "Previous finding actions"}`,
      "",
    );
    for (const finding of existingFindings) {
      lines.push(
        `### ${finding.summary}`,
        "",
        `${(presentation.severity_labels as Json)[String(finding.severity)]} · ${impact(finding.severity)}`,
        "",
        finding.minimum_fix as string,
        "",
      );
      addPublicationAction(String(finding.id));
    }
  }
  for (const item of previous) {
    if (
      !existingFindings.some((finding) => finding.id === item.id) &&
      item.publication_action !== "no_publication"
    ) {
      lines.push(`### ${item.current_status}`, "", item.rationale as string, "");
      addPublicationAction(String(item.id));
    }
  }

  lines.push(`## ${presentation.recommended_issues_heading}`, "");
  if (recommendedIssues.length === 0) {
    lines.push(presentation.no_items as string, "");
  }
  for (const issue of recommendedIssues) {
    lines.push(
      `### ${issue.title}`,
      "",
      `\`${issue.id}\``,
      "",
      issue.problem as string,
      "",
      issue.risk as string,
      "",
      String(issue.importance ?? ""),
      ...(issue.existing_task ? [String(issue.existing_task), ""] : []),
      `**${presentation.evidence_label}**`,
      "",
      ...(issue.evidence as string[]).map((value) => `- ${value}`),
      "",
      issue.reason_out_of_scope as string,
      "",
      issue.minimum_fix as string,
      "",
    );
    addPublicationAction(String(issue.id));
  }

  lines.push(`## ${presentation.checked_heading}`, "");
  const withoutPublication = (content.thread_decisions as Json[]).filter(
    (item) => item.outcome === "no_publication",
  );
  if (withoutPublication.length === 0) {
    lines.push(presentation.no_items as string, "");
  } else {
    lines.push(
      ...withoutPublication.map(
        (item) => `- [${item.id}](${item.url}): ${threadResult(item)}. ${item.rationale}`,
      ),
    );
    lines.push("");
  }

  lines.push(
    `## ${presentation.checks_heading}`,
    "",
    ...[...new Set(content.checks as string[])].map((value) => `- ${value}`),
    "",
  );
  const source = content.review_source as Json | undefined;
  const ci =
    source?.ci_snapshot !== undefined
      ? artifactPayload(String(source.ci_snapshot), "evidence_snapshot")[1]
      : evidence;
  const pipeline = selectExactPipeline(ci.pipelines as Json, ci.head_sha as string);
  if (pipeline !== null)
    lines.push(
      `${content.locale === "ru" ? "CI использованного снимка" : "CI in the assessed snapshot"}: ${pipeline.status}.`,
      "",
    );
  for (const action of publicationActions) {
    if (shownActions.has(action.id as string)) continue;
    if (action.kind !== "labels") {
      lines.push("");
      addAction(action);
    }
  }
  const noItems = String(presentation.no_items).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return `${lines.join("\n")}\n`.replace(new RegExp(`^## [^\\n]+\\n\\n${noItems}\\n\\n`, "gm"), "");
}

export async function publishReviewState(
  root: string,
  markdown: string,
  planPath: string,
  planDigest: string,
  target: Json,
  expectedIncrementalBaselineStateDigest: string | null,
  expectedProgress: Json,
  bindings: Json = {},
): Promise<[string, string]> {
  const markdownPath = `${root}/runbook.md`;
  const baselinePath = `${root}/${BASELINE_NAME}`;
  const currentProgressPath = progressPath(root);
  const markdownDigest = sha256Text(markdown);
  const release = await reviewStateLock(root);
  try {
    if (isSymlink(markdownPath) || isSymlink(baselinePath) || isSymlink(currentProgressPath)) {
      throw new WorkflowError("review state paths must not be symbolic links");
    }
    const currentProgress = validateProgress(
      readJson(currentProgressPath, "code-review progress"),
      root,
    );
    if (
      !Object.keys(expectedProgress).every((key) => key in currentProgress) ||
      Object.entries(expectedProgress).some(([key, value]) => currentProgress[key] !== value)
    ) {
      throw new WorkflowError("code-review progress changed before publication");
    }
    const previousMarkdown = pathExists(markdownPath) ? readFileSync(markdownPath) : null;
    const previousBaseline = pathExists(baselinePath) ? readFileSync(baselinePath) : null;
    const previousProgress = readFileSync(currentProgressPath);
    const actualIncrementalBaselineStateDigest =
      previousBaseline !== null ? sha256Bytes(previousBaseline) : null;
    if (actualIncrementalBaselineStateDigest !== expectedIncrementalBaselineStateDigest) {
      throw new WorkflowError("code-review baseline changed before publication");
    }
    const nextProgress: Json = {
      ...currentProgress,
      ...bindings,
      stage: "plan_ready",
      plan_path: planPath,
      plan_digest: planDigest,
      updated_at: new Date().toISOString(),
    };
    validateProgress(nextProgress, root);
    try {
      replacePrivateBytes(
        markdownPath,
        await versionedMarkdown(markdownPath, Buffer.from(markdown, "utf8")),
      );
      writeJson(currentProgressPath, nextProgress);
      writeJson(baselinePath, {
        contract_version: INCREMENTAL_CONTRACT_VERSION,
        target: target,
        plan_path: planPath,
        plan_digest: planDigest,
        markdown_path: markdownPath,
        markdown_digest: markdownDigest,
        updated_at: new Date().toISOString(),
      });
      fsyncDirectory(root);
    } catch (error) {
      if (!(error instanceof WorkflowError) && !isErrnoException(error)) throw error;
      if (previousMarkdown === null) {
        rmSync(markdownPath, { force: true });
      } else {
        replacePrivateBytes(markdownPath, previousMarkdown);
      }
      if (previousBaseline === null) {
        rmSync(baselinePath, { force: true });
      } else {
        replacePrivateBytes(baselinePath, previousBaseline);
      }
      replacePrivateBytes(currentProgressPath, previousProgress);
      fsyncDirectory(root);
      throw error;
    }
  } finally {
    release();
  }
  return [resolvePath(markdownPath), markdownDigest];
}

export function rejectVisibleRawRefs(
  markdown: string,
  evidence: Json,
  context: Json | null = null,
): void {
  const refs: string[] = [];
  for (const value of [
    evidence.base_sha ?? null,
    evidence.start_sha ?? null,
    evidence.head_sha ?? null,
  ]) {
    if (typeof value === "string" && value.length >= 12) refs.push(value);
  }
  if (context !== null) {
    const release = context.release_evidence;
    if (isDict(release)) {
      const candidates: unknown[] = [release.target_sha];
      for (const key of ["releases", "tags"]) {
        for (const item of (release[key] as Json).items as unknown[]) {
          if (isDict(item) && isDict(item.commit)) candidates.push(item.commit.id);
        }
      }
      refs.push(
        ...candidates.filter(
          (value): value is string => typeof value === "string" && value.length >= 12,
        ),
      );
    }
    const incremental = context.incremental;
    const delta = isDict(incremental) ? (incremental.incremental_delta ?? null) : null;
    if (isDict(delta)) {
      refs.push(
        ...[delta.from_head ?? null, delta.to_head ?? null].filter(
          (value): value is string =>
            typeof value === "string" && value.length >= 12 && !refs.includes(value),
        ),
      );
    }
  }
  for (const line of markdown.split("\n")) {
    if (
      line.startsWith("glab api ") &&
      (line.includes("position[") || line.includes("-F 'position={"))
    )
      continue;
    const visible = line.replace(/\]\(https?:\/\/[^)]*\)/g, "](...)").toLowerCase();
    for (const value of refs) {
      const normalized = value.toLowerCase();
      if (
        visible.includes(normalized) ||
        Array.from(
          { length: Math.min(12, normalized.length) - 7 + 1 },
          (_, offset) => 7 + offset,
        ).some((length) => {
          const prefix = normalized.slice(0, length);
          return new RegExp(
            `(?<![0-9a-f])${prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![0-9a-f])`,
          ).test(visible);
        })
      ) {
        throw new WorkflowError("user-facing review Markdown exposes a raw commit SHA");
      }
    }
  }
}

export function buildFindingLedger(
  incremental: Json,
  assessments: Json[],
  findings: Json[],
  publications: Json[],
  issues: Json[],
  publicationPreview: Json,
): Json[] {
  const previous = new Map<string, Json>();
  for (const item of (incremental.previous_finding_ledger as Json[]) ?? []) {
    previous.set(String(item.id), item);
  }
  const assessmentById = new Map<string, Json>(assessments.map((item) => [String(item.id), item]));
  const findingById = new Map<string, Json>(findings.map((item) => [String(item.id), item]));
  const publicationById = new Map<string, Json>(
    publications.map((item) => [String(item.finding_id), item]),
  );
  const issueById = new Map<string, Json>(issues.map((item) => [String(item.id), item]));
  const actionRevisions: Record<string, number> = {};
  for (const body of (publicationPreview.body_files as Json[]) ?? []) {
    const itemId = String(body.publication_id);
    const revision = body.revision as number;
    actionRevisions[itemId] = Math.max(actionRevisions[itemId] ?? 0, revision);
  }
  const ledger: Json[] = [];
  for (const [itemId, old] of previous.entries()) {
    const assessment = assessmentById.get(itemId) as Json;
    let record: Json;
    let revision: number;
    if (old.kind === "finding" && findingById.has(itemId)) {
      record = {
        finding: findingById.get(itemId),
        publication: publicationById.get(itemId),
      };
      revision = (publicationById.get(itemId) as Json).revision as number;
    } else if (old.kind === "issue" && issueById.has(itemId)) {
      record = { issue: issueById.get(itemId) };
      revision = (issueById.get(itemId) as Json).revision as number;
    } else {
      record = { ...((old.record as Json) ?? {}) };
      revision = old.revision as number;
      if (old.kind === "finding" && assessment.publication_action !== "no_publication") {
        const publication = { ...((record.publication as Json) ?? {}) };
        publication.body = assessment.publication_body;
        publication.revision = Math.max(revision, actionRevisions[itemId] ?? revision);
        record.publication = publication;
      }
    }
    ledger.push({
      id: itemId,
      kind: old.kind,
      status: assessment.status,
      revision: Math.max(revision, actionRevisions[itemId] ?? 0),
      record: record,
    });
  }
  for (const [itemId, finding] of findingById.entries()) {
    if (!previous.has(itemId)) {
      const publication = publicationById.get(itemId) as Json;
      ledger.push({
        id: itemId,
        kind: "finding",
        status: "active",
        revision: publication.revision,
        record: { finding: finding, publication: publication },
      });
    }
  }
  for (const [itemId, issue] of issueById.entries()) {
    if (!previous.has(itemId)) {
      ledger.push({
        id: itemId,
        kind: "issue",
        status: "active",
        revision: issue.revision,
        record: { issue: issue },
      });
    }
  }
  return ledger.sort((left, right) => compareCodePoints(left.id as string, right.id as string));
}

function buildRejectedCandidateLedger(
  incremental: Json,
  rejectedCandidates: Json[],
  assessments: Json[],
  acceptedFindingIds: Set<string>,
): Json[] {
  const previous = new Map<string, Json>();
  for (const item of (incremental.previous_rejected_candidates as Json[]) ?? []) {
    previous.set(String(item.id), item);
  }
  const current = new Map<string, Json>(rejectedCandidates.map((item) => [String(item.id), item]));
  const assessmentById = new Map<string, Json>(assessments.map((item) => [String(item.id), item]));
  const ledger = new Map<string, Json>();
  for (const [itemId, item] of previous.entries()) {
    const assessment = assessmentById.get(itemId) ?? null;
    if (assessment === null) {
      ledger.set(itemId, item);
    } else if (assessment.decision === "promoted") {
      if (!acceptedFindingIds.has(itemId)) {
        throw new WorkflowError("a promoted rejected candidate must become an accepted finding");
      }
    } else if (!current.has(itemId)) {
      throw new WorkflowError("a still-rejected affected candidate must be recorded again");
    } else {
      ledger.set(itemId, current.get(itemId) as Json);
    }
  }
  for (const [itemId, item] of current.entries()) {
    if (!previous.has(itemId)) ledger.set(itemId, item);
  }
  return [...ledger.values()].sort((left, right) =>
    compareCodePoints(left.id as string, right.id as string),
  );
}

export async function scaffoldReview(
  evidenceValue: string,
  contextValue: string,
  decisionValue: string,
  contentValue: string,
  draft?: {
    decision: Json;
    content: Json;
    dryRun: boolean;
    freshnessChecked: boolean;
    progress?: Json;
    bindings?: Json;
    source?: Json;
    baselineStateDigest?: string;
  },
): Promise<Json> {
  const [evidencePath, evidence, root, evidenceDigest] = await evidenceContext(evidenceValue);
  const [, context, contextDigest] = await validateContextBinding(contextValue, evidencePath);
  const [, decision, decisionDigest] = draft?.dryRun
    ? [decisionValue, draft.decision, "0".repeat(64)]
    : contentAddressedArtifact(decisionValue, root, "review_decision");
  if (decision.evidence_digest !== evidenceDigest || decision.context_digest !== contextDigest) {
    throw new WorkflowError("review decision does not bind evidence and context");
  }
  const target = evidence.target;
  if (!isDict(target)) {
    throw new WorkflowError("review evidence target is unavailable");
  }
  if (!draft?.freshnessChecked) {
    const currentEvidence = await collect(target, "code-review", { persist: false });
    const currentContext = await refreshContext(context, evidencePath);
    if (
      currentEvidence.retrieval_complete !== true ||
      !jsonEqual(fingerprint(evidence), fingerprint(currentEvidence)) ||
      context.complete !== true ||
      currentContext.complete !== true ||
      !contextsMatch(context, currentContext)
    ) {
      throw new WorkflowError("review evidence or context is stale before plan creation");
    }
  }
  const content = exactKeys(
    draft?.content ?? readJson(contentValue, "review plan content"),
    new Set([
      "locale",
      "chat_assessment",
      "summary",
      "architecture_assessment",
      "semver_impact",
      "semver_rationale",
      "semver_assessment",
      "mr_metadata_assessment",
      "label_assessments",
      "checks",
      "findings",
      "finding_publications",
      "previous_finding_assessments",
      "issue_templates",
      "recommended_issues",
      "rejected_candidates",
      "rejected_candidate_assessments",
      "thread_decisions",
    ]),
    "review plan content",
  );
  if (
    !SUPPORTED_LOCALES.has(content.locale as string) ||
    !nonemptyString(content.summary) ||
    !nonemptyString(content.architecture_assessment) ||
    !["major", "minor", "patch", "none", "not_applicable"].includes(
      content.semver_impact as string,
    ) ||
    !nonemptyString(content.semver_rationale) ||
    !Array.isArray(content.checks) ||
    !(content.checks as unknown[]).every((value) => nonemptyString(value)) ||
    !detailedFindingsAreValid(content.findings) ||
    !threadDecisionsAreValid(content.thread_decisions)
  ) {
    throw new WorkflowError("review plan content is invalid");
  }
  if (!jsonEqual(content.issue_templates, context.issue_templates)) {
    throw new WorkflowError("review content issue templates do not match review context");
  }
  semverValidate(content.semver_assessment, evidence, context);
  const progress = loadProgress(root);
  if (progress !== null && content.locale !== (progress.locale ?? null)) {
    throw new WorkflowError("review content locale does not match selected progress locale");
  }
  const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const findings = content.findings as Json[];
  const findingIds = findings.map((finding) => finding.id);
  if (
    findingIds.length !== new Set(findingIds).size ||
    findingIds.some(
      (findingId) =>
        String(findingId).startsWith("thread-") ||
        !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(String(findingId)),
    )
  ) {
    throw new WorkflowError("review finding IDs must be unique");
  }
  if (duplicateDetailedFindingIds(findings).length > 0) {
    throw new WorkflowError("review findings must be structurally distinct");
  }
  const orderedFindings = [...findings].sort(
    (left, right) =>
      severityOrder[left.severity as string] - severityOrder[right.severity as string],
  );
  if (!jsonEqual(findings, orderedFindings)) {
    throw new WorkflowError("review findings must be ordered by severity");
  }
  const acceptedFindings = (decision.accepted_findings ?? decision.findings ?? []) as Json[];
  if (!jsonEqual(acceptedFindings, findings)) {
    throw new WorkflowError("review plan findings do not match the review decision");
  }
  content.thread_decisions = (content.thread_decisions as Json[]).map((thread) => {
    const finding = findings.find((finding) =>
      (content.finding_publications as Json[]).some(
        (fix) =>
          fix.type === "existing_thread" &&
          fix.thread_id === thread.id &&
          fix.finding_id === finding.id,
      ),
    );
    return finding ? { ...thread, severity: finding.severity } : thread;
  });
  const incremental = context.incremental as Json;
  const incrementalMode = String(incremental.mode);
  if ((incrementalMode === "incremental") !== (decision.mode === "incremental")) {
    throw new WorkflowError("review decision mode does not match incremental context");
  }
  const chatAssessment = validateChatAssessment(content.chat_assessment);
  const presentation = validatePresentation(
    localizedPresentation(
      content.locale as string,
      context.role as string,
      decision.verdict as string,
      incrementalMode,
    ),
    incrementalMode,
  );
  const labelReview = validateLabelAssessments(
    evidence,
    content.label_assessments,
    content.semver_impact as string,
  );
  const previousFindings = incremental.previous_findings as Json[];
  const previousIssues = incremental.previous_recommended_issues as Json[];
  const previousAssessments = validatePreviousAssessments(
    content.previous_finding_assessments,
    previousFindings,
    previousIssues,
  );
  const reconsideredRejected = incremental.reconsidered_rejected_candidates as Json[];
  const rejectedCandidateAssessments = validateRejectedCandidateAssessments(
    content.rejected_candidate_assessments,
    reconsideredRejected,
  );
  const rejectedCandidates = validateRejectedCandidates(content.rejected_candidates, decision);
  const recommendedIssues = validateRecommendedIssues(
    content.recommended_issues,
    context.issue_templates as Json[],
  );
  const issueIds = recommendedIssues.map((item) => String(item.id));
  if (
    issueIds.length !== new Set(issueIds).size ||
    issueIds.some((issueId) => findingIds.includes(issueId)) ||
    issueIds.some(
      (issueId) =>
        issueId.startsWith("thread-") || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(issueId),
    )
  ) {
    throw new WorkflowError("finding and recommended issue IDs must be unique");
  }
  const assessmentById = new Map<string, Json>(
    previousAssessments.map((item) => [item.id as string, item]),
  );
  const previousLedgerById = new Map<string, Json>(
    ((incremental.previous_finding_ledger as Json[]) ?? []).map((item) => [String(item.id), item]),
  );
  const previousFindingIds = new Set(previousFindings.map((item) => String(item.id)));
  const previousIssueIds = new Set(previousIssues.map((item) => String(item.id)));
  const currentFindingIds = new Set<string>(
    (findingIds as unknown[]).map((findingId) => String(findingId)),
  );
  const currentIssueIds = new Set(issueIds);
  const kindByld: Record<string, string> = {};
  for (const itemId of previousFindingIds) kindByld[itemId] = "finding";
  for (const itemId of previousIssueIds) kindByld[itemId] = "issue";
  for (const [itemId, kind] of Object.entries(kindByld)) {
    const assessmentItem = assessmentById.get(itemId) as Json;
    if (
      ["fixed", "withdrawn"].includes((previousLedgerById.get(itemId) as Json).status as string) &&
      assessmentItem.status === "active"
    ) {
      throw new WorkflowError("a reopened historical finding must use changed status");
    }
    const present =
      currentFindingIds.has(itemId) || (kind === "issue" && currentIssueIds.has(itemId));
    if (["active", "changed", "unverified"].includes(assessmentItem.status as string) && !present) {
      throw new WorkflowError("an active previous finding disappeared from the plan");
    }
    if (["fixed", "withdrawn"].includes(assessmentItem.status as string) && present) {
      throw new WorkflowError("a closed previous finding remains active in the plan");
    }
  }
  if (
    previousAssessments.some((item) => item.status === "unverified") &&
    decision.verdict === "ready"
  ) {
    throw new WorkflowError("an unverified previous finding prohibits ready");
  }
  const targetedPreviousFindings = new Set(
    previousAssessments
      .filter((item) => item.critic_required === true)
      .map((item) => String(item.id)),
  );
  const criticTargets = new Set((decision.critic_target_finding_ids as string[]) ?? []);
  for (const itemId of targetedPreviousFindings) {
    if (!criticTargets.has(itemId)) {
      throw new WorkflowError(
        "changed or disputed previous findings require targeted critic coverage",
      );
    }
  }
  const findingPublications = validateFindingPublications(
    content.finding_publications,
    currentFindingIds,
  );
  const exactGit = context.exact_git as Json;
  const repoRoot = exactGit.repo_root as string;
  const headSha = evidence.head_sha as string;
  const baseSha = evidence.base_sha as string;
  for (const item of findingPublications) {
    if (item.type === "line") {
      const [oldLines, newLines] = changedDiffLines(
        repoRoot,
        baseSha,
        headSha,
        item.path as string,
      );
      if ((item.line ?? null) !== null && !newLines.has(item.line as number)) {
        throw new WorkflowError("finding new-line position is not in the exact diff");
      }
      if ((item.old_line ?? null) !== null && !oldLines.has(item.old_line as number)) {
        throw new WorkflowError("finding old-line position is not in the exact diff");
      }
    }
    if (item.type === "existing_thread") {
      const thread = (content.thread_decisions as Json[]).find(
        (thread) => thread.id === item.thread_id,
      );
      if (
        !thread ||
        thread.assessment !== "accepted" ||
        !["suggestion", "patch"].includes(String(thread.fix_mode))
      )
        throw new WorkflowError(
          "existing_thread must bind an accepted thread with its own validated fix",
        );
      continue;
    }
    if (item.fix_mode === "patch") {
      if (!nonemptyString(item.patch_reason))
        throw new WorkflowError(
          "Patch fallback requires a concrete patch_reason; prefer suggestions",
        );
      validateGitPatch(repoRoot, headSha, item.patch as string);
      validatePatchFallback(item, context, evidence);
    } else {
      const parts = suggestionParts(item);
      for (const part of parts) {
        validateSuggestion(part.body, { repoRoot, headSha, path: part.path, line: part.line });
        const [, lines] = changedDiffLines(repoRoot, baseSha, headSha, part.path);
        if (!lines.has(part.line))
          throw new WorkflowError("Suggestion position is outside the exact visible diff");
        validateGitPatch(repoRoot, headSha, suggestionsPatch(repoRoot, headSha, [part]));
      }
      validateGitPatch(repoRoot, headSha, suggestionsPatch(repoRoot, headSha, parts));
    }
  }
  const currentPublicationById = new Map<string, Json>(
    findingPublications.map((item) => [String(item.finding_id), item]),
  );
  const currentIssueById = new Map<string, Json>(
    recommendedIssues.map((item) => [String(item.id), item]),
  );
  for (const [itemId, old] of previousLedgerById.entries()) {
    if (currentFindingIds.has(itemId) && old.kind !== "finding") {
      throw new WorkflowError("a historical issue ID cannot become a finding ID");
    }
    if (currentIssueIds.has(itemId) && old.kind !== "issue") {
      throw new WorkflowError("a historical finding ID cannot become an issue ID");
    }
    const assessmentItem = assessmentById.get(itemId) as Json;
    if (!["active", "unverified"].includes(assessmentItem.status as string)) continue;
    if (old.kind === "finding" && currentFindingIds.has(itemId)) {
      const oldPublication: Json = { ...((old.record as Json).publication as Json) };
      delete oldPublication.revision;
      delete oldPublication.patch_path;
      delete oldPublication.patch_sha256;
      if (!jsonEqual(oldPublication, currentPublicationById.get(itemId) as Json)) {
        throw new WorkflowError("a changed finding publication must use changed status");
      }
    }
    if (old.kind === "issue" && currentIssueIds.has(itemId)) {
      const oldIssue: Json = { ...((old.record as Json).issue as Json) };
      delete oldIssue.revision;
      if (!jsonEqual(oldIssue, currentIssueById.get(itemId) as Json)) {
        throw new WorkflowError("a changed recommended issue must use changed status");
      }
    }
  }
  for (const assessmentItem of previousAssessments) {
    const itemId = String(assessmentItem.id);
    if (
      assessmentItem.kind === "finding" &&
      currentPublicationById.has(itemId) &&
      assessmentItem.publication_action !== "no_publication" &&
      (currentPublicationById.get(itemId) as Json).body !== assessmentItem.publication_body
    ) {
      throw new WorkflowError("finding publication and previous-finding action bodies disagree");
    }
  }
  if (
    !setsEqual(
      new Set(findingPublications.map((item) => String(item.finding_id))),
      currentFindingIds,
    )
  ) {
    throw new WorkflowError("every actionable finding requires one concrete fix");
  }
  if (
    context.role === "reviewer" &&
    findingPublications.some((item) => item.type === "local_fix")
  ) {
    throw new WorkflowError("reviewer findings require GitLab publication positions");
  }
  if (context.role === "author" && findingPublications.some((item) => item.type !== "local_fix")) {
    throw new WorkflowError("author findings require read-only local fix patches");
  }
  const expectedThreads = expectedThreadBindings(context);
  const threadDecisions = content.thread_decisions as Json[];
  const actualThreads = new Map<string, Json>(
    threadDecisions.map((item) => [String(item.id), item]),
  );
  if (
    actualThreads.size !== threadDecisions.length ||
    !setsEqual(new Set(actualThreads.keys()), new Set(Object.keys(expectedThreads)))
  ) {
    throw new WorkflowError("review plan must account for every non-system thread");
  }
  for (const [threadId, item] of actualThreads.entries()) {
    const source = expectedThreads[threadId] as Json;
    validateUserConfirmation(item, source, context);
    if (item.state !== source.state) {
      throw new WorkflowError("thread decision state does not match review context");
    }
    if (source.state === "open" && item.outcome === "no_publication") {
      throw new WorkflowError("an open thread requires an explicit outcome");
    }
    if (
      (item.outcome === "no_publication" && (item.proposed_response ?? null) !== null) ||
      (item.outcome !== "no_publication" && !nonemptyString(item.proposed_response))
    ) {
      throw new WorkflowError("thread publication outcome and body disagree");
    }
    if (item.url !== (source.url ?? null)) {
      throw new WorkflowError("thread decision URL does not match review context");
    }
    validateFixingCommit(item.fixing_commit ?? null);
    if (
      !setsEqual(
        new Set(
          [...keySet(item)].filter(
            (key) =>
              ![
                "suggestions",
                "split_rationale",
                "patch_reason",
                "severity",
                "user_confirmation",
                "routing_response",
              ].includes(key),
          ),
        ),
        new Set([
          "id",
          "url",
          "state",
          "assessment",
          "rationale",
          "outcome",
          "proposed_response",
          "fix_mode",
          "patch",
          "fixing_commit",
          "last_note_id",
          "last_note_body_sha256",
          "thread_sha256",
        ]),
      ) ||
      item.last_note_id !== (source.last_note_id ?? null) ||
      item.last_note_body_sha256 !== source.last_note_body_sha256 ||
      item.thread_sha256 !== source.thread_sha256
    ) {
      throw new WorkflowError("thread decision does not bind the complete discussion");
    }
    validateThreadFix(item, source, repoRoot, headSha, baseSha);
    validatePatchFallback(item, context, evidence);
    const assessmentValue = item.assessment as string;
    const outcome = item.outcome as string;
    if (assessmentValue === "accepted") {
      if (!["suggestion", "patch"].includes(item.fix_mode as string)) {
        throw new WorkflowError("an accepted thread requires a validated code fix");
      }
      const expectedOutcome = source.state === "resolved" ? "reopen" : null;
      if (expectedOutcome !== null && outcome !== expectedOutcome) {
        throw new WorkflowError("an accepted resolved thread requires reopen");
      }
      if (source.state === "open" && !["reply", "local_fix"].includes(outcome)) {
        throw new WorkflowError("an accepted open thread must remain open");
      }
    }
    if (["fixed", "false_positive", "duplicate", "not_related"].includes(assessmentValue)) {
      const expectedOutcome = source.state === "open" ? "resolve" : null;
      if (expectedOutcome !== null && outcome !== expectedOutcome) {
        throw new WorkflowError("a closing assessment on an open thread requires resolve");
      }
      if (source.state === "resolved" && !["reply", "no_publication"].includes(outcome)) {
        throw new WorkflowError("a closing assessment must keep a resolved thread closed");
      }
    }
    if (
      ["question", "neutral"].includes(assessmentValue) &&
      ["resolve", "reopen"].includes(outcome)
    ) {
      throw new WorkflowError("a neutral or question assessment cannot change thread state");
    }
    if (
      item.outcome === "resolve" &&
      (source.root_resolvable !== true || source.root_resolved === true)
    ) {
      throw new WorkflowError("resolve requires an open resolvable thread");
    }
    if (
      item.outcome === "resolve" &&
      !["fixed", "false_positive", "duplicate", "not_related", "neutral"].includes(
        item.assessment as string,
      )
    ) {
      throw new WorkflowError("resolve requires a closing thread assessment");
    }
    if (
      item.outcome === "reopen" &&
      (source.root_resolvable !== true || source.root_resolved !== true)
    ) {
      throw new WorkflowError("reopen requires a resolved resolvable thread");
    }
    if (
      item.outcome === "reopen" &&
      !["accepted", "question"].includes(item.assessment as string)
    ) {
      throw new WorkflowError("reopen requires an actionable thread assessment");
    }
  }
  if (context.role === "reviewer" && threadDecisions.some((item) => item.outcome === "local_fix")) {
    throw new WorkflowError("reviewer thread decisions cannot promise local fixes");
  }
  const expectedBlockers = blockingThreadIds(threadDecisions, findingPublications);
  if (
    decision.blocking_thread_ids !== undefined &&
    !setsEqual(new Set(expectedBlockers), new Set(decision.blocking_thread_ids as string[]))
  )
    throw new WorkflowError("blocking_thread_ids do not match the accepted non-low thread defects");
  // Legacy decisions may omit the field, but cannot omit the actual readiness gate.
  decision.blocking_thread_ids = expectedBlockers;
  const assessedEvidence =
    draft?.source?.ci_snapshot !== undefined
      ? artifactPayload(String(draft.source.ci_snapshot), "evidence_snapshot")[1]
      : evidence;
  validateReviewVerdict(
    {
      ...decision,
      blocking_findings:
        decision.blocking_findings ?? findings.some((finding) => finding.severity !== "low"),
    },
    findings,
    assessedEvidence,
  );
  const blockingSummaries = findings
    .filter((finding) => finding.severity !== "low")
    .map((finding) => String(finding.summary));
  const threadBlockers = threadDecisions.filter((thread) =>
    expectedBlockers.includes(String(thread.id)),
  );
  content.summary = `${presentation.verdict_value}. ${[...blockingSummaries, ...threadBlockers.map((thread) => String(thread.rationale)), ...((decision.owner_decision_reasons ?? []) as string[])].join(". ") || (content.locale === "ru" ? "Блокирующих находок нет." : "No blocking findings.")}`;
  const metadata = metadataAssessment(evidence, content.mr_metadata_assessment);
  const [publication, enrichedPublications, enrichedIssues, enrichedThreads] =
    await structuredPublicationPreview(
      evidence,
      context,
      root,
      findings,
      findingPublications,
      previousAssessments,
      threadDecisions,
      recommendedIssues,
      labelReview,
      draft?.dryRun ?? false,
      String(content.locale),
    );
  const renderContent: Json = {
    ...content,
    presentation: presentation,
    label_review: labelReview,
    finding_publications: enrichedPublications,
    previous_finding_assessments: previousAssessments,
    recommended_issues: enrichedIssues,
    thread_decisions: enrichedThreads,
    ...(draft?.source ? { review_source: draft.source } : {}),
  };
  const markdown = await reviewMarkdown(
    evidence,
    context,
    decision,
    renderContent,
    metadata,
    publication,
  );
  rejectVisibleRawRefs(markdown, evidence, context);
  const findingLedger = buildFindingLedger(
    incremental,
    previousAssessments,
    findings,
    enrichedPublications,
    enrichedIssues,
    publication,
  );
  const publicationLedger: Json[] = [];
  const rejectedCandidateLedger = buildRejectedCandidateLedger(
    incremental,
    rejectedCandidates,
    rejectedCandidateAssessments,
    new Set(acceptedFindings.map((item) => String(item.id))),
  );
  const payload: Json = {
    profile: "code-review",
    ...(draft?.source ? { review_source: draft.source } : {}),
    review_contract_version: REVIEW_CONTRACT_VERSION,
    external_mutations: false,
    evidence_digest: evidenceDigest,
    context_digest: contextDigest,
    decision_digest: decisionDigest,
    target: context.target,
    role: context.role,
    mode: decision.mode,
    locale: content.locale,
    incremental: incremental,
    verdict: decision.verdict,
    complete: evidence.retrieval_complete === true && context.complete === true,
    summary: content.summary,
    architecture_assessment: content.architecture_assessment,
    semver_impact: content.semver_impact,
    semver_rationale: content.semver_rationale,
    semver_assessment: content.semver_assessment,
    chat_assessment: chatAssessment,
    mr_metadata_assessment: metadata,
    label_review: labelReview,
    publication_preview: publication,
    presentation: presentation,
    checks: content.checks,
    findings: findings,
    finding_publications: enrichedPublications,
    previous_finding_assessments: previousAssessments,
    recommended_issues: enrichedIssues,
    finding_ledger: findingLedger,
    publication_ledger: publicationLedger,
    rejected_candidates: rejectedCandidates,
    rejected_candidate_assessments: rejectedCandidateAssessments,
    rejected_candidate_ledger: rejectedCandidateLedger,
    thread_decisions: enrichedThreads,
    markdown: markdown,
  };
  if (draft?.dryRun) return { status: "ok", payload, external_mutations: false };
  const [path, planDigest] = await writeArtifact(root, "review_plan", payload);
  const [markdownPath, markdownDigest] = await publishReviewState(
    root,
    markdown,
    path,
    planDigest,
    context.target as Json,
    draft?.baselineStateDigest ??
      ((incremental.incremental_baseline as Json).state_digest as string | null) ??
      null,
    draft?.progress ?? {
      stage: "content_missing",
      evidence_path: evidencePath,
      evidence_digest: evidenceDigest,
      context_path: resolvePath(contextValue),
      context_digest: contextDigest,
      decision_path: resolvePath(decisionValue),
      decision_digest: decisionDigest,
    },
    draft?.bindings,
  );
  return {
    status: payload.complete === true ? "ok" : "incomplete",
    summary: {
      tldr: "Prepared an immutable role-aware code review plan.",
      scope: [String((context.target as Json).url ?? "")],
      risks: payload.complete === true ? [] : ["review evidence or context incomplete"],
      checks: ["evidence binding", "role", "all threads", "detailed findings"],
    },
    artifact_path: path,
    digest: planDigest,
    markdown_path: markdownPath,
    markdown_digest: markdownDigest,
    publication_body_paths: (publication.body_files as Json[]).map((item) => item.path),
    patch_paths: [...enrichedPublications, ...enrichedThreads]
      .filter((item) => item.fix_mode === "patch")
      .map((item) => item.patch_path),
    publication_commands: (publication.actions as Json[]).map((item) => item.command),
    publication_actions: (publication.actions as Json[]).map((item) => ({
      id: item.id,
      command: item.command,
    })),
    stage: "plan_ready",
    next_action: runnerAction("report-review", ["--artifact-root", root]),
    external_mutations: false,
  };
}

export function progressArtifact(
  root: string,
  progress: Json,
  prefix: string,
  kind: string,
): [string, Json, string] | null {
  const pathValue = progress[`${prefix}_path`] ?? null;
  const digestValue = progress[`${prefix}_digest`] ?? null;
  if (pathValue === null && digestValue === null) return null;
  if (typeof pathValue !== "string" || !isDigest(digestValue)) {
    throw new WorkflowError("code-review progress artifact binding is incomplete");
  }
  const path = regularFile(pathValue, kind.replace(/_/g, " "));
  const expected = `${root}/artifacts/${kind}/${digestValue}.json`;
  if (path !== expected || sha256Bytes(readFileSync(path)) !== digestValue) {
    throw new WorkflowError("code-review progress artifact binding changed");
  }
  const [, payload] = artifactPayload(path, kind);
  return [path, payload, digestValue as string];
}

function nextActionForStage(stage: string, root: string, progress: Json): Json | null {
  if (
    stage !== "plan_ready" &&
    typeof progress.context_digest === "string" &&
    pathExists(`${root}/review-drafts/review-${progress.context_digest}.json`)
  ) {
    return runnerAction("resume-review", ["--artifact-root", root]);
  }
  if (stage === "prepared") {
    const repoRoot = (progress.repo_root ?? null) as string | null;
    let mode = (progress.mode || "normal") as string;
    if (["incremental", "unchanged"].includes(mode)) mode = "normal";
    return runnerAction(
      "context",
      [
        "--evidence",
        progress.evidence_path as string,
        "--repo-root",
        repoRoot || "<checkout>",
        "--incremental",
        (progress.incremental || "auto") as string,
        "--review-mode",
        mode,
        "--locale",
        (progress.locale || "en") as string,
      ],
      repoRoot === null ? ["repo_root"] : [],
    );
  }
  if (stage === "critic_missing") {
    return runnerAction("template-review", ["--artifact-root", root, "--kind", "critic"]);
  }
  if (stage === "context_ready" || stage === "finalize_missing") {
    return runnerAction("finalize", ["--artifact-root", root]);
  }
  if (stage === "decision_missing") {
    return runnerAction("template-review", ["--artifact-root", root, "--kind", "decision"]);
  }
  if (stage === "content_missing") {
    return runnerAction("template-review", ["--artifact-root", root, "--kind", "content"]);
  }
  if (stage === "plan_ready") {
    return runnerAction("report-review", ["--artifact-root", root]);
  }
  return null;
}

function restartAction(root: string, evidence: Json, progress: Json | null): Json | null {
  const target = evidence.target;
  const url = isDict(target) ? (target.url ?? null) : null;
  if (!nonemptyString(url)) return null;
  const args = ["--url", url as string];
  const repoRoot = progress !== null ? (progress.repo_root ?? null) : null;
  const mode = progress !== null ? (progress.mode ?? null) : null;
  const locale = progress !== null ? (progress.locale ?? null) : null;
  const incremental = progress !== null ? (progress.incremental ?? null) : null;
  if (typeof repoRoot === "string") {
    args.push("--repo-root", repoRoot);
  }
  args.push(
    "--review-mode",
    ["fast", "normal", "deep"].includes(mode as string) ? (mode as string) : "normal",
    "--locale",
    SUPPORTED_LOCALES.has(locale as string) ? (locale as string) : "en",
    "--incremental",
    ["auto", "off"].includes(incremental as string) ? (incremental as string) : "auto",
  );
  return runnerAction("prepare", args);
}

async function reviewStatusInternal(artifactRootValue: string): Promise<Json> {
  const root = await artifactRoot(artifactRootValue);
  const [evidencePath, evidence] = reviewEvidenceFromRoot(root);
  const evidenceDigest = sha256Bytes(readFileSync(evidencePath));
  let progress = loadProgress(root) ?? emptyProgress(evidencePath, evidenceDigest);
  if (progress.evidence_path !== evidencePath || progress.evidence_digest !== evidenceDigest) {
    progress = emptyProgress(evidencePath, evidenceDigest);
  }
  const locale = (progress.locale || "en") as string;
  let actualStage = "prepared";
  let reason = "review context has not been collected";
  let plan: Json | null = null;
  const contextArtifact = progressArtifact(root, progress, "context", "review_context");
  if (contextArtifact !== null) {
    const [contextPath, context, contextDigest] = contextArtifact;
    if (
      context.evidence_digest !== evidenceDigest ||
      !jsonEqual(context.target, evidence.target) ||
      context.complete !== true
    ) {
      throw new WorkflowError("review context is stale or incomplete");
    }
    progress.context_path = contextPath;
    progress.context_digest = contextDigest;
    const mode = (progress.mode ?? null) as string | null;
    if (!REVIEW_MODES.has(mode as string)) {
      actualStage = "context_ready";
      reason = "review mode has not been selected";
    } else {
      const criticRequired = ["normal", "deep", "incremental"].includes(mode as string);
      const criticArtifact = progressArtifact(root, progress, "critic_receipt", "critic_receipt");
      if (criticRequired && criticArtifact === null) {
        actualStage = "critic_missing";
        reason = "an independent recorded critic receipt is required";
      } else {
        if (criticArtifact !== null) {
          const [, critic] = criticArtifact;
          const scopeDigest =
            mode === "incremental"
              ? ((context.incremental as Json).incremental_delta_digest as string)
              : null;
          validateCritic(critic, evidenceDigest, scopeDigest);
        }
        const finalizeArtifact = progressArtifact(
          root,
          progress,
          "finalize_report",
          "finalize_report",
        );
        if (finalizeArtifact === null) {
          actualStage = "finalize_missing";
          reason = "fresh evidence has not been finalized";
        } else {
          const [finalizePath, , finalizeDigest] = finalizeArtifact;
          validateFinalizeReport(finalizePath, evidencePath, evidence);
          const decisionArtifact = progressArtifact(root, progress, "decision", "review_decision");
          if (decisionArtifact === null) {
            actualStage = "decision_missing";
            reason = "the finalized review decision is missing";
          } else {
            const [, decision] = decisionArtifact;
            if (
              decision.evidence_digest !== evidenceDigest ||
              decision.context_digest !== (progress.context_digest ?? null) ||
              decision.finalize_digest !== finalizeDigest ||
              (decision.critic_receipt_digest ?? null) !==
                (progress.critic_receipt_digest ?? null) ||
              decision.mode !== mode
            ) {
              throw new WorkflowError("review decision is stale");
            }
            actualStage = "content_missing";
            reason = "the immutable review plan has not been created";
          }
        }
      }
    }
  }

  let stalePlanReason: string | null = null;
  let baseline: [Json, Json] | null = null;
  try {
    baseline = await baselinePointer(root);
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    baseline = null;
    stalePlanReason = `the stable publication plan is invalid: ${error.message}`;
  }
  if (baseline !== null) {
    const [pointer, candidate] = baseline;
    const current =
      candidate.review_contract_version === REVIEW_CONTRACT_VERSION &&
      candidate.complete === true &&
      jsonEqual(candidate.target, evidence.target) &&
      candidate.evidence_digest === evidenceDigest &&
      candidate.context_digest === (progress.context_digest ?? null) &&
      candidate.decision_digest === (progress.decision_digest ?? null);
    if (current) {
      plan = candidate;
      actualStage = "plan_ready";
      reason = "the current review plan is complete and fresh";
      progress.plan_path = pointer.plan_path;
      progress.plan_digest = pointer.plan_digest;
    } else {
      stalePlanReason = "the stable publication plan does not bind current evidence";
    }
  }
  const stage = stalePlanReason !== null && actualStage !== "plan_ready" ? "stale" : actualStage;
  const nextStage = stage === "stale" ? actualStage : stage;
  return {
    status: actualStage === "plan_ready" ? "ok" : "incomplete",
    stage: stage,
    resume_stage: stage === "stale" ? nextStage : null,
    reason: stalePlanReason ?? reason,
    stale_plan: stalePlanReason !== null,
    artifact_root: root,
    evidence_path: evidencePath,
    context_path: progress.context_path ?? null,
    mode: progress.mode ?? null,
    locale: locale,
    publication_plan_path: actualStage === "plan_ready" ? `${root}/runbook.md` : null,
    plan_digest: plan !== null ? (progress.plan_digest ?? null) : null,
    next_action: nextActionForStage(nextStage, root, progress),
    external_mutations: false,
  };
}

export async function reviewStatus(artifactRootValue: string): Promise<Json> {
  try {
    return await reviewStatusInternal(artifactRootValue);
  } catch (error) {
    if (!(error instanceof WorkflowError) && !isErrnoException(error)) throw error;
    let evidence: Json = {};
    let progress: Json | null = null;
    let root = "";
    try {
      root = await artifactRoot(artifactRootValue);
      try {
        [, evidence] = reviewEvidenceFromRoot(root);
      } catch (innerError) {
        if (!(innerError instanceof WorkflowError)) throw innerError;
        evidence = {};
      }
      try {
        progress = loadProgress(root);
      } catch (innerError) {
        if (!(innerError instanceof WorkflowError)) throw innerError;
        progress = null;
      }
    } catch (innerError) {
      if (!(innerError instanceof WorkflowError)) throw innerError;
    }
    return {
      status: "incomplete",
      stage: "stale",
      resume_stage: "prepared",
      reason: "review progress or a bound artifact is invalid",
      stale_plan: true,
      artifact_root: root,
      evidence_path: null,
      context_path: null,
      mode: progress !== null ? (progress.mode ?? null) : null,
      locale: progress !== null ? (progress.locale ?? "en") : "en",
      publication_plan_path: null,
      plan_digest: null,
      next_action: root === "" ? null : restartAction(root, evidence, progress),
      external_mutations: false,
    };
  }
}

async function writeReviewDraft(
  root: string,
  name: string,
  identity: string,
  value: Json,
): Promise<string> {
  const directory = await privateDirectory(`${root}/review-drafts`);
  const path = `${directory}/${name}-${identity.slice(0, 16)}.json`;
  const release = await reviewStateLock(root);
  try {
    if (pathExists(path) || isSymlink(path)) {
      regularFile(path, "review draft");
    } else {
      writeJson(path, value);
    }
  } finally {
    release();
  }
  return resolvePath(path);
}

export function contentTemplate(
  evidence: Json,
  context: Json,
  decision: Json,
  locale: string,
): Json {
  const incremental = context.incremental as Json;
  const accepted = (decision.accepted_findings ?? []) as Json[];
  const primaryById = new Map<string, Json>();
  for (const item of (decision.findings as Json[]) ?? []) {
    primaryById.set(String(item.id), item);
  }
  const criticById = new Map<string, Json>();
  for (const item of (decision.critic_findings as Json[]) ?? []) {
    criticById.set(String(item.id), item);
  }
  const responses = new Map<string, Json>();
  for (const item of (decision.responses as Json[]) ?? []) {
    responses.set(String(item.id), item);
  }
  const rejectedCandidates: Json[] = [];
  for (const [itemId, finding] of [...primaryById.entries(), ...criticById.entries()]) {
    const response = responses.get(itemId) ?? null;
    if (response === null || response.decision !== "reject") continue;
    rejectedCandidates.push({
      id: itemId,
      source: primaryById.has(itemId) ? "primary" : "critic",
      finding: finding,
      reason: "",
      paths: [],
      thread_ids: [],
      metadata_fields: [],
      ci: false,
    });
  }
  const previousAssessments: Json[] = [];
  for (const [kind, values] of [
    ["finding", incremental.previous_findings as Json[]],
    ["issue", incremental.previous_recommended_issues as Json[]],
  ] as [string, Json[]][]) {
    for (const item of values) {
      previousAssessments.push({
        id: String(item.id),
        kind: kind,
        status: "unverified",
        previous_status: "",
        current_status: "",
        rationale: "",
        action: "",
        publication_action: "no_publication",
        publication_body: null,
        critic_required: true,
      });
    }
  }
  const threads: Json[] = [];
  for (const [threadId, binding] of Object.entries(expectedThreadBindings(context))) {
    threads.push({
      id: threadId,
      url: binding.url,
      state: binding.state,
      assessment: "neutral",
      rationale: "",
      outcome: "reply",
      proposed_response: null,
      fix_mode: "not_required",
      patch: null,
      fixing_commit: null,
      last_note_id: binding.last_note_id,
      last_note_body_sha256: binding.last_note_body_sha256,
      thread_sha256: binding.thread_sha256,
      user_confirmation: {
        status: userProposedFix(binding, context) ? "required" : "not_applicable",
        evidence_note_ids: [],
      },
    });
  }
  return {
    locale: locale,
    chat_assessment: {
      necessity: { status: "unconfirmed", rationale: "" },
      relevance: { status: "current", rationale: "" },
      change: "",
    },
    summary: "",
    architecture_assessment: "",
    semver_impact: "none",
    semver_rationale: "",
    semver_assessment: semverTemplate(evidence, context),
    mr_metadata_assessment: {
      title: { status: "unverified", rationale: "", recommendation: null },
      description: { status: "unverified", rationale: "", recommendation: null },
      labels: { status: "unverified", rationale: "", recommendation: null },
      workflow_state: { status: "unverified", rationale: "", recommendation: null },
      overall: { status: "unverified", rationale: "", recommendation: null },
    },
    label_assessments: labelCatalog(evidence).map((item) => ({
      name: item.name,
      status: "unresolved",
      rationale: "",
    })),
    checks: [],
    findings: accepted,
    finding_publications: accepted.map((item) => ({
      finding_id: item.id,
      type: context.role === "author" ? "local_fix" : "general",
      path: null,
      line: null,
      old_line: null,
      body: "",
      fix_mode: "patch",
      patch: "",
    })),
    previous_finding_assessments: previousAssessments,
    issue_templates: context.issue_templates,
    recommended_issues: [],
    rejected_candidates: rejectedCandidates,
    rejected_candidate_assessments: (incremental.reconsidered_rejected_candidates as Json[]).map(
      (item) => ({ id: item.id, decision: "still_rejected", reason: "" }),
    ),
    thread_decisions: threads,
  };
}

function userFixProposalIndex(source: Json, context: Json): number {
  const root = ((source.notes ?? []) as Json[]).find((note) => note.id === source.root_note_id);
  if (root === undefined || username(root.author) !== context.current_user_username) return -1;
  return ((source.notes ?? []) as Json[]).reduce(
    (last, note, index) =>
      note.system !== true &&
      username(note.author) === context.current_user_username &&
      /```(?:suggestion|diff|patch)|git\s+apply\s*<</m.test(String(note.body))
        ? index
        : last,
    -1,
  );
}

function userProposedFix(source: Json, context: Json): boolean {
  return userFixProposalIndex(source, context) >= 0;
}

export function validateUserConfirmation(item: Json, source: Json, context: Json): void {
  if (!userProposedFix(source, context)) return;
  const confirmation = item.user_confirmation as Json | undefined;
  if (confirmation?.status === "confirmed") {
    const notes = ((source.notes ?? []) as Json[])
      .slice(userFixProposalIndex(source, context) + 1)
      .filter(
        (note) => note.system !== true && username(note.author) === context.current_user_username,
      );
    const ids = confirmation.evidence_note_ids as number[];
    if (
      !Array.isArray(ids) ||
      ids.length === 0 ||
      ids.some((id) => !notes.some((note) => note.id === id))
    )
      throw new WorkflowError(
        "user_confirmation.evidence_note_ids must identify the user's later confirmation in this complete discussion",
      );
    if (
      item.assessment === "fixed" &&
      item.outcome !== "no_publication" &&
      !nonemptyString(confirmation.new_circumstances)
    )
      throw new WorkflowError(
        "An already confirmed fix requires no_publication unless user_confirmation.new_circumstances explains new evidence",
      );
  } else if (item.outcome === "no_publication" && item.assessment === "fixed") {
    throw new WorkflowError(
      "The user's proposed fix still needs their confirmation, even when another participant resolved the thread; prepare a reply or bind their later confirmation note",
    );
  }
}

function ciProblemJobs(evidence: Json): [Json[], boolean, string] {
  const pipelines = evidence.pipelines;
  const headSha = evidence.head_sha;
  if (!isDict(pipelines) || typeof headSha !== "string") {
    return [[], false, "unverified"];
  }
  const pipeline = selectExactPipeline(pipelines, headSha);
  if (pipeline === null) {
    return [[], false, "missing"];
  }
  const status = String(pipeline.status ?? "unknown");
  const jobEvidence = pipeline.job_evidence;
  if (!isDict(jobEvidence)) {
    return [[], false, status];
  }
  const problems: Json[] = [];
  for (const child of (jobEvidence.pipelines as Json[]) ?? []) {
    if (!isDict(child)) continue;
    for (const job of (child.jobs as Json[]) ?? []) {
      if (isDict(job) && ["failed", "canceled"].includes(job.status as string)) {
        problems.push(job);
      }
    }
  }
  const complete = pipelines.complete === true && jobEvidence.complete === true;
  return [problems, complete, status];
}

export function ciJobAssessmentTemplate(evidence: Json): Json[] {
  const [problems] = ciProblemJobs(evidence);
  const result: Json[] = [];
  for (const job of problems) {
    const trace = job.trace;
    const excerpt = isDict(trace) ? (trace.excerpt ?? "") : "";
    const lines = pySplitLines(String(excerpt ?? ""))
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
    result.push({
      project_id: job.project_id,
      pipeline_id: job.pipeline_id,
      job_id: job.id,
      classification: "unknown",
      rationale: "The failure cause has not been classified yet.",
      trace_evidence:
        lines.length > 0 ? lines[lines.length - 1] : "Trace unavailable in canonical evidence.",
    });
  }
  return result;
}

export function ciBlocksReady(evidence: Json, assessments: unknown): boolean {
  const [problems, complete, pipelineStatus] = ciProblemJobs(evidence);
  if (!Array.isArray(assessments)) {
    throw new WorkflowError("CI job assessments are invalid");
  }
  const expected = new Map<string, Json>();
  for (const job of problems) {
    expected.set([job.project_id, job.pipeline_id, job.id].join("\u0000"), job);
  }
  const actual = new Map<string, Json>();
  for (const raw of assessments) {
    if (!isDict(raw)) {
      throw new WorkflowError("CI job assessments are invalid");
    }
    const item = raw as Json;
    const key = [item.project_id, item.pipeline_id, item.job_id].join("\u0000");
    if (
      actual.has(key) ||
      !["process_gate", "code_failure", "infrastructure_failure", "unknown"].includes(
        item.classification as string,
      ) ||
      !nonemptyString(item.rationale) ||
      !nonemptyString(item.trace_evidence)
    ) {
      throw new WorkflowError("CI job assessments are invalid");
    }
    actual.set(key, item);
  }
  if (!setsEqual(new Set(actual.keys()), new Set(expected.keys()))) {
    throw new WorkflowError("review decision does not assess every failed or canceled CI job");
  }
  for (const [key, job] of expected.entries()) {
    const assessment = actual.get(key) as Json;
    const trace = job.trace;
    if (isDict(trace) && trace.complete === true) {
      const excerpt = trace.excerpt;
      if (typeof excerpt !== "string" || !excerpt.includes(assessment.trace_evidence as string)) {
        throw new WorkflowError("CI job assessment is not supported by its trace");
      }
    } else if (assessment.classification !== "unknown") {
      throw new WorkflowError("unavailable CI trace must remain classified as unknown");
    }
  }
  const normalizedStatus = [
    "created",
    "waiting_for_resource",
    "preparing",
    "pending",
    "running",
  ].includes(pipelineStatus)
    ? "running"
    : pipelineStatus;
  if (!complete || !["success", "failed"].includes(normalizedStatus)) {
    return true;
  }
  const pipeline = selectExactPipeline(evidence.pipelines as Json, evidence.head_sha as string);
  const jobEvidence = pipeline !== null ? (pipeline.job_evidence ?? null) : null;
  const terminalStatuses = new Set(["success", "skipped", "manual", "failed", "canceled"]);
  if (
    isDict(jobEvidence) &&
    ((jobEvidence.pipelines as Json[]) ?? []).some(
      (child) =>
        isDict(child) &&
        ((child.jobs as Json[]) ?? []).some(
          (job) => isDict(job) && !terminalStatuses.has(job.status as string),
        ),
    )
  ) {
    return true;
  }
  if (normalizedStatus === "failed" && problems.length === 0) {
    return true;
  }
  return [...actual.values()].some((item) => item.classification !== "process_gate");
}

export async function templateReview(artifactRootValue: string, kind: string): Promise<Json> {
  const status = await reviewStatus(artifactRootValue);
  const root = await artifactRoot(artifactRootValue);
  const progress = loadProgress(root);
  if (progress === null) {
    throw new Error("code-review progress is unavailable");
  }
  const [evidencePath, evidence] = reviewEvidenceFromRoot(root);
  const evidenceDigest = sha256Bytes(readFileSync(evidencePath));
  const contextArtifact = progressArtifact(root, progress, "context", "review_context");
  if (contextArtifact === null) {
    throw new WorkflowError("review context is required before template creation");
  }
  const [contextPath, context, contextDigest] = contextArtifact;
  const mode = progress.mode as string;
  const locale = progress.locale as string;
  let value: Json;
  let identity: string;
  if (kind === "critic") {
    const expectedStage = (status.resume_stage ?? null) || (status.stage as string);
    if (expectedStage !== "critic_missing") {
      throw new WorkflowError("critic template is not the next review stage");
    }
    const incremental = context.incremental as Json;
    value = {
      schema: "portable-gitlab/critic-receipt/v2",
      evidence_digest: evidenceDigest,
      run_id: "",
      session_id: "",
      findings: [],
      external_mutations: false,
    };
    if (mode === "incremental") {
      value.scope_digest = incremental.incremental_delta_digest;
      value.target_finding_ids = sortedStrings(
        ((incremental.previous_findings as Json[]) ?? []).map((item) => String(item.id)),
      );
    }
    identity = evidenceDigest;
  } else if (kind === "decision") {
    const expectedStage = (status.resume_stage ?? null) || (status.stage as string);
    if (expectedStage !== "decision_missing") {
      throw new WorkflowError("decision template is not the next review stage");
    }
    const finalizeArtifact = progressArtifact(root, progress, "finalize_report", "finalize_report");
    if (finalizeArtifact === null) {
      throw new Error("finalize report artifact is unavailable");
    }
    const [, , finalizeDigest] = finalizeArtifact;
    const criticArtifact = progressArtifact(root, progress, "critic_receipt", "critic_receipt");
    const criticFindings =
      criticArtifact !== null ? ((criticArtifact[1].findings as Json[]) ?? []) : [];
    const criticDigest = criticArtifact !== null ? criticArtifact[2] : null;
    const openThreads = Object.entries(expectedThreadBindings(context))
      .filter(([, binding]) => (binding as Json).state === "open")
      .map(([threadId]) => ({ id: `thread:${threadId}` }));
    const ciAssessments = ciJobAssessmentTemplate(evidence);
    const ciBlocked = ciBlocksReady(evidence, ciAssessments);
    const blockingIds = criticFindings
      .filter((item) => item.severity !== "low")
      .map((item) => item.id);
    value = {
      schema: "portable-gitlab/review-decision/v2",
      evidence_digest: evidenceDigest,
      finalize_digest: finalizeDigest,
      context_digest: contextDigest,
      critic_receipt_digest: criticDigest,
      mode: mode,
      external_mutations: false,
      verdict: blockingIds.length > 0 ? "not_ready" : ciBlocked ? "blocked" : "ready",
      run_id: "",
      session_id: "",
      low_risk: mode === "fast",
      blocking_findings: blockingIds.length > 0,
      blocking_finding_ids: blockingIds,
      blocking_thread_ids: [],
      ci_job_assessments: ciAssessments,
      owner_decision_reasons:
        ciBlocked && blockingIds.length === 0
          ? [
              "Exact-head CI jobs are unsuccessful, incomplete, or not yet classified as process gates.",
            ]
          : [],
      findings: [],
      unresolved_threads: openThreads,
      responses: [...criticFindings, ...openThreads].map((item) => ({
        id: item.id,
        decision: "accept",
        reason: "",
      })),
    };
    identity = finalizeDigest;
  } else if (kind === "content") {
    const expectedStage = (status.resume_stage ?? null) || (status.stage as string);
    if (expectedStage !== "content_missing") {
      throw new WorkflowError("content template is not the next review stage");
    }
    const decisionArtifact = progressArtifact(root, progress, "decision", "review_decision");
    if (decisionArtifact === null) {
      throw new Error("review decision artifact is unavailable");
    }
    const [, decision, decisionDigest] = decisionArtifact;
    value = contentTemplate(evidence, context, decision, locale);
    identity = decisionDigest;
  } else {
    throw new WorkflowError("review template kind must be critic, decision, or content");
  }
  const path = await writeReviewDraft(root, kind, identity, value);
  let nextAction: Json;
  if (kind === "critic") {
    nextAction = runnerAction("record-artifact", [
      "--kind",
      "critic_receipt",
      "--evidence",
      evidencePath,
      "--input",
      path,
    ]);
  } else if (kind === "decision") {
    const args = [
      "--evidence",
      evidencePath,
      "--report",
      path,
      "--context",
      contextPath,
      "--finalize-report",
      progress.finalize_report_path as string,
      "--mode",
      mode,
    ];
    if ((progress.critic_receipt_path ?? null) !== null) {
      args.push("--critic-receipt", progress.critic_receipt_path as string);
    }
    nextAction = runnerAction("finalize-review", args);
  } else {
    nextAction = runnerAction("scaffold-review", [
      "--evidence",
      evidencePath,
      "--context",
      contextPath,
      "--decision",
      progress.decision_path as string,
      "--content",
      path,
    ]);
  }
  return {
    status: "ok",
    stage: status.stage,
    template_kind: kind,
    template_path: path,
    next_action: nextAction,
    external_mutations: false,
  };
}

export function blockingThreadIds(threads: Json[], publications: Json[]): string[] {
  return threads
    .filter(
      (thread) =>
        thread.assessment === "accepted" &&
        thread.severity !== "low" &&
        !publications.some((fix) => fix.type === "existing_thread" && fix.thread_id === thread.id),
    )
    .map((thread) => String(thread.id));
}

export function validateReviewVerdict(
  report: Json,
  acceptedFindings: Json[],
  evidence: Json,
): void {
  const acceptedById = new Map<string, Json>(
    acceptedFindings.map((item) => [String(item.id), item]),
  );
  const expectedBlockingIds = new Set(
    [...acceptedById.entries()]
      .filter(([, item]) => item.severity !== "low")
      .map(([itemId]) => itemId),
  );
  const blockingValue = report.blocking_finding_ids ?? null;
  let blockingIds: Set<string>;
  if (blockingValue === null) {
    blockingIds = new Set(
      [...acceptedById.entries()]
        .filter(([, item]) => item.severity !== "low")
        .map(([itemId]) => itemId),
    );
  } else if (
    !Array.isArray(blockingValue) ||
    !(blockingValue as unknown[]).every((item) => nonemptyString(item))
  ) {
    throw new WorkflowError("blocking finding IDs are invalid");
  } else {
    blockingIds = new Set(blockingValue as string[]);
  }
  if (
    blockingIds.size !== new Set((blockingValue as string[] | null) ?? [...blockingIds]).size ||
    !setsEqual(blockingIds, expectedBlockingIds) ||
    report.blocking_findings !== blockingIds.size > 0
  ) {
    throw new WorkflowError("every accepted non-low finding must be blocking");
  }
  const reasons = report.owner_decision_reasons ?? [];
  const threads = report.blocking_thread_ids ?? [];
  if (
    !Array.isArray(threads) ||
    !threads.every(nonemptyString) ||
    new Set(threads).size !== threads.length
  )
    throw new WorkflowError(
      "blocking_thread_ids must be unique IDs of accepted non-low thread defects",
    );
  if (!Array.isArray(reasons) || !(reasons as unknown[]).every((item) => nonemptyString(item))) {
    throw new WorkflowError("owner decision reasons are invalid");
  }
  const ciBlocked = ciBlocksReady(evidence, report.ci_job_assessments ?? []);
  if (
    ciBlocked &&
    blockingIds.size === 0 &&
    threads.length === 0 &&
    (reasons as string[]).length === 0
  ) {
    throw new WorkflowError("blocking CI evidence requires an owner decision reason");
  }
  let expected: string;
  if (blockingIds.size > 0 || threads.length > 0) {
    expected = "not_ready";
  } else if (ciBlocked || (reasons as string[]).length > 0) {
    expected = "blocked";
  } else {
    expected = "ready";
  }
  if (report.verdict !== expected) {
    throw new WorkflowError("review verdict does not match findings and exact-head pipeline");
  }
}

function blockedChat(locale: string, stage: string, reason: string, action: unknown): string {
  const command = isDict(action) ? (action.command ?? null) : null;
  const labels = codeReviewChatLabels(locale);
  const lines = [
    labels.blocked_title as string,
    "",
    `- **${labels.stage}:** \`${stage}\``,
    `- **${labels.reason}:** ${reason}`,
  ];
  if (command) {
    lines.push(`- **${labels.next_action}:** \`${command}\``);
  }
  return lines.join("\n");
}

export function reviewChat(plan: Json, context: Json, planPath: string): string {
  const assessment = validateChatAssessment(plan.chat_assessment);
  const presentation = plan.presentation as Json;
  const locale = plan.locale as string;
  const metadata = ((plan.mr_metadata_assessment as Json).assessment as Json).overall as Json;
  const labels = codeReviewChatLabels(locale);
  const exactGit = context.exact_git as Json;
  const necessity = assessment.necessity as Json;
  const relevance = assessment.relevance as Json;
  const necessityValues = labels.necessity_values as Record<string, string>;
  const relevanceValues = labels.relevance_values as Record<string, string>;
  const metadataValues = labels.metadata_values as Record<string, string>;
  const lines: string[] = [];
  if (plan.mode === "incremental") {
    lines.push(presentation.incremental_notice as string, "");
  }
  lines.push(
    labels.title as string,
    "",
    `- **${labels.role}:** ${presentation.role_value}`,
    `- **${labels.necessity}:** ${necessityValues[necessity.status as string]} - ${necessity.rationale}`,
    `- **${labels.relevance}:** ${relevanceValues[relevance.status as string]} - ${relevance.rationale}`,
    `- **${labels.change}:** ${assessment.change}`,
    `- **${labels.architecture}:** ${plan.architecture_assessment}`,
    ...semverReportLines(plan, locale),
    `- **${labels.metadata}:** ${metadataValues[(metadata as Json).status as string]}`,
    `- **${labels.verdict}:** ${presentation.verdict_value}`,
  );
  if ((plan.findings as Json[]).length === 0) {
    lines.push(`- **${labels.findings}:** ${labels.none}`);
  }
  lines.push(
    `- **${labels.checkout}:** \`${exactGit.repo_root}\``,
    `- **${labels.plan}:** \`${planPath}\``,
  );
  return lines.join("\n");
}

async function reportReviewInternal(artifactRootValue: string): Promise<Json> {
  const status = await reviewStatus(artifactRootValue);
  const locale = (status.locale || "en") as string;
  if (status.stage !== "plan_ready") {
    return {
      status: "blocked",
      stage: status.stage,
      reason: status.reason,
      chat: blockedChat(
        locale,
        status.stage as string,
        status.reason as string,
        status.next_action,
      ),
      next_action: status.next_action,
      external_mutations: false,
    };
  }
  const root = await artifactRoot(artifactRootValue);
  const baseline = await baselinePointer(root);
  if (baseline === null) {
    throw new WorkflowError("current review baseline is unavailable");
  }
  const [pointer, plan] = baseline;
  const [evidencePath, evidence] = reviewEvidenceFromRoot(root);
  const progress = loadProgress(root);
  if (progress === null) {
    throw new WorkflowError("code-review progress is unavailable");
  }
  const recovery = restartAction(root, evidence, progress);
  const current = await collect(evidence.target as Json, "code-review", { persist: false });
  if (
    current.retrieval_complete !== true ||
    !jsonEqual(
      fingerprint(current),
      fingerprint(
        isDict(plan.review_source) && plan.review_source.ci_snapshot !== undefined
          ? artifactPayload(String(plan.review_source.ci_snapshot), "evidence_snapshot")[1]
          : evidence,
      ),
    )
  ) {
    return {
      status: "blocked",
      stage: "stale",
      reason: "review evidence changed before report",
      chat: blockedChat(locale, "stale", "review evidence changed before report", recovery),
      next_action: recovery,
      external_mutations: false,
    };
  }
  const contextArtifact = progressArtifact(root, progress, "context", "review_context");
  if (contextArtifact === null) {
    throw new WorkflowError("current review context is unavailable");
  }
  const [, context] = contextArtifact;
  const refreshed = await refreshContext(context, evidencePath);
  const reportContext: Json = { ...context };
  delete reportContext.incremental;
  if (refreshed.complete !== true || !contextsMatch(reportContext, refreshed)) {
    return {
      status: "blocked",
      stage: "stale",
      reason: "review context changed before report",
      chat: blockedChat(locale, "stale", "review context changed before report", recovery),
      next_action: recovery,
      external_mutations: false,
    };
  }
  const chat = reviewChat(plan, context, String(pointer.markdown_path));
  rejectVisibleRawRefs(chat, evidence, context);
  return {
    status: "ok",
    stage: "plan_ready",
    chat: chat,
    publication_plan_path: pointer.markdown_path,
    plan_digest: pointer.plan_digest,
    next_action: null,
    external_mutations: false,
  };
}

export async function reportReview(artifactRootValue: string): Promise<Json> {
  try {
    return await reportReviewInternal(artifactRootValue);
  } catch (error) {
    if (!(error instanceof WorkflowError) && !isErrnoException(error)) throw error;
    const reason = "review state could not be safely revalidated";
    let nextAction: Json | null = null;
    let locale = "en";
    try {
      const root = await artifactRoot(artifactRootValue);
      try {
        const [, evidence] = reviewEvidenceFromRoot(root);
        let progress: Json | null = null;
        try {
          progress = loadProgress(root);
        } catch (innerError) {
          if (!(innerError instanceof WorkflowError)) throw innerError;
          progress = null;
        }
        if (progress !== null && SUPPORTED_LOCALES.has(progress.locale as string)) {
          locale = progress.locale as string;
        }
        nextAction = restartAction(root, evidence, progress);
      } catch (innerError) {
        if (!(innerError instanceof WorkflowError)) throw innerError;
      }
    } catch (innerError) {
      if (!(innerError instanceof WorkflowError)) throw innerError;
    }
    return {
      status: "blocked",
      stage: "stale",
      reason: reason,
      chat: blockedChat(locale, "stale", reason, nextAction),
      next_action: nextAction,
      external_mutations: false,
    };
  }
}
