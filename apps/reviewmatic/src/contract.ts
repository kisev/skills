import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import {
  accessSync,
  closeSync,
  constants as fsConstants,
  fsyncSync,
  lstatSync,
  openSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeSync,
  type Stats,
} from "node:fs";
import { basename, dirname } from "node:path";
import {
  canonicalJson,
  contentDigest,
  ensurePrivateDirectory,
  StateArtifactError,
  xdgStateHome,
} from "./state-artifacts.js";
import { ARTIFACT_SCHEMA, ARTIFACT_SCHEMA_ID } from "./generated/artifact-schema.js";
import { assessmentIsValid, evidenceIsValid } from "./review-semver.js";

export const MAX_BYTES = 8 * 1024 * 1024;
export const MAX_PAGES = 1_000;
const MAX_CI_PIPELINES = 20;
const MAX_CI_JOB_PAGES = 5;
const MAX_CI_TRACES = 50;
export const MAX_TRACE_BYTES = 64 * 1024;
const MAX_TRACE_HEADER_BYTES = 64 * 1024;
const TRACE_TIMEOUT_SECONDS = 45;
const PROCESS_CLEANUP_TIMEOUT_SECONDS = 1;
const MAX_PIPELINE_DEPTH = 5;
export const ARTIFACT_VERSION = 2;

const URL_RE = /^https:\/\/([^/?#]+)\/(.+?)\/-\/(issues|merge_requests)\/([1-9][0-9]*)\/?$/;
const SECRET_RE = /(token|password|secret|private[_-]?token)\s*[=:]\s*[^\s,]+/gi;
const JSON_SECRET_RE =
  /(["'](?:authorization|password|secret|private[_-]?token|api[_-]?key|access[_-]?key(?:[_-]?id)?|client[_-]?secret|aws_session_token)["']\s*:\s*)(["'])[^\r\n]*?\2/gi;
const AUTHORIZATION_RE = /(\bauthorization\s*:\s*)[^\r\n]+/gim;
const CLOUD_CREDENTIAL_RE =
  /\b((?:AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|GOOGLE_API_KEY|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET)\s*[=:]\s*)[^\s,]+/gi;
const URL_CREDENTIAL_RE = /\b([a-z][a-z0-9+.-]*:\/\/)[^/\s:@]+:[^@\s/]+@/gi;
const PRIVATE_KEY_RE =
  /-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g;

export const LABEL_ROLE_VALUES: Record<string, string[]> = {
  change_type: ["release", "feature", "bug", "maintenance", "documentation", "security"],
  workflow_state: [
    "in_progress",
    "review",
    "blocked",
    "completed",
    "declined",
    "needs_info",
    "stale",
  ],
  urgency: ["emergency", "urgent", "standard", "low"],
  impact: ["critical", "high", "medium", "low"],
  compatibility: ["major", "minor", "patch"],
  origin: ["internal", "external", "inner_source"],
};
const LABEL_ROLE_ALIASES: Record<string, string> = {
  change_type: "change_type",
  type: "change_type",
  kind: "change_type",
  category: "change_type",
  workflow_state: "workflow_state",
  status: "workflow_state",
  state: "workflow_state",
  workflow: "workflow_state",
  urgency: "urgency",
  priority: "urgency",
  impact: "impact",
  risk: "impact",
  severity: "impact",
  compatibility: "compatibility",
  semver: "compatibility",
  version: "compatibility",
  origin: "origin",
  source: "origin",
};
const LABEL_VALUE_ALIASES: Record<string, Record<string, string>> = {
  change_type: {
    release: "release",
    delivery: "release",
    feature: "feature",
    enhancement: "feature",
    capability: "feature",
    bug: "bug",
    defect: "bug",
    fix: "bug",
    maintenance: "maintenance",
    chore: "maintenance",
    refactor: "maintenance",
    technical: "maintenance",
    tech_debt: "maintenance",
    documentation: "documentation",
    docs: "documentation",
    security: "security",
    vulnerability: "security",
  },
  workflow_state: {
    in_progress: "in_progress",
    progress: "in_progress",
    doing: "in_progress",
    development: "in_progress",
    review: "review",
    review_ready: "review",
    ready_for_review: "review",
    blocked: "blocked",
    on_hold: "blocked",
    completed: "completed",
    done: "completed",
    closed: "completed",
    declined: "declined",
    rejected: "declined",
    wontfix: "declined",
    needs_info: "needs_info",
    need_info: "needs_info",
    waiting_for_info: "needs_info",
    stale: "stale",
    inactive: "stale",
  },
  urgency: {
    emergency: "emergency",
    p0: "emergency",
    blocker: "emergency",
    critical: "emergency",
    urgent: "urgent",
    p1: "urgent",
    high: "urgent",
    standard: "standard",
    p2: "standard",
    normal: "standard",
    medium: "standard",
    low: "low",
    p3: "low",
  },
  impact: {
    critical: "critical",
    s1: "critical",
    high: "high",
    s2: "high",
    medium: "medium",
    s3: "medium",
    low: "low",
    s4: "low",
  },
  compatibility: {
    major: "major",
    breaking: "major",
    minor: "minor",
    feature: "minor",
    patch: "patch",
    fix: "patch",
  },
  origin: {
    internal: "internal",
    team: "internal",
    external: "external",
    customer: "external",
    inner_source: "inner_source",
    innersource: "inner_source",
    community: "inner_source",
  },
};
const PROFILES: Record<string, string[]> = {
  "task-triage": ["issues"],
  "task-review": ["issues", "merge_requests"],
  "task-prepare": ["issues"],
  "mr-prepare": ["merge_requests"],
  "code-review": ["merge_requests", "local"],
  "release-prepare": ["merge_requests"],
  "release-review": ["merge_requests"],
};
const ARTIFACT_KINDS = new Set([
  "evidence_snapshot",
  "release_inventory",
  "review_context",
  "publication_plan",
  "review_plan",
  "analysis_report",
  "critic_receipt",
  "review_decision",
  "release_readiness",
  "finalize_report",
  "local_wip_snapshot",
  "local_review_report",
]);

export class WorkflowError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "WorkflowError";
  }
}

export type Semver = [number, number, number, string[], string[]];

const STRING_ESCAPES: Record<string, string> = {
  '"': '\\"',
  "\\": "\\\\",
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
};

function isDict(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPlainInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function fullMatch(pattern: string, value: string): boolean {
  return new RegExp(`^(?:${pattern})$`).test(value);
}

function keySet(value: Record<string, unknown>): Set<string> {
  return new Set(Object.keys(value));
}

function setsEqual(left: Set<unknown>, right: Set<unknown>): boolean {
  if (left.size !== right.size) return false;
  for (const item of left) if (!right.has(item)) return false;
  return true;
}

function pythonStr(value: unknown): string {
  if (value === null || value === undefined) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "string") return value;
  return String(value);
}

function pythonTruthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === "string") return value.length > 0;
  if (typeof value === "number") return value !== 0;
  if (Array.isArray(value)) return value.length > 0;
  if (isDict(value)) return Object.keys(value).length > 0;
  return true;
}

function equalJson(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return (
      left.length === right.length && left.every((item, index) => equalJson(item, right[index]))
    );
  }
  if (isDict(left) && isDict(right)) {
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every((key) => Object.hasOwn(right, key) && equalJson(left[key], right[key]))
    );
  }
  return false;
}

function sha256Text(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
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

function casefold(value: string): string {
  return value.toLowerCase();
}

function quoteString(value: string): string {
  let quoted = '"';
  for (const character of value) {
    const escape = STRING_ESCAPES[character];
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

function serializePython(value: unknown, itemSeparator: string, keySeparator: string): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") return quoteString(value);
  if (Array.isArray(value)) {
    return `[${value
      .map((entry) => serializePython(entry, itemSeparator, keySeparator))
      .join(itemSeparator)}]`;
  }
  if (isDict(value)) {
    const keys = Object.keys(value).sort(compareCodePoints);
    return `{${keys
      .map(
        (key) =>
          `${quoteString(key)}${keySeparator}${serializePython(value[key], itemSeparator, keySeparator)}`,
      )
      .join(itemSeparator)}}`;
  }
  throw new Error("unsupported JSON value for Python serialization");
}

export function canonical(value: unknown): Buffer {
  return Buffer.concat([canonicalJson(value), Buffer.from("\n")]);
}

export function digest(value: unknown): string {
  return contentDigest(canonical(value));
}

export function redact(value: string): string {
  let redacted = value.replace(PRIVATE_KEY_RE, "[REDACTED PRIVATE KEY]");
  redacted = redacted.replace(JSON_SECRET_RE, "$1$2[REDACTED]$2");
  redacted = redacted.replace(AUTHORIZATION_RE, "$1[REDACTED]");
  redacted = redacted.replace(CLOUD_CREDENTIAL_RE, "$1[REDACTED]");
  redacted = redacted.replace(URL_CREDENTIAL_RE, "$1[REDACTED]@");
  return redacted.replace(SECRET_RE, "$1=[REDACTED]");
}

export function emit(value: unknown): void {
  process.stdout.write(`${serializePython(value, ", ", ": ")}\n`);
}

export function error(code: string, message: string, exitCode = 2): number {
  process.stderr.write(`${redact(message)}\n`);
  emit({
    status: "error",
    error: { code: code, message: redact(message), retryable: false },
  });
  return exitCode;
}

function which(binary: string): string | null {
  const pathValue = process.env.PATH ?? "";
  for (const directory of pathValue.split(":")) {
    if (directory === "") continue;
    const candidate = `${directory}/${binary}`;
    try {
      const metadata = statSync(candidate);
      if (!metadata.isFile()) continue;
      accessSync(candidate, fsConstants.X_OK);
      return candidate;
    } catch {
      continue;
    }
  }
  return null;
}

export function capabilities(profile: string): number {
  emit({
    schema_version: 1,
    payload_version: "2.0.0",
    mutation: "local-write",
    dry_run: true,
    state_protocol: "private-content-addressed-artifacts",
    external_tools: {
      glab: which("glab") !== null,
      git: which("git") !== null,
    },
    destructive_flags: [],
    profile: profile,
    external_mutations: false,
  });
  return 0;
}

export function parseTarget(value: string, expected: Set<string>): Record<string, unknown> {
  const match = URL_RE.exec(value);
  let parsed: URL | null = null;
  try {
    parsed = new URL(value);
  } catch {
    parsed = null;
  }
  if (
    parsed === null ||
    parsed.protocol !== "https:" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    match === null ||
    !expected.has(match[3])
  ) {
    throw new WorkflowError("target must be one exact HTTPS GitLab issue or merge request URL");
  }
  const project = match[2];
  if (
    project === "" ||
    project.split("/").some((part) => part === "" || part === "." || part === "..")
  ) {
    throw new WorkflowError("target project path is unsafe");
  }
  return {
    url: value,
    hostname: match[1].toLowerCase(),
    project_path: project,
    kind: match[3],
    iid: Number(match[4]),
  };
}

export function parseProject(value: string): Record<string, unknown> {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new WorkflowError("project must be an exact HTTPS GitLab project URL");
  }
  const parts = parsed.pathname.split("/").filter((part) => part !== "");
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname === "" ||
    parsed.search !== "" ||
    parsed.hash !== "" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parts.length < 2 ||
    parts.includes("-") ||
    parts.some((part) => part === "." || part === "..")
  ) {
    throw new WorkflowError("project must be an exact HTTPS GitLab project URL");
  }
  return {
    url: value.replace(/\/+$/, ""),
    hostname: parsed.hostname.toLowerCase(),
    project_path: parts.join("/"),
    kind: "new_issue",
    iid: 0,
  };
}

function isErrnoException(value: unknown): value is NodeJS.ErrnoException {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof (value as NodeJS.ErrnoException).code === "string"
  );
}

function getPath(target: Record<string, unknown>, key: string, fallback: unknown): unknown {
  return Object.hasOwn(target, key) ? target[key] : fallback;
}

export async function privateDirectory(path: string): Promise<string> {
  try {
    return await ensurePrivateDirectory(path, xdgStateHome());
  } catch (error) {
    if (error instanceof StateArtifactError || isErrnoException(error)) {
      throw new WorkflowError("artifact directory must be a private real directory");
    }
    throw error;
  }
}

export async function stateDirectory(
  profile: string,
  target: Record<string, unknown>,
): Promise<string> {
  if (!(profile in PROFILES)) throw new WorkflowError("workflow profile is unsafe");
  const home = xdgStateHome();
  const project = getPath(target, "project_id", getPath(target, "project_path", "local"));
  const identity = `${pythonStr(getPath(target, "hostname", "local"))}:${pythonStr(project)}:${pythonStr(getPath(target, "kind", "local"))}:${pythonStr(getPath(target, "iid", "local"))}`;
  const identityDigest = createHash("sha256").update(identity, "utf8").digest("hex");
  return privateDirectory(`${home}/agent-skills/gitlab/${identityDigest.slice(0, 32)}`);
}

function posixParts(target: string): string[] {
  const pieces = target.split("/").filter((piece) => piece !== "" && piece !== ".");
  return target.startsWith("/") ? ["/", ...pieces] : pieces;
}

function joinParts(parts: string[]): string {
  if (parts.length === 0 || parts[0] !== "/") return parts.join("/");
  return `/${parts.slice(1).join("/")}`;
}

function normalizeLiteral(target: string): string {
  return joinParts(posixParts(target));
}

function relativeParts(candidate: string, base: string): string[] | null {
  const candidateParts = posixParts(normalizeLiteral(candidate));
  const baseParts = posixParts(normalizeLiteral(base));
  if (candidateParts.length < baseParts.length) return null;
  for (let index = 0; index < baseParts.length; index += 1) {
    if (candidateParts[index] !== baseParts[index]) return null;
  }
  return candidateParts.slice(baseParts.length);
}

function parentPath(path: string): string {
  const normalized = normalizeLiteral(path);
  if (normalized === "/") return "/";
  const index = normalized.lastIndexOf("/");
  return index === 0 ? "/" : normalized.slice(0, index);
}

export async function artifactRoot(path: string): Promise<string> {
  const home = xdgStateHome();
  const stateBase = await privateDirectory(`${home}/agent-skills`);
  const base = await privateDirectory(`${stateBase}/gitlab`);
  const candidate = await privateDirectory(path);
  const relative = relativeParts(candidate, base);
  if (relative === null) {
    const legacy = relativeParts(candidate, stateBase);
    if (legacy === null) {
      throw new WorkflowError("artifact root is outside canonical GitLab collection state");
    }
    if (
      legacy.length === 2 &&
      fullMatch("[a-z0-9][a-z0-9-]{0,63}", legacy[0]) &&
      fullMatch("[a-f0-9]{20}", legacy[1])
    ) {
      return candidate;
    }
    throw new WorkflowError("artifact root is outside canonical GitLab collection state");
  }
  if (relative.length !== 1 || !fullMatch("[a-f0-9]{32}", relative[0])) {
    throw new WorkflowError("artifact root is unsafe");
  }
  return candidate;
}

export function regularFile(path: string, label: string): string {
  let metadata: Stats;
  try {
    metadata = lstatSync(path);
  } catch {
    throw new WorkflowError(`${label} is unavailable`);
  }
  if (metadata.isSymbolicLink() || !metadata.isFile()) {
    throw new WorkflowError(`${label} must be a regular non-symlink file`);
  }
  if (metadata.size > MAX_BYTES) {
    throw new WorkflowError(`${label} exceeds the size limit`);
  }
  return realpathSync(path);
}

export function readJson(path: string, label: string): Record<string, unknown> {
  const resolved = regularFile(path, label);
  let value: unknown;
  try {
    value = JSON.parse(readFileSync(resolved, "utf8"));
  } catch {
    throw new WorkflowError(`${label} must contain a JSON object`);
  }
  if (!isDict(value)) {
    throw new WorkflowError(`${label} must contain a JSON object`);
  }
  return value;
}

export function writeJson(path: string, value: unknown): void {
  writeBytes(path, canonical(value));
}

export function writeBytes(path: string, content: Buffer): void {
  let existing: Stats | undefined;
  try {
    existing = lstatSync(path);
  } catch {
    existing = undefined;
  }
  if (existing !== undefined && (existing.isSymbolicLink() || !existing.isFile())) {
    throw new WorkflowError("state path must be a regular non-symlink file");
  }
  const parentReal = realpathSync(dirname(path));
  const target = `${parentReal}/${basename(path)}`;
  if (dirname(target) !== realpathSync(dirname(path))) {
    throw new WorkflowError("state path escapes its directory");
  }
  const temporary = `${dirname(target)}/.${basename(target)}.${randomBytes(8).toString("hex")}.tmp`;
  try {
    const descriptor = openSync(temporary, "wx", 0o600);
    try {
      writeSync(descriptor, content);
      fsyncSync(descriptor);
    } finally {
      closeSync(descriptor);
    }
    renameSync(temporary, target);
    const directoryDescriptor = openSync(dirname(target), "r");
    try {
      fsyncSync(directoryDescriptor);
    } finally {
      closeSync(directoryDescriptor);
    }
  } finally {
    rmSync(temporary, { force: true });
  }
}

