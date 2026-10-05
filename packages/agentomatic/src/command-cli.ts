import { Command, Option, common, applyConfig, configFileSync, reporter } from "./generated/cli.js";
import {
  applyAgentProfileChange,
  previewAgentProfileChange,
  listAgentProfiles,
  availableModels,
  availableModelVariants,
  validateAgentName,
  validateModel,
  validateVariant,
  suggestCriticName,
  FIXED_AGENT_ROLES,
  type AgentProfileRequest,
  type AgentProfileRecord,
} from "./agent-profiles.js";
import {
  apply,
  preview,
  installedSelection,
  defaultSelection,
  normalizeSelection,
  InstallerError,
  SKILL_COMMANDS,
  SELECTABLE_PLUGINS,
  type InstallerSelection,
} from "./installer.js";
import {
  applyConfigSetup,
  previewConfigSetup,
  recoverConfigSetup,
  normalizeConfigSelection,
  defaultConfigSelection,
  CONFIG_TARGETS,
  CONFIG_FRAGMENTS,
  inspectIntegration,
  type ConfigSetupSelection,
  type ConfigTargetName,
  type FragmentName,
} from "./config-setup.js";
import { collectDoctorFacts, doctorExitCode } from "./doctor.js";
import { applyReconcile, previewReconcile } from "./reconcile.js";
import { CATALOG } from "./catalog.js";
import { skillsInstallerSpec } from "./package-metadata.js";
import { LifecycleError, type Scope } from "./lifecycle.js";
import { previewDependencyRemoval, removeDependency, planDependency } from "./self-install.js";
import { selectOption, selectOptions, promptText, confirmQuestion } from "./terminal-wizard.js";
import {
  renderPlan,
  renderInventory,
  renderCriticsTable,
  renderDoctor,
  renderConfigSetup,
  renderReconcile,
  terminalSafe,
  shellCommand,
  scopeArguments,
} from "./cli-output.js";

type Options = {
  scope: Scope;
  dryRun: boolean;
  yes: boolean;
  json: boolean;
  name?: string;
  commands?: string[];
  agents?: string[];
  plugins?: string[];
  core?: boolean;
  targets?: ConfigTargetName[];
  fragments?: FragmentName[];
  noDependency: boolean;
  model?: string;
  provider?: string;
  variant?: string | null;
  disconnect?: boolean;
  removeDependency: boolean;
};
let diagnostics: ReturnType<typeof reporter> | undefined;
let machineOutput = false;
let diagnosticJSON = false;

const commands: Record<string, { description: string; options: string[]; name?: boolean }> = {
  install: {
    description:
      "Install components, connect integration, and optionally configure models and critics.",
    options: ["commands", "agents", "plugins", "core", "dependency", "targets", "fragments"],
  },
  configure: {
    description: "Choose components, agent models, critics, or application integration.",
    options: [],
  },
  "configure components": {
    description: "Change the installed component set without resetting models.",
    options: ["commands", "agents", "plugins", "core", "dependency", "targets", "fragments"],
  },
  "configure agent": {
    description:
      "Open a staged editor for every agent, or set one model with a name and --model provider/model.",
    options: ["provider", "model", "variant", "clearVariant"],
    name: true,
  },
  "configure critics": {
    description: "Alias of configure agent: staged agent models and critic management.",
    options: [],
  },
  "configure integration": {
    description: "Connect or disconnect the plugin and merge application presets.",
    options: ["targets", "fragments", "dependency"],
  },
  status: {
    description:
      "Show installed components, connection, dependency, models, and critic pool without changes.",
    options: [],
  },
  doctor: {
    description:
      "Diagnose versions, ownership, drift, configuration, tools, and LSP without repair.",
    options: [],
  },
  uninstall: {
    description:
      "Remove owned components; disconnect the plugin by default; retain models and npm dependency unless selected.",
    options: ["disconnect", "removeDependency"],
  },
  agent: { description: "List agents or manage additional critics.", options: [] },
  "agent list": {
    description: "Show installed and saved profiles, models, ownership, collisions, and drift.",
    options: [],
  },
  "agent add-critic": {
    description: "Add critic-<name> interactively or with an explicit model.",
    options: ["provider", "model", "variant"],
    name: true,
  },
  "agent remove": {
    description: "Remove an additional critic; fixed roles cannot be removed here.",
    options: [],
    name: true,
  },
  maintenance: {
    description:
      "Clean up retired files, repair selected components, or recover an interrupted transaction.",
    options: [],
  },
  "maintenance cleanup": {
    description: "Archive exact-owned retired files; preserve modified and user-owned files.",
    options: [],
  },
  "maintenance repair": {
    description:
      "Restore only the saved selected components; never overwrite modified managed files.",
    options: ["dependency"],
  },
  "maintenance recover": {
    description: "Preview and confirm journal-bound recovery, then request a fresh plan.",
    options: [],
  },
  catalog: {
    description: "Print the running package's capability catalog as JSON, not installed state.",
    options: [],
  },
};
const mutationOptions = new Set(["dryRun", "yes"]);
const observations = new Set(["status", "doctor", "agent list", "catalog"]);

function fail(code: string, message: string): never {
  throw new InstallerError(code, message);
}
function value<T>(result: T | null): T {
  return result === null ? fail("cancelled", "Wizard cancelled; no changes applied") : result;
}
function tty(): boolean {
  return Boolean(process.stdin.isTTY && process.stderr.isTTY);
}
function json(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}
function applyHint(args: string[]): string {
  return `${shellCommand(args)} (confirm interactively; add --yes outside a terminal)`;
}

