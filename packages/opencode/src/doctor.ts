import { execFile } from "node:child_process";
import { constants as fsConstants } from "node:fs";
import { readFile, readdir, lstat, stat } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import { CATALOG } from "./catalog.js";
import { listAgentProfiles, type AgentInventory } from "./agent-profiles.js";
import { assertSafePath, deploymentRoot, lifecycleRoot, type Scope } from "./lifecycle.js";
import { inspectReconcile, type ReconcilePlan } from "./reconcile.js";
import { stateRoot } from "./runtime/state.js";

const run = promisify(execFile);
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageName = "@kisev/skills-opencode";
const lspCatalog = JSON.parse(
  readFileSync(resolve(packageRoot, "assets", "lsp-catalog.json"), "utf8"),
) as {
  schema_version: 1;
  catalog_version: string;
  servers: Array<{
    name: string;
    extensions: string[];
    executable: string;
    requirement_class: string;
  }>;
};

export type DoctorCheckStatus = "pass" | "warn" | "fail" | "incomplete";
export type DoctorCheck = {
  id: string;
  status: DoctorCheckStatus;
  summary: string;
  evidence: Record<string, string | number | boolean | string[]>;
  remediation?: string[];
};
export type DoctorHost = {
  config?: () => Promise<unknown>;
  lsp?: () => Promise<unknown>;
};
export type DoctorReport = {
  schema_version: 1;
  status: "clean" | "problems" | "incomplete" | "error";
  mutations: false;
  scope: Scope;
  roots: { project: string; deployment: string; lifecycle: string };
  versions: {
    package: string | null;
    catalog: string;
    installed_manifest: string | null;
    opencode: string | null;
  };
  checks: DoctorCheck[];
  counts: Record<DoctorCheckStatus, number>;
  partial: string[];
  unavailable: string[];
  lsp: Record<string, unknown>;
  retired: Record<string, unknown>;
  conflicts: Array<Record<string, unknown>>;
};

type JsonObject = Record<string, unknown>;
type SafeResult = { raw?: Buffer; status: "present" | "missing" | "incomplete" };

function check(
  id: string,
  status: DoctorCheckStatus,
  summary: string,
  evidence: DoctorCheck["evidence"],
  remediation?: string[],
): DoctorCheck {
  return { id, status, summary, evidence, ...(remediation?.length ? { remediation } : {}) };
}

function errorText(error: unknown): string {
  const code =
    error && typeof error === "object" && "code" in error
      ? String((error as { code: unknown }).code)
      : "error";
  return code === "EACCES" || code === "EPERM" ? "permission denied" : code;
}

async function regular(path: string): Promise<SafeResult> {
  try {
    await assertSafePath(path);
    const info = await lstat(path);
    if (info.isSymbolicLink() || !info.isFile() || info.nlink !== 1)
      return { status: "incomplete" };
    return { raw: await readFile(path), status: "present" };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { status: "missing" };
    return { status: "incomplete" };
  }
}

async function directoryEntries(path: string): Promise<{ files: string[]; incomplete: boolean }> {
  try {
    await assertSafePath(path, { target: "directory" });
    const info = await lstat(path);
    if (info.isSymbolicLink() || !info.isDirectory()) return { files: [], incomplete: true };
    const files: string[] = [];
    let incomplete = false;
    for (const entry of (await readdir(path, { withFileTypes: true })).sort((a, b) =>
      a.name.localeCompare(b.name),
    )) {
      if (entry.isSymbolicLink()) {
        incomplete = true;
        continue;
      }
      if (entry.isFile()) files.push(entry.name);
      else if (entry.isDirectory()) {
        const nested = await directoryEntries(join(path, entry.name));
        files.push(...nested.files.map((name) => `${entry.name}/${name}`));
        incomplete ||= nested.incomplete;
      }
    }
    return { files, incomplete };
  } catch (error) {
    return { files: [], incomplete: errorText(error) !== "ENOENT" };
  }
}

function json(raw: Buffer): JsonObject | undefined {
  try {
    const value: unknown = JSON.parse(raw.toString("utf8"));
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as JsonObject)
      : undefined;
  } catch {
    return undefined;
  }
}

function packageVersion(): string | null {
  try {
    const value = JSON.parse(readFileSync(resolve(packageRoot, "package.json"), "utf8")) as {
      version?: unknown;
    };
    return typeof value.version === "string" ? value.version : null;
  } catch {
    return null;
  }
}