export async function writeArtifact(
  root: string,
  kind: string,
  payload: Record<string, unknown>,
): Promise<[string, string]> {
  if (!ARTIFACT_KINDS.has(kind)) throw new WorkflowError("unknown artifact kind");
  const envelope: Record<string, unknown> = {
    schema: `portable-gitlab/${kind}/v2`,
    schema_version: ARTIFACT_VERSION,
    kind: kind,
    created_at: new Date().toISOString(),
    payload: payload,
  };
  validateV2Artifact(envelope, kind);
  const content = canonical(envelope);
  const contentDigestValue = contentDigest(content);
  const directory = await privateDirectory(`${root}/artifacts/${kind}`);
  const path = `${directory}/${contentDigestValue}.json`;
  let descriptor: number;
  try {
    descriptor = openSync(path, "wx", 0o600);
  } catch (caught) {
    if (isErrnoException(caught) && caught.code === "EEXIST") {
      if (!readFileSync(regularFile(path, "artifact")).equals(content)) {
        throw new WorkflowError("content-addressed artifact conflict");
      }
      return [path, contentDigestValue];
    }
    throw caught;
  }
  try {
    writeSync(descriptor, content);
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
  return [path, contentDigestValue];
}

export function writeCompanion(path: string, content: string): [string, string] {
  const data = Buffer.from(content, "utf8");
  const contentDigestValue = contentDigest(data);
  let descriptor: number;
  try {
    descriptor = openSync(path, "wx", 0o600);
  } catch (caught) {
    if (isErrnoException(caught) && caught.code === "EEXIST") {
      if (!readFileSync(regularFile(path, "Markdown companion")).equals(data)) {
        throw new WorkflowError("immutable Markdown companion conflict");
      }
      return [realpathSync(path), contentDigestValue];
    }
    throw caught;
  }
  try {
    writeSync(descriptor, data);
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
  return [realpathSync(path), contentDigestValue];
}

export function artifactPayload(
  path: string,
  kind: string,
): [Record<string, unknown>, Record<string, unknown>] {
  const value = readJson(path, "artifact");
  if (
    value.schema === `portable-gitlab/${kind}/v2` &&
    value.kind === kind &&
    value.schema_version === ARTIFACT_VERSION &&
    isDict(value.payload)
  ) {
    validateV2Artifact(value, kind);
    return [value, value.payload];
  }
  if (value.schema_version === 1 && kind === "evidence_snapshot") {
    return [value, value];
  }
  throw new WorkflowError("artifact schema is invalid");
}

export function exactKeys(
  value: unknown,
  required: Set<string>,
  label: string,
): Record<string, unknown> {
  if (!isDict(value) || !setsEqual(keySet(value), required)) {
    throw new WorkflowError(`${label} has unknown or missing fields`);
  }
  return value;
}

export function nonemptyString(value: unknown): boolean {
  return typeof value === "string" && value.length > 0;
}

export function isDigest(value: unknown): boolean {
  return typeof value === "string" && fullMatch("[a-f0-9]{64}", value);
}

export function isSha(value: unknown, nullable = false): boolean {
  return (
    (nullable && (value === null || value === undefined)) ||
    (typeof value === "string" && fullMatch("[0-9a-fA-F]{1,128}", value))
  );
}

export function componentIsValid(value: unknown): boolean {
  if (
    !isDict(value) ||
    !setsEqual(keySet(value), new Set(["items", "complete", "errors", "pages", "truncated"]))
  ) {
    return false;
  }
  return (
    Array.isArray(value.items) &&
    typeof value.complete === "boolean" &&
    Array.isArray(value.errors) &&
    value.errors.every((item) => typeof item === "string") &&
    isPlainInt(value.pages) &&
    value.pages >= 0 &&
    typeof value.truncated === "boolean"
  );
}

export function findingsAreValid(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  const legacy = new Set(["id"]);
  const detailed = new Set([
    "id",
    "severity",
    "summary",
    "risk",
    "evidence",
    "consequence",
    "relation_to_change",
    "minimum_fix",
  ]);
  const detailFields = ["summary", "risk", "consequence", "relation_to_change", "minimum_fix"];
  return value.every((entry) => {
    const item = entry;
    if (!isDict(item)) return false;
    const keys = keySet(item);
    const isLegacy = setsEqual(keys, legacy);
    const isDetailed = setsEqual(keys, detailed);
    if (!isLegacy && !isDetailed) return false;
    if (!nonemptyString(item.id)) return false;
    if (isLegacy) return true;
    return (
      ["critical", "high", "medium", "low"].includes(item.severity as string) &&
      detailFields.every((key) => nonemptyString(item[key])) &&
      Array.isArray(item.evidence) &&
      item.evidence.length > 0 &&
      item.evidence.every((subItem) => nonemptyString(subItem))
    );
  });
}

export function detailedFindingsAreValid(value: unknown): boolean {
  return (
    findingsAreValid(value) &&
    Array.isArray(value) &&
    value.every((entry) => isDict(entry) && !setsEqual(keySet(entry), new Set(["id"])))
  );
}

export function duplicateDetailedFindingIds(value: unknown): string[][] {
  if (!detailedFindingsAreValid(value)) return [];
  const groups = new Map<string, string[]>();
  for (const finding of value as Record<string, unknown>[]) {
    const content: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(finding)) {
      if (key !== "id") content[key] = item;
    }
    const contentDigestValue = digest(content);
    const existing = groups.get(contentDigestValue);
    if (existing === undefined) groups.set(contentDigestValue, [finding.id as string]);
    else existing.push(finding.id as string);
  }
  return [...groups.values()].filter((ids) => ids.length > 1);
}

export function threadDecisionsAreValid(value: unknown): boolean {
  const legacy = new Set([
    "id",
    "url",
    "state",
    "assessment",
    "rationale",
    "outcome",
    "proposed_response",
  ]);
  const current = new Set([...legacy, "last_note_id", "last_note_body_sha256", "thread_sha256"]);
  const structured = new Set([...current, "suggestion_applicable"]);
  const fix = new Set([...current, "fix_mode", "patch", "fixing_commit"]);
  const materializedFix = new Set([...fix, "patch_path", "patch_sha256"]);
  const allowed = [legacy, current, structured, fix, materializedFix];
  if (!Array.isArray(value)) return false;
  return value.every((entry) => {
    const item = entry;
    if (!isDict(item)) return false;
    const keys = keySet(item);
    if (!allowed.some((candidate) => setsEqual(keys, candidate))) return false;
    if (!nonemptyString(item.id) || !nonemptyString(item.url) || !nonemptyString(item.rationale)) {
      return false;
    }
    if (!["open", "resolved", "plain"].includes(item.state as string)) return false;
    if (
      ![
        "accepted",
        "fixed",
        "false_positive",
        "duplicate",
        "not_related",
        "question",
        "neutral",
      ].includes(item.assessment as string)
    ) {
      return false;
    }
    if (
      !["no_publication", "local_fix", "reply", "resolve", "reopen"].includes(
        item.outcome as string,
      )
    ) {
      return false;
    }
    if (item.state === "open" && item.outcome === "no_publication") return false;
    if (item.proposed_response !== null && item.proposed_response !== undefined) {
      if (!nonemptyString(item.proposed_response)) return false;
    }
    if (
      !setsEqual(keys, legacy) &&
      !(
        (item.last_note_id ?? null) !== null &&
        isDigest(item.last_note_body_sha256) &&
        isDigest(item.thread_sha256)
      )
    ) {
      return false;
    }
    if (setsEqual(keys, structured) && typeof item.suggestion_applicable !== "boolean") {
      return false;
    }
    if (setsEqual(keys, fix) || setsEqual(keys, materializedFix)) {
      const fixingCommit = item.fixing_commit;
      const fixingCommitValid =
        fixingCommit === null ||
        fixingCommit === undefined ||
        (isDict(fixingCommit) &&
          setsEqual(keySet(fixingCommit), new Set(["title", "url"])) &&
          nonemptyString(fixingCommit.title) &&
          nonemptyString(fixingCommit.url));
      const patch = item.patch;
      const patchValid =
        (item.fix_mode === "patch" && nonemptyString(patch)) ||
        (item.fix_mode !== "patch" && (patch === null || patch === undefined));
      if (
        !["suggestion", "patch", "not_required"].includes(item.fix_mode as string) ||
        !fixingCommitValid ||
        !patchValid
      ) {
        return false;
      }
    }
    if (setsEqual(keys, materializedFix)) {
      const materializedValid =
        (item.fix_mode === "patch" &&
          nonemptyString(item.patch_path) &&
          (item.patch_path as string).startsWith("/") &&
          isDigest(item.patch_sha256) &&
          sha256Text(item.patch as string) === item.patch_sha256) ||
        (item.fix_mode !== "patch" &&
          (item.patch_path === null || item.patch_path === undefined) &&
          (item.patch_sha256 === null || item.patch_sha256 === undefined));
      if (!materializedValid) return false;
    }
    return true;
  });
}

export function findingPublicationsAreValid(value: unknown, requireFixes = false): boolean {
  const legacy = new Set(["finding_id", "revision", "type", "path", "line", "old_line", "body"]);
  const fixed = new Set([...legacy, "fix_mode", "patch", "patch_path", "patch_sha256"]);
  const allowed = requireFixes ? [fixed] : [legacy, fixed];
  if (!Array.isArray(value)) return false;
  return value.every((entry) => {
    const item = entry;
    if (!isDict(item)) return false;
    const keys = keySet(item);
    if (!allowed.some((candidate) => setsEqual(keys, candidate))) return false;
    if (!nonemptyString(item.finding_id)) return false;
    if (!isPlainInt(item.revision)) return false;
    if ((item.revision as number) < 1) return false;
    if (!["general", "line", "local_fix"].includes(item.type as string)) return false;
    if (!nonemptyString(item.body)) return false;
    if (setsEqual(keys, legacy)) return true;
    if (!["suggestion", "patch"].includes(item.fix_mode as string)) return false;
    if (item.fix_mode === "patch") {
      return (
        nonemptyString(item.patch) &&
        nonemptyString(item.patch_path) &&
        (item.patch_path as string).startsWith("/") &&
        isDigest(item.patch_sha256) &&
        sha256Text(item.patch as string) === item.patch_sha256
      );
    }
    return (
      (item.patch === null || item.patch === undefined) &&
      (item.patch_path === null || item.patch_path === undefined) &&
      (item.patch_sha256 === null || item.patch_sha256 === undefined)
    );
  });
}

export function metadataAssessmentItemIsValid(value: unknown): boolean {
  return (
    isDict(value) &&
    setsEqual(keySet(value), new Set(["status", "rationale", "recommendation"])) &&
    ["ok", "needs_change", "unverified"].includes(value.status as string) &&
    nonemptyString(value.rationale) &&
    (value.recommendation === null ||
      value.recommendation === undefined ||
      nonemptyString(value.recommendation))
  );
}

export function mrMetadataAssessmentIsValid(value: unknown): boolean {
  if (!isDict(value) || !setsEqual(keySet(value), new Set(["observed", "assessment"]))) {
    return false;
  }
  const observed = value.observed;
  const assessment = value.assessment;
  const fields = ["title", "description", "labels", "workflow_state"];
  const assessmentFields = [...fields, "overall"];
  return (
    isDict(observed) &&
    setsEqual(keySet(observed), new Set(fields)) &&
    typeof observed.title === "string" &&
    (observed.description === null ||
      observed.description === undefined ||
      typeof observed.description === "string") &&
    Array.isArray(observed.labels) &&
    observed.labels.every((item) => typeof item === "string") &&
    nonemptyString(observed.workflow_state) &&
    isDict(assessment) &&
    setsEqual(keySet(assessment), new Set(assessmentFields)) &&
    assessmentFields.every((field) => metadataAssessmentItemIsValid(assessment[field]))
  );
}

export function reviewChatAssessmentIsValid(value: unknown): boolean {
  if (!isDict(value) || !setsEqual(keySet(value), new Set(["necessity", "relevance", "change"]))) {
    return false;
  }
  const necessity = value.necessity;
  const relevance = value.relevance;
  return (
    isDict(necessity) &&
    setsEqual(keySet(necessity), new Set(["status", "rationale"])) &&
    ["supported", "doubtful", "unconfirmed"].includes(necessity.status as string) &&
    nonemptyString(necessity.rationale) &&
    isDict(relevance) &&
    setsEqual(keySet(relevance), new Set(["status", "rationale"])) &&
    ["current", "partly_outdated", "outdated"].includes(relevance.status as string) &&
    nonemptyString(relevance.rationale) &&
    nonemptyString(value.change)
  );
}

export function reviewMetadataLabels(locale: string): Record<string, string> {
  return locale === "ru"
    ? {
        title: "Заголовок",
        description: "Описание",
        workflow_state: "Состояние",
        overall: "Итог оформления",
      }
    : {
        title: "Title",
        description: "Description",
        workflow_state: "State",
        overall: "Metadata summary",
      };
}

export function reviewActionLabels(locale: string): Record<string, string> {
  return locale === "ru"
    ? {
        add: "Добавить",
        remove: "Убрать",
        reply: "Опубликовать ответ:",
        resolve: "После успешной публикации закрыть тред:",
        reopen: "После успешной публикации переоткрыть тред:",
      }
    : {
        add: "Add",
        remove: "Remove",
        reply: "Publish reply:",
        resolve: "After successful publication, resolve the thread:",
        reopen: "After successful publication, reopen the thread:",
      };
}

export function codeReviewPresentation(
  locale: string,
  role: string,
  verdict: string,
  incrementalMode: string,
): Record<string, unknown> {
  if (locale !== "en" && locale !== "ru") {
    throw new WorkflowError("review locale must be en or ru");
  }
  if (
    (role !== "author" && role !== "reviewer") ||
    (verdict !== "ready" && verdict !== "not_ready" && verdict !== "blocked")
  ) {
    throw new WorkflowError("review presentation identity is invalid");
  }
  if (locale === "ru") {
    return {
      title: "План публикации ревью",
      incremental_notice:
        incrementalMode === "incremental" ? "Проведено инкрементальное ревью." : null,
      target_label: "MR",
      role_label: "Роль",
      role_value: role === "author" ? "автор MR" : "ревьюер чужого MR",
      verdict_label: "Итог",
      verdict_value: {
        ready: "можно сливать",
        not_ready: "нужны изменения",
        blocked: "нужно решение владельца",
      }[verdict],
      metadata_heading: "Оформление MR",
      labels_heading: "Лейблы проекта",
      previous_findings_heading: "Сверка предыдущих обнаружений",
      open_threads_heading: "Открытые треды",
      closed_threads_heading: "Закрытые треды",
      local_fixes_heading: "Локальные исправления",
      new_findings_heading: "Новые обнаружения",
      recommended_issues_heading: "Рекомендуемые задачи",
      checked_heading: "Проверено без публикации",
      architecture_heading: "Архитектурная оценка",
      semver_heading: "Влияние на SemVer",
      checks_heading: "Проверки",
      publication_heading: "Ручная публикация",
      no_items: "Нет.",
      publication_warning: "Команды не выполнялись.",
      previous_table_headers: ["ID", "Было", "Стало", "Основание", "Действие"],
      evidence_label: "Доказательство",
      relation_label: "Связь с изменением",
      severity_labels: {
        critical: "Критическая",
        high: "Высокая",
        medium: "Средняя",
        low: "Низкая",
      },
      recovery_label: "Если ответ опубликован, а состояние не изменилось, выполни только:",
    };
  }
  return {
    title: "Code review publication plan",
    incremental_notice: incrementalMode === "incremental" ? "Incremental review completed." : null,
    target_label: "Target",
    role_label: "Role",
    role_value: role === "author" ? "author of this MR" : "reviewer of another author's MR",
    verdict_label: "Verdict",
    verdict_value: {
      ready: "ready to merge",
      not_ready: "changes required",
      blocked: "owner decision required",
    }[verdict],
    metadata_heading: "MR metadata",
    labels_heading: "Project labels",
    previous_findings_heading: "Previous findings",
    open_threads_heading: "Open threads",
    closed_threads_heading: "Closed threads",
    local_fixes_heading: "Local fixes",
    new_findings_heading: "New findings",
    recommended_issues_heading: "Recommended issues",
    checked_heading: "Reviewed without publication",
    architecture_heading: "Architecture assessment",
    semver_heading: "SemVer impact",
    checks_heading: "Checks",
    publication_heading: "Manual publication preflight",
    no_items: "None.",
    publication_warning: "No command was executed.",
    previous_table_headers: ["ID", "Previous status", "Current status", "Rationale", "Action"],
    evidence_label: "Evidence",
    relation_label: "Relation to change",
    severity_labels: {
      critical: "Critical",
      high: "High",
      medium: "Medium",
      low: "Low",
    },
    recovery_label: "If the response succeeds but the state change fails, run only:",
  };
}

export function codeReviewChatLabels(locale: string): Record<string, unknown> {
  if (locale === "ru") {
    return {
      title: "### Оценка MR",
      blocked_title: "### Ревью заблокировано",
      role: "Роль",
      necessity: "Необходимость",
      relevance: "Актуальность",
      change: "Изменение",
      architecture: "Архитектура",
      semver: "SemVer",
      metadata: "Оформление MR",
      verdict: "Итог",
      checkout: "Checkout ревью",
      plan: "План публикации",
      findings: "Замечания",
      none: "Замечаний нет.",
      stage: "Этап",
      reason: "Причина",
      next_action: "Следующее действие",
      metadata_values: {
        ok: "готово",
        needs_change: "нужны изменения",
        unverified: "нужен контекст",
      },
      necessity_values: {
        supported: "обоснована",
        doubtful: "сомнительна",
        unconfirmed: "не подтверждена",
      },
      relevance_values: {
        current: "актуально",
        partly_outdated: "частично устарело",
        outdated: "устарело",
      },
    };
  }
  if (locale !== "en") {
    throw new WorkflowError("review locale must be en or ru");
  }
  return {
    title: "### MR assessment",
    blocked_title: "### Review blocked",
    role: "Role",
    necessity: "Necessity",
    relevance: "Relevance",
    change: "Change",
    architecture: "Architecture",
    semver: "SemVer",
    metadata: "MR metadata",
    verdict: "Verdict",
    checkout: "Review checkout",
    plan: "Publication plan",
    findings: "Findings",
    none: "No findings.",
    stage: "Stage",
    reason: "Reason",
    next_action: "Next action",
    metadata_values: {
      ok: "ready",
      needs_change: "changes needed",
      unverified: "context needed",
    },
    necessity_values: {
      supported: "supported",
      doubtful: "doubtful",
      unconfirmed: "unconfirmed",
    },
    relevance_values: {
      current: "current",
      partly_outdated: "partly outdated",
      outdated: "outdated",
    },
  };
}

export function reviewPublicationPreviewIsValid(value: unknown): boolean {
  const legacyKeys = new Set([
    "mr_state",
    "warning",
    "preflight_command",
    "body_files",
    "commands",
  ]);
  const currentKeys = new Set([
    "mr_state",
    "warning",
    "preflight_command",
    "preflight_path",
    "preflight_sha256",
    "body_files",
    "commands",
  ]);
  const structuredKeys = new Set([
    "mr_state",
    "warning",
    "preflight_path",
    "preflight_sha256",
    "body_files",
    "actions",
  ]);
  const manualKeys = new Set(["mr_state", "warning", "body_files", "actions"]);
  if (!isDict(value)) return false;
  const keys = keySet(value);
  if (setsEqual(keys, manualKeys)) {
    const bodyFiles = value.body_files;
    const actions = value.actions;
    if (
      !nonemptyString(value.mr_state) ||
      !nonemptyString(value.warning) ||
      !Array.isArray(bodyFiles) ||
      !Array.isArray(actions)
    ) {
      return false;
    }
    const bodiesValid = bodyFiles.every((entry) => {
      const item = entry;
      return (
        isDict(item) &&
        setsEqual(
          keySet(item),
          new Set(["publication_id", "revision", "kind", "path", "content"]),
        ) &&
        nonemptyString(item.publication_id) &&
        isPlainInt(item.revision) &&
        (item.revision as number) >= 1 &&
        ["finding", "thread", "issue"].includes(item.kind as string) &&
        nonemptyString(item.path) &&
        (item.path as string).startsWith("/") &&
        nonemptyString(item.content)
      );
    });
    const actionsValid = actions.every((entry) => {
      const item = entry;
      return (
        isDict(item) &&
        setsEqual(
          keySet(item),
          new Set(["id", "kind", "publication_id", "operation", "command", "path", "line"]),
        ) &&
        nonemptyString(item.id) &&
        ["finding", "thread", "issue", "labels"].includes(item.kind as string) &&
        [
          "create_general",
          "create_line",
          "create_issue",
          "reply",
          "resolve",
          "reopen",
          "update_labels",
        ].includes(item.operation as string) &&
        nonemptyString(item.command)
      );
    });
    if (!bodiesValid || !actionsValid) return false;
    const actionIds = (actions as Record<string, unknown>[]).map((item) => item.id);
    const manualBodyIds = new Set(
      (bodyFiles as Record<string, unknown>[]).map((item) => item.publication_id),
    );
    const manualActionBodyIds = new Set(
      (actions as Record<string, unknown>[])
        .filter((item) => item.publication_id !== null && item.publication_id !== undefined)
        .map((item) => item.publication_id),
    );
    return (
      actionIds.length === new Set(actionIds).size && setsEqual(manualBodyIds, manualActionBodyIds)
    );
  }
  if (setsEqual(keys, structuredKeys)) {
    const bodyFiles = value.body_files;
    const actions = value.actions;
    if (
      !nonemptyString(value.mr_state) ||
      !nonemptyString(value.warning) ||
      !nonemptyString(value.preflight_path) ||
      !(value.preflight_path as string).startsWith("/") ||
      !isDigest(value.preflight_sha256) ||
      !Array.isArray(bodyFiles) ||
      !Array.isArray(actions)
    ) {
      return false;
    }
    const bodiesValid = bodyFiles.every((entry) => {
      const item = entry;
      return (
        isDict(item) &&
        setsEqual(
          keySet(item),
          new Set(["publication_id", "revision", "kind", "path", "sha256", "content"]),
        ) &&
        nonemptyString(item.publication_id) &&
        isPlainInt(item.revision) &&
        (item.revision as number) >= 1 &&
        ["finding", "thread", "issue"].includes(item.kind as string) &&
        nonemptyString(item.path) &&
        (item.path as string).startsWith("/") &&
        isDigest(item.sha256) &&
        nonemptyString(item.content) &&
        sha256Text(item.content as string) === item.sha256
      );
    });
    if (!bodiesValid) return false;
    const operations = new Set([
      "create_general",
      "create_line",
      "create_issue",
      "update_issue",
      "reply",
      "resolve",
      "reopen",
      "update_labels",
    ]);
    const actionsValid = actions.every((entry) => {
      const item = entry;
      if (
        !isDict(item) ||
        !setsEqual(
          keySet(item),
          new Set([
            "id",
            "sha256",
            "kind",
            "publication_id",
            "revision",
            "operation",
            "command",
            "spec",
          ]),
        ) ||
        !nonemptyString(item.id) ||
        !isDigest(item.sha256) ||
        !["finding", "thread", "issue", "labels"].includes(item.kind as string) ||
        !operations.has(item.operation as string) ||
        !nonemptyString(item.command) ||
        !isDict(item.spec)
      ) {
        return false;
      }
      const spec = item.spec;
      if (
        item.sha256 !== digest(spec) ||
        !setsEqual(
          keySet(spec),
          new Set([
            "schema",
            "preflight_sha256",
            "operation",
            "publication",
            "body",
            "expected",
            "mutation",
          ]),
        ) ||
        spec.schema !== "code-review/publication-action/v1" ||
        spec.preflight_sha256 !== value.preflight_sha256 ||
        spec.operation !== item.operation ||
        !isDict(spec.expected) ||
        !setsEqual(keySet(spec.expected), new Set(["thread", "note", "prior_marker", "issue"])) ||
        !isDict(spec.mutation)
      ) {
        return false;
      }
      const mutation = spec.mutation;
      if (item.kind === "labels") {
        if (
          !(
            (item.publication_id === null || item.publication_id === undefined) &&
            (item.revision === null || item.revision === undefined) &&
            item.operation === "update_labels" &&
            (spec.publication === null || spec.publication === undefined) &&
            (spec.body === null || spec.body === undefined) &&
            setsEqual(keySet(mutation), new Set(["add", "remove", "proposed"])) &&
            ["add", "remove", "proposed"].every(
              (key) =>
                Array.isArray(mutation[key]) &&
                (mutation[key] as unknown[]).every((label) => typeof label === "string"),
            )
          )
        ) {
          return false;
        }
        const addLabels = mutation.add as string[];
        const removeLabels = mutation.remove as string[];
        if (addLabels.some((label) => removeLabels.includes(label))) return false;
        return true;
      }
      if (!["finding", "thread", "issue"].includes(item.kind as string)) return false;
      if (!nonemptyString(item.publication_id)) return false;
      if (!isPlainInt(item.revision) || (item.revision as number) < 1) return false;
      if (!isDict(spec.publication)) return false;
      if (
        !equalJson(spec.publication, {
          id: item.publication_id,
          revision: item.revision,
          kind: item.kind,
        })
      ) {
        return false;
      }
      if (!isDict(spec.body)) return false;
      if (!setsEqual(keySet(spec.body), new Set(["path", "sha256"]))) return false;
      if (typeof spec.body.path !== "string" || !(spec.body.path as string).startsWith("/")) {
        return false;
      }
      return isDigest(spec.body.sha256);
    });
    if (!actionsValid) return false;
    const actionIds = (actions as Record<string, unknown>[]).map((item) => item.id);
    const bodyIdentities = new Set(
      (bodyFiles as Record<string, unknown>[]).map((item) =>
        [item.publication_id, item.revision, item.kind, item.path, item.sha256].join("\u0000"),
      ),
    );
    const actionIdentities = new Set(
      (actions as Record<string, unknown>[])
        .filter((item) => item.kind !== "labels")
        .map((item) => {
          const body = (item.spec as Record<string, unknown>).body as Record<string, unknown>;
          return [item.publication_id, item.revision, item.kind, body.path, body.sha256].join(
            "\u0000",
          );
        }),
    );
    return (
      actionIds.length === new Set(actionIds).size &&
      (actions as Record<string, unknown>[]).filter((item) => item.kind === "labels").length <= 1 &&
      setsEqual(bodyIdentities, actionIdentities)
    );
  }
  if (!setsEqual(keys, legacyKeys) && !setsEqual(keys, currentKeys)) return false;
  const legacy = setsEqual(keys, legacyKeys);
  const bodyFiles = value.body_files;
  const commands = value.commands;
  if (
    !nonemptyString(value.mr_state) ||
    !nonemptyString(value.warning) ||
    !nonemptyString(value.preflight_command) ||
    (!legacy &&
      (!nonemptyString(value.preflight_path) ||
        !(value.preflight_path as string).startsWith("/") ||
        !isDigest(value.preflight_sha256))) ||
    !Array.isArray(bodyFiles) ||
    !Array.isArray(commands)
  ) {
    return false;
  }
  if (legacy) {
    const bodiesValid = bodyFiles.every((entry) => {
      const item = entry;
      return (
        isDict(item) &&
        setsEqual(keySet(item), new Set(["finding_id", "path", "sha256", "content"])) &&
        nonemptyString(item.finding_id) &&
        nonemptyString(item.path) &&
        (item.path as string).startsWith("/") &&
        isDigest(item.sha256) &&
        nonemptyString(item.content) &&
        sha256Text(item.content as string) === item.sha256
      );
    });
    const commandsValid = commands.every((entry) => {
      const item = entry;
      return (
        isDict(item) &&
        setsEqual(keySet(item), new Set(["finding_id", "command"])) &&
        nonemptyString(item.finding_id) &&
        nonemptyString(item.command)
      );
    });
    if (!bodiesValid || !commandsValid) return false;
    const bodyIds = (bodyFiles as Record<string, unknown>[]).map((item) => item.finding_id);
    const commandIds = (commands as Record<string, unknown>[]).map((item) => item.finding_id);
    return (
      bodyIds.length === new Set(bodyIds).size &&
      commandIds.length === new Set(commandIds).size &&
      equalJson(bodyIds, commandIds)
    );
  }
  const bodiesValid = bodyFiles.every((entry) => {
    const item = entry;
    return (
      isDict(item) &&
      setsEqual(
        keySet(item),
        new Set(["publication_id", "revision", "kind", "path", "sha256", "content"]),
      ) &&
      nonemptyString(item.publication_id) &&
      isPlainInt(item.revision) &&
      (item.revision as number) >= 1 &&
      ["finding", "thread", "issue"].includes(item.kind as string) &&
      nonemptyString(item.path) &&
      (item.path as string).startsWith("/") &&
      isDigest(item.sha256) &&
      nonemptyString(item.content) &&
      sha256Text(item.content as string) === item.sha256
    );
  });
  if (!bodiesValid) return false;
  const commandsValid = commands.every((entry) => {
    const item = entry;
    return (
      isDict(item) &&
      setsEqual(
        keySet(item),
        new Set(["publication_id", "revision", "kind", "outcome", "command", "recovery_command"]),
      ) &&
      nonemptyString(item.publication_id) &&
      isPlainInt(item.revision) &&
      (item.revision as number) >= 1 &&
      ["finding", "thread", "issue"].includes(item.kind as string) &&
      [
        "create_general",
        "create_line",
        "create_issue",
        "update_issue",
        "reply",
        "resolve",
        "reopen",
      ].includes(item.outcome as string) &&
      nonemptyString(item.command) &&
      (item.recovery_command === null ||
        item.recovery_command === undefined ||
        nonemptyString(item.recovery_command))
    );
  });
  if (!commandsValid) return false;
  const bodyIds = (bodyFiles as Record<string, unknown>[]).map((item) => item.publication_id);
  const commandIds = (commands as Record<string, unknown>[]).map((item) => item.publication_id);
  const typedBodies = bodyFiles as Record<string, unknown>[];
  const typedCommands = commands as Record<string, unknown>[];
  return (
    bodyIds.length === new Set(bodyIds).size &&
    commandIds.length === new Set(commandIds).size &&
    equalJson(bodyIds, commandIds) &&
    typedBodies.every(
      (body, index) =>
        body.revision === typedCommands[index].revision && body.kind === typedCommands[index].kind,
    )
  );
}

export function incrementalReviewIsValid(value: unknown): boolean {
  const required = new Set([
    "contract_version",
    "requested",
    "mode",
    "reason",
    "incremental_baseline",
    "previous_findings",
    "previous_finding_publications",
    "previous_recommended_issues",
    "previous_finding_ledger",
    "previous_publication_ledger",
    "previous_thread_decisions",
    "previous_rejected_candidates",
    "reconsidered_rejected_candidates",
    "incremental_delta",
    "incremental_delta_digest",
    "critic_required",
    "fallback_reasons",
  ]);
  if (!isDict(value) || !setsEqual(keySet(value), required)) return false;
  const mode = value.mode;
  const delta = value.incremental_delta;
  const baseline = value.incremental_baseline;
  const listKeys = [
    "previous_findings",
    "previous_finding_publications",
    "previous_recommended_issues",
    "previous_finding_ledger",
    "previous_publication_ledger",
    "previous_thread_decisions",
    "previous_rejected_candidates",
    "reconsidered_rejected_candidates",
  ];
  const deltaListKeys = [
    "changed_paths",
    "changed_thread_ids",
    "unchanged_thread_ids",
    "changed_note_ids",
    "unchanged_note_ids",
    "metadata_fields",
  ];
  if (
    value.contract_version !== 1 ||
    !["auto", "off"].includes(value.requested as string) ||
    !["full", "incremental", "unchanged"].includes(mode as string) ||
    !nonemptyString(value.reason) ||
    !isDict(baseline) ||
    !setsEqual(keySet(baseline), new Set(["plan_path", "plan_digest", "state_digest"])) ||
    (baseline.state_digest !== null &&
      baseline.state_digest !== undefined &&
      !isDigest(baseline.state_digest)) ||
    typeof value.critic_required !== "boolean" ||
    !Array.isArray(value.fallback_reasons) ||
    !(value.fallback_reasons as unknown[]).every((item) => typeof item === "string") ||
    !listKeys.every((key) => Array.isArray(value[key])) ||
    !isDict(delta) ||
    !isDigest(value.incremental_delta_digest) ||
    !setsEqual(
      keySet(delta),
      new Set([
        "from_head",
        "to_head",
        "changed_paths",
        "changed_thread_ids",
        "unchanged_thread_ids",
        "changed_note_ids",
        "unchanged_note_ids",
        "metadata_fields",
        "pipelines_changed",
      ]),
    ) ||
    !isSha(delta.from_head, true) ||
    !isSha(delta.to_head, true) ||
    !deltaListKeys.every(
      (key) =>
        Array.isArray(delta[key]) &&
        (delta[key] as unknown[]).every((item) => typeof item === "string"),
    ) ||
    typeof delta.pipelines_changed !== "boolean" ||
    value.incremental_delta_digest !== digest(delta)
  ) {
    return false;
  }
  const hasBaseline = nonemptyString(baseline.plan_path) && isDigest(baseline.plan_digest);
  if (mode === "full") {
    return (
      (baseline.plan_path === null || baseline.plan_path === undefined) &&
      (baseline.plan_digest === null || baseline.plan_digest === undefined) &&
      value.critic_required === false &&
      listKeys.every((key) => (value[key] as unknown[]).length === 0)
    );
  }
  return hasBaseline && isSha(delta.to_head) && value.critic_required === (mode === "incremental");
}

export function semanticToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function semanticRole(value: string): string | null {
  return LABEL_ROLE_ALIASES[semanticToken(value)] ?? null;
}

export function semanticValue(role: string, value: string): string | null {
  return (LABEL_VALUE_ALIASES[role] ?? {})[semanticToken(value)] ?? null;
}

export function labelSemantics(value: unknown): [string, string] | null {
  if (!isDict(value) || !nonemptyString(value.name)) return null;
  const name = value.name as string;
  const description = value.description;
  if (typeof description === "string") {
    const marker =
      /semantic[-_ ]role\s*[:=]\s*([^;\n]+)\s*;\s*semantic[-_ ]value\s*[:=]\s*([^;\n]+)/i.exec(
        description,
      );
    if (marker !== null) {
      const role = semanticRole(marker[1] as string);
      const itemValue = role !== null ? semanticValue(role, marker[2] as string) : null;
      if (
        role !== null &&
        itemValue !== null &&
        (LABEL_ROLE_VALUES[role] ?? []).includes(itemValue)
      ) {
        return [role, itemValue];
      }
      return null;
    }
  }
  const separator = /::|:|\/|=/g.exec(name);
  if (separator === null) return null;
  const roleText = name.slice(0, separator.index);
  const valueText = name.slice(separator.index + separator[0].length);
  const role = semanticRole(roleText);
  const itemValue = role !== null ? semanticValue(role, valueText) : null;
  if (role === null || itemValue === null || !(LABEL_ROLE_VALUES[role] ?? []).includes(itemValue)) {
    return null;
  }
  return [role, itemValue];
}

export function labelIntentIsValid(value: unknown): boolean {
  if (!isDict(value) || !setsEqual(keySet(value), new Set(Object.keys(LABEL_ROLE_VALUES)))) {
    return false;
  }
  return Object.entries(value).every(
    ([role, item]) =>
      item === null ||
      item === undefined ||
      (typeof item === "string" && (LABEL_ROLE_VALUES[role] ?? []).includes(item)),
  );
}

export function reviewLabels(
  bundle: Record<string, unknown>,
  intent: Record<string, string | null>,
): Record<string, unknown> {
  const labelsComponent = bundle.labels;
  const objectValue = bundle.object;
  if (!isDict(labelsComponent) || !isDict(objectValue)) {
    throw new WorkflowError("label evidence is unavailable");
  }
  const rawCurrent = objectValue.labels;
  if (!Array.isArray(rawCurrent) || !rawCurrent.every((item) => typeof item === "string")) {
    throw new WorkflowError("current MR labels are invalid");
  }
  const current = rawCurrent as string[];
  const semanticsByName = new Map<string, Set<string>>();
  const labelItems = Array.isArray(labelsComponent.items) ? labelsComponent.items : [];
  for (const entry of labelItems) {
    const semantics = labelSemantics(entry);
    if (semantics === null || !isDict(entry) || typeof entry.name !== "string") continue;
    const existing = semanticsByName.get(entry.name) ?? new Set<string>();
    existing.add(semantics.join("\u0000"));
    semanticsByName.set(entry.name, existing);
  }
  const resolvedByName = new Map<string, [string, string]>();
  for (const [name, values] of semanticsByName.entries()) {
    if (values.size === 1) {
      resolvedByName.set(name, ([...values][0] as string).split("\u0000") as [string, string]);
    }
  }
  const candidates = new Map<string, string[]>();
  for (const [name, semantics] of resolvedByName.entries()) {
    const key = semantics.join("\u0000");
    const existing = candidates.get(key) ?? [];
    existing.push(name);
    candidates.set(key, existing);
  }
  for (const names of candidates.values()) {
    names.sort((left, right) => compareCodePoints(casefold(left), casefold(right)));
  }
  const add: string[] = [];
  const remove: string[] = [];
  const unresolved: string[] = [];
  const decisions: Record<string, unknown>[] = [];
  const catalogComplete = labelsComponent.complete === true;
  for (const role of Object.keys(LABEL_ROLE_VALUES)) {
    const requested = Object.hasOwn(intent, role)
      ? intent[role]
      : (undefined as unknown as string | null);
    const currentForRole = current.filter(
      (name) => (resolvedByName.get(name)?.[0] ?? null) === role,
    );
    if (requested === null || requested === undefined) {
      decisions.push({
        role: role,
        intent: null,
        current: currentForRole,
        desired_label: null,
        action: "keep",
        reason: "no semantic intent supplied",
      });
      continue;
    }
    const matching = catalogComplete ? (candidates.get(`${role}\u0000${requested}`) ?? []) : [];
    if (!catalogComplete || matching.length > 1) {
      const reason = catalogComplete
        ? "multiple project labels match the same semantic intent"
        : "project label catalog is incomplete";
      unresolved.push(`${role}=${requested}: ${reason}`);
      decisions.push({
        role: role,
        intent: requested,
        current: currentForRole,
        desired_label: null,
        action: "unresolved",
        reason: reason,
      });
      continue;
    }
    if (matching.length === 0) {
      decisions.push({
        role: role,
        intent: requested,
        current: currentForRole,
        desired_label: null,
        action: "unsupported",
        reason: "semantic role and value are not represented in the project catalog",
      });
      continue;
    }
    const desiredLabel = matching[0] as string;
    const roleRemove = currentForRole.filter((name) => name !== desiredLabel);
    for (const name of roleRemove) {
      if (!remove.includes(name)) remove.push(name);
    }
    if (!current.includes(desiredLabel) && !add.includes(desiredLabel)) {
      add.push(desiredLabel);
    }
    decisions.push({
      role: role,
      intent: requested,
      current: currentForRole,
      desired_label: desiredLabel,
      action: roleRemove.length > 0 || add.includes(desiredLabel) ? "change" : "keep",
      reason: "unique semantic match in the project label catalog",
    });
  }
  const proposed = current.filter((name) => !remove.includes(name));
  for (const name of add) {
    if (!proposed.includes(name)) proposed.push(name);
  }
  return {
    complete: catalogComplete && unresolved.length === 0,
    intent: intent,
    current: current,
    proposed: proposed,
    add: add,
    remove: remove,
    decisions: decisions,
    unresolved: unresolved,
  };
}

export function labelReviewIsValid(value: unknown): boolean {
  if (
    !isDict(value) ||
    !setsEqual(
      keySet(value),
      new Set([
        "complete",
        "intent",
        "current",
        "proposed",
        "add",
        "remove",
        "decisions",
        "unresolved",
      ]),
    )
  ) {
    return false;
  }
  if (
    typeof value.complete !== "boolean" ||
    !labelIntentIsValid(value.intent) ||
    !["current", "proposed", "add", "remove", "unresolved"].every(
      (key) =>
        Array.isArray(value[key]) &&
        (value[key] as unknown[]).every((item) => typeof item === "string"),
    ) ||
    !Array.isArray(value.decisions)
  ) {
    return false;
  }
  const decisions = value.decisions;
  const required = new Set(["role", "intent", "current", "desired_label", "action", "reason"]);
  const decisionsValid = decisions.every((entry) => {
    const item = entry;
    return (
      isDict(item) &&
      setsEqual(keySet(item), required) &&
      typeof item.role === "string" &&
      item.role in LABEL_ROLE_VALUES &&
      (item.intent === null ||
        item.intent === undefined ||
        (typeof item.intent === "string" &&
          (LABEL_ROLE_VALUES[item.role] ?? []).includes(item.intent))) &&
      Array.isArray(item.current) &&
      (item.current as unknown[]).every((name) => typeof name === "string") &&
      (item.desired_label === null ||
        item.desired_label === undefined ||
        typeof item.desired_label === "string") &&
      ["keep", "change", "unsupported", "unresolved"].includes(item.action as string) &&
      nonemptyString(item.reason)
    );
  });
  if (!decisionsValid) return false;
  const typedDecisions = decisions as Record<string, unknown>[];
  const roles = typedDecisions.map((item) => item.role);
  const current = value.current as string[];
  const add = value.add as string[];
  const remove = value.remove as string[];
  const expected = current.filter((name) => !remove.includes(name));
  for (const name of add) {
    if (!expected.includes(name)) expected.push(name);
  }
  const addSet = new Set(add);
  const removeSet = new Set(remove);
  return (
    roles.length === Object.keys(LABEL_ROLE_VALUES).length &&
    setsEqual(new Set(roles), new Set(Object.keys(LABEL_ROLE_VALUES))) &&
    typedDecisions.every((item) =>
      (item.current as string[]).every((name) => current.includes(name)),
    ) &&
    remove.every((name) => current.includes(name)) &&
    add.every((name) => (value.proposed as string[]).includes(name)) &&
    add.every((name) => !removeSet.has(name)) &&
    add.length === addSet.size &&
    remove.length === removeSet.size &&
    (value.complete === false ||
      ((value.unresolved as string[]).length === 0 &&
        typedDecisions.every((item) => item.action !== "unresolved"))) &&
    equalJson(value.proposed, expected)
  );
}

export function codeReviewLabelReviewIsValid(value: unknown): boolean {
  const required = new Set([
    "complete",
    "catalog_sha256",
    "catalog",
    "assessments",
    "current",
    "add",
    "remove",
    "proposed",
    "unresolved",
    "semver",
  ]);
  if (!isDict(value) || !setsEqual(keySet(value), required)) return false;
  if (
    value.complete !== true ||
    !isDigest(value.catalog_sha256) ||
    !Array.isArray(value.catalog) ||
    !Array.isArray(value.assessments) ||
    !["current", "add", "remove", "proposed", "unresolved"].every(
      (key) =>
        Array.isArray(value[key]) &&
        (value[key] as unknown[]).length === new Set(value[key] as unknown[]).size &&
        (value[key] as unknown[]).every((item) => typeof item === "string"),
    ) ||
    !isDict(value.semver) ||
    !setsEqual(keySet(value.semver), new Set(["impact", "candidates", "selected"])) ||
    !["major", "minor", "patch", "none", "not_applicable"].includes(
      value.semver.impact as string,
    ) ||
    !Array.isArray(value.semver.candidates) ||
    !(value.semver.candidates as unknown[]).every((item) => typeof item === "string") ||
    (value.semver.selected !== null &&
      value.semver.selected !== undefined &&
      typeof value.semver.selected !== "string")
  ) {
    return false;
  }
  const catalog = value.catalog;
  const assessments = value.assessments;
  const catalogValid = catalog.every((entry) => {
    const item = entry;
    return (
      isDict(item) &&
      setsEqual(keySet(item), new Set(["name", "description"])) &&
      nonemptyString(item.name) &&
      (item.description === null ||
        item.description === undefined ||
        typeof item.description === "string")
    );
  });
  const assessmentsValid = assessments.every((entry) => {
    const item = entry;
    return (
      isDict(item) &&
      setsEqual(keySet(item), new Set(["name", "description", "status", "rationale", "current"])) &&
      nonemptyString(item.name) &&
      (item.description === null ||
        item.description === undefined ||
        typeof item.description === "string") &&
      ["applicable", "inapplicable", "unresolved"].includes(item.status as string) &&
      nonemptyString(item.rationale) &&
      typeof item.current === "boolean"
    );
  });
  if (!catalogValid || !assessmentsValid) return false;
  const catalogNames = (catalog as Record<string, unknown>[]).map((item) => item.name as string);
  const assessmentByName = new Map<string, Record<string, unknown>>(
    (assessments as Record<string, unknown>[]).map((item) => [item.name as string, item]),
  );
  const current = value.current as string[];
  const add = value.add as string[];
  const remove = value.remove as string[];
  const proposedSet = new Set<string>(current.filter((name) => !remove.includes(name)));
  for (const name of add) proposedSet.add(name);
  const proposed = [...proposedSet].sort((left, right) =>
    compareCodePoints(casefold(left), casefold(right)),
  );
  return (
    value.catalog_sha256 === digest(value.catalog) &&
    catalogNames.length === new Set(catalogNames).size &&
    catalogNames.length === assessmentByName.size &&
    setsEqual(new Set(catalogNames), new Set(assessmentByName.keys())) &&
    current.every((name) => catalogNames.includes(name)) &&
    add.every((name) => catalogNames.includes(name)) &&
    remove.every((name) => current.includes(name)) &&
    !add.some((name) => remove.includes(name)) &&
    equalJson(value.proposed, proposed) &&
    setsEqual(
      new Set(value.unresolved as string[]),
      new Set(
        [...assessmentByName.entries()]
          .filter(([, item]) => item.status === "unresolved")
          .map(([name]) => name),
      ),
    ) &&
    [...assessmentByName.entries()].every(
      ([name, item]) => current.includes(name) === (item.current === true),
    )
  );
}

export function companionsAreValid(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  const names = new Set<string>();
  for (const entry of value) {
    const item = entry;
    if (!isDict(item) || !setsEqual(keySet(item), new Set(["name", "content", "sha256"]))) {
      return false;
    }
    if (
      typeof item.name !== "string" ||
      !fullMatch("[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", item.name) ||
      names.has(item.name) ||
      typeof item.content !== "string" ||
      !isDigest(item.sha256) ||
      sha256Text(item.content) !== item.sha256
    ) {
      return false;
    }
    names.add(item.name);
  }
  return true;
}

export function parseSemver(value: unknown): Semver | null {
  if (typeof value !== "string" || value.length === 0 || value.trim() !== value) return null;
  if ((value.match(/\+/g) ?? []).length > 1) return null;
  const plusIndex = value.indexOf("+");
  const version = plusIndex >= 0 ? value.slice(0, plusIndex) : value;
  const buildValue = plusIndex >= 0 ? value.slice(plusIndex + 1) : "";
  if (plusIndex >= 0 && buildValue === "") return null;
  const dashIndex = version.indexOf("-");
  const core = dashIndex >= 0 ? version.slice(0, dashIndex) : version;
  const prereleaseValue = dashIndex >= 0 ? version.slice(dashIndex + 1) : "";
  if (dashIndex >= 0 && prereleaseValue === "") return null;
  const coreValues = core.split(".");
  if (
    coreValues.length !== 3 ||
    coreValues.some((item) => item.length > 64 || !fullMatch("0|[1-9][0-9]*", item))
  ) {
    return null;
  }
  const identifiers = (raw: string, prerelease: boolean): string[] | null => {
    if (raw === "") return [];
    const values = raw.split(".");
    if (values.some((item) => !fullMatch("[0-9A-Za-z-]+", item))) return null;
    if (
      prerelease &&
      values.some((item) => fullMatch("[0-9]+", item) && item.length > 1 && item.startsWith("0"))
    ) {
      return null;
    }
    return values;
  };
  const prereleaseValues = identifiers(prereleaseValue, true);
  const buildValues = identifiers(buildValue, false);
  if (prereleaseValues === null || buildValues === null) return null;
  const [major, minor, patch] = coreValues.map((item) => Number(item));
  return [major, minor, patch, prereleaseValues, buildValues];
}

function releaseContentShapeIsValid(value: unknown): boolean {
  const required = new Set([
    "title",
    "description",
    "version",
    "announcement",
    "illustration_prompt",
    "label_intent",
    "milestone_title",
    "contributors",
    "reviewers",
    "illustration_style",
    "work_items",
  ]);
  if (!isDict(value) || !setsEqual(keySet(value), required)) return false;
  const style = value.illustration_style;
  const workItems = value.work_items;
  const contributors = value.contributors;
  const reviewers = value.reviewers;
  const textFields = [
    "title",
    "description",
    "announcement",
    "illustration_prompt",
    "milestone_title",
  ];
  return !(
    !textFields.every((key) => nonemptyString(value[key])) ||
    parseSemver(value.version) === null ||
    !labelIntentIsValid(value.label_intent) ||
    !Array.isArray(contributors) ||
    !(contributors as unknown[]).every((item) => nonemptyString(item)) ||
    contributors.length !== new Set(contributors as string[]).size ||
    !Array.isArray(reviewers) ||
    !(reviewers as unknown[]).every(
      (item) => typeof item === "string" && fullMatch("@[A-Za-z0-9_.-]+", item),
    ) ||
    reviewers.length !== new Set(reviewers as string[]).size ||
    !isDict(style) ||
    !setsEqual(keySet(style), new Set(["preset", "reference", "custom"])) ||
    !["pixel_art", "literary", "neutral_abstract", "custom"].includes(style.preset as string) ||
    (style.reference !== null &&
      style.reference !== undefined &&
      !nonemptyString(style.reference)) ||
    (style.custom !== null && style.custom !== undefined && !nonemptyString(style.custom)) ||
    (style.preset === "literary") !== nonemptyString(style.reference) ||
    (style.preset === "custom") !== nonemptyString(style.custom) ||
    !Array.isArray(workItems)
  );
}

function releaseRequestsAreValid(value: unknown): boolean {
  if (!Array.isArray(value)) return false;
  const requestIds = new Set<string>();
  for (const entry of value) {
    const item = entry;
    if (
      !isDict(item) ||
      !setsEqual(keySet(item), new Set(["id", "stage", "operation", "command", "assets"])) ||
      !nonemptyString(item.id) ||
      requestIds.has(item.id as string) ||
      !["pre_merge", "post_merge"].includes(item.stage as string) ||
      !nonemptyString(item.operation) ||
      (item.command !== null && item.command !== undefined && !nonemptyString(item.command)) ||
      !Array.isArray(item.assets)
    ) {
      return false;
    }
    requestIds.add(item.id as string);
    for (const assetEntry of item.assets as unknown[]) {
      const asset = assetEntry;
      if (
        !isDict(asset) ||
        !setsEqual(keySet(asset), new Set(["role", "name", "path", "sha256", "content"])) ||
        !nonemptyString(asset.role) ||
        !nonemptyString(asset.name) ||
        !nonemptyString(asset.path) ||
        !isDigest(asset.sha256) ||
        typeof asset.content !== "string" ||
        !(asset.name as string).startsWith(asset.sha256 as string) ||
        sha256Text(asset.content as string) !== asset.sha256
      ) {
        return false;
      }
    }
  }
  return true;
}

function releaseTargetStateIsValid(value: unknown, stage: unknown, postMergeSha: unknown): boolean {
  if (stage === "pre_merge") {
    return (
      (value === null || value === undefined) &&
      (postMergeSha === null || postMergeSha === undefined)
    );
  }
  if (stage !== "post_merge") return false;
  if (!isDict(value)) return false;
  if (!setsEqual(keySet(value), new Set(["tag_name", "tag_exists", "tag_sha", "release_exists"]))) {
    return false;
  }
  return (
    nonemptyString(value.tag_name) &&
    typeof value.tag_exists === "boolean" &&
    isSha(value.tag_sha, true) &&
    typeof value.release_exists === "boolean" &&
    value.tag_exists === ((value.tag_sha ?? null) !== null) &&
    (value.tag_sha === null ||
      value.tag_sha === undefined ||
      value.tag_sha === postMergeSha ||
      (postMergeSha === null && value.tag_sha === null) ||
      (postMergeSha === undefined && value.tag_sha === null)) &&
    value.release_exists === false
  );
}

export function artifactSchema(): Record<string, unknown> {
  if (ARTIFACT_SCHEMA.$id !== ARTIFACT_SCHEMA_ID) {
    throw new WorkflowError("canonical artifact schema is unavailable");
  }
  return ARTIFACT_SCHEMA;
}

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function fromIsoFormat(value: string): boolean {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})(?:([^0-9])(\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?(Z|[+-]\d{2}(?::?\d{2})?(?::\d{2}(?:\.\d+)?)?)?)?$/.exec(
      value,
    );
  if (match === null) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const daysInMonth = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (month < 1 || month > 12 || day < 1 || day > (daysInMonth[month - 1] ?? 0)) return false;
  const hour = match[5] !== undefined ? Number(match[5]) : 0;
  const minute = match[6] !== undefined ? Number(match[6]) : 0;
  const second = match[7] !== undefined ? Number(match[7]) : 0;
  if (hour > 23 || minute > 59 || second > 59) return false;
  const zone = match[9];
  if (zone !== undefined && zone !== "Z") {
    const offsetHours = Number(zone.slice(1, 3));
    const offsetMinutes = zone.length >= 5 ? Number(zone.slice(-2)) : 0;
    if (offsetMinutes > 59 || offsetHours >= 24) return false;
    if (offsetHours === 23 && offsetMinutes > 0) return false;
  }
  return true;
}

