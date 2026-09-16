import { readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import { lstat, opendir, readdir, readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import {
  applyTransaction,
  archiveRoot,
  assertSafePath,
  consumeReceipt,
  destination,
  digest,
  LifecycleError,
  lifecycleRoot,
  recoverTransaction,
  saveReceipt,
  supersedeReceipt,
  sha256,
  stable,
  withLifecycleLock,
  type SupersededPlan,
  type FileMutation,
  type Scope,
  type TransactionOptions,
} from "./lifecycle.js";
import { archiveMutations, type ArchiveCandidate } from "./installer.js";
import { skillsInstallerSpec } from "./package-metadata.js";

const PACKAGE_NAME = "@kisev/skills-opencode";
const GENERIC_MANIFEST = ".skills-opencode-manifest.json";
const SEMANTIC_MANIFEST = ".skills-opencode/agent-profiles.manifest.json";
const PORTABLE_SOURCE = "https://kisev.github.io/skills" as const;
const PROCESS_OUTPUT_LIMIT = 64 * 1024;
const PROCESS_TIMEOUT_MS = 120_000;
const PORTABLE_FILE_LIMIT = 4 * 1024 * 1024;
const PORTABLE_TREE_FILE_LIMIT = 256;
const PORTABLE_TREE_BYTE_LIMIT = 16 * 1024 * 1024;
const PORTABLE_TREE_ENTRY_LIMIT = 1_024;
const PORTABLE_TREE_DEPTH_LIMIT = 32;
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = resolve(packageRoot, "dist", "assets");
const inventoryPath = resolve(assetsRoot, "migration-inventory.json");

type InventoryRecord = {
  id: string;
  kind:
    | "portable-skill"
    | "package-command"
    | "package-plugin"
    | "package-agent"
    | "installation-metadata";
  historical_path: string;
  installed_path: string;
  introduced: { ref: string; version: string };
  retired: { ref: string; version: string };
  replacement: string | null;
  replacements?: string[];
  scopes: Scope[];
  sha256?: string;
  files?: Record<string, string>;
};

type Inventory = {
  schema_version: 2;
  inventory_version: string;
  active_portable_skills: string[];
  removed: string[];
  renamed: Record<string, string>;
  replacements: Record<string, string[]>;
  retired_command_hashes?: Record<string, string>;
  records: InventoryRecord[];
};

export type ReconcileStatus =
  | "current"
  | "retired"
  | "renamed"
  | "modified-managed"
  | "user-owned"
  | "unknown"
  | "conflict"
  | "diagnostic-state-only";

export type ReconcileItem = {
  path: string;
  status: ReconcileStatus;
  reason: string;
  sha256?: string;
  replacement?: string | null;
};

export type ReconcilePlan = {
  schema_version: 2;
  domain: "reconcile";
  scope: Scope;
  root: string;
  inventory_version: string;
  current: ReconcileItem[];
  retired: ReconcileItem[];
  renamed: ReconcileItem[];
  modified_managed: ReconcileItem[];
  user_owned: ReconcileItem[];
  unknown: ReconcileItem[];
  conflicts: ReconcileItem[];
  diagnostic_state_only: ReconcileItem[];
  operations: Array<{
    path: string;
    operation: "archive" | "execute" | "remove" | "write";
    sha256?: string;
    via?: "skills-cli" | "transaction";
  }>;
  portable_cleanup?: {
    source: typeof PORTABLE_SOURCE;
    names: string[];
    command: string[];
    cwd: string;
    environment: {
      HOME: string;
      XDG_CONFIG_HOME: string;
      XDG_STATE_HOME?: string;
      CODEX_HOME: string;
    };
    locks: Array<{ path: string; before_sha256: string; after_sha256: string }>;
    trees: Array<{ name: string; path: string; tree_sha256: string; files: number }>;
  };
  plan_digest: string;
  confirmation_digest?: string;
  superseded_plan?: SupersededPlan;
  confirmable: boolean;
  digest?: string;
  receipt_expires_at?: string;
};

export type ReconcileResult = {
  status: "ok";
  applied: true;
  plan: ReconcilePlan;
  portable_remove?: PortableRemoveResult;
};

export type PortableRemoveResult = {
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  timed_out?: boolean;
};

export type ReconcileOptions = TransactionOptions & {
  runPortableRemove?: (
    command: readonly string[],
    cwd: string,
    environment: NodeJS.ProcessEnv,
  ) => Promise<PortableRemoveResult>;
};

export class ReconcileError extends LifecycleError {}

function loadInventory(): Inventory {
  const value = JSON.parse(readFileSync(inventoryPath, "utf8")) as Partial<Inventory>;
  if (
    value.schema_version !== 2 ||
    typeof value.inventory_version !== "string" ||
    !Array.isArray(value.active_portable_skills) ||
    !Array.isArray(value.removed) ||
    !value.renamed ||
    typeof value.renamed !== "object" ||
    Array.isArray(value.renamed) ||
    !value.replacements ||
    typeof value.replacements !== "object" ||
    Array.isArray(value.replacements) ||
    !Array.isArray(value.records)
  ) {
    throw new ReconcileError("invalid_inventory", "Migration inventory has an unsupported schema");
  }
  return value as Inventory;
}

function scopeRoot(scope: Scope, cwd: string, home: string): string {
  return scope === "global" ? resolve(home) : resolve(cwd);
}

function environmentRoot(name: string, home: string, fallback: string): string {
  const configured = home === homedir() ? process.env[name]?.trim() : undefined;
  return resolve(configured || resolve(home, fallback));
}

function portableEnvironment(home: string) {
  const xdgState = home === homedir() ? process.env.XDG_STATE_HOME?.trim() : undefined;
  return {
    HOME: resolve(home),
    XDG_CONFIG_HOME: environmentRoot("XDG_CONFIG_HOME", home, ".config"),
    ...(xdgState ? { XDG_STATE_HOME: resolve(xdgState) } : {}),
    CODEX_HOME: environmentRoot("CODEX_HOME", home, ".codex"),
  };
}

function portableRoots(scope: Scope, cwd: string, home: string): string[] {
  if (scope === "project") return [resolve(cwd, ".agents", "skills")];
  const environment = portableEnvironment(home);
  return [
    resolve(home, ".agents", "skills"),
    resolve(environment.XDG_CONFIG_HOME, "opencode", "skills"),
    resolve(environment.CODEX_HOME, "skills"),
  ].filter((value, index, values) => values.indexOf(value) === index);
}

function reconcileAllowedRoots(scope: Scope, cwd: string, home: string): string[] {
  const environment = portableEnvironment(home);
  const lock =
    scope === "global"
      ? environment.XDG_STATE_HOME
        ? resolve(environment.XDG_STATE_HOME, "skills")
        : resolve(home, ".agents")
      : resolve(cwd);
  return [archiveRoot(scope, cwd, home), ...portableRoots(scope, cwd, home), lock];
}

function displayPath(root: string, target: string): string {
  const value = relative(resolve(root), resolve(target));
  return !value.startsWith(`..${sep}`) && value !== ".." && !value.startsWith(sep)
    ? value.split(sep).join("/")
    : resolve(target);
}

function safePortableName(name: string): boolean {
  return name.length <= 64 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name);
}

function relativePath(root: string, target: string): string {
  const value = relative(resolve(root), resolve(target));
  if (!value || value.startsWith(`..${sep}`) || value === "..")
    throw new ReconcileError("unsafe_path", `Path is outside reconcile root: ${target}`);
  return value.split(sep).join("/");
}

function safeTarget(root: string, path: string): string {
  try {
    return destination(root, path);
  } catch (error) {
    if (error instanceof LifecycleError) throw new ReconcileError(error.code, error.message);
    throw error;
  }
}

async function metadata(path: string): Promise<Awaited<ReturnType<typeof lstat>> | undefined> {
  try {
    return await lstat(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

async function regular(
  path: string,
): Promise<{ content: Buffer; mode: number } | { unsafe: true } | undefined> {
  try {
    await assertSafePath(path);
  } catch (error) {
    if (error instanceof LifecycleError && error.code === "unsafe_path") return { unsafe: true };
    throw error;
  }
  const info = await metadata(path);
  if (!info) return undefined;
  if (info.isSymbolicLink() || !info.isFile() || info.nlink !== 1) return { unsafe: true };
  return { content: await readFile(path), mode: Number(info.mode) & 0o777 };
}

async function filesUnder(
  root: string,
): Promise<
  Array<{ relative: string; absolute: string; content?: Buffer; mode?: number; unsafe?: true }>
> {
  const info = await metadata(root);
  if (!info) return [];
  if (info.isSymbolicLink() || !info.isDirectory())
    return [{ relative: "", absolute: root, unsafe: true }];
  const result: Array<{
    relative: string;
    absolute: string;
    content?: Buffer;
    mode?: number;
    unsafe?: true;
  }> = [];
  let fileCount = 0;
  let totalBytes = 0;
  let entryCount = 0;
  let exceeded = false;
  const exceed = (absolute: string) => {
    if (!exceeded) result.push({ relative: relativePath(root, absolute), absolute, unsafe: true });
    exceeded = true;
  };
  async function visit(directory: string, depth: number): Promise<void> {
    if (exceeded) return;
    if (depth > PORTABLE_TREE_DEPTH_LIMIT) {
      exceed(directory);
      return;
    }
    const entries = [];
    const handle = await opendir(directory);
    for await (const entry of handle) {
      entryCount += 1;
      if (entryCount > PORTABLE_TREE_ENTRY_LIMIT) {
        exceed(directory);
        return;
      }
      entries.push(entry);
    }
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      if (exceeded) return;
      const absolute = join(directory, entry.name);
      const child = await metadata(absolute);
      if (!child || child.isSymbolicLink()) {
        result.push({ relative: relativePath(root, absolute), absolute, unsafe: true });
      } else if (child.isDirectory()) {
        await visit(absolute, depth + 1);
      } else if (child.isFile() && child.nlink === 1) {
        fileCount += 1;
        totalBytes += Number(child.size);
        if (
          fileCount > PORTABLE_TREE_FILE_LIMIT ||
          Number(child.size) > PORTABLE_FILE_LIMIT ||
          totalBytes > PORTABLE_TREE_BYTE_LIMIT
        ) {
          exceed(absolute);
          return;
        }
        result.push({
          relative: relativePath(root, absolute),
          absolute,
          content: await readFile(absolute),
          mode: Number(child.mode) & 0o777,
        });
      } else {
        result.push({ relative: relativePath(root, absolute), absolute, unsafe: true });
      }
    }
  }
  await visit(root, 0);
  return result;
}

function portableIdentity(content: Buffer): { name: string; source?: string } | undefined {
  const text = content.toString("utf8");
  if (!text.startsWith("---\n")) return undefined;
  const end = text.indexOf("\n---\n", 4);
  if (end < 0) return undefined;
  const lines = text.slice(4, end).split("\n");
  const scalar = (value: string): string | undefined => {
    const trimmed = value.trim();
    if (!trimmed || trimmed.startsWith("[") || trimmed.startsWith("{")) return undefined;
    const first = trimmed[0];
    const last = trimmed.at(-1);
    if (first === "'" || first === '"') {
      if (last !== first || trimmed.length < 2) return undefined;
      const inner = trimmed.slice(1, -1);
      return inner.includes(first) ? undefined : inner;
    }
    return last === "'" || last === '"' ? undefined : trimmed;
  };
  const allowed = new Set([
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
  ]);
  const fields = new Map<string, string>();
  const metadata = new Map<string, string>();
  let current = "";
  let block = false;
  for (const line of lines) {
    if (!line) continue;
    if (!line.startsWith(" ")) {
      const match = /^([a-z][a-z0-9-]*):\s*(.*)$/.exec(line);
      if (!match || !allowed.has(match[1]) || fields.has(match[1])) return undefined;
      current = match[1];
      const value = match[2];
      block = value === ">-" || value === "|" || value === "|-";
      if (current === "metadata") {
        if (value || block) return undefined;
      } else if (!block && scalar(value) === undefined) return undefined;
      fields.set(current, value);
      continue;
    }
    if (current === "metadata") {
      const match = /^  ([a-z][a-z0-9-]*):\s*(.*)$/.exec(line);
      if (!match || metadata.has(match[1])) return undefined;
      const value = scalar(match[2]);
      if (value === undefined) return undefined;
      metadata.set(match[1], value);
      continue;
    }
    if (!block || !/^  \S/.test(line)) return undefined;
  }
  if (!["name", "description", "license", "metadata"].every((key) => fields.has(key)))
    return undefined;
  const name = scalar(fields.get("name")!);
  const source = metadata.get("source");
  return name ? { name, ...(source ? { source } : {}) } : undefined;
}

function treeDigest(
  files: readonly { relative: string; content?: Buffer; mode?: number; unsafe?: true }[],
): string {
  return digest({
    schema_version: 1,
    files: files.map((file) => ({
      path: file.relative,
      mode: file.mode,
      size: file.content?.length,
      sha256: file.content ? sha256(file.content) : undefined,
    })),
  });
}

function item(
  path: string,
  status: ReconcileStatus,
  reason: string,
  content?: Buffer,
  replacement?: string | null,
): ReconcileItem {
  return {
    path,
    status,
    reason,
    ...(content ? { sha256: sha256(content) } : {}),
    ...(replacement !== undefined ? { replacement } : {}),
  };
}

function add(target: Record<ReconcileStatus, ReconcileItem[]>, value: ReconcileItem): void {
  target[value.status].push(value);
}

async function packageAssets(): Promise<Map<string, Buffer>> {
  const result = new Map<string, Buffer>();
  for (const category of ["commands", "plugins"] as const) {
    const directory = resolve(assetsRoot, category);
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((left, right) =>
      left.name.localeCompare(right.name),
    )) {
      if (!entry.isFile() || entry.isSymbolicLink())
        throw new ReconcileError("unsafe_path", `Package asset is not regular: ${entry.name}`);
      result.set(`${category}/${entry.name}`, await readFile(join(directory, entry.name)));
    }
  }
  return result;
}

function parseGenericManifest(raw: Buffer): Record<string, { sha256: string }> {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new ReconcileError("invalid_manifest", "Installation manifest is not valid JSON");
  }
  const manifest = value as { schema_version?: unknown; package?: unknown; files?: unknown };
  if (
    (manifest.schema_version !== 1 && manifest.schema_version !== 2) ||
    manifest.package !== PACKAGE_NAME ||
    !manifest.files ||
    typeof manifest.files !== "object" ||
    Array.isArray(manifest.files)
  )
    throw new ReconcileError(
      "invalid_manifest",
      "Installation manifest has an unsupported identity",
    );
  const files: Record<string, { sha256: string }> = {};
  for (const [path, record] of Object.entries(manifest.files)) {
    if (!/^[a-f0-9]{64}$/.test(String((record as { sha256?: unknown })?.sha256)))
      throw new ReconcileError(
        "invalid_manifest",
        `Installation manifest has invalid hash: ${path}`,
      );
    files[path] = { sha256: (record as { sha256: string }).sha256 };
  }
  return files;
}

function retiredRecords(inventory: Inventory, scope: Scope): InventoryRecord[] {
  const commandRecords: InventoryRecord[] = Object.entries(
    inventory.retired_command_hashes ?? {},
  ).map(([installed_path, sha256]) => ({
    id: `package-command:${installed_path}`,
    kind: "package-command",
    historical_path: `packages/opencode/assets/${installed_path}`,
    installed_path,
    introduced: { ref: "5f09d504758b0e99ad9c0306df796411fbcf0f4a", version: "1.2.0" },
    retired: { ref: "5f09d504758b0e99ad9c0306df796411fbcf0f4a", version: "2.0.0" },
    replacement: null,
    scopes: ["project", "global"],
    sha256,
  }));
  return [...inventory.records, ...commandRecords].filter(
    (record) => record.retired && record.scopes.includes(scope),
  );
}

async function diagnostic(home: string): Promise<ReconcileItem[]> {
  const base =
    process.env.XDG_STATE_HOME && home === homedir()
      ? resolve(process.env.XDG_STATE_HOME)
      : resolve(home, ".local", "state");
  const result: ReconcileItem[] = [];
  for (const name of ["goal", "multi-run"]) {
    const path = resolve(base, "opencode", "skills", name);
    if (await metadata(path))
      result.push(
        item(path, "diagnostic-state-only", "runtime state is not inspected or migrated"),
      );
  }
  return result;
}

type Built = {
  plan: ReconcilePlan;
  mutations: FileMutation[];
};

function portableRemoveCommand(scope: Scope, names: readonly string[]): string[] {
  return [
    "npx",
    "--yes",
    skillsInstallerSpec(),
    "remove",
    ...names,
    "--agent",
    "opencode",
    "--agent",
    "codex",
    ...(scope === "global" ? ["--global"] : []),
    "--yes",
  ];
}

function boundedAppend(current: Buffer, chunk: Buffer): { value: Buffer; truncated: boolean } {
  if (current.length >= PROCESS_OUTPUT_LIMIT) return { value: current, truncated: true };
  const remaining = PROCESS_OUTPUT_LIMIT - current.length;
  return {
    value: Buffer.concat([current, chunk.subarray(0, remaining)]),
    truncated: chunk.length > remaining,
  };
}

async function runPortableRemove(
  command: readonly string[],
  cwd: string,
  environment: NodeJS.ProcessEnv,
): Promise<PortableRemoveResult> {
  return new Promise((resolvePromise, reject) => {
    const windows = process.platform === "win32";
    if (windows && command.some((value) => !/^[A-Za-z0-9_./:@=-]+$/.test(value))) {
      reject(new ReconcileError("invalid_plan", "Portable remover has an unsafe Windows argument"));
      return;
    }
    const executable = windows ? (process.env.ComSpec ?? "cmd.exe") : command[0];
    const arguments_ = windows
      ? ["/d", "/s", "/c", `npx.cmd ${command.slice(1).join(" ")}`]
      : command.slice(1);
    const child = spawn(executable, arguments_, {
      cwd,
      env: environment,
      shell: false,
      detached: !windows,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = Buffer.alloc(0);
    let stderr = Buffer.alloc(0);
    let stdoutTruncated = false;
    let stderrTruncated = false;
    let timedOut = false;
    let forceTimeout: NodeJS.Timeout | undefined;
    const terminate = (signal: NodeJS.Signals) => {
      if (!windows && child.pid) {
        try {
          process.kill(-child.pid, signal);
          return;
        } catch {}
      }
      if (windows && child.pid) {
        const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
          stdio: "ignore",
          windowsHide: true,
        });
        killer.on("error", () => undefined);
      }
      child.kill(signal);
    };
    const timeout = setTimeout(() => {
      timedOut = true;
      terminate("SIGTERM");
      forceTimeout = setTimeout(() => terminate("SIGKILL"), 5_000);
    }, PROCESS_TIMEOUT_MS);
    child.stdout.on("data", (chunk: Buffer) => {
      const next = boundedAppend(stdout, chunk);
      stdout = next.value;
      stdoutTruncated ||= next.truncated;
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const next = boundedAppend(stderr, chunk);
      stderr = next.value;
      stderrTruncated ||= next.truncated;
    });
    child.once("error", (error) => {
      clearTimeout(timeout);
      if (forceTimeout) clearTimeout(forceTimeout);
      reject(error);
    });
    child.once("close", (code, signal) => {
      clearTimeout(timeout);
      if (forceTimeout) clearTimeout(forceTimeout);
      resolvePromise({
        code,
        signal,
        stdout: stdout.toString("utf8"),
        stderr: stderr.toString("utf8"),
        stdout_truncated: stdoutTruncated,
        stderr_truncated: stderrTruncated,
        timed_out: timedOut,
      });
    });
  });
}

async function build(scope: Scope, cwd = process.cwd(), home = homedir()): Promise<Built> {
  const inventory = loadInventory();
  const retiredPortableNames = new Set([
    ...inventory.removed,
    ...Object.keys(inventory.renamed),
    ...Object.keys(inventory.replacements),
  ]);
  const root = scopeRoot(scope, cwd, home);
  const deployment = resolve(root, scope === "global" ? ".config/opencode" : ".opencode");
  const portableLocations = portableRoots(scope, cwd, home);
  const portableEnv = portableEnvironment(home);
  const currentAssets = await packageAssets();
  const retired = retiredRecords(inventory, scope);
  const groups: Record<ReconcileStatus, ReconcileItem[]> = {
    current: [],
    retired: [],
    renamed: [],
    "modified-managed": [],
    "user-owned": [],
    unknown: [],
    conflict: [],
    "diagnostic-state-only": [],
  };
  const mutations: FileMutation[] = [];
  const portableMutationTargets = new Set<string>();
  const archiveCandidates: ArchiveCandidate[] = [];
  const portableTrees: Array<{
    name: string;
    path: string;
    root: string;
    tree_sha256: string;
    files: number;
  }> = [];
  const managed = new Map<string, { sha256: string }>();
  const manifestPath = join(deployment, GENERIC_MANIFEST);
  const manifestValue = await regular(manifestPath);
  let manifestRaw: Buffer | undefined;
  let manifestFiles: Record<string, { sha256: string }> = {};
  if (manifestValue && "unsafe" in manifestValue) {
    add(
      groups,
      item(
        relativePath(root, manifestPath),
        "conflict",
        "installation manifest is a symlink or non-regular file",
      ),
    );
  } else if (manifestValue) {
    manifestRaw = manifestValue.content;
    try {
      manifestFiles = parseGenericManifest(manifestRaw);
      for (const [path, record] of Object.entries(manifestFiles)) managed.set(path, record);
      add(
        groups,
        item(
          relativePath(root, manifestPath),
          "current",
          "package ownership manifest is valid",
          manifestRaw,
        ),
      );
    } catch (error) {
      add(
        groups,
        item(
          relativePath(root, manifestPath),
          "conflict",
          error instanceof Error ? error.message : "installation manifest is invalid",
          manifestRaw,
        ),
      );
      manifestRaw = undefined;
      manifestFiles = {};
    }
  }

  const retiredByPath = new Map(
    retired
      .filter(
        (record) => record.kind !== "portable-skill" && record.kind !== "installation-metadata",
      )
      .map((record) => [record.installed_path, record]),
  );
  for (const [path, record] of retiredByPath) {
    const target = safeTarget(deployment, path);
    const value = await regular(target);
    const manifestRecord = manifestFiles[path];
    if (value && "unsafe" in value) {
      add(
        groups,
        item(
          relativePath(root, target),
          "conflict",
          "retired asset is a symlink or non-regular file",
        ),
      );
    } else if (
      value &&
      record.sha256 === sha256(value.content) &&
      (!manifestRecord || manifestRecord.sha256 === sha256(value.content))
    ) {
      const status = record.replacement ? "renamed" : "retired";
      add(
        groups,
        item(
          relativePath(root, target),
          status,
          record.replacement
            ? "exact historical SHA-256 proves renamed package ownership"
            : "exact historical SHA-256 proves retired package ownership",
          value.content,
          record.replacement,
        ),
      );
      const kind =
        record.kind === "package-command"
          ? "command"
          : record.kind === "package-plugin"
            ? "plugin"
            : "state";
      archiveCandidates.push({
        path: relativePath(root, target),
        record: { sha256: record.sha256!, mode: 0o644, kind },
        content: value.content,
        reason: "retired inventory asset",
        kind,
      });
      mutations.push({
        path: relativePath(root, target),
        operation: "remove",
        expected: { sha256: sha256(value.content) },
      });
    } else if (!value && manifestRecord && record.sha256 === manifestRecord.sha256) {
      const status = record.replacement ? "renamed" : "retired";
      add(
        groups,
        item(
          relativePath(root, target),
          status,
          "stale exact package ownership record",
          undefined,
          record.replacement,
        ),
      );
    } else if (value) {
      add(
        groups,
        item(
          relativePath(root, target),
          "conflict",
          "retired asset is modified or ownership is ambiguous",
          value.content,
        ),
      );
    }
  }

  for (const [path, content] of currentAssets) {
    const target = safeTarget(deployment, path);
    const value = await regular(target);
    const manifestRecord = manifestFiles[path] ?? managed.get(path);
    if (!value) continue;
    if ("unsafe" in value) {
      add(
        groups,
        item(
          relativePath(root, target),
          "conflict",
          "managed asset is a symlink or non-regular file",
        ),
      );
    } else if (
      manifestRecord &&
      manifestRecord.sha256 === sha256(value.content) &&
      sha256(content) === sha256(value.content)
    ) {
      add(
        groups,
        item(
          relativePath(root, target),
          "current",
          "current canonical package asset",
          value.content,
        ),
      );
    } else if (manifestRecord) {
      add(
        groups,
        item(
          relativePath(root, target),
          "modified-managed",
          "managed asset differs from its recorded SHA-256",
          value.content,
        ),
      );
    } else {
      add(
        groups,
        item(
          relativePath(root, target),
          "user-owned",
          "asset exists without package ownership evidence",
          value.content,
        ),
      );
    }
  }

  for (const path of Object.keys(manifestFiles).sort()) {
    if (currentAssets.has(path) || retiredByPath.has(path)) continue;
    let target: string;
    try {
      target = safeTarget(deployment, path);
    } catch (error) {
      add(
        groups,
        item(path, "conflict", error instanceof Error ? error.message : "manifest path is unsafe"),
      );
      continue;
    }
    const value = await regular(target);
    if (value && "unsafe" in value)
      add(
        groups,
        item(
          relativePath(root, target),
          "conflict",
          "manifest target is a symlink or non-regular file",
        ),
      );
    else if (value)
      add(
        groups,
        item(
          relativePath(root, target),
          "unknown",
          "manifest entry is outside the current public inventory",
          value.content,
        ),
      );
    else
      add(
        groups,
        item(relativePath(root, target), "unknown", "manifest entry has no current asset"),
      );
  }

  for (const category of ["commands", "plugins"] as const) {
    const directory = resolve(deployment, category);
    const entries = await metadata(directory);
    if (!entries) continue;
    if (entries.isSymbolicLink() || !entries.isDirectory()) {
      add(
        groups,
        item(
          relativePath(root, directory),
          "conflict",
          "asset directory is a symlink or non-directory",
        ),
      );
      continue;
    }
    for (const entry of await readdir(directory)) {
      const path = `${category}/${entry}`;
      if (currentAssets.has(path) || retiredByPath.has(path) || manifestFiles[path]) continue;
      const value = await regular(join(directory, entry));
      if (value && "unsafe" in value)
        add(
          groups,
          item(
            relativePath(root, join(directory, entry)),
            "conflict",
            "unmanaged asset is a symlink or non-regular file",
          ),
        );
      else if (value)
        add(
          groups,
          item(
            relativePath(root, join(directory, entry)),
            "user-owned",
            "asset has no public package ownership evidence",
            value.content,
          ),
        );
    }
  }

  const semanticPath = safeTarget(deployment, SEMANTIC_MANIFEST);
  const semanticValue = await regular(semanticPath);
  const agentHashes = new Map<string, string>();
  if (semanticValue && "unsafe" in semanticValue) {
    add(
      groups,
      item(
        relativePath(root, semanticPath),
        "conflict",
        "agent ownership manifest is a symlink or non-regular file",
      ),
    );
  } else if (semanticValue) {
    try {
      const parsed = JSON.parse(semanticValue.content.toString("utf8")) as {
        profiles?: Record<string, { rendered_sha256?: unknown }>;
      };
      for (const [name, record] of Object.entries(parsed.profiles ?? {})) {
        if (typeof record.rendered_sha256 === "string")
          agentHashes.set(`${name}.md`, record.rendered_sha256);
      }
      add(
        groups,
        item(
          relativePath(root, semanticPath),
          "current",
          "agent ownership manifest is valid",
          semanticValue.content,
        ),
      );
    } catch {
      add(
        groups,
        item(
          relativePath(root, semanticPath),
          "conflict",
          "agent ownership manifest is not valid JSON",
        ),
      );
    }
  }
  const agentDirectory = resolve(deployment, "agents");
  const agentInfo = await metadata(agentDirectory);
  if (agentInfo?.isSymbolicLink() || (agentInfo && !agentInfo.isDirectory())) {
    add(
      groups,
      item(
        relativePath(root, agentDirectory),
        "conflict",
        "agent directory is a symlink or non-directory",
      ),
    );
  } else if (agentInfo?.isDirectory()) {
    for (const entry of await readdir(agentDirectory)) {
      const target = join(agentDirectory, entry);
      const value = await regular(target);
      if (value && "unsafe" in value)
        add(
          groups,
          item(relativePath(root, target), "conflict", "agent is a symlink or non-regular file"),
        );
      else if (!value)
        add(
          groups,
          item(relativePath(root, target), "unknown", "agent ownership record has no file"),
        );
      else if (agentHashes.get(entry) === sha256(value.content))
        add(
          groups,
          item(
            relativePath(root, target),
            "current",
            "semantic agent manifest proves package ownership",
            value.content,
          ),
        );
      else if (agentHashes.has(entry))
        add(
          groups,
          item(
            relativePath(root, target),
            "modified-managed",
            "semantic agent manifest hash differs",
            value.content,
          ),
        );
      else
        add(
          groups,
          item(
            relativePath(root, target),
            "user-owned",
            "agent has no semantic ownership record",
            value.content,
          ),
        );
    }
  }

  const installed = new Map<string, Array<{ directory: string; portableRoot: string }>>();
  for (const portableRoot of portableLocations) {
    const portableInfo = await metadata(portableRoot);
    if (portableInfo?.isSymbolicLink() || (portableInfo && !portableInfo.isDirectory())) {
      add(
        groups,
        item(
          displayPath(root, portableRoot),
          "conflict",
          "portable skill root is a symlink or non-directory",
        ),
      );
      continue;
    }
    for (const entry of portableInfo?.isDirectory() ? (await readdir(portableRoot)).sort() : []) {
      const directory = resolve(portableRoot, entry);
      const directoryInfo = await metadata(directory);
      if (!directoryInfo?.isDirectory() || directoryInfo.isSymbolicLink()) {
        add(
          groups,
          item(
            displayPath(root, directory),
            "unknown",
            "portable skill entry is an external symlink or non-directory",
          ),
        );
        continue;
      }
      const values = installed.get(entry) ?? [];
      values.push({ directory, portableRoot });
      installed.set(entry, values);
    }
  }

  for (const [entry, locations] of [...installed].sort(([left], [right]) =>
    left.localeCompare(right),
  )) {
    if (inventory.active_portable_skills.includes(entry)) {
      for (const { directory } of locations)
        add(groups, item(displayPath(root, directory), "current", "current portable skill source"));
      continue;
    }
    if (!safePortableName(entry)) {
      for (const { directory } of locations)
        add(
          groups,
          item(
            displayPath(root, directory),
            "conflict",
            "portable skill name is unsafe for delegated removal",
          ),
        );
      continue;
    }
    const candidates: Array<{
      directory: string;
      portableRoot: string;
      files: Awaited<ReturnType<typeof filesUnder>>;
    }> = [];
    let blocked = false;
    for (const { directory, portableRoot } of locations) {
      const path = displayPath(root, directory);
      const skill = await regular(resolve(directory, "SKILL.md"));
      if (!skill || "unsafe" in skill) {
        add(groups, item(path, "unknown", "portable skill has no safe SKILL.md ownership marker"));
        blocked = true;
        continue;
      }
      const identity = portableIdentity(skill.content);
      if (identity?.name !== entry || identity.source !== PORTABLE_SOURCE) {
        add(
          groups,
          item(path, "unknown", "portable skill is outside the marked project inventory"),
        );
        blocked = true;
        continue;
      }
      const files = await filesUnder(directory);
      if (
        !files.length ||
        files.some((file) => file.unsafe || !file.content || file.mode === undefined)
      ) {
        add(groups, item(path, "conflict", "marked portable skill contains an unsafe file"));
        blocked = true;
        continue;
      }
      candidates.push({ directory, portableRoot, files });
    }
    if (blocked) continue;
    if (!retiredPortableNames.has(entry)) {
      for (const candidate of candidates)
        add(
          groups,
          item(
            displayPath(root, candidate.directory),
            "unknown",
            "marked portable skill is not declared retired by this package inventory",
          ),
        );
      continue;
    }
    const replacement = inventory.renamed[entry];
    const status: ReconcileStatus = replacement ? "renamed" : "retired";
    for (const candidate of candidates) {
      const path = displayPath(root, candidate.directory);
      add(
        groups,
        item(
          path,
          status,
          replacement
            ? "project source marker proves renamed portable ownership"
            : "project source marker proves retired portable ownership",
          undefined,
          replacement,
        ),
      );
      portableTrees.push({
        name: entry,
        path,
        root: candidate.portableRoot,
        tree_sha256: treeDigest(candidate.files),
        files: candidate.files.length,
      });
      for (const file of candidate.files) {
        const target = `${entry}/${file.relative}`;
        archiveCandidates.push({
          path: displayPath(root, file.absolute),
          record: {
            sha256: sha256(file.content!),
            mode: file.mode!,
            kind: "state",
          },
          content: file.content!,
          reason: `${status} portable skill`,
          kind: "state",
        });
        mutations.push({
          root: candidate.portableRoot,
          path: target,
          operation: "external-remove",
          expected: { sha256: sha256(file.content!) },
        });
        portableMutationTargets.add(file.absolute);
      }
    }
  }

  const portableNames = [...new Set(portableTrees.map((tree) => tree.name))].sort();
  const locks: Array<{ path: string; before_sha256: string; after_sha256: string }> = [];
  if (portableNames.length) {
    const lockPath =
      scope === "global"
        ? portableEnv.XDG_STATE_HOME
          ? resolve(portableEnv.XDG_STATE_HOME, "skills", ".skill-lock.json")
          : resolve(home, ".agents", ".skill-lock.json")
        : resolve(root, "skills-lock.json");
    const lock = await regular(lockPath);
    if (lock && "unsafe" in lock) {
      add(groups, item(lockPath, "conflict", "portable installer lock is unsafe"));
    } else if (lock) {
      try {
        const parsed = JSON.parse(lock.content.toString("utf8")) as {
          version?: unknown;
          skills?: Record<string, unknown>;
          [key: string]: unknown;
        };
        if (typeof parsed.version !== "number" || !parsed.skills || Array.isArray(parsed.skills))
          throw new Error("unsupported lock");
        if (
          (scope === "global" && parsed.version < 3) ||
          (scope === "project" && parsed.version < 1)
        )
          throw new Error("unsupported lock version");
        const tracked = portableNames.filter((name) => Object.hasOwn(parsed.skills!, name));
        if (tracked.length) {
          const remaining = Object.fromEntries(
            Object.entries(parsed.skills).filter(([name]) => !portableNames.includes(name)),
          );
          const next = Buffer.from(
            scope === "global"
              ? JSON.stringify({ ...parsed, skills: remaining }, null, 2)
              : `${JSON.stringify({ version: parsed.version, skills: Object.fromEntries(Object.entries(remaining).sort(([left], [right]) => left.localeCompare(right))) }, null, 2)}\n`,
          );
          const lockRoot = resolve(dirname(lockPath));
          mutations.push({
            root: lockRoot,
            path: lockPath.slice(lockRoot.length + 1),
            operation: "external-write",
            content: next,
            mode: (await lstat(lockPath)).mode & 0o777,
            expected: { sha256: sha256(lock.content) },
          });
          portableMutationTargets.add(lockPath);
          locks.push({
            path: lockPath,
            before_sha256: sha256(lock.content),
            after_sha256: sha256(next),
          });
        }
      } catch {
        add(groups, item(lockPath, "conflict", "portable installer lock is not valid JSON"));
      }
    }
  }

  if (archiveCandidates.length && manifestRaw) {
    for (const candidate of archiveCandidates) {
      delete manifestFiles[candidate.path];
      delete manifestFiles[candidate.path.replace(/^\.opencode\//, "")];
    }
    const value = JSON.parse(manifestRaw.toString("utf8")) as Record<string, unknown>;
    const next = Buffer.from(`${stable({ ...value, files: manifestFiles })}\n`);
    if (!next.equals(manifestRaw))
      mutations.push({
        path: relativePath(root, manifestPath),
        operation: "write",
        content: next,
        mode: 0o600,
        expected: { sha256: sha256(manifestRaw) },
      });
  }
  mutations.push(
    ...(await archiveMutations(archiveCandidates, scope, cwd, home, inventory.inventory_version)),
  );

  const command = portableRemoveCommand(scope, portableNames);
  const operations: ReconcilePlan["operations"] = mutations
    .filter(
      (mutation) =>
        !portableMutationTargets.has(destination(resolve(mutation.root ?? root), mutation.path)),
    )
    .map((mutation) => ({
      path: mutation.root ? resolve(mutation.root, mutation.path) : mutation.path,
      operation: mutation.root
        ? ("archive" as const)
        : mutation.operation === "external-write"
          ? ("write" as const)
          : mutation.operation === "external-remove"
            ? ("remove" as const)
            : mutation.operation,
      ...(mutation.operation === "write" || mutation.operation === "external-write"
        ? { sha256: sha256(mutation.content) }
        : {}),
    }));
  for (const tree of portableTrees) {
    operations.push({ path: tree.path, operation: "archive", sha256: tree.tree_sha256 });
    operations.push({ path: tree.path, operation: "remove", via: "skills-cli" });
  }
  for (const lock of locks)
    operations.push({
      path: lock.path,
      operation: "write",
      sha256: lock.after_sha256,
      via: "skills-cli",
    });
  if (portableNames.length)
    operations.push({ path: command[0], operation: "execute", via: "skills-cli" });
  const base = {
    schema_version: 2 as const,
    domain: "reconcile" as const,
    scope,
    root,
    inventory_version: inventory.inventory_version,
    current: groups.current.sort((left, right) => left.path.localeCompare(right.path)),
    retired: groups.retired.sort((left, right) => left.path.localeCompare(right.path)),
    renamed: groups.renamed.sort((left, right) => left.path.localeCompare(right.path)),
    modified_managed: groups["modified-managed"].sort((left, right) =>
      left.path.localeCompare(right.path),
    ),
    user_owned: groups["user-owned"].sort((left, right) => left.path.localeCompare(right.path)),
    unknown: groups.unknown.sort((left, right) => left.path.localeCompare(right.path)),
    conflicts: groups.conflict.sort((left, right) => left.path.localeCompare(right.path)),
    diagnostic_state_only: await diagnostic(home),
    operations: operations.sort((left, right) => left.path.localeCompare(right.path)),
    ...(portableNames.length
      ? {
          portable_cleanup: {
            source: PORTABLE_SOURCE,
            names: portableNames,
            command,
            cwd: root,
            environment: portableEnv,
            locks,
            trees: portableTrees
              .map(({ root: _root, ...tree }) => tree)
              .sort((left, right) => left.path.localeCompare(right.path)),
          },
        }
      : {}),
  };
  const planDigest = digest(base);
  const confirmable =
    operations.length > 0 &&
    groups["modified-managed"].length === 0 &&
    groups.conflict.length === 0;
  return {
    plan: { ...base, plan_digest: planDigest, confirmable, digest: planDigest },
    mutations,
  };
}

export async function previewReconcile(
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<ReconcilePlan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = scopeRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot, reconcileAllowedRoots(scope, cwd, home)))
        throw new ReconcileError(
          "recovered_transaction",
          "Recovered an interrupted transaction; request a fresh plan",
        );
      const built = await build(scope, cwd, home);
      const blocked = built.plan.modified_managed.length > 0 || built.plan.conflicts.length > 0;
      const actionable = built.plan.operations.length > 0;
      if (blocked || !actionable) {
        await supersedeReceipt(stateRoot);
        const { digest: _digest, ...withoutReceipt } = built.plan;
        return { ...withoutReceipt, confirmable: false };
      }
      const receipt = await saveReceipt(
        stateRoot,
        "reconcile",
        scope,
        root,
        {
          plan_digest: built.plan.plan_digest,
        },
        Date.now(),
        built.plan.plan_digest,
      );
      return {
        ...built.plan,
        plan_digest: built.plan.plan_digest,
        confirmation_digest: receipt.digest,
        digest: receipt.digest,
        confirmable: true,
        receipt_expires_at: receipt.expires_at,
        ...(receipt.superseded_plan ? { superseded_plan: receipt.superseded_plan } : {}),
      };
    });
  } catch (error) {
    if (error instanceof ReconcileError) throw error;
    if (error instanceof LifecycleError) throw new ReconcileError(error.code, error.message);
    throw error;
  }
}

