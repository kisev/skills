import { randomBytes } from "node:crypto";
import { chmod } from "node:fs/promises";
import { homedir } from "node:os";
import { isAbsolute, join, normalize } from "node:path";
import { DatabaseSync, type SQLInputValue } from "node:sqlite";
import { assertSafePath, ensureDirectory } from "@kisev/safe-fs";

export const STATUSES = ["todo", "doing", "review", "blocked", "done"] as const;
export const PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export type Input = Record<string, unknown>;
type Row = Record<string, SQLInputValue>;
export type Activity = { at: string; kind: string; actor: string; detail: string };
export type Card = {
  id: string;
  board: string;
  title: string;
  notes: string;
  status: string;
  priority: string;
  labels: string[];
  assignee: string | null;
  parent: string | null;
  children: string[];
  linked: string | null;
  claimed_by: string | null;
  claim_expires_at: string | null;
  claim_state: "held" | "expired" | null;
  claim_remaining_seconds: number | null;
  created_at: string;
  updated_at: string;
  activity: Activity[];
};
export type Board = { slug: string; title: string; created_at: string };
export type Snapshot = {
  schema: "taskmatic/snapshot/v1";
  generated_at: string;
  boards: Board[];
  cards: Card[];
};
export const iso = (time = Date.now()): string =>
  new Date(time).toISOString().replace(/\.\d{3}Z$/, "Z");

export function rootPath(explicit?: string): string {
  const path =
    explicit ??
    process.env.TASKMATIC_HOME ??
    join(
      process.env.XDG_STATE_HOME ?? join(process.env.HOME ?? homedir(), ".local/state"),
      "agent-skills/taskmatic",
    );
  if (
    !isAbsolute(path) ||
    path.split("/").some((part) => part === "." || part === "..") ||
    path.includes("\0")
  )
    throw new Error("taskmatic home must be an absolute normalized path");
  return normalize(path);
}

export function text(input: Input, key: string, fallback?: string, max = 8000): string {
  const value = input[key] ?? fallback;
  if (typeof value !== "string" || value.length > max)
    throw new Error(`${key} must be a string of at most ${max} characters`);
  return value;
}
function identifier(input: Input, key: string, fallback?: string): string {
  const value = text(input, key, fallback, 60).trim();
  if (!value) throw new Error(`${key} must not be blank`);
  return value;
}
function title(value: string): string {
  if (!value.trim() || /[\r\n]/.test(value) || value.length > 200)
    throw new Error("title must be 1-200 characters without newlines");
  return value.trim();
}
export function boardSlug(value: string): string {
  if (!/^[a-z0-9][a-z0-9-]{0,38}$/.test(value)) throw new Error("invalid board slug");
  return value;
}
function choice(value: string, values: readonly string[]): string {
  if (!values.includes(value)) throw new Error(`expected one of ${values.join(", ")}`);
  return value;
}
export function ttl(value: unknown = 1800): number {
  const match = /^(\d+)([smhd]?)$/.exec(String(value));
  const seconds = match
    ? Number(match[1]) * ({ "": 1, s: 1, m: 60, h: 3600, d: 86400 }[match[2]] ?? 1)
    : 0;
  if (!Number.isSafeInteger(seconds) || seconds < 1 || seconds > 2592000)
    throw new Error("ttl must be between 1 second and 30 days");
  return seconds;
}
function labels(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === "string" && item.trim() && item.length <= 40)
  )
    throw new Error("labels must be non-empty strings of at most 40 characters");
  return [...new Set(value.map((item: string) => item.trim()))].sort();
}
function optionalText(input: Input, key: string, max: number): string | null {
  return input[key] == null ? null : text(input, key, undefined, max);
}

const SCHEMA = `
CREATE TABLE boards (slug TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE cards (id TEXT PRIMARY KEY, board TEXT NOT NULL REFERENCES boards(slug), title TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo', priority TEXT NOT NULL DEFAULT 'normal',
  labels TEXT NOT NULL DEFAULT '[]', assignee TEXT, parent TEXT REFERENCES cards(id), linked TEXT,
  claimed_by TEXT, claim_expires_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX cards_board_status ON cards(board, status);
CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, card TEXT NOT NULL REFERENCES cards(id),
  kind TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE INDEX events_card ON events(card, id);
PRAGMA user_version=1;`;

export class Store {
  private constructor(
    readonly root: string,
    readonly db: DatabaseSync,
  ) {}

