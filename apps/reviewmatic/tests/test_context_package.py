"""Context-package digest, binding, and validation regressions.

Covers the unit surface of ``context-package.test.mjs`` that does not need the
draft state machine: canonical versus narrative digests, question context
versioning and result retirement, answer/verification bindings, and the MR
payload validation. The end-to-end record scenarios land with the draft port.
"""

from __future__ import annotations

from typing import Any

import pytest

from reviewmatic.context_package import (
    ExpectedPackage,
    bind_question_contexts,
    canonical_package_digest,
    extract_superseded_results,
    is_current_result,
    narrative_package_digest,
    question_context_digest,
    question_context_version,
    question_context_versions,
    question_report,
    validate_answers,
    validate_package_payload,
)
from reviewmatic.portable.portable_gitlab import contract

DIGEST = "a" * 64


def base_payload(**overrides: object) -> dict[str, Any]:
    payload: dict[str, object] = {
        "schema": "portable-gitlab/context-package/v2",
        "mode": "mr",
        "binding": {
            "evidence_digest": DIGEST,
            "artifact_root": "/tmp/artifacts",
            "repo_root": "/tmp/repo",
            "base_sha": "b" * 40,
            "head_sha": "b" * 40,
            "start_sha": "b" * 40,
        },
        "goal": {"status": "unknown"},
        "acceptance_criteria": {"status": "unknown", "items": []},
        "background": "Narrative only.",
        "claims": [],
        "constraints": [],
        "prior_decisions": [],
        "questions": [
            {"id": "q1", "subject": "Is the retry path bounded?", "source": "diff"},
            {"id": "q2", "subject": "Is the cleanup idempotent?", "source": "diff"},
        ],
        "thread_registry": [],
        "supersedes": None,
        "external_mutations": False,
        **overrides,
    }
    return payload


def test_editing_the_background_never_changes_the_canonical_digest() -> None:
    payload = base_payload()
    edited = base_payload(background="Reworded narrative.")
    assert canonical_package_digest(payload) == canonical_package_digest(edited)
    assert narrative_package_digest(payload) != narrative_package_digest(edited)


def test_question_versions_follow_meaningful_context() -> None:
    payload = base_payload()
    versions = question_context_versions(payload)
    assert set(versions) == {"q1", "q2"}
    edited_question = base_payload(
        questions=[
            {"id": "q1", "subject": "Reworded?", "source": "diff"},
            {"id": "q2", "subject": "Is the cleanup idempotent?", "source": "diff"},
        ]
    )
    reworded = question_context_versions(edited_question)
    assert reworded["q1"] != versions["q1"]
    assert reworded["q2"] == versions["q2"]
    assert question_context_version(payload, payload["questions"][0]) == versions["q1"]


def test_prior_decisions_change_both_package_and_question_context_bindings() -> None:
    before = base_payload(
        prior_decisions=[
            {"id": "deferral", "decision": "Credential revocation is deferred.", "source": "User"}
        ]
    )
    after = base_payload(
        prior_decisions=[
            {"id": "deferral", "decision": "Credential revocation is deferred.", "source": "User"},
            {"id": "correction", "decision": "The deferral is withdrawn.", "source": "User"},
        ]
    )
    assert question_context_digest(before) != question_context_digest(after)
    assert question_context_version(before, before["questions"][0]) != question_context_version(
        after, after["questions"][0]
    )


def test_manual_question_bindings_must_match_the_meaningful_context() -> None:
    payload = base_payload()
    bind_question_contexts(payload)
    versions = question_context_versions(payload)
    assert payload["questions"][0]["context_digest"] == versions["q1"]
    with pytest.raises(contract.WorkflowError, match="does not match its"):
        bind_question_contexts(
            base_payload(
                questions=[
                    {"id": "q1", "prompt": "Is the retry path bounded?", "context_digest": "c" * 64}
                ]
            )
        )


