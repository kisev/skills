from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "shared/references/documentation_review.py"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "source.py").write_text("value = 1\n")
    (root / "guide.md").write_text(
        '---\nreview: {"components": ["demo"], "sources": ["source.py"], "contracts": []}\n---\n# Guide\n'
    )
    return root


def run(root: Path, *args: str, expected: int = 0) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(RUNNER), *args, "--root", str(root)],
        env={**os.environ, "XDG_STATE_HOME": str(root.parent / "private")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected, result.stderr + result.stdout
    return cast("dict[str, Any]", json.loads(result.stdout))


def finish(
    root: Path,
    prepared: dict[str, Any],
    *,
    unverified: bool = False,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    report = root.parent / "report.json"
    report.write_text(
        json.dumps(
            {
                "checked": [] if unverified else ["guide.md"],
                "unverified": ["guide.md"] if unverified else [],
                "findings": findings or [],
                "decisions": [],
                "impact": dict.fromkeys(
                    prepared["unmapped"],
                    "Checked against the guide; no additional contract changed.",
                ),
                "critic": {"status": "complete", "session": "independent"},
                "checks": [
                    {
                        "required": True,
                        "status": "passed",
                        "evidence": "Compared the documented value with source.py.",
                    }
                ],
            }
        )
    )
    return run(root, "finalize", "--record", prepared["record"], "--report", str(report))


def test_review_reuses_evidence_and_detects_new_unmapped_sources(workspace: Path) -> None:
    first = run(workspace, "prepare", "--session", "primary")
    assert first["mode"] == "full"
    finish(workspace, first)
    assert run(workspace, "prepare", "--session", "next")["mode"] == "unchanged"
    (workspace / "source.py").write_text("value = 2\n")
    (workspace / "new.py").write_text("new_behavior = True\n")
    changed = run(workspace, "prepare", "--session", "next")
    assert changed["mode"] == "incremental"
    assert changed["selected"] == ["guide.md"]
    assert "new.py" in changed["unmapped"]


def test_unverified_scope_survives_unchanged_review(workspace: Path) -> None:
    result = finish(workspace, run(workspace, "prepare", "--session", "primary"), unverified=True)
    assert result["outcome"] == "partial"
    same = run(workspace, "prepare", "--session", "next")
    assert same["selected"] == ["guide.md"]


def test_stale_review_cannot_be_finalized(workspace: Path) -> None:
    prepared = run(workspace, "prepare", "--session", "primary")
    report = workspace.parent / "report.json"
    report.write_text("{}")
    (workspace / "source.py").write_text("changed\n")
    result = run(
        workspace, "finalize", "--record", prepared["record"], "--report", str(report), expected=2
    )
    assert "evidence changed" in result["message"]


def test_metadata_does_not_accept_missing_contract_or_external_path(workspace: Path) -> None:
    for contract in ("missing.md", "../secret.md"):
        (workspace / "guide.md").write_text(
            "---\nreview: "
            + json.dumps(
                {"components": ["demo"], "sources": ["source.py"], "contracts": [contract]}
            )
            + "\n---\n# Guide\n"
        )
        assert run(workspace, "check", expected=2)["status"] == "error"


def test_previous_findings_cannot_disappear(workspace: Path) -> None:
    finding = {
        "id": "D1",
        "status": "accepted_risk",
        "evidence": "User accepted the documented limitation.",
    }
    finish(workspace, run(workspace, "prepare", "--session", "primary"), findings=[finding])
    prepared = run(workspace, "prepare", "--session", "next")
    report = workspace.parent / "report.json"
    prior = json.loads(report.read_text())
    prior["findings"] = []
    prior["impact"] = {}
    report.write_text(json.dumps(prior))
    result = run(
        workspace, "finalize", "--record", prepared["record"], "--report", str(report), expected=2
    )
    assert "retain their IDs" in result["message"]


def test_missing_full_review_critic_remains_required_on_unchanged_evidence(workspace: Path) -> None:
    prepared = run(workspace, "prepare", "--session", "primary")
    report = workspace.parent / "report.json"
    body = {
        "checked": ["guide.md"],
        "unverified": [],
        "findings": [],
        "decisions": [],
        "impact": {},
        "checks": [],
        "critic": {"status": "not_checked"},
    }
    report.write_text(json.dumps(body))
    first = run(workspace, "finalize", "--record", prepared["record"], "--report", str(report))
    assert first["outcome"] == "partial"
    repeated = run(workspace, "prepare", "--session", "next")
    assert repeated["mode"] == "unchanged"
    assert repeated["critic_required"] is True
    body["critic"] = {"status": "not_required"}
    report.write_text(json.dumps(body))
    result = run(workspace, "finalize", "--record", repeated["record"], "--report", str(report))
    assert result["outcome"] == "partial"