export function schemaValid(
  schema: Record<string, unknown>,
  value: unknown,
  root: Record<string, unknown>,
): boolean {
  const reference = schema.$ref;
  if (typeof reference === "string") {
    const prefix = "#/$defs/";
    if (!reference.startsWith(prefix)) return false;
    const definitions = isDict(root.$defs) ? root.$defs : {};
    const definition = definitions[reference.slice(prefix.length)];
    return isDict(definition) && schemaValid(definition, value, root);
  }
  const negated = schema.not;
  if (isDict(negated) && schemaValid(negated, value, root)) return false;
  const condition = schema.if;
  if (isDict(condition)) {
    const branch = schemaValid(condition, value, root) ? schema.then : schema.else;
    if (isDict(branch) && !schemaValid(branch, value, root)) return false;
  }
  if (
    Array.isArray(schema.allOf) &&
    !(schema.allOf as unknown[]).every((item) => isDict(item) && schemaValid(item, value, root))
  ) {
    return false;
  }
  if (
    Array.isArray(schema.oneOf) &&
    (schema.oneOf as unknown[]).filter((item) => isDict(item) && schemaValid(item, value, root))
      .length !== 1
  ) {
    return false;
  }
  if (
    Array.isArray(schema.anyOf) &&
    !(schema.anyOf as unknown[]).some((item) => isDict(item) && schemaValid(item, value, root))
  ) {
    return false;
  }
  if (schema.const !== undefined && !equalJson(value, schema.const)) return false;
  if (
    Array.isArray(schema.enum) &&
    !(schema.enum as unknown[]).some((item) => equalJson(value, item))
  ) {
    return false;
  }
  const expectedType = schema.type;
  if (expectedType === "null" && value !== null) return false;
  if (expectedType === "object" && !isDict(value)) return false;
  if (expectedType === "array" && !Array.isArray(value)) return false;
  if (expectedType === "string" && typeof value !== "string") return false;
  if (expectedType === "boolean" && typeof value !== "boolean") return false;
  if (expectedType === "integer" && !isPlainInt(value)) return false;
  if (typeof value === "string") {
    const pattern = schema.pattern;
    if (typeof pattern === "string" && !fullMatch(pattern, value)) return false;
    if (isPlainInt(schema.minLength) && Array.from(value).length < schema.minLength) return false;
    if (schema.format === "date-time" && !fromIsoFormat(value)) return false;
  }
  if (isPlainInt(value) && isPlainInt(schema.minimum) && value < schema.minimum) return false;
  if (Array.isArray(value)) {
    if (isPlainInt(schema.minItems) && value.length < schema.minItems) return false;
    if (isPlainInt(schema.maxItems) && value.length > schema.maxItems) return false;
    const itemSchema = schema.items;
    if (isDict(itemSchema) && !value.every((item) => schemaValid(itemSchema, item, root))) {
      return false;
    }
  }
  if (isDict(value)) {
    const required = schema.required ?? [];
    if (
      !Array.isArray(required) ||
      !(required as unknown[]).every((key) => typeof key === "string" && key in value)
    ) {
      return false;
    }
    const properties = schema.properties ?? {};
    if (!isDict(properties)) return false;
    if (schema.additionalProperties === false) {
      const propertyNames = new Set(Object.keys(properties));
      if (!Object.keys(value).every((key) => propertyNames.has(key))) return false;
    }
    for (const [key, item] of Object.entries(value)) {
      const propertySchema = properties[key];
      if (isDict(propertySchema) && !schemaValid(propertySchema, item, root)) return false;
    }
  }
  return true;
}

