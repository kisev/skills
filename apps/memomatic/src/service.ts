import { entryLine } from "./entries.js";
import { archiveFile, readTextIfExists, replaceEntryLine } from "./corpus.js";
import { dropToInbox } from "./inbox.js";
import { isForbidden, loadRules, type MemoryRules } from "./rules.js";
import { memomaticPaths, type MemomaticPaths } from "./paths.js";
import { loadSettings, type MemomaticSettings } from "./settings.js";
import { reindex, search, type SearchHit } from "./search.js";
import { MemoryStore } from "./store.js";
import { stat } from "node:fs/promises";

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

export type WriteRequest = {
  text: string;
  key?: string;
  trigger?: string[];
  importance?: number;
  project?: string;
  origin?: "user" | "agent";
  target?: "episodic" | "curated" | "user";
  pinned?: boolean;
  source?: string;
};

export type MemomaticContext = {
  paths: MemomaticPaths;
  settings: MemomaticSettings;
  rules: MemoryRules;
  store: MemoryStore;
};

export async function openMemomatic(): Promise<MemomaticContext> {
  const paths = memomaticPaths();
  const [settings, rules, store] = await Promise.all([
    loadSettings(paths.settingsFile),
    loadRules(paths.rulesFile),
    MemoryStore.open(paths.indexFile),
  ]);
  return { paths, settings, rules, store };
}

export async function writeEntry(
  context: MemomaticContext,
  request: WriteRequest,
): Promise<string> {
  const text = request.text.trim();
  if (!text) throw new Error("memory text is empty");
  if (isForbidden(text, context.rules))
    throw new Error("memory text matches a never-save rule in MEMORY_RULES.md");
  const origin = request.origin ?? "agent";
  const line = entryLine(text, {
    key: request.key,
    status: origin === "user" && request.target === "user" ? "active" : undefined,
    origin,
    observed: new Date().toISOString().slice(0, 10),
    project: request.project,
    importance: request.importance,
    trigger: request.trigger,
    pinned: request.pinned,
    source: request.source ?? origin,
    target: request.target,
  });
  return dropToInbox(context.paths, [line], request.source ?? origin);
}

export async function searchMemory(context: MemomaticContext, query: string): Promise<SearchHit[]> {
  return search(context.store, query, context.settings);
}

export async function getEntry(
  context: MemomaticContext,
  file: string,
  line?: number,
): Promise<{ file: string; line: number; content: string }> {
  const target = file.startsWith("/")
    ? file
    : `${context.paths.stateRoot}/${file.replace(/^\/+/, "")}`;
  if (!target.startsWith(context.paths.stateRoot))
    throw new Error("path escapes memomatic state root");
  const content = await readTextIfExists(target);
  if (content === undefined) throw new Error(`memory file not found: ${file}`);
  if (line === undefined) return { file: target, line: 0, content };
  const lines = content.split("\n");
  if (line < 1 || line > lines.length) throw new Error("line is out of range");
  context.store.markUseful(
    context.store
      .allEntries()
      .filter((entry) => entry.file === target && entry.line === line)
      .map((entry) => entry.stableId),
  );
  return { file: target, line, content: lines[line - 1] };
}

export async function forgetEntry(
  context: MemomaticContext,
  target: {
    file: string;
    line: number;
  },
): Promise<string> {
  const file = target.file.startsWith("/")
    ? target.file
    : `${context.paths.stateRoot}/${target.file.replace(/^\/+/, "")}`;
  if (!file.startsWith(context.paths.stateRoot))
    throw new Error("path escapes memomatic state root");
  const content = await readTextIfExists(file);
  if (content === undefined) throw new Error(`memory file not found: ${target.file}`);
  const lines = content.split("\n");
  if (target.line < 1 || target.line > lines.length) throw new Error("line is out of range");
  await replaceEntryLine(context.paths, file, target.line, null);
  return file;
}

export async function archiveOldEpisodic(context: MemomaticContext): Promise<string[]> {
  const archived: string[] = [];
  if (!context.rules.autoClean) return archived;
  const rule = context.rules.autoClean;
  const cutoff = Date.now() - rule.olderThanDays * 86_400_000;
  for (const entry of context.store.allEntries()) {
    if (entry.kind !== "episodic" || !entry.observedAt || entry.observedAt >= cutoff) continue;
    if (rule.source && entry.source !== rule.source) continue;
    if (entry.pinned) continue;
    if (!(await exists(entry.file))) continue;
    const alreadyDone = archived.includes(entry.file);
    if (!alreadyDone) {
      await archiveFile(context.paths, entry.file);
      archived.push(entry.file);
    }
  }
  return archived;
}

export async function rebuildIndex(context: MemomaticContext): Promise<number> {
  return reindex(context.paths, context.settings, context.store);
}
