import { readFileSync } from "node:fs";
import { lstat, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildAgentProfilePlan,
  listAgentProfiles,
  validateBuiltAgentProfilePlan,
  type LegacyInstallerManifest,
} from "./agent-profiles.js";
import {
  applyTransaction,
  archiveRoot,
  consumeReceipt,
  deploymentRoot,
  destination,
  digest,
  LifecycleError,
  lifecycleRoot,
  readRegular,
  recoverTransaction,
  saveReceipt,
  sha256,
  stable,
  withLifecycleLock,
  type SupersededPlan,
  type FileMutation,
  type Scope,
  type TransactionOptions,
} from "./lifecycle.js";
import { CATALOG } from "./catalog.js";
import { FIXED_AGENT_ROLES, type FixedAgentRole } from "./agent-profiles.js";

export type { Scope } from "./lifecycle.js";

const PACKAGE_NAME = "@kisev/skills-opencode";
const MANIFEST_NAME = ".skills-opencode-manifest.json";
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = resolve(packageRoot, "dist", "assets");

export type Action = "install" | "uninstall";
export type Operation = "create" | "update" | "remove" | "unchanged" | "missing" | "conflict" | "archive-pending";
export type PlanItem = { path: string; operation: Operation; reason?: string; sha256?: string };
export type SelectablePlugin = (typeof CATALOG.plugins)[number];
export type InstallerSelection = {
  commands: string[];
  agents: FixedAgentRole[];
  plugins: SelectablePlugin[];
  core_activation: boolean;
};
export type Plan = {
  schema_version: 2;
  action: Action;
  scope: Scope;
  root: string;
  package_version: string;
  selection: InstallerSelection;
  operations: PlanItem[];
  plan_digest: string;
  confirmation_digest?: string;
  superseded_plan?: SupersededPlan;
  digest: string;
  receipt_expires_at?: string;
  requires_restart: boolean;
};
type Asset = { relativePath: string; content: Buffer; sha256: string; mode: number };
type ManifestFile = { sha256: string; mode: number; kind: "command" | "agent" | "plugin" | "state" };
type Manifest = {
  schema_version: 2;
  package: string;
  package_version: string;
  version: string;
  scope: Scope;
  commands: string[];
  agents: FixedAgentRole[];
  plugins: SelectablePlugin[];
  core_activation: boolean;
  files: Record<string, ManifestFile>;
};
type BuiltInstallerPlan = {
  plan: Plan;
  mutations: FileMutation[];
  expectedManifest?: Buffer;
  profiles: Awaited<ReturnType<typeof buildAgentProfilePlan>>;
};
export type ArchiveCandidate = {
  path: string;
  record: ManifestFile;
  content: Buffer;
  reason: string;
  kind: "command" | "agent" | "plugin" | "state";
};

function retiredAssetPaths(): Set<string> {
  const inventory = JSON.parse(readFileSync(resolve(assetsRoot, "migration-inventory.json"), "utf8")) as {
    retired_command_hashes?: Record<string, string>;
    retired_plugin_hashes?: Record<string, string>;
  };
  return new Set([
    ...Object.keys(inventory.retired_command_hashes ?? {}),
    ...Object.keys(inventory.retired_plugin_hashes ?? {}),
  ]);
}

export const SELECTABLE_PLUGINS = [...CATALOG.plugins] as SelectablePlugin[];
export const PACKAGE_COMMANDS = [...CATALOG.package_commands] as string[];
export const SKILL_COMMANDS = [...CATALOG.skills] as string[];

export function defaultSelection(): InstallerSelection {
  return {
    commands: [...SKILL_COMMANDS, ...PACKAGE_COMMANDS].sort(),
    agents: [...FIXED_AGENT_ROLES],
    plugins: [],
    core_activation: true,
  };
}

export function normalizeSelection(value: Partial<InstallerSelection> = {}): InstallerSelection {
  const allCommands = new Set([...SKILL_COMMANDS, ...PACKAGE_COMMANDS]);
  const commands = [...new Set(value.commands ?? defaultSelection().commands)].sort();
  const agents = [...new Set(value.agents ?? FIXED_AGENT_ROLES)] as FixedAgentRole[];
  const plugins = [...new Set(value.plugins ?? [])] as SelectablePlugin[];
  if (commands.some((name) => !allCommands.has(name))) throw new InstallerError("invalid_selection", "Unknown command selection");
  if (agents.some((name) => !FIXED_AGENT_ROLES.includes(name))) throw new InstallerError("invalid_selection", "Unknown agent selection");
  if (plugins.some((name) => !SELECTABLE_PLUGINS.includes(name))) throw new InstallerError("invalid_selection", "Unknown plugin selection");
  return {
    commands,
    agents: agents.sort(),
    plugins: plugins.sort(),
    core_activation: Boolean(value.core_activation ?? (commands.some((name) => PACKAGE_COMMANDS.includes(name)) || agents.length)),
  };
}

