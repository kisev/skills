import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

import { cosineSimilarity, type IndexedEntry, MemoryStore, stableIdFor } from "./store.js";
import { entryKind, parseCorpusEntries } from "./corpus.js";
import { entryImportance, entryObservedAt } from "./entries.js";
import { embedTexts, embeddingFingerprint } from "./settings.js";
import type { MemomaticPaths } from "./paths.js";
import type { MemomaticSettings } from "./settings.js";

export type SearchHit = {
  entry: IndexedEntry;
  score: number;
  snippet: string;
  explanation: {
    matchedTokens: string[];
    lexical: number;
    semantic: number | null;
    relevance: number;
    exact: boolean;
    recency: number;
    importance: number;
    reason: "lexical" | "semantic" | "both";
  };
};

export async function corpusFiles(paths: MemomaticPaths): Promise<string[]> {
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
  const indexedIds = new Set<string>();
  for (const file of await corpusFiles(paths)) {
    const markdown = await readFile(file, "utf8");
    for (const entry of parseCorpusEntries(markdown, file)) {
      if (entry.annotations.status === "superseded") continue;
      const stableId = stableIdFor(file, entry.text, entry.annotations.key ?? null);
      if (indexedIds.has(stableId)) continue;
      indexedIds.add(stableId);
      entries.push({
        stableId,
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
        source: entry.annotations.source ?? null,
      });
    }
  }
  const vectors = await embedTexts(
    settings,
    entries.map((entry) => entry.text),
  );
  store.replaceIndex(entries, vectors, embeddingFingerprint(settings));
  return entries.length;
}

function recencyMultiplier(entry: IndexedEntry, halfLifeDays: number, now = Date.now()): number {
  if (entry.kind !== "episodic" || entry.pinned) return 1;
  if (!entry.observedAt) return 0.5;
  const ageDays = Math.max(0, (now - entry.observedAt) / 86_400_000);
  return Math.pow(0.5, ageDays / halfLifeDays);
}

export type SearchOptions = { includeArchived?: boolean; markSurfaced?: boolean; project?: string };

export function queryTokens(query: string): string[] {
  return [
    ...new Set(
      query
        .normalize("NFKC")
        .toLowerCase()
        .match(/[\p{L}\p{N}]+/gu) ?? [],
    ),
  ].filter((token) => token.length >= 2);
}

export async function search(
  store: MemoryStore,
  query: string,
  settings: MemomaticSettings,
  options: SearchOptions = {},
): Promise<SearchHit[]> {
  if (!query.trim()) throw new Error("query is required");
  const tokens = queryTokens(query);
  const keyword = store.ftsSearch(query, 200);
  const vector = new Map<string, number>();
  const storedVectors = store.vectors();
  if (
    settings.embedding &&
    store.allEntries().length &&
    store.getMeta("embeddingFingerprint") !== embeddingFingerprint(settings)
  )
    throw new Error("embedding index is missing or belongs to another model; run memomatic index");
  const queryVector = (await embedTexts(settings, [query], "query"))?.[0];
  if (queryVector?.length) {
    for (const row of storedVectors) {
      if (row.data.length !== queryVector.length)
        throw new Error("embedding dimensions changed; run memomatic index");
      const similarity = cosineSimilarity(queryVector, row.data);
      if (similarity > 0.05) vector.set(row.stableId, similarity);
    }
  }
  const candidates = new Set([...keyword.keys(), ...vector.keys()]);
  const entries = store
    .allEntries()
    .filter(
      (item) =>
        options.project === undefined || item.project === options.project || item.kind === "user",
    );
  const byId = new Map(entries.map((entry) => [entry.stableId, entry]));
  const hits: SearchHit[] = [];
  for (const stableId of candidates) {
    const entry = byId.get(stableId);
    if (!entry) continue;
    const words = queryTokens(entry.text);
    const matchedTokens = tokens.filter((token) => words.some((word) => word.startsWith(token)));
    const lexical =
      keyword.has(stableId) && tokens.length ? matchedTokens.length / tokens.length : 0;
    const semantic = vector.get(stableId) ?? null;
    const lexicalAccepted = lexical >= settings.search.minScore && lexical >= 0.5;
    const semanticAccepted =
      semantic !== null &&
      semantic >= settings.search.minSemanticScore &&
      semantic >= settings.search.minScore;
    if (!lexicalAccepted && !semanticAccepted) continue;
    const relevance = Math.max(lexicalAccepted ? lexical : 0, semanticAccepted ? semantic! : 0);
    const recency = recencyMultiplier(entry, settings.search.halfLifeDays);
    const importance = Math.max(0, Math.min(1, (entry.importance - 1) / 9));
    const score = relevance * recency * (0.85 + 0.15 * importance);
    if (score < settings.search.minScore) continue;
    hits.push({
      entry,
      score,
      snippet: entry.text.slice(0, 240),
      explanation: {
        matchedTokens,
        lexical,
        semantic,
        relevance,
        recency,
        importance,
        exact: tokens.length > 0 && tokens.every((token) => words.includes(token)),
        reason: lexicalAccepted ? (semanticAccepted ? "both" : "lexical") : "semantic",
      },
    });
  }
  hits.sort(
    (left, right) =>
      Number(right.explanation.exact) - Number(left.explanation.exact) ||
      right.score - left.score ||
      (right.explanation.semantic ?? 0) - (left.explanation.semantic ?? 0) ||
      left.entry.stableId.localeCompare(right.entry.stableId),
  );
  const limited = hits.slice(0, settings.search.maxResults);
  if (options.markSurfaced !== false && limited.length)
    store.markSurfaced(
      limited.map((hit) => hit.entry.stableId),
      query,
    );
  return limited;
}
