import { spawnSync } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { constants as fsConstants, type Stats } from "node:fs";
import {
  chmod,
  lstat,
  mkdir,
  open,
  readFile,
  realpath,
  rename,
  rm,
  stat,
  type FileHandle,
} from "node:fs/promises";
import { constants as osConstants, homedir } from "node:os";
import { basename, dirname } from "node:path";

export const HISTORY_HEADING = "## History";
export const MARKER_SCHEMA = "agent-skills/post-success-marker/v1";

const DIGEST_SOURCE = "[0-9a-f]{64}";
const SKILL_SOURCE = "[a-z][a-z0-9-]{0,63}";
const SNAPSHOT_LINE_PATTERN = /^- `([^`]+)`$/;
const EXECUTION_STATUS_PATTERN = /# execution-status=(?:not_run|run_unverified)\n/;
const TIMESTAMP_PATTERN =
  /^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[Zz]|[+-]\d{2}:?\d{2})$/;
const STRING_ESCAPES: Record<string, string> = {
  '"': '\\"',
  "\\": "\\\\",
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
};

export class StateArtifactError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StateArtifactError";
  }
}

export function canonicalJson(value: unknown): Buffer {
  return Buffer.from(canonical(value), "utf8");
}

function canonical(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      if (Number.isNaN(value)) return "NaN";
      return value > 0 ? "Infinity" : "-Infinity";
    }
    return String(value);
  }
  if (typeof value === "string") return quoteString(value);
  if (Array.isArray(value)) return `[${value.map((item) => canonical(item)).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    entries.sort((left, right) => compareCodePoints(left[0], right[0]));
    return `{${entries.map(([key, item]) => `${quoteString(key)}:${canonical(item)}`).join(",")}}`;
  }
  throw new Error(`unsupported canonical JSON value: ${typeof value}`);
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

export function contentDigest(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
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

function pythonStem(name: string): string {
  const index = name.lastIndexOf(".");
  return index > 0 && index < name.length - 1 ? name.slice(0, index) : name;
}

function pythonSuffix(name: string): string {
  const index = name.lastIndexOf(".");
  return index > 0 && index < name.length - 1 ? name.slice(index) : "";
}

function fullmatch(source: string, value: string): boolean {
  const match = new RegExp(`^(?:${source})$`).exec(value);
  return match !== null && match[0].length === value.length;
}

function missingEntry(target: string): NodeJS.ErrnoException {
  const error = new Error(
    `ENOENT: no such file or directory, stat '${target}'`,
  ) as NodeJS.ErrnoException;
  error.code = "ENOENT";
  return error;
}

function isWithinBoundary(pathParts: string[], boundaryParts: string[]): boolean {
  if (boundaryParts.length > pathParts.length) return false;
  return boundaryParts.every((part, index) => part === pathParts[index]);
}

async function openDirectorySafely(
  target: string,
  boundary: string,
  create: boolean,
): Promise<void> {
  const pathParts = posixParts(target);
  const boundaryParts = posixParts(boundary);
  if (
    [...pathParts.slice(1), ...boundaryParts.slice(1)].some(
      (part) => part === "" || part === "." || part === "..",
    )
  ) {
    throw new StateArtifactError("state path must be normalized");
  }
  if (!isWithinBoundary(pathParts, boundaryParts)) {
    throw new StateArtifactError("state path escapes its boundary");
  }
  if (!target.startsWith("/") || !boundary.startsWith("/")) {
    throw new StateArtifactError("state path must be absolute");
  }
  const nofollow = fsConstants.O_NOFOLLOW;
  const directoryFlag = fsConstants.O_DIRECTORY;
  if (nofollow === undefined || directoryFlag === undefined) {
    throw new StateArtifactError("safe state traversal is unsupported");
  }
  const owner = typeof process.getuid === "function" ? process.getuid() : undefined;
  const boundaryIndex = boundaryParts.length - 1;
  let current = "";
  for (let index = 1; index < pathParts.length; index += 1) {
    current = index === 1 ? `/${pathParts[index]}` : `${current}/${pathParts[index]}`;
    let created = false;
    let metadata = await lstatEntry(current);
    if (metadata === undefined) {
      if (!create) throw missingEntry(current);
      try {
        await mkdir(current, { mode: 0o700 });
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
          throw new StateArtifactError("state directory is unsafe");
        }
      }
      metadata = await lstatEntry(current);
      if (metadata === undefined) throw missingEntry(current);
      created = true;
    }
    if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
      throw new StateArtifactError("state directory is unsafe");
    }
    if (index >= boundaryIndex) {
      if (owner !== undefined && metadata.uid !== owner) {
        throw new StateArtifactError("state directory is unsafe");
      }
      if ((metadata.mode & 0o022) !== 0) {
        throw new StateArtifactError("state directory is not private");
      }
      if (created || (create && (metadata.mode & 0o077) !== 0)) {
        await chmod(current, 0o700);
      }
    }
  }
}

