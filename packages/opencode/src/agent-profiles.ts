import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";
import { lstat } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

import {
  applyTransaction,
  consumeReceipt,
  deploymentRoot,
  destination,
  digest,
  LifecycleError,
  lifecycleRoot,
  listDirectRegular,
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

export { type Scope as AgentProfileScope } from "./lifecycle.js";

export const FIXED_AGENT_ROLES = [
  "manager",
  "architect",
  "mapper",
  "worker",
  "review",
  "critic",
] as const;
export type FixedAgentRole = (typeof FIXED_AGENT_ROLES)[number];
export type AgentModelSelection = { model: string; variant?: string };
export type AgentProfileConfig = {
  schema_version: 1;
  fixed: Record<FixedAgentRole, AgentModelSelection | Record<string, never>>;
  additional_critics: Record<string, AgentModelSelection>;
};
export type DeploymentRecord = {
  kind: "fixed" | "additional-critic";
  template: FixedAgentRole;
  canonical_sha256: string;
  configuration_sha256: string;
  rendered_sha256: string;
};
export type DeploymentManifest = {
  schema_version: 1;
  package: "@kisev/skills-opencode";
  package_version: string;
  scope: Scope;
  critic_pool: string[];
  profiles: Record<string, DeploymentRecord>;
};
export type AgentOwnership = "package-owned" | "managed" | "user-owned";
export type AgentState = "current" | "missing" | "drift" | "collision";
export type AgentProfileRecord = {
  name: string;
  ownership: AgentOwnership;
  state: AgentState;
  model?: string;
  variant?: string;
  rendered_sha256?: string;
};
export type AgentInventory = {
  schema_version: 1;
  scope: Scope;
  root: string;
  package_version: string;
  critic_pool: string[];
  profiles: AgentProfileRecord[];
  user_owned: string[];
  collisions: string[];
  drift: string[];
  requires_restart: false;
  digest: string;
};
export type AgentProfileAction =
  "install" | "model-set" | "critic-add" | "critic-remove" | "reconcile" | "uninstall";
export type AgentProfileRequest = {
  action: AgentProfileAction;
  name?: string;
  model?: string;
  variant?: string | null;
};
export type AgentProfileOperation = {
  path: string;
  operation: "create" | "update" | "remove" | "unchanged" | "conflict";
  reason: string;
  sha256?: string;
};
export type AgentProfilePlan = {
  schema_version: 1;
  domain: "agent-profiles";
  action: AgentProfileAction;
  scope: Scope;
  root: string;
  operations: AgentProfileOperation[];
  critic_pool: string[];
  digest: string;
  receipt_expires_at?: string;
  requires_restart: boolean;
};
export type AgentProfileResult = {
  status: "ok";
  applied: boolean;
  requires_restart: boolean;
  plan: AgentProfilePlan;
};

export class AgentProfileError extends LifecycleError {}

type LegacyManifest = {
  schema_version: 1;
  package: string;
  version: string;
  files: Record<string, { sha256: string }>;
};
export type LegacyAgentOwnership = {
  manifest: LegacyManifest;
  manifestPath: string;
  manifestSha256: string;
};
type BuiltPlan = {
  plan: AgentProfilePlan;
  mutations: FileMutation[];
  inventoryDigest: string;
  config: AgentProfileConfig;
  manifest?: DeploymentManifest;
  expectedConfig?: Buffer;
  expectedManifest?: Buffer;
  legacyTransferred: string[];
};

const PACKAGE_NAME = "@kisev/skills-opencode" as const;
const CONFIG_PATH = ".skills-opencode/agent-profiles.json";
const MANIFEST_PATH = ".skills-opencode/agent-profiles.manifest.json";
const AGENTS_DIRECTORY = "agents";
const NAME_PATTERN = /^(?:manager|architect|mapper|worker|review|critic)$/;
const CRITIC_PATTERN = /^critic-[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_./-]*$/;
const VARIANT_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/;
const execFileAsync = promisify(execFile);
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const assetsRoot = resolve(packageRoot, "assets", "agents");

const V1_AGENT_SHA256: Readonly<Record<FixedAgentRole, string>> = {
  architect: "3894c4ea5719d8945809157f1611fe5d1ea0ef2461a6092d94c18948baca1bee",
  critic: "17396c401c6680f95394c2a2d004fc8c9409d845fad99bee0b6cc485fd923e74",
  manager: "6b6e2d6a845aebf0b3d5609e461021ece07f80a70618e7ba2d8679c2592e7570",
  mapper: "d98a1c84d718cf3394a9e2274318973784770280b4cbbc53f968819bde3bf7eb",
  review: "ae33393964e9e9faf5c9c87884d8746d8f80d85f4ddf854d442bd0f44f50d95f",
  worker: "eee1163111b59856cc95c8be4ef4bc85a12e23c05bf576ece9f8e6a933b5466d",
};

function packageVersion(): string {
  const value = JSON.parse(readFileSync(resolve(packageRoot, "package.json"), "utf8")) as {
    version?: unknown;
  };
  if (typeof value.version !== "string")
    throw new AgentProfileError("invalid_package", "Package version is unavailable");
  return value.version;
}

function emptyConfig(): AgentProfileConfig {
  return {
    schema_version: 1,
    fixed: Object.fromEntries(
      FIXED_AGENT_ROLES.map((role) => [role, {}]),
    ) as AgentProfileConfig["fixed"],
    additional_critics: {},
  };
}

export function validateAgentName(name: string): string {
  if (NAME_PATTERN.test(name) || CRITIC_PATTERN.test(name)) return name;
  throw new AgentProfileError("invalid_name", "Agent must be a fixed role or critic-<safe-suffix>");
}

export function validateModel(model: string): string {
  if (!MODEL_PATTERN.test(model))
    throw new AgentProfileError("invalid_model", "Model must be an exact provider/model value");
  return model;
}

export function validateVariant(variant: string | null | undefined): string | undefined {
  if (variant === null || variant === undefined || variant === "") return undefined;
  if (!VARIANT_PATTERN.test(variant))
    throw new AgentProfileError("invalid_variant", "Variant must be a safe exact value");
  return variant;
}

function parseSelection(
  value: unknown,
  required: boolean,
): AgentModelSelection | Record<string, never> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new AgentProfileError("invalid_configuration", "Agent selection must be an object");
  const entry = value as Record<string, unknown>;
  const keys = Object.keys(entry).sort();
  if (!entry.model && !required && keys.length === 0) return {};
  if (typeof entry.model !== "string")
    throw new AgentProfileError("invalid_configuration", "Agent model is required");
  const selection: AgentModelSelection = { model: validateModel(entry.model) };
  if (entry.variant !== undefined) {
    if (typeof entry.variant !== "string")
      throw new AgentProfileError("invalid_configuration", "Agent variant must be a string");
    selection.variant = validateVariant(entry.variant);
  }
  if (keys.some((key) => key !== "model" && key !== "variant"))
    throw new AgentProfileError("invalid_configuration", "Agent selection contains unknown fields");
  return selection;
}

