#!/usr/bin/env python3
"""Validate the portable normalized work-item contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "work-item/v1"
VERDICTS = {"ready", "needs_clarification", "blocked"}
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def finding(
    code: str,
    path: str,
    message: str,
    severity: str = "error",
    evidence: list[str] | None = None,
    change: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "path": path, "message": message, "severity": severity}
    if evidence:
        result["evidence"] = sorted(evidence)
    if change:
        result["recommended_change"] = change
    return result


def sorted_findings(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            SEVERITY_ORDER.get(str(item.get("severity")), 9),
            str(item.get("code", "")),
            str(item.get("path", "")),
            str(item.get("message", "")),
        ),
    )


def load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def machine_checks(item: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    required = (
        "contract_version",
        "item_id",
        "problem",
        "outcome",
        "acceptance_criteria",
        "scope",
        "dependencies",
        "external_actions",
        "assumptions",
        "safety",
        "risks",
        "unresolved_questions",
        "stop_conditions",
    )
    for key in required:
        if key not in item:
            findings.append(
                finding(
                    "MISSING_FIELD",
                    key,
                    f"required field {key!r} is missing",
                    change=f"Add {key} to the normalized item.",
                )
            )
    allowed = set(required)
    for key in sorted(set(item) - allowed):
        findings.append(finding("UNKNOWN_FIELD", key, f"field {key!r} is not part of work-item/v1"))
    if item.get("contract_version") != CONTRACT_VERSION:
        findings.append(
            finding("SCHEMA_VERSION", "contract_version", f"expected {CONTRACT_VERSION!r}")
        )
    for key in ("problem", "outcome"):
        if key in item and (not isinstance(item[key], str) or not item[key].strip()):
            findings.append(finding("INVALID_TEXT", key, "must be a non-empty string"))
    scope = item.get("scope")
    if isinstance(scope, dict):
        inside = {
            str(value).strip().casefold()
            for value in scope.get("in_scope", [])
            if isinstance(value, str)
        }
        outside = {
            str(value).strip().casefold()
            for value in scope.get("non_goals", [])
            if isinstance(value, str)
        }
        for overlap in sorted(inside & outside):
            findings.append(
                finding(
                    "BOUNDARY_CONFLICT",
                    "scope",
                    f"boundary appears in both in_scope and non_goals: {overlap!r}",
                    change="Move the boundary to exactly one list.",
                )
            )
        outcome = str(item.get("outcome", "")).casefold()
        for boundary in sorted(outside):
            if boundary and boundary in outcome:
                findings.append(
                    finding(
                        "OUTCOME_SCOPE_CONFLICT",
                        "outcome",
                        f"outcome mentions explicit non-goal {boundary!r}",
                    )
                )
        safety = item.get("safety")
        constraints = safety.get("constraints", []) if isinstance(safety, dict) else []
        if isinstance(constraints, list):
            for constraint in constraints:
                if isinstance(constraint, str) and constraint.strip().casefold() in inside:
                    findings.append(
                        finding(
                            "SAFETY_SCOPE_CONFLICT",
                            "safety.constraints",
                            f"safety constraint conflicts with in_scope boundary {constraint!r}",
                        )
                    )
    criteria = item.get("acceptance_criteria")
    criterion_ids: set[str] = set()
    if not isinstance(criteria, list) or not criteria:
        findings.append(
            finding("INVALID_CRITERIA", "acceptance_criteria", "at least one criterion is required")
        )
    else:
        for index, criterion in enumerate(criteria):
            path = f"acceptance_criteria[{index}]"
            if not isinstance(criterion, dict):
                findings.append(finding("INVALID_CRITERION", path, "criterion must be an object"))
                continue
            identifier = criterion.get("id")
            if not isinstance(identifier, str) or not identifier:
                findings.append(
                    finding("INVALID_CRITERION_ID", f"{path}.id", "criterion id is required")
                )
            elif identifier in criterion_ids:
                findings.append(
                    finding("DUPLICATE_ID", f"{path}.id", f"duplicate criterion id {identifier!r}")
                )
            else:
                criterion_ids.add(identifier)
            if (
                not isinstance(criterion.get("statement"), str)
                or not criterion["statement"].strip()
            ):
                findings.append(
                    finding(
                        "INVALID_CRITERION", f"{path}.statement", "criterion statement is required"
                    )
                )
            if not isinstance(criterion.get("evidence"), list) or not criterion["evidence"]:
                findings.append(
                    finding(
                        "MISSING_EVIDENCE",
                        f"{path}.evidence",
                        "criterion requires at least one evidence description",
                    )
                )
    dependencies = item.get("dependencies")
    dependency_ids: set[str] = set()
    dependency_map: dict[str, dict[str, Any]] = {}
    if not isinstance(dependencies, list):
        findings.append(
            finding("INVALID_DEPENDENCIES", "dependencies", "dependencies must be an array")
        )
    else:
        for index, dependency in enumerate(dependencies):
            path = f"dependencies[{index}]"
            if not isinstance(dependency, dict):
                findings.append(finding("INVALID_DEPENDENCY", path, "dependency must be an object"))
                continue
            if dependency.get("status") not in {"available", "pending", "blocked"}:
                findings.append(
                    finding(
                        "INVALID_DEPENDENCY_STATUS",
                        f"{path}.status",
                        "status must be available, pending or blocked",
                    )
                )
            identifier = dependency.get("id")
            if not isinstance(identifier, str) or not identifier:
                findings.append(
                    finding("INVALID_DEPENDENCY_ID", f"{path}.id", "dependency id is required")
                )
            elif identifier in dependency_ids:
                findings.append(
                    finding("DUPLICATE_ID", f"{path}.id", f"duplicate dependency id {identifier!r}")
                )
            else:
                dependency_ids.add(identifier)
                dependency_map[identifier] = dependency
        for identifier, dependency in sorted(dependency_map.items()):
            for reference in (
                dependency.get("depends_on", [])
                if isinstance(dependency.get("depends_on"), list)
                else []
            ):
                if reference not in dependency_ids:
                    findings.append(
                        finding(
                            "BROKEN_REFERENCE",
                            f"dependencies[{identifier}].depends_on",
                            f"unknown dependency {reference!r}",
                        )
                    )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(identifier: str, trail: list[str]) -> None:
            if identifier in visiting:
                cycle = trail[trail.index(identifier) :] + [identifier]
                findings.append(
                    finding(
                        "DEPENDENCY_CYCLE",
                        "dependencies",
                        "dependency cycle: " + " -> ".join(cycle),
                    )
                )
                return
            if identifier in visited:
                return
            visiting.add(identifier)
            for reference in dependency_map[identifier].get("depends_on", []):
                if reference in dependency_map:
                    visit(reference, trail + [reference])
            visiting.remove(identifier)
            visited.add(identifier)

        for identifier in sorted(dependency_map):
            visit(identifier, [identifier])
    if isinstance(criteria, list):
        for index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                continue
            for reference in (
                criterion.get("dependencies", [])
                if isinstance(criterion.get("dependencies"), list)
                else []
            ):
                if reference not in dependency_ids:
                    findings.append(
                        finding(
                            "BROKEN_REFERENCE",
                            f"acceptance_criteria[{index}].dependencies",
                            f"unknown dependency {reference!r}",
                        )
                    )
                elif dependency_map.get(reference, {}).get("status") == "blocked":
                    findings.append(
                        finding(
                            "UNREACHABLE_CRITERION",
                            f"acceptance_criteria[{index}]",
                            f"criterion depends on blocked dependency {reference!r}",
                        )
                    )
                elif dependency_map.get(reference, {}).get("status") == "pending":
                    findings.append(
                        finding(
                            "UNAVAILABLE_DEPENDENCY",
                            f"acceptance_criteria[{index}]",
                            f"criterion depends on pending dependency {reference!r}",
                        )
                    )
    return findings


def semantic_checks(semantic: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    if semantic is None:
        return "needs_clarification", [
            finding(
                "SEMANTIC_ASSESSMENT_REQUIRED",
                "semantic_assessment",
                "an independent feasibility and consistency assessment is required",
                change="Supply a structured semantic assessment.",
            )
        ]
    status = semantic.get("status")
    if status not in {"passed", "needs_clarification", "blocked"}:
        return "needs_clarification", [
            finding(
                "INVALID_SEMANTIC_STATUS",
                "semantic_assessment.status",
                "status must be passed, needs_clarification or blocked",
            )
        ]
    raw = semantic.get("findings", [])
    if not isinstance(raw, list):
        return "needs_clarification", [
            finding(
                "INVALID_SEMANTIC_FINDINGS",
                "semantic_assessment.findings",
                "findings must be an array",
            )
        ]
    result: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) and value[key].strip() for key in ("code", "message")
        ):
            result.append(
                finding(
                    "INVALID_SEMANTIC_FINDING",
                    f"semantic_assessment.findings[{index}]",
                    "finding requires code and message",
                )
            )
        else:
            result.append(
                {
                    "code": value["code"],
                    "path": str(value.get("path", "semantic_assessment")),
                    "message": value["message"],
                    "severity": value.get("severity", "error"),
                    **(
                        {"evidence": sorted(value["evidence"])}
                        if isinstance(value.get("evidence"), list)
                        else {}
                    ),
                }
            )
    return status, sorted_findings(result)


def validate(item: dict[str, Any], semantic: dict[str, Any] | None = None) -> dict[str, Any]:
    machine = sorted_findings(machine_checks(item))
    semantic_status, semantic_findings = semantic_checks(semantic)
    if any(value["severity"] == "error" for value in machine):
        verdict = (
            "blocked"
            if any(
                value["code"]
                in {
                    "DEPENDENCY_CYCLE",
                    "UNREACHABLE_CRITERION",
                    "BOUNDARY_CONFLICT",
                    "OUTCOME_SCOPE_CONFLICT",
                    "SAFETY_SCOPE_CONFLICT",
                }
                for value in machine
            )
            else "needs_clarification"
        )
    elif semantic_status == "blocked" or any(
        value["severity"] == "error" for value in semantic_findings
    ):
        verdict = "blocked"
    elif semantic_status == "needs_clarification" or semantic_findings:
        verdict = "needs_clarification"
    else:
        verdict = "ready"
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "verdict": verdict,
        "machine_findings": machine,
        "semantic_assessment": {"status": semantic_status, "findings": semantic_findings},
        "item_digest": digest(item),
    }
    report["report_digest"] = digest(report)
    return report


def premortem(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the single optional independent pre-execution pass."""
    required = bool(value.get("requested") or value.get("complex"))
    available = value.get("independent_agent_available") is True
    raw = value.get("findings", [])
    findings: list[dict[str, Any]] = []
    if not required or not available:
        return {
            "status": "skipped",
            "findings": [],
            "decisions": [],
            "report_digest": digest({"status": "skipped", "findings": [], "decisions": []}),
        }
    if not isinstance(raw, list) or len(raw) > 3:
        findings.append(
            finding(
                "PREMORTEM_LIMIT",
                "findings",
                "an independent premortem may contain at most three findings",
            )
        )
        raw = raw if isinstance(raw, list) else []
    identifiers: set[str] = set()
    for index, item in enumerate(raw):
        path = f"findings[{index}]"
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) and item[key].strip()
            for key in ("id", "probability", "impact", "proposed_wording_change")
        ):
            findings.append(
                finding(
                    "PREMORTEM_FINDING_INVALID",
                    path,
                    "finding requires id, probability, impact and proposed_wording_change",
                )
            )
            continue
        identifier = str(item["id"])
        if identifier in identifiers:
            findings.append(
                finding("PREMORTEM_DUPLICATE_ID", path, f"duplicate premortem id {identifier!r}")
            )
        identifiers.add(identifier)
        if item["probability"] not in {"low", "medium", "high"} or item["impact"] not in {
            "low",
            "medium",
            "high",
        }:
            findings.append(
                finding(
                    "PREMORTEM_RATING_INVALID",
                    path,
                    "probability and impact must be low, medium or high",
                )
            )
    decisions = value.get("decisions", [])
    if (
        not isinstance(decisions, list)
        or {item.get("id") for item in decisions if isinstance(item, dict)} != identifiers
    ):
        findings.append(
            finding(
                "PREMORTEM_DECISIONS_INCOMPLETE",
                "decisions",
                "main agent must accept or reject every proposal with a reason",
            )
        )
    else:
        for index, decision in enumerate(decisions):
            if (
                not isinstance(decision, dict)
                or decision.get("decision") not in {"accepted", "rejected"}
                or not isinstance(decision.get("reason"), str)
                or not decision["reason"].strip()
            ):
                findings.append(
                    finding(
                        "PREMORTEM_DECISION_INVALID",
                        f"decisions[{index}]",
                        "decision must be accepted or rejected with a reason",
                    )
                )
    status = "invalid" if findings else "completed"
    result: dict[str, Any] = {
        "status": status,
        "findings": sorted_findings(findings),
        "decisions": decisions if isinstance(decisions, list) else [],
    }
    result["report_digest"] = digest(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "premortem"), nargs="?", default="validate")
    parser.add_argument("--input", required=True)
    parser.add_argument("--semantic")
    args = parser.parse_args(argv)
    try:
        item = load(args.input)
        semantic = load(args.semantic) if args.semantic else None
        report = validate(item, semantic) if args.command == "validate" else premortem(item)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "error", "error": {"code": "invalid_input", "message": str(error)}},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return (
        {"ready": 0, "needs_clarification": 1, "blocked": 2}[report["verdict"]]
        if args.command == "validate"
        else (0 if report["status"] in {"completed", "skipped"} else 2)
    )


if __name__ == "__main__":
    raise SystemExit(main())
