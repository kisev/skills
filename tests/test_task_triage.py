from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from shared.references.work_item_runtime import triage


def arguments(source: str) -> argparse.Namespace:
    return argparse.Namespace(
        source=[source],
        state="opened",
        label=None,
        search=None,
        assignee=None,
        milestone=None,
    )


def gitlab_response(endpoint: str) -> Any:
    if endpoint == "projects/group%2Fproject":
        return {"id": 19, "path_with_namespace": "group/project"}
    if endpoint.startswith("projects/19/issues?state=opened"):
        return [
            {
                "id": 107,
                "iid": 7,
                "title": "Clarify retries",
                "web_url": "https://gitlab.example/group/project/-/issues/7",
            }
        ]
    if endpoint.startswith("projects/19/issues?state=all"):
        return [
            {"id": 107, "iid": 7, "title": "Clarify retries"},
            {"id": 103, "iid": 3, "title": "Older retry issue", "state": "closed"},
        ]
    if endpoint.startswith("projects/19/labels?"):
        return [{"id": 1, "name": "priority::high"}]
    if endpoint.startswith("projects/19/milestones?state=active"):
        return [{"id": 9, "title": "v1.1.0", "state": "active"}]
    if endpoint.startswith("projects/19/milestones?state=closed"):
        return []
    if endpoint.startswith("projects/19/releases?"):
        return [{"tag_name": "v1.0.0", "released_at": "2026-09-01T00:00:00Z"}]
    if endpoint.startswith("projects/19/repository/tags?"):
        return [{"name": "v1.0.0", "commit": {"id": "abc"}}]
    if endpoint == "projects/19/issues/7":
        return {
            "id": 107,
            "iid": 7,
            "title": "Clarify retries",
            "description": "Retry behavior is ambiguous.",
            "state": "opened",
            "labels": [],
            "updated_at": "2026-09-23T00:00:00Z",
            "web_url": "https://gitlab.example/group/project/-/issues/7",
        }
    if endpoint.startswith("projects/19/issues/7/discussions?"):
        return [{"id": "discussion-1", "notes": []}]
    if endpoint.startswith("projects/19/issues/7/links?"):
        return []
    if endpoint.startswith("projects/19/issues/7/related_merge_requests?"):
        return [{"id": 41, "iid": 11, "state": "opened", "title": "Implement retries"}]
    if endpoint.startswith("projects/19/issues/7/closed_by?"):
        return []
    raise AssertionError(endpoint)


def analysis_for(result: dict[str, Any]) -> dict[str, Any]:
    item = result["items"][0]
    return {
        "collection_digest": result["collection_digest"],
        "items": [
            {
                "evidence_digest": item["evidence_digest"],
                "actuality": {
                    "status": "current",
                    "rationale": "The issue is open and the related MR is not merged.",
                    "confidence": "high",
                },
                "duplicates": ["#3 is related but already closed with a narrower scope."],
                "quality": {"verdict": "ready", "findings": []},
                "related_issues": ["#3 documents the earlier behavior."],
                "merge_requests": ["!11 is open and related by GitLab evidence."],
                "release_plan": {
                    "decision": {
                        "status": "accepted",
                        "rationale": "The task is current, distinct, and semantically ready.",
                        "confidence": "high",
                    },
                    "semver": {
                        "level": "patch",
                        "rationale": "The change corrects existing retry behavior.",
                        "confidence": "medium",
                    },
                    "release": {
                        "policy": "Published stable tags define this release line.",
                        "baseline_version": "1.0.0",
                        "target_version": "1.1.0",
                        "impact": "minor",
                        "rationale": "The nearest planned release already includes features.",
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
                        "rationale": "This is the nearest compatible active milestone.",
                        "confidence": "high",
                    },
                },
                "severity": "medium",
                "priority": "high",
                "recommendations": ["Add acceptance criteria."],
                "proposed_changes": {
                    "title": "Clarify retry behavior; $(touch unsafe)",
                    "labels": ["priority::high", "type::bug"],
                    "links": [
                        {
                            "target_project_id": 19,
                            "target_issue_iid": 3,
                            "link_type": "relates_to",
                        }
                    ],
                },
            }
        ],
        "top_five": ["#7 because it blocks safe retries."],
        "parallel_groups": [["#7"]],
        "questions": [],
    }


def test_collection_url_filters_are_normalized_and_unknown_filters_fail() -> None:
    source = triage.parse_url(
        "https://gitlab.example/group/project/-/issues?state=closed&label_name[]=bug"
    )
    filters = triage.query_args([source], arguments(source["url"]))
    assert filters == {"state": "closed", "labels": "bug"}
    with pytest.raises(triage.WorkflowError, match="unsupported"):
        triage.parse_url("https://gitlab.example/group/project/-/issues?sort=updated_desc")


def test_pagination_deduplicates_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        [{"id": index} for index in range(100)],
        [{"id": 99}, {"id": 100}],
    ]
    monkeypatch.setattr(triage, "glab_json", lambda _host, _endpoint: pages.pop(0))
    assert len(triage.paginated("gitlab.example", "projects/19/issues")) == 101

    monkeypatch.setattr(
        triage,
        "glab_json",
        lambda _host, _endpoint: (_ for _ in ()).throw(triage.WorkflowError("temporary failure")),
    )
    with pytest.raises(triage.WorkflowError, match="temporary failure"):
        triage.paginated("gitlab.example", "projects/19/issues")


