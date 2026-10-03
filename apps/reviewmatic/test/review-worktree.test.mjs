import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { test, after } from "node:test";
import { startReview, refreshReview, checkReview, finishReview } from "../dist/draft.js";
import { artifactPayload, readJson, writeJson } from "../dist/contract.js";
import { loadProgress } from "../dist/context.js";
import { localBundle } from "../dist/local-review.js";
import { prepareApplication } from "../dist/worktree.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

const stateHome = mkdtempSync(join(tmpdir(), "reviewmatic-review-state-"));
process.env.XDG_STATE_HOME = stateHome;
after(() => rmSync(stateHome, { recursive: true, force: true }));

function gitIn(cwd, ...args) {
  return execFileSync("git", ["-C", cwd, ...args], { encoding: "utf8" }).trim();
}

function worktreeHead(path) {
  return gitIn(path, "rev-parse", "HEAD");
}

function serviceTargetSha(repo, worktreePath) {
  return gitIn(
    repo,
    "rev-parse",
    "--verify",
    `refs/reviewmatic/mr/${basename(worktreePath)}/target`,
  );
}

function registry() {
  return readJson(
    join(process.env.XDG_STATE_HOME, "agent-skills", "reviewmatic", "review-worktrees.json"),
    "review worktree registry",
  );
}

function requestEndpoints(fixture) {
  return readFileSync(fixture.config.requests, "utf8")
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line).endpoint);
}

function assertNoCodeFetches(fixture) {
  const endpoints = requestEndpoints(fixture);
  assert.ok(
    endpoints.every((endpoint) => !/blobs|\/files\/|\/raw\/|repository\/tree/.test(endpoint)),
    `no per-file code fetches: ${endpoints.join(", ")}`,
  );
}

function pushHeadFromClone(fixture, message, branches) {
  const clone = join(fixture.tmp, `origin-push-${message.replace(/\W+/g, "-")}`);
  execFileSync("git", ["clone", "-q", fixture.origin, clone]);
  execFileSync("git", ["-C", clone, "config", "user.email", "author@example.invalid"]);
  execFileSync("git", ["-C", clone, "config", "user.name", "Author"]);
  execFileSync("git", ["-C", clone, "config", "commit.gpgsign", "false"]);
  writeFileSync(join(clone, "review.txt"), `base\nreviewed change\n${message}\n`);
  execFileSync("git", ["-C", clone, "commit", "-qam", message]);
  const sha = gitIn(clone, "rev-parse", "HEAD");
  for (const branch of branches) {
    execFileSync("git", ["-C", clone, "push", "-q", "origin", `HEAD:refs/heads/${branch}`]);
  }
  rmSync(clone, { recursive: true, force: true });
  return sha;
}

