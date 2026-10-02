import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { test, after } from "node:test";
import { suggestionToPatch, prepareApplication, commitApplication } from "../dist/worktree.js";

const stateHome = mkdtempSync(join(tmpdir(), "reviewmatic-state-"));
process.env.XDG_STATE_HOME = stateHome;
after(() => rmSync(stateHome, { recursive: true, force: true }));

function temporary() {
  return mkdtempSync(join(tmpdir(), "reviewmatic-worktree-"));
}

function git(cwd, ...args) {
  execFileSync("git", args, { cwd, encoding: "utf8" });
}

test("suggestion to patch replaces the anchored line and applies cleanly", () => {
  const root = temporary();
  try {
    git(root, "init", "-q", "--initial-branch=main");
    git(root, "config", "user.email", "t@example.com");
    git(root, "config", "user.name", "t");
    git(root, "config", "commit.gpgsign", "false");
    writeFileSync(join(root, "src.txt"), "one\ntwo\nthree\n");
    git(root, "add", "src.txt");
    git(root, "commit", "-q", "-m", "init");
    const head = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
    const patch = suggestionToPatch({
      repoRoot: root,
      headSha: head,
      newPath: "src.txt",
      oldPath: "src.txt",
      newLine: 2,
      oldLine: null,
      suggestion: "TWO\nTWO-B",
    });
    execFileSync("git", ["apply", "--check", "-"], { cwd: root, input: patch });
    execFileSync("git", ["apply", "-"], { cwd: root, input: patch });
    assert.equal(readFileSync(join(root, "src.txt"), "utf8"), "one\nTWO\nTWO-B\nthree\n");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("prepare and commit application run in a dedicated worktree", async () => {
  const area = temporary();
  try {
    const origin = join(area, "origin");
    mkdirSync(origin);
    git(origin, "init", "-q", "--bare", "--initial-branch=main");
    const checkout = join(area, "checkout");
    mkdirSync(checkout);
    git(checkout, "clone", "-q", origin, ".");
    git(checkout, "config", "user.email", "t@example.com");
    git(checkout, "config", "user.name", "t");
    git(checkout, "config", "commit.gpgsign", "false");
    writeFileSync(join(checkout, "a.txt"), "1\n2\n");
    git(checkout, "add", "a.txt");
    git(checkout, "commit", "-q", "-m", "init");
    git(checkout, "push", "-q", "origin", "main");
    const head = execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: checkout,
      encoding: "utf8",
    }).trim();
    const patch =
      "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n 1\n-2\n+22\n";
    const result = await prepareApplication({
      repoRoot: checkout,
      branch: "main",
      headSha: head,
      patch,
      mrUrl: "https://gitlab.example/group/project/-/merge_requests/1",
    });
    assert.equal(result.explanation.branch, "main");
    assert.equal(result.explanation.head_sha, head);
    assert.deepEqual(result.explanation.files, ["a.txt"]);
    assert.match(result.diff, /\+22/);
    assert.match(result.explanation.worktree_path, /\.worktrees\/reviewmatic\/main$/);
    const { commit_sha: sha } = commitApplication(
      result.explanation.worktree_path,
      "fix: apply review patch",
    );
    assert.equal(sha.length, 40);
    assert.throws(
      () => commitApplication(result.explanation.worktree_path, "again"),
      /nothing to commit/,
    );
  } finally {
    rmSync(area, { recursive: true, force: true });
  }
});
