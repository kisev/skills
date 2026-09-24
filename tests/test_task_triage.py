from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from shared.references.work_item_runtime import triage

ROOT = Path(__file__).resolve().parents[1]


def arguments(source: str) -> argparse.Namespace:
    return argparse.Namespace(
        source=[source],
        state="opened",
        label=None,
        search=None,
        assignee=None,
        milestone=None,
        locale="en",
    )


def test_workflow_requires_user_questions_and_strict_stale_sequence() -> None:
    workflow = (ROOT / "skills/task-triage/references/workflow.md").read_text(encoding="utf-8")
    normalized = " ".join(workflow.split())
    for requirement in (
        "Continue the same invocation after the answers.",
        "question -> first ping -> second ping -> closure proposal",
        "Never skip a stage after a long gap between runs.",
        "current GitLab discussions and notes by the authenticated user",
        "one directly runnable command per action",
        "plain absolute paths, never Markdown links",
    ):
        assert requirement in normalized


def gitlab_response(endpoint: str) -> Any:
    if endpoint == "user":
        return {"id": 5, "username": "reviewer"}
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
        return [
            {
                "id": 41,
                "iid": 11,
                "project_id": 19,
                "state": "opened",
                "title": "Implement retries",
                "web_url": "https://gitlab.example/group/project/-/merge_requests/11",
            }
        ]
    if endpoint.startswith("projects/19/issues/7/closed_by?"):
        return []
    if endpoint.startswith("projects/19/merge_requests/11/discussions?"):
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
    assert report.count("--silent") == 4
    assert "$(touch unsafe)" in report
    command_blocks = [line for line in report.splitlines() if " marker-run " in line]
    assert len(command_blocks) == 4
    assert report.count("# execution-status=not_run") == 4
    assert all("$(touch unsafe)" not in line for line in command_blocks)
    command_payloads = list(
        (Path(first["artifact_root"]) / "artifacts" / "commands").glob("*.json")
    )
    assert any("$(touch unsafe)" in path.read_text(encoding="utf-8") for path in command_payloads)
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in command_payloads]
    assert {"title": "Clarify retry behavior; $(touch unsafe)"} in payloads
    assert {"labels": "priority::high,type::bug"} in payloads
    assert {"milestone_id": 9} in payloads
    assert not any("title" in payload and "labels" in payload for payload in payloads)

    fake_glab = tmp_path / "glab"
    fake_glab.write_text("#!/bin/sh\nexit 0\n")
    fake_glab.chmod(0o700)
    executed = subprocess.run(
        ["sh", "-c", command_blocks[0]],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        check=False,
    )
    assert executed.returncode == 0
    republished = triage.publish(
        argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
    )
    refreshed = Path(republished["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "# execution-status=run_unverified" in refreshed

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
    assert "--method POST projects/19/milestones" in report
    assert "--method POST projects/19/milestones --silent" in report


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
    assert report.count("--silent") == 4
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


def test_russian_reports_are_localized_and_summary_uses_plain_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    args = arguments("https://gitlab.example/group/project/-/issues/7")
    args.locale = "ru"
    result = triage.collect(args)
    analysis_path = tmp_path / "analysis-ru.json"
    analysis_path.write_text(json.dumps(analysis_for(result)), encoding="utf-8")

    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )

    summary = Path(published["summary"]).read_text(encoding="utf-8")
    report_path = Path(published["reports"][0]["report"])
    report = report_path.read_text(encoding="utf-8")
    assert "# Сводка триажа задач" in summary
    assert "## Подробные отчёты" in summary
    assert f"- {report_path}" in summary
    assert "](" not in summary
    assert "- Актуальность: актуальна" in report
    assert "- Качество: готово" in report
    assert "- Решение по планированию: принято" in report
    assert "- Готовность планирования: готова" in report
    assert "## Замечания к качеству" in report
    assert "## Связанные MR" in report
    assert "## Ручные команды" in report
    assert "Ничего не обнаружено." in report


def test_information_request_sequence_and_reply_reassessment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    participant_replied = {"value": False}

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/discussions?"):
            notes = [
                {
                    "id": 101,
                    "created_at": "2026-08-01T00:00:00Z",
                    "body": "Could you clarify the expected behavior?",
                    "author": {"id": 5, "username": "reviewer"},
                },
                {
                    "id": 102,
                    "created_at": "2026-08-10T00:00:00Z",
                    "body": "Ping: this context is still needed.",
                    "author": {"id": 5, "username": "reviewer"},
                },
            ]
            if participant_replied["value"]:
                notes.append(
                    {
                        "id": 103,
                        "created_at": "2026-08-11T00:00:00Z",
                        "body": "The expected behavior is documented elsewhere.",
                        "author": {"id": 8, "username": "author"},
                    }
                )
            return [{"id": "discussion-1", "notes": notes}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["information_requests"] = [
        {
            "action": "ping_2",
            "target": {
                "kind": "issue",
                "project_id": 19,
                "iid": 7,
                "discussion_id": "discussion-1",
            },
            "body": "Повторно прошу уточнить ожидаемое поведение.",
            "prior_note_ids": [101, 102],
            "rationale": "Содержательного ответа пока нет.",
        }
    ]
    analysis_path = tmp_path / "information-request.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "apply-information" in report
    assert "--stage message" in report
    assert published["status"] == "partial"

    value["items"][0]["information_requests"][0]["action"] = "close"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="does not follow"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )

    participant_replied["value"] = True
    refreshed = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(refreshed)
    value["items"][0]["information_requests"] = [
        {
            "action": "ping_2",
            "target": {
                "kind": "issue",
                "project_id": 19,
                "iid": 7,
                "discussion_id": "discussion-1",
            },
            "body": "Повторный пинг.",
            "prior_note_ids": [101, 102],
            "rationale": "Ответ ещё не проверен.",
        }
    ]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="later note"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(refreshed["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )

    value["items"][0]["information_requests"][0].update(
        {
            "action": "new",
            "body": "Спасибо. Подскажи, где именно описан ожидаемый контракт?",
            "prior_note_ids": [],
            "rationale": "Ответ получен, но ссылки на контракт не хватает; начинается новый цикл.",
        }
    )
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    assert (
        triage.publish(
            argparse.Namespace(
                collection=str(Path(refreshed["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )["status"]
        == "partial"
    )


def test_related_mr_message_gets_its_own_publication_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["proposed_changes"]["messages"] = [
        {
            "target": {
                "kind": "merge_request",
                "project_id": 19,
                "iid": 11,
                "discussion_id": None,
            },
            "body": "Эта реализация связана с issue #7; проверь, что контракт совпадает.",
        }
    ]
    analysis_path = tmp_path / "mr-message.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "projects/19/merge_requests/11/notes" in report
    assert report.count("### Publish message") == 1


def test_information_request_requires_exact_latest_current_user_cycle() -> None:
    target = {
        "kind": "issue",
        "project_id": 19,
        "iid": 7,
        "discussion_id": "discussion-1",
    }
    request = {
        "action": "ping_2",
        "target": target,
        "body": "Second follow-up.",
        "prior_note_ids": [101, 102],
        "rationale": "No sufficient answer was observed.",
    }
    snapshot: dict[str, Any] = {
        "target": {"project_id": 19, "iid": 7},
        "issue": {"state": "opened"},
        "discussions": [
            {
                "id": "discussion-1",
                "notes": [
                    {
                        "id": 101,
                        "created_at": "2026-08-01T00:00:00Z",
                        "author": {"id": 5, "username": "reviewer"},
                    },
                    {
                        "id": 150,
                        "created_at": "2026-08-02T00:00:00Z",
                        "author": {"id": 8, "username": "author"},
                    },
                    {
                        "id": 102,
                        "created_at": "2026-08-03T00:00:00Z",
                        "author": {"id": 5, "username": "reviewer"},
                    },
                ],
            }
        ],
        "merge_request_conversations": [],
    }
    current_user = {"id": 5, "username": "reviewer"}
    with pytest.raises(triage.WorkflowError, match="complete latest cycle"):
        triage.validate_information_request(snapshot, current_user, request, "request")

    notes = snapshot["discussions"][0]["notes"]
    notes.pop(1)
    notes.append(
        {
            "id": 103,
            "created_at": "2026-08-04T00:00:00Z",
            "author": {"id": 5, "username": "reviewer"},
        }
    )
    with pytest.raises(triage.WorkflowError, match="later note"):
        triage.validate_information_request(snapshot, current_user, request, "request")

    notes.pop()
    notes[0]["author"] = {"id": 6, "username": "reviewer"}
    with pytest.raises(triage.WorkflowError, match="current user"):
        triage.validate_information_request(snapshot, current_user, request, "request")

    notes[0]["author"] = {"id": 5, "username": "reviewer"}
    notes.append(
        {
            "id": 103,
            "created_at": "2026-08-04T00:00:00Z",
            "author": {"id": 5, "username": "reviewer"},
        }
    )
    repeated_stage = {
        **request,
        "action": "ping_1",
        "prior_note_ids": [103],
    }
    with pytest.raises(triage.WorkflowError, match="complete latest cycle"):
        triage.validate_information_request(snapshot, current_user, repeated_stage, "request")

    repeated_question = {
        **request,
        "action": "new",
        "body": "Another question without an answer.",
        "prior_note_ids": [],
    }
    with pytest.raises(triage.WorkflowError, match="latest participant reply"):
        triage.validate_information_request(snapshot, current_user, repeated_question, "request")


def test_information_request_rejects_closed_issue() -> None:
    snapshot = {
        "target": {"project_id": 19, "iid": 7},
        "issue": {"state": "closed"},
        "discussions": [],
        "merge_request_conversations": [],
    }
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Could you clarify this?",
        "prior_note_ids": [],
        "rationale": "Context is missing.",
    }
    with pytest.raises(triage.WorkflowError, match="issue is not open"):
        triage.validate_information_request(
            snapshot,
            {"id": 5, "username": "reviewer"},
            request,
            "request",
        )


def test_only_one_information_action_is_allowed_per_discussion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/discussions?"):
            return [
                {
                    "id": "discussion-1",
                    "notes": [
                        {
                            "id": 101,
                            "created_at": "2026-08-01T00:00:00Z",
                            "author": {"id": 5, "username": "reviewer"},
                        }
                    ],
                }
            ]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    request = {
        "action": "ping_1",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "First follow-up.",
        "prior_note_ids": [101],
        "rationale": "No answer was observed.",
    }
    value["items"][0]["information_requests"] = [request, {**request, "body": "Duplicate."}]
    analysis_path = tmp_path / "duplicate-actions.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="multiple information actions"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )


def test_stale_closure_has_separate_message_and_close_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/discussions?"):
            return [
                {
                    "id": "discussion-1",
                    "notes": [
                        {
                            "id": note_id,
                            "created_at": f"2026-08-{day:02d}T00:00:00Z",
                            "author": {"id": 5, "username": "reviewer"},
                        }
                        for note_id, day in ((101, 1), (102, 6), (103, 20))
                    ],
                }
            ]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["information_requests"] = [
        {
            "action": "close",
            "target": {
                "kind": "issue",
                "project_id": 19,
                "iid": 7,
                "discussion_id": "discussion-1",
            },
            "body": "Закрываю задачу: после вопроса и двух пингов информации не поступило.",
            "prior_note_ids": [101, 102, 103],
            "rationale": "Последовательность ожидания завершена без ответа.",
        }
    ]
    analysis_path = tmp_path / "close.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "### Publish stale closure message" in report
    assert "### Close issue" in report
    assert report.count("apply-information") == 2
    assert "--stage message" in report
    assert "--stage close" in report


def information_guard(
    root: Path,
    request: dict[str, Any],
    *,
    discussions: list[dict[str, Any]] | None = None,
    schema: str = "task-triage/information-guard/v2",
) -> Path:
    root = root / "agent-skills" / "task-triage" / ("a" * 32)
    value: dict[str, Any] = {
        "schema": schema,
        "host": "gitlab.example",
        "current_user": {"id": 5, "username": "reviewer"},
        "request": request,
    }
    if schema == "task-triage/information-guard/v2":
        target = request.get("target") if isinstance(request, dict) else None
        value["conversation_state"] = (
            triage.conversation_state(discussions or [])
            if request.get("action") == "new"
            and isinstance(target, dict)
            and target.get("discussion_id") is None
            else None
        )
    guard, _ = triage.write_artifact(
        root,
        "information-guards",
        value,
    )
    return guard


def test_discussion_notes_break_equal_timestamp_ties_numerically() -> None:
    timestamp = "2026-08-01T00:00:00Z"
    numeric = [
        {
            "id": "discussion-1",
            "notes": [
                {"id": 10, "created_at": timestamp},
                {"id": 9, "created_at": timestamp},
            ],
        }
    ]
    nonnumeric = [
        {
            "id": "discussion-2",
            "notes": [
                {"id": "note-b", "created_at": timestamp},
                {"id": "note-a", "created_at": timestamp},
            ],
        }
    ]

    assert [note["id"] for note in triage.discussion_notes(numeric, None)] == [9, 10]
    assert [note["id"] for note in triage.discussion_notes(nonnumeric, None)] == [
        "note-b",
        "note-a",
    ]


def test_information_actions_emit_v2_with_prepared_non_system_conversation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    discussions = [
        {
            "id": "discussion-1",
            "notes": [
                {"id": 10, "created_at": "2026-08-01T00:00:00Z", "body": "second"},
                {"id": 9, "created_at": "2026-08-01T00:00:00Z", "body": "first"},
                {"id": 11, "system": True, "body": "system event"},
            ],
        }
    ]
    snapshot = {
        "target": {"project_id": 19, "iid": 7},
        "issue": {"state": "opened"},
        "discussions": discussions,
        "merge_request_conversations": [],
    }

    triage.information_actions(
        tmp_path,
        "gitlab.example",
        request,
        {"id": 5, "username": "reviewer"},
        snapshot,
    )

    guards = list((tmp_path / "artifacts/information-guards").glob("*.json"))
    assert len(guards) == 1
    guard = json.loads(guards[0].read_text(encoding="utf-8"))
    assert guard["schema"] == "task-triage/information-guard/v2"
    assert guard["conversation_state"] == {
        "note_ids": [9, 10],
        "digest": triage.digest(
            [
                {"id": 9, "created_at": "2026-08-01T00:00:00Z", "body": "first"},
                {"id": 10, "created_at": "2026-08-01T00:00:00Z", "body": "second"},
            ]
        ),
    }


@pytest.mark.parametrize("change", ["addition", "removal", "content"])
def test_new_standalone_information_rejects_any_conversation_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, change: str
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    prepared_notes = [
        {
            "id": 9,
            "created_at": "2026-08-01T00:00:00Z",
            "body": "Observed context.",
            "author": {"id": 8},
        }
    ]
    guard = information_guard(
        tmp_path,
        request,
        discussions=[{"id": "discussion-1", "notes": prepared_notes}],
    )
    fresh_notes = [dict(note) for note in prepared_notes]
    if change == "addition":
        fresh_notes.append(
            {
                "id": 10,
                "created_at": "2026-08-02T00:00:00Z",
                "body": "New context.",
                "author": {"id": 8},
            }
        )
    elif change == "removal":
        fresh_notes.clear()
    else:
        fresh_notes[0]["body"] = "Changed context."

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [{"id": "discussion-1", "notes": fresh_notes}]

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: pytest.fail("changed conversation must not mutate GitLab"),
    )

    with pytest.raises(triage.WorkflowError, match="conversation changed"):
        triage.apply_information(guard, "message")


def test_legacy_information_guard_fails_closed_and_requires_regeneration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    guard = information_guard(tmp_path, {}, schema="task-triage/information-guard/v1")
    monkeypatch.setattr(
        triage,
        "glab_json",
        lambda *_args, **_kwargs: pytest.fail("legacy guard must fail before GitLab access"),
    )

    with pytest.raises(triage.WorkflowError, match=r"legacy information guard.*regenerated"):
        triage.apply_information(guard, "message")


def test_information_command_revalidates_and_rejects_later_reply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "ping_1",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "First follow-up.",
        "prior_note_ids": [101],
        "rationale": "No answer was observed.",
    }
    guard = information_guard(tmp_path, request)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [
            {
                "id": "discussion-1",
                "notes": [
                    {"id": 101, "created_at": "2026-08-01T00:00:00Z", "author": {"id": 5}},
                    {"id": 102, "created_at": "2026-08-02T00:00:00Z", "author": {"id": 8}},
                ],
            }
        ]

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: pytest.fail("stale command must not mutate GitLab"),
    )

    with pytest.raises(triage.WorkflowError, match="later note"):
        triage.apply_information(guard, "message")


def test_information_command_records_receipt_and_rejects_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    guard = information_guard(tmp_path, request)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return []

    monkeypatch.setattr(triage, "glab_json", response)
    mutations: list[str] = []

    def mutate(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        mutations.append("POST")
        return {"id": 104}

    monkeypatch.setattr(
        triage,
        "glab_mutation",
        mutate,
    )

    triage.apply_information(guard, "message")
    with pytest.raises(triage.WorkflowError, match="already published"):
        triage.apply_information(guard, "message")
    assert mutations == ["POST"]


def test_standalone_information_timeout_leaves_durable_blocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    guard = information_guard(tmp_path, request)
    synced: list[Path] = []
    original_fsync_directory = triage.fsync_directory

    def observe_fsync(path: Path) -> None:
        original_fsync_directory(path)
        synced.append(path)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return []

    attempts: list[str] = []

    def timeout(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        receipt = triage.information_receipt_path(guard, guard.stem)
        assert receipt.is_file()
        assert receipt.parent in synced
        attempts.append("POST")
        raise triage.WorkflowError("ambiguous timeout")

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(triage, "glab_mutation", timeout)
    monkeypatch.setattr(triage, "fsync_directory", observe_fsync)

    with pytest.raises(triage.WorkflowError, match="ambiguous timeout"):
        triage.apply_information(guard, "message")
    receipt = triage.information_receipt_path(guard, guard.stem)
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "status": "in_progress",
        "guard_digest": guard.stem,
        "body": request["body"],
    }
    with pytest.raises(triage.WorkflowError, match="outcome is unknown"):
        triage.apply_information(guard, "message")
    assert attempts == ["POST"]


def test_standalone_information_retries_only_when_process_did_not_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    guard = information_guard(tmp_path, request)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return []

    attempts = 0

    def mutate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise triage.MutationNotAttempted("not started")
        return {"id": 104}

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(triage, "glab_mutation", mutate)

    with pytest.raises(triage.MutationNotAttempted, match="not started"):
        triage.apply_information(guard, "message")
    assert not triage.information_receipt_path(guard, guard.stem).exists()
    triage.apply_information(guard, "message")


def test_follow_up_reserves_before_post_and_only_clears_pre_start_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "ping_1",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "First follow-up.",
        "prior_note_ids": [101],
        "rationale": "No answer was observed.",
    }
    guard = information_guard(tmp_path, request)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [
            {
                "id": "discussion-1",
                "notes": [
                    {
                        "id": 101,
                        "created_at": "2026-08-01T00:00:00Z",
                        "author": {"id": 5, "username": "reviewer"},
                    }
                ],
            }
        ]

    attempts = 0

    def mutate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal attempts
        receipt = triage.information_receipt_path(guard, guard.stem)
        assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "in_progress"
        attempts += 1
        if attempts == 1:
            raise triage.MutationNotAttempted("not started")
        raise triage.MutationOutcomeUnknown("unknown")

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(triage, "glab_mutation", mutate)

    with pytest.raises(triage.MutationNotAttempted):
        triage.apply_information(guard, "message")
    receipt = triage.information_receipt_path(guard, guard.stem)
    assert not receipt.exists()
    with pytest.raises(triage.MutationOutcomeUnknown):
        triage.apply_information(guard, "message")
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "in_progress"


def test_information_command_rejects_changed_authenticated_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "new",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": None,
        },
        "body": "Please provide the missing context.",
        "prior_note_ids": [],
        "rationale": "The issue is incomplete.",
    }
    guard = information_guard(tmp_path, request)
    monkeypatch.setattr(
        triage,
        "glab_json",
        lambda _host, _endpoint: {"id": 8, "username": "different-user"},
    )
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: pytest.fail("changed identity must not mutate GitLab"),
    )

    with pytest.raises(triage.WorkflowError, match="authenticated GitLab user changed"):
        triage.apply_information(guard, "message")


def test_information_command_rejects_guard_outside_artifact_collection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    payload = {
        "schema": "task-triage/information-guard/v1",
        "host": "gitlab.example",
        "current_user": {"id": 5},
        "request": {},
    }
    content = triage.canonical(payload) + b"\n"
    guard = (
        tmp_path
        / "arbitrary"
        / ("a" * 32)
        / "artifacts"
        / "information-guards"
        / f"{hashlib.sha256(content).hexdigest()}.json"
    )
    guard.parent.mkdir(parents=True)
    guard.write_bytes(content)

    with pytest.raises(triage.WorkflowError, match=r"scope|outside"):
        triage.apply_information(guard, "message")


def test_information_guard_parses_the_digest_verified_bytes_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    guard = information_guard(tmp_path, {})
    monkeypatch.setattr(
        triage,
        "read_object",
        lambda *_args, **_kwargs: pytest.fail(
            "guard must not be reopened after digest verification"
        ),
    )

    value, guard_digest = triage.read_information_guard(guard)

    assert value["schema"] == "task-triage/information-guard/v2"
    assert guard_digest == guard.stem


def test_shallow_information_guard_path_is_a_controlled_error() -> None:
    with pytest.raises(triage.WorkflowError, match="path is invalid"):
        triage.read_information_guard(Path("guard.json"))


def test_triage_runner_resolves_built_and_source_layouts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    built_runtime = tmp_path / "archive/scripts/portable_runtime/triage.py"
    built_runner = tmp_path / "archive/scripts/triage_task.py"
    built_runner.parent.mkdir(parents=True)
    built_runner.touch()
    monkeypatch.setattr(triage, "__file__", str(built_runtime))
    assert triage.triage_runner() == built_runner

    built_runner.unlink()
    source_runtime = tmp_path / "repo/shared/references/work_item_runtime/triage.py"
    source_runner = tmp_path / "repo/skills/task-triage/scripts/triage_task.py"
    source_runner.parent.mkdir(parents=True)
    source_runner.touch()
    monkeypatch.setattr(triage, "__file__", str(source_runtime))
    assert triage.triage_runner() == source_runner


def test_source_layout_runner_executes_without_generated_runtime(tmp_path: Path) -> None:
    runner = tmp_path / "repo/skills/task-triage/scripts/triage_task.py"
    runner.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "skills/task-triage/scripts/triage_task.py", runner)
    shared = tmp_path / "repo/shared/references"
    shared.mkdir(parents=True)
    shutil.copytree(
        ROOT / "shared/references/work_item_runtime",
        shared / "work_item_runtime",
    )
    shutil.copy2(ROOT / "shared/references/state_artifacts.py", shared / "state_artifacts.py")
    assert not (runner.parent / "portable_runtime").exists()

    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(runner), "--capabilities"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["payload_version"] == "2.0.0"


