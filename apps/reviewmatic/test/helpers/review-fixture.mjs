import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";

export const FAKE_GLAB = `#!/usr/bin/env node
const { readFileSync, appendFileSync, writeFileSync } = require("node:fs");
const argv = process.argv.slice(2);
const apiIndex = argv.indexOf("api");
if (apiIndex === -1) { process.stderr.write("expected glab api invocation\\n"); process.exit(1); }
const rest = argv.slice(apiIndex + 1);
let endpoint = "";
let method = "GET";
for (let i = 0; i < rest.length; i += 1) {
  if (rest[i] === "--hostname") i += 1;
  else if (rest[i] === "--method") { method = rest[i + 1]; endpoint = rest[i + 2]; i += 2; }
}
const clean = endpoint.split("?")[0];
const config = JSON.parse(readFileSync(process.env.FAKE_GLAB_CONFIG, "utf8"));
if (config.requests) appendFileSync(config.requests, JSON.stringify({ method, endpoint: clean }) + "\\n");
if (method !== "GET") {
  if (config.mutationError) { process.stderr.write(config.mutationError); process.exit(1); }
  const payload = {};
  for (let i = 0; i < rest.length; i += 1) {
    if (rest[i] !== "-F" && rest[i] !== "-f") continue;
    const assignment = rest[++i]; const split = assignment.indexOf("=");
    const key = assignment.slice(0, split), raw = assignment.slice(split + 1);
    payload[key] = raw.startsWith("@") ? readFileSync(raw.slice(1), "utf8") : key === "resolved" ? raw === "true" : raw;
  }
  if (method === "POST" && clean === "projects/19/merge_requests/7/discussions/discussion-42/notes") {
    config.publishedNotes ??= [];
    config.publishedNotes.push({ id: 43 + config.publishedNotes.length, system: false, author: { id: 23, username: "reviewer" }, body: payload.body.trimEnd(), resolved: null, position: null });
  } else if (method === "PUT" && clean === "projects/19/merge_requests/7/discussions/discussion-42") config.resolved = payload.resolved;
  else if (method === "POST" && clean === "projects/19/merge_requests/7/discussions") {
    config.publishedNotes ??= [];
    config.publishedNotes.push({ id: 100 + config.publishedNotes.length, body: payload.body });
  }
  else if (method === "PUT" && clean === "projects/19/merge_requests/7") config.labels = payload.labels.split(",").filter(Boolean);
  else { process.stderr.write("unexpected mutation " + method + " " + clean); process.exit(1); }
  writeFileSync(process.env.FAKE_GLAB_CONFIG, JSON.stringify(config));
  process.stdout.write("{}"); process.exit(0);
}
const discussion = {
  id: "discussion-42", individual_note: false,
  notes: [{ id: 42, system: false, resolvable: true, resolved: config.resolved === true,
    author: { username: "other-reviewer" }, body: config.noteBody ?? "Retry needs an idempotency key",
    position: { head_sha: config.headSha, new_path: config.changedPath, new_line: 2 } }, ...(config.publishedNotes ?? [])],
};
let value = null;
if (clean === "user") value = { id: 23, username: "reviewer" };
else if (clean === "projects/group%2Fproject") value = { id: 19, path_with_namespace: "group/project", default_branch: "main" };
else if (clean === "projects/19/repository/branches/main" || clean === "projects/19/releases" || clean === "projects/19/repository/tags") value = [];
else if (clean.startsWith("projects/19/labels")) value = [
  { name: "ship-ready", description: "semantic-role: change_type; semantic-value: release" },
  { name: "next-compatible", description: "semantic-role: compatibility; semantic-value: minor" },
  { name: "semver::major", description: "Breaking compatibility" },
  { name: "semver::patch", description: "Backward-compatible fix" },
];
else if (clean === "projects/19/merge_requests/7") value = {
  iid: 7, title: "Current merge request title", description: "Current description",
  source_branch: "dev", target_branch: "main", web_url: "https://gitlab.example/group/project/-/merge_requests/7",
  author: { username: "author" }, state: "opened", labels: config.labels ?? [], updated_at: "fresh",
  pipeline: config.mrPipeline,
  latest_build_started_at: config.latestBuildStartedAt,
  latest_build_finished_at: config.latestBuildFinishedAt,
  diff_refs: { base_sha: config.baseSha, start_sha: config.startSha, head_sha: config.headSha },
};
else if (clean === "projects/19/merge_requests/7/changes") value = {
  changes: [{ old_path: config.changedPath, new_path: config.changedPath }],
  diff_refs: { base_sha: config.baseSha, start_sha: config.startSha, head_sha: config.headSha },
};
else if (clean === "projects/19/merge_requests/7/commits") value = [{ id: config.headSha }];
else if (clean === "projects/19/merge_requests/7/pipelines") value = [{ id: 1, sha: config.headSha, status: config.pipelineStatus ?? "success" }];
else if (clean === "projects/19/pipelines/1/jobs" || clean === "projects/19/pipelines/1/bridges" || clean === "projects/19/merge_requests/7/notes") value = [];
else if (clean === "projects/19/merge_requests/7/discussions") value = [discussion];
if (value === null) { process.stderr.write("unexpected GET " + clean + "\\n"); process.exit(1); }
process.stdout.write(JSON.stringify(value));
`;

