import { homedir } from "node:os";
import { isAbsolute, join } from "node:path";

export function opencodeDatabasePath(): string {
  const base = process.env.XDG_DATA_HOME ?? join(homedir(), ".local/share");
  if (!isAbsolute(base)) throw new Error("XDG_DATA_HOME must be an absolute path");
  return join(base, "opencode", "opencode.db");
}
