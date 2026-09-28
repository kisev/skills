#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { exportAll, cardMarkdown } from "./export.js";
import { runMcp, VERSION } from "./mcp.js";
import { filterCards, rootPath, Store, ttl, type Input } from "./store.js";
import { serve } from "./web.js";

const HELP = `taskmatic [--home PATH] COMMAND [options]
Commands: boards, board-create SLUG [--title TITLE], add TITLE, list, show ID,
  edit ID, move ID STATUS, claim ID --agent NAME [--ttl 30m], heartbeat ID --agent NAME,
  release ID --agent NAME, complete ID, note ID TEXT, export, snapshot, mcp,
  path [root|db|export|web], serve [--host 127.0.0.1] [--port 8765]
Fields: --board --title --priority --labels a,b --assignee --parent --linked
  --notes TEXT | --notes-file FILE (or - for stdin); --clear-assignee --clear-linked
Filters: --board --status --assignee --label. Output: --json.
Use --version for the installed package version. taskmatic-web is a compatibility alias.
`;
async function main(argv: string[]): Promise<void> {
  if (argv.includes("--version")) {
    console.log(VERSION);
    return;
  }
  if (!argv.length || argv.includes("--help") || argv[0] === "help") {
    console.log(HELP);
    return;
  }
  const fields: Input = {};
  const positional: string[] = [];
  const valueOptions = new Set([
    "home",
    "title",
    "board",
    "priority",
    "labels",
    "assignee",
    "parent",
    "linked",
    "notes",
    "notes-file",
    "status",
    "label",
    "agent",
    "ttl",
    "actor",
    "host",
    "port",
  ]);
  let json = false;
  let literal = false;
  for (let index = 0; index < argv.length; index++) {
    const value = argv[index];
    if (value === "--") {
      literal = true;
      continue;
    }
    if (literal || !value.startsWith("--")) {
      positional.push(value);
      continue;
    }
    const key = value.slice(2);
    if (key === "json") {
      json = true;
      continue;
    }
    if (key === "clear-assignee" || key === "clear-linked") {
      fields[key.slice(6)] = null;
      continue;
    }
    if (!valueOptions.has(key) || index + 1 >= argv.length || argv[index + 1].startsWith("--"))
      throw new Error(`unknown or incomplete option ${value}`);
    fields[key] = argv[++index];
  }
  const [command, ...args] = positional;
  if (!command) throw new Error("command is required");
  const commands = new Set([
    "boards",
    "board-create",
    "add",
    "list",
    "show",
    "edit",
    "move",
    "claim",
    "heartbeat",
    "release",
    "complete",
    "note",
    "export",
    "snapshot",
    "mcp",
    "path",
    "serve",
  ]);
  if (!commands.has(command)) throw new Error(`unknown command ${command}`);
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
    console.log(
      `taskmatic board: http://${typeof address === "object" && address ? address.address : "127.0.0.1"}:${typeof address === "object" && address ? address.port : fields.port}/`,
    );
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
try {
  await main(process.argv.slice(2));
} catch (error) {
  console.error(`taskmatic: ${(error as Error).message}`);
  process.exitCode = 2;
}
