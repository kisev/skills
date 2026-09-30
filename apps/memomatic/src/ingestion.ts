import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import type { MemoryStore } from "./store.js";

export type Fragment = {
  id: string;
  sessionId: string;
  messageIds: string[];
  title: string;
  directory: string;
  text: string;
  context: string;
  checkpointKeys: string[];
  seal?: [string, string];
};
export type IngestionPlan = {
  fragments: Fragment[];
  sessions: number;
  messages: number;
  cached: number;
  skipped: number;
  characters: number;
  watermark: number;
  cachedSessions: number;
  unscannedSessions: number;
  seals: Array<[string, string]>;
};
const digest = (text: string) => createHash("sha256").update(text).digest("hex");

export function planIngestion(
  file: string,
  store: MemoryStore,
  options: { before: number; maxChars: number; maxSessions?: number; contextChars?: number },
): IngestionPlan {
  if (
    !Number.isSafeInteger(options.maxChars) ||
    options.maxChars < 2 ||
    !Number.isFinite(options.before)
  )
    throw new Error("invalid ingestion limits");
  const result: IngestionPlan = {
    fragments: [],
    sessions: 0,
    messages: 0,
    cached: 0,
    skipped: 0,
    characters: 0,
    watermark: 0,
    cachedSessions: 0,
    unscannedSessions: 0,
    seals: [],
  };
  const db = new DatabaseSync(file, { readOnly: true });
  try {
    db.exec("BEGIN");
    const required: Record<string, string[]> = {
      session_v2: ["id", "title", "directory", "time_created", "time_updated"],
      session_message: ["id", "session_id", "type", "seq", "data", "time_created", "time_updated"],
    };
    for (const [table, fields] of Object.entries(required)) {
      const columns = new Set(
        db
          .prepare(`PRAGMA table_info(${table})`)
          .all()
          .map((row) => row.name),
      );
      if (!fields.every((field) => columns.has(field)))
        throw new Error(
          "OpenCode V2 session projections are unavailable; start V2 to migrate history before ingestion",
        );
    }
    const sessions = db
      .prepare(
        "SELECT id,COALESCE(title,'') AS title,directory,time_created,time_updated AS revision FROM session_v2 WHERE time_updated < ? ORDER BY time_created,id",
      )
      .all(options.before) as Array<{
      id: string;
      title: string;
      directory: string;
      time_created: number;
      revision: number;
    }>;
    for (const [position, session] of sessions.entries()) {
      if (session.title.startsWith("[memomatic-internal]")) {
        result.skipped++;
        continue;
      }
      const sealKey = `ingest-session-v2:${digest(session.id)}`;
      let seal: [string, string] | undefined;
      {
        const revisions = db
          .prepare(
            "SELECT id,seq,time_updated FROM session_message WHERE session_id=? ORDER BY seq,id",
          )
          .all(session.id);
        if (revisions.some((message) => Number(message.time_updated) >= options.before)) {
          result.skipped++;
          continue;
        }
        const revision = digest(
          JSON.stringify([session.revision, session.title, session.directory, revisions]),
        );
        if (store.getMeta(sealKey) === revision) {
          result.cachedSessions++;
          continue;
        }
        seal = [sealKey, revision];
      }
      const rows = db
        .prepare(`
        SELECT id,type AS role,json_extract(data,'$.text') AS text,seq,0 AS part_index
        FROM session_message WHERE session_id=? AND type='user'
          AND CASE WHEN json_valid(data) THEN json_type(data,'$.text') END='text'
        UNION ALL
        SELECT m.id,m.type AS role,json_extract(p.value,'$.text') AS text,m.seq,CAST(p.key AS INTEGER) AS part_index
        FROM session_message m JOIN json_each(CASE WHEN json_valid(m.data) THEN json_extract(m.data,'$.content') ELSE '[]' END) p
        WHERE m.session_id=? AND m.type='assistant'
          AND CASE WHEN json_valid(p.value) THEN json_extract(p.value,'$.type') END='text'
          AND CASE WHEN json_valid(p.value) THEN json_type(p.value,'$.text') END='text'
        ORDER BY seq,part_index
      `)
        .all(session.id, session.id) as Array<{ id: string; role: string; text: string }>;
      const messages = new Map<string, { role: string; texts: string[] }>();
      for (const row of rows) {
        const item = messages.get(row.id) ?? { role: row.role, texts: [] };
        item.texts.push(row.text);
        messages.set(row.id, item);
      }
      const firstUser = [...messages.values()].find((message) => message.role === "user");
      if (firstUser?.texts.join("\n").trimStart().startsWith("[memomatic-internal]")) {
        result.skipped++;
        continue;
      }
      let batch: string[] = [];
      let ids: string[] = [];
      let keys: string[] = [];
      let context = "";
      let previous = "";
      let length = 0;
      let changed = false;
      const flush = () => {
        if (!batch.length) return;
        result.fragments.push({
          id: digest(keys.join("\n")),
          sessionId: session.id,
          messageIds: ids,
          title: session.title,
          directory: session.directory,
          text: batch.join("\n\n"),
          context,
          checkpointKeys: keys,
        });
        batch = [];
        ids = [];
        keys = [];
        length = 0;
      };
      let lastMessage = "";
      for (const [id, message] of messages) {
        const body = message.texts.join("\n").trim();
        if (!body) {
          result.skipped++;
          continue;
        }
        result.messages++;
        const full = `${message.role}: ${body}`;
        // Only adjacent exact duplicate messages with the same role are redundant.
        if (full === lastMessage) {
          result.skipped++;
          continue;
        }
        lastMessage = full;
        for (let offset = 0; offset < body.length;) {
          const start = offset;
          let end = Math.min(body.length, offset + options.maxChars);
          if (
            end < body.length &&
            /[\uD800-\uDBFF]/.test(body[end - 1]) &&
            /[\uDC00-\uDFFF]/.test(body[end])
          )
            end--;
          const text = `${message.role}: ${body.slice(start, end)}`;
          offset = end;
          const preceding = Array.from(previous)
            .slice(-(options.contextChars ?? 2000))
            .join("");
          const key = `ingest-v2:${digest(`${session.id}\n${id}\n${start}\n${preceding}\n${text}`)}`;
          if (store.getMeta(key)) {
            result.cached++;
            previous = text;
            continue;
          }
          if (batch.length && length + text.length > options.maxChars) flush();
          if (!batch.length) context = preceding;
          batch.push(text);
          ids.push(id);
          keys.push(key);
          length += text.length;
          result.characters += text.length;
          changed = true;
          previous = text;
        }
      }
      flush();
      if (seal) {
        if (changed) result.fragments.at(-1)!.seal = seal;
        else result.seals.push(seal);
      }
      if (changed) {
        result.sessions++;
        result.watermark = Math.max(result.watermark, session.time_created);
      }
      if (options.maxSessions && result.sessions >= options.maxSessions) {
        result.unscannedSessions = sessions.length - position - 1;
        break;
      }
    }
    db.exec("COMMIT");
    return result;
  } finally {
    db.close();
  }
}