def test_information_lifecycle_lock_is_bounded_and_requires_posix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    locking = triage.fcntl
    if locking is None:
        pytest.skip("fcntl is unavailable")
    lock_path = tmp_path / "information.lock"
    held = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    locking.flock(held, locking.LOCK_EX | locking.LOCK_NB)
    monkeypatch.setattr(triage, "LOCK_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(triage, "LOCK_RETRY_SECONDS", 0.005)
    try:
        with pytest.raises(triage.WorkflowError, match="timed out"):
            triage.lock_information_lifecycle(lock_path)
    finally:
        os.close(held)

    monkeypatch.setattr(triage, "fcntl", None)
    with pytest.raises(triage.WorkflowError, match="requires POSIX fcntl"):
        triage.lock_information_lifecycle(lock_path)


def test_information_lifecycle_lock_rejects_hardlink(tmp_path: Path) -> None:
    lock_path = tmp_path / "information.lock"
    lock_path.touch(mode=0o600)
    os.link(lock_path, tmp_path / "information-alias.lock")

    with pytest.raises(triage.WorkflowError, match="private owned regular file"):
        triage.lock_information_lifecycle(lock_path)


def test_read_only_cli_imports_without_fcntl() -> None:
    script = (
        "import importlib, sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "real = importlib.import_module; "
        "importlib.import_module = lambda name, *args, **kwargs: "
        "(_ for _ in ()).throw(ImportError('missing')) if name == 'fcntl' "
        "else real(name, *args, **kwargs); "
        "from shared.references.work_item_runtime import triage; "
        "raise SystemExit(triage.run(['--capabilities']))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["external_mutations"] is False


def test_closure_command_requires_message_and_rechecks_for_later_reply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "close",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "Closing after no response.",
        "prior_note_ids": [101, 102, 103],
        "rationale": "The request remained unanswered.",
    }
    guard = information_guard(tmp_path, request)
    notes = [
        {
            "id": note_id,
            "created_at": f"2026-08-{day:02d}T00:00:00Z",
            "body": "prior",
            "author": {"id": 5},
        }
        for note_id, day in ((101, 1), (102, 2), (103, 3))
    ]

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [{"id": "discussion-1", "notes": notes}]

    mutations: list[str] = []

    def mutate(_host: str, method: str, _endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        mutations.append(method)
        if method == "POST":
            notes.append(
                {
                    "id": 104,
                    "created_at": "2026-08-04T00:00:00Z",
                    "body": payload["body"],
                    "author": {"id": 5},
                }
            )
            return {"id": 104}
        return {}

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(triage, "glab_mutation", mutate)

    with pytest.raises(triage.WorkflowError, match="receipt"):
        triage.apply_information(guard, "close")
    triage.apply_information(guard, "message")
    notes.append(
        {
            "id": 105,
            "created_at": "2026-08-05T00:00:00Z",
            "body": "Here is the missing context.",
            "author": {"id": 8},
        }
    )
    with pytest.raises(triage.WorkflowError, match="later note"):
        triage.apply_information(guard, "close")
    assert mutations == ["POST"]


def test_closure_receipt_blocks_replay_after_issue_is_reopened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "close",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "Closing after no response.",
        "prior_note_ids": [101, 102, 103],
        "rationale": "The request remained unanswered.",
    }
    guard = information_guard(tmp_path, request)
    issue_state = "opened"
    notes = [
        {
            "id": note_id,
            "created_at": f"2026-08-{note_id - 100:02d}T00:00:00Z",
            "body": request["body"] if note_id == 104 else "prior",
            "author": {"id": 5, "username": "reviewer"},
        }
        for note_id in (101, 102, 103, 104)
    ]
    receipt = triage.information_receipt_path(guard, guard.stem)
    message_receipt = {
        "guard_digest": guard.stem,
        "note_id": 104,
        "body": request["body"],
    }
    triage.write_json(receipt, message_receipt)

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"project_id": 19, "iid": 7, "state": issue_state}
        return [{"id": "discussion-1", "notes": notes}]

    mutations: list[str] = []

    def mutate(_host: str, method: str, _endpoint: str, _payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal issue_state
        assert json.loads(receipt.read_text(encoding="utf-8")) == {
            "status": "in_progress",
            "stage": "close",
            **message_receipt,
        }
        mutations.append(method)
        issue_state = "closed"
        return {"project_id": 19, "iid": 7, "state": "opened"}

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(triage, "glab_mutation", mutate)

    triage.apply_information(guard, "close")
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "status": "closed",
        **message_receipt,
    }

    issue_state = "opened"
    with pytest.raises(triage.WorkflowError, match="closure was already applied"):
        triage.apply_information(guard, "close")
    assert mutations == ["PUT"]


