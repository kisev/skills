import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

import { cosineSimilarity, type IndexedEntry, MemoryStore, stableIdFor } from "./store.js";
import { entryKind, parseCorpusEntries } from "./corpus.js";
import { entryImportance, entryObservedAt } from "./entries.js";
import { embedTexts } from "./settings.js";
import type { MemomaticPaths } from "./paths.js";
import type { MemomaticSettings } from "./settings.js";

export type SearchHit = {
  entry: IndexedEntry;
  score: number;
  snippet: string;
};

async function corpusFiles(paths: MemomaticPaths): Promise<string[]> {
  const files: string[] = [];
  for (const name of ["MEMORY.md", "USER.md"]) {
    const file = join(paths.stateRoot, name);
    if (
      await readFile(file, "utf8").then(
        () => true,
        () => false,
      )
    )
      files.push(file);
  }
  for (const name of (await readdir(paths.dailyDir).catch(() => [])).sort()) {
    if (name.endsWith(".md")) files.push(join(paths.dailyDir, name));
  }
  return files;
}

export async function reindex(
  paths: MemomaticPaths,
  settings: MemomaticSettings,
  store: MemoryStore,
): Promise<number> {
  const entries: IndexedEntry[] = [];
  for (const file of await corpusFiles(paths)) {
    const markdown = await readFile(file, "utf8");
    for (const entry of parseCorpusEntries(markdown, file)) {
      if (entry.annotations.status === "superseded") continue;
      entries.push({
        stableId: stableIdFor(file, entry.text, entry.annotations.key ?? null),
        file: entry.file,
        line: entry.line,
        kind: entryKind(file),
        key: entry.annotations.key ?? null,
        text: entry.text,
        trigger: entry.annotations.trigger ?? [],
        importance: entryImportance(entry),
        pinned: entry.annotations.pinned === true,
        project: entry.annotations.project ?? null,
        origin: entry.annotations.origin ?? null,
        observedAt: Number.isNaN(entryObservedAt(entry)) ? null : entryObservedAt(entry),
        status: entry.annotations.status === "active" ? "active" : null,
      });
    }
  }
  store.replaceEntries(entries);
  const vectors = await embedTexts(
    settings,
    entries.map((entry) => entry.text),
  ).catch(() => null);
  if (vectors)
    for (let index = 0; index < entries.length; index += 1) {
      if (vectors[index].length) store.setVector(entries[index].stableId, vectors[index]);
    }
  return entries.length;
}

function recencyMultiplier(entry: IndexedEntry, halfLifeDays: number, now = Date.now()): number {
  if (entry.kind !== "episodic" || entry.pinned) return 1;
  if (!entry.observedAt) return 0.5;
  const ageDays = Math.max(0, (now - entry.observedAt) / 86_400_000);
  return Math.pow(0.5, ageDays / halfLifeDays);
}

function importanceMultiplier(entry: IndexedEntry): number {
  return 1 + (entry.importance - 5) * 0.06;
}

export async function search(
  store: MemoryStore,
  query: string,
  settings: MemomaticSettings,
  options: { includeArchived?: boolean; markSurfaced?: boolean } = {},
): Promise<SearchHit[]> {
  const keyword = store.ftsSearch(query, 200);
  const vector = new Map<string, number>();
  const queryVector = (await embedTexts(settings, [query]).catch(() => null))?.[0];
  if (queryVector?.length) {
    for (const row of store.vectors()) {
      const similarity = cosineSimilarity(queryVector, row.data);
      if (similarity > 0.05) vector.set(row.stableId, similarity);
    }
  }
  const candidates = new Set([...keyword.keys(), ...vector.keys()]);
  const entries = store.allEntries().filter((item) => item.status === null);
  const byId = new Map(entries.map((entry) => [entry.stableId, entry]));
  const hits: SearchHit[] = [];
  for (const stableId of candidates) {
    const entry = byId.get(stableId);
    if (!entry) continue;
    const keywordScore = keyword.get(stableId) ?? 0;
    const vectorScore = vector.get(stableId) ?? 0;
    const hybrid = vectorScore
      ? keywordScore
        ? 0.65 * vectorScore + 0.35 * keywordScore
        : vectorScore
      : keywordScore;
    if (hybrid <= 0) continue;
    const score =
      hybrid * recencyMultiplier(entry, settings.search.halfLifeDays) * importanceMultiplier(entry);
    if (score < settings.search.minScore) continue;
    hits.push({ entry, score, snippet: entry.text.slice(0, 240) });
  }
  hits.sort((left, right) => right.score - left.score);
  const limited = hits.slice(0, settings.search.maxResults);
  if (options.markSurfaced !== false && limited.length)
    store.markSurfaced(
      limited.map((hit) => hit.entry.stableId),
      query,
    );
  return limited;
}
