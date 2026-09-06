import { createHash, randomBytes, randomUUID } from "node:crypto";
import { constants } from "node:fs";
import {
  chmod,
  lstat,
  mkdir,
  open,
  readFile,
  readdir,
  rename,
  rm,
  rmdir,
  stat,
  unlink,
} from "node:fs/promises";
import { homedir } from "node:os";
import {
  basename,
  dirname,
  isAbsolute,
  join,
  normalize,
  parse,
  relative,
  resolve,
  sep,
} from "node:path";

export const RECEIPT_TTL_MS = 10 * 60 * 1000;

export class LifecycleError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export type Scope = "global" | "project";
export type FileExpectation = { sha256?: string; absent?: true };
export type FileMutation =
  | { path: string; operation: "write"; content: Buffer; mode: number; expected: FileExpectation }
  | { path: string; operation: "remove"; expected: FileExpectation };

type JournalSnapshot = { path: string; content: string | null; mode: number | null };
type Journal = {
  schema_version: 1;
  root: string;
  operations: Array<{
    path: string;
    operation: "write" | "remove";
    content?: string;
    mode?: number;
    expected: FileExpectation;
  }>;
  snapshots: JournalSnapshot[];
  created_directories: Array<{ path: string; device: number; inode: number }>;
  published: number;
  applying: number | null;
};

type Receipt = {
  schema_version: 1;
  digest: string;
  nonce: string;
  expires_at: string;
  consumed: boolean;
  kind: string;
  scope: Scope;
  root: string;
  payload: unknown;
  integrity: string;
};

export function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stable(object[key])}`)
    .join(",")}}`;
}