@pytest.mark.parametrize("fresh_result", ["opened", "get_failure", "wrong_project", "wrong_iid"])
def test_closure_keeps_reservation_until_fresh_exact_issue_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fresh_result: str,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "close",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "Closing after no response.",
        "prior_note_ids": [101, 102, 103],
        "rationale": "The request remained unanswered.",
    }
    guard = information_guard(tmp_path, request)
    receipt = triage.information_receipt_path(guard, guard.stem)
    message_receipt = {
        "guard_digest": guard.stem,
        "note_id": 104,
        "body": request["body"],
    }
    triage.write_json(receipt, message_receipt)
    notes = [
        {
            "id": note_id,
            "created_at": f"2026-08-{note_id - 100:02d}T00:00:00Z",
            "body": request["body"] if note_id == 104 else "prior",
            "author": {"id": 5, "username": "reviewer"},
        }
        for note_id in (101, 102, 103, 104)
    ]
    issue_gets = 0

    def response(_host: str, endpoint: str) -> Any:
        nonlocal issue_gets
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            issue_gets += 1
            if issue_gets == 1:
                return {"project_id": 19, "iid": 7, "state": "opened"}
            if fresh_result == "get_failure":
                raise triage.WorkflowError("GitLab GET failed")
            project_id = 20 if fresh_result == "wrong_project" else 19
            iid = 8 if fresh_result == "wrong_iid" else 7
            state = "opened" if fresh_result == "opened" else "closed"
            return {"project_id": project_id, "iid": iid, "state": state}
        return [{"id": "discussion-1", "notes": notes}]

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: {"project_id": 19, "iid": 7, "state": "closed"},
    )

    with pytest.raises(triage.MutationOutcomeUnknown, match=r"verified|fresh exact"):
        triage.apply_information(guard, "close")
    assert json.loads(receipt.read_text(encoding="utf-8")) == {
        "status": "in_progress",
        "stage": "close",
        **message_receipt,
    }


