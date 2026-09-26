import { createHash } from "node:crypto";
import { lstat, mkdir, open, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, relative } from "node:path";

import { writeAtomic } from "../lifecycle.js";
import { type CorpusEntry, parseEntryLine } from "./entries.js";
import type { MemomaticPaths } from "./paths.js";

const CURATED_FILES = ["MEMORY.md", "USER.md"] as const;

function inside(root: string, target: string): boolean {
  const value = relative(root, target);
  return value === "" || (!value.startsWith("..") && value !== "..");
}

async function safeDirectory(path: string, boundary: string, create: boolean): Promise<void> {
  if (!inside(boundary, path)) throw new Error("memomatic path escapes its root");
  if (create) await mkdir(path, { mode: 0o700, recursive: true });
  let current = boundary;
  for (const piece of relative(current, path).split("/").filter(Boolean)) {
    current = join(current, piece);
    const info = await lstat(current);
    if (!info.isDirectory() || info.isSymbolicLink())
      throw new Error(`memomatic directory is unsafe: ${current}`);
  }
}

async function writePreImage(
  paths: MemomaticPaths,
  source: string,
  previous: Buffer,
): Promise<void> {
  await safeDirectory(paths.historyDir, paths.stateRoot, true);
  const name = `${createHash("sha256").update(previous).digest("hex")}.md`;
  const target = join(paths.historyDir, name);
  try {
    const file = await open(target, "wx", 0o600);
    try {
      await file.writeFile(previous);
      await file.sync();
    } finally {
      await file.close();
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    const info = await lstat(target);
    if (!info.isFile() || info.isSymbolicLink() || !(await readFile(target)).equals(previous))
      throw new Error("memomatic history was changed");
  }
}

export async function readTextIfExists(path: string): Promise<string | undefined> {
  try {
    return await readFile(path, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function writeCorpusFile(
  paths: MemomaticPaths,
  file: string,
  next: string,
): Promise<void> {
  if (!inside(paths.stateRoot, file)) throw new Error("memomatic path escapes its root");
  const previous = await readFile(file).catch(() => undefined);
  if (previous !== undefined && previous.toString("utf8") === next) return;
  await safeDirectory(dirname(file), paths.stateRoot, true);
  if (previous !== undefined) await writePreImage(paths, file, previous);
  await writeAtomic(file, Buffer.from(next), 0o600);
}

export function dailyNotePath(paths: MemomaticPaths, date = new Date()): string {
  const iso = date.toISOString().slice(0, 10);
  return join(paths.dailyDir, `${iso}.md`);
}

export function entryKind(file: string): "curated" | "user" | "episodic" {
  const name = file.slice(file.lastIndexOf("/") + 1);
  if (name === "MEMORY.md") return "curated";
  if (name === "USER.md") return "user";
  return "episodic";
}

export function parseCorpusEntries(markdown: string, file: string): CorpusEntry[] {
  const entries: CorpusEntry[] = [];
  const lines = markdown.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const parsed = parseEntryLine(lines[index]);
    if (!parsed) continue;
    entries.push({ file, line: index + 1, text: parsed.text, annotations: parsed.annotations });
  }
  return entries;
}

export async function appendDailyEntry(
  paths: MemomaticPaths,
  line: string,
  date = new Date(),
): Promise<string> {
  const file = dailyNotePath(paths, date);
  const current = (await readTextIfExists(file)) ?? "";
  const next = current.length ? `${current.trimEnd()}\n${line}\n` : `${line}\n`;
  await writeCorpusFile(paths, file, next);
  return file;
}

export async function replaceEntryLine(
  paths: MemomaticPaths,
  file: string,
  line: number,
  replacement: string | null,
): Promise<void> {
  const content = await readFile(file, "utf8");
  const lines = content.split("\n");
  if (line < 1 || line > lines.length) throw new Error("entry line is out of range");
  if (replacement === null) {
    lines.splice(line - 1, 1);
    const rest = lines.join("\n");
    await writeCorpusFile(paths, file, rest.length ? `${rest}` : "");
    return;
  }
  lines[line - 1] = replacement;
  await writeCorpusFile(paths, file, lines.join("\n"));
}

export async function appendDreams(paths: MemomaticPaths, report: string): Promise<void> {
  const stamp = new Date().toISOString().replace("T", " ").slice(0, 16);
  const current = (await readTextIfExists(paths.dreamsFile)) ?? "";
  const block = `## ${stamp}\n\n${report.trim()}\n\n`;
  const next = `${current}${current.length ? "\n" : ""}${block}`;
  await writeCorpusFile(paths, paths.dreamsFile, next);
}

export async function archiveFile(paths: MemomaticPaths, file: string): Promise<string> {
  if (!inside(paths.stateRoot, file)) throw new Error("memomatic path escapes its root");
  const name = file.slice(file.lastIndexOf("/") + 1);
  const target = join(paths.archiveDir, `${name}`);
  await safeDirectory(paths.archiveDir, paths.stateRoot, true);
  const content = await readFile(file);
  const existing = await readFile(target).catch(() => undefined);
  if (existing !== undefined) {
    const merged = `${existing.toString("utf8").trimEnd()}\n${content.toString("utf8").trimEnd()}\n`;
    await writeAtomic(target, Buffer.from(merged), 0o600);
  } else {
    await writeAtomic(target, content, 0o600);
  }
  await rm(file);
  return target;
}

export function isCuratedFile(file: string): boolean {
  return CURATED_FILES.some((name) => file.endsWith(name));
}
