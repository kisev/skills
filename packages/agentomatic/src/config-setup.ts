import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { requirePackageVersion } from "./package-metadata.js";
import {
  applyTransaction,
  consumeReceipt,
  deploymentRoot,
  digest,
  LifecycleError,
  lifecycleRoot,
  readRegular,
  recoverTransaction,
  saveReceipt,
  sha256,
  withLifecycleLock,
  type FileMutation,
  type Scope,
  type SupersededPlan,
} from "./lifecycle.js";
import { applyJsoncEdits, parseJsonc, type JsoncEdit } from "./jsonc.js";

const PACKAGE_NAME = "@kisev/agentomatic";
const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const XDG_STATE_GLOB = "~/.local/state/agent-skills/**";
const OPENCODE_SKILLS_GLOB = "~/.config/opencode/skills/**";
const SECRET_PATHS = [
  "**/.env",
  "**/.env.*",
  "**/*.env",
  "**/.envrc",
  "**/.npmrc",
  "**/.netrc",
  "**/.pypirc",
  "**/.git-credentials",
  "**/.ssh/**",
  "**/id_rsa",
  "**/id_ed25519",
  "**/*.pem",
  "**/*.key",
  "**/*.p12",
  "**/*.pfx",
  "**/.kube/config",
  "**/kubeconfig*",
  "**/.aws/credentials",
  "**/.docker/config.json",
  "**/auth.json",
];

export class ConfigSetupError extends LifecycleError {}

export const CONFIG_TARGETS = ["opencode", "tui", "kilo", "mimo"] as const;
export type ConfigTargetName = (typeof CONFIG_TARGETS)[number];

export const CONFIG_FRAGMENTS = [
  {
    name: "core-plugin",
    description: "Register @kisev/agentomatic in the plugin array (OpenCode only)",
    targets: ["opencode"],
  },
  {
    name: "skills-state-permissions",
    description: "Allow the standard skills XDG state paths without per-run prompts",
    targets: ["opencode", "kilo", "mimo"],
  },
  {
    name: "lsp-preset",
    description: "Add LSP servers from the shared catalog (OpenCode only)",
    targets: ["opencode"],
  },
  {
    name: "secrets-guard",
    description: "Deny reads and edits of common secret files",
    targets: ["opencode", "kilo", "mimo"],
  },
  {
    name: "kilo-display",
    description: "Expand Kilo reasoning, terminal, edit, and tool blocks",
    targets: ["kilo"],
  },
  {
    name: "tui-schema",
    description: "Add the tui.json schema and stacked diffs",
    targets: ["tui"],
  },
] as const;
export type FragmentName = (typeof CONFIG_FRAGMENTS)[number]["name"];
const FRAGMENT_NAMES = CONFIG_FRAGMENTS.map((fragment) => fragment.name) as FragmentName[];

export type ConfigSetupSelection = {
  targets: ConfigTargetName[];
  fragments: FragmentName[];
};

export type ConfigSetupOperation = {
  target: ConfigTargetName;
  path: string;
  fragment: FragmentName | "file";
  operation: "create" | "update" | "unchanged" | "conflict";
  reason?: string;
};

export type ConfigSetupPlan = {
  schema_version: 1;
  action: "config-setup";
  scope: Scope;
  root: string;
  package_version: string;
  selection: ConfigSetupSelection;
  targets: Array<{ target: ConfigTargetName; path: string; exists: boolean }>;
  operations: ConfigSetupOperation[];
  skipped_fragments: Array<{ fragment: FragmentName; reason: string }>;
  plan_digest: string;
  digest: string;
  confirmation_digest?: string;
  receipt_expires_at?: string;
  superseded_plan?: SupersededPlan;
  requires_restart: boolean;
  confirmable: boolean;
};

type TargetFile = {
  target: ConfigTargetName;
  root: string;
  path: string;
  absolute: string;
  exists: boolean;
};

