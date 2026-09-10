import { validateExecutionCard, type ExecutionCard } from "./routing.js";

export const CONTRACT_SCHEMA_VERSION = 1 as const;
export type AgentReportStatus =
  "COMPLETED" | "BLOCKED" | "FAILED" | "REJECTED_PLAN" | "APPROVED" | "CHANGES_REQUIRED";
export type MapperReport = {
  mapper_report: {
    schema_version: 1;
    paths: Array<Record<string, string>>;
    callers: Array<Record<string, string>>;
    tests: Array<Record<string, string>>;
    patterns: Array<Record<string, string>>;
    evidence_gaps: string[];
  };
};
export type WorkerReport = {
  worker_report: {
    schema_version: 1;
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
    schema_version: 1;
    status: "APPROVED" | "CHANGES_REQUIRED";
    target: string;
    findings: Array<Record<string, unknown>>;
    evidence: string[];
    checks: string[];
    risks: string[];
  };
};
export type CriticReport = {
  critic_report: {
    schema_version: 1;
    status: "APPROVED" | "CHANGES_REQUIRED";
    card_id: string;
    revision: number;
    findings: Array<Record<string, unknown>>;
    evidence: string[];
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
  const reportKey = agent === "architect" ? "execution_card" : `${agent}_report`;
  if (Object.keys(report).length !== 1 || !(reportKey in report))
    throw new Error(`${agent} report has an invalid envelope`);
  const value = report[reportKey];
  if (!object(value)) throw new Error(`missing ${agent}_report`);
  if (value.schema_version !== CONTRACT_SCHEMA_VERSION)
    throw new Error(`${agent} report schema version is unsupported`);
  if (agent === "mapper") {
    for (const key of ["paths", "callers", "tests", "patterns"])
      if (!Array.isArray(value[key])) throw new Error(`mapper report field is invalid: ${key}`);
    if (
      Object.keys(value).some(
        (key) =>
          !["schema_version", "paths", "callers", "tests", "patterns", "evidence_gaps"].includes(
            key,
          ),
      )
    )
      throw new Error("mapper report contains unknown fields");
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
    if (
      Object.keys(value).some(
        (key) =>
          ![
            "schema_version",
            "status",
            "card_id",
            "revision",
            "changed_files",
            "checks",
            "writes_performed",
            "risks",
          ].includes(key),
      )
    )
      throw new Error("worker report contains unknown fields");
    if (
      value.status === "COMPLETED" &&
      (value.writes_performed !== true ||
        (value.checks as Array<Record<string, unknown>>).some((check) => check.status !== "passed"))
    )
      throw new Error("completed worker report has incomplete checks");
    if (card && (value.changed_files as string[]).some((path) => !card.write_set.includes(path)))
      throw new Error("worker report writes outside execution card");
  } else if (agent === "review" || agent === "critic") {
    if (
      !["APPROVED", "CHANGES_REQUIRED"].includes(String(value.status)) ||
      !Array.isArray(value.findings) ||
      (typeof value.target !== "string" && agent === "review")
    )
      throw new Error(`${agent} report is invalid`);
    if (
      agent === "review" &&
      (!Array.isArray(value.checks) ||
        !strings(value.checks) ||
        !strings(value.risks) ||
        !strings(value.evidence) ||
        !value.target)
    )
      throw new Error("review report fields are invalid");
    if (
      agent === "critic" &&
      (typeof value.card_id !== "string" ||
        !Number.isInteger(value.revision) ||
        !strings(value.unrun_checks) ||
        !strings(value.risks) ||
        !strings(value.evidence))
    )
      throw new Error("critic report fields are invalid");
    const allowed =
      agent === "review"
        ? ["schema_version", "status", "target", "findings", "evidence", "checks", "risks"]
        : [
            "schema_version",
            "status",
            "card_id",
            "revision",
            "findings",
            "evidence",
            "unrun_checks",
            "risks",
          ];
    if (Object.keys(value).some((key) => !allowed.includes(key)))
      throw new Error(`${agent} report contains unknown fields`);
  } else throw new Error(`unknown report agent: ${agent}`);
  if (card && (value.card_id !== card.card_id || value.revision !== card.revision))
    throw new Error("agent report does not match execution card");
}
