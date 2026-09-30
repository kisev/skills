import { appendDailyEntry, readTextIfExists, parseCorpusEntries } from "./corpus.js";
import { extractJson, type ModelExecutor } from "./executor.js";
import { opencodeDatabasePath } from "./ingest.js";
import { planIngestion, type IngestionPlan } from "./ingestion.js";
import { check, type OperationOptions } from "./operations.js";
import { writeAtomic } from "@kisev/safe-fs";
import { join } from "node:path";
import { stat } from "node:fs/promises";
import { corpusFiles, reindex } from "./search.js";
import { isForbidden } from "./rules.js";
import { entryLine, parseEntryLine } from "./entries.js";
import type { MemomaticContext } from "./service.js";

export const WATERMARK_KEY = "ingest-watermark";
export const LAST_RUN_KEY = "last-sessions-at";

export type SessionsReport = {
  sessionsIngested: number;
  candidatesExtracted: number;
  rejected: Array<{ text: string; reason: string }>;
  dryRun: boolean;
  ingestion: {
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

export type SessionsOptions = OperationOptions & { dryRun?: boolean; databaseFile?: string };

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

export async function runSessions(
  context: MemomaticContext,
  executor: ModelExecutor | null,
  options: SessionsOptions = {},
): Promise<SessionsReport> {
  if (!options.dryRun) return executeSessions(context, executor, options);
  const store = context.store.fork();
  try {
    return await executeSessions({ ...context, store }, executor, options);
  } finally {
    store.close();
  }
}

async function executeSessions(
  context: MemomaticContext,
  executor: ModelExecutor | null,
  options: SessionsOptions,
): Promise<SessionsReport> {
  const started = Date.now();
  const dryRun = options.dryRun === true;
  const report: SessionsReport = {
    sessionsIngested: 0,
    candidatesExtracted: 0,
    rejected: [],
    dryRun,
    ingestion: {
      messages: 0,
      fragments: 0,
      completed: 0,
      cached: 0,
      characters: 0,
      remaining: 0,
      cachedSessions: 0,
      unscannedSessions: 0,
    },
  };
  if (!executor) {
    options.observe?.({
      phase: "sessions.disabled",
      message: "No sessions model configured; nothing to extract",
      level: "warn",
    });
    report.elapsedMs = Date.now() - started;
    return report;
  }
  check(options);
  options.observe?.({ phase: "sessions.scan", message: "Snapshotting eligible session messages" });
  if (
    context.store.getMeta(WATERMARK_KEY) &&
    !context.store.db
      .prepare(
        "SELECT 1 FROM meta WHERE key LIKE 'ingest-v2:%' OR key LIKE 'ingest-session-v2:%' LIMIT 1",
      )
      .get()
  )
    options.observe?.({
      phase: "sessions.migration",
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
      phase: "sessions.unavailable",
      message: "No OpenCode database exists yet; nothing to extract",
      level: "warn",
    });
    report.elapsedMs = Date.now() - started;
    return report;
  }
  let plan: IngestionPlan;
  try {
    plan = planIngestion(options.databaseFile ?? opencodeDatabasePath(), context.store, {
      before: Date.now() - context.settings.sessions.idleMs,
      maxChars: context.settings.sessions.maxChars,
      maxSessions: context.settings.sessions.maxSessions,
    });
  } catch (error) {
    throw new Error(`cannot read OpenCode sessions: ${(error as Error).message}`);
  }
  report.ingestion = {
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
    phase: "sessions.plan",
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
  const rejected: Array<{ text: string; reason: string }> = [];
  const sessions = new Set<string>();
  const extracted: ExtractedCandidate[] = [];
  for (const fragment of plan.fragments) {
    check(options);
    options.observe?.({
      phase: "sessions.extract",
      message: "Extracting a new or changed fragment",
      completed: report.ingestion.completed,
      total: report.ingestion.fragments,
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
        phase: "sessions.resume",
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
      const parsed = parseEntryLine(line);
      const text = parsed?.text ?? `- ${candidate.text}`;
      if (!options.dryRun && !seen.has(text)) await appendDailyEntry(context.paths, line);
      seen.add(text);
    }
    if (!options.dryRun) {
      for (const key of fragment.checkpointKeys) context.store.setMeta(key, fragment.id);
      if (fragment.seal) context.store.setMeta(...fragment.seal);
    }
    sessions.add(fragment.sessionId);
    report.ingestion.completed++;
    report.ingestion.remaining--;
    options.observe?.({
      phase: "sessions.checkpoint",
      message: "Fragment checkpoint committed",
      completed: report.ingestion.completed,
      total: report.ingestion.fragments,
    });
  }
  if (!options.dryRun && sessions.size) {
    context.store.setMeta(WATERMARK_KEY, String(plan.watermark));
    context.store.setMeta(LAST_RUN_KEY, new Date().toISOString());
  }
  await reindex(context.paths, context.settings, context.store, options);
  report.sessionsIngested = sessions.size;
  report.candidatesExtracted = extracted.length;
  report.rejected = rejected;
  report.elapsedMs = Date.now() - started;
  options.observe?.({
    phase: "sessions.done",
    message: "Session extraction complete",
    elapsedMs: report.elapsedMs,
    ...report.ingestion,
  });
  return report;
}
