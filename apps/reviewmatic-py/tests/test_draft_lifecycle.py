"""Draft lifecycle end-to-end against the fake glab, from draft.test.mjs and
draft-input.test.mjs.

Covers: start-review (Russian locale), check-review invalid on the fresh
draft, resume-review identity, the completed-draft contract, check/finish
with zero extra GitLab requests, the recorded decision artifact, and the
record-input/record-critic mechanical contracts (addressed diagnostics,
missing package binding).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Any:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _complete_draft(draft: dict[str, Any], started: dict[str, Any]) -> dict[str, Any]:
    """The completeDraft helper from the TS fixture, in Python."""
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Bound the retry write behind an idempotency key without changing callers.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path; the remark is assessed directly."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(
        str(started["draft_path"]), str(started["context_package"]["template_path"])
    )
    recorded = contract.read_json(Path(str(started["draft_path"])), "review draft")
    draft["context_package_path"] = recorded["context_package_path"]
    draft["context_package_digest"] = recorded["context_package_digest"]
    draft["question_verifications"] = []
    draft["run_id"] = "primary-run"
    draft["session_id"] = "primary-session"
    draft["critics"] = [
        {
            **started["critic_receipt_template"],
            "run_id": "critic-run",
            "session_id": "child-session",
            "findings": [],
        },
    ]
    content = cast("dict[str, Any]", draft["content"])
    content["summary"] = "The bounded change meets the agreed contract."
    content["architecture_assessment"] = "Existing ownership is preserved."
    content["chat_assessment"] = {
        "necessity": {"status": "supported", "rationale": "The existing timeout is unbounded."},
        "relevance": {"status": "current", "rationale": "The current runner uses this path."},
        "change": "Bound the check.",
    }
    content["semver_impact"] = "patch"
    content["semver_rationale"] = "Backward-compatible correction."
    content["checks"] = ["Inspected the exact committed diff; external tests were not run."]
    for value in cast("dict[str, dict[str, Any]]", content["mr_metadata_assessment"]).values():
        value["status"] = "ok"
        value["rationale"] = "The observed metadata is sufficient."
    for value in cast("list[dict[str, Any]]", content["label_assessments"]):
        value["status"] = "applicable" if value["name"] == "semver::patch" else "inapplicable"
        value["rationale"] = "Matches the assessed patch contribution."
    semver = cast("dict[str, Any]", content["semver_assessment"])
    semver["policy"] = "No publication configuration is available."
    semver["sources"] = ["Fixture repository and empty release catalog"]
    semver["fallback_reason"] = "No published release can be established."
    for thread in cast("list[dict[str, Any]]", content["thread_decisions"]):
        thread["assessment"] = "fixed"
        thread["rationale"] = "The exact reviewed code already addresses the remark."
        thread["outcome"] = (
            "no_publication"
            if thread["state"] == "resolved"
            else "reply"
            if thread["state"] == "plain"
            else "resolve"
        )
        thread["proposed_response"] = (
            None
            if thread["state"] == "resolved"
            else "The exact reviewed code now handles this path."
        )
    assert content["finding_publications"] == []
    return draft


def _progress(root: Path) -> dict[str, Any]:
    from reviewmatic import context

    progress = context.load_progress(root)
    assert progress is not None
    return progress


def test_draft_lifecycle_completes_a_remote_review(fixture: ReviewFixture) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo), locale="ru")
    assert started["status"] == "ok"
    assert started["critic_required"] is True
    root = Path(str(started["artifact_root"]))
    initial_progress = (root / "review-current.json").read_bytes()
    requests = fixture.request_count()

    invalid = draft_module.check_review(str(started["draft_path"]))
    assert invalid["status"] == "invalid"
    paths = {item["path"] for item in invalid["errors"]}
    assert "$.run_id" in paths
    assert "$.content.summary" in paths
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

    draft = _complete_draft(
        contract.read_json(Path(str(started["draft_path"])), "review draft"), started
    )
    contract.write_json(Path(str(started["draft_path"])), draft)
    checked = draft_module.check_review(str(started["draft_path"]))
    assert checked["status"] == "ok", json.dumps(checked["errors"])
    assert fixture.request_count() == requests
    assert (root / "review-current.json").read_bytes() == initial_progress
    assert not (root / "artifacts" / "review_plan").exists()

    finished = draft_module.finish_review(str(started["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    assert "undefined" not in finished["chat"]
    assert "готово" in finished["chat"]
    assert _progress(root)["stage"] == "plan_ready"
    assert draft_module.resume_review(str(root))["stage"] == "plan_ready"
    collected = fixture.request_count() - requests
    assert collected == 0, "finalization collects nothing; it is local-only"
    assert len(list((root / "artifacts" / "review_decision").iterdir())) == 1


def test_record_input_and_record_critic_rejections(fixture: ReviewFixture) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])

    # record-input rejects unknown sections without touching the draft.
    bad_input = fixture.tmp / "bad-input.json"
    bad_input.write_text(json.dumps({"bogus_section": []}))
    invalid = draft_module.record_draft_input(draft_path, str(bad_input))
    assert invalid["status"] == "invalid"
    assert invalid["errors"][0]["path"] == "$.bogus_section"

    # record-critic without a recorded package names the missing binding.
    receipt = fixture.tmp / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "portable-gitlab/critic-receipt/v2",
                "evidence_digest": started["critic_receipt_template"]["evidence_digest"],
                "run_id": "critic-run",
                "session_id": "critic-session",
                "findings": [],
                "external_mutations": False,
            }
        )
    )
    invalid_critic = draft_module.record_draft_critic(draft_path, str(receipt))
    assert invalid_critic["status"] == "invalid"
    assert any(item["path"] == "$.question_answers" for item in invalid_critic["errors"])