async function lstatEntry(target: string): Promise<Stats | undefined> {
  try {
    return await lstat(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw new StateArtifactError("state directory is unsafe");
  }
}

export async function ensurePrivateDirectory(target: string, boundary: string): Promise<string> {
  await openDirectorySafely(target, boundary, true);
  return target;
}

export async function inspectPrivateDirectory(target: string, boundary: string): Promise<string> {
  await openDirectorySafely(target, boundary, false);
  return target;
}

async function syncDirectory(target: string): Promise<void> {
  const handle = await open(target, fsConstants.O_RDONLY | (fsConstants.O_DIRECTORY ?? 0));
  try {
    await handle.sync();
  } finally {
    await handle.close();
  }
}

async function readRegularNoFollow(target: string): Promise<Buffer> {
  const handle = await open(target, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
  try {
    const metadata = await handle.stat();
    if (!metadata.isFile()) throw new StateArtifactError("state file is unsafe");
    return await handle.readFile();
  } finally {
    await handle.close();
  }
}

async function writeImmutableWithin(
  target: string,
  content: Buffer,
  boundary: string,
): Promise<void> {
  const directory = dirname(target);
  await openDirectorySafely(directory, boundary, true);
  const writeFlags =
    fsConstants.O_WRONLY | fsConstants.O_CREAT | fsConstants.O_EXCL | (fsConstants.O_NOFOLLOW ?? 0);
  let handle: FileHandle;
  try {
    handle = await open(target, writeFlags, 0o600);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    const existingHandle = await open(target, fsConstants.O_RDONLY | (fsConstants.O_NOFOLLOW ?? 0));
    try {
      const metadata = await existingHandle.stat();
      const existing = await existingHandle.readFile();
      if (!metadata.isFile() || !existing.equals(content)) {
        throw new StateArtifactError("immutable state history was changed");
      }
    } finally {
      await existingHandle.close();
    }
    return;
  }
  try {
    await handle.chmod(0o600);
    await handle.writeFile(content);
    await handle.sync();
    await syncDirectory(directory);
  } catch (error) {
    await rm(target, { force: true }).catch(() => undefined);
    await syncDirectory(directory).catch(() => undefined);
    throw error;
  } finally {
    await handle.close();
  }
}

async function readImmutableWithin(target: string, boundary: string): Promise<Buffer> {
  await openDirectorySafely(dirname(target), boundary, false);
  try {
    return await readRegularNoFollow(target);
  } catch (error) {
    if (error instanceof StateArtifactError) throw error;
    throw new StateArtifactError("state file is unsafe");
  }
}

async function readOptionalImmutableWithin(
  target: string,
  boundary: string,
): Promise<Buffer | null> {
  try {
    await openDirectorySafely(dirname(target), boundary, false);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
  try {
    return await readRegularNoFollow(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    if (error instanceof StateArtifactError) throw error;
    throw new StateArtifactError("state file is unsafe");
  }
}

export async function readImmutable(target: string, boundary: string): Promise<Buffer> {
  let present = false;
  try {
    await stat(target);
    present = true;
  } catch {
    present = false;
  }
  if (!present) throw missingEntry(target);
  return readImmutableWithin(target, boundary);
}

async function snapshot(history: string, suffix: string, content: Buffer): Promise<string> {
  const digest = contentDigest(content);
  const target = `${history}/${digest}${suffix}`;
  await writeImmutableWithin(target, content, dirname(history));
  return target;
}

async function managedHistoryExists(history: string): Promise<boolean> {
  try {
    await openDirectorySafely(history, dirname(history), false);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
  return true;
}

async function splitHistory(
  content: Buffer,
  history: string,
  managed: boolean,
): Promise<[Buffer, string[]]> {
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(content);
  } catch {
    throw new StateArtifactError("stable Markdown must be UTF-8");
  }
  const separator = `\n${HISTORY_HEADING}\n`;
  if (!managed || !text.includes(separator)) return [content, []];
  const separatorIndex = text.lastIndexOf(separator);
  const body = text.slice(0, separatorIndex);
  const footer = text.slice(separatorIndex + separator.length);
  const lines = footer
    .trim()
    .split(/\r\n|\r|\n/)
    .filter((line) => line !== "");
  const historyParent = dirname(history);
  const paths: string[] = [];
  for (const line of lines) {
    const match = SNAPSHOT_LINE_PATTERN.exec(line);
    if (match === null) {
      const legacySnapshot = `${history}/${contentDigest(content)}.md`;
      let archivedLegacy: Buffer | null = null;
      try {
        archivedLegacy = await readImmutableWithin(legacySnapshot, historyParent);
      } catch (error) {
        if (!(error instanceof StateArtifactError)) throw error;
      }
      if (archivedLegacy !== null && archivedLegacy.equals(content)) return [content, []];
      throw new StateArtifactError("stable Markdown history footer is malformed");
    }
    const entryParts = posixParts(match[1]);
    const name = entryParts[entryParts.length - 1];
    const stem = pythonStem(name);
    if (
      !match[1].startsWith("/") ||
      joinParts(entryParts.slice(0, -1)) !== history ||
      !fullmatch(DIGEST_SOURCE, stem) ||
      pythonSuffix(name) !== ".md"
    ) {
      throw new StateArtifactError("stable Markdown history path is invalid");
    }
    const snapshotPath = joinParts(entryParts);
    const snapshotContent = await readImmutableWithin(snapshotPath, historyParent);
    if (contentDigest(snapshotContent) !== stem) {
      throw new StateArtifactError("stable Markdown history snapshot changed");
    }
    if (paths.includes(snapshotPath)) {
      throw new StateArtifactError("stable Markdown history path is duplicated");
    }
    paths.push(snapshotPath);
  }
  return [Buffer.from(body, "utf8"), paths];
}

export async function versionedMarkdown(
  target: string,
  body: Buffer,
  options: { legacy?: Buffer | null } = {},
): Promise<Buffer> {
  const stable = normalizeLiteral(target);
  const name = basename(stable);
  if (pythonSuffix(name) !== ".md" || !stable.startsWith("/")) {
    throw new StateArtifactError("stable Markdown path must be an absolute .md path");
  }
  const link = await lstat(stable).catch(() => undefined);
  if (link !== undefined && link.isSymbolicLink()) {
    throw new StateArtifactError("stable Markdown path is unsafe");
  }
  const followed = await stat(stable).catch(() => undefined);
  if (followed !== undefined && !followed.isFile()) {
    throw new StateArtifactError("stable Markdown path is unsafe");
  }
  const content =
    body.length === 0 || body[body.length - 1] === 0x0a
      ? body
      : Buffer.concat([body, Buffer.from("\n")]);
  const historyDir = `${dirname(stable)}/history`;
  const history = `${historyDir}/${pythonStem(name)}`;
  let previous: string[] = [];
  if (followed !== undefined) {
    const existing = await readFile(stable);
    const managed = await managedHistoryExists(history);
    const [oldBody, prior] = await splitHistory(existing, history, managed);
    if (oldBody.equals(content)) return existing;
    const oldSnapshot = await snapshot(history, ".md", oldBody);
    previous = prior;
    if (!previous.includes(oldSnapshot)) previous.push(oldSnapshot);
  } else if (options.legacy != null) {
    const [legacyBody] = await splitHistory(options.legacy, history, false);
    const legacySnapshot = await snapshot(history, ".md", legacyBody);
    if (!legacyBody.equals(content)) previous = [legacySnapshot];
  }
  const footer = [HISTORY_HEADING, "", ...previous.map((item) => `- \`${item}\``)];
  await openDirectorySafely(history, historyDir, true);
  return Buffer.concat([content, Buffer.from(`\n${footer.join("\n")}\n`, "utf8")]);
}

export async function markdownBody(target: string): Promise<Buffer> {
  const stable = normalizeLiteral(target);
  const history = `${dirname(stable)}/history/${pythonStem(basename(stable))}`;
  const managed = await managedHistoryExists(history);
  const [body] = await splitHistory(await readFile(stable), history, managed);
  return body;
}

export async function archiveJson(target: string, body: Buffer, boundary: string): Promise<string> {
  const history = `${normalizeLiteral(boundary)}/history/${pythonStem(basename(target))}`;
  return snapshot(history, ".json", body);
}

export async function archiveBytes(
  boundary: string,
  stem: string,
  suffix: string,
  body: Buffer,
): Promise<string> {
  if (!fullmatch(SKILL_SOURCE, stem)) {
    throw new StateArtifactError("archive history stem is invalid");
  }
  if (suffix !== ".json" && suffix !== ".md") {
    throw new StateArtifactError("archive history suffix is unsupported");
  }
  const history = `${normalizeLiteral(boundary)}/history/${stem}`;
  return snapshot(history, suffix, body);
}

export function xdgStateHome(): string {
  const configured = process.env.XDG_STATE_HOME;
  const target = configured ? configured : `${homedir()}/.local/state`;
  const parts = posixParts(target);
  if (!target.startsWith("/") || parts.slice(1).some((part) => part === "..")) {
    throw new StateArtifactError("XDG_STATE_HOME must be an absolute normalized path");
  }
  return joinParts(parts);
}

export function mutationDigest(argv: string[], stdinSha256: string | null): string {
  return contentDigest(canonicalJson({ argv: argv, stdin_sha256: stdinSha256 }));
}

export function markerIdentity(
  skill: string,
  action: string,
  binding: string,
  mutation: string,
): string {
  return contentDigest(canonicalJson([MARKER_SCHEMA, skill, action, binding, mutation]));
}

function validateMarker(skill: string, action: string, binding: string, mutation: string): void {
  if (!fullmatch(SKILL_SOURCE, skill)) {
    throw new StateArtifactError("marker skill is unsafe");
  }
  if (action === "" || action.includes("\x00") || Buffer.byteLength(action, "utf8") > 512) {
    throw new StateArtifactError("marker action is unsafe");
  }
  if (!fullmatch(DIGEST_SOURCE, binding) || !fullmatch(DIGEST_SOURCE, mutation)) {
    throw new StateArtifactError("marker digest is invalid");
  }
}

function markerRoot(): string {
  return `${xdgStateHome()}/agent-skills/post-success/v1`;
}

export function markerPath(
  skill: string,
  action: string,
  binding: string,
  mutation: string,
): string {
  validateMarker(skill, action, binding, mutation);
  const markerId = markerIdentity(skill, action, binding, mutation);
  return `${markerRoot()}/markers/${markerId.slice(0, 2)}/${markerId}.json`;
}

export async function executionStatus(
  argv: string[],
  options: { skill: string; action: string; binding: string; stdinSha256?: string | null },
): Promise<string> {
  const stdinSha256 = options.stdinSha256 ?? null;
  const mutation = mutationDigest(argv, stdinSha256);
  const target = markerPath(options.skill, options.action, options.binding, mutation);
  const root = markerRoot();
  const markerContent = await readOptionalImmutableWithin(target, root);
  if (markerContent === null) return "not_run";
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(markerContent));
  } catch {
    throw new StateArtifactError("marker is unreadable");
  }
  const markerId = pythonStem(basename(target));
  const expected: Record<string, unknown> = {
    schema: MARKER_SCHEMA,
    marker_id: markerId,
    skill: options.skill,
    action_id: options.action,
    binding_digest: options.binding,
    mutation_digest: mutation,
    exit_status: 0,
  };
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new StateArtifactError("marker does not match its action");
  }
  const record = value as Record<string, unknown>;
  const expectedKeys = new Set([...Object.keys(expected), "succeeded_at"]);
  const actualKeys = Object.keys(record);
  if (
    actualKeys.length !== expectedKeys.size ||
    actualKeys.some((key) => !expectedKeys.has(key)) ||
    Object.entries(expected).some(([key, item]) => record[key] !== item)
  ) {
    throw new StateArtifactError("marker does not match its action");
  }
  const succeededAt = record.succeeded_at;
  if (typeof succeededAt !== "string" || !validTimestamp(succeededAt)) {
    throw new StateArtifactError("marker timestamp is invalid");
  }
  return "run_unverified";
}

function validTimestamp(value: string): boolean {
  if (!TIMESTAMP_PATTERN.test(value)) return false;
  const normalized = value
    .replace(/[Zz]$/, "+00:00")
    .replace(/([+-]\d{2})(\d{2})$/, "$1:$2")
    .replace(/[Tt ]/, "T");
  return !Number.isNaN(Date.parse(normalized));
}

export function commandWithoutExecutionStatus(command: string | null): string | null {
  if (command === null) return null;
  return command.replace(EXECUTION_STATUS_PATTERN, "");
}

export async function recordSuccess(
  skill: string,
  action: string,
  binding: string,
  mutation: string,
): Promise<string> {
  const target = markerPath(skill, action, binding, mutation);
  const markerId = pythonStem(basename(target));
  const root = markerRoot();
  const payload: Record<string, unknown> = {
    schema: MARKER_SCHEMA,
    marker_id: markerId,
    skill: skill,
    action_id: action,
    binding_digest: binding,
    mutation_digest: mutation,
    exit_status: 0,
    succeeded_at: new Date().toISOString(),
  };
  const directory = dirname(target);
  await openDirectorySafely(directory, root, true);
  const temporary = `${directory}/.marker-${randomBytes(16).toString("hex")}`;
  let handle: FileHandle | undefined;
  try {
    handle = await open(
      temporary,
      fsConstants.O_WRONLY |
        fsConstants.O_CREAT |
        fsConstants.O_EXCL |
        (fsConstants.O_NOFOLLOW ?? 0),
      0o600,
    );
    await handle.chmod(0o600);
    await handle.writeFile(Buffer.concat([canonicalJson(payload), Buffer.from("\n")]));
    await handle.sync();
    await handle.close();
    handle = undefined;
    const finalMetadata = await lstat(target).catch((error) => {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
      throw error;
    });
    if (finalMetadata !== undefined && !finalMetadata.isFile()) {
      throw new StateArtifactError("marker path is unsafe");
    }
    await rename(temporary, target);
    await syncDirectory(directory);
  } finally {
    if (handle !== undefined) await handle.close().catch(() => undefined);
    await rm(temporary, { force: true }).catch(() => undefined);
  }
  return target;
}

function shlexQuote(token: string): string {
  if (token === "") return "''";
  if (/[^A-Za-z0-9_@%+=:,./-]/.test(token)) return `'${token.replace(/'/g, "'\"'\"'")}'`;
  return token;
}

function shlexJoin(tokens: string[]): string {
  return tokens.map(shlexQuote).join(" ");
}

export async function renderMutationCommand(
  argv: string[],
  options: {
    skill: string;
    action: string;
    binding: string;
    stdinSha256?: string | null;
    cwd?: string | null;
    gitHead?: string | null;
  },
): Promise<string> {
  const command = [
    "reviewmatic",
    "marker-run",
    "--skill",
    options.skill,
    "--action",
    options.action,
    "--binding",
    options.binding,
  ];
  if (options.stdinSha256 != null) command.push("--stdin-sha256", options.stdinSha256);
  if (options.cwd != null) command.push("--cwd", options.cwd);
  if (options.gitHead != null) {
    command.push("--git-head-digest", contentDigest(canonicalJson({ git_head: options.gitHead })));
  }
  const status = await executionStatus(argv, {
    skill: options.skill,
    action: options.action,
    binding: options.binding,
    stdinSha256: options.stdinSha256 ?? null,
  });
  return `# execution-status=${status}\n${shlexJoin([...command, "--", ...argv])}`;
}

export interface MarkerRunArguments {
  skill: string;
  action: string;
  binding: string;
  stdinSha256?: string;
  cwd?: string;
  gitHeadDigest?: string;
  mutation: string[];
}

const MARKER_RUN_FLAGS: Record<string, string> = {
  "--skill": "--skill",
  "--action": "--action",
  "--binding": "--binding",
  "--stdin-sha256": "--stdin-sha256",
  "--cwd": "--cwd",
  "--git-head-digest": "--git-head-digest",
};

export function parseMarkerRunArguments(argv: string[]): MarkerRunArguments {
  const tokens = argv[0] === "marker-run" ? argv.slice(1) : argv;
  const values: Record<string, string> = {};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === "--") return finalizeMarkerRunValues(values, tokens.slice(index));
    if (MARKER_RUN_FLAGS[token] !== undefined) {
      const value = tokens[index + 1];
      if (value === undefined || value === "--" || (value.startsWith("-") && value !== "-")) {
        throw new StateArtifactError(`argument ${token}: expected one argument`);
      }
      values[token] = value;
      index += 1;
      continue;
    }
    if (token.startsWith("-") && token !== "-") {
      throw new StateArtifactError(`unrecognized arguments: ${token}`);
    }
    return finalizeMarkerRunValues(values, tokens.slice(index));
  }
  return finalizeMarkerRunValues(values, []);
}

