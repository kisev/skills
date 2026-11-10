"""Draft-note generation is one head-checked, publish-free shell block."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from reviewmatic import drafts
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from pathlib import Path

HEAD = "a" * 40
BASE = "b" * 40
START = "c" * 40


def payload(**overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "hostname": "gitlab.example.com",
        "project_id": 7,
        "mr_iid": 3,
        "head_sha": HEAD,
        "findings": [
            {
                "old_path": "a.py",
                "new_path": "a.py",
                "new_line": 12,
                "base_sha": BASE,
                "start_sha": START,
                "body": "A positioned finding.",
            },
            {
                "old_path": "b.py",
                "new_path": "b.py",
                "old_line": 4,
                "base_sha": BASE,
                "start_sha": START,
                "body": "A deletion finding.",
            },
        ],
        "general_notes": ["A general note with an apostrophe's escape."],
        "discussion_replies": [{"discussion_id": "disc-1", "body": "A reply."}],
    }
    data.update(overrides)
    return data


def test_the_block_starts_with_the_head_check() -> None:
    shell = drafts.build_drafts(payload())["shell"]
    assert shell.splitlines()[0] == "set -eu"
    assert f"reviewed_head='{HEAD}'" in shell
    assert "current_head=$(glab api" in shell
    assert "--jq '.sha'" in shell
    assert "exit 1" in shell


def test_positioned_general_and_reply_commands_are_generated() -> None:
    result = drafts.build_drafts(payload())
    shell = result["shell"]
    assert result["positioned"] == 2
    assert result["general"] == 1
    assert result["replies"] == 1
    assert "position[position_type]=text" in shell
    assert "position[new_line]=12" in shell
    assert "position[old_line]=4" in shell
    assert "in_reply_to_discussion_id=disc-1" in shell
    assert "'\\''" in shell


def test_no_publish_command_exists() -> None:
    shell = drafts.build_drafts(payload())["shell"]
    assert "--method PUT" not in shell
    assert "/notes" not in shell
    assert "publish" not in shell.lower()


def test_a_reply_falls_back_to_a_general_draft_when_unsupported() -> None:
    shell = drafts.build_drafts(payload(draft_reply_support=False))["shell"]
    assert "in_reply_to_discussion_id" not in shell
    assert shell.count("projects/7/merge_requests/3/drafts") == 4


@pytest.mark.parametrize(
    "override",
    [
        {"hostname": "https://evil.example.com"},
        {"project_id": "7"},
        {"mr_iid": 0},
        {"head_sha": "not-a-sha"},
        {"findings": [{"body": ""}]},
        {"findings": [{"old_path": "a.py", "new_path": "a.py", "new_line": 1, "base_sha": "x"}]},
    ],
)
def test_invalid_input_is_rejected(override: dict[str, object]) -> None:
    with pytest.raises(contract.WorkflowError):
        drafts.build_drafts(payload(**override))


def fake_glab(tmp_path: Path, current_head: str) -> tuple[Path, Path]:
    log = tmp_path / "calls.log"
    script = tmp_path / "glab"
    script.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> {log}\n"
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "POST" ]; then echo \'{"id":1}\'; exit 0; fi\n'
        "done\n"
        f"echo '{current_head}'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, log


def run_block(shell: str, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(
        ["sh", "-c", shell], capture_output=True, text=True, check=False, env=environment
    )


def test_a_moved_head_stops_before_creating_a_draft(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_glab(bin_dir, "d" * 40)
    completed = run_block(drafts.build_drafts(payload())["shell"], bin_dir)
    assert completed.returncode == 1
    assert "head moved" in completed.stderr
    assert "POST" not in log.read_text(encoding="utf-8")


def test_the_unchanged_head_creates_every_draft(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_glab(bin_dir, HEAD)
    completed = run_block(drafts.build_drafts(payload())["shell"], bin_dir)
    assert completed.returncode == 0
    calls = log.read_text(encoding="utf-8")
    assert calls.count("POST") == 4
