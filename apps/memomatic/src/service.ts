import { entryLine, parseEntryLine } from "./entries.js";
import { readTextIfExists, replaceEntryLine, writeCorpusFile } from "./corpus.js";
import { assertSafePath } from "@kisev/safe-fs";
import { basename, isAbsolute, join, relative, resolve, sep } from "node:path";
import { rm } from "node:fs/promises";
import { dropToInbox } from "./inbox.js";
import { isForbidden, loadRules, type MemoryRules } from "./rules.js";
import { memomaticPaths, type MemomaticPaths } from "./paths.js";
import { loadSettings, type MemomaticSettings } from "./settings.js";
import { reindex, search, type SearchHit } from "./search.js";
import { MemoryStore } from "./store.js";
import { visibilityForSource } from "./visibility.js";

async function memoryPath(context: MemomaticContext, file: string): Promise<string> {
  const target = resolve(context.paths.stateRoot, file);
  const part = relative(context.paths.stateRoot, target);
  if (!part || part === ".." || part.startsWith(`..${sep}`) || isAbsolute(part))
    throw new Error("path escapes memomatic state root");
  await assertSafePath(target, { target: "file" });
  return target;
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

export async function openMemomatic(
  options: { readOnly?: boolean } = {},
): Promise<MemomaticContext> {
  const paths = memomaticPaths();
  const [settings, rules, store] = await Promise.all([
    loadSettings(paths.settingsFile),
    loadRules(paths.rulesFile),
    options.readOnly ? MemoryStore.preview(paths.indexFile) : MemoryStore.open(paths.indexFile),
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

export async function searchMemoryResults(context: MemomaticContext, query: string) {
  return (await searchMemory(context, query)).map((hit) => ({
    file: hit.entry.file.replace(`${context.paths.stateRoot}/`, ""),
    kind: hit.entry.kind,
    line: hit.entry.line,
    score: Number(hit.score.toFixed(4)),
    snippet: hit.snippet,
    source: hit.entry.source,
    visibility: visibilityForSource(hit.entry.source),
  }));
}

export async function getEntry(
  context: MemomaticContext,
  file: string,
  line?: number,
): Promise<{ file: string; line: number; content: string }> {
  const target = await memoryPath(context, file);
  const content = await readTextIfExists(target);
  if (content === undefined) throw new Error(`memory file not found: ${file}`);
  if (line === undefined) return { file: target, line: 0, content };
  const lines = content.split("\n");
  if (!Number.isSafeInteger(line) || line < 1 || line > lines.length)
    throw new Error("line is out of range");
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
  const file = await memoryPath(context, target.file);
  const content = await readTextIfExists(file);
  if (content === undefined) throw new Error(`memory file not found: ${target.file}`);
  const lines = content.split("\n");
  if (!Number.isSafeInteger(target.line) || target.line < 1 || target.line > lines.length)
    throw new Error("line is out of range");
  await replaceEntryLine(context.paths, file, target.line, null);
  return file;
}

export async function archiveOldEpisodic(context: MemomaticContext): Promise<string[]> {
  const archived: string[] = [];
  if (!context.rules.autoClean) return archived;
  const rule = context.rules.autoClean;
  const cutoff = Date.now() - rule.olderThanDays * 86_400_000;
  const files = new Set(
    context.store
      .allEntries()
      .filter((entry) => entry.kind === "episodic")
      .map((entry) => entry.file),
  );
  for (const file of files) {
    await memoryPath(context, file);
    const content = await readTextIfExists(file);
    if (content === undefined) continue;
    const selected: string[] = [];
    const remaining = content.split("\n").filter((line) => {
      const entry = parseEntryLine(line)?.annotations;
      const observed = entry?.observed ? Date.parse(entry.observed) : NaN;
      if (
        !entry ||
        !Number.isFinite(observed) ||
        observed >= cutoff ||
        entry.pinned ||
        (rule.source && entry.source !== rule.source)
      )
        return true;
      selected.push(line);
      return false;
    });
    if (!selected.length) continue;
    const target = join(context.paths.archiveDir, basename(file));
    const prior = (await readTextIfExists(target)) ?? "";
    const seen = new Set(prior.split("\n"));
    await writeCorpusFile(
      context.paths,
      target,
      `${[prior.trimEnd(), ...selected.filter((line) => !seen.has(line))].filter(Boolean).join("\n")}\n`,
    );
    await writeCorpusFile(context.paths, file, remaining.join("\n"));
    if (!remaining.some((line) => line.trim())) await rm(file);
    archived.push(file);
  }
  return archived;
}

export async function rebuildIndex(context: MemomaticContext): Promise<number> {
  return reindex(context.paths, context.settings, context.store);
}
