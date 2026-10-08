import { FIXED_AGENT_ROLES, type AgentInventory, type AgentProfilePlan } from "./agent-profiles.js";
import { CATALOG } from "./catalog.js";
import type { ConfigSetupPlan } from "./config-setup.js";
import type { Plan as InstallerPlan } from "./installer.js";
import type { ReconcilePlan } from "./reconcile.js";
import type { DoctorReport } from "./doctor.js";
import type { Scope } from "./lifecycle.js";

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

// ANSI styling is opt-in per call so tests can force either form; the CLI uses
// the environment default, which disables color on non-TTY output and NO_COLOR.
export function colorEnabled(
  env: NodeJS.ProcessEnv = process.env,
  isTTY: boolean | undefined = process.stdout.isTTY,
): boolean {
  if (env.NO_COLOR !== undefined && env.NO_COLOR !== "") return false;
  if (env.FORCE_COLOR !== undefined && env.FORCE_COLOR !== "") return env.FORCE_COLOR !== "0";
  return Boolean(isTTY);
}

function paint(color: boolean, code: string | undefined, text: string): string {
  return color && code ? `\u001b[${code}m${text}\u001b[0m` : text;
}

// One glyph per operation keeps the summary readable even with color off; the
// matching ANSI code is applied only when color is enabled.
const OPERATION_STYLES: Record<(typeof OPERATIONS)[number], { symbol: string; code?: string }> = {
  create: { symbol: "▸", code: "32" },
  update: { symbol: "●", code: "36" },
  remove: { symbol: "■", code: "31" },
  "archive-pending": { symbol: "■", code: "33" },
  conflict: { symbol: "✗", code: "31" },
  missing: { symbol: "✗", code: "33" },
  unchanged: { symbol: "◻", code: "2" },
};

const MARKS = {
  ok: "✓",
  bad: "✗",
  change: "▸",
  item: "●",
  pending: "◻",
};

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
      reconcile: "Repair selected agents",
    } as const
  )[action];
}

function operationSummary(operations: readonly DisplayOperation[], color: boolean): string {
  return OPERATIONS.map((operation) => {
    const count = operations.filter((item) => item.operation === operation).length;
    if (!count) return undefined;
    const spec = OPERATION_STYLES[operation];
    return paint(color, spec.code, `${spec.symbol} ${operation} ${count}`);
  })
    .filter(Boolean)
    .join(", ");
}

function shortPath(path: string, group: (typeof GROUPS)[number]): string {
  if (group === "State") return terminalSafe(path);
  const value = path.slice(path.indexOf("/") + 1);
  return terminalSafe(value.endsWith(".md") || value.endsWith(".js") ? value.slice(0, -3) : value);
}

function detailLines(operations: readonly DisplayOperation[], color: boolean): string[] {
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
      const spec = OPERATION_STYLES[operation];
      lines.push(
        `  ${paint(color, spec.code, spec.symbol)} ${group}/${operation}: ${visible.join(", ")}${rest ? ` (+${rest} more)` : ""}`,
      );
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
  options: { applied: boolean; applyHint?: string; hint?: string; color?: boolean },
): string {
  const color = options.color ?? colorEnabled();
  const version = "package_version" in plan ? ` @kisev/agentomatic ${plan.package_version}` : "";
  const lines = [
    paint(color, "1", `${actionName(plan.action)}${version} (${plan.scope})`),
    `Target: ${terminalSafe(plan.root)}`,
    ...("selection" in plan
      ? [
          `Core integration: ${plan.selection.core_activation ? "active" : "not selected"}`,
          `Plugins: ${plan.selection.plugins.length ? plan.selection.plugins.join(", ") : "none"}`,
        ]
      : []),
    "",
    paint(color, "1", options.applied ? "Applied changes:" : "Planned changes:"),
  ];
  for (const group of GROUPS) {
    const operations = plan.operations.filter((item) => groupFor(item.path) === group);
    if (operations.length)
      lines.push(`  ${paint(color, "1", group)}: ${operationSummary(operations, color)}`);
  }
  const migration = migrationSummary(plan.operations);
  if (migration) lines.push(migration);
  const details = detailLines(plan.operations, color);
  if (details.length) lines.push("", paint(color, "1", "Details:"), ...details);
  const conflicts = plan.operations.filter((item) => item.operation === "conflict").length;
  lines.push(
    "",
    `Conflicts: ${conflicts ? paint(color, "31", `${MARKS.bad} ${conflicts}`) : paint(color, "32", `${MARKS.ok} none`)}`,
  );
  const restartNote = "restart the host session so the deployed roles and settings load";
  lines.push(
    plan.requires_restart
      ? `${options.applied ? "Restart required" : "Restart after apply"}: ${paint(color, "33", `${MARKS.ok} yes`)} — ${restartNote}`
      : `${options.applied ? "Restart required" : "Restart after apply"}: ${paint(color, "2", `${MARKS.pending} no`)}`,
  );
  if (!options.applied && options.applyHint)
    lines.push(
      "",
      paint(color, "1", "Apply (repeat non-interactively):"),
      `  ${options.applyHint}`,
    );
  if (options.applied && options.hint)
    lines.push("", paint(color, "1", "Next:"), `  ${options.hint}`);
  return `${lines.join("\n")}\n`;
}