@pytest.mark.parametrize(
    ("failure", "expected_receipt"),
    [
        (triage.MutationNotAttempted("not started"), "message"),
        (triage.MutationOutcomeUnknown("unknown"), "reservation"),
    ],
)
def test_closure_transition_restores_only_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: triage.WorkflowError,
    expected_receipt: str,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "close",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "Closing after no response.",
        "prior_note_ids": [101, 102, 103],
        "rationale": "The request remained unanswered.",
    }
    guard = information_guard(tmp_path, request)
    receipt = triage.information_receipt_path(guard, guard.stem)
    message_receipt = {
        "guard_digest": guard.stem,
        "note_id": 104,
        "body": request["body"],
    }
    triage.write_json(receipt, message_receipt)
    notes = [
        {
            "id": note_id,
            "created_at": f"2026-08-{note_id - 100:02d}T00:00:00Z",
            "body": request["body"] if note_id == 104 else "prior",
            "author": {"id": 5, "username": "reviewer"},
        }
        for note_id in (101, 102, 103, 104)
    ]

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [{"id": "discussion-1", "notes": notes}]

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(type(failure), match=str(failure)):
        triage.apply_information(guard, "close")
    stored = json.loads(receipt.read_text(encoding="utf-8"))
    if expected_receipt == "message":
        assert stored == message_receipt
    else:
        assert stored == {"status": "in_progress", "stage": "close", **message_receipt}
        with pytest.raises(triage.WorkflowError, match="closure outcome is unknown"):
            triage.apply_information(guard, "close")