// Prompt for a critic name, auto-converting unsafe input such as "sonnet-5.5" to
// "critic-sonnet-5-5" after explicit confirmation; exact safe names pass untouched.
async function promptCriticName(): Promise<string> {
  for (;;) {
    const input = value(await promptText("Critic name (critic-<suffix>)"));
    const suggestion = suggestCriticName(input);
    if (suggestion !== null && suggestion === input.trim().toLowerCase()) return suggestion;
    if (suggestion) {
      const accept = value(
        await selectOption(`"${terminalSafe(input)}" is not a safe critic name`, [
          `Use ${suggestion}`,
          "Enter a different name",
        ]),
      );
      if (accept === 0) return suggestion;
      continue;
    }
    process.stderr.write(
      "Invalid critic name: use a fixed role or critic-<suffix> with lowercase letters, digits, and hyphens between parts (for example critic-sonnet-5-5).\n",
    );
  }
}

function help(topic = ""): string {
  if (topic && !commands[topic]) fail("invalid_input", `Unknown command: ${topic}`);
  const visible = topic
    ? Object.entries(commands).filter(([key]) => key === topic || key.startsWith(`${topic} `))
    : Object.entries(commands).filter(([key]) => !key.includes(" "));
  return [
    `agentomatic ${CATALOG.version}`,
    "",
    topic
      ? commands[topic].description
      : "Install, configure, inspect, and remove application integration. Portable skills use the separate skills CLI.",
    ...(!topic
      ? [
          `Install skills separately: npx --yes ${skillsInstallerSpec()} add https://kisev.github.io/skills --agent opencode --copy`,
        ]
      : []),
    "",
    `Usage: agentomatic${topic ? ` ${topic}${commands[topic].name ? " [name]" : ""}` : " <command>"} [options]`,
    "",
    "Commands:",
    ...visible.map(([key, entry]) => `  ${key.padEnd(26)} ${entry.description}`),
    "",
    "Options:",
    "Common: --global (otherwise project), --json, --help, --version",
    ...(observations.has(topic) || topic === "catalog"
      ? []
      : [
          "Mutations: --dry-run previews without writes; --yes confirms a fresh plan without a final prompt.",
        ]),
    ...(topic && commands[topic].options.length
      ? [
          `Options: ${commands[topic].options.map((option) => ({ clearVariant: "--clear-variant", removeDependency: "--remove-dependency", dependency: "--no-dependency", core: "--core / --no-core", disconnect: "--disconnect / --no-disconnect" })[option] ?? `--${option} <value>`).join(", ")}`,
        ]
      : []),
    ...(!topic || ["install", "configure components"].includes(topic)
      ? [
          "Non-TTY component selection: --commands <list|none> --agents <list|none> --plugins <list|none>",
          "Saved selection is reused on repeat runs. --no-core disconnects the plugin; npm removal is an explicit uninstall choice.",
        ]
      : []),
    ...(topic === "configure integration"
      ? [
          "Outside a terminal supply both --targets and --fragments. Lists are comma-separated; none selects an empty list.",
          "Targets: opencode, kilo, mimo (project scope: opencode only).",
          `Fragments: ${CONFIG_FRAGMENTS.map((fragment) => fragment.name).join(", ")}.`,
        ]
      : []),
    "Behavior:",
    "Project scope uses .opencode under the current directory; run from the project root. Global scope uses ~/.config/opencode.",
    "Use status to inspect the installation, doctor to diagnose problems, and maintenance for explicit recovery.",
    "",
    "Examples:",
    `  ${shellCommand([...(topic ? topic.split(" ") : ["install"]), ...(commands[topic]?.name ? [topic === "agent remove" ? "critic-security" : "critic"] : []), ...(observations.has(topic) || ["agent", "maintenance"].includes(topic) ? [] : ["--dry-run"])])}`,
    "Documentation: https://github.com/kisev/skills/blob/main/docs/how-to/opencode-integration.md",
    "",
  ].join("\n");
}