const LSP_SERVER_COMMANDS: Record<string, string[]> = {
  python: ["basedpyright-langserver", "--stdio"],
  typescript: ["typescript-language-server", "--stdio"],
  yaml: ["yaml-language-server", "--stdio"],
  shell: ["bash-language-server", "start"],
};

function lspCatalog(): Array<{ name: string; extensions: string[] }> {
  const raw = readFileSync(resolve(packageRoot, "dist", "assets", "lsp-catalog.json"), "utf8");
  const catalog = JSON.parse(raw) as {
    servers?: Array<{ name?: unknown; extensions?: unknown }>;
  };
  if (!Array.isArray(catalog.servers))
    throw new ConfigSetupError("invalid_package", "LSP catalog is unavailable");
  return catalog.servers
    .filter(
      (server): server is { name: string; extensions: string[] } =>
        typeof server.name === "string" &&
        Array.isArray(server.extensions) &&
        server.extensions.every((extension) => typeof extension === "string"),
    )
    .filter((server) => LSP_SERVER_COMMANDS[server.name]);
}

function mapAllowsAll(value: unknown): boolean {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>)["*"] === "allow",
  );
}

function permissionMapEdits(path: string[], entries: Record<string, string>): JsoncEdit[] {
  return [{ kind: "widen-scalar-map", path, entries }];
}

function fragmentEdits(
  fragment: FragmentName,
  target: ConfigTargetName,
  current: unknown,
): JsoncEdit[] {
  const value =
    current && typeof current === "object" && !Array.isArray(current)
      ? (current as Record<string, unknown>)
      : {};
  const permission =
    value.permission && typeof value.permission === "object" && !Array.isArray(value.permission)
      ? (value.permission as Record<string, unknown>)
      : {};
  if (fragment === "core-plugin") {
    return [
      { kind: "set-if-absent", path: ["$schema"], value: "https://opencode.ai/config.json" },
      { kind: "set-if-absent", path: ["plugin"], value: [] },
      { kind: "append-unique", path: ["plugin"], value: PACKAGE_NAME },
    ];
  }
  if (fragment === "skills-state-permissions") {
    const statePaths =
      target === "opencode" ? [XDG_STATE_GLOB, OPENCODE_SKILLS_GLOB] : [XDG_STATE_GLOB];
    const edits: JsoncEdit[] = [];
    if (!mapAllowsAll(permission.read))
      edits.push(
        ...permissionMapEdits(
          ["permission", "read"],
          Object.fromEntries(statePaths.map((glob) => [glob, "allow"])),
        ),
      );
    if (!mapAllowsAll(permission.edit))
      edits.push(...permissionMapEdits(["permission", "edit"], { [XDG_STATE_GLOB]: "allow" }));
    if (!mapAllowsAll(permission.external_directory))
      edits.push(
        ...permissionMapEdits(
          ["permission", "external_directory"],
          Object.fromEntries(statePaths.map((glob) => [glob, "allow"])),
        ),
      );
    return edits;
  }
  if (fragment === "lsp-preset") {
    return lspCatalog().map((server) => ({
      kind: "set-if-absent" as const,
      path: ["lsp", server.name],
      value: { command: LSP_SERVER_COMMANDS[server.name], extensions: server.extensions },
    }));
  }
  if (fragment === "secrets-guard") {
    const deny = Object.fromEntries(SECRET_PATHS.map((glob) => [glob, "deny"]));
    return [
      ...permissionMapEdits(["permission", "read"], {
        ...deny,
        "**/.env.example": "allow",
      }),
      ...permissionMapEdits(["permission", "edit"], deny),
    ];
  }
  if (fragment === "kilo-display") {
    return [
      { kind: "set-if-absent", path: ["reasoning_display"], value: "expanded" },
      { kind: "set-if-absent", path: ["terminal_command_display"], value: "expanded" },
      { kind: "set-if-absent", path: ["code_edit_display"], value: "expanded" },
      { kind: "set-if-absent", path: ["mcp_tool_display"], value: "expanded" },
    ];
  }
  return [
    { kind: "set-if-absent", path: ["$schema"], value: "https://opencode.ai/tui.json" },
    { kind: "set-if-absent", path: ["diff_style"], value: "stacked" },
  ];
}