function manifestVersion(raw: Buffer | undefined): string | null {
  const value = raw && json(raw);
  const files = value?.files;
  const validFiles =
    files &&
    typeof files === "object" &&
    !Array.isArray(files) &&
    Object.entries(files).every(
      ([path, record]) =>
        path.length > 0 &&
        !path.startsWith("/") &&
        !path.includes("\\") &&
        !path.split("/").some((part) => part === "" || part === "." || part === "..") &&
        record &&
        typeof record === "object" &&
        /^[a-f0-9]{64}$/.test(String((record as JsonObject).sha256 ?? "")),
    );
  return value &&
    value.schema_version === 1 &&
    value.package === packageName &&
    typeof value.version === "string" &&
    validFiles
    ? value.version
    : null;
}

function agentManifestValid(raw: Buffer | undefined): boolean {
  const value = raw && json(raw);
  return Boolean(
    value &&
    value.schema_version === 1 &&
    value.package === packageName &&
    typeof value.package_version === "string" &&
    (value.scope === "global" || value.scope === "project") &&
    Array.isArray(value.critic_pool) &&
    value.profiles &&
    typeof value.profiles === "object" &&
    !Array.isArray(value.profiles),
  );
}

function redactedConfig(value: unknown): {
  plugins: string[];
  enabled_plugins: string[];
  disabled_plugins: string[];
  unknown_plugins: number;
  keys: string[];
  source: string;
} {
  const object =
    value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
  const rawPlugins = Array.isArray(object.plugin)
    ? object.plugin.flatMap((item) => {
        if (typeof item === "string") return [item];
        if (Array.isArray(item) && typeof item[0] === "string") return [item[0]];
        return [];
      })
    : [];
  const knownPlugins = new Set<string>([packageName, ...CATALOG.plugins]);
  const plugins = rawPlugins.filter((plugin) => knownPlugins.has(plugin));
  const enabled = plugins.filter(
    (plugin) =>
      plugin === packageName ||
      CATALOG.plugins.includes(plugin as (typeof CATALOG.plugins)[number]),
  );
  return {
    plugins: plugins.sort(),
    enabled_plugins: enabled.sort(),
    disabled_plugins: CATALOG.plugins.filter((plugin) => !enabled.includes(plugin)),
    unknown_plugins: rawPlugins.length - plugins.length,
    keys: Object.keys(object)
      .filter((key) =>
        [
          "$schema",
          "theme",
          "keybinds",
          "logLevel",
          "command",
          "watcher",
          "plugin",
          "lsp",
          "formatter",
          "provider",
          "agent",
          "permission",
          "compaction",
          "model",
        ].includes(key),
      )
      .sort(),
    source: "allowlisted-projection",
  };
}

async function localConfig(
  scope: Scope,
  cwd: string,
  home: string,
): Promise<{
  projection?: ReturnType<typeof redactedConfig>;
  source?: string;
  incomplete?: boolean;
}> {
  const paths =
    scope === "project"
      ? [join(cwd, "opencode.json"), join(cwd, ".opencode", "opencode.json")]
      : [join(home, ".config", "opencode", "opencode.json")];
  for (const path of paths) {
    const value = await regular(path);
    if (value.status === "present") {
      const parsed = json(value.raw!);
      return parsed
        ? { projection: redactedConfig(parsed), source: path }
        : { incomplete: true, source: path };
    }
    if (value.status === "incomplete") return { incomplete: true, source: path };
  }
  return {};
}

async function expectedAssets(group: "commands" | "plugins" | "agents"): Promise<string[]> {
  try {
    return (await readdir(join(packageRoot, "assets", group), { withFileTypes: true }))
      .filter((entry) => entry.isFile())
      .map((entry) => entry.name)
      .sort();
  } catch {
    return [];
  }
}

async function filesInState(root: string): Promise<{ count: number; incomplete: boolean }> {
  const result = await directoryEntries(root);
  return {
    count: result.files.filter((name) => name.endsWith(".json") || name.endsWith(".jsonl")).length,
    incomplete: result.incomplete,
  };
}

function diagnosticStateRoot(name: string, home: string): string {
  return home === homedir()
    ? stateRoot(name, home)
    : join(home, ".local", "state", "opencode", "skills", name);
}

async function lifecycleArtifacts(root: string): Promise<{
  count: number;
  locks: number;
  receipts: number;
  journals: number;
  incomplete: boolean;
}> {
  const result = await directoryEntries(root);
  const files = result.files.map((name) => name.toLowerCase());
  return {
    count: files.filter((name) => name.endsWith(".json") || name.endsWith(".jsonl")).length,
    locks: files.filter((name) => name.includes("lock")).length,
    receipts: files.filter((name) => name.includes("receipt")).length,
    journals: files.filter((name) => name.includes("journal")).length,
    incomplete: result.incomplete,
  };
}

