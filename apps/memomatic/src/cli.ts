#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { readdir, stat } from "node:fs/promises";
import { isAbsolute } from "node:path";
import { openMemomatic, rebuildIndex, searchMemory } from "./service.js";
import { runDream } from "./dream.js";
import { runSessions } from "./sessions.js";
import { processInbox, withRunLock } from "./inbox.js";
import { OpenCodeExecutor } from "./executor.js";
import { normalizeSettings } from "./settings.js";
import { planIngestion } from "./ingestion.js";
import { opencodeDatabasePath } from "./ingest.js";
import { promotionCandidates, relevanceByFts } from "./gates.js";
import { memomaticPaths } from "./paths.js";
import {
  program,
  common,
  Option,
  configFile,
  applyConfig,
  reporter,
  cancellation,
  duration,
  integer,
  fail,
  type Command,
} from "./generated/cli.js";

const version = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
).version;
const cli = common(
  program("memomatic", "Explicit memory retrieval and observable background processing", version),
  "MEMOMATIC",
).addOption(
  new Option("--state-dir <path>", "absolute private memory directory").env("MEMOMATIC_HOME"),
);
const add = (name: string, description: string) => cli.command(name).description(description);
const resolveOptions = async (command: Command) => {
  const initial = command.optsWithGlobals();
  if (initial.stateDir) {
    if (!isAbsolute(initial.stateDir)) throw new Error("state-dir must be absolute");
    process.env.MEMOMATIC_HOME = initial.stateDir;
  }
  const config = await configFile(initial.config ?? memomaticPaths().settingsFile).catch(
    (error) => {
      if (!initial.config && (error as NodeJS.ErrnoException).code === "ENOENT") return {};
      throw error;
    },
  );
  applyConfig(cli, config);
  applyConfig(command, config);
  const opts = command.optsWithGlobals();
  if (opts.stateDir) {
    if (!isAbsolute(opts.stateDir)) throw new Error("state-dir must be absolute");
    process.env.MEMOMATIC_HOME = opts.stateDir;
  }
  if (opts.config) process.env.MEMOMATIC_CONFIG = opts.config;
  return opts;
};
const run = async (
  command: Command,
  action: (
    context: Awaited<ReturnType<typeof openMemomatic>>,
    options: Record<string, any>,
    runtime: { signal: AbortSignal; observe: ReturnType<typeof reporter>["emit"] },
  ) => Promise<void>,
) => {
  const opts = await resolveOptions(command);
  const log = reporter(opts);
  const abort = cancellation();
  const limited = opts.maxDuration
    ? AbortSignal.any([abort.signal, AbortSignal.timeout(opts.maxDuration)])
    : abort.signal;
  let context: Awaited<ReturnType<typeof openMemomatic>> | undefined;
  try {
    context = await openMemomatic({
      readOnly: opts.dryRun || opts.plan || command.name() === "status",
      configure: (settings) => {
        const sessions = { ...settings.sessions };
        const dream = { ...settings.dream };
        for (const [flag, key] of [
          ["model", "model"],
          ["variant", "variant"],
          ["timeout", "timeoutMs"],
          ["maxDuration", "maxDurationMs"],
          ["retries", "retries"],
        ] as const) {
          if (opts[flag] !== undefined) {
            Object.assign(sessions, { [key]: opts[flag] });
            Object.assign(dream, { [key]: opts[flag] });
          }
        }
        for (const [flag, key] of [
          ["maxSessions", "maxSessions"],
          ["chunkChars", "maxChars"],
          ["idle", "idleMs"],
          ["opencodeUrl", "opencodeUrl"],
        ] as const)
          if (opts[flag] !== undefined) Object.assign(sessions, { [key]: opts[flag] });
        return normalizeSettings({ ...settings, sessions, dream });
      },
    });
    const deadline = (section: "sessions" | "dream") =>
      context!.settings[section].maxDurationMs && !opts.maxDuration
        ? AbortSignal.any([limited, AbortSignal.timeout(context!.settings[section].maxDurationMs!)])
        : limited;
    const signal = command.name() === "sessions" ? deadline("sessions") : deadline("dream");
    await action(context, opts, { signal, observe: log.emit });
  } finally {
    context?.store.close();
    abort.dispose();
    log.close();
  }
};
const output = (value: unknown, opts: Record<string, unknown>, summary: string) =>
  console.log(opts.json || !process.stdout.isTTY ? JSON.stringify(value, null, 2) : summary);