@pytest.mark.parametrize(
    ("receipt_update", "message"),
    [
        ({"body": "tampered"}, "receipt is invalid"),
        ({"note_id": 0}, "receipt is invalid"),
        ({"guard_digest": "b" * 64}, "receipt is invalid"),
    ],
)
def test_closure_rejects_receipt_not_exactly_bound_to_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    receipt_update: dict[str, Any],
    message: str,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    request = {
        "action": "close",
        "target": {
            "kind": "issue",
            "project_id": 19,
            "iid": 7,
            "discussion_id": "discussion-1",
        },
        "body": "Closing after no response.",
        "prior_note_ids": [101, 102, 103],
        "rationale": "The request remained unanswered.",
    }
    guard = information_guard(tmp_path, request)
    receipt = triage.information_receipt_path(guard, guard.stem)
    triage.write_json(
        receipt,
        {
            "guard_digest": guard.stem,
            "note_id": 104,
            "body": request["body"],
            **receipt_update,
        },
    )
    notes = [
        {
            "id": note_id,
            "created_at": f"2026-08-{note_id - 100:02d}T00:00:00Z",
            "body": request["body"] if note_id == 104 else "prior",
            "author": {"id": 5},
        }
        for note_id in (101, 102, 103, 104)
    ]

    def response(_host: str, endpoint: str) -> Any:
        if endpoint == "user":
            return {"id": 5, "username": "reviewer"}
        if endpoint == "projects/19/issues/7":
            return {"iid": 7, "state": "opened"}
        return [{"id": "discussion-1", "notes": notes}]

    monkeypatch.setattr(triage, "glab_json", response)
    monkeypatch.setattr(
        triage,
        "glab_mutation",
        lambda *_args, **_kwargs: pytest.fail("invalid receipt must not close the issue"),
    )

    with pytest.raises(triage.WorkflowError, match=message):
        triage.apply_information(guard, "close")


