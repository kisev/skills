import { entryLine, parseEntryLine } from "./entries.js";
import { appendDailyEntry, appendDreams, readTextIfExists, writeCorpusFile } from "./corpus.js";
import { promotionCandidates } from "./gates.js";
import { extractJson, type ModelExecutor } from "./executor.js";
import { loadRecentSessions, opencodeDatabasePath } from "./ingest.js";
import { isForbidden } from "./rules.js";
import { reindex } from "./search.js";
import type { MemomaticContext } from "./service.js";
import { archiveOldEpisodic } from "./service.js";

export type DreamReport = {
  sessionsIngested: number;
  candidatesExtracted: number;
  promoted: string[];
  superseded: string[];
  dropped: string[];
  rejected: Array<{ text: string; reason: string }>;
  archived: string[];
  appendOnlyFallback: boolean;
  dryRun: boolean;
};

const WATERMARK_KEY = "ingest-watermark";

const EXTRACT_SYSTEM = `You distill durable engineering memory from a coding session.
Reply with exactly one JSON object of the form
{"candidates":[{"text":string,"key":string|null,"reason":string}]}.
Include only standing decisions with rationale, discoveries, failed attempts with
the reason they were rejected, session outcomes, and action-sensitive boundaries
(approval requirements, temporary constraints, handoffs, expiry conditions).
Each "text" is imperative, self-contained, at most two sentences, without secrets,
credentials, or machine-local paths. "key" is a stable kebab-case identifier when
the item clearly has a durable identity, otherwise null. Return {"candidates":[]}
when nothing qualifies.`;

const CONSOLIDATE_SYSTEM = `You consolidate a long-term memory file.
Reply with exactly one JSON object of the form
{"operations":[{"op":"add","line":string},{"op":"supersede","key":string,"line":string},{"op":"drop","key":string}]}.
Merge duplicates, supersede outdated entries sharing a key instead of appending,
keep every line compact (at most two sentences), keep or assign "key" annotations
in the form <!-- key: ... -->, and add <!-- trigger: ... --> phrases only when a
clear activation context exists. Never invent keys for "supersede" or "drop" that
are not present in the current file.`;

export type ExtractedCandidate = { text: string; key: string | null; reason: string };

export function parseExtraction(response: string): ExtractedCandidate[] {
  const parsed = extractJson(response) as { candidates?: unknown };
  if (!Array.isArray(parsed.candidates)) throw new Error("extraction response has no candidates");
  const result: ExtractedCandidate[] = [];
  for (const raw of parsed.candidates) {
    const value = raw as { text?: unknown; key?: unknown; reason?: unknown };
    if (typeof value.text !== "string" || !value.text.trim()) continue;
    result.push({
      text: value.text.trim(),
      key:
        typeof value.key === "string" && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value.key)
          ? value.key
          : null,
      reason: typeof value.reason === "string" ? value.reason : "",
    });
  }
  return result.slice(0, 24);
}

export type ConsolidationOperation =
  | { op: "add"; line: string }
  | { op: "supersede"; key: string; line: string }
  | { op: "drop"; key: string };

export function parseConsolidation(response: string): ConsolidationOperation[] {
  const parsed = extractJson(response) as { operations?: unknown };
  if (!Array.isArray(parsed.operations))
    throw new Error("consolidation response has no operations");
  const result: ConsolidationOperation[] = [];
  for (const raw of parsed.operations) {
    const value = raw as Record<string, unknown>;
    if (value.op === "add" && typeof value.line === "string") {
      const line = value.line.trim();
      if (parseEntryLine(line)) result.push({ op: "add", line });
    } else if (
      value.op === "supersede" &&
      typeof value.key === "string" &&
      typeof value.line === "string"
    ) {
      const line = value.line.trim();
      if (parseEntryLine(line)) result.push({ op: "supersede", key: value.key, line });
    } else if (value.op === "drop" && typeof value.key === "string") {
      result.push({ op: "drop", key: value.key });
    }
  }
  return result.slice(0, 32);
}