const modelOptions = (command: Command) =>
  command
    .addOption(
      new Option("--model <provider/model>", "OpenCode model; defaults to settings").env(
        "MEMOMATIC_MODEL",
      ),
    )
    .addOption(
      new Option("--variant <name>", "provider reasoning variant").env("MEMOMATIC_VARIANT"),
    )
    .addOption(
      new Option("--timeout <duration>", "per-model-call timeout (default 3m)")
        .argParser(duration)
        .env("MEMOMATIC_TIMEOUT"),
    )
    .addOption(
      new Option("--max-duration <duration>", "whole-run deadline; 0 means unlimited")
        .argParser(duration)
        .env("MEMOMATIC_MAX_DURATION"),
    )
    .addOption(
      new Option("--retries <count>", "additional model attempts (default 1)")
        .argParser(integer)
        .env("MEMOMATIC_RETRIES"),
    );
const executor = (
  context: Awaited<ReturnType<typeof openMemomatic>>,
  runtime: {
    signal: AbortSignal;
    observe: ReturnType<typeof reporter>["emit"];
  },
) => {
  const sections = {
    sessions: context.settings.sessions,
    dream: context.settings.dream,
  } as const;
  const create = (section: "sessions" | "dream") => {
    const config = sections[section];
    return config.model
      ? new OpenCodeExecutor({
          model: config.model,
          variant: config.variant,
          url: "opencodeUrl" in config ? config.opencodeUrl : null,
          timeoutMs: config.timeoutMs,
          retries: config.retries,
          ...runtime,
        })
      : null;
  };
  return create;
};

const sessions = add(
  "sessions",
  "Drain the OpenCode session snapshot into episodic memory, checkpointing fragments",
)
  .option("--plan", "count pending work without model calls or writes")
  .option("--dry-run", "preview without persistent writes (model calls still occur)");
modelOptions(sessions)
  .addOption(
    new Option("--max-sessions <count>", "optional session limit; 0 means all")
      .argParser(integer)
      .env("MEMOMATIC_MAX_SESSIONS"),
  )
  .addOption(
    new Option("--chunk-chars <count>", "maximum new text per fragment (default 24000)")
      .argParser(integer)
      .env("MEMOMATIC_CHUNK_CHARS"),
  )
  .addOption(
    new Option("--idle <duration>", "minimum session idle age (default 10m)")
      .argParser(duration)
      .env("MEMOMATIC_IDLE"),
  )
  .addOption(
    new Option(
      "--opencode-url <url>",
      "reuse an existing OpenCode server; otherwise start one per run",
    ).env("MEMOMATIC_OPENCODE_URL"),
  )
  .addOption(
    new Option("--database <path>", "OpenCode SQLite session database").env("MEMOMATIC_DATABASE"),
  )
  .addHelpText(
    "after",
    "\nExamples:\n  memomatic sessions\n  memomatic sessions --max-duration 15m --log-format json\n  memomatic sessions --dry-run --max-sessions 2\n\nCompleted fragments survive cancellation. Logs use stderr; --json keeps stdout machine-readable.",
  );
