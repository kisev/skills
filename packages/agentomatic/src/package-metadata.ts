import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

type PackageMetadata = Record<string, unknown>;

const packageJson = resolve(dirname(fileURLToPath(import.meta.url)), "..", "package.json");
let cachedMetadata: PackageMetadata | null | undefined;

function readPackageMetadata(): PackageMetadata | null {
  if (cachedMetadata !== undefined) return cachedMetadata;
  try {
    const value: unknown = JSON.parse(readFileSync(packageJson, "utf8"));
    cachedMetadata =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as PackageMetadata)
        : null;
  } catch {
    cachedMetadata = null;
  }
  return cachedMetadata;
}

function readString(name: string): string | null {
  const value = readPackageMetadata()?.[name];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function readPackageVersion(): string | null {
  return readString("version");
}

export function requirePackageVersion(): string {
  const version = readPackageVersion();
  if (!version) throw new Error("Package version is unavailable");
  return version;
}

export function requireSkillsInstallerVersion(): string {
  const version = readString("skillsInstallerVersion");
  if (!version) throw new Error("Skills installer version is unavailable");
  return version;
}

export function skillsInstallerSpec(): string {
  return `skills@${requireSkillsInstallerVersion()}`;
}
