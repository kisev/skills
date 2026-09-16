import { readFileSync } from "node:fs";
import { lstat, readdir, readFile } from "node:fs/promises";
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

const PACKAGE_NAME = "@kisev/skills-opencode";
const GENERIC_MANIFEST = ".skills-opencode-manifest.json";
const SEMANTIC_MANIFEST = ".skills-opencode/agent-profiles.manifest.json";
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
    operation: "archive" | "remove" | "write";
    sha256?: string;
  }>;
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
};

export type ReconcileOptions = TransactionOptions;

export class ReconcileError extends LifecycleError {}

function loadInventory(): Inventory {
  const value = JSON.parse(readFileSync(inventoryPath, "utf8")) as Partial<Inventory>;
  if (
    value.schema_version !== 2 ||
    typeof value.inventory_version !== "string" ||
    !Array.isArray(value.records)
  ) {
    throw new ReconcileError("invalid_inventory", "Migration inventory has an unsupported schema");
  }
  return value as Inventory;
}

function scopeRoot(scope: Scope, cwd: string, home: string): string {
  return scope === "global" ? resolve(home) : resolve(cwd);
}

function reconcileAllowedRoots(scope: Scope, cwd: string, home: string): string[] {
  return [archiveRoot(scope, cwd, home)];
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

async function build(scope: Scope, cwd = process.cwd(), home = homedir()): Promise<Built> {
  const inventory = loadInventory();
  const root = scopeRoot(scope, cwd, home);
  const deployment = resolve(root, scope === "global" ? ".config/opencode" : ".opencode");
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
  const archiveCandidates: ArchiveCandidate[] = [];
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

  const operations: ReconcilePlan["operations"] = mutations.map((mutation) => ({
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
      await applyTransaction(root, stateRoot, built.mutations, {
        ...options,
        validateFinal: async () => {
          await options.validateFinal?.();
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
      };
    });
  } catch (error) {
    if (error instanceof ReconcileError) throw error;
    if (error instanceof LifecycleError) throw new ReconcileError(error.code, error.message);
    throw error;
  }
}