async function executableAvailable(name: string): Promise<boolean> {
  const pathValue = process.env.PATH ?? "";
  for (const directory of pathValue.split(delimiter)) {
    if (!directory) continue;
    try {
      const info = await stat(join(directory, name));
      if (info.isFile() && (info.mode & fsConstants.X_OK) !== 0) return true;
    } catch {
      // A missing or inaccessible PATH entry is equivalent to an unavailable binary.
    }
  }
  return false;
}

async function lspFacts(
  project: string,
  host: DoctorHost | undefined,
  partial: string[],
): Promise<Record<string, unknown>> {
  const suffixes = new Set<string>();
  let scanIncomplete = false;
  const visit = async (root: string): Promise<void> => {
    try {
      const info = await lstat(root);
      if (info.isSymbolicLink()) {
        scanIncomplete = true;
        return;
      }
      if (info.isFile()) {
        suffixes.add(root.slice(root.lastIndexOf(".")).toLowerCase());
        return;
      }
      if (!info.isDirectory()) return;
      for (const name of await readdir(root)) await visit(join(root, name));
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") scanIncomplete = true;
    }
  };
  await visit(project);
  if (scanIncomplete) partial.push("lsp.project-files");
  const disabled = process.env.OPENCODE_DISABLE_LSP_DOWNLOAD === "true";
  const servers = await Promise.all(
    lspCatalog.servers.map(async (server) => {
      let available = false;
      available = await executableAvailable(server.executable);
      const applicable = server.extensions.some((extension) => suffixes.has(extension));
      return {
        name: server.name,
        applicable,
        configured: applicable,
        binary_available: available,
        active: applicable && available && !disabled,
        runtime_status: "unavailable",
        requirement_class: server.requirement_class,
        reason: !applicable
          ? "not-selected"
          : disabled
            ? "download-disabled"
            : !available
              ? "missing-dependency"
              : "available",
        missing: available ? [] : [server.executable],
        install: `Install ${server.executable} with your project toolchain.`,
      };
    }),
  );
  let runtimeStatus: unknown = "unavailable";
  if (host?.lsp) {
    try {
      const value = await host.lsp();
      runtimeStatus = Array.isArray(value)
        ? value.map((item) => {
            const entry = item && typeof item === "object" ? (item as JsonObject) : {};
            return {
              id: typeof entry.id === "string" ? entry.id : "unknown",
              name: typeof entry.name === "string" ? entry.name : "unknown",
              status:
                entry.status === "connected" || entry.status === "error" ? entry.status : "unknown",
            };
          })
        : { status: "unavailable" };
    } catch {
      partial.push("lsp.runtime-status");
    }
  } else partial.push("lsp.runtime-status");
  return {
    schema_version: 1,
    catalog_version: lspCatalog.catalog_version,
    download_disabled: disabled,
    runtime_status: runtimeStatus,
    servers,
  };
}

function reconcileProjection(plan: ReconcilePlan): {
  retired: Record<string, unknown>;
  conflicts: Array<Record<string, unknown>>;
} {
  const groups = [
    "current",
    "renamed",
    "retired",
    "modified_managed",
    "user_owned",
    "unknown",
    "diagnostic_state_only",
  ] as const;
  const retired = Object.fromEntries(
    groups.map((name) => [
      name,
      plan[name].map((item) => ({
        path: item.path,
        status: item.status,
        replacement: item.replacement ?? null,
      })),
    ]),
  );
  const conflicts = plan.conflicts.map((item) => ({
    path: item.path,
    status: item.status,
    reason: item.reason,
    replacement: item.replacement ?? null,
  }));
  return { retired, conflicts };
}

