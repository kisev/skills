"""Local review preparation, comparison boundaries, and baselines, from local-review.test.mjs.

Covers: accepted-risk reopening, task-boundary and finding retention, report
severity rules, stale and superseded baselines, explicit audits and fallbacks,
staging and untracked deltas, comparison-ref handling, empty scopes, in-place
linked worktrees, incomplete untracked evidence, and the finalize-local and
prepare-local command surface.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"git {' '.join(arguments)} failed: {result.stderr}"
    return result.stdout.strip()


@pytest.fixture(name="repo")
def local_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "renderer.txt").write_text("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "renderer.txt").write_text("broken\n")
    return repo


def _finding() -> dict[str, Any]:
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


def _report_payload() -> dict[str, Any]:
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
        "findings": [_finding()],
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


def _prepare(repo: Path, incremental: str = "auto") -> tuple[Path, dict[str, Any]]:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    root = str(bundle["artifact_root"])
    path, digest = contract.write_artifact(Path(root), "local_wip_snapshot", bundle)
    return path, local_review.prepare_followup(root, bundle, digest, incremental)


def _initial_report(repo: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    snapshot, context = _prepare(repo)
    report = _report_payload()
    report["evidence_digest"] = context["report_template"]["evidence_digest"]
    return snapshot, context, report


def _complete_package(
    snapshot: Path, context: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    template_path = Path(str(context["context_package"]["template_path"]))
    template = contract.read_json(template_path, "context package template")
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
    contract.write_json(template_path, template)
    recorded = local_review.record_local_package(str(snapshot), str(template_path))
    report["context_package"] = {"path": recorded["artifact_path"], "digest": recorded["digest"]}
    return recorded


def _record(snapshot: Path, context: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    draft = Path(str(context["draft_path"]))
    _complete_package(snapshot, context, report)
    contract.write_json(draft, report)
    return local_review.record_review(str(draft.parent), str(snapshot), str(draft))


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "reviewmatic", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_accepted_risk_cannot_reopen_without_a_changed_basis(repo: Path) -> None:
    snapshot, context, report = _initial_report(repo)
    report["findings"][0]["status"] = "accepted_risk"
    report["findings"][0]["blocking"] = False
    report["findings"][0]["decision_evidence"] = (
        "User explicitly accepts unlinked references in mixed Markdown."
    )
    report["verdict"] = "ready"
    _record(snapshot, context, report)
    next_snapshot, followup = _prepare(repo)
    reopened = copy.deepcopy(report)
    reopened["evidence_digest"] = followup["report_template"]["evidence_digest"]
    reopened["previous_review_digest"] = followup["previous_review_digest"]
    reopened["mode"] = "unchanged"
    reopened["verdict"] = "not_ready"
    reopened["findings"][0]["status"] = "open"
    reopened["findings"][0]["blocking"] = True
    reopened["findings"][0]["reopen_reason"] = "Reviewer disagrees."
    with pytest.raises(contract.WorkflowError, match=r"changed facts or a user decision"):
        _record(next_snapshot, followup, reopened)
    reopened["findings"][0]["evidence"] = (
        "The renderer now deletes the table rather than leaving references unlinked."
    )
    reopened["findings"][0]["reopen_reason"] = (
        "The new failure causes data loss outside the accepted limitation."
    )
    assert _record(next_snapshot, followup, reopened)["verdict"] == "not_ready"


def test_prior_findings_and_the_task_boundary_cannot_silently_disappear(repo: Path) -> None:
    snapshot, context, report = _initial_report(repo)
    saved = _record(snapshot, context, report)
    next_snapshot, followup = _prepare(repo)
    draft = copy.deepcopy(report)
    draft["evidence_digest"] = followup["report_template"]["evidence_digest"]
    draft["previous_review_digest"] = saved["digest"]
    draft["mode"] = "unchanged"
    draft["task"]["constraints"] = []
    with pytest.raises(contract.WorkflowError, match=r"changed task boundary"):
        _record(next_snapshot, followup, draft)
    draft["task"] = report["task"]
    draft["findings"] = []
    draft["verdict"] = "ready"
    with pytest.raises(contract.WorkflowError, match=r"stable IDs"):
        _record(next_snapshot, followup, draft)
    assert local_review.baseline(str(Path(str(context["draft_path"])).parent))[0] == saved["digest"]


def test_severity_does_not_override_acceptance_or_scope() -> None:
    report = _report_payload()
    local_review.validate_report(report)
    report["verdict"] = "ready"
    with pytest.raises(contract.WorkflowError, match=r"not_ready"):
        local_review.validate_report(report)
    report["findings"][0]["severity"] = "high"
    report["findings"][0]["origin"] = "new_requirement"
    report["findings"][0]["blocking"] = False
    report["findings"][0]["summary"] = "Replace relations using guarded delete and create."
    local_review.validate_report(report)
    report["findings"][0]["blocking"] = True
    report["verdict"] = "not_ready"
    with pytest.raises(contract.WorkflowError, match=r"scope expansion"):
        local_review.validate_report(report)
    report["findings"][0]["decision_evidence"] = "User chose replacement instead of rejection."
    local_review.validate_report(report)


def test_stale_or_superseded_review_preserves_the_baseline(repo: Path) -> None:
    snapshot, context, report = _initial_report(repo)
    saved = _record(snapshot, context, report)
    with pytest.raises(contract.WorkflowError, match=r"baseline changed"):
        _record(snapshot, context, report)
    next_snapshot, followup = _prepare(repo)
    draft = copy.deepcopy(report)
    draft["evidence_digest"] = followup["report_template"]["evidence_digest"]
    draft["previous_review_digest"] = saved["digest"]
    draft["mode"] = "unchanged"
    (repo / "renderer.txt").write_text("changed after review\n")
    with pytest.raises(contract.WorkflowError, match=r"evidence changed"):
        _record(next_snapshot, followup, draft)
    assert local_review.baseline(str(Path(str(context["draft_path"])).parent))[0] == saved["digest"]


def test_explicit_audit_keeps_history_and_a_changed_head_falls_back(repo: Path) -> None:
    snapshot, context, report = _initial_report(repo)
    _record(snapshot, context, report)
    _, full = _prepare(repo, "off")
    assert full["mode"] == "full"
    assert full["report_template"]["findings"] == report["findings"]
    _git(repo, "commit", "-am", "fix")
    _, fallback = _prepare(repo)
    assert fallback["mode"] == "full"
    assert fallback["reason"] == "incompatible_boundary_or_incomplete_evidence"
    assert fallback["previous_report"]["task"] == report["task"]


def test_corrupt_baseline_or_missing_snapshot_selects_an_explicit_full_review(
    repo: Path,
) -> None:
    snapshot, context, report = _initial_report(repo)
    saved = _record(snapshot, context, report)
    snapshot.unlink()
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    missing = local_review.prepare_followup(str(bundle["artifact_root"]), bundle, "b" * 64, "auto")
    assert missing["mode"] == "full"
    assert missing["reason"] == "previous_evidence_unavailable"
    contract.write_json(Path(str(saved["artifact_path"])), {"damaged": True})
    _, corrupted = _prepare(repo)
    assert corrupted["reason"] == "previous_review_unavailable"


def test_followup_detects_staging_and_untracked_changes(repo: Path) -> None:
    note = repo / "example.txt"
    removed = repo / "removed.txt"
    note.write_text("before\n")
    removed.write_text("remove this example\n")
    snapshot, context, report = _initial_report(repo)
    _record(snapshot, context, report)
    _git(repo, "add", "renderer.txt")
    note.write_text("after\n")
    removed.unlink()
    _, followup = _prepare(repo)
    assert set(followup["delta"]) == {"staged", "unstaged", "untracked"}
    changes = {item["path"]: item for item in followup["delta"]["untracked"]}
    assert changes["example.txt"]["before"]["sha256"] != changes["example.txt"]["after"]["sha256"]
    assert changes["removed.txt"]["after"] is None


def test_committed_and_wip_sections_track_the_comparison_boundary(repo: Path) -> None:
    initial = local_review.local_bundle(str(repo), "code-review", None)
    assert initial["sections"]["committed"]["diff"] == ""
    assert "broken" in initial["sections"]["unstaged"]["diff"]
    assert initial["sections"]["staged"]["diff"] == ""
    _git(repo, "branch", "review-base")
    _git(repo, "commit", "-am", "change")
    with_ref = local_review.local_bundle(str(repo), "code-review", "review-base")
    assert "broken" in with_ref["sections"]["committed"]["diff"]
    assert with_ref["base_sha"] != with_ref["head_sha"]
    assert with_ref["sections"]["staged"]["diff"] == ""
    assert with_ref["sections"]["unstaged"]["diff"] == ""
    assert with_ref["retrieval_complete"] is True
    without_ref = local_review.local_bundle(str(repo), "code-review", None)
    assert without_ref["sections"]["committed"]["diff"] == ""
    (repo / "renderer.txt").write_text("staged\n")
    _git(repo, "add", "renderer.txt")
    staged = local_review.local_bundle(str(repo), "code-review", None)
    assert "diff --git" in staged["sections"]["staged"]["diff"]
    assert staged["sections"]["unstaged"]["diff"] == ""
    (repo / "renderer.txt").write_text("again\n")
    unstaged = local_review.local_bundle(str(repo), "code-review", None)
    assert "diff --git" in unstaged["sections"]["staged"]["diff"]
    assert "diff --git" in unstaged["sections"]["unstaged"]["diff"]


def test_changed_comparison_ref_invalidates_freshness(repo: Path) -> None:
    _git(repo, "branch", "review-base")
    _git(repo, "commit", "-am", "change")
    bundle = local_review.local_bundle(str(repo), "code-review", "review-base")
    path, _ = contract.write_artifact(
        Path(str(bundle["artifact_root"])), "local_wip_snapshot", bundle
    )
    _git(repo, "branch", "-f", "review-base", "HEAD")
    result = local_review.finalize_local(str(path))
    assert result["status"] == "stale"
    assert isinstance(result["changed"], list)
    assert "base_sha" in result["changed"]


def test_empty_local_scope_stops_with_an_explicit_reason_instead_of_a_review(
    repo: Path,
) -> None:
    _git(repo, "checkout", "--", "renderer.txt")
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    assert bundle["retrieval_complete"] is True
    assert local_review.empty_scope_reason(bundle) == "no_uncommitted_changes"

    _git(repo, "branch", "merge-target")
    with_ref = local_review.local_bundle(str(repo), "code-review", "merge-target")
    assert with_ref["sections"]["committed"]["diff"] == ""
    assert local_review.empty_scope_reason(with_ref) == "no_changes_relative_to_ref"

    (repo / "renderer.txt").write_text("wip\n")
    wip = local_review.local_bundle(str(repo), "code-review", "merge-target")
    assert local_review.empty_scope_reason(wip) is None
    _git(repo, "commit", "-qam", "accepted work")
    committed = local_review.local_bundle(str(repo), "code-review", "merge-target")
    assert "diff --git" in committed["sections"]["committed"]["diff"]
    assert local_review.empty_scope_reason(committed) is None


def test_staged_and_unstaged_sections_stay_separate_when_their_changes_cancel_out(
    repo: Path,
) -> None:
    (repo / "renderer.txt").write_text("broken\n")
    _git(repo, "add", "renderer.txt")
    (repo / "renderer.txt").write_text("base\n")
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    assert "+broken" in bundle["sections"]["staged"]["diff"]
    assert "+base" in bundle["sections"]["unstaged"]["diff"]
    assert bundle["sections"]["committed"]["diff"] == ""
    assert local_review.empty_scope_reason(bundle) is None


def test_missing_ambiguous_or_unrelated_comparison_refs_stop_with_concrete_reasons(
    repo: Path,
) -> None:
    with pytest.raises(
        contract.WorkflowError, match=r"comparison ref 'missing-branch' was not found"
    ):
        local_review.local_bundle(str(repo), "code-review", "missing-branch")
    _git(repo, "branch", "dup")
    _git(repo, "-c", "tag.gpgsign=false", "tag", "-m", "duplicate name", "dup")
    for ref in ("dup", "dup~0"):
        ambiguous = (
            rf"comparison ref '{re.escape(ref)}' is ambiguous.*refs/heads/dup.*refs/tags/dup"
        )
        with pytest.raises(contract.WorkflowError, match=ambiguous):
            local_review.local_bundle(str(repo), "code-review", ref)
    tagged = local_review.local_bundle(str(repo), "code-review", "refs/tags/dup")
    assert tagged["retrieval_complete"] is True
    unambiguous = local_review.local_bundle(str(repo), "code-review", "refs/heads/dup")
    assert unambiguous["retrieval_complete"] is True
    original_branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _git(repo, "checkout", "-q", "--orphan", "isolated")
    _git(repo, "commit", "-q", "-m", "isolated", "--allow-empty")
    _git(repo, "checkout", "-q", original_branch)
    with pytest.raises(
        contract.WorkflowError, match=r"no common merge base between 'isolated' and HEAD"
    ):
        local_review.local_bundle(str(repo), "code-review", "isolated")


def test_a_repeated_run_keeps_the_agreed_comparison_boundary(repo: Path) -> None:
    _git(repo, "branch", "merge-target")
    bundle = local_review.local_bundle(str(repo), "code-review", "merge-target")
    root = str(bundle["artifact_root"])
    snapshot, digest_value = contract.write_artifact(Path(root), "local_wip_snapshot", bundle)
    first = local_review.prepare_followup(root, bundle, digest_value, "auto")
    assert first["mode"] == "full"
    report = _report_payload()
    report["evidence_digest"] = digest_value
    _complete_package(snapshot, first, report)
    draft = Path(str(first["draft_path"]))
    contract.write_json(draft, report)
    local_review.record_review(str(draft.parent), str(snapshot), str(draft))

    again = local_review.local_bundle(str(repo), "code-review", "merge-target")
    _, again_digest = contract.write_artifact(Path(root), "local_wip_snapshot", again)
    second = local_review.prepare_followup(root, again, again_digest, "auto")
    assert second["mode"] == "unchanged"
    assert second["previous_ref"] == "merge-target"

    drifted = local_review.local_bundle(str(repo), "code-review", None)
    _, drifted_digest = contract.write_artifact(Path(root), "local_wip_snapshot", drifted)
    third = local_review.prepare_followup(root, drifted, drifted_digest, "auto")
    assert third["mode"] == "full"
    assert third["reason"] == "incompatible_boundary_or_incomplete_evidence"
    assert third["previous_ref"] == "merge-target"


def test_local_preparation_works_without_remotes_and_preserves_head_index_and_tree(
    repo: Path,
) -> None:
    assert _git(repo, "remote") == ""
    head_before = _git(repo, "rev-parse", "HEAD")
    index_before = (repo / ".git" / "index").read_bytes()
    status_before = _git(repo, "status", "--porcelain")
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    path, _ = contract.write_artifact(
        Path(str(bundle["artifact_root"])), "local_wip_snapshot", bundle
    )
    assert _git(repo, "rev-parse", "HEAD") == head_before
    assert (repo / ".git" / "index").read_bytes() == index_before
    assert _git(repo, "status", "--porcelain") == status_before
    assert not Path(f"{repo}.worktrees").exists()
    assert not str(path).startswith(str(repo))
    assert not str(bundle["artifact_root"]).startswith(str(repo))


def test_an_existing_linked_worktree_is_reviewed_in_place(repo: Path) -> None:
    nested = repo.parent / "linked-checkout"
    _git(repo, "worktree", "add", "-q", str(nested), "-b", "topic")
    (nested / "renderer.txt").write_text("touched in the worktree\n")
    (nested / "note.txt").write_text("untracked\n")
    bundle = local_review.local_bundle(str(nested), "code-review", None)
    assert bundle["repo_root"] == str(nested.resolve())
    assert "touched in the worktree" in bundle["sections"]["unstaged"]["diff"]
    assert [item["path"] for item in bundle["sections"]["untracked"]["items"]] == ["note.txt"]
    assert bundle["retrieval_complete"] is True


def test_untracked_symlinks_and_unreadable_files_mark_the_evidence_incomplete(
    repo: Path,
) -> None:
    (repo / "link.txt").symlink_to("renderer.txt")
    note = repo / "note.txt"
    note.write_text("private\n")
    note.chmod(0o000)
    try:
        bundle = local_review.local_bundle(str(repo), "code-review", None)
    finally:
        note.chmod(0o600)
    items = {item["path"]: item for item in bundle["sections"]["untracked"]["items"]}
    assert items["link.txt"] == {"path": "link.txt", "complete": False, "reason": "symlink"}
    if os.getuid() != 0:
        assert items["note.txt"] == {"path": "note.txt", "complete": False, "reason": "unreadable"}
    assert "link.txt" in bundle["sections"]["untracked"]["errors"]
    assert bundle["sections"]["untracked"]["complete"] is False
    assert bundle["retrieval_complete"] is False


def test_finalize_local_rejects_non_repository_and_symlinked_roots(
    repo: Path, tmp_path: Path
) -> None:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    path, _ = contract.write_artifact(
        Path(str(bundle["artifact_root"])), "local_wip_snapshot", bundle
    )
    assert local_review.finalize_local(str(path))["status"] == "ok"
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(contract.WorkflowError, match=r"repo root must be a real Git checkout"):
        local_review.local_bundle(str(plain), "code-review", None)
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / "repo").symlink_to(repo)
    with pytest.raises(contract.WorkflowError, match=r"repo root must not be a symbolic link"):
        local_review.local_bundle(str(linked / "repo"), "code-review", None)


def test_prepare_local_returns_an_executable_record_command_for_the_immutable_snapshot(
    repo: Path,
) -> None:
    snapshot, context = _prepare(repo)
    command = str(context["context_package"]["record_command"])
    assert str(snapshot) in command, command
    assert "<snapshot>" not in command
    template_path = Path(str(context["context_package"]["template_path"]))
    template = contract.read_json(template_path, "template")
    template["goal"] = {"status": "known", "text": "Link plain text."}
    template["acceptance_criteria"] = {"status": "known", "items": ["Plain references link."]}
    contract.write_json(template_path, template)
    argv = command.split(" ")
    assert argv[0] == "reviewmatic"
    execution = _run_cli(*argv[1:], "--json")
    assert execution.returncode == 0, execution.stderr + execution.stdout
    assert json.loads(execution.stdout)["status"] == "ok"
