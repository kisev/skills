import {
  closeSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
  writeSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname, resolve } from "node:path";
import { WorkflowError, glabJson, isDict, nonemptyString } from "./contract.js";
import { loadProgress } from "./context.js";
import { xdgStateHome } from "./state-artifacts.js";
import { git, mainCheckoutRoot } from "./worktree.js";

type Json = Record<string, unknown>;

const REGISTRY_SCHEMA = "reviewmatic/review-worktree-registry/v1";
const RECORD_SCHEMA = "reviewmatic/review-worktree/v1";
const LOCK_ATTEMPTS = 600;
const LOCK_DELAY_MS = 100;
const ANALYSIS_GRACE_MS = 15 * 60 * 1000;
const FETCH_TIMEOUT_MS = 180000;
const FAILURE_LIMIT = 900;

export type ReviewWorktreeRefs = {
  base_sha: string;
  start_sha: string;
  head_sha: string;
  target_ref: string;
  target_sha: string;
};

export type ReviewWorktree = {
  path: string;
  source_repo_root: string;
  reused: boolean;
  switched: boolean;
  remote: string;
  refs: ReviewWorktreeRefs;
};

type RemoteTarget = { name: string; host: string; project: string };
type FetchAttempt = { remote: string; ref: string | null; label: string };

export type ReviewAnalysis = {
  head_sha: string;
  evidence_digest: string;
  artifact_root: string;
  pid: number;
  started_at: string;
};

export type ReviewWorktreeRecord = {
  schema: "reviewmatic/review-worktree/v1";
  path: string;
  source_repo_root: string;
  host: string;
  project_path: string;
  source_project_path: string | null;
  iid: number;
  base_sha: string;
  start_sha: string;
  head_sha: string;
  target_ref: string;
  target_sha: string;
  remote: string;
  analysis: ReviewAnalysis | null;
  created_at: string;
  updated_at: string;
};

type WorktreeRegistry = {
  schema: "reviewmatic/review-worktree-registry/v1";
  items: ReviewWorktreeRecord[];
};

