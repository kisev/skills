import { createHash } from "node:crypto";
import { validateAgentReport } from "./contracts.js";

export const CATEGORIES = ["exploration", "architecture", "implementation", "review"] as const;
export type Category = (typeof CATEGORIES)[number];
export type AvailableAgent = { agent: string; available?: boolean; capabilities?: string[]; tools?: string[] };
export type RoutingInput = { category: Category; task?: string; requirements: string[]; agents: AvailableAgent[]; inventory_revision?: string; execution_card?: unknown; override?: string; trusted_override?: boolean; budget?: { cost_class?: string; latency_class?: string } };
export type RoutingDecision = { schema_version: 1; status: "selected" | "escalate"; category: Category; agent?: string; reason_codes: string[]; alternatives: { agent: string; excluded_reasons: string[] }[]; matrix_revision: string; host_inventory_revision: string; task_digest: string; requirements_digest: string; execution_card_digest?: string; execution_card_revision?: number; decision_digest: string };
export type RoutingReceipt = { schema_version: 1; task_digest: string; requirements_digest: string; destination: Category; agent: string; card_digest: string | null; host_inventory_revision: string; expires_at: string; nonce: string; receipt_digest: string };

export type ControlMarker = { path: string; expected?: string; expected_absent?: boolean };

export type ExecutionCard = {
  schema_version: 1;
  status: "READY";
  card_id: string;
  revision: number;
  objective: string;
  evidence: string[];
  changed_behavior: string[];
  risks: string[];
  write_set: string[];
  control_markers: ControlMarker[];
  decisions: string[];
  steps: Array<{ path: string; operation: string }>;
  acceptance_criteria: string[];
  checks: string[];
  operations: Array<{ kind: "write" | "check" | "commit" | "rebase" | "push" | "merge" | "tag" | "release"; command: string; confirmation_ref?: string }>;
  confirmations: { execution: string; publication?: string; history_rewrite?: string };
  boundaries: { forbidden_paths: string[]; scope: string };
};

export type ExecutionCardStatus = ExecutionCard["status"] | "RUNNING" | "COMPLETED" | "BLOCKED" | "FAILED" | "REJECTED_PLAN" | "APPROVED" | "CHANGES_REQUIRED" | "CANCELLED";

