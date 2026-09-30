import type { Plugin } from "@opencode/plugin";
import {
  resultText,
  replaceResultText,
  subscribeEvents,
  toolInput,
  type ToolAfter,
} from "./events.js";
import { lstat, readFile, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";

const NAME = "AGENTS.md";
export type RulesInjectorOptions = { budget?: number; cwd?: string; enabled?: boolean };
type Rule = { path: string; revision: string; content: string };
type Session = { loaded: Map<string, Rule>; injected: Set<string>; used: number; replay: boolean };

function sessionID(value: unknown): string | undefined {
  const item = value as Record<string, unknown> | undefined;
  for (const key of ["sessionID", "sessionId", "session_id"])
    if (typeof item?.[key] === "string" && item[key]) return item[key] as string;
  return undefined;
}
function marker(rule: Rule): string {
  return `[rules-injector source=${rule.path} revision=${rule.revision}]`;
}
function block(rule: Rule): string {
  return `${marker(rule)}\n${rule.content}\n[/rules-injector source=${rule.path}]`;
}

export async function rulesInjector(options: RulesInjectorOptions = {}) {
  if (options.enabled === false) return {};
  const budget = options.budget ?? 12_000;
  const cwd = resolve(options.cwd ?? process.cwd());
  const global = resolve(process.env.XDG_CONFIG_HOME ?? resolve(homedir(), ".config"), "opencode");
  const sessions = new Map<string, Session>();
  const state = (identifier: string) => {
    let item = sessions.get(identifier);
    if (!item) {
      item = { loaded: new Map(), injected: new Set(), used: 0, replay: false };
      sessions.set(identifier, item);
    }
    return item;
  };
  const inject = async (input: ToolAfter & { directory?: string }) => {
    if (input.status !== "completed" || (input.tool !== "read" && input.tool !== "edit")) return;
    const identifier = input.sessionID;
    const target = toolInput(input.input).path;
    const original = resultText(input.result);
    if (!identifier || typeof target !== "string" || original === undefined) return;
    const output = (text: string) => {
      input.result = replaceResultText(input.result, `${original}\n${text}`);
    };
    try {
      const native = input.directory ?? cwd;
      const paths: string[] = [];
      let current = dirname(resolve(native, target));
      while (true) {
        const candidate = resolve(current, NAME);
        try {
          const info = await lstat(candidate);
          if (
            info.isFile() &&
            candidate !== resolve(native, NAME) &&
            candidate !== resolve(global, NAME)
          )
            paths.push(await realpath(candidate));
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        }
        const parent = dirname(current);
        if (parent === current) break;
        current = parent;
      }
      const currentState = state(identifier);
      const additions: string[] = [];
      for (const path of paths.reverse()) {
        if (currentState.injected.has(path)) continue;
        try {
          const info = await lstat(path);
          if (!info.isFile()) continue;
          const rule = {
            path,
            revision: `${Math.trunc(info.mtimeMs)}:${info.size}`,
            content: await readFile(path, "utf8"),
          };
          const text = block(rule);
          if (currentState.used + text.length > budget) {
            additions.push(`[rules-injector warning] context budget exhausted; skipped ${path}`);
            continue;
          }
          currentState.loaded.set(path, rule);
          currentState.injected.add(path);
          currentState.used += text.length;
          additions.push(text);
        } catch (error) {
          additions.push(`[rules-injector warning] cannot read ${path}: ${String(error)}`);
        }
      }
      if (additions.length) output(additions.join("\n\n"));
    } catch (error) {
      output(`[rules-injector warning] cannot read AGENTS.md: ${String(error)}`);
    }
  };
  return {
    "execute.after": inject,
    event: async (event: { type: string; data?: unknown }) => {
      if (event.type === "session.compacted" || event.type.includes("compaction")) {
        const identifier = sessionID(event.data);
        if (identifier) state(identifier).replay = true;
      }
    },
    context: async (input: {
      sessionID: string;
      system: Array<{ type: "text"; text: string }>;
    }) => {
      const identifier = sessionID(input);
      if (!identifier || !state(identifier).replay) return;
      for (const rule of state(identifier).loaded.values())
        input.system.push({ type: "text", text: block(rule) });
      state(identifier).replay = false;
    },
  };
}

export default {
  id: "agentomatic.rules-injector",
  async setup(ctx) {
    const hooks = await rulesInjector({ ...ctx.options, cwd: ctx.location.directory });
    if (hooks["execute.after"])
      await ctx.tool.hook("execute.after", async (event) => {
        if (event.status !== "completed" || (event.tool !== "read" && event.tool !== "edit"))
          return;
        const session = await ctx.session
          .get({ sessionID: event.sessionID })
          .catch(() => undefined);
        if (session) {
          const scoped = { ...event, directory: session.location.directory };
          await hooks["execute.after"]!(scoped);
          event.result = scoped.result;
        }
      });
    if (hooks.context) await ctx.session.hook("context", hooks.context);
    if (hooks.event) return subscribeEvents(ctx, hooks.event);
  },
} satisfies Plugin.Plugin;
