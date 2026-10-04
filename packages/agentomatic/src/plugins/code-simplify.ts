import type { Plugin } from "@opencode/plugin";

export type CodeSimplifyLevel = "off" | "lite" | "full" | "ultra";
export type CodeSimplifyOptions = { level?: CodeSimplifyLevel };

const LADDER = `Prevention ladder for the code being written or changed, applied in order; stop at the first step that satisfies the agreed need: 1) necessity; 2) existing code; 3) standard library; 4) native platform; 5) installed dependency; 6) one line; 7) minimum. The ladder applies to the current change only; never scan repositories or unrelated files.`;
const AUDIT = `Complexity audit only on an explicit request, only in the requested scope, always report-only. Findings are ranked one-liners: exact location, one tag of delete/stdlib/native/reuse/yagni/shrink, and the concrete simpler alternative that preserves behavior.`;
const GUARDS = `Search every usage, including dynamic references, before any delete finding. Never propose simplification that crosses a trust boundary, risks data loss, weakens security or accessibility, drops error handling that hides failures, or removes explicitly requested behavior.`;

function rules(level: Exclude<CodeSimplifyLevel, "off">): string {
  const parts =
    level === "lite" ? [LADDER] : level === "full" ? [LADDER, AUDIT] : [LADDER, AUDIT, GUARDS];
  return `[code-simplify level=${level}]\n${parts.join("\n\n")}\n[/code-simplify]`;
}

export function codeSimplify(options: CodeSimplifyOptions = {}) {
  const level = options.level ?? "full";
  if (level === "off") return {};
  const text = rules(level);
  return {
    context: async (input: { system: Array<{ type: "text"; text: string }> }) => {
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