export function validateV2Artifact(value: Record<string, unknown>, kind: string): void {
  const schema = artifactSchema();
  if (!schemaValid(schema, value, schema)) {
    throw new WorkflowError("artifact does not satisfy the canonical schema");
  }
  const envelope = exactKeys(
    value,
    new Set(["schema", "schema_version", "kind", "created_at", "payload"]),
    "artifact",
  );
  if (
    envelope.schema !== `portable-gitlab/${kind}/v2` ||
    envelope.schema_version !== ARTIFACT_VERSION ||
    envelope.kind !== kind ||
    !nonemptyString(envelope.created_at) ||
    !isDict(envelope.payload)
  ) {
    throw new WorkflowError("artifact schema is invalid");
  }
  if (typeof envelope.created_at !== "string" || !fromIsoFormat(envelope.created_at)) {
    throw new WorkflowError("artifact timestamp is schema-invalid");
  }
  const payload = envelope.payload;
  if (kind === "local_review_report") {
    return;
  }
  if (kind === "evidence_snapshot") {
    exactKeys(
      payload,
      new Set([
        "schema_version",
        "profile",
        "external_mutations",
        "target",
        "project",
        "object",
        "labels",
        "changed_files",
        "commits",
        "pipelines",
        "discussions",
        "head_sha",
        "base_sha",
        "start_sha",
        "artifact_root",
        "prepared_at",
        "components_complete",
        "retrieval_complete",
      ]),
      "evidence payload",
    );
    const requiredComponents = new Set([
      "project",
      "labels",
      "object",
      "changed_files",
      "commits",
      "pipelines",
      "discussions",
    ]);
    if (
      payload.schema_version !== ARTIFACT_VERSION ||
      payload.external_mutations !== false ||
      !["target", "project", "object"].every((key) => isDict(payload[key])) ||
      !["labels", "changed_files", "commits", "pipelines", "discussions"].every((key) =>
        componentIsValid(payload[key]),
      ) ||
      !["head_sha", "base_sha", "start_sha"].every((key) => isSha(payload[key], true)) ||
      !nonemptyString(payload.profile) ||
      !nonemptyString(payload.artifact_root) ||
      !nonemptyString(payload.prepared_at) ||
      !isDict(payload.components_complete) ||
      !setsEqual(keySet(payload.components_complete), requiredComponents) ||
      !Object.values(payload.components_complete).every((item) => typeof item === "boolean") ||
      typeof payload.retrieval_complete !== "boolean"
    ) {
      throw new WorkflowError("evidence payload is schema-invalid");
    }
  } else if (kind === "local_wip_snapshot") {
    exactKeys(
      payload,
      new Set([
        "schema_version",
        "profile",
        "external_mutations",
        "repo_root",
        "base_sha",
        "head_sha",
        "ref",
        "sections",
        "artifact_root",
        "retrieval_complete",
      ]),
      "local WIP payload",
    );
    if (
      payload.schema_version !== ARTIFACT_VERSION ||
      payload.external_mutations !== false ||
      !nonemptyString(payload.profile) ||
      !nonemptyString(payload.repo_root) ||
      !isSha(payload.base_sha) ||
      !isSha(payload.head_sha) ||
      (payload.ref !== null && payload.ref !== undefined && !nonemptyString(payload.ref)) ||
      !isDict(payload.sections) ||
      !setsEqual(
        keySet(payload.sections),
        new Set(["committed", "staged", "unstaged", "untracked"]),
      ) ||
      !nonemptyString(payload.artifact_root) ||
      typeof payload.retrieval_complete !== "boolean"
    ) {
      throw new WorkflowError("local WIP payload is schema-invalid");
    }
  } else if (kind === "release_inventory") {
    const required = new Set([
      "schema_version",
      "profile",
      "external_mutations",
      "evidence_digest",
      "target",
      "repo_root",
      "project_id",
      "hostname",
      "head_sha",
      "component_target_branch",
      "previous_ref",
      "previous_ref_explicit",
      "previous_sha",
      "previous_tag",
      "revision_range",
      "commits",
      "merge_requests",
      "direct_commits",
      "contributors",
      "reviewers",
      "milestone_candidates",
      "work_item_candidates",
      "collection_completeness",
      "errors",
      "warnings",
      "complete",
      "artifact_root",
      "prepared_at",
      "counts",
    ]);
    exactKeys(payload, required, "release inventory payload");
    const counts = payload.counts;
    if (
      payload.schema_version !== ARTIFACT_VERSION ||
      payload.profile !== "release-prepare" ||
      payload.external_mutations !== false ||
      !isDigest(payload.evidence_digest) ||
      !isDict(payload.target) ||
      !nonemptyString(payload.repo_root) ||
      !isPlainInt(payload.project_id) ||
      (payload.project_id as number) < 1 ||
      !["hostname", "component_target_branch", "revision_range"].every((key) =>
        nonemptyString(payload[key]),
      ) ||
      !isSha(payload.head_sha) ||
      (payload.previous_ref !== null &&
        payload.previous_ref !== undefined &&
        !nonemptyString(payload.previous_ref)) ||
      typeof payload.previous_ref_explicit !== "boolean" ||
      !isSha(payload.previous_sha, true) ||
      (payload.previous_tag !== null &&
        payload.previous_tag !== undefined &&
        !isDict(payload.previous_tag)) ||
      ![
        "commits",
        "merge_requests",
        "direct_commits",
        "contributors",
        "reviewers",
        "milestone_candidates",
        "work_item_candidates",
        "errors",
        "warnings",
      ].every((key) => Array.isArray(payload[key])) ||
      !isDict(payload.collection_completeness) ||
      !setsEqual(
        keySet(payload.collection_completeness),
        new Set(["component_merge_requests", "project_milestones", "work_items"]),
      ) ||
      !Object.values(payload.collection_completeness).every((item) => typeof item === "boolean") ||
      typeof payload.complete !== "boolean" ||
      !nonemptyString(payload.artifact_root) ||
      !nonemptyString(payload.prepared_at) ||
      !isDict(counts) ||
      !setsEqual(
        keySet(counts),
        new Set([
          "commits",
          "merge_requests",
          "direct_commits",
          "contributors",
          "reviewers",
          "milestone_candidates",
          "work_item_candidates",
          "errors",
          "warnings",
        ]),
      ) ||
      !Object.values(counts).every((item) => isPlainInt(item) && (item as number) >= 0)
    ) {
      throw new WorkflowError("release inventory payload is schema-invalid");
    }
  } else if (kind === "review_context") {
    const legacyRequired = new Set([
      "schema_version",
      "profile",
      "external_mutations",
      "evidence_digest",
      "target",
      "role",
      "current_user_username",
      "mr_author_username",
      "discussions",
      "notes",
      "counts",
      "exact_git",
      "complete",
      "errors",
      "artifact_root",
      "prepared_at",
    ]);
    const currentRequired = new Set([...legacyRequired, "incremental", "issue_templates"]);
    const structuredRequired = new Set([...currentRequired, "current_user_id"]);
    const releaseRequired = new Set([...structuredRequired, "release_evidence"]);
    const payloadKeys = keySet(payload);
    if (
      !setsEqual(payloadKeys, legacyRequired) &&
      !setsEqual(payloadKeys, currentRequired) &&
      !setsEqual(payloadKeys, structuredRequired) &&
      !setsEqual(payloadKeys, releaseRequired)
    ) {
      throw new WorkflowError("review context payload has unknown or missing fields");
    }
    const legacyContext = setsEqual(payloadKeys, legacyRequired);
    const structuredContext =
      setsEqual(payloadKeys, structuredRequired) || setsEqual(payloadKeys, releaseRequired);
    if (setsEqual(payloadKeys, releaseRequired) && !evidenceIsValid(payload.release_evidence)) {
      throw new WorkflowError("review release evidence is schema-invalid");
    }
    const counts = payload.counts;
    const exactGit = payload.exact_git;
    if (
      payload.schema_version !== ARTIFACT_VERSION ||
      payload.profile !== "code-review" ||
      payload.external_mutations !== false ||
      !isDigest(payload.evidence_digest) ||
      !isDict(payload.target) ||
      !["author", "reviewer"].includes(payload.role as string) ||
      (structuredContext &&
        (!isPlainInt(payload.current_user_id) || (payload.current_user_id as number) < 1)) ||
      !["current_user_username", "mr_author_username", "artifact_root", "prepared_at"].every(
        (key) => nonemptyString(payload[key]),
      ) ||
      (payload.current_user_username === payload.mr_author_username) !==
        (payload.role === "author") ||
      !["discussions", "notes", "errors"].every((key) => Array.isArray(payload[key])) ||
      !(payload.errors as unknown[]).every((item) => typeof item === "string") ||
      (!legacyContext && !incrementalReviewIsValid(payload.incremental)) ||
      typeof payload.complete !== "boolean" ||
      !isDict(counts) ||
      !setsEqual(
        keySet(counts),
        new Set([
          "discussions",
          "notes",
          "content_notes",
          "system_notes",
          "open_resolvable",
          "resolved_resolvable",
          "plain_discussions",
        ]),
      ) ||
      !Object.values(counts).every((item) => isPlainInt(item) && (item as number) >= 0) ||
      !isDict(exactGit) ||
      !setsEqual(
        keySet(exactGit),
        new Set(["repo_root", "refs", "changed_paths", "diff_sha256", "complete", "errors"]),
      ) ||
      !nonemptyString(exactGit.repo_root) ||
      !isDict(exactGit.refs) ||
      !Array.isArray(exactGit.changed_paths) ||
      !(exactGit.changed_paths as unknown[]).every((item) => typeof item === "string") ||
      !(
        isDigest(exactGit.diff_sha256) ||
        exactGit.diff_sha256 === null ||
        exactGit.diff_sha256 === undefined
      ) ||
      typeof exactGit.complete !== "boolean" ||
      !Array.isArray(exactGit.errors) ||
      !(exactGit.errors as unknown[]).every((item) => typeof item === "string")
    ) {
      throw new WorkflowError("review context payload is schema-invalid");
    }
  } else if (kind === "publication_plan") {
    const required = new Set([
      "profile",
      "target",
      "evidence_digest",
      "complete",
      "markdown",
      "plan_name",
      "external_mutations",
    ]);
    const releaseFields = new Set([
      "inventory_digest",
      "release_version",
      "companions",
      "stage",
      "release_content",
      "requests",
      "post_merge_sha",
      "release_target_state",
    ]);
    const labelFields = new Set(["label_review"]);
    const profile = typeof payload.profile === "string" ? payload.profile : "";
    const actualKeys = keySet(payload);
    let keysValid: boolean;
    if (profile === "release-prepare") {
      const expected = new Set([...required, ...releaseFields]);
      const withLabels = new Set([...expected, ...labelFields]);
      keysValid = setsEqual(actualKeys, expected) || setsEqual(actualKeys, withLabels);
    } else if (profile === "mr-prepare") {
      const withLabels = new Set([...required, ...labelFields]);
      const withContent = new Set([...withLabels, "mr_content", "requests"]);
      keysValid =
        setsEqual(actualKeys, new Set([...required])) ||
        setsEqual(actualKeys, withLabels) ||
        setsEqual(actualKeys, withContent);
    } else {
      keysValid = setsEqual(actualKeys, new Set([...required]));
    }
    if (
      !keysValid ||
      !nonemptyString(payload.profile) ||
      !isDict(payload.target) ||
      !isDigest(payload.evidence_digest) ||
      typeof payload.markdown !== "string" ||
      !nonemptyString(payload.plan_name) ||
      typeof payload.complete !== "boolean" ||
      payload.external_mutations !== false ||
      (payload.profile === "release-prepare" &&
        (!isDigest(payload.inventory_digest) ||
          parseSemver(payload.release_version) === null ||
          !companionsAreValid(payload.companions) ||
          !["pre_merge", "post_merge"].includes(payload.stage as string) ||
          !releaseContentShapeIsValid(payload.release_content) ||
          payload.release_version !==
            (isDict(payload.release_content) ? payload.release_content.version : undefined) ||
          !releaseRequestsAreValid(payload.requests) ||
          !isSha(payload.post_merge_sha, true) ||
          (payload.stage === "pre_merge") !==
            (payload.post_merge_sha === null || payload.post_merge_sha === undefined) ||
          !releaseTargetStateIsValid(
            payload.release_target_state,
            payload.stage,
            payload.post_merge_sha,
          ))) ||
      ("label_review" in payload &&
        !("mr_content" in payload
          ? codeReviewLabelReviewIsValid(payload.label_review)
          : labelReviewIsValid(payload.label_review))) ||
      ("mr_content" in payload &&
        (!isDict(payload.mr_content) ||
          !Array.isArray(payload.requests) ||
          !(payload.requests as unknown[]).every((entry) => {
            const item = entry;
            return (
              isDict(item) &&
              setsEqual(keySet(item), new Set(["name", "content", "sha256", "field", "command"])) &&
              ["name", "content", "sha256", "field", "command"].every(
                (key) => typeof item[key] === "string",
              ) &&
              ["title", "description", "labels"].includes(item.field as string) &&
              isDigest(item.sha256) &&
              item.name === `${item.sha256 as string}-${item.field as string}.json`
            );
          })))
    ) {
      throw new WorkflowError("publication plan payload is schema-invalid");
    }
  } else if (kind === "review_plan") {
    const legacyRequired = new Set([
      "profile",
      "external_mutations",
      "evidence_digest",
      "context_digest",
      "decision_digest",
      "target",
      "role",
      "mode",
      "verdict",
      "complete",
      "summary",
      "architecture_assessment",
      "semver_impact",
      "semver_rationale",
      "mr_metadata_assessment",
      "publication_preview",
      "checks",
      "findings",
      "thread_decisions",
      "markdown",
    ]);
    const minimalRequired = new Set(
      [...legacyRequired].filter(
        (key) =>
          !["semver_rationale", "mr_metadata_assessment", "publication_preview"].includes(key),
      ),
    );
    const currentRequired = new Set([
      ...legacyRequired,
      "review_contract_version",
      "incremental",
      "presentation",
      "finding_publications",
      "previous_finding_assessments",
      "recommended_issues",
      "finding_ledger",
      "publication_ledger",
      "rejected_candidates",
      "rejected_candidate_assessments",
      "rejected_candidate_ledger",
    ]);
    const structuredRequired = new Set([...currentRequired, "label_review"]);
    const finalRequired = new Set([...structuredRequired, "chat_assessment", "locale"]);
    const releaseRequired = new Set([...finalRequired, "semver_assessment"]);
    const actualKeys = keySet(payload);
    if (
      !setsEqual(actualKeys, minimalRequired) &&
      !setsEqual(actualKeys, legacyRequired) &&
      !setsEqual(actualKeys, currentRequired) &&
      !setsEqual(actualKeys, structuredRequired) &&
      !setsEqual(actualKeys, finalRequired) &&
      !setsEqual(actualKeys, releaseRequired)
    ) {
      throw new WorkflowError("review plan payload has unknown or missing fields");
    }
    const legacyPlan =
      !setsEqual(actualKeys, currentRequired) &&
      !setsEqual(actualKeys, structuredRequired) &&
      !setsEqual(actualKeys, finalRequired) &&
      !setsEqual(actualKeys, releaseRequired);
    const structuredPlan =
      setsEqual(actualKeys, structuredRequired) ||
      setsEqual(actualKeys, finalRequired) ||
      setsEqual(actualKeys, releaseRequired);
    const finalPlan =
      setsEqual(actualKeys, finalRequired) || setsEqual(actualKeys, releaseRequired);
    const releasePlan = setsEqual(actualKeys, releaseRequired);
    const minimalPlan = setsEqual(actualKeys, minimalRequired);
    if (
      releasePlan !== (payload.review_contract_version === 6) ||
      (releasePlan &&
        (!assessmentIsValid(payload.semver_assessment) ||
          !codeReviewLabelReviewIsValid(payload.label_review) ||
          ((payload.label_review as Record<string, unknown>).semver as Record<string, unknown>)
            .impact !== payload.semver_impact))
    ) {
      throw new WorkflowError("review plan SemVer assessment is invalid");
    }
    const listKeys = [
      "finding_publications",
      "previous_finding_assessments",
      "recommended_issues",
      "finding_ledger",
      "publication_ledger",
      "rejected_candidates",
      "rejected_candidate_assessments",
      "rejected_candidate_ledger",
    ];
    const version = payload.review_contract_version as number | undefined;
    const invalid =
      payload.profile !== "code-review" ||
      (!legacyPlan &&
        (structuredPlan ? ![2, 3, 4, 5, 6].includes(version as number) : version !== 1)) ||
      finalPlan !== [4, 5, 6].includes(version as number) ||
      payload.external_mutations !== false ||
      !["evidence_digest", "context_digest", "decision_digest"].every((key) =>
        isDigest(payload[key]),
      ) ||
      !isDict(payload.target) ||
      !["author", "reviewer"].includes(payload.role as string) ||
      !(legacyPlan
        ? ["fast", "normal", "deep"].includes(payload.mode as string)
        : ["fast", "normal", "deep", "incremental", "unchanged"].includes(
            payload.mode as string,
          )) ||
      (!legacyPlan && !incrementalReviewIsValid(payload.incremental)) ||
      !["ready", "not_ready", "blocked"].includes(payload.verdict as string) ||
      typeof payload.complete !== "boolean" ||
      !["summary", "architecture_assessment"].every((key) => nonemptyString(payload[key])) ||
      !["major", "minor", "patch", "none", "not_applicable", "unknown"].includes(
        payload.semver_impact as string,
      ) ||
      !Array.isArray(payload.checks) ||
      !(payload.checks as unknown[]).every((item) => nonemptyString(item)) ||
      !(minimalPlan
        ? findingsAreValid(payload.findings)
        : detailedFindingsAreValid(payload.findings)) ||
      !threadDecisionsAreValid(payload.thread_decisions) ||
      (structuredPlan &&
        (!codeReviewLabelReviewIsValid(payload.label_review) ||
          (version === 2 &&
            !(payload.thread_decisions as unknown[]).every(
              (item) => isDict(item) && "suggestion_applicable" in item,
            )) ||
          ([3, 4, 5, 6].includes(version as number) &&
            (!findingPublicationsAreValid(payload.finding_publications, true) ||
              !(payload.thread_decisions as unknown[]).every(
                (item) =>
                  isDict(item) &&
                  ["fix_mode", "patch", "patch_path", "patch_sha256"].every((key) => key in item),
              ))))) ||
      (!legacyPlan && !listKeys.every((key) => Array.isArray(payload[key]))) ||
      (!legacyPlan && !isDict(payload.presentation)) ||
      (finalPlan && !reviewChatAssessmentIsValid(payload.chat_assessment)) ||
      (finalPlan && !["en", "ru"].includes(payload.locale as string)) ||
      typeof payload.markdown !== "string" ||
      (!minimalPlan && payload.semver_impact === "unknown") ||
      (!minimalPlan && !nonemptyString(payload.semver_rationale)) ||
      (!minimalPlan && !mrMetadataAssessmentIsValid(payload.mr_metadata_assessment)) ||
      (!minimalPlan && !reviewPublicationPreviewIsValid(payload.publication_preview));
    if (invalid) {
      throw new WorkflowError("review plan payload is schema-invalid");
    }
  } else if (kind === "analysis_report" || kind === "critic_receipt") {
    const requiredReport = new Set([
      "schema",
      "evidence_digest",
      "run_id",
      "session_id",
      "findings",
      "external_mutations",
    ]);
    const payloadKeys = keySet(payload);
    if (
      !setsEqual(payloadKeys, requiredReport) &&
      !setsEqual(payloadKeys, new Set([...requiredReport, "scope_digest"])) &&
      !setsEqual(payloadKeys, new Set([...requiredReport, "target_finding_ids"])) &&
      !setsEqual(payloadKeys, new Set([...requiredReport, "scope_digest", "target_finding_ids"]))
    ) {
      throw new WorkflowError(`${kind} payload has unknown or missing fields`);
    }
    const expected = kind === "analysis_report" ? "analysis-report" : "critic-receipt";
    if (
      payload.schema !== `portable-gitlab/${expected}/v2` ||
      !isDigest(payload.evidence_digest) ||
      !["run_id", "session_id"].every((key) => nonemptyString(payload[key])) ||
      !findingsAreValid(payload.findings) ||
      payload.external_mutations !== false ||
      ("scope_digest" in payload && !isDigest(payload.scope_digest)) ||
      ("target_finding_ids" in payload &&
        (!Array.isArray(payload.target_finding_ids) ||
          !(payload.target_finding_ids as unknown[]).every((item) => nonemptyString(item))))
    ) {
      throw new WorkflowError(`${kind} payload is schema-invalid`);
    }
  } else if (kind === "review_decision") {
    const required = new Set([
      "schema",
      "evidence_digest",
      "finalize_digest",
      "mode",
      "external_mutations",
      "verdict",
      "run_id",
      "session_id",
      "findings",
      "unresolved_threads",
      "responses",
    ]);
    const optional = new Set([
      "context_digest",
      "critic_receipt_digest",
      "low_risk",
      "blocking_findings",
      "critic_findings",
      "accepted_findings",
      "critic_target_finding_ids",
      "blocking_finding_ids",
      "owner_decision_reasons",
      "ci_job_assessments",
    ]);
    const allowed = new Set([...required, ...optional]);
    const payloadKeys = keySet(payload);
    if (
      ![...required].every((key) => payloadKeys.has(key)) ||
      ![...payloadKeys].every((key) => allowed.has(key))
    ) {
      throw new WorkflowError("review decision payload has unknown or missing fields");
    }
    const responses = payload.responses;
    if (
      payload.schema !== "portable-gitlab/review-decision/v2" ||
      !isDigest(payload.evidence_digest) ||
      !isDigest(payload.finalize_digest) ||
      ("context_digest" in payload && !isDigest(payload.context_digest)) ||
      ("critic_receipt_digest" in payload &&
        payload.critic_receipt_digest !== null &&
        payload.critic_receipt_digest !== undefined &&
        !isDigest(payload.critic_receipt_digest)) ||
      !["fast", "normal", "deep", "incremental", "unchanged"].includes(payload.mode as string) ||
      !["ready", "not_ready", "blocked"].includes(payload.verdict as string) ||
      !["run_id", "session_id"].every((key) => nonemptyString(payload[key])) ||
      !findingsAreValid(payload.findings) ||
      ("critic_findings" in payload && !detailedFindingsAreValid(payload.critic_findings)) ||
      ("accepted_findings" in payload && !detailedFindingsAreValid(payload.accepted_findings)) ||
      ("critic_target_finding_ids" in payload &&
        (!Array.isArray(payload.critic_target_finding_ids) ||
          !(payload.critic_target_finding_ids as unknown[]).every((item) =>
            nonemptyString(item),
          ))) ||
      ("blocking_finding_ids" in payload &&
        (!Array.isArray(payload.blocking_finding_ids) ||
          !(payload.blocking_finding_ids as unknown[]).every((item) => nonemptyString(item)) ||
          (payload.blocking_finding_ids as string[]).length !==
            new Set(payload.blocking_finding_ids as string[]).size)) ||
      ("owner_decision_reasons" in payload &&
        (!Array.isArray(payload.owner_decision_reasons) ||
          !(payload.owner_decision_reasons as unknown[]).every((item) => nonemptyString(item)))) ||
      ("ci_job_assessments" in payload &&
        (!Array.isArray(payload.ci_job_assessments) ||
          !(payload.ci_job_assessments as unknown[]).every((entry) => {
            const item = entry;
            return (
              isDict(item) &&
              setsEqual(
                keySet(item),
                new Set([
                  "project_id",
                  "pipeline_id",
                  "job_id",
                  "classification",
                  "rationale",
                  "trace_evidence",
                ]),
              ) &&
              ["project_id", "pipeline_id", "job_id"].every((key) => isPlainInt(item[key])) &&
              ["process_gate", "code_failure", "infrastructure_failure", "unknown"].includes(
                item.classification as string,
              ) &&
              nonemptyString(item.rationale) &&
              nonemptyString(item.trace_evidence)
            );
          }))) ||
      !findingsAreValid(payload.unresolved_threads) ||
      !Array.isArray(responses) ||
      !(responses as unknown[]).every((entry) => {
        const item = entry;
        return (
          isDict(item) &&
          setsEqual(keySet(item), new Set(["id", "decision", "reason"])) &&
          nonemptyString(item.id) &&
          ["accept", "reject"].includes(item.decision as string) &&
          nonemptyString(item.reason)
        );
      }) ||
      ("low_risk" in payload && typeof payload.low_risk !== "boolean") ||
      ("blocking_findings" in payload && typeof payload.blocking_findings !== "boolean") ||
      ("external_mutations" in payload && payload.external_mutations !== false)
    ) {
      throw new WorkflowError("review decision payload is schema-invalid");
    }
  } else if (kind === "release_readiness") {
    exactKeys(
      payload,
      new Set(["schema", "evidence_digest", "verdict", "readiness", "gates", "external_mutations"]),
      "release readiness payload",
    );
    const gates = payload.gates;
    if (
      payload.schema !== "portable-gitlab/release-readiness/v2" ||
      !isDigest(payload.evidence_digest) ||
      !["ready", "not_ready", "blocked"].includes(payload.verdict as string) ||
      typeof payload.readiness !== "boolean" ||
      payload.external_mutations !== false ||
      !isDict(gates) ||
      !setsEqual(
        keySet(gates),
        new Set(["semver", "compatibility", "migration", "rollback", "ci"]),
      ) ||
      !Object.values(gates).every((entry) => {
        const gate = entry;
        return (
          isDict(gate) &&
          setsEqual(keySet(gate), new Set(["status", "evidence", "range"])) &&
          ["passed", "failed", "blocked", "not_applicable"].includes(gate.status as string) &&
          Array.isArray(gate.evidence) &&
          (gate.evidence as unknown[]).length > 0 &&
          isDict(gate.range) &&
          setsEqual(keySet(gate.range), new Set(["base_sha", "start_sha", "head_sha"])) &&
          ["base_sha", "start_sha", "head_sha"].every((key) =>
            isSha((gate.range as Record<string, unknown>)[key], true),
          )
        );
      })
    ) {
      throw new WorkflowError("release readiness payload is schema-invalid");
    }
  } else if (kind === "finalize_report") {
    const allowed = new Set([
      "status",
      "changed",
      "head_sha",
      "complete",
      "evidence_digest",
      "evidence_kind",
      "evidence_fingerprint_digest",
      "publication_plan_digest",
      "external_mutations",
      "release_readiness_digest",
      "release_readiness_valid",
    ]);
    const required = new Set([
      "status",
      "changed",
      "complete",
      "evidence_digest",
      "evidence_kind",
      "evidence_fingerprint_digest",
      "external_mutations",
    ]);
    const payloadKeys = keySet(payload);
    if (
      ![...payloadKeys].every((key) => allowed.has(key)) ||
      ![...required].every((key) => payloadKeys.has(key))
    ) {
      throw new WorkflowError("finalize report payload has unknown or missing fields");
    }
    if (
      !["ok", "stale", "not_applicable"].includes(payload.status as string) ||
      !Array.isArray(payload.changed) ||
      !(payload.changed as unknown[]).every((item) => typeof item === "string") ||
      ("head_sha" in payload && !isSha(payload.head_sha, true)) ||
      typeof payload.complete !== "boolean" ||
      !isDigest(payload.evidence_digest) ||
      !["evidence_snapshot", "local_wip_snapshot"].includes(payload.evidence_kind as string) ||
      !isDigest(payload.evidence_fingerprint_digest) ||
      ("publication_plan_digest" in payload && !isDigest(payload.publication_plan_digest)) ||
      payload.external_mutations !== false ||
      ("release_readiness_digest" in payload && !isDigest(payload.release_readiness_digest)) ||
      ("release_readiness_valid" in payload && payload.release_readiness_valid !== true)
    ) {
      throw new WorkflowError("finalize report payload is schema-invalid");
    }
  } else {
    throw new WorkflowError("unknown artifact kind");
  }
}

