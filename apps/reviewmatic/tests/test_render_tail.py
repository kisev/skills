"""The inverted tail: render from the decision, edit only prose, re-anchor drift.

The live-review pain was 62 minutes of blind lettered iterations over
re-publication semantics (stable IDs, revision+1, update_issue, presence,
binding) and full re-authoring on head drift. The runtime now renders the
complete content from the recorded decision - machine fields by the
validators' own functions, prose as placeholders - the agent edits one prose
file applied by one command, and drift re-anchors machine fields with the
decision and prose preserved verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic import publication_skeletons, render, tail
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


FINDING = {
    "id": "docs-1",
    "severity": "low",
    "summary": "Retry documentation omits the idempotency key",
    "risk": "Operators can deploy the retry without the required key.",
    "evidence": ["The reviewed README documents the retry without the key argument."],
    "consequence": "A deployment following the documented steps repeats writes.",
    "relation_to_change": "The reviewed change introduces the retry path.",
    "minimum_fix": "Document the idempotency key next to the retry example.",
}

REVIEW_PATCH = (
    "diff --git a/retry-policy.txt b/retry-policy.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/retry-policy.txt\n"
    "@@ -0,0 +1 @@\n"
    "+reserve idempotency key\n"
)


def _write(fixture: ReviewFixture, name: str, value: dict[str, Any]) -> Path:
    path = fixture.tmp / name
    contract.write_json(path, value)
    return path


def _prose_fill(prose: dict[str, Any]) -> dict[str, Any]:
    """Judge-authored prose over the rendered projection."""
    return {
        **prose,
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The reviewed change is complete."},
            "relevance": {"status": "current", "rationale": "The exact head is current."},
            "change": "The change keeps the reviewed contract intact.",
        },
        "summary": "The change is small and preserves the reviewed contract.",
        "architecture_assessment": "The responsibility remains with its existing owner.",
        "semver_impact": "patch",
        "semver_rationale": "Backward-compatible correction.",
        "semver_assessment": {
            **prose["semver_assessment"],
            "policy": "No release policy was found in the fixture.",
            "sources": ["Fixture repository and empty release catalog"],
            "fallback_reason": "No confirmed release is available.",
        },
        "mr_metadata_assessment": {
            field: {
                "status": "ok",
                "rationale": f"The observed {field} is sufficient.",
                "recommendation": None,
            }
            for field in ("title", "description", "labels", "workflow_state", "overall")
        },
        "label_assessments": [
            {
                "name": item["name"],
                "status": ("applicable" if item["name"] == "semver::patch" else "inapplicable"),
                "rationale": "Matches the assessed patch contribution.",
            }
            for item in prose["label_assessments"]
        ],
        "checks": ["Compared the exact base and head revisions."],
        "recommended_issues": [],
        "rejected_candidate_assessments": [
            {**item, "reason": "The exact head does not contain the reported gap."}
            for item in prose["rejected_candidate_assessments"]
        ],
        "thread_decisions": [
            {
                **{
                    key: item[key]
                    for key in item
                    if key not in ("assessment", "rationale", "outcome", "proposed_response")
                },
                "assessment": "fixed",
                "rationale": "The exact reviewed code addresses the remark.",
                # The fixture thread is open (machine state); a closing
                # assessment resolves it.
                "outcome": "resolve",
                "proposed_response": "The exact reviewed code handles this path.",
            }
            for item in prose["thread_decisions"]
        ],
        "finding_publications": [
            {
                **{
                    key: row[key]
                    for key in row
                    if key not in ("body", "patch", "patch_reason", "type", "fix_mode")
                },
                "body": "The documented retry needs the idempotency key; the patch adds it.",
                "patch": REVIEW_PATCH,
                "patch_reason": "The documented setup has no suggestion anchor in prose.",
            }
            for row in prose["finding_publications"]
        ],
    }


def _prepare(fixture: ReviewFixture) -> dict[str, Any]:
    started = draft_module.start_review(
        url=fixture.url, repo_root=str(fixture.repo), review_mode="fast"
    )
    assert started["status"] == "ok"
    return started


def test_render_places_and_prose_surface_pass_both_layers_first_time(
    fixture: ReviewFixture,
) -> None:
    """The live-cluster shape: render once, fill prose once, finalize."""
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    contract.read_json(Path(draft_path), "draft")
    root = Path(str(started["artifact_root"]))

    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    # The recorded decision: one accepted finding with a publication intent.
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "low_risk": True,
        "findings": [FINDING],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Confirmed on the exact head.",
                "dependencies": {
                    "paths": ["review.txt"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                },
                "publication": {"kind": "general", "fix_mode": "patch"},
            }
        ],
    }
    imported = draft_module.record_draft_input(
        draft_path, str(_write(fixture, "decision.json", sections))
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))

    rendered = draft_module.render_content_review(draft_path)
    assert rendered["status"] == "ok"
    prose_path = Path(str(rendered["prose_path"]))
    assert prose_path.exists()
    prose = contract.read_json(prose_path, "prose")
    # Machine fields are absent from the prose surface; prose keys only.
    assert "path" not in prose["finding_publications"][0]
    assert "url" not in prose["thread_decisions"][0]
    # The rendered draft is not finalizable: check gives fill guidance.
    checked = draft_module.check_review(draft_path)
    assert checked["status"] == "invalid"
    assert any("unfilled template variant" in error["message"] for error in checked["errors"]), (
        checked["errors"]
    )

    # The agent fills the prose once; record-prose applies it.
    contract.write_json(prose_path, _prose_fill(prose))
    applied = draft_module.record_prose(draft_path, str(prose_path))
    assert applied["status"] == "ok"
    assert applied["fill_guidance"] == []

    # check-review passes and finish-review finalizes: both layers, first time.
    checked = draft_module.check_review(draft_path)
    assert checked["status"] == "ok", json.dumps(checked["errors"])
    finished = draft_module.finish_review(draft_path)
    assert finished["status"] == "ok", json.dumps(finished.get("errors", finished))
    assert (root / "runbook.md").exists()


def test_record_prose_rejects_structural_keys(fixture: ReviewFixture) -> None:
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "dispositions": [],
    }
    assert (
        draft_module.record_draft_input(
            draft_path, str(_write(fixture, "decision2.json", sections))
        )["status"]
        == "ok"
    )
    assert draft_module.render_content_review(draft_path)["status"] == "ok"
    structural = {
        "finding_publications": [
            {"finding_id": "docs-1", "type": "general", "line": 3, "fix_mode": "patch"}
        ]
    }
    with pytest.raises(contract.WorkflowError, match="structural keys"):
        draft_module.record_prose(draft_path, str(_write(fixture, "bad-prose.json", structural)))


def test_rendered_draft_record_input_requires_repair_kind(fixture: ReviewFixture) -> None:
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "dispositions": [],
    }
    assert (
        draft_module.record_draft_input(
            draft_path, str(_write(fixture, "decision3.json", sections))
        )["status"]
        == "ok"
    )
    assert draft_module.render_content_review(draft_path)["status"] == "ok"
    result = draft_module.record_draft_input(
        draft_path,
        str(_write(fixture, "sections.json", {"content": {"summary": "edited"}})),
    )
    assert result["status"] == "invalid"
    assert any(
        "rendered" in error["message"] and "record-prose" in error["message"]
        for error in result["errors"]
    ), result["errors"]


def test_line_intent_anchor_comes_from_changed_lines(fixture: ReviewFixture) -> None:
    """A line publication intent renders the machine anchor deterministically."""
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "low_risk": True,
        "findings": [FINDING],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Confirmed on the exact head.",
                "dependencies": {
                    "paths": ["review.txt"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                },
                "publication": {"kind": "line", "fix_mode": "suggestion"},
            }
        ],
    }
    assert (
        draft_module.record_draft_input(
            draft_path, str(_write(fixture, "decision4.json", sections))
        )["status"]
        == "ok"
    )
    rendered = draft_module.render_content_review(draft_path)
    assert rendered["status"] == "ok"
    draft = contract.read_json(Path(draft_path), "draft")
    row = draft["content"]["finding_publications"][0]
    assert row["type"] == "line"
    assert row["path"] == "review.txt"
    assert row["line"] == 2  # the added line, not an unchanged context line
    assert publication_skeletons.placeholder_fields(row)  # prose stays placeholder


def test_re_anchor_preserves_decision_and_remaps_anchors(fixture: ReviewFixture) -> None:
    """Head drift: machine anchors shift, decision and prose stay verbatim."""
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "low_risk": True,
        "findings": [FINDING],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Confirmed on the exact head.",
                "dependencies": {
                    "paths": ["review.txt"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                },
                "publication": {"kind": "line", "fix_mode": "suggestion"},
            }
        ],
    }
    assert (
        draft_module.record_draft_input(
            draft_path, str(_write(fixture, "decision5.json", sections))
        )["status"]
        == "ok"
    )
    assert draft_module.render_content_review(draft_path)["status"] == "ok"
    rendered = contract.read_json(Path(draft_path), "draft")
    prose_path = render.prose_file(
        Path(str(started["artifact_root"])), str(rendered["context_digest"])
    )
    prose = contract.read_json(prose_path, "prose")
    filled = _prose_fill(prose)
    filled["finding_publications"] = [
        {
            "finding_id": "docs-1",
            "body": "Keep the key.\n\n```suggestion:-0+0\nkeyed retry\n```",
            "patch": None,
        }
    ]
    contract.write_json(prose_path, filled)
    assert draft_module.record_prose(draft_path, str(prose_path))["status"] == "ok"

    # Drift: a new commit inserts one line above the reviewed one.
    (fixture.repo / "review.txt").write_text("base\nintro\nreviewed change\n")
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "drift")
    new_head = fixture.head()
    fixture.git("push", "-q", "origin", "main")
    fixture._git(fixture.origin, "update-ref", "refs/merge-requests/7/head", new_head)
    fixture.config_path.write_text(json.dumps({**fixture.read_config(), "headSha": new_head}))

    re_anchored = draft_module.re_anchor_review(draft_path)
    assert re_anchored["status"] == "ok", re_anchored
    assert re_anchored["re_anchored"] is True
    assert re_anchored["delta_check"]["scope"]["from_head"] == fixture.head_sha
    assert "record-prose" not in re_anchored["next_action"]["command"]
    checkpoint = tail.load(Path(re_anchored["artifact_root"]))
    assert checkpoint is not None
    assert (
        checkpoint["content"]["summary"]
        == "The change is small and preserves the reviewed contract."
    )
    # The transfer cannot be certified by mapping alone.
    assert checkpoint["pending_delta"]["checked"] is False


def test_re_anchor_refuses_anchors_inside_changed_hunks(fixture: ReviewFixture) -> None:
    """An anchor consumed by a changed hunk refuses loudly, never guesses."""
    started = _prepare(fixture)
    draft_path = str(started["draft_path"])
    # The context package grounds the review (fixture helper pattern).
    template = contract.read_json(
        Path(str(started["context_package"]["template_path"])), "context package template"
    )
    template["goal"] = {
        "status": "known",
        "text": "Document the idempotency key beside the retry.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(Path(str(started["context_package"]["template_path"])), template)
    draft_module.record_draft_package(draft_path, str(started["context_package"]["template_path"]))

    sections = {
        "run_id": "primary-run",
        "session_id": "primary-session",
        "low_risk": True,
        "findings": [FINDING],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Confirmed on the exact head.",
                "dependencies": {
                    "paths": ["review.txt"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                },
                "publication": {"kind": "line", "fix_mode": "suggestion"},
            }
        ],
    }
    assert (
        draft_module.record_draft_input(
            draft_path, str(_write(fixture, "decision6.json", sections))
        )["status"]
        == "ok"
    )
    assert draft_module.render_content_review(draft_path)["status"] == "ok"

    # The drift rewrites the anchored line itself: no unique image exists.
    (fixture.repo / "review.txt").write_text("base\nrewritten line\n")
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "rewrites the anchor")
    new_head = fixture.head()
    fixture.git("push", "-q", "origin", "main")
    fixture._git(fixture.origin, "update-ref", "refs/merge-requests/7/head", new_head)
    fixture.config_path.write_text(json.dumps({**fixture.read_config(), "headSha": new_head}))

    before = Path(draft_path).read_bytes()
    result = draft_module.re_anchor_review(draft_path)
    assert result["status"] == "invalid"
    assert Path(draft_path).read_bytes() == before
    assert any("unfilled template variant" in row["message"] for row in result["errors"])


def test_prose_round_trips_previous_assessment_handles() -> None:
    content = {
        "previous_finding_assessments": [
            {
                "id": "prior-1",
                "kind": "finding",
                "critic_required": False,
                "previous_status": "active",
                "status": "fixed",
                "rationale": "Verified on the exact head.",
            }
        ]
    }
    prose = render.prose_projection(content)
    assert prose["previous_finding_assessments"][0]["id"] == "prior-1"
    assert render.apply_prose(content, prose) == content


def test_prose_rejects_runtime_publication_stamps() -> None:
    content = {"finding_publications": [{"finding_id": "prior-1", "body": "Explanation."}]}
    for field, value in (("revision", 2), ("patch_path", "/forged"), ("patch_sha256", "a" * 64)):
        with pytest.raises(contract.WorkflowError, match="machine-rendered"):
            render.apply_prose(
                content, {"finding_publications": [{"finding_id": "prior-1", field: value}]}
            )


def test_re_anchor_maps_insertions_without_guessing(fixture: ReviewFixture) -> None:
    old_head = fixture.head_sha
    (fixture.repo / "review.txt").write_text("base\nintro\nreviewed change\n")
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "insert before the anchor")
    new_head = fixture.head()
    rows = render.re_anchor_line(
        fixture.repo, old_head, new_head, [{"type": "line", "path": "review.txt", "line": 2}]
    )
    assert rows[0]["line"] == 3
    unchanged = render.re_anchor_line(
        fixture.repo, old_head, new_head, [{"type": "line", "path": "review.txt", "line": 1}]
    )
    assert unchanged[0]["line"] == 1


def _prepare_panel(fixture: ReviewFixture) -> str:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    path = str(started["draft_path"])
    package_path = Path(str(started["context_package"]["template_path"]))
    package = contract.read_json(package_path, "package")
    package["questions"] = []
    for thread in package["thread_registry"]:
        thread["summary"] = "Retry discussion."
        thread["review_relevance"] = "The change affects this path."
    contract.write_json(package_path, package)
    draft_module.record_draft_package(path, str(package_path))
    selection = {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arb-1"}}
    draft_module.record_draft_participants(path, str(_write(fixture, "panel.json", selection)))
    receipt = {
        **started["critic_receipt_template"],
        "run_id": "critic-run",
        "session_id": "critic-session",
        "findings": [FINDING],
    }
    draft_module.record_draft_critic(path, str(_write(fixture, "critic.json", receipt)), "critic-1")
    arbitration = {
        "schema": "code-review/arbitration/v1",
        "evidence_digest": receipt["evidence_digest"],
        "run_id": "arb-run",
        "session_id": "arb-session",
        "external_mutations": False,
        "merge_verdict": "merge_then_fix",
        "merge_verdict_rationale": "The fix is local.",
        "findings": [],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Confirmed on the exact head.",
                "dependencies": {
                    "paths": ["review.txt"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                },
                "publication": {"kind": "general", "fix_mode": "patch"},
            }
        ],
        "ci_job_assessments": [],
        "owner_decision_reasons": [],
        "question_verifications": [],
        "content": {},
    }
    imported = draft_module.record_draft_arbitration(
        path, str(_write(fixture, "panel-arbitration.json", arbitration))
    )
    assert imported["status"] == "ok", imported
    draft_module.render_content_review(path)
    return path


def test_renderer_keeps_an_accepted_critic_finding(fixture: ReviewFixture) -> None:
    path = _prepare_panel(fixture)
    draft = contract.read_json(Path(path), "draft")
    assert draft["content"]["findings"] == [FINDING]
    assert draft["content"]["finding_publications"][0]["finding_id"] == "docs-1"


def test_panel_record_prose_passes_ownership_and_validation(fixture: ReviewFixture) -> None:
    path = _prepare_panel(fixture)
    draft = contract.read_json(Path(path), "draft")
    decision_before = draft["arbitration"]["dispositions"]
    identity = {"run_id": "orchestrator-run", "session_id": "orchestrator-session"}
    assert (
        draft_module.record_draft_input(path, str(_write(fixture, "identity.json", identity)))[
            "status"
        ]
        == "ok"
    )
    prose_path = render.prose_file(Path(path).parent.parent, draft["context_digest"])
    prose = contract.read_json(prose_path, "prose")
    contract.write_json(prose_path, _prose_fill(prose))
    draft_module.record_prose(path, str(prose_path))
    after = contract.read_json(Path(path), "draft")
    assert after["arbitration"]["dispositions"] == decision_before
    checked = draft_module.check_review(path)
    assert checked["status"] == "ok", checked["errors"]


def test_no_drift_re_anchor_preserves_the_recorded_panel(fixture: ReviewFixture) -> None:
    path = _prepare_panel(fixture)
    before = Path(path).read_bytes()
    root = Path(path).parent.parent
    progress_before = (root / review_context.PROGRESS_NAME).read_bytes()
    result = draft_module.re_anchor_review(path)
    assert result["re_anchored"] is False
    assert Path(path).read_bytes() == before
    assert (root / review_context.PROGRESS_NAME).read_bytes() == progress_before


def test_unfinished_panel_re_anchor_preserves_authorship(
    fixture: ReviewFixture,
) -> None:
    path = _prepare_panel(fixture)
    before = Path(path).read_bytes()
    root = Path(path).parent.parent
    progress_before = (root / review_context.PROGRESS_NAME).read_bytes()
    (fixture.repo / "review.txt").write_text("base\nintro\nreviewed change\n")
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "head drift")
    head = fixture.head()
    fixture.config_path.write_text(json.dumps({**fixture.read_config(), "headSha": head}))
    result = draft_module.re_anchor_review(path)
    assert result["status"] == "invalid"
    assert Path(path).read_bytes() == before
    assert (root / review_context.PROGRESS_NAME).read_bytes() == progress_before


def test_validated_draft_panel_hands_off_to_fresh_delta_check(fixture: ReviewFixture) -> None:
    path = _prepare_panel(fixture)
    root = Path(path).parent.parent
    draft = contract.read_json(Path(path), "draft")
    assert (
        draft_module.record_draft_input(
            path,
            str(
                _write(
                    fixture,
                    "checkpoint-identity.json",
                    {
                        "run_id": "checkpoint-primary-run",
                        "session_id": "checkpoint-primary-session",
                    },
                )
            ),
        )["status"]
        == "ok"
    )
    prose_path = render.prose_file(root, draft["context_digest"])
    contract.write_json(prose_path, _prose_fill(contract.read_json(prose_path, "prose")))
    draft_module.record_prose(path, str(prose_path))
    before = Path(path).read_bytes()
    (fixture.repo / "review.txt").write_text("base\nintro\nreviewed change\n")
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "move the draft head")
    head = fixture.head()
    fixture.git("push", "-q", "origin", "main")
    fixture._git(fixture.origin, "update-ref", "refs/merge-requests/7/head", head)
    fixture.config_path.write_text(json.dumps({**fixture.read_config(), "headSha": head}))
    migrated = draft_module.re_anchor_review(path)
    assert migrated["status"] == "ok", migrated
    assert Path(path).read_bytes() == before
    state = tail.load(root)
    assert state is not None
    check_path = Path(state["pending_delta"]["template_path"])
    check = contract.read_json(check_path, "delta")
    check.update(run_id="draft-delta-run", session_id="draft-delta-session")
    for row in check["checks"]:
        row.update(
            verdict="confirmed", evidence="Verified the changed code and affected consumers."
        )
    contract.write_json(check_path, check)
    assert tail.record_delta(root, str(check_path))["status"] == "ok"
    final = tail.finalize(root)
    assert final["status"] == "ok", final
