"""Release evidence and distinct release/MR SemVer assessments for code review."""

from __future__ import annotations

import re
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
    target_sha, target_revision = comparison_target(evidence, context)
    return {
        "mode": "target_fallback",
        "policy": "",
        "sources": [],
        "baseline": None,
        "target_branch": release["target_branch"] or evidence["object"].get("target_branch", ""),
        "target_sha": target_sha,
        "target_revision": target_revision,
        "fallback_reason": "",
        "release_impact": None,
        "release_rationale": None,
    }


def comparison_target(evidence: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    target_sha = context["release_evidence"]["target_sha"]
    exact_git = context.get("exact_git")
    if portable.is_sha(target_sha) and isinstance(exact_git, dict):
        repo_root = exact_git.get("repo_root")
        if isinstance(repo_root, str):
            try:
                resolved = str(
                    portable.git_read(
                        Path(repo_root), "rev-parse", "--verify", f"{target_sha}^{{commit}}"
                    )
                ).strip()
            except portable.WorkflowError:
                pass
            else:
                if resolved == target_sha:
                    return target_sha, "current"
    return evidence["start_sha"], "mr_snapshot"


def rendered_template(
    evidence: dict[str, Any], context: dict[str, Any], basis: dict[str, str] | None = None
) -> dict[str, Any]:
    """Derive a stable release basis from complete catalogs and local Git proof."""
    result = template(evidence, context)
    release = context["release_evidence"]
    root = Path(context["exact_git"]["repo_root"])
    reasons = list(release["errors"])
    candidates: list[tuple[tuple[int, ...], dict[str, str]]] = []
    for source, field in (("releases", "tag_name"), ("tags", "name")):
        catalog = release[source]
        if catalog["complete"] is not True:
            reasons.append(f"{source} catalog is incomplete")
            continue
        for item in catalog["items"]:
            name = str(item.get(field) or "")
            # SIMPLIFY: automatic selection uses stable v?X.Y.Z only -> extend when a confirmed policy requires other automatic baselines.
            match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", name)
            sha = (item.get("commit") or {}).get("id")
            if (
                (match is None and basis is None)
                or not portable.is_sha(sha)
                or item.get("upcoming_release") is True
            ):
                continue
            if result["target_revision"] != "current":
                continue
            try:
                resolved = str(
                    portable.git_read(root, "rev-parse", "--verify", f"{sha}^{{commit}}")
                ).strip()
                if resolved != sha:
                    raise portable.WorkflowError("release commit identity differs")
                portable.git_read(root, "merge-base", sha, result["target_sha"])
            except portable.WorkflowError:
                reasons.append(f"{source} entry {name}: local comparison proof unavailable")
                continue
            candidates.append(
                (
                    tuple(int(part) for part in match.groups()) if match else (),
                    {"name": name, "sha": sha, "source": source},
                )
            )
    result["sources"] = [f"Collected {source} catalog" for source in ("releases", "tags")]
    if basis is not None:
        if set(basis) != {"name", "source"}:
            raise portable.WorkflowError(
                "semver_assessment.basis: select a collected name and source, not a SHA or binding"
            )
        selected = [
            candidate
            for _, candidate in candidates
            if candidate["name"] == basis["name"] and candidate["source"] == basis["source"]
        ]
        if len(selected) != 1:
            raise portable.WorkflowError(
                "semver_assessment.basis: select one policy-confirmed publication from a complete catalog with locally verifiable Git proof"
            )
        result.update(
            mode="release",
            baseline=selected[0],
            fallback_reason=None,
            release_impact="<IMPACT: assess the complete future release>",
            release_rationale="<RATIONALE: explain the release impact>",
        )
        return result
    if (
        candidates
        and not reasons
        and not any(release[source]["complete"] is not True for source in ("releases", "tags"))
    ):
        latest = max(version for version, _ in candidates)
        choices = [basis for version, basis in candidates if version == latest]
        if len({basis["sha"] for basis in choices}) == 1:
            result.update(
                mode="release",
                baseline=choices[0],
                fallback_reason=None,
                release_impact="<IMPACT: assess the complete future release>",
                release_rationale="<RATIONALE: explain the release impact>",
            )
            return result
        reasons.append("latest stable version has conflicting commit identities")
    if result["target_revision"] != "current":
        reasons.append("current target branch commit unavailable locally; using MR target snapshot")
    result["fallback_reason"] = (
        "; ".join(dict.fromkeys(reasons)) or "no confirmed stable release or tag is available"
    )
    return result


def validate(value: object, evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not assessment_is_valid(value):
        field, action = (
            "basis",
            "use the prepared basis or select {name,source} from the collected catalog",
        )
        if isinstance(value, dict):
            if not portable.nonempty_string(value.get("policy")):
                field, action = "policy", "explain the observed publication policy or its absence"
            elif not value.get("sources"):
                field, action = (
                    "sources",
                    "retain collected sources and add inspected policy evidence",
                )
            elif value.get("mode") == "target_fallback" and not portable.nonempty_string(
                value.get("fallback_reason")
            ):
                field, action = (
                    "fallback_reason",
                    "explain why publication proof is unavailable or inapplicable",
                )
            elif value.get("mode") == "release":
                field, action = (
                    "release_impact/release_rationale",
                    "assess the future release with concrete evidence",
                )
        raise portable.WorkflowError(
            f"SemVer assessment requires a release basis or explicit target fallback; semver_assessment.{field}: {action}; retain other authored fields"
        )
    result = cast("dict[str, Any]", value)
    release = context["release_evidence"]
    expected_sha, expected_revision = comparison_target(evidence, context)
    if (
        result["target_branch"] != release["target_branch"]
        or result["target_sha"] != expected_sha
        or result["target_revision"] != expected_revision
    ):
        raise portable.WorkflowError(
            "SemVer target does not match collected target branch evidence"
        )
    if result["mode"] == "target_fallback":
        return result
    if release["target_sha"] is None or expected_revision != "current":
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
