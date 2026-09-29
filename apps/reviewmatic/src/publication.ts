import { createHash } from "node:crypto";
import {
  accessSync,
  closeSync,
  constants as fsConstants,
  existsSync,
  fstatSync,
  openSync,
  readFileSync,
  readdirSync,
  readSync,
  realpathSync,
  rmSync,
  statSync,
  writeSync,
} from "node:fs";
import { basename, dirname } from "node:path";
import { isatty } from "node:tty";
import {
  artifactPayload,
  artifactRoot,
  canonical,
  glabJson,
  isDigest,
  nonemptyString,
  paginated,
  privateDirectory,
  readJson,
  redact,
  regularFile,
  WorkflowError,
  writeCompanion,
  writeJson,
} from "./contract.js";
import {
  MutationNotAttempted,
  MutationOutcomeUnknown,
  runMutationProcess,
  type MutationProcessResult,
} from "./mutation-process.js";

export const SCHEMA = "code-review/publication/v1";
export const POSTCONDITION_DELAYS: number[] = [0.0, 0.5, 1.5, 4.0, 8.0];
export const RETRY_WARNING = "retry may duplicate a delayed GitLab write";

const LOCK_ACQUIRE_ATTEMPTS = 20;
const LOCK_ACQUIRE_DELAY_MS = 50;

type Json = Record<string, unknown>;

function isDict(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isPlainInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isErrnoException(value: unknown): value is NodeJS.ErrnoException {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    typeof (value as NodeJS.ErrnoException).code === "string"
  );
}

