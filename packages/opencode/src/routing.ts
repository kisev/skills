import { createHash } from "node:crypto";

export const CATEGORIES = ["exploration", "architecture", "implementation", "review", "documentation", "quick"] as const;
export type Category = (typeof CATEGORIES)[number];
export type AvailableAgent = { agent: string; available?: boolean; capabilities?: string[]; tools?: string[] };
export type RoutingInput = { category: Category; requirements: string[]; agents: AvailableAgent[]; override?: string; budget?: { cost_class?: string; latency_class?: string } };
export type RoutingDecision = { schema_version: 1; status: "selected" | "escalate"; category: Category; agent?: string; reason_codes: string[]; alternatives: { agent: string; excluded_reasons: string[] }[]; matrix_revision: string; decision_digest: string };

const MATRIX = {
  schema_version: 1,
  categories: {
    exploration: { profiles: ["mapper", "architect"], capabilities: ["read", "search"], tools: ["read", "glob", "grep"], cost: "low", latency: "fast" },
    architecture: { profiles: ["architect", "mapper"], capabilities: ["read", "architecture"], tools: ["read", "glob", "grep"], cost: "medium", latency: "standard" },
    implementation: { profiles: ["worker"], capabilities: ["read", "write", "verify"], tools: ["read", "edit", "bash"], cost: "medium", latency: "standard" },
    review: { profiles: ["review", "critic"], capabilities: ["read", "review"], tools: ["read", "glob", "grep"], cost: "medium", latency: "standard" },
    documentation: { profiles: ["worker", "review"], capabilities: ["read", "write", "documentation"], tools: ["read", "edit"], cost: "low", latency: "standard" },
    quick: { profiles: ["mapper", "worker"], capabilities: ["read"], tools: ["read"], cost: "low", latency: "fast" }
  }
} as const;

function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object).sort().map((key) => `${JSON.stringify(key)}:${stable(object[key])}`).join(",")}}`;
}

function digest(value: unknown): string {
  return createHash("sha256").update(stable(value), "utf8").digest("hex");
}

function missing(required: readonly string[], actual: string[] | undefined): boolean {
  const values = new Set(actual ?? []);
  return required.some((item) => !values.has(item));
}

function exceeds(value: string, limit: string | undefined, order: readonly string[]): boolean {
  return limit !== undefined && order.indexOf(value) > order.indexOf(limit);
}

export function resolveRouting(input: RoutingInput): RoutingDecision {
  const category = MATRIX.categories[input.category];
  const revision = digest(MATRIX);
  const inventory = new Map(input.agents.map((agent) => [agent.agent, agent]));
  const alternatives: RoutingDecision["alternatives"] = [];
  const eligible: AvailableAgent[] = [];
  for (const profile of category.profiles) {
    const agent = inventory.get(profile);
    const reasons: string[] = [];
    if (!agent) reasons.push("agent_missing");
    else {
      if (agent.available === false) reasons.push("agent_unavailable");
      if (missing([...category.capabilities, ...input.requirements], agent.capabilities)) reasons.push("capabilities_missing");
      if (missing(category.tools, agent.tools)) reasons.push("tools_missing");
      if (exceeds(category.cost, input.budget?.cost_class, ["low", "medium", "high"])) reasons.push("cost_class_exceeded");
      if (exceeds(category.latency, input.budget?.latency_class, ["fast", "standard", "slow"])) reasons.push("latency_class_exceeded");
    }
    if (reasons.length) alternatives.push({ agent: profile, excluded_reasons: reasons });
    else if (agent) eligible.push(agent);
  }
  const selected = input.override ? eligible.find((agent) => agent.agent === input.override) : eligible[0];
  const base = selected
    ? { schema_version: 1 as const, status: "selected" as const, category: input.category, agent: selected.agent, reason_codes: [input.override ? "explicit_override" : selected.agent === category.profiles[0] ? "primary_available" : "fallback_selected", "capabilities_match"], alternatives, matrix_revision: revision }
    : { schema_version: 1 as const, status: "escalate" as const, category: input.category, reason_codes: [input.override ? "override_unavailable" : "no_eligible_profile"], alternatives, matrix_revision: revision };
  return { ...base, decision_digest: digest(base) };
}

export class RoutingGate {
  #receipts = new Map<string, RoutingDecision>();

  preview(input: RoutingInput): RoutingDecision {
    return resolveRouting(input);
  }

  dispatch(input: RoutingInput, provided: unknown): RoutingDecision {
    const decision = resolveRouting(input);
    if (!provided || typeof provided !== "object" || (provided as Partial<RoutingDecision>).decision_digest !== decision.decision_digest || (provided as Partial<RoutingDecision>).matrix_revision !== decision.matrix_revision) throw new Error("Routing decision is stale; request a new preview");
    if (decision.status !== "selected" || !decision.agent) throw new Error("Routing escalated; no agent was dispatched");
    return decision;
  }

  grant(sessionID: string, decision: RoutingDecision): void {
    this.#receipts.set(sessionID, decision);
  }

  consume(sessionID: string, agent: string): void {
    const receipt = this.#receipts.get(sessionID);
    if (!receipt) throw new Error("Native Task requires an active routing receipt; use the route tool");
    if (receipt.agent !== agent) throw new Error("Native Task agent does not match the active routing receipt");
    this.#receipts.delete(sessionID);
  }
}
