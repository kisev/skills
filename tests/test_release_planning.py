from __future__ import annotations

import copy
from typing import Any

import pytest

from shared.references.work_item_runtime import release_planning


def plan() -> dict[str, Any]:
    return {
        "decision": {
            "status": "accepted",
            "rationale": "The current task is ready and belongs on the roadmap.",
            "confidence": "high",
        },
        "semver": {
            "level": "patch",
            "rationale": "Corrects existing public behavior.",
            "confidence": "high",
        },
        "release": {
            "policy": "Published stable tags define the project release line.",
            "baseline_version": "1.0.0",
            "target_version": "1.1.0",
            "impact": "minor",
            "rationale": "The next planned release already contains compatible features.",
            "confidence": "high",
        },
        "milestone": {
            "status": "selected",
            "candidate": {
                "project_id": 19,
                "id": 9,
                "title": "v1.1.0",
                "state": "active",
                "version": "1.1.0",
            },
            "rationale": "This is the nearest compatible open release milestone.",
            "confidence": "high",
        },
    }


def catalog() -> list[dict[str, Any]]:
    return [{"project_id": 19, "id": 9, "title": "v1.1.0", "state": "active"}]


def validate(value: dict[str, Any]) -> dict[str, Any]:
    return release_planning.validate(
        value,
        quality_verdict="ready",
        milestone_catalog=catalog(),
        current_milestone_id=None,
    )


@pytest.mark.parametrize("impact", ["patch", "none", "not_applicable"])
def test_patch_planning_accepts_nearest_larger_compatible_release(impact: str) -> None:
    value = plan()
    value["semver"]["level"] = impact
    assert validate(value)["planning_verdict"] == "ready"


def test_lower_release_impact_and_closed_milestone_block() -> None:
    value = plan()
    value["semver"]["level"] = "major"
    result = validate(value)
    assert result["planning_verdict"] == "blocked"
    assert "lower than the task impact" in result["findings"][0]

    value = plan()
    value["milestone"]["candidate"]["state"] = "closed"
    closed_catalog = [{**catalog()[0], "state": "closed"}]
    result = release_planning.validate(
        value,
        quality_verdict="ready",
        milestone_catalog=closed_catalog,
        current_milestone_id=9,
    )
    assert result["planning_verdict"] == "blocked"


def test_pre_one_project_policy_may_classify_minor_bump_as_major() -> None:
    value = plan()
    value["semver"]["level"] = "major"
    value["release"].update(
        {
            "baseline_version": "0.4.0",
            "target_version": "0.5.0",
            "impact": "major",
            "policy": "Before 1.0, the project treats minor bumps as breaking releases.",
        }
    )
    value["milestone"]["candidate"].update({"title": "v0.5.0", "version": "0.5.0"})
    pre_one_catalog = [{"project_id": 19, "id": 9, "title": "v0.5.0", "state": "active"}]
    result = release_planning.validate(
        value,
        quality_verdict="ready",
        milestone_catalog=pre_one_catalog,
        current_milestone_id=None,
    )
    assert result["planning_verdict"] == "ready"


def test_missing_milestone_is_a_creation_proposal_until_recollected() -> None:
    value = plan()
    value["milestone"] = {
        "status": "create",
        "candidate": {
            "project_id": 19,
            "id": None,
            "title": "v1.1.0",
            "state": "proposed",
            "version": "1.1.0",
        },
        "rationale": "No compatible active milestone exists.",
        "confidence": "high",
    }
    result = release_planning.validate(
        value,
        quality_verdict="ready",
        milestone_catalog=[],
        current_milestone_id=None,
    )
    assert result["planning_verdict"] == "needs_clarification"
    assert "created and recollected" in result["findings"][0]


@pytest.mark.parametrize("decision", ["deferred", "rejected", "duplicate", "obsolete"])
def test_nonaccepted_work_has_no_milestone_or_removes_existing(decision: str) -> None:
    value = plan()
    value["decision"]["status"] = decision
    value["milestone"] = {
        "status": "none",
        "candidate": None,
        "rationale": "Non-accepted work is not assigned to a release.",
        "confidence": "high",
    }
    assert validate(value)["planning_verdict"] == "ready"

    value["milestone"]["status"] = "remove"
    result = release_planning.validate(
        value,
        quality_verdict="ready",
        milestone_catalog=catalog(),
        current_milestone_id=9,
    )
    assert result["planning_verdict"] == "ready"


def test_accepted_work_requires_semantic_readiness_and_catalog_binding() -> None:
    with pytest.raises(release_planning.PlanningError, match="semantically ready"):
        release_planning.validate(
            plan(),
            quality_verdict="needs_clarification",
            milestone_catalog=catalog(),
            current_milestone_id=None,
        )
    with pytest.raises(release_planning.PlanningError, match="observed catalog"):
        release_planning.validate(
            plan(),
            quality_verdict="ready",
            milestone_catalog=[],
            current_milestone_id=None,
        )
    unknown = copy.deepcopy(plan())
    unknown["semver"]["level"] = "unknown"
    with pytest.raises(release_planning.PlanningError, match="known SemVer"):
        validate(unknown)

    boolean_id = copy.deepcopy(plan())
    boolean_id["milestone"]["candidate"]["id"] = True
    with pytest.raises(release_planning.PlanningError, match="positive observed ID"):
        validate(boolean_id)