export function allowedEndpoint(endpoint: string): boolean {
  if (
    fullMatch(
      "projects/[0-9]+/(?:releases|repository/tags)(?:\\?[^#]+)?|projects/[0-9]+/repository/branches/[^/?#]+",
      endpoint,
    )
  ) {
    return true;
  }
  return fullMatch(
    "(?:user|projects/(?:[^/?]+|[0-9]+/(?:labels|milestones|pipelines|issues)(?:\\?[^#]+)?|[0-9]+/pipelines/[1-9][0-9]*/(?:jobs|bridges)(?:\\?[^#]+)?|[0-9]+/jobs/[1-9][0-9]*/trace|[0-9]+/(?:issues|merge_requests)/[1-9][0-9]*(?:/(?:approvals|closes_issues|discussions|changes|commits|links|notes|pipelines))?(?:\\?[^#]+)?|[0-9]+/repository/tags/[^/?#]+|[0-9]+/repository/commits/[0-9a-fA-F]{1,128}/merge_requests(?:\\?[^#]+)?|[0-9]+/repository/commits/[^/?#]+|[0-9]+/repository/(?:tree|files/[^/?#]+)\\?[^#]+))",
    endpoint,
  );
}

export function glabJson(hostname: string, endpoint: string): unknown {
  if (!fullMatch("[a-z0-9.-]+", hostname) || !allowedEndpoint(endpoint)) {
    throw new WorkflowError("GitLab endpoint is outside the collection allowlist");
  }
  const glab = which("glab");
  if (glab === null) {
    throw new WorkflowError("glab is unavailable; install and authenticate it outside this skill");
  }
  const completed = spawnSync(glab, ["api", "--hostname", hostname, "--method", "GET", endpoint], {
    encoding: "utf8",
    timeout: 45_000,
    maxBuffer: Infinity,
  });
  if (completed.error !== undefined) {
    throw new WorkflowError("GitLab GET could not be completed");
  }
  if (completed.status !== 0) {
    throw new WorkflowError(
      `GitLab GET failed: ${(completed.stderr ?? "").trim() || String(completed.status)}`,
    );
  }
  if (Buffer.byteLength(completed.stdout ?? "", "utf8") > MAX_BYTES) {
    throw new WorkflowError("GitLab response exceeds the size limit");
  }
  try {
    return JSON.parse(completed.stdout ?? "");
  } catch {
    throw new WorkflowError("GitLab returned invalid JSON");
  }
}

