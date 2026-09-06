import { createHash } from "node:crypto";
import { lstat, mkdir, readFile, readdir } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

import { appendPrivate, writeAtomic } from "../lifecycle.js";

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
  if (create) {
    let current = resolve(target).startsWith(sep) ? sep : "";
    for (const piece of resolve(target).split(sep).filter(Boolean)) {
      current = join(current, piece);
      try {
        const info = await lstat(current);
        if (!info.isDirectory() || info.isSymbolicLink()) throw new Error("state directory is unsafe");
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
        await mkdir(current, { mode: 0o700 });
      }
    }
  }
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
  await writeAtomic(path, Buffer.from(`${JSON.stringify(value)}\n`), 0o600);
}

export async function appendState(path: string, boundary: string, value: unknown): Promise<void> {
  if (!inside(boundary, path)) throw new Error("state path escapes its boundary");
  await safeDirectory(dirname(path), boundary, true);
  await appendPrivate(path, value);
}

export function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value), "utf8").digest("hex");
}
