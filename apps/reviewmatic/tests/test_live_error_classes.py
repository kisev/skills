"""Live error classes answered by rule, path, and valid form.

Every tail refusal names the rule, the offending path, and the accepted form,
so an agent never iterates fields blindly. The classes mirror the live review
sessions: patch_reason, a null thread_id, a suggestion anchored outside the
file, patch hunk counters, thread outcomes on resolved threads, and the
content-findings mirroring; the skeleton catalog renders again after a
replace-artifact rewind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import workflow
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Iterator

RECORD_SHAPE = r"; path: \$[^;]+; valid form: "


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def low_finding() -> dict[str, Any]:
    return {
        "id": "docs-1",
        "severity": "low",
        "summary": "Retry documentation omits the idempotency key",
        "risk": "Operators can deploy the retry without the required key.",
        "evidence": ["The reviewed README documents the retry without the key argument."],
        "consequence": "A deployment following the documented steps repeats writes.",
        "relation_to_change": "The reviewed change introduces the retry path.",
        "minimum_fix": "Document the idempotency key next to the retry example.",
    }


def test_patch_reason_refusal_names_rule_path_and_form() -> None:
    with pytest.raises(contract.WorkflowError, match=RECORD_SHAPE) as excinfo:
        review_context.validate_patch_fallback(
            {"fix_mode": "patch", "patch_reason": "", "finding_id": "docs-1"},
            {"exact_git": {"repo_root": "/unused"}},
            {"head_sha": "0" * 40},
        )
    message = str(excinfo.value)
    assert "a patch fallback names its concrete reason" in message
    assert "$.patch_reason" in message


def test_null_thread_id_refusal_names_the_owner_path() -> None:
    invalid = {
        "finding_id": "docs-1",
        "type": "existing_thread",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "The thread owns the fix.",
        "fix_mode": "not_required",
        "patch": None,
        "thread_id": None,
    }
    with pytest.raises(contract.WorkflowError, match=RECORD_SHAPE) as excinfo:
        review_context.validate_finding_publications([invalid], {"docs-1"})
    assert "an existing_thread publication binds the prepared thread" in str(excinfo.value)
    assert "finding_id=docs-1" in str(excinfo.value)


def test_suggestion_anchored_outside_the_reviewed_file(fixture: ReviewFixture) -> None:
    with pytest.raises(contract.WorkflowError, match=RECORD_SHAPE) as excinfo:
        review_context.validate_suggestion(
            "prose\n\n```suggestion:-0+5\nreplacement\n```",
            repo_root=Path(str(fixture.repo)),
            head_sha=fixture.head_sha,
            path="review.txt",
            line=2,
        )
    message = str(excinfo.value)
    assert "anchors on lines that exist at the reviewed head" in message
    assert "inside the 2-line file" in message


def test_patch_hunk_counters_surface_the_git_detail(fixture: ReviewFixture) -> None:
    corrupt_hunks = (
        "diff --git a/review.txt b/review.txt\n"
        "--- a/review.txt\n"
        "+++ b/review.txt\n"
        "@@ -1,2 +1,2 @@\n"
        " base\n"
        "-reviewed change\n"
    )
    with pytest.raises(contract.WorkflowError, match=RECORD_SHAPE) as excinfo:
        review_context.validate_git_patch(Path(str(fixture.repo)), fixture.head_sha, corrupt_hunks)
    message = str(excinfo.value)
    assert "the patch applies to the exact reviewed head" in message
    assert "$.patch" in message
    assert "hunk" in message.lower() or "patch" in message.lower()


def _prepare_fast(fixture: ReviewFixture, **overrides: Any) -> tuple[Path, str, str]:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    evidence_path = str(bundle["preview_artifact_path"])
    root = Path(str(bundle["artifact_root"]))
    review_context.begin_review(
        evidence_path,
        str(bundle["preview_digest"]),
        str(root),
        str(fixture.repo),
        "fast",
        "en",
        "auto",
        **overrides,
    )
    prepared = review_context.prepare_context(
        evidence_path, str(fixture.repo), "auto", "fast", "en"
    )
    assert prepared["status"] == "ok"
    return root, evidence_path, str(prepared["artifact_path"])


def _decide_empty(fixture: ReviewFixture, root: Path, evidence: str, context_path: str) -> None:
    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    decision = review_context.template_review(str(root), "decision")
    template = contract.read_json(Path(decision["template_path"]), "decision template")
    filled = {
        **template,
        "run_id": "primary-run",
        "session_id": "primary-session",
        "responses": [
            {**item, "decision": "accept", "reason": "Confirmed on the exact reviewed head."}
            for item in cast("list[dict[str, Any]]", template["responses"])
        ],
    }
    path = fixture.tmp / "decision.json"
    contract.write_json(path, filled)
    workflow.decide(
        argparse.Namespace(
            evidence=evidence,
            report=str(path),
            context=context_path,
            finalize_report=_progress(root, "finalize_report_path"),
            critic_receipt=None,
            mode="fast",
        )
    )


def _progress(root: Path, field: str) -> Any:
    progress = review_context.load_progress(root)
    assert progress is not None
    return progress[field]


def test_thread_binding_refusal_names_the_prepared_ids_and_the_repair(
    fixture: ReviewFixture,
) -> None:
    """The existing_thread render refusal is self-describing (decision 69/71):
    it names the prepared thread ids and the exact replace-artifact repair
    command, because the live acceptance caught a 37-minute flail that ended in
    an out-of-stage contract read when the refusal said only "use decision
    repair" and the repair surface went unnamed."""
    from reviewmatic import context as review_context_module
    from reviewmatic import render

    _root, evidence_path, context_path = _prepare_fast(fixture)
    _, evidence = contract.artifact_payload(Path(evidence_path), "evidence_snapshot")
    _artifact, review_ctx = contract.artifact_payload(Path(context_path), "review_context")
    assert isinstance(evidence, dict) and isinstance(review_ctx, dict)
    finding = low_finding()
    dummy = {
        "findings": [finding],
        "dispositions": [
            {
                "id": "docs-1",
                "decision": "accept",
                "reason": "Recorded decision.",
                "publication": {"kind": "existing_thread", "fix_mode": "suggestion"},
                "dependencies": {
                    "paths": [],
                    "thread_ids": ["guessed-thread"],
                    "metadata_fields": [],
                    "ci": False,
                },
            }
        ],
        "content": {"locale": "en"},
    }
    with pytest.raises(contract.WorkflowError) as excinfo:
        render.render_content(dummy, review_ctx, evidence)
    message = str(excinfo.value)
    assert "existing_thread intent for docs-1" in message
    assert "top-level `publication_intents` array" in message
    assert '"finding_id": "docs-1"' in message
    assert '"thread_ids": ["' in message
    prepared = sorted(review_context_module.expected_thread_bindings(review_ctx))
    assert f"prepared threads: {', '.join(prepared) if prepared else 'none'}" in message
    assert "replace-artifact --artifact-root" in message
    assert "--kind decision --path" in message


