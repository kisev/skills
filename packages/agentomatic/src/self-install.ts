import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { LifecycleError, writeAtomic, readRegular } from "@kisev/safe-fs";
import { sha256 } from "./lifecycle.js";
import { requirePackageVersion } from "./package-metadata.js";

const execFileAsync = promisify(execFile);

export const SELF_PACKAGE_NAME = "@kisev/agentomatic";
export const LEGACY_SELF_PACKAGE_NAME = "@kisev/skills-opencode";
const NPM_INSTALL_TIMEOUT_MS = 180_000;

export type DependencyRunner = (
  command: string,
  args: string[],
  options: { cwd: string; timeout: number },
) => Promise<{ stdout: string; stderr: string }>;

export type DependencyPlan = {
  dir: string | null;
  name: string;
  version: string;
  status: "install" | "update" | "satisfied" | "manual";
  package_json: "present" | "create" | "missing";
  reason?: string;
};

export class SelfInstallError extends LifecycleError {}

export function owningProjectDir(
  scope: "project" | "global",
  cwd = process.cwd(),
  home = homedir(),
): string | null {
  if (scope === "global") return join(home, ".config", "opencode");
  let dir = resolve(cwd);
  for (;;) {
    if (existsSync(join(dir, "package.json"))) return dir;
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function readDependencyVersion(dir: string): string | null {
  try {
    const value: unknown = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const dependency = (value as Record<string, unknown>).dependencies;
    if (!dependency || typeof dependency !== "object" || Array.isArray(dependency)) return null;
    const pinned = (dependency as Record<string, unknown>)[SELF_PACKAGE_NAME];
    return typeof pinned === "string" && pinned.length > 0 ? pinned : null;
  } catch {
    return null;
  }
}

export function legacyDependencyPresent(dir: string): boolean {
  try {
    const value: unknown = JSON.parse(readFileSync(join(dir, "package.json"), "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    const dependency = (value as Record<string, unknown>).dependencies;
    if (!dependency || typeof dependency !== "object" || Array.isArray(dependency)) return false;
    return typeof (dependency as Record<string, unknown>)[LEGACY_SELF_PACKAGE_NAME] === "string";
  } catch {
    return false;
  }
}

export function planDependency(
  scope: "project" | "global",
  cwd = process.cwd(),
  home = homedir(),
  version: string = requirePackageVersion(),
): DependencyPlan {
  if (scope === "global") {
    const dir = join(home, ".config", "opencode");
    const hasPackageJson = existsSync(join(dir, "package.json"));
    if (!hasPackageJson)
      return { dir, name: SELF_PACKAGE_NAME, version, status: "install", package_json: "create" };
    const pinned = readDependencyVersion(dir);
    if (pinned === version)
      return {
        dir,
        name: SELF_PACKAGE_NAME,
        version,
        status: "satisfied",
        package_json: "present",
      };
    return {
      dir,
      name: SELF_PACKAGE_NAME,
      version,
      status: pinned ? "update" : "install",
      package_json: "present",
    };
  }
  const dir = owningProjectDir("project", cwd, home);
  if (!dir)
    return {
      dir: null,
      name: SELF_PACKAGE_NAME,
      version,
      status: "manual",
      package_json: "missing",
      reason:
        "no package.json found upward from the working directory; create an npm project or use --global",
    };
  const pinned = readDependencyVersion(dir);
  if (pinned === version)
    return { dir, name: SELF_PACKAGE_NAME, version, status: "satisfied", package_json: "present" };
  return {
    dir,
    name: SELF_PACKAGE_NAME,
    version,
    status: pinned ? "update" : "install",
    package_json: "present",
  };
}

export async function ensureDependency(
  plan: DependencyPlan,
  runner: DependencyRunner = execFileAsync as DependencyRunner,
): Promise<DependencyPlan & { applied: "changed" | "unchanged" | "skipped" }> {
  if (plan.status === "manual" || plan.status === "satisfied")
    return { ...plan, applied: plan.status === "satisfied" ? "unchanged" : "skipped" };
  const dir = plan.dir as string;
  if (plan.package_json === "create" && !existsSync(join(dir, "package.json"))) {
    await writeAtomic(
      join(dir, "package.json"),
      Buffer.from('{"name":"opencode-agentomatic","private":true}\n'),
      0o644,
    );
  }
  try {
    await runner(
      "npm",
      ["install", "--save-exact", `${plan.name}@${plan.version}`, "--no-audit", "--no-fund"],
      { cwd: dir, timeout: NPM_INSTALL_TIMEOUT_MS },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message.split("\n").slice(-6).join("\n") : "";
    throw new SelfInstallError(
      "npm_dependency_failed",
      `npm install for ${plan.name}@${plan.version} in ${dir} failed: ${detail}`,
    );
  }
  let removedLegacy = false;
  if (legacyDependencyPresent(dir)) {
    try {
      await runner("npm", ["rm", LEGACY_SELF_PACKAGE_NAME, "--no-audit", "--no-fund"], {
        cwd: dir,
        timeout: NPM_INSTALL_TIMEOUT_MS,
      });
      removedLegacy = true;
    } catch (error) {
      const detail = error instanceof Error ? error.message.split("\n").slice(-6).join("\n") : "";
      throw new SelfInstallError(
        "npm_dependency_failed",
        `npm rm for ${LEGACY_SELF_PACKAGE_NAME} in ${dir} failed: ${detail}`,
      );
    }
  }
  return { ...plan, applied: "changed", ...(removedLegacy ? { removed_legacy: true } : {}) };
}

export type DependencyRemovalPlan = {
  dir: string | null;
  names: string[];
  sources: Record<string, string | null>;
};

export async function previewDependencyRemoval(
  scope: "project" | "global",
  cwd = process.cwd(),
  home = homedir(),
): Promise<DependencyRemovalPlan> {
  const dir = owningProjectDir(scope, cwd, home);
  if (!dir) return { dir, names: [], sources: {} };
  const sources: Record<string, string | null> = {};
  for (const name of ["package.json", "package-lock.json"]) {
    const raw = await readRegular(join(dir, name));
    sources[name] = raw ? sha256(raw) : null;
  }
  const raw = await readRegular(join(dir, "package.json"));
  if (!raw) return { dir, names: [], sources };
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new SelfInstallError(
      "invalid_configuration",
      "Cannot inspect dependency removal: invalid package.json",
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    throw new SelfInstallError(
      "invalid_configuration",
      "Cannot inspect dependency removal: package.json must be an object",
    );
  const names = [SELF_PACKAGE_NAME, LEGACY_SELF_PACKAGE_NAME].filter((name) =>
    ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"].some((key) => {
      const section = parsed[key];
      return section && typeof section === "object" && name in section;
    }),
  );
  return { dir, names, sources };
}

export async function removeDependency(
  plan: DependencyRemovalPlan,
  runner: DependencyRunner = execFileAsync as DependencyRunner,
): Promise<void> {
  if (!plan.dir || !plan.names.length) return;
  for (const [name, expected] of Object.entries(plan.sources)) {
    const raw = await readRegular(join(plan.dir, name));
    if ((raw ? sha256(raw) : null) !== expected)
      throw new SelfInstallError("stale_plan", "npm files changed; preview uninstall again");
  }
  try {
    await runner("npm", ["rm", ...plan.names, "--no-audit", "--no-fund"], {
      cwd: plan.dir,
      timeout: NPM_INSTALL_TIMEOUT_MS,
    });
    const raw = await readRegular(join(plan.dir, "package.json"));
    const parsed = raw ? JSON.parse(raw.toString("utf8")) : undefined;
    if (
      !parsed ||
      plan.names.some((name) =>
        ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"].some(
          (key) => parsed[key] && name in parsed[key],
        ),
      )
    )
      throw new Error("npm did not remove the selected dependencies");
  } catch {
    throw new SelfInstallError(
      "npm_dependency_failed",
      "npm removal failed after local stages; inspect package.json and retry uninstall --remove-dependency",
    );
  }
}
