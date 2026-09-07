import { randomUUID } from "node:crypto";

type Execute = (args: Record<string, unknown>, context: { sessionID: string }) => Promise<string>;
type BridgeInput = {
  operation: "create_group" | "status" | "cancel" | "create_fusion";
  idempotency_key?: string;
  task?: { task_b64?: string; category?: string; routing?: unknown[] };
  runs?: Array<Record<string, unknown>>;
  source?: Record<string, unknown>;
};

export function createMultiRunPackageBridge(input: { attempts: Execute; sessionID: string }) {
  const applied = new Map<string, Record<string, unknown>>();
  return async (request: BridgeInput): Promise<Record<string, unknown>> => {
    if (request.idempotency_key && applied.has(request.idempotency_key))
      return applied.get(request.idempotency_key)!;
    if (request.operation === "create_group") {
      const task = request.task;
      if (!task || !Array.isArray(task.routing))
        throw new Error("package bridge group request is incomplete");
      const text = Buffer.from(String(task.task_b64 ?? ""), "base64").toString("utf8");
      const runs = [];
      for (const decision of task.routing) {
        const result = JSON.parse(
          await input.attempts(
            {
              action: "start",
              task: text,
              category: String(task.category ?? "implementation"),
              decision,
            },
            { sessionID: input.sessionID },
          ),
        );
        runs.push({
          run_id: randomUUID(),
          attempt_id: result.attempt_id,
          session_id: result.session_id,
          workspace_id: result.workspace_id,
          status: result.status,
          revision: result.revision,
        });
      }
      const result = { status: "started", runs };
      if (request.idempotency_key) applied.set(request.idempotency_key, result);
      return result;
    }
    if (request.operation === "status") {
      const runs = [];
      for (const run of request.runs ?? []) {
        const status = JSON.parse(
          await input.attempts(
            { action: "status", attempt_id: run.attempt_id },
            { sessionID: input.sessionID },
          ),
        );
        runs.push({
          ...run,
          status: status.status,
          revision: status.revision,
          ...(status.result?.manifest ? { manifest: status.result.manifest } : {}),
        });
      }
      return {
        status: runs.every((run) =>
          ["completed", "failed", "cancelled", "orphaned"].includes(String(run.status)),
        )
          ? "completed"
          : "running",
        runs,
      };
    }
    if (request.operation === "cancel") {
      const runs = [];
      for (const run of request.runs ?? [])
        runs.push(
          JSON.parse(
            await input.attempts(
              {
                action: "cancel",
                attempt_id: run.attempt_id,
                expected_revision: run.revision,
                expected_status: run.status,
              },
              { sessionID: input.sessionID },
            ),
          ),
        );
      return { status: "cancel_requested", runs };
    }
    if (!request.source) throw new Error("fusion request is incomplete");
    const source = request.source;
    const task = source.task as Record<string, unknown> | undefined;
    const routing = Array.isArray(source.routing) ? source.routing[0] : undefined;
    if (!task || !routing) throw new Error("fusion source lacks routing and task");
    const result = JSON.parse(
      await input.attempts(
        {
          action: "start",
          task: Buffer.from(String(task.task_b64 ?? ""), "base64").toString("utf8"),
          category: String(source.category ?? "implementation"),
          decision: routing,
        },
        { sessionID: input.sessionID },
      ),
    );
    const response = {
      run: {
        run_id: randomUUID(),
        attempt_id: result.attempt_id,
        session_id: result.session_id,
        workspace_id: result.workspace_id,
        status: result.status,
        revision: result.revision,
        provenance: source,
      },
    };
    if (request.idempotency_key) applied.set(request.idempotency_key, response);
    return response;
  };
}
