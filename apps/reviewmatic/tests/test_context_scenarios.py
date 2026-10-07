"""Context-state scenarios ported from ``context.test.mjs``.

The first-run happy path lives in ``test_review_happy_path.py``; this module
carries the remaining small contracts (runner action, progress machine,
finding publications, verdict gates, atomic state publication) and the
incremental second-run scaffold that the TypeScript happy path finishes with.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.portable.state_artifacts import StateArtifactError

if TYPE_CHECKING:
    from collections.abc import Iterator

EVIDENCE_B = "b" * 64
PLAN_A = "a" * 64


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def initial_progress(root: Path) -> dict[str, Any]:
    return review_context.empty_progress(
        Path(f"{root}/artifacts/evidence_snapshot/{EVIDENCE_B}.json"),
        EVIDENCE_B,
        mode="normal",
        locale="en",
    )


def test_runner_action_renders_reviewmatic_cli_invocations() -> None:
    action = review_context.runner_action(
        "context",
        "--evidence",
        "/tmp/evidence.json",
        "--repo-root",
        "<checkout>",
        required_inputs=("repo_root",),
    )
    assert action["argv"][0] == "reviewmatic"
    assert action["argv"][1] == "context"
    assert (
        action["command"] == "reviewmatic context --evidence /tmp/evidence.json "
        "--repo-root '<checkout>'"
    )
    assert action["required_inputs"] == ["repo_root"]


def test_progress_machine_rejects_invalid_transitions(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir()
    progress = initial_progress(root)
    progress["stage"] = "prepared"
    contract.write_json(review_context.progress_path(root), progress)
    with pytest.raises(contract.WorkflowError, match=r"changed during transition"):
        review_context.advance_progress(
            root, "decision_missing", expected_stages={"context_ready", "finalize_missing"}
        )
    with pytest.raises(contract.WorkflowError, match=r"unknown fields"):
        review_context.advance_progress(root, "context_ready", mystery_field=1)
    with pytest.raises(contract.WorkflowError, match=r"progress stage is invalid"):
        review_context.advance_progress(root, "finished")
    broken = {**progress, "context_digest": EVIDENCE_B}
    contract.write_json(review_context.progress_path(root), broken)
    with pytest.raises(contract.WorkflowError, match=r"artifact binding is incomplete"):
        review_context.load_progress(root)
    contract.write_json(review_context.progress_path(root), {"schema": "code-review/progress/v1"})
    with pytest.raises(contract.WorkflowError, match=r"invalid shape"):
        review_context.load_progress(root)


def test_line_finding_publications_require_exactly_one_suggestion_block() -> None:
    invalid = {
        "finding_id": "finding-1",
        "type": "line",
        "path": "src/example.py",
        "line": 7,
        "old_line": None,
        "body": "Replace this line.",
        "fix_mode": "suggestion",
        "patch": None,
    }
    with pytest.raises(
        contract.WorkflowError,
        match=r"fix_mode=suggestion without suggestions\[\] requires exactly one suggestion",
    ):
        review_context.validate_finding_publications([invalid], {"finding-1"})
    valid = {
        **invalid,
        "body": "Use the bounded value.\n\n```suggestion:-1+1\nvalue = bounded\n```",
    }
    assert review_context.validate_finding_publications([valid], {"finding-1"}) == [valid]
    general = {
        **invalid,
        "type": "general",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "Apply the complete fix.",
        "fix_mode": "patch",
        "patch": (
            "diff --git a/src/example.py b/src/example.py\n"
            "--- a/src/example.py\n"
            "+++ b/src/example.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
    }
    assert review_context.validate_finding_publications([general], {"finding-1"}) == [general]


def test_review_verdict_keeps_low_findings_non_blocking_and_gates_ci_classifications() -> None:
    low = {
        "id": "docs-1",
        "severity": "low",
        "summary": "Documentation is incomplete",
        "risk": "Readers can miss an option.",
        "evidence": ["README omits the option."],
        "consequence": "Adoption can take longer.",
        "relation_to_change": "The change adds the option.",
        "minimum_fix": "Document the option.",
    }
    evidence: dict[str, Any] = {
        "head_sha": "c",
        "pipelines": {"complete": True, "items": [{"id": 1, "sha": "c", "status": "failed"}]},
    }
    report: dict[str, Any] = {
        "verdict": "blocked",
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "owner_decision_reasons": ["The exact-head pipeline failed."],
    }
    review_context.validate_review_verdict(report, [low], evidence)
    with pytest.raises(contract.WorkflowError, match=r"does not match findings"):
        review_context.validate_review_verdict({**report, "verdict": "not_ready"}, [low], evidence)
    with pytest.raises(contract.WorkflowError, match=r"non-low finding must be blocking"):
        review_context.validate_review_verdict(
            {
                "verdict": "not_ready",
                "blocking_findings": True,
                "blocking_finding_ids": ["docs-1"],
                "owner_decision_reasons": [],
            },
            [low],
            evidence,
        )
    high = {**low, "id": "runtime-1", "severity": "high"}
    successful = {
        **evidence,
        "pipelines": {"complete": True, "items": [{"id": 2, "sha": "c", "status": "success"}]},
    }
    with pytest.raises(contract.WorkflowError, match=r"non-low finding must be blocking"):
        review_context.validate_review_verdict(
            {
                "verdict": "ready",
                "blocking_findings": False,
                "blocking_finding_ids": [],
                "owner_decision_reasons": [],
            },
            [high],
            successful,
        )
    job_evidence: dict[str, Any] = {
        "head_sha": "c",
        "pipelines": {
            "complete": True,
            "items": [
                {
                    "id": 2,
                    "sha": "c",
                    "status": "failed",
                    "job_evidence": {
                        "complete": True,
                        "errors": [],
                        "truncated": False,
                        "pipelines": [
                            {
                                "project_id": 19,
                                "pipeline_id": 2,
                                "jobs": [
                                    {
                                        "project_id": 19,
                                        "pipeline_id": 2,
                                        "id": 7,
                                        "status": "failed",
                                        "trace": {
                                            "complete": True,
                                            "truncated": False,
                                            "excerpt": "Merge request requires two approvals.",
                                            "sha256": "a" * 64,
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                },
            ],
        },
    }
    process_gate = {
        "project_id": 19,
        "pipeline_id": 2,
        "job_id": 7,
        "classification": "process_gate",
        "rationale": "The job enforces the approval policy rather than code quality.",
        "trace_evidence": "requires two approvals",
    }
    ready: dict[str, Any] = {
        "verdict": "ready",
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "owner_decision_reasons": [],
    }
    review_context.validate_review_verdict(
        {**ready, "ci_job_assessments": [process_gate]}, [low], job_evidence
    )
    with pytest.raises(
        contract.WorkflowError, match=r"owner decision reason|does not match findings"
    ):
        review_context.validate_review_verdict(
            {
                **ready,
                "ci_job_assessments": [
                    {
                        **process_gate,
                        "classification": "code_failure",
                        "rationale": "The test assertion failed.",
                    },
                ],
            },
            [low],
            job_evidence,
        )
    raw_head = "a" * 40
    with pytest.raises(contract.WorkflowError, match=r"raw commit SHA"):
        review_context.reject_visible_raw_refs(
            f"Changed behavior at {raw_head}", {"head_sha": raw_head}
        )
    previous_head = "b" * 40
    with pytest.raises(contract.WorkflowError, match=r"raw commit SHA"):
        review_context.reject_visible_raw_refs(
            f"Compared from {previous_head}",
            {"head_sha": raw_head},
            {
                "incremental": {
                    "incremental_delta": {"from_head": previous_head, "to_head": raw_head}
                }
            },
        )


def test_publish_review_state_writes_and_rolls_back_atomically(tmp_path: Path) -> None:
    root = tmp_path / "publish"
    root.mkdir()
    root.chmod(0o700)
    markdown = root / "review-publication.md"
    baseline = root / review_context.BASELINE_NAME
    progress = initial_progress(root)
    progress["stage"] = "content_missing"
    progress_file = review_context.progress_path(root)
    contract.write_json(progress_file, progress)
    plan_path = Path(f"{root}/artifacts/review_plan/{PLAN_A}.json")
    target = {"url": "https://gitlab.example/group/project/-/merge_requests/7"}

    def baseline_digest() -> str | None:
        return sha256(baseline.read_bytes()) if baseline.exists() else None

    markdown.write_text("old review\n")
    baseline.write_text('{"old":true}\n')
    progress_bytes = progress_file.read_bytes()
    with pytest.raises(contract.WorkflowError, match=r"baseline changed before publication"):
        review_context.publish_review_state(
            root, "new review\n", plan_path, PLAN_A, target, "0" * 64, {"stage": "content_missing"}
        )
    assert markdown.read_text() == "old review\n"
    assert baseline.read_text() == '{"old":true}\n'
    assert progress_file.read_bytes() == progress_bytes

    markdown.write_text("new review\n")
    baseline.unlink()
    root.chmod(0o500)
    try:
        with pytest.raises((OSError, contract.WorkflowError, StateArtifactError)):
            review_context.publish_review_state(
                root,
                "new review\n",
                plan_path,
                PLAN_A,
                target,
                baseline_digest(),
                {"stage": "content_missing"},
            )
    finally:
        root.chmod(0o700)
    assert markdown.read_text() == "new review\n"
    assert progress_file.read_bytes() == progress_bytes

    path, digest = review_context.publish_review_state(
        root, "final review\n", plan_path, PLAN_A, target, None, {"stage": "content_missing"}
    )
    assert path.name == "runbook.md"
    assert digest == sha256("final review\n")
    written = contract.read_json(root / review_context.BASELINE_NAME, "baseline")
    assert written["contract_version"] == 1
    assert contract.read_json(progress_file, "progress")["stage"] == "plan_ready"


PRIMARY_FINDING = {
    "id": "primary-1",
    "severity": "high",
    "summary": "Retry can repeat the external operation",
    "risk": "A retry can execute the operation twice.",
    "evidence": ["The current retry path calls the provider before reserving an ID."],
    "consequence": "Users can observe duplicate side effects.",
    "relation_to_change": "The reviewed change adds the retry path.",
    "minimum_fix": "Persist an idempotency key before the external call.",
}


def bind(progress: dict[str, Any], *keys: str) -> dict[str, object]:
    return {key: progress[key] for key in keys}


def advance_with(
    root: Path, stage: str, expected_stages: set[str], bound: tuple[str, ...], **changes: object
) -> None:
    progress = review_context.load_progress(root)
    assert progress is not None
    review_context.advance_progress(
        root,
        stage,
        expected_stages=expected_stages,
        expected=bind(progress, *bound),
        **changes,
    )


CLEARED = {
    "finalize_report_path": None,
    "finalize_report_digest": None,
    "decision_path": None,
    "decision_digest": None,
    "plan_path": None,
    "plan_digest": None,
}
CONTEXT_BOUND = ("evidence_path", "evidence_digest", "context_path", "context_digest")


def review_content(critic_finding: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    return {
        "locale": "en",
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The retry defect is confirmed."},
            "relevance": {
                "status": "current",
                "rationale": "The exact reviewed head is current.",
            },
            "change": (
                "The MR adds retry behavior but does not reserve an idempotency key before "
                "the external call."
            ),
        },
        "summary": "The change is small and preserves the reviewed contract.",
        "architecture_assessment": "The responsibility remains with its existing owner.",
        "semver_impact": "patch",
        "semver_rationale": "The fix changes behavior without changing the public API.",
        "semver_assessment": {
            **template["semver_assessment"],
            "policy": "No release policy was found in the fixture.",
            "sources": ["Fixture repository and empty release catalog"],
            "fallback_reason": "No confirmed release is available.",
        },
        "mr_metadata_assessment": {
            "title": {
                "status": "needs_change",
                "rationale": "The title does not identify the affected behavior.",
                "recommendation": "Name the affected retry behavior.",
            },
            "description": {
                "status": "ok",
                "rationale": "The description states the intended behavior.",
                "recommendation": None,
            },
            "labels": {
                "status": "needs_change",
                "rationale": "The MR has no labels.",
                "recommendation": "Apply the project-required labels.",
            },
            "workflow_state": {
                "status": "ok",
                "rationale": "The MR is open and remains commentable.",
                "recommendation": None,
            },
            "overall": {
                "status": "needs_change",
                "rationale": "Title and labels need clearer release metadata.",
                "recommendation": "Correct metadata independently of code findings.",
            },
        },
        "label_assessments": [
            {
                "name": "next-compatible",
                "status": "inapplicable",
                "rationale": "The change is a patch, not a minor release.",
            },
            {
                "name": "semver::major",
                "status": "inapplicable",
                "rationale": "The change is backward compatible.",
            },
            {
                "name": "semver::patch",
                "status": "applicable",
                "rationale": "The reviewed fix has patch SemVer impact.",
            },
            {
                "name": "ship-ready",
                "status": "inapplicable",
                "rationale": "This MR is not a release publication.",
            },
        ],
        "checks": ["Compared the exact base and head revisions."],
        "findings": [PRIMARY_FINDING],
        "finding_publications": [
            {
                "finding_id": "primary-1",
                "type": "general",
                "path": None,
                "line": None,
                "old_line": None,
                "body": "You need to reserve an idempotency key before the external call.",
                "fix_mode": "patch",
                "patch_reason": "A new policy file has no existing suggestion anchor.",
                "patch": (
                    "diff --git a/retry-policy.txt b/retry-policy.txt\n"
                    "new file mode 100644\n"
                    "--- /dev/null\n"
                    "+++ b/retry-policy.txt\n"
                    "@@ -0,0 +1 @@\n"
                    "+reserve idempotency key\n"
                ),
            },
        ],
        "previous_finding_assessments": [],
        "issue_templates": [],
        "recommended_issues": [
            {
                "id": "issue-1",
                "title": "Track retry exhaustion observability",
                "problem": "The broader retry subsystem lacks a terminal signal.",
                "risk": "Operators cannot distinguish retry exhaustion.",
                "evidence": ["The existing subsystem has no terminal metric."],
                "reason_out_of_scope": "The subsystem is not changed by this MR.",
                "minimum_fix": "Add the existing terminal retry metric separately.",
                "body": "Track a terminal metric for retry exhaustion in the broader subsystem.",
                "template_path": None,
            },
        ],
        "rejected_candidates": [
            {
                "id": "critic-1",
                "source": "critic",
                "finding": critic_finding,
                "reason": "The broader observability gap is outside this MR.",
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        ],
        "rejected_candidate_assessments": [],
        "thread_decisions": [
            {
                "id": "42",
                "url": "https://gitlab.example/group/project/-/merge_requests/7#note_42",
                "state": "open",
                "assessment": "fixed",
                "rationale": "The existing thread can be acknowledged and resolved.",
                "outcome": "resolve",
                "proposed_response": "I tracked the remaining risk in the current finding. Closing.",
                "fix_mode": "not_required",
                "patch": None,
                "fixing_commit": None,
                "last_note_id": 42,
                "last_note_body_sha256": sha256("Retry needs an idempotency key"),
                "thread_sha256": template["thread_decisions"][0]["thread_sha256"],
            },
        ],
    }


def test_unchanged_second_run_does_not_republish_findings_or_issues(
    fixture: ReviewFixture,
) -> None:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    repo = str(fixture.repo)
    bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    evidence_path = str(bundle["preview_artifact_path"])
    evidence_digest = str(bundle["preview_digest"])
    root = Path(str(bundle["artifact_root"]))

    review_context.begin_review(
        evidence_path, evidence_digest, str(root), repo, "deep", "en", "auto"
    )
    context_result = review_context.prepare_context(evidence_path, repo, "auto", "deep", "en")
    context_path = str(context_result["artifact_path"])
    context_digest = str(context_result["digest"])

    critic_finding = {
        "id": "critic-1",
        "severity": "medium",
        "summary": "Retry failure is not observable",
        "risk": "Operators cannot distinguish retry exhaustion.",
        "evidence": [f"The exact reviewed SHA is {fixture.head_sha}."],
        "consequence": "Incident diagnosis takes longer.",
        "relation_to_change": "The new retry path emits no terminal signal.",
        "minimum_fix": "Emit the existing terminal retry metric.",
    }
    receipt = {
        "schema": "portable-gitlab/critic-receipt/v2",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "run_id": "critic-run",
        "session_id": "critic-session",
        "findings": [critic_finding],
    }
    receipt_path, receipt_digest = contract.write_artifact(root, "critic_receipt", receipt)
    advance_with(
        root,
        "finalize_missing",
        {"context_ready"},
        CONTEXT_BOUND,
        critic_receipt_path=str(receipt_path),
        critic_receipt_digest=receipt_digest,
        **CLEARED,
    )
    finalize_result = contract.finalize_payload(
        contract.finalize(str(root), "review-evidence.json"),
        Path(evidence_path),
        bundle,
        "evidence_snapshot",
    )
    finalize_path, finalize_digest = contract.write_artifact(
        root, "finalize_report", finalize_result
    )
    advance_with(
        root,
        "decision_missing",
        {"context_ready", "finalize_missing"},
        (*CONTEXT_BOUND, "critic_receipt_path", "critic_receipt_digest"),
        finalize_report_path=str(finalize_path),
        finalize_report_digest=finalize_digest,
        decision_path=None,
        decision_digest=None,
        plan_path=None,
        plan_digest=None,
    )
    decision_payload = {
        "schema": "portable-gitlab/review-decision/v2",
        "mode": "deep",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "finalize_digest": finalize_digest,
        "context_digest": context_digest,
        "critic_receipt_digest": receipt_digest,
        "verdict": "not_ready",
        "blocking_findings": True,
        "blocking_finding_ids": ["primary-1"],
        "owner_decision_reasons": [],
        "run_id": "primary-run",
        "session_id": "primary-session",
        "findings": [PRIMARY_FINDING],
        "unresolved_threads": [{"id": "thread:42"}],
        "responses": [
            {"id": "primary-1", "decision": "accept", "reason": "confirmed"},
            {"id": "critic-1", "decision": "reject", "reason": "outside the changed contract"},
            {"id": "thread:42", "decision": "accept", "reason": "still open"},
        ],
        "critic_findings": [critic_finding],
        "accepted_findings": [PRIMARY_FINDING],
        "critic_target_finding_ids": [],
    }
    decision_file, decision_digest = contract.write_artifact(
        root, "review_decision", decision_payload
    )
    advance_with(
        root,
        "content_missing",
        {"decision_missing"},
        (
            *CONTEXT_BOUND,
            "critic_receipt_path",
            "critic_receipt_digest",
            "finalize_report_path",
            "finalize_report_digest",
        ),
        decision_path=str(decision_file),
        decision_digest=decision_digest,
        plan_path=None,
        plan_digest=None,
    )
    content_template = contract.read_json(
        Path(review_context.template_review(str(root), "content")["template_path"]),
        "content template",
    )
    content = review_content(critic_finding, content_template)
    content_file = fixture.tmp / "review-content.json"
    content_file.write_text(json.dumps(content))
    plan = review_context.scaffold_review(
        evidence_path, context_path, str(decision_file), str(content_file)
    )
    assert plan["status"] == "ok"
    assert plan["stage"] == "plan_ready"

    bundle2: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    evidence_path2 = str(bundle2["preview_artifact_path"])
    review_context.begin_review(
        evidence_path2, str(bundle2["preview_digest"]), str(root), repo, "deep", "en", "auto"
    )
    context2: dict[str, Any] = review_context.prepare_context(
        evidence_path2, repo, "auto", "deep", "en"
    )
    assert context2["incremental"]["mode"] == "unchanged"
    assert context2["incremental"]["critic_required"] is False

    receipt2 = {**receipt, "evidence_digest": bundle2["preview_digest"]}
    receipt_path2, receipt_digest2 = contract.write_artifact(root, "critic_receipt", receipt2)
    advance_with(
        root,
        "finalize_missing",
        {"context_ready"},
        CONTEXT_BOUND,
        critic_receipt_path=str(receipt_path2),
        critic_receipt_digest=receipt_digest2,
        **CLEARED,
    )
    finalize_result2 = contract.finalize_payload(
        contract.finalize(str(root), "review-evidence.json"),
        Path(evidence_path2),
        bundle2,
        "evidence_snapshot",
    )
    finalize_path2, finalize_digest2 = contract.write_artifact(
        root, "finalize_report", finalize_result2
    )
    advance_with(
        root,
        "decision_missing",
        {"context_ready", "finalize_missing"},
        CONTEXT_BOUND,
        finalize_report_path=str(finalize_path2),
        finalize_report_digest=finalize_digest2,
        decision_path=None,
        decision_digest=None,
        plan_path=None,
        plan_digest=None,
    )
    decision2 = {
        **decision_payload,
        "mode": "unchanged",
        "evidence_digest": bundle2["preview_digest"],
        "context_digest": context2["digest"],
        "finalize_digest": finalize_digest2,
        "critic_receipt_digest": receipt_digest2,
    }
    decision_path2, decision_digest2 = contract.write_artifact(root, "review_decision", decision2)
    advance_with(
        root,
        "content_missing",
        {"context_ready", "finalize_missing", "decision_missing"},
        CONTEXT_BOUND,
        decision_path=str(decision_path2),
        decision_digest=decision_digest2,
        plan_path=None,
        plan_digest=None,
    )
    template_content2 = contract.read_json(
        Path(review_context.template_review(str(root), "content")["template_path"]),
        "content template",
    )

    incremental_content = copy.deepcopy(content)
    incremental_content["thread_decisions"][0]["thread_sha256"] = template_content2[
        "thread_decisions"
    ][0]["thread_sha256"]
    incremental_content["previous_finding_assessments"] = []
    incremental_file = fixture.tmp / "review-content-incremental.json"
    incremental_file.write_text(json.dumps(incremental_content))
    plan2 = review_context.scaffold_review(
        evidence_path2, str(context2["artifact_path"]), str(decision_path2), str(incremental_file)
    )
    assert plan2["status"] == "ok"
    actions2 = contract.read_json(Path(str(plan2["artifact_path"])), "review plan")["payload"][
        "publication_preview"
    ]["actions"]
    assert any(item.get("publication_id") == "primary-1" for item in actions2), (
        "a confirmed current finding receives its own action independently of history"
    )
    assert any(item["kind"] == "thread" and item["operation"] == "resolve" for item in actions2)

    updated_issue = copy.deepcopy(incremental_content)
    updated_issue["previous_finding_assessments"] = [
        {
            "id": "issue-1",
            "kind": "issue",
            "status": "active",
            "previous_status": "active",
            "current_status": "changed",
            "rationale": "The proposal changed.",
            "action": "Update the proposal.",
            "publication_action": "update_issue",
            "publication_body": "Update the proposal.",
            "critic_required": False,
        }
    ]
    with pytest.raises(
        contract.WorkflowError, match=r"every previous finding and issue requires one assessment"
    ):
        review_context.scaffold_review(
            evidence_path2,
            str(context2["artifact_path"]),
            str(decision_path2),
            str(fixture.tmp / "review-content-update-issue.json"),
            {
                "decision": decision2,
                "content": updated_issue,
                "dry_run": True,
                "freshness_checked": True,
            },
        )


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _exact_repo(tmp_path: Path, name: str) -> tuple[Path, str]:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "--quiet", "--initial-branch=main")
    _git(repo, "config", "user.email", "context@example.invalid")
    _git(repo, "config", "user.name", "Context Fixture")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "review.txt").write_text("one\ntwo\nthree\nfour\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _exact_evidence(base: str, head: str, items: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "base_sha": base,
        "start_sha": base,
        "head_sha": head,
        "changed_files": {
            "items": items,
            "complete": True,
            "errors": [],
            "pages": 1,
            "truncated": False,
        },
    }


def test_exact_git_context_accepts_a_gitlab_rename_git_reports_as_delete_and_add(
    tmp_path: Path,
) -> None:
    repo, base = _exact_repo(tmp_path, "pair-rename")
    _git(repo, "mv", "review.txt", "renamed.txt")
    (repo / "renamed.txt").write_text("alpha\nbeta\ngamma\ndelta\n")
    _git(repo, "commit", "-qam", "rename with new content")
    head = _git(repo, "rev-parse", "HEAD")
    listed = _git(repo, "diff", "--name-only", "--find-renames", "-z", base, head)
    assert sorted(filter(None, listed.split("\0"))) == ["renamed.txt", "review.txt"], (
        "the scenario requires git to report both rename sides"
    )
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(base, head, [{"old_path": "review.txt", "new_path": "renamed.txt"}]),
    )
    assert exact["complete"] is True, exact["errors"]
    assert exact["changed_paths"] == ["renamed.txt", "review.txt"]


def test_exact_git_context_accepts_a_gitlab_rename_git_pairs_completely(tmp_path: Path) -> None:
    repo, base = _exact_repo(tmp_path, "pure-rename")
    _git(repo, "mv", "review.txt", "renamed.txt")
    _git(repo, "commit", "-qam", "rename")
    head = _git(repo, "rev-parse", "HEAD")
    listed = _git(repo, "diff", "--name-only", "--find-renames", "-z", base, head)
    assert listed.rstrip("\0").split("\0") == ["renamed.txt"]
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(base, head, [{"old_path": "review.txt", "new_path": "renamed.txt"}]),
    )
    assert exact["complete"] is True, exact["errors"]
    assert exact["changed_paths"] == ["renamed.txt"]


def test_exact_git_context_matches_plain_modifications_without_renames(tmp_path: Path) -> None:
    repo, base = _exact_repo(tmp_path, "plain")
    (repo / "review.txt").write_text("one\ntwo\nthree\nedited\n")
    _git(repo, "commit", "-qam", "edit")
    head = _git(repo, "rev-parse", "HEAD")
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(base, head, [{"old_path": "review.txt", "new_path": "review.txt"}]),
    )
    assert exact["complete"] is True, exact["errors"]
    assert exact["changed_paths"] == ["review.txt"]


def test_exact_git_context_still_flags_paths_the_server_did_not_report(tmp_path: Path) -> None:
    repo, base = _exact_repo(tmp_path, "mismatch")
    (repo / "extra.txt").write_text("absent from the server report\n")
    _git(repo, "add", ".")
    (repo / "review.txt").write_text("one\ntwo\nthree\nedited\n")
    _git(repo, "commit", "-qam", "edit plus an unreported file")
    head = _git(repo, "rev-parse", "HEAD")
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(base, head, [{"old_path": "review.txt", "new_path": "review.txt"}]),
    )
    assert exact["complete"] is False
    assert "local changed paths do not match GitLab evidence" in exact["errors"]


def test_exact_git_context_measures_the_real_merge_base_delta(tmp_path: Path) -> None:
    repo, base = _exact_repo(tmp_path, "delta")
    (repo / "review.txt").write_text("one\ntwo\nthree\nedited\nfour\nfive\n")
    (repo / "extra.bin").write_bytes(b"\x00\x01\x02\x03")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qam", "edit plus a binary file")
    head = _git(repo, "rev-parse", "HEAD")
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(
            base,
            head,
            [
                {"old_path": "review.txt", "new_path": "review.txt"},
                {"old_path": "extra.bin", "new_path": "extra.bin"},
            ],
        ),
    )
    assert exact["complete"] is True, exact["errors"]
    delta = exact["delta"]
    assert delta["merge_base"] == base
    assert delta["files"] == 2
    assert delta["insertions"] == 2
    assert delta["deletions"] == 0
    assert delta["binary_files"] == 1


def test_exact_git_context_omits_delta_when_the_merge_base_differs(tmp_path: Path) -> None:
    repo, _base = _exact_repo(tmp_path, "unverified-base")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "side.txt").write_text("divergent\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "side commit")
    side_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    (repo / "review.txt").write_text("one\ntwo\nthree\nchanged\n")
    _git(repo, "commit", "-qam", "main commit")
    main_head = _git(repo, "rev-parse", "HEAD")
    exact = review_context.exact_git_context(
        str(repo),
        _exact_evidence(
            main_head, main_head, [{"old_path": "review.txt", "new_path": "review.txt"}]
        )
        | {"start_sha": side_head},
    )
    assert "local merge-base does not match evidence base_sha" in exact["errors"]
    assert "delta" not in exact
