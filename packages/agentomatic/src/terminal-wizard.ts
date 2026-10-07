import type { Readable, Writable } from "node:stream";
import * as clack from "@clack/prompts";

import { InstallerError } from "./installer.js";

function interactiveStreams(stdin: Readable, stderr: Writable): void {
  if (!isTTY(stdin) || !isTTY(stderr))
    throw new InstallerError(
      "terminal_required",
      "This operation requires an interactive terminal",
    );
}

function isTTY(stream: Readable | Writable): boolean {
  return Boolean((stream as { isTTY?: boolean }).isTTY);
}

function validateOptions(options: readonly string[]): void {
  if (options.length === 0)
    throw new InstallerError("invalid_input", "Interactive selector requires at least one option");
  if (new Set(options).size !== options.length)
    throw new InstallerError("invalid_input", "Interactive selector options must be unique");
}

export async function selectOption(
  label: string,
  options: readonly string[],
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
  initial = 0,
): Promise<number | null> {
  interactiveStreams(stdin, stderr);
  validateOptions(options);
  const value = await clack.select({
    message: label,
    options: options.map((option, index) => ({ value: index, label: option })),
    initialValue: Math.max(0, Math.min(initial, options.length - 1)),
    input: stdin,
    output: stderr,
  });
  if (clack.isCancel(value)) return null;
  return value as number;
}

// The multiselect contract: each option carries a data-driven description and
// the message states the all/none controls, so every group is self-explanatory.
const MULTISELECT_CONTROLS = " (move: up/down; toggle: space; all/none: a; enter confirms)";

export async function selectOptions(
  label: string,
  options: readonly string[],
  initialSelected: readonly string[] = [],
  hints?: readonly (string | undefined)[],
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
): Promise<string[] | null> {
  interactiveStreams(stdin, stderr);
  validateOptions(options);
  const allowed = new Set(options);
  for (const value of initialSelected) {
    if (!allowed.has(value))
      throw new InstallerError("invalid_input", `Unknown initial selector option: ${value}`);
  }
  const value = await clack.multiselect({
    message: `${label}${MULTISELECT_CONTROLS}`,
    options: options.map((option, index) => ({
      value: option,
      label: option,
      ...(hints?.[index] ? { hint: hints[index] } : {}),
    })),
    initialValues: [...initialSelected],
    required: false,
    input: stdin,
    output: stderr,
  });
  if (clack.isCancel(value)) return null;
  return value as string[];
}

export async function promptText(
  label: string,
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
): Promise<string | null> {
  interactiveStreams(stdin, stderr);
  const value = await clack.text({ message: label, input: stdin, output: stderr });
  if (clack.isCancel(value)) return null;
  const trimmed = (value as string).trim();
  return trimmed.length ? trimmed : null;
}

export async function confirmQuestion(
  label: string,
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
  initialValue = true,
): Promise<boolean | null> {
  interactiveStreams(stdin, stderr);
  const value = await clack.confirm({ message: label, input: stdin, output: stderr, initialValue });
  if (clack.isCancel(value)) return null;
  return value as boolean;
}
