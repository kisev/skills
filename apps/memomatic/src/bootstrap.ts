import { readFile } from "node:fs/promises";

import { visibilityForSource } from "./visibility.js";
import type { IndexedEntry } from "./store.js";
import type { MemomaticContext } from "./service.js";

export type SessionFacts = {
  directory: string | null;
  title: string | null;
  firstMessage: string | null;
};

export type BootstrapOptions = {
  curatedBudgetChars?: number;
  episodicBudgetChars?: number;
};

const DEFAULT_CURATED_BUDGET = 4_000;
const DEFAULT_EPISODIC_BUDGET = 1_500;
const MAX_BLOCK_ENTRIES = 8;

/** Longest-prefix match of a working directory against the projects map. */
export function resolveProject(
  directory: string | null,
  projects: Record<string, string>,
): string | null {
  if (!directory) return null;
  let best: { prefix: string; name: string } | null = null;
  for (const [prefix, name] of Object.entries(projects)) {
    if (directory === prefix || directory.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`))
      if (!best || prefix.length > best.prefix.length) best = { prefix, name };
  }
  return best?.name ?? null;
}

function renderEntry(entry: IndexedEntry): string {
  const visibility = visibilityForSource(entry.source);
  const label = entry.source ? `source: ${entry.source}, ${visibility}-only` : `${visibility}-only`;
  const text = entry.text.startsWith("- ") ? entry.text.slice(2) : entry.text;
  return `- ${text} (${label})`;
}

function rankEntries(entries: IndexedEntry[]): IndexedEntry[] {
  return [...entries].sort((left, right) => {
    if (right.importance !== left.importance) return right.importance - left.importance;
    return (right.observedAt ?? 0) - (left.observedAt ?? 0);
  });
}

function fitsBudget(lines: string[], budget: number): string[] {
  const result: string[] = [];
  let used = 0;
  for (const line of lines) {
    if (result.length >= MAX_BLOCK_ENTRIES) break;
    if (used + line.length > budget) break;
    result.push(line);
    used += line.length + 1;
  }
  return result;
}

/**
 * Build the session bootstrap context: curated MEMORY.md and USER.md heads,
 * plus episodic entries matched by project annotation and trigger phrases.
 * Every episodic line carries its source visibility so team-facing artifacts
 * never quote personal-only memory.
 */
export async function bootstrapContext(
  context: MemomaticContext,
  facts: SessionFacts,
  options: BootstrapOptions = {},
): Promise<string | null> {
  const curatedBudget = options.curatedBudgetChars ?? DEFAULT_CURATED_BUDGET;
  const episodicBudget = options.episodicBudgetChars ?? DEFAULT_EPISODIC_BUDGET;
  const blocks: string[] = [];
  for (const file of [context.paths.memoryFile, context.paths.userFile]) {
    const content = await readFile(file, "utf8").catch(() => undefined);
    if (content === undefined || !content.trim()) continue;
    const name = file.slice(file.lastIndexOf("/") + 1);
    blocks.push(`# Memomatic ${name}\n\n${content.trim().slice(0, curatedBudget)}`);
  }
  const entries = context.store.allEntries().filter((entry) => entry.status === null);
  const project = resolveProject(facts.directory, context.settings.projects);
  const usedTexts = new Set<string>();
  if (project) {
    const lines = rankEntries(
      entries.filter((entry) => entry.kind === "episodic" && entry.project === project),
    ).map((entry) => {
      usedTexts.add(entry.text);
      return renderEntry(entry);
    });
    const fitted = fitsBudget(lines, episodicBudget);
    if (fitted.length)
      blocks.push(
        `# Memomatic project recall (${project})\n\n${fitted.join("\n")}\n\nEntries marked personal-only must never be quoted in team-facing artifacts.`,
      );
  }
  const haystack = [facts.title ?? "", facts.firstMessage ?? ""].join("\n").toLowerCase();
  if (haystack.trim()) {
    const triggered = rankEntries(
      entries.filter(
        (entry) =>
          !usedTexts.has(entry.text) &&
          entry.trigger.some((phrase) => phrase.trim() && haystack.includes(phrase.toLowerCase())),
      ),
    ).map((entry) => renderEntry(entry));
    const fitted = fitsBudget(triggered, episodicBudget);
    if (fitted.length)
      blocks.push(
        `# Memomatic triggered recall\n\n${fitted.join("\n")}\n\nEntries marked personal-only must never be quoted in team-facing artifacts.`,
      );
  }
  if (!blocks.length) return null;
  return `${blocks.join("\n\n")}\n\nUse memory_search for details and memory_write to queue durable outcomes. Never re-save content that is already present in this memory.`;
}