function parse(topic: string, args: string[]): Options {
  const parser = common(
    new Command()
      .exitOverride()
      .helpOption(false)
      .configureOutput({ writeErr: () => {} }),
    "AGENTOMATIC",
  );
  if (commands[topic].name) parser.argument("[name]");
  const flags = [
    "--global",
    "--dry-run",
    "--yes",
    "--core",
    "--no-core",
    "--no-dependency",
    "--commands <value>",
    "--agents <value>",
    "--plugins <value>",
    "--targets <value>",
    "--fragments <value>",
    "--model <value>",
    "--provider <value>",
    "--variant <value>",
    "--clear-variant",
    "--disconnect",
    "--no-disconnect",
    "--remove-dependency",
  ];
  for (const flag of flags) {
    const option = new Option(flag, flag);
    if (flag.includes("<value>") || ["--global", "--dry-run"].includes(flag))
      option.env(
        `AGENTOMATIC_${option
          .attributeName()
          .replace(/[A-Z]/g, (letter) => `_${letter}`)
          .toUpperCase()}`,
      );
    parser.addOption(option);
  }
  try {
    for (const flag of args.filter((arg) => arg.startsWith("--")))
      if (args.filter((arg) => arg === flag).length > 1)
        throw new Error(`${flag} may be supplied once`);
    for (const [left, right] of [
      ["--core", "--no-core"],
      ["--disconnect", "--no-disconnect"],
      ["--variant", "--clear-variant"],
    ])
      if (args.includes(left) && args.includes(right))
        throw new Error(`Choose either ${left} or ${right}`);
    parser.parse(args, { from: "user" });
    applyConfig(parser, configFileSync(parser.opts().config));
    const parsed = parser.opts();
    machineOutput = parsed.json === true;
    diagnosticJSON = parsed.logFormat === "json";
    diagnostics = reporter({ ...parsed, progress: parsed.progress ?? "never" });
    for (const flag of flags) {
      const key = new Option(flag).attributeName();
      const source = parser.getOptionValueSource(key);
      if (
        source &&
        source !== "default" &&
        ![
          "global",
          ...commands[topic].options,
          ...(!observations.has(topic) ? mutationOptions : []),
        ].includes(key)
      )
        throw new Error(`${topic} does not accept ${flag.split(" ")[0]}`);
    }
    if (topic === "catalog" && parsed.global)
      throw new Error("catalog accepts no scope: it describes the running package");
    const list = (input: unknown): string[] | undefined =>
      input === undefined
        ? undefined
        : Array.isArray(input)
          ? input.map(String)
          : String(input) === "none"
            ? []
            : String(input)
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean);
    const specified = (key: string): boolean =>
      Boolean(parser.getOptionValueSource(key) && parser.getOptionValueSource(key) !== "default");
    return {
      scope: parsed.global ? "global" : "project",
      dryRun: parsed.dryRun === true,
      yes: parsed.yes === true,
      json: parsed.json === true,
      name: parser.args[0],
      commands: list(parsed.commands),
      agents: list(parsed.agents),
      plugins: list(parsed.plugins),
      targets: list(parsed.targets) as ConfigTargetName[] | undefined,
      fragments: list(parsed.fragments) as FragmentName[] | undefined,
      core: specified("core") ? parsed.core : undefined,
      noDependency: parsed.dependency === false,
      model: parsed.model,
      provider: parsed.provider,
      variant: parsed.clearVariant ? null : parsed.variant,
      disconnect: specified("disconnect") ? parsed.disconnect : undefined,
      removeDependency: parsed.removeDependency === true,
    };
  } catch (error) {
    fail("invalid_input", error instanceof Error ? error.message : String(error));
  }
}

async function consent(options: Options, hasChanges: boolean): Promise<void> {
  if (!options.dryRun && !options.yes && hasChanges)
    if (value(await confirmQuestion("Apply the displayed changes?")) !== true)
      fail("cancelled", "No changes applied");
}
function requireApply(options: Options): void {
  if (!options.dryRun && !options.yes && !tty())
    fail("confirmation_required", "Use --dry-run to inspect or --yes to apply outside a terminal");
}
function conflicts(operations: Array<{ operation: string; path: string }>): void {
  const blocked = operations.filter((operation) => operation.operation === "conflict");
  if (blocked.length)
    fail(
      "conflict",
      `Plan blocked; preserved paths: ${blocked.map((operation) => operation.path).join(", ")}. Inspect doctor; restore recorded bytes or resolve ownership before retrying.`,
    );
}

async function integrationSelection(
  options: Options,
  presetsOnly = false,
): Promise<ConfigSetupSelection> {
  if (options.targets !== undefined || options.fragments !== undefined) {
    if (options.targets === undefined || options.fragments === undefined)
      fail("invalid_input", "Supply both --targets and --fragments");
    return normalizeConfigSelection(options.scope, {
      targets: options.targets,
      fragments: options.fragments,
    });
  }
  const defaults = await defaultConfigSelection(options.scope);
  const targets = value(
    await selectOptions(
      "Applications to configure",
      options.scope === "project" ? ["opencode"] : CONFIG_TARGETS,
      defaults.targets,
    ),
  ) as ConfigTargetName[];
  if (!targets.length) return { targets, fragments: [] };
  const connection: FragmentName[] = [];
  if (!presetsOnly && targets.includes("opencode")) {
    const choice = value(
      await selectOption("OpenCode plugin connection", [
        "Keep current connection",
        "Connect and pin this package version",
        "Disconnect agentomatic",
      ]),
    );
    if (choice === 1) connection.push("core-plugin");
    if (choice === 2) connection.push("core-disable");
  }
  const available = CONFIG_FRAGMENTS.filter(
    (fragment) =>
      !["core-plugin", "core-disable"].includes(fragment.name) &&
      fragment.targets.some((target) => targets.includes(target)),
  ).map((fragment) => fragment.name);
  const fragments = value(
    await selectOptions(
      "Application presets",
      available,
      defaults.fragments.filter((fragment) => available.includes(fragment)),
    ),
  ) as FragmentName[];
  return normalizeConfigSelection(options.scope, {
    targets,
    fragments: [...connection, ...fragments],
  });
}

