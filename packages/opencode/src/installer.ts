import { createHash, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { lstat, mkdir, readdir, readFile, rename, rm, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, normalize, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const PACKAGE_NAME = "agent-skills-opencode";
const MANIFEST_NAME = ".agent-skills-opencode-manifest.json";
const MANIFEST_SCHEMA_VERSION = 1;
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = resolve(packageRoot, "assets");

export type Scope = "global" | "project";
export type Action = "install" | "uninstall";
export type Operation = "create" | "update" | "remove" | "unchanged" | "missing" | "conflict";
export type PlanItem = { path: string; operation: Operation; reason?: string; sha256?: string };
export type Plan = { schema_version: 1; action: Action; scope: Scope; root: string; operations: PlanItem[]; manifest_sha256?: string; digest: string };
type Asset = { relativePath: string; content: Buffer; sha256: string };
type ManifestFile = { sha256: string; previous_sha256?: string };
type Manifest = { schema_version: 1; package: string; version: string; state?: "applying"; files: Record<string, ManifestFile> };

export class InstallerError extends Error {
  constructor(readonly code: string, message: string) {
    super(message);
  }
}

function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stable(object[key])}`).join(",")}}`;
}

function sha256(value: Buffer | string): string {
  return createHash("sha256").update(value).digest("hex");
}

function planDigest(plan: Omit<Plan, "digest">): string {
  return sha256(stable(plan));
}

function packageVersion(): string {
  const metadata = JSON.parse(requireReadFile(resolve(packageRoot, "package.json"))) as { version?: unknown };
  if (typeof metadata.version !== "string" || !metadata.version) throw new InstallerError("invalid_package", "Package version is unavailable");
  return metadata.version;
}

function requireReadFile(path: string): string {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    throw new InstallerError("asset_error", `Cannot read ${path}: ${String(error)}`);
  }
}

function isInside(root: string, target: string): boolean {
  const difference = relative(root, target);
  return difference === "" || (!difference.startsWith(`..${sep}`) && difference !== ".." && !isAbsolute(difference));
}

function assertSafeRelative(value: string): void {
  if (!value || isAbsolute(value) || normalize(value) !== value || value.split(/[\\/]/).some((part) => !part || part === "." || part === "..")) {
    throw new InstallerError("unsafe_path", `Unsafe relative path: ${value}`);
  }
}

async function lstatSafe(path: string) {
  try {
    return await lstat(path);
  } catch (error: unknown) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

async function assertSafeAncestors(path: string): Promise<void> {
  const parsed = parse(resolve(path));
  let current = parsed.root;
  const pieces = resolve(path).slice(parsed.root.length).split(sep).filter(Boolean);
  for (const piece of pieces) {
    current = join(current, piece);
    const stat = await lstatSafe(current);
    if (!stat) return;
    if (stat.isSymbolicLink()) throw new InstallerError("unsafe_path", `Symlink is not allowed: ${current}`);
    if (current !== resolve(path) && !stat.isDirectory()) throw new InstallerError("unsafe_path", `Path parent is not a directory: ${current}`);
  }
}

async function readRegular(path: string): Promise<Buffer | undefined> {
  await assertSafeAncestors(path);
  const stat = await lstatSafe(path);
  if (!stat) return undefined;
  if (!stat.isFile()) throw new InstallerError("unsafe_path", `Target is not a regular file: ${path}`);
  return readFile(path);
}

async function ensureSafeDirectory(path: string): Promise<void> {
  await assertSafeAncestors(path);
  const stat = await lstatSafe(path);
  if (stat && !stat.isDirectory()) throw new InstallerError("unsafe_path", `Destination root is not a directory: ${path}`);
  await mkdir(path, { recursive: true });
  await assertSafeAncestors(path);
}

function rootFor(scope: Scope, cwd = process.cwd(), home = homedir()): string {
  return scope === "global" ? resolve(home, ".config", "opencode") : resolve(cwd, ".opencode");
}

function destination(root: string, relativePath: string): string {
  assertSafeRelative(relativePath);
  const target = resolve(root, relativePath);
  if (!isInside(root, target)) throw new InstallerError("unsafe_path", `Path escapes destination root: ${relativePath}`);
  return target;
}

async function assets(): Promise<Asset[]> {
  const result: Asset[] = [];
  for (const category of ["agents", "commands", "plugins"]) {
    const directory = resolve(assetsRoot, category);
    await assertSafeAncestors(directory);
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      const extension = category === "plugins" ? ".js" : ".md";
      if (!entry.isFile() || entry.isSymbolicLink() || !entry.name.endsWith(extension)) throw new InstallerError("asset_error", `Asset is not a regular ${extension} asset: ${entry.name}`);
      const relativePath = `${category}/${entry.name}`;
      assertSafeRelative(relativePath);
      const source = destination(assetsRoot, relativePath);
      const content = await readRegular(source);
      if (!content) throw new InstallerError("asset_error", `Asset is missing: ${relativePath}`);
      result.push({ relativePath, content, sha256: sha256(content) });
    }
  }
  return result.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
}

