"""Check Python behavior against the retained TypeScript-generated baseline."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from reviewmatic import context_package
from reviewmatic import draft as draft_module
from reviewmatic.portable import state_artifacts
from reviewmatic.portable.portable_gitlab import contract, review_semver
from reviewmatic.portable.portable_gitlab.label_assessment import validate_label_assessments

GOLDEN = Path(__file__).resolve().parent / "golden"
SOURCE_REVISION = "3e409c217e94d643f77eb543caab9a2ed4b7288d"
GOLDEN_NAMES = {
    "analysis-fingerprint-ci-only-drift.json",
    "analysis-fingerprint-material-change.json",
    "artifact-context-package-local-mode.json",
    "artifact-context-package-mr-needs-registry.json",
    "artifact-context-package-unbound-evidence.json",
    "artifact-context-package-valid.json",
    "artifact-evidence-snapshot-valid.json",
    "artifact-kind-mismatch.json",
    "artifact-local-review-report-foreign-field.json",
    "artifact-local-review-report-invalid-timestamp.json",
    "artifact-local-review-report-legacy-version.json",
    "artifact-local-review-report-valid.json",
    "canonical-containers.json",
    "canonical-key-order.json",
    "canonical-scalars.json",
    "canonical-unicode-order.json",
    "draft-gaps-complete.json",
    "draft-gaps-fresh.json",
    "draft-gaps-panel-awaiting-arbitration.json",
    "draft-gaps-panel-awaiting-receipt.json",
    "label-intent-extra-role.json",
    "label-intent-unknown-value.json",
    "label-intent-valid.json",
    "retirement-edited-question.json",
    "retirement-keeps-unaffected-question.json",
    "retirement-nothing-stale.json",
    "retirement-prior-decision-change.json",
    "retirement-unbound-answer-without-previous.json",
    "semver-assessment-fallback.json",
    "semver-assessment-missing-baseline.json",
    "semver-assessment-release.json",
    "semver-evidence-incomplete-component.json",
    "semver-evidence-valid.json",
}


def fixtures() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(GOLDEN.glob("*.json"))]


def test_golden_fixtures_exist() -> None:
    names = {path.name for path in GOLDEN.glob("*.json")}
    kinds = {fixture["kind"] for fixture in fixtures()}
    assert names == GOLDEN_NAMES
    assert {
        "canonical_digest",
        "artifact_validation_v2",
        "semver_evidence",
        "semver_assessment",
        "label_intent",
        "draft_gaps",
        "superseded_results",
        "analysis_fingerprint",
    } <= kinds


def test_golden_baseline_provenance_is_retained() -> None:
    provenance = (GOLDEN / "README.md").read_text(encoding="utf-8")
    assert SOURCE_REVISION in provenance
    assert "33 fixtures" in provenance


def test_golden_fixtures_carry_complete_expectations() -> None:
    for fixture in fixtures():
        assert set(fixture) == {"name", "kind", "input", "expected"}, fixture["name"]
        expected = fixture["expected"]
        assert {"digest", "valid", "python_valid"} <= set(expected), fixture["name"]
        assert contract.is_digest(expected["digest"]), fixture["name"]
        assert isinstance(expected["valid"], bool), fixture["name"]
        assert isinstance(expected["python_valid"], bool), fixture["name"]
        if expected["valid"] is not expected["python_valid"]:
            reason = expected.get("divergence_reason")
            assert isinstance(reason, str) and reason, fixture["name"]
        else:
            assert "divergence_reason" not in expected, fixture["name"]


@pytest.mark.parametrize("fixture", fixtures(), ids=lambda fixture: fixture.get("name", "?"))
def test_python_canon_matches_the_golden_digest_and_verdict(fixture: dict[str, Any]) -> None:
    assert contract.digest(fixture["input"]) == fixture["expected"]["digest"]
    # Both canonical serializers must produce identical bytes (the state
    # artifact form carries no trailing newline; the contract digest does).
    assert state_artifacts.canonical_json(fixture["input"]) + b"\n" == contract.canonical(
        fixture["input"]
    )
    # The Python canon is the strictness reference (decision 33): its own
    # verdict must match the declared python_valid expectation, and the
    # TypeScript divergence stays an explicitly documented exception.
    assert verdict(fixture) is fixture["expected"]["python_valid"]


TRANSITION_KINDS = {"draft_gaps", "superseded_results", "analysis_fingerprint"}


def transition_output(fixture: dict[str, Any]) -> Any:
    """Run the Python state-machine function the fixture's kind names."""
    kind, value = fixture["kind"], copy.deepcopy(fixture["input"])
    if kind == "draft_gaps":
        return draft_module.draft_gaps(value)
    if kind == "analysis_fingerprint":
        return draft_module.analysis_fingerprint(value)
    if kind == "superseded_results":
        result = context_package.extract_superseded_results(
            value["previous"], value["next"], value["answers"], value["verifications"]
        )
        if result is None:
            return None
        return {
            "entry": result.entry,
            "question_ids": result.question_ids,
            "answers": result.answers,
            "verifications": result.verifications,
        }
    raise AssertionError(f"unknown transition kind: {kind}")


@pytest.mark.parametrize(
    "fixture",
    [item for item in fixtures() if item["kind"] in TRANSITION_KINDS],
    ids=lambda fixture: fixture.get("name", "?"),
)
def test_python_state_machine_matches_the_frozen_transition_expectation(
    fixture: dict[str, Any],
) -> None:
    assert "output" in fixture["expected"], fixture["name"]
    assert transition_output(fixture) == fixture["expected"]["output"]


def test_only_transition_fixtures_carry_outputs() -> None:
    for fixture in fixtures():
        assert ("output" in fixture["expected"]) is (fixture["kind"] in TRANSITION_KINDS), fixture[
            "name"
        ]


def verdict(fixture: dict[str, Any]) -> bool:
    kind, value = fixture["kind"], fixture["input"]
    if kind in {"canonical_digest", *TRANSITION_KINDS}:
        return True
    if kind == "artifact_validation_v2":
        try:
            contract.validate_v2_artifact(value["artifact"], value["kind"])
        except contract.WorkflowError:
            return False
        return True
    if kind == "semver_evidence":
        return review_semver.evidence_is_valid(value)
    if kind == "semver_assessment":
        return review_semver.assessment_is_valid(value)
    if kind == "label_intent":
        return bool(contract.label_intent_is_valid(value))
    raise AssertionError(f"unknown fixture kind: {kind}")


def test_label_assessment_contract_stays_importable() -> None:
    evidence = {
        "labels": {
            "items": [{"name": "bug", "description": None}],
            "complete": True,
            "errors": [],
            "pages": 0,
            "truncated": False,
        },
        "object": {"labels": ["bug"]},
    }
    assessments = [
        {"name": "bug", "status": "applicable", "rationale": "The change fixes a defect."}
    ]
    result = validate_label_assessments(evidence, assessments, "patch")
    assert result["assessments"][0]["name"] == "bug"
    assert result["current"] == ["bug"]
    assert result["add"] == []