function applicable(fragment: FragmentName, target: ConfigTargetName): boolean {
  const targets: readonly ConfigTargetName[] =
    CONFIG_FRAGMENTS.find((item) => item.name === fragment)?.targets ?? [];
  return targets.includes(target);
}

export function normalizeConfigSelection(
  scope: Scope,
  value: Partial<ConfigSetupSelection> = {},
): ConfigSetupSelection {
  const requestedTargets = value.targets ?? ["opencode"];
  const targets = CONFIG_TARGETS.filter((target) => requestedTargets.includes(target));
  if (targets.length !== requestedTargets.length)
    throw new ConfigSetupError("invalid_selection", "Unknown config target selection");
  if (scope === "project" && (targets.length !== 1 || targets[0] !== "opencode"))
    throw new ConfigSetupError(
      "invalid_selection",
      "Project scope supports only the opencode target",
    );
  const requestedFragments = value.fragments ?? [];
  const fragments = FRAGMENT_NAMES.filter((fragment) => requestedFragments.includes(fragment));
  if (fragments.length !== requestedFragments.length)
    throw new ConfigSetupError("invalid_selection", "Unknown config fragment selection");
  return { targets, fragments };
}

export async function defaultConfigSelection(
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<ConfigSetupSelection> {
  const exists = async (path: string): Promise<boolean> =>
    Boolean(await readRegular(path).catch(() => undefined));
  const targets: ConfigTargetName[] = ["opencode"];
  if (scope === "global") {
    if (await exists(join(home, ".config", "opencode", "tui.json"))) targets.push("tui");
    if (await exists(join(home, ".config", "kilo", "kilo.json"))) targets.push("kilo");
    if (await exists(join(home, ".config", "kilo", "kilo.jsonc"))) targets.push("kilo");
    if (await exists(join(home, ".config", "mimocode", "mimocode.json"))) targets.push("mimo");
    if (await exists(join(home, ".config", "mimocode", "mimocode.jsonc"))) targets.push("mimo");
  }
  return normalizeConfigSelection(scope, {
    targets: [...new Set(targets)],
    fragments: [...FRAGMENT_NAMES],
  });
}

async function resolveTargetFile(
  target: ConfigTargetName,
  scope: Scope,
  cwd: string,
  home: string,
): Promise<TargetFile> {
  const existing = async (root: string, path: string): Promise<boolean> =>
    Boolean(await readRegular(join(root, path)).catch(() => undefined));
  const globalRoot = deploymentRoot("global", cwd, home);
  if (target === "opencode") {
    if (scope === "global") {
      for (const path of ["opencode.json", "opencode.jsonc"])
        if (await existing(globalRoot, path))
          return { target, root: globalRoot, path, absolute: join(globalRoot, path), exists: true };
      return {
        target,
        root: globalRoot,
        path: "opencode.jsonc",
        absolute: join(globalRoot, "opencode.jsonc"),
        exists: false,
      };
    }
    const projectRoot = deploymentRoot("project", cwd, home);
    for (const [root, path] of [
      [cwd, "opencode.json"],
      [cwd, "opencode.jsonc"],
      [projectRoot, "opencode.json"],
      [projectRoot, "opencode.jsonc"],
    ] as const)
      if (await existing(root, path))
        return { target, root, path, absolute: join(root, path), exists: true };
    return {
      target,
      root: cwd,
      path: "opencode.jsonc",
      absolute: join(cwd, "opencode.jsonc"),
      exists: false,
    };
  }
  if (target === "tui")
    return {
      target,
      root: globalRoot,
      path: "tui.json",
      absolute: join(globalRoot, "tui.json"),
      exists: await existing(globalRoot, "tui.json"),
    };
  if (target === "kilo") {
    const root = join(home, ".config", "kilo");
    for (const path of ["kilo.jsonc", "kilo.json"])
      if (await existing(root, path))
        return { target, root, path, absolute: join(root, path), exists: true };
    return { target, root, path: "kilo.jsonc", absolute: join(root, "kilo.jsonc"), exists: false };
  }
  const root = join(home, ".config", "mimocode");
  for (const path of ["mimocode.jsonc", "mimocode.json"])
    if (await existing(root, path))
      return { target, root, path, absolute: join(root, path), exists: true };
  return {
    target,
    root,
    path: "mimocode.jsonc",
    absolute: join(root, "mimocode.jsonc"),
    exists: false,
  };
}

type BuiltPlan = { plan: ConfigSetupPlan; mutations: FileMutation[]; allowedRoots: string[] };

async function build(
  selection: ConfigSetupSelection,
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<BuiltPlan> {
  const root = deploymentRoot(scope, cwd, home);
  const operations: ConfigSetupOperation[] = [];
  const mutations: FileMutation[] = [];
  const allowedRoots = new Set<string>([root]);
  const files: TargetFile[] = [];

  for (const target of CONFIG_TARGETS.filter((name) => selection.targets.includes(name))) {
    let file: TargetFile;
    let current: Buffer | undefined;
    try {
      file = await resolveTargetFile(target, scope, cwd, home);
      current = file.exists ? await readRegular(file.absolute) : undefined;
    } catch (error) {
      const reason = error instanceof LifecycleError ? error.message : "target is unreadable";
      for (const fragment of selection.fragments.filter((item) => applicable(item, target)))
        operations.push({ target, path: "unknown", fragment, operation: "conflict", reason });
      continue;
    }
    if (file.exists && current === undefined) {
      for (const fragment of selection.fragments.filter((item) => applicable(item, target)))
        operations.push({
          target,
          path: file.absolute,
          fragment,
          operation: "conflict",
          reason: "target is unreadable",
        });
      continue;
    }
    files.push(file);
    allowedRoots.add(file.root);
    let text = current ? current.toString("utf8") : "{}\n";
    let changed = false;
    for (const fragment of selection.fragments) {
      if (!applicable(fragment, target)) continue;
      let parsed: unknown = undefined;
      try {
        parsed = parseJsonc(text);
      } catch {
        parsed = undefined;
      }
      try {
        const applied = applyJsoncEdits(text, fragmentEdits(fragment, target, parsed));
        if (applied.changed) {
          text = applied.text;
          changed = true;
          operations.push({
            target,
            path: file.absolute,
            fragment,
            operation: file.exists ? "update" : "create",
          });
        } else {
          operations.push({ target, path: file.absolute, fragment, operation: "unchanged" });
        }
      } catch (error) {
        operations.push({
          target,
          path: file.absolute,
          fragment,
          operation: "conflict",
          reason:
            error instanceof LifecycleError || error instanceof Error
              ? error.message
              : String(error),
        });
      }
    }
    if (changed) {
      const content = Buffer.from(text.endsWith("\n") ? text : `${text}\n`);
      mutations.push({
        ...(file.root === root ? {} : { root: file.root }),
        path: file.path,
        operation: "write",
        content,
        mode: 0o644,
        expected: current ? { sha256: sha256(current) } : { absent: true },
      });
    }
  }

  const skipped = selection.fragments
    .filter((fragment) => !selection.targets.some((target) => applicable(fragment, target)))
    .map((fragment) => ({ fragment, reason: "no selected target supports this fragment" }));
  const sorted = operations.sort(
    (left, right) =>
      CONFIG_TARGETS.indexOf(left.target) - CONFIG_TARGETS.indexOf(right.target) ||
      FRAGMENT_NAMES.indexOf(left.fragment as FragmentName) -
        FRAGMENT_NAMES.indexOf(right.fragment as FragmentName) ||
      left.path.localeCompare(right.path),
  );
  const base = {
    schema_version: 1 as const,
    action: "config-setup" as const,
    scope,
    root,
    package_version: requirePackageVersion(),
    selection,
    targets: files.map((file) => ({
      target: file.target,
      path: file.absolute,
      exists: file.exists,
    })),
    operations: sorted,
    skipped_fragments: skipped,
    requires_restart: sorted.some(
      (item) => item.operation === "create" || item.operation === "update",
    ),
    confirmable: mutations.length > 0,
  };
  const planDigest = digest(base);
  return {
    plan: { ...base, plan_digest: planDigest, digest: planDigest },
    mutations,
    allowedRoots: [...allowedRoots],
  };
}

export async function previewConfigSetup(
  selection: ConfigSetupSelection,
  scope: Scope,
  cwd = process.cwd(),
  home = homedir(),
): Promise<ConfigSetupPlan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      const built = await build(selection, scope, cwd, home);
      if (await recoverTransaction(root, stateRoot, built.allowedRoots))
        throw new ConfigSetupError(
          "recovered_transaction",
          "Recovered an interrupted transaction; request a fresh plan",
        );
      if (!built.plan.confirmable) return built.plan;
      const receipt = await saveReceipt(
        stateRoot,
        "config-setup",
        scope,
        root,
        { plan_digest: built.plan.plan_digest },
        Date.now(),
        built.plan.plan_digest,
      );
      return {
        ...built.plan,
        digest: receipt.digest,
        confirmation_digest: receipt.digest,
        receipt_expires_at: receipt.expires_at,
        ...(receipt.superseded_plan ? { superseded_plan: receipt.superseded_plan } : {}),
      };
    });
  } catch (error) {
    if (error instanceof ConfigSetupError) throw error;
    if (error instanceof LifecycleError) throw new ConfigSetupError(error.code, error.message);
    throw error;
  }
}

