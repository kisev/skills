"""Review contract regressions ported from ``review-contract-regressions.test.mjs``.

Every scenario drives the real draft, context, and publication code against the
fake ``glab`` from ``helpers.review_fixture``. UI-only assertions from the
historical TypeScript suite are replaced with direct artifact and runbook checks:

* ``loadPlan`` reads the finalized plan artifact through the progress pointer
  (``PlanView``), exactly like ``test_repair.py``.
* ``planItems`` assertions read the underlying publication preview.
* ``amendBody`` is replaced by the draft-level ``routing_response`` field it
  writes, so the editable-reply contract is still exercised through
  ``check-review``, ``finish-review`` and ``repair-review``.
* ``sendItem`` is replaced by running the plan's own publication command, or
  the annotated shell block of the plan Markdown, against the fake ``glab``.

``test_contract_validators.py`` carries the validator-level regressions.
"""

from __future__ import annotations

import copy
import json
import os
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

SAFE_PATCH = (
    "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n"
    "@@ -1,2 +1,2 @@\n base\n-reviewed change\n+keyed retry\n"
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


def finding(finding_id: str, severity: str = "high") -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "summary": "Retry repeats a write",
        "risk": "A retry repeats the external operation.",
        "evidence": ["The exact retry path has no request key."],
        "consequence": "A caller can receive a duplicate charge.",
        "relation_to_change": "The changed retry path reaches this write.",
        "minimum_fix": "Reuse the request key.",
    }


def disposition(disposition_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": disposition_id,
        "decision": "accept",
        "reason": "Verified against the exact head.",
        "dependencies": {
            "paths": ["review.txt"],
            "thread_ids": ["42"],
            "metadata_fields": [],
            "ci": False,
        },
        **extra,
    }


def read(path: Any) -> dict[str, Any]:
    return contract.read_json(Path(str(path)), "review state")


def write(path: Any, value: dict[str, Any]) -> None:
    contract.write_json(Path(str(path)), value)


class PlanView:
    """The finalized plan behind the progress pointer (the TUI ``loadPlan`` result)."""

    def __init__(self, root: Any) -> None:
        root_path = Path(str(root))
        progress = review_context.load_progress(root_path)
        assert progress is not None
        if progress["stage"] != "plan_ready":
            baseline = contract.read_json(root_path / review_context.BASELINE_NAME, "baseline")
            progress = {**progress, "plan_path": baseline["plan_path"]}
        _, self.plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
        self.markdown: str = self.plan["markdown"]

    def actions(self, kind: str) -> list[dict[str, Any]]:
        return [
            action
            for action in self.plan["publication_preview"]["actions"]
            if action["kind"] == kind
        ]

    def bodies(self) -> list[dict[str, Any]]:
        return list(self.plan["publication_preview"]["body_files"])

    def shell_blocks(self) -> list[str]:
        return re.findall(r"```shell\n([\s\S]*?)\n```", self.markdown)


def prepared(
    fixtures: Any, overrides: dict[str, Any] | None = None
) -> tuple[ReviewFixture, dict[str, Any], dict[str, Any]]:
    fixture: ReviewFixture = fixtures(overrides)
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    return fixture, result, complete_draft(read(result["draft_path"]), result)


def link_defect(draft: dict[str, Any]) -> None:
    thread = draft["content"]["thread_decisions"][0]
    thread.update(
        {
            "assessment": "accepted",
            "severity": "high",
            "outcome": "reopen" if thread["state"] == "resolved" else "reply",
            "rationale": "The retry still repeats a write on the exact head.",
            "proposed_response": "Reuse the key.\n\n```suggestion\nkeyed retry\n```",
            "fix_mode": "suggestion",
        }
    )
    draft["content"]["finding_publications"] = [
        {
            "finding_id": "critic-retry",
            "type": "existing_thread",
            "thread_id": "42",
            "path": None,
            "line": None,
            "old_line": None,
            "body": "The existing discussion owns this fix.",
            "fix_mode": "not_required",
            "patch": None,
        }
    ]


def errors_of(checked: dict[str, Any]) -> str:
    return json.dumps(checked.get("errors"))


def run_block(block: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", block], capture_output=True, text=True, env=os.environ, check=False
    )