async function modelSelection(
  options: Options,
  name: string,
  current?: AgentProfileRecord,
): Promise<AgentProfileRequest> {
  validateAgentName(name);
  if (options.model) {
    const model = validateModel(
      options.model.includes("/") ? options.model : `${options.provider ?? ""}/${options.model}`,
    );
    return { action: "model-set", name, model, variant: validateVariant(options.variant) ?? null };
  }
  if (options.provider) fail("invalid_input", "--provider requires --model");
  if (options.variant !== undefined) {
    if (!current?.model) fail("invalid_input", "Changing only variant requires a saved model");
    return {
      action: "model-set",
      name,
      model: current.model,
      variant: validateVariant(options.variant) ?? null,
    };
  }
  const choices = current?.model
    ? [
        `Keep current (${current.model}${current.variant ? ` / ${current.variant}` : ""})`,
        "Change model",
        ...(current.variant ? ["Clear variant"] : []),
      ]
    : ["Change model"];
  const choice = choices[value(await selectOption(`Agent: ${name}`, choices))];
  if (choice.startsWith("Keep current"))
    return { action: "model-set", name, model: current!.model, variant: current!.variant ?? null };
  if (choice === "Clear variant")
    return { action: "model-set", name, model: current!.model, variant: null };
  try {
    const models = await availableModels();
    const providers = [...new Set(models.map((model) => model.split("/", 1)[0]))].sort();
    const provider = providers[value(await selectOption("Provider", providers))];
    const candidates = models.filter((model) => model.startsWith(`${provider}/`));
    const model = candidates[value(await selectOption("Model", candidates))];
    const variants = await availableModelVariants(model);
    let variant: string | null = null;
    if (variants.length) {
      const labels = variants.map((item) =>
        item === current?.variant ? `${item} (default)` : item,
      );
      const choice = value(
        await selectOption(
          "Variant",
          ["(none)", ...labels],
          undefined,
          undefined,
          current?.variant ? variants.indexOf(current.variant) + 1 : 0,
        ),
      );
      variant = choice === 0 ? null : (variants[choice - 1] ?? null);
    }
    return { action: "model-set", name, model, variant };
  } catch (error) {
    if (!(error instanceof LifecycleError && error.code === "catalog_unavailable")) throw error;
    process.stderr.write(
      "Start opencode in another terminal to browse models, or enter provider/model manually\n",
    );
    const model = validateModel(value(await promptText("Model (provider/model)")));
    const answer = await promptText(
      current?.variant ? "Variant (empty keeps current)" : "Variant (optional)",
    );
    const variant = (answer ? validateVariant(answer) : current?.variant) ?? null;
    return { action: "model-set", name, model, variant };
  }
}

async function profileDraft(options: Options, names: string[]): Promise<AgentProfileRequest[]> {
  const inventory = await listAgentProfiles(options.scope);
  const records = new Map(
    inventory.profiles
      .filter((profile) => profile.ownership !== "user-owned")
      .map((profile) => [profile.name, { ...profile }]),
  );
  const changes: AgentProfileRequest[] = [];
  while (true) {
    const actions = ["Configure model", "Add critic", "Remove additional critic", "Done"];
    const action =
      actions[
        value(
          await selectOption(
            "Agent models and critics (changes are staged until confirmation)",
            actions,
            process.stdin,
            process.stderr,
            3,
          ),
        )
      ];
    if (action === "Done") return changes;
    if (action === "Add critic") {
      const name = await promptCriticName();
      if (records.has(name)) fail("profile_exists", `Profile already exists: ${name}`);
      const request = { ...(await modelSelection(options, name)), action: "critic-add" as const };
      changes.push(request);
      names.push(name);
      records.set(name, {
        name,
        ownership: "managed",
        state: "current",
        model: request.model,
        variant: request.variant ?? undefined,
      });
    } else {
      const candidates =
        action === "Remove additional critic"
          ? names.filter((name) => name.startsWith("critic-"))
          : names;
      if (!candidates.length) {
        process.stderr.write("No eligible profiles; choose another action.\n");
        continue;
      }
      const name = candidates[value(await selectOption("Agent", candidates))];
      if (action === "Remove additional critic") {
        changes.push({ action: "critic-remove", name });
        names = names.filter((candidate) => candidate !== name);
        records.delete(name);
      } else {
        const request = await modelSelection(options, name, records.get(name));
        changes.push(request);
        records.set(name, {
          ...records.get(name)!,
          model: request.model,
          variant: request.variant ?? undefined,
        });
      }
    }
  }
}

async function componentSelection(options: Options): Promise<InstallerSelection> {
  const supplied = [options.commands, options.agents, options.plugins].some(
    (selection) => selection !== undefined,
  );
  if (supplied && (!options.commands || !options.agents || !options.plugins))
    fail(
      "invalid_input",
      "Supply --commands, --agents, and --plugins together (none selects an empty set)",
    );
  const overrides: Partial<InstallerSelection> = supplied
    ? {
        commands: options.commands,
        agents: options.agents as InstallerSelection["agents"],
        plugins: options.plugins as InstallerSelection["plugins"],
      }
    : {};
  const saved = await installedSelection(options.scope, undefined, undefined, overrides);
  const defaults = saved ?? defaultSelection();
  if (supplied) {
    return normalizeSelection({
      ...overrides,
      core_activation: options.core ?? defaults.core_activation,
    });
  }
  if (!tty()) {
    if (!saved)
      fail(
        "terminal_required",
        "First install outside a terminal requires --commands, --agents, and --plugins",
      );
    return { ...saved, core_activation: options.core ?? saved.core_activation };
  }
  process.stderr.write(
    `Portable skills are installed separately through the skills CLI (npx --yes ${skillsInstallerSpec()} add https://kisev.github.io/skills --agent opencode --copy). Selecting an adapter does not install its skill.\n`,
  );
  const commands = value(
    await selectOptions("Skill command adapters", SKILL_COMMANDS, defaults.commands),
  );
  const agents = value(
    await selectOptions("Fixed agents", FIXED_AGENT_ROLES, defaults.agents),
  ) as InstallerSelection["agents"];
  const plugins = value(
    await selectOptions("Optional plugins", SELECTABLE_PLUGINS, defaults.plugins),
  ) as InstallerSelection["plugins"];
  const core_activation =
    options.core ??
    value(
      await confirmQuestion(
        "Connect the OpenCode plugin and pin its npm dependency?",
        process.stdin,
        process.stderr,
        defaults.core_activation,
      ),
    );
  return normalizeSelection({ commands, agents, plugins, core_activation });
}

