"""Keep local review decisions across read-only WIP follow-ups."""

from __future__ import annotations

import copy
import difflib
import hashlib
from typing import TYPE_CHECKING, Any

from . import contract as c

if TYPE_CHECKING:
    from pathlib import Path


def addressed_payload(root: Path, kind: str, digest: str) -> dict[str, Any]:
    if not c.is_digest(digest):
        raise c.WorkflowError("local review artifact digest is invalid")
    path = root / "artifacts" / kind / f"{digest}.json"
    envelope, payload = c.artifact_payload(path, kind)
    if hashlib.sha256(c.canonical(envelope)).hexdigest() != digest:
        raise c.WorkflowError("local review artifact digest does not match its content")
    return payload


def baseline(root: Path) -> tuple[str | None, dict[str, Any] | None, str]:
    pointer = root / "local-review.json"
    if not pointer.exists() and not pointer.is_symlink():
        return None, None, "no_previous_review"
    try:
        value = c.read_json(pointer, "local review pointer")
        digest = value.get("review_digest")
        if not isinstance(digest, str) or not c.is_digest(digest):
            raise c.WorkflowError("local review pointer has no valid digest")
        report = addressed_payload(root, "local_review_report", digest)
        validate_report(report)
    except c.WorkflowError:
        return None, None, "previous_review_unavailable"
    return digest, report, "previous_review_available"