function parseConfig(raw: Buffer): AgentProfileConfig {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new AgentProfileError(
      "invalid_configuration",
      "Agent profile configuration is not valid JSON",
    );
  }
  const config = value as Partial<AgentProfileConfig>;
  if (
    config.schema_version !== 1 ||
    !config.fixed ||
    typeof config.fixed !== "object" ||
    Array.isArray(config.fixed) ||
    !config.additional_critics ||
    typeof config.additional_critics !== "object" ||
    Array.isArray(config.additional_critics)
  ) {
    throw new AgentProfileError(
      "invalid_configuration",
      "Agent profile configuration has an unsupported schema",
    );
  }
  if (Object.keys(config.fixed).sort().join(",") !== [...FIXED_AGENT_ROLES].sort().join(","))
    throw new AgentProfileError(
      "invalid_configuration",
      "Configuration must contain every fixed role exactly once",
    );
  const fixed = Object.fromEntries(
    FIXED_AGENT_ROLES.map((role) => [role, parseSelection(config.fixed![role], false)]),
  ) as AgentProfileConfig["fixed"];
  const additional: Record<string, AgentModelSelection> = {};
  for (const [name, selection] of Object.entries(config.additional_critics)) {
    if (!CRITIC_PATTERN.test(name))
      throw new AgentProfileError(
        "invalid_configuration",
        `Unsafe additional critic name: ${name}`,
      );
    additional[name] = parseSelection(selection, true) as AgentModelSelection;
  }
  return {
    schema_version: 1,
    fixed,
    additional_critics: Object.fromEntries(
      Object.entries(additional).sort(([left], [right]) => left.localeCompare(right)),
    ),
  };
}