class LowLevel:
    def __init__(self, fixtures: Any, overrides: dict[str, Any] | None = None) -> None:
        self.fixture, self.result, self.draft = prepared(fixtures, overrides)
        self.root = Path(str(self.result["artifact_root"]))
        self.progress = read(self.root / "review-current.json")
        _, receipt_digest = contract.write_artifact(
            self.root, "critic_receipt", self.draft["critics"][0]
        )
        threads = [
            {"id": f"thread:{thread['id']}"}
            for thread in self.draft["content"]["thread_decisions"]
            if thread["state"] == "open"
        ]
        self.decision: dict[str, Any] = {
            "schema": "portable-gitlab/review-decision/v2",
            "evidence_digest": self.draft["evidence_digest"],
            "context_digest": self.draft["context_digest"],
            "finalize_digest": "0" * 64,
            "critic_receipt_digest": receipt_digest,
            "mode": self.result["mode"],
            "external_mutations": False,
            "run_id": self.draft["run_id"],
            "session_id": self.draft["session_id"],
            "low_risk": False,
            "verdict": "ready",
            "findings": [],
            "accepted_findings": [],
            "critic_findings": [],
            "unresolved_threads": threads,
            "responses": [
                {
                    "id": thread["id"],
                    "decision": "accept",
                    "reason": "The complete discussion was inspected.",
                }
                for thread in threads
            ],
            "blocking_findings": False,
            "blocking_finding_ids": [],
            "blocking_thread_ids": [],
            "ci_job_assessments": [],
            "owner_decision_reasons": [],
        }
        self.content: dict[str, Any] = {
            **copy.deepcopy(self.draft["content"]),
            "findings": [],
            "rejected_candidates": [],
        }
        self.content_path = self.fixture.tmp / "low-level-content.json"

    def scaffold(self, *, dry_run: bool = False) -> dict[str, object]:
        write(self.content_path, self.content)
        decision_path, _ = contract.write_artifact(self.root, "review_decision", self.decision)
        return review_context.scaffold_review(
            str(self.result["evidence_path"]),
            str(self.result["context_path"]),
            str(decision_path),
            str(self.content_path),
            {
                "decision": copy.deepcopy(self.decision),
                "content": copy.deepcopy(self.content),
                "dry_run": True,
                "freshness_checked": True,
            }
            if dry_run
            else None,
        )


def test_low_level_scaffold_derives_omitted_thread_blockers_and_rejects_contradictory_verdicts(
    fixtures: Any,
) -> None:
    low = LowLevel(fixtures)
    low.content["thread_decisions"][0].update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "rationale": "The exact retry path still duplicates writes.",
            "fix_mode": "suggestion",
            "proposed_response": "Reuse the key.\n\n```suggestion\nkeyed retry\n```",
        }
    )
    del low.decision["blocking_thread_ids"]
    with pytest.raises(contract.WorkflowError, match="verdict does not match"):
        low.scaffold()
    low.decision["blocking_thread_ids"] = []
    with pytest.raises(contract.WorkflowError, match="blocking_thread_ids do not match"):
        low.scaffold()
    del low.decision["blocking_thread_ids"]
    low.decision["verdict"] = "not_ready"
    accepted = low.scaffold(dry_run=True)
    assert accepted["status"] == "ok"
    payload: dict[str, Any] = accepted["payload"]  # type: ignore[assignment]
    assert re.search(r"still duplicates writes", payload["summary"])
    assert re.search(r"Blocks merge", payload["markdown"])
    assert "No blocking findings" not in payload["summary"]
    assert read(low.root / "review-current.json") == low.progress
    low.content["thread_decisions"][0]["severity"] = "low"
    low.decision["verdict"] = "ready"
    assert low.scaffold(dry_run=True)["status"] == "ok"


@pytest.mark.parametrize("owner", ["finding", "thread"])
def test_low_level_scaffold_rejects_an_available_safe_suggestion_for_patch(
    fixtures: Any, owner: str
) -> None:
    low = LowLevel(fixtures, {"resolved": True})
    low.decision["verdict"] = "not_ready"
    fix = {
        "fix_mode": "patch",
        "patch": SAFE_PATCH,
        "patch_reason": "Keep the complete correction together.",
    }
    if owner == "finding":
        candidate = finding("primary-retry")
        low.decision["findings"] = [candidate]
        low.decision["accepted_findings"] = [candidate]
        low.decision["blocking_findings"] = True
        low.decision["blocking_finding_ids"] = [candidate["id"]]
        low.decision["responses"] = [
            {"id": candidate["id"], "decision": "accept", "reason": "Confirmed on the exact head."}
        ]
        low.content["findings"] = [candidate]
        low.content["finding_publications"] = [
            {
                **fix,
                "finding_id": candidate["id"],
                "type": "line",
                "path": "review.txt",
                "line": 2,
                "old_line": None,
                "body": "Reuse the request key.",
            }
        ]
    else:
        low.decision["blocking_thread_ids"] = ["42"]
        low.content["thread_decisions"][0].update(
            {
                **fix,
                "severity": "medium",
                "assessment": "accepted",
                "outcome": "reopen",
                "proposed_response": "Reuse the request key.",
            }
        )
    with pytest.raises(contract.WorkflowError, match="safe bounded suggestion is available"):
        low.scaffold()
    assert read(low.root / "review-current.json") == low.progress