export function reviewFixture(t, overrides = {}) {
  const tmp = mkdtempSync(join(tmpdir(), "reviewmatic-fixture-"));
  const keys = ["XDG_STATE_HOME", "PATH", "FAKE_GLAB_CONFIG"];
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  t.after(() => {
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key];
      else process.env[key] = previous[key];
    }
    rmSync(tmp, { recursive: true, force: true });
  });
  const repo = join(tmp, "repository");
  mkdirSync(repo);
  const git = (...args) => execFileSync("git", ["-C", repo, ...args], { encoding: "utf8" }).trim();
  git("init", "--quiet");
  git("config", "commit.gpgsign", "false");
  git("config", "user.email", "reviewer@example.invalid");
  git("config", "user.name", "Example Reviewer");
  writeFileSync(join(repo, "review.txt"), "base\n");
  git("add", "review.txt");
  git("commit", "-qm", "base");
  const baseSha = git("rev-parse", "HEAD");
  writeFileSync(join(repo, "review.txt"), "base\nreviewed change\n");
  git("commit", "-qam", "change");
  const headSha = git("rev-parse", "HEAD");
  const bin = join(tmp, "bin");
  mkdirSync(bin);
  writeFileSync(join(bin, "glab"), FAKE_GLAB);
  chmodSync(join(bin, "glab"), 0o755);
  const requests = join(tmp, "requests.log");
  writeFileSync(requests, "");
  const config = {
    baseSha,
    startSha: baseSha,
    headSha,
    changedPath: "review.txt",
    requests,
    ...overrides,
  };
  const configPath = join(tmp, "glab-config.json");
  writeFileSync(configPath, JSON.stringify(config));
  process.env.XDG_STATE_HOME = join(tmp, "state");
  process.env.FAKE_GLAB_CONFIG = configPath;
  process.env.PATH = `${bin}:${previous.PATH}`;
  return {
    tmp,
    repo,
    git,
    config,
    configPath,
    headSha,
    baseSha,
    url: "https://gitlab.example/group/project/-/merge_requests/7",
    requestCount: () => readFileSync(requests, "utf8").trim().split("\n").filter(Boolean).length,
  };
}

export function completeDraft(draft, result) {
  draft.run_id = "primary-run";
  draft.session_id = "primary-session";
  draft.critics = [
    {
      ...result.critic_receipt_template,
      run_id: "critic-run",
      session_id: "child-session",
      findings: [],
    },
  ];
  const content = draft.content;
  content.summary = "The bounded change meets the agreed contract.";
  content.architecture_assessment = "Existing ownership is preserved.";
  content.chat_assessment = {
    necessity: { status: "supported", rationale: "The existing timeout is unbounded." },
    relevance: { status: "current", rationale: "The current runner uses this path." },
    change: "Bound the check.",
  };
  content.semver_impact = "patch";
  content.semver_rationale = "Backward-compatible correction.";
  content.checks = ["Inspected the exact committed diff; external tests were not run."];
  for (const value of Object.values(content.mr_metadata_assessment)) {
    value.status = "ok";
    value.rationale = "The observed metadata is sufficient.";
  }
  for (const value of content.label_assessments) {
    value.status = value.name === "semver::patch" ? "applicable" : "inapplicable";
    value.rationale = "Matches the assessed patch contribution.";
  }
  const semver = content.semver_assessment;
  semver.policy = "No publication configuration is available.";
  semver.sources = ["Fixture repository and empty release catalog"];
  semver.fallback_reason = "No published release can be established.";
  for (const thread of content.thread_decisions) {
    thread.assessment = "fixed";
    thread.rationale = "The exact reviewed code already addresses the remark.";
    thread.outcome = thread.state === "resolved" ? "no_publication" : "resolve";
    thread.proposed_response =
      thread.state === "resolved" ? null : "The exact reviewed code now handles this path.";
  }
  assert.equal(content.finding_publications.length, 0);
  return draft;
}
