import { readFile } from "node:fs/promises";

export type MemomaticSettings = {
  embedding: { url: string; model: string } | null;
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
  search: { maxResults: number; minScore: number; halfLifeDays: number };
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
  search: { maxResults: 6, minScore: 0.35, halfLifeDays: 30 },
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
  return {
    embedding:
      embedding && typeof embedding.url === "string" && typeof embedding.model === "string"
        ? { url: embedding.url, model: embedding.model }
        : null,
    dream: mergeSection(defaults.dream, source.dream as Record<string, unknown> | undefined),
    search: mergeSection(defaults.search, source.search as Record<string, unknown> | undefined),
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
): Promise<Float32Array[] | null> {
  if (!settings.embedding || !texts.length) return null;
  const response = await fetch(settings.embedding.url, {
    body: JSON.stringify({ input: texts, model: settings.embedding.model }),
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
    if (!Array.isArray(item.embedding)) throw new Error("embedding response is malformed");
    byIndex.set(item.index ?? byIndex.size, item.embedding);
  }
  return texts.map((_, index) => Float32Array.from(byIndex.get(index) ?? []));
}