export function sha256(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function digest(value: unknown): string {
  return sha256(stable(value));
}

export function assertSafeRelative(value: string): void {
  if (
    !value ||
    isAbsolute(value) ||
    normalize(value) !== value ||
    value.split(/[\\/]/).some((part) => !part || part === "." || part === "..")
  ) {
    throw new LifecycleError("unsafe_path", `Unsafe relative path: ${value}`);
  }
}

function inside(root: string, target: string): boolean {
  const difference = relative(root, target);
  return (
    difference === "" ||
    (!difference.startsWith(`..${sep}`) && difference !== ".." && !isAbsolute(difference))
  );
}

export function destination(root: string, relativePath: string): string {
  assertSafeRelative(relativePath);
  const target = resolve(root, relativePath);
  if (!inside(resolve(root), target))
    throw new LifecycleError("unsafe_path", `Path escapes destination root: ${relativePath}`);
  return target;
}

async function lstatSafe(path: string) {
  try {
    return await lstat(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function assertSafePath(
  path: string,
  options: { target?: "file" | "directory"; allowMissing?: boolean } = {},
): Promise<void> {
  const target = resolve(path);
  const parsed = parse(target);
  let current = parsed.root;
  const pieces = target.slice(parsed.root.length).split(sep).filter(Boolean);
  for (let index = 0; index < pieces.length; index += 1) {
    current = join(current, pieces[index]);
    const metadata = await lstatSafe(current);
    if (!metadata) {
      if (options.allowMissing !== false) return;
      throw new LifecycleError("unsafe_path", `Required path is missing: ${current}`);
    }
    if (metadata.isSymbolicLink())
      throw new LifecycleError("unsafe_path", `Symlink is not allowed: ${current}`);
    const final = index === pieces.length - 1;
    if (!final && !metadata.isDirectory())
      throw new LifecycleError("unsafe_path", `Path parent is not a directory: ${current}`);
    if (final && options.target === "file" && !metadata.isFile())
      throw new LifecycleError("unsafe_path", `Target is not a regular file: ${current}`);
    if (final && options.target === "directory" && !metadata.isDirectory())
      throw new LifecycleError("unsafe_path", `Target is not a directory: ${current}`);
  }
}

export async function readRegular(path: string): Promise<Buffer | undefined> {
  await assertSafePath(path);
  const metadata = await lstatSafe(path);
  if (!metadata) return undefined;
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) {
    throw new LifecycleError("unsafe_path", `Target is not a single-link regular file: ${path}`);
  }
  return readFile(path);
}

async function ensureDirectory(path: string, mode: number): Promise<string[]> {
  const target = resolve(path);
  const parsed = parse(target);
  let current = parsed.root;
  const created: string[] = [];
  for (const piece of target.slice(parsed.root.length).split(sep).filter(Boolean)) {
    current = join(current, piece);
    const metadata = await lstatSafe(current);
    if (metadata) {
      if (!metadata.isDirectory() || metadata.isSymbolicLink())
        throw new LifecycleError("unsafe_path", `Unsafe directory: ${current}`);
      continue;
    }
    await mkdir(current, { mode });
    created.push(current);
  }
  return created;
}

export async function writeAtomic(path: string, content: Buffer, mode: number): Promise<void> {
  await ensureDirectory(dirname(path), 0o700);
  await assertSafePath(path);
  const current = await lstatSafe(path);
  if (current && (!current.isFile() || current.isSymbolicLink() || current.nlink !== 1)) {
    throw new LifecycleError("unsafe_path", `Target is not a single-link regular file: ${path}`);
  }
  const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  const handle = await open(
    temporary,
    constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW,
    mode,
  );
  try {
    await handle.writeFile(content);
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    await chmod(temporary, mode);
    await rename(temporary, path);
    const directory = await open(dirname(path), constants.O_RDONLY | constants.O_DIRECTORY);
    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
  } finally {
    await rm(temporary, { force: true });
  }
}

export function deploymentRoot(scope: Scope, cwd = process.cwd(), home = homedir()): string {
  return scope === "global" ? resolve(home, ".config", "opencode") : resolve(cwd, ".opencode");
}

export function lifecycleRoot(scope: Scope, cwd = process.cwd(), home = homedir()): string {
  const base =
    process.env.XDG_STATE_HOME && home === homedir()
      ? resolve(process.env.XDG_STATE_HOME)
      : resolve(home, ".local", "state");
  const suffix = scope === "global" ? "global" : join("project", sha256(resolve(cwd)));
  return join(base, "opencode", "skills-opencode", suffix);
}

async function processAlive(pid: number): Promise<boolean> {
  if (!Number.isSafeInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

async function reclaimStaleLifecycleLock(stateRoot: string, lock: string): Promise<void> {
  const cleanup = join(stateRoot, "lifecycle-lock-cleanup");
  try {
    await mkdir(cleanup, { mode: 0o700 });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "EEXIST")
      throw new LifecycleError("lifecycle_locked", "Another process is checking a stale lock");
    throw error;
  }
  try {
    const lockInfo = await lstatSafe(lock);
    if (!lockInfo) return;
    if (!lockInfo.isDirectory() || lockInfo.isSymbolicLink() || (lockInfo.mode & 0o077) !== 0)
      throw new LifecycleError("unsafe_path", "Lifecycle lock is not a private directory");
    const ownerRaw = await readRegular(join(lock, "owner.json")).catch(() => undefined);
    if (!ownerRaw) {
      if (Date.now() - lockInfo.mtimeMs < 10_000)
        throw new LifecycleError("lifecycle_locked", "Lifecycle lock is being initialized");
      await rm(lock, { recursive: true, force: true });
      return;
    }
    let ownerPid = 0;
    let released = false;
    try {
      const owner = JSON.parse(ownerRaw.toString("utf8")) as {
        pid?: unknown;
        released?: unknown;
      };
      ownerPid = Number(owner.pid);
      released = owner.released === true;
    } catch {
      ownerPid = 0;
    }
    if (!released && (await processAlive(ownerPid)))
      throw new LifecycleError("lifecycle_locked", `Lifecycle is locked by process ${ownerPid}`);
    await rm(lock, { recursive: true, force: true });
  } finally {
    await rm(cleanup, { recursive: true, force: true }).catch(() => undefined);
  }
}

export async function withLifecycleLock<T>(
  stateRoot: string,
  callback: () => Promise<T>,
): Promise<T> {
  await ensureDirectory(stateRoot, 0o700);
  const stateInfo = await lstat(stateRoot);
  if (!stateInfo.isDirectory() || stateInfo.isSymbolicLink() || (stateInfo.mode & 0o077) !== 0) {
    throw new LifecycleError("unsafe_path", "Lifecycle state root must be a private directory");
  }
  const lock = join(stateRoot, "lifecycle.lock");
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      await mkdir(lock, { mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      await reclaimStaleLifecycleLock(stateRoot, lock);
      continue;
    }
    try {
      await writeAtomic(
        join(lock, "owner.json"),
        Buffer.from(
          `${JSON.stringify({ pid: process.pid, created_at: new Date().toISOString(), released: false })}\n`,
        ),
        0o600,
      );
      return await callback();
    } finally {
      await writeAtomic(
        join(lock, "owner.json"),
        Buffer.from(
          `${JSON.stringify({ pid: process.pid, released_at: new Date().toISOString(), released: true })}\n`,
        ),
        0o600,
      ).catch(() => undefined);
      await rm(lock, { recursive: true, force: true }).catch(() => undefined);
    }
  }
  throw new LifecycleError("lifecycle_locked", "Cannot acquire lifecycle lock");
}

function receiptPath(stateRoot: string): string {
  return join(stateRoot, "receipt.json");
}

export async function saveReceipt(
  stateRoot: string,
  kind: string,
  scope: Scope,
  root: string,
  payload: unknown,
  now = Date.now(),
): Promise<{ digest: string; expires_at: string }> {
  const confirmationDigest = digest({ schema_version: 1, kind, scope, root, payload });
  const existingRaw = await readRegular(receiptPath(stateRoot));
  if (existingRaw) {
    const existing = parseReceipt(existingRaw);
    if (
      !existing.consumed &&
      Date.parse(existing.expires_at) >= now &&
      existing.digest !== confirmationDigest
    ) {
      throw new LifecycleError(
        "active_receipt",
        "An unconsumed agent or installer plan is still active",
      );
    }
    if (
      !existing.consumed &&
      Date.parse(existing.expires_at) >= now &&
      existing.digest === confirmationDigest
    ) {
      return { digest: existing.digest, expires_at: existing.expires_at };
    }
  }
  const receipt: Receipt = {
    schema_version: 1,
    digest: confirmationDigest,
    nonce: randomBytes(32).toString("base64url"),
    expires_at: new Date(now + RECEIPT_TTL_MS).toISOString(),
    consumed: false,
    kind,
    scope,
    root,
    payload,
    integrity: "",
  };
  receipt.integrity = receiptIntegrity(receipt);
  await writeAtomic(receiptPath(stateRoot), Buffer.from(`${stable(receipt)}\n`), 0o600);
  return { digest: receipt.digest, expires_at: receipt.expires_at };
}

function parseReceipt(raw: Buffer): Receipt {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new LifecycleError("invalid_receipt", "Receipt is not valid JSON");
  }
  const receipt = value as Partial<Receipt>;
  if (
    !receipt ||
    receipt.schema_version !== 1 ||
    typeof receipt.digest !== "string" ||
    !/^[a-f0-9]{64}$/.test(receipt.digest) ||
    typeof receipt.nonce !== "string" ||
    typeof receipt.expires_at !== "string" ||
    typeof receipt.consumed !== "boolean" ||
    typeof receipt.kind !== "string" ||
    (receipt.scope !== "global" && receipt.scope !== "project") ||
    typeof receipt.root !== "string" ||
    typeof receipt.integrity !== "string"
  ) {
    throw new LifecycleError("invalid_receipt", "Receipt has an unsupported schema");
  }
  if (
    receipt.digest !==
    digest({
      schema_version: 1,
      kind: receipt.kind,
      scope: receipt.scope,
      root: receipt.root,
      payload: receipt.payload,
    })
  ) {
    throw new LifecycleError("invalid_receipt", "Receipt digest does not match its payload");
  }
  if (receipt.integrity !== receiptIntegrity(receipt as Receipt))
    throw new LifecycleError("invalid_receipt", "Receipt integrity check failed");
  return receipt as Receipt;
}

function receiptIntegrity(receipt: Receipt): string {
  const { integrity: _integrity, ...document } = receipt;
  return digest(document);
}

export async function consumeReceipt(
  stateRoot: string,
  expected: { digest: string; kind: string; scope: Scope; root: string },
  now = Date.now(),
): Promise<unknown> {
  if (!/^[a-f0-9]{64}$/.test(expected.digest))
    throw new LifecycleError("invalid_digest", "Confirmation digest must be a SHA-256 value");
  const raw = await readRegular(receiptPath(stateRoot));
  if (!raw) throw new LifecycleError("confirmation_unknown", "Confirmation receipt is missing");
  const receipt = parseReceipt(raw);
  if (
    receipt.digest !== expected.digest ||
    receipt.kind !== expected.kind ||
    receipt.scope !== expected.scope ||
    receipt.root !== expected.root
  ) {
    throw new LifecycleError("confirmation_unknown", "Confirmation does not match the saved plan");
  }
  if (receipt.consumed)
    throw new LifecycleError("confirmation_consumed", "Confirmation receipt was already consumed");
  if (Date.parse(receipt.expires_at) < now)
    throw new LifecycleError(
      "confirmation_expired",
      "Confirmation receipt expired; request a fresh plan",
    );
  const consumed = { ...receipt, consumed: true, integrity: "" };
  consumed.integrity = receiptIntegrity(consumed);
  await writeAtomic(receiptPath(stateRoot), Buffer.from(`${stable(consumed)}\n`), 0o600);
  return receipt.payload;
}

function journalPath(stateRoot: string): string {
  return join(stateRoot, "transaction-journal.json");
}

async function snapshot(root: string, mutation: FileMutation): Promise<JournalSnapshot> {
  const target = destination(root, mutation.path);
  const content = await readRegular(target);
  if (!content) return { path: mutation.path, content: null, mode: null };
  const metadata = await stat(target);
  return { path: mutation.path, content: content.toString("base64"), mode: metadata.mode & 0o777 };
}

async function validateExpectation(root: string, mutation: FileMutation): Promise<void> {
  const current = await readRegular(destination(root, mutation.path));
  if (mutation.expected.absent) {
    if (current)
      throw new LifecycleError("stale_plan", `Expected an absent target: ${mutation.path}`);
    return;
  }
  if (!mutation.expected.sha256 || !current || sha256(current) !== mutation.expected.sha256) {
    throw new LifecycleError("stale_plan", `Destination changed after preview: ${mutation.path}`);
  }
}

async function writeJournal(stateRoot: string, journal: Journal): Promise<void> {
  await writeAtomic(journalPath(stateRoot), Buffer.from(`${stable(journal)}\n`), 0o600);
}

async function restore(root: string, journal: Journal): Promise<void> {
  const conflicts: string[] = [];
  for (let index = journal.snapshots.length - 1; index >= 0; index -= 1) {
    const item = journal.snapshots[index];
    const operation = journal.operations[index];
    const target = destination(root, item.path);
    const current = await readRegular(target);
    const currentHash = current ? sha256(current) : undefined;
    const currentMode = current ? (await lstat(target)).mode & 0o777 : undefined;
    const beforeHash =
      item.content === null ? undefined : sha256(Buffer.from(item.content, "base64"));
    const beforeMode = item.mode ?? undefined;
    const intendedHash =
      operation.operation === "write" && operation.content
        ? sha256(Buffer.from(operation.content, "base64"))
        : undefined;
    const intendedMode = operation.operation === "write" ? operation.mode : undefined;
    const touched = index < journal.published || index === journal.applying;
    if (!touched) {
      if (currentHash !== beforeHash || currentMode !== beforeMode) conflicts.push(item.path);
      continue;
    }
    if (currentHash === beforeHash && currentMode === beforeMode) continue;
    if (currentHash !== intendedHash || currentMode !== intendedMode) {
      conflicts.push(item.path);
      continue;
    }
    if (item.content === null) {
      if (current) await unlink(target);
    } else {
      await writeAtomic(target, Buffer.from(item.content, "base64"), item.mode ?? 0o600);
    }
  }
  for (const directory of [...journal.created_directories].reverse()) {
    try {
      const metadata = await lstat(directory.path);
      if (
        !metadata.isDirectory() ||
        metadata.isSymbolicLink() ||
        metadata.dev !== directory.device ||
        metadata.ino !== directory.inode
      ) {
        conflicts.push(directory.path);
        continue;
      }
      await rmdir(directory.path);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "ENOENT" && code !== "ENOTEMPTY") throw error;
    }
  }
  if (conflicts.length)
    throw new LifecycleError(
      "recovery_conflict",
      `Transaction targets changed outside the lifecycle lock: ${conflicts.join(", ")}`,
    );
}

function parseJournal(raw: Buffer, expectedRoot: string): Journal {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new LifecycleError("invalid_journal", "Transaction journal is not valid JSON");
  }
  const journal = value as Partial<Journal>;
  if (
    journal.schema_version !== 1 ||
    journal.root !== expectedRoot ||
    !Array.isArray(journal.operations) ||
    !Array.isArray(journal.snapshots) ||
    journal.operations.length !== journal.snapshots.length ||
    !Array.isArray(journal.created_directories) ||
    typeof journal.published !== "number" ||
    !Number.isSafeInteger(journal.published) ||
    journal.published < 0 ||
    journal.published > journal.operations.length ||
    (journal.applying !== null &&
      (typeof journal.applying !== "number" ||
        !Number.isSafeInteger(journal.applying) ||
        journal.applying !== journal.published ||
        journal.applying < 0 ||
        journal.applying >= journal.operations.length))
  ) {
    throw new LifecycleError("invalid_journal", "Transaction journal has an unsupported schema");
  }
  for (const item of journal.snapshots) assertSafeRelative(item.path);
  for (const item of journal.snapshots) {
    if (
      (item.content !== null &&
        (typeof item.content !== "string" ||
          !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
            item.content,
          ))) ||
      (item.mode !== null &&
        (!Number.isSafeInteger(item.mode) || item.mode < 0 || item.mode > 0o777))
    ) {
      throw new LifecycleError(
        "invalid_journal",
        "Transaction journal contains an invalid snapshot",
      );
    }
  }
  for (const item of journal.operations) {
    assertSafeRelative(item.path);
    if (item.operation !== "write" && item.operation !== "remove")
      throw new LifecycleError(
        "invalid_journal",
        "Transaction journal contains an invalid operation",
      );
    if (
      item.operation === "write" &&
      (typeof item.content !== "string" ||
        !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(item.content) ||
        typeof item.mode !== "number" ||
        !Number.isSafeInteger(item.mode) ||
        item.mode < 0 ||
        item.mode > 0o777)
    )
      throw new LifecycleError(
        "invalid_journal",
        "Transaction journal contains invalid write content",
      );
  }
  if (
    !journal.created_directories.every(
      (item) =>
        item &&
        typeof item.path === "string" &&
        inside(resolve(expectedRoot), resolve(item.path)) &&
        Number.isSafeInteger(item.device) &&
        item.device >= 0 &&
        Number.isSafeInteger(item.inode) &&
        item.inode > 0,
    )
  ) {
    throw new LifecycleError(
      "invalid_journal",
      "Transaction journal contains an unsafe created directory",
    );
  }
  return journal as Journal;
}

