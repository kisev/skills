import { tool, type Plugin } from "@opencode-ai/plugin";

import { CATEGORIES, type AvailableAgent, type Category, RoutingGate, type RoutingInput } from "./routing.js";

export { COMMAND_REGISTRY, renderCommand } from "./registry.js";
export { CATEGORIES, resolveRouting, RoutingGate } from "./routing.js";

const plugin = (async () => {
  const gate = new RoutingGate();
  const route = tool({
    description: "Resolve a capability category and dispatch one eligible agent through a one-use Task receipt gate.",
    args: {
      action: tool.schema.enum(["preview", "dispatch"]),
      category: tool.schema.enum(CATEGORIES),
      task: tool.schema.string(),
      requirements: tool.schema.array(tool.schema.string()).default([]),
      agents: tool.schema.array(tool.schema.object({ agent: tool.schema.string(), available: tool.schema.boolean().optional(), capabilities: tool.schema.array(tool.schema.string()).optional(), tools: tool.schema.array(tool.schema.string()).optional() })),
      override: tool.schema.string().optional(),
      budget: tool.schema.object({ cost_class: tool.schema.string().optional(), latency_class: tool.schema.string().optional() }).optional(),
      decision: tool.schema.any().optional()
    },
    async execute(args: { action: "preview" | "dispatch"; category: Category; task: string; requirements: string[]; agents: AvailableAgent[]; override?: string; budget?: RoutingInput["budget"]; decision?: unknown }, context: { sessionID: string }) {
      const input: RoutingInput = { category: args.category, requirements: args.requirements, agents: args.agents, override: args.override, budget: args.budget };
      if (args.action === "preview") return JSON.stringify(gate.preview(input));
      const decision = gate.dispatch(input, args.decision);
      gate.grant(context.sessionID, decision);
      return JSON.stringify({ decision, status: "routed" });
    }
  });
  return {
    tool: { route },
    "tool.execute.before": async (input: { tool: string; sessionID: string }, output: { args: unknown }) => {
      if (input.tool !== "task") return;
      const args = output.args && typeof output.args === "object" ? output.args as Record<string, unknown> : {};
      const agent = typeof args.agent === "string" ? args.agent : typeof args.subagent_type === "string" ? args.subagent_type : undefined;
      if (!agent) throw new Error("Native Task requires an explicit agent and an active routing receipt");
      gate.consume(input.sessionID, agent);
    }
  };
}) satisfies Plugin;

export const server = plugin;
export default plugin;
