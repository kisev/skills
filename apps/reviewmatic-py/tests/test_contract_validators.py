"""Contract validator regressions ported from the TypeScript contract suite.

Each scenario mirrors one ``contract.test.mjs`` case for the canon functions
that the review business logic consumes; see
``docs/reviewmatic-py-test-matrix.md`` for the complete TS-to-pytest mapping.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.portable.portable_gitlab.label_assessment import validate_label_assessments

DIGEST = "a" * 64


def workflow_error(match: str) -> Any:
    return pytest.raises(contract.WorkflowError, match=match)


def detailed_finding(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "finding-1",
        "severity": "low",
        "summary": "The contract example is concrete.",
        "risk": "Schema drift can invalidate emitted artifacts.",
        "evidence": ["tests/test_json_schemas.py"],
        "consequence": "A consumer could reject an artifact.",
        "relation_to_change": "The schema is part of the maintained contract.",
        "minimum_fix": "Keep the producer and schema aligned.",
        **overrides,
    }


def critic_payload() -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": DIGEST,
        "run_id": "critic-run",
        "session_id": "critic-session",
        "scope_digest": DIGEST,
        "target_finding_ids": [],
        "findings": [
            detailed_finding(
                id="rejected-1", summary="The broader cleanup is not part of this change."
            )
        ],
        "external_mutations": False,
    }


def decision_payload() -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/review-decision/v2",
        "evidence_digest": DIGEST,
        "finalize_digest": DIGEST,
        "context_digest": DIGEST,
        "critic_receipt_digest": DIGEST,
        "mode": "deep",
        "external_mutations": False,
        "run_id": "review-run",
        "session_id": "review-session",
        "verdict": "ready",
        "low_risk": True,
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "owner_decision_reasons": [],
        "findings": [detailed_finding()],
        "unresolved_threads": [],
        "responses": [
            {"id": "finding-1", "decision": "accept", "reason": "confirmed"},
            {"id": "rejected-1", "decision": "reject", "reason": "outside the changed contract"},
        ],
    }


def test_findings_validators_separate_legacy_and_detailed_shapes() -> None:
    detailed = detailed_finding()
    legacy = {"id": "finding-1"}
    assert contract.findings_are_valid([detailed]) is True
    assert contract.findings_are_valid([legacy]) is True
    assert contract.findings_are_valid([{"id": ""}]) is False
    assert contract.detailed_findings_are_valid([detailed]) is True
    assert contract.detailed_findings_are_valid([legacy]) is False
    assert contract.detailed_findings_are_valid([detailed_finding(severity="unknown")]) is False
    assert contract.detailed_findings_are_valid([detailed_finding(evidence=[])]) is False
    assert contract.detailed_findings_are_valid([detailed_finding(risk="")]) is False
    assert contract.duplicate_detailed_finding_ids(
        [detailed, detailed_finding(id="finding-2")]
    ) == [["finding-1", "finding-2"]]
    assert (
        contract.duplicate_detailed_finding_ids(
            [detailed, detailed_finding(id="finding-2", risk="Different risk.")]
        )
        == []
    )


def test_thread_decisions_validate_shape_outcome_and_patch_bindings() -> None:
    current = {
        "id": "thread:abc",
        "url": "https://gitlab.example/g/p/-/merge_requests/1#note_1",
        "state": "open",
        "assessment": "accepted",
        "rationale": "The finding is confirmed.",
        "outcome": "reply",
        "proposed_response": "Agreed.",
        "last_note_id": 5,
        "last_note_body_sha256": DIGEST,
        "thread_sha256": DIGEST,
    }
    assert contract.thread_decisions_are_valid([current]) is True
    assert contract.thread_decisions_are_valid([{**current, "suggestion_applicable": True}]) is True
    open_silent = {**current, "outcome": "no_publication"}
    assert contract.thread_decisions_are_valid([open_silent]) is False
    assert contract.thread_decisions_are_valid([{**open_silent, "state": "resolved"}]) is True
    patch = "diff --git a/f b/f\n"
    materialized = {
        **current,
        "state": "resolved",
        "assessment": "fixed",
        "outcome": "local_fix",
        "proposed_response": None,
        "fix_mode": "patch",
        "patch": patch,
        "fixing_commit": None,
        "patch_path": "/tmp/artifacts/f.patch",
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
    }
    assert contract.thread_decisions_are_valid([materialized]) is True
    assert contract.thread_decisions_are_valid([{**materialized, "patch": "other diff\n"}]) is False
    assert (
        contract.thread_decisions_are_valid([{**materialized, "patch_path": "relative.patch"}])
        is False
    )
    suggestion = {
        **materialized,
        "fix_mode": "suggestion",
        "patch": None,
        "patch_path": None,
        "patch_sha256": None,
    }
    assert contract.thread_decisions_are_valid([suggestion]) is True
    assert (
        contract.thread_decisions_are_valid([{**suggestion, "patch": "leftover diff\n"}]) is False
    )


def test_finding_publications_validate_fix_bindings() -> None:
    patch = "diff --git a/f b/f\n"
    patch_digest = hashlib.sha256(patch.encode()).hexdigest()
    legacy = {
        "finding_id": "finding-1",
        "revision": 1,
        "type": "general",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "Finding body",
    }
    assert contract.finding_publications_are_valid([legacy]) is True
    assert contract.finding_publications_are_valid([legacy], require_fixes=True) is False
    fixed = {
        **legacy,
        "fix_mode": "patch",
        "patch": patch,
        "patch_path": "/tmp/artifacts/f.patch",
        "patch_sha256": patch_digest,
    }
    assert contract.finding_publications_are_valid([fixed], require_fixes=True) is True
    assert (
        contract.finding_publications_are_valid(
            [{**fixed, "patch": "tampered\n"}], require_fixes=True
        )
        is False
    )
    assert contract.finding_publications_are_valid([{**fixed, "revision": 0}], True) is False
    assert contract.finding_publications_are_valid([{**fixed, "type": "inline"}], True) is False


def test_review_labels_derive_a_semantic_delta_from_catalog_and_intent() -> None:
    bundle = {
        "labels": {
            "items": [{"name": "kind::feature"}, {"name": "type::bug"}, {"name": "ambiguous"}],
            "complete": True,
        },
        "object": {"labels": ["kind::feature"]},
    }
    intent = {
        "change_type": "bug",
        "workflow_state": None,
        "urgency": None,
        "impact": None,
        "compatibility": None,
        "origin": None,
    }
    review = contract.review_labels(bundle, intent)
    assert review["complete"] is True
    assert review["current"] == ["kind::feature"]
    assert review["add"] == ["type::bug"]
    assert review["remove"] == ["kind::feature"]
    assert review["proposed"] == ["type::bug"]
    change_decision = next(item for item in review["decisions"] if item["role"] == "change_type")
    assert change_decision["action"] == "change"
    assert change_decision["desired_label"] == "type::bug"
    keep_decision = next(item for item in review["decisions"] if item["role"] == "workflow_state")
    assert keep_decision["action"] == "keep"
    assert keep_decision["intent"] is None
    incomplete = contract.review_labels(
        {"labels": {"items": [], "complete": False}, "object": {"labels": []}}, intent
    )
    assert incomplete["complete"] is False
    assert incomplete["unresolved"] == ["change_type=bug: project label catalog is incomplete"]
    with workflow_error("current MR labels are invalid"):
        contract.review_labels({"labels": {"items": []}, "object": {"labels": "nope"}}, intent)


def test_publication_preview_accepts_a_structured_action_plan() -> None:
    body_content = "Finding body\n"
    body_digest = hashlib.sha256(body_content.encode()).hexdigest()
    spec: dict[str, Any] = {
        "schema": "code-review/publication-action/v1",
        "preflight_sha256": DIGEST,
        "operation": "create_general",
        "publication": {"id": "finding-1", "revision": 1, "kind": "finding"},
        "body": {"path": "/tmp/portable-artifacts/finding-1.md", "sha256": body_digest},
        "expected": {"thread": None, "note": None, "prior_marker": None, "issue": None},
        "mutation": {"path": None, "line": None, "old_line": None},
    }
    preview: dict[str, Any] = {
        "mr_state": "merged",
        "warning": "Actions are prepared but were not executed.",
        "preflight_path": "/tmp/portable-artifacts/preflight.json",
        "preflight_sha256": DIGEST,
        "body_files": [
            {
                "publication_id": "finding-1",
                "revision": 1,
                "kind": "finding",
                "path": "/tmp/portable-artifacts/finding-1.md",
                "sha256": body_digest,
                "content": body_content,
            }
        ],
        "actions": [
            {
                "id": "finding:finding-1:r1:create_general",
                "sha256": contract.digest(spec),
                "kind": "finding",
                "publication_id": "finding-1",
                "revision": 1,
                "operation": "create_general",
                "command": "glab api --method POST projects/1/merge_requests/1/discussions",
                "spec": spec,
            }
        ],
    }
    assert contract.review_publication_preview_is_valid(preview) is True
    assert (
        contract.review_publication_preview_is_valid({**preview, "preflight_sha256": "nope"})
        is False
    )
    duplicated = {
        **preview,
        "actions": [preview["actions"][0], {**preview["actions"][0]}],
    }
    assert contract.review_publication_preview_is_valid(duplicated) is False
    spec_mismatch = {**spec, "operation": "create_line"}
    with_mismatch = {**preview, "actions": [{**preview["actions"][0], "spec": spec_mismatch}]}
    assert contract.review_publication_preview_is_valid(with_mismatch) is False


def test_metadata_assessment_validates_observed_fields() -> None:
    valid: dict[str, Any] = {
        "observed": {
            "title": "Fix schema drift",
            "description": None,
            "labels": ["type::bug"],
            "workflow_state": "merged",
        },
        "assessment": {
            "title": {"status": "ok", "rationale": "sufficient", "recommendation": None},
            "description": {
                "status": "needs_change",
                "rationale": "missing",
                "recommendation": "describe it",
            },
            "labels": {"status": "unverified", "rationale": "unknown", "recommendation": None},
            "workflow_state": {"status": "ok", "rationale": "sufficient", "recommendation": None},
            "overall": {"status": "ok", "rationale": "sufficient", "recommendation": None},
        },
    }
    assert contract.mr_metadata_assessment_is_valid(valid) is True
    assert (
        contract.mr_metadata_assessment_is_valid(
            {**valid, "observed": {**valid["observed"], "title": 5}}
        )
        is False
    )
    assert (
        contract.mr_metadata_assessment_is_valid(
            {
                **valid,
                "assessment": {
                    **valid["assessment"],
                    "overall": {"status": "unknown", "rationale": "x", "recommendation": None},
                },
            }
        )
        is False
    )


def test_incremental_review_state_validates_mode_bindings() -> None:
    delta: dict[str, Any] = {
        "from_head": None,
        "to_head": "c",
        "changed_paths": [],
        "changed_thread_ids": [],
        "unchanged_thread_ids": [],
        "changed_note_ids": [],
        "unchanged_note_ids": [],
        "metadata_fields": [],
        "pipelines_changed": False,
    }
    state: dict[str, Any] = {
        "contract_version": 1,
        "requested": "auto",
        "mode": "full",
        "reason": "no compatible finalized baseline exists",
        "incremental_baseline": {"plan_path": None, "plan_digest": None, "state_digest": None},
        "previous_findings": [],
        "previous_finding_publications": [],
        "previous_recommended_issues": [],
        "previous_finding_ledger": [],
        "previous_publication_ledger": [],
        "previous_thread_decisions": [],
        "previous_rejected_candidates": [],
        "reconsidered_rejected_candidates": [],
        "incremental_delta": delta,
        "incremental_delta_digest": contract.digest(delta),
        "critic_required": False,
        "fallback_reasons": [],
    }
    assert contract.incremental_review_is_valid(state) is True
    assert contract.incremental_review_is_valid({**state, "mode": "incremental"}) is False
    assert (
        contract.incremental_review_is_valid({**state, "incremental_delta_digest": DIGEST}) is False
    )
    incremental = {
        **state,
        "mode": "incremental",
        "critic_required": True,
        "incremental_baseline": {
            "plan_path": "/tmp/plan.md",
            "plan_digest": DIGEST,
            "state_digest": None,
        },
    }
    assert contract.incremental_review_is_valid(incremental) is True


def test_validate_critic_binds_evidence_and_scope() -> None:
    receipt: dict[str, Any] = critic_payload()
    contract.validate_critic(receipt, DIGEST, DIGEST)
    bare = {**critic_payload()}
    del bare["scope_digest"]
    del bare["target_finding_ids"]
    contract.validate_critic(bare, DIGEST)
    with workflow_error(r"\$\.evidence_digest: must bind the selected evidence digest"):
        contract.validate_critic(receipt, "b" * 64)
    with workflow_error(r"\$\.scope_digest: an incremental receipt must bind"):
        contract.validate_critic({**receipt, "scope_digest": "c" * 64}, DIGEST, DIGEST)
    with workflow_error("independent run identity"):
        contract.validate_critic({**receipt, "run_id": ""}, DIGEST)


def test_validate_decision_accounts_for_findings_and_threads() -> None:
    report = decision_payload()
    receipt = critic_payload()
    contract.validate_decision(report, DIGEST, receipt, "deep", DIGEST, DIGEST)
    with workflow_error("schema-invalid"):
        contract.validate_decision(
            {**report, "verdict": "unknown"}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    with workflow_error("does not account for every finding"):
        contract.validate_decision(
            {**report, "responses": []}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    no_critic_report = dict(report)
    del no_critic_report["critic_receipt_digest"]
    no_critic_report["responses"] = [
        response for response in report["responses"] if response["id"] == "finding-1"
    ]
    with workflow_error("independent critic receipt"):
        contract.validate_decision({**no_critic_report, "mode": "normal"}, DIGEST, None, "normal")
    with workflow_error("confirmed low-risk scope"):
        contract.validate_decision(
            {**no_critic_report, "mode": "fast", "low_risk": False}, DIGEST, None, "fast"
        )
    contract.validate_decision(
        {**no_critic_report, "mode": "fast", "low_risk": True}, DIGEST, None, "fast"
    )
    with workflow_error("blocking findings prohibit ready"):
        contract.validate_decision(
            {**report, "blocking_findings": True}, DIGEST, receipt, "deep", DIGEST, DIGEST
        )
    with_threads = {
        **report,
        "unresolved_threads": [{"id": "thread:note-1"}],
        "responses": [
            *report["responses"],
            {"id": "thread:note-1", "decision": "reject", "reason": "stale"},
        ],
    }
    contract.validate_decision(with_threads, DIGEST, receipt, "deep", DIGEST, DIGEST)
    bad_namespace = {
        **with_threads,
        "unresolved_threads": [{"id": "finding-1"}],
    }
    with workflow_error("namespace-safe"):
        contract.validate_decision(bad_namespace, DIGEST, receipt, "deep", DIGEST, DIGEST)


def test_model_label_delta_agreement_with_label_assessment() -> None:
    evidence = {
        "labels": {
            "items": [{"name": "kind::feature"}, {"name": "type::bug"}],
            "complete": True,
            "errors": [],
            "pages": 0,
            "truncated": False,
        },
        "object": {"labels": ["kind::feature"]},
    }
    intent = {
        "change_type": "bug",
        "workflow_state": None,
        "urgency": None,
        "impact": None,
        "compatibility": None,
        "origin": None,
    }
    modeled = contract.review_labels(evidence, intent)
    assessed = validate_label_assessments(
        evidence,
        [
            {"name": "type::bug", "status": "applicable", "rationale": "Matches the change kind."},
            {
                "name": "kind::feature",
                "status": "inapplicable",
                "rationale": "Equivalent to the preferred scoped type.",
            },
        ],
        "none",
    )
    assert modeled["add"] == assessed["add"] == ["type::bug"]
    assert modeled["remove"] == assessed["remove"] == ["kind::feature"]


def test_artifact_timestamp_contract_rejects_compact_iso_forms() -> None:
    # Decision 33: the Python validator is the strictness reference. The
    # canonical timestamp check is the extended ISO-8601 grammar; compact
    # basic formats stay rejected exactly like the TypeScript runtime.
    assert contract._iso_format_is_valid("2026-10-05T00:00:00+00:00") is True
    assert contract._iso_format_is_valid("2026-10-05 00:00:00") is True
    assert contract._iso_format_is_valid("2026-10-05") is True
    assert contract._iso_format_is_valid("20261005T000000") is False
    assert contract._iso_format_is_valid("2026-02-30T00:00:00+00:00") is False
    assert contract._iso_format_is_valid("2026-10-05T24:00:00+00:00") is False
    assert contract._iso_format_is_valid("2026-10-05T00:60:00+00:00") is False
