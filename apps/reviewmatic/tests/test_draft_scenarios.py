"""End-to-end draft and runbook scenarios against the fake glab.

Tests inspect finalized plan artifacts and generated publication blocks
directly; no terminal viewer or in-app send adapter is involved.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.publication import command_argv

SHARED_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "references"
    / "portable_gitlab"
    / "artifact-contracts-v2.schema.json"
)


@pytest.fixture(name="fixtures")
def fake_glab_factory() -> Any:
    created: list[ReviewFixture] = []

    def build(overrides: dict[str, Any] | None = None) -> ReviewFixture:
        fixture = make_review_fixture(overrides)
        created.append(fixture)
        return fixture

    try:
        yield build
    finally:
        for fixture in reversed(created):
            fixture.close()


def _read(path: Any) -> dict[str, Any]:
    return contract.read_json(Path(str(path)), "draft")


def _write(path: Any, value: dict[str, Any]) -> None:
    contract.write_json(Path(str(path)), value)


def _errors(result: dict[str, Any]) -> str:
    return json.dumps(result["errors"])


def _progress(root: Path) -> dict[str, Any]:
    progress = review_context.load_progress(root)
    assert progress is not None
    return progress


def _plan(root: Path) -> dict[str, Any]:
    progress = _progress(root)
    assert progress["stage"] == "plan_ready"
    _, plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
    return plan


def _thread_discussion(root: Path, thread_id: str) -> dict[str, Any]:
    progress = _progress(root)
    _, context = contract.artifact_payload(Path(str(progress["context_path"])), "review_context")
    return next(item for item in context["discussions"] if str(item["root_note_id"]) == thread_id)


def _thread_actions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        action
        for action in plan["publication_preview"]["actions"]
        if str(action.get("publication_id") or "").startswith("thread-")
    ]


def _send(action: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command_argv(str(action["command"])), capture_output=True, text=True, check=False
    )


def test_schema_diagnostics_identify_independent_fields() -> None:
    shared = json.loads(SHARED_SCHEMA.read_text(encoding="utf-8"))
    assert (
        contract.artifact_schema()["$defs"]["critic_receipt"] == shared["$defs"]["critic_receipt"]
    )
    issues = draft_module.schema_issues(
        {
            "type": "object",
            "required": ["a", "b"],
            "additionalProperties": False,
            "properties": {
                "a": {"type": "string", "minLength": 1},
                "b": {"type": "array", "items": {"type": "string"}},
            },
        },
        {"a": "", "b": [3], "unknown": True},
    )
    assert [item["path"] for item in issues] == ["$.a", "$.b[0]", "$.unknown"]


def test_one_draft_completes_remote_review_and_retains_real_thread_data(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures()
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo), locale="ru")
    assert started["status"] == "ok"
    assert started["critic_required"] is True
    root = Path(str(started["artifact_root"]))
    initial_progress = (root / "review-current.json").read_bytes()
    requests = fixture.request_count()
    invalid = draft_module.check_review(str(started["draft_path"]))
    assert invalid["status"] == "invalid"
    assert any(item["path"] == "$.run_id" for item in invalid["errors"])
    assert any(item["path"] == "$.content.summary" for item in invalid["errors"])
    assert fixture.request_count() == requests
    assert (root / "review-current.json").read_bytes() == initial_progress
    assert not (root / "artifacts" / "review_decision").exists()
    resumed = draft_module.resume_review(str(root))
    assert resumed["draft_path"] == started["draft_path"]
    assert fixture.request_count() == requests
    inspection = contract.read_json(Path(str(started["inspection_path"])), "inspection index")
    head_file = next(item for item in inspection["files"] if item["side"] == "head")
    assert Path(head_file["snapshot_path"]).read_text(encoding="utf-8") == (
        "base\nreviewed change\n"
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    _write(started["draft_path"], draft)
    checked = draft_module.check_review(str(started["draft_path"]))
    assert checked["status"] == "ok", _errors(checked)
    assert fixture.request_count() == requests
    assert (root / "review-current.json").read_bytes() == initial_progress
    assert not (root / "artifacts" / "review_plan").exists()
    finished = draft_module.finish_review(str(started["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    assert "undefined" not in finished["chat"]
    assert re.search(r"Оформление MR.*готово", finished["chat"])
    assert _progress(root)["stage"] == "plan_ready"
    assert draft_module.resume_review(str(root))["stage"] == "plan_ready"
    collected = fixture.request_count() - requests
    assert collected == 0, "finalization collects nothing; it is local-only"

    plan = _plan(root)
    decision = next(item for item in plan["thread_decisions"] if item["id"] == "42")
    assert decision["url"].endswith("#note_42")
    discussion = _thread_discussion(root, "42")
    assert discussion["root_position"]["new_path"] == "review.txt"
    assert discussion["root_position"]["new_line"] == 2
    assert "Retry needs an idempotency key" in discussion["notes"][0]["body"]
    assert "exact reviewed code" in decision["rationale"]
    actions = _thread_actions(plan)
    assert [item["operation"] for item in actions] == ["reply", "resolve"]
    assert all(item["publication_id"] == "thread-42" for item in actions)
    assert len(list((root / "artifacts" / "review_decision").iterdir())) == 1
    markdown = Path(str(finished["markdown_path"])).read_text(encoding="utf-8")
    assert "The exact reviewed code now handles this path." in markdown
    assert review_context.report_review(str(root))["status"] == "ok"
    assert plan["publication_preview"]["actions"][0]["command"] == actions[0]["command"]

    reply = _send(actions[0])
    assert reply.returncode == 0, reply.stderr
    after_reply = fixture.read_config()
    assert after_reply.get("resolved") is not True
    assert len(after_reply["publishedNotes"]) == 1
    resolve = _send(actions[1])
    assert resolve.returncode == 0, resolve.stderr
    after_resolve = fixture.read_config()
    assert after_resolve["resolved"] is True
    assert len(after_resolve["publishedNotes"]) == 1


def test_public_guided_cli_completes_the_same_contract(fixtures: Any) -> None:
    import os
    import sys

    fixture: ReviewFixture = fixtures({"resolved": True})
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    def run(*arguments: str) -> dict[str, Any]:
        execution = subprocess.run(
            [sys.executable, "-m", "reviewmatic", *arguments, "--json"],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        assert execution.returncode == 0, execution.stderr + execution.stdout
        value: dict[str, Any] = json.loads(execution.stdout)
        return value

    result = run("start-review", "--url", fixture.url, "--repo-root", str(fixture.repo))
    _write(result["draft_path"], complete_draft(_read(result["draft_path"]), result))
    assert run("check-review", "--draft", result["draft_path"])["status"] == "ok"
    finished = run("finish-review", "--draft", result["draft_path"])
    assert "runbook.md" in finished["chat"]
    assert "undefined" not in finished["chat"]


def test_fast_unchanged_and_incremental_modes_keep_critic_and_baseline_rules(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures({"resolved": True})
    first = draft_module.start_review(
        url=fixture.url, repo_root=str(fixture.repo), review_mode="fast"
    )
    fast = complete_draft(_read(first["draft_path"]), first)
    fast["critics"] = []
    _write(first["draft_path"], fast)
    assert "low-risk" in _errors(draft_module.check_review(str(first["draft_path"])))
    fast["low_risk"] = True
    _write(first["draft_path"], fast)
    assert draft_module.finish_review(str(first["draft_path"]))["status"] == "ok"
    same = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert same["mode"] == "unchanged"
    unchanged = complete_draft(_read(same["draft_path"]), same)
    unchanged["critics"] = []
    _write(same["draft_path"], unchanged)
    assert draft_module.finish_review(str(same["draft_path"]))["status"] == "ok"
    (fixture.repo / "review.txt").write_text("base\nreviewed change\nnew correction\n")
    fixture.git("commit", "-qam", "correction")
    fixture.config_path.write_text(
        json.dumps({**fixture.config, "headSha": fixture.git("rev-parse", "HEAD")})
    )
    changed = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert changed["mode"] == "incremental"
    assert isinstance(changed["critic_receipt_template"]["scope_digest"], str)
    incremental = complete_draft(_read(changed["draft_path"]), changed)
    _write(changed["draft_path"], incremental)
    checked = draft_module.check_review(str(changed["draft_path"]))
    assert checked["status"] == "ok", _errors(checked)
    assert draft_module.finish_review(str(changed["draft_path"]))["status"] == "ok"


def test_publication_errors_are_repairable_in_the_same_draft_before_a_decision(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures({"resolved": True})
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft = complete_draft(_read(result["draft_path"]), result)
    draft["findings"] = [
        {
            "id": "primary-1",
            "severity": "low",
            "summary": "The correction needs a line",
            "risk": "The old line remains.",
            "evidence": [f"The reviewed revision is {fixture.head_sha}."],
            "consequence": "The path remains incorrect.",
            "relation_to_change": "This path is changed.",
            "minimum_fix": "Correct the line.",
        }
    ]
    draft["dispositions"] = [
        {
            "id": "primary-1",
            "decision": "accept",
            "reason": "Confirmed in the exact diff.",
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        }
    ]
    draft["content"]["finding_publications"] = [
        {
            "finding_id": "primary-1",
            "type": "line",
            "path": "review.txt",
            "line": 2,
            "old_line": None,
            "body": "Correct the line.\n\n```suggestion\nbounded change\n```",
            "fix_mode": "suggestion",
            "patch": None,
        }
    ]
    draft["findings"][0]["summary"] += f" {fixture.head_sha[:8]}"
    _write(result["draft_path"], draft)
    invalid = draft_module.check_review(str(result["draft_path"]))
    assert invalid["status"] == "invalid"
    assert any(re.search(r"raw commit SHA", item["message"]) for item in invalid["errors"]), (
        _errors(invalid)
    )
    assert not (Path(str(result["artifact_root"])) / "artifacts" / "review_decision").exists()
    draft["findings"][0]["summary"] = "The correction needs a line"
    draft["findings"][0]["evidence"] = [
        "The exact changed line was inspected in the bound private evidence."
    ]
    _write(result["draft_path"], draft)
    repaired = draft_module.check_review(str(result["draft_path"]))
    assert repaired["status"] == "ok", _errors(repaired)
    draft["content"]["chat_assessment"]["change"] += f" {fixture.head_sha[:8]}"
    _write(result["draft_path"], draft)
    invalid_chat = draft_module.check_review(str(result["draft_path"]))
    assert invalid_chat["status"] == "invalid"
    assert any(
        item["path"] == "$.content.chat_assessment.change" for item in invalid_chat["errors"]
    )
    draft["content"]["chat_assessment"]["change"] = "The correction preserves the agreed behavior."
    _write(result["draft_path"], draft)
    completed = draft_module.finish_review(str(result["draft_path"]))
    assert completed["status"] == "ok"
    _, plan = contract.artifact_payload(Path(str(completed["artifact_path"])), "review_plan")
    assert plan["thread_decisions"][0]["outcome"] == "no_publication"
    assert _thread_actions(plan) == []
    discussion = _thread_discussion(Path(str(result["artifact_root"])), "42")
    assert "Retry needs an idempotency key" in discussion["notes"][0]["body"]
    assert plan["thread_decisions"][0]["proposed_response"] is None


def test_chosen_critic_count_independent_identities_and_local_finalization(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures()
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft = complete_draft(_read(result["draft_path"]), result)
    draft["critic_count"] = 2
    _write(result["draft_path"], draft)
    assert "critic_count" in _errors(draft_module.check_review(str(result["draft_path"])))
    draft["critics"].append({**draft["critics"][0], "run_id": "critic-2", "session_id": "child-2"})
    candidate = {
        "severity": "low",
        "summary": "A related path needs separate documentation",
        "risk": "Readers can miss the separate policy.",
        "evidence": ["The existing related behavior was inspected."],
        "consequence": "Operators can select an unsuitable policy.",
        "relation_to_change": "The related policy is outside this change.",
        "minimum_fix": "Document the policy separately.",
    }
    draft["critics"][0]["findings"] = [{**candidate, "id": "critic-a-policy"}]
    draft["critics"][1]["findings"] = [
        {
            **candidate,
            "id": "critic-b-policy",
            "summary": "A different related path needs separate documentation",
        }
    ]
    draft["dispositions"] = [
        {
            "id": finding["id"],
            "decision": "reject",
            "reason": "The policy is outside this MR and remains separately tracked.",
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        }
        for receipt in draft["critics"]
        for finding in receipt["findings"]
    ]
    _write(result["draft_path"], draft)
    assert draft_module.check_review(str(result["draft_path"]))["status"] == "ok"
    draft["critics"][1]["session_id"] = draft["session_id"]
    _write(result["draft_path"], draft)
    assert "identity" in _errors(draft_module.check_review(str(result["draft_path"])))
    draft["critics"][1]["session_id"] = "child-2"
    _write(result["draft_path"], draft)
    fixture.config_path.write_text(
        json.dumps({**fixture.config, "noteBody": "The conversation changed after inspection"})
    )
    requests = fixture.request_count()
    # Finalization is local: even when GitLab changed after inspection, the
    # plan stays bound to the reviewed evidence and no GitLab request runs.
    final = draft_module.finish_review(str(result["draft_path"]))
    assert final["status"] == "ok", json.dumps(final)
    assert fixture.request_count() == requests
    markdown = Path(str(final["markdown_path"])).read_text(encoding="utf-8")
    assert "current_head_json=$(glab api --hostname gitlab.example --method GET" in markdown
    assert "current_head=$(printf '%s' \"$current_head_json\" | jq -er" in markdown
    fixture.config_path.write_text(json.dumps(fixture.config))
    receipt_path = _progress(Path(str(result["artifact_root"])))["critic_receipt_path"]
    _, receipt = contract.artifact_payload(Path(str(receipt_path)), "critic_receipt")
    assert [item["session_id"] for item in receipt["contributors"]] == [
        "child-session",
        "child-2",
    ]
    assert [item["id"] for item in receipt["findings"]] == ["critic-a-policy", "critic-b-policy"]
    _, plan = contract.artifact_payload(Path(str(final["artifact_path"])), "review_plan")
    assert len(plan["rejected_candidates"]) == 2
    assert all("review.txt" in item["paths"] for item in plan["rejected_candidates"])