function fullMatch(pattern: string, value: string): boolean {
  return new RegExp(`^(?:${pattern})$`).test(value);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function keySet(value: Json): Set<string> {
  return new Set(Object.keys(value));
}

function setsEqual(left: Set<unknown>, right: Set<unknown>): boolean {
  if (left.size !== right.size) return false;
  for (const item of left) if (!right.has(item)) return false;
  return true;
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

function sha256Hex(data: Buffer): string {
  return createHash("sha256").update(data).digest("hex");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
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

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

function pythonInt(token: string): number {
  const trimmed = token.trim();
  if (!/^[+-]?[0-9]+$/.test(trimmed)) {
    throw new Error(`invalid literal for int() with base 10: ${token}`);
  }
  return Number.parseInt(trimmed, 10);
}

function sortedLabels(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return (value as unknown[]).filter((item) => typeof item === "string").sort();
}

function shlexQuote(token: string): string {
  if (token.length === 0) return "''";
  if (/[^\w@%+=:,./-]/.test(token)) {
    return `'${token.replace(/'/g, "'\\''")}'`;
  }
  return token;
}

function shlexJoin(tokens: string[]): string {
  return tokens.map(shlexQuote).join(" ");
}

function shlexSplit(command: string): string[] {
  const tokens: string[] = [];
  let token = "";
  let started = false;
  let index = 0;
  while (index < command.length) {
    const character = command[index];
    if (character === " " || character === "\t" || character === "\n") {
      if (started) {
        tokens.push(token);
        token = "";
        started = false;
      }
      index += 1;
      continue;
    }
    started = true;
    if (character === "'") {
      index += 1;
      while (index < command.length && command[index] !== "'") {
        token += command[index];
        index += 1;
      }
      index += 1;
      continue;
    }
    if (character === '"') {
      index += 1;
      while (index < command.length && command[index] !== '"') {
        if (
          command[index] === "\\" &&
          index + 1 < command.length &&
          '"$`\\'.includes(command[index + 1])
        ) {
          index += 1;
        }
        token += command[index];
        index += 1;
      }
      index += 1;
      continue;
    }
    if (character === "\\") {
      index += 1;
      if (index < command.length) {
        token += command[index];
        index += 1;
      }
      continue;
    }
    token += character;
    index += 1;
  }
  if (started) tokens.push(token);
  return tokens;
}

function readStdinLine(): string {
  const chunks: Buffer[] = [];
  const byte = Buffer.alloc(1);
  for (;;) {
    let read: number;
    try {
      read = readSync(0, byte, 0, 1, null);
    } catch {
      break;
    }
    if (read === 0) break;
    if (byte[0] === 10) break;
    chunks.push(Buffer.from(byte));
  }
  return Buffer.concat(chunks).toString("utf8");
}

function resolvedPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return path;
  }
}

export function notesSnapshot(discussions: unknown): Json {
  const result: Json = {};
  for (const discussionEntry of discussions as unknown[]) {
    const discussion = discussionEntry as Json;
    const notes = Array.isArray(discussion.notes) ? (discussion.notes as unknown[]) : [];
    for (const noteEntry of notes) {
      const note = noteEntry as Json;
      if (note.system === true) continue;
      if (!isPlainInt(note.id) || typeof note.body !== "string") {
        throw new WorkflowError("publication conversation is incomplete");
      }
      if (!("id" in discussion)) throw new Error("'id'");
      result[String(note.id)] = {
        discussion: String(discussion.id),
        body: note.body,
        author: isDict(note.author) ? (note.author.id ?? null) : null,
        resolved: note.resolved ?? null,
        position: note.position ?? null,
      };
    }
  }
  return result;
}

export function mrBinding(mr: Json): Json {
  const result: Json = {};
  for (const key of ["id", "iid", "project_id", "state", "diff_refs", "author"]) {
    result[key] = mr[key] ?? null;
  }
  return result;
}

export async function makeCommand(
  root: string,
  evidence: Json,
  context: Json,
  actionId: string,
  argv: string[],
  value: Json,
  dependencies: Record<string, string>,
  stdinSha256: string | null = null,
): Promise<string> {
  const project = evidence.project as Json;
  const target = evidence.target as Json;
  const base = `projects/${project.id}/merge_requests/${target.iid}`;
  let body: { path: string; sha256: string } | null = null;
  const payload: Json = {};
  let endpoint = base;
  let method = "POST";
  if (argv[1] === "mr" && argv[2] === "update") {
    method = "PUT";
    payload.labels = ((value.proposed as string[]) ?? []).join(",");
  } else if (argv[1] === "mr" && argv[2] === "note" && argv[3] === "create") {
    const bodiesDirectory = `${root}/artifacts/review_plan/bodies`;
    let names: string[] = [];
    try {
      names = readdirSync(bodiesDirectory).filter((name) => name.endsWith(".md"));
    } catch {
      names = [];
    }
    let bodyName: string | null = null;
    for (const name of names) {
      if (sha256Hex(readFileSync(`${bodiesDirectory}/${name}`)) === stdinSha256) {
        bodyName = name;
        break;
      }
    }
    if (bodyName === null) {
      throw new WorkflowError("line publication body is unavailable");
    }
    const bodyPath = `${bodiesDirectory}/${bodyName}`;
    body = { path: bodyPath, sha256: String(stdinSha256) };
    payload.body = readFileSync(bodyPath, "utf8");
    const fileName = argv[argv.indexOf("--file") + 1];
    const side = argv.includes("--line") ? "new" : "old";
    const flag = side === "new" ? "--line" : "--old-line";
    const changedFiles =
      isDict(evidence.changed_files) && Array.isArray(evidence.changed_files.items)
        ? (evidence.changed_files.items as unknown[])
        : [];
    const changes = changedFiles.filter(
      (item) => isDict(item) && item[`${side}_path`] === fileName,
    ) as Json[];
    if (changes.length !== 1) {
      throw new WorkflowError("line publication requires one exact changed-file identity");
    }
    const diffRefs = isDict((evidence.object as Json).diff_refs)
      ? ((evidence.object as Json).diff_refs as Json)
      : {};
    payload.position = {
      position_type: "text",
      ...diffRefs,
      new_path: changes[0].new_path,
      old_path: changes[0].old_path,
      [`${side}_line`]: pythonInt(argv[argv.indexOf(flag) + 1]),
    };
    endpoint += "/discussions";
  } else if (argv[1] === "api") {
    method = argv[argv.indexOf("--method") + 1];
    endpoint = argv[argv.indexOf("--method") + 2];
    for (let index = 0; index < argv.length; index += 1) {
      if (argv[index] !== "-F" && argv[index] !== "-f") continue;
      const assignment = argv[index + 1];
      const separator = assignment.indexOf("=");
      if (separator === -1) {
        throw new Error("not enough values to unpack");
      }
      const key = assignment.slice(0, separator);
      const text = assignment.slice(separator + 1);
      if ((key === "body" || key === "description") && text.startsWith("@")) {
        const path = text.slice(1);
        const content = readFileSync(regularFile(path, "publication body"));
        body = { path: path, sha256: sha256Hex(content) };
        payload[key] = content.toString("utf8");
      } else {
        payload[key] = key === "resolved" ? text === "true" : text;
      }
    }
  } else {
    throw new WorkflowError("unsupported publication command");
  }
  let dependency: string | null = null;
  if (actionId.endsWith(":resolve") || actionId.endsWith(":reopen")) {
    dependency = dependencies[`${actionId.slice(0, actionId.lastIndexOf(":"))}:reply`] ?? null;
    if (dependency === null) {
      throw new WorkflowError("thread state requires its explanation action");
    }
  }
  const guard: Json = {
    schema: SCHEMA,
    action_id: actionId,
    host: project.hostname,
    project_id: project.id,
    mr_iid: target.iid,
    method: method,
    endpoint: endpoint,
    payload: payload,
    body: body,
    user: { id: context.current_user_id, username: context.current_user_username },
    mr: mrBinding(evidence.object as Json),
    labels: sortedLabels((evidence.object as Json).labels),
    notes: notesSnapshot(context.discussions),
    dependency: dependency,
    evidence_digest: context.evidence_digest,
    expires_at: Math.floor(Date.now() / 1000) + 24 * 60 * 60,
  };
  validateGuard(guard);
  const content = canonical(guard);
  const actionDigest = sha256Hex(content);
  const directory = await privateDirectory(`${root}/artifacts/publication_actions`);
  const [path] = writeCompanion(`${directory}/${actionDigest}.json`, content.toString("utf8"));
  dependencies[actionId] = actionDigest;
  return shlexJoin([
    "reviewmatic",
    "publication",
    "apply",
    "--action",
    path,
    "--confirm",
    actionDigest,
  ]);
}

export function recoveryCommand(path: string, digest: string, mode: string): string {
  return shlexJoin(["reviewmatic", "publication", mode, "--action", path, "--confirm", digest]);
}

export function validateGuard(guard: Json): void {
  if (guard.schema !== SCHEMA) {
    throw new WorkflowError("legacy publication requires regeneration");
  }
  if (!fullMatch("[A-Za-z0-9.-]+", String(guard.host ?? ""))) {
    throw new WorkflowError("invalid publication host");
  }
  for (const key of ["project_id", "mr_iid"]) {
    if (!isPlainInt(guard[key]) || (guard[key] as number) < 1) {
      throw new WorkflowError("invalid publication identity");
    }
  }
  const base = `projects/${guard.project_id}/merge_requests/${guard.mr_iid}`;
  const endpoint = guard.endpoint;
  const method = guard.method;
  const payload = guard.payload;
  if (typeof endpoint !== "string" || !isDict(payload)) {
    throw new WorkflowError("invalid publication request");
  }
  let allowed = false;
  if (method === "PUT" && endpoint === base) {
    allowed = setsEqual(keySet(payload), new Set(["labels"])) && typeof payload.labels === "string";
  } else if (
    method === "PUT" &&
    fullMatch(`${escapeRegExp(base)}/discussions/[A-Za-z0-9_-]+`, endpoint)
  ) {
    allowed =
      setsEqual(keySet(payload), new Set(["resolved"])) &&
      typeof payload.resolved === "boolean" &&
      isDigest(guard.dependency);
  } else if (method === "POST" && endpoint === `projects/${guard.project_id}/issues`) {
    allowed =
      setsEqual(keySet(payload), new Set(["title", "description"])) &&
      [...Object.values(payload)].every((item) => nonemptyString(item));
  } else if (
    method === "POST" &&
    (endpoint === `${base}/notes` ||
      endpoint === `${base}/discussions` ||
      fullMatch(`${escapeRegExp(base)}/discussions/[A-Za-z0-9_-]+/notes`, endpoint))
  ) {
    allowed =
      (setsEqual(keySet(payload), new Set(["body"])) ||
        setsEqual(keySet(payload), new Set(["body", "position"]))) &&
      nonemptyString(payload.body);
    if ("position" in payload) {
      const position = payload.position;
      const positionIsDict = isDict(position);
      allowed = allowed && endpoint === `${base}/discussions` && positionIsDict;
      if (allowed) {
        const typedPosition = position as Json;
        const side = "new_line" in typedPosition ? "new_line" : "old_line";
        allowed =
          setsEqual(
            keySet(typedPosition),
            new Set([
              "position_type",
              "base_sha",
              "start_sha",
              "head_sha",
              "new_path",
              "old_path",
              side,
            ]),
          ) &&
          typedPosition.position_type === "text" &&
          isPlainInt(typedPosition[side]) &&
          (typedPosition[side] as number) > 0;
      }
    }
  }
  if (!allowed || !isDict(guard.notes) || !isDict(guard.mr)) {
    throw new WorkflowError("publication action is outside the closed operation set");
  }
  if (!isDict(guard.user) || !isPlainInt(guard.user.id)) {
    throw new WorkflowError("publication identity is incomplete");
  }
  if (!isPlainInt(guard.expires_at) || !isDigest(guard.evidence_digest)) {
    throw new WorkflowError("publication binding is incomplete");
  }
}

export async function loadAction(path: string, digest: string): Promise<[string, Json]> {
  if (
    !isDigest(digest) ||
    basename(path) !== `${digest}.json` ||
    basename(dirname(path)) !== "publication_actions" ||
    basename(dirname(dirname(path))) !== "artifacts"
  ) {
    throw new WorkflowError("publication action path or digest is invalid");
  }
  const root = await artifactRoot(dirname(dirname(dirname(path))));
  if (
    path !== `${root}/artifacts/publication_actions/${basename(path)}` ||
    path !== resolvedPath(path)
  ) {
    throw new WorkflowError("publication action path escapes its owner");
  }
  const data = readFileSync(regularFile(path, "publication action"));
  if (sha256Hex(data) !== digest) {
    throw new WorkflowError("publication action digest changed");
  }
  const guard = JSON.parse(data.toString("utf8")) as unknown;
  if (!isDict(guard)) {
    throw new WorkflowError("publication action must be an object");
  }
  validateGuard(guard);
  const body = guard.body as { path: string; sha256: string } | null;
  if (body !== null && body !== undefined) {
    const bodyPath = body.path;
    if (
      dirname(bodyPath) !== `${root}/artifacts/review_plan/bodies` ||
      bodyPath !== resolvedPath(bodyPath)
    ) {
      throw new WorkflowError("publication body escapes its owner");
    }
    const bodyData = readFileSync(regularFile(bodyPath, "publication body"));
    const payload = guard.payload as Json;
    const expected = "body" in payload ? payload.body : payload.description;
    if (sha256Hex(bodyData) !== body.sha256 || bodyData.toString("utf8") !== expected) {
      throw new WorkflowError("publication body changed");
    }
  }
  return [root, guard];
}

export async function publicationLock(
  root: string,
): Promise<{ directory: string; release: () => void }> {
  const directory = await privateDirectory(`${root}/code-review-publication`);
  const lockPath = `${directory}/lock`;
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
    throw new WorkflowError("another publication is running");
  }
  try {
    writeSync(descriptor, Buffer.from(`${process.pid}\n`, "utf8"));
    const metadata = fstatSync(descriptor);
    const ownerUid = typeof process.getuid === "function" ? process.getuid() : undefined;
    if (
      !metadata.isFile() ||
      metadata.nlink !== 1 ||
      (metadata.mode & 0o077) !== 0 ||
      (ownerUid !== undefined && metadata.uid !== ownerUid)
    ) {
      throw new WorkflowError("unsafe publication lock");
    }
  } finally {
    closeSync(descriptor);
  }
  const release = (): void => {
    try {
      rmSync(lockPath, { force: true });
    } catch {
      undefined;
    }
  };
  return { directory, release };
}

