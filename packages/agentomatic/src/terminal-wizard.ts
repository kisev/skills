import type { Readable, Writable } from "node:stream";
import * as clack from "@clack/prompts";

import { InstallerError } from "./installer.js";

// Sentinel returned when the user chooses the "Back" item; `runWizard` steps
// back to the previous enabled screen and restores the saved answer.
export const BACK = Symbol("wizard-back");
export type BackSignal = typeof BACK;

export function isBack(value: unknown): value is BackSignal {
  return value === BACK;
}

const BACK_VALUE = "$__agentomatic_back__";
const BACK_LABEL = "← Back";

// A wizard is an ordered list of screens over one mutable answer object. Each
// step returns the next answer, BACK to revisit the previous enabled screen, or
// throws (via the caller's `value`) on cancellation. Conditional screens declare
// `enabled` so Back never lands on a skipped screen.
export type WizardStep<T> = {
  enabled?: (state: T) => boolean;
  run: (state: T, back: boolean) => Promise<T | BackSignal>;
};

export async function runWizard<T>(initial: T, steps: ReadonlyArray<WizardStep<T>>): Promise<T> {
  const enabled = (index: number, state: T): boolean =>
    !steps[index].enabled || steps[index].enabled!(state);
  let state = initial;
  let index = 0;
  while (index < steps.length) {
    if (!enabled(index, state)) {
      index += 1;
      continue;
    }
    let previous = index - 1;
    while (previous >= 0 && !enabled(previous, state)) previous -= 1;
    const result = await steps[index].run(state, previous >= 0);
    if (result === BACK) {
      if (previous < 0) continue;
      index = previous;
      continue;
    }
    state = result;
    index += 1;
  }
  return state;
}
const DEFAULT_COLUMNS = 80;
// clack renders a guide and a state marker ("│  ◻ ") before the label; keep the
// composed label inside the remaining terminal columns so it never wraps.
const LABEL_RESERVE = 8;

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

function terminalColumns(stderr: Writable): number {
  const columns = (stderr as { columns?: number }).columns;
  return Number.isFinite(columns) && (columns ?? 0) > 0 ? (columns as number) : DEFAULT_COLUMNS;
}

// Long single-line values are cut to the terminal width with a trailing
// ellipsis; the description is never silently dropped for a normal terminal.
export function truncateLine(value: string, width: number): string {
  if (width <= 1) return "…";
  return [...value].length <= width ? value : `${[...value].slice(0, width - 1).join("")}…`;
}

// Every option label carries its data-driven description so the text is
// visible on every line, not only under the cursor (clack renders `hint` for
// the focused option only).
export function optionLabel(
  name: string,
  description: string | undefined,
  columns: number,
): string {
  const combined = description ? `${name} — ${description}` : name;
  return truncateLine(combined, Math.max(12, columns - LABEL_RESERVE));
}

function backOption(): { value: string; label: string } {
  return { value: BACK_VALUE, label: BACK_LABEL };
}

export async function selectOption(
  label: string,
  options: readonly string[],
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
  initial = 0,
  descriptions?: readonly (string | undefined)[],
  back = false,
): Promise<number | null | BackSignal> {
  interactiveStreams(stdin, stderr);
  validateOptions(options);
  const columns = terminalColumns(stderr);
  const entries: Array<{ value: string; label: string }> = options.map((option, index) => ({
    value: String(index),
    label: optionLabel(option, descriptions?.[index], columns),
  }));
  if (back) entries.push(backOption());
  const value = await clack.select<string>({
    message: label,
    options: entries,
    initialValue: String(Math.max(0, Math.min(initial, options.length - 1))),
    input: stdin,
    output: stderr,
  });
  if (clack.isCancel(value)) return null;
  if (value === BACK_VALUE) return BACK;
  return Number(value);
}

// The multiselect contract: each option carries a data-driven description and
// the message states the all/none controls, so every group is self-explanatory.
// SIMPLIFY: Back is a normal option, so the all/none key also selects it -> upgrade to a dedicated Back key if clack exposes one.
const MULTISELECT_CONTROLS = " (move: up/down; toggle: space; all/none: a; enter confirms)";

export async function selectOptions(
  label: string,
  options: readonly string[],
  initialSelected: readonly string[] = [],
  descriptions?: readonly (string | undefined)[],
  stdin: Readable = process.stdin,
  stderr: Writable = process.stderr,
  back = false,
): Promise<string[] | null | BackSignal> {
  interactiveStreams(stdin, stderr);
  validateOptions(options);
  const allowed = new Set(options);
  for (const value of initialSelected) {
    if (!allowed.has(value))
      throw new InstallerError("invalid_input", `Unknown initial selector option: ${value}`);
  }
  const columns = terminalColumns(stderr);
  const entries: Array<{ value: string; label: string }> = options.map((option, index) => ({
    value: option,
    label: optionLabel(option, descriptions?.[index], columns),
  }));
  if (back) entries.push(backOption());
  const value = await clack.multiselect<string>({
    message: `${label}${MULTISELECT_CONTROLS}`,
    options: entries,
    initialValues: [...initialSelected],
    required: false,
    input: stdin,
    output: stderr,
  });
  if (clack.isCancel(value)) return null;
  const selected = value as string[];
  if (selected.includes(BACK_VALUE)) return BACK;
  return selected;
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