export class InstallerError extends LifecycleError {}

function packageVersion(): string {
  const metadata = JSON.parse(readFileSync(resolve(packageRoot, "package.json"), "utf8")) as { version?: unknown };
  if (typeof metadata.version !== "string" || !metadata.version) throw new InstallerError("invalid_package", "Package version is unavailable");
  return metadata.version;
}

async function assets(selection: InstallerSelection): Promise<Asset[]> {
  const result: Asset[] = [];
  for (const category of ["commands", "plugins"] as const) {
    const directory = resolve(assetsRoot, category);
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name))) {
      const extension = category === "plugins" ? ".js" : ".md";
      const name = entry.name.slice(0, -extension.length);
      if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(extension)) throw new InstallerError("asset_error", `Asset is not a regular ${extension} file: ${entry.name}`);
      if (category === "plugins" && !selection.plugins.includes(name as SelectablePlugin)) continue;
      if (category === "commands" && !selection.commands.includes(name)) continue;
      const relativePath = `${category}/${entry.name}`;
      const content = await readRegular(destination(assetsRoot, relativePath));
      if (!content) throw new InstallerError("asset_error", `Asset is missing: ${relativePath}`);
      result.push({ relativePath, content, sha256: sha256(content), mode: 0o644 });
    }
  }
  return result.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
}

function parseManifest(raw: Buffer, path: string): Manifest {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new InstallerError("invalid_manifest", `Ownership manifest is not valid JSON: ${path}`);
  }
  const manifest = value as Partial<Manifest>;
  if (
    (manifest as { schema_version?: unknown }).schema_version === 1 &&
    manifest.package === PACKAGE_NAME &&
    typeof manifest.version === "string" &&
    manifest.files &&
    typeof manifest.files === "object" &&
    !Array.isArray(manifest.files)
  ) {
    const files = Object.fromEntries(
      Object.entries(manifest.files).map(([relativePath, record]) => [
        relativePath,
        {
          sha256: (record as { sha256: string }).sha256,
          mode: 0o644,
          kind: relativePath.startsWith("commands/")
            ? "command"
            : relativePath.startsWith("plugins/")
              ? "plugin"
              : relativePath.startsWith("agents/")
                ? "agent"
                : "state",
        },
      ]),
    ) as Manifest["files"];
    return {
      schema_version: 1 as unknown as 2,
      package: PACKAGE_NAME,
      package_version: manifest.version,
      version: manifest.version,
      scope: "global",
      commands: Object.keys(files).filter((path) => path.startsWith("commands/")).map((path) => path.slice(9, -3)).sort(),
      agents: [...FIXED_AGENT_ROLES].filter((role) => `agents/${role}.md` in files),
      plugins: Object.keys(files).filter((path) => path.startsWith("plugins/")).map((path) => path.slice(8, -3)).filter((name): name is SelectablePlugin => SELECTABLE_PLUGINS.includes(name as SelectablePlugin)),
      core_activation: true,
      files,
    };
  }
  if (manifest.schema_version !== 2 || manifest.package !== PACKAGE_NAME || typeof manifest.package_version !== "string" || (manifest.scope !== "global" && manifest.scope !== "project") || !Array.isArray(manifest.commands) || !Array.isArray(manifest.agents) || !Array.isArray(manifest.plugins) || typeof manifest.core_activation !== "boolean" || !manifest.files || typeof manifest.files !== "object" || Array.isArray(manifest.files)) {
    throw new InstallerError("invalid_manifest", `Ownership manifest has an unexpected format: ${path}`);
  }
  const files = Object.fromEntries(Object.entries(manifest.files).map(([relativePath, record]) => {
    destination("/", relativePath);
    if (!record || typeof record !== "object" || typeof (record as ManifestFile).sha256 !== "string" || !/^[a-f0-9]{64}$/.test((record as ManifestFile).sha256)) {
      throw new InstallerError("invalid_manifest", `Ownership manifest has an invalid record: ${relativePath}`);
    }
    const existing = record as Partial<ManifestFile>;
    return [relativePath, {
      sha256: existing.sha256,
      mode: Number.isInteger(existing.mode) ? existing.mode : 0o644,
      kind: ["command", "agent", "plugin", "state"].includes(String(existing.kind)) ? existing.kind : relativePath.startsWith("commands/") ? "command" : relativePath.startsWith("plugins/") ? "plugin" : relativePath.startsWith("agents/") ? "agent" : "state",
    }];
  })) as Manifest["files"];
  return { ...manifest, files } as Manifest;
}

