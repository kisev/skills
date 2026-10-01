import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { test, after } from "node:test";
import {
  planItems,
  itemText,
  safeLink,
  terminalLink,
  visualLines,
  displayText,
} from "../dist/tui/support.js";
import { suggestionToPatch, prepareApplication, commitApplication } from "../dist/worktree.js";

const stateHome = mkdtempSync(join(tmpdir(), "reviewmatic-state-"));
process.env.XDG_STATE_HOME = stateHome;
after(() => rmSync(stateHome, { recursive: true, force: true }));

function temporary() {
  return mkdtempSync(join(tmpdir(), "reviewmatic-tui-"));
}

function git(cwd, ...args) {
  execFileSync("git", args, { cwd, encoding: "utf8" });
}

function minimalPlan(root) {
  return {
    root,
    planPath: join(root, "plan.json"),
    planDigest: "0".repeat(64),
    progress: {},
    context: {
      discussions: [
        {
          id: "abc",
          root_note_id: 101,
          root_position: { new_path: "src/a.ts", new_line: 3 },
          notes: [
            {
              id: 101,
              system: false,
              author: { username: "reviewer" },
              body: "Please fix the retry.",
            },
            {
              id: 102,
              system: false,
              author: { username: "author" },
              body: "Fixed in the current code.",
            },
          ],
        },
      ],
    },
    plan: {
      verdict: "commented",
      locale: "ru",
      target: { url: "https://gitlab.example/group/project/-/merge_requests/7" },
      thread_decisions: [
        {
          id: "101",
          assessment: "accepted",
          outcome: "reply",
          proposed_response: "fixed",
          url: "https://gitlab.example/group/project/-/merge_requests/7#note_101",
          state: "open",
          rationale: "The reviewed implementation addresses the remark.",
        },
      ],
      finding_publications: [
        {
          finding_id: "finding-2",
          position: { new_path: "src/b.ts", new_line: 9 },
        },
      ],
      recommended_issues: [{ id: "issue-3", title: "Follow-up" }],
      label_review: { add: ["review::approved"], remove: [] },
      publication_preview: {
        body_files: [
          {
            publication_id: "thread-101",
            revision: 1,
            kind: "thread",
            path: "/bodies/t.md",
            content: "fixed\n",
          },
          {
            publication_id: "finding-2",
            revision: 1,
            kind: "finding",
            path: "/bodies/f.md",
            content: "note\n",
          },
        ],
        actions: [
          {
            id: "thread:thread-101:r1:reply",
            kind: "thread",
            publication_id: "thread-101",
            operation: "reply",
            command:
              "reviewmatic publication apply --action /actions/a1.json --confirm " + "a".repeat(64),
            path: "src/a.ts",
            line: 3,
          },
          {
            id: "finding:finding-2:r1:create_line",
            kind: "finding",
            publication_id: "finding-2",
            operation: "create_line",
            command:
              "reviewmatic publication apply --action /actions/a2.json --confirm " + "b".repeat(64),
            path: "src/b.ts",
            line: 9,
          },
          {
            id: "labels:update",
            kind: "labels",
            publication_id: null,
            operation: "update_labels",
            command: "x",
            path: null,
            line: null,
          },
        ],
      },
    },
  };
}

test("plan items classify threads, findings, issues, and labels", () => {
  const items = planItems(minimalPlan(temporary()));
  assert.equal(items.length, 4);
  const thread = items.find((item) => item.key === "thread-101");
  assert.equal(thread.kind, "thread");
  assert.equal(thread.path, "src/a.ts");
  assert.equal(thread.line, 3);
  assert.equal(thread.body, "fixed\n");
  assert.equal(thread.actions.length, 1);
  assert.match(thread.url, /#note_101$/);
  assert.match(itemText(thread), /Please fix the retry/);
  assert.match(itemText(thread), /Fixed in the current code/);
  const finding = items.find((item) => item.key === "finding-2");
  assert.equal(finding.kind, "line");
  const issue = items.find((item) => item.key === "issue-3");
  assert.equal(issue.kind, "issue");
  const labels = items.find((item) => item.key === "labels:update");
  assert.equal(labels.kind, "labels");
  assert.deepEqual(labels.detail.add, ["review::approved"]);
});

test("terminal links reject unsafe schemes and controls and long lines are scrollable without loss", () => {
  assert.equal(safeLink("javascript:alert(1)"), null);
  assert.equal(safeLink("https://example.test/\x1b]8;;evil"), null);
  assert.equal(safeLink("https://user:password@example.test/"), null);
  assert.equal(terminalLink("https://example.test/#note_1", false), "https://example.test/#note_1");
  assert.match(terminalLink("https://example.test/#note_1", true), /\x1b\]8;;https:/);
  assert.equal(displayText("hello\x1b]52;c;payload\x07world"), "helloworld");
  const line = "Long source line ".repeat(100);
  assert.equal(visualLines(line, 30).join(""), line);
  assert.ok(visualLines(line, 30).every((row) => row.length <= 30));
});

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