const MATRIX = {
  schema_version: 1,
  categories: {
    exploration: { profiles: ["mapper", "architect"], capabilities: ["read", "search"], tools: ["read", "glob", "grep"], cost: "low", latency: "fast" },
    architecture: { profiles: ["architect", "mapper"], capabilities: ["read", "architecture"], tools: ["read", "glob", "grep"], cost: "medium", latency: "standard" },
    implementation: { profiles: ["worker"], capabilities: ["read", "write", "verify"], tools: ["read", "edit", "bash"], cost: "medium", latency: "standard" },
    review: { profiles: ["review", "critic"], capabilities: ["read", "review"], tools: ["read", "glob", "grep"], cost: "medium", latency: "standard" }
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

export function validateRoutingReceipt(value: unknown, context?: { task?: string; category?: string }): RoutingDecision {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("routing receipt is not an object");
  const decision = value as RoutingDecision;
  if ("destination" in decision) {
    const receipt = value as RoutingReceipt;
    if (receipt.schema_version !== 1 || !CATEGORIES.includes(receipt.destination) || !receipt.agent || !receipt.nonce || !/^[a-f0-9]{64}$/.test(receipt.host_inventory_revision) || !/^[a-f0-9]{64}$/.test(receipt.receipt_digest)) throw new Error("routing receipt is malformed");
    const { receipt_digest: _receiptDigest, ...receiptBase } = receipt;
    if (digest(receiptBase) !== receipt.receipt_digest) throw new Error("routing receipt integrity is invalid");
    return receipt as unknown as RoutingDecision;
  }
  if (decision.schema_version !== 1 || decision.status !== "selected" || !decision.agent || !CATEGORIES.includes(decision.category)) throw new Error("routing receipt is not selected");
  if (!decision.matrix_revision || !decision.decision_digest || !/^[a-f0-9]{64}$/.test(decision.decision_digest)) throw new Error("routing receipt is incomplete");
  const { decision_digest: _digest, ...base } = decision;
  if (digest(base) !== decision.decision_digest) throw new Error("routing receipt digest is forged or stale");
  if (decision.matrix_revision !== digest(MATRIX)) throw new Error("routing receipt matrix is stale");
  if (context?.category !== undefined && decision.category !== context.category) throw new Error("routing receipt category does not match");
  if (context?.task !== undefined && decision.task_digest !== digest(context.task)) throw new Error("routing receipt task does not match");
  return decision;
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
  const hostInventoryRevision = input.inventory_revision ?? digest(input.agents);
  const inventory = new Map(input.agents.map((agent) => [agent.agent, agent]));
  const alternatives: RoutingDecision["alternatives"] = [];
  const eligible: AvailableAgent[] = [];
  const profiles = input.trusted_override && input.override && !category.profiles.includes(input.override as never)
    ? [...category.profiles, input.override]
    : category.profiles;
  for (const profile of profiles) {
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
  if (input.override && !input.trusted_override && !category.profiles.includes(input.override as never))
    throw new Error("Unknown or user-owned profile requires a trusted override");
  const selected = input.override ? eligible.find((agent) => agent.agent === input.override) : eligible[0];
  const card = input.execution_card === undefined ? undefined : validateExecutionCard(input.execution_card);
  if (card && !card.valid) throw new Error(`Invalid execution card: ${card.failedField}`);
  const base = selected
    ? { schema_version: 1 as const, status: "selected" as const, category: input.category, agent: selected.agent, reason_codes: [input.override ? "explicit_override" : selected.agent === category.profiles[0] ? "primary_available" : "fallback_selected", "capabilities_match"], alternatives, matrix_revision: revision, host_inventory_revision: hostInventoryRevision, task_digest: digest(input.task ?? ""), requirements_digest: digest(input.requirements), ...(card?.valid ? { execution_card_digest: digest(card.card), execution_card_revision: card.card.revision } : {}) }
     : { schema_version: 1 as const, status: "escalate" as const, category: input.category, reason_codes: [input.override ? "override_unavailable" : "no_eligible_profile"], alternatives, matrix_revision: revision, host_inventory_revision: hostInventoryRevision, task_digest: digest(input.task ?? ""), requirements_digest: digest(input.requirements), ...(card?.valid ? { execution_card_digest: digest(card.card), execution_card_revision: card.card.revision } : {}) };
  return { ...base, decision_digest: digest(base) };
}

function isNonEmptyStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.length > 0 && value.every((item) => typeof item === "string" && item.length > 0);
}

export function validateExecutionCard(card: unknown): { valid: true; card: ExecutionCard } | { valid: false; failedField: string } {
  if (!card || typeof card !== "object" || Array.isArray(card)) {
    return { valid: false, failedField: "root" };
  }
  const c = card as Record<string, unknown>;
  const expectedFields = [
    "schema_version", "status", "card_id", "revision", "objective", "evidence", "changed_behavior", "risks",
    "write_set", "control_markers", "decisions", "steps", "acceptance_criteria",
    "checks", "operations", "confirmations", "boundaries",
  ];
  if (Object.keys(c).sort().join(",") !== expectedFields.slice().sort().join(",")) return { valid: false, failedField: "schema" };

  if (c.schema_version !== 1) return { valid: false, failedField: "schema_version" };
  if (c.status !== "READY") return { valid: false, failedField: "status" };
  if (typeof c.card_id !== "string" || !c.card_id) return { valid: false, failedField: "card_id" };
  if (typeof c.revision !== "number" || !Number.isInteger(c.revision) || c.revision < 1) return { valid: false, failedField: "revision" };
  if (typeof c.objective !== "string" || !c.objective) return { valid: false, failedField: "objective" };
  if (!isNonEmptyStringArray(c.evidence)) return { valid: false, failedField: "evidence" };
  if (!isNonEmptyStringArray(c.changed_behavior)) return { valid: false, failedField: "changed_behavior" };
  if (!isNonEmptyStringArray(c.risks)) return { valid: false, failedField: "risks" };
  if (!isNonEmptyStringArray(c.write_set)) return { valid: false, failedField: "write_set" };
  if (new Set(c.write_set).size !== c.write_set.length) return { valid: false, failedField: "write_set" };
  if (!Array.isArray(c.control_markers) || c.control_markers.length === 0) return { valid: false, failedField: "control_markers" };
  for (const marker of c.control_markers) {
    if (!marker || typeof marker !== "object" || Array.isArray(marker)) return { valid: false, failedField: "control_markers" };
    const m = marker as Record<string, unknown>;
    if (typeof m.path !== "string" || !m.path) return { valid: false, failedField: "control_markers" };
    const hasExpected = typeof m.expected === "string" && m.expected.length > 0;
    const hasExpectedAbsent = m.expected_absent === true;
    if (hasExpected === hasExpectedAbsent) return { valid: false, failedField: "control_markers" };
    if (Object.keys(m).some((k) => k !== "path" && k !== "expected" && k !== "expected_absent")) return { valid: false, failedField: "control_markers" };
  }
  if (!isNonEmptyStringArray(c.decisions)) return { valid: false, failedField: "decisions" };
  if (!Array.isArray(c.steps) || c.steps.length === 0) return { valid: false, failedField: "steps" };
  for (const step of c.steps) {
    if (!step || typeof step !== "object" || Array.isArray(step)) return { valid: false, failedField: "steps" };
    const s = step as Record<string, unknown>;
    if (typeof s.path !== "string" || !s.path) return { valid: false, failedField: "steps" };
    if (typeof s.operation !== "string" || !s.operation) return { valid: false, failedField: "steps" };
    if (Object.keys(s).some((k) => k !== "path" && k !== "operation")) return { valid: false, failedField: "steps" };
  }
  if (!isNonEmptyStringArray(c.acceptance_criteria)) return { valid: false, failedField: "acceptance_criteria" };
  if (!isNonEmptyStringArray(c.checks)) return { valid: false, failedField: "checks" };
  if (!Array.isArray(c.operations) || c.operations.length === 0) return { valid: false, failedField: "operations" };
  const operationKinds = new Set(["write", "check", "commit", "rebase", "push", "merge", "tag", "release"]);
  for (const operation of c.operations) {
    if (!operation || typeof operation !== "object" || Array.isArray(operation)) return { valid: false, failedField: "operations" };
    const item = operation as Record<string, unknown>;
    if (typeof item.kind !== "string" || !operationKinds.has(item.kind) || typeof item.command !== "string" || !item.command) return { valid: false, failedField: "operations" };
    if (item.confirmation_ref !== undefined && (typeof item.confirmation_ref !== "string" || !item.confirmation_ref)) return { valid: false, failedField: "operations" };
    if (Object.keys(item).some((key) => !["kind", "command", "confirmation_ref"].includes(key))) return { valid: false, failedField: "operations" };
  }
  const operationSet = new Set((c.operations as Array<{ kind: string }>).map(({ kind }) => kind));
  for (const required of ["commit", "rebase", "push", "merge", "tag", "release"])
    if (!operationSet.has(required)) return { valid: false, failedField: "operations" };
  if (!c.confirmations || typeof c.confirmations !== "object" || Array.isArray(c.confirmations)) return { valid: false, failedField: "confirmations" };
  const confirmations = c.confirmations as Record<string, unknown>;
  if (typeof confirmations.execution !== "string" || !confirmations.execution) return { valid: false, failedField: "confirmations" };
  if (operationSet.has("push") || operationSet.has("merge") || operationSet.has("tag") || operationSet.has("release"))
    if (typeof confirmations.publication !== "string" || !confirmations.publication) return { valid: false, failedField: "confirmations" };
  if (operationSet.has("rebase"))
    if (typeof confirmations.history_rewrite !== "string" || !confirmations.history_rewrite) return { valid: false, failedField: "confirmations" };
  if (Object.keys(confirmations).some((key) => !["execution", "publication", "history_rewrite"].includes(key))) return { valid: false, failedField: "confirmations" };
  if (!c.boundaries || typeof c.boundaries !== "object" || Array.isArray(c.boundaries)) return { valid: false, failedField: "boundaries" };
  const b = c.boundaries as Record<string, unknown>;
  if (!isNonEmptyStringArray(b.forbidden_paths) || typeof b.scope !== "string" || !b.scope) return { valid: false, failedField: "boundaries" };
  if (Object.keys(b).some((k) => k !== "forbidden_paths" && k !== "scope")) return { valid: false, failedField: "boundaries" };

  const writeSet = c.write_set as string[];
  const forbiddenPaths = b.forbidden_paths as string[];
  const stepPaths = (c.steps as Array<{ path: string }>).map((s) => s.path);
  const markerPaths = (c.control_markers as Array<{ path: string }>).map((m) => m.path);
  const referenced = new Set([...stepPaths, ...markerPaths]);
  if (![...referenced].every((p) => writeSet.includes(p))) return { valid: false, failedField: "steps" };
  if (writeSet.some((p) => forbiddenPaths.includes(p))) return { valid: false, failedField: "boundaries" };
  if (!writeSet.every((path) => stepPaths.includes(path))) return { valid: false, failedField: "steps" };

  return { valid: true, card: c as ExecutionCard };
}

type ReceiptContext = {
  task?: string;
  requirements?: string[];
  card?: unknown;
};

export class ExecutionCardLifecycle {
  #status: ExecutionCardStatus = "READY";
  #cardID: string;
  #revision: number;

  constructor(card: unknown) {
    const result = validateExecutionCard(card);
    if (!result.valid) throw new Error(`Invalid execution card: ${result.failedField}`);
    this.#cardID = result.card.card_id;
    this.#revision = result.card.revision;
  }

  get status(): ExecutionCardStatus { return this.#status; }
  get card_id(): string { return this.#cardID; }
  get revision(): number { return this.#revision; }

  transition(status: ExecutionCardStatus, identity: { card_id: string; revision: number }): ExecutionCardStatus {
    if (identity.card_id !== this.#cardID || identity.revision !== this.#revision) throw new Error("Execution card identity is stale");
    const allowed: Record<ExecutionCardStatus, readonly ExecutionCardStatus[]> = {
      READY: ["RUNNING", "CANCELLED"],
      RUNNING: ["COMPLETED", "BLOCKED", "FAILED", "REJECTED_PLAN", "CANCELLED"],
      COMPLETED: ["APPROVED", "CHANGES_REQUIRED"],
      BLOCKED: [], FAILED: [], REJECTED_PLAN: [], APPROVED: [], CHANGES_REQUIRED: [], CANCELLED: [],
    };
    if (!allowed[this.#status].includes(status)) throw new Error(`Invalid execution-card transition: ${this.#status} -> ${status}`);
    this.#status = status;
    return this.#status;
  }
}

export class RoutingGate {
  #receipts = new Map<string, { decision: RoutingDecision; taskDigest: string; requirementsDigest: string; cardDigest?: string; expiresAt: number }>();
  #active = new Map<string, { agent: string; card?: ExecutionCard; lifecycle?: ExecutionCardLifecycle; expiresAt: number }>();
  #ttlMs = 10 * 60 * 1000;

  preview(input: RoutingInput): RoutingDecision {
    return resolveRouting(input);
  }

  dispatch(input: RoutingInput, provided: unknown): RoutingDecision {
    const decision = resolveRouting(input);
    if (!provided || typeof provided !== "object" || stable(provided) !== stable(decision)) throw new Error("Routing decision is stale; request a new preview");
    if (decision.status !== "selected" || !decision.agent) throw new Error("Routing escalated; no agent was dispatched");
    return decision;
  }

  grant(sessionID: string, decision: RoutingDecision, context?: ReceiptContext): RoutingReceipt {
    const now = Date.now();
    const taskDigest = context?.task === undefined ? decision.task_digest : digest(context.task);
    const requirementsDigest = context?.requirements === undefined ? decision.requirements_digest : digest(context.requirements);
    const cardDigest = context?.card === undefined ? decision.execution_card_digest : digest(context.card);
    const receiptBase = {
      schema_version: 1 as const,
      task_digest: taskDigest,
      requirements_digest: requirementsDigest,
      destination: decision.category,
      agent: decision.agent!,
      card_digest: cardDigest ?? null,
      host_inventory_revision: decision.host_inventory_revision,
      expires_at: new Date(now + this.#ttlMs).toISOString(),
      nonce: createHash("sha256").update(`${sessionID}:${now}:${decision.decision_digest}`).digest("hex"),
    };
    const receipt: RoutingReceipt = { ...receiptBase, receipt_digest: digest(receiptBase) };
    this.#receipts.set(sessionID, {
      decision,
      taskDigest,
      requirementsDigest,
      cardDigest,
      expiresAt: Date.parse(receipt.expires_at),
    });
    return receipt;
  }

  cancel(sessionID: string): void { this.#receipts.delete(sessionID); this.#active.delete(sessionID); }

  consume(sessionID: string, agent: string, context?: ReceiptContext): void {
    const receipt = this.#receipts.get(sessionID);
    if (!receipt) throw new Error("Native Task requires an active routing receipt; use the route tool");
    if (receipt.decision.agent !== agent) throw new Error("Native Task agent does not match the active routing receipt");
    if (Date.now() > receipt.expiresAt) throw new Error("Routing receipt has expired; request a new preview");
    if (context) {
      const taskDigest = digest(context.task ?? "");
      if (taskDigest !== receipt.taskDigest) throw new Error("Routing receipt task does not match the active routing receipt");
      const requirementsDigest = digest(context.requirements ?? []);
      if (requirementsDigest !== receipt.requirementsDigest) throw new Error("Routing receipt requirements do not match the active routing receipt");
      const cardDigest = context.card !== undefined ? digest(context.card) : undefined;
      if (cardDigest !== receipt.cardDigest) throw new Error("Routing receipt execution card does not match the active routing receipt");
    }
    this.#receipts.delete(sessionID);
    const validatedCard = context?.card === undefined ? undefined : validateExecutionCard(context.card);
    const card = validatedCard?.valid ? validatedCard.card : undefined;
    const lifecycle = card ? new ExecutionCardLifecycle(card) : undefined;
    if (lifecycle) lifecycle.transition("RUNNING", { card_id: card!.card_id, revision: card!.revision });
    this.#active.set(sessionID, { agent, card, lifecycle, expiresAt: receipt.expiresAt });
  }

  complete(sessionID: string, agent: string, output: unknown): void {
    const active = this.#active.get(sessionID);
    if (!active || active.agent !== agent) throw new Error("Task result has no matching active routing receipt");
    if (Date.now() > active.expiresAt) throw new Error("Task result routing receipt has expired");
    const report = output && typeof output === "object" ? output as Record<string, unknown> : undefined;
    const value = report?.[`${agent}_report`] ?? report?.report;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Task result is missing a structured agent report");
    const result = value as Record<string, unknown>;
    validateAgentReport(agent, report, active.card);
    if (active.card && (result.card_id !== active.card.card_id || result.revision !== active.card.revision)) throw new Error("Task result does not match the active execution card");
    const status = result.status;
    const allowed = agent === "worker" ? ["COMPLETED", "BLOCKED", "FAILED", "REJECTED_PLAN"] : agent === "critic" ? ["APPROVED", "CHANGES_REQUIRED"] : undefined;
    if (allowed && (typeof status !== "string" || !allowed.includes(status))) throw new Error("Task result has an invalid machine transition");
    if (active.lifecycle && status === "COMPLETED") active.lifecycle.transition("COMPLETED", { card_id: active.card!.card_id, revision: active.card!.revision });
    if (active.lifecycle && (status === "BLOCKED" || status === "FAILED" || status === "REJECTED_PLAN"))
      active.lifecycle.transition(status, { card_id: active.card!.card_id, revision: active.card!.revision });
    if (active.lifecycle && (status === "APPROVED" || status === "CHANGES_REQUIRED")) {
      active.lifecycle.transition("COMPLETED", { card_id: active.card!.card_id, revision: active.card!.revision });
      active.lifecycle.transition(status, { card_id: active.card!.card_id, revision: active.card!.revision });
    }
    this.#active.delete(sessionID);
  }
}
