from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from shared.references.work_item_runtime import triage

ROOT = Path(__file__).resolve().parents[1]


def test_observed_ce_link_uses_relationship_id_not_target_issue_id() -> None:
    snapshot = {
        "links": [
            {"id": 104, "project_id": 19, "iid": 7, "issue_link_id": 293, "link_type": "relates_to"}
        ]
    }
    assert triage.observed_issue_links(snapshot, 19, 7) == [
        {"id": 293, "relation_type": "relates_to"}
    ]


def test_observed_link_retains_explicit_relation_envelope_compatibility() -> None:
    snapshot = {
        "links": [
            {
                "id": 293,
                "target_issue": {"id": 104, "project_id": 19, "iid": 7},
                "link_type": "relates_to",
            }
        ]
    }
    assert triage.observed_issue_links(snapshot, 19, 7) == [
        {"id": 293, "relation_type": "relates_to"}
    ]


@pytest.mark.parametrize("value", [None, 0, -1, True, "293"])
def test_invalid_relationship_id_cannot_fall_back_to_issue_id(value: Any) -> None:
    snapshot = {
        "links": [
            {
                "id": 104,
                "project_id": 19,
                "iid": 7,
                "issue_link_id": value,
                "link_type": "relates_to",
            }
        ]
    }
    with pytest.raises(triage.WorkflowError, match="invalid relationship ID"):
        triage.observed_issue_links(snapshot, 19, 7)


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
        "Prepare one guarded command block per action",
        "stops before any write when a guard fails",
        "emitted as a regeneration instruction, never as a ready command",
        "names and links the issue",
        "two or three concrete, understood, reversible alternatives",
        "never offer to ask the author later",
        "most specific relevant existing discussion",
        "Answer an already-addressed question before introducing a new one.",
        "separates analysis completeness from follow-up state",
        "only when the complete analyzed value is plain text",
        "Issue identities returned by the assessed issue's GitLab link evidence",
        "use an explicit empty list when none are found",
        "one guarded block that finds or creates the milestone",
        "publishes the final message and then closes the issue in the same `&&` chain",
        "one explanation-and-close block with `state_event=close`",
        "delete-then-create block that re-verifies the observed link before deleting",
        "`glab`, `jq`, and `sha256sum`",
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
            "milestone": {"id": 9, "title": "v1.1.0", "state": "active"},
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
                "author": {"id": 8, "username": "mr-author"},
                "assignees": [{"id": 9, "username": "mr-assignee"}],
                "reviewers": [{"id": 10, "username": "mr-reviewer"}],
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
                "issue_relations": [
                    {
                        "target_hostname": "gitlab.example",
                        "target_project_id": 19,
                        "target_issue_iid": 3,
                        "relation_type": "relates_to",
                        "rationale": "The older issue documents only part of the retry behavior.",
                        "existing_link": None,
                        "comment": None,
                    }
                ],
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
                "agent_recommendation": {
                    "proposal": "Clarify retry acceptance criteria before implementation.",
                    "rationale": "The implementation MR is open while expected behavior is ambiguous.",
                    "assumptions": ["The existing retry interface remains supported."],
                    "confidence": "medium",
                    "alternatives": ["Defer the issue until the MR defines the contract."],
                    "reconsider_if": "The related MR already contains complete acceptance tests.",
                },
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
        "top_five": [
            {
                "evidence_digest": item["evidence_digest"],
                "rationale": "It blocks safe retries implemented in !11.",
            }
        ],
        "parallel_groups": [
            {
                "evidence_digests": [item["evidence_digest"]],
                "rationale": "The task can proceed independently.",
            }
        ],
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


def test_summary_reference_linking_only_changes_whole_plain_text_values() -> None:
    references = {
        "#": {7: "https://gitlab.example/group/project/-/issues/7"},
        "!": {},
    }
    assert triage.link_summary_references("Use #7 and !11.", references) == (
        "Use [#7](https://gitlab.example/group/project/-/issues/7) and !11."
    )
    assert triage.link_summary_references("Keep #7beta and !11draft; link #7.", references) == (
        "Keep #7beta and !11draft; link [#7](https://gitlab.example/group/project/-/issues/7)."
    )
    assert triage.link_summary_references("Keep #7/notes and link #7.", references) == (
        "Keep #7/notes and link [#7](https://gitlab.example/group/project/-/issues/7)."
    )
    mixed = (
        "Use #7 and !11; keep [issue #7](https://example.test/7), `#7`, "
        "<https://example.test/#7>, https://example.test/?ref=#7 and \\#7 unchanged."
    )
    assert triage.link_summary_references(mixed, references) == mixed