test("start-review prepares one managed worktree from a subdirectory without --repo-root", async (t) => {
  const fixture = reviewFixture(t);
  const subdir = join(fixture.repo, "docs", "deep");
  mkdirSync(subdir, { recursive: true });
  const previousCwd = process.cwd();
  t.after(() => process.chdir(previousCwd));
  process.chdir(subdir);
  writeFileSync(join(fixture.repo, "scratch.txt"), "untracked work\n");
  fixture.git("add", "scratch.txt");
  const headBefore = fixture.git("rev-parse", "HEAD");
  const branchBefore = fixture.git("symbolic-ref", "--short", "HEAD");
  const statusBefore = fixture.git("status", "--porcelain");
  const branchesBefore = fixture.git("branch", "--list");

  const result = await startReview({ url: fixture.url });
  assert.equal(result.status, "ok", JSON.stringify(result));
  const worktree = result.review_worktree;
  assert.equal(worktree.source_repo_root, fixture.repo);
  assert.equal(worktree.reused, false);
  assert.equal(worktree.switched, false);
  assert.equal(worktree.remote, "origin");
  assert.match(worktree.path, /\.worktrees\/reviewmatic\/mr-gitlab\.example-group-project-iid7$/);
  assert.equal(worktree.refs.head_sha, fixture.headSha);
  assert.equal(worktree.refs.base_sha, fixture.baseSha);
  assert.equal(worktree.refs.start_sha, fixture.baseSha);
  assert.equal(worktree.refs.target_ref, "main");
  assert.equal(serviceTargetSha(fixture.repo, worktree.path), worktree.refs.target_sha);
  assert.equal(worktreeHead(worktree.path), fixture.headSha);
  assert.equal(gitIn(worktree.path, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD", "detached HEAD");
  assert.equal(readFileSync(join(worktree.path, "review.txt"), "utf8"), "base\nreviewed change\n");
  assert.equal(loadProgress(result.artifact_root).repo_root, worktree.path);
  assert.equal(result.critic_task.repo_root, worktree.path);

  assert.equal(fixture.git("rev-parse", "HEAD"), headBefore);
  assert.equal(fixture.git("symbolic-ref", "--short", "HEAD"), branchBefore);
  assert.equal(fixture.git("status", "--porcelain"), statusBefore);
  assert.equal(fixture.git("branch", "--list"), branchesBefore);
  assert.equal(existsSync(join(fixture.repo, ".worktrees")), false);
  assert.equal(existsSync(join(worktree.path, "scratch.txt")), false);

  const repeated = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(repeated.status, "ok");
  assert.equal(repeated.review_worktree.path, worktree.path);
  assert.equal(repeated.review_worktree.reused, true);
  assert.equal(registry().items.length, 1);
  assertNoCodeFetches(fixture);
});

test("the fixed target revision never replaces the merge request diff base", async (t) => {
  const fixture = reviewFixture(t);
  const advancedTip = pushHeadFromClone(fixture, "target advanced", ["main"]);
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(result.status, "ok", JSON.stringify(result));
  assert.equal(result.review_worktree.refs.target_sha, advancedTip);
  assert.equal(result.review_worktree.refs.base_sha, fixture.baseSha);
  assert.equal(result.review_worktree.refs.head_sha, fixture.headSha);
  assert.equal(worktreeHead(result.review_worktree.path), fixture.headSha);
});

test("a fork merge request is fetched from the fork remote under any name", async (t) => {
  const fixture = reviewFixture(t);
  const forkOrigin = join(fixture.tmp, "fork.git");
  execFileSync("git", ["init", "--quiet", "--bare", "--initial-branch=main", forkOrigin]);
  const forkClone = join(fixture.tmp, "fork-clone");
  execFileSync("git", ["clone", "-q", fixture.origin, forkClone]);
  const forkGit = (...args) =>
    execFileSync("git", ["-C", forkClone, ...args], { encoding: "utf8" }).trim();
  forkGit("config", "user.email", "author@example.invalid");
  forkGit("config", "user.name", "Author");
  forkGit("config", "commit.gpgsign", "false");
  writeFileSync(join(forkClone, "review.txt"), "base\nreviewed change\nfork change\n");
  forkGit("commit", "-qam", "fork change");
  const forkHead = forkGit("rev-parse", "HEAD");
  forkGit("push", "-q", forkOrigin, "HEAD:refs/heads/dev");
  fixture.git("remote", "add", "contrib", "https://gitlab.example/fork/project.git");
  fixture.git("config", `url.${forkOrigin}.insteadOf`, "https://gitlab.example/fork/project.git");
  writeFileSync(
    fixture.configPath,
    JSON.stringify({
      ...fixture.config,
      headSha: forkHead,
      sourceProjectId: 21,
      sourceProjectPath: "fork/project",
    }),
  );

  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(result.status, "ok", JSON.stringify(result));
  assert.equal(result.review_worktree.refs.head_sha, forkHead);
  assert.equal(result.review_worktree.refs.base_sha, fixture.baseSha);
  assert.equal(result.review_worktree.remote, "contrib");
  assert.equal(worktreeHead(result.review_worktree.path), forkHead);
  assert.ok(requestEndpoints(fixture).includes("projects/21"));
  assertNoCodeFetches(fixture);
});

test("an unrelated repository stops the review and asks for the correct checkout", async (t) => {
  const fixture = reviewFixture(t);
  fixture.git("remote", "set-url", "origin", "https://gitlab.example/other/project.git");
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(result.status, "blocked");
  assert.match(JSON.stringify(result.errors), /--repo-root/);
  assert.equal(existsSync(`${fixture.repo}.worktrees`), false);
  const plain = mkdtempSync(join(tmpdir(), "reviewmatic-plain-"));
  t.after(() => rmSync(plain, { recursive: true, force: true }));
  const missing = await startReview({ url: fixture.url, repoRoot: plain });
  assert.equal(missing.status, "blocked");
  assert.match(JSON.stringify(missing.errors), /not a Git checkout/);
});

test("fetch failures block preparation and a later run recovers", async (t) => {
  const fixture = reviewFixture(t);
  const newHead = pushHeadFromClone(fixture, "unreachable head", ["main", "dev"]);
  execFileSync("git", ["-C", fixture.origin, "update-ref", "refs/merge_requests/7/head", newHead]);
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, headSha: newHead }));
  fixture.git("config", "--unset-all", `url.${fixture.origin}.insteadOf`);
  fixture.git("config", "url./nonexistent/reviewmatic-unreachable.insteadOf", fixture.originUrl);

  const blocked = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(blocked.status, "blocked");
  assert.match(JSON.stringify(blocked.errors), /unavailable|fetch failed/);
  assert.equal(existsSync(`${fixture.repo}.worktrees`), false);

  fixture.git("config", "--unset-all", "url./nonexistent/reviewmatic-unreachable.insteadOf");
  fixture.git("config", `url.${fixture.origin}.insteadOf`, fixture.originUrl);
  const recovered = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(recovered.status, "ok", JSON.stringify(recovered));
  assert.equal(recovered.review_worktree.refs.head_sha, newHead);
  assert.equal(worktreeHead(recovered.review_worktree.path), newHead);
});

