#!/usr/bin/env node
import { createInterface } from "node:readline/promises";

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
import { apply, InstallerError, preview, result, type Action } from "./installer.js";
import { LifecycleError, type Scope } from "./lifecycle.js";

type Options = { scope?: Scope; dryRun: boolean; confirm?: string; provider?: string; model?: string; variant?: string | null; name?: string };

function parseOptions(values: string[]): Options {
  const options: Options = { dryRun: false };
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

async function choose(label: string, values: readonly string[], input: ReturnType<typeof createInterface>): Promise<string> {
  process.stderr.write(`${label}:\n${values.map((value, index) => `  ${index + 1}. ${value}`).join("\n")}\n`);
  const answer = await input.question("> ");
  const index = Number(answer) - 1;
  if (!Number.isSafeInteger(index) || !values[index]) throw new InstallerError("invalid_input", `Invalid ${label.toLowerCase()} selection`);
  return values[index];
}

async function interactiveSelection(options: Options): Promise<{ name: string; model: string; variant?: string }> {
  if (!process.stdin.isTTY || !process.stderr.isTTY) throw new InstallerError("terminal_required", "agent configure requires a terminal or explicit --provider and --model");
  const input = createInterface({ input: process.stdin, output: process.stderr });
  try {
    const inventory = await listAgentProfiles(options.scope!);
    const configurable = inventory.profiles.filter((item) => item.ownership !== "user-owned").map((item) => item.name);
    const name = options.name ? validateAgentName(options.name) : await choose("Agent", configurable.length ? configurable : FIXED_AGENT_ROLES, input);
    if (options.provider && options.model) return { name, model: exactModel(options)!, ...(validateVariant(options.variant) ? { variant: validateVariant(options.variant) } : {}) };
    let models: string[];
    try {
      models = await availableModels();
    } catch (error) {
      if (!(error instanceof AgentProfileError) || error.code !== "catalog_unavailable") throw error;
      const provider = options.provider ?? (await input.question("Provider: ")).trim();
      const model = options.model ?? (await input.question("Model: ")).trim();
      const variant = options.variant === undefined ? (await input.question("Variant (optional): ")).trim() : options.variant;
      return { name, model: validateModel(model.includes("/") ? model : `${provider}/${model}`), ...(validateVariant(variant) ? { variant: validateVariant(variant) } : {}) };
    }
    const providers = [...new Set(models.map((model) => model.split("/", 1)[0]))].sort();
    const provider = options.provider ?? (await choose("Provider", providers, input));
    const selectedModel = options.model
      ? exactModel({ ...options, provider })!
      : await choose("Model", models.filter((model) => model.startsWith(`${provider}/`)), input);
    let variants: string[] = [];
    try {
      variants = await availableModelVariants(selectedModel);
    } catch (error) {
      if (!(error instanceof AgentProfileError) || error.code !== "catalog_unavailable") throw error;
    }
    const variant = options.variant === null
      ? undefined
      : options.variant ?? (variants.length ? await choose("Variant", ["none", ...variants.filter((value) => value !== "none")], input) : (await input.question("Variant (optional): ")).trim());
    return { name, model: selectedModel, ...(variant && variant !== "none" ? { variant: validateVariant(variant) } : {}) };
  } finally {
    input.close();
  }
}

async function runProfile(request: AgentProfileRequest, options: Options): Promise<void> {
  requireConfirmationMode(options);
  if (options.dryRun) {
    const plan = await previewAgentProfileChange(request, options.scope!);
    process.stdout.write(`${JSON.stringify({ status: "ok", applied: false, requires_restart: false, plan }, null, 2)}\n`);
  } else {
    process.stdout.write(`${JSON.stringify(await applyAgentProfileChange(request, options.scope!, options.confirm!), null, 2)}\n`);
  }
}

async function run(arguments_: string[]): Promise<void> {
  const [domain, operation, ...rest] = arguments_;
  if (domain === "install" || domain === "uninstall") {
    if (operation?.startsWith("--") || operation === undefined) rest.unshift(...(operation ? [operation] : []));
    else throw new InstallerError("invalid_input", `Unexpected argument: ${operation}`);
    const options = parseOptions(rest);
    if (options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "Installer accepts only scope and confirmation options");
    requireConfirmationMode(options);
    const action = domain as Action;
    process.stdout.write(`${result(options.dryRun ? await preview(action, options.scope!) : await apply(action, options.scope!, options.confirm!), !options.dryRun)}\n`);
    return;
  }
  if (domain === "agent" && operation === "list") {
    const options = parseOptions(rest);
    if (options.dryRun || options.confirm || options.name || options.provider || options.model || options.variant !== undefined) throw new InstallerError("invalid_input", "agent list accepts only --scope");
    process.stdout.write(`${JSON.stringify({ status: "ok", inventory: await listAgentProfiles(options.scope!) }, null, 2)}\n`);
    return;
  }
  if (domain === "agent" && operation === "configure") {
    const options = parseOptions(rest);
    requireConfirmationMode(options);
    const selected = options.provider && options.model && options.name
      ? { name: validateAgentName(options.name), model: exactModel(options)!, ...(validateVariant(options.variant) ? { variant: validateVariant(options.variant) } : {}) }
      : await interactiveSelection(options);
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
      if (!model) throw new InstallerError("invalid_input", "critic add requires --provider and --model, or exact --model provider/model");
      await runProfile({ action: "critic-add", name, model, variant: options.variant ?? null }, options);
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
    process.stdout.write(`${JSON.stringify({ status: "error", error: { code: known.code, message: known.message } })}\n`);
    process.exitCode = 2;
  }
}

void main();