export function page(host: string, endpoint: string): Json[] {
  const value = paginated(host, endpoint);
  if (
    value.complete !== true ||
    !Array.isArray(value.items) ||
    !(value.items as unknown[]).every((item) => isDict(item))
  ) {
    throw new WorkflowError("publication evidence is incomplete");
  }
  return value.items as Json[];
}

export function observe(guard: Json): Json {
  const host = guard.host as string;
  const base = `projects/${guard.project_id}/merge_requests/${guard.mr_iid}`;
  const user = glabJson(host, "user");
  const mr = glabJson(host, base);
  if (
    !isDict(user) ||
    !jsonEqual({ id: user.id ?? null, username: user.username ?? null }, guard.user)
  ) {
    throw new WorkflowError("authenticated publication user changed");
  }
  if (!isDict(mr) || !jsonEqual(mrBinding(mr), guard.mr)) {
    throw new WorkflowError("reviewed MR identity, refs, author, or state changed");
  }
  const result: Json = { mr: mr, notes: notesSnapshot(page(host, `${base}/discussions`)) };
  if ((guard.endpoint as string).endsWith("/issues")) {
    result.issues = page(host, `${guard.endpoint}?state=all&order_by=created_at&sort=desc`);
  }
  return result;
}

export function desiredLabels(payload: Json): string[] {
  return String(payload.labels)
    .split(",")
    .filter((label) => label !== "")
    .sort();
}

