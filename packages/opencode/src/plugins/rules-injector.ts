import { lstat, readFile, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, resolve } from "node:path";

const NAME = "AGENTS.md";
export type RulesInjectorOptions = { budget?: number; cwd?: string; enabled?: boolean };
type Rule = { path: string; revision: string; content: string };
type Session = { loaded: Map<string, Rule>; injected: Set<string>; used: number; replay: boolean };

function sessionID(value: unknown): string | undefined { const item = value as Record<string, unknown> | undefined; for (const key of ["sessionID", "sessionId", "session_id"]) if (typeof item?.[key] === "string" && item[key]) return item[key] as string; return undefined; }
function pathOf(input: unknown, output: unknown): string | undefined { for (const value of [input, output]) { const args = (value as { args?: Record<string, unknown> } | undefined)?.args; for (const key of ["filePath", "file_path", "path"]) if (typeof args?.[key] === "string") return args[key] as string; } return undefined; }
function output(value: unknown, text: string): void { const item = value as { output?: unknown } | undefined; if (typeof item?.output === "string") item.output = `${item.output}\n${text}`; }
function marker(rule: Rule): string { return `[rules-injector source=${rule.path} revision=${rule.revision}]`; }
function block(rule: Rule): string { return `${marker(rule)}\n${rule.content}\n[/rules-injector source=${rule.path}]`; }

export async function rulesInjector(options: RulesInjectorOptions = {}) {
  if (options.enabled === false) return {};
  const budget = options.budget ?? 12_000;
  const cwd = resolve(options.cwd ?? process.cwd());
  const global = resolve(process.env.XDG_CONFIG_HOME ?? resolve(homedir(), ".config"), "opencode");
  const sessions = new Map<string, Session>();
  const state = (identifier: string) => { let item = sessions.get(identifier); if (!item) { item = { loaded: new Map(), injected: new Set(), used: 0, replay: false }; sessions.set(identifier, item); } return item; };
  const inject = async (input: unknown, result: unknown) => {
    const call = input as Record<string, unknown> | undefined;
    if (call?.tool !== "read" && call?.tool !== "edit") return;
    const identifier = sessionID(input); const target = pathOf(input, result);
    if (!identifier || !target) return;
    try {
      const native = typeof call?.directory === "string" ? call.directory : cwd;
      const paths: string[] = [];
      let current = dirname(resolve(native, target));
      while (true) {
        const candidate = resolve(current, NAME);
        try { const info = await lstat(candidate); if (info.isFile() && candidate !== resolve(native, NAME) && candidate !== resolve(global, NAME)) paths.push(await realpath(candidate)); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
        const parent = dirname(current); if (parent === current) break; current = parent;
      }
      const currentState = state(identifier); const additions: string[] = [];
      for (const path of paths.reverse()) {
        if (currentState.injected.has(path)) continue;
        try {
          const info = await lstat(path); if (!info.isFile()) continue;
          const rule = { path, revision: `${Math.trunc(info.mtimeMs)}:${info.size}`, content: await readFile(path, "utf8") };
          const text = block(rule);
          if (currentState.used + text.length > budget) { additions.push(`[rules-injector warning] context budget exhausted; skipped ${path}`); continue; }
          currentState.loaded.set(path, rule); currentState.injected.add(path); currentState.used += text.length; additions.push(text);
        } catch (error) { additions.push(`[rules-injector warning] cannot read ${path}: ${String(error)}`); }
      }
      if (additions.length) output(result, additions.join("\n\n"));
    } catch (error) { output(result, `[rules-injector warning] cannot read AGENTS.md: ${String(error)}`); }
  };
  return { "tool.execute.after": inject, event: async ({ event }: { event?: { type?: string; properties?: Record<string, unknown> } }) => { if (event?.type?.includes("compaction")) { const identifier = sessionID(event.properties); if (identifier) state(identifier).replay = true; } }, "experimental.chat.system.transform": async (input: unknown, result: { system?: unknown[] }) => { const identifier = sessionID(input); if (!identifier || !state(identifier).replay || !Array.isArray(result.system)) return; for (const rule of state(identifier).loaded.values()) result.system.push(block(rule)); state(identifier).replay = false; } };
}

export default rulesInjector;