async function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  return new Promise((resolve) => {
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, timeoutMs);
    child.on("exit", onExit);
  });
}

async function stopProcessGroup(child: ChildProcess): Promise<void> {
  if (child.pid !== undefined) {
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch (caught) {
      if ((caught as NodeJS.ErrnoException).code !== "ESRCH") {
        try {
          child.kill("SIGKILL");
        } catch {
          undefined;
        }
      }
    }
  }
  if (!(await waitForExit(child, PROCESS_CLEANUP_TIMEOUT_SECONDS * 1000))) {
    try {
      child.kill("SIGKILL");
    } catch {
      undefined;
    }
    if (!(await waitForExit(child, PROCESS_CLEANUP_TIMEOUT_SECONDS * 1000))) {
      throw new WorkflowError("GitLab job trace process could not be reaped");
    }
  }
}

export function traceBoundary(response: Buffer): [number, number] | null {
  const boundaries: [number, number][] = [];
  for (const separator of ["\r\n\r\n", "\n\n"]) {
    const position = response.indexOf(Buffer.from(separator, "latin1"));
    if (position >= 0) boundaries.push([position, separator.length]);
  }
  if (boundaries.length === 0) return null;
  return boundaries.reduce((best, candidate) => (candidate[0] < best[0] ? candidate : best));
}

export function splitGlabTraceResponse(response: Buffer): [Buffer, Buffer] | null {
  const boundary = traceBoundary(response);
  if (boundary === null) return null;
  const [position, length] = boundary;
  return [response.subarray(0, position), response.subarray(position + length)];
}

