import { JsoncError, type JsoncEdit } from "./jsonc.js";
import { requirePackageVersion } from "./package-metadata.js";

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
  // Rules that existed before this preset run. V2 resolves by the last
  // matching rule, so a new allow that can overlap a pre-existing deny is
  // inserted before that deny instead of being appended after it: the user's
  // prohibition keeps priority for every resource it matches. An allow that
  // overlaps a deny added earlier in the same batch is a deliberate exception
  // to that deny (the OpenCode "specific rule follows the broad rule" order)
  // and is appended, and denies are always appended because a later deny can
  // only strengthen the result. Batch membership is tracked by object
  // identity: insertions shift array positions, so a length boundary would
  // misclassify shifted pre-existing rules as batch additions.
  const preexisting = rules;
  const batchRules = new Set<PermissionRule>();
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
    const overlapsDeny = (candidate: PermissionRule): boolean =>
      candidate.effect === "deny" && rulesOverlap(candidate, rule);
    const anchor =
      rule.effect === "allow" && ![...batchRules].some((added) => overlapsDeny(added))
        ? preexisting.find((existing) => overlapsDeny(existing))
        : undefined;
    if (anchor !== undefined) {
      edits.push({ kind: "insert-before", path: ["permissions"], before: anchor, value: rule });
      const position = rules.indexOf(anchor);
      rules = [...rules.slice(0, position), rule, ...rules.slice(position)];
    } else {
      edits.push({ kind: "append-unique", path: ["permissions"], value: rule });
      rules = [...rules, rule];
    }
    batchRules.add(rule);
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

// Decides whether two whole-value wildcard patterns (V2 semantics: `*` matches
// zero or more characters including `/`, `?` exactly one) can match at least
// one common resource. Ordered rules resolve by the last match, so an allow
// overlapping a deny must be placed before it to preserve the deny.
type PatternUnit = { kind: "star" } | { kind: "any" } | { kind: "char"; char: string };

function patternUnits(pattern: string): PatternUnit[] {
  return [...pattern].map((character): PatternUnit =>
    character === "*"
      ? { kind: "star" }
      : character === "?"
        ? { kind: "any" }
        : { kind: "char", char: character },
  );
}

export function patternsOverlap(left: string, right: string): boolean {
  const a = patternUnits(left);
  const b = patternUnits(right);
  const memo = new Map<string, boolean>();
  const overlap = (i: number, j: number): boolean => {
    if (i === a.length && j === b.length) return true;
    // A trailing wildcard run can still match the empty string, so exhaustion
    // is compatible only with an all-star remainder on the other side.
    if (i === a.length) return b.slice(j).every((unit) => unit.kind === "star");
    if (j === b.length) return a.slice(i).every((unit) => unit.kind === "star");
    const key = `${i}:${j}`;
    const cached = memo.get(key);
    if (cached !== undefined) return cached;
    const unit = a[i] as PatternUnit;
    const other = b[j] as PatternUnit;
    let result: boolean;
    if (unit.kind === "star" || other.kind === "star")
      // A star consumes nothing from the other pattern or absorbs one unit of it.
      result = overlap(i + 1, j) || overlap(i, j + 1);
    else if (unit.kind === "any" || other.kind === "any") result = overlap(i + 1, j + 1);
    else result = unit.char === other.char && overlap(i + 1, j + 1);
    memo.set(key, result);
    return result;
  };
  return overlap(0, 0);
}

function rulesOverlap(existing: PermissionRule, candidate: PermissionRule): boolean {
  return (
    patternsOverlap(existing.action, candidate.action) &&
    patternsOverlap(existing.resource, candidate.resource)
  );
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

const OUR_PACKAGE = /^@kisev\/(?:agentomatic|skills-opencode)(?:@|$)/;

function ourEntry(entry: unknown): boolean {
  if (typeof entry === "string") return OUR_PACKAGE.test(entry);
  return object(entry) && typeof entry.package === "string" && OUR_PACKAGE.test(entry.package);
}

export function corePluginRemovalEdits(config: Record<string, unknown>): JsoncEdit[] {
  return ["plugin", "plugins"].flatMap((key): JsoncEdit[] => {
    if (!(key in config)) return [];
    plugins(config[key], key === "plugin");
    const entries = config[key] as unknown[];
    const remaining = entries.filter((entry) => !ourEntry(Array.isArray(entry) ? entry[0] : entry));
    return remaining.length === entries.length
      ? []
      : [{ kind: "set-value", path: [key], value: remaining }];
  });
}

export function corePluginEdits(config: Record<string, unknown>): JsoncEdit[] {
  const edits: JsoncEdit[] = [
    { kind: "set-if-absent", path: ["$schema"], value: "https://opencode.ai/config.json" },
  ];
  // V2 resolves a bare package name through the registry "latest" dist-tag, which
  // can differ from the installed build; pin the exact running version instead.
  const pinned = `@kisev/agentomatic@${requirePackageVersion()}`;
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
  const normalized: unknown[] = [];
  let pinnedPresent = false;
  for (const entry of native ?? legacy ?? []) {
    if (!ourEntry(entry)) {
      normalized.push(entry);
      continue;
    }
    if (pinnedPresent) continue;
    normalized.push(object(entry) ? { ...entry, package: pinned } : pinned);
    pinnedPresent = true;
  }
  const entries = normalized;
  if (!pinnedPresent) entries.push(pinned);
  edits.push({ kind: "set-value", path: ["plugins"], value: entries });
  return edits;
}