function parseManifest(raw: Buffer, scope: Scope): DeploymentManifest {
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    throw new AgentProfileError("invalid_manifest", "Agent deployment manifest is not valid JSON");
  }
  const manifest = value as Partial<DeploymentManifest>;
  if (
    manifest.schema_version !== 1 ||
    manifest.package !== PACKAGE_NAME ||
    typeof manifest.package_version !== "string" ||
    manifest.scope !== scope ||
    !Array.isArray(manifest.critic_pool) ||
    !manifest.profiles ||
    typeof manifest.profiles !== "object" ||
    Array.isArray(manifest.profiles)
  ) {
    throw new AgentProfileError(
      "invalid_manifest",
      "Agent deployment manifest has an unsupported schema",
    );
  }
  const names = Object.keys(manifest.profiles).sort();
  const expectedPool = names.filter((name) => name === "critic" || CRITIC_PATTERN.test(name));
  if (manifest.critic_pool.join(",") !== expectedPool.join(","))
    throw new AgentProfileError(
      "invalid_manifest",
      "Agent deployment manifest has a non-exact critic pool",
    );
  for (const [name, record] of Object.entries(manifest.profiles)) {
    validateAgentName(name);
    if (
      !record ||
      typeof record !== "object" ||
      !["fixed", "additional-critic"].includes(record.kind) ||
      !FIXED_AGENT_ROLES.includes(record.template) ||
      ![record.canonical_sha256, record.configuration_sha256, record.rendered_sha256].every(
        (item) => typeof item === "string" && /^[a-f0-9]{64}$/.test(item),
      )
    ) {
      throw new AgentProfileError("invalid_manifest", `Invalid deployment record: ${name}`);
    }
    if (
      (NAME_PATTERN.test(name) && record.kind !== "fixed") ||
      (CRITIC_PATTERN.test(name) && record.kind !== "additional-critic") ||
      (record.kind === "additional-critic" && record.template !== "critic")
    ) {
      throw new AgentProfileError(
        "invalid_manifest",
        `Deployment ownership does not match profile name: ${name}`,
      );
    }
  }
  return manifest as DeploymentManifest;
}

async function loadState(
  scope: Scope,
  root: string,
): Promise<{
  config: AgentProfileConfig;
  configRaw?: Buffer;
  manifest?: DeploymentManifest;
  manifestRaw?: Buffer;
}> {
  const configPath = destination(root, CONFIG_PATH);
  const manifestPath = destination(root, MANIFEST_PATH);
  const [configRaw, manifestRaw] = await Promise.all([
    readRegular(configPath),
    readRegular(manifestPath),
  ]);
  if (configRaw && (await inspectFileMode(configPath)) !== 0o600)
    throw new AgentProfileError(
      "unsafe_configuration",
      "Agent profile configuration must use mode 0600",
    );
  if (manifestRaw && (await inspectFileMode(manifestPath)) !== 0o600)
    throw new AgentProfileError("unsafe_manifest", "Agent deployment manifest must use mode 0600");
  return {
    config: configRaw ? parseConfig(configRaw) : emptyConfig(),
    configRaw,
    manifest: manifestRaw ? parseManifest(manifestRaw, scope) : undefined,
    manifestRaw,
  };
}

async function canonicalAssets(): Promise<Record<FixedAgentRole, Buffer>> {
  return Object.fromEntries(
    await Promise.all(
      FIXED_AGENT_ROLES.map(async (role) => {
        const path = resolve(assetsRoot, `${role}.md`);
        const content = await readRegular(path);
        if (!content)
          throw new AgentProfileError("asset_error", `Canonical agent asset is missing: ${role}`);
        return [role, content] as const;
      }),
    ),
  ) as Record<FixedAgentRole, Buffer>;
}

function withSelection(
  content: string,
  selection: AgentModelSelection | Record<string, never>,
): string {
  if (!("model" in selection)) return content;
  const lines = content.split("\n");
  const end = lines.indexOf("---", 1);
  if (lines[0] !== "---" || end < 2)
    throw new AgentProfileError("asset_error", "Canonical agent frontmatter is invalid");
  const filtered = lines.filter((line, index) => index > end || !/^(model|variant):/.test(line));
  const mode = filtered.findIndex((line, index) => index < end && line.startsWith("mode:"));
  if (mode < 0) throw new AgentProfileError("asset_error", "Canonical agent has no mode");
  filtered.splice(
    mode + 1,
    0,
    `model: ${selection.model}`,
    ...(selection.variant ? [`variant: ${selection.variant}`] : []),
  );
  return filtered.join("\n");
}

function replaceTaskAllowlist(content: string, allowed: readonly string[]): string {
  const lines = content.split("\n");
  const permission = lines.indexOf("permission:");
  if (permission < 0)
    throw new AgentProfileError("asset_error", "Canonical primary agent has no permission block");
  const task = lines.findIndex((line, index) => index > permission && line === "  task:");
  if (task < 0)
    throw new AgentProfileError("asset_error", "Canonical primary agent has no task permission");
  let end = task + 1;
  while (end < lines.length && (lines[end].startsWith("    ") || lines[end] === "")) end += 1;
  lines.splice(
    task,
    end - task,
    "  task:",
    '    "*": deny',
    ...allowed.map((name) => `    ${name}: allow`),
  );
  return lines.join("\n");
}