async function deploy(options: Options, repair = false): Promise<void> {
  const selection = repair
    ? await installedSelection(options.scope)
    : await componentSelection(options);
  if (!selection) fail("not_installed", "No saved installation to repair; use install");
  requireApply(options);
  let integration: ConfigSetupSelection = {
    targets: ["opencode"],
    fragments: [selection.core_activation ? "core-plugin" : "core-disable"],
  };
  if (
    !repair &&
    (options.targets !== undefined ||
      options.fragments !== undefined ||
      (tty() && value(await confirmQuestion("Configure application presets as well?"))))
  ) {
    integration = await integrationSelection(options, true);
    const chosenCore = integration.fragments.includes("core-plugin")
      ? true
      : integration.fragments.includes("core-disable")
        ? false
        : undefined;
    if (chosenCore !== undefined) {
      if (options.core !== undefined && options.core !== chosenCore)
        fail("invalid_input", "Core flags conflict with the selected connection fragment");
      selection.core_activation = chosenCore;
    }
    integration = {
      targets: [...new Set([...integration.targets, "opencode" as const])],
      fragments: [
        ...new Set([
          ...integration.fragments.filter(
            (fragment) => !["core-plugin", "core-disable"].includes(fragment),
          ),
          selection.core_activation ? ("core-plugin" as const) : ("core-disable" as const),
        ]),
      ],
    };
  }
  let changes: AgentProfileRequest[] = [];
  if (
    !repair &&
    tty() &&
    value(await confirmQuestion("Configure agent models or additional critics now?"))
  ) {
    const inventory = await listAgentProfiles(options.scope);
    changes = await profileDraft(options, [
      ...selection.agents,
      ...inventory.profiles
        .filter(
          (profile) => profile.name.startsWith("critic-") && profile.ownership !== "user-owned",
        )
        .map((profile) => profile.name),
    ]);
  }
  const plan = await preview(
    "install",
    options.scope,
    undefined,
    undefined,
    selection,
    !options.noDependency,
    changes,
  );
  const config = await previewConfigSetup(
    integration,
    options.scope,
    undefined,
    undefined,
    false,
    false,
  );
  const report = {
    status: "ok",
    command: repair ? "maintenance repair" : "install",
    applied: false,
    plan,
    integration: config,
    profile_changes: changes,
    stages: ["owned-components-and-profiles", "npm-dependency", "application-config"],
    atomic_across_stages: false,
  };
  if (!options.json) {
    if (repair)
      process.stdout.write(
        "Repair the saved installation; component selection and model choices are retained.\n",
      );
    const args = [
      repair ? "maintenance" : "install",
      ...(repair ? ["repair"] : []),
      ...scopeArguments(options.scope),
      ...(!repair
        ? [
            "--commands",
            selection.commands.join(",") || "none",
            "--agents",
            selection.agents.join(",") || "none",
            "--plugins",
            selection.plugins.join(",") || "none",
            selection.core_activation ? "--core" : "--no-core",
          ]
        : []),
      ...(options.noDependency ? ["--no-dependency"] : []),
      ...(!repair
        ? [
            "--targets",
            integration.targets.join(","),
            "--fragments",
            integration.fragments
              .filter((fragment) => !["core-plugin", "core-disable"].includes(fragment))
              .join(",") || "none",
          ]
        : []),
    ];
    process.stdout.write(
      renderPlan(plan, {
        applied: false,
        applyHint: changes.length ? undefined : applyHint(args),
      }) + renderConfigSetup(config, { applied: false }),
    );
    if (changes.length)
      process.stdout.write(`Staged profiles: ${terminalSafe(JSON.stringify(changes))}\n`);
    process.stdout.write(
      "Components, npm, and application configuration are separate stages; a later failure does not roll back completed stages.\n",
    );
  }
  if (options.dryRun) {
    if (options.json) json(report);
    return;
  }
  conflicts(plan.operations);
  conflicts(config.operations);
  await consent(
    options,
    [...plan.operations, ...config.operations].some(
      (operation) => operation.operation !== "unchanged",
    ) || Boolean(plan.dependency && plan.dependency.status !== "satisfied"),
  );
  const completed: string[] = [];
  try {
    const applied = await apply(
      "install",
      options.scope,
      undefined,
      undefined,
      { expectedDigest: plan.digest },
      selection,
      !options.noDependency,
      changes,
    );
    completed.push("owned-components-and-profiles");
    if (applied.dependency?.status !== "manual" && applied.dependency)
      completed.push("npm-dependency");
    const connected = await applyConfigSetup(integration, options.scope, undefined, undefined, {
      provisionDependency: false,
      receipt: config.receipt,
      syncSelection: false,
    });
    completed.push("application-config");
    const result = {
      ...report,
      applied: true,
      plan: applied,
      integration: connected,
      completed_stages: completed,
      npm_dependency: applied.dependency?.applied ?? "skipped",
      ...(applied.dependency?.status === "manual"
        ? {
            pending_stages: ["npm-dependency"],
            next_step:
              "Create an owning npm project, then repeat install; the preview reports the dependency directory.",
          }
        : {}),
      requires_restart: applied.requires_restart || connected.requires_restart,
    };
    if (options.json) json(result);
    else
      process.stdout.write(
        renderPlan(applied, { applied: true }) + renderConfigSetup(connected, { applied: true }),
      );
  } catch (error) {
    if (
      error instanceof LifecycleError &&
      error.code === "npm_dependency_failed" &&
      !completed.length
    )
      completed.push("owned-components-and-profiles");
    partial(
      options,
      error,
      completed,
      `Run status, then ${repair ? "maintenance repair" : "install"} with the same selected components; use configure integration for configuration-only continuation.`,
      completed.includes("owned-components-and-profiles") && plan.requires_restart,
    );
  }
}

