from __future__ import annotations

import errno
import hashlib
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "handoff" / "scripts" / "handoff.py"
MAX_HANDOFF_BYTES = 256 * 1024
SESSION = "ses_default"


def load_handoff_without_fcntl(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setitem(sys.modules, "fcntl", None)
    spec = importlib.util.spec_from_file_location("handoff_without_fcntl", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_handoff() -> Any:
    spec = importlib.util.spec_from_file_location("handoff_for_test", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_handoff(
    command: str,
    workspace: Path,
    state: Path,
    *,
    content: bytes | None = None,
    expected_path: Path | None = None,
    session: str | None = SESSION,
) -> subprocess.CompletedProcess[bytes]:
    environment = {**os.environ, "XDG_STATE_HOME": str(state)}
    arguments = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(RUNNER),
        command,
        "--workspace",
        str(workspace),
    ]
    if session is not None:
        arguments.extend(["--session", session])
    if command == "write":
        if expected_path is None:
            preview = run_handoff("path", workspace, state, session=session)
            if preview.returncode != 0:
                return preview
            expected_path = Path(preview.stdout.decode().strip())
        arguments.extend(["--expected-path", str(expected_path)])
    return subprocess.run(
        arguments,
        input=content,
        capture_output=True,
        check=False,
        env=environment,
    )


def test_path_is_stable_canonical_workspace_scoped_and_read_only(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    state = tmp_path / "state"

    direct = run_handoff("path", workspace, state)
    through_alias = run_handoff("path", alias, state)

    assert direct.returncode == 0, direct.stderr.decode()
    assert through_alias.returncode == 0, through_alias.stderr.decode()
    assert direct.stdout == through_alias.stdout
    destination = Path(direct.stdout.decode().strip())
    assert destination.parent.parent.parent.name == "handoff"
    assert destination.parent.parent.parent.parent.name == "agent-skills"
    assert destination.name == "handoff.md"
    assert destination.parent.name == SESSION
    assert len(destination.parent.parent.name) == 64
    assert not state.exists()


def test_path_scopes_destination_per_session(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    first = run_handoff("path", workspace, state, session="ses_alpha")
    second = run_handoff("path", workspace, state, session="ses_beta")
    repeat = run_handoff("path", workspace, state, session="ses_alpha")

    assert first.returncode == second.returncode == repeat.returncode == 0
    alpha = Path(first.stdout.decode().strip())
    beta = Path(second.stdout.decode().strip())
    assert alpha == Path(repeat.stdout.decode().strip())
    assert alpha != beta
    assert alpha.parent.name == "ses_alpha"
    assert beta.parent.name == "ses_beta"
    assert alpha.parent.parent == beta.parent.parent
    assert not state.exists()


def test_path_rejects_missing_workspace_without_creating_state(tmp_path: Path) -> None:
    state = tmp_path / "state"

    result = run_handoff("path", tmp_path / "missing", state)

    assert result.returncode == 2
    assert "existing path" in result.stderr.decode()
    assert not state.exists()


def test_missing_fcntl_returns_controlled_handoff_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = load_handoff_without_fcntl(monkeypatch)

    with pytest.raises(handoff.HandoffError, match="requires POSIX fcntl"):
        handoff.atomic_write(tmp_path / "handoff.md", 1, b"approved\n")

    assert not (tmp_path / "handoff.md").exists()


def test_lock_contention_retries_until_bounded_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = load_handoff()

    class ContendedLocking:
        LOCK_EX = 2
        LOCK_NB = 4

        def __init__(self) -> None:
            self.operations: list[int] = []

        def flock(self, _descriptor: int, operation: int) -> None:
            self.operations.append(operation)
            raise BlockingIOError(errno.EAGAIN, "contended")

    class Clock:
        now = 10.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    locking = ContendedLocking()
    clock = Clock()
    monkeypatch.setattr(handoff, "fcntl", locking)
    monkeypatch.setattr(handoff, "time", clock)
    monkeypatch.setattr(handoff, "LOCK_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(handoff, "LOCK_RETRY_SECONDS", 0.04)
    directory = os.open(tmp_path, os.O_RDONLY)
    try:
        with pytest.raises(handoff.HandoffError, match="timed out waiting"):
            handoff.lock_handoff_directory(directory)
    finally:
        os.close(directory)

    assert len(locking.operations) == 4
    assert set(locking.operations) == {locking.LOCK_EX | locking.LOCK_NB}
    assert clock.now == pytest.approx(10.1)


def test_hard_linked_lock_is_rejected_before_chmod_or_flock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = load_handoff()
    lock_path = tmp_path / ".handoff.lock"
    lock_path.touch(mode=0o600)
    os.link(lock_path, tmp_path / "linked-lock")
    operations: list[int] = []
    chmod_calls: list[tuple[int, int]] = []

    class UnexpectedLocking:
        LOCK_EX = 2
        LOCK_NB = 4

        def flock(self, _descriptor: int, operation: int) -> None:
            operations.append(operation)

    def record_fchmod(descriptor: int, mode: int) -> None:
        chmod_calls.append((descriptor, mode))

    monkeypatch.setattr(handoff, "fcntl", UnexpectedLocking())
    monkeypatch.setattr(handoff.os, "fchmod", record_fchmod)
    directory = os.open(tmp_path, os.O_RDONLY)
    try:
        with pytest.raises(handoff.HandoffError, match="handoff lock is unsafe"):
            handoff.lock_handoff_directory(directory)
    finally:
        os.close(directory)

    assert chmod_calls == []
    assert operations == []


def test_write_privately_creates_and_atomically_replaces_handoff(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    first = run_handoff("write", workspace, state, content=b"# First\n")
    assert first.returncode == 0, first.stderr.decode()
    destination = Path(first.stdout.decode().strip())
    first_inode = destination.stat().st_ino
    second = run_handoff("write", workspace, state, content=b"# Second\n")

    assert second.returncode == 0, second.stderr.decode()
    assert second.stdout == first.stdout
    content = destination.read_text()
    assert content.startswith("# Second\n\n## History\n\n")
    snapshots = list((destination.parent / "history" / "handoff").glob("*.md"))
    assert {path.read_bytes() for path in snapshots} == {b"# First\n"}
    assert destination.stat().st_ino != first_inode
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    for directory in (
        destination.parent,
        destination.parent.parent,
        destination.parent.parent.parent,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert not list(destination.parent.glob(".handoff.*.tmp"))


def test_retired_stopit_state_is_never_read_migrated_or_removed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    legacy_id = "0" * 64
    state.mkdir(mode=0o700)
    legacy = state / "agent-skills" / "stopit" / legacy_id / "handoff.md"
    legacy.parent.mkdir(parents=True)
    for directory in (
        state,
        state / "agent-skills",
        state / "agent-skills" / "stopit",
        legacy.parent,
    ):
        directory.chmod(0o700)
    legacy.write_bytes(b"# Legacy stopit handoff\n")
    legacy_before = legacy.read_bytes()

    destination = Path(run_handoff("path", workspace, state).stdout.decode().strip())
    result = run_handoff("write", workspace, state, content=b"# First handoff\n")

    assert result.returncode == 0, result.stderr.decode()
    assert destination.parent.parent.parent.name == "handoff"
    assert destination.parent.parent.name != legacy_id
    assert destination.parent.name == SESSION
    current = destination.read_text(encoding="utf-8")
    assert current.startswith("# First handoff\n")
    assert "Legacy stopit handoff" not in current
    assert destination.read_text(encoding="utf-8").count("## History") == 1
    assert legacy.read_bytes() == legacy_before
    assert {entry.name for entry in (state / "agent-skills").iterdir()} == {
        "handoff",
        "stopit",
    }


def test_concurrent_writes_retain_every_handoff_version(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    expected_path = Path(run_handoff("path", workspace, state).stdout.decode().strip())
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(RUNNER),
                "write",
                "--workspace",
                str(workspace),
                "--session",
                SESSION,
                "--expected-path",
                str(expected_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "XDG_STATE_HOME": str(state)},
        )
        for _ in range(8)
    ]
    bodies = [f"# Handoff {index}\n".encode() for index in range(len(processes))]
    results = [process.communicate(body) for process, body in zip(processes, bodies, strict=True)]

    assert all(process.returncode == 0 for process in processes), results
    current = expected_path.read_bytes()
    snapshots = (expected_path.parent / "history" / "handoff").glob("*.md")
    retained = {path.read_bytes() for path in snapshots}
    retained.add(current.split(b"\n## History\n", 1)[0])
    assert retained == set(bodies)


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"", "must not be empty"),
        (b" \n\t", "must not be empty"),
        (b"\xff", "valid UTF-8"),
        (b"x" * (MAX_HANDOFF_BYTES + 1), "exceeds"),
    ],
    ids=("empty", "whitespace", "invalid-utf8", "oversized"),
)
def test_write_rejects_invalid_content_without_creating_state(
    tmp_path: Path, content: bytes, error: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    result = run_handoff("write", workspace, state, content=content)

    assert result.returncode == 2
    assert error in result.stderr.decode()
    assert not state.exists()


@pytest.mark.parametrize("command", ["path", "write"])
def test_commands_reject_symlinked_state_components(tmp_path: Path, command: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    (state / "agent-skills").symlink_to(outside, target_is_directory=True)

    result = run_handoff(command, workspace, state, content=b"approved\n")

    assert result.returncode == 2
    assert "unsafe" in result.stderr.decode()
    assert not (outside / "handoff").exists()


def test_write_rejects_symlink_handoff_without_changing_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    reported = run_handoff("path", workspace, state)
    destination = Path(reported.stdout.decode().strip())
    destination.parent.mkdir(parents=True, mode=0o700)
    for directory in (
        state / "agent-skills",
        state / "agent-skills" / "handoff",
        destination.parent.parent,
    ):
        directory.chmod(0o700)
    target = tmp_path / "target.md"
    target.write_text("keep\n", encoding="utf-8")
    destination.symlink_to(target)

    result = run_handoff("write", workspace, state, content=b"replace\n")

    assert result.returncode == 2
    assert "unsafe" in result.stderr.decode()
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_write_rejects_workspace_changed_after_resolution(tmp_path: Path) -> None:
    first_workspace = tmp_path / "first"
    first_workspace.mkdir()
    second_workspace = tmp_path / "second"
    second_workspace.mkdir()
    alias = tmp_path / "workspace"
    alias.symlink_to(first_workspace, target_is_directory=True)
    state = tmp_path / "state"
    preview = run_handoff("path", alias, state)
    expected_path = Path(preview.stdout.decode().strip())
    alias.unlink()
    alias.symlink_to(second_workspace, target_is_directory=True)

    result = run_handoff("write", alias, state, content=b"approved\n", expected_path=expected_path)

    assert result.returncode == 2
    assert "changed after resolution" in result.stderr.decode()
    assert not state.exists()


@pytest.mark.parametrize(
    "session",
    ["", "ses_", "ses", "session-1", "../x", "/abs", "a/b", "ses_a/b", "ses_x y"],
    ids=[
        "empty",
        "bare-prefix",
        "missing-prefix",
        "wrong-prefix",
        "traversal",
        "absolute",
        "nested",
        "nested-after-prefix",
        "whitespace",
    ],
)
@pytest.mark.parametrize("command", ["path", "write"])
def test_invalid_session_fails_without_creating_state(
    tmp_path: Path, command: str, session: str
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    result = run_handoff(
        command,
        workspace,
        state,
        content=b"approved\n",
        expected_path=tmp_path / "unused.md",
        session=session,
    )

    assert result.returncode == 2
    assert "session" in result.stderr.decode()
    assert not state.exists()


@pytest.mark.parametrize("command", ["path", "write"])
def test_commands_require_session_without_creating_state(tmp_path: Path, command: str) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    result = run_handoff(
        command,
        workspace,
        state,
        content=b"approved\n",
        expected_path=tmp_path / "unused.md",
        session=None,
    )

    assert result.returncode == 2
    assert "--session" in result.stderr.decode()
    assert not state.exists()


def test_sessions_keep_independent_files_and_histories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"

    alpha_first = run_handoff(
        "write", workspace, state, content=b"# Alpha one\n", session="ses_alpha"
    )
    beta_first = run_handoff("write", workspace, state, content=b"# Beta one\n", session="ses_beta")
    alpha_second = run_handoff(
        "write", workspace, state, content=b"# Alpha two\n", session="ses_alpha"
    )

    assert alpha_first.returncode == beta_first.returncode == alpha_second.returncode == 0
    alpha = Path(alpha_second.stdout.decode().strip())
    beta = Path(beta_first.stdout.decode().strip())
    assert alpha != beta

    alpha_body, _, alpha_footer = alpha.read_text(encoding="utf-8").partition("\n## History\n")
    beta_body, _, beta_footer = beta.read_text(encoding="utf-8").partition("\n## History\n")
    assert alpha_body == "# Alpha two\n"
    assert beta_body == "# Beta one\n"
    assert [line for line in alpha_footer.strip().splitlines() if line]
    assert not [line for line in beta_footer.strip().splitlines() if line]

    alpha_snapshots = (alpha.parent / "history" / "handoff").glob("*.md")
    assert {path.read_bytes() for path in alpha_snapshots} == {b"# Alpha one\n"}
    assert list((beta.parent / "history" / "handoff").glob("*.md")) == []


def test_session_runs_never_touch_the_legacy_workspace_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    workspace_id = hashlib.sha256(os.fsencode(workspace.resolve())).hexdigest()
    legacy = state / "agent-skills" / "handoff" / workspace_id / "handoff.md"
    legacy.parent.mkdir(parents=True, mode=0o700)
    for directory in (
        state,
        state / "agent-skills",
        state / "agent-skills" / "handoff",
        legacy.parent,
    ):
        directory.chmod(0o700)
    legacy.write_bytes(b"# Legacy workspace handoff\n")
    legacy_before = legacy.read_bytes()

    reported = run_handoff("path", workspace, state, session="ses_current")
    result = run_handoff(
        "write", workspace, state, content=b"# Current session\n", session="ses_current"
    )

    assert reported.returncode == 0, reported.stderr.decode()
    assert result.returncode == 0, result.stderr.decode()
    destination = Path(reported.stdout.decode().strip())
    assert destination != legacy
    assert destination.parent.name == "ses_current"
    assert destination.read_text(encoding="utf-8").startswith("# Current session\n")
    assert "Legacy workspace handoff" not in destination.read_text(encoding="utf-8")
    assert legacy.read_bytes() == legacy_before


class RecordingInbox:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def entry_lines(self, texts: list[str], *, source: str, key: str) -> list[str]:
        self.keys.append(key)
        return [f"- {text} <!-- source: {source} --> <!-- key: {key} -->" for text in texts]

    def drop_memory(self, lines: list[str], source: str) -> None:
        assert lines and source == "handoff"


def test_distillate_key_is_scoped_to_workspace_and_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = load_handoff()
    inbox = RecordingInbox()
    monkeypatch.setattr(handoff, "_load_inbox", lambda: inbox)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    handoff._drop_memory_distillate(workspace, "ses_alpha", b"# Alpha one\n")
    handoff._drop_memory_distillate(workspace, "ses_beta", b"# Beta one\n")
    handoff._drop_memory_distillate(workspace, "ses_alpha", b"# Alpha two\n")

    assert len(inbox.keys) == 3
    assert inbox.keys[0] == inbox.keys[2]
    assert inbox.keys[0] != inbox.keys[1]
    assert handoff.distillate_key(workspace, "ses_alpha") != handoff.distillate_key(
        other, "ses_alpha"
    )

    helper = ROOT / "shared" / "references" / "memomatic_inbox.py"
    spec = importlib.util.spec_from_file_location("memomatic_inbox_keycheck", helper)
    assert spec is not None and spec.loader is not None
    memomatic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memomatic)
    for key in {*inbox.keys, handoff.distillate_key(workspace, "ses_alpha")}:
        assert memomatic.KEY_PATTERN.fullmatch(key)