export function renderAgentProfile(
  name: string,
  config: AgentProfileConfig,
  canonical: Record<FixedAgentRole, Buffer>,
): Buffer {
  validateAgentName(name);
  const role = NAME_PATTERN.test(name) ? (name as FixedAgentRole) : "critic";
  const selection = NAME_PATTERN.test(name) ? config.fixed[role] : config.additional_critics[name];
  if (!selection)
    throw new AgentProfileError("invalid_configuration", `No configuration exists for ${name}`);
  let rendered = withSelection(canonical[role].toString("utf8"), selection);
  const pool = ["critic", ...Object.keys(config.additional_critics)].sort();
  if (name === "manager")
    rendered = replaceTaskAllowlist(rendered, ["architect", "worker", "mapper", ...pool]);
  if (name === "review") rendered = replaceTaskAllowlist(rendered, pool);
  return Buffer.from(rendered);
}

function selectionFor(
  config: AgentProfileConfig,
  name: string,
): AgentModelSelection | Record<string, never> {
  return NAME_PATTERN.test(name)
    ? config.fixed[name as FixedAgentRole]
    : config.additional_critics[name];
}

function desiredNames(config: AgentProfileConfig): string[] {
  return [...FIXED_AGENT_ROLES, ...Object.keys(config.additional_critics)].sort();
}

function desiredManifest(
  scope: Scope,
  config: AgentProfileConfig,
  rendered: Record<string, Buffer>,
  canonical: Record<FixedAgentRole, Buffer>,
): DeploymentManifest {
  const profiles: Record<string, DeploymentRecord> = {};
  for (const name of desiredNames(config)) {
    const role = NAME_PATTERN.test(name) ? (name as FixedAgentRole) : "critic";
    const selection = selectionFor(config, name);
    profiles[name] = {
      kind: NAME_PATTERN.test(name) ? "fixed" : "additional-critic",
      template: role,
      canonical_sha256: sha256(canonical[role]),
      configuration_sha256: digest(selection),
      rendered_sha256: sha256(rendered[name]),
    };
  }
  return {
    schema_version: 1,
    package: PACKAGE_NAME,
    package_version: packageVersion(),
    scope,
    critic_pool: desiredNames(config).filter(
      (name) => name === "critic" || CRITIC_PATTERN.test(name),
    ),
    profiles,
  };
}

function changeConfig(
  current: AgentProfileConfig,
  request: AgentProfileRequest,
): AgentProfileConfig {
  const config = JSON.parse(JSON.stringify(current)) as AgentProfileConfig;
  if (request.action === "model-set") {
    const name = validateAgentName(request.name ?? "");
    if (!NAME_PATTERN.test(name) && !(name in config.additional_critics))
      throw new AgentProfileError(
        "unknown_profile",
        `Additional critic is not configured: ${name}`,
      );
    const selection: AgentModelSelection = { model: validateModel(request.model ?? "") };
    const variant = validateVariant(request.variant);
    if (variant) selection.variant = variant;
    if (NAME_PATTERN.test(name)) config.fixed[name as FixedAgentRole] = selection;
    else config.additional_critics[name] = selection;
  } else if (request.action === "critic-add") {
    const name = request.name ?? "";
    if (!CRITIC_PATTERN.test(name))
      throw new AgentProfileError(
        "invalid_name",
        "Additional critic must match critic-<safe-suffix>",
      );
    if (name in config.additional_critics)
      throw new AgentProfileError("profile_exists", `Additional critic already exists: ${name}`);
    const selection: AgentModelSelection = { model: validateModel(request.model ?? "") };
    const variant = validateVariant(request.variant);
    if (variant) selection.variant = variant;
    config.additional_critics[name] = selection;
  } else if (request.action === "critic-remove") {
    const name = request.name ?? "";
    if (name === "critic" || NAME_PATTERN.test(name))
      throw new AgentProfileError(
        "immutable_profile",
        "Standard critic and fixed roles cannot be removed or renamed",
      );
    if (!CRITIC_PATTERN.test(name))
      throw new AgentProfileError(
        "invalid_name",
        "Additional critic must match critic-<safe-suffix>",
      );
    if (!(name in config.additional_critics))
      throw new AgentProfileError(
        "unknown_profile",
        `Additional critic is not configured: ${name}`,
      );
    delete config.additional_critics[name];
  }
  config.additional_critics = Object.fromEntries(
    Object.entries(config.additional_critics).sort(([left], [right]) => left.localeCompare(right)),
  );
  return config;
}