export async function streamedGlabTrace(
  arguments_: string[],
): Promise<{ stdout: Buffer; stderr: Buffer; tailDropped: boolean }> {
  if (process.platform === "win32") {
    throw new WorkflowError("GitLab job trace streaming requires POSIX process capabilities");
  }
  const child = spawn(arguments_[0], arguments_.slice(1), {
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = Buffer.alloc(0);
  let stderr = Buffer.alloc(0);
  let tailDropped = false;
  let stdoutDone = false;
  let stderrDone = false;
  let exitCode: number | null = null;
  const applyStdoutRules = (chunk: Buffer): void => {
    stdout = Buffer.concat([stdout, chunk]);
    const boundary = traceBoundary(stdout);
    if (boundary === null) {
      if (stdout.length > MAX_TRACE_HEADER_BYTES) {
        throw new WorkflowError("GitLab job trace response headers exceed the size limit");
      }
      return;
    }
    const [position, length] = boundary;
    if (position > MAX_TRACE_HEADER_BYTES) {
      throw new WorkflowError("GitLab job trace response headers exceed the size limit");
    }
    const excess = stdout.length - position - length - MAX_TRACE_BYTES;
    if (excess > 0) {
      stdout = Buffer.concat([
        stdout.subarray(0, position + length),
        stdout.subarray(position + length + excess),
      ]);
      tailDropped = true;
    }
  };
  try {
    if (child.stdout === null || child.stderr === null) {
      throw new WorkflowError("GitLab job trace streaming pipes are unavailable");
    }
    const outcome = await new Promise<number>((resolve, reject) => {
      let settled = false;
      const fail = (error: unknown): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      };
      const finish = (): void => {
        if (settled) return;
        if (stdoutDone && stderrDone && exitCode !== null) {
          settled = true;
          clearTimeout(timer);
          resolve(exitCode);
        }
      };
      const timer = setTimeout(
        () => fail(new WorkflowError("GitLab job trace request timed out")),
        TRACE_TIMEOUT_SECONDS * 1000,
      );
      child.stdout?.on("data", (chunk: Buffer) => {
        try {
          applyStdoutRules(chunk);
        } catch (error) {
          fail(error);
        }
      });
      child.stdout?.on("end", () => {
        stdoutDone = true;
        finish();
      });
      child.stdout?.on("error", (streamError: NodeJS.ErrnoException) => {
        fail(streamError);
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        stderr = Buffer.concat([stderr, chunk]);
        if (stderr.length > MAX_TRACE_HEADER_BYTES) {
          fail(new WorkflowError("GitLab job trace response exceeds the size limit"));
        }
      });
      child.stderr?.on("end", () => {
        stderrDone = true;
        finish();
      });
      child.stderr?.on("error", (streamError: NodeJS.ErrnoException) => {
        fail(streamError);
      });
      child.on("error", (spawnError: Error) => {
        fail(spawnError);
      });
      child.on("exit", (code) => {
        exitCode = code ?? (child.signalCode !== null ? -1 : 0);
        finish();
      });
    });
    if (outcome !== 0) {
      throw new WorkflowError(`GitLab job trace request failed with status ${outcome}`);
    }
    return { stdout: stdout, stderr: stderr, tailDropped: tailDropped };
  } catch (error) {
    if (error instanceof WorkflowError) throw error;
    throw new WorkflowError("GitLab job trace POSIX streaming is unavailable");
  } finally {
    await stopProcessGroup(child);
  }
}

export function parseGlabTrace(
  response: Buffer,
  tailDropped = false,
): { text: string; complete: boolean } {
  const responseParts = splitGlabTraceResponse(response);
  if (responseParts === null) {
    throw new WorkflowError("GitLab job trace response headers are unavailable");
  }
  const [headerBytes, body] = responseParts;
  if (headerBytes.length > MAX_TRACE_HEADER_BYTES || body.length > MAX_TRACE_BYTES) {
    throw new WorkflowError("GitLab job trace exceeds the response size limit");
  }
  const headers = headerBytes.toString("latin1").split(/\r\n|\r|\n|\v|\f|\x1c|\x1d|\x1e|\x85/);
  const statusMatch = headers.length > 0 ? /^HTTP\/\S+ ([0-9]{3})(?: .*)?$/.exec(headers[0]) : null;
  if (statusMatch === null) {
    throw new WorkflowError("GitLab job trace response status is unavailable");
  }
  const status = Number(statusMatch[1]);
  let contentRange: string | null = null;
  for (const line of headers.slice(1)) {
    if (line.toLowerCase().startsWith("content-range:")) {
      contentRange = line.split(":").slice(1).join(":").trim();
      break;
    }
  }
  let complete = status === 200 && contentRange === null && !tailDropped;
  if ((status === 200 || status === 206) && contentRange !== null) {
    const rangeMatch = /^bytes ([0-9]+)-([0-9]+)\/([0-9]+)$/.exec(contentRange);
    if (rangeMatch !== null) {
      const start = Number(rangeMatch[1]);
      const end = Number(rangeMatch[2]);
      const total = Number(rangeMatch[3]);
      complete = start === 0 && end + 1 === total && body.length === total;
    }
  } else if (status !== 200 && status !== 206) {
    throw new WorkflowError(`GitLab job trace request returned HTTP ${status}`);
  }
  return { text: body.toString("utf8"), complete: complete };
}

export async function glabText(
  hostname: string,
  endpoint: string,
): Promise<{ text: string; complete: boolean }> {
  if (!fullMatch("[a-z0-9.-]+", hostname) || !allowedEndpoint(endpoint)) {
    throw new WorkflowError("GitLab endpoint is outside the collection allowlist");
  }
  const glab = which("glab");
  if (glab === null) {
    throw new WorkflowError("glab is unavailable; install and authenticate it outside this skill");
  }
  const streamed = await streamedGlabTrace([
    glab,
    "api",
    "--hostname",
    hostname,
    "--method",
    "GET",
    "--include",
    "--header",
    `Range: bytes=-${MAX_TRACE_BYTES}`,
    endpoint,
  ]);
  return parseGlabTrace(streamed.stdout, streamed.tailDropped);
}

export function paginated(
  hostname: string,
  endpoint: string,
  maxPages = MAX_PAGES,
): Record<string, unknown> {
  const items: unknown[] = [];
  const seen = new Set<string>();
  const pageDigests = new Set<string>();
  const errors: string[] = [];
  let page = maxPages;
  for (let index = 1; index <= maxPages; index += 1) {
    page = index;
    const separator = endpoint.includes("?") ? "&" : "?";
    let value: unknown;
    try {
      value = glabJson(hostname, `${endpoint}${separator}per_page=100&page=${page}`);
    } catch (error) {
      if (error instanceof WorkflowError) {
        errors.push(error.message);
        break;
      }
      throw error;
    }
    if (!Array.isArray(value)) {
      errors.push("GitLab pagination response is not an array");
      break;
    }
    const pageDigest = digest(value);
    if (pageDigests.has(pageDigest)) {
      errors.push("GitLab pagination repeated a page");
      break;
    }
    pageDigests.add(pageDigest);
    for (const item of value) {
      const key = serializePython(item, ", ", ": ");
      if (!seen.has(key)) {
        seen.add(key);
        items.push(item);
      }
    }
    if (value.length < 100) {
      return {
        items: items,
        complete: true,
        errors: [],
        pages: page,
        truncated: false,
      };
    }
  }
  if (errors.length === 0) {
    errors.push("pagination protective limit reached");
  }
  return {
    items: items,
    complete: false,
    errors: errors,
    pages: errors.length === 0 ? maxPages : page,
    truncated: true,
  };
}

export function component(
  items: unknown[] | null = null,
  options: {
    complete?: boolean;
    errors?: string[] | null;
    pages?: number;
    truncated?: boolean;
  } = {},
): Record<string, unknown> {
  return {
    items: items ?? [],
    complete: options.complete ?? true,
    errors: options.errors ?? [],
    pages: options.pages ?? 0,
    truncated: options.truncated ?? false,
  };
}

export function selectExactPipeline(
  pipelines: Record<string, unknown>,
  headSha: string,
): Record<string, unknown> | null {
  const items = pipelines.items;
  if (!Array.isArray(items)) return null;
  const exact = items.filter((entry) => isDict(entry) && entry.sha === headSha) as Record<
    string,
    unknown
  >[];
  if (exact.length === 0) return null;
  const pipelineId = (item: Record<string, unknown>): number =>
    isPlainInt(item.id) ? (item.id as number) : -1;
  return exact.reduce((best, candidate) =>
    pipelineId(candidate) > pipelineId(best) ? candidate : best,
  );
}

export function traceExcerpt(value: string, sourceComplete = true): Record<string, unknown> {
  const sanitized = redact(value.replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")).replace(/\r/g, "");
  let encoded = Buffer.from(sanitized, "utf8");
  let text = sanitized;
  const truncated = !sourceComplete || encoded.length > MAX_TRACE_BYTES;
  if (truncated) {
    encoded = encoded.subarray(encoded.length - MAX_TRACE_BYTES);
    text = encoded.toString("utf8");
  }
  return {
    complete: !truncated,
    truncated: truncated,
    excerpt: text,
    sha256: sha256Text(value),
  };
}

export function pipelineJob(
  item: Record<string, unknown>,
  projectId: number,
  pipelineId: number,
): Record<string, unknown> {
  const fields = [
    "id",
    "name",
    "stage",
    "status",
    "allow_failure",
    "web_url",
    "created_at",
    "started_at",
    "finished_at",
    "duration",
    "queued_duration",
    "failure_reason",
  ];
  const result: Record<string, unknown> = { project_id: projectId, pipeline_id: pipelineId };
  for (const key of fields) {
    result[key] = item[key];
  }
  return result;
}

export async function collectPipelineJobs(
  hostname: string,
  projectId: number,
  pipeline: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const pipelineId = pipeline.id;
  if (!isPlainInt(pipelineId)) {
    return {
      complete: false,
      errors: ["selected pipeline has no numeric ID"],
      pipelines: [],
      truncated: true,
    };
  }
  type QueueEntry = [number, number, number, number | null];
  const queue: QueueEntry[] = [[projectId, pipelineId, 0, null]];
  const seen = new Set<string>();
  const collected: Record<string, unknown>[] = [];
  const errors: string[] = [];
  let traces = 0;
  let truncated = false;
  while (queue.length > 0) {
    const [currentProject, currentPipeline, depth, parentPipeline] = queue.shift() as QueueEntry;
    const identity = `${currentProject}:${currentPipeline}`;
    if (seen.has(identity)) continue;
    if (seen.size >= MAX_CI_PIPELINES) {
      errors.push("CI pipeline traversal limit reached");
      truncated = true;
      break;
    }
    seen.add(identity);
    const jobs = paginated(
      hostname,
      `projects/${currentProject}/pipelines/${currentPipeline}/jobs`,
      MAX_CI_JOB_PAGES,
    );
    const bridges = paginated(
      hostname,
      `projects/${currentProject}/pipelines/${currentPipeline}/bridges`,
      MAX_CI_JOB_PAGES,
    );
    const pipelineErrors = [...(jobs.errors as string[]), ...(bridges.errors as string[])];
    const normalizedJobs: Record<string, unknown>[] = [];
    for (const raw of [...(jobs.items as unknown[]), ...(bridges.items as unknown[])]) {
      if (!isDict(raw) || !isPlainInt(raw.id)) {
        pipelineErrors.push("GitLab returned invalid CI job metadata");
        continue;
      }
      const normalized = pipelineJob(raw, currentProject, currentPipeline);
      if (raw.status === "failed" || raw.status === "canceled") {
        if (traces >= MAX_CI_TRACES) {
          traces += 1;
          normalized.trace = {
            complete: false,
            truncated: true,
            excerpt: "",
            sha256: null,
          };
          truncated = true;
        } else {
          traces += 1;
          try {
            const trace = await glabText(
              hostname,
              `projects/${currentProject}/jobs/${raw.id}/trace`,
            );
            normalized.trace = traceExcerpt(trace.text, trace.complete);
          } catch (error) {
            if (!(error instanceof WorkflowError)) throw error;
            normalized.trace = {
              complete: false,
              truncated: true,
              excerpt: "",
              sha256: null,
            };
            pipelineErrors.push(error.message);
          }
        }
      }
      normalizedJobs.push(normalized);
    }
    for (const raw of bridges.items as unknown[]) {
      if (!isDict(raw) || !isDict(raw.downstream_pipeline)) continue;
      const downstream = raw.downstream_pipeline as Record<string, unknown>;
      const downstreamId = downstream.id;
      const downstreamProject = Object.hasOwn(downstream, "project_id")
        ? downstream.project_id
        : currentProject;
      if (!isPlainInt(downstreamId) || !isPlainInt(downstreamProject)) {
        pipelineErrors.push("downstream pipeline identity is incomplete");
        continue;
      }
      if (depth >= MAX_PIPELINE_DEPTH) {
        pipelineErrors.push("downstream pipeline depth limit reached");
        truncated = true;
        continue;
      }
      queue.push([downstreamProject, downstreamId, depth + 1, currentPipeline]);
    }
    collected.push({
      project_id: currentProject,
      pipeline_id: currentPipeline,
      parent_pipeline_id: parentPipeline,
      depth: depth,
      jobs: normalizedJobs,
      complete: jobs.complete === true && bridges.complete === true && pipelineErrors.length === 0,
      errors: pipelineErrors,
    });
    errors.push(...pipelineErrors);
  }
  return {
    complete: errors.length === 0 && !truncated,
    errors: errors,
    pipelines: collected,
    truncated: truncated,
  };
}

function iidMatches(observed: unknown, iid: number): boolean {
  return observed === null || observed === undefined || observed === iid;
}

function urlQuote(value: string): string {
  let quoted = "";
  for (const byte of Buffer.from(value, "utf8")) {
    const character = String.fromCharCode(byte);
    if (/[A-Za-z0-9_.\-~]/.test(character)) {
      quoted += character;
    } else {
      quoted += `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
    }
  }
  return quoted;
}

export async function collect(
  target: Record<string, unknown>,
  profile: string,
  options: { persist?: boolean; locale?: string } = {},
): Promise<Record<string, unknown>> {
  const persist = options.persist ?? true;
  if (!(profile in PROFILES)) throw new WorkflowError("workflow profile is unsafe");
  const iidValue = target.iid;
  if (!isPlainInt(iidValue)) throw new WorkflowError("GitLab target IID is invalid");
  const hostname = String(target.hostname);
  const projectPath = String(target.project_path);
  const kind = String(target.kind);
  const iid = iidValue;
  const projectResponse = glabJson(hostname, `projects/${urlQuote(projectPath)}`);
  if (!isDict(projectResponse) || !isPlainInt(projectResponse.id)) {
    throw new WorkflowError("GitLab project identity is incomplete");
  }
  const projectId = projectResponse.id;
  const identity: Record<string, unknown> = { ...target, project_id: projectId };
  const root = await stateDirectory(profile, identity);
  const labels = paginated(hostname, `projects/${projectId}/labels?include_ancestor_groups=true`);
  let bundle: Record<string, unknown>;
  if (kind === "new_issue") {
    bundle = {
      schema_version: ARTIFACT_VERSION,
      profile: profile,
      external_mutations: false,
      target: identity,
      project: {
        id: projectId,
        path: projectPath,
        path_with_namespace: projectPath,
        hostname: hostname,
      },
      object: {},
      labels: labels,
      changed_files: component(),
      commits: component(),
      pipelines: component(),
      discussions: component(),
      head_sha: null,
      base_sha: null,
      start_sha: null,
      artifact_root: root,
      prepared_at: new Date().toISOString(),
      components_complete: {
        project: true,
        labels: pythonTruthy(labels.complete),
        object: true,
        changed_files: true,
        commits: true,
        pipelines: true,
        discussions: true,
      },
    };
  } else {
    const objectValue = glabJson(hostname, `projects/${projectId}/${kind}/${iid}`);
    if (!isDict(objectValue) || !iidMatches(objectValue.iid, iid)) {
      throw new WorkflowError("GitLab target response is incomplete");
    }
    const discussions = paginated(hostname, `projects/${projectId}/${kind}/${iid}/discussions`);
    const refs: Record<string, unknown> = isDict(objectValue.diff_refs)
      ? (objectValue.diff_refs as Record<string, unknown>)
      : {};
    const headSha = refs.head_sha;
    const baseSha = refs.base_sha;
    const startSha = refs.start_sha;
    let changed = component();
    let commits = component();
    let pipelines = component();
    if (kind === "merge_requests") {
      try {
        const changesValue = glabJson(
          hostname,
          `projects/${projectId}/merge_requests/${iid}/changes`,
        );
        const overflow =
          isDict(changesValue) &&
          (changesValue.overflow === true || changesValue.changes_count === "1000+");
        if (
          isDict(changesValue) &&
          Array.isArray(changesValue.changes) &&
          !overflow &&
          equalJson(changesValue.diff_refs, refs)
        ) {
          changed = component(changesValue.changes as unknown[], { pages: 1 });
        } else {
          changed = component(undefined, {
            complete: false,
            errors: ["GitLab changed-files response is incomplete, stale, or overflowed"],
            pages: 1,
            truncated: true,
          });
        }
      } catch (error) {
        if (!(error instanceof WorkflowError)) throw error;
        changed = component(undefined, {
          complete: false,
          errors: [error.message],
          truncated: true,
        });
      }
      if (
        ![baseSha, startSha, headSha].every((value) => typeof value === "string" && value !== "")
      ) {
        changed = component(changed.items as unknown[], {
          complete: false,
          errors: [...(changed.errors as string[]), "exact diff refs are unavailable"],
          pages: changed.pages as number,
          truncated: true,
        });
      }
      if (typeof headSha === "string" && headSha !== "") {
        commits = paginated(hostname, `projects/${projectId}/merge_requests/${iid}/commits`);
        if (!(commits.items as unknown[]).some((entry) => isDict(entry) && entry.id === headSha)) {
          commits = component(commits.items as unknown[], {
            complete: false,
            errors: [...(commits.errors as string[]), "commits do not bind exact head SHA"],
            pages: commits.pages as number,
            truncated: true,
          });
        }
        const pipelineEndpoint =
          profile === "code-review"
            ? `projects/${projectId}/merge_requests/${iid}/pipelines`
            : `projects/${projectId}/pipelines?sha=${urlQuote(headSha)}`;
        pipelines = paginated(hostname, pipelineEndpoint);
        if (profile === "code-review" && pipelines.complete === true) {
          const selectedPipeline = selectExactPipeline(pipelines, headSha);
          if (selectedPipeline !== null) {
            const jobEvidence = await collectPipelineJobs(
              hostname,
              projectId,
              selectedPipeline as Record<string, unknown>,
            );
            selectedPipeline.job_evidence = jobEvidence;
            if (jobEvidence.complete !== true) {
              pipelines = component(pipelines.items as unknown[], {
                complete: false,
                errors: [...(pipelines.errors as string[]), ...(jobEvidence.errors as string[])],
                pages: pipelines.pages as number,
                truncated: pythonTruthy(jobEvidence.truncated),
              });
            }
          }
        }
      } else {
        pipelines = component(undefined, {
          complete: false,
          errors: ["exact head SHA is unavailable"],
          truncated: true,
        });
        commits = component(undefined, {
          complete: false,
          errors: ["exact head SHA is unavailable"],
          truncated: true,
        });
      }
    }
    bundle = {
      schema_version: ARTIFACT_VERSION,
      profile: profile,
      external_mutations: false,
      target: identity,
      project: {
        id: projectId,
        path: projectPath,
        path_with_namespace: projectPath,
        hostname: hostname,
      },
      object: objectValue,
      labels: labels,
      changed_files: changed,
      commits: commits,
      pipelines: pipelines,
      discussions: discussions,
      head_sha: headSha,
      base_sha: baseSha,
      start_sha: startSha,
      artifact_root: root,
      prepared_at: new Date().toISOString(),
      components_complete: {
        project: true,
        labels: pythonTruthy(labels.complete),
        object: true,
        changed_files: pythonTruthy(changed.complete),
        commits: pythonTruthy(commits.complete),
        pipelines: pythonTruthy(pipelines.complete),
        discussions: pythonTruthy(discussions.complete),
      },
    };
  }
  const componentsComplete = bundle.components_complete as Record<string, unknown>;
  bundle.retrieval_complete = Object.values(componentsComplete).every((item) => pythonTruthy(item));
  if (persist) {
    const [artifactPath, artifactDigest] = await writeArtifact(root, "evidence_snapshot", bundle);
    if (!["mr-prepare", "release-prepare", "code-review"].includes(profile)) {
      writeJson(`${root}/current.json`, {
        evidence_path: artifactPath,
        evidence_digest: artifactDigest,
      });
    }
    bundle.preview_artifact_path = artifactPath;
    bundle.preview_digest = artifactDigest;
  }
  return bundle;
}

export function evidenceFromRoot(
  root: string,
  pointerName = "current.json",
): { source: string; payload: Record<string, unknown> } {
  if (pointerName !== "current.json" && pointerName !== "review-evidence.json") {
    throw new WorkflowError("collection state pointer name is invalid");
  }
  try {
    const pointer = readJson(`${root}/${pointerName}`, "collection state");
    const path = pointer.evidence_path;
    if (typeof path !== "string") {
      throw new WorkflowError("collection state has no evidence snapshot");
    }
    if (parentPath(parentPath(parentPath(normalizeLiteral(path)))) !== normalizeLiteral(root)) {
      throw new WorkflowError("evidence snapshot escapes collection root");
    }
    const [, payload] = artifactPayload(path, "evidence_snapshot");
    return { source: path, payload: payload };
  } catch (error) {
    if (!(error instanceof WorkflowError)) throw error;
    if (pointerName !== "current.json") throw error;
    const source = `${root}/bundle.json`;
    const [, payload] = artifactPayload(source, "evidence_snapshot");
    return { source: source, payload: payload };
  }
}

export function markedPreview(label: string, value: string): string {
  const separator = value.endsWith("\n") ? "" : "\n";
  return `<!-- ${label} START -->\n${value}${separator}<!-- ${label} END -->`;
}

export function templateHeadings(body: string): string[] {
  return body.match(/^#{1,6}\s+.+$/gm) ?? [];
}

export function pipelineSummary(
  bundle: Record<string, unknown>,
): [string, Record<string, unknown> | null] {
  const pipelines = bundle.pipelines;
  const headSha = bundle.head_sha;
  if (!isDict(pipelines) || pipelines.complete !== true) {
    return ["unverified: collection incomplete", null];
  }
  if (typeof headSha !== "string" || headSha === "") {
    return ["unverified: exact head SHA unavailable", null];
  }
  if (!Array.isArray(pipelines.items)) {
    return ["unverified: pipeline data invalid", null];
  }
  const pipeline = selectExactPipeline(pipelines, headSha);
  if (pipeline === null) {
    return ["missing", null];
  }
  const rawStatus = pipeline.status;
  if (["success", "running", "failed", "canceled"].includes(rawStatus as string)) {
    return [String(rawStatus), pipeline];
  }
  if (["created", "waiting_for_resource", "preparing", "pending"].includes(rawStatus as string)) {
    return ["running", pipeline];
  }
  return [`unsupported raw state: ${pythonStr(rawStatus)}`, pipeline];
}

export function labelMarkdownCell(cellValue: unknown): string {
  let value = cellValue;
  if (Array.isArray(value)) {
    const joined = value.map(pythonStr).join(", ");
    value = joined === "" ? "none" : joined;
  }
  if (value === null || value === undefined) {
    value = "none";
  }
  return pythonStr(value).replace(/\|/g, "\\|").replace(/\n/g, " ");
}

export function labelReviewMarkdown(labelReview: Record<string, unknown>): string[] {
  const lines = [
    "",
    "## Semantic label review",
    "",
    `- Completeness: \`${labelReview.complete ? "complete" : "unresolved"}\``,
    `- Current: ${labelMarkdownCell(labelReview.current)}`,
    `- Proposed: ${labelMarkdownCell(labelReview.proposed)}`,
    `- Add: ${labelMarkdownCell(labelReview.add)}`,
    `- Remove: ${labelMarkdownCell(labelReview.remove)}`,
    "",
    "| Semantic role | Intent | Current labels | Desired label | Action | Reason |",
    "|---|---|---|---|---|---|",
  ];
  for (const decision of labelReview.decisions as Record<string, unknown>[]) {
    lines.push(
      `| ${["role", "intent", "current", "desired_label", "action", "reason"]
        .map((key) => labelMarkdownCell(decision[key]))
        .join(" | ")} |`,
    );
  }
  if ((labelReview.unresolved as string[]).length > 0) {
    lines.push("", "Unresolved semantic intents:");
    for (const value of labelReview.unresolved as string[]) {
      lines.push(`- ${value}`);
    }
  }
  lines.push("", "This is a read-only delta. No label mutation command was generated or executed.");
  return lines;
}

export function publicationMarkdown(
  bundle: Record<string, unknown>,
  content: Record<string, unknown>,
  inventory: Record<string, unknown> | null = null,
  labelReview: Record<string, unknown> | null = null,
): string {
  const target = isDict(bundle.target) ? bundle.target : {};
  const profile = bundle.profile;
  if (profile !== "mr-prepare" && profile !== "release-prepare") {
    return (
      [
        "# Verified publication plan",
        "",
        `- Target: ${pythonStr(getPath(target, "url", "local"))}`,
        `- Base SHA: ${bundle.base_sha || "not applicable"}`,
        `- Start SHA: ${bundle.start_sha || "not applicable"}`,
        `- Head SHA: ${bundle.head_sha || "not applicable"}`,
        `- Collection completeness: ${pythonTruthy(bundle.retrieval_complete) ? "complete" : "partial"}`,
        "- `external_mutations=false`: this plan does not perform or propose automated publish/resolve/approve/merge operations.",
        "",
        "## Proposed text",
        "",
        `### Title\n\n${content.title || "No changes."}`,
        `\n### Description\n\n${content.description || "No changes."}`,
        "",
        "Before manual publication, run `finalize`; stale or incomplete evidence blocks ready.",
      ].join("\n") + "\n"
    );
  }
  const objectValue = bundle.object;
  if (!isDict(objectValue)) {
    throw new WorkflowError("evidence object is invalid");
  }
  if (labelReview === null) {
    throw new WorkflowError("publication plan requires a semantic label review");
  }
  const currentTitle = objectValue.title;
  const rawDescription = objectValue.description;
  if (
    typeof currentTitle !== "string" ||
    (rawDescription !== null && rawDescription !== undefined && typeof rawDescription !== "string")
  ) {
    throw new WorkflowError("current title or description is invalid");
  }
  const currentDescription = pythonTruthy(rawDescription) ? (rawDescription as string) : "";
  const proposedTitle = content.title;
  const proposedDescription = content.description;
  const [pipelineStatus, pipeline] = pipelineSummary(bundle);
  const pipelineId = pipeline !== null ? pipeline.id : null;
  let releaseDetails: string[] = [];
  let releaseSections: string[] = [];
  if (profile === "release-prepare") {
    if (inventory === null) {
      throw new WorkflowError("release publication plan requires an inventory");
    }
    releaseDetails = [
      `- Release version: \`v${content.version}\``,
      `- Previous boundary: ${inventory.previous_ref || "first release"}`,
      `- Previous SHA: ${inventory.previous_sha || "not applicable"}`,
      `- Release range: \`${inventory.revision_range}\``,
      `- Inventory completeness: ${pythonTruthy(inventory.complete) ? "complete" : "partial"}`,
    ];
    releaseSections = [
      "",
      "## Announcement",
      "",
      markedPreview("ANNOUNCEMENT", content.announcement as string),
      "",
      "## Illustration prompt",
      "",
      markedPreview("ILLUSTRATION PROMPT", content.illustration_prompt as string),
    ];
  }
  return (
    [
      "# Verified publication plan",
      "",
      `- Target: ${pythonStr(getPath(target, "url", "local"))}`,
      `- Base SHA: ${bundle.base_sha || "not applicable"}`,
      `- Start SHA: ${bundle.start_sha || "not applicable"}`,
      `- Head SHA: ${bundle.head_sha || "not applicable"}`,
      `- Collection completeness: ${pythonTruthy(bundle.retrieval_complete) ? "complete" : "partial"}`,
      `- Pipeline status for exact head SHA: \`${pipelineStatus}\``,
      `- Pipeline ID: ${pipelineId !== null && pipelineId !== undefined ? pipelineId : "not applicable"}`,
      ...releaseDetails,
      "- `external_mutations=false`: this plan does not perform or propose automated publish/resolve/approve/merge operations.",
      "",
      "## Title",
      "",
      `- Decision: \`${currentTitle !== proposedTitle ? "change" : "keep"}\``,
      "",
      "### Current title",
      "",
      markedPreview("CURRENT TITLE", currentTitle),
      "",
      "### Proposed title",
      "",
      markedPreview("PROPOSED TITLE", proposedTitle as string),
      "",
      "## Description",
      "",
      `- Decision: \`${currentDescription !== proposedDescription ? "change" : "keep"}\``,
      "",
      "### Current description",
      "",
      markedPreview("CURRENT DESCRIPTION", currentDescription),
      "",
      "### Proposed description",
      "",
      markedPreview("PROPOSED DESCRIPTION", proposedDescription as string),
      ...labelReviewMarkdown(labelReview),
      ...releaseSections,
      "",
      "Before manual publication, run `finalize` with the stable plan pointer and binding returned by scaffold; stale or incomplete evidence blocks readiness.",
    ].join("\n") + "\n"
  );
}

export function fingerprint(bundle: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  if (bundle.profile === "mr-prepare") {
    result.mr_project = bundle.project;
  }
  result.target = bundle.target;
  result.head_sha = bundle.head_sha;
  result.base_sha = bundle.base_sha;
  result.start_sha = bundle.start_sha;
  result.object = bundle.object;
  result.labels = bundle.labels;
  result.discussions = bundle.discussions;
  result.changed_files = bundle.changed_files;
  result.commits = bundle.commits;
  result.pipelines = bundle.pipelines;
  result.retrieval_complete = bundle.retrieval_complete;
  return result;
}

export async function finalize(
  rootValue: string,
  pointerName = "current.json",
): Promise<Record<string, unknown>> {
  const root = await artifactRoot(rootValue);
  const { source, payload: baseline } = evidenceFromRoot(root, pointerName);
  const target = baseline.target;
  if (!isDict(target)) {
    throw new WorkflowError("evidence target is missing");
  }
  if (target.kind === "new_issue") {
    return {
      status: "not_applicable",
      changed: [],
      complete: baseline.retrieval_complete,
      evidence_digest: contentDigest(readFileSync(source)),
    };
  }
  const current = await collect(target, pythonStr(getPath(baseline, "profile", "task-triage")), {
    persist: false,
  });
  const before = fingerprint(baseline);
  const after = fingerprint(current);
  const changed = Object.keys(before).filter((name) => !equalJson(before[name], after[name]));
  return {
    status: changed.length === 0 && pythonTruthy(current.retrieval_complete) ? "ok" : "stale",
    changed: changed,
    head_sha: current.head_sha,
    complete: current.retrieval_complete,
    evidence_digest: contentDigest(readFileSync(source)),
  };
}

export function gitRead(root: string, args: string[], text = true): string | Buffer {
  const git = which("git");
  if (git === null) {
    throw new WorkflowError("git is unavailable");
  }
  const completed = spawnSync(git, ["-C", root, ...args], {
    encoding: text ? "utf8" : "buffer",
    maxBuffer: Infinity,
  });
  if (completed.error !== undefined) {
    throw completed.error;
  }
  if (completed.status !== 0) {
    throw new WorkflowError("local Git input can no longer be read");
  }
  return completed.stdout as string | Buffer;
}

export function validateCritic(
  receipt: Record<string, unknown>,
  evidenceDigest: string,
  scopeDigest: string | null = null,
): void {
  const required = new Set([
    "schema",
    "evidence_digest",
    "run_id",
    "session_id",
    "findings",
    "external_mutations",
  ]);
  const allowed = new Set([...required, "scope_digest", "target_finding_ids"]);
  const keys = keySet(receipt);
  const targetFindingIds = receipt.target_finding_ids;
  if (
    receipt.schema !== "portable-gitlab/critic-receipt/v2" ||
    ![...required].every((key) => keys.has(key)) ||
    ![...keys].every((key) => allowed.has(key)) ||
    receipt.evidence_digest !== evidenceDigest ||
    (scopeDigest !== null && receipt.scope_digest !== scopeDigest) ||
    (scopeDigest !== null && !Array.isArray(targetFindingIds)) ||
    (scopeDigest === null && "scope_digest" in receipt && !isDigest(receipt.scope_digest)) ||
    !findingsAreValid(receipt.findings) ||
    ("target_finding_ids" in receipt &&
      (!Array.isArray(targetFindingIds) ||
        !(targetFindingIds as unknown[]).every((item) => nonemptyString(item)) ||
        (targetFindingIds as string[]).length !== new Set(targetFindingIds as string[]).size)) ||
    receipt.external_mutations !== false
  ) {
    throw new WorkflowError("critic receipt is schema-invalid or does not bind evidence");
  }
  if (!["run_id", "session_id"].every((key) => typeof receipt[key] === "string" && receipt[key])) {
    throw new WorkflowError("critic receipt lacks independent run identity");
  }
}

export function validateDecision(
  report: Record<string, unknown>,
  evidenceDigest: string,
  receipt: Record<string, unknown> | null,
  mode: string,
  contextDigest: string | null = null,
  criticReceiptDigest: string | null = null,
): void {
  if (
    report.schema !== "portable-gitlab/review-decision/v2" ||
    report.evidence_digest !== evidenceDigest ||
    (contextDigest !== null && report.context_digest !== contextDigest) ||
    (report.critic_receipt_digest ?? null) !== criticReceiptDigest ||
    !isDigest(report.finalize_digest) ||
    report.mode !== mode ||
    report.external_mutations !== false ||
    !["ready", "not_ready", "blocked"].includes(report.verdict as string) ||
    !Array.isArray(report.responses) ||
    !Array.isArray(report.unresolved_threads)
  ) {
    throw new WorkflowError("review decision is schema-invalid");
  }
  const responseValues = report.responses as Record<string, unknown>[];
  const responseIds = new Set<unknown>(
    responseValues
      .filter(
        (item) =>
          isDict(item) &&
          ["accept", "reject"].includes(item.decision as string) &&
          typeof item.reason === "string" &&
          item.reason !== "",
      )
      .map((item) => item.id),
  );
  const findingSubjects = [
    ...((Array.isArray(report.findings) ? (report.findings as unknown[]) : []) as unknown[]),
    ...(receipt !== null && Array.isArray(receipt.findings) ? (receipt.findings as unknown[]) : []),
  ].filter((item) => isDict(item)) as Record<string, unknown>[];
  const findingIds = new Set<unknown>(findingSubjects.map((item) => item.id));
  const required = new Set<unknown>(findingIds);
  if (receipt !== null && Array.isArray(receipt.findings)) {
    for (const item of receipt.findings as unknown[]) {
      if (isDict(item)) required.add(item.id);
    }
  }
  for (const item of report.unresolved_threads as unknown[]) {
    if (isDict(item)) required.add(item.id);
  }
  if (contextDigest !== null) {
    const threadIds = new Set<unknown>(
      (report.unresolved_threads as unknown[])
        .filter((item) => isDict(item))
        .map((item) => (item as Record<string, unknown>).id),
    );
    if (
      findingIds.size !== findingSubjects.length ||
      [...findingIds].some(
        (itemId) =>
          typeof itemId !== "string" || !fullMatch("[A-Za-z0-9][A-Za-z0-9._-]{0,63}", itemId),
      ) ||
      [...threadIds].some(
        (itemId) =>
          typeof itemId !== "string" ||
          !fullMatch("thread:[A-Za-z0-9][A-Za-z0-9._-]{0,127}", itemId),
      ) ||
      [...findingIds].some((itemId) => threadIds.has(itemId))
    ) {
      throw new WorkflowError("code-review finding and thread subjects are not namespace-safe");
    }
  }
  if (
    required.has(null) ||
    required.has(undefined) ||
    responseIds.size !== responseValues.length ||
    !setsEqual(responseIds, required)
  ) {
    throw new WorkflowError(
      "review decision does not account for every finding and unresolved thread",
    );
  }
  const responseById = new Map<unknown, Record<string, unknown>>(
    responseValues.map((item) => [item.id, item]),
  );
  const acceptedFindings = findingSubjects.filter(
    (item) => (responseById.get(item.id) as Record<string, unknown>).decision === "accept",
  );
  if (duplicateDetailedFindingIds(acceptedFindings).length > 0) {
    throw new WorkflowError("review decision accepts structurally duplicate findings");
  }
  if (["normal", "deep", "incremental"].includes(mode) && receipt === null) {
    throw new WorkflowError(
      "normal, deep, and incremental review require an independent critic receipt",
    );
  }
  if (mode === "fast" && report.low_risk !== true && receipt === null) {
    throw new WorkflowError("fast review without critic requires confirmed low-risk scope");
  }
  if (report.verdict === "ready" && report.blocking_findings === true) {
    throw new WorkflowError("blocking findings prohibit ready");
  }
}

export function validateReleaseReadiness(
  report: Record<string, unknown>,
  bundle: Record<string, unknown>,
  evidenceDigest: string,
): void {
  const required = new Set(["semver", "compatibility", "migration", "rollback", "ci"]);
  const gates = report.gates;
  if (
    report.schema !== "portable-gitlab/release-readiness/v2" ||
    !setsEqual(
      keySet(report),
      new Set(["schema", "evidence_digest", "verdict", "readiness", "gates", "external_mutations"]),
    ) ||
    report.evidence_digest !== evidenceDigest ||
    !["ready", "not_ready", "blocked"].includes(report.verdict as string) ||
    typeof report.readiness !== "boolean" ||
    report.external_mutations !== false ||
    !isDict(gates) ||
    !setsEqual(keySet(gates), required)
  ) {
    throw new WorkflowError("release readiness report is schema-invalid");
  }
  const identity = {
    base_sha: bundle.base_sha,
    start_sha: bundle.start_sha,
    head_sha: bundle.head_sha,
  };
  for (const gateEntry of Object.values(gates)) {
    const gate = gateEntry;
    if (
      !isDict(gate) ||
      !["passed", "failed", "blocked", "not_applicable"].includes(gate.status as string) ||
      !Array.isArray(gate.evidence) ||
      (gate.evidence as unknown[]).length === 0 ||
      !equalJson(gate.range, identity)
    ) {
      throw new WorkflowError("release readiness gate does not bind exact range and evidence");
    }
  }
  if (
    (report.verdict === "ready") !== (report.readiness === true) ||
    !pythonTruthy(bundle.retrieval_complete)
  ) {
    throw new WorkflowError(
      "incomplete evidence or readiness disagreement prohibits release ready",
    );
  }
  if (
    report.readiness === true &&
    Object.values(gates).some(
      (gate) => !isDict(gate) || (gate as Record<string, unknown>).status !== "passed",
    )
  ) {
    throw new WorkflowError("an unclosed release gate prohibits ready");
  }
}

export function finalizePayload(
  result: Record<string, unknown>,
  source: string,
  evidence: Record<string, unknown>,
  kind: string,
): Record<string, unknown> {
  return {
    ...result,
    external_mutations: false,
    evidence_digest: contentDigest(readFileSync(source)),
    evidence_kind: kind,
    evidence_fingerprint_digest: digest(
      kind === "evidence_snapshot" ? fingerprint(evidence) : evidence,
    ),
  };
}

export function validateFinalizeReport(
  path: string,
  evidencePath: string,
  evidence: Record<string, unknown>,
): [Record<string, unknown>, string] {
  const [document, report] = artifactPayload(path, "finalize_report");
  const reportDigest = contentDigest(readFileSync(regularFile(path, "finalize report")));
  const evidenceDigest = contentDigest(
    readFileSync(regularFile(evidencePath, "evidence snapshot")),
  );
  if (
    report.status !== "ok" ||
    report.complete !== true ||
    report.evidence_kind !== "evidence_snapshot" ||
    report.evidence_digest !== evidenceDigest ||
    report.evidence_fingerprint_digest !== digest(fingerprint(evidence)) ||
    document.kind !== "finalize_report"
  ) {
    throw new WorkflowError(
      "finalize report is stale, incomplete, or does not bind exact evidence",
    );
  }
  return [report, reportDigest];
}