export function renderConfigNoop(plan: ConfigSetupPlan, color = colorEnabled()): string {
  return [
    paint(
      color,
      "1",
      `Integration configuration @kisev/agentomatic ${plan.package_version} (${plan.scope})`,
    ),
    `Root: ${terminalSafe(plan.root)}`,
    "",
    paint(color, "32", `${MARKS.ok} No configuration changes are required.`),
    "",
  ].join("\n");
}

export function renderConfigSetup(
  plan: ConfigSetupPlan,
  options: { applied: boolean; applyHint?: string; hint?: string; color?: boolean },
): string {
  const color = options.color ?? colorEnabled();
  const lines = [
    paint(
      color,
      "1",
      `Integration configuration @kisev/agentomatic ${plan.package_version} (${plan.scope})`,
    ),
    `Root: ${terminalSafe(plan.root)}`,
    "",
  ];
  if (plan.targets.length)
    lines.push(
      paint(color, "1", "Targets:"),
      ...plan.targets.map(
        (item) =>
          `  ${item.target}: ${terminalSafe(item.path)} ${paint(color, "2", `(${item.exists ? "existing" : "new"})`)}`,
      ),
    );
  else lines.push("Targets: none");
  const fragments = plan.operations.filter((item) => item.fragment !== "file");
  if (plan.dependency)
    lines.push(
      "",
      `Dependency: ${plan.dependency.status} ${plan.dependency.name}@${plan.dependency.version}`,
      "  Provisioning may access npm and update package.json, package-lock.json, and node_modules.",
    );
  if (fragments.length) {
    lines.push(
      "",
      paint(color, "1", options.applied ? "Applied fragments:" : "Planned fragments:"),
      ...fragments.map((item) => {
        const spec = OPERATION_STYLES[item.operation];
        const badge = spec
          ? `${paint(color, spec.code, spec.symbol)} `
          : `${paint(color, "33", MARKS.change)} `;
        return `  ${badge}${item.target}/${item.fragment}: ${item.operation}${item.reason ? ` (${terminalSafe(item.reason)})` : ""}`;
      }),
    );
  }
  if (plan.skipped_fragments.length)
    lines.push(
      "",
      paint(color, "1", "Skipped fragments:"),
      ...plan.skipped_fragments.map((item) => `  ${item.fragment}: ${terminalSafe(item.reason)}`),
    );
  const conflicts = plan.operations.filter((item) => item.operation === "conflict").length;
  lines.push(
    "",
    `Conflicts: ${conflicts ? paint(color, "31", `${MARKS.bad} ${conflicts}`) : paint(color, "32", `${MARKS.ok} none`)}`,
  );
  lines.push(
    plan.requires_restart
      ? `${options.applied ? "Restart required" : "Restart after apply"}: ${paint(color, "33", `${MARKS.ok} yes`)} — restart the host session so the merged presets load`
      : `${options.applied ? "Restart required" : "Restart after apply"}: ${paint(color, "2", `${MARKS.pending} no`)}`,
  );
  if (!options.applied) {
    if (!plan.confirmable)
      lines.push("", paint(color, "32", "No configuration changes are required."));
    else if (options.applyHint)
      lines.push(
        "",
        paint(color, "1", "Apply (repeat non-interactively):"),
        `  ${options.applyHint}`,
      );
  }
  if (options.applied && options.hint)
    lines.push("", paint(color, "1", "Next:"), `  ${options.hint}`);
  return `${lines.join("\n")}\n`;
}

function table(rows: string[][], color = false): string[] {
  const widths = rows[0].map((_, column) =>
    Math.max(...rows.map((row) => row[column]?.length ?? 0)),
  );
  return rows.map((row, index) =>
    paint(
      color && index === 0,
      "1",
      row
        .map((value, column) => value.padEnd(widths[column]))
        .join("  ")
        .trimEnd(),
    ),
  );
}