function partial(
  options: Options,
  error: unknown,
  completed: string[],
  next: string,
  requiresRestart = false,
): never {
  const code = error instanceof LifecycleError ? error.code : "internal_error";
  const message = error instanceof Error ? error.message : String(error);
  if (options.json) {
    json({
      status: completed.length ? "partial" : "error",
      applied: completed.length > 0,
      completed_stages: completed,
      requires_restart: requiresRestart,
      error: { code, message },
      next_step: next,
    });
    process.exitCode = 2;
    throw new ReportedError();
  }
  fail(
    code,
    `${message}\nCompleted: ${completed.join(", ") || "none"}. Restart required: ${requiresRestart ? "yes" : "no"}. ${next}`,
  );
}
class ReportedError extends Error {}

async function configureIntegration(options: Options): Promise<void> {
  requireApply(options);
  const selection = await integrationSelection(options);
  const plan = await previewConfigSetup(
    selection,
    options.scope,
    undefined,
    undefined,
    !options.noDependency,
  );
  if (!options.json)
    process.stdout.write(
      renderConfigSetup(plan, {
        applied: false,
        applyHint: applyHint([
          "configure",
          "integration",
          ...scopeArguments(options.scope),
          "--targets",
          selection.targets.join(",") || "none",
          "--fragments",
          selection.fragments.join(",") || "none",
          ...(options.noDependency ? ["--no-dependency"] : []),
        ]),
      }),
    );
  if (options.dryRun) {
    if (options.json) json({ status: "ok", applied: false, plan });
    return;
  }
  conflicts(plan.operations);
  await consent(
    options,
    plan.confirmable || Boolean(plan.dependency && plan.dependency.status !== "satisfied"),
  );
  try {
    const result = await applyConfigSetup(selection, options.scope, undefined, undefined, {
      provisionDependency: !options.noDependency,
      receipt: plan.receipt,
    });
    if (options.json)
      json({
        status: "ok",
        applied: true,
        plan: result,
        requires_restart: result.requires_restart,
      });
    else process.stdout.write(renderConfigSetup(result, { applied: true }));
  } catch (error) {
    partial(
      options,
      error,
      error instanceof LifecycleError && error.code === "npm_dependency_failed"
        ? ["application-config"]
        : [],
      "Inspect status and retry configure integration with the same selection.",
      error instanceof LifecycleError &&
        error.code === "npm_dependency_failed" &&
        plan.requires_restart,
    );
  }
}

async function profileChange(options: Options, request: AgentProfileRequest): Promise<void> {
  requireApply(options);
  const plan = await previewAgentProfileChange(request, options.scope);
  if (!options.json) {
    const args = request.changes
      ? ["configure", "critics"]
      : request.action === "critic-remove"
        ? ["agent", "remove", request.name!]
        : [
            request.action === "critic-add" ? "agent" : "configure",
            request.action === "critic-add" ? "add-critic" : "agent",
            request.name!,
            "--model",
            request.model!,
            ...(request.variant
              ? ["--variant", request.variant]
              : request.action === "model-set"
                ? ["--clear-variant"]
                : []),
          ];
    process.stdout.write(
      renderPlan(plan, {
        applied: false,
        applyHint: applyHint([...args, ...scopeArguments(options.scope)]),
      }),
    );
  }
  if (options.dryRun) {
    if (options.json) json({ status: "ok", applied: false, plan });
    return;
  }
  conflicts(plan.operations);
  await consent(
    options,
    plan.operations.some((operation) => operation.operation !== "unchanged"),
  );
  const result = await applyAgentProfileChange(request, options.scope, undefined, undefined, {
    expectedDigest: plan.digest,
  });
  if (options.json) json(result);
  else process.stdout.write(renderPlan(result.plan, { applied: true }));
}

