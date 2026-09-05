import { join } from "node:path";
import { listState, readState, stateRoot, writeState } from "../runtime/state.js";

type Goal = { schema_version: 1; goal_id: string; session_id: string; status: "running" | "paused" | "complete" | "blocked"; revision: number; limits: { turn_cap: number; token_budget: number }; usage: { turns: number; tokens: number }; receipts: Array<Record<string, unknown>>; updated_at: string };
type Client = { session: { messages: (input: { path: { id: string } }) => Promise<unknown>; prompt: (input: { path: { id: string }; body: Record<string, unknown> }) => Promise<unknown> } };
export type GoalLoopOptions = { enabled?: boolean; quietWindowMs?: number; now?: () => number };

function sessionID(event: { properties?: Record<string, unknown> }): string | undefined {
  const value = event.properties?.sessionID ?? event.properties?.session_id;
  return typeof value === "string" && value ? value : undefined;
}
function tokens(messages: unknown): number {
  const entries = Array.isArray(messages) ? messages : (messages as { data?: unknown[] } | undefined)?.data;
  if (!Array.isArray(entries)) return 0;
  const last = [...entries].reverse().find((entry) => ((entry as { info?: { role?: string } })?.info?.role === "assistant")) as { info?: { tokens?: { total?: number; output?: number } } } | undefined;
  const value = last?.info?.tokens?.total ?? last?.info?.tokens?.output;
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
}

export async function goalLoop({ client }: { client: Client }, options: GoalLoopOptions = {}) {
  if (!options.enabled) return {};
  const root = stateRoot("goal");
  const timers = new Map<string, ReturnType<typeof setTimeout>>();
  const lookup = async (session: string) => {
    for (const name of await listState(root)) {
      const state = await readState<Goal>(join(root, name), root);
      if (state?.schema_version === 1 && state.session_id === session) return { state, path: join(root, name) };
    }
    return undefined;
  };
  const settle = async (session: string, status: Goal["status"], note: string) => {
    const item = await lookup(session);
    if (!item || item.state.status !== "running") return;
    item.state.status = status;
    item.state.revision += 1;
    item.state.updated_at = new Date().toISOString();
    item.state.receipts.push({ revision: item.state.revision, status, note, at: item.state.updated_at });
    await writeState(item.path, root, item.state);
  };
  const run = async (session: string) => {
    timers.delete(session);
    const item = await lookup(session);
    if (!item || item.state.status !== "running") return;
    try {
      const used = tokens(await client.session.messages({ path: { id: session } }));
      item.state.usage.turns += 1;
      item.state.usage.tokens += used;
      item.state.revision += 1;
      item.state.updated_at = new Date().toISOString();
      item.state.receipts.push({ revision: item.state.revision, status: "running", note: "turn audited", at: item.state.updated_at });
      await writeState(item.path, root, item.state);
      if (item.state.usage.turns >= item.state.limits.turn_cap) return settle(session, "blocked", "turn cap reached");
      if (item.state.limits.token_budget > 0 && item.state.usage.tokens >= item.state.limits.token_budget) return settle(session, "blocked", "token budget reached");
      await client.session.prompt({ path: { id: session }, body: { parts: [{ type: "text", text: "Continue the current goal within its declared constraints and boundaries." }] } });
    } catch (error) {
      await settle(session, "blocked", String(error));
    }
  };
  const schedule = (session: string) => {
    const previous = timers.get(session);
    if (previous) clearTimeout(previous);
    timers.set(session, setTimeout(() => void run(session), options.quietWindowMs ?? 250));
  };
  return { event: async ({ event }: { event: { type?: string; properties?: Record<string, unknown> } }) => {
    const session = sessionID(event);
    if (!session) return;
    if (event.type === "session.abort" || event.type === "session.aborted") {
      const timer = timers.get(session);
      if (timer) clearTimeout(timer);
      timers.delete(session);
      await settle(session, "paused", "user abort");
    } else if (event.type === "session.error") await settle(session, "blocked", "session error");
    else if (event.type === "session.idle") schedule(session);
  } };
}

export default goalLoop;
