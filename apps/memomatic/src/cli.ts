#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { openMemomatic, rebuildIndex, searchMemory } from "./service.js";
import { runDream } from "./dream.js";
import { processInbox, withRunLock } from "./inbox.js";
import { OpenCodeExecutor } from "./executor.js";
import { handleMcpRequest } from "./mcp.js";

const USAGE = `usage: memomatic <command> [args]

commands:
  process [--dry-run]      validate the inbox and move accepted entries into the corpus
  dream [--dry-run]        run the consolidation sweep (scheduled by memomatic-dream.timer)
  search <query>           search memory from the command line
  status                   report corpus and index status
  index                    rebuild the search index
  mcp-serve                run the MCP stdio server`;

function parseArguments(argv: string[]): { command: string; rest: string[] } {
  const [command, ...rest] = argv;
  if (!command || command === "help" || command === "--help") {
    process.stderr.write(`${USAGE}\nSearch options: --explain, --project NAME\n`);
    process.exitCode = command ? 0 : 2;
    return { command: "", rest };
  }
  return { command, rest };
}

async function main(): Promise<void> {
  const { command, rest } = parseArguments(process.argv.slice(2));
  if (!command) return;
  if (command === "mcp-serve") {
    const { runMcpServer } = await import("./mcp.js");
    await runMcpServer();
    return;
  }
  if (command === "mcp-selftest") {
    process.stdout.write(await handleMcpRequest({ id: 1, method: "tools/list" }));
    return;
  }
  if (command === "--version") {
    const { version } = JSON.parse(
      readFileSync(new URL("../package.json", import.meta.url), "utf8"),
    ) as { version: string };
    process.stdout.write(`${version}\n`);
    return;
  }
  const dryRun = (command === "dream" || command === "process") && rest.includes("--dry-run");
  const context = await openMemomatic({ readOnly: dryRun });
  try {
    if (command === "dream" || command === "process") {
      const execute = async () => {
        if (command === "process") return processInbox(context, { dryRun });
        const executor = context.settings.dream.model
          ? new OpenCodeExecutor({
              model: context.settings.dream.model,
              variant: context.settings.dream.variant,
            })
          : null;
        return runDream(context, executor, { dryRun });
      };
      const result = dryRun ? await execute() : await withRunLock(context.paths, execute);
      process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
      return;
    }
    if (command === "search") {
      const parts: string[] = [];
      let explain = false;
      let project: string | undefined;
      for (let index = 0; index < rest.length; index += 1) {
        if (rest[index] === "--explain") explain = true;
        else if (rest[index] === "--project") {
          project = rest[++index];
          if (!project || project.startsWith("--")) throw new Error("--project requires a value");
        } else parts.push(rest[index]);
      }
      const query = parts.join(" ").trim();
      if (!query) throw new Error("search requires a query");
      const hits = await searchMemory(context, query, { project });
      if (!hits.length) process.stdout.write("No relevant memory found.\n");
      for (const hit of hits) {
        process.stdout.write(
          `${hit.score.toFixed(3)}  ${hit.entry.file.replace(`${context.paths.stateRoot}/`, "")}:${hit.entry.line}  ${hit.snippet}\n`,
        );
        if (explain) process.stdout.write(`  ${JSON.stringify(hit.explanation)}\n`);
      }
      return;
    }
    if (command === "status") {
      const count = await rebuildIndex(context);
      const fts = context.store.hasFts();
      process.stdout.write(
        `${JSON.stringify({ entries: count, fts5: fts, stateRoot: context.paths.stateRoot }, null, 2)}\n`,
      );
      return;
    }
    if (command === "index") {
      process.stdout.write(`${await rebuildIndex(context)} entries indexed\n`);
      return;
    }
    process.stderr.write(`unknown command: ${command}\n${USAGE}`);
    process.exitCode = 2;
  } finally {
    context.store.close();
  }
}

await main();
