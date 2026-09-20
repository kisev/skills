"""Release evidence and distinct release/MR SemVer assessments for code review."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from . import contract as portable

IMPACTS = {"major", "minor", "patch", "none", "not_applicable"}


def evidence_is_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"target_branch", "target_sha", "releases", "tags", "errors"}
        and (value["target_branch"] is None or portable.nonempty_string(value["target_branch"]))
        and portable.is_sha(value["target_sha"], nullable=True)
        and portable.component_is_valid(value["releases"])
        and portable.component_is_valid(value["tags"])
        and isinstance(value["errors"], list)
        and all(portable.nonempty_string(item) for item in value["errors"])
    )


def collect(evidence: dict[str, Any]) -> dict[str, Any]:
    project = evidence["project"]
    host, project_id = project["hostname"], project["id"]
    branch = evidence["object"].get("target_branch")
    errors: list[str] = []
    target_sha = None
    if portable.nonempty_string(branch):
        try:
            target = portable.glab_json(
                host, f"projects/{project_id}/repository/branches/{quote(branch, safe='')}"
            )
            if isinstance(target, dict) and isinstance(target.get("commit"), dict):
                target_sha = target["commit"].get("id")
            if not portable.is_sha(target_sha):
                raise portable.WorkflowError("current target branch revision is unavailable")
        except portable.WorkflowError as exc:
            errors.append(portable.redact(str(exc)))
            target_sha = None
    else:
        errors.append("target branch name is unavailable")
    return {
        "target_branch": branch if portable.nonempty_string(branch) else None,
        "target_sha": target_sha,
        "releases": portable.paginated(host, f"projects/{project_id}/releases"),
        "tags": portable.paginated(host, f"projects/{project_id}/repository/tags"),
        "errors": errors,
    }


def assessment_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "mode",
        "policy",
        "sources",
        "baseline",
        "target_branch",
        "target_sha",
        "fallback_reason",
        "release_impact",
        "release_rationale",
        "target_revision",
    }:
        return False
    if (
        value["mode"] not in ("release", "target_fallback")
        or not portable.nonempty_string(value["policy"])
        or not isinstance(value["sources"], list)
        or not value["sources"]
        or not all(portable.nonempty_string(item) for item in value["sources"])
        or not portable.nonempty_string(value["target_branch"])
        or not portable.is_sha(value["target_sha"])
        or value["target_revision"] not in ("current", "mr_snapshot")
    ):
        return False
    if value["mode"] == "target_fallback":
        return (
            value["baseline"] is None
            and portable.nonempty_string(value["fallback_reason"])
            and value["release_impact"] is None
            and value["release_rationale"] is None
        )
    baseline = value["baseline"]
    return (
        value["fallback_reason"] is None
        and value["target_revision"] == "current"
        and isinstance(value["release_impact"], str)
        and value["release_impact"] in IMPACTS
        and portable.nonempty_string(value["release_rationale"])
        and isinstance(baseline, dict)
        and set(baseline) == {"name", "sha", "source"}
        and portable.nonempty_string(baseline["name"])
        and portable.is_sha(baseline["sha"])
        and baseline["source"] in ("releases", "tags")
    )


def template(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    release = context["release_evidence"]
    return {
        "mode": "target_fallback",
        "policy": "",
        "sources": [],
        "baseline": None,
        "target_branch": release["target_branch"] or evidence["object"].get("target_branch", ""),
        "target_sha": release["target_sha"] or evidence["start_sha"],
        "target_revision": "current" if release["target_sha"] else "mr_snapshot",
        "fallback_reason": "",
        "release_impact": None,
        "release_rationale": None,
    }


def validate(value: object, evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not assessment_is_valid(value):
        raise portable.WorkflowError(
            "SemVer assessment requires a release basis or explicit target fallback"
        )
    result = cast("dict[str, Any]", value)
    release = context["release_evidence"]
    expected_sha = release["target_sha"] or evidence["start_sha"]
    if (
        result["target_branch"] != release["target_branch"]
        or result["target_sha"] != expected_sha
        or result["target_revision"] != ("current" if release["target_sha"] else "mr_snapshot")
    ):
        raise portable.WorkflowError(
            "SemVer target does not match collected target branch evidence"
        )
    if result["mode"] == "target_fallback":
        return result
    if release["target_sha"] is None:
        raise portable.WorkflowError("release SemVer requires the current target branch revision")
    baseline = result["baseline"]
    catalog = release[baseline["source"]]
    name_field = "tag_name" if baseline["source"] == "releases" else "name"
    if catalog["complete"] is not True or not any(
        isinstance(item, dict)
        and item.get(name_field) == baseline["name"]
        and isinstance(item.get("commit"), dict)
        and item["commit"].get("id") == baseline["sha"]
        and item.get("upcoming_release") is not True
        for item in catalog["items"]
    ):
        raise portable.WorkflowError(
            "SemVer baseline is not bound to a complete release/tag catalog"
        )
    root = Path(context["exact_git"]["repo_root"])
    for sha in (baseline["sha"], result["target_sha"]):
        resolved = str(
            portable.git_read(root, "rev-parse", "--verify", f"{sha}^{{commit}}")
        ).strip()
        if resolved != sha:
            raise portable.WorkflowError("SemVer comparison commit is unavailable locally")
    # Release-only commits need not be ancestors of dev, but history must be related.
    portable.git_read(root, "merge-base", baseline["sha"], result["target_sha"])
    return result


def report_lines(content: dict[str, Any], locale: str) -> list[str]:
    assessment = content["semver_assessment"]
    ru = locale == "ru"

    def impact_text(value: str) -> str:
        return {
            "none": "нет" if ru else "none",
            "not_applicable": "не применимо" if ru else "not applicable",
        }.get(value, value.upper())

    impact = impact_text(content["semver_impact"])
    contribution = "Вклад MR / метка" if ru else "MR contribution / label"
    lines = [f"- **{contribution}:** {impact} - {content['semver_rationale']}"]
    target = assessment["target_branch"]
    if assessment["mode"] == "release":
        baseline = assessment["baseline"]["name"]
        basis = "База SemVer" if ru else "SemVer basis"
        release_label = "Будущий релиз" if ru else "Next release"
        release_impact = impact_text(assessment["release_impact"])
        lines.extend(
            [
                f"- **{basis}:** `{baseline}` → `{target}` + MR",
                f"- **{release_label}:** {release_impact} - {assessment['release_rationale']}",
            ]
        )
    else:
        mode = (
            "SemVer: fallback относительно целевой ветки"
            if ru
            else "SemVer: target-branch fallback"
        )
        lines.append(f"- **{mode}:** `{target}` - {assessment['fallback_reason']}")
        if assessment["target_revision"] == "mr_snapshot":
            lines.append(
                "- Текущая ревизия целевой ветки недоступна. Использован снимок базы MR."
                if ru
                else "- Current target revision unavailable. Using the MR target snapshot."
            )
    policy = "Политика выпуска" if ru else "Release policy"
    lines.append(f"- **{policy}:** {assessment['policy']}")
    return lines