function legacyIsExact(
  legacy: LegacyAgentOwnership | undefined,
  current: Map<string, Buffer>,
): boolean {
  if (
    !legacy ||
    legacy.manifest.schema_version !== 1 ||
    legacy.manifest.package !== PACKAGE_NAME ||
    legacy.manifest.version !== "1.0.0"
  )
    return false;
  return FIXED_AGENT_ROLES.every((role) => {
    const path = `agents/${role}.md`;
    const record = legacy.manifest.files[path];
    const content = current.get(`${role}.md`);
    return (
      record?.sha256 === V1_AGENT_SHA256[role] &&
      content !== undefined &&
      sha256(content) === record.sha256
    );
  });
}

function planDigestBase(
  plan: Omit<AgentProfilePlan, "digest" | "receipt_expires_at">,
  inventoryDigest: string,
  request: AgentProfileRequest,
): string {
  return digest({ plan, inventory_digest: inventoryDigest, request });
}

export async function buildAgentProfilePlan(
  request: AgentProfileRequest,
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
  legacy?: LegacyAgentOwnership,
): Promise<BuiltPlan> {
  const root = deploymentRoot(scope, cwd, home);
  const [state, canonical, agentFiles] = await Promise.all([
    loadState(scope, root),
    canonicalAssets(),
    listDirectRegular(destination(root, AGENTS_DIRECTORY)),
  ]);
  const byFile = new Map(
    agentFiles.filter((item) => item.name.endsWith(".md")).map((item) => [item.name, item.content]),
  );
  const config = changeConfig(state.config, request);
  const names = request.action === "uninstall" ? [] : desiredNames(config);
  const rendered = Object.fromEntries(
    names.map((name) => [name, renderAgentProfile(name, config, canonical)]),
  );
  const desired =
    request.action === "uninstall"
      ? undefined
      : desiredManifest(scope, config, rendered, canonical);
  const legacyExact = !state.manifest && legacyIsExact(legacy, byFile);
  const legacyTransferred = legacyExact ? FIXED_AGENT_ROLES.map((role) => `agents/${role}.md`) : [];
  const operations: AgentProfileOperation[] = [];
  const mutations: FileMutation[] = [];
  const currentManifest = state.manifest;

  const allOwnedNames = new Set([
    ...(currentManifest ? Object.keys(currentManifest.profiles) : []),
    ...names,
  ]);
  for (const name of [...allOwnedNames].sort()) {
    const path = `agents/${name}.md`;
    const content = byFile.get(`${name}.md`);
    const record = currentManifest?.profiles[name];
    const next = rendered[name];
    const adopted = legacyExact && NAME_PATTERN.test(name);
    if (!next) {
      if (!record) continue;
      if (!content) {
        operations.push({
          path,
          operation: "unchanged",
          reason: "managed profile is already missing",
        });
      } else if (sha256(content) !== record.rendered_sha256) {
        operations.push({
          path,
          operation: "conflict",
          reason: "managed profile drift is preserved",
          sha256: sha256(content),
        });
      } else {
        operations.push({
          path,
          operation: "remove",
          reason: "explicit profile uninstall or critic removal",
        });
        mutations.push({ path, operation: "remove", expected: { sha256: record.rendered_sha256 } });
      }
      continue;
    }
    if (!record && !adopted) {
      if (content) {
        operations.push({ path, operation: "conflict", reason: "exact-name user-owned collision" });
      } else {
        operations.push({ path, operation: "create", reason: "package profile deployment" });
        mutations.push({
          path,
          operation: "write",
          content: next,
          mode: 0o600,
          expected: { absent: true },
        });
      }
      continue;
    }
    const ownedHash = adopted ? V1_AGENT_SHA256[name as FixedAgentRole] : record!.rendered_sha256;
    const drift =
      !adopted &&
      (!content ||
        sha256(content) !== ownedHash ||
        agentFiles.find((item) => item.name === `${name}.md`)?.mode !== 0o600);
    if (drift && request.action !== "reconcile") {
      operations.push({
        path,
        operation: "conflict",
        reason: "managed profile drift requires explicit reconcile",
        ...(content ? { sha256: sha256(content) } : {}),
      });
      continue;
    }
    if (!content) {
      operations.push({ path, operation: "create", reason: "explicit managed profile reconcile" });
      mutations.push({
        path,
        operation: "write",
        content: next,
        mode: 0o600,
        expected: { absent: true },
      });
    } else if (
      !content.equals(next) ||
      agentFiles.find((item) => item.name === `${name}.md`)?.mode !== 0o600
    ) {
      operations.push({
        path,
        operation: "update",
        reason: drift
          ? "explicit managed profile reconcile"
          : adopted
            ? "v1.0.0 ownership transfer"
            : "model, variant, critic pool, or package update",
      });
      mutations.push({
        path,
        operation: "write",
        content: next,
        mode: 0o600,
        expected: { sha256: sha256(content) },
      });
    } else {
      operations.push({ path, operation: "unchanged", reason: "rendered profile is current" });
    }
  }

  const configContent = Buffer.from(`${stable(config)}\n`);
  if (
    request.action !== "uninstall" &&
    (!state.configRaw || !state.configRaw.equals(configContent))
  ) {
    operations.push({
      path: CONFIG_PATH,
      operation: state.configRaw ? "update" : "create",
      reason: "separate user profile configuration",
    });
    mutations.push({
      path: CONFIG_PATH,
      operation: "write",
      content: configContent,
      mode: 0o600,
      expected: state.configRaw ? { sha256: sha256(state.configRaw) } : { absent: true },
    });
  }

  const remainingDrift = operations
    .filter((item) => item.operation === "conflict" && item.reason.includes("drift"))
    .map((item) => item.path.replace(/^agents\//, "").replace(/\.md$/, ""));
  let finalManifest = desired;
  if (request.action === "uninstall" && currentManifest && remainingDrift.length) {
    finalManifest = {
      ...currentManifest,
      profiles: Object.fromEntries(
        remainingDrift.map((name) => [name, currentManifest.profiles[name]]),
      ),
      critic_pool: remainingDrift.filter((name) => name === "critic" || CRITIC_PATTERN.test(name)),
    };
  }
  const manifestContent = finalManifest ? Buffer.from(`${stable(finalManifest)}\n`) : undefined;
  if (manifestContent && (!state.manifestRaw || !state.manifestRaw.equals(manifestContent))) {
    operations.push({
      path: MANIFEST_PATH,
      operation: state.manifestRaw ? "update" : "create",
      reason: "semantic rendered ownership manifest",
    });
    mutations.push({
      path: MANIFEST_PATH,
      operation: "write",
      content: manifestContent,
      mode: 0o600,
      expected: state.manifestRaw ? { sha256: sha256(state.manifestRaw) } : { absent: true },
    });
  } else if (!manifestContent && state.manifestRaw && !remainingDrift.length) {
    operations.push({
      path: MANIFEST_PATH,
      operation: "remove",
      reason: "profile deployment uninstalled",
    });
    mutations.push({
      path: MANIFEST_PATH,
      operation: "remove",
      expected: { sha256: sha256(state.manifestRaw) },
    });
  }

  const inventoryDigest = digest({
    package_version: packageVersion(),
    canonical: Object.fromEntries(FIXED_AGENT_ROLES.map((role) => [role, sha256(canonical[role])])),
    desired_configuration: config,
    desired_manifest: finalManifest ?? null,
    config: state.configRaw?.toString("base64") ?? null,
    manifest: state.manifestRaw?.toString("base64") ?? null,
    agents: agentFiles.map((item) => ({
      name: item.name,
      sha256: sha256(item.content),
      mode: item.mode,
    })),
  });
  const base = {
    schema_version: 1 as const,
    domain: "agent-profiles" as const,
    action: request.action,
    scope,
    root,
    operations: operations.sort((left, right) => left.path.localeCompare(right.path)),
    critic_pool: desired?.critic_pool ?? finalManifest?.critic_pool ?? [],
    requires_restart: mutations.some((item) => item.path.startsWith("agents/")),
  };
  const plan: AgentProfilePlan = {
    ...base,
    digest: planDigestBase(base, inventoryDigest, request),
  };
  return {
    plan,
    mutations,
    inventoryDigest,
    config,
    manifest: finalManifest,
    expectedConfig: request.action === "uninstall" ? state.configRaw : configContent,
    expectedManifest: manifestContent,
    legacyTransferred,
  };
}

export async function validateBuiltAgentProfilePlan(built: BuiltPlan): Promise<void> {
  const configPath = destination(built.plan.root, CONFIG_PATH);
  const manifestPath = destination(built.plan.root, MANIFEST_PATH);
  const [config, manifest] = await Promise.all([
    readRegular(configPath),
    readRegular(manifestPath),
  ]);
  if (
    (built.expectedConfig && (!config || !config.equals(built.expectedConfig))) ||
    (!built.expectedConfig && config)
  )
    throw new AgentProfileError(
      "final_validation_failed",
      "Agent profile configuration does not match the planned state",
    );
  if (
    (built.expectedManifest && (!manifest || !manifest.equals(built.expectedManifest))) ||
    (!built.expectedManifest && manifest)
  )
    throw new AgentProfileError(
      "final_validation_failed",
      "Agent deployment manifest does not match the planned state",
    );
  if (config && (await inspectFileMode(configPath)) !== 0o600)
    throw new AgentProfileError(
      "final_validation_failed",
      "Agent profile configuration is not private",
    );
  if (manifest && (await inspectFileMode(manifestPath)) !== 0o600)
    throw new AgentProfileError(
      "final_validation_failed",
      "Agent deployment manifest is not private",
    );
  for (const [name, record] of Object.entries(built.manifest?.profiles ?? {})) {
    const target = destination(built.plan.root, `agents/${name}.md`);
    const content = await readRegular(target);
    const planned = built.plan.operations.find((item) => item.path === `agents/${name}.md`);
    const preservedDrift =
      built.plan.action === "uninstall" &&
      content &&
      planned?.operation === "conflict" &&
      planned.reason === "managed profile drift is preserved" &&
      planned.sha256 === sha256(content);
    if (
      !content ||
      (!preservedDrift &&
        (sha256(content) !== record.rendered_sha256 || (await inspectFileMode(target)) !== 0o600))
    )
      throw new AgentProfileError(
        "final_validation_failed",
        `Rendered agent does not match the planned manifest: ${name}`,
      );
  }
}

export async function listAgentProfiles(
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<AgentInventory> {
  const root = deploymentRoot(scope, cwd, home);
  const [state, canonical, files] = await Promise.all([
    loadState(scope, root),
    canonicalAssets(),
    listDirectRegular(destination(root, AGENTS_DIRECTORY)),
  ]);
  const byName = new Map(
    files.filter((item) => item.name.endsWith(".md")).map((item) => [item.name.slice(0, -3), item]),
  );
  const configured = desiredNames(state.config);
  const desired = Object.fromEntries(
    configured.map((name) => [name, renderAgentProfile(name, state.config, canonical)]),
  );
  const records: AgentProfileRecord[] = [];
  const collisions: string[] = [];
  const drift: string[] = [];
  for (const name of configured) {
    const file = byName.get(name);
    const owned = state.manifest?.profiles[name];
    let stateValue: AgentState;
    if (!owned && file) stateValue = "collision";
    else if (!file) stateValue = owned ? "drift" : "missing";
    else if (
      !owned ||
      sha256(file.content) !== owned.rendered_sha256 ||
      !file.content.equals(desired[name]) ||
      file.mode !== 0o600
    )
      stateValue = owned ? "drift" : "collision";
    else stateValue = "current";
    if (stateValue === "collision") collisions.push(name);
    if (stateValue === "drift") drift.push(name);
    const selection = selectionFor(state.config, name);
    records.push({
      name,
      ownership: NAME_PATTERN.test(name) ? "package-owned" : "managed",
      state: stateValue,
      ...("model" in selection
        ? { model: selection.model, ...(selection.variant ? { variant: selection.variant } : {}) }
        : {}),
      ...(file ? { rendered_sha256: sha256(file.content) } : {}),
    });
    byName.delete(name);
  }
  const userOwned = [...byName.keys()].sort();
  records.push(
    ...userOwned.map((name) => ({
      name,
      ownership: "user-owned" as const,
      state: "current" as const,
      rendered_sha256: sha256(byName.get(name)!.content),
    })),
  );
  const base = {
    schema_version: 1 as const,
    scope,
    root,
    package_version: packageVersion(),
    critic_pool:
      state.manifest?.critic_pool ??
      ["critic", ...Object.keys(state.config.additional_critics)].sort(),
    profiles: records.sort((left, right) => left.name.localeCompare(right.name)),
    user_owned: userOwned,
    collisions,
    drift,
    requires_restart: false as const,
  };
  return { ...base, digest: digest(base) };
}

export async function previewAgentProfileChange(
  request: AgentProfileRequest,
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<AgentProfilePlan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  return withLifecycleLock(stateRoot, async () => {
    if (await recoverTransaction(deploymentRoot(scope, cwd, home), stateRoot))
      throw new AgentProfileError(
        "recovered_transaction",
        "Recovered an interrupted transaction; request a fresh plan",
      );
    const built = await buildAgentProfilePlan(request, scope, cwd, home);
    const receipt = await saveReceipt(
      stateRoot,
      `agent:${request.action}`,
      scope,
      built.plan.root,
      { request, digest: built.plan.digest },
    );
    return { ...built.plan, digest: receipt.digest, receipt_expires_at: receipt.expires_at };
  });
}

export async function applyAgentProfileChange(
  request: AgentProfileRequest,
  scope: Scope,
  confirmationDigest: string,
  cwd = process.cwd(),
  home = homedir(),
  options: TransactionOptions = {},
): Promise<AgentProfileResult> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  return withLifecycleLock(stateRoot, async () => {
    if (await recoverTransaction(root, stateRoot))
      throw new AgentProfileError(
        "recovered_transaction",
        "Recovered an interrupted transaction; request a fresh plan",
      );
    const receipt = (await consumeReceipt(stateRoot, {
      digest: confirmationDigest,
      kind: `agent:${request.action}`,
      scope,
      root,
    })) as { request?: AgentProfileRequest; digest?: string };
    if (stable(receipt.request) !== stable(request))
      throw new AgentProfileError(
        "confirmation_unknown",
        "Saved confirmation belongs to a different request",
      );
    const built = await buildAgentProfilePlan(request, scope, cwd, home);
    if (built.plan.digest !== receipt.digest)
      throw new AgentProfileError("stale_plan", "Agent inventory changed after preview");
    if (
      built.plan.operations.some(
        (item) => item.operation === "conflict" && item.reason.includes("collision"),
      )
    )
      throw new AgentProfileError("collision", "Exact-name user-owned collision blocks apply");
    if (
      request.action !== "uninstall" &&
      request.action !== "reconcile" &&
      built.plan.operations.some((item) => item.operation === "conflict")
    )
      throw new AgentProfileError("drift", "Managed profile drift requires explicit reconcile");
    await applyTransaction(root, stateRoot, built.mutations, {
      ...options,
      validateFinal: async () => {
        await options.validateFinal?.();
        await validateBuiltAgentProfilePlan(built);
        const final = await listAgentProfiles(scope, cwd, home);
        if (
          request.action !== "uninstall" &&
          (final.collisions.length ||
            final.drift.length ||
            final.profiles
              .filter((item) => item.ownership !== "user-owned")
              .some((item) => item.state !== "current"))
        ) {
          throw new AgentProfileError(
            "final_validation_failed",
            "Final agent inventory validation failed",
          );
        }
      },
    });
    return {
      status: "ok",
      applied: true,
      requires_restart: built.plan.requires_restart,
      plan: { ...built.plan, digest: confirmationDigest },
    };
  });
}

export async function availableModels(): Promise<string[]> {
  try {
    const { stdout } = await execFileAsync("opencode", ["models"], {
      timeout: 10_000,
      encoding: "utf8",
    });
    const models = [
      ...new Set(
        stdout
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter((line) => MODEL_PATTERN.test(line)),
      ),
    ].sort();
    if (!models.length) throw new Error("empty catalog");
    return models;
  } catch (error) {
    throw new AgentProfileError(
      "catalog_unavailable",
      `Cached OpenCode model catalog is unavailable; provide an explicit provider/model: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export async function availableModelVariants(model: string): Promise<string[]> {
  const selected = validateModel(model);
  const provider = selected.split("/", 1)[0];
  try {
    const { stdout } = await execFileAsync("opencode", ["models", provider, "--verbose"], {
      timeout: 10_000,
      encoding: "utf8",
      maxBuffer: 10 * 1024 * 1024,
    });
    const lines = stdout.split(/\r?\n/);
    for (let index = 0; index < lines.length; index += 1) {
      if (lines[index].trim() !== selected) continue;
      let document = "";
      for (index += 1; index < lines.length; index += 1) {
        document += `${lines[index]}\n`;
        try {
          const metadata = JSON.parse(document) as { variants?: unknown };
          if (
            !metadata.variants ||
            typeof metadata.variants !== "object" ||
            Array.isArray(metadata.variants)
          )
            throw new Error("variants missing");
          const variants = Object.keys(metadata.variants);
          if (!variants.every((variant) => VARIANT_PATTERN.test(variant)))
            throw new Error("unsafe variant");
          return variants;
        } catch (error) {
          if (!(error instanceof SyntaxError)) throw error;
        }
      }
    }
    throw new Error("selected model is absent");
  } catch (error) {
    throw new AgentProfileError(
      "catalog_unavailable",
      `Cached OpenCode model variants are unavailable: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
}

export async function inspectFileMode(path: string): Promise<number | undefined> {
  try {
    return (await lstat(path)).mode & 0o777;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function readLegacyManifest(root: string): Promise<LegacyAgentOwnership | undefined> {
  const manifestPath = destination(root, ".skills-opencode-manifest.json");
  const raw = await readRegular(manifestPath);
  if (!raw) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(raw.toString("utf8"));
  } catch {
    return undefined;
  }
  const manifest = value as LegacyManifest;
  if (
    manifest?.schema_version !== 1 ||
    manifest.package !== PACKAGE_NAME ||
    typeof manifest.version !== "string" ||
    !manifest.files ||
    typeof manifest.files !== "object"
  )
    return undefined;
  return { manifest, manifestPath, manifestSha256: sha256(raw) };
}

export async function applyBuiltAgentPlan(
  built: BuiltPlan,
  stateRoot: string,
  options: TransactionOptions = {},
): Promise<void> {
  await applyTransaction(built.plan.root, stateRoot, built.mutations, options);
}

export type { BuiltPlan as InternalAgentProfilePlan, LegacyManifest as LegacyInstallerManifest };