def test_incomplete_related_mr_identity_makes_collection_partial(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/related_merge_requests?"):
            return [{"id": 41, "iid": 11, "title": "Incomplete related MR"}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    assert result["status"] == "partial"
    assert result["items"] == []
    assert result["errors"][0]["message"] == "related merge request identity is incomplete"


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
    assert "--silent" not in observed[0]


@pytest.mark.parametrize(
    ("result", "message"),
    [
        (subprocess.CompletedProcess([], 1, b"", b"failed"), "failed"),
        (subprocess.CompletedProcess([], 0, b"not-json", b""), "invalid JSON"),
        (subprocess.CompletedProcess([], 0, b"[]", b""), "incomplete"),
    ],
)
def test_glab_mutation_started_failures_are_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    result: subprocess.CompletedProcess[bytes],
    message: str,
) -> None:
    monkeypatch.setattr(triage, "run_mutation_process", lambda *_args: result)
    with pytest.raises(triage.MutationOutcomeUnknown, match=message):
        triage.glab_mutation("gitlab.example", "POST", "projects/19/issues/7/notes", {})


def test_glab_mutation_start_failure_is_proven_not_attempted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with pytest.raises(triage.MutationNotAttempted, match="not attempted"):
        triage.glab_mutation("gitlab.example", "POST", "projects/19/issues/7/notes", {})


def test_mutation_runner_bounds_output_and_reaps_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage, "MUTATION_OUTPUT_LIMIT", 16)
    with pytest.raises(triage.MutationOutcomeUnknown, match="size limit"):
        triage.run_mutation_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100)"], b"{}"
        )

    processes: list[subprocess.Popen[bytes]] = []
    original_popen = subprocess.Popen

    def observe_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", observe_popen)
    monkeypatch.setattr(triage, "MUTATION_OUTPUT_LIMIT", 1024)
    monkeypatch.setattr(triage, "MUTATION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(triage, "MUTATION_TERMINATION_GRACE_SECONDS", 0.02)
    started = time.monotonic()
    with pytest.raises(triage.MutationOutcomeUnknown, match="timed out"):
        triage.run_mutation_process([sys.executable, "-c", "import time; time.sleep(10)"], b"{}")
    assert time.monotonic() - started < 1
    assert processes[0].poll() is not None


def test_mutation_cleanup_failure_cli_reports_unknown_outcome(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    selector_factory = selectors.DefaultSelector

    class FailingCloseSelector:
        def __init__(self) -> None:
            self.delegate = selector_factory()

        def __getattr__(self, name: str) -> Any:
            return getattr(self.delegate, name)

        def close(self) -> None:
            self.delegate.close()
            raise OSError("selector cleanup failed")

    monkeypatch.setattr(selectors, "DefaultSelector", FailingCloseSelector)

    def apply(*_args: Any) -> None:
        triage.run_mutation_process([sys.executable, "-c", "pass"], b"{}")

    monkeypatch.setattr(triage, "apply_information", apply)

    assert triage.run(["apply-information", "--guard", "guard", "--stage", "message"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["external_mutations"] is True
    assert output["mutation_outcome"] == "unknown"
    assert output["error"]["code"] == "mutation_outcome_unknown"


@pytest.mark.parametrize(
    ("failure", "external_mutations", "mutation_outcome", "code"),
    [
        (triage.MutationNotAttempted("not started"), False, "none", "triage_failed"),
        (
            triage.MutationOutcomeUnknown("unknown"),
            True,
            "unknown",
            "mutation_outcome_unknown",
        ),
        (triage.WorkflowError("stale"), False, "none", "triage_failed"),
    ],
)
def test_apply_information_cli_reports_mutation_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: triage.WorkflowError,
    external_mutations: bool,
    mutation_outcome: str,
    code: str,
) -> None:
    monkeypatch.setattr(
        triage,
        "apply_information",
        lambda *_args: (_ for _ in ()).throw(failure),
    )
    assert triage.run(["apply-information", "--guard", "guard", "--stage", "message"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["external_mutations"] is external_mutations
    assert output["mutation_outcome"] == mutation_outcome
    assert output["error"]["code"] == code


def test_apply_information_cli_reports_applied_mutation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(triage, "apply_information", lambda *_args: None)
    assert triage.run(["apply-information", "--guard", "guard", "--stage", "message"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["external_mutations"] is True
    assert output["mutation_outcome"] == "applied"
