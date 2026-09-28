import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

export type MemomaticSettings = {
  embedding: { url: string; model: string; queryInstruction?: string } | null;
  dream: {
    model: string | null;
    variant: string | null;
    minScore: number;
    minUseful: number;
    minUniqueQueries: number;
    maxCandidates: number;
    memoryBudgetLines: number;
    maxPriorEntryLoss: number;
  };
  search: { maxResults: number; minScore: number; minSemanticScore: number; halfLifeDays: number };
  archive: { enabled: boolean; days: number };
};

export const defaultSettings = (): MemomaticSettings => ({
  embedding: null,
  dream: {
    model: null,
    variant: null,
    minScore: 0.45,
    minUseful: 2,
    minUniqueQueries: 2,
    maxCandidates: 12,
    memoryBudgetLines: 80,
    maxPriorEntryLoss: 0.25,
  },
  search: { maxResults: 6, minScore: 0.35, minSemanticScore: 0.45, halfLifeDays: 30 },
  archive: { enabled: false, days: 60 },
});

function mergeSection<T extends Record<string, unknown>>(
  base: T,
  override: Record<string, unknown> | undefined,
): T {
  if (!override || typeof override !== "object") return base;
  const merged: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(override)) {
    if (key in base && value !== null && value !== undefined) merged[key] = value;
  }
  return merged as T;
}

export function normalizeSettings(raw: unknown): MemomaticSettings {
  const defaults = defaultSettings();
  const source = (raw ?? {}) as Record<string, unknown>;
  const embedding = source.embedding as Record<string, unknown> | null | undefined;
  const search = mergeSection(
    defaults.search,
    source.search as Record<string, unknown> | undefined,
  );
  if (
    !Number.isInteger(search.maxResults) ||
    search.maxResults < 1 ||
    search.maxResults > 200 ||
    !Number.isFinite(search.halfLifeDays) ||
    search.halfLifeDays <= 0 ||
    ![search.minScore, search.minSemanticScore].every(
      (value) => Number.isFinite(value) && value >= 0 && value <= 1,
    )
  )
    throw new Error("invalid search settings");
  return {
    embedding:
      embedding && typeof embedding.url === "string" && typeof embedding.model === "string"
        ? {
            url: embedding.url,
            model: embedding.model,
            ...(typeof embedding.queryInstruction === "string"
              ? { queryInstruction: embedding.queryInstruction }
              : {}),
          }
        : null,
    dream: mergeSection(defaults.dream, source.dream as Record<string, unknown> | undefined),
    search,
    archive: mergeSection(defaults.archive, source.archive as Record<string, unknown> | undefined),
  };
}

export async function loadSettings(settingsFile: string): Promise<MemomaticSettings> {
  try {
    return normalizeSettings(JSON.parse(await readFile(settingsFile, "utf8")));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return defaultSettings();
    throw error;
  }
}

export async function embedTexts(
  settings: MemomaticSettings,
  texts: string[],
  purpose: "document" | "query" = "document",
): Promise<Float32Array[] | null> {
  if (!settings.embedding || !texts.length) return null;
  const response = await fetch(settings.embedding.url, {
    body: JSON.stringify({
      input: texts.map((text) => (purpose === "query" ? embeddingQuery(settings, text) : text)),
      model: settings.embedding.model,
    }),
    headers: { "content-type": "application/json" },
    method: "POST",
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok)
    throw new Error(`embedding request failed: ${response.status} ${await response.text()}`);
  const payload = (await response.json()) as {
    data?: Array<{ embedding?: number[]; index?: number }>;
  };
  const list = payload.data ?? [];
  if (list.length !== texts.length) throw new Error("embedding response is incomplete");
  const byIndex = new Map<number, number[]>();
  for (const item of list) {
    if (
      !Array.isArray(item.embedding) ||
      !item.embedding.length ||
      !item.embedding.every((value) => typeof value === "number" && Number.isFinite(value)) ||
      !item.embedding.some((value) => value !== 0)
    )
      throw new Error("embedding response is malformed");
    const index = item.index ?? byIndex.size;
    if (!Number.isInteger(index) || index < 0 || index >= texts.length || byIndex.has(index))
      throw new Error("embedding response has invalid indices");
    byIndex.set(index, item.embedding);
  }
  const vectors = texts.map((_, index) => Float32Array.from(byIndex.get(index)!));
  if (
    !vectors.every((vector) => vector.length === vectors[0].length && vector.every(Number.isFinite))
  )
    throw new Error("embedding response has incompatible vectors");
  return vectors;
}

export const MEMORY_QUERY_INSTRUCTION =
  "Given a search query, retrieve relevant personal memory entries that answer the query.";

export function embeddingQuery(settings: MemomaticSettings, query: string): string {
  const embedding = settings.embedding;
  const instruction =
    embedding?.queryInstruction ??
    (/qwen3[-_]?embedding/i.test(embedding?.model ?? "") ? MEMORY_QUERY_INSTRUCTION : "");
  return instruction ? `Instruct: ${instruction}\nQuery:${query}` : query;
}

export function embeddingFingerprint(settings: MemomaticSettings): string {
  return createHash("sha256")
    .update(
      JSON.stringify(
        settings.embedding
          ? {
              url: settings.embedding.url,
              model: settings.embedding.model,
              documentFormat: "raw-v1",
            }
          : null,
      ),
    )
    .digest("hex");
}