function plainInt(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

function revisionValue(value: unknown, name: string): string {
  if (typeof value !== "string" || !/^[0-9a-f]{40,64}$/.test(value)) {
    throw new WorkflowError(`the exact ${name} revision is unavailable in the review evidence`);
  }
  return value.toLowerCase();
}

function byName(left: RemoteTarget, right: RemoteTarget): number {
  return left.name < right.name ? -1 : left.name > right.name ? 1 : 0;
}

function uniqueRemotes(remotes: RemoteTarget[]): RemoteTarget[] {
  const seen = new Set<string>();
  const result: RemoteTarget[] = [];
  for (const remote of remotes) {
    if (!seen.has(remote.name)) {
      seen.add(remote.name);
      result.push(remote);
    }
  }
  return result;
}

export function checkoutRoot(value: string): string {
  const input = resolve(value);
  let inside: string;
  try {
    inside = git(input, ["rev-parse", "--is-inside-work-tree"]).trim();
  } catch (error) {
    if (error instanceof WorkflowError)
      throw new WorkflowError(
        `${input} is not a Git checkout; run from the merge request checkout or pass it with --repo-root`,
      );
    throw error;
  }
  if (inside !== "true")
    throw new WorkflowError(
      `${input} is not a Git checkout; run from the merge request checkout or pass it with --repo-root`,
    );
  return git(input, ["rev-parse", "--path-format=absolute", "--show-toplevel"]).trim();
}

function parseRemoteUrl(raw: string): { host: string; project: string } | null {
  const url = raw.trim();
  if (url === "") return null;
  let host: string | null = null;
  let path: string | null = null;
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) {
    const scheme = /^(?:https?|ssh|git):\/\/(?:[^/@]+@)?([^/:?#]+)(?::\d+)?\/(.*)$/i.exec(url);
    if (scheme) {
      host = scheme[1];
      path = scheme[2];
    }
  } else {
    const scp = /^(?:[^/@]+@)?([^/:]+):(.+)$/.exec(url);
    if (scp) {
      host = scp[1];
      path = scp[2];
    }
  }
  if (host === null || path === null) return null;
  path = path
    .split("#")[0]
    .split("?")[0]
    .replace(/\/+$/, "")
    .replace(/\.git$/i, "");
  if (path === "") return null;
  let project = path;
  try {
    project = decodeURIComponent(path);
  } catch {
    undefined;
  }
  return { host: host.toLowerCase(), project };
}

function remotesFor(root: string, host: string, projects: string[]): RemoteTarget[] {
  const wanted = projects.map((item) => item.toLowerCase());
  const result: RemoteTarget[] = [];
  for (const name of git(root, ["remote"])
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item !== "")) {
    let urls: string;
    try {
      urls = git(root, ["config", "--get-all", `remote.${name}.url`]);
    } catch (error) {
      if (error instanceof WorkflowError) continue;
      throw error;
    }
    for (const url of urls.split("\n")) {
      const parsed = parseRemoteUrl(url);
      // Both sides are normalized; the original project path stays on the
      // target for display.
      if (parsed && parsed.host === host && wanted.includes(parsed.project.toLowerCase())) {
        result.push({ name, host: parsed.host, project: parsed.project });
        break;
      }
    }
  }
  return result;
}

function sourceProjectPathFor(host: string, projectId: number): string {
  let response: unknown;
  try {
    response = glabJson(host, `projects/${projectId}`);
  } catch (error) {
    if (error instanceof WorkflowError)
      throw new WorkflowError(
        `the merge request source project ${projectId} is unavailable from GitLab: ${error.message}`,
      );
    throw error;
  }
  if (isDict(response) && nonemptyString(response.path_with_namespace)) {
    return String(response.path_with_namespace);
  }
  throw new WorkflowError("the merge request source project path is unavailable");
}

function hasCommit(root: string, sha: string): boolean {
  try {
    return (
      git(root, ["rev-parse", "--verify", "--quiet", `${sha}^{commit}`])
        .trim()
        .toLowerCase() === sha
    );
  } catch (error) {
    if (error instanceof WorkflowError) return false;
    throw error;
  }
}

function fetchRevision(root: string, sha: string, what: string, attempts: FetchAttempt[]): string {
  if (hasCommit(root, sha)) return "";
  const failures: string[] = [];
  for (const attempt of attempts) {
    try {
      git(
        root,
        ["fetch", "--no-tags", attempt.remote, attempt.ref ?? sha],
        undefined,
        FETCH_TIMEOUT_MS,
      );
    } catch (error) {
      if (error instanceof WorkflowError) {
        failures.push(`${attempt.remote}: ${error.message.slice(0, 200)}`);
        continue;
      }
      throw error;
    }
    if (hasCommit(root, sha)) return attempt.remote;
    failures.push(`${attempt.remote}: ${attempt.label} does not carry ${sha.slice(0, 12)}`);
  }
  throw new WorkflowError(
    `the exact ${what} revision ${sha} is unavailable; fetch failed: ${failures.join(" | ")}`.slice(
      0,
      FAILURE_LIMIT,
    ),
  );
}

function fetchTargetRevision(
  root: string,
  targetRef: string,
  serviceRef: string,
  remotes: RemoteTarget[],
): { sha: string; remote: string } {
  const failures: string[] = [];
  for (const remote of remotes) {
    try {
      git(
        root,
        ["fetch", "--no-tags", remote.name, `+refs/heads/${targetRef}:${serviceRef}`],
        undefined,
        FETCH_TIMEOUT_MS,
      );
      return {
        sha: git(root, ["rev-parse", "--verify", serviceRef]).trim().toLowerCase(),
        remote: remote.name,
      };
    } catch (error) {
      if (error instanceof WorkflowError) {
        failures.push(`${remote.name}: ${error.message.slice(0, 200)}`);
        continue;
      }
      throw error;
    }
  }
  throw new WorkflowError(
    `the merge request target branch ${targetRef} is unavailable; fetch failed: ${failures.join(" | ")}`.slice(
      0,
      FAILURE_LIMIT,
    ),
  );
}

// The readable part can collide (group/a-b versus group-a/b) and the readable
// form is truncated for long project paths, so the slug ends with a short hash
// of the full host/project/IID identity. The suffix is appended after
// truncation and is never cut.
export function reviewSlug(host: string, project: string, iid: number): string {
  const readable = `mr-${host}-${project}-iid${iid}`.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 96);
  return `${readable}-${identitySuffix(host, project, iid)}`;
}

