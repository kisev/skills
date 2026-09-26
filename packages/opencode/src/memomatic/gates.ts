import type { MemomaticSettings } from "./settings.js";
import type { IndexedEntry, MemoryStore } from "./store.js";

export type PromotionCandidate = {
  entry: IndexedEntry;
  score: number;
  signals: {
    relevance: number;
    frequency: number;
    diversity: number;
    recency: number;
    consolidation: number;
    richness: number;
  };
  eligible: boolean;
  reason: string | null;
};

export function scoreCandidate(
  entry: IndexedEntry,
  usage: { useful: number; queries: string[]; days: string[] },
  settings: MemomaticSettings,
  relevance: number,
  now = Date.now(),
): PromotionCandidate {
  const signals = {
    relevance: Math.max(0, Math.min(1, relevance)),
    frequency: Math.min(1, usage.useful / 10),
    diversity: Math.min(1, usage.queries.length / 5),
    recency: entry.observedAt
      ? Math.pow(
          0.5,
          Math.max(0, now - entry.observedAt) / 86_400_000 / settings.search.halfLifeDays,
        )
      : 0.5,
    consolidation: Math.min(1, usage.useful / Math.max(1, settings.dream.minUseful)),
    richness: Math.min(1, entry.text.length / 400),
  };
  const score =
    0.3 * signals.relevance +
    0.24 * signals.frequency +
    0.15 * signals.diversity +
    0.15 * signals.recency +
    0.1 * signals.consolidation +
    0.06 * signals.richness;
  let eligible = true;
  let reason: string | null = null;
  if (entry.kind !== "episodic") {
    eligible = false;
    reason = "not episodic";
  } else if (entry.origin === null) {
    eligible = false;
    reason = "unknown origin";
  } else if (usage.useful < settings.dream.minUseful) {
    eligible = false;
    reason = `useful ${usage.useful} < ${settings.dream.minUseful}`;
  } else if (usage.queries.length < settings.dream.minUniqueQueries) {
    eligible = false;
    reason = `queries ${usage.queries.length} < ${settings.dream.minUniqueQueries}`;
  } else if (score < settings.dream.minScore) {
    eligible = false;
    reason = `score ${score.toFixed(3)} < ${settings.dream.minScore}`;
  }
  return { entry, score, signals, eligible, reason };
}

export function promotionCandidates(
  store: MemoryStore,
  settings: MemomaticSettings,
  relevanceByStableId: Map<string, number>,
  now = Date.now(),
): PromotionCandidate[] {
  const candidates: PromotionCandidate[] = [];
  for (const entry of store.allEntries()) {
    const usage = store.usageFor(entry.stableId);
    candidates.push(
      scoreCandidate(entry, usage, settings, relevanceByStableId.get(entry.stableId) ?? 0, now),
    );
  }
  return candidates
    .filter((candidate) => candidate.eligible)
    .sort((left, right) => right.score - left.score)
    .slice(0, settings.dream.maxCandidates);
}
