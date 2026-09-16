#!/usr/bin/env node
import {
  AgentProfileError,
  applyAgentProfileChange,
  availableModels,
  availableModelVariants,
  FIXED_AGENT_ROLES,
  listAgentProfiles,
  previewAgentProfileChange,
  validateAgentName,
  validateModel,
  validateVariant,
  type AgentProfileRequest,
} from "./agent-profiles.js";
import {
  renderDoctor,
  renderInventory,
  renderPlan,
  renderReconcile,
  scopeArguments,
  shellCommand,
  terminalSafe,
} from "./cli-output.js";
import { collectDoctorFacts, doctorExitCode } from "./doctor.js";
import { CATALOG } from "./catalog.js";
import {
  apply,
  defaultSelection,
  InstallerError,
  normalizeSelection,
  preview,
  SELECTABLE_PLUGINS,
  SKILL_COMMANDS,
  type Action,
  type InstallerSelection,
} from "./installer.js";
import { LifecycleError, type Scope } from "./lifecycle.js";
import { skillsInstallerSpec } from "./package-metadata.js";
import { applyReconcile, previewReconcile } from "./reconcile.js";
import { promptText, selectOption, selectOptions } from "./terminal-wizard.js";

type Options = {
  scope: Scope;
  global: boolean;
  dryRun: boolean;
  json: boolean;
  confirm?: string;
  provider?: string;
  model?: string;
  variant?: string | null;
  name?: string;
  commands?: string[];
  agents?: string[];
  plugins?: string[];
  selectionFlag: boolean;
};

function parseOptions(values: string[]): Options {
  const options: Options = {
    scope: "project",
    global: false,
    dryRun: false,
    json: false,
    selectionFlag: false,
  };
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith("--")) {
      if (options.name) throw new InstallerError("invalid_input", `Unexpected argument: ${value}`);
      options.name = value;
    } else if (value === "--global") {
      if (options.global)
        throw new InstallerError("invalid_input", "--global may be supplied once");
      options.global = true;
      options.scope = "global";
    } else if (value === "--dry-run") {
      if (options.dryRun)
        throw new InstallerError("invalid_input", "--dry-run may be supplied once");
      options.dryRun = true;
    } else if (value === "--confirm") {
      if (options.confirm)
        throw new InstallerError("invalid_input", "--confirm may be supplied once");
      options.confirm = values[++index];
      if (!options.confirm)
        throw new InstallerError("invalid_input", "--confirm requires a digest");
    } else if (value === "--provider") {
      options.provider = values[++index];
      if (!options.provider)
        throw new InstallerError("invalid_input", "--provider requires a value");
    } else if (value === "--model") {
      options.model = values[++index];
      if (!options.model) throw new InstallerError("invalid_input", "--model requires a value");
    } else if (value === "--variant") {
      options.variant = values[++index];
      if (!options.variant) throw new InstallerError("invalid_input", "--variant requires a value");
    } else if (value === "--clear-variant") {
      if (options.variant !== undefined)
        throw new InstallerError("invalid_input", "Use only one variant option");
      options.variant = null;
    } else if (value === "--json") {
      if (options.json) throw new InstallerError("invalid_input", "--json may be supplied once");
      options.json = true;
    } else if (["--commands", "--skill-commands", "--agents", "--plugins"].includes(value)) {
      const raw = values[++index];
      if (!raw)
        throw new InstallerError("invalid_input", `${value} requires a comma-separated value`);
      const target =
        value === "--agents" ? "agents" : value === "--plugins" ? "plugins" : "commands";
      const names =
        raw === "none"
          ? []
          : raw
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean);
      options.selectionFlag = true;
      if (value === "--skill-commands") {
        options.commands = [...(options.commands ?? []), ...names];
      } else {
        options[target] = names;
      }
    } else {
      throw new InstallerError("invalid_input", `Unknown argument: ${value}`);
    }
  }
  return options;
}

function helpRows(rows: readonly (readonly [string, string])[]): string[] {
  const width = Math.max(...rows.map(([label]) => label.length));
  return rows.map(([label, description]) => `  ${label.padEnd(width)}  ${description}`);
}