function identitySuffix(host: string, project: string, iid: number): string {
  return createHash("sha256").update(`${host}\n${project}\n${iid}\n`).digest("hex").slice(0, 8);
}

// Directory layout used before the identity suffix was introduced. Managed
// trees with such paths are never reused; preparation stops with a manual
// migration instruction instead.
function legacyReviewSlug(host: string, project: string, iid: number): string {
  return `mr-${host}-${project}-iid${iid}`.replace(/[^A-Za-z0-9._-]+/g, "-").slice(0, 120);
}

function sameIdentity(
  item: ReviewWorktreeRecord,
  host: string,
  project: string,
  iid: number,
): boolean {
  return item.host === host && item.project_path === project && item.iid === iid;
}

function reviewWorktreeBase(mainCheckout: string): string {
  return join(`${mainCheckout}.worktrees`, "reviewmatic");
}

export function reviewWorktreePath(
  mainCheckout: string,
  host: string,
  project: string,
  iid: number,
): string {
  return join(reviewWorktreeBase(mainCheckout), reviewSlug(host, project, iid));
}

function registryPath(): string {
  return join(xdgStateHome().toString(), "agent-skills", "reviewmatic", "review-worktrees.json");
}

export function loadReviewRegistry(): WorktreeRegistry {
  const path = registryPath();
  if (!existsSync(path)) return { schema: REGISTRY_SCHEMA, items: [] };
  const value = JSON.parse(readFileSync(path, "utf8")) as unknown;
  if (!isDict(value) || value.schema !== REGISTRY_SCHEMA || !Array.isArray(value.items)) {
    throw new WorkflowError("review worktree registry is invalid");
  }
  return value as WorktreeRegistry;
}