export function normalizedText(value: unknown): string {
  return typeof value === "string" ? value.replace(/\s+$/, "") : "";
}

export function postcondition(guard: Json, observed: Json, before: Json): Json | null {
  const payload = guard.payload as Json;
  if ("labels" in payload) {
    const desired = desiredLabels(payload);
    return jsonEqual(sortedLabels((observed.mr as Json).labels), desired)
      ? { labels: desired }
      : null;
  }
  if ("resolved" in payload) {
    const discussion = (guard.endpoint as string).split("/").slice(-1)[0];
    const notes = Object.values(observed.notes as Json).filter(
      (note) => (note as Json).discussion === discussion && (note as Json).resolved !== null,
    ) as Json[];
    return notes.length > 0 && notes.every((note) => note.resolved === payload.resolved)
      ? { discussion: discussion, resolved: payload.resolved }
      : null;
  }
  if ("description" in payload) {
    const previous = new Set(
      (Array.isArray(before.issues) ? (before.issues as unknown[]) : [])
        .filter((issue) => isDict(issue))
        .map((issue) => (issue as Json).id),
    );
    const matches = (Array.isArray(observed.issues) ? (observed.issues as unknown[]) : []).filter(
      (issue) =>
        isDict(issue) &&
        !previous.has(issue.id) &&
        issue.project_id === guard.project_id &&
        isDict(issue.author) &&
        (issue.author as Json).id === (guard.user as Json).id &&
        issue.title === payload.title &&
        normalizedText(issue.description) === normalizedText(payload.description),
    ) as Json[];
    return matches.length === 1 ? { issue_id: matches[0].id, issue_iid: matches[0].iid } : null;
  }
  const matches: Json[] = [];
  for (const [noteId, noteEntry] of Object.entries(observed.notes as Json)) {
    const note = noteEntry as Json;
    if (
      Object.hasOwn(before.notes as Json, noteId) ||
      normalizedText(note.body) !== normalizedText(payload.body) ||
      note.author !== (guard.user as Json).id
    ) {
      continue;
    }
    const endpointText = guard.endpoint as string;
    if (
      endpointText.includes("/discussions/") &&
      note.discussion !== endpointText.split("/discussions/")[1].split("/")[0]
    ) {
      continue;
    }
    if (
      "position" in payload &&
      (!isDict(note.position) ||
        Object.entries(payload.position as Json).some(
          ([key, value]) => (note.position as Json)[key] !== value,
        ))
    ) {
      continue;
    }
    matches.push({ note_id: noteId, note: note });
  }
  return matches.length === 1 ? matches[0] : null;
}

