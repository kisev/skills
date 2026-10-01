import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";
import { startReview, finishReview } from "../dist/draft.js";
import { readJson, writeJson } from "../dist/contract.js";
import { reviewFixture, completeDraft } from "./helpers/review-fixture.mjs";

test(
  "real CLI under CI prints without a TTY and supports interactive PTY review without publication",
  { skip: process.platform === "win32" },
  async (t) => {
    const fixture = reviewFixture(t, { resolved: true });
    const started = await startReview({ url: fixture.url, repoRoot: fixture.repo });
    writeJson(started.draft_path, completeDraft(readJson(started.draft_path), started));
    assert.equal((await finishReview(started.draft_path)).status, "ok");
    const requests = fixture.requestCount();
    const cli = new URL("../dist/cli.js", import.meta.url).pathname;
    const env = { ...process.env, CI: "true" };
    const printed = spawnSync(
      process.execPath,
      [cli, "plan", "--artifact-root", started.artifact_root],
      { encoding: "utf8", env, timeout: 5000 },
    );
    assert.equal(printed.status, 0, printed.stdout + printed.stderr);
    assert.match(printed.stdout, /reviewmatic/);
    assert.match(printed.stdout, /Retry needs an idempotency key/);
    const script = `
import os, pty, fcntl, termios, struct, subprocess, select, time, sys
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 90, 0, 0))
env = dict(os.environ, TERM='xterm-256color', FORCE_COLOR='0')
child = subprocess.Popen([sys.argv[1], sys.argv[2], 'plan', '--artifact-root', sys.argv[3]], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
os.close(slave)
data = b''
def until(expected):
    global data
    start = len(data)
    deadline = time.monotonic() + 8
    while expected not in data[start:]:
        if time.monotonic() > deadline:
            raise AssertionError('missing terminal frame: ' + repr(expected) + '\\n' + data.decode(errors='replace'))
        ready, _, _ = select.select([master], [], [], 0.1)
        if ready:
            try: data += os.read(master, 65536)
            except OSError: raise AssertionError('terminal exited before expected frame')
try:
    until(b'reviewmatic')
    deadline = time.monotonic() + 8
    while termios.tcgetattr(master)[3] & termios.ICANON:
        if time.monotonic() > deadline: raise AssertionError('stdin did not enter raw mode')
        select.select([], [], [], 0.02)
    os.write(master, b'\\r')
    until(b'Retry needs an idempotency key')
    assert b'\\x1b]8;;https://gitlab.example/' in data
    assert b'#note_42' in data
    os.write(master, b'\\x1b')
    until(b'select')
    os.write(master, b'q')
    assert child.wait(timeout=5) == 0
    print('PTY: discussion content, OSC 8 link, Escape/back, quit; no publication')
finally:
    if child.poll() is None: child.kill(); child.wait()
    os.close(master)
`;
    const result = spawnSync(
      "python3",
      ["-c", script, process.execPath, cli, started.artifact_root],
      { encoding: "utf8", env, timeout: 25000 },
    );
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /PTY: discussion content/);
    assert.equal(fixture.requestCount(), requests);
    assert.equal(readFileSync(fixture.configPath, "utf8"), JSON.stringify(fixture.config));
  },
);
