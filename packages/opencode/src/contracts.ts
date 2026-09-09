import { validateExecutionCard, type ExecutionCard } from "./routing.js";

export const CONTRACT_SCHEMA_VERSION = 1 as const;
export type AgentReportStatus =
  "COMPLETED" | "BLOCKED" | "FAILED" | "REJECTED_PLAN" | "APPROVED" | "CHANGES_REQUIRED";
export type MapperReport = {
  mapper_report: {
    paths: Array<Record<string, string>>;
    callers: Array<Record<string, string>>;
    tests: Array<Record<string, string>>;
    patterns: Array<Record<string, string>>;
    evidence_gaps: string[];
  };
};
export type WorkerReport = {
  worker_report: {
    status: Extract<AgentReportStatus, "COMPLETED" | "BLOCKED" | "FAILED" | "REJECTED_PLAN">;
    card_id: string | null;
    revision: number | null;
    changed_files: string[];
    checks: Array<{ command: string; status: string }>;
    writes_performed: boolean;
    risks: string[];
  };
};
export type ReviewReport = {
  review_report: {
    status: "APPROVED" | "CHANGES_REQUIRED";
    target: string;
    findings: Array<Record<string, unknown>>;
    checks: string[];
    risks: string[];
  };
};
export type CriticReport = {
  critic_report: {
    status: "APPROVED" | "CHANGES_REQUIRED";
    card_id: string;
    revision: number;
    findings: Array<Record<string, unknown>>;
    unrun_checks: string[];
    risks: string[];
  };
};

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function validateAgentReport(agent: string, report: unknown, card?: ExecutionCard): void {
  if (!object(report)) throw new Error("agent report must be an object");
  const value = report[`${agent}_report`];
  if (!object(value)) throw new Error(`missing ${agent}_report`);
  if (agent === "mapper") {
    for (const key of ["paths", "callers", "tests", "patterns"])
      if (!Array.isArray(value[key])) throw new Error(`mapper report field is invalid: ${key}`);
    if (!strings(value.evidence_gaps)) throw new Error("mapper report evidence_gaps is invalid");
  } else if (agent === "architect") {
    if (value.status === "NEEDS_EVIDENCE") return;
    const result = validateExecutionCard(value);
    if (!result.valid)
      throw new Error(`architect execution card is invalid: ${result.failedField}`);
  } else if (agent === "worker") {
    if (
      !strings(value.changed_files) ||
      !Array.isArray(value.checks) ||
      typeof value.writes_performed !== "boolean" ||
      !strings(value.risks)
    )
      throw new Error("worker report is invalid");
  } else if (agent === "review" || agent === "critic") {
    if (
      !["APPROVED", "CHANGES_REQUIRED"].includes(String(value.status)) ||
      !Array.isArray(value.findings)
    )
      throw new Error(`${agent} report is invalid`);
  } else throw new Error(`unknown report agent: ${agent}`);
  if (card && (value.card_id !== card.card_id || value.revision !== card.revision))
    throw new Error("agent report does not match execution card");
}
