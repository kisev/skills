import type { AgentInventory, AgentProfilePlan } from "./agent-profiles.js";
import type { Plan as InstallerPlan } from "./installer.js";
import type { ReconcilePlan } from "./reconcile.js";
import type { DoctorReport } from "./doctor.js";

type DisplayPlan = InstallerPlan | AgentProfilePlan;
type DisplayOperation = DisplayPlan["operations"][number];

const GROUPS = ["Agents", "Commands", "Plugins", "State"] as const;
const OPERATIONS = [
  "create",
  "update",
  "remove",
  "archive-pending",
  "conflict",
  "missing",
  "unchanged",
] as const;
const UNSAFE_TERMINAL_CHARACTER = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u;

export function terminalSafe(value: string): string {
  return [...value]
    .map((character) => {
      const code = character.codePointAt(0)!;
      const unsafe = character === "\\" || UNSAFE_TERMINAL_CHARACTER.test(character);
      if (!unsafe) return character;
      if (character === "\\") return "\\\\";
      if (character === "\n") return "\\n";
      if (character === "\r") return "\\r";
      if (character === "\t") return "\\t";
      if (code <= 0xff) return `\\x${code.toString(16).padStart(2, "0")}`;
      if (code <= 0xffff) return `\\u${code.toString(16).padStart(4, "0")}`;
      return `\\u{${code.toString(16)}}`;
    })
    .join("");
}

function groupFor(path: string): (typeof GROUPS)[number] {
  if (path.startsWith("agents/")) return "Agents";
  if (path.startsWith("commands/")) return "Commands";
  if (path.startsWith("plugins/")) return "Plugins";
  return "State";
}

function actionName(action: DisplayPlan["action"]): string {
  return (
    {
      install: "Install",
      uninstall: "Uninstall",
      "model-set": "Configure agent model",
      "critic-add": "Add critic",
      "critic-remove": "Remove critic",
      reconcile: "Reconcile agents",
    } as const
  )[action];
}

function operationSummary(operations: readonly DisplayOperation[]): string {
  return OPERATIONS.map((operation) => {
    const count = operations.filter((item) => item.operation === operation).length;
    return count ? `${operation} ${count}` : undefined;
  })
    .filter(Boolean)
    .join(", ");
}

function shortPath(path: string, group: (typeof GROUPS)[number]): string {
  if (group === "State") return terminalSafe(path);
  const value = path.slice(path.indexOf("/") + 1);
  return terminalSafe(value.endsWith(".md") || value.endsWith(".js") ? value.slice(0, -3) : value);
}

function detailLines(operations: readonly DisplayOperation[]): string[] {
  const lines: string[] = [];
  for (const group of GROUPS) {
    const grouped = operations.filter(
      (item) => groupFor(item.path) === group && item.operation !== "unchanged",
    );
    for (const operation of OPERATIONS.filter(
      (value) => value !== "unchanged" && grouped.some((item) => item.operation === value),
    )) {
      const values = grouped
        .filter((item) => item.operation === operation)
        .map((item) =>
          operation === "conflict"
            ? `${shortPath(item.path, group)} (${terminalSafe(item.reason ?? "conflict")})`
            : shortPath(item.path, group),
        );
      const visible = operation === "conflict" ? values : values.slice(0, 8);
      const rest = values.length - visible.length;
      lines.push(`  ${group}/${operation}: ${visible.join(", ")}${rest ? ` (+${rest} more)` : ""}`);
    }
  }
  return lines;
}

function migrationSummary(operations: readonly DisplayOperation[]): string | undefined {
  const count = operations.filter((item) => item.reason === "v1.0.0 ownership transfer").length;
  return count
    ? `  Ownership migration: ${count} agent${count === 1 ? "" : "s"} from v1.0.0`
    : undefined;
}

export function renderPlan(
  plan: DisplayPlan,
  options: { applied: boolean; confirmationCommand?: string },
): string {
  const version =
    "package_version" in plan ? ` @kisev/skills-opencode ${plan.package_version}` : "";
  const lines = [
    `${actionName(plan.action)}${version} (${plan.scope})`,
    `Target: ${terminalSafe(plan.root)}`,
    ...("selection" in plan
      ? [
          `Core integration: ${plan.selection.core_activation ? "active" : "not selected"}`,
          `Plugins: ${plan.selection.plugins.length ? plan.selection.plugins.join(", ") : "none"}`,
        ]
      : []),
    "",
    options.applied ? "Applied changes:" : "Planned changes:",
  ];
  for (const group of GROUPS) {
    const operations = plan.operations.filter((item) => groupFor(item.path) === group);
    if (operations.length) lines.push(`  ${group}: ${operationSummary(operations)}`);
  }
  const migration = migrationSummary(plan.operations);
  if (migration) lines.push(migration);
  const details = detailLines(plan.operations);
  if (details.length) lines.push("", "Details:", ...details);
  const conflicts = plan.operations.filter((item) => item.operation === "conflict").length;
  lines.push("", `Conflicts: ${conflicts || "none"}`);
  lines.push(
    options.applied
      ? `Restart required: ${plan.requires_restart ? "yes" : "no"}`
      : `Restart after apply: ${plan.requires_restart ? "yes" : "no"}`,
  );
  if (!options.applied) {
    if (plan.receipt_expires_at) lines.push(`Confirmation expires: ${plan.receipt_expires_at}`);
    lines.push(`Digest: ${plan.digest}`);
    if (options.confirmationCommand) lines.push("", "Apply:", `  ${options.confirmationCommand}`);
  }
  return `${lines.join("\n")}\n`;
}