test("a revision that no ref carries blocks preparation without creating a worktree", async (t) => {
  const fixture = reviewFixture(t);
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, headSha: "f".repeat(40) }));
  const blocked = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(blocked.status, "blocked");
  assert.match(JSON.stringify(blocked.errors), /merge request head/);
  assert.equal(existsSync(`${fixture.repo}.worktrees`), false);
});

test("a new head switches the same worktree only when no review is active", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(first.status, "ok");
  const worktreePath = first.review_worktree.path;

  writeFileSync(join(fixture.repo, "review.txt"), "base\nreviewed change\ncorrected\n");
  fixture.git("commit", "-qam", "correction");
  const newHead = fixture.git("rev-parse", "HEAD");
  fixture.git("push", "-q", "origin", "main");
  fixture.git("push", "-q", "origin", "dev");
  execFileSync("git", ["-C", fixture.origin, "update-ref", "refs/merge_requests/7/head", newHead]);
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, headSha: newHead }));

  const blocked = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(blocked.status, "blocked");
  assert.match(JSON.stringify(blocked.errors), /in progress/);
  assert.equal(worktreeHead(worktreePath), fixture.headSha);

  const refreshed = await refreshReview(first.draft_path);
  assert.equal(refreshed.status, "needs_reassessment", JSON.stringify(refreshed));
  assert.equal(refreshed.review_worktree.path, worktreePath);
  assert.equal(refreshed.review_worktree.switched, true);
  assert.equal(worktreeHead(worktreePath), newHead);
  assert.equal(registry().items.length, 1);
  assert.equal(registry().items[0].head_sha, newHead);
});

test("a finalized review no longer blocks switching to a new head", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const draft = completeDraft(readJson(first.draft_path), first);
  writeJson(first.draft_path, draft);
  const checked = await checkReview(first.draft_path);
  assert.equal(checked.status, "ok", JSON.stringify(checked.errors));
  assert.equal((await finishReview(first.draft_path)).status, "ok");
  const planPath = loadProgress(first.artifact_root).plan_path;
  const planBytes = readFileSync(planPath);

  writeFileSync(join(fixture.repo, "review.txt"), "base\nreviewed change\nfollow-up\n");
  fixture.git("commit", "-qam", "follow-up");
  const newHead = fixture.git("rev-parse", "HEAD");
  fixture.git("push", "-q", "origin", "main");
  fixture.git("push", "-q", "origin", "dev");
  execFileSync("git", ["-C", fixture.origin, "update-ref", "refs/merge_requests/7/head", newHead]);
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, headSha: newHead }));

  const second = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(second.status, "ok", JSON.stringify(second));
  assert.equal(second.review_worktree.path, first.review_worktree.path);
  assert.equal(second.review_worktree.switched, true);
  assert.equal(worktreeHead(second.review_worktree.path), newHead);
  assert.ok(readFileSync(planPath).equals(planBytes), "the finalized plan stays untouched");
});