sessions.action(async () =>
  run(sessions, async (context, opts, runtime) => {
    if (opts.plan) {
      const start = Date.now();
      const plan = planIngestion(opts.database ?? opencodeDatabasePath(), context.store, {
        before: Date.now() - context.settings.sessions.idleMs,
        maxChars: context.settings.sessions.maxChars,
        maxSessions: context.settings.sessions.maxSessions,
      });
      const summary = {
        sessions: plan.sessions,
        messages: plan.messages,
        fragments: plan.fragments.length,
        characters: plan.characters,
        cachedFragments: plan.cached,
        cachedSessions: plan.cachedSessions,
        unscannedSessions: plan.unscannedSessions,
        scanMs: Date.now() - start,
      };
      output(
        summary,
        opts,
        `${summary.sessions} sessions, ${summary.fragments} fragments, ${summary.characters} characters (${summary.scanMs}ms scan). No model calls.`,
      );
      return;
    }
    const create = executor(context, runtime);
    const model = create("sessions");
    try {
      const execute = () =>
        runSessions(context, model, {
          ...runtime,
          dryRun: opts.dryRun,
          databaseFile: opts.database,
        });
      const result = opts.dryRun ? await execute() : await withRunLock(context.paths, execute);
      output(
        { ...result, modelUsage: model?.usage ?? null },
        opts,
        `Sessions complete: ${result.sessionsIngested} sessions, ${result.candidatesExtracted} candidates, ${result.elapsedMs}ms`,
      );
    } finally {
      await model?.close();
    }
  }),
);

const dream = add("dream", "Consolidate memory: inbox, promotion, bounded rewrite, archive")
  .option("--plan", "count pending work without model calls or writes")
  .option("--dry-run", "preview without persistent writes (model calls still occur)");
modelOptions(dream).addHelpText(
  "after",
  "\nExamples:\n  memomatic dream\n  memomatic dream --max-duration 15m --log-format json\n  memomatic dream --dry-run\n\nSession extraction lives in `memomatic sessions`. Logs use stderr; --json keeps stdout machine-readable.",
);
dream.action(async () =>
  run(dream, async (context, opts, runtime) => {
    if (opts.plan) {
      const relevance = relevanceByFts(context.store, context.settings);
      const candidates = promotionCandidates(context.store, context.settings, relevance);
      const inboxFiles = (await readdir(context.paths.inboxDir).catch(() => [])).filter((name) =>
        name.endsWith(".md"),
      ).length;
      const summary = { inboxFiles, promotionCandidates: candidates.length };
      output(
        summary,
        opts,
        `${summary.inboxFiles} inbox files, ${summary.promotionCandidates} promotion candidates. No model calls.`,
      );
      return;
    }
    const create = executor(context, runtime);
    const model = create("dream");
    try {
      const execute = () => runDream(context, model, { ...runtime, dryRun: opts.dryRun });
      const result = opts.dryRun ? await execute() : await withRunLock(context.paths, execute);
      output(
        { ...result, modelUsage: model?.usage ?? null },
        opts,
        `Dream complete: ${result.promoted.length} promoted, ${result.superseded.length} superseded, ${result.elapsedMs}ms`,
      );
    } finally {
      await model?.close();
    }
  }),
);
const processCommand = add(
  "process",
  "Process explicit inbox entries without LLM extraction",
).option("--dry-run", "preview without writes");
processCommand.action(() =>
  run(processCommand, async (context, opts, runtime) => {
    const execute = () => processInbox(context, { ...runtime, dryRun: opts.dryRun });
    const result = opts.dryRun ? await execute() : await withRunLock(context.paths, execute);
    output(
      result,
      opts,
      `Processed ${result.filesProcessed} inbox files; ${result.entriesAppended} entries added`,
    );
  }),
);
const index = add("index", "Update derived search data, reusing unchanged embeddings").option(
  "--force",
  "recompute all document embeddings",
);
index.action(() =>
  run(index, async (context, opts, runtime) => {
    const entries = await rebuildIndex(context, { ...runtime, force: opts.force });
    if (opts.json) output({ entries }, opts, "");
    else console.log(`${entries} entries indexed`);
  }),
);
const status = add("status", "Read corpus/index/queue status without indexing or model calls");
status.action(() =>
  run(status, async (context, opts, runtime) => {
    const inboxFiles = (await readdir(context.paths.inboxDir).catch(() => [])).filter((name) =>
      name.endsWith(".md"),
    ).length;
    let sessionBacklog: {
      sessions: number;
      messages: number;
      fragments: number;
      characters: number;
      cachedFragments: number;
      cachedSessions: number;
      unscannedSessions: number;
    } | null = null;
    const databaseFile = opencodeDatabasePath();
    if (await stat(databaseFile).catch(() => null)) {
      try {
        const plan = planIngestion(databaseFile, context.store, {
          before: Date.now() - context.settings.sessions.idleMs,
          maxChars: context.settings.sessions.maxChars,
          maxSessions: context.settings.sessions.maxSessions,
        });
        sessionBacklog = {
          sessions: plan.sessions,
          messages: plan.messages,
          fragments: plan.fragments.length,
          characters: plan.characters,
          cachedFragments: plan.cached,
          cachedSessions: plan.cachedSessions,
          unscannedSessions: plan.unscannedSessions,
        };
      } catch (error) {
        runtime.observe({
          phase: "status.sessions",
          message: `Cannot read OpenCode sessions: ${(error as Error).message}`,
          level: "warn",
        });
      }
    }
    const relevance = relevanceByFts(context.store, context.settings);
    const candidates = promotionCandidates(context.store, context.settings, relevance);
    const report = {
      entries: context.store.allEntries().length,
      fts5: context.store.hasFts(),
      stateRoot: context.paths.stateRoot,
      queue: {
        inboxFiles,
        sessions: sessionBacklog,
        promotionCandidates: candidates.length,
      },
      lastRun: {
        dream: context.store.getMeta("last-dream-at"),
        sessions: context.store.getMeta("last-sessions-at"),
      },
    };
    output(
      report,
      opts,
      `${report.entries} indexed entries, ${inboxFiles} inbox files, ${
        sessionBacklog ? `${sessionBacklog.fragments} pending fragments` : "no session database"
      }, ${candidates.length} promotion candidates in ${context.paths.stateRoot}`,
    );
  }),
);
const search = add("search <query...>", "Find relevant memory or return no matches")
  .option("--explain", "include relevance diagnostics")
  .addOption(
    new Option("--project <name>", "restrict to a project and user-level memory").env(
      "MEMOMATIC_PROJECT",
    ),
  );