/** Build the ownership classification without receipts, locks, or recovery. */
export async function inspectReconcile(
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<ReconcilePlan> {
  return (await build(scope, cwd, home)).plan;
}

export async function applyReconcile(
  scope: Scope,
  confirmationDigest: string,
  cwd = process.cwd(),
  home = homedir(),
  options: ReconcileOptions = {},
): Promise<ReconcileResult> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = scopeRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot, reconcileAllowedRoots(scope, cwd, home)))
        throw new ReconcileError(
          "recovered_transaction",
          "Recovered an interrupted transaction; request a fresh plan",
        );
      const payload = (await consumeReceipt(stateRoot, {
        digest: confirmationDigest,
        kind: "reconcile",
        scope,
        root,
      })) as { plan_digest?: string; digest?: string };
      const built = await build(scope, cwd, home);
      if (built.plan.plan_digest !== (payload.plan_digest ?? payload.digest))
        throw new ReconcileError("stale_plan", "Reconcile inventory changed after preview");
      if (built.plan.conflicts.length || built.plan.modified_managed.length)
        throw new ReconcileError("conflict", "Reconcile contains unsafe ownership conflicts");
      const cleanup = built.plan.portable_cleanup;
      let portableRemove: PortableRemoveResult | undefined;
      await applyTransaction(root, stateRoot, built.mutations, {
        ...options,
        applyExternal: async () => {
          await options.applyExternal?.();
          if (!cleanup) return;
          const environment: NodeJS.ProcessEnv = {
            ...process.env,
            ...cleanup.environment,
            DO_NOT_TRACK: "1",
          };
          if (!cleanup.environment.XDG_STATE_HOME) delete environment.XDG_STATE_HOME;
          const result = await (options.runPortableRemove ?? runPortableRemove)(
            cleanup.command,
            cleanup.cwd,
            environment,
          );
          portableRemove = result;
          if (result.code !== 0 || result.signal || result.timed_out)
            throw new ReconcileError(
              "portable_remove_failed",
              `skills remove failed with ${result.signal ?? `exit ${result.code}`}`,
            );
        },
        validateFinal: async () => {
          await options.validateFinal?.();
          if (cleanup) {
            for (const tree of cleanup.trees)
              if (await metadata(resolve(root, tree.path)))
                throw new ReconcileError(
                  "final_validation_failed",
                  `skills remove retained portable skill: ${tree.path}`,
                );
            for (const expected of cleanup.locks) {
              const lock = await regular(expected.path);
              if (!lock || "unsafe" in lock || sha256(lock.content) !== expected.after_sha256)
                throw new ReconcileError(
                  "final_validation_failed",
                  `skills remove left an invalid lock: ${expected.path}`,
                );
            }
          }
          const final = await build(scope, cwd, home);
          if (
            final.plan.retired.length ||
            final.plan.renamed.length ||
            final.plan.operations.length
          )
            throw new ReconcileError(
              "final_validation_failed",
              "Retired assets remain after reconcile",
            );
        },
      });
      return {
        status: "ok",
        applied: true,
        plan: { ...built.plan, digest: confirmationDigest },
        ...(portableRemove ? { portable_remove: portableRemove } : {}),
      };
    });
  } catch (error) {
    if (error instanceof ReconcileError) throw error;
    if (error instanceof LifecycleError) throw new ReconcileError(error.code, error.message);
    throw error;
  }
}