export async function observePostcondition(
  guard: Json,
  before: Json,
): Promise<[Json | null, Json]> {
  let observed: Json | null = null;
  for (const delay of POSTCONDITION_DELAYS) {
    if (delay > 0) await sleep(delay * 1000);
    observed = observe(guard);
    const effect = postcondition(guard, observed, before);
    if (effect !== null) {
      return [effect, observed];
    }
  }
  if (observed === null) {
    throw new WorkflowError("publication postcondition polling is unavailable");
  }
  return [null, observed];
}

export function processDiagnostic(result: MutationProcessResult): string {
  const output = result.stderr.length > 0 ? result.stderr : result.stdout;
  const detail = output.length > 0 ? output.toString("utf8").trim() : "no diagnostic output";
  return redact(`glab exited with status ${result.code}: ${detail}`).slice(0, 2000);
}

export function recoveryResult(
  path: string,
  digest: string,
  guard: Json,
  error: string,
  options: { externalMutations: boolean },
): Json {
  return {
    status: "blocked",
    mutation_outcome: "unknown",
    external_mutations: options.externalMutations,
    pending_action: guard.action_id,
    error: redact(error).slice(0, 2000),
    inspect_command: recoveryCommand(path, digest, "inspect"),
    retry_command: recoveryCommand(path, digest, "retry"),
    retry_warning: RETRY_WARNING,
  };
}

export function expectedState(guard: Json, receipts: unknown[]): [Json, string[]] {
  let expectedNotes: Json = { ...(guard.notes as Json) };
  let labels = sortedLabels(guard.labels);
  for (const receiptEntry of receipts) {
    const effect = (receiptEntry as Json).effect as Json;
    if ("note_id" in effect) {
      expectedNotes[effect.note_id as string] = effect.note;
    }
    if ("discussion" in effect) {
      expectedNotes = Object.fromEntries(
        Object.entries(expectedNotes).map(([key, noteEntry]) => {
          const note = noteEntry as Json;
          return [
            key,
            note.discussion === effect.discussion && note.resolved !== null
              ? { ...note, resolved: effect.resolved }
              : note,
          ];
        }),
      ) as Json;
    }
    if ("labels" in effect) {
      labels = sortedLabels(effect.labels);
    }
  }
  return [expectedNotes, labels];
}

export function targetDiscussionId(guard: Json): string | null {
  const match = /^.*\/discussions\/([A-Za-z0-9_-]+)(?:\/notes)?$/.exec(guard.endpoint as string);
  return match !== null ? match[1] : null;
}

export function satisfiedEffect(guard: Json, observed: Json, expectedNotes: Json): Json | null {
  const before: Json = { notes: expectedNotes };
  return postcondition(guard, observed, before);
}