function finalizeMarkerRunValues(
  values: Record<string, string>,
  mutation: string[],
): MarkerRunArguments {
  const missing: string[] = [];
  for (const flag of ["--skill", "--action", "--binding"]) {
    if (values[flag] === undefined) missing.push(flag);
  }
  if (missing.length > 0) {
    throw new StateArtifactError(`the following arguments are required: ${missing.join(", ")}`);
  }
  return {
    skill: values["--skill"],
    action: values["--action"],
    binding: values["--binding"],
    stdinSha256: values["--stdin-sha256"],
    cwd: values["--cwd"],
    gitHeadDigest: values["--git-head-digest"],
    mutation,
  };
}

function readStdin(): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    process.stdin.on("data", (chunk: Buffer) => chunks.push(chunk));
    process.stdin.on("end", () => resolve(Buffer.concat(chunks)));
    process.stdin.on("error", reject);
  });
}

function signalNumber(signal: string): number {
  const signals = osConstants.signals as unknown as Record<string, number | undefined>;
  return signals[signal] ?? 0;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function markerRun(argv: string[]): Promise<number> {
  const arguments_ = parseMarkerRunArguments(argv);
  let mutation = arguments_.mutation;
  if (mutation.length > 0 && mutation[0] === "--") mutation = mutation.slice(1);
  if (mutation.length === 0) throw new StateArtifactError("mutation command is required");
  let stdinContent: Buffer | null = null;
  if (arguments_.stdinSha256 !== undefined) {
    if (!fullmatch(DIGEST_SOURCE, arguments_.stdinSha256)) {
      throw new StateArtifactError("stdin digest is invalid");
    }
    stdinContent = await readStdin();
    if (contentDigest(stdinContent) !== arguments_.stdinSha256) {
      throw new StateArtifactError("mutation stdin does not match its digest");
    }
  }
  const mutationId = mutationDigest(mutation, arguments_.stdinSha256 ?? null);
  validateMarker(arguments_.skill, arguments_.action, arguments_.binding, mutationId);
  let resolvedCwd: string | null = null;
  if (arguments_.cwd !== undefined) {
    let resolved: string;
    try {
      resolved = await realpath(arguments_.cwd);
    } catch {
      throw new StateArtifactError("mutation cwd is unavailable");
    }
    const statResult = await stat(resolved).catch(() => undefined);
    if (
      !arguments_.cwd.startsWith("/") ||
      normalizeLiteral(arguments_.cwd) !== resolved ||
      statResult === undefined ||
      !statResult.isDirectory()
    ) {
      throw new StateArtifactError("mutation cwd is unsafe");
    }
    resolvedCwd = resolved;
  }
  if (arguments_.gitHeadDigest !== undefined) {
    if (resolvedCwd === null || !fullmatch(DIGEST_SOURCE, arguments_.gitHeadDigest)) {
      throw new StateArtifactError("git head precondition is invalid");
    }
    const current = spawnSync("git", ["-C", resolvedCwd, "rev-parse", "HEAD"], {
      encoding: "utf8",
    });
    if (current.error !== undefined && (current.error as NodeJS.ErrnoException).code === "ENOENT") {
      throw new StateArtifactError("git is unavailable");
    }
    const currentDigest = contentDigest(canonicalJson({ git_head: (current.stdout ?? "").trim() }));
    if (current.status !== 0 || currentDigest !== arguments_.gitHeadDigest) {
      process.stderr.write("error: mutation git head changed; regenerate before applying\n");
      return 3;
    }
  }
  const result = spawnSync(mutation[0], mutation.slice(1), {
    input: stdinContent === null ? undefined : stdinContent,
    stdio:
      stdinContent === null ? ["inherit", "inherit", "inherit"] : ["pipe", "inherit", "inherit"],
  });
  if (result.error !== undefined) throw result.error;
  if (result.status === null) {
    if (result.signal !== null) return -signalNumber(result.signal);
    throw new Error("mutation process produced no exit status");
  }
  if (result.status !== 0) return result.status;
  try {
    await recordSuccess(arguments_.skill, arguments_.action, arguments_.binding, mutationId);
  } catch (error) {
    process.stderr.write(
      `warning: mutation exited 0, but its advisory marker was not written; revalidate the target before retrying (${describeError(error)})\n`,
    );
  }
  return 0;
}
