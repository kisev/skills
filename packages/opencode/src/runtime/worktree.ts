import { randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { chmod, lstat, mkdir, readFile, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { digest, listState, readState, stateRoot, withStateLock } from "./state.js";
import { appendPrivate, writeAtomic } from "../lifecycle.js";

const run = promisify(execFile);
const SCHEMA_VERSION = 1;
export type WorktreeStatus = "managed" | "missing" | "blocked" | "unknown";
export type WorktreeRecord = {
  schema_version: 1;
  workspace_id: string;
  project: string;
  path: string;
  branch: string;
  start_ref: string;
  repository_fingerprint: string;
  marker: string;
  status: WorktreeStatus;
  created_at: string;
  updated_at: string;
};

function markerPath(path: string): string {
  return join(path, ".opencode-worktree.json");
}
function root(project: string): string {
  return join(stateRoot("worktree"), digest(resolve(project)));
}
function recordPath(project: string, id: string): string {
  return join(root(project), "workspaces", `${id}.json`);
}
async function git(project: string, args: string[]): Promise<string> {
  const result = await run("git", args, { cwd: project, maxBuffer: 1024 * 1024 });
  return result.stdout.trim();
}
async function fingerprint(project: string): Promise<string> {
  const common = await git(project, ["rev-parse", "--git-common-dir"]);
  return digest({ common: resolve(project, common) });
}
async function privateDirectory(path: string): Promise<void> {
  const info = await lstat(path);
  if (!info.isDirectory() || info.isSymbolicLink() || (info.mode & 0o077) !== 0)
    throw new Error("workspace directory is unsafe");
}
async function marker(path: string): Promise<Record<string, unknown> | undefined> {
  try {
    const info = await lstat(markerPath(path));
    if (!info.isFile() || info.isSymbolicLink() || info.nlink !== 1 || (info.mode & 0o077) !== 0)
      throw new Error("workspace marker is unsafe");
    return JSON.parse(await readFile(markerPath(path), "utf8")) as Record<string, unknown>;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}
async function saveRecord(item: WorktreeRecord, event: string): Promise<void> {
  const state = root(item.project);
  item.updated_at = new Date().toISOString();
  await writeAtomic(
    recordPath(item.project, item.workspace_id),
    Buffer.from(`${JSON.stringify(item)}\n`),
    0o600,
  );
  await appendPrivate(join(state, "receipts.jsonl"), {
    schema_version: 1,
    event,
    workspace_id: item.workspace_id,
    status: item.status,
    at: item.updated_at,
  });
  await appendPrivate(
    join(state, event.startsWith("release") ? "release.journal.jsonl" : "create.journal.jsonl"),
    {
      schema_version: 1,
      event,
      workspace_id: item.workspace_id,
      path: item.path,
      at: item.updated_at,
    },
  );
}
async function records(project: string): Promise<WorktreeRecord[]> {
  const state = root(project);
  const directory = join(state, "workspaces");
  const values = await Promise.all(
    (await listState(directory)).map((name) =>
      readState<WorktreeRecord>(recordPath(project, name.slice(0, -5)), state),
    ),
  );
  for (const value of values)
    if (value && value.schema_version !== SCHEMA_VERSION) throw new Error("unsupported_schema");
  return values.filter((v): v is WorktreeRecord => Boolean(v));
}
async function inspect(item: WorktreeRecord): Promise<WorktreeStatus> {
  try {
    await privateDirectory(item.path);
    const actual = await marker(item.path);
    if (
      !actual ||
      actual.workspace_id !== item.workspace_id ||
      actual.repository_fingerprint !== item.repository_fingerprint ||
      actual.project !== item.project ||
      actual.marker !== item.marker
    )
      return "unknown";
    const registered = await git(item.project, ["worktree", "list", "--porcelain"]);
    if (!registered.split("\n").some((line) => line === `worktree ${item.path}`)) return "unknown";
    if ((await fingerprint(item.path)) !== item.repository_fingerprint) return "blocked";
    const status = await git(item.path, ["status", "--porcelain"]);
    const foreignChanges = status
      .split("\n")
      .filter((line) => line && line !== "?? .opencode-worktree.json");
    return foreignChanges.length ? "blocked" : "managed";
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return "missing";
    return "blocked";
  }
}

export async function worktreePlan(
  project: string,
  workspaceID = randomUUID(),
): Promise<Record<string, unknown>> {
  const rootProject = resolve(project);
  const repo = await fingerprint(rootProject);
  return {
    schema_version: SCHEMA_VERSION,
    workspace_id: workspaceID,
    project: rootProject,
    path: join(stateRoot("worktree"), "managed", digest(rootProject), workspaceID),
    start_ref: await git(rootProject, ["rev-parse", "HEAD"]),
    repository_fingerprint: repo,
  };
}
export async function worktreeCreate(input: {
  project: string;
  workspace_id: string;
  path?: string;
  branch?: string;
  start_ref?: string;
}): Promise<WorktreeRecord> {
  const project = resolve(input.project);
  const state = root(project);
  return withStateLock(state, async () => {
    const existing = await readState<WorktreeRecord>(
      recordPath(project, input.workspace_id),
      state,
    );
    if (existing) {
      const status = await inspect(existing);
      existing.status = status;
      await saveRecord(existing, "create.idempotent");
      if (status !== "managed") throw new Error(`workspace ${status}`);
      return existing;
    }
    const repo = await fingerprint(project);
    const path = resolve(
      input.path ?? join(stateRoot("worktree"), "managed", digest(project), input.workspace_id),
    );
    const branch = input.branch ?? `opencode/${input.workspace_id}`;
    const start = input.start_ref ?? (await git(project, ["rev-parse", "HEAD"]));
    try {
      const existingPath = await lstat(path);
      if (!existingPath.isDirectory() || existingPath.isSymbolicLink())
        throw new Error("workspace path is unsafe");
      throw new Error(
        (await readdir(path)).length
          ? "workspace path is unknown and not empty"
          : "workspace path is unknown",
      );
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await git(project, ["worktree", "add", "-b", branch, path, start]);
    await chmod(path, 0o700);
    const markerValue = {
      schema_version: 1,
      workspace_id: input.workspace_id,
      project,
      repository_fingerprint: repo,
      marker: randomUUID(),
    };
    await writeAtomic(markerPath(path), Buffer.from(`${JSON.stringify(markerValue)}\n`), 0o600);
    const item: WorktreeRecord = {
      schema_version: 1,
      workspace_id: input.workspace_id,
      project,
      path,
      branch,
      start_ref: start,
      repository_fingerprint: repo,
      marker: String(markerValue.marker),
      status: "managed",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    await saveRecord(item, "create.completed");
    return item;
  });
}
export async function worktreeStatus(
  project: string,
  workspaceID: string,
): Promise<WorktreeRecord | undefined> {
  const item = await readState<WorktreeRecord>(
    recordPath(resolve(project), workspaceID),
    root(resolve(project)),
  );
  if (!item) return undefined;
  if (item.schema_version !== SCHEMA_VERSION) throw new Error("unsupported_schema");
  item.status = await inspect(item);
  return item;
}
export async function worktreeList(project: string): Promise<WorktreeRecord[]> {
  const result = await records(resolve(project));
  for (const item of result) item.status = await inspect(item);
  return result;
}
export async function worktreeRelease(
  project: string,
  workspaceID: string,
): Promise<{ status: "released" | "blocked"; workspace_id: string; reason?: string }> {
  const projectRoot = resolve(project);
  return withStateLock(root(projectRoot), async () => {
    const item = await worktreeStatus(projectRoot, workspaceID);
    if (!item) throw new Error("workspace not found");
    if (item.status !== "managed")
      return { status: "blocked", workspace_id: workspaceID, reason: item.status };
    try {
      await git(item.project, ["worktree", "remove", "--force", item.path]);
      item.status = "missing";
      await saveRecord(item, "release.completed");
      return { status: "released", workspace_id: workspaceID };
    } catch (error) {
      return { status: "blocked", workspace_id: workspaceID, reason: String(error) };
    }
  });
}
export async function worktreeRecover(
  project: string,
): Promise<{ recovered: number; blocked: number }> {
  const projectRoot = resolve(project);
  const items = await worktreeList(projectRoot);
  const result = { recovered: 0, blocked: 0 };
  await withStateLock(root(projectRoot), async () => {
    for (const item of items) {
      if (item.status === "managed") {
        result.recovered += 1;
        await saveRecord(item, "recover.completed");
      } else if (item.status !== "missing") {
        result.blocked += 1;
        await saveRecord(item, "recover.blocked");
      }
    }
  });
  return result;
}