export async function collectDoctorFacts(
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
  host?: DoctorHost,
): Promise<DoctorReport> {
  const project = resolve(cwd);
  const homeRoot = resolve(home);
  const deployment = deploymentRoot(scope, project, homeRoot);
  const lifecycle = lifecycleRoot(scope, project, homeRoot);
  const checks: DoctorCheck[] = [];
  const partial: string[] = [];
  const unavailable: string[] = [];
  let installedRaw: Buffer | undefined;
  const packageVersionValue = packageVersion();
  checks.push(
    check(
      "package.version",
      packageVersionValue ? "pass" : "fail",
      "Package metadata is readable",
      { package: packageName, version: packageVersionValue ?? "unavailable" },
      ["Reinstall the package if metadata is missing."],
    ),
  );
  checks.push(
    check(
      "catalog.version",
      CATALOG.version === packageVersionValue ? "pass" : "fail",
      "Capability catalog matches package metadata",
      { catalog_version: CATALOG.version, package_version: packageVersionValue ?? "unavailable" },
      ["Regenerate the package catalog from package metadata."],
    ),
  );
  const manifest = await regular(join(deployment, ".skills-opencode-manifest.json"));
  if (manifest.status === "present") installedRaw = manifest.raw;
  if (manifest.status === "incomplete") partial.push("installed-manifest");
  const installedVersion = manifestVersion(installedRaw);
  checks.push(
    check(
      "manifest.version",
      manifest.status === "missing"
        ? "incomplete"
        : installedVersion === null
          ? "warn"
          : installedVersion === packageVersionValue
            ? "pass"
            : "warn",
      manifest.status === "present"
        ? "Installed manifest format and version are classified"
        : "Installed manifest is not available",
      {
        path: ".skills-opencode-manifest.json",
        present: manifest.status === "present",
        valid: installedVersion !== null,
        version: installedVersion ?? "unavailable",
      },
      ["Run the installer preview for this scope."],
    ),
  );

  const assetGroups = await Promise.all(
    ["commands", "plugins", "agents"].map(
      async (group) =>
        [
          group,
          await directoryEntries(join(deployment, group)),
          await expectedAssets(group as "commands" | "plugins" | "agents"),
        ] as const,
    ),
  );
  for (const [group, entries, expected] of assetGroups) {
    const missing = expected.filter((name) => !entries.files.includes(name));
    const extra = entries.files.filter((name) => !expected.includes(name));
    const status: DoctorCheckStatus = entries.incomplete
      ? "incomplete"
      : missing.length || (group !== "agents" && extra.length)
        ? "fail"
        : "pass";
    checks.push(
      check(
        `assets.${group}`,
        status,
        `${group} completeness and collisions are classified`,
        {
          count: entries.files.length,
          expected: expected.length,
          missing,
          collisions: group === "agents" ? [] : extra,
        },
        status === "fail"
          ? ["Run the installer preview and review ownership conflicts before applying."]
          : entries.incomplete
            ? ["Remove symlinks or restore inaccessible asset paths."]
            : undefined,
      ),
    );
  }
  let inventory: AgentInventory | undefined;
  try {
    inventory = await listAgentProfiles(scope, project, homeRoot);
  } catch {
    partial.push("agent-profiles");
  }
  const agentStatus = inventory
    ? inventory.collisions.length || inventory.drift.length
      ? "fail"
      : "pass"
    : "incomplete";
  checks.push(
    check(
      "agents.completeness-ownership-drift",
      agentStatus,
      "Agent profile inventory is classified",
      {
        profiles: inventory?.profiles.length ?? 0,
        collisions: inventory?.collisions.length ?? 0,
        drift: inventory?.drift.length ?? 0,
        user_owned: inventory?.user_owned.length ?? 0,
      },
      ["Review collisions and run agent reconcile only after explicit confirmation."],
    ),
  );
  const config = await localConfig(scope, project, homeRoot);
  if (config.incomplete) partial.push("config.local");
  let hostConfig: ReturnType<typeof redactedConfig> | undefined;
  if (host?.config) {
    try {
      hostConfig = redactedConfig(await host.config());
    } catch {
      partial.push("config.resolved");
    }
  } else unavailable.push("config.resolved");
  checks.push(
    check(
      "config.plugins",
      config.projection || hostConfig ? "pass" : "incomplete",
      "Config plugin projection is available",
      {
        local: config.projection?.plugins ?? [],
        local_enabled: config.projection?.enabled_plugins ?? [],
        local_disabled: config.projection?.disabled_plugins ?? [...CATALOG.plugins],
        local_unknown: config.projection?.unknown_plugins ?? 0,
        resolved: hostConfig?.plugins ?? [],
        resolved_enabled: hostConfig?.enabled_plugins ?? [],
        resolved_disabled: hostConfig?.disabled_plugins ?? [...CATALOG.plugins],
        resolved_unknown: hostConfig?.unknown_plugins ?? 0,
        source: config.source ?? "host-or-file-unavailable",
      },
      ["Inspect OpenCode configuration without exposing secrets."],
    ),
  );
  const profileManifest = await regular(
    join(deployment, ".skills-opencode", "agent-profiles.manifest.json"),
  );
  const profileManifestIsValid = agentManifestValid(profileManifest.raw);
  checks.push(
    check(
      "agents.manifest",
      profileManifest.status === "present"
        ? profileManifestIsValid
          ? "pass"
          : "warn"
        : profileManifest.status === "missing"
          ? "incomplete"
          : "warn",
      "Agent profile manifest is classified",
      {
        present: profileManifest.status === "present",
        valid: profileManifestIsValid,
        path: ".skills-opencode/agent-profiles.manifest.json",
      },
      ["Run the installer preview for this scope."],
    ),
  );

  let reconcile: ReconcilePlan | undefined;
  try {
    reconcile = await inspectReconcile(scope, project, homeRoot);
  } catch {
    partial.push("stage-8-reconcile");
  }
  const projected = reconcile ? reconcileProjection(reconcile) : { retired: {}, conflicts: [] };
  checks.push(
    check(
      "migration.stage-8",
      reconcile ? (projected.conflicts.length ? "fail" : "pass") : "incomplete",
      "Stage-8 inventory classifications are read-only",
      {
        inventory_version: reconcile?.inventory_version ?? "unavailable",
        retired: reconcile?.retired.length ?? 0,
        conflicts: projected.conflicts.length,
      },
      ["Review retired or conflicting entries; do not use historical backup state."],
    ),
  );

  const stateRoots = ["attempt", "schedule", "worktree", "goal", "multi-run"].map(
    (name) => [name, diagnosticStateRoot(name, homeRoot)] as const,
  );
  for (const [name, root] of stateRoots) {
    const value = await filesInState(root);
    if (value.incomplete) partial.push(`state.${name}`);
    checks.push(
      check(
        `state.${name}`,
        value.incomplete ? "incomplete" : "pass",
        `${name} state is inspected without recovery`,
        { records: value.count, diagnostic_state_only: name === "goal" || name === "multi-run" },
        value.incomplete
          ? ["Repair permissions or malformed state manually; doctor never recovers it."]
          : undefined,
      ),
    );
  }
  const lifecycleFiles = await lifecycleArtifacts(lifecycle);
  checks.push(
    check(
      "lifecycle.artifacts",
      lifecycleFiles.incomplete ? "incomplete" : "pass",
      "Lifecycle locks, receipts, and journals are inspected without mutation",
      {
        records: lifecycleFiles.count,
        locks: lifecycleFiles.locks,
        receipts: lifecycleFiles.receipts,
        journals: lifecycleFiles.journals,
        recovery: false,
      },
      lifecycleFiles.incomplete
        ? ["Resolve inaccessible lifecycle state before applying a mutation."]
        : undefined,
    ),
  );
  const tools = await Promise.all(
    ["opencode", ...lspCatalog.servers.map((server) => server.executable)].map(async (name) => {
      try {
        const result = await run(name, ["--version"], { timeout: 1000 });
        return {
          name,
          available: true,
          version:
            result.stdout
              .trim()
              .split(/\s+/)
              .find((value) => /\d+\.\d+/.test(value)) ?? null,
        };
      } catch {
        return { name, available: false, version: null };
      }
    }),
  );
  checks.push(
    check(
      "host.tools",
      tools.some((item) => item.name === "opencode" && item.available) ? "pass" : "incomplete",
      "External tool availability is reported",
      { tools: tools.map((item) => `${item.name}:${item.available ? "available" : "missing"}`) },
      ["Install OpenCode or missing external tools when needed."],
    ),
  );
  const lsp = await lspFacts(project, host, partial);
  const counts = { pass: 0, warn: 0, fail: 0, incomplete: 0 };
  for (const item of checks) counts[item.status] += 1;
  const status = counts.fail
    ? "problems"
    : counts.incomplete || partial.length > 0 || unavailable.length > 0
      ? "incomplete"
      : "clean";
  return {
    schema_version: 1,
    status,
    mutations: false,
    scope,
    roots: { project, deployment, lifecycle },
    versions: {
      package: packageVersionValue,
      catalog: CATALOG.version,
      installed_manifest: installedVersion,
      opencode: tools.find((item) => item.name === "opencode")?.version ?? null,
    },
    checks,
    counts,
    partial: [...new Set(partial)].sort(),
    unavailable: [...new Set(unavailable)].sort(),
    lsp,
    retired: projected.retired,
    conflicts: projected.conflicts,
  };
}

export function doctorExitCode(report: DoctorReport): number {
  return report.status === "clean" ? 0 : report.status === "problems" ? 1 : 2;
}