async function ingestSessions(
  context: MemomaticContext,
  executor: ModelExecutor | null,
): Promise<{
  sessions: number;
  extracted: ExtractedCandidate[];
  watermark: number | null;
  rejected: Array<{ text: string; reason: string }>;
}> {
  const watermark = Number.parseInt(context.store.getMeta(WATERMARK_KEY) ?? "0", 10) || 0;
  const sessions = loadRecentSessions(opencodeDatabasePath(), watermark, {
    before: Date.now() - 10 * 60_000,
    maxSessions: 20,
    maxCharsPerSession: 24_000,
  });
  const extracted: ExtractedCandidate[] = [];
  const rejected: Array<{ text: string; reason: string }> = [];
  let latest = watermark;
  for (const session of sessions) {
    latest = Math.max(latest, session.timeCreated);
    if (!executor) continue;
    const transcript = session.messages
      .map((message) => `${message.role}: ${message.text}`)
      .join("\n\n")
      .slice(0, 24_000);
    const response = await executor.complete({
      system: EXTRACT_SYSTEM,
      prompt: `Session title: ${session.title}\nWorking directory: ${session.directory}\n\n${transcript}`,
    });
    for (const candidate of parseExtraction(response)) {
      if (isForbidden(candidate.text, context.rules)) {
        rejected.push({ text: candidate.text, reason: "never-save rule" });
        continue;
      }
      extracted.push(candidate);
    }
  }
  return {
    sessions: sessions.length,
    extracted,
    watermark: sessions.length ? latest : null,
    rejected,
  };
}

export async function runDream(
  context: MemomaticContext,
  executor: ModelExecutor | null,
  options: { dryRun?: boolean } = {},
): Promise<DreamReport> {
  const dryRun = options.dryRun === true;
  const report: DreamReport = {
    sessionsIngested: 0,
    candidatesExtracted: 0,
    promoted: [],
    superseded: [],
    dropped: [],
    rejected: [],
    archived: [],
    appendOnlyFallback: false,
    dryRun,
  };
  await reindex(context.paths, context.settings, context.store);

  const ingestion = await ingestSessions(context, executor);
  report.sessionsIngested = ingestion.sessions;
  report.candidatesExtracted = ingestion.extracted.length;
  report.rejected = ingestion.rejected;
  if (!dryRun) {
    for (const candidate of ingestion.extracted) {
      await appendDailyEntry(
        context.paths,
        entryLine(candidate.text, {
          key: candidate.key ?? undefined,
          origin: "agent",
          observed: new Date().toISOString().slice(0, 10),
        }),
      );
    }
    if (ingestion.watermark !== null)
      context.store.setMeta(WATERMARK_KEY, String(ingestion.watermark));
  }
  await reindex(context.paths, context.settings, context.store);

  const relevance = new Map<string, number>();
  for (const entry of context.store.allEntries()) {
    if (entry.kind !== "episodic") continue;
    const usage = context.store.usageFor(entry.stableId);
    if (usage.useful < context.settings.dream.minUseful) continue;
    const match = context.store.ftsSearch(entry.text, 10).get(entry.stableId);
    if (match) relevance.set(entry.stableId, match);
  }
  const finalCandidates = promotionCandidates(context.store, context.settings, relevance);

  if (executor && finalCandidates.length) {
    const current = (await readTextIfExists(context.paths.memoryFile)) ?? "";
    const response = await executor.complete({
      system: CONSOLIDATE_SYSTEM,
      prompt: `Current MEMORY.md:\n${current || "(empty)"}\n\nCandidates:\n${finalCandidates
        .map(
          (candidate) =>
            `- ${candidate.entry.text} <!-- key: ${candidate.entry.key ?? candidate.entry.stableId} -->`,
        )
        .join("\n")}`,
    });
    const operations = parseConsolidation(response);
    const outcome = await applyConsolidation(context, operations, current, dryRun);
    report.promoted = outcome.promoted;
    report.superseded = outcome.superseded;
    report.dropped = outcome.dropped;
    report.appendOnlyFallback = outcome.appendOnlyFallback;
  }

  if (!dryRun) report.archived = await archiveOldEpisodic(context);
  await reindex(context.paths, context.settings, context.store);

  const summary = [
    `- sessions ingested: ${report.sessionsIngested}`,
    `- candidates extracted: ${report.candidatesExtracted}`,
    `- promoted: ${report.promoted.length}${report.promoted.length ? ` (${report.promoted.join(", ")})` : ""}`,
    `- superseded: ${report.superseded.length ? report.superseded.join(", ") : "none"}`,
    `- dropped: ${report.dropped.length ? report.dropped.join(", ") : "none"}`,
    `- rejected by rules: ${report.rejected.length}`,
    `- archived files: ${report.archived.length ? report.archived.join(", ") : "none"}`,
    `- append-only fallback: ${report.appendOnlyFallback}`,
    `- dry run: ${report.dryRun}`,
  ].join("\n");
  if (!dryRun) await appendDreams(context.paths, summary);
  return report;
}