async function uninstall(options: Options): Promise<void> {
  requireApply(options);
  const disconnect =
    options.disconnect ??
    (tty()
      ? value(
          await confirmQuestion("Disconnect the agentomatic plugin as well? (other presets stay)"),
        )
      : true);
  const remove =
    options.removeDependency ||
    (tty() &&
      value(
        await selectOption("npm dependency", ["Keep (default)", "Remove agentomatic dependency"]),
      ) === 1);
  const plan = await preview("uninstall", options.scope);
  const selection: ConfigSetupSelection = { targets: ["opencode"], fragments: ["core-disable"] };
  const config = disconnect
    ? await previewConfigSetup(selection, options.scope, undefined, undefined, false, false)
    : undefined;
  const dependency = remove ? await previewDependencyRemoval(options.scope) : undefined;
  const report = {
    status: "ok",
    applied: false,
    plan,
    integration: config,
    dependency_removal: dependency,
    models: "retained",
    portable_skills: "untouched",
    atomic_across_stages: false,
  };
  if (!options.json) {
    process.stdout.write(
      renderPlan(plan, {
        applied: false,
        applyHint: applyHint([
          "uninstall",
          ...scopeArguments(options.scope),
          ...(disconnect ? [] : ["--no-disconnect"]),
          ...(remove ? ["--remove-dependency"] : []),
        ]),
      }) +
        (config ? renderConfigSetup(config, { applied: false }) : "Plugin connection: retained\n"),
    );
    process.stdout.write(
      `npm dependency: ${remove ? `remove ${dependency?.names.join(", ") || "none present"}` : "retained"}\nSaved models: retained\nPortable skills and other presets: untouched\nSeparate stages; completed changes are retained on a later failure.\n`,
    );
  }
  if (options.dryRun) {
    if (options.json) json(report);
    return;
  }
  conflicts(plan.operations);
  if (config) conflicts(config.operations);
  await consent(
    options,
    plan.operations.some((operation) => operation.operation !== "unchanged") ||
      Boolean(config?.confirmable) ||
      Boolean(dependency?.names.length),
  );
  const completed: string[] = [];
  try {
    const removed = await apply("uninstall", options.scope, undefined, undefined, {
      expectedDigest: plan.digest,
    });
    completed.push("owned-components");
    const disconnected = config
      ? await applyConfigSetup(selection, options.scope, undefined, undefined, {
          provisionDependency: false,
          receipt: config.receipt,
          syncSelection: false,
        })
      : undefined;
    if (config) completed.push("plugin-disconnection");
    if (dependency) {
      await removeDependency(dependency);
      completed.push("npm-removal");
    }
    if (options.json)
      json({
        ...report,
        applied: true,
        plan: removed,
        integration: disconnected,
        completed_stages: completed,
        requires_restart: removed.requires_restart || Boolean(disconnected?.requires_restart),
      });
    else
      process.stdout.write(
        "Uninstall complete. Saved models retained; restart OpenCode if files changed.\n",
      );
  } catch (error) {
    partial(
      options,
      error,
      completed,
      "Inspect status and retry uninstall with the same disconnect and dependency choices.",
      (completed.includes("owned-components") && plan.requires_restart) ||
        (completed.includes("plugin-disconnection") && Boolean(config?.requires_restart)),
    );
  }
}

