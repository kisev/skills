import { randomUUID } from "node:crypto";
import { constants } from "node:fs";
import { chmod, lstat, mkdir, open, readFile, rename, rm } from "node:fs/promises";
import { basename, dirname, join, parse, resolve, sep } from "node:path";

export class LifecycleError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function lstatSafe(path: string) {
  try {
    return await lstat(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export async function assertSafePath(
  path: string,
  options: { target?: "file" | "directory"; allowMissing?: boolean } = {},
): Promise<void> {
  const target = resolve(path);
  const parsed = parse(target);
  let current = parsed.root;
  const pieces = target.slice(parsed.root.length).split(sep).filter(Boolean);
  for (let index = 0; index < pieces.length; index += 1) {
    current = join(current, pieces[index]);
    const metadata = await lstatSafe(current);
    if (!metadata) {
      if (options.allowMissing !== false) return;
      throw new LifecycleError("unsafe_path", `Required path is missing: ${current}`);
    }
    if (metadata.isSymbolicLink())
      throw new LifecycleError("unsafe_path", `Symlink is not allowed: ${current}`);
    const final = index === pieces.length - 1;
    if (!final && !metadata.isDirectory())
      throw new LifecycleError("unsafe_path", `Path parent is not a directory: ${current}`);
    if (final && options.target === "file" && !metadata.isFile())
      throw new LifecycleError("unsafe_path", `Target is not a regular file: ${current}`);
    if (final && options.target === "directory" && !metadata.isDirectory())
      throw new LifecycleError("unsafe_path", `Target is not a directory: ${current}`);
  }
}

export async function readRegular(path: string): Promise<Buffer | undefined> {
  await assertSafePath(path);
  const metadata = await lstatSafe(path);
  if (!metadata) return undefined;
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) {
    throw new LifecycleError("unsafe_path", `Target is not a single-link regular file: ${path}`);
  }
  return readFile(path);
}

export async function ensureDirectory(path: string, mode: number): Promise<string[]> {
  const target = resolve(path);
  const parsed = parse(target);
  let current = parsed.root;
  const created: string[] = [];
  for (const piece of target.slice(parsed.root.length).split(sep).filter(Boolean)) {
    current = join(current, piece);
    const metadata = await lstatSafe(current);
    if (metadata) {
      if (!metadata.isDirectory() || metadata.isSymbolicLink())
        throw new LifecycleError("unsafe_path", `Unsafe directory: ${current}`);
      continue;
    }
    try {
      await mkdir(current, { mode });
      created.push(current);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      const raced = await lstat(current);
      if (!raced.isDirectory() || raced.isSymbolicLink())
        throw new LifecycleError("unsafe_path", `Unsafe directory: ${current}`);
    }
  }
  return created;
}

export async function writeAtomic(path: string, content: Buffer, mode: number): Promise<void> {
  await ensureDirectory(dirname(path), 0o700);
  await assertSafePath(path);
  const current = await lstatSafe(path);
  if (current && (!current.isFile() || current.isSymbolicLink() || current.nlink !== 1)) {
    throw new LifecycleError("unsafe_path", `Target is not a single-link regular file: ${path}`);
  }
  const temporary = join(dirname(path), `.${basename(path)}.${process.pid}.${randomUUID()}.tmp`);
  const handle = await open(
    temporary,
    constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW,
    mode,
  );
  try {
    await handle.writeFile(content);
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    await chmod(temporary, mode);
    await rename(temporary, path);
    const directory = await open(dirname(path), constants.O_RDONLY | constants.O_DIRECTORY);
    try {
      await directory.sync();
    } finally {
      await directory.close();
    }
  } finally {
    await rm(temporary, { force: true });
  }
}