function table(rows: string[][]): string[] {
  const widths = rows[0].map((_, column) =>
    Math.max(...rows.map((row) => row[column]?.length ?? 0)),
  );
  return rows.map((row) =>
    row
      .map((value, column) => value.padEnd(widths[column]))
      .join("  ")
      .trimEnd(),
  );
}

export function renderInventory(inventory: AgentInventory): string {
  const rows = [
    ["NAME", "MODEL", "VARIANT", "OWNER", "STATE"],
    ...inventory.profiles.map((profile) => [
      terminalSafe(profile.name),
      terminalSafe(profile.model ?? "default"),
      terminalSafe(profile.variant ?? "-"),
      profile.ownership,
      profile.state,
    ]),
  ];
  return `${[
    `OpenCode agents (${inventory.scope})`,
    `Target: ${terminalSafe(inventory.root)}`,
    "",
    ...table(rows),
    "",
    `Critic pool: ${inventory.critic_pool.map(terminalSafe).join(", ")}`,
    `Collisions: ${inventory.collisions.length ? inventory.collisions.map(terminalSafe).join(", ") : "none"}`,
    `Drift: ${inventory.drift.length ? inventory.drift.map(terminalSafe).join(", ") : "none"}`,
  ].join("\n")}\n`;
}

export function shellCommand(arguments_: readonly string[]): string {
  return ["npm", "exec", "--", "skills-opencode", ...arguments_]
    .map((value) =>
      /^[A-Za-z0-9_./:@=-]+$/.test(value) ? value : `'${value.replaceAll("'", `'"'"'`)}'`,
    )
    .join(" ");
}

export function renderReconcile(
  plan: ReconcilePlan,
  options: { applied: boolean; confirmationCommand?: string },
): string {
  const lines = [
    `Reconcile (${plan.scope})`,
    `Target: ${terminalSafe(plan.root)}`,
    "",
    options.applied ? "Applied retired assets:" : "Planned retired assets:",
    `  current: ${plan.current.length}`,
    `  retired: ${plan.retired.length}`,
    `  renamed: ${plan.renamed.length}`,
    `  modified-managed: ${plan.modified_managed.length}`,
    `  user-owned: ${plan.user_owned.length}`,
    `  unknown: ${plan.unknown.length}`,
    `  conflicts: ${plan.conflicts.length}`,
    `  diagnostic-state-only: ${plan.diagnostic_state_only.length}`,
  ];
  if (plan.retired.length)
    lines.push(
      "",
      "Retired:",
      ...plan.retired.slice(0, 20).map((entry) => `  ${terminalSafe(entry.path)}`),
    );
  if (plan.conflicts.length)
    lines.push(
      "",
      "Conflicts:",
      ...plan.conflicts.map(
        (entry) => `  ${terminalSafe(entry.path)} (${terminalSafe(entry.reason)})`,
      ),
    );
  if (plan.modified_managed.length)
    lines.push(
      "",
      "Modified managed:",
      ...plan.modified_managed.map(
        (entry) => `  ${terminalSafe(entry.path)} (${terminalSafe(entry.reason)})`,
      ),
    );
  if (!options.applied) {
    lines.push("", `Digest: ${plan.digest}`);
    if (plan.receipt_expires_at) lines.push(`Confirmation expires: ${plan.receipt_expires_at}`);
    const blocked = plan.modified_managed.length > 0 || plan.conflicts.length > 0;
    if (blocked) {
      lines.push("", "Blocked:");
      if (plan.modified_managed.length)
        lines.push(
          `  Update managed assets first: ${shellCommand(["install", "--scope", plan.scope, "--dry-run"])}`,
          "  Apply the exact confirmation command from that installer preview, then build a new reconcile preview.",
        );
      if (plan.conflicts.length)
        lines.push("  Manually resolve every ownership conflict listed above before reconciling.");
    } else if (options.confirmationCommand) {
      lines.push("", "Apply:", `  ${options.confirmationCommand}`);
    }
  }
  return `${lines.join("\n")}\n`;
}

export function renderDoctor(report: DoctorReport): string {
  const actionable = report.checks.filter(
    (item) => item.status === "fail" || item.status === "warn",
  );
  const next = new Set(actionable.flatMap((item) => item.remediation ?? []));
  if (report.conflicts.length) {
    next.add(`npm exec -- skills-opencode reconcile --scope ${report.scope} --dry-run`);
  }
  if (actionable.some((item) => item.id.startsWith("assets."))) {
    next.add(`npm exec -- skills-opencode install --scope ${report.scope} --dry-run`);
  }
  const lines = [
    `Doctor TLDR: ${report.status} (${report.scope})`,
    `Package: ${report.versions.package ?? "unavailable"}  Catalog: ${report.versions.catalog}  OpenCode: ${report.versions.opencode ?? "unavailable"}`,
    `Checks: pass ${report.counts.pass}, warn ${report.counts.warn}, fail ${report.counts.fail}, incomplete ${report.counts.incomplete}`,
    "Mutations: no",
  ];
  if (actionable.length)
    lines.push(
      "",
      "Actionable findings:",
      ...actionable.map((item) => `  ${terminalSafe(item.id)}: ${terminalSafe(item.summary)}`),
    );
  if (report.conflicts.length)
    lines.push(
      "",
      "Conflicts:",
      ...report.conflicts.map(
        (item) =>
          `  ${terminalSafe(String(item.path ?? "unknown"))} (${terminalSafe(String(item.reason ?? "conflict"))})`,
      ),
    );
  if (next.size)
    lines.push("", "Next commands:", ...[...next].map((item) => `  ${terminalSafe(item)}`));
  return `${lines.join("\n")}\n`;
}
