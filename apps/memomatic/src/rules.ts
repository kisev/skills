import { readFile } from "node:fs/promises";

export type MemoryRules = {
  neverSave: string[];
  autoClean: {
    olderThanDays: number;
    scope: "episodic";
    source?: string;
    unusedAfterDays?: number;
  } | null;
};

const NEVER_SAVE = /^-\s*never-save:\s*(.+?)\s*$/gim;
const AUTO_CLEAN =
  /^-\s*auto-clean:\s*older-than=(\d+)d\s+scope=episodic(?:\s+source=([a-z0-9-]+))?(?:\s+unused-after=(\d+)d)?\s*$/im;

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
    const unused = autoClean[3] ? Number.parseInt(autoClean[3], 10) : NaN;
    if (Number.isFinite(days) && days > 0)
      rules.autoClean = {
        olderThanDays: days,
        scope: "episodic",
        source: autoClean[2],
        ...(Number.isFinite(unused) && unused > 0 ? { unusedAfterDays: unused } : {}),
      };
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
