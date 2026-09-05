import { randomUUID } from "node:crypto";
import { join, resolve } from "node:path";
import { tool } from "@opencode-ai/plugin";
import { appendState, listState, readState, stateRoot, writeState } from "../runtime/state.js";

const TERMINAL = new Set(["completed", "failed", "cancelled", "orphaned"]);
const LIMIT = 2;
type Status = "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled" | "orphaned";
type Attempt = { schema_version: 1; attempt_id: string; parent_session_id: string; project: string; directory: string; task: string; category: string; agent: string; routing_decision_digest: string; status: Status; revision: number; priority: number; read_only: boolean; created_at: string; receipts: Array<Record<string, unknown>>; parent_attempt_id?: string; retry_number: number; child_session_id?: string; workspace_id?: string; result?: { summary: string; evidence: string[] }; error?: { message: string; retryable: boolean } };
type Client = { session: { create?: (input: { query?: Record<string, unknown>; body: Record<string, unknown> }) => Promise<unknown>; prompt: (input: { path: { id: string }; body: Record<string, unknown> }) => Promise<unknown>; abort?: (input: { path: { id: string } }) => Promise<unknown> } };
export type BackgroundAttemptsOptions = { enabled?: boolean; concurrency?: number; parentConcurrency?: number };

function id(value: unknown): string | undefined {
  const item = ((value as { data?: unknown })?.data ?? value) as Record<string, unknown> | undefined;
  return typeof item?.id === "string" && item.id ? item.id : undefined;
}