def test_collect_publish_and_reuse_bound_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    source = "https://gitlab.example/group/project/-/issues"

    first = triage.collect(arguments(source))
    assert first["status"] == "ok"
    assert first["items"][0]["analysis_required"] is True
    collection_path = Path(first["artifact_root"]) / "current.json"
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(first)), encoding="utf-8")

    published = triage.publish(
        argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
    )
    assert published["status"] == "ok"
    summary = Path(published["summary"])
    assert summary.is_file()
    assert "#7 because it blocks safe retries." in summary.read_text(encoding="utf-8")

    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "--method PUT" in report
    assert "--method POST" in report
    assert "$(touch unsafe)" not in report
    command_payloads = list(
        (Path(first["artifact_root"]) / "artifacts" / "commands").glob("*.json")
    )
    assert any("$(touch unsafe)" in path.read_text(encoding="utf-8") for path in command_payloads)

    second = triage.collect(arguments(source))
    assert second["items"][0]["analysis_required"] is False
    assert second["items"][0]["cached_analysis"]["priority"] == "high"
    reused = {
        "collection_digest": second["collection_digest"],
        "items": [second["items"][0]["cached_analysis"]],
        "top_five": ["#7 because it blocks safe retries."],
        "parallel_groups": [["#7"]],
        "questions": [],
    }
    reused_path = tmp_path / "reused.json"
    reused_path.write_text(json.dumps(reused), encoding="utf-8")
    assert (
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(reused_path))
        )["status"]
        == "ok"
    )


def test_publish_rejects_stale_or_incomplete_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    collection_path = Path(result["artifact_root"]) / "current.json"
    value = analysis_for(result)
    value["collection_digest"] = "0" * 64
    analysis_path = tmp_path / "stale.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="stale"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["actuality"]["status"] = "implemented"
    value["collection_digest"] = result["collection_digest"]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="only a current issue"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )


def test_explicit_cross_project_list_isolates_issue_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "projects/group%2Fother":
            return {"id": 20, "path_with_namespace": "group/other"}
        if endpoint.startswith("projects/20/issues?state=all"):
            return [{"id": 209, "iid": 9, "title": "Unavailable detail"}]
        if endpoint.startswith("projects/20/labels?"):
            return []
        if endpoint.startswith("projects/20/milestones?"):
            return []
        if endpoint.startswith("projects/20/releases?"):
            return []
        if endpoint.startswith("projects/20/repository/tags?"):
            return []
        if endpoint == "projects/20/issues/9":
            raise triage.WorkflowError("simulated issue failure")
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    args = arguments("https://gitlab.example/group/project/-/issues/7")
    args.source.append("https://gitlab.example/group/other/-/issues/9")
    result = triage.collect(args)
    assert result["status"] == "partial"
    assert len(result["items"]) == 1
    assert result["errors"] == [
        {"target": "gitlab.example:20:9", "message": "simulated issue failure"}
    ]


def test_related_merge_request_change_invalidates_cached_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    mr_state = {"updated_at": "2026-09-23T00:00:00Z"}

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint.startswith("projects/19/issues/7/related_merge_requests?"):
            value[0].update(mr_state)
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    source = "https://gitlab.example/group/project/-/issues/7"
    first = triage.collect(arguments(source))
    collection_path = Path(first["artifact_root"]) / "current.json"
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(first)), encoding="utf-8")
    triage.publish(argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path)))

    mr_state["updated_at"] = "2026-09-24T00:00:00Z"
    second = triage.collect(arguments(source))
    assert second["items"][0]["analysis_required"] is True
    assert second["items"][0]["cached_analysis"] is None


def test_missing_milestone_generates_creation_command_and_partial_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    release_plan = value["items"][0]["release_plan"]
    release_plan["semver"]["level"] = "major"
    release_plan["release"].update(
        {"target_version": "2.0.0", "impact": "major", "rationale": "Breaking release."}
    )
    release_plan["milestone"] = {
        "status": "create",
        "candidate": {
            "project_id": 19,
            "id": None,
            "title": "v2.0.0",
            "state": "proposed",
            "version": "2.0.0",
        },
        "rationale": "No compatible active major milestone exists.",
        "confidence": "high",
    }
    analysis_path = tmp_path / "create.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    assert published["status"] == "partial"
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert '--method POST "projects/19/milestones"' in report


def test_rejected_issue_removes_existing_milestone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint == "projects/19/issues/7":
            value["milestone"] = {"id": 9, "title": "v1.1.0", "state": "active"}
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    item = value["items"][0]
    item["release_plan"]["decision"].update(
        {"status": "rejected", "rationale": "The task is not accepted for the roadmap."}
    )
    item["release_plan"]["milestone"] = {
        "status": "remove",
        "candidate": None,
        "rationale": "Rejected work must leave the active release plan.",
        "confidence": "high",
    }
    analysis_path = tmp_path / "remove.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "--method PUT" in report
    command_payloads = list(
        (Path(result["artifact_root"]) / "artifacts" / "commands").glob("*.json")
    )
    assert any(json.loads(path.read_text()) == {"milestone_id": 0} for path in command_payloads)


def test_milestone_catalog_change_invalidates_cached_analysis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    milestone_state = {"title": "v1.1.0"}

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint.startswith("projects/19/milestones?state=active"):
            value[0]["title"] = milestone_state["title"]
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    source = "https://gitlab.example/group/project/-/issues/7"
    first = triage.collect(arguments(source))
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(first)), encoding="utf-8")
    triage.publish(
        argparse.Namespace(
            collection=str(Path(first["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    milestone_state["title"] = "v1.1.1"
    second = triage.collect(arguments(source))
    assert second["items"][0]["analysis_required"] is True


def test_glab_boundary_uses_get_without_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "{}"

    def fake_run(command: list[str], **kwargs: Any) -> Result:
        observed.append(command)
        assert "shell" not in kwargs
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert triage.glab_json("gitlab.example", "projects/19") == {}
    assert observed == [
        ["glab", "api", "--hostname", "gitlab.example", "--method", "GET", "projects/19"]
    ]