export async function recoverTransaction(root: string, stateRoot: string): Promise<boolean> {
  const raw = await readRegular(journalPath(stateRoot));
  if (!raw) return false;
  const journal = parseJournal(raw, resolve(root));
  await restore(root, journal);
  await unlink(journalPath(stateRoot));
  return true;
}

export type TransactionOptions = {
  beforePublish?: (index: number) => void;
  afterPublish?: (published: number) => "continue" | "fail" | "interrupt";
  validateFinal?: () => Promise<void>;
};

async function ensureTransactionDirectories(
  root: string,
  mutation: FileMutation,
  stateRoot: string,
  journal: Journal,
): Promise<void> {
  await ensureDirectory(dirname(resolve(root)), 0o700);
  const relativeParent = relative(resolve(root), dirname(destination(root, mutation.path)));
  const parts = relativeParent.split(sep).filter(Boolean);
  const directories = [
    resolve(root),
    ...parts.map((_, index) => resolve(root, ...parts.slice(0, index + 1))),
  ];
  for (const directory of directories) {
    const existing = await lstatSafe(directory);
    if (existing) {
      if (!existing.isDirectory() || existing.isSymbolicLink())
        throw new LifecycleError("unsafe_path", `Transaction parent is unsafe: ${directory}`);
      continue;
    }
    try {
      await mkdir(directory, { mode: 0o700 });
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const raced = await lstat(directory);
      if (!raced.isDirectory() || raced.isSymbolicLink())
        throw new LifecycleError("unsafe_path", `Transaction parent is unsafe: ${directory}`);
      continue;
    }
    const metadata = await lstat(directory);
    journal.created_directories.push({
      path: directory,
      device: metadata.dev,
      inode: metadata.ino,
    });
    await writeJournal(stateRoot, journal);
  }
}

