from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "stopit" / "scripts" / "handoff.py"
MAX_HANDOFF_BYTES = 256 * 1024


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
    assert destination.read_bytes() == b"# Second\n"
    assert destination.stat().st_ino != first_inode
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    for directory in (
        destination.parent,
        destination.parent.parent,
        destination.parent.parent.parent,
    ):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert not list(destination.parent.glob(".handoff.*.tmp"))


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
