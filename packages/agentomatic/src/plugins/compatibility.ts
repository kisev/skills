import type { Plugin } from "@opencode/plugin";
import type { Result } from "@opencode/plugin/promise/tool";

type Input = { tool: string; sessionID: string; args: Record<string, unknown>; directory?: string };
type Hooks = {
  "tool.execute.before"?: (input: Input, output: { args: unknown }) => Promise<void>;
  "tool.execute.after"?: (input: Input, output: { output: string }) => Promise<void>;
  event?: (input: {
    event: { type: string; properties?: Record<string, unknown> };
  }) => Promise<void>;
  "experimental.chat.system.transform"?: (
    input: { sessionID: string },
    output: { system: string[] },
  ) => Promise<void>;
};

function toolName(name: string): string {
  return name === "shell" ? "bash" : name === "subagent" ? "task" : name;
}

function args(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(result: Result): string | undefined {
  if (typeof result.content === "string") return result.content;
  if (Array.isArray(result.content))
    return result.content
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("\n");
  return undefined;
}

function replaceText(result: Result, output: string): Result {
  if (!Array.isArray(result.content)) return { ...result, content: output };
  let replaced = false;
  return {
    ...result,
    content: result.content.flatMap((part) => {
      if (part.type !== "text") return [part];
      if (replaced) return [];
      replaced = true;
      return [{ type: "text" as const, text: output }];
    }),
  };
}

export async function registerV2Hooks(
  ctx: Plugin.Context,
  hooks: Hooks,
  options: { sessionDirectory?: boolean } = {},
) {
  if (hooks["tool.execute.before"])
    await ctx.tool.hook("execute.before", async (event) => {
      const output = { args: event.input };
      await hooks["tool.execute.before"]!(
        { ...event, tool: toolName(event.tool), args: args(event.input) },
        output,
      );
      event.input = output.args;
    });
  if (hooks["tool.execute.after"])
    await ctx.tool.hook("execute.after", async (event) => {
      if (event.status !== "completed") return;
      const original = text(event.result);
      if (original === undefined) return;
      const output = { output: original };
      let directory: string = ctx.location.directory;
      if (options.sessionDirectory && (event.tool === "read" || event.tool === "edit")) {
        const session = await ctx.session
          .get({ sessionID: event.sessionID })
          .catch(() => undefined);
        if (!session) return;
        directory = session.location.directory;
      }
      await hooks["tool.execute.after"]!(
        { ...event, tool: toolName(event.tool), args: args(event.input), directory },
        output,
      );
      if (output.output !== original) event.result = replaceText(event.result, output.output);
    });
  if (hooks["experimental.chat.system.transform"])
    await ctx.session.hook("context", async (event) => {
      const output = { system: [] as string[] };
      await hooks["experimental.chat.system.transform"]!({ sessionID: event.sessionID }, output);
      event.system.push(...output.system.map((text) => ({ type: "text" as const, text })));
    });
  if (!hooks.event) return;
  const controller = new AbortController();
  const subscription = (async () => {
    try {
      for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
        await hooks.event!({ event: { type: event.type, properties: args(event.data) } });
      }
    } catch (error) {
      if (!controller.signal.aborted) console.error("agentomatic event subscription failed", error);
    }
  })();
  return async () => {
    controller.abort();
    await subscription;
  };
}
