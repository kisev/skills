import type { Plugin } from "@opencode/plugin";
import type { Result } from "@opencode/plugin/promise/tool";

export type ToolAfter = {
  tool: string;
  sessionID: string;
  input: unknown;
} & ({ status: "completed"; result: Result } | { status: "error"; error: unknown });

export function toolInput(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function resultText(result: Result): string | undefined {
  if (typeof result.content === "string") return result.content;
  if (Array.isArray(result.content))
    return result.content
      .filter((part) => part.type === "text")
      .map((part) => part.text)
      .join("\n");
  return undefined;
}

export function replaceResultText(result: Result, text: string): Result {
  if (!Array.isArray(result.content)) return { ...result, content: text };
  let replaced = false;
  return {
    ...result,
    content: result.content.flatMap((part) => {
      if (part.type !== "text") return [part];
      if (replaced) return [];
      replaced = true;
      return [{ type: "text" as const, text }];
    }),
  };
}

export function subscribeEvents(
  ctx: Plugin.Context,
  receive: (event: { type: string; data?: unknown }) => Promise<void>,
) {
  const controller = new AbortController();
  const subscription = (async () => {
    try {
      for await (const event of ctx.event.subscribe({ signal: controller.signal }))
        await receive(event);
    } catch (error) {
      if (!controller.signal.aborted) console.error("agentomatic event subscription failed", error);
    }
  })();
  return async () => {
    controller.abort();
    await subscription;
  };
}