function rootHelp(): string {
  return [
    `skills-opencode ${CATALOG.version}`,
    "",
    "Manage OpenCode integration assets, agents, diagnostics, and migration state.",
    `Portable Agent Skills are installed separately with npx --yes ${skillsInstallerSpec()}.`,
    "",
    "Usage:",
    "  skills-opencode <command> [options]",
    "  Add --help after any command or command group for focused guidance.",
    "",
    "Commands:",
    ...helpRows([
      ["install", "Select and deploy skill commands, agents, and plugin wrappers."],
      [
        "uninstall",
        "Archive and remove exact-owned assets while preserving conflicts and user files.",
      ],
      ["doctor", "Inspect versions, ownership, drift, config, archives, tools, and LSP."],
      ["capabilities", "Print the versioned commands, agents, plugins, and tools catalog as JSON."],
      ["reconcile", "Classify current and retired assets; archive exact-owned retired entries."],
      ["agent list", "List profiles, models, ownership, collisions, and drift."],
      ["agent configure", "Choose an agent model interactively or with explicit options."],
      ["agent model-set", "Set one agent model directly without the interactive wizard."],
      ["agent reconcile", "Re-render package-managed agents from saved profile configuration."],
      ["critic add", "Add a named critic with a selected model."],
      ["critic remove", "Remove a package-managed additional critic."],
    ]),
    "",
    "Common options:",
    ...helpRows([
      ["--global", "Use global scope; project scope is the default."],
      ["--dry-run", "Preview a mutation and issue a one-time confirmation digest."],
      ["--confirm <digest>", "Apply the exact unexpired preview after final revalidation."],
      ["--json", "Emit stable machine-readable output when supported."],
      ["--help", "Show this help and exit."],
      ["--version", "Show the package version and exit."],
    ]),
    "",
    "Install selection:",
    ...helpRows([
      ["--commands <list|none>", "Select adapters for installed portable skills."],
      ["--skill-commands <list|none>", "Select adapters for installed portable skills."],
      ["--agents <list|none>", "Select fixed agents."],
      ["--plugins <list|none>", "Select optional plugin wrappers."],
    ]),
    "  Lists are comma-separated. Outside a TTY, provide command selection, --agents, and --plugins.",
    "",
    "Agent model options:",
    ...helpRows([
      ["--provider <id>", "Provider for a model name that is not provider/model."],
      ["--model <id>", "Exact provider/model or a model paired with --provider."],
      ["--variant <id>", "Set an optional model variant."],
      ["--clear-variant", "Remove the configured variant during agent model-set."],
    ]),
    "  Used by agent configure, agent model-set, and critic add.",
    "",
    "Safe mutation workflow:",
    "  1. Run the command with --dry-run.",
    "  2. Review the target, operations, conflicts, restart requirement, and expiry.",
    "  3. Run the exact Apply command printed by the preview before it expires.",
    "  4. Restart OpenCode when the applied plan requires it.",
    "  The installer never edits opencode.json or installs portable skills.",
    "",
    "Scope behavior:",
    ...helpRows([
      ["default", "Targets .opencode under the current directory; run from the project root."],
      ["--global", "Targets ~/.config/opencode and can run from any directory."],
    ]),
    "",
    "Examples:",
    `  ${shellCommand(["capabilities", "--json"])}`,
    `  ${shellCommand(["install", "--global", "--dry-run"])}`,
    `  ${shellCommand(["doctor", "--global"])}`,
    `  ${shellCommand([
      "agent",
      "model-set",
      "worker",
      "--global",
      "--model",
      "openai/gpt-5",
      "--variant",
      "high",
      "--dry-run",
    ])}`,
    "",
    "Documentation:",
    "  https://github.com/kisev/skills/blob/main/docs/how-to/opencode-integration.md",
    "",
  ].join("\n");
}

function commandHelp(
  topic: string,
  summary: string,
  usage: readonly string[],
  options: readonly (readonly [string, string])[],
  behavior: readonly string[],
  examples: readonly string[],
): string {
  return [
    `skills-opencode ${CATALOG.version} - ${topic}`,
    "",
    summary,
    "",
    "Usage:",
    ...usage.map((line) => `  ${line}`),
    "",
    "Options:",
    ...helpRows(options),
    "",
    "Behavior:",
    ...behavior.map((line) => `  ${line}`),
    "",
    "Examples:",
    ...examples.map((line) => `  ${line}`),
    "",
  ].join("\n");
}

function groupHelp(
  topic: string,
  summary: string,
  usage: string,
  commands: readonly (readonly [string, string])[],
  behavior: readonly string[],
  examples: readonly string[],
): string {
  return [
    `skills-opencode ${CATALOG.version} - ${topic}`,
    "",
    summary,
    "",
    "Usage:",
    `  ${usage}`,
    "",
    "Commands:",
    ...helpRows(commands),
    "",
    "Behavior:",
    ...behavior.map((line) => `  ${line}`),
    "",
    "Examples:",
    ...examples.map((line) => `  ${line}`),
    "",
  ].join("\n");
}