export function revalidate(guard: Json, observed: Json, receipts: unknown[]): void {
  const [expectedNotes, labels] = expectedState(guard, receipts);
  const payload = guard.payload as Json;
  if ("labels" in payload) {
    const current = sortedLabels((observed.mr as Json).labels);
    if (!jsonEqual(current, labels) && !jsonEqual(current, desiredLabels(payload))) {
      throw new WorkflowError("labels changed outside the plan; regenerate the plan");
    }
    return;
  }
  const discussion = targetDiscussionId(guard);
  if (discussion === null) return;
  const expected = Object.fromEntries(
    Object.entries(expectedNotes).filter(
      ([, noteEntry]) => (noteEntry as Json).discussion === discussion,
    ),
  );
  const observedThread = Object.fromEntries(
    Object.entries(observed.notes as Json).filter(
      ([, noteEntry]) => (noteEntry as Json).discussion === discussion,
    ),
  );
  if (!jsonEqual(expected, observedThread)) {
    throw new WorkflowError("target thread changed; regenerate the plan");
  }
}

export function finalizedAction(root: string, guard: Json, digest: string): void {
  const progress = readJson(`${root}/review-current.json`, "review progress");
  if (progress.stage !== "plan_ready") {
    throw new WorkflowError("publication requires a finalized current review plan");
  }
  const planPath = progress.plan_path;
  const planDigest = progress.plan_digest;
  if (
    typeof planPath !== "string" ||
    planPath !== `${root}/artifacts/review_plan/${planDigest}.json`
  ) {
    throw new WorkflowError("publication plan path is invalid");
  }
  if (sha256Hex(readFileSync(regularFile(planPath, "review plan"))) !== planDigest) {
    throw new WorkflowError("publication plan changed");
  }
  const [, plan] = artifactPayload(planPath, "review_plan");
  const actions = (plan.publication_preview as Json | undefined)?.actions;
  if (!Array.isArray(actions)) throw new Error("'actions'");
  if (
    plan.evidence_digest !== guard.evidence_digest ||
    !actions.some(
      (entry) =>
        isDict(entry) &&
        entry.id === guard.action_id &&
        typeof entry.command === "string" &&
        entry.command.includes(`--confirm ${digest}`),
    )
  ) {
    throw new WorkflowError("action does not belong to the current plan; regenerate legacy plans");
  }
}

export function loadLedger(ledgerPath: string): Json {
  if (!existsSync(ledgerPath)) {
    return { receipts: [], pendings: [] };
  }
  let ledger = readJson(ledgerPath, "publication ledger");
  if (setsEqual(keySet(ledger), new Set(["receipts", "pending"]))) {
    const legacy = ledger.pending;
    ledger = {
      receipts: ledger.receipts,
      pendings: isDict(legacy) ? [legacy] : [],
    };
  }
  if (
    !setsEqual(keySet(ledger), new Set(["receipts", "pendings"])) ||
    !Array.isArray(ledger.receipts) ||
    !Array.isArray(ledger.pendings)
  ) {
    throw new WorkflowError("invalid publication ledger");
  }
  for (const pending of ledger.pendings as unknown[]) {
    if (!isDict(pending) || !isDigest(pending.digest)) {
      throw new WorkflowError("invalid publication ledger");
    }
  }
  return ledger;
}

export function dropPending(ledger: Json, digest: string): void {
  ledger.pendings = (ledger.pendings as unknown[]).filter(
    (pending) => (pending as Json).digest !== digest,
  );
}

export async function inspectReservation(
  path: string,
  digest: string,
  guard: Json,
  pending: Json | null,
  ledger: Json,
  ledgerPath: string,
  receipts: unknown[],
  options: { inspect: boolean },
): Promise<[Json | null, Json | null]> {
  if (pending === null || pending.digest !== digest) {
    return [null, { status: "not_attempted", mutation_outcome: "none", external_mutations: false }];
  }
  let effect: Json | null;
  let observed: Json;
  try {
    [effect, observed] = await observePostcondition(guard, pending.before as Json);
  } catch (error) {
    if (error instanceof TypeError) throw error;
    pending.error = redact(`publication inspection failed: ${errorMessage(error)}`).slice(0, 2000);
    writeJson(ledgerPath, ledger);
    return [
      null,
      recoveryResult(path, digest, guard, pending.error as string, {
        externalMutations: false,
      }),
    ];
  }
  if (effect === null && options.inspect) {
    const error = `publication effect was not observed after bounded inspection; ${
      typeof pending.error === "string" ? pending.error : "the original mutation outcome is unknown"
    }`;
    return [null, recoveryResult(path, digest, guard, error, { externalMutations: false })];
  }
  if (effect === null) {
    const related = receipts.filter(
      (receipt) => (receipt as Json).evidence_digest === guard.evidence_digest,
    );
    revalidate(guard, observed, related);
  }
  return [effect, null];
}