  static async open(explicit?: string, readOnly = false): Promise<Store> {
    const root = rootPath(explicit);
    await assertSafePath(root, { target: "directory", allowMissing: !readOnly });
    const path = join(root, "taskmatic.db");
    await assertSafePath(path, { target: "file", allowMissing: !readOnly });
    for (const suffix of ["-wal", "-shm", "-journal"])
      await assertSafePath(`${path}${suffix}`, { target: "file" });
    if (!readOnly) {
      await ensureDirectory(root, 0o700);
      await chmod(root, 0o700);
    }
    const db = new DatabaseSync(path, { readOnly });
    try {
      db.exec("PRAGMA busy_timeout=15000; PRAGMA foreign_keys=ON;");
      if (!readOnly) db.exec("PRAGMA journal_mode=WAL;");
      const store = new Store(root, db);
      const version = Number(db.prepare("PRAGMA user_version").get()!.user_version);
      if (version === 0 && !readOnly)
        store.transaction(() => {
          if (Number(db.prepare("PRAGMA user_version").get()!.user_version) === 0) db.exec(SCHEMA);
        });
      else if (version !== 1) throw new Error(`unsupported taskmatic database version ${version}`);
      if (!readOnly) await chmod(path, 0o600);
      return store;
    } catch (error) {
      db.close();
      throw error;
    }
  }
  close(): void {
    this.db.close();
  }
  transaction<T>(action: () => T): T {
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const result = action();
      this.db.exec("COMMIT");
      return result;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }
  private row(id: string): Row {
    if (!/^[0-9a-f]{8}$/.test(id)) throw new Error("invalid card id");
    const row = this.db.prepare("SELECT * FROM cards WHERE id=?").get(id);
    if (!row) throw new Error(`unknown card ${id}`);
    return row as Row;
  }
  private event(id: string, kind: string, actor: string, detail = ""): void {
    this.db
      .prepare("INSERT INTO events(card,kind,actor,at,detail) VALUES (?,?,?,?,?)")
      .run(id, kind, actor, iso(), detail);
  }
  private ensureBoard(slug: string, name = slug): void {
    this.db
      .prepare("INSERT OR IGNORE INTO boards(slug,title,created_at,updated_at) VALUES (?,?,?,?)")
      .run(boardSlug(slug), title(name), iso(), iso());
  }
  board(slug: string, name?: string): Board {
    this.transaction(() => this.ensureBoard(slug, name));
    return this.db
      .prepare("SELECT slug,title,created_at FROM boards WHERE slug=?")
      .get(slug) as Board;
  }
  read(id: string): Card {
    return this.payload(this.row(id));
  }
  private payload(row: Row): Card {
    const claimed = row.claimed_by as string | null;
    const expires = row.claim_expires_at as string | null;
    const remaining =
      claimed && expires
        ? Math.max(0, Math.trunc((Date.parse(expires) - Date.now()) / 1000))
        : null;
    return {
      id: String(row.id),
      board: boardSlug(String(row.board)),
      title: String(row.title),
      notes: String(row.notes),
      status: choice(String(row.status), STATUSES),
      priority: choice(String(row.priority), PRIORITIES),
      labels: JSON.parse(String(row.labels)) as string[],
      assignee: row.assignee as string | null,
      parent: row.parent as string | null,
      children: this.db
        .prepare("SELECT id FROM cards WHERE parent=? ORDER BY created_at")
        .all(row.id)
        .map((item) => String(item.id)),
      linked: row.linked as string | null,
      created_at: String(row.created_at),
      updated_at: String(row.updated_at),
      claimed_by: claimed,
      claim_expires_at: expires,
      claim_state: remaining === null ? null : remaining > 0 ? "held" : "expired",
      claim_remaining_seconds: remaining,
      activity: this.db
        .prepare("SELECT at,kind,actor,detail FROM events WHERE card=? ORDER BY id DESC LIMIT 20")
        .all(row.id) as Activity[],
    };
  }
  snapshot(): Snapshot {
    this.db.exec("BEGIN");
    try {
      const boards = this.db
        .prepare("SELECT slug,title,created_at FROM boards ORDER BY slug")
        .all() as Board[];
      const cards = (
        this.db.prepare("SELECT * FROM cards ORDER BY board,created_at").all() as Row[]
      ).map((row) => this.payload(row));
      cards.sort(
        (a, b) =>
          a.board.localeCompare(b.board) ||
          STATUSES.indexOf(a.status as (typeof STATUSES)[number]) -
            STATUSES.indexOf(b.status as (typeof STATUSES)[number]) ||
          PRIORITIES.indexOf(b.priority as (typeof PRIORITIES)[number]) -
            PRIORITIES.indexOf(a.priority as (typeof PRIORITIES)[number]) ||
          a.created_at.localeCompare(b.created_at),
      );
      this.db.exec("COMMIT");
      return { schema: "taskmatic/snapshot/v1", generated_at: iso(), boards, cards };
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
  }
  mutate(action: string, args: Input, defaultActor = "cli"): Card {
    const actor = identifier(args, "actor", defaultActor);
    return this.transaction(() => {
      if (action === "create") {
        const name = title(text(args, "title"));
        const board = boardSlug(text(args, "board", "main"));
        const priority = choice(text(args, "priority", "normal"), PRIORITIES);
        const parent = optionalText(args, "parent", 8);
        if (parent !== null) this.row(parent);
        this.ensureBoard(board);
        let id = "";
        for (let attempt = 0; attempt < 8; attempt++) {
          const candidate = randomBytes(4).toString("hex");
          if (!this.db.prepare("SELECT 1 FROM cards WHERE id=?").get(candidate)) {
            id = candidate;
            break;
          }
        }
        if (!id) throw new Error("could not allocate a unique card id");
        this.db
          .prepare(
            "INSERT INTO cards(id,board,title,notes,priority,labels,assignee,parent,linked,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          )
          .run(
            id,
            board,
            name,
            text(args, "notes", ""),
            priority,
            JSON.stringify(labels(args.labels ?? [])),
            optionalText(args, "assignee", 60),
            parent,
            optionalText(args, "linked", 500),
            iso(),
            iso(),
          );
        this.event(id, "created", actor, `status=todo priority=${priority}`);
        if (parent) this.event(id, "linked", actor, `parent=${parent}`);
        return this.read(id);
      }
      const id = text(args, "id");
      const card = this.read(id);
      if (action === "edit") {
        const changes: [string, SQLInputValue][] = [];
        if (args.title !== undefined) changes.push(["title", title(text(args, "title"))]);
        if (args.priority !== undefined)
          changes.push(["priority", choice(text(args, "priority"), PRIORITIES)]);
        if (args.labels !== undefined)
          changes.push(["labels", JSON.stringify(labels(args.labels))]);
        for (const [key, max] of [
          ["assignee", 60],
          ["linked", 500],
        ] as const)
          if (args[key] !== undefined) changes.push([key, optionalText(args, key, max)]);
        if (args.notes !== undefined) changes.push(["notes", text(args, "notes")]);
        if (!changes.length) throw new Error("edit requires at least one field");
        this.db
          .prepare(
            `UPDATE cards SET ${changes.map(([key]) => `${key}=?`).join(",")},updated_at=? WHERE id=?`,
          )
          .run(...changes.map(([, value]) => value), iso(), id);
        this.event(id, "edited", actor, changes.map(([key]) => key).join(", "));
      } else if (action === "move" || action === "complete") {
        const status = action === "complete" ? "done" : choice(text(args, "status"), STATUSES);
        if (action === "complete") {
          if (card.claimed_by) this.event(id, "release", card.claimed_by);
          this.db
            .prepare("UPDATE cards SET claimed_by=NULL,claim_expires_at=NULL WHERE id=?")
            .run(id);
        }
        this.db.prepare("UPDATE cards SET status=?,updated_at=? WHERE id=?").run(status, iso(), id);
        this.event(id, "status", actor, `${card.status} -> ${status}`);
      } else if (["claim", "heartbeat", "release"].includes(action)) {
        const agent = identifier(args, "agent");
        if (action === "heartbeat" && (card.claimed_by !== agent || card.claim_state !== "held"))
          throw new Error(`card ${id} is not held by ${agent}`);
        if (card.claim_state === "held" && card.claimed_by !== agent)
          throw new Error(`card ${id} is claimed by ${card.claimed_by}`);
        if (action === "release") {
          this.db
            .prepare(
              "UPDATE cards SET claimed_by=NULL,claim_expires_at=NULL,updated_at=? WHERE id=?",
            )
            .run(iso(), id);
          this.event(id, "release", agent);
        } else {
          const seconds = ttl(args.ttl_seconds);
          const expires = iso(Date.now() + seconds * 1000);
          if (action === "heartbeat")
            this.db.prepare("UPDATE cards SET claim_expires_at=? WHERE id=?").run(expires, id);
          else {
            this.db
              .prepare(
                "UPDATE cards SET claimed_by=?,claim_expires_at=?,status=?,updated_at=? WHERE id=?",
              )
              .run(agent, expires, card.status === "todo" ? "doing" : card.status, iso(), id);
            this.event(id, "claim", agent, `ttl=${seconds}s`);
          }
        }
      } else if (action === "note") {
        const note = text(args, "text").trim();
        if (!note) throw new Error("note text must not be empty");
        this.event(id, "note", actor, note);
        this.db.prepare("UPDATE cards SET updated_at=? WHERE id=?").run(iso(), id);
      } else throw new Error(`unknown action ${action}`);
      return this.read(id);
    });
  }
}

export function filterCards(snapshot: Snapshot, filters: Input): Card[] {
  return snapshot.cards.filter(
    (card) =>
      ["board", "status", "assignee"].every(
        (key) =>
          filters[key] === undefined ||
          card[key as "board" | "status" | "assignee"] === filters[key],
      ) &&
      (filters.label === undefined || card.labels.includes(String(filters.label))),
  );
}
