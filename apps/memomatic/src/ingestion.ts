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
    const hasParts = Boolean(
      db.prepare("SELECT 1 FROM sqlite_master WHERE name='part' AND type='table'").get(),
    );
    const hasUpdated = db
      .prepare("PRAGMA table_info(session)")
      .all()
      .some((row) => row.name === "time_updated");
    const fastRevision =
      hasParts &&
      hasUpdated &&
      ["message", "part"].every((table) =>
        db
          .prepare(`PRAGMA table_info(${table})`)
          .all()
          .some((row) => row.name === "time_updated"),
      );
    const partHasSession =
      hasParts &&
      db
        .prepare("PRAGMA table_info(part)")
        .all()
        .some((row) => row.name === "session_id");
    const sessions = db
      .prepare(
        `SELECT id,title,directory,time_created,${hasUpdated ? "time_updated" : "time_created"} AS revision FROM session WHERE ${hasUpdated ? "time_updated" : "time_created"} < ? ORDER BY time_created,id`,
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
      if (fastRevision) {
        const messages = db
          .prepare(
            "SELECT COUNT(*) AS count,MAX(time_updated) AS updated FROM message WHERE session_id=?",
          )
          .get(session.id)!;
        const parts = db
          .prepare(
            `SELECT COUNT(*) AS count,MAX(time_updated) AS updated FROM part WHERE ${partHasSession ? "session_id=?" : "message_id IN (SELECT id FROM message WHERE session_id=?)"}`,
          )
          .get(session.id)!;
        if (Math.max(Number(messages.updated), Number(parts.updated)) >= options.before) {
          result.skipped++;
          continue;
        }
        const revision = digest(
          JSON.stringify([session.revision, session.title, session.directory, messages, parts]),
        );
        if (store.getMeta(sealKey) === revision) {
          result.cachedSessions++;
          continue;
        }
        seal = [sealKey, revision];
      }
      const rows = hasParts
        ? (db
            .prepare(
              `SELECT m.id,m.data AS message,p.data AS part FROM message m JOIN part p ON p.message_id=m.id
                WHERE ${partHasSession ? "p" : "m"}.session_id=?
                AND CASE WHEN json_valid(p.data) THEN json_extract(p.data,'$.type') END='text'
                AND CASE WHEN json_valid(m.data) THEN json_extract(m.data,'$.role') END IN ('user','assistant')
                ORDER BY m.time_created,m.id,p.time_created,p.id`,
            )
            .all(session.id) as Array<{ id: string; message: string; part: string }>)
        : (
            db
              .prepare(
                "SELECT rowid AS id,data FROM message WHERE session_id=? ORDER BY time_created,rowid",
              )
              .all(session.id) as Array<{ id: number; data: string }>
          ).flatMap((row) => {
            try {
              const message = JSON.parse(row.data);
              return (message.parts ?? []).map((part: unknown) => ({
                id: String(row.id),
                message: row.data,
                part: JSON.stringify(part),
              }));
            } catch {
              return [];
            }
          });
      const messages = new Map<string, { role: string; texts: string[] }>();
      for (const row of rows) {
        try {
          const message = JSON.parse(row.message);
          const part = JSON.parse(row.part);
          if (
            !["user", "assistant"].includes(message.role) ||
            part.type !== "text" ||
            typeof part.text !== "string"
          )
            continue;
          const item: { role: string; texts: string[] } = messages.get(row.id) ?? {
            role: message.role,
            texts: [],
          };
          item.texts.push(part.text);
          messages.set(row.id, item);
        } catch {
          result.skipped++;
        }
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
