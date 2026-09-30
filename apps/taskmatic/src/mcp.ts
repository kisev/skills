import { createInterface } from "node:readline";
import { readFileSync } from "node:fs";
import { exportAll } from "./export.js";
import { filterCards, PRIORITIES, STATUSES, Store, type Input } from "./store.js";

export const VERSION: string = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
).version;
const string = { type: "string" };
const id = { ...string, pattern: "^[0-9a-f]{8}$" };
const title = { ...string, minLength: 1, maxLength: 200 };
const status = { ...string, enum: STATUSES };
const priority = { ...string, enum: PRIORITIES };
const labels = { type: "array", items: { ...string, minLength: 1, maxLength: 40 } };
const agent = { ...string, minLength: 1, maxLength: 60 };
const ttl_seconds = { type: "integer", minimum: 1, maximum: 2592000 };
const tool = (name: string, description: string, properties: Input, required: string[] = []) => ({
  name: `taskmatic_${name}`,
  description,
  inputSchema: { type: "object", properties, required, additionalProperties: false },
});
export const TOOLS = [
  tool("boards", "List boards with card counts.", {}),
  tool("list", "List cards with claim state and optional filters.", {
    board: string,
    status,
    assignee: string,
    label: string,
  }),
  tool("read", "Read a card with notes and recent activity.", { id }, ["id"]),
  tool(
    "create",
    "Create a card on a board (default: main).",
    {
      title,
      board: string,
      priority,
      labels,
      assignee: string,
      parent: id,
      linked: string,
      notes: string,
    },
    ["title"],
  ),
  tool(
    "edit",
    "Edit fields; omitted fields stay unchanged, null clears assignee or linked.",
    {
      id,
      title,
      priority,
      labels,
      assignee: { type: ["string", "null"] },
      linked: { type: ["string", "null"] },
      notes: string,
    },
    ["id"],
  ),
  tool("move", "Move a card to another status.", { id, status }, ["id", "status"]),
  tool(
    "claim",
    "Claim a free or expired card; reject another agent's live claim.",
    { id, agent, ttl_seconds },
    ["id", "agent"],
  ),
  tool("heartbeat", "Refresh a held claim before it expires.", { id, agent, ttl_seconds }, [
    "id",
    "agent",
  ]),
  tool("release", "Release your claim.", { id, agent }, ["id", "agent"]),
  tool("complete", "Mark done and clear the claim.", { id }, ["id"]),
  tool(
    "note",
    "Append a bounded activity note.",
    { id, text: { ...string, minLength: 1, maxLength: 8000 }, actor: agent },
    ["id", "text"],
  ),
];

function validate(name: string, args: Input): void {
  const definition = TOOLS.find((item) => item.name === name);
  if (!definition) throw new Error(`unknown tool ${name}`);
  for (const key of definition.inputSchema.required)
    if (!(key in args)) throw new Error(`${key} is required`);
  for (const [key, value] of Object.entries(args)) {
    const property = definition.inputSchema.properties[key] as Input | undefined;
    if (!property) throw new Error(`unknown argument ${key}`);
    const types = Array.isArray(property.type) ? property.type : [property.type];
    const type =
      value === null
        ? "null"
        : Array.isArray(value)
          ? "array"
          : typeof value === "number" && Number.isInteger(value)
            ? "integer"
            : typeof value;
    if (!types.includes(type)) throw new Error(`invalid type for ${key}`);
    if (Array.isArray(property.enum) && !property.enum.includes(value))
      throw new Error(`invalid ${key}`);
    if (
      typeof value === "string" &&
      (value.length < Number(property.minLength ?? 0) ||
        value.length > Number(property.maxLength ?? Infinity) ||
        (typeof property.pattern === "string" && !new RegExp(property.pattern).test(value)))
    )
      throw new Error(`invalid ${key}`);
    if (
      typeof value === "number" &&
      (value < Number(property.minimum ?? -Infinity) ||
        value > Number(property.maximum ?? Infinity))
    )
      throw new Error(`invalid ${key}`);
  }
}
export async function callTool(store: Store, name: string, args: Input): Promise<Input> {
  try {
    validate(name, args);
    let result: unknown;
    if (name === "taskmatic_boards") {
      const snapshot = store.snapshot();
      result = {
        boards: snapshot.boards.map((board) => ({
          ...board,
          cards: snapshot.cards.filter((card) => card.board === board.slug).length,
        })),
      };
    } else if (name === "taskmatic_list") result = { cards: filterCards(store.snapshot(), args) };
    else if (name === "taskmatic_read") result = store.read(String(args.id));
    else {
      result = store.mutate(name.slice("taskmatic_".length), args, "mcp");
      if (name !== "taskmatic_heartbeat") await exportAll(store);
    }
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      structuredContent: result,
      isError: false,
    };
  } catch (error) {
    return {
      content: [{ type: "text", text: `taskmatic: ${(error as Error).message}` }],
      isError: true,
    };
  }
}
export async function dispatchMcp(store: Store, request: Input): Promise<Input | null> {
  if (
    typeof request.method !== "string" ||
    request.method.startsWith("notifications/") ||
    !("id" in request)
  )
    return null;
  const params =
    request.params && typeof request.params === "object" && !Array.isArray(request.params)
      ? (request.params as Input)
      : {};
  const reply = (result: unknown) => ({ jsonrpc: "2.0", id: request.id, result });
  if (request.method === "initialize")
    return reply({
      protocolVersion:
        typeof params.protocolVersion === "string" ? params.protocolVersion : "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "taskmatic", version: VERSION },
    });
  if (request.method === "ping") return reply({});
  if (request.method === "tools/list") return reply({ tools: TOOLS });
  if (request.method === "tools/call") {
    if (
      typeof params.name !== "string" ||
      (params.arguments !== undefined &&
        (params.arguments === null ||
          typeof params.arguments !== "object" ||
          Array.isArray(params.arguments)))
    )
      return {
        jsonrpc: "2.0",
        id: request.id,
        error: { code: -32602, message: "invalid tools/call parameters" },
      };
    return reply(await callTool(store, params.name, (params.arguments ?? {}) as Input));
  }
  return {
    jsonrpc: "2.0",
    id: request.id,
    error: { code: -32601, message: `unknown method ${request.method}` },
  };
}
export async function runMcp(store: Store): Promise<void> {
  for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
    try {
      const request: unknown = JSON.parse(line);
      if (!request || typeof request !== "object" || Array.isArray(request)) continue;
      const response = await dispatchMcp(store, request as Input);
      if (response) process.stdout.write(`${JSON.stringify(response)}\n`);
    } catch (error) {
      process.stdout.write(
        `${JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: (error as Error).message } })}\n`,
      );
    }
  }
}
