"""Local context-package and critic-answer scenarios, from local-review.test.mjs.

Covers: a full critic answer passing the schema, re-recording a changed local
package, late answers and verifications bound to a previous context, a
significant prior decision moving the question version, and mixed-version
recovery that retires only the stale critic answer.
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "q-renderer"
PROTECTED_SUBJECT = "Does the staged renderer change touch protected values?"
REVOCATION_SUBJECT = "Is credential revocation enforced on renderer failure?"


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


def _question(subject: str = PROTECTED_SUBJECT) -> dict[str, Any]:
    return {
        "id": QUESTION,
        "subject": subject,
        "source": "Local conversation with the author",
        "critic": True,
    }


def _initial_report(repo: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    root = str(bundle["artifact_root"])
    snapshot, digest = contract.write_artifact(Path(root), "local_wip_snapshot", bundle)
    context = local_review.prepare_followup(root, bundle, digest, "auto")
    report = _report_payload()
    report["evidence_digest"] = context["report_template"]["evidence_digest"]
    return snapshot, context, report


def _record_package(snapshot: Path, template_path: Path) -> dict[str, Any]:
    return local_review.record_local_package(str(snapshot), str(template_path))


def _record_review(snapshot: Path, draft_path: Path) -> dict[str, Any]:
    return local_review.record_review(str(draft_path.parent), str(snapshot), str(draft_path))


def _package_ref(recorded: dict[str, Any]) -> dict[str, str]:
    return {"path": recorded["artifact_path"], "digest": recorded["digest"]}


def _read_draft(draft_path: Path) -> dict[str, Any]:
    return contract.read_json(draft_path, "local review draft")


def _finalize_local_cli(snapshot: Path, draft_path: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "reviewmatic",
            "finalize-local",
            "--bundle",
            str(snapshot),
            "--report",
            str(draft_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )


def _critic_answer(
    context_digest: str,
    evidence: str,
    run: str = "local-critic-run",
    session: str = "local-critic-session",
) -> dict[str, Any]:
    return {
        "question_id": QUESTION,
        "verdict": "confirmed",
        "evidence": evidence,
        "run_id": run,
        "session_id": session,
        "context_digest": context_digest,
    }


def _verification(context_digest: str, evidence: str) -> dict[str, Any]:
    return {
        "question_id": QUESTION,
        "original": {
            "run_id": "local-primary",
            "session_id": "local-session",
            "verdict": "not_verified",
        },
        "verdict": "confirmed",
        "evidence": evidence,
        "context_digest": context_digest,
    }


def _start_question_package(
    repo: Path, **edits: Any
) -> tuple[Path, dict[str, Any], dict[str, Any], Path, dict[str, Any], Path]:
    """Record V1 with one critic question and write a draft bound to it."""
    snapshot, context, report = _initial_report(repo)
    template_path = Path(str(context["context_package"]["template_path"]))
    template = contract.read_json(template_path, "template")
    template["goal"] = {"status": "known", "text": report["task"]["goal"]}
    template["questions"] = [_question()]
    template.update(edits)
    contract.write_json(template_path, template)
    v1 = _record_package(snapshot, template_path)
    draft = copy.deepcopy(report)
    draft["context_package"] = _package_ref(v1)
    return snapshot, template, v1, template_path, draft, Path(str(context["draft_path"]))


def test_a_full_critic_answer_passes_the_schema_and_finalizes_the_local_report(
    repo: Path,
) -> None:
    report = _report_payload()
    report["question_answers"] = [
        {
            "question_id": QUESTION,
            "verdict": "confirmed",
            "evidence": "The staged diff only rewrites plain text values.",
            "run_id": "local-critic-run",
            "session_id": "local-critic-session",
        }
    ]
    local_review.validate_report(report)

    snapshot, context, review = _initial_report(repo)
    review["verdict"] = "ready"
    review["findings"][0]["status"] = "fixed"
    review["findings"][0]["blocking"] = False
    review["findings"][0]["evidence"] = "Table remains unchanged."
    template_path = Path(str(context["context_package"]["template_path"]))
    template = contract.read_json(template_path, "template")
    template["goal"] = {"status": "known", "text": review["task"]["goal"]}
    template["acceptance_criteria"] = {
        "status": "known",
        "items": review["task"]["acceptance_criteria"],
    }
    template["questions"] = [
        {
            "id": QUESTION,
            "subject": "Does the staged renderer change touch protected values?",
            "source": "Local conversation with the author",
            "critic": True,
        }
    ]
    contract.write_json(template_path, template)
    recorded = _record_package(snapshot, template_path)
    review["context_package"] = _package_ref(recorded)
    review["question_answers"] = [
        {**answer, "context_digest": recorded["question_context_versions"][answer["question_id"]]}
        for answer in report["question_answers"]
    ]
    draft_path = Path(str(context["draft_path"]))
    contract.write_json(draft_path, review)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "ready"
    assert saved["question_summary"]["answered"] == 1


def test_re_recording_a_changed_local_package_retires_answers_for_the_old_questions(
    repo: Path,
) -> None:
    snapshot, template, v1, template_path, draft, draft_path = _start_question_package(repo)
    draft["question_answers"] = [
        _critic_answer(
            v1["question_context_versions"][QUESTION],
            "Inspected protected values in the staged diff.",
        )
    ]
    contract.write_json(draft_path, draft)

    template["supersedes"] = v1["digest"]
    template["questions"] = [_question(REVOCATION_SUBJECT)]
    contract.write_json(template_path, template)
    v2 = _record_package(snapshot, template_path)
    assert v2["superseded_questions"] == [QUESTION]
    updated = _read_draft(draft_path)
    assert updated["question_answers"] == []
    assert len(updated["superseded_question_results"]) == 1
    retired = updated["superseded_question_results"][0]
    assert retired["package_digest"] == v1["digest"]
    assert retired["answers"][0]["run_id"] == "local-critic-run", (
        "authorship is preserved historically"
    )
    assert retired["answers"][0]["context_digest"] == v1["question_context_versions"][QUESTION], (
        "history keeps the binding the answer was collected under"
    )

    updated["context_package"] = _package_ref(v2)
    contract.write_json(draft_path, updated)
    with pytest.raises(contract.WorkflowError, match=r"superseded context package"):
        _record_review(snapshot, draft_path)

    updated["question_answers"] = [
        _critic_answer(
            v2["question_context_versions"][QUESTION],
            "Traced the revocation path in the staged renderer.",
            "local-critic-run-2",
            "local-critic-session-2",
        )
    ]
    contract.write_json(draft_path, updated)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "not_ready"
    assert len(_read_draft(draft_path)["superseded_question_results"]) == 1


def test_a_late_local_answer_for_the_previous_package_cannot_certify_the_changed_question(
    repo: Path,
) -> None:
    snapshot, template, v1, template_path, draft, draft_path = _start_question_package(repo)
    contract.write_json(draft_path, draft)

    # The report author records a changed question before the critic answers.
    template["supersedes"] = v1["digest"]
    template["questions"] = [_question(REVOCATION_SUBJECT)]
    contract.write_json(template_path, template)
    v2 = _record_package(snapshot, template_path)
    assert v2["superseded_questions"] == []

    # The late answer arrives, still bound to the superseded context version.
    updated = _read_draft(draft_path)
    updated["context_package"] = _package_ref(v2)
    updated["question_answers"] = [
        _critic_answer(
            v1["question_context_versions"][QUESTION],
            "Inspected protected values only, before the package changed.",
        )
    ]
    contract.write_json(draft_path, updated)
    execution = _finalize_local_cli(snapshot, draft_path)
    assert execution.returncode != 0, "finalize-local accepted a stale V1 answer for V2"
    assert "is bound to context digest" in execution.stderr
    assert QUESTION in execution.stderr
    with pytest.raises(contract.WorkflowError, match=r"is bound to context digest"):
        _record_review(snapshot, draft_path)

    # Recovery: a fresh answer bound to the recorded package finalizes normally.
    updated["question_answers"] = [
        _critic_answer(
            v2["question_context_versions"][QUESTION],
            "Traced the revocation path in the staged renderer.",
            "local-critic-run-2",
            "local-critic-session-2",
        )
    ]
    contract.write_json(draft_path, updated)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "not_ready"
    assert "superseded_question_results" not in _read_draft(draft_path)


def test_a_verification_bound_to_the_previous_context_cannot_verify_the_changed_question(
    repo: Path,
) -> None:
    snapshot, template, v1, template_path, draft, draft_path = _start_question_package(repo)
    contract.write_json(draft_path, draft)

    template["supersedes"] = v1["digest"]
    template["questions"] = [_question(REVOCATION_SUBJECT)]
    contract.write_json(template_path, template)
    v2 = _record_package(snapshot, template_path)

    # A primary verification performed before the supersession is bound to V1.
    updated = _read_draft(draft_path)
    updated["context_package"] = _package_ref(v2)
    updated["question_verifications"] = [
        _verification(
            v1["question_context_versions"][QUESTION],
            "Verified the protected-value question before the package changed.",
        )
    ]
    contract.write_json(draft_path, updated)
    with pytest.raises(contract.WorkflowError, match=r"is bound to context digest"):
        _record_review(snapshot, draft_path)

    updated["question_verifications"] = [
        _verification(
            v2["question_context_versions"][QUESTION],
            "Traced the revocation path in the staged renderer.",
        )
    ]
    contract.write_json(draft_path, updated)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "not_ready"


def test_a_significant_local_prior_decision_invalidates_a_late_answer_for_the_same_question(
    repo: Path,
) -> None:
    snapshot, template, v1, template_path, draft, draft_path = _start_question_package(
        repo,
        prior_decisions=[
            {
                "id": "scope-deferral",
                "decision": "Credential revocation on renderer failure is deferred.",
                "source": "Earlier user decision in the local conversation.",
            }
        ],
    )
    contract.write_json(draft_path, draft)

    # The user withdraws the deferral. The question keeps its ID and subject;
    # the significant agreed decision still moves its version.
    template["supersedes"] = v1["digest"]
    template["prior_decisions"].append(
        {
            "id": "scope-correction",
            "decision": "The deferral is withdrawn; revocation is required in this review.",
            "source": "Explicit later user correction in the local conversation.",
        }
    )
    contract.write_json(template_path, template)
    v2 = _record_package(snapshot, template_path)
    assert v2["superseded_questions"] == []
    assert v1["question_context_versions"][QUESTION] != v2["question_context_versions"][QUESTION], (
        "the agreed decision change moves the question version"
    )

    # The late V1 answer arrives with its original binding.
    updated = _read_draft(draft_path)
    updated["context_package"] = _package_ref(v2)
    late_answer = _critic_answer(
        v1["question_context_versions"][QUESTION],
        "Inspected the staged diff under the original deferral.",
    )
    updated["question_answers"] = [late_answer]
    contract.write_json(draft_path, updated)
    execution = _finalize_local_cli(snapshot, draft_path)
    assert execution.returncode != 0, "finalize-local accepted the stale V1 answer for V2"
    assert "is bound to context digest" in execution.stderr
    assert QUESTION in execution.stderr

    # Documented recovery: re-record the current package.
    template["supersedes"] = v2["digest"]
    contract.write_json(template_path, template)
    v3 = _record_package(snapshot, template_path)
    assert v3["superseded_questions"] == [QUESTION]
    recovered = _read_draft(draft_path)
    assert recovered["question_answers"] == []
    assert len(recovered["superseded_question_results"]) == 1
    retired = recovered["superseded_question_results"][0]
    assert len(retired["answers"]) == 1
    assert retired["answers"][0]["evidence"] == late_answer["evidence"]
    assert retired["answers"][0]["run_id"] == "local-critic-run"
    assert retired["answers"][0]["context_digest"] == v1["question_context_versions"][QUESTION]

    # A fresh bound answer finalizes; the saved report keeps the complete fresh
    # evidence and the full retired history.
    recovered["context_package"] = _package_ref(v3)
    recovered["question_answers"] = [
        _critic_answer(
            v3["question_context_versions"][QUESTION],
            "Traced revocation in the staged renderer under the corrected scope.",
            "local-critic-run-2",
            "local-critic-session-2",
        )
    ]
    contract.write_json(draft_path, recovered)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "not_ready"
    _, payload = contract.artifact_payload(Path(saved["artifact_path"]), "local_review_report")
    assert [
        [item["evidence"], item["run_id"], item["context_digest"]]
        for item in payload["question_answers"]
    ] == [
        [
            "Traced revocation in the staged renderer under the corrected scope.",
            "local-critic-run-2",
            v3["question_context_versions"][QUESTION],
        ]
    ]
    assert len(payload["superseded_question_results"]) == 1
    historical = payload["superseded_question_results"][0]["answers"][0]
    assert historical["evidence"] == late_answer["evidence"]
    assert historical["context_digest"] == v1["question_context_versions"][QUESTION]


def test_local_mixed_version_recovery_keeps_the_fresh_critic_answer_and_retires_only_the_stale_one(
    repo: Path,
) -> None:
    snapshot, template, v1, template_path, draft, draft_path = _start_question_package(repo)
    contract.write_json(draft_path, draft)

    # The question changes before critic A answers; the late V1 answer and a
    # fresh V2 answer from critic B then coexist in the report.
    template["supersedes"] = v1["digest"]
    template["questions"][0]["subject"] = REVOCATION_SUBJECT
    contract.write_json(template_path, template)
    v2 = _record_package(snapshot, template_path)
    assert v2["superseded_questions"] == []

    updated = _read_draft(draft_path)
    updated["context_package"] = _package_ref(v2)
    stale_answer = _critic_answer(
        v1["question_context_versions"][QUESTION],
        "Critic A inspected protected values under V1, late.",
        "local-critic-a",
        "local-critic-a-session",
    )
    fresh_answer = {
        "question_id": QUESTION,
        "verdict": "not_verified",
        "reason": "Critic B could not trace the revocation path in time.",
        "run_id": "local-critic-b",
        "session_id": "local-critic-b-session",
        "context_digest": v2["question_context_versions"][QUESTION],
    }
    fresh_verification = {
        "question_id": QUESTION,
        "original": {
            "run_id": "local-critic-b",
            "session_id": "local-critic-b-session",
            "verdict": "not_verified",
        },
        "verdict": "confirmed",
        "evidence": "Primary traced the revocation path in the staged renderer.",
        "context_digest": v2["question_context_versions"][QUESTION],
    }
    updated["question_answers"] = [stale_answer, fresh_answer]
    updated["question_verifications"] = [fresh_verification]
    contract.write_json(draft_path, updated)

    # Documented recovery: re-record the current package.
    template["supersedes"] = v2["digest"]
    contract.write_json(template_path, template)
    v3 = _record_package(snapshot, template_path)
    assert v3["superseded_questions"] == [QUESTION]
    after = _read_draft(draft_path)
    assert after["question_answers"] == [fresh_answer], (
        "only critic A's stale answer leaves the active results"
    )
    assert after["question_verifications"] == [fresh_verification]
    assert len(after["superseded_question_results"]) == 1
    assert after["superseded_question_results"][0]["answers"] == [stale_answer]
    assert after["superseded_question_results"][0]["verifications"] == []

    # A repeated recovery neither duplicates history nor drops fresh results.
    template["supersedes"] = v3["digest"]
    template["background"] = "Presentation-only narrative revision."
    contract.write_json(template_path, template)
    v4 = _record_package(snapshot, template_path)
    assert v4["superseded_questions"] == []
    stable = _read_draft(draft_path)
    assert len(stable["superseded_question_results"]) == 1
    assert stable["question_answers"] == [fresh_answer]
    assert stable["question_verifications"] == [fresh_verification]

    # Critic A's retired V1 answer never counts: the report finalizes only
    # through critic B's current answer, and the saved payload shows the fresh
    # evidence as the sole active result with the stale one only in history.
    stable["context_package"] = _package_ref(v4)
    contract.write_json(draft_path, stable)
    saved = _record_review(snapshot, draft_path)
    assert saved["verdict"] == "not_ready"
    _, payload = contract.artifact_payload(Path(saved["artifact_path"]), "local_review_report")
    assert [
        [item.get("evidence", item.get("reason")), item["run_id"]]
        for item in payload["question_answers"]
    ] == [["Critic B could not trace the revocation path in time.", "local-critic-b"]]
    assert len(payload["question_verifications"]) == 1
    assert len(payload["superseded_question_results"]) == 1
    assert payload["superseded_question_results"][0]["answers"][0]["run_id"] == "local-critic-a"
