from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from shared.references.portable_gitlab import contract as c
from shared.references.portable_gitlab import local_review as local

ROOT = Path(__file__).resolve().parents[1]


def finding() -> dict[str, Any]:
    return {
        "id": "markdown-1",
        "severity": "low",
        "status": "open",
        "summary": "Mixed Markdown is modified.",
        "requirement": "Preserve mixed Markdown verbatim.",
        "scenario": "A user includes an issue reference in a Markdown table.",
        "evidence": "renderer('table #7') rewrites a protected value.",
        "consequence": "The generated table is corrupted.",
        "origin": "regression",
        "minimum_fix": "Keep non-plain-text values unchanged.",
        "blocking": True,
        "rationale": "A small correction restores the explicitly agreed behavior.",
        "decision_evidence": None,
        "reopen_reason": None,
    }


def report_payload() -> dict[str, Any]:
    return {
        "evidence_digest": "a" * 64,
        "previous_review_digest": None,
        "mode": "full",
        "task": {
            "goal": "Link plain text without modifying mixed Markdown.",
            "acceptance_criteria": ["Plain references link; mixed Markdown remains unchanged."],
            "constraints": ["Do not implement a Markdown parser."],
            "accepted_risks": ["Mixed Markdown may retain unlinked references."],
            "deferred": [],
            "decision_evidence": "User chose whole-value plain-text linking in the interview.",
        },
        "task_change_reason": None,
        "findings": [finding()],
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


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    for args in (
        ("init", "-q"),
        ("config", "commit.gpgsign", "false"),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    (repo / "renderer.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, capture_output=True)
    (repo / "renderer.txt").write_text("broken\n", encoding="utf-8")
    return repo


def prepare(repo: Path, incremental: str = "auto") -> tuple[Path, dict[str, Any]]:
    bundle = c.local_bundle(str(repo), "code-review", None)
    root = Path(str(bundle["artifact_root"]))
    path, digest = c.write_artifact(root, "local_wip_snapshot", bundle)
    return path, local.prepare_followup(root, bundle, digest, incremental)


def initial_report(repo: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    snapshot, context = prepare(repo)
    report = report_payload()
    report["evidence_digest"] = context["report_template"]["evidence_digest"]
    return snapshot, context, report


def record(snapshot: Path, context: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    draft = Path(context["draft_path"])
    c.write_json(draft, report)
    return local.record_review(draft.parent, snapshot, draft)


def test_local_fix_cycle_retains_decisions_and_checks_delta(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    assert context["mode"] == "full"
    saved = record(snapshot, context, report)
    assert saved["verdict"] == "not_ready"

    _, unchanged = prepare(repository)
    assert unchanged["mode"] == "unchanged"
    assert unchanged["previous_report"]["task"] == report["task"]
    assert unchanged["report_template"]["checks"] == []

    (repository / "renderer.txt").write_text("fixed\n", encoding="utf-8")
    (repository / "example.txt").write_text("#7\n", encoding="utf-8")
    fixed_snapshot, followup = prepare(repository)
    assert followup["mode"] == "incremental"
    assert "fixed" in followup["delta"]["unstaged"]
    assert followup["delta"]["untracked"][0]["path"] == "example.txt"
    fixed = followup["report_template"]
    fixed["findings"][0].update(status="fixed", blocking=False, evidence="Table remains unchanged.")
    fixed.update(checks=report["checks"], assessment=report["assessment"], verdict="ready")
    result = record(fixed_snapshot, followup, fixed)
    assert result["verdict"] == "ready"
    assert prepare(repository)[1]["mode"] == "unchanged"
    assert (repository / "renderer.txt").read_text(encoding="utf-8") == "fixed\n"


def test_accepted_risk_cannot_reopen_without_changed_basis(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    report["findings"][0].update(
        status="accepted_risk",
        blocking=False,
        decision_evidence="User explicitly accepts unlinked references in mixed Markdown.",
    )
    report["verdict"] = "ready"
    record(snapshot, context, report)
    next_snapshot, followup = prepare(repository)
    reopened = copy.deepcopy(report)
    reopened.update(
        evidence_digest=followup["report_template"]["evidence_digest"],
        previous_review_digest=followup["previous_review_digest"],
        mode="unchanged",
        verdict="not_ready",
    )
    reopened["findings"][0].update(
        status="open", blocking=True, reopen_reason="Reviewer disagrees."
    )
    with pytest.raises(c.WorkflowError, match="changed facts or a user decision"):
        record(next_snapshot, followup, reopened)
    reopened["findings"][0].update(
        evidence="The renderer now deletes the table rather than leaving references unlinked.",
        reopen_reason="The new failure causes data loss outside the accepted limitation.",
    )
    assert record(next_snapshot, followup, reopened)["verdict"] == "not_ready"


def test_prior_findings_and_task_boundary_cannot_silently_disappear(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    saved = record(snapshot, context, report)
    next_snapshot, followup = prepare(repository)
    draft = copy.deepcopy(report)
    draft.update(
        evidence_digest=followup["report_template"]["evidence_digest"],
        previous_review_digest=saved["digest"],
        mode="unchanged",
    )
    draft["task"]["constraints"] = []
    with pytest.raises(c.WorkflowError, match="changed task boundary"):
        record(next_snapshot, followup, draft)
    draft["task"] = report["task"]
    draft["findings"] = []
    draft["verdict"] = "ready"
    with pytest.raises(c.WorkflowError, match="stable IDs"):
        record(next_snapshot, followup, draft)
    assert local.baseline(Path(context["draft_path"]).parent)[0] == saved["digest"]


def test_severity_does_not_override_acceptance_or_scope() -> None:
    report = report_payload()
    local.validate_report(report)  # A low-severity regression can block an agreed requirement.
    report["verdict"] = "ready"
    with pytest.raises(c.WorkflowError, match="not_ready"):
        local.validate_report(report)
    report["findings"][0].update(
        severity="high",
        origin="new_requirement",
        blocking=False,
        summary="Replace relations using guarded delete and create.",
    )
    local.validate_report(report)
    report["findings"][0]["blocking"] = True
    report["verdict"] = "not_ready"
    with pytest.raises(c.WorkflowError, match="scope expansion"):
        local.validate_report(report)
    report["findings"][0]["decision_evidence"] = "User chose replacement instead of rejection."
    local.validate_report(report)


@pytest.mark.parametrize(("status", "verdict"), [("not_run", "blocked"), ("failed", "not_ready")])
def test_required_checks_prevent_ready(status: str, verdict: str) -> None:
    report = report_payload()
    report["findings"] = []
    report["checks"][0]["status"] = status
    report["verdict"] = verdict
    local.validate_report(report)
    report["verdict"] = "ready"
    with pytest.raises(c.WorkflowError, match=verdict):
        local.validate_report(report)


def test_stale_or_superseded_review_preserves_baseline(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    saved = record(snapshot, context, report)
    with pytest.raises(c.WorkflowError, match="baseline changed"):
        record(snapshot, context, report)
    next_snapshot, followup = prepare(repository)
    draft = copy.deepcopy(report)
    draft.update(
        evidence_digest=followup["report_template"]["evidence_digest"],
        previous_review_digest=saved["digest"],
        mode="unchanged",
    )
    (repository / "renderer.txt").write_text("changed after review\n", encoding="utf-8")
    with pytest.raises(c.WorkflowError, match="evidence changed"):
        record(next_snapshot, followup, draft)
    assert local.baseline(Path(context["draft_path"]).parent)[0] == saved["digest"]


def test_explicit_audit_keeps_history_and_changed_head_falls_back(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    record(snapshot, context, report)
    _, full = prepare(repository, "off")
    assert full["mode"] == "full"
    assert full["report_template"]["findings"] == report["findings"]
    subprocess.run(["git", "commit", "-am", "fix"], cwd=repository, check=True, capture_output=True)
    _, fallback = prepare(repository)
    assert fallback["mode"] == "full"
    assert fallback["reason"] == "incompatible_boundary_or_incomplete_evidence"
    assert fallback["previous_report"]["task"] == report["task"]


def test_corrupt_baseline_or_missing_snapshot_selects_explicit_full(repository: Path) -> None:
    snapshot, context, report = initial_report(repository)
    saved = record(snapshot, context, report)
    snapshot.unlink()
    bundle = c.local_bundle(str(repository), "code-review", None)
    root = Path(str(bundle["artifact_root"]))
    missing = local.prepare_followup(root, bundle, "b" * 64, "auto")
    assert missing["mode"] == "full"
    assert missing["reason"] == "previous_evidence_unavailable"
    c.write_json(Path(saved["artifact_path"]), {"damaged": True})
    assert prepare(repository)[1]["reason"] == "previous_review_unavailable"


def test_followup_detects_staging_and_untracked_changes(repository: Path) -> None:
    note = repository / "example.txt"
    removed = repository / "removed.txt"
    note.write_text("before\n", encoding="utf-8")
    removed.write_text("remove this example\n", encoding="utf-8")
    snapshot, context, report = initial_report(repository)
    record(snapshot, context, report)
    subprocess.run(["git", "add", "renderer.txt"], cwd=repository, check=True, capture_output=True)
    note.write_text("after\n", encoding="utf-8")
    removed.unlink()
    _, followup = prepare(repository)
    assert {"staged", "unstaged", "untracked"} == set(followup["delta"])
    changes = {item["path"]: item for item in followup["delta"]["untracked"]}
    assert changes["example.txt"]["before"]["sha256"] != changes["example.txt"]["after"]["sha256"]
    assert changes["removed.txt"]["after"] is None


def test_changed_comparison_ref_invalidates_freshness(repository: Path) -> None:
    subprocess.run(
        ["git", "branch", "review-base"], cwd=repository, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-am", "change"], cwd=repository, check=True, capture_output=True
    )
    bundle = c.local_bundle(str(repository), "code-review", "review-base")
    path, _ = c.write_artifact(Path(str(bundle["artifact_root"])), "local_wip_snapshot", bundle)
    subprocess.run(
        ["git", "branch", "-f", "review-base", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    result = c.finalize_local(str(path))
    assert result["status"] == "stale"
    assert isinstance(result["changed"], list)
    assert "base_sha" in result["changed"]


def test_portable_cli_finalizes_report_and_preserves_old_freshness_api(repository: Path) -> None:
    runner = ROOT / ".build/skills/code-review/scripts/review_mr.py"

    def run(*args: str) -> dict[str, Any]:
        result = subprocess.run(
            ["python3", "-I", "-S", "-B", str(runner), *args],
            cwd=repository,
            check=True,
            text=True,
            capture_output=True,
        )
        return dict(json.loads(result.stdout))

    prepared = run("prepare-local", "--repo-root", str(repository))
    legacy = run("finalize-local", "--bundle", prepared["bundle"])
    assert legacy["review"] is None
    assert run("prepare-local", "--repo-root", str(repository))["review"]["mode"] == "full"
    report = report_payload()
    report["evidence_digest"] = prepared["digest"]
    draft = Path(prepared["review"]["draft_path"])
    c.write_json(draft, report)
    final = run("finalize-local", "--bundle", prepared["bundle"], "--report", str(draft))
    assert final["review"]["verdict"] == "not_ready"
    assert run("prepare-local", "--repo-root", str(repository))["review"]["mode"] == "unchanged"
