import { mkdir, open, readdir, rename, rm, unlink } from "node:fs/promises";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { check, type OperationOptions } from "./operations.js";

import { writeAtomic } from "@kisev/safe-fs";

import { appendDailyEntry, readTextIfExists, replaceEntryLine, writeCorpusFile } from "./corpus.js";
import { entryLine, parseEntryLine, type EntryAnnotations } from "./entries.js";
import { corpusFiles, reindex } from "./search.js";
import { isForbidden } from "./rules.js";
import type { MemomaticContext } from "./service.js";
import type { MemomaticPaths } from "./paths.js";

const SOURCE_PATTERN = /^[a-z][a-z0-9-]{0,63}$/;
const LIST_PREFIX = /^- /;

/** parseEntryLine keeps the leading "- "; strip it before re-serializing. */
function entryText(parsed: { text: string }): string {
  return LIST_PREFIX.test(parsed.text) ? parsed.text.slice(2) : parsed.text;
}
const LOCK_STALE_MS = 30 * 60_000;

export type InboxReport = {
  filesProcessed: number;
  filesRejected: number;
  entriesAppended: number;
  entriesSuperseded: number;
  entriesDuplicated: number;
  linesForbidden: number;
  linesInvalid: number;
  dryRun: boolean;
};

type CorpusIndex = {
  texts: Set<string>;
  keys: Map<string, { file: string; line: number }>;
};

export function inboxFileName(source: string, now = new Date()): string {
  const stamp = now.toISOString().replace(/[-:]/g, "").slice(0, 15);
  return `${source}-${stamp}-${randomBytes(4).toString("hex")}.md`;
}

/**
 * Append one inbox drop file. Producers write Markdown entry lines that the
 * deterministic `process` pass later validates, gates, and moves into the
 * corpus. Nothing here touches corpus files.
 */
export async function dropToInbox(
  paths: MemomaticPaths,
  lines: string[],
  source: string,
): Promise<string> {
  if (!SOURCE_PATTERN.test(source)) throw new Error(`inbox source is invalid: ${source}`);
  const content = `${lines.filter((line) => line.trim()).join("\n")}\n`;
  if (!content.trim()) throw new Error("inbox drop is empty");
  const file = join(paths.inboxDir, inboxFileName(source));
  await writeAtomic(file, Buffer.from(content, "utf8"), 0o600);
  return file;
}

async function scanCorpus(paths: MemomaticPaths): Promise<CorpusIndex> {
  const index: CorpusIndex = { texts: new Set(), keys: new Map() };
  for (const file of await corpusFiles(paths)) {
    const markdown = (await readTextIfExists(file)) ?? "";
    const lines = markdown.split("\n");
    for (let position = 0; position < lines.length; position += 1) {
      const parsed = parseEntryLine(lines[position]);
      if (!parsed) continue;
      index.texts.add(parsed.text);
      if (parsed.annotations.key && parsed.annotations.status !== "superseded")
        index.keys.set(parsed.annotations.key, { file, line: position + 1 });
    }
  }
  return index;
}

async function moveRejected(paths: MemomaticPaths, name: string): Promise<void> {
  await mkdir(paths.rejectedDir, { mode: 0o700, recursive: true });
  await rename(join(paths.inboxDir, name), join(paths.rejectedDir, name));
}

async function appendLine(context: MemomaticContext, file: string, line: string): Promise<void> {
  const current = (await readTextIfExists(file)) ?? "";
  await writeCorpusFile(context.paths, file, `${current.trimEnd()}\n${line}\n`);
}

function routeFor(annotations: EntryAnnotations): "user" | "curated" | "episodic" {
  if (annotations.target === "user" && annotations.origin === "user") return "user";
  if (annotations.target === "curated" && annotations.origin === "user") return "curated";
  return "episodic";
}

/**
 * Deterministic inbox pass: validate entry lines, enforce never-save rules,
 * deduplicate exact texts, supersede entries sharing a key, route user-origin
 * targets, then rebuild the index with embeddings. No model turns.
 */
