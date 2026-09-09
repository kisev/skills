import { tool, type Plugin, type PluginInput } from "@opencode-ai/plugin";

import { CATEGORIES, type AvailableAgent, type Category, RoutingGate, type RoutingInput } from "./routing.js";
import backgroundAttempts, { type BackgroundAttemptsOptions } from "./plugins/background-attempts.js";
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
import { applyReconcile, previewReconcile } from "./reconcile.js";
import { collectDoctorFacts, type DoctorHost } from "./doctor.js";
import { CATALOG } from "./catalog.js";
import { digest } from "./lifecycle.js";

export { COMMAND_REGISTRY, renderCommand } from "./registry.js";
export { CATEGORIES, resolveRouting, RoutingGate, ExecutionCardLifecycle, validateExecutionCard, validateRoutingReceipt } from "./routing.js";
export { validateAgentReport, CONTRACT_SCHEMA_VERSION } from "./contracts.js";
export type { ExecutionCard, ExecutionCardStatus, RoutingReceipt } from "./routing.js";
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
export { backgroundAttempts, scheduler, autonomyPolicy, rulesInjector, rtk, zedBell, zedClickablePaths };
export { applyReconcile, previewReconcile } from "./reconcile.js";
export { inspectReconcile } from "./reconcile.js";
export type { ReconcileItem, ReconcilePlan, ReconcileResult, ReconcileStatus } from "./reconcile.js";
export { collectDoctorFacts, doctorExitCode } from "./doctor.js";
export type { DoctorReport, DoctorHost, DoctorCheck, DoctorCheckStatus } from "./doctor.js";
export { worktreePlan, worktreeCreate, worktreeStatus, worktreeList, worktreeRelease, worktreeRecover } from "./runtime/worktree.js";
export type { WorktreeRecord, WorktreeStatus } from "./runtime/worktree.js";
export type OpenCodeOptions = {
  backgroundAttempts?: BackgroundAttemptsOptions;
  scheduler?: SchedulerOptions;
  autonomyPolicy?: AutonomyPolicyOptions;
  rulesInjector?: RulesInjectorOptions;
  rtk?: RtkOptions;
  zedBell?: ZedBellOptions;
  zedClickablePaths?: ZedClickablePathsOptions;
};

export { CATALOG } from "./catalog.js";