function manifestPath(root: string): string {
  return destination(root, MANIFEST_NAME);
}

function parseManifest(value: Buffer, path: string): Manifest {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value.toString("utf8"));
  } catch {
    throw new InstallerError("invalid_manifest", `Ownership manifest is not valid JSON: ${path}`);
  }
  if (!parsed || typeof parsed !== "object") throw new InstallerError("invalid_manifest", `Ownership manifest is not an object: ${path}`);
  const manifest = parsed as Partial<Manifest>;
  if (manifest.schema_version !== MANIFEST_SCHEMA_VERSION || manifest.package !== PACKAGE_NAME || typeof manifest.version !== "string" || (manifest.state !== undefined && manifest.state !== "applying") || !manifest.files || typeof manifest.files !== "object" || Array.isArray(manifest.files)) throw new InstallerError("invalid_manifest", `Ownership manifest has an unexpected format: ${path}`);
  for (const [relativePath, record] of Object.entries(manifest.files)) {
    assertSafeRelative(relativePath);
    if (!record || typeof record !== "object" || typeof (record as { sha256?: unknown }).sha256 !== "string" || !/^[a-f0-9]{64}$/.test((record as { sha256: string }).sha256) || ((record as { previous_sha256?: unknown }).previous_sha256 !== undefined && (typeof (record as { previous_sha256: unknown }).previous_sha256 !== "string" || !/^[a-f0-9]{64}$/.test((record as { previous_sha256: string }).previous_sha256)))) throw new InstallerError("invalid_manifest", `Ownership manifest has an invalid record: ${relativePath}`);
  }
  return manifest as Manifest;
}

async function manifestFor(root: string): Promise<{ manifest?: Manifest; sha256?: string }> {
  const path = manifestPath(root);
  const content = await readRegular(path);
  return content ? { manifest: parseManifest(content, path), sha256: sha256(content) } : {};
}

function makePlan(action: Action, scope: Scope, root: string, operations: PlanItem[], manifestHash?: string): Plan {
  const base = { schema_version: 1 as const, action, scope, root, operations, ...(manifestHash ? { manifest_sha256: manifestHash } : {}) };
  return { ...base, digest: planDigest(base) };
}

