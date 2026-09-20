"""Release-relative assessment, fallback, and MR-label regression coverage."""

from __future__ import annotations

import copy
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from shared.references.portable_gitlab import contract, review_semver
from shared.references.portable_gitlab.label_assessment import validate_label_assessments

if TYPE_CHECKING:
    from pathlib import Path


def fallback_assessment(target_sha: str = "b") -> dict[str, Any]:
    return {
        "mode": "target_fallback",
        "policy": "No publication policy could be established from repository documentation or CI.",
        "sources": ["README.md and CI configuration at the reviewed head; empty release catalog"],
        "baseline": None,
        "target_branch": "main",
        "target_sha": target_sha,
        "target_revision": "mr_snapshot",
        "fallback_reason": "No confirmed publication baseline is available.",
        "release_impact": None,
        "release_rationale": None,
    }


def release_assessment(release_sha: str = "a", target_sha: str = "b") -> dict[str, Any]:
    return {
        **fallback_assessment(target_sha),
        "mode": "release",
        "policy": "Stable v1 tags are published by the documented release job.",
        "sources": ["docs/releases.md at the target revision", "GitLab release v1.4.0"],
        "baseline": {"name": "v1.4.0", "sha": release_sha, "source": "releases"},
        "target_revision": "current",
        "fallback_reason": None,
        "release_impact": "major",
        "release_rationale": "Target already removes a released API; the MR fixes a compatible bug.",
    }


@pytest.fixture
def release_context(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(tmp_path), *args], text=True).strip()

    git("init", "--quiet")
    git("config", "commit.gpgsign", "false")
    for value in ("released API\n", "pending breaking change\n"):
        (tmp_path / "api.txt").write_text(value)
        git("add", "api.txt")
        git(
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Change API",
        )
    target = git("rev-parse", "HEAD")
    released = git("rev-parse", "HEAD~1")
    catalog = contract.component([{"tag_name": "v1.4.0", "commit": {"id": released}}])
    evidence = {"start_sha": target, "object": {"target_branch": "main"}}
    context = {
        "exact_git": {"repo_root": str(tmp_path)},
        "release_evidence": {
            "target_branch": "main",
            "target_sha": target,
            "releases": catalog,
            "tags": contract.component(),
            "errors": [],
        },
    }
    return evidence, context, release_assessment(released, target)


def test_release_major_keeps_patch_mr_label(
    release_context: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    evidence, context, assessment = release_context
    assert review_semver.validate(assessment, evidence, context) == assessment
    evidence.update(
        {
            "object": {"labels": []},
            "labels": contract.component(
                [
                    {"name": "semver::major", "description": "Breaking compatibility"},
                    {"name": "semver::patch", "description": "Backward-compatible fix"},
                ]
            ),
        }
    )
    labels = validate_label_assessments(
        evidence,
        [
            {
                "name": "semver::major",
                "status": "inapplicable",
                "rationale": "Breaking change predates this MR.",
            },
            {
                "name": "semver::patch",
                "status": "applicable",
                "rationale": "MR fixes a compatible bug.",
            },
        ],
        "patch",
    )
    assert labels["add"] == ["semver::patch"]
    content = {
        "semver_impact": "patch",
        "semver_rationale": "Compatible fix.",
        "semver_assessment": assessment,
    }
    report = "\n".join(review_semver.report_lines(content, "en"))
    assert "MR contribution / label:** PATCH" in report
    assert "Next release:** MAJOR" in report
    assert "v1.4.0" in report
    assert assessment["baseline"]["sha"] not in report


@pytest.mark.parametrize("case", ["missing", "moved", "incomplete", "upcoming", "target"])
def test_release_assessment_rejects_unbound_evidence(
    release_context: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    case: str,
) -> None:
    evidence, context, assessment = copy.deepcopy(release_context)
    catalog = context["release_evidence"]["releases"]
    if case == "missing":
        catalog["items"] = []
    elif case == "moved":
        catalog["items"][0]["commit"]["id"] = assessment["target_sha"]
    elif case == "incomplete":
        catalog["complete"] = False
    elif case == "upcoming":
        catalog["items"][0]["upcoming_release"] = True
    else:
        context["release_evidence"]["target_sha"] = assessment["baseline"]["sha"]
    with pytest.raises(contract.WorkflowError):
        review_semver.validate(assessment, evidence, context)


def test_unknown_policy_is_explicit_fallback_without_release_claim() -> None:
    evidence = {"start_sha": "b", "object": {"target_branch": "main"}}
    context = {"release_evidence": {"target_branch": "main", "target_sha": None}}
    assessment = fallback_assessment()
    assert review_semver.validate(assessment, evidence, context) == assessment
    content = {
        "semver_impact": "patch",
        "semver_rationale": "Compatible fix.",
        "semver_assessment": assessment,
    }
    for locale, expected in (
        ("en", "target-branch fallback"),
        ("ru", "fallback относительно целевой ветки"),
    ):
        report = "\n".join(review_semver.report_lines(content, locale))
        assert expected in report
        assert "main" in report
        assert "Next release" not in report and "Будущий релиз" not in report
        assert assessment["fallback_reason"] in report
    for invalid in (
        {**assessment, "fallback_reason": ""},
        {**assessment, "release_impact": "patch"},
        {**assessment, "baseline": {"name": "main", "sha": "b", "source": "tags"}},
        {**assessment, "sources": []},
    ):
        with pytest.raises(contract.WorkflowError):
            review_semver.validate(invalid, evidence, context)


def test_release_only_commit_need_not_be_target_ancestor(
    release_context: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    evidence, context, assessment = release_context
    repo = context["exact_git"]["repo_root"]
    parent = assessment["baseline"]["sha"]
    tree = subprocess.check_output(
        ["git", "-C", repo, "rev-parse", f"{parent}^{{tree}}"], text=True
    ).strip()
    release = subprocess.check_output(
        [
            "git",
            "-C",
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            "Release bookkeeping",
        ],
        text=True,
    ).strip()
    assessment["baseline"]["sha"] = release
    context["release_evidence"]["releases"]["items"][0]["commit"]["id"] = release
    assert review_semver.validate(assessment, evidence, context) == assessment


def test_collection_keeps_catalog_failures_nonblocking(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoints = []

    def missing_branch(host: str, endpoint: str) -> object:
        endpoints.append(endpoint)
        raise contract.WorkflowError("target lookup unavailable")

    def catalog(host: str, endpoint: str) -> dict[str, object]:
        endpoints.append(endpoint)
        return contract.component(complete=False, errors=["release information unavailable"])

    monkeypatch.setattr(contract, "glab_json", missing_branch)
    monkeypatch.setattr(contract, "paginated", catalog)
    result = review_semver.collect(
        {
            "project": {"hostname": "gitlab.example", "id": 19},
            "object": {"target_branch": "release/1.x"},
        }
    )
    assert review_semver.evidence_is_valid(result)
    assert result["target_sha"] is None
    assert result["releases"]["complete"] is False
    assert endpoints == [
        "projects/19/repository/branches/release%2F1.x",
        "projects/19/releases",
        "projects/19/repository/tags",
    ]
    assert all(contract.allowed_endpoint(endpoint) for endpoint in endpoints)
    assert contract.allowed_endpoint("projects/19/releases?per_page=100&page=2")
    assert contract.allowed_endpoint("projects/19/repository/tags?per_page=100&page=2")
    assert not contract.allowed_endpoint("projects/19/repository/branches/main/protect")
