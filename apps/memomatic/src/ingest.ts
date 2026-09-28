import { homedir } from "node:os";
import { isAbsolute, join } from "node:path";
import { DatabaseSync } from "node:sqlite";

export type IngestSession = {
  id: string;
  title: string;
  directory: string;
  timeCreated: number;
  messages: Array<{ role: string; text: string }>;
};

export function opencodeDatabasePath(): string {
  const base = process.env.XDG_DATA_HOME
    ? process.env.XDG_DATA_HOME
    : join(homedir(), ".local", "share");
  if (!isAbsolute(base)) throw new Error("XDG_DATA_HOME must be an absolute path");
  return join(base, "opencode", "opencode.db");
}

export type SessionFacts = {
  directory: string | null;
  title: string | null;
  firstMessage: string | null;
};

/**
 * Resolve session context for the bootstrap block: working directory, title,
 * and the first user message, read-only from the OpenCode database. Returns
 * nulls when the session or database is unavailable.
 */
export function sessionFacts(databaseFile: string, sessionId: string): SessionFacts {
  let db: DatabaseSync;
  try {
    db = new DatabaseSync(databaseFile, { readOnly: true });
  } catch {
    return { directory: null, title: null, firstMessage: null };
  }
  try {
    const session = db
      .prepare("SELECT directory, title FROM session WHERE id = ?;")
      .get(sessionId) as { directory?: string; title?: string } | undefined;
    let firstMessage: string | null = null;
    const rows = readMessages(db, sessionId, 20);
    for (const row of rows) {
      try {
        const parsed = JSON.parse(row.data) as { role?: string; parts?: unknown[] };
        if (parsed.role !== "user") continue;
        const texts: string[] = [];
        for (const part of parsed.parts ?? []) {
          const value = part as { type?: string; text?: string };
          if (value.type === "text" && typeof value.text === "string") texts.push(value.text);
        }
        const text = texts.join("\n").trim();
        if (text) {
          firstMessage = text;
          break;
        }
      } catch {
        continue;
      }
    }
    return {
      directory: session?.directory ?? null,
      title: session?.title ?? null,
      firstMessage,
    };
  } catch {
    return { directory: null, title: null, firstMessage: null };
  } finally {
    db.close();
  }
}

type RawMessage = { data: string; id?: string };

function readMessages(db: DatabaseSync, sessionId: string, limit = -1): RawMessage[] {
  const hasParts = db
    .prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'part'")
    .get();
  const rows = db
    .prepare(
      `SELECT ${hasParts ? "id, " : ""}data FROM message WHERE session_id = ? ORDER BY time_created ASC LIMIT ?;`,
    )
    .all(sessionId, limit) as RawMessage[];
  if (!hasParts) return rows;
  const parts = db.prepare(
    "SELECT data FROM part WHERE message_id = ? ORDER BY time_created ASC, id ASC",
  );
  return rows.map((row) => {
    try {
      const message = JSON.parse(row.data) as { parts?: unknown[] };
      message.parts = (parts.all(row.id!) as RawMessage[]).flatMap((part) => {
        try {
          return [JSON.parse(part.data) as unknown];
        } catch {
          return [];
        }
      });
      return { data: JSON.stringify(message) };
    } catch {
      return row;
    }
  });
}

export function loadRecentSessions(
  databaseFile: string,
  afterTimeCreated: number,
  options: { maxSessions: number; maxCharsPerSession: number; before?: number } = {
    maxSessions: 20,
    maxCharsPerSession: 24_000,
  },
): IngestSession[] {
  let db: DatabaseSync;
  try {
    db = new DatabaseSync(databaseFile, { readOnly: true });
  } catch {
    return [];
  }
  try {
    const before = options.before ?? Number.MAX_SAFE_INTEGER;
    const sessions = db
      .prepare(
        `SELECT id, title, directory, time_created FROM session
        WHERE time_created > ? AND time_created < ? ORDER BY time_created ASC LIMIT ?;`,
      )
      .all(afterTimeCreated, before, options.maxSessions) as Array<{
      id: string;
      title: string;
      directory: string;
      time_created: number;
    }>;
    const result: IngestSession[] = [];
    for (const session of sessions) {
      const messages: Array<{ role: string; text: string }> = [];
      let budget = options.maxCharsPerSession;
      let internal = false;
      const rows = readMessages(db, session.id);
      for (const row of rows) {
        if (budget <= 0) break;
        let parsed: { role?: string; parts?: unknown[] };
        try {
          parsed = JSON.parse(row.data);
        } catch {
          continue;
        }
        const texts: string[] = [];
        for (const part of parsed.parts ?? []) {
          const value = part as { type?: string; text?: string };
          if (value.type === "text" && typeof value.text === "string") texts.push(value.text);
        }
        const text = texts.join("\n").trim();
        if (!text) continue;
        if (text.includes("[memomatic-internal]")) internal = true;
        if (budget - text.length < 0) {
          messages.push({ role: parsed.role ?? "unknown", text: text.slice(0, budget) });
          budget = 0;
          break;
        }
        budget -= text.length;
        messages.push({ role: parsed.role ?? "unknown", text });
      }
      if (internal || !messages.length) continue;
      result.push({
        id: session.id,
        title: session.title,
        directory: session.directory,
        timeCreated: session.time_created,
        messages,
      });
    }
    return result;
  } finally {
    db.close();
  }
}