def test_summary_reference_linking_keeps_whole_markdown_value_unchanged() -> None:
    references = {"#": {7: "https://gitlab.example/group/project/-/issues/7"}, "!": {}}
    value = "\n".join(
        [
            "Plain #7.",
            "Ordinary [text #7] remains plain text around the linked reference.",
            "[reference #7][target] and [escaped \\] #7](https://example.test/a_(b)#7)",
            "[target]: docs?issue=#7",
            "",
            '``code ` #7`` and <code class="ref">#7</code>',
            "`multiline",
            "#7",
            "code`",
            "[label `]` #7](docs)",
            "[label #7",
            "continued](docs)",
            "    indented #7",
            "```text",
            "fenced #7",
            "```",
            "> ~~~text",
            "> quoted fence #7",
            "> ~~~",
            ">     quoted indented #7",
            "escaped \\` #7 \\` markers",
            "HTTPS://example.test/?ref=#7",
            "[escaped \\] #7]: docs?issue=#7",
            '  "continued title #7"',
            "Plain after definition #7.",
        ]
    )
    rendered = triage.link_summary_references(value, references)
    assert rendered == value
    assert triage.link_summary_references("[plain #7][missing]", references) == (
        "[plain #7][missing]"
    )


@pytest.mark.parametrize(
    "value",
    [
        "See ftp://example.test/#8 and #7.",
        "See www.example.test/#8 and #7.",
        "Title #7\n---",
        "Title #7\n===",
        "---\nSee #7.",
        "| Task | Ref |\n| --- | --- |\n| Retry | #7 |",
        "See #7\\\nnext line",
        "See #7  \nnext line",
        "See \\? and #7.",
        "See \\/path and #7.",
    ],
)
def test_summary_reference_linking_rejects_nonplain_whole_values(value: str) -> None:
    references = {"#": {7: "https://gitlab.example/group/project/-/issues/7"}, "!": {}}
    assert triage.link_summary_references(value, references) == value


def test_summary_escapes_issue_title_and_uses_canonical_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint == "projects/19/issues/7":
            value["title"] = "Unsafe ] ![image](https://invalid.example/x) <img>"
            value["web_url"] = "javascript:alert(1)"
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    analysis_path = tmp_path / "safe-markdown.json"
    analysis_path.write_text(json.dumps(analysis_for(result)), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "javascript:" not in summary
    assert "javascript:" not in report
    assert "https://gitlab.example/group/project/-/issues/7" in summary
    assert "- Source: https://gitlab.example/group/project/-/issues/7" in report
    assert r"Unsafe \] !\[image\](https://invalid.example/x) &lt;img&gt;" in summary
    assert r"# Unsafe \] !\[image\](https://invalid.example/x) &lt;img&gt;" in report


def test_canonical_merge_request_url_rejects_untrusted_web_urls() -> None:
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {"iid": 11, "web_url": "javascript:alert(1)"},
        )
        is None
    )
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {"iid": 11, "web_url": "https://gitlab.example/group/project/merge_requests/11"},
        )
        == "https://gitlab.example/group/project/-/merge_requests/11"
    )
    assert (
        triage.canonical_linked_issue_url(
            "gitlab.example",
            {"iid": 7, "web_url": "https://gitlab.example/group/project/issues/7"},
        )
        == "https://gitlab.example/group/project/-/issues/7"
    )
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {
                "iid": 11,
                "references": {"full": "other/project!11"},
                "web_url": "https://gitlab.example/group/project/-/merge_requests/11",
            },
        )
        is None
    )
    assert (
        triage.canonical_linked_issue_url(
            "gitlab.example",
            {
                "iid": 7,
                "references": {"full": "other/project#7"},
                "web_url": "https://gitlab.example/group/project/-/issues/7",
            },
        )
        is None
    )
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {"iid": 11, "web_url": "https://gitlab.example:443/group/project/merge_requests/11"},
        )
        == "https://gitlab.example/group/project/-/merge_requests/11"
    )
    assert (
        triage.canonical_linked_issue_url(
            "gitlab.example",
            {"iid": 7, "web_url": "https://gitlab.example:443/group/project/issues/7"},
        )
        == "https://gitlab.example/group/project/-/issues/7"
    )
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {"iid": 11, "web_url": "https://GitLab.Example/group/project/merge_requests/11/"},
        )
        == "https://gitlab.example/group/project/-/merge_requests/11"
    )
    assert (
        triage.canonical_linked_issue_url(
            "gitlab.example",
            {"iid": 7, "web_url": "https://GitLab.Example/group/project/issues/7/"},
        )
        == "https://gitlab.example/group/project/-/issues/7"
    )
    assert (
        triage.canonical_merge_request_url(
            "gitlab.example",
            {"iid": 11, "web_url": "https://other.example/group/project/-/merge_requests/11"},
        )
        is None
    )


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
    summary_text = summary.read_text(encoding="utf-8")
    assert "[#7 Clarify retries](https://gitlab.example/group/project/-/issues/7)" in summary_text
    assert "[!11](https://gitlab.example/group/project/-/merge_requests/11)" in summary_text
    assert "## Detailed reports\n\n### Accepted" in summary_text
    assert "#### Fully planned" in summary_text
    assert "#### Awaiting planning action" in summary_text
    assert "[Report](file://" in summary_text

    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "## Agent recommendation" in report
    assert "- Primary proposal: Clarify retry acceptance criteria before implementation." in report
    assert "## Issue relations" in report
    assert "--method PUT" in report
    assert "--method POST" in report
    assert "$(touch unsafe)" in report
    blocks = shell_blocks(report)
    assert len(blocks) == 4
    assert all("marker-run" not in block for block in blocks)
    assert all("execution-status" not in block for block in blocks)
    title_block, labels_block, milestone_block, link_block = blocks
    assert '{"title":"Clarify retry behavior; $(touch unsafe)"}' in title_block
    assert '{"labels":"priority::high,type::bug"}' in labels_block
    assert '{"milestone_id":9}' in milestone_block
    assert '{"target_project_id":19,"target_issue_iid":3,"link_type":"relates_to"}' in link_block
    assert not (Path(first["artifact_root"]) / "artifacts" / "commands").exists()

    second = triage.collect(arguments(source))
    assert second["items"][0]["analysis_required"] is False
    assert second["items"][0]["cached_analysis"]["priority"] == "high"
    reused = {
        "collection_digest": second["collection_digest"],
        "items": [second["items"][0]["cached_analysis"]],
        "top_five": [
            {
                "evidence_digest": second["items"][0]["evidence_digest"],
                "rationale": "It blocks safe retries.",
            }
        ],
        "parallel_groups": [
            {
                "evidence_digests": [second["items"][0]["evidence_digest"]],
                "rationale": "The task can proceed independently.",
            }
        ],
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


def test_execution_plan_requires_unique_accepted_evidence_bindings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    collection_path = Path(result["artifact_root"]) / "current.json"
    analysis_path = tmp_path / "execution-plan.json"
    value = analysis_for(result)
    value["top_five"][0]["evidence_digest"] = "f" * 64
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="unique accepted item"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["parallel_groups"].append(dict(value["parallel_groups"][0]))
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="unique accepted items"):
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


