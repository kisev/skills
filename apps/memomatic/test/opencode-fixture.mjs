export function createSessionTables(db) {
  db.exec(`
    CREATE TABLE session_v2(id TEXT PRIMARY KEY,title TEXT,directory TEXT,time_created INTEGER,time_updated INTEGER);
    CREATE TABLE session_message(id TEXT PRIMARY KEY,session_id TEXT,type TEXT,seq INTEGER,data TEXT,time_created INTEGER,time_updated INTEGER);
  `);
}

export function insertMessage(db, id, session, type, text, seq, updated = seq) {
  const data = type === "user" ? { text } : { content: [{ type: "text", text }] };
  db.prepare("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)").run(
    id,
    session,
    type,
    seq,
    JSON.stringify(data),
    seq,
    updated,
  );
}
