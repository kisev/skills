import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { appendState, configRoot, stateRoot, readState, writeState } from "../runtime/state.js";

type Rule = { tool: string; operation: string; class?: "read" | "mutate" | "destructive" };
type Policy = { schema_version: 1; max_mutations_per_session: number; max_mutations_per_hour: number; on_exhausted: "ask_pause"; always_ask: Rule[]; classifications: Rule[] };
type State = { schema_version: 1; session_id: string; mutations: number; timestamps: number[]; paused: boolean };
export type AutonomyPolicyOptions = { enabled?: boolean; now?: () => number };

function match(pattern: string, value: string): boolean { return new RegExp(`^${pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")}$`).test(value); }
function rule(rules: Rule[], tool: string, operation: string): Rule | undefined { return [...rules].reverse().find((item) => match(item.tool, tool) && match(item.operation, operation)); }
function valid(value: unknown): value is Policy {
  const item = value as Policy;
  return Boolean(item && item.schema_version === 1 && item.on_exhausted === "ask_pause" && Number.isInteger(item.max_mutations_per_session) && Number.isInteger(item.max_mutations_per_hour) && Array.isArray(item.always_ask) && Array.isArray(item.classifications));
}

export async function autonomyPolicy({ directory, cwd }: { directory?: string; cwd?: string } = {}, options: AutonomyPolicyOptions = {}) {
  if (!options.enabled) return {};
  const project = resolve(directory ?? cwd ?? process.cwd());
  const root = stateRoot("autonomy-policy");
  const load = async (): Promise<Policy | undefined> => {
    let current = project;
    while (true) {
      try { const value = JSON.parse(await readFile(resolve(current, ".opencode", "autonomy-policy.json"), "utf8")); if (valid(value)) return value; return undefined; } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") return undefined; }
      const parent = dirname(current); if (parent === current) break; current = parent;
    }
    try { const value = JSON.parse(await readFile(resolve(configRoot("autonomy-policy"), "autonomy-policy.json"), "utf8")); return valid(value) ? value : undefined; } catch { return undefined; }
  };
  const inspect = async (input: { permission: string; sessionID: string; patterns?: string[]; metadata?: Record<string, unknown>; tool?: string }, output: { status: "ask" | "deny" | "allow" }) => {
    const policy = await load();
    const tool = input.tool ?? input.permission;
    const operation = typeof input.metadata?.operation === "string" ? input.metadata.operation : input.patterns?.[0] ?? input.permission;
    const classification = policy && rule(policy.classifications, tool, operation);
    if (!policy || !classification || classification.class === "destructive" || rule(policy.always_ask, tool, operation)) { output.status = "ask"; return; }
    if (classification.class === "read" || output.status === "deny") return;
    const path = resolve(root, `${encodeURIComponent(input.sessionID)}.json`);
    const previous = await readState<State>(path, root);
    const state = previous && previous.schema_version === 1 ? previous : { schema_version: 1 as const, session_id: input.sessionID, mutations: 0, timestamps: [], paused: false };
    const current = options.now?.() ?? Date.now();
    state.timestamps = state.timestamps.filter((value) => value > current - 3_600_000);
    if ((policy.max_mutations_per_session > 0 && state.mutations >= policy.max_mutations_per_session) || (policy.max_mutations_per_hour > 0 && state.timestamps.length >= policy.max_mutations_per_hour)) {
      state.paused = true;
      await writeState(path, root, state);
      await appendState(resolve(root, "receipts.jsonl"), root, { schema_version: 1, session_id: input.sessionID, tool, class: "mutate", decision: "ask", reason: "budget-exhausted", at: new Date().toISOString() });
      output.status = "ask";
      return;
    }
    state.mutations += 1;
    state.timestamps.push(current);
    await writeState(path, root, state);
    await appendState(resolve(root, "receipts.jsonl"), root, { schema_version: 1, session_id: input.sessionID, tool, class: "mutate", decision: "passed", reason: "budget-available", at: new Date().toISOString() });
  };
  return { "permission.ask": inspect };
}

export default autonomyPolicy;