async function currentManifest(root: string): Promise<{ manifest?: Manifest; raw?: Buffer }> {
  const path = destination(root, MANIFEST_NAME);
  const raw = await readRegular(path);
  return raw ? { manifest: parseManifest(raw, path), raw } : {};
}

export async function archiveMutations(
  candidates: readonly ArchiveCandidate[],
  scope: Scope,
  cwd: string,
  home: string,
  sourceVersion: string,
): Promise<FileMutation[]> {
  if (!candidates.length) return [];
  const root = archiveRoot(scope, cwd, home);
  const rootInfo = await lstat(root).catch((error: unknown) => {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw new InstallerError("unsafe_path", "Archive root is inaccessible");
  });
  if (rootInfo && (!rootInfo.isDirectory() || rootInfo.isSymbolicLink() || (rootInfo.mode & 0o077) !== 0))
    throw new InstallerError("unsafe_path", "Archive root must be a private directory");
  const objectsInfo = await lstat(join(root, "objects")).catch((error: unknown) => {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw new InstallerError("unsafe_path", "Archive object store is inaccessible");
  });
  if (objectsInfo && (!objectsInfo.isDirectory() || objectsInfo.isSymbolicLink() || (objectsInfo.mode & 0o077) !== 0))
    throw new InstallerError("unsafe_path", "Archive object store must be private");
  const indexPath = destination(root, "index.json");
  const existingRaw = await readRegular(indexPath);
  if (existingRaw) {
    const indexInfo = await lstat(indexPath);
    if ((indexInfo.mode & 0o777) !== 0o600)
      throw new InstallerError("unsafe_path", "Archive index must be private");
  }
  let entries: Array<Record<string, unknown>> = [];
  if (existingRaw) {
    try {
      const parsed = JSON.parse(existingRaw.toString("utf8")) as { schema_version?: unknown; entries?: unknown };
      if (parsed.schema_version !== 1 || !Array.isArray(parsed.entries)) throw new Error("invalid archive index");
      entries = parsed.entries.filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === "object" && !Array.isArray(entry)));
    } catch {
      throw new InstallerError("invalid_archive", "Archive index is not valid content-addressed state");
    }
  }
  const known = new Set(entries.map((entry) => `${String(entry.original_path)}:${String(entry.digest)}`));
  const mutations: FileMutation[] = [];
  const now = new Date(0).toISOString();
  for (const candidate of candidates) {
    const digestValue = sha256(candidate.content);
    const key = `${candidate.path}:${digestValue}`;
    if (known.has(key)) continue;
    const objectPath = `objects/${digestValue}`;
    const object = await readRegular(destination(root, objectPath));
    if (!object) {
      mutations.push({
        root,
        path: objectPath,
        operation: "write",
        content: candidate.content,
        mode: candidate.record.mode,
        expected: { absent: true },
      });
    } else if (sha256(object) !== digestValue) {
      throw new InstallerError("archive_collision", `Archive object collision: ${digestValue}`);
    }
    entries.push({
      schema_version: 1,
      digest: digestValue,
      original_path: candidate.path,
      scope,
      kind: candidate.kind,
      reason: candidate.reason,
      package_version: packageVersion(),
      source_version: sourceVersion,
      original_hash: candidate.record.sha256,
      mode: candidate.record.mode,
      timestamp: now,
    });
    known.add(key);
  }
  const next = Buffer.from(`${stable({ schema_version: 1, version: packageVersion(), entries: entries.sort((a, b) => String(a.original_path).localeCompare(String(b.original_path)) || String(a.digest).localeCompare(String(b.digest))) })}\n`);
  if (!existingRaw || !existingRaw.equals(next)) {
    mutations.push({ root, path: "index.json", operation: "write", content: next, mode: 0o600, expected: existingRaw ? { sha256: sha256(existingRaw) } : { absent: true } });
  }
  return mutations;
}

