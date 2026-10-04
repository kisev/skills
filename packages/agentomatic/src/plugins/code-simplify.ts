import type { Plugin } from "@opencode/plugin";

export type CodeSimplifyLevel = "off" | "lite" | "full" | "ultra";
export const CODE_SIMPLIFY_ROLES = [
  "manager",
  "architect",
  "mapper",
  "worker",
  "review",
  "critic",
] as const;
export type CodeSimplifyRole = (typeof CODE_SIMPLIFY_ROLES)[number];
export type CodeSimplifyOptions = {
  level?: CodeSimplifyLevel;
  /** Agent roles that receive the injection; every role when absent. */
  scope?: readonly CodeSimplifyRole[];
};

const LADDER = `Prevention ladder for the code being written or changed, applied in order; stop at the first step that satisfies the agreed need: 1) necessity; 2) existing code; 3) standard library; 4) native platform; 5) installed dependency; 6) one line; 7) minimum. The ladder applies to the current change only; never scan repositories or unrelated files — a targeted caller search by exact name for code you are changing is not scanning. Fix the caller in the same change when that is the smaller diff. A conscious cut records a one-line SIMPLIFY marker (ceiling -> upgrade trigger) on the added or changed code in the same edit. Keep new verification proportionate: one runnable check for logic that is not evidently correct, none for a trivial one-liner. Never cancel a clarification or confirmation gate.`;
const AUDIT = `Complexity audit only on an explicit request, only in the requested scope, always report-only. Findings are ranked one-liners: exact location, one tag of delete/stdlib/native/reuse/yagni/shrink, and the concrete simpler alternative that preserves behavior. Collect SIMPLIFY debt markers in the scope into a separate registry section, never tagged findings: location, ceiling, trigger; mark a marker no-trigger when its upgrade trigger has not fired.`;
const GUARDS = `Search every usage, including dynamic references, before any delete finding. Never propose simplification that crosses a trust boundary, risks data loss, weakens security or accessibility, drops error handling that hides failures, or removes explicitly requested behavior.`;

function rules(level: Exclude<CodeSimplifyLevel, "off">): string {
  const parts =
    level === "lite" ? [LADDER] : level === "full" ? [LADDER, AUDIT] : [LADDER, AUDIT, GUARDS];
  return `[code-simplify level=${level}]\n${parts.join("\n\n")}\n[/code-simplify]`;
}

function roleOf(agent: string | undefined): CodeSimplifyRole | undefined {
  if (agent && (CODE_SIMPLIFY_ROLES as readonly string[]).includes(agent))
    return agent as CodeSimplifyRole;
  return agent?.startsWith("critic-") ? "critic" : undefined;
}

export function codeSimplify(options: CodeSimplifyOptions = {}) {
  const level = options.level ?? "full";
  if (level === "off") return {};
  if (options.scope?.some((role) => !CODE_SIMPLIFY_ROLES.includes(role)))
    throw new Error(`code-simplify scope must list roles from ${CODE_SIMPLIFY_ROLES.join(", ")}`);
  const scope = options.scope ? new Set<CodeSimplifyRole>(options.scope) : undefined;
  const text = rules(level);
  return {
    context: async (input: { agent?: string; system: Array<{ type: "text"; text: string }> }) => {
      if (scope) {
        const role = roleOf(input.agent);
        if (!role || !scope.has(role)) return;
      }
      if (input.system.some((part) => part.type === "text" && part.text === text)) return;
      input.system.push({ type: "text", text });
    },
  };
}

export default {
  id: "agentomatic.code-simplify",
  async setup(ctx) {
    const hooks = await codeSimplify(ctx.options);
    if (hooks.context) await ctx.session.hook("context", hooks.context);
  },
} satisfies Plugin.Plugin;
