import { createHash } from "node:crypto";
import { mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

export type EntryKind = "curated" | "user" | "episodic";

export type IndexedEntry = {
  stableId: string;
  file: string;
  line: number;
  kind: EntryKind;
  key: string | null;
  text: string;
  trigger: string[];
  importance: number;
  pinned: boolean;
  project: string | null;
  origin: "user" | "agent" | null;
  observedAt: number | null;
  status: "active" | null;
};

export type VectorRow = { stableId: string; dim: number; data: Float32Array };

export function stableIdFor(file: string, text: string, key: string | null): string {
  if (key) return `key:${key}`;
  return `sha:${createHash("sha256").update(`${file}\n${text}`).digest("hex").slice(0, 24)}`;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS entries (
  stable_id TEXT PRIMARY KEY,
  file TEXT NOT NULL,
  line INTEGER NOT NULL,
  kind TEXT NOT NULL,
  key TEXT,
  text TEXT NOT NULL,
  trigger_phrases TEXT NOT NULL DEFAULT '[]',
  importance INTEGER NOT NULL DEFAULT 5,
  pinned INTEGER NOT NULL DEFAULT 0,
  project TEXT,
  origin TEXT,
  observed_at INTEGER,
  status TEXT
);
CREATE TABLE IF NOT EXISTS usage (
  stable_id TEXT PRIMARY KEY,
  surfaced INTEGER NOT NULL DEFAULT 0,
  useful INTEGER NOT NULL DEFAULT 0,
  queries TEXT NOT NULL DEFAULT '[]',
  days TEXT NOT NULL DEFAULT '[]',
  last_useful_at INTEGER
);
CREATE TABLE IF NOT EXISTS vectors (
  stable_id TEXT PRIMARY KEY,
  dim INTEGER NOT NULL,
  data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
`;

export class MemoryStore {
  readonly db: DatabaseSync;
  private readonly fts: boolean;

  private constructor(indexFile: string) {
    this.db = new DatabaseSync(indexFile);
    this.db.exec("PRAGMA journal_mode = WAL;");
    this.db.exec(SCHEMA);
    this.fts = this.ensureFts();
  }

  static async open(indexFile: string): Promise<MemoryStore> {
    await mkdir(dirname(indexFile), { mode: 0o700, recursive: true });
    return new MemoryStore(indexFile);
  }

  private ensureFts(): boolean {
    try {
      this.db.exec(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(stable_id UNINDEXED, text);",
      );
      return true;
    } catch {
      return false;
    }
  }

  hasFts(): boolean {
    return this.fts;
  }

  replaceEntries(entries: IndexedEntry[]): void {
    this.db.exec("BEGIN IMMEDIATE;");
    try {
      this.db.exec("DELETE FROM entries;");
      if (this.fts) this.db.exec("DELETE FROM entries_fts;");
      const seen = new Set<string>();
      for (const entry of entries) {
        if (seen.has(entry.stableId)) continue;
        seen.add(entry.stableId);
        this.db
          .prepare(
            `INSERT INTO entries (stable_id, file, line, kind, key, text, trigger_phrases, importance, pinned, project, origin, observed_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          )
          .run(
            entry.stableId,
            entry.file,
            entry.line,
            entry.kind,
            entry.key,
            entry.text,
            JSON.stringify(entry.trigger),
            entry.importance,
            entry.pinned ? 1 : 0,
            entry.project,
            entry.origin,
            entry.observedAt,
            entry.status,
          );
        if (this.fts)
          this.db
            .prepare("INSERT INTO entries_fts (stable_id, text) VALUES (?, ?);")
            .run(entry.stableId, entry.text);
      }
      this.db.exec("DELETE FROM usage WHERE stable_id NOT IN (SELECT stable_id FROM entries);");
      this.db.exec("DELETE FROM vectors WHERE stable_id NOT IN (SELECT stable_id FROM entries);");
      this.db.exec("COMMIT;");
    } catch (error) {
      this.db.exec("ROLLBACK;");
      throw error;
    }
  }

  allEntries(): IndexedEntry[] {
    return this.db
      .prepare(
        "SELECT stable_id, file, line, kind, key, text, trigger_phrases, importance, pinned, project, origin, observed_at, status FROM entries ORDER BY observed_at ASC",
      )
      .all()
      .map((row) => {
        const value = row as Record<string, unknown>;
        return {
          stableId: value.stable_id as string,
          file: value.file as string,
          line: value.line as number,
          kind: value.kind as EntryKind,
          key: (value.key as string | null) ?? null,
          text: value.text as string,
          trigger: JSON.parse(value.trigger_phrases as string) as string[],
          importance: value.importance as number,
          pinned: value.pinned === 1,
          project: (value.project as string | null) ?? null,
          origin: (value.origin as "user" | "agent" | null) ?? null,
          observedAt: (value.observed_at as number | null) ?? null,
          status: (value.status as "active" | null) ?? null,
        };
      });
  }

  ftsSearch(query: string, limit: number): Map<string, number> {
    if (!this.fts) return new Map();
    const tokens = query
      .toLowerCase()
      .split(/[^\p{L}\p{N}]+/u)
      .filter((token) => token.length >= 2)
      .slice(0, 12);
    if (!tokens.length) return new Map();
    const pattern = tokens.map((token) => `"${token.replace(/"/g, "")}"*`).join(" OR ");
    const rows = this.db
      .prepare(
        `SELECT stable_id, rank FROM entries_fts WHERE entries_fts MATCH ? ORDER BY rank LIMIT ?;`,
      )
      .all(pattern, limit) as Array<{ stable_id: string; rank: number }>;
    const result = new Map<string, number>();
    for (const row of rows) {
      const quality = -row.rank;
      const score = quality <= 0 ? 0.1 : Math.min(1, 0.5 + quality * 0.25);
      result.set(row.stable_id, score);
    }
    return result;
  }

  markSurfaced(stableIds: string[], query: string, now = Date.now()): void {
    const queryHash = createHash("sha256").update(query.toLowerCase()).digest("hex").slice(0, 16);
    const day = new Date(now).toISOString().slice(0, 10);
    const read = this.db.prepare("SELECT queries, days FROM usage WHERE stable_id = ?;");
    const upsert = this.db.prepare(
      `INSERT INTO usage (stable_id, surfaced, useful, queries, days) VALUES (?, 1, 0, ?, ?)
      ON CONFLICT(stable_id) DO UPDATE SET
        surfaced = usage.surfaced + 1,
        queries = excluded.queries,
        days = excluded.days;`,
    );
    for (const stableId of stableIds) {
      const row = read.get(stableId) as { queries: string; days: string } | undefined;
      const queries = row ? (JSON.parse(row.queries) as string[]) : [];
      const days = row ? (JSON.parse(row.days) as string[]) : [];
      if (!queries.includes(queryHash) && queries.length < 32) queries.push(queryHash);
      if (!days.includes(day)) days.push(day);
      upsert.run(stableId, JSON.stringify(queries), JSON.stringify(days));
    }
  }

  markUseful(stableIds: string[], now = Date.now()): void {
    const statement = this.db.prepare(
      `INSERT INTO usage (stable_id, useful, last_useful_at) VALUES (?, 1, ?)
      ON CONFLICT(stable_id) DO UPDATE SET useful = useful + 1, last_useful_at = ?;`,
    );
    for (const stableId of stableIds) statement.run(stableId, now, now);
  }

  usageFor(stableId: string): {
    surfaced: number;
    useful: number;
    queries: string[];
    days: string[];
    lastUsefulAt: number | null;
  } {
    const row = this.db.prepare("SELECT * FROM usage WHERE stable_id = ?").get(stableId) as
      | Record<string, unknown>
      | undefined;
    if (!row) return { surfaced: 0, useful: 0, queries: [], days: [], lastUsefulAt: null };
    return {
      surfaced: row.surfaced as number,
      useful: row.useful as number,
      queries: JSON.parse(row.queries as string) as string[],
      days: JSON.parse(row.days as string) as string[],
      lastUsefulAt: (row.last_useful_at as number | null) ?? null,
    };
  }

  setVector(stableId: string, vector: Float32Array): void {
    this.db
      .prepare(
        `INSERT INTO vectors (stable_id, dim, data) VALUES (?, ?, ?)
        ON CONFLICT(stable_id) DO UPDATE SET dim = excluded.dim, data = excluded.data;`,
      )
      .run(
        stableId,
        vector.length,
        Buffer.from(vector.buffer, vector.byteOffset, vector.byteLength),
      );
  }

  vectors(): VectorRow[] {
    return (
      this.db.prepare("SELECT stable_id, dim, data FROM vectors").all() as Array<{
        stable_id: string;
        dim: number;
        data: Uint8Array;
      }>
    ).map((row) => ({
      stableId: row.stable_id,
      dim: row.dim,
      data: new Float32Array(
        row.data.buffer.slice(row.data.byteOffset, row.data.byteOffset + row.data.byteLength),
      ),
    }));
  }

  getMeta(key: string): string | null {
    const row = this.db.prepare("SELECT value FROM meta WHERE key = ?").get(key) as
      | { value: string }
      | undefined;
    return row?.value ?? null;
  }

  setMeta(key: string, value: string): void {
    this.db
      .prepare(
        `INSERT INTO meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value;`,
      )
      .run(key, value);
  }

  close(): void {
    this.db.close();
  }
}

export function cosineSimilarity(left: Float32Array, right: Float32Array): number {
  const length = Math.min(left.length, right.length);
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < length; index += 1) {
    dot += left[index] * right[index];
    leftNorm += left[index] * left[index];
    rightNorm += right[index] * right[index];
  }
  if (!leftNorm || !rightNorm) return 0;
  return dot / (Math.sqrt(leftNorm) * Math.sqrt(rightNorm));
}
