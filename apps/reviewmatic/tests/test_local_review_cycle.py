"""Local WIP review cycle end-to-end, from local-review.test.mjs.

Covers: the initial full review, the unchanged second preparation, the
incremental delta with unstaged and untracked sections, fixing a finding to
reach ready, and prepare-local without --ref keeping the working tree intact.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract


@pytest.fixture(name="repo")
def local_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "commit.gpgsign", "false")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (repo / "renderer.txt").write_text("base\n")
    git("add", ".")
    git("commit", "-qm", "base")
    (repo / "renderer.txt").write_text("broken\n")
    return repo


def _prepare(repo: Path, incremental: str = "auto") -> tuple[Path, str, dict[str, Any]]:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    root = str(bundle["artifact_root"])
    bundle_path, digest = contract.write_artifact(Path(root), "local_wip_snapshot", bundle)
    followup = local_review.prepare_followup(root, bundle, digest, incremental)
    return bundle_path, digest, followup


def _report_payload(evidence_digest: str) -> dict[str, Any]:
    return {
        "evidence_digest": evidence_digest,
        "previous_review_digest": None,
        "mode": "full",
        "task": {
            "goal": "Link plain text without modifying mixed Markdown.",
            "acceptance_criteria": ["Plain references link; mixed Markdown remains unchanged."],
            "constraints": ["Do not implement a Markdown parser."],
            "accepted_risks": ["Mixed Markdown may retain unlinked references."],
            "deferred": [],
            "decision_evidence": ("User chose whole-value plain-text linking in the interview."),
        },
        "task_change_reason": None,
        "findings": [
            {
                "id": "link-1",
                "severity": "high",
                "status": "open",
                "summary": "Renderer does not link plain references",
                "requirement": "Plain references must become links.",
                "scenario": "Rendering a document with a plain reference.",
                "evidence": "The renderer output keeps the reference unlinked.",
                "consequence": "Readers cannot follow the reference.",
                "origin": "regression",
                "minimum_fix": "Keep non-plain-text values unchanged.",
                "blocking": True,
                "rationale": "A small correction restores the explicitly agreed behavior.",
                "decision_evidence": None,
                "reopen_reason": None,
            }
        ],
        "checks": [
            {
                "name": "Renderer acceptance cases",
                "status": "passed",
                "required": True,
                "evidence": "Plain text and protected input examples inspected.",
            }
        ],
        "assessment": "A narrow renderer fix suffices. Patch impact; no new parser needed.",
        "verdict": "not_ready",
        "external_mutations": False,
    }


def _record(snapshot: Path, followup: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    draft_path = Path(str(followup["draft_path"]))
    template = contract.read_json(
        Path(str(followup["context_package"]["template_path"])), "context package template"
    )
    goal = report["task"]["goal"]
    template["goal"] = (
        {"status": "known", "text": goal}
        if isinstance(goal, str) and goal
        else {"status": "unknown"}
    )
    criteria = cast("list[str]", report["task"]["acceptance_criteria"])
    template["acceptance_criteria"] = {
        "status": "known" if criteria else "unknown",
        "items": criteria,
    }
    template["constraints"] = report["task"]["constraints"]
    contract.write_json(Path(str(followup["context_package"]["template_path"])), template)
    recorded = local_review.record_local_package(
        str(snapshot), str(followup["context_package"]["template_path"])
    )
    report = {
        **report,
        "context_package": {
            "path": recorded["artifact_path"],
            "digest": recorded["digest"],
        },
    }
    contract.write_json(draft_path, report)
    return local_review.record_review(str(draft_path.parent), str(snapshot), str(draft_path))


def test_local_fix_cycle_retains_decisions_and_checks_the_delta(repo: Path) -> None:
    snapshot, digest, followup = _prepare(repo)
    assert followup["mode"] == "full"
    report = _report_payload(digest)
    saved = _record(snapshot, followup, report)
    assert saved["verdict"] == "not_ready"

    _, _, unchanged = _prepare(repo)
    assert unchanged["mode"] == "unchanged"
    assert unchanged["previous_report"]["task"] == report["task"]
    assert unchanged["report_template"]["checks"] == []

    (repo / "renderer.txt").write_text("fixed\n")
    (repo / "example.txt").write_text("#7\n")
    fixed_snapshot, _fixed_digest, followup_fixed = _prepare(repo)
    assert followup_fixed["mode"] == "incremental"
    assert "fixed" in followup_fixed["delta"]["unstaged"]
    assert followup_fixed["delta"]["untracked"][0]["path"] == "example.txt"
    fixed = cast("dict[str, Any]", followup_fixed["report_template"])
    fixed["findings"][0]["status"] = "fixed"
    fixed["findings"][0]["blocking"] = False
    fixed["findings"][0]["evidence"] = "Table remains unchanged."
    fixed["checks"] = report["checks"]
    fixed["assessment"] = report["assessment"]
    fixed["verdict"] = "ready"
    result = _record(fixed_snapshot, followup_fixed, fixed)
    assert result["verdict"] == "ready"
    _, _, after = _prepare(repo)
    assert after["mode"] == "unchanged"
    assert (repo / "renderer.txt").read_text(encoding="utf-8") == "fixed\n"


def test_required_checks_prevent_a_ready_verdict() -> None:
    findings: list[dict[str, Any]] = []
    checks = [{"name": "cases", "status": "not_run", "required": True, "evidence": ""}]
    assert local_review._expected_local_verdict(findings, checks) == "blocked"
    checks = [{"name": "cases", "status": "failed", "required": True, "evidence": "x"}]
    assert local_review._expected_local_verdict(findings, checks) == "not_ready"
    checks = [{"name": "cases", "status": "passed", "required": True, "evidence": "x"}]
    assert local_review._expected_local_verdict(findings, checks) == "ready"
