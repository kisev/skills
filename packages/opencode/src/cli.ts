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
import { renderDoctor, renderInventory, renderPlan, renderReconcile, shellCommand, terminalSafe } from "./cli-output.js";
import { collectDoctorFacts, doctorExitCode } from "./doctor.js";
import { apply, InstallerError, preview, type Action } from "./installer.js";
import { LifecycleError, type Scope } from "./lifecycle.js";
import { applyReconcile, previewReconcile } from "./reconcile.js";
import { promptText, selectOption } from "./terminal-wizard.js";

type Options = { scope?: Scope; dryRun: boolean; json: boolean; confirm?: string; provider?: string; model?: string; variant?: string | null; name?: string };

function parseOptions(values: string[]): Options {
  const options: Options = { dryRun: false, json: false };
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith("--")) {
      if (options.name) throw new InstallerError("invalid_input", `Unexpected argument: ${value}`);
      options.name = value;
    } else if (value === "--scope") {
      const scope = values[++index];
      if (scope !== "global" && scope !== "project") throw new InstallerError("invalid_input", "--scope must be global or project");
      if (options.scope) throw new InstallerError("invalid_input", "--scope may be supplied once");
      options.scope = scope;
    } else if (value === "--dry-run") {
      if (options.dryRun) throw new InstallerError("invalid_input", "--dry-run may be supplied once");
      options.dryRun = true;
    } else if (value === "--confirm") {
      if (options.confirm) throw new InstallerError("invalid_input", "--confirm may be supplied once");
      options.confirm = values[++index];
      if (!options.confirm) throw new InstallerError("invalid_input", "--confirm requires a digest");
    } else if (value === "--provider") {
      options.provider = values[++index];
      if (!options.provider) throw new InstallerError("invalid_input", "--provider requires a value");
    } else if (value === "--model") {
      options.model = values[++index];
      if (!options.model) throw new InstallerError("invalid_input", "--model requires a value");
    } else if (value === "--variant") {
      options.variant = values[++index];
      if (!options.variant) throw new InstallerError("invalid_input", "--variant requires a value");
    } else if (value === "--clear-variant") {
      if (options.variant !== undefined) throw new InstallerError("invalid_input", "Use only one variant option");
      options.variant = null;
    } else if (value === "--json") {
      if (options.json) throw new InstallerError("invalid_input", "--json may be supplied once");
      options.json = true;
    } else {
      throw new InstallerError("invalid_input", `Unknown argument: ${value}`);
    }
  }
  if (!options.scope) throw new InstallerError("invalid_input", "--scope is required");
  return options;
}

function requireConfirmationMode(options: Options): void {
  if (options.dryRun === Boolean(options.confirm)) throw new InstallerError("invalid_input", "Use exactly one of --dry-run or --confirm <digest>");
}

function exactModel(options: Options): string | undefined {
  if (!options.model) return undefined;
  if (options.model.includes("/")) {
    const model = validateModel(options.model);
    if (options.provider && model.split("/", 1)[0] !== options.provider) throw new InstallerError("invalid_input", "--provider does not match the exact --model value");
    return model;
  }
  if (!options.provider) throw new InstallerError("invalid_input", "--provider is required when --model is not provider/model");
  return validateModel(`${options.provider}/${options.model}`);
}

async function interactiveSelection(options: Options, action: "model-set" | "critic-add" = "model-set"): Promise<{ name: string; model: string; variant?: string }> {
  if (!process.stdin.isTTY || !process.stderr.isTTY) {
    throw new InstallerError("terminal_required", "agent configure requires a terminal or explicit --provider and --model");
  }
  const inventory = await listAgentProfiles(options.scope!);
  const configurable = inventory.profiles.filter((item) => item.ownership !== "user-owned");

  let name: string;
  if (options.name) {
    name = action === "critic-add" && !options.name.startsWith("critic-")
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
          process.stderr.write("\nModel catalog is unavailable.\nUse direct CLI with exact --model provider/model and optional --variant.\n\n");
          throw new InstallerError("catalog_unavailable", "Use direct CLI with exact --model provider/model");
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
          process.stderr.write("\nModel variant metadata is unavailable.\nUse direct CLI with exact --model provider/model and optional --variant.\n\n");
          throw new InstallerError("catalog_unavailable", "Use direct CLI with exact --model provider/model");
        }
        throw error;
      }

      showTarget(selectedModel, selectedVariant);
      return { name, model: selectedModel, ...(selectedVariant ? { variant: selectedVariant } : {}) };
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
    if (options.json) process.stdout.write(`${JSON.stringify({ status: "ok", applied: false, requires_restart: false, plan }, null, 2)}\n`);
    else process.stdout.write(renderPlan(plan, { applied: false, confirmationCommand: shellCommand(profileConfirmationArguments(request, options.scope!, plan.digest)) }));
  } else {
    const applied = await applyAgentProfileChange(request, options.scope!, options.confirm!);
    if (options.json) process.stdout.write(`${JSON.stringify(applied, null, 2)}\n`);
    else process.stdout.write(renderPlan(applied.plan, { applied: true }));
  }
}

function profileConfirmationArguments(request: AgentProfileRequest, scope: Scope, digest: string): string[] {
  if (request.action === "reconcile") return ["agent", "reconcile", "--scope", scope, "--confirm", digest];
  if (request.action === "critic-remove") return ["critic", "remove", request.name!, "--scope", scope, "--confirm", digest];
  const command = request.action === "critic-add" ? ["critic", "add", request.name!] : ["agent", "model-set", request.name!];
  command.push("--scope", scope, "--model", request.model!);
  if (request.variant) command.push("--variant", request.variant);
  else if (request.action === "model-set") command.push("--clear-variant");
  command.push("--confirm", digest);
  return command;
}

