import { entryLine, parseEntryLine } from "./entries.js";
import { appendDreams, readTextIfExists, writeCorpusFile } from "./corpus.js";
import { processInbox, type InboxReport } from "./inbox.js";
import { promotionCandidates, relevanceByFts } from "./gates.js";
import { extractJson, type ModelExecutor } from "./executor.js";
import { check, type OperationOptions } from "./operations.js";
import { createHash } from "node:crypto";
import { reindex } from "./search.js";
import type { MemomaticContext } from "./service.js";
import { archiveOldEpisodic } from "./service.js";

export const LAST_RUN_KEY = "last-dream-at";

export type DreamReport = {
  inbox: InboxReport;
  promoted: string[];
  superseded: string[];
  dropped: string[];
  archived: string[];
  appendOnlyFallback: boolean;
  dryRun: boolean;
  elapsedMs?: number;
};

export type DreamOptions = OperationOptions & { dryRun?: boolean };

const CONSOLIDATE_SYSTEM = `You consolidate a long-term memory file.
Reply with exactly one JSON object of the form
{"operations":[{"op":"add","line":string},{"op":"supersede","key":string,"line":string},{"op":"drop","key":string}]}.
Merge duplicates, supersede outdated entries sharing a key instead of appending,
keep every line compact (at most two sentences), keep or assign "key" annotations
in the form <!-- key: ... -->, and add <!-- trigger: ... --> phrases only when a
clear activation context exists. Never invent keys for "supersede" or "drop" that
are not present in the current file.`;

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

export async function runDream(
  context: MemomaticContext,
  executor: ModelExecutor | null,
  options: DreamOptions = {},
): Promise<DreamReport> {
  if (!options.dryRun) return executeDream(context, executor, options);
  const store = context.store.fork();
  try {
    return await executeDream({ ...context, store }, executor, options);
  } finally {
    store.close();
  }
}

async function executeDream(
  context: MemomaticContext,
  executor: ModelExecutor | null,
  options: DreamOptions,
): Promise<DreamReport> {
  const started = Date.now();
  const dryRun = options.dryRun === true;
  const report: DreamReport = {
    inbox: {
      filesProcessed: 0,
      filesRejected: 0,
      entriesAppended: 0,
      entriesSuperseded: 0,
      entriesDuplicated: 0,
      linesForbidden: 0,
      linesInvalid: 0,
      dryRun,
    },
    promoted: [],
    superseded: [],
    dropped: [],
    archived: [],
    appendOnlyFallback: false,
    dryRun,
  };
  options.observe?.({
    phase: "dream.start",
    message: dryRun ? "Previewing Dream without persistent writes" : "Starting Dream",
  });
  report.inbox = await processInbox(context, { ...options, dryRun, deferIndex: true });
  await reindex(context.paths, context.settings, context.store, options);

  const relevance = relevanceByFts(context.store, context.settings);
  const finalCandidates = promotionCandidates(context.store, context.settings, relevance);

  if (executor && finalCandidates.length) {
    check(options);
    options.observe?.({
      phase: "consolidation",
      message: "Consolidating eligible memory",
      candidates: finalCandidates.length,
    });
    const current = (await readTextIfExists(context.paths.memoryFile)) ?? "";
    const consolidationKey = `consolidation-v1:${createHash("sha256")
      .update(
        JSON.stringify([
          current,
          finalCandidates.map((candidate) => [candidate.entry.stableId, candidate.entry.text]),
          context.settings.dream.model,
          context.settings.dream.variant,
        ]),
      )
      .digest("hex")}`;
    const cachedResponse = context.store.getMeta(consolidationKey);
    const response =
      cachedResponse ??
      (await executor.complete({
        system: CONSOLIDATE_SYSTEM,
        prompt: `Current MEMORY.md:\n${current || "(empty)"}\n\nCandidates:\n${finalCandidates
          .map(
            (candidate) =>
              `- ${candidate.entry.text} <!-- key: ${candidate.entry.key ?? candidate.entry.stableId} -->`,
          )
          .join("\n")}`,
      }));
    let operations: ConsolidationOperation[];
    let invalidResponse = false;
    try {
      operations = parseConsolidation(response);
    } catch {
      invalidResponse = true;
      operations = finalCandidates.map(({ entry }) => ({
        op: "add",
        line: entryLine(entry.text.replace(/^- /, ""), {
          key: entry.key ?? undefined,
          origin: entry.origin ?? "agent",
          source: entry.source ?? undefined,
        }),
      }));
    }
    check(options);
    const outcome = await applyConsolidation(context, operations, current, dryRun);
    if (!dryRun) context.store.setMeta(consolidationKey, response);
    if (cachedResponse)
      options.observe?.({
        phase: "consolidation.cached",
        message: "Reused unchanged consolidation input",
      });
    report.promoted = outcome.promoted;
    report.superseded = outcome.superseded;
    report.dropped = outcome.dropped;
    report.appendOnlyFallback = invalidResponse || outcome.appendOnlyFallback;
  }

  if (!dryRun) {
    report.archived = await archiveOldEpisodic(context, options);
    context.store.setMeta(LAST_RUN_KEY, new Date().toISOString());
  }
  if (report.promoted.length || report.superseded.length || report.archived.length)
    await reindex(context.paths, context.settings, context.store, options);

  const summary = [
    `- inbox files processed: ${report.inbox.filesProcessed}`,
    `- inbox entries appended: ${report.inbox.entriesAppended}`,
    `- inbox entries superseded: ${report.inbox.entriesSuperseded}`,
    `- inbox files rejected: ${report.inbox.filesRejected}`,
    `- promoted: ${report.promoted.length}${report.promoted.length ? ` (${report.promoted.join(", ")})` : ""}`,
    `- superseded: ${report.superseded.length ? report.superseded.join(", ") : "none"}`,
    `- dropped: ${report.dropped.length ? report.dropped.join(", ") : "none"}`,
    `- archived files: ${report.archived.length ? report.archived.join(", ") : "none"}`,
    `- append-only fallback: ${report.appendOnlyFallback}`,
    `- dry run: ${report.dryRun}`,
  ].join("\n");
  if (!dryRun) await appendDreams(context.paths, summary);
  report.elapsedMs = Date.now() - started;
  options.observe?.({
    phase: "dream.done",
    message: "Dream complete",
    elapsedMs: report.elapsedMs,
  });
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
  // Consolidation never grants permission to delete curated memory.
  if (drops.length) result.appendOnlyFallback = true;
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
