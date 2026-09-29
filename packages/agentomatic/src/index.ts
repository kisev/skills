import type { Plugin } from "@opencode-ai/plugin";
import type { Plugin as V2Plugin } from "@opencode/plugin";
import { z } from "zod";

import { registerV2Hooks } from "./plugins/compatibility.js";

import {
  CATEGORIES,
  type AvailableAgent,
  type Category,
  RoutingGate,
  type RoutingInput,
} from "./routing.js";
import { rulesInjector, type RulesInjectorOptions } from "./plugins/rules-injector.js";
import { rtk, type RtkOptions } from "./plugins/rtk.js";
import { zedBell, type ZedBellOptions } from "./plugins/zed-bell.js";
import { digest } from "./lifecycle.js";

export { rulesInjector, rtk, zedBell };
export type OpenCodeOptions = {
  rulesInjector?: RulesInjectorOptions;
  rtk?: RtkOptions;
  zedBell?: ZedBellOptions;
};

type RuntimeInput = {
  directory: string;
  client?: {
    app?: { agents?: (input: { query: { directory: string } }) => Promise<{ data?: unknown }> };
  };
};

const plugin = (async (input: RuntimeInput) => {
  const gate = new RoutingGate();
  const hostInventory = async (): Promise<{ agents: AvailableAgent[]; revision: string }> => {
    if (!input.client?.app?.agents)
      throw new Error("Resolved OpenCode agent inventory is unavailable");
    const response = await input.client.app.agents({ query: { directory: input.directory } });
    const raw = response.data;
    if (!Array.isArray(raw)) throw new Error("Resolved OpenCode agent inventory is malformed");
    const capabilities: Record<string, string[]> = {
      mapper: ["read", "search"],
      architect: ["read", "architecture"],
      worker: ["read", "write", "verify"],
      review: ["read", "review"],
      critic: ["read", "review"],
    };
    const agents = raw.map((value) => {
      const agent = value as {
        name?: unknown;
        permission?: { edit?: string; bash?: Record<string, string> };
        tools?: Record<string, boolean>;
      };
      if (typeof agent.name !== "string" || !agent.name)
        throw new Error("Resolved OpenCode agent has no name");
      return {
        agent: agent.name,
        available: true,
        capabilities:
          capabilities[agent.name] ??
          (/^critic-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(agent.name) ? ["read", "review"] : ["read"]),
        tools: [
          "read",
          ...(agent.permission?.edit !== "deny" ? ["edit"] : []),
          ...Object.entries(agent.tools ?? {})
            .filter(([, enabled]) => enabled)
            .map(([name]) => name),
          ...Object.entries(agent.permission?.bash ?? {})
            .filter(([, mode]) => mode !== "deny")
            .map(() => "bash"),
        ].filter((name, index, list) => list.indexOf(name) === index),
      };
    });
    return { agents, revision: digest(raw) };
  };
  const route = {
    description:
      "Resolve a capability category and dispatch one eligible agent through a one-use Task receipt gate.",
    args: {
      action: z.enum(["preview", "dispatch"]),
      category: z.enum(CATEGORIES),
      task: z.string(),
      requirements: z.array(z.string()).default([]),
      execution_card: z.any().optional(),
      override: z.string().optional(),
      trusted_override: z.boolean().optional(),
      budget: z
        .object({
          cost_class: z.string().optional(),
          latency_class: z.string().optional(),
        })
        .optional(),
      decision: z.any().optional(),
    },
    async execute(
      args: {
        action: "preview" | "dispatch";
        category: Category;
        task: string;
        requirements: string[];
        execution_card?: unknown;
        override?: string;
        trusted_override?: boolean;
        budget?: RoutingInput["budget"];
        decision?: unknown;
      },
      context: { sessionID: string },
    ) {
      const inventory = await hostInventory();
      const input: RoutingInput = {
        category: args.category,
        task: args.task,
        requirements: args.requirements,
        agents: inventory.agents,
        inventory_revision: inventory.revision,
        execution_card: args.execution_card,
        override: args.override,
        trusted_override: args.trusted_override,
        budget: args.budget,
      };
      if (args.action === "preview") return JSON.stringify(gate.preview(input));
      const decision = gate.dispatch(input, args.decision);
      if (decision.agent === "worker" && args.execution_card === undefined)
        throw new Error("implementation dispatch requires a confirmed execution card");
      const receipt = gate.grant(context.sessionID, decision, {
        task: args.task,
        requirements: args.requirements,
        card: args.execution_card,
      });
      return JSON.stringify({ decision, receipt, status: "routed" });
    },
  };
  return {
    tool: { route },
    "tool.execute.before": async (
      input: { tool: string; sessionID: string },
      output: { args: unknown },
    ) => {
      if (input.tool !== "task") return;
      const args =
        output.args && typeof output.args === "object"
          ? (output.args as Record<string, unknown>)
          : {};
      const agent =
        typeof args.agent === "string"
          ? args.agent
          : typeof args.subagent_type === "string"
            ? args.subagent_type
            : undefined;
      if (!agent)
        throw new Error("Native Task requires an explicit agent and an active routing receipt");
      const hasBinding = "task" in args || "requirements" in args || "execution_card" in args;
      if (!hasBinding) gate.consume(input.sessionID, agent);
      else {
        const task = typeof args.task === "string" ? args.task : "";
        const requirements = Array.isArray(args.requirements)
          ? (args.requirements as string[])
          : [];
        gate.consume(input.sessionID, agent, { task, requirements, card: args.execution_card });
      }
    },
    "tool.execute.after": async (
      input: { tool: string; sessionID: string; args: unknown },
      output: { output: string },
    ) => {
      if (input.tool !== "task") return;
      const args =
        input.args && typeof input.args === "object" ? (input.args as Record<string, unknown>) : {};
      const agent =
        typeof args.agent === "string"
          ? args.agent
          : typeof args.subagent_type === "string"
            ? args.subagent_type
            : undefined;
      if (!agent) throw new Error("Task result requires an explicit agent");
      let result: unknown;
      try {
        result = JSON.parse(output.output);
      } catch {
        throw new Error("Task result must be JSON structured report");
      }
      gate.complete(input.sessionID, agent, result);
    },
  };
}) satisfies Plugin;