def test_results_retire_only_when_their_binding_is_stale() -> None:
    previous = base_payload()
    versions = question_context_versions(previous)
    current_payload = base_payload(
        questions=[
            {"id": "q1", "subject": "Reworded?", "source": "diff"},
            {"id": "q2", "subject": "Is the cleanup idempotent?", "source": "diff"},
        ]
    )
    current_versions = question_context_versions(current_payload)
    fresh = {
        "question_id": "q1",
        "verdict": "confirmed",
        "evidence": "x",
        "context_digest": current_versions["q1"],
    }
    stale = {
        "question_id": "q1",
        "verdict": "confirmed",
        "evidence": "x",
        "context_digest": versions["q1"],
    }
    unbound = {"question_id": "q2", "verdict": "not_verified", "reason": "unsure"}
    assert is_current_result(fresh, current_versions) is True
    assert is_current_result(stale, current_versions) is False
    assert is_current_result(unbound, current_versions) is False
    superseded = extract_superseded_results(
        {"payload": previous, "digest": DIGEST},
        current_payload,
        [fresh, stale],
        [unbound],
    )
    assert superseded is not None
    assert [item["context_digest"] for item in superseded.answers] == [versions["q1"]]
    assert superseded.verifications == [unbound]
    assert superseded.question_ids == ["q1", "q2"]
    assert superseded.entry["package_digest"] == DIGEST
    retained = {**fresh, "context_digest": versions["q1"]}
    assert extract_superseded_results(None, previous, [retained], []) is None


def test_answers_require_bindings_to_the_recorded_package() -> None:
    payload = base_payload()
    versions = question_context_versions(payload)
    good = {
        "question_id": "q1",
        "verdict": "confirmed",
        "evidence": "Inspected the exact head.",
        "run_id": "critic-run",
        "session_id": "critic-session",
        "context_digest": versions["q1"],
    }
    assert validate_answers([good], set(versions), versions, "answers") == [good]
    with pytest.raises(contract.WorkflowError, match="does not name a question"):
        validate_answers([{**good, "question_id": "q9"}], set(versions), versions, "answers")
    with pytest.raises(contract.WorkflowError, match="has no context binding"):
        validate_answers(
            [{key: value for key, value in good.items() if key != "context_digest"}],
            set(versions),
            versions,
            "answers",
        )
    with pytest.raises(contract.WorkflowError, match="is bound to context digest"):
        validate_answers([{**good, "context_digest": "c" * 64}], set(versions), versions, "answers")


def test_question_report_counts_verifications_against_originals() -> None:
    questions = [
        {"id": "q1", "critic": True},
        {"id": "q2", "critic": True},
    ]
    answers = [
        {
            "question_id": "q1",
            "verdict": "not_verified",
            "reason": "unsure",
            "run_id": "critic-run",
            "session_id": "critic-session",
        },
        {
            "question_id": "q2",
            "verdict": "confirmed",
            "evidence": "x",
            "run_id": "critic-run",
            "session_id": "critic-session",
        },
    ]
    verifications = [
        {
            "question_id": "q1",
            "verdict": "refuted",
            "evidence": "checked",
            "context_digest": "d" * 64,
            "original": {
                "run_id": "critic-run",
                "session_id": "critic-session",
                "verdict": "not_verified",
            },
        },
        {
            "question_id": "q2",
            "verdict": "unresolved",
            "reason": "unclear",
            "context_digest": "d" * 64,
            "original": {
                "run_id": "critic-run",
                "session_id": "critic-session",
                "verdict": "confirmed",
            },
        },
    ]
    report = question_report(questions, answers, verifications)
    assert report == {
        "assigned": 2,
        "answered": 2,
        "unverified": 0,
        "verified": 1,
        "unresolved": 1,
        "contradicted": 0,
    }


def test_mr_package_validation_binds_the_selected_evidence() -> None:
    payload = base_payload()
    expected = ExpectedPackage(
        mode="mr",
        evidence_digest=DIGEST,
        artifact_root="/tmp/artifacts",
        repo_root="/tmp/repo",
        base_sha="b" * 40,
        start_sha="b" * 40,
        head_sha="b" * 40,
    )
    bind_question_contexts(payload)
    validate_package_payload(payload, expected)
    with pytest.raises(contract.WorkflowError, match="does not bind the selected evidence"):
        validate_package_payload(
            payload, ExpectedPackage(**{**expected.__dict__, "evidence_digest": "e" * 64})
        )
    with pytest.raises(contract.WorkflowError, match="mode must match"):
        validate_package_payload(payload, ExpectedPackage(**{**expected.__dict__, "mode": "local"}))