test("dirty, extended, and foreign worktrees are blocked without reset or cleanup", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const worktreePath = first.review_worktree.path;

  writeFileSync(join(worktreePath, "review.txt"), "tampered\n");
  const dirty = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(dirty.status, "blocked");
  assert.match(JSON.stringify(dirty.errors), /not clean/);
  assert.equal(readFileSync(join(worktreePath, "review.txt"), "utf8"), "tampered\n");
  gitIn(worktreePath, "checkout", "--", "review.txt");

  writeFileSync(join(worktreePath, "experiment.txt"), "experiment\n");
  gitIn(worktreePath, "add", "-A");
  gitIn(worktreePath, "commit", "-qm", "experiment");
  const extendedHead = worktreeHead(worktreePath);
  const extended = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(extended.status, "blocked");
  assert.match(JSON.stringify(extended.errors), /beyond its registered revision/);
  assert.equal(worktreeHead(worktreePath), extendedHead);

  rmSync(worktreePath, { recursive: true, force: true });
  writeJson(
    join(process.env.XDG_STATE_HOME, "agent-skills", "reviewmatic", "review-worktrees.json"),
    { schema: "reviewmatic/review-worktree-registry/v1", items: [] },
  );
  mkdirSync(worktreePath, { recursive: true });
  writeFileSync(join(worktreePath, "keep.txt"), "foreign\n");
  const foreign = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(foreign.status, "blocked");
  assert.match(JSON.stringify(foreign.errors), /not a reviewmatic-managed/);
  assert.equal(readFileSync(join(worktreePath, "keep.txt"), "utf8"), "foreign\n");
});

test("concurrent preparations serialize into one reused worktree", async (t) => {
  const fixture = reviewFixture(t);
  const cli = new URL("../dist/cli.js", import.meta.url).pathname;
  const runs = [0, 1].map(() =>
    spawn(
      process.execPath,
      [cli, "start-review", "--url", fixture.url, "--repo-root", fixture.repo, "--json"],
      { env: process.env, stdio: ["ignore", "pipe", "ignore"] },
    ),
  );
  const outputs = await Promise.all(
    runs.map(
      (child) =>
        new Promise((resolvePromise) => {
          let out = "";
          child.stdout.on("data", (chunk) => {
            out += chunk;
          });
          child.on("close", () => resolvePromise(out));
        }),
    ),
  );
  const results = outputs.map((out) => JSON.parse(out));
  const succeeded = results.filter((result) => result.status === "ok");
  const superseded = results.filter(
    (result) =>
      result.status === "error" &&
      /progress (binding )?changed during transition|another review state update is running/.test(
        String(result.error?.message ?? ""),
      ),
  );
  assert.equal(succeeded.length + superseded.length, results.length, JSON.stringify(results));
  assert.ok(succeeded.length >= 1, "at least one concurrent run completes");
  if (succeeded.length === 2) {
    assert.equal(
      succeeded.some((result) => result.review_worktree.reused === true),
      true,
      "one of two successful runs must reuse the prepared worktree",
    );
  }
  assert.equal(registry().items.length, 1);
  const worktreePath = succeeded[0].review_worktree.path;
  assert.equal(gitIn(worktreePath, "status", "--porcelain"), "");
  assert.equal(worktreeHead(worktreePath), fixture.headSha);
});

test("identical branch names in different projects never share a worktree", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(first.status, "ok");
  fixture.git("remote", "add", "second", "https://gitlab.example/other/project.git");
  fixture.git(
    "config",
    "--add",
    `url.${fixture.origin}.insteadOf`,
    "https://gitlab.example/other/project.git",
  );
  const second = await startReview({
    url: "https://gitlab.example/other/project/-/merge_requests/7",
    repoRoot: fixture.repo,
  });
  assert.equal(second.status, "ok", JSON.stringify(second));
  assert.notEqual(second.review_worktree.path, first.review_worktree.path);
  assert.match(second.review_worktree.path, /mr-gitlab\.example-other-project-iid7$/);
  assert.equal(registry().items.length, 2);
});

test("local WIP review creates no worktree and manual fix application keeps working", async (t) => {
  const fixture = reviewFixture(t);
  const bundle = await localBundle(fixture.repo, "code-review", null);
  assert.equal(bundle.retrieval_complete, true);
  assert.equal(existsSync(`${fixture.repo}.worktrees`), false);

  const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(started.status, "ok");
  const patch =
    "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n@@ -1,2 +1,2 @@\n base\n-reviewed change\n+reviewed change corrected\n";
  const applied = await prepareApplication({
    repoRoot: started.review_worktree.path,
    branch: "dev",
    headSha: fixture.headSha,
    patch,
    mrUrl: fixture.url,
  });
  assert.match(applied.explanation.worktree_path, /\.worktrees\/reviewmatic\/dev$/);
  assert.match(applied.diff, /\+reviewed change corrected/);
  assert.equal(
    artifactPayload(started.evidence_path, "evidence_snapshot")[1].head_sha,
    fixture.headSha,
  );
});