export async function backgroundAttempts({ client, directory, cwd }: { client: Client; directory?: string; cwd?: string }, options: BackgroundAttemptsOptions = {}) {
  if (!options.enabled) return {};
  const project = resolve(directory ?? cwd ?? process.cwd());
  const root = stateRoot("attempt");
  const attemptsRoot = join(root, "attempts");
  const load = async (attemptID: string) => readState<Attempt>(join(attemptsRoot, `${attemptID}.json`), root);
  const all = async () => (await Promise.all((await listState(attemptsRoot)).map((name) => load(name.slice(0, -5))))).filter((item): item is Attempt => Boolean(item));
  const save = async (item: Attempt, event: string) => {
    item.receipts.push({ at: new Date().toISOString(), event, status: item.status, revision: item.revision });
    await writeState(join(attemptsRoot, `${item.attempt_id}.json`), root, item);
    await appendState(join(root, "receipts.jsonl"), root, { attempt_id: item.attempt_id, event, status: item.status, revision: item.revision, at: new Date().toISOString() });
  };
  const transition = async (item: Attempt, status: Status, event: string) => {
    if (!TERMINAL.has(item.status)) {
      item.status = status;
      item.revision += 1;
    }
    await save(item, event);
  };
  const pump = async () => {
    const records = await all();
    const running = records.filter((item) => item.status === "running" || item.status === "waiting");
    const limit = options.concurrency ?? LIMIT;
    for (const item of records.filter((candidate) => candidate.project === project && candidate.status === "queued").sort((left, right) => left.priority - right.priority || left.created_at.localeCompare(right.created_at))) {
      if (running.length >= limit || running.filter((candidate) => candidate.parent_session_id === item.parent_session_id).length >= (options.parentConcurrency ?? 1)) continue;
      if (!client.session.create) {
        item.error = { message: "session.create unavailable", retryable: false };
        await transition(item, "failed", "dispatch.error");
        continue;
      }
      const created = await client.session.create({ query: { directory: item.directory }, body: { title: `background-attempt:${item.attempt_id}`, parentID: item.parent_session_id, directory: item.directory } });
      const child = id(created);
      if (!child) {
        item.error = { message: "OpenCode did not return child session id", retryable: false };
        await transition(item, "failed", "dispatch.error");
        continue;
      }
      item.child_session_id = child;
      await transition(item, "running", "session.created");
      running.push(item);
      void client.session.prompt({ path: { id: child }, body: { agent: item.agent, parts: [{ type: "text", text: `Complete this bounded background attempt. Do not create recursive attempts.\nTask:\n${item.task}` }] } }).catch(async (error) => {
        item.error = { message: String(error), retryable: false };
        await transition(item, "failed", "session.prompt.error");
      });
    }
  };
  const attempts = tool({
    description: "Start and manage bounded routed background attempts.",
    args: { action: tool.schema.enum(["start", "list", "status", "result", "cancel", "retry"]), task: tool.schema.string().optional(), category: tool.schema.string().optional(), decision: tool.schema.any().optional(), priority: tool.schema.number().optional(), read_only: tool.schema.boolean().optional(), attempt_id: tool.schema.string().optional(), expected_revision: tool.schema.number().optional(), expected_status: tool.schema.enum(["queued", "running", "waiting"]).optional() },
    async execute(args: { action: "start" | "list" | "status" | "result" | "cancel" | "retry"; task?: string; category?: string; decision?: unknown; priority?: number; read_only?: boolean; attempt_id?: string; expected_revision?: number; expected_status?: "queued" | "running" | "waiting" }, context: { sessionID: string }) {
      if (args.action === "start") {
        const decision = args.decision as Record<string, unknown> | undefined;
        if (!args.task || !args.category || !decision || typeof decision.agent !== "string" || typeof decision.decision_digest !== "string") throw new Error("start requires a routed decision, task and category");
        const item: Attempt = { schema_version: 1, attempt_id: randomUUID(), parent_session_id: context.sessionID, project, directory: project, task: args.task, category: args.category, agent: decision.agent, routing_decision_digest: decision.decision_digest, status: "queued", revision: 0, priority: args.priority ?? 0, read_only: args.read_only !== false, created_at: new Date().toISOString(), receipts: [], retry_number: 0 };
        await save(item, "attempt.queued");
        await pump();
        const current = await load(item.attempt_id);
        return JSON.stringify({ attempt_id: item.attempt_id, status: current?.status ?? "queued" });
      }
      const candidates = (await all()).filter((item) => item.project === project && item.parent_session_id === context.sessionID);
      if (args.action === "list") return JSON.stringify(candidates.map(({ task: _task, receipts: _receipts, ...item }) => item));
      const item = candidates.find((candidate) => candidate.attempt_id === args.attempt_id);
      if (!item) throw new Error("attempt not found in current parent session/project");
      if (args.action === "retry") {
        if (item.status !== "failed" || item.read_only !== true || item.error?.retryable !== true || item.retry_number >= 2) throw new Error("retry requires a failed, read-only, retryable attempt within its retry limit");
        const retry: Attempt = { ...item, attempt_id: randomUUID(), parent_attempt_id: item.attempt_id, retry_number: item.retry_number + 1, status: "queued", revision: 0, created_at: new Date().toISOString(), receipts: [], child_session_id: undefined, workspace_id: undefined, result: undefined, error: undefined };
        await save(retry, "attempt.retry.queued");
        await pump();
        return JSON.stringify({ attempt_id: retry.attempt_id, parent_attempt_id: item.attempt_id, status: (await load(retry.attempt_id))?.status ?? "queued" });
      }
      if (args.action === "status") return JSON.stringify(item);
      if (args.action === "result") return JSON.stringify(TERMINAL.has(item.status) ? { attempt_id: item.attempt_id, status: item.status, terminal: true, result: item.result, session_id: item.child_session_id, workspace_id: item.workspace_id } : { attempt_id: item.attempt_id, status: item.status, terminal: false });
      if (TERMINAL.has(item.status)) return JSON.stringify({ attempt_id: item.attempt_id, status: item.status, cancelled: false, reason: "terminal" });
      if (item.revision !== args.expected_revision || item.status !== args.expected_status) throw new Error("attempt changed since cancellation preview");
      if (item.status === "queued") await transition(item, "cancelled", "cancel.confirmed");
      else if (item.child_session_id && client.session.abort) {
        await client.session.abort({ path: { id: item.child_session_id } });
        await transition(item, "cancelled", "cancel.confirmed");
      } else await transition(item, "orphaned", "cancel.unconfirmed");
      return JSON.stringify({ attempt_id: item.attempt_id, status: item.status });
    },
  });
  return { tool: { background_attempts: attempts }, "tool.execute.before": async (input: { tool: string; sessionID: string }) => {
    if (input.tool !== "background_attempts" && input.tool !== "task") return;
    if ((await all()).some((item) => item.child_session_id === input.sessionID)) throw new Error("child attempts cannot create recursive attempts or tasks");
  } };
}

export default backgroundAttempts;