async function installPlan(scope: Scope, cwd?: string, home?: string): Promise<{ plan: Plan; assets: Asset[]; manifest?: Manifest }> {
  const root = rootFor(scope, cwd, home);
  await assertSafeAncestors(root);
  const [owned, currentAssets] = await Promise.all([manifestFor(root), assets()]);
  const manifest = owned.manifest;
  const operations: PlanItem[] = [];
  for (const asset of currentAssets) {
    const target = destination(root, asset.relativePath);
    const content = await readRegular(target);
    if (!content) {
      operations.push({ path: asset.relativePath, operation: "create", sha256: asset.sha256 });
      continue;
    }
    const currentHash = sha256(content);
    const record = manifest?.files[asset.relativePath];
    if (!record) operations.push({ path: asset.relativePath, operation: "conflict", reason: "unmanaged_file", sha256: currentHash });
    else if (record.sha256 !== currentHash && !(manifest?.state === "applying" && record.previous_sha256 === currentHash)) operations.push({ path: asset.relativePath, operation: "conflict", reason: "managed_file_changed", sha256: currentHash });
    else if (currentHash === asset.sha256) operations.push({ path: asset.relativePath, operation: "unchanged", sha256: currentHash });
    else operations.push({ path: asset.relativePath, operation: "update", sha256: asset.sha256 });
  }
  const active = new Set(currentAssets.map((asset) => asset.relativePath));
  for (const [relativePath, record] of Object.entries(manifest?.files ?? {}).sort(([left], [right]) => left.localeCompare(right))) {
    if (active.has(relativePath)) continue;
    const content = await readRegular(destination(root, relativePath));
    if (!content) operations.push({ path: relativePath, operation: "missing" });
    else if (sha256(content) === record.sha256) operations.push({ path: relativePath, operation: "remove", sha256: record.sha256 });
    else operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(content) });
  }
  return { plan: makePlan("install", scope, root, operations, owned.sha256), assets: currentAssets, manifest };
}

async function uninstallPlan(scope: Scope, cwd?: string, home?: string): Promise<{ plan: Plan; manifest?: Manifest }> {
  const root = rootFor(scope, cwd, home);
  await assertSafeAncestors(root);
  const owned = await manifestFor(root);
  if (!owned.manifest) return { plan: makePlan("uninstall", scope, root, []) };
  const operations: PlanItem[] = [];
  for (const [relativePath, record] of Object.entries(owned.manifest.files).sort(([left], [right]) => left.localeCompare(right))) {
    const content = await readRegular(destination(root, relativePath));
    if (!content) operations.push({ path: relativePath, operation: "missing" });
    else if (sha256(content) === record.sha256) operations.push({ path: relativePath, operation: "remove", sha256: record.sha256 });
    else operations.push({ path: relativePath, operation: "conflict", reason: "managed_file_changed", sha256: sha256(content) });
  }
  return { plan: makePlan("uninstall", scope, root, operations, owned.sha256), manifest: owned.manifest };
}

export async function preview(action: Action, scope: Scope, cwd?: string, home?: string): Promise<Plan> {
  return action === "install" ? (await installPlan(scope, cwd, home)).plan : (await uninstallPlan(scope, cwd, home)).plan;
}

async function writeAtomically(path: string, content: Buffer): Promise<void> {
  await ensureSafeDirectory(dirname(path));
  await assertSafeAncestors(path);
  const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    await writeFile(temporary, content, { flag: "wx", mode: 0o644 });
    await rename(temporary, path);
  } finally {
    await rm(temporary, { force: true });
  }
}

