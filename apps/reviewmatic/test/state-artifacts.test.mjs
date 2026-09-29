import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  StateArtifactError,
  commandWithoutExecutionStatus,
  contentDigest,
  ensurePrivateDirectory,
  executionStatus,
  markerIdentity,
  markerPath,
  markerRun,
  mutationDigest,
  recordSuccess,
  versionedMarkdown,
  xdgStateHome,
} from "../dist/state-artifacts.js";

const DIGEST = "a".repeat(64);

function temporaryDirectory(t) {
  const root = mkdtempSync(join(tmpdir(), "state-artifacts-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function collectFiles(root) {
  const found = [];
  const stack = [root];
  while (stack.length > 0) {
    const current = stack.pop();
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = join(current, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else found.push(full);
    }
  }
  return found;
}

function isStateArtifactError(message) {
  return (error) => {
    assert.ok(error instanceof StateArtifactError);
    assert.match(error.message, message);
    return true;
  };
}

test("versioned markdown retains body-only history and stays idempotent", async (t) => {
  const root = temporaryDirectory(t);
  const stable = join(root, "publication.md");
  const first = Buffer.from("# First\n");
  writeFileSync(stable, await versionedMarkdown(stable, first));

  assert.ok(readFileSync(stable, "utf8").endsWith("\n## History\n\n"));
  const firstSnapshot = join(root, "history", "publication", `${contentDigest(first)}.md`);
  assert.equal(existsSync(firstSnapshot), false);

  writeFileSync(stable, await versionedMarkdown(stable, Buffer.from("# Second\n")));
  assert.ok(readFileSync(stable, "utf8").endsWith(`\n## History\n\n- \`${firstSnapshot}\`\n`));
  assert.ok(readFileSync(firstSnapshot).equals(first));

  const unchanged = await versionedMarkdown(stable, Buffer.from("# Second\n"));
  assert.ok(unchanged.equals(readFileSync(stable)));
  const history = join(root, "history", "publication");
  assert.equal(readdirSync(history).filter((name) => name.endsWith(".md")).length, 1);
});

test("versioned markdown rejects a malformed owned footer", async (t) => {
  const root = temporaryDirectory(t);
  const stable = join(root, "publication.md");
  mkdirSync(join(root, "history", "publication"), { recursive: true });
  writeFileSync(stable, "current\n\n## History\n\nnot a snapshot path\n");

  await assert.rejects(
    versionedMarkdown(stable, Buffer.from("replacement\n")),
    isStateArtifactError(/footer is malformed/),
  );
});

test("versioned markdown rejects a forged history path", async (t) => {
  const root = temporaryDirectory(t);
  const stable = join(root, "publication.md");
  mkdirSync(join(root, "history", "publication"), { recursive: true });
  const forged = `${join(root, "history", "publication")}/../${DIGEST}.md`;
  writeFileSync(stable, `current\n\n## History\n\n- \`${forged}\`\n`);

  await assert.rejects(
    versionedMarkdown(stable, Buffer.from("replacement\n")),
    isStateArtifactError(/history path is invalid/),
  );
});

test("marker runner records only success", async (t) => {
  const root = temporaryDirectory(t);
  const previous = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = join(root, "state");
  t.after(() => {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
  });
  const mutation = ["true"];

  assert.equal(
    await executionStatus(mutation, { skill: "test-skill", action: "publish", binding: DIGEST }),
    "not_run",
  );
  assert.equal(
    await markerRun([
      "marker-run",
      "--skill",
      "test-skill",
      "--action",
      "publish",
      "--binding",
      DIGEST,
      "--",
      ...mutation,
    ]),
    0,
  );
  const markers = collectFiles(join(root, "state")).filter((path) => path.endsWith(".json"));
  assert.equal(markers.length, 1);
  const marker = JSON.parse(readFileSync(markers[0], "utf8"));
  assert.equal(marker.schema, "agent-skills/post-success-marker/v1");
  assert.equal(marker.exit_status, 0);
  assert.equal(statSync(markers[0]).mode & 0o077, 0);
  assert.equal(
    await executionStatus(mutation, { skill: "test-skill", action: "publish", binding: DIGEST }),
    "run_unverified",
  );

  assert.equal(
    await markerRun([
      "marker-run",
      "--skill",
      "test-skill",
      "--action",
      "fail",
      "--binding",
      DIGEST,
      "--",
      "sh",
      "-c",
      "exit 7",
    ]),
    7,
  );
  assert.equal(
    collectFiles(join(root, "state")).filter((path) => path.endsWith(".json")).length,
    1,
  );
});

test("marker runner validates stdin digest format before the mutation", async (t) => {
  const root = temporaryDirectory(t);
  const touched = join(root, "touched");
  await assert.rejects(
    markerRun([
      "marker-run",
      "--skill",
      "test-skill",
      "--action",
      "stdin",
      "--binding",
      DIGEST,
      "--stdin-sha256",
      "zz",
      "--",
      "touch",
      touched,
    ]),
    isStateArtifactError(/stdin digest is invalid/),
  );
  assert.equal(existsSync(touched), false);
});

test("marker runner rejects stdin that does not match its digest", async (t) => {
  const root = temporaryDirectory(t);
  const touched = join(root, "touched");
  const moduleUrl = new URL("../dist/state-artifacts.js", import.meta.url).href;
  const script = [
    `const { markerRun } = await import(${JSON.stringify(moduleUrl)});`,
    `await markerRun([`,
    `"marker-run",`,
    `"--skill", "test-skill",`,
    `"--action", "stdin",`,
    `"--binding", ${JSON.stringify(DIGEST)},`,
    `"--stdin-sha256", ${JSON.stringify("b".repeat(64))},`,
    `"--", "touch", ${JSON.stringify(touched)},`,
    `]);`,
  ].join("\n");
  const result = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    input: Buffer.from("payload"),
    encoding: "utf8",
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /stdin does not match its digest/);
  assert.equal(existsSync(touched), false);
});

test("marker path validates skill, action, and digests", () => {
  assert.throws(
    () => markerPath("Bad Skill", "publish", DIGEST, DIGEST),
    isStateArtifactError(/marker skill is unsafe/),
  );
  assert.throws(
    () => markerPath("test-skill", "", DIGEST, DIGEST),
    isStateArtifactError(/marker action is unsafe/),
  );
  assert.throws(
    () => markerPath("test-skill", "publish", "b".repeat(63), DIGEST),
    isStateArtifactError(/marker digest is invalid/),
  );
  const previous = process.env.XDG_STATE_HOME;
  process.env.XDG_STATE_HOME = "/tmp/state-home";
  try {
    const identity = markerIdentity("test-skill", "publish", DIGEST, DIGEST);
    assert.equal(
      markerPath("test-skill", "publish", DIGEST, DIGEST),
      `/tmp/state-home/agent-skills/post-success/v1/markers/${identity.slice(0, 2)}/${identity}.json`,
    );
  } finally {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
  }
});

test("xdg state home rejects relative and symlinked roots", async (t) => {
  const previous = process.env.XDG_STATE_HOME;
  t.after(() => {
    if (previous === undefined) delete process.env.XDG_STATE_HOME;
    else process.env.XDG_STATE_HOME = previous;
  });
  process.env.XDG_STATE_HOME = "relative-state";
  assert.throws(() => xdgStateHome(), isStateArtifactError(/absolute normalized/));

  const root = temporaryDirectory(t);
  mkdirSync(join(root, "outside"));
  symlinkSync(join(root, "outside"), join(root, "linked"));
  process.env.XDG_STATE_HOME = join(root, "linked");
  await assert.rejects(
    executionStatus(["true"], { skill: "test-skill", action: "symlink", binding: DIGEST }),
    isStateArtifactError(/state directory is unsafe/),
  );
  await assert.rejects(
    recordSuccess("test-skill", "symlink", DIGEST, DIGEST),
    isStateArtifactError(/state directory is unsafe/),
  );
});

test("state directory rejects lexical traversal", async (t) => {
  const root = temporaryDirectory(t);
  const boundary = join(root, "state");
  const target = `${join(boundary, "private")}/../../outside`;
  await assert.rejects(
    ensurePrivateDirectory(target, boundary),
    isStateArtifactError(/normalized/),
  );
});

test("command without execution status strips only the marker line", () => {
  assert.equal(
    commandWithoutExecutionStatus("# execution-status=not_run\nreviewmatic marker-run --skill x"),
    "reviewmatic marker-run --skill x",
  );
  assert.equal(
    commandWithoutExecutionStatus("pre\n# execution-status=run_unverified\nrest"),
    "pre\nrest",
  );
  assert.equal(commandWithoutExecutionStatus("plain"), "plain");
  assert.equal(commandWithoutExecutionStatus(null), null);
});

test("digests match python canonical json byte for byte", async (t) => {
  const argv = ["café", 'quote"x', "back\\slash", "line\nbreak", "tab\ty"];
  const check = spawnSync(
    "python3",
    [
      "-c",
      [
        "import hashlib, json, sys",
        "argv = json.loads(sys.argv[1])",
        "value = {'argv': argv, 'stdin_sha256': None}",
        "listed = ['agent-skills/post-success-marker/v1', 'test-skill', 'publish', sys.argv[2], sys.argv[2]]",
        "print(hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest())",
        "print(hashlib.sha256(json.dumps(listed, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest())",
        "print(hashlib.sha256(json.dumps({'argv': argv, 'stdin_sha256': sys.argv[2]}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest())",
      ].join("\n"),
      JSON.stringify(argv),
      DIGEST,
    ],
    { encoding: "utf8" },
  );
  if (check.error !== undefined || check.status !== 0) {
    t.skip("python3 is unavailable");
    return;
  }
  const [mutation, identity, withStdin] = check.stdout.trim().split("\n");
  assert.equal(mutationDigest(argv, null), mutation);
  assert.equal(markerIdentity("test-skill", "publish", DIGEST, DIGEST), identity);
  assert.equal(mutationDigest(argv, DIGEST), withStdin);
});