def compatible(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return (
        previous["retrieval_complete"] is True
        and current["retrieval_complete"] is True
        and all(
            previous[key] == current[key]
            for key in ("repo_root", "profile", "base_sha", "head_sha", "ref", "artifact_root")
        )
    )


def section_delta(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Diff snapshot sections, not patches intended for application."""
    delta: dict[str, Any] = {}
    for name in ("committed", "staged", "unstaged"):
        before, after = previous["sections"][name], current["sections"][name]
        if before != after:
            delta[name] = "".join(
                difflib.unified_diff(
                    before["diff"].splitlines(keepends=True),
                    after["diff"].splitlines(keepends=True),
                    fromfile=f"previous/{name}",
                    tofile=f"current/{name}",
                )
            )
    before_items = {item["path"]: item for item in previous["sections"]["untracked"]["items"]}
    after_items = {item["path"]: item for item in current["sections"]["untracked"]["items"]}
    changed = [
        {"path": path, "before": before_items.get(path), "after": after_items.get(path)}
        for path in sorted(before_items.keys() | after_items.keys())
        if before_items.get(path) != after_items.get(path)
    ]
    if changed:
        delta["untracked"] = changed
    return delta


def prepare_followup(
    root: Path, bundle: dict[str, Any], digest: str, incremental: str
) -> dict[str, Any]:
    previous_digest, report, reason = baseline(root)
    prior = None
    if report is not None:
        try:
            prior = addressed_payload(root, "local_wip_snapshot", report["evidence_digest"])
        except c.WorkflowError:
            reason = "previous_evidence_unavailable"
    reusable = prior is not None and compatible(prior, bundle)
    delta = section_delta(prior, bundle) if reusable and prior is not None else {}
    mode = "full"
    if reusable and incremental == "auto":
        mode = "incremental" if delta else "unchanged"
        reason = "changed_local_evidence" if delta else "unchanged_local_evidence"
    elif incremental == "off":
        reason = "explicit_full_review"
    elif prior is not None and not reusable:
        reason = "incompatible_boundary_or_incomplete_evidence"
    retained = report if reusable else None
    template = {
        "evidence_digest": digest,
        "previous_review_digest": previous_digest,
        "mode": mode,
        "task": copy.deepcopy(retained["task"])
        if retained
        else {
            "goal": "",
            "acceptance_criteria": [],
            "constraints": [],
            "accepted_risks": [],
            "deferred": [],
            "decision_evidence": "",
        },
        "task_change_reason": None,
        "findings": copy.deepcopy(retained["findings"]) if retained else [],
        "checks": [],
        "assessment": "",
        "verdict": "blocked",
        "external_mutations": False,
    }
    return {
        "mode": mode,
        "reason": reason,
        "baseline_compatible": reusable,
        "previous_review_digest": previous_digest,
        "previous_report": report,
        "previous_evidence_digest": report["evidence_digest"] if report else None,
        "delta": delta,
        "report_template": template,
        "draft_path": str(root / "local-review-draft.json"),
    }


def validate_finding(finding: dict[str, Any]) -> None:
    if finding["blocking"] and finding["status"] != "open":
        raise c.WorkflowError("only open findings can block local acceptance")
    if finding["status"] == "accepted_risk" and not finding["decision_evidence"]:
        raise c.WorkflowError("accepted risk requires the user's decision evidence")
    if (
        finding["blocking"]
        and finding["origin"] in {"new_requirement", "pre_existing"}
        and not finding["decision_evidence"]
    ):
        raise c.WorkflowError("scope expansion requires explicit decision evidence")


def validate_report(report: dict[str, Any]) -> None:
    schema = c.artifact_schema()
    if not c.schema_valid(schema["$defs"]["local_review_payload"], report, schema):
        raise c.WorkflowError("local review report is schema-invalid")
    ids = [finding["id"] for finding in report["findings"]]
    if len(ids) != len(set(ids)):
        raise c.WorkflowError("local review finding IDs must be unique")
    for finding in report["findings"]:
        validate_finding(finding)
    required = [check for check in report["checks"] if check["required"]]
    if not required:
        raise c.WorkflowError("local review must include required acceptance checks")
    if any(check["status"] == "not_run" for check in required):
        expected = "blocked"
    elif any(check["status"] == "failed" for check in required) or any(
        finding["blocking"] for finding in report["findings"]
    ):
        expected = "not_ready"
    else:
        expected = "ready"
    if report["verdict"] != expected:
        raise c.WorkflowError(f"local review verdict must be {expected} for the recorded evidence")


def validate_continuity(report: dict[str, Any], previous: dict[str, Any]) -> None:
    if report["task"] != previous["task"] and not report["task_change_reason"]:
        raise c.WorkflowError(
            "changed task boundary requires decision evidence in task_change_reason"
        )
    findings = {finding["id"]: finding for finding in report["findings"]}
    for old in previous["findings"]:
        new = findings.get(old["id"])
        if new is None:
            raise c.WorkflowError("previous findings must retain their stable IDs and dispositions")
        reopened = new["status"] == "open" and (
            old["status"] != "open" or (new["blocking"] and not old["blocking"])
        )
        if reopened:
            changed_basis = any(
                new[key] != old[key] for key in ("requirement", "scenario", "evidence")
            ) or (report["task"] != previous["task"] and bool(report["task_change_reason"]))
            changed_decision = (
                bool(new["decision_evidence"])
                and new["decision_evidence"] != old["decision_evidence"]
            )
            if not new["reopen_reason"] or not (changed_basis or changed_decision):
                raise c.WorkflowError(
                    "reopening a finding requires changed facts or a user decision"
                )


def record_review(root: Path, bundle_path: Path, report_path: Path) -> dict[str, Any]:
    _, bundle = c.artifact_payload(bundle_path, "local_wip_snapshot")
    envelope = c.read_json(bundle_path, "local evidence")
    digest = hashlib.sha256(c.canonical(envelope)).hexdigest()
    if bundle_path.resolve() != root / "artifacts" / "local_wip_snapshot" / f"{digest}.json":
        raise c.WorkflowError("local review requires its canonical immutable snapshot")
    report = c.read_json(report_path, "local review draft")
    validate_report(report)
    if report["evidence_digest"] != digest:
        raise c.WorkflowError("local review does not bind the current snapshot")
    followup = prepare_followup(root, bundle, digest, "off" if report["mode"] == "full" else "auto")
    if report["previous_review_digest"] != followup["previous_review_digest"]:
        raise c.WorkflowError("local review baseline changed; prepare again")
    if report["mode"] != followup["mode"]:
        raise c.WorkflowError("local review mode does not match the available baseline")
    if followup["baseline_compatible"]:
        validate_continuity(report, followup["previous_report"])
    if c.finalize_local(str(bundle_path))["status"] != "ok":
        raise c.WorkflowError("local evidence changed before report finalization")
    path, report_digest = c.write_artifact(root, "local_review_report", report)
    c.write_json(root / "local-review.json", {"review_digest": report_digest})
    return {
        "artifact_path": str(path),
        "digest": report_digest,
        "mode": report["mode"],
        "verdict": report["verdict"],
    }