async function validateGenericDeployment(
  root: string,
  action: Action,
  expectedAssets: readonly Asset[],
  plannedOperations: readonly PlanItem[],
  expectedManifest: Buffer | undefined,
  retiredPaths: ReadonlySet<string>,
): Promise<void> {
  const owned = await currentManifest(root);
  if (
    (expectedManifest && (!owned.raw || !owned.raw.equals(expectedManifest))) ||
    (!expectedManifest && owned.raw)
  )
    throw new InstallerError(
      "final_validation_failed",
      "Generic ownership manifest does not match the planned state",
    );
  if (!owned.manifest) {
    if (action === "install")
      throw new InstallerError("final_validation_failed", "Generic ownership manifest is missing");
    return;
  }
  if (((await lstat(destination(root, MANIFEST_NAME))).mode & 0o777) !== 0o600)
    throw new InstallerError(
      "final_validation_failed",
      "Generic ownership manifest is not private",
    );
  const expected = new Map(expectedAssets.map((asset) => [asset.relativePath, asset]));
  if (
    action === "install" &&
    Object.keys(owned.manifest.files)
      .filter((path) => !retiredPaths.has(path))
      .sort()
      .join(",") !== [...expected.keys()].sort().join(",")
  ) {
    throw new InstallerError("final_validation_failed", "Generic ownership inventory is incomplete");
  }
  for (const [relativePath, record] of Object.entries(owned.manifest.files)) {
    if (relativePath.startsWith("agents/"))
      throw new InstallerError("final_validation_failed", "Generic installer retained agent ownership");
    const target = destination(root, relativePath);
    const content = await readRegular(target);
    const planned = plannedOperations.find((item) => item.path === relativePath);
    const preservedDrift =
      action === "uninstall" &&
      content &&
      planned?.operation === "conflict" &&
      planned.sha256 === sha256(content);
    if (!content || (sha256(content) !== record.sha256 && !preservedDrift))
      throw new InstallerError(
        "final_validation_failed",
        `Generic managed file failed final validation: ${relativePath}`,
      );
    const asset = expected.get(relativePath);
    if (
      action === "install" &&
      ((!asset && !retiredPaths.has(relativePath)) || (asset && asset.sha256 !== record.sha256))
    )
      throw new InstallerError(
        "final_validation_failed",
        `Generic manifest does not match package asset: ${relativePath}`,
      );
    if (action === "install" && asset && ((await lstat(target)).mode & 0o777) !== asset.mode)
      throw new InstallerError(
        "final_validation_failed",
        `Generic managed file has an unexpected mode: ${relativePath}`,
      );
  }
}

function asLegacy(manifest: Manifest | undefined): LegacyInstallerManifest | undefined {
  return manifest?.version === "1.0.0" ? (manifest as unknown as LegacyInstallerManifest) : undefined;
}

