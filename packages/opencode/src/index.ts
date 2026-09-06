import { tool, type Plugin } from "@opencode-ai/plugin";

import { CATEGORIES, type AvailableAgent, type Category, RoutingGate, type RoutingInput } from "./routing.js";
import backgroundAttempts, { type BackgroundAttemptsOptions } from "./plugins/background-attempts.js";
import goalLoop, { type GoalLoopOptions } from "./plugins/goal-loop.js";
import scheduler, { type SchedulerOptions } from "./plugins/schedule.js";
import autonomyPolicy, { type AutonomyPolicyOptions } from "./plugins/autonomy-policy.js";
import rulesInjector, { type RulesInjectorOptions } from "./plugins/rules-injector.js";
import rtk, { type RtkOptions } from "./plugins/rtk.js";
import zedBell, { type ZedBellOptions } from "./plugins/zed-bell.js";
import zedClickablePaths, { type ZedClickablePathsOptions } from "./plugins/zed-clickable-paths.js";
import {
  applyAgentProfileChange,
  listAgentProfiles,
  previewAgentProfileChange,
  type AgentProfileAction,
  type AgentProfileRequest,
} from "./agent-profiles.js";

export { COMMAND_REGISTRY, renderCommand } from "./registry.js";
export { CATEGORIES, resolveRouting, RoutingGate } from "./routing.js";
export {
  AgentProfileError,
  FIXED_AGENT_ROLES,
  applyAgentProfileChange,
  availableModels,
  availableModelVariants,
  listAgentProfiles,
  previewAgentProfileChange,
  renderAgentProfile,
  validateAgentName,
  validateModel,
  validateVariant,
} from "./agent-profiles.js";
export type {
  AgentInventory,
  AgentModelSelection,
  AgentOwnership,
  AgentProfileAction,
  AgentProfileConfig,
  AgentProfileOperation,
  AgentProfilePlan,
  AgentProfileRecord,
  AgentProfileRequest,
  AgentProfileResult,
  AgentProfileScope,
  AgentState,
  DeploymentManifest,
  DeploymentRecord,
  FixedAgentRole,
} from "./agent-profiles.js";
export { backgroundAttempts, goalLoop, scheduler, autonomyPolicy, rulesInjector, rtk, zedBell, zedClickablePaths };

export type OpenCodeOptions = {
  backgroundAttempts?: BackgroundAttemptsOptions;
  goalLoop?: GoalLoopOptions;
  scheduler?: SchedulerOptions;
  autonomyPolicy?: AutonomyPolicyOptions;
  rulesInjector?: RulesInjectorOptions;
  rtk?: RtkOptions;
  zedBell?: ZedBellOptions;
  zedClickablePaths?: ZedClickablePathsOptions;
};

const CATALOG = {
  skills: ["attempt", "goal", "schedule", "multi-run", "usage", "overview", "lsp-report"],
  plugins: ["background-attempts", "goal-loop", "schedule", "autonomy-policy", "rules-injector", "rtk", "zed-bell", "zed-clickable-paths"],
  replacements: ["capabilities", "route", "doctor", "agent_profiles"],
  version: "1.1.1",
} as const;

const plugin = (async (input: { directory?: string }) => {
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
  const capabilities = tool({
    description: "Show the bundled OpenCode capability catalog without installing or changing anything.",
    args: {},
    async execute() { return JSON.stringify({ schema_version: 1, status: "ok", ...CATALOG }); },
  });
  const doctor = tool({
    description: "Read package health and opt-in defaults without installing or repairing anything.",
    args: {},
    async execute() {
      return JSON.stringify({ schema_version: 1, status: "ok", package: "@kisev/skills-opencode", opencode: ">=1.18.29", state: "not-inspected", mutations: false, defaults: { backgroundAttempts: false, goalLoop: false, scheduler: false, autonomyPolicy: false, zedBell: false, zedClickablePaths: false } });
    },
  });
  const agentProfiles = tool({
    description: "List, preview, or apply package-owned OpenCode agent profile configuration without editing opencode.json.",
    args: {
      action: tool.schema.enum(["list", "model_set", "critic_add", "critic_remove"]),
      phase: tool.schema.enum(["preview", "apply"]).optional(),
      scope: tool.schema.enum(["global", "project"]),
      name: tool.schema.string().optional(),
      model: tool.schema.string().optional(),
      variant: tool.schema.string().nullable().optional(),
      confirmation_digest: tool.schema.string().optional(),
    },
    async execute(args: { action: "list" | "model_set" | "critic_add" | "critic_remove"; phase?: "preview" | "apply"; scope: "global" | "project"; name?: string; model?: string; variant?: string | null; confirmation_digest?: string }) {
      const cwd = input.directory ?? process.cwd();
      if (args.action === "list") {
        if (args.phase || args.name || args.model || args.variant !== undefined || args.confirmation_digest) throw new Error("agent_profiles list accepts only scope");
        return JSON.stringify({ status: "ok", inventory: await listAgentProfiles(args.scope, cwd) });
      }
      if (!args.phase) throw new Error("agent_profiles mutation requires preview or apply phase");
      const action = ({ model_set: "model-set", critic_add: "critic-add", critic_remove: "critic-remove" } as const)[args.action] satisfies AgentProfileAction;
      const request: AgentProfileRequest = { action, ...(args.name ? { name: args.name } : {}), ...(args.model ? { model: args.model } : {}), ...(args.variant !== undefined ? { variant: args.variant } : {}) };
      if (args.phase === "preview") return JSON.stringify({ status: "ok", applied: false, requires_restart: false, plan: await previewAgentProfileChange(request, args.scope, cwd) });
      if (!args.confirmation_digest) throw new Error("agent_profiles apply requires confirmation_digest");
      return JSON.stringify(await applyAgentProfileChange(request, args.scope, args.confirmation_digest, cwd));
    },
  });
  return {
    tool: { route, capabilities, doctor, agent_profiles: agentProfiles },
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
