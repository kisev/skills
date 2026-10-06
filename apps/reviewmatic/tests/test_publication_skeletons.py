"""Publication skeletons: formally complete variants that fail until filled.

The renderer pre-renders every valid (type, fix_mode) variant per finding into
the materializable templates. Judgment placeholders are structurally detectable
and always refuse with fill-or-delete guidance; once the agent substitutes the
judgment and prunes the unused variants, the same rows pass the app-layer
validator and — after the runtime's own patch materialization — the canonical
artifact validator, first time, without any form corrections.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from helpers.review_fixture import make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic import publication_skeletons
from reviewmatic.portable.portable_gitlab import contract

UNIFIED_DIFF = (
    "diff --git a/retry.txt b/retry.txt\n"
    "--- a/retry.txt\n"
    "+++ b/retry.txt\n"
    "@@ -1,2 +1,2 @@\n"
    " base\n"
    "-reviewed change\n"
    "+reviewed change with the idempotency key\n"
)

GENERAL_FINDING = {
    "id": "docs-1",
    "severity": "low",
    "summary": "The retry lacks the idempotencyency key in prose",
    "risk": "Operators deploying the documented retry repeat writes.",
    "evidence": ["The reviewed README documents the retry without the key argument."],
    "consequence": "A deployment following the documented steps repeats writes.",
    "relation_to_change": "The reviewed change introduces the retry path.",
    "minimum_fix": "Document the idempotency key next to the retry example.",
}
LINE_FINDING = {**GENERAL_FINDING, "id": "line-1"}
THREAD_FINDING = {**GENERAL_FINDING, "id": "thread-owned-1"}
REJECTED_FINDING = {**GENERAL_FINDING, "id": "refuted-1"}


def fill_general_patch(finding_id: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": "general",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "The documented retry needs the idempotency key; the patch adds it.",
        "fix_mode": "patch",
        "patch": UNIFIED_DIFF,
        "patch_reason": "The documented setup has no suggestion anchor in prose.",
    }


def fill_line_suggestion(finding_id: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": "line",
        "path": "retry.txt",
        "line": 2,
        "old_line": None,
        "body": "Use the keyed retry form.\n\n```suggestion:-0+0\nreviewed change with the idempotency key\n```",
        "fix_mode": "suggestion",
        "patch": None,
    }


def fill_existing_thread(finding_id: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": "existing_thread",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "The exact retry path now reuses the key; closing with the confirmed fix.",
        "fix_mode": "not_required",
        "patch": None,
        "thread_id": "discussion-42",
    }


def test_skeleton_renderer_emits_the_full_variant_catalog() -> None:
    blocks = publication_skeletons.skeleton_variants("docs-1", "reviewer")
    assert [(item["type"], item["fix_mode"]) for item in blocks] == [
        ("general", "patch"),
        ("line", "suggestion"),
        ("line", "patch"),
        ("existing_thread", "not_required"),
    ]
    author = publication_skeletons.skeleton_variants("docs-1", "author")
    assert [(item["type"], item["fix_mode"]) for item in author] == [
        ("local_fix", "patch"),
        ("existing_thread", "not_required"),
    ]
    for block in [*blocks, *author]:
        # Mechanically filled identity; every judgment field is detectable.
        assert block["finding_id"] == "docs-1"
        assert publication_skeletons.placeholder_fields(block) != []


def test_unfilled_variants_refuse_with_fill_or_delete_guidance() -> None:
    skeletons = publication_skeletons.publication_skeletons(
        [GENERAL_FINDING, LINE_FINDING], "reviewer"
    )
    with pytest.raises(
        contract.WorkflowError, match="unfilled template variant: fill the judgment fields"
    ):
        review_context.validate_finding_publications(
            skeletons, {"docs-1", "line-1", "thread-owned-1"}
        )
    # A single leftover variant refuses as loudly as a whole template.
    leftover = fill_general_patch("docs-1")
    leftover["patch"] = ""
    with pytest.raises(contract.WorkflowError, match="unfilled template variant"):
        review_context.validate_finding_publications([leftover], {"docs-1"})


def test_self_documenting_rule_refusals() -> None:
    ids = {"docs-1", "line-1"}
    rules: list[tuple[dict[str, Any], str]] = [
        # thread_id outside existing_thread.
        (
            {**fill_general_patch("docs-1"), "thread_id": "discussion-42"},
            r"thread_id is valid only with type=existing_thread",
        ),
        # A general publication with positions.
        (
            {**fill_general_patch("docs-1"), "path": "retry.txt", "line": 2},
            (
                r"general and local_fix publish a general comment: path, line, and old_line "
                r"must be null"
            ),
        ),
        # A general publication without a patch.
        (
            {
                **fill_general_patch("docs-1"),
                "fix_mode": "suggestion",
                "patch": None,
                "body": "Use the keyed retry form.\n\n```suggestion\nkeyed\n```",
            },
            (
                r"general and local_fix require a Git patch \(fix_mode=patch\) or grouped "
                r"suggestions"
            ),
        ),
        # A line publication with both anchors set.
        (
            {**fill_line_suggestion("line-1"), "line": 2, "old_line": 2},
            r"type line requires the changed file path and exactly one anchor",
        ),
        # A line publication with no anchor yet answers with fill-or-delete
        # guidance: the anchor is a judgment field of the skeleton.
        (
            {
                **fill_line_suggestion("line-1"),
                "line": None,
                "old_line": None,
            },
            r"unfilled template variant: fill the judgment fields line",
        ),
        # A patch publication with a diff inside the body prose.
        (
            {**fill_general_patch("docs-1"), "body": f"Apply this:\n\n{UNIFIED_DIFF}"},
            r"body must be prose only: no diff headers and no git apply",
        ),
        # An existing_thread publication with a position.
        (
            {**fill_existing_thread("docs-1"), "path": "retry.txt"},
            r"an existing_thread publication binds the prepared thread",
        ),
    ]
    for invalid, message in rules:
        with pytest.raises(contract.WorkflowError, match=message):
            review_context.validate_finding_publications([invalid], ids)


def test_filled_variants_pass_both_layers_first_time(tmp_path: Path) -> None:
    """Substituted skeletons accept the app layer and the canonical artifact."""
    skeletons = publication_skeletons.publication_skeletons(
        [GENERAL_FINDING, LINE_FINDING, THREAD_FINDING], "reviewer"
    )
    by_variant = {(item["finding_id"], item["type"], item["fix_mode"]): item for item in skeletons}
    chosen = [
        # (general; patch) — substitute texts and the real unified diff.
        {**by_variant[("docs-1", "general", "patch")], **fill_general_patch("docs-1")},
        # (line; suggestion) — substitute the anchor and the suggestion block.
        {**by_variant[("line-1", "line", "suggestion")], **fill_line_suggestion("line-1")},
        # (existing_thread; not_required) — substitute prose and the thread id.
        {
            **by_variant[("thread-owned-1", "existing_thread", "not_required")],
            **fill_existing_thread("thread-owned-1"),
        },
    ]
    # The rejected finding keeps no variant rows at all.
    assert all(item["finding_id"] != "refuted-1" for item in chosen)

    # Layer one: the app-layer input validator accepts the substituted rows.
    accepted = review_context.validate_finding_publications(
        chosen, {"docs-1", "line-1", "thread-owned-1", "refuted-1"}
    )
    assert accepted == chosen

    # The runtime's own materialization: patch companions land content-addressed
    # with the patch digest, exactly as enrich_fix writes them.
    materialized: list[dict[str, Any]] = []
    for item in accepted:
        if item["fix_mode"] != "patch":
            materialized.append({**item, "patch_path": None, "patch_sha256": None})
            continue
        patch = str(item["patch"])
        identity = hashlib.sha256(f"finding:{item['finding_id']}".encode()).hexdigest()[:12]
        patch_digest = hashlib.sha256(patch.encode()).hexdigest()
        destination = tmp_path / "patches" / f"{identity}-{patch_digest}.patch"
        destination.parent.mkdir(parents=True, exist_ok=True)
        written, digest = contract.write_companion(destination, patch)
        materialized.append(
            {**item, "revision": 1, "patch_path": str(written), "patch_sha256": digest}
        )
    for index, item in enumerate(materialized):
        if item["fix_mode"] == "patch":
            continue
        materialized[index] = {**item, "revision": 1}

    # Layer two: the canonical artifact validator accepts the materialized rows.
    assert contract.finding_publications_are_valid(materialized, require_fixes=True) is True


def test_content_template_and_arbitration_template_carry_the_skeletons() -> None:
    fixture = make_review_fixture()
    try:
        target = contract.parse_target(fixture.url, {"merge_requests"})
        bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
        root = Path(str(bundle["artifact_root"]))
        review_context.begin_review(
            str(bundle["preview_artifact_path"]),
            str(bundle["preview_digest"]),
            str(root),
            str(fixture.repo),
            "normal",
            "en",
            "auto",
        )
        prepared = review_context.prepare_context(
            str(bundle["preview_artifact_path"]), str(fixture.repo), "auto", "normal", "en"
        )
        assert prepared["status"] == "ok"
        context_artifact = review_context.progress_artifact(
            root,
            review_context.load_progress(root) or {},
            "context",
            "review_context",
        )
        assert context_artifact is not None
        _context_path, review_context_value, _digest = context_artifact
        _evidence_path, evidence = review_context.review_evidence_from_root(root)

        # The run-path content template pre-renders the variants per accepted
        # finding with the reviewer role from the context.
        template = review_context.content_template(
            evidence,
            review_context_value,
            {"accepted_findings": [GENERAL_FINDING], "findings": [], "responses": []},
            "en",
        )
        assert [(item["type"], item["fix_mode"]) for item in template["finding_publications"]] == [
            ("general", "patch"),
            ("line", "suggestion"),
            ("line", "patch"),
            ("existing_thread", "not_required"),
        ]

        # The arbitration receipt template pre-renders the variants over every
        # candidate finding, primary and critic alike.
        draft: dict[str, Any] = {
            "participants": {"critics": [], "arbitrator": {"name": "arb-main"}},
            "evidence_digest": "0" * 64,
            "findings": [{"id": "primary-1"}],
            "critics": [
                {
                    "schema": "portable-gitlab/critic-receipt/v2",
                    "evidence_digest": "0" * 64,
                    "run_id": "r",
                    "session_id": "s",
                    "findings": [{"id": "critic-1"}],
                    "external_mutations": False,
                }
            ],
        }
        receipt = draft_module._arbitration_receipt_template(draft, "reviewer")
        assert [
            item["finding_id"]
            for item in receipt["content"]["finding_publications"]
            if item["type"] == "general"
        ] == ["primary-1", "critic-1"]
    finally:
        fixture.close()


def test_apply_content_rejects_duplicate_variant_identities() -> None:
    current: dict[str, Any] = {"finding_publications": []}
    rows = [fill_general_patch("docs-1"), fill_general_patch("docs-1")]
    merged, issues = draft_module._apply_content(current, {"finding_publications": rows})
    assert merged == current
    assert len(issues) == 1
    assert issues[0]["path"] == "$.content.finding_publications"
    assert "unique identity" in issues[0]["message"]


def test_record_arbitration_accepts_a_text_only_fresh_receipt(
    tmp_path: Path,
) -> None:
    """The atomic text repair: same decisions, new arbitrator session, new texts."""
    previous: dict[str, Any] = {
        "schema": "code-review/arbitration/v1",
        "evidence_digest": "0" * 64,
        "run_id": "run-1",
        "session_id": "session-1",
        "external_mutations": False,
        "merge_verdict": "merge",
        "merge_verdict_rationale": "The fix is local and verified.",
        "findings": [],
        "dispositions": [],
        "ci_job_assessments": [],
        "owner_decision_reasons": [],
        "question_verifications": [],
        "content": {"finding_publications": []},
    }
    fresh_session = {**previous, "session_id": "session-2"}
    assert draft_module._arbitration_decisions_unchanged(previous, fresh_session) is True
    changed_verdict = {**fresh_session, "merge_verdict": "push_back"}
    assert draft_module._arbitration_decisions_unchanged(previous, changed_verdict) is False
