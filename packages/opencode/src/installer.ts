import { readFileSync } from "node:fs";
import { lstat, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildAgentProfilePlan,
  listAgentProfiles,
  validateBuiltAgentProfilePlan,
  type LegacyInstallerManifest,
} from "./agent-profiles.js";
import {
  applyTransaction,
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
  type FileMutation,
  type Scope,
  type TransactionOptions,
} from "./lifecycle.js";

export type { Scope } from "./lifecycle.js";

const PACKAGE_NAME = "@kisev/skills-opencode";
const MANIFEST_NAME = ".skills-opencode-manifest.json";
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = resolve(packageRoot, "assets");

export type Action = "install" | "uninstall";
export type Operation = "create" | "update" | "remove" | "unchanged" | "missing" | "conflict";
export type PlanItem = { path: string; operation: Operation; reason?: string; sha256?: string };
export type Plan = {
  schema_version: 1;
  action: Action;
  scope: Scope;
  root: string;
  package_version: string;
  operations: PlanItem[];
  digest: string;
  receipt_expires_at?: string;
  requires_restart: boolean;
};
type Asset = { relativePath: string; content: Buffer; sha256: string; mode: number };
type ManifestFile = { sha256: string };
type Manifest = { schema_version: 1; package: string; version: string; files: Record<string, ManifestFile> };
type BuiltInstallerPlan = {
  plan: Plan;
  mutations: FileMutation[];
  expectedManifest?: Buffer;
  profiles: Awaited<ReturnType<typeof buildAgentProfilePlan>>;
};

export class InstallerError extends LifecycleError {}

function packageVersion(): string {
  const metadata = JSON.parse(readFileSync(resolve(packageRoot, "package.json"), "utf8")) as { version?: unknown };
  if (typeof metadata.version !== "string" || !metadata.version) throw new InstallerError("invalid_package", "Package version is unavailable");
  return metadata.version;
}

async function assets(): Promise<Asset[]> {
  const result: Asset[] = [];
  for (const category of ["commands", "plugins"] as const) {
    const directory = resolve(assetsRoot, category);
    for (const entry of (await readdir(directory, { withFileTypes: true })).sort((left, right) => left.name.localeCompare(right.name))) {
      const extension = category === "plugins" ? ".js" : ".md";
      if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(extension)) throw new InstallerError("asset_error", `Asset is not a regular ${extension} file: ${entry.name}`);
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
  if (manifest.schema_version !== 1 || manifest.package !== PACKAGE_NAME || typeof manifest.version !== "string" || !manifest.files || typeof manifest.files !== "object" || Array.isArray(manifest.files)) {
    throw new InstallerError("invalid_manifest", `Ownership manifest has an unexpected format: ${path}`);
  }
  for (const [relativePath, record] of Object.entries(manifest.files)) {
    destination("/", relativePath);
    if (!record || typeof record !== "object" || typeof (record as ManifestFile).sha256 !== "string" || !/^[a-f0-9]{64}$/.test((record as ManifestFile).sha256)) {
      throw new InstallerError("invalid_manifest", `Ownership manifest has an invalid record: ${relativePath}`);
    }
  }
  return manifest as Manifest;
}

async function currentManifest(root: string): Promise<{ manifest?: Manifest; raw?: Buffer }> {
  const path = destination(root, MANIFEST_NAME);
  const raw = await readRegular(path);
  return raw ? { manifest: parseManifest(raw, path), raw } : {};
}

async function validateGenericDeployment(
  root: string,
  action: Action,
  expectedAssets: readonly Asset[],
  plannedOperations: readonly PlanItem[],
  expectedManifest: Buffer | undefined,
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
    Object.keys(owned.manifest.files).sort().join(",") !== [...expected.keys()].sort().join(",")
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
    if (action === "install" && (!asset || asset.sha256 !== record.sha256))
      throw new InstallerError(
        "final_validation_failed",
        `Generic manifest does not match package asset: ${relativePath}`,
      );
    if (action === "install" && ((await lstat(target)).mode & 0o777) !== asset!.mode)
      throw new InstallerError(
        "final_validation_failed",
        `Generic managed file has an unexpected mode: ${relativePath}`,
      );
  }
}

function asLegacy(manifest: Manifest | undefined): LegacyInstallerManifest | undefined {
  return manifest?.version === "1.0.0" ? (manifest as LegacyInstallerManifest) : undefined;
}