const plugin = (async (input: PluginInput) => {
  const gate = new RoutingGate();
  const hostInventory = async (): Promise<{ agents: AvailableAgent[]; revision: string }> => {
    const raw = input.client?.config
      ? (await input.client.config.get({ query: { directory: input.directory } })).data
      : undefined;
    const config = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
    const configured = config.agents && typeof config.agents === "object" && !Array.isArray(config.agents)
      ? config.agents as Record<string, unknown>
      : {};
    const defaults: Record<string, { capabilities: string[]; tools: string[] }> = {
      mapper: { capabilities: ["read", "search"], tools: ["read", "glob", "grep"] },
      architect: { capabilities: ["read", "architecture"], tools: ["read", "glob", "grep"] },
      worker: { capabilities: ["read", "write", "verify"], tools: ["read", "edit", "bash"] },
      review: { capabilities: ["read", "review"], tools: ["read", "glob", "grep"] },
      critic: { capabilities: ["read", "review"], tools: ["read", "glob", "grep"] },
    };
    const names = new Set([...Object.keys(defaults), ...Object.keys(configured)]);
    const agents = [...names].sort().map((agent) => {
      const value = configured[agent];
      return {
        agent,
        available: !(value && typeof value === "object" && (value as Record<string, unknown>).disabled === true),
        capabilities: defaults[agent]?.capabilities ?? ["read"],
        tools: defaults[agent]?.tools ?? ["read"],
      };
    });
    return { agents, revision: digest({ config: raw ?? null, agents }) };
  };
  const route = tool({
    description: "Resolve a capability category and dispatch one eligible agent through a one-use Task receipt gate.",
    args: {
      action: tool.schema.enum(["preview", "dispatch"]),
      category: tool.schema.enum(CATEGORIES),
      task: tool.schema.string(),
      requirements: tool.schema.array(tool.schema.string()).default([]),
      execution_card: tool.schema.any().optional(),
      override: tool.schema.string().optional(),
      budget: tool.schema.object({ cost_class: tool.schema.string().optional(), latency_class: tool.schema.string().optional() }).optional(),
       decision: tool.schema.any().optional()
     },
    async execute(args: { action: "preview" | "dispatch"; category: Category; task: string; requirements: string[]; execution_card?: unknown; override?: string; budget?: RoutingInput["budget"]; decision?: unknown }, context: { sessionID: string }) {
      const inventory = await hostInventory();
      const input: RoutingInput = { category: args.category, task: args.task, requirements: args.requirements, agents: inventory.agents, inventory_revision: inventory.revision, execution_card: args.execution_card, override: args.override, budget: args.budget };
      if (args.action === "preview") return JSON.stringify(gate.preview(input));
      const decision = gate.dispatch(input, args.decision);
      const receipt = gate.grant(context.sessionID, decision, { task: args.task, requirements: args.requirements, card: args.execution_card });
      return JSON.stringify({ decision, receipt, status: "routed" });
    }
  });
  const capabilities = tool({
    description: "Show the bundled OpenCode capability catalog without installing or changing anything.",
    args: {},
    async execute() { return JSON.stringify({ schema_version: 1, status: "ok", ...CATALOG }); },
  });
  const doctor = tool({
    description: "Read package health and opt-in defaults without installing or repairing anything.",
    args: { scope: tool.schema.enum(["global", "project"]).default("project") },
    async execute(args: { scope: "global" | "project" }, context: { directory: string }) {
      const host: DoctorHost | undefined = input.client
        ? {
            config: async () => (await input.client.config.get({ query: { directory: context.directory } })).data,
            lsp: async () => (await input.client.lsp.status({ query: { directory: context.directory } })).data,
          }
        : undefined;
      return JSON.stringify(await collectDoctorFacts(args.scope ?? "project", context.directory, undefined, host));
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
  const reconcile = tool({
    description: "Preview or apply scope-isolated removal of retired public assets without touching unknown sources or runtime state.",
    args: {
      phase: tool.schema.enum(["preview", "apply"]),
      scope: tool.schema.enum(["global", "project"]),
      confirmation_digest: tool.schema.string().optional(),
    },
    async execute(args: { phase: "preview" | "apply"; scope: "global" | "project"; confirmation_digest?: string }) {
      const cwd = input.directory ?? process.cwd();
      if (args.phase === "preview") return JSON.stringify({ status: "ok", applied: false, plan: await previewReconcile(args.scope, cwd) });
      if (!args.confirmation_digest) throw new Error("reconcile apply requires confirmation_digest");
      return JSON.stringify(await applyReconcile(args.scope, args.confirmation_digest, cwd));
    },
  });
  return {
    tool: { route, capabilities, doctor, agent_profiles: agentProfiles, reconcile },
      "tool.execute.before": async (input: { tool: string; sessionID: string }, output: { args: unknown }) => {
      if (input.tool !== "task") return;
      const args = output.args && typeof output.args === "object" ? output.args as Record<string, unknown> : {};
      const agent = typeof args.agent === "string" ? args.agent : typeof args.subagent_type === "string" ? args.subagent_type : undefined;
      if (!agent) throw new Error("Native Task requires an explicit agent and an active routing receipt");
      const hasBinding = "task" in args || "requirements" in args || "execution_card" in args;
      if (!hasBinding) gate.consume(input.sessionID, agent);
      else {
        const task = typeof args.task === "string" ? args.task : "";
        const requirements = Array.isArray(args.requirements) ? args.requirements as string[] : [];
         gate.consume(input.sessionID, agent, { task, requirements, card: args.execution_card });
       }
      },
      "tool.execute.after": async (input: { tool: string; sessionID: string; args: unknown }, output: { output: string }) => {
        if (input.tool !== "task") return;
        const args = input.args && typeof input.args === "object" ? input.args as Record<string, unknown> : {};
        const agent = typeof args.agent === "string" ? args.agent : typeof args.subagent_type === "string" ? args.subagent_type : undefined;
        if (!agent) throw new Error("Task result requires an explicit agent");
        let result: unknown;
        try { result = JSON.parse(output.output); } catch { throw new Error("Task result must be JSON structured report"); }
        gate.complete(input.sessionID, agent, result);
      },
    };
  }) satisfies Plugin;

export const server = plugin;
export default plugin;