search.action((query: string[]) =>
  run(search, async (context, opts) => {
    const hits = await searchMemory(context, query.join(" "), { project: opts.project });
    if (opts.json) {
      console.log(
        JSON.stringify(
          hits.map((hit) => ({
            file: hit.entry.file,
            line: hit.entry.line,
            score: hit.score,
            text: hit.snippet,
            ...(opts.explain ? { explanation: hit.explanation } : {}),
          })),
          null,
          2,
        ),
      );
      return;
    }
    if (!hits.length) console.log("No relevant memory found.");
    for (const hit of hits) {
      console.log(
        `${hit.score.toFixed(3)}  ${hit.entry.file.replace(`${context.paths.stateRoot}/`, "")}:${hit.entry.line}  ${hit.snippet}`,
      );
      if (opts.explain) console.log(`  ${JSON.stringify(hit.explanation)}`);
    }
  }),
);
cli
  .command("mcp-serve")
  .description("Serve newline-delimited MCP; stdout is protocol-only")
  .action(async () => {
    await resolveOptions(cli);
    const { runMcpServer } = await import("./mcp.js");
    await runMcpServer();
  });
cli
  .command("mcp-selftest")
  .description("Print the MCP tool registry without touching state")
  .action(async () => {
    const { handleMcpRequest } = await import("./mcp.js");
    process.stdout.write(await handleMcpRequest({ id: 1, method: "tools/list" }));
  });
try {
  if (process.argv.length === 2) cli.outputHelp();
  else await cli.parseAsync(process.argv);
} catch (error) {
  fail(
    "memomatic",
    error,
    process.argv.includes("--json") || cli.opts().json === true || cli.opts().logFormat === "json",
  );
}
