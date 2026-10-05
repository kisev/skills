"""Workflow dispatch regressions, ported from ``workflow.test.mjs``."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

import pytest

from reviewmatic import workflow
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from pathlib import Path


def _args(**values: object) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_workflow_dispatch_rejects_out_of_order_commands_with_exact_stage_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    root = tmp_path / "agent-skills" / "gitlab" / ("d" * 32)
    with pytest.raises(contract.WorkflowError) as raised:
        workflow.dispatch(_args(command="finalize", artifact_root=str(root)))
    assert str(raised.value) == "review command is out of order; current stage is prepared"

    capsys.readouterr()
    assert workflow.dispatch(_args(command="status", artifact_root=str(root))) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "incomplete"
    assert payload["stage"] == "stale"
    assert payload["resume_stage"] == "prepared"
    assert workflow.dispatch(_args(command="next", artifact_root=str(root))) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "stale"


def test_workflow_dispatch_leaves_contract_owned_commands_to_the_caller() -> None:
    for command in (
        "prepare",
        "prepare-local",
        "finalize-local",
        "assess-mode",
        "publication",
        "marker-run",
        "unknown-command",
    ):
        assert workflow.dispatch(_args(command=command)) is None