async function build(action: Action, scope: Scope, cwd = process.cwd(), home = homedir()): Promise<BuiltInstallerPlan> {
  const root = deploymentRoot(scope, cwd, home);
  const [owned, bundled] = await Promise.all([currentManifest(root), assets()]);
  const legacyRecord = owned.manifest && owned.raw && asLegacy(owned.manifest)
    ? { manifest: asLegacy(owned.manifest)!, manifestPath: destination(root, MANIFEST_NAME), manifestSha256: sha256(owned.raw) }
    : undefined;
  const profiles = await buildAgentProfilePlan({ action }, scope, cwd, home, legacyRecord);
  const operations: PlanItem[] = profiles.plan.operations.map((item) => ({ path: item.path, operation: item.operation, reason: item.reason }));
  const mutations: FileMutation[] = [...profiles.mutations];
  const desiredFiles: Record<string, ManifestFile> = {};

  if (action === "install") {
    for (const asset of bundled) {
      desiredFiles[asset.relativePath] = { sha256: asset.sha256 };
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
      if (relativePath.startsWith("agents/")) {
        operations.push({ path: relativePath, operation: "conflict", reason: "v1.0.0_agent_ownership_mismatch" });
        continue;
      }
      const current = await readRegular(destination(root, relativePath));
      if (!current) operations.push({ path: relativePath, operation: "missing" });
      else if (sha256(current) === record.sha256) {
        operations.push({ path: relativePath, operation: "remove", sha256: record.sha256 });
        mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
      } else operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
    }
  } else {
    for (const [relativePath, record] of Object.entries(owned.manifest?.files ?? {}).sort(([left], [right]) => left.localeCompare(right))) {
      const current = await readRegular(destination(root, relativePath));
      if (!current) operations.push({ path: relativePath, operation: "missing" });
      else if (sha256(current) === record.sha256) {
        operations.push({ path: relativePath, operation: "remove", sha256: record.sha256 });
        mutations.push({ path: relativePath, operation: "remove", expected: { sha256: record.sha256 } });
      } else {
        operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(current) });
        desiredFiles[relativePath] = record;
      }
    }
  }

  const nextManifest: Manifest | undefined = action === "install" || Object.keys(desiredFiles).length
    ? { schema_version: 1, package: PACKAGE_NAME, version: packageVersion(), files: desiredFiles }
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
  const base = { schema_version: 1 as const, action, scope, root, package_version: packageVersion(), operations: sorted, requires_restart: (action === "install" && owned.manifest?.version !== packageVersion()) || profiles.plan.requires_restart || mutations.some((item) => item.path.startsWith("agents/") || item.path.startsWith("commands/") || item.path.startsWith("plugins/")) };
  return {
    plan: { ...base, digest: digest(base) },
    mutations,
    expectedManifest: manifestContent,
    profiles,
  };
}

export async function preview(action: Action, scope: Scope, cwd = process.cwd(), home = homedir()): Promise<Plan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot)) throw new InstallerError("recovered_transaction", "Recovered an interrupted transaction; request a fresh plan");
      const built = await build(action, scope, cwd, home);
      const receipt = await saveReceipt(stateRoot, `installer:${action}`, scope, root, { digest: built.plan.digest });
      return { ...built.plan, digest: receipt.digest, receipt_expires_at: receipt.expires_at };
    });
  } catch (error) {
    if (error instanceof InstallerError) throw error;
    if (error instanceof LifecycleError) throw new InstallerError(error.code, error.message);
    throw error;
  }
}

export async function apply(action: Action, scope: Scope, confirmationDigest: string, cwd = process.cwd(), home = homedir(), options: TransactionOptions = {}): Promise<Plan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      if (await recoverTransaction(root, stateRoot)) throw new InstallerError("recovered_transaction", "Recovered an interrupted transaction; request a fresh plan");
      const receipt = (await consumeReceipt(stateRoot, { digest: confirmationDigest, kind: `installer:${action}`, scope, root })) as { digest?: string };
      const built = await build(action, scope, cwd, home);
      if (built.plan.digest !== receipt.digest) throw new InstallerError("stale_plan", "Installer plan changed after preview");
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
            await assets(),
            built.plan.operations,
            built.expectedManifest,
          );
          if (action !== "install") return;
          const inventory = await listAgentProfiles(scope, cwd, home);
          if (inventory.collisions.length || inventory.drift.length || inventory.profiles.filter((item) => item.ownership !== "user-owned").some((item) => item.state !== "current")) {
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