export async function applyTransaction(
  root: string,
  stateRoot: string,
  mutations: readonly FileMutation[],
  options: TransactionOptions = {},
): Promise<void> {
  if (await readRegular(journalPath(stateRoot)))
    throw new LifecycleError(
      "recovery_required",
      "An interrupted transaction must be recovered before apply",
    );
  const unique = new Set<string>();
  for (const mutation of mutations) {
    assertSafeRelative(mutation.path);
    if (unique.has(mutation.path))
      throw new LifecycleError("invalid_plan", `Duplicate transaction target: ${mutation.path}`);
    unique.add(mutation.path);
    await validateExpectation(root, mutation);
  }
  const snapshots = await Promise.all(mutations.map((mutation) => snapshot(root, mutation)));
  const journal: Journal = {
    schema_version: 1,
    root: resolve(root),
    operations: mutations.map((mutation) =>
      mutation.operation === "write"
        ? {
            path: mutation.path,
            operation: mutation.operation,
            content: mutation.content.toString("base64"),
            mode: mutation.mode,
            expected: mutation.expected,
          }
        : { path: mutation.path, operation: mutation.operation, expected: mutation.expected },
    ),
    snapshots,
    created_directories: [],
    published: 0,
    applying: null,
  };
  await writeJournal(stateRoot, journal);
  try {
    for (const mutation of mutations) {
      journal.applying = journal.published;
      await writeJournal(stateRoot, journal);
      options.beforePublish?.(journal.published);
      if (mutation.operation === "write")
        await ensureTransactionDirectories(root, mutation, stateRoot, journal);
      await validateExpectation(root, mutation);
      const target = destination(root, mutation.path);
      if (mutation.operation === "write")
        await writeAtomic(target, mutation.content, mutation.mode);
      else await unlink(target);
      journal.published += 1;
      journal.applying = null;
      await writeJournal(stateRoot, journal);
      const injected = options.afterPublish?.(journal.published);
      if (injected === "interrupt")
        throw new LifecycleError("test_interruption", "Injected transaction interruption");
      if (injected === "fail")
        throw new LifecycleError("test_failure", "Injected transaction failure");
    }
    for (const mutation of mutations) {
      const target = destination(root, mutation.path);
      const current = await readRegular(target);
      if (
        (mutation.operation === "remove" && current) ||
        (mutation.operation === "write" &&
          (!current ||
            !current.equals(mutation.content) ||
            ((await stat(target)).mode & 0o777) !== mutation.mode))
      ) {
        throw new LifecycleError(
          "final_validation_failed",
          `Transaction target failed final validation: ${mutation.path}`,
        );
      }
    }
    await options.validateFinal?.();
    await unlink(journalPath(stateRoot));
  } catch (error) {
    if (error instanceof LifecycleError && error.code === "test_interruption") throw error;
    try {
      await restore(root, journal);
      await unlink(journalPath(stateRoot));
    } catch (rollbackError) {
      throw new LifecycleError(
        "rollback_failed",
        `Transaction failed and rollback failed: ${String(rollbackError)}`,
      );
    }
    throw new LifecycleError(
      "rolled_back",
      `Transaction failed and was rolled back: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export async function appendPrivate(path: string, value: unknown): Promise<void> {
  await ensureDirectory(dirname(path), 0o700);
  await assertSafePath(path);
  const existing = await lstatSafe(path);
  if (existing && (!existing.isFile() || existing.isSymbolicLink() || existing.nlink !== 1))
    throw new LifecycleError("unsafe_path", `Append target is unsafe: ${path}`);
  const handle = await open(
    path,
    constants.O_APPEND | constants.O_CREAT | constants.O_WRONLY | constants.O_NOFOLLOW,
    0o600,
  );
  try {
    const metadata = await handle.stat();
    if (!metadata.isFile() || metadata.nlink !== 1 || (metadata.mode & 0o777) !== 0o600)
      throw new LifecycleError("unsafe_path", `Append target is unsafe: ${path}`);
    await handle.writeFile(`${stable(value)}\n`);
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export async function listDirectRegular(
  directory: string,
): Promise<Array<{ name: string; content: Buffer; mode: number }>> {
  const metadata = await lstatSafe(directory);
  if (!metadata) return [];
  if (!metadata.isDirectory() || metadata.isSymbolicLink())
    throw new LifecycleError("unsafe_path", `Directory is unsafe: ${directory}`);
  const values: Array<{ name: string; content: Buffer; mode: number }> = [];
  for (const entry of (await readdir(directory, { withFileTypes: true })).sort((left, right) =>
    left.name.localeCompare(right.name),
  )) {
    if (!entry.isFile() || entry.isSymbolicLink())
      throw new LifecycleError(
        "unsafe_path",
        `Directory entry is not a regular file: ${entry.name}`,
      );
    const path = join(directory, entry.name);
    const info = await lstat(path);
    if (info.nlink !== 1)
      throw new LifecycleError(
        "unsafe_path",
        `Directory entry has multiple hard links: ${entry.name}`,
      );
    values.push({ name: entry.name, content: await readFile(path), mode: info.mode & 0o777 });
  }
  return values;
}