export function saveReviewRegistry(registry: WorktreeRegistry): void {
  const path = registryPath();
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(registry, null, 2)}\n`, { mode: 0o600 });
  renameSync(temporary, path);
}

// The registry file is shared by all merge requests, so every read-modify-write
// holds one short global lock. Fetches never run under it: they happen before
// the lock is taken, so parallel preparations of different merge requests only
// serialize the final record update.
export function withReviewRegistryLock<T>(operation: () => T): T {
  return withPreparationLock(dirname(registryPath()), "registry", operation);
}

function pathExists(path: string): boolean {
  try {
    lstatSync(path);
    return true;
  } catch {
    return false;
  }
}

function processAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

function sleepSync(milliseconds: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function withPreparationLock<T>(base: string, slug: string, operation: () => T): T {
  mkdirSync(base, { recursive: true });
  const lockPath = join(base, `.${slug}.lock`);
  let descriptor: number | null = null;
  for (let attempt = 0; attempt < LOCK_ATTEMPTS && descriptor === null; attempt += 1) {
    try {
      descriptor = openSync(lockPath, "wx", 0o600);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      let stale = false;
      try {
        const raw = readFileSync(lockPath, "utf8").trim();
        // An empty file means the owner created it but has not written its
        // PID yet: a live, just-started holder. Removing it here would let
        // two preparations run the same mutation concurrently.
        stale =
          raw !== "" &&
          (() => {
            const owner = Number.parseInt(raw, 10);
            return !Number.isInteger(owner) || owner === process.pid || !processAlive(owner);
          })();
      } catch {
        stale = false;
      }
      if (stale) rmSync(lockPath, { force: true });
      else sleepSync(LOCK_DELAY_MS);
    }
  }
  if (descriptor === null) {
    throw new WorkflowError(
      `another review worktree preparation is running or a stale lock remains at ${lockPath}`,
    );
  }
  try {
    writeSync(descriptor, Buffer.from(`${process.pid}\n`, "utf8"));
  } catch {
    // Best-effort identification; an unwritten PID keeps the lock unstealable.
  }
  try {
    return operation();
  } finally {
    closeSync(descriptor);
    rmSync(lockPath, { force: true });
  }
}

function liveAnalysis(
  marker: ReviewAnalysis | null,
  supersedeRoot: string | null,
): ReviewAnalysis | null {
  if (marker === null) return null;
  if (supersedeRoot !== null && marker.artifact_root === supersedeRoot) return null;
  let progress: Json | null = null;
  try {
    progress = loadProgress(marker.artifact_root);
  } catch (error) {
    if (error instanceof WorkflowError) progress = null;
    else throw error;
  }
  if (progress !== null) {
    // Unfinished progress at the marker's artifact root means the tree is
    // being analyzed even when the progress digest differs from the marker
    // (a reused preparation restarted collection on the same root). Only a
    // finalized plan or an explicit supersede root frees the tree.
    return progress.stage === "plan_ready" ? null : marker;
  }
  const started = Date.parse(marker.started_at);
  return Number.isFinite(started) && Date.now() - started < ANALYSIS_GRACE_MS ? marker : null;
}

function isWorktreeAt(path: string): boolean {
  try {
    return (
      git(path, ["rev-parse", "--is-inside-work-tree"]).trim() === "true" &&
      git(path, ["rev-parse", "--path-format=absolute", "--show-toplevel"]).trim() === path
    );
  } catch (error) {
    if (error instanceof WorkflowError) return false;
    throw error;
  }
}

export function prepareReviewWorktree(options: {
  repoRoot: string;
  evidence: Json;
  evidenceDigest: string;
  supersedeRoot?: string | null;
}): ReviewWorktree {
  const evidence = options.evidence;
  const target = isDict(evidence.target) ? evidence.target : null;
  const object = isDict(evidence.object) ? evidence.object : null;
  if (target === null || object === null) {
    throw new WorkflowError("merge request evidence is incomplete");
  }
  const host = typeof target.hostname === "string" ? target.hostname.toLowerCase() : "";
  const projectPath = typeof target.project_path === "string" ? target.project_path : "";
  const iid = plainInt(target.iid);
  const projectId = plainInt(target.project_id);
  const diffRefs = isDict(object.diff_refs) ? object.diff_refs : null;
  const baseSha = revisionValue(diffRefs?.base_sha, "merge request diff base");
  const startSha = revisionValue(diffRefs?.start_sha, "merge request diff start");
  const headSha = revisionValue(diffRefs?.head_sha ?? evidence.head_sha, "merge request head");
  const targetBranch = nonemptyString(object.target_branch) ? String(object.target_branch) : "";
  const sourceBranch = nonemptyString(object.source_branch) ? String(object.source_branch) : "";
  const artifactRoot = nonemptyString(evidence.artifact_root) ? String(evidence.artifact_root) : "";
  if (
    host === "" ||
    projectPath === "" ||
    iid === null ||
    targetBranch === "" ||
    sourceBranch === "" ||
    artifactRoot === "" ||
    typeof options.evidenceDigest !== "string" ||
    options.evidenceDigest === ""
  ) {
    throw new WorkflowError("merge request identity or evidence binding is incomplete");
  }

  const toplevel = checkoutRoot(options.repoRoot);
  const main = mainCheckoutRoot(toplevel);
  const slug = reviewSlug(host, projectPath, iid);
  const path = reviewWorktreePath(main, host, projectPath, iid);
  const serviceRef = `refs/reviewmatic/mr/${slug}/target`;

  const targetRemotes = remotesFor(main, host, [projectPath]).sort(byName);
  let sourceRemotes: RemoteTarget[] = [];
  let sourceProjectPath: string | null = null;
  const sourceProjectId = plainInt(object.source_project_id);
  if (sourceProjectId !== null && projectId !== null && sourceProjectId !== projectId) {
    sourceProjectPath = sourceProjectPathFor(host, sourceProjectId);
    sourceRemotes = remotesFor(main, host, [sourceProjectPath]).sort(byName);
  }
  const allRemotes = uniqueRemotes([...sourceRemotes, ...targetRemotes]);
  if (allRemotes.length === 0) {
    throw new WorkflowError(
      `no remote of ${main} points at ${host}/${projectPath}` +
        `${sourceProjectPath === null ? "" : ` or ${host}/${sourceProjectPath}`}; ` +
        `run from the merge request checkout or pass it with --repo-root; cloning is not performed`,
    );
  }

  const headAttempts: FetchAttempt[] = [
    ...targetRemotes.map((remote) => ({
      remote: remote.name,
      ref: `refs/merge_requests/${iid}/head`,
      label: "merge request head ref",
    })),
    ...allRemotes.map((remote) => ({
      remote: remote.name,
      ref: `refs/heads/${sourceBranch}`,
      label: `source branch ${sourceBranch}`,
    })),
    ...allRemotes.map((remote) => ({
      remote: remote.name,
      ref: null,
      label: "exact revision fetch",
    })),
  ];
  const baseAttempts: FetchAttempt[] = allRemotes.map((remote) => ({
    remote: remote.name,
    ref: null,
    label: "exact revision fetch",
  }));
  const headRemote = fetchRevision(main, headSha, "merge request head", headAttempts);

  // Refuse retired layouts before any mutation: a managed tree of the old
  // path scheme is never replaced, moved, or shadowed by a second directory.
  const legacyPath = join(reviewWorktreeBase(main), legacyReviewSlug(host, projectPath, iid));
  for (const record of loadReviewRegistry().items) {
    if (!sameIdentity(record, host, projectPath, iid) || record.path === path) continue;
    if (pathExists(record.path)) {
      throw new WorkflowError(
        `the review worktree for ${host}/${projectPath}!${iid} is registered under the ` +
          `retired path layout at ${record.path}; migrate it manually: keep or finish the ` +
          `active review there, check \`git -C ${record.path} status --porcelain\` for local ` +
          `changes, then remove the tree with ` +
          `\`git -C ${main} worktree remove ${record.path}\` (--force only after preserving ` +
          `changes) and start the review again; it will create ${path}. The registry record ` +
          `for the removed tree is replaced automatically`,
      );
    }
  }
  if (legacyPath !== path && pathExists(legacyPath)) {
    throw new WorkflowError(
      `a review worktree of the retired path layout exists at ${legacyPath}; it may belong ` +
        `to ${host}/${projectPath}!${iid} or to a merge request whose readable path collides ` +
        `with it, and it is not managed by the registry. Inspect it and remove it manually ` +
        `with \`git -C ${main} worktree remove ${legacyPath}\` only after preserving any ` +
        `active review and local changes; the next preparation creates ${path}`,
    );
  }

  return withPreparationLock(reviewWorktreeBase(main), slug, () => {
    const known = loadReviewRegistry();
    const existing = known.items.find((item) => sameIdentity(item, host, projectPath, iid)) ?? null;
    let targetSha: string;
    let remote: string;
    if (existing !== null && hasCommit(main, existing.target_sha)) {
      targetSha = existing.target_sha;
      remote = existing.remote;
    } else {
      const fetched = fetchTargetRevision(main, targetBranch, serviceRef, [
        ...targetRemotes,
        ...sourceRemotes,
      ]);
      targetSha = fetched.sha;
      remote = fetched.remote;
    }
    if (headRemote !== "") remote = headRemote;
    if (!hasCommit(main, baseSha))
      fetchRevision(main, baseSha, "merge request diff base", baseAttempts);
    if (!hasCommit(main, startSha))
      fetchRevision(main, startSha, "merge request diff start", headAttempts);

    const active = liveAnalysis(existing?.analysis ?? null, options.supersedeRoot ?? null);
    let reused = false;
    let switched = false;
    if (pathExists(path)) {
      if (existing === null) {
        throw new WorkflowError(
          `${path} exists and is not a reviewmatic-managed review worktree; remove it manually or choose another checkout`,
        );
      }
      if (!isWorktreeAt(path)) {
        throw new WorkflowError(
          `the registered review worktree ${path} is broken; remove it manually with git worktree remove --force`,
        );
      }
      const current = git(path, ["rev-parse", "HEAD"]).trim().toLowerCase();
      if (current !== headSha) {
        if (current !== existing.head_sha) {
          throw new WorkflowError(
            `the review worktree ${path} contains commits beyond its registered revision; ` +
              `inspect it and remove the worktree manually if it is no longer needed`,
          );
        }
        if (active !== null && active.head_sha !== headSha) {
          throw new WorkflowError(
            `the review of ${host}/${projectPath}!${iid} is in progress at revision ` +
              `${active.head_sha.slice(0, 12)} in ${path}; finish that review before ` +
              `switching the worktree to ${headSha.slice(0, 12)}`,
          );
        }
        if (git(path, ["status", "--porcelain"]).trim() !== "") {
          throw new WorkflowError(
            `the review worktree ${path} holds local changes; resolve them manually ` +
              `before switching to revision ${headSha.slice(0, 12)}`,
          );
        }
        git(path, ["checkout", "--detach", headSha]);
        switched = true;
      } else {
        reused = true;
      }
    } else {
      git(main, ["worktree", "add", "--detach", path, headSha], undefined, 120000);
    }
    if (git(path, ["rev-parse", "HEAD"]).trim().toLowerCase() !== headSha) {
      throw new WorkflowError("the review worktree head does not match the merge request revision");
    }
    if (git(path, ["status", "--porcelain"]).trim() !== "") {
      throw new WorkflowError(
        `the review worktree ${path} is not clean; resolve its local changes manually`,
      );
    }

    const now = new Date().toISOString();
    const record: ReviewWorktreeRecord = {
      schema: RECORD_SCHEMA,
      path,
      source_repo_root: toplevel,
      host,
      project_path: projectPath,
      source_project_path: sourceProjectPath,
      iid,
      base_sha: baseSha,
      start_sha: startSha,
      head_sha: headSha,
      target_ref: targetBranch,
      target_sha: targetSha,
      remote,
      analysis:
        // A live analysis keeps its marker: a preparation that has not run
        // beginReview yet must not claim the tree away from the running review.
        active !== null
          ? active
          : {
              head_sha: headSha,
              evidence_digest: options.evidenceDigest,
              artifact_root: artifactRoot,
              pid: process.pid,
              started_at: now,
            },
      created_at: existing?.created_at ?? now,
      updated_at: now,
    };
    // Re-read and merge under the shared registry lock so parallel
    // preparations of different merge requests cannot lose each other's
    // records. No fetch happens inside this lock.
    withReviewRegistryLock(() => {
      const registry = loadReviewRegistry();
      const sameIdentityRecord = registry.items.find((item) =>
        sameIdentity(item, host, projectPath, iid),
      );
      if (sameIdentityRecord !== undefined && sameIdentityRecord.path !== path) {
        if (pathExists(sameIdentityRecord.path)) {
          throw new WorkflowError(
            `the review worktree for ${host}/${projectPath}!${iid} is registered under the ` +
              `retired path layout at ${sameIdentityRecord.path}; migrate it manually as ` +
              `reported before the worktree was prepared`,
          );
        }
      }
      saveReviewRegistry({
        schema: REGISTRY_SCHEMA,
        items: [
          ...registry.items.filter((item) => !sameIdentity(item, host, projectPath, iid)),
          record,
        ],
      });
    });
    return {
      path,
      source_repo_root: toplevel,
      reused,
      switched,
      remote,
      refs: {
        base_sha: baseSha,
        start_sha: startSha,
        head_sha: headSha,
        target_ref: targetBranch,
        target_sha: targetSha,
      },
    };
  });
}