def test_thread_outcome_on_a_resolved_thread_names_the_rule() -> None:
    fixture = make_review_fixture({"resolved": True})
    try:
        root, evidence, context_path = _prepare_fast(fixture)
        _decide_empty(fixture, root, evidence, context_path)
        content = review_context.template_review(str(root), "content")
        template = contract.read_json(Path(content["template_path"]), "content template")
        thread = cast("list[dict[str, Any]]", template["thread_decisions"])[0]
        # A closing assessment on an already-resolved thread must keep it
        # closed; reopen reintroduces the problem without a fix.
        thread.update(
            {
                "assessment": "false_positive",
                "rationale": "The exact reviewed head does not contain the reported gap.",
                "outcome": "reopen",
                "proposed_response": "The exact reviewed head does not contain this problem.",
                "fix_mode": "not_required",
            }
        )
        _fill_minimal_content(template)
        path = fixture.tmp / "content.json"
        contract.write_json(path, template)
        with pytest.raises(contract.WorkflowError, match=RECORD_SHAPE) as excinfo:
            review_context.scaffold_review(
                evidence, context_path, str(_progress(root, "decision_path")), str(path)
            )
        assert "a closing assessment keeps a resolved thread closed" in str(excinfo.value)
    finally:
        fixture.close()


def test_skeletons_render_again_after_a_replace_artifact_rewind(
    fixture: ReviewFixture,
) -> None:
    root, evidence, context_path = _prepare_fast(fixture)
    _decide_empty(fixture, root, evidence, context_path)
    first = review_context.template_review(str(root), "content")
    template = contract.read_json(Path(first["template_path"]), "content template")
    assert template["finding_publications"] == []

    # A replacement decision accepts one finding and rewinds to content_missing.
    _meta, decision_template = contract.artifact_payload(
        Path(str(_progress(root, "decision_path"))), "review_decision"
    )
    finding = low_finding()
    replaced = {
        **decision_template,
        "run_id": "primary-run",
        "session_id": "primary-session",
        "verdict": "ready",
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "findings": [finding],
        "accepted_findings": [finding],
        "responses": [
            {**item, "decision": "accept", "reason": "Confirmed on the exact reviewed head."}
            for item in cast("list[dict[str, Any]]", decision_template["responses"])
        ]
        + [{"id": "docs-1", "decision": "accept", "reason": "Confirmed on the exact head."}],
        "critic_findings": [],
        "critic_target_finding_ids": [],
    }
    replacement = fixture.tmp / "replaced-decision.json"
    contract.write_json(replacement, replaced)
    workflow.replace_artifact(
        argparse.Namespace(artifact_root=str(root), kind="decision", path=str(replacement))
    )
    assert review_context.review_status(str(root))["stage"] == "content_missing"

    # The content stop re-renders the full skeleton catalog for the finding.
    after = review_context.template_review(str(root), "content")
    template = contract.read_json(Path(after["template_path"]), "content template")
    assert [(item["type"], item["fix_mode"]) for item in template["finding_publications"]] == [
        ("general", "patch"),
        ("line", "suggestion"),
        ("line", "patch"),
        ("existing_thread", "not_required"),
    ]