export const server = plugin;
export default {
  id: "agentomatic",
  server,
  async setup(ctx) {
    const hooks = await plugin({
      directory: ctx.location.directory,
      client: {
        app: {
          agents: async () => {
            const { data: agents } = await ctx.agent.list({
              location: { directory: ctx.location.directory },
            });
            return {
              data: agents.map((agent) => ({
                name: agent.id,
                tools: Object.fromEntries(
                  ["read", "glob", "grep", "edit", "bash"].map((tool) => [
                    tool,
                    [...agent.permissions]
                      .reverse()
                      .find(
                        (rule) =>
                          (rule.action === (tool === "bash" ? "shell" : tool) ||
                            rule.action === "*") &&
                          rule.resource === "*",
                      )?.effect !== "deny",
                  ]),
                ),
                permission: {
                  edit: agent.permissions.some(
                    (rule) =>
                      rule.action === "edit" && rule.resource === "*" && rule.effect === "deny",
                  )
                    ? "deny"
                    : "allow",
                  bash: Object.fromEntries(
                    agent.permissions
                      .filter((rule) => rule.action === "shell")
                      .map((rule) => [rule.resource, rule.effect]),
                  ),
                },
              })),
            };
          },
        },
      },
    });
    await ctx.tool.transform((editor) => {
      const route = hooks.tool.route;
      editor.add({
        name: "route",
        description: route.description,
        input: z.object(route.args),
        async execute(args, context) {
          return { content: await route.execute(args, context) };
        },
      });
    });
    return registerV2Hooks(ctx, hooks);
  },
} satisfies V2Plugin.Plugin & { server: typeof server };
