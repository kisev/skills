import { homedir } from "node:os";
import { isAbsolute, join } from "node:path";

export function opencodeDatabasePath(): string {
  const base = process.env.XDG_DATA_HOME ?? join(homedir(), ".local/share");
  if (!isAbsolute(base)) throw new Error("XDG_DATA_HOME must be an absolute path");
  if (process.env.OPENCODE_DB) {
    if (process.env.OPENCODE_DB === ":memory:")
      throw new Error("An in-memory OpenCode database cannot be ingested from another process");
    return isAbsolute(process.env.OPENCODE_DB)
      ? process.env.OPENCODE_DB
      : join(base, "opencode", process.env.OPENCODE_DB);
  }
  return join(base, "opencode", "opencode.db");
}
