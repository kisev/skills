#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { isAbsolute } from "node:path";
import { openMemomatic, rebuildIndex, searchMemory } from "./service.js";
import { runDream } from "./dream.js";
import { processInbox, withRunLock } from "./inbox.js";
import { OpenCodeExecutor } from "./executor.js";
import { normalizeSettings } from "./settings.js";
import { planIngestion } from "./ingestion.js";
import { opencodeDatabasePath } from "./ingest.js";
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
        const dream = { ...settings.dream };
        for (const [flag, key] of [
          ["model", "model"],
          ["variant", "variant"],
          ["timeout", "timeoutMs"],
          ["maxDuration", "maxDurationMs"],
          ["maxSessions", "maxSessions"],
          ["chunkChars", "maxChars"],
          ["retries", "retries"],
          ["idle", "idleMs"],
          ["opencodeUrl", "opencodeUrl"],
        ] as const)
          if (opts[flag] !== undefined) Object.assign(dream, { [key]: opts[flag] });
        return normalizeSettings({ ...settings, dream });
      },
    });
    const signal =
      context.settings.dream.maxDurationMs && !opts.maxDuration
        ? AbortSignal.any([limited, AbortSignal.timeout(context.settings.dream.maxDurationMs)])
        : limited;
    await action(context, opts, { signal, observe: log.emit });
  } finally {
    context?.store.close();
    abort.dispose();
    log.close();
  }
};
const output = (value: unknown, opts: Record<string, unknown>, summary: string) =>
  console.log(opts.json || !process.stdout.isTTY ? JSON.stringify(value, null, 2) : summary);

const dream = add("dream", "Drain the session snapshot, checkpointing completed fragments")
  .option("--plan", "count pending work without model calls or writes")
  .option("--dry-run", "preview without persistent writes (model calls still occur)")
  .addOption(
    new Option("--model <provider/model>", "OpenCode model; defaults to settings.dream.model").env(
      "MEMOMATIC_MODEL",
    ),
  )
  .addOption(new Option("--variant <name>", "provider reasoning variant").env("MEMOMATIC_VARIANT"))
  .addOption(
    new Option("--timeout <duration>", "per-model-call timeout (default 3m)")
      .argParser(duration)
      .env("MEMOMATIC_TIMEOUT"),
  )
  .addOption(
    new Option("--max-duration <duration>", "whole-run deadline; 0 means drain the snapshot")
      .argParser(duration)
      .env("MEMOMATIC_MAX_DURATION"),
  )
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
    new Option("--retries <count>", "additional model attempts (default 1)")
      .argParser(integer)
      .env("MEMOMATIC_RETRIES"),
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
    "\nExamples:\n  memomatic dream\n  memomatic dream --max-duration 15m --log-format json\n  memomatic dream --dry-run --max-sessions 2\n\nCompleted fragments survive cancellation. Logs use stderr; --json keeps stdout machine-readable.",
  );
dream.action(async () =>
  run(dream, async (context, opts, runtime) => {
    if (opts.plan) {
      const start = Date.now();
      const plan = planIngestion(opts.database ?? opencodeDatabasePath(), context.store, {
        before: Date.now() - context.settings.dream.idleMs,
        maxChars: context.settings.dream.maxChars,
        maxSessions: context.settings.dream.maxSessions,
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
    const executor = context.settings.dream.model
      ? new OpenCodeExecutor({
          model: context.settings.dream.model,
          variant: context.settings.dream.variant,
          url: context.settings.dream.opencodeUrl,
          timeoutMs: context.settings.dream.timeoutMs,
          retries: context.settings.dream.retries,
          ...runtime,
        })
      : null;
    try {
      const execute = () =>
        runDream(context, executor, {
          ...runtime,
          dryRun: opts.dryRun,
          databaseFile: opts.database,
        });
      const result = opts.dryRun ? await execute() : await withRunLock(context.paths, execute);
      output(
        { ...result, modelUsage: executor?.usage ?? null },
        opts,
        `Dream complete: ${result.sessionsIngested} sessions, ${result.candidatesExtracted} candidates, ${result.elapsedMs}ms`,
      );
    } finally {
      await executor?.close();
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
const status = add("status", "Read corpus/index status without indexing or model calls");
status.action(() =>
  run(status, async (context, opts) =>
    output(
      {
        entries: context.store.allEntries().length,
        fts5: context.store.hasFts(),
        stateRoot: context.paths.stateRoot,
      },
      opts,
      `${context.store.allEntries().length} indexed entries in ${context.paths.stateRoot}`,
    ),
  ),
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