def test_publish_requires_primary_recommendation_and_partial_relation_link(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    collection_path = Path(result["artifact_root"]) / "current.json"
    analysis_path = tmp_path / "analysis.json"

    value = analysis_for(result)
    del value["items"][0]["agent_recommendation"]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="agent recommendation fields"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    del value["items"][0]["issue_relations"]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="issue_relations field is required"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["related_issues"] = ["legacy"]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="legacy issue relation fields"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["issue_relations"] = []
    value["items"][0]["proposed_changes"]["links"] = []
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    assert (
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )["status"]
        == "ok"
    )

    value = analysis_for(result)
    value["items"][0]["proposed_changes"]["links"] = []
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="must exactly match"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["proposed_changes"]["links"].append(
        dict(value["items"][0]["proposed_changes"]["links"][0])
    )
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="contain duplicates"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["proposed_changes"]["links"].append(
        {"target_project_id": 999999, "target_issue_iid": 1, "link_type": "relates_to"}
    )
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="must exactly match"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["issue_relations"][0]["existing_link"] = {
        "id": 300,
        "relation_type": "relates_to",
    }
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="does not match collected evidence"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    value["items"][0]["issue_relations"][0]["target_hostname"] = "other.example"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="target is invalid"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value = analysis_for(result)
    comment = "#3 establishes the compatibility constraint used by this task."
    value["items"][0]["issue_relations"][0]["comment"] = comment
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="requires a matching issue message"):
        triage.publish(
            argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
        )

    value["items"][0]["proposed_changes"]["messages"] = [
        {
            "target": {
                "kind": "issue",
                "project_id": 19,
                "iid": 7,
                "discussion_id": None,
            },
            "body": comment,
        }
    ]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(collection=str(collection_path), analysis=str(analysis_path))
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert comment in report


def test_observed_partial_relation_does_not_require_duplicate_link_proposal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/links?"):
            return [{"id": 300, "project_id": 19, "iid": 3, "link_type": "relates_to"}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["issue_relations"][0]["existing_link"] = {
        "id": 300,
        "relation_type": "relates_to",
    }
    value["items"][0]["proposed_changes"]["links"] = []
    analysis_path = tmp_path / "existing-relation.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")

    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "Create issue link" not in report


def test_observed_issue_link_requires_explicit_type() -> None:
    with pytest.raises(triage.WorkflowError, match="link type is invalid"):
        triage.observed_issue_links({"links": [{"id": 300, "project_id": 19, "iid": 3}]}, 19, 3)
    with pytest.raises(triage.WorkflowError, match="evidence is incomplete"):
        triage.validate_observed_link_evidence({"links": [{"id": 300, "project_id": 19, "iid": 3}]})