export async function applyConfigSetup(
  selection: ConfigSetupSelection,
  scope: Scope,
  confirmationDigest: string,
  cwd = process.cwd(),
  home = homedir(),
): Promise<ConfigSetupPlan> {
  const stateRoot = lifecycleRoot(scope, cwd, home);
  const root = deploymentRoot(scope, cwd, home);
  try {
    return await withLifecycleLock(stateRoot, async () => {
      const built = await build(selection, scope, cwd, home);
      if (await recoverTransaction(root, stateRoot, built.allowedRoots))
        throw new ConfigSetupError(
          "recovered_transaction",
          "Recovered an interrupted transaction; request a fresh plan",
        );
      const receipt = (await consumeReceipt(stateRoot, {
        digest: confirmationDigest,
        kind: "config-setup",
        scope,
        root,
      })) as { plan_digest?: string };
      if (built.plan.plan_digest !== (receipt.plan_digest ?? digest(receipt)))
        throw new ConfigSetupError("stale_plan", "Config setup plan changed after preview");
      if (!built.plan.confirmable)
        throw new ConfigSetupError("invalid_state", "Config setup plan has no applicable changes");
      await applyTransaction(root, stateRoot, built.mutations, {
        validateFinal: async () => {
          for (const mutation of built.mutations) {
            if (mutation.operation !== "write") continue;
            const target = join(mutation.root ?? root, mutation.path);
            const content = await readRegular(target);
            if (!content || !content.equals(mutation.content))
              throw new ConfigSetupError(
                "final_validation_failed",
                `Written config failed final validation: ${mutation.path}`,
              );
          }
        },
      });
      return { ...built.plan, digest: confirmationDigest };
    });
  } catch (error) {
    if (error instanceof ConfigSetupError) throw error;
    if (error instanceof LifecycleError) throw new ConfigSetupError(error.code, error.message);
    throw error;
  }
}
