import { JsoncError, type JsoncEdit } from "./jsonc.js";

export type PermissionRule = { action: string; resource: string; effect: "allow" | "ask" | "deny" };
const effects = new Set(["allow", "ask", "deny"]);
const aliases: Record<string, string> = {
  bash: "shell",
  task: "subagent",
  write: "edit",
  patch: "edit",
};

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function legacyPermissions(value: unknown): PermissionRule[] {
  if (typeof value === "string" && effects.has(value))
    return [{ action: "*", resource: "*", effect: value as PermissionRule["effect"] }];
  if (!object(value))
    throw new JsoncError("conflict", "Legacy permission must be an effect or a tool map");
  return Object.entries(value).flatMap(([name, entry]) => {
    if (name === "lsp" || name === "doom_loop")
      throw new JsoncError("conflict", `Permission action has no V2 equivalent: ${name}`);
    const action = aliases[name] ?? name;
    const resources = typeof entry === "string" ? { "*": entry } : entry;
    if (!object(resources)) throw new JsoncError("conflict", `Invalid permission map: ${name}`);
    return Object.entries(resources).map(([resource, effect]) => {
      if (typeof effect !== "string" || !effects.has(effect))
        throw new JsoncError("conflict", `Invalid permission effect: ${name}`);
      return { action, resource, effect: effect as PermissionRule["effect"] };
    });
  });
}

export function permissionEdits(
  config: Record<string, unknown>,
  additions: PermissionRule[],
): JsoncEdit[] {
  const edits: JsoncEdit[] = [];
  let rules: PermissionRule[] = [];
  if ("permissions" in config) {
    if (
      !Array.isArray(config.permissions) ||
      !config.permissions.every(
        (rule) =>
          object(rule) &&
          typeof rule.action === "string" &&
          typeof rule.resource === "string" &&
          typeof rule.effect === "string" &&
          effects.has(rule.effect),
      )
    )
      throw new JsoncError(
        "conflict",
        "V2 permissions must be an ordered array of action/resource/effect rules",
      );
    rules = config.permissions as PermissionRule[];
  }
  let tools: PermissionRule[] = [];
  if ("tools" in config) {
    if (
      !object(config.tools) ||
      !Object.values(config.tools).every((value) => typeof value === "boolean")
    )
      throw new JsoncError("conflict", "Legacy tools must be a boolean map");
    tools = Object.entries(config.tools).map(([name, enabled]) => ({
      action: aliases[name] ?? name,
      resource: "*",
      effect: enabled ? "allow" : "deny",
    }));
  }
  const legacyKeys = ["tools", "permission"].filter((key) => key in config);
  if (legacyKeys.length) {
    // V2 normalizes tools first, legacy permission next, and native rules last.
    rules = [
      ...tools,
      ...("permission" in config ? legacyPermissions(config.permission) : []),
      ...rules,
    ];
    const renamed = "permissions" in config ? undefined : legacyKeys[0];
    for (const key of legacyKeys)
      edits.push(
        key === renamed
          ? { kind: "rename-key", path: [key], to: "permissions" }
          : { kind: "remove-key", path: [key] },
      );
    edits.push({ kind: "set-value", path: ["permissions"], value: rules });
  } else if (!("permissions" in config))
    edits.push({ kind: "set-if-absent", path: ["permissions"], value: [] });
  for (const rule of additions) {
    const exact = rules.reduce(
      (last, existing, index) =>
        existing.action === rule.action && existing.resource === rule.resource ? index : last,
      -1,
    );
    if (exact >= 0) {
      if (
        rules[exact].effect !== rule.effect ||
        rules
          .slice(exact + 1)
          .some(
            (later) =>
              matchesWildcard(later.action, rule.action) &&
              matchesWildcard(later.resource, rule.resource) &&
              later.effect !== rule.effect,
          )
      )
        throw new JsoncError(
          "conflict",
          `Existing permission conflicts with preset: ${rule.action} ${rule.resource}`,
        );
      continue;
    }
    edits.push({ kind: "append-unique", path: ["permissions"], value: rule });
    rules = [...rules, rule];
  }
  return edits;
}

export function matchesWildcard(pattern: string, value: string): boolean {
  return new RegExp(
    `^${pattern
      .replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      .replace(/\\\*/g, ".*")
      .replace(/\\\?/g, ".")}$`,
  ).test(value);
}

function plugins(value: unknown, legacy: boolean): unknown[] {
  if (!Array.isArray(value))
    throw new JsoncError("conflict", "Plugin configuration must be an array");
  return value.map((entry) => {
    if (typeof entry === "string")
      return entry === "@kisev/skills-opencode" ? "@kisev/agentomatic" : entry;
    if (
      legacy &&
      Array.isArray(entry) &&
      entry.length === 2 &&
      typeof entry[0] === "string" &&
      object(entry[1])
    )
      return {
        package: entry[0] === "@kisev/skills-opencode" ? "@kisev/agentomatic" : entry[0],
        options: entry[1],
      };
    if (object(entry) && typeof entry.package === "string")
      return {
        ...entry,
        package: entry.package === "@kisev/skills-opencode" ? "@kisev/agentomatic" : entry.package,
      };
    throw new JsoncError(
      "conflict",
      "Invalid plugin entry; use a package string or V2 package/options object",
    );
  });
}

export function corePluginEdits(config: Record<string, unknown>): JsoncEdit[] {
  const edits: JsoncEdit[] = [
    { kind: "set-if-absent", path: ["$schema"], value: "https://opencode.ai/config.json" },
  ];
  const native = "plugins" in config ? plugins(config.plugins, false) : undefined;
  const legacy = "plugin" in config ? plugins(config.plugin, true) : undefined;
  if (native && legacy) {
    if (JSON.stringify(native) !== JSON.stringify(legacy))
      throw new JsoncError(
        "conflict",
        "Conflicting plugin and plugins sections; migrate explicitly before config setup",
      );
    edits.push({ kind: "remove-key", path: ["plugin"] });
  } else if (legacy) edits.push({ kind: "rename-key", path: ["plugin"], to: "plugins" });
  const entries = native ?? legacy ?? [];
  if (
    !entries.some(
      (entry) =>
        entry === "@kisev/agentomatic" || (object(entry) && entry.package === "@kisev/agentomatic"),
    )
  )
    entries.push("@kisev/agentomatic");
  edits.push({ kind: "set-value", path: ["plugins"], value: entries });
  return edits;
}