def test_publish_rejects_malformed_collected_links_without_questions_or_relations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/links?"):
            return [{"id": 300, "project_id": 19, "iid": 3}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["issue_relations"] = []
    value["items"][0]["proposed_changes"]["links"] = []
    value["questions"] = []
    analysis_path = tmp_path / "malformed-link-evidence.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="evidence is incomplete"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )


def test_cross_project_partial_relation_accepts_same_host_link_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/links?"):
            return [{"id": 301, "project_id": 20, "iid": 9, "link_type": "relates_to"}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    relation = value["items"][0]["issue_relations"][0]
    relation.update(
        {
            "target_project_id": 20,
            "target_issue_iid": 9,
            "existing_link": {"id": 301, "relation_type": "relates_to"},
        }
    )
    value["items"][0]["proposed_changes"]["links"] = []
    analysis_path = tmp_path / "cross-project-relation.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")

    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "gitlab.example:20#9" in report


def test_cross_project_link_evidence_makes_same_iid_reference_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues?state=all"):
            return [
                {"id": 103, "iid": 3, "title": "Old retries"},
                {"id": 109, "iid": 9, "title": "Local issue"},
            ]
        if endpoint.startswith("projects/19/issues/7/links?"):
            return [{"id": 302, "project_id": 20, "iid": 9, "link_type": "relates_to"}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["top_five"] = [
        {
            "evidence_digest": result["items"][0]["evidence_digest"],
            "rationale": "Investigate #9 before implementation.",
        }
    ]
    analysis_path = tmp_path / "ambiguous-cross-project-reference.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert "Investigate #9 before implementation." in summary
    assert "[#9](" not in summary


def test_unanswered_question_requires_context_options_and_nonself_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint == "projects/19/issues/7":
            value["author"] = {"id": 5, "username": "reviewer"}
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    question = {
        "evidence_digest": result["items"][0]["evidence_digest"],
        "kind": "bounded_technical",
        "tldr": "Retry behavior is ambiguous while implementation is open.",
        "evidence": "The issue and !11 do not define the retry limit.",
        "decision": "Choose the public retry limit.",
        "why_now": "The answer determines whether the task can be accepted.",
        "planning_effect": "Choosing an option makes planning ready; otherwise it stays deferred.",
        "recommendation": {
            "option": "Three retries",
            "rationale": "It preserves the current implementation with a bounded failure time.",
        },
        "options": [
            {"label": "Three retries", "description": "Preserve current bounded behavior."},
            {"label": "Configurable", "description": "Add a new public setting."},
        ],
        "fallback": None,
    }
    value = analysis_for(result)
    value["questions"] = [question]
    analysis_path = tmp_path / "question.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    assert published["status"] == "partial"
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert "[#7 Clarify retries](https://gitlab.example/group/project/-/issues/7)" in summary
    assert "[!11](https://gitlab.example/group/project/-/merge_requests/11)" in summary
    assert "Decision needed: Choose the public retry limit." in summary
    assert "Why now: The answer determines whether the task can be accepted." in summary
    assert "Planning effect: Choosing an option makes planning ready" in summary
    assert "Agent recommendation: Three retries" in summary
    assert "Options: Three retries: Preserve current bounded behavior." in summary
    assert "Fallback: None observed." in summary

    second_question = json.loads(json.dumps(question))
    second_question.update(
        {
            "kind": "authority",
            "decision": "Confirm whether this issue remains in the release scope.",
            "why_now": "The release scope is being finalized.",
            "planning_effect": "A rejection moves the task out of the milestone.",
        }
    )
    value["questions"] = [question, second_question]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    assert "- Unanswered user questions: 2 - " in Path(published["summary"]).read_text(
        encoding="utf-8"
    )

    fallback_target = {
        "kind": "merge_request",
        "project_id": 19,
        "iid": 11,
        "discussion_id": None,
    }
    fallback_body = "Please confirm the implementation behavior."
    value["questions"] = [question]
    value["questions"][0]["fallback"] = {
        "participant": "mr-author",
        "target": fallback_target,
        "body": fallback_body,
    }
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="must match an information request"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )

    value["items"][0]["information_requests"] = [
        {
            "action": "new",
            "target": fallback_target,
            "body": fallback_body,
            "prior_note_ids": [],
            "rationale": "The implementation evidence is incomplete.",
            "standalone_reason": "No merge-request discussion covers this behavior.",
        }
    ]
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    assert (
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )["status"]
        == "partial"
    )

    value["questions"][0]["fallback"]["participant"] = "reviewer"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="fallback participant is invalid"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )

    value["questions"][0]["fallback"]["participant"] = "mr-reviewer"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="fallback participant is invalid"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )

    value["questions"][0]["fallback"] = None
    value["questions"][0]["options"].extend(
        [
            {"label": "Five retries", "description": "Increase tolerance."},
            {"label": "Unlimited", "description": "Retry until success."},
        ]
    )
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(triage.WorkflowError, match="two or three options"):
        triage.publish(
            argparse.Namespace(
                collection=str(Path(result["artifact_root"]) / "current.json"),
                analysis=str(analysis_path),
            )
        )


