"""Shared validation for task-level release and milestone planning."""

from __future__ import annotations

import re
from typing import Any

IMPACTS = {"major", "minor", "patch", "none", "not_applicable", "unknown"}
RELEASE_IMPACTS = {"major", "minor", "patch"}
DECISIONS = {"accepted", "deferred", "rejected", "duplicate", "obsolete"}
MILESTONE_STATUSES = {"selected", "create", "none", "remove", "unknown"}
CONFIDENCE = {"low", "medium", "high"}
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
RANK = {"patch": 1, "minor": 2, "major": 3}


class PlanningError(ValueError):
    """Release plan is malformed or not bound to supplied evidence."""


def fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise PlanningError(f"{label} must contain exactly {sorted(expected)}")
    return value


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlanningError(f"{label} must be non-empty text")
    return value.strip()


def confidence(value: object, label: str) -> str:
    if value not in CONFIDENCE:
        raise PlanningError(f"{label} must be low, medium, or high")
    return str(value)


def assessment(value: object, levels: set[str], label: str) -> dict[str, str]:
    item = fields(value, {"level", "rationale", "confidence"}, label)
    if item["level"] not in levels:
        raise PlanningError(f"{label}.level is unsupported")
    return {
        "level": str(item["level"]),
        "rationale": text(item["rationale"], f"{label}.rationale"),
        "confidence": confidence(item["confidence"], f"{label}.confidence"),
    }


def version(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or SEMVER_RE.fullmatch(value) is None:
        raise PlanningError(f"{label} must be a normalized stable SemVer")
    return value


def release_impact(baseline: str, target: str) -> str:
    before = tuple(int(part) for part in baseline.split("."))
    after = tuple(int(part) for part in target.split("."))
    if after <= before:
        raise PlanningError("target release must be newer than the published baseline")
    if after[0] != before[0]:
        return "major"
    if after[1] != before[1]:
        return "minor"
    return "patch"


def milestone_candidate(value: object, label: str) -> dict[str, Any]:
    item = fields(value, {"project_id", "id", "title", "state", "version"}, label)
    if type(item["project_id"]) is not int or item["project_id"] < 1:
        raise PlanningError(f"{label}.project_id must be a positive observed ID")
    if item["id"] is not None and (type(item["id"]) is not int or item["id"] < 1):
        raise PlanningError(f"{label}.id must be a positive observed ID or null")
    state = item["state"]
    if state not in {"active", "closed", "proposed"}:
        raise PlanningError(f"{label}.state is unsupported")
    return {
        "project_id": item["project_id"],
        "id": item["id"],
        "title": text(item["title"], f"{label}.title"),
        "state": state,
        "version": version(item["version"], f"{label}.version"),
    }


def catalog_match(candidate: dict[str, Any], catalog: list[dict[str, Any]]) -> bool:
    return any(
        raw.get("project_id") == candidate["project_id"]
        and raw.get("id") == candidate["id"]
        and raw.get("title") == candidate["title"]
        and raw.get("state") == candidate["state"]
        for raw in catalog
    )


def validate(
    value: object,
    *,
    quality_verdict: str,
    milestone_catalog: list[dict[str, Any]],
    current_milestone_id: int | None,
) -> dict[str, Any]:
    plan = fields(value, {"decision", "semver", "release", "milestone"}, "release plan")
    decision = fields(plan["decision"], {"status", "rationale", "confidence"}, "decision")
    if decision["status"] not in DECISIONS:
        raise PlanningError("decision.status is unsupported")
    normalized_decision = {
        "status": decision["status"],
        "rationale": text(decision["rationale"], "decision.rationale"),
        "confidence": confidence(decision["confidence"], "decision.confidence"),
    }
    semver = assessment(plan["semver"], IMPACTS, "semver")
    release = fields(
        plan["release"],
        {"policy", "baseline_version", "target_version", "impact", "rationale", "confidence"},
        "release",
    )
    baseline = version(release["baseline_version"], "release.baseline_version", nullable=True)
    target = version(release["target_version"], "release.target_version", nullable=True)
    impact = release["impact"]
    if impact is not None and impact not in RELEASE_IMPACTS:
        raise PlanningError("release.impact is unsupported")
    normalized_release = {
        "policy": text(release["policy"], "release.policy"),
        "baseline_version": baseline,
        "target_version": target,
        "impact": impact,
        "rationale": text(release["rationale"], "release.rationale"),
        "confidence": confidence(release["confidence"], "release.confidence"),
    }
    if baseline is not None and target is not None:
        conventional_impact = release_impact(baseline, target)
        if int(baseline.split(".")[0]) > 0 and impact != conventional_impact:
            raise PlanningError("release impact does not match baseline and target versions")

    milestone = fields(
        plan["milestone"], {"status", "candidate", "rationale", "confidence"}, "milestone"
    )
    status = milestone["status"]
    if status not in MILESTONE_STATUSES:
        raise PlanningError("milestone.status is unsupported")
    candidate = (
        milestone_candidate(milestone["candidate"], "milestone.candidate")
        if milestone["candidate"] is not None
        else None
    )
    normalized_milestone = {
        "status": status,
        "candidate": candidate,
        "rationale": text(milestone["rationale"], "milestone.rationale"),
        "confidence": confidence(milestone["confidence"], "milestone.confidence"),
    }

    findings: list[str] = []
    planning_verdict = "ready"
    accepted = normalized_decision["status"] == "accepted"
    if accepted:
        if quality_verdict != "ready":
            raise PlanningError("only a semantically ready task may be accepted")
        if semver["level"] == "unknown":
            raise PlanningError("an accepted task requires a known SemVer impact")
        if target is None or impact is None:
            raise PlanningError("an accepted task requires a target release")
        required = "patch" if semver["level"] in {"none", "not_applicable"} else semver["level"]
        if required not in RANK or RANK[impact] < RANK[required]:
            planning_verdict = "blocked"
            findings.append("selected release impact is lower than the task impact")
        if status not in {"selected", "create"} or candidate is None:
            raise PlanningError("an accepted task requires a selected or proposed milestone")
        if candidate["version"] != target:
            planning_verdict = "blocked"
            findings.append("milestone version does not match the target release")
        if status == "selected":
            if candidate["id"] is None or not catalog_match(candidate, milestone_catalog):
                raise PlanningError("selected milestone is not bound to the observed catalog")
            if candidate["state"] != "active":
                planning_verdict = "blocked"
                findings.append("selected milestone is not active")
        else:
            if candidate["id"] is not None or candidate["state"] != "proposed":
                raise PlanningError("a proposed milestone must have null ID and proposed state")
            if any(
                raw.get("project_id") == candidate["project_id"]
                and raw.get("title") == candidate["title"]
                and raw.get("state") == "active"
                for raw in milestone_catalog
            ):
                raise PlanningError("proposed milestone already exists in the observed catalog")
            if planning_verdict != "blocked":
                planning_verdict = "needs_clarification"
                findings.append(
                    "proposed milestone must be created and recollected before assignment"
                )
    else:
        expected = "remove" if current_milestone_id is not None else "none"
        if status != expected or candidate is not None:
            raise PlanningError(f"non-accepted task requires milestone status {expected}")
        if quality_verdict == "blocked":
            planning_verdict = "blocked"

    return {
        "decision": normalized_decision,
        "semver": semver,
        "release": normalized_release,
        "milestone": normalized_milestone,
        "planning_verdict": planning_verdict,
        "findings": findings,
    }