function contextualHelp(arguments_: readonly string[]): string | undefined {
  const [domain, operation] = arguments_.filter((value) => value !== "--help");
  if (domain === "install")
    return commandHelp(
      "install",
      "Select and deploy package-owned OpenCode integration assets.",
      [
        "skills-opencode install [--global] --dry-run [selection options]",
        "skills-opencode install [--global] --confirm <digest> [selection options]",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--dry-run", "Preview operations and issue a one-time confirmation digest."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--commands <list|none>", "Select installed-skill adapters."],
        ["--skill-commands <list|none>", "Select installed-skill adapters."],
        ["--agents <list|none>", "Select fixed agents."],
        ["--plugins <list|none>", "Select optional plugin wrappers."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Without selection flags, a TTY opens command, agent, and plugin selectors.",
        "Use Up/Down to move, Space to toggle, A/N for all/none, and Enter to confirm.",
        "Outside a TTY, provide command selection, --agents, and --plugins.",
        "Writes occur only after confirmation; the installer never edits opencode.json.",
        "Portable skills are installed separately; restart OpenCode after asset changes.",
      ],
      [
        shellCommand(["install", "--global", "--dry-run"]),
        shellCommand([
          "install",
          "--commands",
          "doctor,reconcile,agent-profiles",
          "--agents",
          "manager,architect,mapper,worker,review,critic",
          "--plugins",
          "none",
          "--dry-run",
        ]),
      ],
    );
  if (domain === "uninstall")
    return commandHelp(
      "uninstall",
      "Remove package-owned integration assets safely.",
      [
        "skills-opencode uninstall [--global] --dry-run",
        "skills-opencode uninstall [--global] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--dry-run", "Preview removals, archives, and conflicts."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Archives and removes only exact manifest-owned assets after confirmation.",
        "Preserves modified and user-owned files, worktrees, runtime state, and portable skills.",
        "Remove the plugin config entry and npm dependency only after managed assets.",
      ],
      [
        shellCommand(["uninstall", "--global", "--dry-run"]),
        shellCommand(["uninstall", "--dry-run"]),
      ],
    );
  if (domain === "doctor")
    return commandHelp(
      "doctor",
      "Inspect integration health without changing state.",
      ["skills-opencode doctor [--global] [--json]"],
      [
        ["--global", "Inspect global scope; project scope is the default."],
        ["--json", "Emit the complete stable machine-readable report."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Creates no receipts and starts no recovery, plugin factories, or LSP servers.",
        "Reports versions, ownership, drift, collisions, config, archives, tools, and LSP facts.",
        "Exit status: 0 clean, 1 findings, 2 invalid input or incomplete probing.",
      ],
      [shellCommand(["doctor"]), shellCommand(["doctor", "--global", "--json"])],
    );
  if (domain === "capabilities")
    return commandHelp(
      "capabilities",
      "Print the versioned package capability catalog.",
      ["skills-opencode capabilities [--json]"],
      [
        ["--json", "Explicitly request stable JSON output; JSON is the default."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Requires no scope and performs no mutation.",
        "Lists exact skills, commands, agents, plugins, and package tools.",
      ],
      [shellCommand(["capabilities", "--json"])],
    );
  if (domain === "reconcile")
    return commandHelp(
      "reconcile",
      "Classify current and historical assets and retire exact-owned entries.",
      [
        "skills-opencode reconcile [--global] --dry-run",
        "skills-opencode reconcile [--global] --confirm <digest>",
      ],
      [
        ["--global", "Reconcile global scope; project scope is the default."],
        ["--dry-run", "Preview classifications, archives, and blockers."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Preview is read-only and blocks Apply on modified managed files or ownership conflicts.",
        "Confirmed reconcile archives exact-owned retired package assets.",
        "Marked retired portable skills are removed by the pinned skills CLI.",
      ],
      [
        shellCommand(["reconcile", "--global", "--dry-run"]),
        shellCommand(["reconcile", "--dry-run", "--json"]),
      ],
    );
  if (domain === "agent" && operation === "list")
    return commandHelp(
      "agent list",
      "List agent profiles, models, ownership, collisions, and drift.",
      ["skills-opencode agent list [--global] [--json]"],
      [
        ["--global", "Inspect global scope; project scope is the default."],
        ["--json", "Emit stable machine-readable inventory."],
        ["--help", "Show this command help and exit."],
      ],
      ["Read-only inventory; creates no receipts and changes no files or configuration."],
      [shellCommand(["agent", "list", "--global"]), shellCommand(["agent", "list", "--json"])],
    );
  if (domain === "agent" && operation === "configure")
    return commandHelp(
      "agent configure",
      "Choose an agent model interactively or with explicit options.",
      [
        "skills-opencode agent configure [name] [--global] --dry-run",
        "skills-opencode agent configure <name> [--global] --model <provider/model> [--variant <id>] --dry-run",
        "skills-opencode agent configure <name> [--global] --model <provider/model> [--variant <id>] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--provider <id>", "Provider when --model is not provider/model."],
        ["--model <id>", "Exact provider/model or model paired with --provider."],
        ["--variant <id>", "Set an optional model variant."],
        ["--clear-variant", "Remove the configured variant."],
        ["--dry-run", "Preview the profile change."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Opens a TTY wizard unless the agent and model are explicit.",
        "Uses the cached OpenCode model catalog and makes no LLM call.",
        "The preview normally prints an agent model-set Apply command.",
      ],
      [
        shellCommand(["agent", "configure", "manager", "--global", "--dry-run"]),
        shellCommand([
          "agent",
          "configure",
          "worker",
          "--global",
          "--model",
          "openai/gpt-5",
          "--variant",
          "high",
          "--dry-run",
        ]),
      ],
    );
  if (domain === "agent" && operation === "model-set")
    return commandHelp(
      "agent model-set",
      "Set one agent model and optional variant directly.",
      [
        "skills-opencode agent model-set <name> [--global] --model <provider/model> [--variant <id>] --dry-run",
        "skills-opencode agent model-set <name> [--global] --model <provider/model> [--variant <id>] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--provider <id>", "Provider when --model is not provider/model."],
        ["--model <id>", "Exact provider/model or model paired with --provider."],
        ["--variant <id>", "Set an optional model variant."],
        ["--clear-variant", "Remove the configured variant."],
        ["--dry-run", "Preview the profile change."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Accepts exact provider/model or a provider and model pair.",
        "Keeps fixed prompts and permissions unchanged and makes no LLM call.",
        "Writes only after exact confirmation.",
      ],
      [
        shellCommand([
          "agent",
          "model-set",
          "worker",
          "--global",
          "--model",
          "openai/gpt-5",
          "--variant",
          "high",
          "--dry-run",
        ]),
        shellCommand([
          "agent",
          "model-set",
          "manager",
          "--global",
          "--model",
          "openai/gpt-5",
          "--clear-variant",
          "--dry-run",
        ]),
      ],
    );
  if (domain === "agent" && operation === "reconcile")
    return commandHelp(
      "agent reconcile",
      "Re-render managed agent files from saved profile configuration.",
      [
        "skills-opencode agent reconcile [--global] --dry-run",
        "skills-opencode agent reconcile [--global] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--dry-run", "Preview rendered agent changes and conflicts."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Uses saved models and variants while preserving package prompts and permissions.",
        "Preserves user-owned files and collisions; writes only after confirmation.",
      ],
      [
        shellCommand(["agent", "reconcile", "--global", "--dry-run"]),
        shellCommand(["agent", "reconcile", "--dry-run", "--json"]),
      ],
    );
  if (domain === "agent")
    return groupHelp(
      "agent",
      "Inspect and manage fixed agents and additional critics.",
      "skills-opencode agent <command> [options]",
      [
        ["list", "List profiles, models, ownership, collisions, and drift."],
        ["configure", "Choose an agent model interactively or with explicit options."],
        ["model-set", "Set one agent model directly without the interactive wizard."],
        ["reconcile", "Re-render package-managed agents from saved profile configuration."],
      ],
      [
        "Prompts and permissions remain package-owned.",
        "Profile configuration changes models, variants, and additional critics.",
        "Mutations use preview and exact confirmation.",
      ],
      [shellCommand(["agent", "list", "--global"]), shellCommand(["agent", "model-set", "--help"])],
    );
  if (domain === "critic" && operation === "add")
    return commandHelp(
      "critic add",
      "Add an additional named critic with a selected model.",
      [
        "skills-opencode critic add [name] [--global] --dry-run",
        "skills-opencode critic add <name> [--global] --model <provider/model> [--variant <id>] --dry-run",
        "skills-opencode critic add <name> [--global] --model <provider/model> [--variant <id>] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--provider <id>", "Provider when --model is not provider/model."],
        ["--model <id>", "Exact provider/model or model paired with --provider."],
        ["--variant <id>", "Set an optional model variant."],
        ["--dry-run", "Preview critic creation and pool changes."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Prefixes names with critic- when needed.",
        "Uses TTY model selection when the model is omitted and makes no LLM call.",
        "Updates manager and review critic pools after confirmation.",
      ],
      [
        shellCommand([
          "critic",
          "add",
          "security",
          "--global",
          "--model",
          "anthropic/claude-sonnet-4-6",
          "--dry-run",
        ]),
        shellCommand(["critic", "add", "performance", "--global", "--dry-run"]),
      ],
    );
  if (domain === "critic" && operation === "remove")
    return commandHelp(
      "critic remove",
      "Remove a package-managed additional critic.",
      [
        "skills-opencode critic remove <name> [--global] --dry-run",
        "skills-opencode critic remove <name> [--global] --confirm <digest>",
      ],
      [
        ["--global", "Use global scope; project scope is the default."],
        ["--dry-run", "Preview critic removal and pool changes."],
        ["--confirm <digest>", "Apply the exact unexpired preview."],
        ["--json", "Emit stable machine-readable output."],
        ["--help", "Show this command help and exit."],
      ],
      [
        "Accepts the name with or without the critic- prefix.",
        "Preserves the fixed critic and user-owned files.",
        "Updates manager and review critic pools after confirmation.",
      ],
      [
        shellCommand(["critic", "remove", "security", "--global", "--dry-run"]),
        shellCommand(["critic", "remove", "security", "--dry-run"]),
      ],
    );
  if (domain === "critic")
    return groupHelp(
      "critic",
      "Manage additional package-owned critic profiles.",
      "skills-opencode critic <command> [options]",
      [
        ["add", "Add a named critic with a selected model."],
        ["remove", "Remove a package-managed additional critic."],
      ],
      [
        "Names use critic-<safe-suffix>.",
        "Manager and review critic pools update with profile configuration.",
        "Mutations use preview and exact confirmation.",
      ],
      [
        shellCommand(["critic", "add", "security", "--help"]),
        shellCommand(["critic", "remove", "security", "--help"]),
      ],
    );
  return undefined;
}

async function interactiveInstallerSelection(): Promise<InstallerSelection> {
  if (!process.stdin.isTTY || !process.stderr.isTTY)
    throw new InstallerError(
      "terminal_required",
      "install requires explicit selection flags outside a terminal",
    );
  process.stderr.write(
    [
      "Portable skills are installed separately through npx skills.",
      "This installer does not install, update, or remove portable skills.",
      "Skill command adapters are OpenCode slash commands that load an already-installed skill with the same name.",
      "Selecting a command adapter does not select or install its skill.",
      "\n",
    ].join("\n"),
  );
  const group = async (
    label: string,
    names: readonly string[],
    initialSelected: readonly string[],
  ): Promise<string[]> => {
    const selected = await selectOptions(
      label,
      names,
      initialSelected,
      process.stdin,
      process.stderr,
    );
    if (selected === null) throw new InstallerError("cancelled", "Wizard cancelled");
    return selected;
  };
  const defaults = defaultSelection();
  const commands = await group("Skill command adapters", SKILL_COMMANDS, SKILL_COMMANDS);
  const agents = await group("Fixed agents", defaults.agents, defaults.agents);
  const plugins = await group("Selectable plugins", SELECTABLE_PLUGINS, []);
  return normalizeSelection({
    commands,
    agents: agents as InstallerSelection["agents"],
    plugins: plugins as InstallerSelection["plugins"],
  });
}

function installerSelection(options: Options): Partial<InstallerSelection> {
  return normalizeSelection({
    commands: options.commands,
    agents: options.agents as InstallerSelection["agents"] | undefined,
    plugins: options.plugins as InstallerSelection["plugins"] | undefined,
  });
}

function selectionArguments(selection: InstallerSelection): string[] {
  return [
    "--commands",
    selection.commands.join(",") || "none",
    "--agents",
    selection.agents.join(",") || "none",
    "--plugins",
    selection.plugins.join(",") || "none",
  ];
}

function requireConfirmationMode(options: Options): void {
  if (options.dryRun === Boolean(options.confirm))
    throw new InstallerError("invalid_input", "Use exactly one of --dry-run or --confirm <digest>");
}

function exactModel(options: Options): string | undefined {
  if (!options.model) return undefined;
  if (options.model.includes("/")) {
    const model = validateModel(options.model);
    if (options.provider && model.split("/", 1)[0] !== options.provider)
      throw new InstallerError(
        "invalid_input",
        "--provider does not match the exact --model value",
      );
    return model;
  }
  if (!options.provider)
    throw new InstallerError(
      "invalid_input",
      "--provider is required when --model is not provider/model",
    );
  return validateModel(`${options.provider}/${options.model}`);
}

async function interactiveSelection(
  options: Options,
  action: "model-set" | "critic-add" = "model-set",
): Promise<{ name: string; model: string; variant?: string }> {
  if (!process.stdin.isTTY || !process.stderr.isTTY) {
    throw new InstallerError(
      "terminal_required",
      "agent configure requires a terminal or explicit --provider and --model",
    );
  }
  const inventory = await listAgentProfiles(options.scope!);
  const configurable = inventory.profiles.filter((item) => item.ownership !== "user-owned");

  let name: string;
  if (options.name) {
    name =
      action === "critic-add" && !options.name.startsWith("critic-")
        ? validateAgentName(`critic-${options.name}`)
        : validateAgentName(options.name);
  } else if (action === "critic-add") {
    const raw = await promptText("Critic name (critic-<suffix>):");
    if (raw === null) throw new InstallerError("cancelled", "Wizard cancelled");
    name = raw.startsWith("critic-") ? raw : `critic-${raw}`;
    validateAgentName(name);
  } else {
    const agentNames = configurable.map((item) => item.name);
    if (agentNames.length === 0) agentNames.push(...FIXED_AGENT_ROLES);
    const index = await selectOption("Select agent:", agentNames);
    if (index === null) throw new InstallerError("cancelled", "Wizard cancelled");
    name = agentNames[index];
  }

  const currentProfile = configurable.find((item) => item.name === name);
  const currentModel = currentProfile?.model;
  const currentVariant = currentProfile?.variant;
  const showTarget = (model: string, variant?: string): void => {
    process.stderr.write(`Target: ${model}${variant ? ` / ${variant}` : ""}\n`);
  };

  if (options.provider && options.model) {
    const model = exactModel(options)!;
    const variant = validateVariant(options.variant);
    return { name, model, ...(variant ? { variant } : {}) };
  }

  while (true) {
    const actions: string[] = [];
    if (currentModel) {
      actions.push(`Keep current (${currentModel}${currentVariant ? ` / ${currentVariant}` : ""})`);
    }
    actions.push("Change model");
    if (currentVariant) actions.push("Clear variant");
    if (!options.name && action === "model-set") actions.push("Back");
    actions.push("Cancel");

    const currentLabel = `Agent: ${name}${currentModel ? ` (current: ${currentModel}${currentVariant ? ` / ${currentVariant}` : ""})` : ""}`;
    const actionIndex = await selectOption(currentLabel, actions);
    if (actionIndex === null) throw new InstallerError("cancelled", "Wizard cancelled");

    const chosen = actions[actionIndex];

    if (chosen.startsWith("Keep current")) {
      if (!currentModel) throw new InstallerError("invalid_state", "No current model to keep");
      showTarget(currentModel, currentVariant);
      return { name, model: currentModel, ...(currentVariant ? { variant: currentVariant } : {}) };
    }

    if (chosen === "Change model") {
      let models: string[];
      try {
        models = await availableModels();
      } catch (error) {
        if (error instanceof AgentProfileError && error.code === "catalog_unavailable") {
          process.stderr.write(
            "\nModel catalog is unavailable.\nUse direct CLI with exact --model provider/model and optional --variant.\n\n",
          );
          throw new InstallerError(
            "catalog_unavailable",
            "Use direct CLI with exact --model provider/model",
          );
        }
        throw error;
      }

      const providers = [...new Set(models.map((m) => m.split("/", 1)[0]))].sort();
      const providerIndex = await selectOption("Select provider:", providers);
      if (providerIndex === null) continue;
      const provider = providers[providerIndex];

      const filteredModels = models.filter((m) => m.startsWith(`${provider}/`));
      const modelIndex = await selectOption("Select model:", filteredModels);
      if (modelIndex === null) continue;
      const selectedModel = filteredModels[modelIndex];

      let selectedVariant: string | undefined;
      try {
        const variants = await availableModelVariants(selectedModel);
        if (variants.length) {
          const variantOptions = ["(none)", ...variants];
          const variantIndex = await selectOption("Select variant:", variantOptions);
          if (variantIndex === null) continue;
          if (variantIndex > 0) selectedVariant = variantOptions[variantIndex];
        }
      } catch (error) {
        if (error instanceof AgentProfileError && error.code === "catalog_unavailable") {
          process.stderr.write(
            "\nModel variant metadata is unavailable.\nUse direct CLI with exact --model provider/model and optional --variant.\n\n",
          );
          throw new InstallerError(
            "catalog_unavailable",
            "Use direct CLI with exact --model provider/model",
          );
        }
        throw error;
      }

      showTarget(selectedModel, selectedVariant);
      return {
        name,
        model: selectedModel,
        ...(selectedVariant ? { variant: selectedVariant } : {}),
      };
    }

    if (chosen === "Clear variant") {
      if (!currentModel) throw new InstallerError("invalid_state", "No model to clear variant for");
      showTarget(currentModel);
      return { name, model: currentModel };
    }

    if (chosen === "Back") {
      return interactiveSelection({ ...options, name: undefined }, action);
    }

    if (chosen === "Cancel") {
      throw new InstallerError("cancelled", "Wizard cancelled");
    }
  }
}

async function runProfile(request: AgentProfileRequest, options: Options): Promise<void> {
  requireConfirmationMode(options);
  if (options.dryRun) {
    const plan = await previewAgentProfileChange(request, options.scope!);
    if (options.json)
      process.stdout.write(
        `${JSON.stringify({ status: "ok", applied: false, requires_restart: false, plan }, null, 2)}\n`,
      );
    else
      process.stdout.write(
        renderPlan(plan, {
          applied: false,
          confirmationCommand: shellCommand(
            profileConfirmationArguments(request, options.scope!, plan.digest),
          ),
        }),
      );
  } else {
    const applied = await applyAgentProfileChange(request, options.scope!, options.confirm!);
    if (options.json) process.stdout.write(`${JSON.stringify(applied, null, 2)}\n`);
    else process.stdout.write(renderPlan(applied.plan, { applied: true }));
  }
}

function profileConfirmationArguments(
  request: AgentProfileRequest,
  scope: Scope,
  digest: string,
): string[] {
  if (request.action === "reconcile")
    return ["agent", "reconcile", ...scopeArguments(scope), "--confirm", digest];
  if (request.action === "critic-remove")
    return ["critic", "remove", request.name!, ...scopeArguments(scope), "--confirm", digest];
  const command =
    request.action === "critic-add"
      ? ["critic", "add", request.name!]
      : ["agent", "model-set", request.name!];
  command.push(...scopeArguments(scope), "--model", request.model!);
  if (request.variant) command.push("--variant", request.variant);
  else if (request.action === "model-set") command.push("--clear-variant");
  command.push("--confirm", digest);
  return command;
}

async function run(arguments_: string[]): Promise<void> {
  const removedScope = arguments_.find(
    (value) => value === "--scope" || value.startsWith("--scope="),
  );
  if (removedScope)
    throw new InstallerError(
      "invalid_input",
      "--scope has been removed; omit it for project scope or use --global",
    );
  if (arguments_.filter((value) => value === "--global").length > 1)
    throw new InstallerError("invalid_input", "--global may be supplied once");
  if (arguments_[0] === "capabilities" && arguments_.includes("--global"))
    throw new InstallerError("invalid_input", "capabilities accepts only --json");
  if (arguments_.includes("--help")) {
    const [domain, operation] = arguments_.filter((value) => !value.startsWith("--"));
    if (
      (domain === "agent" &&
        operation &&
        !["list", "configure", "model-set", "reconcile"].includes(operation)) ||
      (domain === "critic" && operation && !["add", "remove"].includes(operation))
    )
      throw new InstallerError("invalid_input", `Unknown command: ${domain} ${operation}`);
    const page = contextualHelp(arguments_);
    if (!page && arguments_[0] !== "--help")
      throw new InstallerError("invalid_input", `Unknown command: ${arguments_[0]}`);
    for (const value of arguments_.filter((item) => item.startsWith("--") && item !== "--help"))
      if (!(page ?? rootHelp()).includes(value))
        throw new InstallerError("invalid_input", `Unknown argument: ${value}`);
    process.stdout.write(page ?? rootHelp());
    return;
  }
  if (arguments_.length === 0) {
    process.stdout.write(rootHelp());
    return;
  }
  if (arguments_.includes("--version")) {
    if (arguments_.some((value) => value !== "--version" && value !== "--json"))
      throw new InstallerError("invalid_input", "--version accepts only --json");
    process.stdout.write(
      arguments_.includes("--json")
        ? `${JSON.stringify({ status: "ok", version: CATALOG.version })}\n`
        : `${CATALOG.version}\n`,
    );
    return;
  }
  const [domain, operation, ...rest] = arguments_;
  if (domain === "doctor") {
    if (operation) rest.unshift(operation);
    const options = parseOptions(rest);
    if (
      options.dryRun ||
      options.confirm ||
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      options.selectionFlag
    )
      throw new InstallerError("invalid_input", "doctor accepts only --global and --json");
    const report = await collectDoctorFacts(options.scope!);
    if (options.json) process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    else process.stdout.write(renderDoctor(report));
    process.exitCode = doctorExitCode(report);
    return;
  }
  if (domain === "capabilities") {
    if (operation) rest.unshift(operation);
    const options = parseOptions(rest);
    if (
      options.dryRun ||
      options.confirm ||
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      options.global ||
      options.selectionFlag
    )
      throw new InstallerError("invalid_input", "capabilities accepts only --json");
    process.stdout.write(
      `${JSON.stringify({ schema_version: 1, status: "ok", ...CATALOG }, null, 2)}\n`,
    );
    return;
  }
  if (domain === "reconcile") {
    if (operation) rest.unshift(operation);
    const options = parseOptions(rest);
    if (
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      options.selectionFlag
    )
      throw new InstallerError(
        "invalid_input",
        "reconcile accepts only --global, --dry-run, --confirm, and --json",
      );
    requireConfirmationMode(options);
    if (options.dryRun) {
      const plan = await previewReconcile(options.scope!);
      if (options.json)
        process.stdout.write(
          `${JSON.stringify({ status: "ok", applied: false, plan }, null, 2)}\n`,
        );
      else
        process.stdout.write(
          renderReconcile(plan, {
            applied: false,
            confirmationCommand: plan.confirmable
              ? shellCommand([
                  "reconcile",
                  ...scopeArguments(options.scope),
                  "--confirm",
                  plan.confirmation_digest ?? plan.digest!,
                ])
              : undefined,
          }),
        );
    } else {
      const applied = await applyReconcile(options.scope!, options.confirm!);
      if (options.json) process.stdout.write(`${JSON.stringify(applied, null, 2)}\n`);
      else process.stdout.write(renderReconcile(applied.plan, { applied: true }));
    }
    return;
  }
  if (domain === "install" || domain === "uninstall") {
    if (operation?.startsWith("--") || operation === undefined)
      rest.unshift(...(operation ? [operation] : []));
    else throw new InstallerError("invalid_input", `Unexpected argument: ${operation}`);
    const options = parseOptions(rest);
    const action = domain as Action;
    if (
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      (action === "uninstall" && options.selectionFlag)
    )
      throw new InstallerError(
        "invalid_input",
        action === "install"
          ? "install does not accept model options or positional arguments"
          : "uninstall accepts only --global, --dry-run, --confirm, and --json",
      );
    if (
      action === "install" &&
      options.selectionFlag &&
      (options.commands === undefined ||
        options.agents === undefined ||
        options.plugins === undefined)
    )
      throw new InstallerError(
        "invalid_input",
        "Non-TTY install requires --commands, --agents, and --plugins",
      );
    const selection =
      action === "install"
        ? options.selectionFlag
          ? installerSelection(options)
          : await interactiveInstallerSelection()
        : undefined;
    requireConfirmationMode(options);
    if (options.dryRun) {
      const plan = await preview(action, options.scope!, process.cwd(), undefined, selection);
      if (options.json)
        process.stdout.write(
          `${JSON.stringify({ status: "ok", applied: false, requires_restart: plan.requires_restart, plan }, null, 2)}\n`,
        );
      else
        process.stdout.write(
          renderPlan(plan, {
            applied: false,
            confirmationCommand: shellCommand([
              action,
              ...scopeArguments(options.scope),
              ...selectionArguments(plan.selection),
              "--confirm",
              plan.digest,
            ]),
          }),
        );
    } else {
      const plan = await apply(
        action,
        options.scope!,
        options.confirm!,
        process.cwd(),
        undefined,
        {},
        selection,
      );
      if (options.json)
        process.stdout.write(
          `${JSON.stringify({ status: "ok", applied: true, requires_restart: plan.requires_restart, plan }, null, 2)}\n`,
        );
      else process.stdout.write(renderPlan(plan, { applied: true }));
    }
    return;
  }
  if (domain === "agent" && operation === "list") {
    const options = parseOptions(rest);
    if (
      options.dryRun ||
      options.confirm ||
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      options.selectionFlag
    )
      throw new InstallerError("invalid_input", "agent list accepts only --global and --json");
    const inventory = await listAgentProfiles(options.scope!);
    if (options.json)
      process.stdout.write(`${JSON.stringify({ status: "ok", inventory }, null, 2)}\n`);
    else process.stdout.write(renderInventory(inventory));
    return;
  }
  if (domain === "agent" && operation === "configure") {
    const options = parseOptions(rest);
    if (options.selectionFlag)
      throw new InstallerError(
        "invalid_input",
        "agent configure does not accept selection options",
      );
    requireConfirmationMode(options);
    const selected =
      options.provider && options.model && options.name
        ? {
            name: validateAgentName(options.name),
            model: exactModel(options)!,
            ...(validateVariant(options.variant)
              ? { variant: validateVariant(options.variant) }
              : {}),
          }
        : await interactiveSelection(options, "model-set");
    await runProfile(
      { action: "model-set", ...selected, variant: selected.variant ?? null },
      options,
    );
    return;
  }
  if (domain === "agent" && operation === "model-set") {
    const options = parseOptions(rest);
    if (options.selectionFlag)
      throw new InstallerError(
        "invalid_input",
        "agent model-set does not accept selection options",
      );
    const name = validateAgentName(options.name ?? "");
    const model = exactModel(options);
    if (!model)
      throw new InstallerError(
        "invalid_input",
        "agent model-set requires --provider and --model, or exact --model provider/model",
      );
    await runProfile(
      { action: "model-set", name, model, variant: options.variant ?? null },
      options,
    );
    return;
  }
  if (domain === "agent" && operation === "reconcile") {
    const options = parseOptions(rest);
    if (
      options.name ||
      options.provider ||
      options.model ||
      options.variant !== undefined ||
      options.selectionFlag
    )
      throw new InstallerError(
        "invalid_input",
        "agent reconcile accepts only --global, --dry-run, --confirm, and --json",
      );
    await runProfile({ action: "reconcile" }, options);
    return;
  }
  if (domain === "critic" && (operation === "add" || operation === "remove")) {
    const options = parseOptions(rest);
    if (options.selectionFlag)
      throw new InstallerError(
        "invalid_input",
        `critic ${operation} does not accept selection options`,
      );
    const name =
      options.name === "critic" || options.name?.startsWith("critic-")
        ? options.name
        : `critic-${options.name ?? ""}`;
    if (operation === "add") {
      if (options.variant === null)
        throw new InstallerError("invalid_input", "critic add does not accept --clear-variant");
      const model = exactModel(options);
      if (!model) {
        const selected = await interactiveSelection(options, "critic-add");
        await runProfile(
          {
            action: "critic-add",
            name: selected.name,
            model: selected.model,
            variant: selected.variant ?? null,
          },
          options,
        );
      } else {
        await runProfile(
          { action: "critic-add", name, model, variant: options.variant ?? null },
          options,
        );
      }
    } else {
      if (
        options.provider ||
        options.model ||
        options.variant !== undefined ||
        options.selectionFlag
      )
        throw new InstallerError("invalid_input", "critic remove does not accept model options");
      await runProfile({ action: "critic-remove", name }, options);
    }
    return;
  }
  throw new InstallerError(
    "invalid_input",
    "Use install, uninstall, doctor, capabilities, reconcile, agent list|configure|model-set|reconcile, or critic add|remove",
  );
}

async function main(): Promise<void> {
  try {
    await run(process.argv.slice(2));
  } catch (error) {
    const known =
      error instanceof LifecycleError
        ? error
        : new InstallerError(
            "internal_error",
            error instanceof Error ? error.message : String(error),
          );
    if (process.argv.includes("--json"))
      process.stdout.write(
        `${JSON.stringify({ status: "error", error: { code: known.code, message: known.message } })}\n`,
      );
    else process.stderr.write(`Error [${known.code}]: ${terminalSafe(known.message)}\n`);
    process.exitCode = 2;
  }
}

void main();