async function build(action: Action, scope: Scope, cwd = process.cwd(), home = homedir(), requestedSelection?: Partial<InstallerSelection>): Promise<BuiltInstallerPlan> {
  const root = deploymentRoot(scope, cwd, home);
  const owned = await currentManifest(root);
  const selection = normalizeSelection(
    requestedSelection ??
      (owned.manifest
        ? {
            commands: owned.manifest.commands,
            agents: owned.manifest.agents,
            plugins: owned.manifest.plugins,
            core_activation: owned.manifest.core_activation,
          }
        : undefined),
  );
  const bundled = await assets(selection);
  const retiredPaths = retiredAssetPaths();
  const legacyRecord = owned.manifest && owned.raw && asLegacy(owned.manifest)
    ? { manifest: asLegacy(owned.manifest)!, manifestPath: destination(root, MANIFEST_NAME), manifestSha256: sha256(owned.raw) }
    : undefined;
  const profiles = await buildAgentProfilePlan({ action }, scope, cwd, home, legacyRecord, selection.agents);
  const operations: PlanItem[] = profiles.plan.operations.map((item) => ({ path: item.path, operation: item.operation, reason: item.reason }));
  const mutations: FileMutation[] = [...profiles.mutations];
  const archiveCandidates: ArchiveCandidate[] = [];
  const desiredFiles: Record<string, ManifestFile> = {};

  if (action === "install") {
    for (const asset of bundled) {
      desiredFiles[asset.relativePath] = {
        sha256: asset.sha256,
        mode: asset.mode,
        kind: asset.relativePath.startsWith("commands/") ? "command" : "plugin",
      };
      const current = await readRegular(destination(root, asset.relativePath));
      const record = owned.manifest?.files[asset.relativePath];
      if (!current) {
        operations.push({ path: asset.relativePath, operation: "create", sha256: asset.sha256 });
        mutations.push({ path: asset.relativePath, operation: "write", content: asset.content, mode: asset.mode, expected: { absent: true } });
      } else if (!record) {
        operations.push({ path: asset.relativePath, operation: "conflict", reason: "unmanaged_file", sha256: sha256(current) });
      } else if (sha256(current) !== record.sha256) {
        operations.push({ path: asset.relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
      } else if (
        current.equals(asset.content) &&
        ((await lstat(destination(root, asset.relativePath))).mode & 0o777) === asset.mode
      ) {
        operations.push({ path: asset.relativePath, operation: "unchanged", sha256: asset.sha256 });
      } else {
        operations.push({ path: asset.relativePath, operation: "update", sha256: asset.sha256 });
        mutations.push({ path: asset.relativePath, operation: "write", content: asset.content, mode: asset.mode, expected: { sha256: record.sha256 } });
      }
    }
    const active = new Set(bundled.map((asset) => asset.relativePath));
    for (const [relativePath, record] of Object.entries(owned.manifest?.files ?? {}).sort(([left], [right]) => left.localeCompare(right))) {
      if (active.has(relativePath) || profiles.legacyTransferred.includes(relativePath)) continue;
      const current = await readRegular(destination(root, relativePath));
      if (retiredPaths.has(relativePath)) {
        if (!current) {
          operations.push({ path: relativePath, operation: "missing", sha256: record.sha256 });
        } else if (sha256(current) !== record.sha256) {
          operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
        } else {
          operations.push({ path: relativePath, operation: "archive-pending", reason: "archive lifecycle is pending", sha256: record.sha256 });
          archiveCandidates.push({ path: relativePath, record, content: current!, reason: "retired managed asset", kind: record.kind });
          mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
        }
        continue;
      }
      if (relativePath.startsWith("agents/")) {
        operations.push({ path: relativePath, operation: "conflict", reason: "v1.0.0_agent_ownership_mismatch" });
        continue;
      }
      if (!current) operations.push({ path: relativePath, operation: "missing" });
      else if (sha256(current) === record.sha256) {
        operations.push({ path: relativePath, operation: "archive-pending", reason: "stale managed asset is archived", sha256: record.sha256 });
        archiveCandidates.push({ path: relativePath, record, content: current, reason: "stale managed asset", kind: record.kind });
        mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
      } else operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
    }
  } else {
    for (const [relativePath, record] of Object.entries(owned.manifest?.files ?? {}).sort(([left], [right]) => left.localeCompare(right))) {
      const current = await readRegular(destination(root, relativePath));
      if (retiredPaths.has(relativePath)) {
        if (!current) {
          operations.push({ path: relativePath, operation: "missing", sha256: record.sha256 });
        } else if (sha256(current) !== record.sha256) {
          operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
        } else {
          operations.push({ path: relativePath, operation: "archive-pending", reason: "archive lifecycle is pending", sha256: record.sha256 });
          archiveCandidates.push({ path: relativePath, record, content: current!, reason: "retired managed asset", kind: record.kind });
          mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
        }
      } else if (!current) operations.push({ path: relativePath, operation: "missing" });
      else if (sha256(current) === record.sha256) {
        operations.push({ path: relativePath, operation: "archive-pending", reason: "stale managed asset is archived", sha256: record.sha256 });
        archiveCandidates.push({ path: relativePath, record, content: current, reason: "stale managed asset", kind: record.kind });
        mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
      } else {
        operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
        desiredFiles[relativePath] = record;
      }
    }
  }

  mutations.push(...await archiveMutations(archiveCandidates, scope, cwd, home, owned.manifest?.package_version ?? "1.0.0"));

  const nextManifest: Manifest | undefined = action === "install" || Object.keys(desiredFiles).length
    ? {
        schema_version: 2,
        package: PACKAGE_NAME,
        package_version: packageVersion(),
        version: packageVersion(),
        scope,
        commands: selection.commands,
        agents: selection.agents,
        plugins: selection.plugins,
        core_activation: selection.core_activation,
        files: desiredFiles,
      }
    : undefined;
  const manifestContent = nextManifest ? Buffer.from(`${stable(nextManifest)}\n`) : undefined;
  if (manifestContent && (!owned.raw || !owned.raw.equals(manifestContent))) {
    operations.push({ path: MANIFEST_NAME, operation: owned.raw ? "update" : "create", reason: "generic installer ownership" });
    mutations.push({ path: MANIFEST_NAME, operation: "write", content: manifestContent, mode: 0o600, expected: owned.raw ? { sha256: sha256(owned.raw) } : { absent: true } });
  } else if (!manifestContent && owned.raw) {
    operations.push({ path: MANIFEST_NAME, operation: "remove", reason: "generic assets uninstalled" });
    mutations.push({ path: MANIFEST_NAME, operation: "remove", expected: { sha256: sha256(owned.raw) } });
  }

  const sorted = operations.sort((left, right) => left.path.localeCompare(right.path) || left.operation.localeCompare(right.operation));
  const base = { schema_version: 2 as const, action, scope, root, package_version: packageVersion(), selection, operations: sorted, requires_restart: (action === "install" && owned.manifest?.package_version !== packageVersion()) || profiles.plan.requires_restart || mutations.some((item) => item.path.startsWith("agents/") || item.path.startsWith("commands/") || item.path.startsWith("plugins/")) };
  const planDigest = digest(base);
  return {
    plan: { ...base, plan_digest: planDigest, digest: planDigest },
    mutations,
    expectedManifest: manifestContent,
    profiles,
  };
}

export async function preview(action: Action, scope: Scope, cwd = process.cwd(), home = homedir(), selection?: Partial<InstallerSelection>): Promise<Plan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot)) throw new InstallerError("recovered_transaction", "Recovered an interrupted transaction; request a fresh plan");
      const built = await build(action, scope, cwd, home, selection);
      const receipt = await saveReceipt(
        stateRoot,
        `installer:${action}`,
        scope,
        root,
        { plan_digest: built.plan.digest },
        Date.now(),
        built.plan.digest,
      );
      return {
        ...built.plan,
        plan_digest: built.plan.digest,
        confirmation_digest: receipt.digest,
        digest: receipt.digest,
        receipt_expires_at: receipt.expires_at,
        ...(receipt.superseded_plan ? { superseded_plan: receipt.superseded_plan } : {}),
      };
    });
  } catch (error) {
    if (error instanceof InstallerError) throw error;
    if (error instanceof LifecycleError) throw new InstallerError(error.code, error.message);
    throw error;
  }
}