def test_an_authors_local_patch_remains_valid_even_when_a_bounded_suggestion_exists(
    fixtures: Any,
) -> None:
    _fixture, result, draft = prepared(fixtures, {"resolved": True, "mrAuthor": "reviewer"})
    draft["findings"] = [finding("primary-retry")]
    draft["dispositions"] = [disposition("primary-retry")]
    draft["content"]["finding_publications"] = [
        {
            "finding_id": "primary-retry",
            "type": "local_fix",
            "path": None,
            "line": None,
            "old_line": None,
            "body": "Reuse the request key.",
            "fix_mode": "patch",
            "patch": SAFE_PATCH,
            "patch_reason": "The author applies a validated local patch.",
        }
    ]
    write(result["draft_path"], draft)
    finished = draft_module.finish_review(str(result["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    view = PlanView(result["artifact_root"])
    assert view.plan["role"] == "author"
    assert view.actions("finding") == []


def test_routing_only_replies_keep_positioned_suggestions_and_survive_repair(
    fixtures: Any,
) -> None:
    fixture, result, draft = prepared(fixtures, {"positionHead": "a" * 40})
    thread = draft["content"]["thread_decisions"][0]
    thread.update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "fix_mode": "suggestion",
            "proposed_response": "The existing request key must cover this retry.",
            "suggestions": [
                {
                    "path": "review.txt",
                    "line": 2,
                    "body": "Reuse the request key.\n\n```suggestion\nkeyed retry\n```",
                }
            ],
        }
    )
    write(result["draft_path"], draft)
    assert draft_module.finish_review(str(result["draft_path"]))["status"] == "ok"
    before = PlanView(result["artifact_root"])
    requests = fixture.request_count()
    # The TUI ``amendBody`` edit writes exactly this draft-level field.
    routing = "The correction is proposed on the current lines in a separate thread."
    edited_draft = draft_module.repair_review(str(result["artifact_root"]), "presentation")
    source = read(edited_draft["draft_path"])
    source_thread = source["content"]["thread_decisions"][0]
    assert source_thread["suggestions"] == before.plan["thread_decisions"][0]["suggestions"]
    source_thread["routing_response"] = routing
    source["repair"]["rationale"] = (
        "Preserve the edited routing reply and the exact suggestion result."
    )
    source["repair"]["checks"] = ["Compared the routing reply and unchanged suggestion bytes."]
    write(edited_draft["draft_path"], source)
    finished = draft_module.finish_review(str(edited_draft["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    after = PlanView(result["artifact_root"])
    assert (
        after.plan["thread_decisions"][0]["suggestions"]
        == before.plan["thread_decisions"][0]["suggestions"]
    )
    content_thread = after.plan["review_source"]["content"]["thread_decisions"][0]
    assert content_thread["proposed_response"] == thread["proposed_response"]
    assert re.search(r"separate thread", content_thread["routing_response"])
    assert re.search(
        r"separate thread",
        next(b for b in after.bodies() if b["publication_id"] == "thread-42")["content"],
    )
    assert re.search(
        r"correction is proposed on the current lines in a separate thread", after.markdown
    )
    assert after.plan["thread_decisions"][0]["suggestions"] == thread["suggestions"]
    assert fixture.request_count() == requests

    invalid = draft_module.repair_review(str(result["artifact_root"]), "presentation")
    broken = read(invalid["draft_path"])
    broken["content"]["thread_decisions"][0]["routing_response"] = (
        "```suggestion\nunverified replacement\n```"
    )
    broken["repair"]["rationale"] = "A routing reply must stay prose."
    broken["repair"]["checks"] = ["Compared the routing reply."]
    write(invalid["draft_path"], broken)
    rejected = draft_module.check_review(str(invalid["draft_path"]))
    assert rejected["status"] == "invalid"
    assert "routing_response requires grouped suggestions and prose only" in errors_of(rejected)
    assert fixture.request_count() == requests


def test_a_later_user_proposed_patch_and_prior_confirmation_use_the_complete_chronology() -> None:
    context = {"current_user_username": "reviewer"}
    source = {
        "root_note_id": 42,
        "notes": [
            {"id": 42, "author": {"username": "reviewer"}, "body": "Retries duplicate writes."},
            {
                "id": 43,
                "author": {"username": "reviewer"},
                "body": "```diff\n-keyless\n+keyed\n```",
            },
            {"id": 44, "author": {"username": "maintainer"}, "body": "Applied and closed."},
            {
                "id": 45,
                "author": {"username": "reviewer"},
                "body": "Checked, the retry reuses the key.",
            },
        ],
    }
    decision: dict[str, Any] = {
        "assessment": "fixed",
        "outcome": "no_publication",
        "user_confirmation": {"status": "required", "evidence_note_ids": []},
    }
    with pytest.raises(contract.WorkflowError, match="still needs their confirmation"):
        review_context.validate_user_confirmation(decision, source, context)
    decision["user_confirmation"] = {"status": "confirmed", "evidence_note_ids": [45]}
    review_context.validate_user_confirmation(decision, source, context)
    decision["outcome"] = "reply"
    with pytest.raises(contract.WorkflowError, match="already confirmed fix"):
        review_context.validate_user_confirmation(decision, source, context)
    decision["user_confirmation"]["new_circumstances"] = (
        "A new failure path was verified after the confirmation."
    )
    review_context.validate_user_confirmation(decision, source, context)
    decision["user_confirmation"]["evidence_note_ids"] = [44]
    with pytest.raises(contract.WorkflowError, match="user's later confirmation"):
        review_context.validate_user_confirmation(decision, source, context)


def test_verdict_effective_severity_and_existing_thread_dedup_preserve_the_original_receipt(
    fixtures: Any,
) -> None:
    _fixture, result, draft = prepared(fixtures, {"resolved": True})
    draft["critics"][0]["findings"] = [finding("critic-retry")]
    draft["findings"] = [finding("primary-retry")]
    draft["dispositions"] = [
        disposition(
            "primary-retry",
            decision="reject",
            duplicate_of="critic-retry",
            reason="Same defect as the accepted critic finding.",
        ),
        disposition(
            "critic-retry",
            severity_override={
                "original_severity": "high",
                "severity": "medium",
                "reason": "Only callers enabling retry are affected.",
            },
        ),
    ]
    link_defect(draft)
    receipt = copy.deepcopy(draft["critics"][0])
    draft["content"]["summary"] = "This deliberately stale prose says ready to merge."
    write(result["draft_path"], draft)
    checked = draft_module.check_review(str(result["draft_path"]))
    assert checked["status"] == "ok", errors_of(checked)
    finished = draft_module.finish_review(str(result["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    _, plan = contract.artifact_payload(Path(str(finished["artifact_path"])), "review_plan")
    assert plan["verdict"] == "not_ready"
    assert plan["findings"][0]["severity"] == "medium"
    assert plan["thread_decisions"][0]["severity"] == "medium"
    assert "deliberately stale" not in plan["summary"]
    assert plan["review_source"]["critics"][0] == receipt
    actions = plan["publication_preview"]["actions"]
    assert len([a for a in actions if a["kind"] == "finding"]) == 0
    assert [a["operation"] for a in actions if a["kind"] == "thread"] == ["reply", "reopen"]
    markdown: str = plan["markdown"]
    assert markdown.index("Merge impact") < markdown.index("## MR metadata")
    assert markdown.index("Architecture assessment") < markdown.index("## MR metadata")
    assert markdown.index("MR contribution") < markdown.index("## MR metadata")
    assert re.search(r"1 blocking findings", markdown)
    assert re.search(r"Blocks merge", markdown)
    assert re.search(
        r"# Publish reply:\n.* &&\n# After successful publication, reopen the thread:\n", markdown
    )


def test_a_users_suggestion_closed_by_somebody_else_still_requires_their_confirmation(
    fixtures: Any,
) -> None:
    fixture, result, draft = prepared(
        fixtures,
        {
            "resolved": True,
            "rootAuthor": "reviewer",
            "resolvedBy": {"username": "maintainer"},
            "noteBody": "The retry duplicates writes.\n\n```suggestion\nkeyed retry\n```",
            "replies": [
                {
                    "id": 43,
                    "system": False,
                    "author": {"username": "maintainer"},
                    "body": "Applied and closing.",
                }
            ],
        },
    )
    thread = draft["content"]["thread_decisions"][0]
    assert thread["user_confirmation"]["status"] == "required"
    write(result["draft_path"], draft)
    checked = draft_module.check_review(str(result["draft_path"]))
    assert any(
        error["path"].endswith(".user_confirmation")
        and re.search(r"another participant resolved", error["message"])
        for error in checked["errors"]
    )
    thread["outcome"] = "reply"
    thread["proposed_response"] = "Thanks, the exact retry path now reuses the key."
    write(result["draft_path"], draft)
    checked = draft_module.check_review(str(result["draft_path"]))
    assert checked["status"] == "ok", errors_of(checked)
    assert draft_module.finish_review(str(result["draft_path"]))["status"] == "ok"
    fixture.config_path.write_text(
        json.dumps(
            {
                **fixture.config,
                "replies": [
                    *fixture.config["replies"],
                    {
                        "id": 44,
                        "system": False,
                        "author": {"username": "reviewer"},
                        "body": "Checked the correction, thanks.",
                    },
                ],
            }
        )
    )
    following = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    confirmed = complete_draft(read(following["draft_path"]), following)
    confirmed["content"]["thread_decisions"][0]["user_confirmation"] = {
        "status": "confirmed",
        "evidence_note_ids": [44],
    }
    write(following["draft_path"], confirmed)
    checked = draft_module.check_review(str(following["draft_path"]))
    assert checked["status"] == "ok", errors_of(checked)
    assert draft_module.finish_review(str(following["draft_path"]))["status"] == "ok"
    view = PlanView(following["artifact_root"])
    assert len(view.actions("thread")) == 0
    assert re.search(r"exact reviewed code already addresses", view.markdown)


def test_grouped_suggestions_use_the_original_position_or_link_a_new_positioned_thread(
    fixtures: Any,
) -> None:
    _fixture, result, draft = prepared(fixtures)
    thread = draft["content"]["thread_decisions"][0]
    thread.update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "fix_mode": "suggestion",
            "proposed_response": "Shared explanation must not be repeated.",
            "suggestions": [
                {
                    "path": "review.txt",
                    "line": 2,
                    "body": "Reuse the key.\n\n```suggestion\nkeyed retry\n```",
                }
            ],
        }
    )
    write(result["draft_path"], draft)
    assert draft_module.finish_review(str(result["draft_path"]))["status"] == "ok"
    view = PlanView(result["artifact_root"])
    assert view.plan["verdict"] == "not_ready", (
        "a defect cannot disappear just because it belongs to a thread"
    )
    assert [a["operation"] for a in view.actions("thread")] == ["reply"]
    assert re.search(r"```suggestion", view.bodies()[0]["content"])

    other_fixture, _other_result, _other_draft = prepared(fixtures, {"positionHead": "a" * 40})
    other = draft_module.start_review(url=other_fixture.url, repo_root=str(other_fixture.repo))
    stale_position = complete_draft(read(other["draft_path"]), other)
    stale_position["content"]["thread_decisions"][0].update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "fix_mode": "suggestion",
            "proposed_response": "Shared explanation must not be repeated.",
            "suggestions": thread["suggestions"],
        }
    )
    write(other["draft_path"], stale_position)
    finished = draft_module.finish_review(str(other["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    bodies = PlanView(other["artifact_root"]).bodies()
    shared = next(body for body in bodies if body["publication_id"] == "thread-42")
    assert "Shared explanation" not in shared["content"]
    part = next(body for body in bodies if "@suggestion" in body["publication_id"])
    assert re.search(r"Original thread: \[42\]\(https:", part["content"])


def test_input_package_has_the_exact_draft_schema_and_examples_and_validation_gathers_independent_errors(
    fixtures: Any,
) -> None:
    fixture, result, draft = prepared(fixtures)
    schema = read(result["draft_schema_path"])
    with pytest.raises(contract.WorkflowError, match="valid only with type=existing_thread"):
        review_context.validate_finding_publications(
            [{**result["input_examples"]["suggestion"], "thread_id": "42"}], {"primary-retry"}
        )
    assert schema["$defs"] == contract.artifact_schema()["$defs"]
    assert draft_module.schema_issues(draft_module.DRAFT_SCHEMA, draft) == []
    properties = draft_module.DRAFT_SCHEMA["properties"]
    for name, value in result["input_examples"].items():
        if name == "disposition":
            shape = properties["dispositions"]["items"]
        elif name == "severity_override":
            shape = properties["dispositions"]["items"]["properties"]["severity_override"]
        elif name == "follow_up":
            shape = properties["content"]["properties"]["recommended_issues"]["items"]
        elif name == "thread_decision":
            shape = properties["content"]["properties"]["thread_decisions"]["items"]
        else:
            shape = properties["content"]["properties"]["finding_publications"]["items"]
        prepared_thread = next(
            (
                item
                for item in draft["content"]["thread_decisions"]
                if item["id"] == value.get("id")
            ),
            draft["content"]["thread_decisions"][0],
        )
        candidate = (
            {**prepared_thread, **value, "id": prepared_thread["id"]}
            if name == "thread_decision"
            else value
        )
        assert draft_module.schema_issues(shape, candidate) == [], name
    write(result["draft_path"], draft)
    count = fixture.request_count()
    assert draft_module.check_review(str(result["draft_path"]))["status"] == "ok"
    inspection = Path(str(result["inspection_path"]))
    mtime = inspection.stat().st_mtime_ns
    resumed = draft_module.resume_review(str(result["artifact_root"]))
    assert resumed["inspection_path"] == result["inspection_path"]
    assert inspection.stat().st_mtime_ns == mtime
    assert fixture.request_count() == count

    draft["content"]["summary"] = ""
    draft["critics"][0]["findings"] = [finding("critic-retry")]
    draft["critics"][0]["findings"][0]["evidence"] = [f"Head {fixture.head_sha}"]
    draft["content"]["finding_publications"] = [
        {
            "finding_id": "critic-retry",
            "type": "line",
            "path": "review.txt",
            "line": 2,
            "old_line": None,
            "body": "Correct.\n\n```suggestion:-4+0\nfixed\n```",
            "fix_mode": "suggestion",
            "patch": None,
        }
    ]
    write(result["draft_path"], draft)
    invalid = draft_module.check_review(str(result["draft_path"]))
    assert invalid["status"] == "invalid"
    for path in (
        "$.content.summary",
        "$.critics[0].findings[0].evidence[0]",
        "$.content.finding_publications[0].body",
    ):
        assert any(error["path"] == path for error in invalid["errors"]), errors_of(invalid)
    assert fixture.request_count() == count
    draft["content"]["thread_decisions"][0].update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "fix_mode": "suggestion",
            "proposed_response": "The parts are separate corrections.",
            "split_rationale": "The changes have independent consumers.",
            "suggestions": [
                {"path": "review.txt", "line": 1, "body": "```suggestion:-2+0\nfixed\n```"},
                {"path": "review.txt", "line": 2, "body": "```suggestion:-0+4\nfixed\n```"},
            ],
        }
    )
    write(result["draft_path"], draft)
    invalid_parts = draft_module.check_review(str(result["draft_path"]))
    for index in (0, 1):
        assert any(
            error["path"] == f"$.content.thread_decisions[0].suggestions[{index}].body"
            and re.search(r"expected a non-overlapping range within", error["message"])
            for error in invalid_parts["errors"]
        ), errors_of(invalid_parts)
    assert fixture.request_count() == count
    task = result["critic_task"]
    assert re.search(r"Launch immediately.*background.*alongside", task["instructions"])
    assert re.search(r"never manually transcribed", task["instructions"])
    assert task["launch_when"] == "evidence_ready"
    assert task["preferred_execution"] == "native_background"
    assert task["join_before"] == "check-review"
    assert task["draft_schema_path"] == result["draft_schema_path"]


def test_follow_ups_are_concise_proposals_not_issue_publication_or_mandatory_mr_fixes(
    fixtures: Any,
) -> None:
    _fixture, result, draft = prepared(fixtures, {"resolved": True})
    draft["content"]["recommended_issues"] = [result["input_examples"]["follow_up"]]
    write(result["draft_path"], draft)
    finished = draft_module.finish_review(str(result["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    view = PlanView(result["artifact_root"])
    assert view.plan["verdict"] == "ready"
    assert not view.actions("issue")
    assert re.search(r"Non-blocking operational improvement", view.markdown)
    assert "description=@" not in view.markdown


def test_patch_reasons_precede_thread_patches_and_an_available_safe_suggestion_rejects_fallback(
    fixtures: Any,
) -> None:
    _fixture, result, draft = prepared(fixtures)
    thread = draft["content"]["thread_decisions"][0]
    thread.update(
        {
            "assessment": "accepted",
            "severity": "medium",
            "outcome": "reply",
            "fix_mode": "patch",
            "proposed_response": "Add the missing policy file.",
            "patch_reason": "A new file has no existing suggestion anchor.",
            "patch": (
                "diff --git a/policy.txt b/policy.txt\nnew file mode 100644\n--- /dev/null\n"
                "+++ b/policy.txt\n@@ -0,0 +1 @@\n+keyed retries\n"
            ),
        }
    )
    write(result["draft_path"], draft)
    finished = draft_module.finish_review(str(result["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    body = PlanView(result["artifact_root"]).bodies()[0]["content"]
    assert body.index(thread["patch_reason"]) < body.index("git apply")
    thread["patch"] = SAFE_PATCH
    write(result["draft_path"], draft)
    assert any(
        error["path"].endswith(".patch_reason")
        and re.search(r"safe bounded suggestion", error["message"])
        for error in draft_module.check_review(str(result["draft_path"]))["errors"]
    )


@pytest.mark.parametrize("completed", [True, False])
def test_ordinary_comment_uses_returned_discussion_identity(fixtures: Any, completed: bool) -> None:
    fixture, result, draft = prepared(fixtures, {"plain": True, "returnedResolvable": True})
    if not completed:
        draft["content"]["thread_decisions"][0].update(
            {
                "assessment": "question",
                "rationale": "The policy question is still unanswered.",
                "proposed_response": "Does this policy cover retries?",
            }
        )
    write(result["draft_path"], draft)
    assert draft_module.finish_review(str(result["draft_path"]))["status"] == "ok"
    view = PlanView(result["artifact_root"])
    thread_actions = view.actions("thread")
    assert len(thread_actions) == 1
    # The TUI ``sendItem`` posts this action and resolves from the returned
    # discussion identity; the plan's annotated shell block carries that logic.
    sent = subprocess.run(
        command_argv(str(thread_actions[0]["command"])),
        capture_output=True,
        text=True,
        env=os.environ,
        check=False,
    )
    assert sent.returncode == 0, sent.stderr
    assert len(fixture.read_config()["publishedNotes"]) == 1
    assert fixture.read_config().get("createdResolved") is None
    fixture.config_path.write_text(json.dumps(fixture.config))
    block = next(item for item in view.shell_blocks() if "Publish reply:" in item)
    if not completed:
        assert "response=$(" not in block
        assert run_block(block).returncode == 0
        assert fixture.read_config().get("createdResolved") is None
        return
    assert re.search(r"discussion_id=.*jq", block)
    run = run_block(block)
    assert run.returncode == 0, run.stderr
    assert fixture.read_config().get("createdResolved") is True
    fixture.config_path.write_text(
        json.dumps({**fixture.config, "mutationError": "Synthetic POST failure"})
    )
    failed = run_block(block)
    assert failed.returncode != 0
    assert fixture.read_config().get("createdResolved") is None


def test_thread_state_changes_follow_a_successful_reply_in_the_same_annotated_shell_block(
    fixtures: Any,
) -> None:
    fixture, result, draft = prepared(fixtures)
    write(result["draft_path"], draft)
    assert draft_module.finish_review(str(result["draft_path"]))["status"] == "ok"
    view = PlanView(result["artifact_root"])
    assert [a["operation"] for a in view.actions("thread")] == ["reply", "resolve"]
    block = next(item for item in view.shell_blocks() if "/discussion-42/notes" in item)
    assert re.search(
        r"# Publish reply:\n.* &&\n# After successful publication, resolve the thread:\n", block
    )
    fixture.config_path.write_text(
        json.dumps({**fixture.config, "mutationError": "Synthetic POST failure"})
    )
    failed = run_block(block)
    assert failed.returncode != 0
    assert fixture.read_config().get("resolved") is not True
    fixture.config_path.write_text(json.dumps(fixture.config))
    sent = run_block(block)
    assert sent.returncode == 0, sent.stderr
    assert fixture.read_config().get("resolved") is True
