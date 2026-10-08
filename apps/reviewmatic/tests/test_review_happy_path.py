"""Review state machine happy path against the fake glab, ported from
``context.test.mjs`` ("review state machine happy path with fake glab").

Exercises the full preparation chain through the fake glab helper: evidence
collection, begin/prepare context, progress transitions, templates, scaffold,
runbook publication, report review, and the incremental second run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic.portable.portable_gitlab import contract


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Any:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def test_review_state_machine_happy_path_with_fake_glab(fixture: ReviewFixture) -> None:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    assert bundle["retrieval_complete"] is True
    evidence_path = bundle["preview_artifact_path"]
    evidence_digest = bundle["preview_digest"]
    root = Path(str(bundle["artifact_root"]))

    review_context.begin_review(
        str(evidence_path),
        str(evidence_digest),
        str(root),
        str(fixture.repo),
        "normal",
        "en",
        "auto",
    )
    context_result: dict[str, Any] = review_context.prepare_context(
        str(evidence_path), str(fixture.repo), "auto", "normal", "en"
    )
    assert context_result["status"] == "ok"
    assert context_result["stage"] == "context_ready"
    assert context_result["role"] == "reviewer"
    assert context_result["counts"]["open_resolvable"] == 1
    assert context_result["incremental"]["mode"] == "full"
    assert context_result["next_action"]["argv"][0] == "reviewmatic"
    assert context_result["next_action"]["argv"][1] == "template-review"
    context_path = context_result["artifact_path"]
    context_digest = context_result["digest"]

    status1 = review_context.review_status(str(root))
    assert status1["stage"] == "critic_missing"
    assert status1["resume_stage"] is None

    critic = review_context.template_review(str(root), "critic")
    assert critic["stage"] == "critic_missing"
    critic_draft = contract.read_json(Path(critic["template_path"]), "critic template")
    assert critic_draft["run_id"] == ""
    assert critic_draft["evidence_digest"] == evidence_digest

    primary_finding = {
        "id": "primary-1",
        "severity": "high",
        "summary": "Retry can repeat the external operation",
        "risk": "A retry can execute the operation twice.",
        "evidence": ["The current retry path calls the provider before reserving an ID."],
        "consequence": "Users can observe duplicate side effects.",
        "relation_to_change": "The reviewed change adds the retry path.",
        "minimum_fix": "Persist an idempotency key before the external call.",
    }
    critic_finding = {
        "id": "critic-1",
        "severity": "medium",
        "summary": "Retry failure is not observable",
        "risk": "Operators cannot distinguish retry exhaustion.",
        "evidence": [f"The exact reviewed SHA is {fixture.head_sha}."],
        "consequence": "Incident diagnosis takes longer.",
        "relation_to_change": "The new retry path emits no terminal signal.",
        "minimum_fix": "Emit the existing terminal retry metric.",
    }
    receipt = {
        "schema": "portable-gitlab/critic-receipt/v2",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "run_id": "critic-run",
        "session_id": "critic-session",
        "findings": [critic_finding],
    }
    receipt_path, receipt_digest = contract.write_artifact(root, "critic_receipt", receipt)
    progress1 = review_context.load_progress(root)
    assert progress1 is not None
    review_context.advance_progress(
        root,
        "finalize_missing",
        expected_stages={"context_ready"},
        expected={
            "evidence_path": progress1["evidence_path"],
            "evidence_digest": progress1["evidence_digest"],
            "context_path": progress1["context_path"],
            "context_digest": progress1["context_digest"],
        },
        critic_receipt_path=str(receipt_path),
        critic_receipt_digest=receipt_digest,
        finalize_report_path=None,
        finalize_report_digest=None,
        decision_path=None,
        decision_digest=None,
        plan_path=None,
        plan_digest=None,
    )

    finalize_result = contract.finalize_payload(
        contract.finalize(str(root), "review-evidence.json"),
        Path(str(evidence_path)),
        bundle,
        "evidence_snapshot",
    )
    assert finalize_result["status"] == "ok"
    finalize_path, finalize_digest = contract.write_artifact(
        root, "finalize_report", finalize_result
    )
    progress2 = review_context.load_progress(root)
    assert progress2 is not None
    review_context.advance_progress(
        root,
        "decision_missing",
        expected_stages={"context_ready", "finalize_missing"},
        expected={
            "evidence_path": progress2["evidence_path"],
            "evidence_digest": progress2["evidence_digest"],
            "context_path": progress2["context_path"],
            "context_digest": progress2["context_digest"],
            "critic_receipt_path": progress2["critic_receipt_path"],
            "critic_receipt_digest": progress2["critic_receipt_digest"],
        },
        finalize_report_path=str(finalize_path),
        finalize_report_digest=finalize_digest,
        decision_path=None,
        decision_digest=None,
        plan_path=None,
        plan_digest=None,
    )

    decision = review_context.template_review(str(root), "decision")
    decision_draft = contract.read_json(Path(decision["template_path"]), "decision template")
    assert decision_draft["context_digest"] == context_digest
    assert decision_draft["unresolved_threads"] == [{"id": "thread:42"}]
    assert decision_draft["verdict"] == "not_ready"
    assert decision_draft["responses"] == [
        {"id": "critic-1", "decision": "accept", "reason": ""},
        {"id": "thread:42", "decision": "accept", "reason": ""},
    ]

    decision_report = {
        "schema": "portable-gitlab/review-decision/v2",
        "mode": "normal",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "finalize_digest": finalize_digest,
        "context_digest": context_digest,
        "critic_receipt_digest": receipt_digest,
        "verdict": "not_ready",
        "blocking_findings": True,
        "blocking_finding_ids": ["primary-1"],
        "owner_decision_reasons": [],
        "run_id": "primary-run",
        "session_id": "primary-session",
        "findings": [primary_finding],
        "unresolved_threads": [{"id": "thread:42"}],
        "responses": [
            {"id": "primary-1", "decision": "accept", "reason": "confirmed"},
            {"id": "critic-1", "decision": "reject", "reason": "outside the changed contract"},
            {"id": "thread:42", "decision": "accept", "reason": "still open"},
        ],
    }
    review_context.validate_review_verdict(decision_report, [primary_finding], bundle)
    decision_payload = {
        **decision_report,
        "critic_findings": [critic_finding],
        "accepted_findings": [primary_finding],
        "critic_target_finding_ids": [],
    }
    decision_path, decision_digest = contract.write_artifact(
        root, "review_decision", decision_payload
    )
    progress3 = review_context.load_progress(root)
    assert progress3 is not None
    review_context.advance_progress(
        root,
        "content_missing",
        expected_stages={"decision_missing"},
        expected={
            "evidence_path": progress3["evidence_path"],
            "evidence_digest": progress3["evidence_digest"],
            "context_path": progress3["context_path"],
            "context_digest": progress3["context_digest"],
            "critic_receipt_path": progress3["critic_receipt_path"],
            "critic_receipt_digest": progress3["critic_receipt_digest"],
            "finalize_report_path": progress3["finalize_report_path"],
            "finalize_report_digest": progress3["finalize_report_digest"],
        },
        decision_path=str(decision_path),
        decision_digest=decision_digest,
        plan_path=None,
        plan_digest=None,
    )

    content = review_context.template_review(str(root), "content")
    assert content["stage"] == "content_missing"
    template_content = contract.read_json(Path(content["template_path"]), "content template")
    assert "presentation" not in template_content
    assert len(template_content["thread_decisions"]) == 1
    assert len(template_content["label_assessments"]) == 4
    assert len(template_content["rejected_candidates"]) == 1
    assert template_content["rejected_candidates"][0]["id"] == "critic-1"
    assert template_content["semver_assessment"]["mode"] == "target_fallback"

    review_content = {
        "locale": "en",
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The retry defect is confirmed."},
            "relevance": {
                "status": "current",
                "rationale": "The exact reviewed head is current.",
            },
            "change": (
                "The MR adds retry behavior but does not reserve an idempotency key before "
                "the external call."
            ),
        },
        "summary": "The change is small and preserves the reviewed contract.",
        "architecture_assessment": "The responsibility remains with its existing owner.",
        "semver_impact": "patch",
        "semver_rationale": "The fix changes behavior without changing the public API.",
        "semver_assessment": {
            **template_content["semver_assessment"],
            "policy": "No release policy was found in the fixture.",
            "sources": ["Fixture repository and empty release catalog"],
            "fallback_reason": "No confirmed release is available.",
        },
        "mr_metadata_assessment": {
            "title": {
                "status": "needs_change",
                "rationale": "The title does not identify the affected behavior.",
                "recommendation": "Name the affected retry behavior.",
            },
            "description": {
                "status": "ok",
                "rationale": "The description states the intended behavior.",
                "recommendation": None,
            },
            "labels": {
                "status": "needs_change",
                "rationale": "The MR has no labels.",
                "recommendation": "Apply the project-required labels.",
            },
            "workflow_state": {
                "status": "ok",
                "rationale": "The MR is open and remains commentable.",
                "recommendation": None,
            },
            "overall": {
                "status": "needs_change",
                "rationale": "Title and labels need clearer release metadata.",
                "recommendation": "Correct metadata independently of code findings.",
            },
        },
        "label_assessments": [
            {
                "name": "next-compatible",
                "status": "inapplicable",
                "rationale": "The change is a patch, not a minor release.",
            },
            {
                "name": "semver::major",
                "status": "inapplicable",
                "rationale": "The change is backward compatible.",
            },
            {
                "name": "semver::patch",
                "status": "applicable",
                "rationale": "The reviewed fix has patch SemVer impact.",
            },
            {
                "name": "ship-ready",
                "status": "inapplicable",
                "rationale": "This MR is not a release publication.",
            },
        ],
        "checks": ["Compared the exact base and head revisions."],
        "findings": [primary_finding],
        "finding_publications": [
            {
                "finding_id": "primary-1",
                "type": "general",
                "path": None,
                "line": None,
                "old_line": None,
                "body": "You need to reserve an idempotency key before the external call.",
                "fix_mode": "patch",
                "patch_reason": "A new policy file has no existing suggestion anchor.",
                "patch": (
                    "diff --git a/retry-policy.txt b/retry-policy.txt\n"
                    "new file mode 100644\n"
                    "--- /dev/null\n"
                    "+++ b/retry-policy.txt\n"
                    "@@ -0,0 +1 @@\n"
                    "+reserve idempotency key\n"
                ),
            },
        ],
        "previous_finding_assessments": [],
        "issue_templates": [],
        "recommended_issues": [
            {
                "id": "issue-1",
                "title": "Track retry exhaustion observability",
                "problem": "The broader retry subsystem lacks a terminal signal.",
                "risk": "Operators cannot distinguish retry exhaustion.",
                "evidence": ["The existing subsystem has no terminal metric."],
                "reason_out_of_scope": "The subsystem is not changed by this MR.",
                "minimum_fix": "Add the existing terminal retry metric separately.",
                "body": "Track a terminal metric for retry exhaustion in the broader subsystem.",
                "template_path": None,
            },
        ],
        "rejected_candidates": [
            {
                "id": "critic-1",
                "source": "critic",
                "finding": critic_finding,
                "reason": "The broader observability gap is outside this MR.",
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        ],
        "rejected_candidate_assessments": [],
        "thread_decisions": [
            {
                "id": "42",
                "url": ("https://gitlab.example/group/project/-/merge_requests/7#note_42"),
                "state": "open",
                "assessment": "fixed",
                "rationale": "The existing thread can be acknowledged and resolved.",
                "outcome": "resolve",
                "proposed_response": (
                    "I tracked the remaining risk in the current finding. Closing."
                ),
                "fix_mode": "not_required",
                "patch": None,
                "fixing_commit": None,
                "last_note_id": 42,
                "last_note_body_sha256": hashlib.sha256(
                    b"Retry needs an idempotency key"
                ).hexdigest(),
                "thread_sha256": template_content["thread_decisions"][0]["thread_sha256"],
            },
        ],
    }

    invalid_state = json.loads(json.dumps(review_content))
    invalid_state["thread_decisions"][0].update(
        {"state": "resolved", "outcome": "no_publication", "proposed_response": None}
    )
    invalid_state_path = fixture.tmp / "invalid-state.json"
    invalid_state_path.write_text(json.dumps(invalid_state))
    with pytest.raises(
        contract.WorkflowError, match="thread decision state does not match review context"
    ):
        review_context.scaffold_review(
            str(evidence_path), str(context_path), str(decision_path), str(invalid_state_path)
        )
    invalid_accepted = json.loads(json.dumps(review_content))
    invalid_accepted["thread_decisions"][0].update(
        {"assessment": "accepted", "outcome": "reply", "fix_mode": "not_required"}
    )
    invalid_accepted_path = fixture.tmp / "invalid-accepted.json"
    invalid_accepted_path.write_text(json.dumps(invalid_accepted))
    with pytest.raises(
        contract.WorkflowError, match="an accepted thread requires a validated code fix"
    ):
        review_context.scaffold_review(
            str(evidence_path), str(context_path), str(decision_path), str(invalid_accepted_path)
        )

    content_file = fixture.tmp / "review-content.json"
    content_file.write_text(json.dumps(review_content))
    plan: dict[str, Any] = review_context.scaffold_review(
        str(evidence_path), str(context_path), str(decision_path), str(content_file)
    )
    assert plan["status"] == "ok"
    assert plan["stage"] == "plan_ready"
    assert Path(plan["markdown_path"]).name == "runbook.md"
    markdown = Path(plan["markdown_path"]).read_text(encoding="utf-8")
    for section in (
        "# Code review publication plan",
        "## MR metadata",
        "## Project labels",
        "## Open threads",
        "## New findings",
        "## Recommended issues",
        "**Architecture assessment:**",
        "MR contribution",
        "## Checks",
        "git apply <<'PATCH_",
        f"code-review: {review_context.SKILL_VERSION} · contract: 7",
        "Retry can repeat the external operation",
        "https://gitlab.example/group/project/-/merge_requests/7#note_42",
    ):
        assert section in markdown, f"markdown must contain {section}"
    assert fixture.base_sha not in markdown
    assert fixture.head_sha not in markdown
    assert "marker-run" not in markdown
    assert len(plan["publication_body_paths"]) == 2
    bodies = [Path(path).read_text(encoding="utf-8") for path in plan["publication_body_paths"]]
    assert all("<!-- code-review:id=" not in body for body in bodies)
    patch_body = next(body for body in bodies if "diff --git" in body)
    assert "```sh\n" in patch_body
    assert "git apply <<'PATCH_" in patch_body
    assert "marker-run" not in patch_body
    assert len(plan["publication_commands"]) == 4
    assert all(command.startswith("glab ") for command in plan["publication_commands"])
    assert all(" --confirm " not in command for command in plan["publication_commands"])
    plan_document = contract.read_json(Path(plan["artifact_path"]), "review plan")
    payload = plan_document["payload"]
    assert payload["review_contract_version"] == 7
    assert payload["label_review"]["semver"]["selected"] == "semver::patch"
    assert contract.review_publication_preview_is_valid(payload["publication_preview"])
    thread_actions = [
        item for item in payload["publication_preview"]["actions"] if item["kind"] == "thread"
    ]
    assert [item["operation"] for item in thread_actions] == ["reply", "resolve"]
    label_action = next(
        item for item in payload["publication_preview"]["actions"] if item["kind"] == "labels"
    )
    assert "--label semver::patch" in label_action["command"]
    assert "/notes" in thread_actions[0]["command"]
    assert "resolved=true" in thread_actions[1]["command"]
    progress_after = review_context.load_progress(root)
    assert progress_after is not None and progress_after["stage"] == "plan_ready"

    status2 = review_context.review_status(str(root))
    assert status2["stage"] == "plan_ready"
    assert status2["status"] == "ok"
    assert status2["publication_plan_path"] == plan["markdown_path"]

    report = review_context.report_review(str(root))
    assert report["status"] == "ok"
    assert report["stage"] == "plan_ready"
    assert "### MR assessment" in report["chat"]
    assert plan["markdown_path"] in report["chat"]
    assert primary_finding["summary"] not in report["chat"]
    assert report["next_action"] is None

    # Second collection over unchanged evidence enters unchanged mode and
    # carries the published finding and issue in the incremental ledger.
    bundle2: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    review_context.begin_review(
        str(bundle2["preview_artifact_path"]),
        str(bundle2["preview_digest"]),
        str(root),
        str(fixture.repo),
        "normal",
        "en",
        "auto",
    )
    context2: dict[str, Any] = review_context.prepare_context(
        str(bundle2["preview_artifact_path"]), str(fixture.repo), "auto", "normal", "en"
    )
    assert context2["incremental"]["mode"] == "unchanged"
    assert context2["incremental"]["critic_required"] is False
    assert context2["review_mode"] == "unchanged"
    context2_document = contract.read_json(Path(context2["artifact_path"]), "review context")
    context2_payload = context2_document["payload"]
    assert context2_payload["incremental"]["mode"] == "unchanged"
    history = context2_payload["incremental"]["history_context"]
    assert [item["id"] for item in history["findings"]] == ["primary-1"]
    assert [item["id"] for item in history["recommended_issues"]] == ["issue-1"]
    assert context2_payload["incremental"]["previous_findings"] == []
    assert "finalize" in context2["next_action"]["command"]