export async function apply(action: Action, scope: Scope, confirmationDigest: string, cwd = process.cwd(), home = homedir(), options: TransactionOptions = {}, selection?: Partial<InstallerSelection>): Promise<Plan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot)) throw new InstallerError("recovered_transaction", "Recovered an interrupted transaction; request a fresh plan");
      const receipt = (await consumeReceipt(stateRoot, { digest: confirmationDigest, kind: `installer:${action}`, scope, root })) as { digest?: string };
      const built = await build(action, scope, cwd, home, selection);
      const savedPlanDigest = (receipt as { plan_digest?: string; digest?: string }).plan_digest ??
        (receipt as { digest?: string }).digest;
      if (built.plan.digest !== savedPlanDigest)
         throw new InstallerError("stale_plan", "Installer plan changed after preview");
      if (built.plan.operations.some((item) => item.operation === "conflict" && (item.reason === "unmanaged_file" || item.reason === "v1.0.0_agent_ownership_mismatch" || item.reason?.includes("collision")))) {
        throw new InstallerError("conflict", "Installer plan contains an exact-name ownership conflict");
      }
      if (action === "install" && built.plan.operations.some((item) => item.operation === "conflict")) throw new InstallerError("conflict", "Installer plan contains managed drift");
      await applyTransaction(root, stateRoot, built.mutations, {
        ...options,
        validateFinal: async () => {
          await options.validateFinal?.();
          await validateBuiltAgentProfilePlan(built.profiles);
          await validateGenericDeployment(
            root,
            action,
             await assets(built.plan.selection),
            built.plan.operations,
            built.expectedManifest,
            retiredAssetPaths(),
          );
          if (action !== "install") return;
          const inventory = await listAgentProfiles(scope, cwd, home);
           if (built.plan.selection.agents.length > 0 && (inventory.collisions.length || inventory.drift.length || inventory.profiles.filter((item) => item.ownership !== "user-owned").some((item) => item.state !== "current"))) {
            throw new InstallerError("final_validation_failed", "Final installed agent inventory is invalid");
          }
        },
      });
      return { ...built.plan, digest: confirmationDigest };
    });
  } catch (error) {
    if (error instanceof InstallerError) throw error;
    if (error instanceof LifecycleError) throw new InstallerError(error.code, error.message);
    throw error;
  }
}

export function result(plan: Plan, applied: boolean): string {
  return JSON.stringify({ status: "ok", applied, requires_restart: applied && plan.requires_restart, plan }, null, 2);
}
