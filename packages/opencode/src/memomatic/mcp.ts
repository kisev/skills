import { forgetEntry, getEntry, openMemomatic, searchMemory, writeEntry } from "./service.js";

const PROTOCOL_VERSION = "2025-06-18";

type JsonRpcRequest = {
  jsonrpc?: string;
  id?: unknown;
  method?: string;
  params?: Record<string, unknown>;
};

const TOOLS = [
  {
    description: "Search personal memory: durable decisions, discoveries, and session outcomes.",
    inputSchema: {
      additionalProperties: false,
      properties: { query: { type: "string" } },
      required: ["query"],
      type: "object",
    },
    name: "memory_search",
  },
  {
    description:
      "Read a memory file fully or one line. Fetching a line marks that entry as useful.",
    inputSchema: {
      additionalProperties: false,
      properties: {
        file: { description: "Path relative to the memomatic state root", type: "string" },
        line: { type: "number" },
      },
      required: ["file"],
      type: "object",
    },
    name: "memory_get",
  },
  {
    description:
      "Save a memory entry. Use for standing decisions with rationale, discoveries, failed attempts with rejection reasons, session outcomes, and action-sensitive boundaries. Respect MEMORY_RULES.md; never-save topics are rejected.",
    inputSchema: {
      additionalProperties: false,
      properties: {
        importance: { maximum: 10, minimum: 1, type: "number" },
        key: { type: "string" },
        origin: { enum: ["user", "agent"], type: "string" },
        pinned: { type: "boolean" },
        project: { type: "string" },
        target: { enum: ["episodic", "curated", "user"], type: "string" },
        text: { type: "string" },
        trigger: { items: { type: "string" }, type: "array" },
      },
      required: ["text"],
      type: "object",
    },
    name: "memory_write",
  },
  {
    description: "Remove one entry line from a memory file (explicit deletion only).",
    inputSchema: {
      additionalProperties: false,
      properties: {
        file: { description: "Path relative to the memomatic state root", type: "string" },
        line: { type: "number" },
      },
      required: ["file", "line"],
      type: "object",
    },
    name: "memory_forget",
  },
] as const;

async function callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const context = await openMemomatic();
  try {
    switch (name) {
      case "memory_search": {
        if (typeof args.query !== "string" || !args.query.trim())
          throw new Error("query is required");
        const hits = await searchMemory(context, args.query);
        return hits.map((hit) => ({
          file: hit.entry.file.replace(`${context.paths.stateRoot}/`, ""),
          kind: hit.entry.kind,
          line: hit.entry.line,
          score: Number(hit.score.toFixed(4)),
          snippet: hit.snippet,
        }));
      }
      case "memory_get": {
        if (typeof args.file !== "string" || !args.file) throw new Error("file is required");
        const line = typeof args.line === "number" ? args.line : undefined;
        const result = await getEntry(context, args.file, line);
        return {
          content: result.content,
          file: result.file.replace(`${context.paths.stateRoot}/`, ""),
          line: result.line,
        };
      }
      case "memory_write": {
        if (typeof args.text !== "string" || !args.text.trim()) throw new Error("text is required");
        const file = await writeEntry(context, {
          importance: typeof args.importance === "number" ? args.importance : undefined,
          key: typeof args.key === "string" ? args.key : undefined,
          origin: args.origin === "user" ? "user" : "agent",
          pinned: args.pinned === true,
          project: typeof args.project === "string" ? args.project : undefined,
          target: args.target === "curated" || args.target === "user" ? args.target : "episodic",
          text: args.text,
          trigger: Array.isArray(args.trigger)
            ? args.trigger.filter((item): item is string => typeof item === "string")
            : undefined,
        });
        return { file: file.replace(`${context.paths.stateRoot}/`, ""), saved: true };
      }
      case "memory_forget": {
        if (typeof args.file !== "string" || typeof args.line !== "number")
          throw new Error("file and line are required");
        const file = await forgetEntry(context, { file: args.file, line: args.line });
        return { file: file.replace(`${context.paths.stateRoot}/`, ""), forgotten: true };
      }
      default:
        throw new Error(`unknown tool: ${name}`);
    }
  } finally {
    context.store.close();
  }
}

export function mcpResponse(id: unknown, result: unknown): string {
  return `${JSON.stringify({ id, jsonrpc: "2.0", result })}\n`;
}

export function mcpError(id: unknown, code: number, message: string): string {
  return `${JSON.stringify({ error: { code, message }, id, jsonrpc: "2.0" })}\n`;
}

export async function handleMcpRequest(request: JsonRpcRequest): Promise<string> {
  const { id, method } = request;
  if (method === "initialize")
    return mcpResponse(id, {
      capabilities: { tools: {} },
      protocolVersion: PROTOCOL_VERSION,
      serverInfo: { name: "memomatic", version: "0.1.0" },
    });
  if (method === "ping") return mcpResponse(id, {});
  if (method === "tools/list") return mcpResponse(id, { tools: TOOLS });
  if (method === "tools/call") {
    const params = request.params ?? {};
    const name = typeof params.name === "string" ? params.name : "";
    const args =
      params.arguments && typeof params.arguments === "object"
        ? (params.arguments as Record<string, unknown>)
        : {};
    try {
      const content = await callTool(name, args);
      return mcpResponse(id, {
        content: [{ text: JSON.stringify(content), type: "text" }],
      });
    } catch (error) {
      return mcpResponse(id, {
        content: [
          {
            text: JSON.stringify({ error: (error as Error).message }),
            type: "text",
          },
        ],
        isError: true,
      });
    }
  }
  if (method?.startsWith("notifications/")) return "";
  return mcpError(id, -32601, `method not found: ${method ?? "(none)"}`);
}

export async function runMcpServer(input = process.stdin, output = process.stdout): Promise<void> {
  let buffer = "";
  input.setEncoding("utf8");
  for await (const chunk of input) {
    buffer += chunk as string;
    let newline = buffer.indexOf("\n");
    while (newline !== -1) {
      const frame = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (frame) {
        try {
          const request = JSON.parse(frame) as JsonRpcRequest;
          const response = await handleMcpRequest(request);
          if (response) output.write(response);
        } catch {
          output.write(mcpError(null, -32700, "parse error"));
        }
      }
      newline = buffer.indexOf("\n");
    }
  }
}