export async function beginAction(
  root: string,
  digest: string,
  guard: Json,
  pending: Json | null,
  ledger: Json,
  ledgerPath: string,
  receipts: unknown[],
): Promise<[Json | null, Json | null, string | null, Json | null]> {
  if (pending !== null) {
    const pendingPath = `${root}/artifacts/publication_actions/${pending.digest}.json`;
    const [, pendingGuard] = await loadAction(pendingPath, pending.digest as string);
    const result = recoveryResult(
      pendingPath,
      pending.digest as string,
      pendingGuard,
      typeof pending.error === "string"
        ? pending.error
        : "unresolved publication blocks writes; inspect it first",
      { externalMutations: false },
    );
    return [null, null, null, result];
  }
  finalizedAction(root, guard, digest);
  if (Date.now() / 1000 > (guard.expires_at as number)) {
    throw new WorkflowError("publication action expired; regenerate the plan");
  }
  if (
    guard.dependency !== null &&
    guard.dependency !== undefined &&
    !receipts.some((receipt) => (receipt as Json).digest === guard.dependency)
  ) {
    throw new WorkflowError("publish the thread explanation before changing its state");
  }
  const observed = observe(guard);
  const related = receipts.filter(
    (receipt) => (receipt as Json).evidence_digest === guard.evidence_digest,
  );
  const [expectedNotes] = expectedState(guard, related);
  const effect = satisfiedEffect(guard, observed, expectedNotes);
  if (effect !== null) {
    return [effect, null, null, null];
  }
  revalidate(guard, observed, related);
  const executable = which("glab");
  if (executable === null) {
    throw new WorkflowError("glab is unavailable");
  }
  const newPending: Json = { digest: digest, before: observed };
  (ledger.pendings as unknown[]).push(newPending);
  writeJson(ledgerPath, ledger);
  return [null, newPending, executable, null];
}

export async function attemptMutation(
  path: string,
  digest: string,
  guard: Json,
  pending: Json,
  ledger: Json,
  ledgerPath: string,
  executableValue: string | null,
  options: { retry: boolean },
): Promise<[Json | null, boolean, Json | null]> {
  const executable = executableValue ?? which("glab");
  if (executable === null) {
    if (!options.retry) {
      throw new WorkflowError("glab is unavailable");
    }
    pending.error = "glab is unavailable";
    writeJson(ledgerPath, ledger);
    const unavailable = recoveryResult(path, digest, guard, pending.error as string, {
      externalMutations: false,
    });
    return [null, false, unavailable];
  }
  let externalMutations = false;
  let effect: Json | null;
  try {
    const process = await runMutationProcess(
      [
        executable,
        "api",
        "--hostname",
        guard.host as string,
        "--method",
        guard.method as string,
        guard.endpoint as string,
        "--header",
        "Content-Type: application/json",
        "--input",
        "-",
      ],
      canonical(guard.payload),
    );
    externalMutations = true;
    const processError = process.code !== 0 ? processDiagnostic(process) : null;
    try {
      [effect] = await observePostcondition(guard, pending.before as Json);
    } catch (error) {
      if (processError !== null) {
        throw new WorkflowError(
          `${processError}; postcondition read failed: ${errorMessage(error)}`,
        );
      }
      throw error;
    }
    if (effect === null) {
      const diagnostic =
        processError ?? "publication postcondition is unverified after bounded inspection";
      throw new MutationOutcomeUnknown(diagnostic);
    }
  } catch (error) {
    if (error instanceof MutationNotAttempted) {
      if (!options.retry) {
        dropPending(ledger, digest);
        writeJson(ledgerPath, ledger);
        throw error;
      }
      pending.error = redact(errorMessage(error));
      writeJson(ledgerPath, ledger);
      const notAttempted = recoveryResult(path, digest, guard, errorMessage(error), {
        externalMutations: false,
      });
      return [null, false, notAttempted];
    }
    if (error instanceof TypeError) throw error;
    if (error instanceof MutationOutcomeUnknown) {
      externalMutations = true;
    }
    pending.error = redact(errorMessage(error)).slice(0, 2000);
    try {
      writeJson(ledgerPath, ledger);
    } catch (writeError) {
      if (!isErrnoException(writeError)) throw writeError;
    }
    const result = recoveryResult(path, digest, guard, errorMessage(error), {
      externalMutations: externalMutations,
    });
    return [null, externalMutations, result];
  }
  return [effect, externalMutations, null];
}

