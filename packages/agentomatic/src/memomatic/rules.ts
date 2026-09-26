import { readFile } from "node:fs/promises";

export type MemoryRules = {
  neverSave: string[];
  autoClean: { olderThanDays: number; scope: "episodic" } | null;
};

const NEVER_SAVE = /^-\s*never-save:\s*(.+?)\s*$/gim;
const AUTO_CLEAN = /^-\s*auto-clean:\s*older-than=(\d+)d\s+scope=episodic\s*$/im;

export const emptyRules = (): MemoryRules => ({ neverSave: [], autoClean: null });

export function parseRules(markdown: string): MemoryRules {
  const rules = emptyRules();
  for (const match of markdown.matchAll(NEVER_SAVE)) {
    const topic = match[1].trim().toLowerCase();
    if (topic) rules.neverSave.push(topic);
  }
  const autoClean = AUTO_CLEAN.exec(markdown);
  if (autoClean) {
    const days = Number.parseInt(autoClean[1], 10);
    if (Number.isFinite(days) && days > 0)
      rules.autoClean = { olderThanDays: days, scope: "episodic" };
  }
  return rules;
}

export async function loadRules(rulesFile: string): Promise<MemoryRules> {
  try {
    return parseRules(await readFile(rulesFile, "utf8"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return emptyRules();
    throw error;
  }
}

export function isForbidden(text: string, rules: MemoryRules): boolean {
  const lowered = text.toLowerCase();
  return rules.neverSave.some((topic) => lowered.includes(topic));
}
