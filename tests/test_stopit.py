from __future__ import annotations

import errno
import importlib.util
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "stopit" / "scripts" / "handoff.py"
MAX_HANDOFF_BYTES = 256 * 1024


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
    if command == "write":
        if expected_path is None:
            preview = run_handoff("path", workspace, state)
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
    assert destination.parent.parent.name == "stopit"
    assert destination.parent.parent.parent.name == "agent-skills"
    assert destination.name == "handoff.md"
    assert len(destination.parent.name) == 64
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
            handoff.lock_workspace(directory)
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
            handoff.lock_workspace(directory)
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
    assert not (outside / "stopit").exists()


def test_write_rejects_symlink_handoff_without_changing_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    reported = run_handoff("path", workspace, state)
    destination = Path(reported.stdout.decode().strip())
    destination.parent.mkdir(parents=True, mode=0o700)
    for directory in (state / "agent-skills", state / "agent-skills" / "stopit"):
        directory.chmod(0o700)
    target = tmp_path / "target.md"
    target.write_text("keep\n", encoding="utf-8")
    destination.symlink_to(target)

    result = run_handoff("write", workspace, state, content=b"replace\n")

    assert result.returncode == 2
    assert "unsafe" in result.stderr.decode()
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_write_rejects_workspace_changed_after_preview(tmp_path: Path) -> None:
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
    assert "changed after confirmation" in result.stderr.decode()
    assert not state.exists()
