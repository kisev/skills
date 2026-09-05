import { createHash, randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, rename, readdir, unlink } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

function home(value = process.env.HOME ?? homedir()): string {
  if (!isAbsolute(value) || value.split(sep).includes("..")) throw new Error("HOME must be an absolute safe path");
  return resolve(value);
}

function inside(root: string, target: string): boolean {
  const value = relative(root, target);
  return value === "" || (!value.startsWith(`..${sep}`) && value !== "..");
}

export function stateRoot(name: string, homePath?: string): string {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) throw new Error("unsafe state name");
  const base = process.env.XDG_STATE_HOME ? resolve(process.env.XDG_STATE_HOME) : join(home(homePath), ".local", "state");
  return join(base, "opencode", "skills", name);
}

export function configRoot(name: string, homePath?: string): string {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) throw new Error("unsafe config name");
  const base = process.env.XDG_CONFIG_HOME ? resolve(process.env.XDG_CONFIG_HOME) : join(home(homePath), ".config");
  return join(base, "opencode", "skill-config", name);
}

async function safeDirectory(path: string, boundary: string, create = false): Promise<void> {
  const target = resolve(path);
  if (!inside(boundary, target)) throw new Error("state path escapes its boundary");
  try {
    const info = await lstat(boundary);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("state directory is unsafe");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
  }
  if (create) await mkdir(target, { recursive: true, mode: 0o700 });
  const rootInfo = await lstat(boundary);
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) throw new Error("state directory is unsafe");
  let current = resolve(boundary);
  for (const piece of relative(current, target).split(sep).filter(Boolean)) {
    current = join(current, piece);
    const info = await lstat(current);
    if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("state directory is unsafe");
  }
}

export async function readState<T>(path: string, boundary: string): Promise<T | undefined> {
  if (!inside(boundary, path)) throw new Error("state path escapes its boundary");
  try {
    await safeDirectory(dirname(path), boundary);
    const info = await lstat(path);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error("state file is unsafe");
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function listState(boundary: string, suffix = ".json"): Promise<string[]> {
  try {
    await safeDirectory(boundary, boundary);
    return (await readdir(boundary)).filter((name) => name.endsWith(suffix)).sort();
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
}

export async function writeState(path: string, boundary: string, value: unknown): Promise<void> {
  if (!inside(boundary, path)) throw new Error("state path escapes its boundary");
  await safeDirectory(dirname(path), boundary, true);
  const temporary = join(dirname(path), `.${randomUUID()}.tmp`);
  const handle = await open(temporary, "wx", 0o600);
  try {
    await handle.writeFile(`${JSON.stringify(value)}\n`, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    try {
      const previous = await lstat(path);
      if (!previous.isFile() || previous.isSymbolicLink()) throw new Error("state file is unsafe");
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    await rename(temporary, path);
  } finally {
    await unlink(temporary).catch(() => undefined);
  }
}

export async function appendState(path: string, boundary: string, value: unknown): Promise<void> {
  if (!inside(boundary, path)) throw new Error("state path escapes its boundary");
  await safeDirectory(dirname(path), boundary, true);
  const handle = await open(path, "a", 0o600);
  try {
    const info = await handle.stat();
    if (!info.isFile()) throw new Error("state file is unsafe");
    await handle.writeFile(`${JSON.stringify(value)}\n`, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
}

export function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");
}