async function applyConsolidation(
  context: MemomaticContext,
  operations: ConsolidationOperation[],
  currentMemory: string,
  dryRun: boolean,
): Promise<{
  promoted: string[];
  superseded: string[];
  dropped: string[];
  appendOnlyFallback: boolean;
}> {
  const result = {
    promoted: [] as string[],
    superseded: [] as string[],
    dropped: [] as string[],
    appendOnlyFallback: false,
  };
  if (!operations.length) return result;
  const lines = currentMemory.split("\n").filter((line) => line.trim().length > 0);
  const existingKeys = new Set(
    lines
      .map((line) => parseEntryLine(line)?.annotations.key)
      .filter((key): key is string => Boolean(key)),
  );
  const removals = operations.filter((operation) => operation.op !== "add");
  const lossRatio = lines.length ? removals.length / lines.length : 0;
  const adds = operations.filter(
    (operation): operation is { op: "add"; line: string } => operation.op === "add",
  );
  const supersessions = operations.filter(
    (operation): operation is { op: "supersede"; key: string; line: string } =>
      operation.op === "supersede" && existingKeys.has(operation.key),
  );
  const drops = operations.filter(
    (operation): operation is { op: "drop"; key: string } =>
      operation.op === "drop" && existingKeys.has(operation.key),
  );
  if (removals.length !== supersessions.length + drops.length) result.appendOnlyFallback = true;
  if (!result.appendOnlyFallback && lossRatio > context.settings.dream.maxPriorEntryLoss)
    result.appendOnlyFallback = true;

  if (result.appendOnlyFallback) {
    const budget = context.settings.dream.memoryBudgetLines;
    if (lines.length + adds.length > budget) return result;
    const next = `${lines.join("\n")}\n${adds.map((operation) => operation.line).join("\n")}\n`;
    if (!dryRun) await writeCorpusFile(context.paths, context.paths.memoryFile, next);
    result.promoted = adds.map((operation) => operation.line);
    return result;
  }

  const nextLines = [...lines];
  for (const operation of supersessions) {
    const index = nextLines.findIndex(
      (line) => parseEntryLine(line)?.annotations.key === operation.key,
    );
    if (index === -1) continue;
    nextLines[index] = operation.line;
    result.superseded.push(operation.key);
  }
  for (const operation of drops) {
    const index = nextLines.findIndex(
      (line) => parseEntryLine(line)?.annotations.key === operation.key,
    );
    if (index === -1) continue;
    nextLines.splice(index, 1);
    result.dropped.push(operation.key);
  }
  for (const operation of adds) {
    const key = parseEntryLine(operation.line)?.annotations.key;
    if (key && nextLines.some((line) => parseEntryLine(line)?.annotations.key === key)) continue;
    nextLines.push(operation.line);
    result.promoted.push(operation.line);
  }
  if (nextLines.length > context.settings.dream.memoryBudgetLines) {
    result.appendOnlyFallback = true;
    result.promoted = [];
    result.superseded = [];
    result.dropped = [];
    return result;
  }
  const next = `${nextLines.join("\n")}\n`;
  if (!dryRun) await writeCorpusFile(context.paths, context.paths.memoryFile, next);
  return result;
}
