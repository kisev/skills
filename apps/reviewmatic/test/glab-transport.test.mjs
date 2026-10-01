import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import test from "node:test";
import { commandArgv, makeCommand } from "../dist/publication.js";

test("real glab serializes positioned bodies as nested JSON without bracket fields", async (t) => {
  const root = mkdtempSync(join(tmpdir(), "reviewmatic-transport-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const env = {
    PATH: process.env.PATH,
    HOME: root,
    XDG_CONFIG_HOME: join(root, "config"),
    GLAB_CONFIG_DIR: join(root, "config"),
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    GITLAB_TOKEN: "synthetic-test-token",
    NO_COLOR: "1",
  };
  const run = promisify(execFile);
  const version = await run("glab", ["version"], { env, cwd: root });
  t.diagnostic(version.stdout.trim());
  assert.match(version.stdout, /glab 1\.120\.0\b/);
  const requests = [];
  const server = createServer(async (req, res) => {
    let body = "";
    for await (const chunk of req) body += chunk;
    requests.push({ method: req.method, url: req.url, body: JSON.parse(body) });
    res.writeHead(201, { "Content-Type": "application/json" });
    res.end('{"id":"synthetic"}');
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const host = "gitlab.example";
  mkdirSync(env.GLAB_CONFIG_DIR, { recursive: true });
  writeFileSync(
    join(env.GLAB_CONFIG_DIR, "config.yml"),
    `hosts:\n  ${host}:\n    api_protocol: http\n    api_host: 127.0.0.1:${server.address().port}\n`,
  );
  const repo = join(root, "repo");
  mkdirSync(repo);
  const git = (...args) =>
    execFileSync("git", ["-C", repo, ...args], { env, encoding: "utf8" }).trim();
  git("init", "-q");
  git("config", "user.name", "Fixture");
  git("config", "user.email", "fixture@example.invalid");
  git("config", "commit.gpgsign", "false");
  const path = "file with spaces.txt";
  writeFileSync(join(repo, path), "context\nold\n");
  git("add", ".");
  git("commit", "-qm", "base");
  const base = git("rev-parse", "HEAD");
  writeFileSync(join(repo, path), "context\nnew\n");
  git("commit", "-qam", "head");
  const head = git("rev-parse", "HEAD");
  const body = "Текст 'quoted' \"double\" $(literal)\\path\n\n```suggestion\nvalue\n```\n";
  const bodies = join(root, "artifacts/review_plan/bodies");
  mkdirSync(bodies, { recursive: true });
  writeFileSync(join(bodies, "body.md"), body);
  const evidence = {
    project: { hostname: host, id: 7 },
    target: { iid: 3 },
    base_sha: base,
    head_sha: head,
    object: { diff_refs: { base_sha: base, start_sha: base, head_sha: head } },
    changed_files: { items: [{ old_path: path, new_path: path }] },
  };
  for (const [flag, line, expected] of [
    ["--line", 2, { new_line: 2 }],
    ["--line", 1, { new_line: 1, old_line: 1 }],
    ["--old-line", 2, { old_line: 2 }],
  ]) {
    const command = await makeCommand(
      root,
      evidence,
      { exact_git: { repo_root: repo } },
      "test",
      ["glab", "mr", "note", "create", "3", "--file", path, flag, String(line)],
      {},
      {},
      createHash("sha256").update(body).digest("hex"),
    );
    const argv = commandArgv(command);
    await run(argv[0], argv.slice(1), { env, cwd: root, timeout: 10000 });
    assert.deepEqual(requests.at(-1), {
      method: "POST",
      url: "/api/v4/projects/7/merge_requests/3/discussions",
      body: {
        body,
        position: {
          position_type: "text",
          base_sha: base,
          start_sha: base,
          head_sha: head,
          new_path: path,
          old_path: path,
          ...expected,
        },
      },
    });
    const directRequest = requests.at(-1);
    await run("sh", ["-c", command], { env, cwd: root, timeout: 10000 });
    assert.deepEqual(
      requests.at(-1),
      directRequest,
      "copied shell command matches TUI argv transport",
    );
  }
  const count = requests.length;
  await assert.rejects(
    run(
      "glab",
      [
        "api",
        "--hostname",
        host,
        "--method",
        "POST",
        "projects/7/merge_requests/3/discussions",
        "-f",
        "position[new_line]=2",
      ],
      { env, cwd: root, timeout: 10000 },
    ),
    /bracket/,
  );
  assert.equal(requests.length, count, "invalid fields fail before HTTP");
});