async function writeManifest(root: string, manifest: Manifest, existingHash?: string, expectAbsent = false): Promise<string> {
  const target = manifestPath(root);
  const current = await readRegular(target);
  if (existingHash && (!current || sha256(current) !== existingHash)) throw new InstallerError("stale_plan", "Ownership manifest changed after preview");
  if (expectAbsent && current) throw new InstallerError("stale_plan", "Ownership manifest appeared after preview");
  const content = Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`);
  if (!current || !current.equals(content)) await writeAtomically(target, content);
  return sha256(content);
}

async function applyInstall(scope: Scope, expectedDigest: string, cwd?: string, home?: string): Promise<Plan> {
  const initial = await installPlan(scope, cwd, home);
  if (initial.plan.digest !== expectedDigest) throw new InstallerError("stale_plan", "Install plan changed; request a new dry-run");
  if (initial.plan.operations.some((item) => item.operation === "conflict")) throw new InstallerError("conflict", "Install plan contains conflicts");
  const verified = await installPlan(scope, cwd, home);
  if (verified.plan.digest !== expectedDigest) throw new InstallerError("stale_plan", "Install plan changed before apply");
  await ensureSafeDirectory(verified.plan.root);
  const staged: Manifest = {
    schema_version: MANIFEST_SCHEMA_VERSION,
    package: PACKAGE_NAME,
    version: packageVersion(),
    state: "applying",
    files: Object.fromEntries(verified.assets.map((asset) => {
      const operation = verified.plan.operations.find((item) => item.path === asset.relativePath)?.operation;
      const previous = operation === "update" ? verified.manifest?.files[asset.relativePath]?.previous_sha256 ?? verified.manifest?.files[asset.relativePath]?.sha256 : undefined;
      return [asset.relativePath, { sha256: asset.sha256, ...(previous ? { previous_sha256: previous } : {}) }];
    }))
  };
  const stagedHash = await writeManifest(verified.plan.root, staged, verified.plan.manifest_sha256, !verified.plan.manifest_sha256);
  for (const asset of verified.assets) {
    const item = verified.plan.operations.find((candidate) => candidate.path === asset.relativePath);
    if (item?.operation === "create" || item?.operation === "update") {
      const target = destination(verified.plan.root, asset.relativePath);
      const current = await readRegular(target);
      const expected = item.operation === "create" ? undefined : verified.manifest?.files[asset.relativePath]?.previous_sha256 ?? verified.manifest?.files[asset.relativePath]?.sha256;
      if ((current && sha256(current)) !== expected) throw new InstallerError("stale_plan", `Destination changed: ${asset.relativePath}`);
      await writeAtomically(target, asset.content);
    }
  }
  for (const item of verified.plan.operations.filter((candidate) => candidate.operation === "remove")) {
    const target = destination(verified.plan.root, item.path);
    const current = await readRegular(target);
    if (!current || sha256(current) !== item.sha256) throw new InstallerError("stale_plan", `Destination changed: ${item.path}`);
    await unlink(target);
  }
  const completed: Manifest = {
    schema_version: MANIFEST_SCHEMA_VERSION,
    package: PACKAGE_NAME,
    version: packageVersion(),
    files: Object.fromEntries(verified.assets.map((asset) => [asset.relativePath, { sha256: asset.sha256 }]))
  };
  await writeManifest(verified.plan.root, completed, stagedHash);
  return verified.plan;
}

async function applyUninstall(scope: Scope, expectedDigest: string, cwd?: string, home?: string): Promise<Plan> {
  const initial = await uninstallPlan(scope, cwd, home);
  if (initial.plan.digest !== expectedDigest) throw new InstallerError("stale_plan", "Uninstall plan changed; request a new dry-run");
  if (!initial.manifest) return initial.plan;
  const verified = await uninstallPlan(scope, cwd, home);
  if (verified.plan.digest !== expectedDigest || !verified.manifest) throw new InstallerError("stale_plan", "Uninstall plan changed before apply");
  const remaining: Record<string, ManifestFile> = {};
  for (const item of verified.plan.operations) {
    if (item.operation === "remove") {
      const target = destination(verified.plan.root, item.path);
      const current = await readRegular(target);
      if (!current || sha256(current) !== item.sha256) throw new InstallerError("stale_plan", `Destination changed: ${item.path}`);
      await unlink(target);
    } else if (item.operation === "conflict") {
      remaining[item.path] = verified.manifest.files[item.path];
    }
  }
  const manifestTarget = manifestPath(verified.plan.root);
  const manifestContent = await readRegular(manifestTarget);
  if (!manifestContent || sha256(manifestContent) !== verified.plan.manifest_sha256) throw new InstallerError("stale_plan", "Ownership manifest changed after preview");
  if (Object.keys(remaining).length) await writeManifest(verified.plan.root, { schema_version: MANIFEST_SCHEMA_VERSION, package: PACKAGE_NAME, version: packageVersion(), files: remaining }, verified.plan.manifest_sha256);
  else await unlink(manifestTarget);
  return verified.plan;
}

export async function apply(action: Action, scope: Scope, digest: string, cwd?: string, home?: string): Promise<Plan> {
  if (!/^[a-f0-9]{64}$/.test(digest)) throw new InstallerError("invalid_digest", "Confirmation digest must be a SHA-256 hex value");
  return action === "install" ? applyInstall(scope, digest, cwd, home) : applyUninstall(scope, digest, cwd, home);
}

export function result(plan: Plan, applied: boolean): string {
  return JSON.stringify({ status: "ok", applied, plan }, null, 2);
}