export async function processInbox(
  context: MemomaticContext,
  options: OperationOptions & { dryRun?: boolean; deferIndex?: boolean } = {},
): Promise<InboxReport> {
  const dryRun = options.dryRun === true;
  const report: InboxReport = {
    filesProcessed: 0,
    filesRejected: 0,
    entriesAppended: 0,
    entriesSuperseded: 0,
    entriesDuplicated: 0,
    linesForbidden: 0,
    linesInvalid: 0,
    dryRun,
  };
  const names = (await readdir(context.paths.inboxDir).catch(() => []))
    .filter((name) => name.endsWith(".md"))
    .sort();
  if (!names.length) return report;
  const corpus = await scanCorpus(context.paths);
  for (const name of names) {
    check(options);
    options.observe?.({
      phase: "inbox",
      message: "Processing inbox file",
      completed: report.filesProcessed + report.filesRejected,
      total: names.length,
    });
    const markdown = (await readTextIfExists(join(context.paths.inboxDir, name))) ?? "";
    const rawLines = markdown.split("\n");
    const parsedLines = rawLines.filter((line) => line.trim()).map((line) => parseEntryLine(line));
    report.linesInvalid += parsedLines.filter((parsed) => !parsed).length;
    const allowed = parsedLines.filter((parsed): parsed is NonNullable<typeof parsed> => {
      if (!parsed) return false;
      if (isForbidden(parsed.text, context.rules)) {
        report.linesForbidden += 1;
        return false;
      }
      return true;
    });
    if (!allowed.length) {
      if (!dryRun) await moveRejected(context.paths, name);
      report.filesRejected += 1;
      continue;
    }
    let accepted = false;
    for (const parsed of allowed) {
      check(options);
      if (corpus.texts.has(parsed.text)) {
        report.entriesDuplicated += 1;
        continue;
      }
      const annotations: EntryAnnotations = {
        ...parsed.annotations,
        target: undefined,
        observed: parsed.annotations.observed ?? new Date().toISOString().slice(0, 10),
      };
      const line = entryLine(entryText(parsed), annotations, { dropTarget: true });
      const route = routeFor(parsed.annotations);
      const existing =
        route === "episodic" && parsed.annotations.key
          ? corpus.keys.get(parsed.annotations.key)
          : undefined;
      if (existing) {
        if (!dryRun) await replaceEntryLine(context.paths, existing.file, existing.line, line);
        report.entriesSuperseded += 1;
      } else if (route === "user" || route === "curated") {
        if (!dryRun)
          await appendLine(
            context,
            route === "user" ? context.paths.userFile : context.paths.memoryFile,
            line,
          );
        report.entriesAppended += 1;
      } else {
        if (!dryRun) await appendDailyEntry(context.paths, line);
        report.entriesAppended += 1;
      }
      corpus.texts.add(parsed.text);
      accepted = true;
    }
    if (accepted) {
      if (!dryRun) await unlink(join(context.paths.inboxDir, name)).catch(() => undefined);
      report.filesProcessed += 1;
    } else {
      if (!dryRun) await moveRejected(context.paths, name);
      report.filesRejected += 1;
    }
  }
  if (!dryRun && !options.deferIndex)
    await reindex(context.paths, context.settings, context.store, options);
  return report;
}

/**
 * Serialize whole runs (dream or process) with a stale-tolerant lock file so a
 * nightly sweep and a manual CLI invocation never mutate the corpus together.
 */
export async function withRunLock<T>(paths: MemomaticPaths, work: () => Promise<T>): Promise<T> {
  const owner = `${process.pid} ${new Date().toISOString()} ${randomBytes(12).toString("hex")}\n`;
  const acquire = async (): Promise<void> => {
    try {
      const handle = await open(paths.runLockFile, "wx", 0o600);
      try {
        await handle.writeFile(owner);
      } finally {
        await handle.close();
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      let stale = false;
      try {
        const handle = await open(paths.runLockFile, "r");
        try {
          const info = await handle.stat();
          const owner = Number.parseInt((await handle.readFile("utf8")).split(" ")[0], 10);
          if (Number.isSafeInteger(owner) && owner > 0) {
            try {
              process.kill(owner, 0);
            } catch (cause) {
              stale = (cause as NodeJS.ErrnoException).code === "ESRCH";
            }
          } else stale = Date.now() - info.mtimeMs > LOCK_STALE_MS;
        } finally {
          await handle.close();
        }
      } catch {
        return acquire();
      }
      if (!stale) throw new Error("another memomatic run is active");
      await rm(paths.runLockFile, { force: true });
      return acquire();
    }
  };
  await acquire();
  try {
    return await work();
  } finally {
    if ((await readTextIfExists(paths.runLockFile)) === owner)
      await rm(paths.runLockFile, { force: true }).catch(() => undefined);
  }
}
