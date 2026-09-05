#!/usr/bin/env node
import { apply, InstallerError, preview, result, type Action, type Scope } from "./installer.js";

type Parsed = { action: Action; scope: Scope; dryRun: boolean; confirm?: string };

function parseArguments(arguments_: string[]): Parsed {
  const [action, ...rest] = arguments_;
  if (action !== "install" && action !== "uninstall") throw new InstallerError("invalid_input", "Use install or uninstall");
  let scope: Scope | undefined;
  let dryRun = false;
  let confirm: string | undefined;
  for (let index = 0; index < rest.length; index += 1) {
    const value = rest[index];
    if (value === "--scope") {
      const candidate = rest[++index];
      if (candidate !== "global" && candidate !== "project") throw new InstallerError("invalid_input", "--scope must be global or project");
      if (scope) throw new InstallerError("invalid_input", "--scope may be supplied once");
      scope = candidate;
    } else if (value === "--dry-run") {
      if (dryRun) throw new InstallerError("invalid_input", "--dry-run may be supplied once");
      dryRun = true;
    } else if (value === "--confirm") {
      if (confirm) throw new InstallerError("invalid_input", "--confirm may be supplied once");
      confirm = rest[++index];
      if (!confirm) throw new InstallerError("invalid_input", "--confirm requires a digest");
    } else {
      throw new InstallerError("invalid_input", `Unknown argument: ${value}`);
    }
  }
  if (!scope) throw new InstallerError("invalid_input", "--scope is required");
  if (dryRun === Boolean(confirm)) throw new InstallerError("invalid_input", "Use exactly one of --dry-run or --confirm <digest>");
  return { action, scope, dryRun, confirm };
}

async function main(): Promise<void> {
  try {
    const parsed = parseArguments(process.argv.slice(2));
    if (parsed.dryRun) {
      process.stdout.write(`${result(await preview(parsed.action, parsed.scope), false)}\n`);
      return;
    }
    process.stdout.write(`${result(await apply(parsed.action, parsed.scope, parsed.confirm!), true)}\n`);
  } catch (error) {
    const known = error instanceof InstallerError ? error : new InstallerError("internal_error", error instanceof Error ? error.message : String(error));
    process.stdout.write(`${JSON.stringify({ status: "error", error: { code: known.code, message: known.message } })}\n`);
    process.exitCode = 2;
  }
}

void main();
