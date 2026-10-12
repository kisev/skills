"""Session modes, thread matrix, CC enforcement, and profiles (decision 75).

The six-case thread matrix renames `no_publication` to `no_reply` and lets an
open thread with a confirmed but unattempted defect stay silent; every
published answer opens with its Conventional Comments label; the auto session
publishes findings as ready comments without fixes plus one metadata proposal
comment; profiles are written only by an explicit setup invocation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import profiles, workflow
from reviewmatic.cli import main
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="fixture")
def review_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _prepare(fixture: ReviewFixture, **overrides: Any) -> tuple[Path, str, str, dict[str, Any]]:
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
    import argparse

    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    progress = review_context.load_progress(root)
    assert progress is not None
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
            evidence=evidence_path,
            report=str(path),
            context=str(prepared["artifact_path"]),
            finalize_report=progress.get("finalize_report_path"),
            critic_receipt=None,
            mode=str(progress.get("mode") or "fast"),
        )
    )
    content = review_context.template_review(str(root), "content")
    content_template = contract.read_json(Path(content["template_path"]), "content template")
    return root, evidence_path, str(prepared["artifact_path"]), content_template


def _fill(template: dict[str, Any], *, findings: bool = False) -> dict[str, Any]:
    result = dict(template)
    result.update(
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
                for field in template["mr_metadata_assessment"]
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
            "finding_publications": [],
            "previous_finding_assessments": [],
            "recommended_issues": [],
            "rejected_candidates": [
                {**candidate, "reason": "Not observable in the exact reviewed head."}
                for candidate in template.get("rejected_candidates", [])
            ],
            "rejected_candidate_assessments": [
                {**item, "reason": "The exact head does not contain the reported gap."}
                for item in template.get("rejected_candidate_assessments", [])
            ],
        }
    )
    return result


def test_thread_matrix_decides_all_six_cases(fixture: ReviewFixture) -> None:
    """Decision 75.5 verbatim: closed+none -> no_reply; closed+problem ->
    reply+reopen; open+fixed -> reply+resolve; open+unattempted -> no_reply;
    open+attempted -> reply; open+not confirmed -> reply+resolve. Each case
    runs its own fresh cycle: a published plan makes the same evidence stale
    for a second scaffold by design."""

    def case(
        review_fixture: ReviewFixture,
        assessment: str,
        outcome: str,
        response: str | None,
        **extra: Any,
    ) -> dict[str, Any]:
        root, evidence, context_path, template = _prepare(review_fixture)
        row = {
            **dict(template["thread_decisions"][0]),
            "assessment": assessment,
            "rationale": "Verified against the exact head.",
            "outcome": outcome,
            "proposed_response": response,
            "fix_mode": extra.pop("fix_mode", "not_required"),
            "patch": None,
            "severity": "low",
        }
        row.update(extra)
        content = _fill({**template, "thread_decisions": [row]})
        path = review_fixture.tmp / "content-matrix.json"
        contract.write_json(path, content)
        progress = review_context.load_progress(root) or {}
        return cast(
            "dict[str, Any]",
            review_context.scaffold_review(
                evidence, context_path, str(progress["decision_path"]), str(path)
            ),
        )

    resolved_fixture = make_review_fixture({"resolved": True})
    try:
        # closed + no problem -> no_reply
        threads = _plan_threads(case(resolved_fixture, "false_positive", "no_reply", None))
        assert threads[0]["outcome"] == "no_reply"
        # closed + problem -> reply + reopen
        threads = _plan_threads(
            case(
                resolved_fixture,
                "accepted",
                "reopen",
                "issue: The defect persists on the exact head.",
            )
        )
        assert threads[0]["outcome"] == "reopen"
        # closed + closing assessment never reopens
        with pytest.raises(
            contract.WorkflowError, match="a closing assessment keeps a resolved thread closed"
        ):
            case(resolved_fixture, "fixed", "reopen", "note: Reopened by mistake.")
    finally:
        resolved_fixture.close()

    # open + fixed -> reply + resolve
    threads = _plan_threads(
        case(fixture, "fixed", "resolve", "praise: The exact head fixes the reported path.")
    )
    assert threads[0]["outcome"] == "resolve"
    # open + confirmed, no attempt -> no_reply (the renamed allowance)
    threads = _plan_threads(case(fixture, "accepted", "no_reply", None))
    assert threads[0]["outcome"] == "no_reply"
    # open + attempted fix -> reply (a grouped suggestion proves the attempt)
    threads = _plan_threads(
        case(
            fixture,
            "accepted",
            "reply",
            "suggestion: The attempted fix lands on the head.",
            fix_mode="suggestion",
            suggestions=[
                {
                    "path": "review.txt",
                    "line": 2,
                    "body": "```suggestion\nreviewed change with the key\n```",
                }
            ],
        )
    )
    assert threads[0]["outcome"] == "reply"
    # open + not confirmed -> reply + resolve
    threads = _plan_threads(
        case(fixture, "false_positive", "resolve", "note: The reported gap is not real.")
    )
    assert threads[0]["outcome"] == "resolve"
    # open + confirmed + reply without a fix is the refused shape
    with pytest.raises(
        contract.WorkflowError, match="an unattempted confirmed defect adds no reply yet"
    ):
        case(fixture, "accepted", "reply", "issue: No fix attempt exists yet.")


def test_published_answers_require_their_conventional_comments_label(
    fixture: ReviewFixture,
) -> None:
    """Decision 75.6 (MR !517/!538 evidence): real runbooks carried zero CC
    marks; the validator now refuses an unlabeled published answer and the
    label renders in the runbook."""
    root, evidence, context_path, template = _prepare(fixture)
    row = {
        **dict(template["thread_decisions"][0]),
        "assessment": "fixed",
        "rationale": "Verified against the exact head.",
        "outcome": "resolve",
        "proposed_response": "The exact head fixes the reported path.",
        "fix_mode": "not_required",
        "patch": None,
        "severity": "low",
    }
    content = _fill({**template, "thread_decisions": [row]})
    path = fixture.tmp / "content-unlabeled.json"
    contract.write_json(path, content)
    progress = review_context.load_progress(root) or {}
    with pytest.raises(
        contract.WorkflowError, match="a published reply opens with its Conventional"
    ):
        review_context.scaffold_review(
            evidence, context_path, str(progress["decision_path"]), str(path)
        )
    row["proposed_response"] = "praise: The exact head fixes the reported path."
    content = _fill({**template, "thread_decisions": [row]})
    contract.write_json(path, content)
    plan = review_context.scaffold_review(
        evidence, context_path, str(progress["decision_path"]), str(path)
    )
    assert "praise:" in Path(str(plan["markdown_path"])).read_text(encoding="utf-8")


def test_auto_session_publishes_ready_comments_and_one_proposal(
    fixture: ReviewFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    """Decision 75.3: the auto runbook carries finding comments without
    suggestions or patches plus one ready metadata proposal comment (SemVer,
    labels, title, description, milestone) - no per-item shell commands."""
    args = [
        "run",
        "--url",
        fixture.url,
        "--repo-root",
        str(fixture.repo),
        "--review-mode",
        "fast",
        "--session-mode",
        "auto",
        "--fix-policy",
        "none",
    ]
    assert main(args) == 0
    decision_stop = json.loads(capsys.readouterr().out)
    decision_path = Path(decision_stop["template_path"])
    decision = contract.read_json(decision_path, "decision")
    decision.update(run_id="auto-primary-run", session_id="auto-primary-session")
    finding = {
        "id": "docs-1",
        "severity": "low",
        "summary": "Retry documentation omits the idempotency key",
        "risk": "Operators can deploy the retry without the required key.",
        "evidence": ["The reviewed README documents the retry without the key argument."],
        "consequence": "A deployment following the documented steps repeats writes.",
        "relation_to_change": "The reviewed change introduces the retry path.",
        "minimum_fix": "Document the idempotency key next to the retry example.",
    }
    decision["findings"] = [finding]
    decision["responses"] = [
        {**response, "reason": "Verified the exact reviewed code."}
        for response in decision["responses"]
    ]
    decision["responses"].append(
        {"id": "docs-1", "decision": "accept", "reason": "Confirmed on the exact head."}
    )
    contract.write_json(decision_path, decision)
    assert main(decision_stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    prose_stop = json.loads(capsys.readouterr().out)
    assert prose_stop["template_kind"] == "prose"
    prose = contract.read_json(Path(prose_stop["template_path"]), "prose")
    # fix=none: every prepared publication is the comment-only variant.
    for row in prose["finding_publications"]:
        assert row["publication"]["fix_mode"] == "not_required"
    filled = dict(prose)
    filled.update(
        summary="The change is small and preserves the reviewed contract.",
        architecture_assessment="The responsibility remains with its owner.",
        chat_assessment={
            "necessity": {"status": "supported", "rationale": "The change is complete."},
            "relevance": {"status": "current", "rationale": "The exact head is current."},
            "change": "The change keeps the reviewed contract intact.",
        },
        semver_impact="patch",
        semver_rationale="Backward-compatible correction.",
        semver_assessment={
            **prose["semver_assessment"],
            "policy": "No release policy was found in the fixture.",
        },
        mr_metadata_assessment={
            field: {
                "status": "ok",
                "rationale": f"The observed {field} is sufficient.",
                "recommendation": None,
            }
            for field in prose["mr_metadata_assessment"]
        },
        label_assessments=[
            {
                **row,
                "status": "applicable" if row["name"] == "semver::patch" else "inapplicable",
                "rationale": "Matches the assessed patch contribution.",
            }
            for row in prose["label_assessments"]
        ],
        checks=["Compared the exact base and head revisions."],
    )
    for row in filled["finding_publications"]:
        row["body"] = "issue: The reviewed retry path needs the documented key."
    for row in filled["thread_decisions"]:
        row.update(
            assessment="fixed",
            rationale="The exact reviewed code addresses the remark.",
            outcome="resolve",
            proposed_response="praise: The exact reviewed code handles this path.",
        )
    for row in filled.get("rejected_candidates", []):
        row["reason"] = "Not observable in the exact reviewed head."
    for row in filled.get("rejected_candidate_assessments", []):
        row["reason"] = "The exact head does not contain the reported gap."
    contract.write_json(Path(prose_stop["template_path"]), filled)
    code = main(prose_stop["manual_argv"][1:])
    assert code == 0, json.loads(capsys.readouterr().out)
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["stage"] == "plan_ready", final
    runbook = Path(final["report"]["publication_plan_path"]).read_text(encoding="utf-8")
    assert "Metadata proposal comment (auto mode)" in runbook
    assert "no command is generated" in runbook
    assert "```shell" not in runbook
    assert "issue: The reviewed retry path needs the documented key." in runbook
    progress = review_context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    proposal = plan["publication_preview"]["proposal"]
    assert proposal["publication_id"] == "metadata-proposal"
    assert proposal["body"].startswith("note: ")


def test_auto_mode_refuses_a_fix_policy_and_manual_allows_each(
    fixture: ReviewFixture,
) -> None:
    """Auto forces fix=none at the runtime boundary; the thread validators
    enforce the same policy inside the plan."""
    with pytest.raises(contract.WorkflowError, match="review mode or locale cannot initialize"):
        review_context.begin_review(
            *_begin_args(fixture, session_mode="auto", fix_policy="suggestion")
        )
    root, evidence, context_path, template = _prepare(
        fixture, session_mode="auto", fix_policy="none"
    )
    row = {
        **dict(template["thread_decisions"][0]),
        "assessment": "accepted",
        "rationale": "The defect is confirmed on the exact head.",
        "outcome": "no_reply",
        "proposed_response": None,
        "fix_mode": "not_required",
        "patch": None,
    }
    row["fix_mode"] = "suggestion"
    content = _fill({**template, "thread_decisions": [row]})
    path = fixture.tmp / "content-policy.json"
    contract.write_json(path, content)
    progress = review_context.load_progress(root) or {}
    with pytest.raises(contract.WorkflowError, match="the session fix policy publishes no code"):
        review_context.scaffold_review(
            evidence, context_path, str(progress["decision_path"]), str(path)
        )


def _begin_args(
    fixture: ReviewFixture, *, session_mode: str, fix_policy: str | None
) -> tuple[str, str, str, str, str, str, str, str, str | None]:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    bundle = cast("dict[str, Any]", contract.collect(target, "code-review"))
    return (
        str(bundle["preview_artifact_path"]),
        str(bundle["preview_digest"]),
        str(bundle["artifact_root"]),
        str(fixture.repo),
        "fast",
        "en",
        "auto",
        session_mode,
        fix_policy,
    )


def test_profiles_are_explicit_setup_and_read_only(
    fixture: ReviewFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 75.2: a profile is written only by the explicit setup command;
    reading a missing profile answers with the setup instruction."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    missing = profiles.read_profile("work")
    assert missing["status"] == "missing"
    assert "profile-setup --name" in missing["instruction"]
    assert main(["profile-setup", "--name", "work", "--locale", "ru", "--fix-policy", "none"]) == 0
    stored = profiles.read_profile("work")
    assert stored["status"] == "ok"
    assert stored["profile"]["locale"] == "ru"
    assert stored["profile"]["fix_policy"] == "none"
    stored_path = tmp_path / "config" / "agent-skills" / "code-review" / "profiles" / "work.json"
    assert stored_path.is_file()
    with pytest.raises(contract.WorkflowError, match="profile name must match"):
        profiles.profile_path("../escape")


def _plan_threads(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The scaffold answer carries the plan artifact payload, not bare rows."""
    progressless = plan.get("thread_decisions")
    if progressless is not None:
        return cast("list[dict[str, Any]]", progressless)
    _, payload = contract.artifact_payload(Path(str(plan["artifact_path"])), "review_plan")
    return cast("list[dict[str, Any]]", payload["thread_decisions"])
