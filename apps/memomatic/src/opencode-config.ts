import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { parse, type ParseError } from "jsonc-parser";

const PROVIDER_FIELDS = [
  "providers",
  "provider",
  "model",
  "enabled_providers",
  "disabled_providers",
  "experimental",
  "enterprise",
];

function record(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function merge(left: unknown, right: unknown, key = ""): unknown {
  if (key === "policies" && Array.isArray(left) && Array.isArray(right)) return [...left, ...right];
  if (!record(left) || !record(right)) return right;
  return Object.fromEntries(
    [...new Set([...Object.keys(left), ...Object.keys(right)])].map((key) => [
      key,
      key in right ? merge(left[key], right[key], key) : left[key],
    ]),
  );
}

function anchorFiles(value: unknown, directory: string): unknown {
  if (typeof value === "string")
    return value.replace(/\{file:([^}]+)\}/g, (original, path: string) =>
      isAbsolute(path) || path.startsWith("~/") ? original : `{file:${resolve(directory, path)}}`,
    );
  if (Array.isArray(value)) return value.map((entry) => anchorFiles(entry, directory));
  if (record(value))
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, anchorFiles(entry, directory)]),
    );
  return value;
}

export async function isolatedProviderConfig(): Promise<Record<string, unknown>> {
  const root =
    process.env.OPENCODE_CONFIG_DIR ??
    join(process.env.XDG_CONFIG_HOME ?? join(homedir(), ".config"), "opencode");
  const paths = [
    join(root, "opencode.json"),
    join(root, "opencode.jsonc"),
    ...(process.env.OPENCODE_CONFIG ? [resolve(process.env.OPENCODE_CONFIG)] : []),
  ];
  let result: Record<string, unknown> = {};
  const include = (value: unknown, directory: string) => {
    if (!record(value)) throw new Error("OpenCode configuration must be a JSON object");
    const selected = Object.fromEntries(
      PROVIDER_FIELDS.filter((key) => key in value).map((key) => [
        key,
        anchorFiles(value[key], directory),
      ]),
    );
    if (record(selected.experimental))
      selected.experimental = { policies: selected.experimental.policies ?? [] };
    result = merge(result, selected) as Record<string, unknown>;
  };
  for (const path of [...new Set(paths)]) {
    let text: string;
    try {
      text = await readFile(path, "utf8");
    } catch (error) {
      if (
        (error as NodeJS.ErrnoException).code === "ENOENT" &&
        path !== (process.env.OPENCODE_CONFIG ? resolve(process.env.OPENCODE_CONFIG) : undefined)
      )
        continue;
      throw new Error("Cannot read OpenCode provider configuration");
    }
    const errors: ParseError[] = [];
    const value: unknown = parse(text, errors, { allowTrailingComma: true });
    if (errors.length) throw new Error("OpenCode provider configuration is not valid JSON/JSONC");
    include(value, dirname(path));
  }
  if (process.env.OPENCODE_CONFIG_CONTENT) {
    let value: unknown;
    try {
      value = JSON.parse(process.env.OPENCODE_CONFIG_CONTENT);
    } catch {
      throw new Error("OpenCode inline configuration must be a JSON object");
    }
    include(value, process.cwd());
  }
  return result;
}
