#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { exportAll, cardMarkdown } from "./export.js";
import { runMcp, VERSION } from "./mcp.js";
import { filterCards, rootPath, Store, ttl, type Input } from "./store.js";
import { serve } from "./web.js";
import {
  program,
  common,
  Option,
  configFile,
  applyConfig,
  reporter,
  fail,
  integer,
  type Command,
} from "./generated/cli.js";

async function main(command: string, args: string[], fields: Input, json: boolean): Promise<void> {
  const home = typeof fields.home === "string" ? fields.home : undefined;
  if (command === "path") {
    const root = rootPath(home);
    const paths: Record<string, string> = {
      root,
      db: join(root, "taskmatic.db"),
      export: join(root, "export"),
      web: join(root, "export/web"),
    };
    if (!paths[args[0] ?? "root"]) throw new Error("unknown path");
    console.log(paths[args[0] ?? "root"]);
    return;
  }
  if (command === "serve") {
    const server = await serve(
      home,
      String(fields.host ?? "127.0.0.1"),
      Number(fields.port ?? 8765),
    );
    const address = server.address();
    const url = `http://${typeof address === "object" && address ? address.address : "127.0.0.1"}:${typeof address === "object" && address ? address.port : fields.port}/`;
    console.log(json ? JSON.stringify({ url, readOnly: true }) : `taskmatic board: ${url}`);
    for (const signal of ["SIGINT", "SIGTERM"] as const) process.once(signal, () => server.close());
    return;
  }
  if (fields.labels !== undefined)
    fields.labels = String(fields.labels)
      .split(",")
      .filter((value) => value.trim());
  if (fields.ttl !== undefined) fields.ttl_seconds = ttl(fields.ttl);
  if (fields["notes-file"] !== undefined) {
    if (fields.notes !== undefined) throw new Error("use either --notes or --notes-file, not both");
    if (fields["notes-file"] === "-") {
      let notes = "";
      for await (const chunk of process.stdin) notes += String(chunk);
      fields.notes = notes;
    } else fields.notes = await readFile(String(fields["notes-file"]), "utf8");
  }
  const store = await Store.open(home);
  try {
    if (command === "mcp") {
      await runMcp(store);
      return;
    }
    let result: unknown;
    if (command === "boards") {
      const snapshot = store.snapshot();
      result = snapshot.boards.map((board) => ({
        ...board,
        cards: snapshot.cards.filter((card) => card.board === board.slug).length,
      }));
    } else if (command === "board-create") {
      result = store.board(args[0], fields.title as string | undefined);
      await exportAll(store);
    } else if (command === "snapshot" || command === "list") {
      const snapshot = store.snapshot();
      snapshot.cards = filterCards(snapshot, fields);
      result = command === "list" ? snapshot.cards : snapshot;
    } else if (command === "show") {
      const card = store.read(args[0]);
      if (!json) {
        console.log(cardMarkdown(card));
        return;
      }
      result = card;
    } else if (command === "export") {
      await exportAll(store);
      console.log(join(store.root, "export"));
      return;
    } else {
      fields.id = args[0];
      if (command === "add") fields.title = args[0];
      if (command === "move") fields.status = args[1];
      if (command === "note") fields.text = args[1];
      result = store.mutate(
        command === "add" ? "create" : command,
        fields,
        command === "note" ? "human" : "cli",
      );
      if (command !== "heartbeat") await exportAll(store);
    }
    if (json || command === "snapshot") console.log(JSON.stringify(result, null, 2));
    else if (command === "boards") {
      for (const board of result as Array<{ slug: string; title: string; cards: number }>)
        console.log(`${board.slug}\t${board.title}\t${board.cards} cards`);
    } else if (command === "list") {
      const cards = result as Array<{
        id: string;
        board: string;
        status: string;
        priority: string;
        title: string;
      }>;
      if (!cards.length) console.log("no cards match");
      for (const card of cards)
        console.log(`${card.id}  ${card.board}  ${card.status}  p:${card.priority}  ${card.title}`);
    } else if (command === "board-create") {
      const board = result as { slug: string; title: string };
      console.log(`board ${board.slug}: ${board.title}`);
    } else {
      const card = result as {
        id: string;
        board: string;
        status: string;
        claim_remaining_seconds: number;
      };
      const messages: Record<string, string> = {
        add: `created ${card.id} on ${card.board}`,
        edit: `edited ${card.id}`,
        move: `moved ${card.id} to ${card.status}`,
        claim: `claimed ${card.id} by ${fields.agent}`,
        heartbeat: `heartbeat ${card.id}: ${card.claim_remaining_seconds}s left`,
        release: `released ${card.id}`,
        complete: `completed ${card.id}`,
        note: `noted ${card.id}`,
      };
      console.log(messages[command]);
    }
  } finally {
    store.close();
  }
}
const cli = common(
  program("taskmatic", "Private task boards for people and agents", VERSION),
  "TASKMATIC",
).addOption(new Option("--home <path>", "absolute state directory").env("TASKMATIC_HOME"));
const definitions: Array<[string, string, string[]]> = [
  ["boards", "List boards and card counts", []],
  ["board-create <slug>", "Create an empty board", ["title"]],
  [
    "add <title>",
    "Create a task card",
    ["board", "priority", "labels", "assignee", "parent", "linked", "notes", "notes-file"],
  ],
  ["list", "List matching cards", ["board", "status", "assignee", "label"]],
  ["show <id>", "Read a card with its activity", []],
  [
    "edit <id>",
    "Change only explicitly supplied card fields",
    [
      "title",
      "priority",
      "labels",
      "assignee",
      "linked",
      "notes",
      "notes-file",
      "clear-assignee",
      "clear-linked",
    ],
  ],
  ["move <id> <status>", "Move a card to another status", []],
  ["claim <id>", "Claim work without taking another agent's live claim", ["agent", "ttl"]],
  ["heartbeat <id>", "Extend your live claim without rewriting exports", ["agent", "ttl"]],
  ["release <id>", "Release your claim", ["agent"]],
  ["complete <id>", "Mark a card done and clear its claim", []],
  ["note <id> <text>", "Append a progress note", ["actor"]],
  ["export", "Regenerate derived Markdown and HTML", []],
  ["snapshot", "Print the current snapshot JSON", ["board", "status", "assignee", "label"]],
  ["mcp", "Serve MCP on stdio; stdout is protocol-only", []],
  ["path [kind]", "Print root, db, export or web path without creating it", []],
  ["serve", "Serve the existing board on IPv4 loopback (read-only)", ["host", "port"]],
];
for (const [signature, description, names] of definitions) {
  const command = cli.command(signature).description(description);
  for (const name of names) {
    const option = new Option(
      `--${name}${name.startsWith("clear-") ? "" : " <value>"}`,
      (
        {
          ttl: "claim duration, e.g. 30m (default 30m)",
          port: "loopback port (default 8765)",
          host: "loopback address (default 127.0.0.1)",
          "notes-file": "read notes from a UTF-8 file or - for stdin",
        } as Record<string, string>
      )[name] ?? name.replaceAll("-", " "),
    );
    if (!name.startsWith("clear-"))
      option.env(`TASKMATIC_${name.toUpperCase().replaceAll("-", "_")}`);
    if (name === "port") option.argParser(integer);
    if (name === "ttl") option.argParser((value) => ttl(value));
    if (name === "agent") option.makeOptionMandatory();
    if (name === "priority") option.choices(["low", "normal", "high", "urgent"]);
    if (name === "status") option.choices(["todo", "doing", "review", "blocked", "done"]);
    command.addOption(option);
  }
  command.addHelpText(
    "after",
    `\nExample: taskmatic ${signature.replace(/<([^>]+)>/g, (_, value) => value.toUpperCase()).replace(/\[.*?\]/g, "")}\n\nUse --json for automation; logs use stderr. Configuration precedence: CLI > env > file > defaults.`,
  );
  command.action(async (...values: unknown[]) => {
    const cmd = values.at(-1) as Command;
    const config = await configFile(cli.opts().config);
    applyConfig(cli, config);
    applyConfig(cmd, config);
    const fields: Input = { ...cmd.optsWithGlobals() };
    if (fields.notesFile !== undefined) fields["notes-file"] = fields.notesFile;
    if (fields.clearAssignee) fields.assignee = null;
    if (fields.clearLinked) fields.linked = null;
    const logs = reporter(command.name() === "mcp" ? { logLevel: "silent" } : fields);
    try {
      logs.emit({ phase: command.name(), message: "Executing command", level: "debug" });
      await main(command.name(), cmd.args, fields, fields.json === true);
      logs.emit({
        phase: `${command.name()}.${command.name() === "serve" ? "ready" : "done"}`,
        message: command.name() === "serve" ? "Server ready" : "Command complete",
        level: "debug",
      });
    } finally {
      logs.close();
    }
  });
}
try {
  if (process.argv.length === 2) cli.outputHelp();
  else await cli.parseAsync(process.argv);
} catch (error) {
  fail(
    "taskmatic",
    error,
    process.argv.includes("--json") || cli.opts().json === true || cli.opts().logFormat === "json",
  );
}
