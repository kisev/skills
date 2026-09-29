import { entryLine, parseEntryLine } from "./entries.js";
import { appendDailyEntry, appendDreams, readTextIfExists, writeCorpusFile } from "./corpus.js";
import { processInbox, type InboxReport } from "./inbox.js";
import { promotionCandidates } from "./gates.js";
import { extractJson, type ModelExecutor } from "./executor.js";
import { opencodeDatabasePath } from "./ingest.js";
import { planIngestion, type IngestionPlan } from "./ingestion.js";
import { check, type OperationOptions } from "./operations.js";
import { writeAtomic } from "@kisev/safe-fs";
import { join } from "node:path";
import { stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { corpusFiles } from "./search.js";
import { parseCorpusEntries } from "./corpus.js";
import { isForbidden } from "./rules.js";
import { reindex } from "./search.js";
import type { MemomaticContext } from "./service.js";
import { archiveOldEpisodic } from "./service.js";

export type DreamReport = {
  inbox: InboxReport;
  sessionsIngested: number;
  candidatesExtracted: number;
  promoted: string[];
  superseded: string[];
  dropped: string[];
  rejected: Array<{ text: string; reason: string }>;
  archived: string[];
  appendOnlyFallback: boolean;
  dryRun: boolean;
  ingestion?: {
    messages: number;
    fragments: number;
    completed: number;
    cached: number;
    characters: number;
    remaining: number;
    cachedSessions: number;
    unscannedSessions: number;
  };
  elapsedMs?: number;
};

const WATERMARK_KEY = "ingest-watermark";
export type DreamOptions = OperationOptions & { dryRun?: boolean; databaseFile?: string };

const EXTRACT_SYSTEM = `You distill durable engineering memory from a coding session.
Reply with exactly one JSON object of the form
{"candidates":[{"text":string,"key":string|null,"reason":string}]}.
Include only standing decisions with rationale, discoveries, failed attempts with
the reason they were rejected, session outcomes, and action-sensitive boundaries
(approval requirements, temporary constraints, handoffs, expiry conditions).
Do not mistake proposals, plans or instructions quoted in a transcript for accepted
decisions. Preserve conditions, uncertainty and later corrections. If a reference
cannot be resolved from the supplied context, do not invent its meaning.
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
  options: DreamOptions,
): Promise<{
  sessions: number;
  extracted: ExtractedCandidate[];
  watermark: number | null;
  rejected: Array<{ text: string; reason: string }>;
  progress?: DreamReport["ingestion"];
}> {
  if (!executor) {
    options.observe?.({
      phase: "ingestion.disabled",
      message: "No Dream model configured; processing explicit memory only",
      level: "warn",
    });
    return { sessions: 0, extracted: [], watermark: null, rejected: [] };
  }
  check(options);
  options.observe?.({ phase: "ingestion.scan", message: "Snapshotting eligible session messages" });
  if (
    context.store.getMeta(WATERMARK_KEY) &&
    !context.store.db
      .prepare(
        "SELECT 1 FROM meta WHERE key LIKE 'ingest-v2:%' OR key LIKE 'ingest-session-v2:%' LIMIT 1",
      )
      .get()
  )
    options.observe?.({
      phase: "ingestion.migration",
      message:
        "Legacy cursor has no message revisions: checking existing history once; completed fragments will be cached",
      level: "warn",
    });
  const databaseFile = options.databaseFile ?? opencodeDatabasePath();
  if (
    !options.databaseFile &&
    !(await stat(databaseFile).catch((error) => {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw error;
    }))
  ) {
    options.observe?.({
      phase: "ingestion.unavailable",
      message: "No OpenCode database exists yet; skipping session extraction",
      level: "warn",
    });
    return { sessions: 0, extracted: [], watermark: null, rejected: [] };
  }
  let plan: IngestionPlan;
  try {
    plan = planIngestion(options.databaseFile ?? opencodeDatabasePath(), context.store, {
      before: Date.now() - context.settings.dream.idleMs,
      maxChars: context.settings.dream.maxChars,
      maxSessions: context.settings.dream.maxSessions,
    });
  } catch (error) {
    throw new Error(`cannot read OpenCode sessions: ${(error as Error).message}`);
  }
  const progress = {
    messages: plan.messages,
    fragments: plan.fragments.length,
    completed: 0,
    cached: plan.cached,
    characters: plan.characters,
    remaining: plan.fragments.length,
    cachedSessions: plan.cachedSessions,
    unscannedSessions: plan.unscannedSessions,
  };
  if (!options.dryRun) for (const [key, value] of plan.seals) context.store.setMeta(key, value);
  options.observe?.({
    phase: "ingestion.plan",
    message: "Session snapshot ready",
    total: plan.fragments.length,
    completed: 0,
    messages: plan.messages,
    cached: plan.cached,
    characters: plan.characters,
  });
  const seen = new Set<string>();
  for (const file of await corpusFiles(context.paths))
    for (const entry of parseCorpusEntries((await readTextIfExists(file)) ?? "", file))
      seen.add(entry.text);
  const extracted: ExtractedCandidate[] = [];
  const rejected: Array<{ text: string; reason: string }> = [];
  const sessions = new Set<string>();
  for (const fragment of plan.fragments) {
    check(options);
    options.observe?.({
      phase: "ingestion.extract",
      message: "Extracting a new or changed fragment",
      completed: progress.completed,
      total: progress.fragments,
      fragment: fragment.id,
    });
    const receipt = join(context.paths.historyDir, "ingestion", `${fragment.id}.json`);
    const cached = await readTextIfExists(receipt);
    let candidates: ExtractedCandidate[];
    if (cached) {
      const value = JSON.parse(cached) as { version?: number; id?: string; candidates?: unknown };
      if (value.version !== 1 || value.id !== fragment.id)
        throw new Error("invalid ingestion checkpoint");
      candidates = parseExtraction(JSON.stringify({ candidates: value.candidates }));
      options.observe?.({
        phase: "ingestion.resume",
        message: "Reusing completed model response",
        fragment: fragment.id,
      });
    } else
      candidates = parseExtraction(
        await executor.complete({
          system: EXTRACT_SYSTEM,
          prompt: `Session: ${fragment.sessionId}\nTitle: ${fragment.title}\nWorking directory: ${fragment.directory}\nMessage IDs: ${fragment.messageIds.join(",")}\nPrevious context (do not extract again):\n${fragment.context}\n\nNew or changed fragment:\n${fragment.text}`,
        }),
      );
    if (!options.dryRun && !cached)
      await writeAtomic(
        receipt,
        Buffer.from(
          JSON.stringify({
            version: 1,
            id: fragment.id,
            sessionId: fragment.sessionId,
            messageIds: fragment.messageIds,
            candidates: candidates.filter(
              (candidate) => !isForbidden(candidate.text, context.rules),
            ),
          }),
        ),
        0o600,
      );
    check(options);
    for (const candidate of candidates) {
      if (isForbidden(candidate.text, context.rules)) {
        rejected.push({ text: candidate.text, reason: "never-save rule" });
        continue;
      }
      extracted.push(candidate);
      const line = entryLine(candidate.text, {
        key: candidate.key ?? undefined,
        origin: "agent",
        source: "opencode",
        observed: new Date().toISOString().slice(0, 10),
      });
      const parsed = parseCorpusEntries(`${line}\n`, "")[0];
      const text = parsed?.text ?? `- ${candidate.text}`;
      if (!options.dryRun && !seen.has(text)) await appendDailyEntry(context.paths, line);
      seen.add(text);
    }
    if (!options.dryRun) {
      for (const key of fragment.checkpointKeys) context.store.setMeta(key, fragment.id);
      if (fragment.seal) context.store.setMeta(...fragment.seal);
    }
    sessions.add(fragment.sessionId);
    progress.completed++;
    progress.remaining--;
    options.observe?.({
      phase: "ingestion.checkpoint",
      message: "Fragment checkpoint committed",
      completed: progress.completed,
      total: progress.fragments,
    });
  }
  return {
    sessions: sessions.size,
    extracted,
    watermark: sessions.size ? plan.watermark : null,
    rejected,
    progress,
  };
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
  options.observe?.({
    phase: "dream.start",
    message: dryRun ? "Previewing Dream without persistent writes" : "Starting Dream",
  });
  report.inbox = await processInbox(context, { ...options, dryRun, deferIndex: true });

  const ingestion = await ingestSessions(context, executor, options);
  report.ingestion = ingestion.progress;
  report.sessionsIngested = ingestion.sessions;
  report.candidatesExtracted = ingestion.extracted.length;
  report.rejected = ingestion.rejected;
  if (!dryRun) {
    if (ingestion.watermark !== null)
      context.store.setMeta(WATERMARK_KEY, String(ingestion.watermark));
  }
  await reindex(context.paths, context.settings, context.store, options);

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

  if (!dryRun) report.archived = await archiveOldEpisodic(context, options);
  if (report.promoted.length || report.superseded.length || report.archived.length)
    await reindex(context.paths, context.settings, context.store, options);

  const summary = [
    `- inbox files processed: ${report.inbox.filesProcessed}`,
    `- inbox entries appended: ${report.inbox.entriesAppended}`,
    `- inbox entries superseded: ${report.inbox.entriesSuperseded}`,
    `- inbox files rejected: ${report.inbox.filesRejected}`,
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
  report.elapsedMs = Date.now() - started;
  options.observe?.({
    phase: "dream.done",
    message: "Dream complete",
    elapsedMs: report.elapsedMs,
    ...report.ingestion,
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
