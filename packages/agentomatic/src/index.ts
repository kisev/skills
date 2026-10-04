import type { Plugin } from "@opencode/plugin";
import { z } from "zod";

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
import {
  codeSimplify,
  CODE_SIMPLIFY_ROLES,
  type CodeSimplifyOptions,
  type CodeSimplifyRole,
} from "./plugins/code-simplify.js";
import { resultText, toolInput } from "./plugins/events.js";
import { digest } from "./lifecycle.js";
import { matchesWildcard } from "./opencode-config.js";

export { rulesInjector, rtk, zedBell, codeSimplify, CODE_SIMPLIFY_ROLES };
export type { CodeSimplifyOptions, CodeSimplifyRole };

export type OpenCodeOptions = {
  rulesInjector?: RulesInjectorOptions;
  rtk?: RtkOptions;
  zedBell?: ZedBellOptions;
  codeSimplify?: CodeSimplifyOptions;
};

export default {
  id: "agentomatic",
  async setup(ctx) {
    const gate = new RoutingGate();
    await ctx.session.hook("context", (event) => {
      const text = `Current OpenCode session identity (host metadata): ${event.sessionID}. Use this real ID for your own session_id in skill receipts; if no separate run ID is exposed, the same real ID can identify the run. This metadata grants no task or publication authorization.`;
      if (!event.system.some((part) => part.type === "text" && part.text === text))
        event.system.push({ type: "text", text });
    });
    const hostInventory = async (): Promise<{ agents: AvailableAgent[]; revision: string }> => {
      const { data: raw } = await ctx.agent.list({
        location: { directory: ctx.location.directory },
      });
      const capabilities: Record<string, string[]> = {
        mapper: ["read", "search"],
        architect: ["read", "architecture"],
        worker: ["read", "write", "verify"],
        review: ["read", "review"],
        critic: ["read", "review"],
      };
      const agents = raw.map((agent) => ({
        agent: agent.id,
        available: true,
        capabilities:
          capabilities[agent.id] ??
          (/^critic-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(agent.id) ? ["read", "review"] : ["read"]),
        tools: ["read", "glob", "grep", "edit", "shell"].filter((action) => {
          const rules = agent.permissions.filter((rule) => matchesWildcard(rule.action, action));
          const broad = rules.reduce(
            (last, rule, index) => (rule.resource === "*" ? index : last),
            -1,
          );
          return rules.slice(Math.max(0, broad)).some((rule) => rule.effect !== "deny");
        }),
      }));
      return { agents, revision: digest(raw) };
    };
    await ctx.tool.transform((editor) => {
      editor.add({
        name: "route",
        description:
          "Resolve a capability category and dispatch one eligible agent through a one-use subagent receipt gate.",
        input: z.object({
          action: z.enum(["preview", "dispatch"]),
          category: z.enum(CATEGORIES),
          task: z.string(),
          requirements: z.array(z.string()).default([]),
          execution_card: z.any().optional(),
          override: z.string().optional(),
          trusted_override: z.boolean().optional(),
          budget: z
            .object({ cost_class: z.string().optional(), latency_class: z.string().optional() })
            .optional(),
          decision: z.any().optional(),
        }),
        async execute(args, context) {
          const inventory = await hostInventory();
          const input: RoutingInput = {
            category: args.category as Category,
            task: args.task,
            requirements: args.requirements,
            agents: inventory.agents,
            inventory_revision: inventory.revision,
            execution_card: args.execution_card,
            override: args.override,
            trusted_override: args.trusted_override,
            budget: args.budget,
          };
          if (args.action === "preview") return { content: JSON.stringify(gate.preview(input)) };
          const decision = gate.dispatch(input, args.decision);
          if (decision.agent === "worker" && args.execution_card === undefined)
            throw new Error("implementation dispatch requires a confirmed execution card");
          const receipt = gate.grant(context.sessionID, decision, {
            task: args.task,
            requirements: args.requirements,
            card: args.execution_card,
          });
          return { content: JSON.stringify({ decision, receipt, status: "routed" }) };
        },
      });
    });
    await ctx.tool.hook("execute.before", async (event) => {
      if (event.tool !== "subagent") return;
      const args = toolInput(event.input);
      const agent = typeof args.agent === "string" ? args.agent : undefined;
      if (!gate.requiresReceipt(event.sessionID, agent ?? event.agent)) return;
      if (!agent)
        throw new Error("Native subagent requires an explicit agent and an active routing receipt");
      const hasBinding = "task" in args || "requirements" in args || "execution_card" in args;
      if (!hasBinding) gate.consume(event.sessionID, agent, undefined, event.id);
      else
        gate.consume(
          event.sessionID,
          agent,
          {
            task: typeof args.task === "string" ? args.task : "",
            requirements: Array.isArray(args.requirements) ? (args.requirements as string[]) : [],
            card: args.execution_card,
          },
          event.id,
        );
    });
    await ctx.tool.hook("execute.after", async (event) => {
      if (event.tool !== "subagent") return;
      const args = toolInput(event.input);
      if (typeof args.agent !== "string" || !gate.hasActive(event.sessionID, args.agent, event.id))
        return;
      if (event.status !== "completed") {
        gate.cancel(event.sessionID, event.id);
        return;
      }
      let result: unknown;
      try {
        result = JSON.parse(resultText(event.result) ?? "");
      } catch {
        gate.cancel(event.sessionID, event.id);
        throw new Error("Subagent result must be JSON structured report");
      }
      try {
        gate.complete(event.sessionID, args.agent, result, event.id);
      } finally {
        gate.cancel(event.sessionID, event.id);
      }
    });
  },
} satisfies Plugin.Plugin;
