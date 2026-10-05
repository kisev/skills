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
from typing import Any

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Any:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


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

    draft = complete_draft(
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
