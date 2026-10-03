import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { test, after } from "node:test";
import { startReview, refreshReview, checkReview, finishReview } from "../dist/draft.js";
import { artifactPayload, readJson, writeJson } from "../dist/contract.js";
import { prepareReviewWorktree, reviewSlug, saveReviewRegistry } from "../dist/review-worktree.js";
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
  assert.match(
    worktree.path,
    /\.worktrees\/reviewmatic\/mr-gitlab\.example-group-project-iid7-[0-9a-f]{8}$/,
  );
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
  const draft = await completeDraft(readJson(first.draft_path), first);
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
  assert.match(second.review_worktree.path, /mr-gitlab\.example-other-project-iid7-[0-9a-f]{8}$/);
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

test("an interrupted repeated preparation keeps the active review protected", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(first.status, "ok", JSON.stringify(first));
  const worktreePath = first.review_worktree.path;

  // A repeated preparation of the same head that stops before beginReview
  // must not claim the tree away from the running review.
  const [, evidence] = artifactPayload(first.evidence_path, "evidence_snapshot");
  const repeated = prepareReviewWorktree({
    repoRoot: fixture.repo,
    evidence: { ...evidence, artifact_root: first.artifact_root },
    evidenceDigest: "b".repeat(64),
  });
  assert.equal(repeated.path, worktreePath);
  assert.equal(repeated.reused, true);
  const marker = registry().items[0].analysis;
  assert.equal(marker.artifact_root, first.artifact_root);
  assert.equal(marker.evidence_digest, loadProgress(first.artifact_root).evidence_digest);

  writeFileSync(join(fixture.repo, "review.txt"), "base\nreviewed change\nadvanced\n");
  fixture.git("commit", "-qam", "advanced");
  const newHead = fixture.git("rev-parse", "HEAD");
  fixture.git("push", "-q", "origin", "main");
  fixture.git("push", "-q", "origin", "dev");
  execFileSync("git", ["-C", fixture.origin, "update-ref", "refs/merge-requests/7/head", newHead]);
  writeFileSync(fixture.configPath, JSON.stringify({ ...fixture.config, headSha: newHead }));

  const blocked = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(blocked.status, "blocked");
  assert.match(JSON.stringify(blocked.errors), /in progress/);
  assert.equal(worktreeHead(worktreePath), fixture.headSha);

  const refreshed = await refreshReview(first.draft_path);
  assert.equal(refreshed.status, "needs_reassessment", JSON.stringify(refreshed));
  assert.equal(refreshed.review_worktree.switched, true);
  assert.equal(worktreeHead(worktreePath), newHead);
});