async function run(arguments_: string[]): Promise<void> {
  const [domain, operation, ...rest] = arguments_;
  if (domain === "doctor") {
    if (operation) rest.unshift(operation);
    const options = parseOptions(rest);
    if (options.dryRun || options.confirm || options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "doctor accepts only --scope and --json");
    const report = await collectDoctorFacts(options.scope!);
    if (options.json) process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    else process.stdout.write(renderDoctor(report));
    process.exitCode = doctorExitCode(report);
    return;
  }
  if (domain === "reconcile") {
    if (operation) rest.unshift(operation);
    const options = parseOptions(rest);
    if (options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "reconcile accepts only scope and confirmation options");
    requireConfirmationMode(options);
    if (options.dryRun) {
      const plan = await previewReconcile(options.scope!);
      if (options.json) process.stdout.write(`${JSON.stringify({ status: "ok", applied: false, plan }, null, 2)}\n`);
      else process.stdout.write(renderReconcile(plan, { applied: false, confirmationCommand: shellCommand(["reconcile", "--scope", options.scope!, "--confirm", plan.digest]) }));
    } else {
      const applied = await applyReconcile(options.scope!, options.confirm!);
      if (options.json) process.stdout.write(`${JSON.stringify(applied, null, 2)}\n`);
      else process.stdout.write(renderReconcile(applied.plan, { applied: true }));
    }
    return;
  }
  if (domain === "install" || domain === "uninstall") {
    if (operation?.startsWith("--") || operation === undefined) rest.unshift(...(operation ? [operation] : []));
    else throw new InstallerError("invalid_input", `Unexpected argument: ${operation}`);
    const options = parseOptions(rest);
    if (options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "Installer accepts only scope and confirmation options");
    requireConfirmationMode(options);
    const action = domain as Action;
    if (options.dryRun) {
      const plan = await preview(action, options.scope!);
      if (options.json) process.stdout.write(`${JSON.stringify({ status: "ok", applied: false, requires_restart: false, plan }, null, 2)}\n`);
      else process.stdout.write(renderPlan(plan, { applied: false, confirmationCommand: shellCommand([action, "--scope", options.scope!, "--confirm", plan.digest]) }));
    } else {
      const plan = await apply(action, options.scope!, options.confirm!);
      if (options.json) process.stdout.write(`${JSON.stringify({ status: "ok", applied: true, requires_restart: plan.requires_restart, plan }, null, 2)}\n`);
      else process.stdout.write(renderPlan(plan, { applied: true }));
    }
    return;
  }
  if (domain === "agent" && operation === "list") {
    const options = parseOptions(rest);
    if (options.dryRun || options.confirm || options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "agent list accepts only --scope");
    const inventory = await listAgentProfiles(options.scope!);
    if (options.json) process.stdout.write(`${JSON.stringify({ status: "ok", inventory }, null, 2)}\n`);
    else process.stdout.write(renderInventory(inventory));
    return;
  }
  if (domain === "agent" && operation === "configure") {
    const options = parseOptions(rest);
    requireConfirmationMode(options);
    const selected = options.provider && options.model && options.name
      ? { name: validateAgentName(options.name), model: exactModel(options)!, ...(validateVariant(options.variant) ? { variant: validateVariant(options.variant) } : {}) }
      : await interactiveSelection(options, "model-set");
    await runProfile({ action: "model-set", ...selected, variant: selected.variant ?? null }, options);
    return;
  }
  if (domain === "agent" && operation === "model-set") {
    const options = parseOptions(rest);
    const name = validateAgentName(options.name ?? "");
    const model = exactModel(options);
    if (!model) throw new InstallerError("invalid_input", "agent model-set requires --provider and --model, or exact --model provider/model");
    await runProfile({ action: "model-set", name, model, variant: options.variant ?? null }, options);
    return;
  }
  if (domain === "agent" && operation === "reconcile") {
    const options = parseOptions(rest);
    if (options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "agent reconcile accepts only scope and confirmation options");
    await runProfile({ action: "reconcile" }, options);
    return;
  }
  if (domain === "critic" && (operation === "add" || operation === "remove")) {
    const options = parseOptions(rest);
    const name =
      options.name === "critic" || options.name?.startsWith("critic-")
        ? options.name
        : `critic-${options.name ?? ""}`;
    if (operation === "add") {
      const model = exactModel(options);
      if (!model) {
        const selected = await interactiveSelection(options, "critic-add");
        await runProfile({ action: "critic-add", name: selected.name, model: selected.model, variant: selected.variant ?? null }, options);
      } else {
        await runProfile({ action: "critic-add", name, model, variant: options.variant ?? null }, options);
      }
    } else {
      if (options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "critic remove does not accept model options");
      await runProfile({ action: "critic-remove", name }, options);
    }
    return;
  }
  throw new InstallerError("invalid_input", "Use install, uninstall, agent list|configure|model-set|reconcile, or critic add|remove");
}

async function main(): Promise<void> {
  try {
    await run(process.argv.slice(2));
  } catch (error) {
    const known = error instanceof LifecycleError ? error : new InstallerError("internal_error", error instanceof Error ? error.message : String(error));
    if (process.argv.includes("--json")) process.stdout.write(`${JSON.stringify({ status: "error", error: { code: known.code, message: known.message } })}\n`);
    else process.stderr.write(`Error [${known.code}]: ${terminalSafe(known.message)}\n`);
    process.exitCode = 2;
  }
}

void main();
