import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync, renameSync, mkdirSync } from "node:fs";
import { dirname, basename, join } from "node:path";
import { WorkflowError, digest } from "./contract.js";
import { xdgStateHome } from "./state-artifacts.js";
import { suggestionsPatch } from "./fixes.js";

export type WorktreeRecord = {
  path: string;
  branch: string;
  head_sha: string;
  mr_url: string;
  patch_sha256: string;
  created_at: string;
  commit_sha: string | null;
  pushed: boolean;
};

export type WorktreeRegistry = {
  schema: "reviewmatic/worktree-registry/v1";
  items: WorktreeRecord[];
};

function git(cwd: string, args: string[], input?: string, timeoutMs = 45000): string {
  const result = spawnSync("git", args, {
    cwd,
    ...(input !== undefined ? { input } : {}),
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: 16 * 1024 * 1024,
  });
  if (result.error) {
    throw new WorkflowError(`git ${args[0]} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout)
      .trim()
      .slice(0, 500);
    throw new WorkflowError(`git ${args[0]} failed: ${detail}`);
  }
  return String(result.stdout);
}

function branchSlug(branch: string): string {
  return branch.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 80);
}

export function mainCheckoutRoot(repoRoot: string): string {
  if (!existsSync(repoRoot)) {
    throw new WorkflowError("repository root is unavailable");
  }
  const commonDir = git(repoRoot, [
    "rev-parse",
    "--path-format=absolute",
    "--git-common-dir",
  ]).trim();
  const root = git(repoRoot, ["rev-parse", "--path-format=absolute", "--show-toplevel"]).trim();
  if (commonDir.includes("/worktrees/")) {
    return dirname(dirname(dirname(commonDir))) === root ? root : dirname(dirname(commonDir));
  }
  if (join(commonDir, ".git") === join(root, ".git") || `${commonDir}/.git` === `${root}/.git`) {
    return root;
  }
  return dirname(commonDir) === root ? root : dirname(commonDir);
}

export function worktreeBase(repoRoot: string): string {
  return join(`${mainCheckoutRoot(repoRoot)}.worktrees`, "reviewmatic");
}

export function worktreePath(repoRoot: string, branch: string): string {
  return join(worktreeBase(repoRoot), branchSlug(branch));
}

function registryPath(): string {
  return join(xdgStateHome().toString(), "agent-skills", "reviewmatic", "worktrees.json");
}

export function loadRegistry(): WorktreeRegistry {
  const path = registryPath();
  if (!existsSync(path)) {
    return { schema: "reviewmatic/worktree-registry/v1", items: [] };
  }
  const value = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (
    !value ||
    typeof value !== "object" ||
    (value as { schema?: unknown }).schema !== "reviewmatic/worktree-registry/v1" ||
    !Array.isArray((value as { items?: unknown }).items)
  ) {
    throw new WorkflowError("worktree registry is invalid");
  }
  return value as WorktreeRegistry;
}

export function saveRegistry(registry: WorktreeRegistry): void {
  const path = registryPath();
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(registry, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, path);
}

export type ApplicationExplanation = {
  repository: string;
  branch: string;
  head_sha: string;
  worktree_path: string;
  files: string[];
  fetch_command: string;
  create_command: string;
  apply_preview: string;
};

export type ApplicationResult = {
  explanation: ApplicationExplanation;
  applied: boolean;
  diff: string;
  record: WorktreeRecord;
};

function patchFiles(patch: string): string[] {
  const files: string[] = [];
  for (const line of patch.split("\n")) {
    const match = /^diff --git a\/(\S+) b\/(\S+)$/.exec(line);
    if (match && !files.includes(match[2])) files.push(match[2]);
  }
  return files;
}

export async function prepareApplication(options: {
  repoRoot: string;
  branch: string;
  headSha: string;
  patch: string;
  mrUrl: string;
}): Promise<ApplicationResult> {
  const repository = mainCheckoutRoot(options.repoRoot);
  git(repository, ["fetch", "origin", options.branch]);
  const fetched = git(repository, ["rev-parse", "FETCH_HEAD"]).trim();
  if (fetched !== options.headSha) {
    throw new WorkflowError(
      "the merge request branch moved after the review; regenerate the plan before applying",
    );
  }
  const target = worktreePath(options.repoRoot, options.branch);
  if (existsSync(target)) {
    const status = git(target, ["status", "--porcelain"]);
    if (status.trim() !== "") {
      throw new WorkflowError(`the review worktree already exists with local changes: ${target}`);
    }
    const current = git(target, ["rev-parse", "HEAD"]).trim();
    if (current !== options.headSha) {
      throw new WorkflowError(`the review worktree exists at a different commit: ${target}`);
    }
  } else {
    mkdirSync(dirname(target), { recursive: true });
    git(repository, ["worktree", "add", "--detach", target, fetched]);
  }
  const check = spawnSync("git", ["apply", "--check", "-"], {
    cwd: target,
    input: options.patch,
    encoding: "utf8",
    timeout: 45000,
  });
  if (check.status === 0) {
    const applied = spawnSync("git", ["apply", "-"], {
      cwd: target,
      input: options.patch,
      encoding: "utf8",
      timeout: 45000,
    });
    if (applied.status !== 0) {
      throw new WorkflowError(
        `git apply failed: ${String(applied.stderr || applied.stdout)
          .trim()
          .slice(0, 500)}`,
      );
    }
  } else if (!/already applied|does not match|patch does not apply/.test(String(check.stderr))) {
    throw new WorkflowError(
      `git apply --check failed: ${String(check.stderr).trim().slice(0, 500)}`,
    );
  }
  const diff = git(target, ["diff"]);
  const record: WorktreeRecord = {
    path: target,
    branch: options.branch,
    head_sha: options.headSha,
    mr_url: options.mrUrl,
    patch_sha256: digest({ text: options.patch } as never),
    created_at: new Date().toISOString(),
    commit_sha: null,
    pushed: false,
  };
  const registry = loadRegistry();
  registry.items = [...registry.items.filter((item) => item.path !== target), record];
  saveRegistry(registry);
  return {
    explanation: {
      repository,
      branch: options.branch,
      head_sha: options.headSha,
      worktree_path: target,
      files: patchFiles(options.patch),
      fetch_command: `git fetch origin ${options.branch}`,
      create_command: `git worktree add --detach ${target} ${options.headSha}`,
      apply_preview: `git apply -`,
    },
    applied: diff.trim() !== "",
    diff,
    record,
  };
}

export function commitApplication(worktreePath: string, message: string): { commit_sha: string } {
  const status = git(worktreePath, ["status", "--porcelain"]);
  if (status.trim() === "") {
    throw new WorkflowError("nothing to commit in the review worktree");
  }
  git(worktreePath, ["add", "-A"]);
  git(worktreePath, ["commit", "-m", message]);
  const sha = git(worktreePath, ["rev-parse", "HEAD"]).trim();
  const registry = loadRegistry();
  const record = registry.items.find((item) => item.path === worktreePath);
  if (record) {
    record.commit_sha = sha;
    saveRegistry(registry);
  }
  return { commit_sha: sha };
}

export function pushApplication(options: { worktreePath: string; branch: string }): {
  pushed: true;
} {
  git(
    options.worktreePath,
    ["push", "origin", `HEAD:refs/heads/${options.branch}`],
    undefined,
    120000,
  );
  const registry = loadRegistry();
  const record = registry.items.find((item) => item.path === options.worktreePath);
  if (record) {
    record.pushed = true;
    saveRegistry(registry);
  }
  return { pushed: true };
}

export function pushPreview(options: { worktreePath: string; branch: string }): string {
  return `git push origin HEAD:refs/heads/${options.branch}`;
}

export function remoteUrl(repoRoot: string): string {
  return git(mainCheckoutRoot(repoRoot), ["remote", "get-url", "origin"]).trim();
}

export function suggestionToPatch(options: {
  repoRoot: string;
  headSha: string;
  newPath: string;
  oldPath: string;
  newLine: number | null;
  oldLine: number | null;
  suggestion: string;
}): string {
  if (options.suggestion.includes("```suggestion")) {
    return suggestionsPatch(mainCheckoutRoot(options.repoRoot), options.headSha, [
      { path: options.newPath, line: options.newLine!, body: options.suggestion },
    ]);
  }
  const side = options.newLine !== null ? "new" : "old";
  const path = side === "new" ? options.newPath : options.oldPath;
  const line = side === "new" ? options.newLine : options.oldLine;
  if (line === null || line < 1) {
    throw new WorkflowError("suggestion position is invalid");
  }
  const blob = git(mainCheckoutRoot(options.repoRoot), ["show", `${options.headSha}:${path}`]);
  const lines = blob.split("\n");
  if (lines.at(-1) === "") lines.pop();
  if (line > lines.length) {
    throw new WorkflowError("suggestion position is outside the file");
  }
  const replacement = options.suggestion.replace(/\n$/, "").split("\n");
  const before = lines.slice(0, line - 1);
  const after = lines.slice(line);
  const context = 3;
  const start = Math.max(0, before.length - context);
  const beforeContext = before.slice(start);
  const afterContext = after.slice(0, context);
  const oldCount = beforeContext.length + 1 + afterContext.length;
  const newCount = beforeContext.length + replacement.length + afterContext.length;
  const startLine = line - beforeContext.length;
  const hunk: string[] = [`@@ -${startLine},${oldCount} +${startLine},${newCount} @@`];
  for (const item of beforeContext) hunk.push(` ${item}`);
  hunk.push(`-${lines[line - 1]}`);
  for (const item of replacement) hunk.push(`+${item}`);
  for (const item of afterContext) hunk.push(` ${item}`);
  return [
    `diff --git a/${options.oldPath} b/${options.newPath}`,
    `--- a/${options.oldPath}`,
    `+++ b/${options.newPath}`,
    ...hunk,
    "",
  ].join("\n");
}

export function registrySummary(): WorktreeRecord[] {
  return loadRegistry().items;
}

export function removeWorktree(worktreePath: string): void {
  const registry = loadRegistry();
  const record = registry.items.find((item) => item.path === worktreePath);
  if (!record) {
    throw new WorkflowError("unknown review worktree");
  }
  if (record.pushed) {
    throw new WorkflowError("a pushed review worktree is removed without protection");
  }
  const status = git(worktreePath, ["status", "--porcelain"]);
  if (status.trim() !== "") {
    throw new WorkflowError("the review worktree holds uncommitted changes");
  }
  git(dirname(dirname(worktreePath)), ["worktree", "remove", worktreePath]);
  registry.items = registry.items.filter((item) => item.path !== worktreePath);
  saveRegistry(registry);
}

export function worktreeLabel(worktreePath: string): string {
  return basename(worktreePath);
}