def test_collect_invalidates_pre_recommendation_analysis_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    source = "https://gitlab.example/group/project/-/issues/7"
    first = triage.collect(arguments(source))
    item = first["items"][0]
    old_analysis = analysis_for(first)["items"][0]
    old_analysis.pop("agent_recommendation")
    old_analysis.pop("issue_relations")
    Path(first["artifact_root"], "analysis-index.json").write_text(
        json.dumps(
            {
                "items": {
                    "gitlab.example:19:7": {
                        "source_fingerprint": item["source_fingerprint"],
                        "context_digest": item["context_digest"],
                        "analysis": old_analysis,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    second = triage.collect(arguments(source))
    assert second["items"][0]["analysis_required"] is True
    assert second["items"][0]["cached_analysis"] is None


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


def test_missing_milestone_keeps_analysis_complete_and_marks_follow_up_pending(
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
    assert published["status"] == "ok"
    assert published["follow_up_status"] == "pending"
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert "- Analysis status: complete" in summary
    assert "- Follow-up status: pending" in summary
    assert "- Non-ready planning: 1 - [#7 Clarify retries]" in summary
    assert "No compatible active major milestone exists." in summary
    assert "#### Awaiting planning action\n\n- [#7 Clarify retries]" in summary
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "--method POST" in report
    assert "projects/19/milestones" in report
    assert "'map(select(.title == $title) | .id) | first // empty'" in report
    assert '{"title":"v2.0.0"}' in report
    assert '{"milestone_id": $milestone_id}' in report
    create_block = next(block for block in shell_blocks(report) if "--method POST" in block)
    assert (
        create_block.index("first // empty")
        < create_block.index("--method POST")
        < create_block.index('{"milestone_id": $milestone_id}')
    )
    assert ".milestone.id == 9" in create_block


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
    value["top_five"] = []
    value["parallel_groups"] = []
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
    assert '{"milestone_id":0}' in report
    assert "jq -e '.milestone.id == 9' >/dev/null" in report
    assert not (Path(result["artifact_root"]) / "artifacts" / "commands").exists()


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


def test_russian_reports_are_localized_and_summary_groups_linked_reports(
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
    for heading in (
        "### Приняты",
        "### Отложены",
        "### Отклонены",
        "### Дубликаты",
        "### Устарели",
    ):
        assert heading in summary
    assert "#### Полностью распланированы" in summary
    assert "#### Ожидают действия по планированию" in summary
    assert "[#7 Clarify retries](https://gitlab.example/group/project/-/issues/7)" in summary
    assert f"[Отчёт]({report_path.as_uri()})" in summary
    assert "- Статус анализа: завершён" in summary
    assert "- Статус дальнейших действий: действия не требуются" in summary
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
            "standalone_reason": None,
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
    assert "projects/19/issues/7/discussions/discussion-1/notes" in report
    assert '{"body":"Повторно прошу уточнить ожидаемое поведение."}' in report
    assert published["status"] == "ok"
    assert published["follow_up_status"] == "pending"
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert (
        "- Information requests to publish: 1; Affected issues: 1 - [#7 Clarify retries]" in summary
    )
    assert "Содержательного ответа пока нет." in summary

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
            "standalone_reason": None,
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
            "standalone_reason": None,
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
        == "ok"
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
    message_block = next(block for block in shell_blocks(report) if "/merge_requests/11" in block)
    assert '.state == "opened"' in message_block
    assert "projects/19/merge_requests/11/discussions" in message_block
    assert "sha256sum" in message_block


def test_summary_counts_information_requests_and_affected_issues_separately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    value["items"][0]["information_requests"] = [
        {
            "action": "new",
            "target": {
                "kind": "issue",
                "project_id": 19,
                "iid": 7,
                "discussion_id": None,
            },
            "body": "Please clarify the issue contract.",
            "prior_note_ids": [],
            "rationale": "The issue contract is incomplete.",
            "standalone_reason": "No issue discussion covers this contract gap.",
        },
        {
            "action": "new",
            "target": {
                "kind": "merge_request",
                "project_id": 19,
                "iid": 11,
                "discussion_id": None,
            },
            "body": "Please confirm the implementation behavior.",
            "prior_note_ids": [],
            "rationale": "The implementation evidence is incomplete.",
            "standalone_reason": "No merge-request discussion covers this behavior.",
        },
    ]
    analysis_path = tmp_path / "request-counts.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert "- Information requests to publish: 2; Affected issues: 1 - " in summary


def test_information_request_requires_exact_latest_current_user_cycle() -> None:
    target = {
        "kind": "issue",
        "project_id": 19,
        "iid": 7,
        "discussion_id": "discussion-1",
    }
    request: dict[str, Any] = {
        "action": "ping_2",
        "target": target,
        "body": "Second follow-up.",
        "prior_note_ids": [101, 102],
        "rationale": "No sufficient answer was observed.",
        "standalone_reason": None,
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
        "standalone_reason": "No observed discussion concerns the missing context.",
    }
    with pytest.raises(triage.WorkflowError, match="issue is not open"):
        triage.validate_information_request(
            snapshot,
            {"id": 5, "username": "reviewer"},
            request,
            "request",
        )


def test_new_standalone_information_requires_explicit_thread_reason() -> None:
    snapshot = {
        "target": {"project_id": 19, "iid": 7},
        "issue": {"state": "opened"},
        "discussions": [{"id": "discussion-1", "notes": []}],
        "merge_request_conversations": [],
    }
    request: dict[str, Any] = {
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
        "standalone_reason": None,
    }
    with pytest.raises(triage.WorkflowError, match="standalone_reason"):
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
        "standalone_reason": None,
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
            "standalone_reason": None,
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
    assert "### Close issue" not in report
    assert "apply-information" not in report
    closure_blocks = [block for block in shell_blocks(report) if '"state_event":"close"' in block]
    assert len(closure_blocks) == 1
    block = closure_blocks[0]
    assert block.count("glab api --hostname") == 5
    assert "--method POST" in block
    assert "projects/19/issues/7/discussions/discussion-1/notes" in block
    assert (
        '{"body":"Закрываю задачу: после вопроса и двух пингов информации не поступило."}' in block
    )
    assert block.index("--method POST") < block.index('"state_event":"close"')
    assert "<<'TRIAGE_JSON_" in block
    assert '.state == "opened"' in block
    assert '| sha256sum)" && [ "${note_digest%% *}"' in block


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


def shell_blocks(markdown: str) -> list[str]:
    return [
        block for block in re.findall(r"```sh\n(.*?)\n```", markdown, re.DOTALL) if block.strip()
    ]


def test_generated_blocks_use_direct_glab_api_with_guards(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(result)), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert "- Actions without commands: 0" in summary
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    for helper in ("marker-run", "apply-information", "apply-link", "--silent"):
        assert helper not in report
    blocks = shell_blocks(report)
    assert len(blocks) == 4
    for block in blocks:
        assert block.startswith(f"# {triage.TEXT['en']['guard_user']}")
        assert block.count("glab api --hostname gitlab.example user") == 1
        assert "<<'TRIAGE_JSON_" in block
    title_block, labels_block, milestone_block, link_block = blocks
    assert "jq -r '.updated_at'" in title_block
    assert "= 2026-09-23T00:00:00Z ]" in title_block
    for block in blocks:
        for tool in ("| cut ", "|awk", "awk ", "| sed ", "| grep ", "base64", "xargs"):
            assert tool not in block, (tool, block)
    for block in blocks[1:]:
        assert ".updated_at" not in block
    assert "jq -c '[(.labels // [])[] | if type == \"object\" then .name else . end] | sort'" in (
        labels_block
    )
    assert "= '[]' ]" in labels_block
    assert ".milestone.id == 9" in milestone_block
    assert ".iid == $i" in link_block


def test_replace_link_block_deletes_then_creates_in_one_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        if endpoint.startswith("projects/19/issues/7/links?"):
            return [{"id": 300, "project_id": 19, "iid": 3, "link_type": "relates_to"}]
        return gitlab_response(endpoint)

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    relation = value["items"][0]["issue_relations"][0]
    relation["relation_type"] = "blocks"
    relation["existing_link"] = {"id": 300, "relation_type": "relates_to"}
    value["items"][0]["proposed_changes"]["links"][0]["link_type"] = "blocks"
    analysis_path = tmp_path / "replace-relation.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert "### Replace conflicting issue link" in report
    assert "### Delete conflicting issue link" not in report
    assert "apply-link" not in report
    assert not list(Path(result["artifact_root"]).glob("**/link-guards/*.json"))
    replace_blocks = [block for block in shell_blocks(report) if "--method DELETE" in block]
    assert len(replace_blocks) == 1
    block = replace_blocks[0]
    assert block.count(".link_type == $t") == 2
    assert "issue_link_id // .id" in block
    assert '[ "$link_id" = 300 ]' in block
    assert "projects/19/issues/7/links/300" in block
    assert '{"target_project_id":19,"target_issue_iid":3,"link_type":"blocks"}' in block
    assert block.index("--method DELETE") < block.index("--method POST")


@pytest.mark.parametrize("status", ["obsolete", "duplicate"])
def test_obsolete_and_duplicate_issues_get_explanation_and_close_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    value = analysis_for(result)
    item = value["items"][0]
    item["actuality"] = {
        "status": status,
        "rationale": "Superseded by the older retry issue.",
        "confidence": "high",
    }
    item["release_plan"]["decision"] = {
        "status": status,
        "rationale": "The issue must leave the open backlog.",
        "confidence": "high",
    }
    item["release_plan"]["milestone"] = {
        "status": "remove",
        "candidate": None,
        "rationale": "Unaccepted work leaves the active milestone.",
        "confidence": "high",
    }
    value["top_five"] = []
    value["parallel_groups"] = []
    analysis_path = tmp_path / "close.json"
    analysis_path.write_text(json.dumps(value), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    close_blocks = [block for block in shell_blocks(report) if '"state_event":"close"' in block]
    assert len(close_blocks) == 1
    block = close_blocks[0]
    assert "# Close issue: Superseded by the older retry issue." in block
    assert '.state == "opened"' in block
    assert '{"state_event":"close"}' in block


def test_summary_lists_uncovered_actions_with_reasons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    def response(_host: str, endpoint: str) -> Any:
        value = gitlab_response(endpoint)
        if endpoint == "projects/19/issues/7":
            value.pop("updated_at")
        return value

    monkeypatch.setattr(triage, "glab_json", response)
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(result)), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    report = Path(published["reports"][0]["report"]).read_text(encoding="utf-8")
    assert shell_blocks(report) == []
    assert report.count("- Regeneration required: ") == 4
    summary = Path(published["summary"]).read_text(encoding="utf-8")
    assert (
        "- Actions without commands: 4 - "
        "https://gitlab.example/group/project/-/issues/7: Update title" in summary
    )
    assert "Create issue link" in summary


def test_conversation_digest_matches_the_jq_guard_pipeline() -> None:
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("jq is unavailable")
    notes: list[dict[str, Any]] = [
        {"id": 1, "system": True, "body": "changed the issue"},
        {"id": 2, "body": "alpha"},
        {"id": 3, "body": "beta\nline"},
    ]
    expected = triage.bodies_digest(["alpha", "beta\nline"])

    def live(items: list[dict[str, Any]]) -> str:
        result = subprocess.run(
            [
                jq,
                "-sr",
                "[.[][] | .notes[]? | select(.system != true) | .body] | sort | .[]",
            ],
            input=json.dumps([{"id": "d1", "notes": items}]),
            capture_output=True,
            text=True,
            check=True,
        )
        return triage.stream_digest(result.stdout)

    assert live(notes) == expected
    changed = [*notes, {"id": 4, "body": "prepared message"}]
    assert live(changed) != expected


def test_removed_helper_commands_are_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    assert triage.run(["apply-information", "--guard", "g", "--stage", "message"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert triage.run(["apply-link", "--guard", "g", "--stage", "delete"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"


def test_heredoc_delimiter_never_collides_with_the_body() -> None:
    for body in (
        '{"body":"line1\\nline2"}',
        '{"title":"TRIAGE_JSON_AAAAAAAAAAAAAAAA"}',
        '{"body":"Закрываю задачу."}',
    ):
        rendered = triage.inline_write("gitlab.example", "POST", "projects/1/issues/2/notes", body)
        first, *rest = rendered.splitlines()
        delimiter = first.split("<<", 1)[1].removesuffix(" &&").strip("'")
        assert delimiter.startswith("TRIAGE_JSON_")
        assert rest[-1] == delimiter
        assert all(line != delimiter for line in rest[:-1])


def test_blocks_execute_in_order_against_a_stateful_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Each later block re-reads live state; executing in order succeeds and replaying stops."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(triage, "glab_json", lambda _host, endpoint: gitlab_response(endpoint))
    result = triage.collect(arguments("https://gitlab.example/group/project/-/issues/7"))
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps(analysis_for(result)), encoding="utf-8")
    published = triage.publish(
        argparse.Namespace(
            collection=str(Path(result["artifact_root"]) / "current.json"),
            analysis=str(analysis_path),
        )
    )
    blocks = shell_blocks(Path(published["reports"][0]["report"]).read_text(encoding="utf-8"))
    assert len(blocks) == 4

    state = tmp_path / "server"
    state.mkdir()
    (state / "issue.json").write_text(
        json.dumps(
            {
                "iid": 7,
                "title": "Clarify retries",
                "description": "Retry behavior is ambiguous.",
                "state": "opened",
                "labels": [],
                "milestone": {"id": 9, "title": "v1.1.0", "state": "active"},
                "updated_at": "2026-09-23T00:00:00Z",
            }
        )
    )
    for name in ("milestones.json", "links.json"):
        (state / name).write_text("[]")
    stub = tmp_path / "glab"
    stub.write_text(
        f"""#!/bin/bash
set -u
state="{state}"
args="$*"
body="$(cat)"
case "$args" in
  *" user")
    printf '%s' '{{"id":5,"username":"reviewer"}}' ;;
  *"--method PUT projects/19/issues/7"*)
    jq -c --argjson b "$body" '
      if ($b | has("title")) then .title = $b.title else . end
      | if ($b | has("labels")) then .labels = ($b.labels | split(",")) else . end
      | if ($b | has("milestone_id")) then .milestone = {{"id": $b.milestone_id}} else . end
      | .updated_at = "2026-09-24T00:00:00Z"
    ' "$state/issue.json" > "$state/issue.next"
    mv "$state/issue.next" "$state/issue.json"
    jq -c . "$state/issue.json" ;;
  *"--method POST projects/19/milestones"*)
    id="$(jq -r '[.[] | .id] | max // 0 | . + 1' "$state/milestones.json")"
    jq -c --arg title "$(printf '%s' "$body" | jq -r .title)" --argjson id "$id" '
      . + [{{"id": $id, "title": $title, "state": "active"}}]' "$state/milestones.json" \
      > "$state/milestones.next"
    mv "$state/milestones.next" "$state/milestones.json"
    printf '%s' "{{\\"id\\": $id}}" ;;
  *"--method POST projects/19/issues/7/links"*)
    id="$(jq -r '[.[] | .issue_link_id] | max // 100 | . + 1' "$state/links.json")"
    jq -c --argjson b "$body" --argjson id "$id" '
      . + [{{"issue_link_id": $id, "project_id": $b.target_project_id,
            "iid": $b.target_issue_iid, "link_type": $b.link_type}}]' \
      "$state/links.json" > "$state/links.next"
    mv "$state/links.next" "$state/links.json"
    printf '%s' '{{"ok": true}}' ;;
  *milestones\\?*)
    jq -c '[.[] | select(.state == "active")]' "$state/milestones.json" ;;
  *issues/7/links\\?*)
    jq -c '[.[] | select(.link_type)]' "$state/links.json" ;;
  *"projects/19/issues/7"*)
    jq -c . "$state/issue.json" ;;
  *)
    printf '%s' '{{}}' ;;
esac
"""
    )
    stub.chmod(0o700)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    for index, block in enumerate(blocks):
        executed = subprocess.run(
            ["bash", "-ec", block + "\n"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert executed.returncode == 0, f"block {index} failed: {executed.stderr}"

    issue = json.loads((state / "issue.json").read_text())
    assert issue["title"] == "Clarify retry behavior; $(touch unsafe)"
    assert issue["labels"] == ["priority::high", "type::bug"]
    assert issue["milestone"] == {"id": 9}
    links = json.loads((state / "links.json").read_text())
    assert links == [
        {
            "issue_link_id": 101,
            "project_id": 19,
            "iid": 3,
            "link_type": "relates_to",
        }
    ]

    # Replays stop on their own preconditions; the milestone attach is an
    # idempotent no-op when the candidate is already attached, so its replay
    # may succeed but must leave the state unchanged.
    for index, block in enumerate(blocks):
        replayed = subprocess.run(
            ["bash", "-ec", block + "\n"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if index == 2:
            assert replayed.returncode == 0, replayed.stderr
            assert json.loads((state / "issue.json").read_text())["milestone"]["id"] == 9
            continue
        assert replayed.returncode != 0, f"replayed block {index} did not stop"
        assert "regenerate" in replayed.stderr


def test_labels_guard_accepts_string_and_object_label_shapes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The live issue API returns label strings; the guard must also accept objects."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    guard = triage.labels_guard(
        "gitlab.example",
        "projects/19/issues/7",
        ["priority::high", "type::bug"],
        "en",
    )
    stub = tmp_path / "glab"
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    def run(labels: Any) -> subprocess.CompletedProcess[str]:
        script = tmp_path / "labels-guard.sh"
        script.write_text(guard + "\ntrue\n")
        assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0
        stub.write_text(
            "#!/bin/sh\ncat > /dev/null\nprintf '%s' '" + json.dumps({"labels": labels}) + "'\n"
        )
        stub.chmod(0o700)
        return subprocess.run(
            ["bash", "-ec", guard + "\ntrue"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert run(["type::bug", "priority::high"]).returncode == 0
    assert run([{"name": "priority::high"}, {"name": "type::bug"}]).returncode == 0
    stopped = run(["priority::high"])
    assert stopped.returncode != 0
    assert "labels changed after triage" in stopped.stderr
    assert run(None).returncode != 0
