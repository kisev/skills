import { lstat } from "node:fs/promises";
import { homedir } from "node:os";
import { isAbsolute, join, resolve, sep } from "node:path";

export type MemomaticPaths = {
  stateRoot: string;
  configRoot: string;
  memoryFile: string;
  userFile: string;
  dreamsFile: string;
  rulesFile: string;
  settingsFile: string;
  dailyDir: string;
  archiveDir: string;
  historyDir: string;
  indexFile: string;
};

function safeXdg(name: string, fallback: string): string {
  const configured = process.env[name];
  if (configured) {
    if (!isAbsolute(configured) || configured.split(sep).includes(".."))
      throw new Error(`${name} must be an absolute safe path`);
    return resolve(configured);
  }
  const home = process.env.HOME ?? homedir();
  if (!isAbsolute(home) || home.split(sep).includes(".."))
    throw new Error("HOME must be an absolute safe path");
  return join(resolve(home), fallback);
}

async function assertDirectory(path: string): Promise<void> {
  try {
    const info = await lstat(path);
    if (!info.isDirectory() || info.isSymbolicLink())
      throw new Error(`memomatic directory is unsafe: ${path}`);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
}

export function memomaticPaths(): MemomaticPaths {
  const stateRoot = join(safeXdg("XDG_STATE_HOME", ".local/state"), "memomatic");
  const configRoot = join(safeXdg("XDG_CONFIG_HOME", ".config"), "memomatic");
  return {
    stateRoot,
    configRoot,
    memoryFile: join(stateRoot, "MEMORY.md"),
    userFile: join(stateRoot, "USER.md"),
    dreamsFile: join(stateRoot, "DREAMS.md"),
    rulesFile: join(configRoot, "MEMORY_RULES.md"),
    settingsFile: join(configRoot, "settings.json"),
    dailyDir: join(stateRoot, "memory"),
    archiveDir: join(stateRoot, "archive"),
    historyDir: join(stateRoot, "history"),
    indexFile: join(stateRoot, "index.sqlite"),
  };
}

export async function verifyMemomaticRoots(paths: MemomaticPaths): Promise<void> {
  await assertDirectory(paths.stateRoot);
  await assertDirectory(paths.configRoot);
}