async function run(args: string[]): Promise<void> {
  if (args.includes("--version") || args.includes("-V")) {
    if (args.some((arg) => !["--version", "-V", "--json"].includes(arg)))
      fail("invalid_input", "--version accepts only --json");
    if (args.includes("--json")) json({ status: "ok", version: CATALOG.version });
    else process.stdout.write(`${CATALOG.version}\n`);
    return;
  }
  if (args[0] === "help") args = [...args.slice(1), "--help"];
  let topic = args.shift() ?? "";
  if (["configure", "agent", "maintenance"].includes(topic) && args[0] && !args[0].startsWith("-"))
    topic += ` ${args.shift()}`;
  if (["--help", "-h", ""].includes(topic)) {
    if (args.some((arg) => !["--help", "-h"].includes(arg)))
      fail("invalid_input", "Unexpected root help argument");
    process.stdout.write(help());
    return;
  }
  if (args.includes("--help") || args.includes("-h")) {
    if (!commands[topic]) fail("invalid_input", `Unknown command: ${topic}`);
    parse(
      topic,
      args.filter((arg) => !["--help", "-h"].includes(arg)),
    );
    process.stdout.write(help(topic));
    return;
  }
  if (!commands[topic]) {
    const match = [...new Set(Object.keys(commands).map((key) => key.split(" ", 1)[0]))].find(
      (root) => root.startsWith(topic) || topic.startsWith(root),
    );
    fail(
      "invalid_input",
      `Unknown command: ${topic}.${match ? ` Did you mean '${match}'?` : ""} Use install, configure, status, doctor, uninstall, agent, maintenance, or catalog.`,
    );
  }
  const options = parse(topic, args);
  if (topic === "configure") {
    requireApply(options);
    const routes = ["configure components", "configure agent", "configure integration"];
    const selected = value(
      await selectOption("What would you like to configure?", [
        "Installed components",
        "Agent models and critics",
        "Application connection and presets",
      ]),
    );
    topic = routes[selected];
  }
  if (topic === "install" || topic === "configure components" || topic === "maintenance repair") {
    await deploy(options, topic === "maintenance repair");
    return;
  }
  if (topic === "configure integration") {
    await configureIntegration(options);
    return;
  }
  if (topic === "uninstall") {
    await uninstall(options);
    return;
  }
  if (topic === "catalog") {
    json({ schema_version: 1, status: "ok", ...CATALOG });
    return;
  }
  if (topic === "status" || topic === "agent list") {
    const inventory = await listAgentProfiles(options.scope);
    if (topic === "agent list") {
      if (options.json) json({ status: "ok", inventory });
      else process.stdout.write(renderInventory(inventory));
      return;
    }
    const selection = await installedSelection(options.scope);
    const connection = await inspectIntegration(options.scope);
    const dependency = planDependency(options.scope);
    const result = {
      status: connection.problem ? "incomplete" : "ok",
      scope: options.scope,
      installed: Boolean(selection),
      selection,
      connection,
      dependency,
      inventory,
    };
    if (options.json) json(result);
    else
      process.stdout.write(
        `Installation: ${selection ? "present" : "not installed"}\nCommands: ${selection?.commands.join(", ") || "none"}\nPlugins: ${selection?.plugins.join(", ") || "none"}\nPlugin connection: ${connection.connected ? "active" : "not confirmed (use doctor)"}\nnpm dependency: ${dependency.status}\n` +
          renderInventory(inventory),
      );
    return;
  }
  if (topic === "doctor") {
    const report = await collectDoctorFacts(options.scope);
    if (options.json) json(report);
    else process.stdout.write(renderDoctor(report));
    process.exitCode = doctorExitCode(report);
    return;
  }
  if (
    topic === "configure critics" ||
    topic === "configure agent" ||
    topic === "agent add-critic"
  ) {
    const inventory = await listAgentProfiles(options.scope);
    // configure critics is an alias; a nameless configure agent opens the same staged editor.
    if (topic === "configure critics" || (topic === "configure agent" && !options.name)) {
      requireApply(options);
      if (!options.json) process.stdout.write(renderCriticsTable(inventory));
      const changes = await profileDraft(
        options,
        inventory.profiles
          .filter((profile) => profile.ownership !== "user-owned")
          .map((profile) => profile.name),
      );
      if (!changes.length) {
        if (options.json) json({ status: "ok", applied: false });
        else process.stdout.write("No profile changes selected.\n");
        return;
      }
      await profileChange(options, { action: "model-set", changes });
      return;
    }
    let name = options.name;
    if (!name) {
      if (topic === "agent add-critic") name = await promptCriticName();
      else {
        const names = inventory.profiles
          .filter((profile) => profile.ownership !== "user-owned")
          .map((profile) => profile.name);
        name = names[value(await selectOption("Agent", names))];
      }
    }
    if (topic === "agent add-critic" && !name.startsWith("critic-")) name = `critic-${name}`;
    const request = await modelSelection(
      options,
      name,
      inventory.profiles.find((profile) => profile.name === name),
    );
    await profileChange(options, {
      ...request,
      action: topic === "agent add-critic" ? "critic-add" : "model-set",
    });
    return;
  }
  if (topic === "agent remove") {
    if (!options.name) fail("invalid_input", "agent remove requires an additional critic name");
    await profileChange(options, { action: "critic-remove", name: options.name });
    return;
  }
  if (topic === "maintenance recover") {
    requireApply(options);
    const plan = await recoverConfigSetup(options.scope, true);
    if (!options.json)
      process.stdout.write(
        `Recovery paths:\n${plan.paths.map((path) => `  ${terminalSafe(path)}`).join("\n")}\n`,
      );
    if (options.dryRun) {
      if (options.json) json({ status: "ok", applied: false, plan });
      return;
    }
    await consent(options, plan.paths.length > 0);
    const result = await recoverConfigSetup(
      options.scope,
      false,
      undefined,
      undefined,
      plan.digest,
    );
    if (options.json) json({ status: "ok", ...result, next_step: "Request a fresh preview" });
    else process.stdout.write("Recovery complete; request a fresh preview.\n");
    return;
  }
  if (topic === "maintenance cleanup") {
    requireApply(options);
    const plan = await previewReconcile(options.scope);
    if (!options.json)
      process.stdout.write(
        renderReconcile(plan, {
          applied: false,
          applyHint: applyHint(["maintenance", "cleanup", ...scopeArguments(options.scope)]),
        }),
      );
    if (options.dryRun) {
      if (options.json) json({ status: "ok", applied: false, plan });
      return;
    }
    if (plan.conflicts.length || plan.modified_managed.length)
      fail(
        "conflict",
        "Cleanup blocked by modified or conflicting files; inspect the preview paths and restore recorded bytes before retrying",
      );
    if (!plan.confirmable) {
      if (options.json) json({ status: "ok", applied: false, plan });
      return;
    }
    await consent(options, true);
    const result = await applyReconcile(options.scope, undefined, undefined, {
      expectedDigest: plan.digest,
    });
    if (options.json) json(result);
    else process.stdout.write(renderReconcile(result.plan, { applied: true }));
    return;
  }
  process.stdout.write(help(topic));
}

try {
  await run(process.argv.slice(2));
} catch (error) {
  if (!(error instanceof ReportedError)) {
    const code = error instanceof LifecycleError ? error.code : "internal_error";
    const message = error instanceof Error ? error.message : String(error);
    if (machineOutput || process.argv.includes("--json"))
      json({ status: "error", error: { code, message } });
    else if (diagnosticJSON)
      process.stderr.write(
        `${JSON.stringify({ level: "error", phase: "agentomatic.error", code, message })}\n`,
      );
    else process.stderr.write(`Error [${code}]: ${terminalSafe(message)}\n`);
  }
  process.exitCode = 2;
} finally {
  diagnostics?.close();
}