export async function execute(
  path: string,
  digest: string,
  options: { inspect?: boolean; retry?: boolean } = {},
): Promise<Json> {
  const inspect = options.inspect ?? false;
  const retry = options.retry ?? false;
  if (inspect && retry) {
    throw new WorkflowError("publication action mode is invalid");
  }
  const [root, guard] = await loadAction(path, digest);
  const lock = await publicationLock(root);
  try {
    const ledgerPath = `${lock.directory}/ledger.json`;
    const ledger = loadLedger(ledgerPath);
    const receipts = ledger.receipts as unknown[];
    if (receipts.some((receipt) => isDict(receipt) && receipt.digest === digest)) {
      return {
        status: "already_applied",
        mutation_outcome: "applied",
        external_mutations: false,
      };
    }
    let pending: Json | null = ((ledger.pendings as unknown[]).find(
      (entry) => isDict(entry) && entry.digest === digest,
    ) ?? null) as Json | null;
    let effect: Json | null = null;
    let externalMutations = false;
    let executable: string | null = null;
    if (inspect || retry) {
      if (retry) {
        finalizedAction(root, guard, digest);
        if (Date.now() / 1000 > (guard.expires_at as number)) {
          throw new WorkflowError("publication action expired; regenerate the plan");
        }
      }
      const [inspectedEffect, result] = await inspectReservation(
        path,
        digest,
        guard,
        pending as Json | null,
        ledger,
        ledgerPath,
        receipts,
        { inspect: inspect },
      );
      effect = inspectedEffect;
      if (result !== null) {
        return result;
      }
    } else {
      const [begunEffect, begunPending, begunExecutable, result] = await beginAction(
        root,
        digest,
        guard,
        pending as Json | null,
        ledger,
        ledgerPath,
        receipts,
      );
      effect = begunEffect;
      pending = begunPending;
      executable = begunExecutable;
      if (result !== null) {
        return result;
      }
    }
    const externallySatisfied = effect !== null && pending === null;
    if (effect === null) {
      if (pending === null) {
        throw new WorkflowError("publication reservation is unavailable");
      }
      const [mutationEffect, mutationExternal, result] = await attemptMutation(
        path,
        digest,
        guard,
        pending,
        ledger,
        ledgerPath,
        executable,
        { retry: retry },
      );
      effect = mutationEffect;
      externalMutations = mutationExternal;
      if (result !== null) {
        return result;
      }
    }
    receipts.push({
      digest: digest,
      evidence_digest: guard.evidence_digest,
      effect: effect,
    });
    dropPending(ledger, digest);
    try {
      writeJson(ledgerPath, ledger);
    } catch (error) {
      if (!isErrnoException(error)) throw error;
      return recoveryResult(
        path,
        digest,
        guard,
        "publication effect was observed but its receipt could not be persisted",
        { externalMutations: externalMutations },
      );
    }
    return {
      status: externallySatisfied ? "already_applied" : "applied",
      mutation_outcome: "applied",
      external_mutations: externalMutations,
    };
  } finally {
    lock.release();
  }
}

export function confirmInteractively(prompt: string): boolean {
  process.stderr.write(`${prompt}\n`);
  const answer = readStdinLine();
  return answer.trim().toLowerCase() === "y" || answer.trim().toLowerCase() === "yes";
}

export async function interactiveRecovery(
  pathValue: string,
  digestValue: string,
  result: Json,
  options: { inspected?: boolean } = {},
): Promise<Json> {
  if (result.status !== "blocked" || result.mutation_outcome !== "unknown") {
    return result;
  }
  if (!isatty(0) || !isatty(2)) {
    return result;
  }
  let path = pathValue;
  let digest = digestValue;
  const command = result.inspect_command;
  if (typeof command === "string") {
    const tokens = shlexSplit(command);
    path = tokens[tokens.indexOf("--action") + 1];
    digest = tokens[tokens.indexOf("--confirm") + 1];
  }
  process.stderr.write(`Publication is unverified: ${result.error ?? "unknown error"}\n`);
  let inspectedResult = result;
  if (!options.inspected) {
    if (!confirmInteractively("Inspect GitLab for the exact effect now? [y/N]")) {
      return result;
    }
    inspectedResult = await execute(path, digest, { inspect: true });
  }
  if (inspectedResult.status !== "blocked") {
    return inspectedResult;
  }
  const warning = `The exact effect is still absent; ${RETRY_WARNING}. Retry this action? [y/N]`;
  return confirmInteractively(warning) ? execute(path, digest, { retry: true }) : inspectedResult;
}