def _fill_minimal_content(template: dict[str, Any]) -> None:
    template.update(
        {
            "chat_assessment": {
                "necessity": {"status": "supported", "rationale": "The change is complete."},
                "relevance": {"status": "current", "rationale": "The exact head is current."},
                "change": "The change keeps the reviewed contract intact.",
            },
            "summary": "The change is small and preserves the reviewed contract.",
            "architecture_assessment": "The responsibility remains with its owner.",
            "semver_impact": "patch",
            "semver_rationale": "Backward-compatible correction.",
            "semver_assessment": {
                **template["semver_assessment"],
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
                    "status": "applicable" if item["name"] == "semver::patch" else "inapplicable",
                    "rationale": "Matches the assessed patch contribution.",
                }
                for item in template["label_assessments"]
            ],
            "checks": ["Compared the exact base and head revisions."],
            "findings": [],
            "previous_finding_assessments": [],
            "recommended_issues": [],
            "rejected_candidates": [
                {**candidate, "reason": "Not observable in the exact reviewed head."}
                for candidate in template["rejected_candidates"]
            ],
            "rejected_candidate_assessments": [
                {**item, "reason": "The exact head does not contain the reported gap."}
                for item in template["rejected_candidate_assessments"]
            ],
        }
    )


def test_json_envelope_of_a_record_is_stable() -> None:
    error = review_context.validation_record("rule one", "$.a[0].b", "shape one", "detail one")
    assert str(error) == "rule one; path: $.a[0].b; valid form: shape one; detail: detail one"
    assert json.loads(json.dumps({"error": str(error)}))["error"].startswith("rule one")


def test_mr_metadata_refusal_names_the_offending_fields() -> None:
    """Decision 67: the refusal is the environment's answer.

    The live acceptance caught an eight-round flail on the bare
    "MR metadata assessment is invalid" (the agent guessed enums and even
    blamed semicolons); the refusal now names each offending field and its
    accepted form so one round answers it.
    """
    evidence: dict[str, Any] = {
        "object": {
            "title": "Bound the retry writes",
            "description": None,
            "labels": [],
            "state": "opened",
        }
    }
    assessment = {
        "title": {"status": "fine", "rationale": "Seen.", "recommendation": None},
        "workflow_state": {"status": "ok", "rationale": "Open.", "recommendation": None},
        "overall": {"status": "ok", "rationale": "", "recommendation": None},
    }
    with pytest.raises(contract.WorkflowError) as raised:
        review_context.metadata_assessment(evidence, assessment)
    message = str(raised.value)
    assert message.startswith("MR metadata assessment is invalid: ")
    assert "missing field description" in message
    assert "missing field labels" in message
    assert "title.status is 'fine'; expected ok, needs_change, or unverified" in message
    assert "overall.rationale must be a non-empty string" in message