test("a retired-layout worktree blocks preparation until it is migrated manually", async (t) => {
  const fixture = reviewFixture(t);
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(first.status, "ok", JSON.stringify(first));
  const newPath = first.review_worktree.path;
  const legacyPath = `${fixture.repo}.worktrees/reviewmatic/mr-gitlab.example-group-project-iid7`;
  execFileSync("git", [
    "-C",
    fixture.repo,
    "worktree",
    "add",
    "--detach",
    legacyPath,
    fixture.headSha,
  ]);
  const registryFile = join(
    process.env.XDG_STATE_HOME,
    "agent-skills",
    "reviewmatic",
    "review-worktrees.json",
  );
  const state = readJson(registryFile, "registry");
  state.items[0].path = legacyPath;
  writeJson(registryFile, state);

  const blocked = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(blocked.status, "blocked");
  const reported = JSON.stringify(blocked.errors);
  assert.match(reported, /retired path layout/);
  assert.match(reported, /worktree remove/);
  assert.match(reported, new RegExp(newPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.equal(gitIn(legacyPath, "rev-parse", "HEAD"), fixture.headSha);
  assert.equal(readJson(registryFile, "registry").items[0].path, legacyPath);

  execFileSync("git", ["-C", fixture.repo, "worktree", "remove", legacyPath]);
  const migrated = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(migrated.status, "ok", JSON.stringify(migrated));
  assert.equal(migrated.review_worktree.path, newPath);
  assert.equal(migrated.review_worktree.reused, true);
  const items = registry().items;
  assert.equal(items.length, 1);
  assert.equal(items[0].path, newPath);

  saveReviewRegistry({ schema: "reviewmatic/review-worktree-registry/v1", items: [] });
  rmSync(legacyPath, { recursive: true, force: true });
  mkdirSync(legacyPath, { recursive: true });
  writeFileSync(join(legacyPath, "keep.txt"), "legacy\n");
  const unmanaged = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(unmanaged.status, "blocked");
  assert.match(JSON.stringify(unmanaged.errors), /retired path layout/);
  assert.equal(readFileSync(join(legacyPath, "keep.txt"), "utf8"), "legacy\n");
});

test("parallel preparations of different merge requests keep both registry records", async (t) => {
  const fixture = reviewFixture(t);
  const worker = new URL("./helpers/registry-worker.mjs", import.meta.url).pathname;
  const writeRecord = (project) =>
    new Promise((done, failed) => {
      const child = spawn(
        process.execPath,
        [
          worker,
          JSON.stringify({
            schema: "reviewmatic/review-worktree/v1",
            path: `${fixture.repo}.worktrees/reviewmatic/mr-${project.replace(/\//g, "-")}-iid7`,
            host: "gitlab.example",
            project_path: project,
            iid: 7,
          }),
        ],
        { env: process.env, stdio: ["ignore", "pipe", "pipe"] },
      );
      let error = "";
      child.stderr.on("data", (chunk) => {
        error += chunk;
      });
      child.on("close", (code, signal) => {
        if (code === 0) done();
        else failed(new Error(`registry writer for ${project} failed: ${signal ?? code} ${error}`));
      });
    });
  await Promise.all([writeRecord("group/project"), writeRecord("other/project")]);
  const raced = registry()
    .items.map((item) => item.project_path)
    .sort();
  assert.deepEqual(raced, ["group/project", "other/project"]);

  fixture.git("remote", "add", "second", "https://gitlab.example/other/project.git");
  fixture.git(
    "config",
    "--add",
    `url.${fixture.origin}.insteadOf`,
    "https://gitlab.example/other/project.git",
  );
  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const second = await startReview({
    url: "https://gitlab.example/other/project/-/merge_requests/7",
    repoRoot: fixture.repo,
  });
  assert.equal(first.status, "ok", JSON.stringify(first));
  assert.equal(second.status, "ok", JSON.stringify(second));

  const repeatedFirst = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  const repeatedSecond = await startReview({
    url: "https://gitlab.example/other/project/-/merge_requests/7",
    repoRoot: fixture.repo,
  });
  assert.equal(repeatedFirst.review_worktree.reused, true);
  assert.equal(repeatedSecond.review_worktree.reused, true);
  const kept = registry()
    .items.map((item) => item.project_path)
    .sort();
  assert.deepEqual(kept, ["group/project", "other/project"]);
});

test("worktree paths separate the full host, project, and IID identity", async (t) => {
  const fixture = reviewFixture(t);
  assert.notEqual(
    reviewSlug("gitlab.example", "group/a-b", 7),
    reviewSlug("gitlab.example", "group-a/b", 7),
  );
  assert.notEqual(
    reviewSlug("gitlab.example", "group/project", 7),
    reviewSlug("gitlab.example", "group/project", 8),
  );
  const longA = `long/${"a".repeat(120)}`;
  const longB = `long/${"a".repeat(119)}b`;
  assert.notEqual(reviewSlug("gitlab.example", longA, 7), reviewSlug("gitlab.example", longB, 7));

  const first = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(first.status, "ok", JSON.stringify(first));
  const addProject = (remote, url) => {
    fixture.git("remote", "add", remote, url);
    fixture.git("config", "--add", `url.${fixture.origin}.insteadOf`, url);
  };
  addProject("slash", "https://gitlab.example/group/a-b.git");
  const slash = await startReview({
    url: "https://gitlab.example/group/a-b/-/merge_requests/7",
    repoRoot: fixture.repo,
  });
  assert.equal(slash.status, "ok", JSON.stringify(slash));
  addProject("dashed", "https://gitlab.example/group-a/b.git");
  const dashed = await startReview({
    url: "https://gitlab.example/group-a/b/-/merge_requests/7",
    repoRoot: fixture.repo,
  });
  assert.equal(dashed.status, "ok", JSON.stringify(dashed));
  addProject("long-a", `https://gitlab.example/${longA}.git`);
  const longReviewA = await startReview({
    url: `https://gitlab.example/${longA}/-/merge_requests/7`,
    repoRoot: fixture.repo,
  });
  assert.equal(longReviewA.status, "ok", JSON.stringify(longReviewA));
  addProject("long-b", `https://gitlab.example/${longB}.git`);
  const longReviewB = await startReview({
    url: `https://gitlab.example/${longB}/-/merge_requests/7`,
    repoRoot: fixture.repo,
  });
  assert.equal(longReviewB.status, "ok", JSON.stringify(longReviewB));

  const paths = [
    first.review_worktree.path,
    slash.review_worktree.path,
    dashed.review_worktree.path,
    longReviewA.review_worktree.path,
    longReviewB.review_worktree.path,
  ];
  assert.equal(new Set(paths).size, 5);
  for (const path of paths) {
    assert.match(basename(path), /^mr-gitlab\.example-.*-[0-9a-f]{8}$/);
    assert.ok(basename(path).length <= 96 + 1 + 8);
  }
  assert.equal(
    basename(longReviewA.review_worktree.path).slice(0, -9),
    basename(longReviewB.review_worktree.path).slice(0, -9),
  );
  assert.equal(registry().items.length, 5);
});

test("remote matching normalizes the project path case on both sides", async (t) => {
  const fixture = reviewFixture(t);
  fixture.git("remote", "set-url", "origin", "https://gitlab.example/Group/Project.git");
  fixture.git(
    "config",
    "--add",
    `url.${fixture.origin}.insteadOf`,
    "https://gitlab.example/Group/Project.git",
  );
  const result = await startReview({ url: fixture.url, repoRoot: fixture.repo });
  assert.equal(result.status, "ok", JSON.stringify(result));
  assert.equal(result.review_worktree.remote, "origin");

  const forkFixture = reviewFixture(t);
  const forkOrigin = join(forkFixture.tmp, "fork.git");
  execFileSync("git", ["init", "--quiet", "--bare", "--initial-branch=main", forkOrigin]);
  const forkClone = join(forkFixture.tmp, "fork-clone-case");
  execFileSync("git", ["clone", "-q", forkFixture.origin, forkClone]);
  const forkGit = (...args) =>
    execFileSync("git", ["-C", forkClone, ...args], { encoding: "utf8" }).trim();
  forkGit("config", "user.email", "author@example.invalid");
  forkGit("config", "user.name", "Author");
  forkGit("config", "commit.gpgsign", "false");
  writeFileSync(join(forkClone, "review.txt"), "base\nreviewed change\nfork change\n");
  forkGit("commit", "-qam", "fork change");
  const forkHead = forkGit("rev-parse", "HEAD");
  forkGit("push", "-q", forkOrigin, "HEAD:refs/heads/dev");
  forkFixture.git("remote", "add", "contrib", "https://gitlab.example/Fork/Project.git");
  forkFixture.git(
    "config",
    `url.${forkOrigin}.insteadOf`,
    "https://gitlab.example/Fork/Project.git",
  );
  writeFileSync(
    forkFixture.configPath,
    JSON.stringify({
      ...forkFixture.config,
      headSha: forkHead,
      sourceProjectId: 21,
      sourceProjectPath: "Fork/Project",
    }),
  );
  const forked = await startReview({ url: forkFixture.url, repoRoot: forkFixture.repo });
  assert.equal(forked.status, "ok", JSON.stringify(forked));
  assert.equal(forked.review_worktree.remote, "contrib");
  assert.equal(forked.review_worktree.refs.head_sha, forkHead);
});