export function renderCriticsTable(inventory: AgentInventory, color = colorEnabled()): string {
  // The panel keeps the package-owned fixed critic (`critic`) apart from the
  // additional `critic-*` pool entries and points at the canonical overview.
  const critics = inventory.profiles.filter(
    (profile) =>
      profile.ownership !== "user-owned" &&
      (profile.name === "critic" || profile.name.startsWith("critic-")),
  );
  if (!critics.length) return "Critics:\n  No critics\n";
  const pool = critics.filter((profile) => profile.name !== "critic");
  const rows = [
    ["NAME", "MODEL", "VARIANT", "PROVIDER"],
    ...critics.map((profile) => [
      `${profile.name === "critic" ? MARKS.item : MARKS.change} ${terminalSafe(profile.name)}`,
      terminalSafe(profile.model ?? "default (host)"),
      terminalSafe(profile.variant ?? "-"),
      terminalSafe(profile.model?.split("/", 1)[0] ?? "-"),
    ]),
  ];
  const head = paint(color, "1", "Critics:");
  return (
    `${head}\n${table(rows, color).join("\n")}\n` +
    `Pool: additional critics are optional specialist profiles (` +
    `${pool.length ? pool.map((profile) => terminalSafe(profile.name)).join(", ") : "none"}); ` +
    "the fixed critic always deploys with the package.\n"
  );
}

export function renderFixedRoles(inventory: AgentInventory, color = colorEnabled()): string {
  const roles = inventory.profiles.filter(
    (profile) =>
      profile.ownership !== "user-owned" &&
      FIXED_AGENT_ROLES.includes(profile.name as (typeof FIXED_AGENT_ROLES)[number]),
  );
  const rows = [
    ["NAME", "MODEL", "VARIANT"],
    ...roles.map((profile) => [
      `${MARKS.item} ${terminalSafe(profile.name)}`,
      terminalSafe(profile.model ?? "default (host)"),
      terminalSafe(profile.variant ?? "-"),
    ]),
  ];
  return [
    paint(
      color,
      "1",
      "Fixed roles (all six belong to the package; models and critic composition: agentomatic configure agent):",
    ),
    ...table(rows, color),
    "",
  ].join("\n");
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
  return commandLine(["npx", "--yes", `@kisev/agentomatic@${CATALOG.version}`, ...arguments_]);
}

function commandLine(arguments_: readonly string[]): string {
  return arguments_
    .map((value) =>
      /^[A-Za-z0-9_./:@=-]+$/.test(value) ? value : `'${value.replaceAll("'", `'"'"'`)}'`,
    )
    .join(" ");
}

export function scopeArguments(scope: Scope): [] | ["--global"] {
  return scope === "global" ? ["--global"] : [];
}

export function renderReconcile(
  plan: ReconcilePlan,
  options: { applied: boolean; applyHint?: string },
): string {
  const lines = [
    `Cleanup retired components (${plan.scope})`,
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
    `  operations: ${plan.operations.length}`,
  ];
  if (plan.retired.length)
    lines.push(
      "",
      "Retired:",
      ...plan.retired.slice(0, 20).map((entry) => `  ${terminalSafe(entry.path)}`),
    );
  if (plan.renamed.length)
    lines.push(
      "",
      "Renamed:",
      ...plan.renamed.map(
        (entry) =>
          `  ${terminalSafe(entry.path)} -> ${terminalSafe(entry.replacement ?? "unknown")}`,
      ),
    );
  if (plan.unknown.length)
    lines.push(
      "",
      "Unknown (preserved):",
      ...plan.unknown.map(
        (entry) => `  ${terminalSafe(entry.path)} (${terminalSafe(entry.reason)})`,
      ),
    );
  if (plan.operations.length)
    lines.push(
      "",
      "Operations:",
      ...plan.operations.map((entry) => `  ${entry.operation}: ${terminalSafe(entry.path)}`),
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
    const blocked = plan.modified_managed.length > 0 || plan.conflicts.length > 0;
    if (blocked) {
      lines.push("", "Blocked:");
      if (plan.modified_managed.length)
        lines.push(
          "  Modified managed bytes are preserved. Restore recorded bytes before retrying cleanup.",
          `  Inspect: ${shellCommand(["doctor", ...scopeArguments(plan.scope)])}`,
        );
      if (plan.conflicts.length)
        lines.push("  Manually resolve every ownership conflict listed above before reconciling.");
    } else if (!plan.confirmable) {
      lines.push("", "No cleanup changes are required.");
    } else if (options.applyHint) {
      lines.push("", "Apply (repeat non-interactively):", `  ${options.applyHint}`);
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
    next.add(
      shellCommand(["maintenance", "cleanup", ...scopeArguments(report.scope), "--dry-run"]),
    );
  }
  if (actionable.some((item) => item.id.startsWith("assets."))) {
    next.add(shellCommand(["install", ...scopeArguments(report.scope), "--dry-run"]));
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
