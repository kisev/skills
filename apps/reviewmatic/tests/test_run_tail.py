"""The shared renderer is reached through the real run, not a draft-only path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context, render, tail
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


def output(capsys: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(capsys.readouterr().out))


def test_run_content_stop_is_the_prose_surface(fixture: ReviewFixture, capsys: Any) -> None:
    args = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo), "--review-mode", "fast"]
    assert main(args) == 0
    decision_stop = output(capsys)
    decision_path = Path(decision_stop["template_path"])
    decision = contract.read_json(decision_path, "decision")
    decision.update(run_id="native-primary-run", session_id="native-primary-session")
    for response in decision["responses"]:
        response["reason"] = "Verified the exact reviewed code."
    contract.write_json(decision_path, decision)
    assert main(decision_stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    prose_stop = output(capsys)
    assert prose_stop["template_kind"] == "prose"
    assert Path(prose_stop["template_path"]).name.startswith("content-prose-")
    prose = contract.read_json(Path(prose_stop["template_path"]), "prose")
    assert "findings" not in prose
    assert "target_sha" not in prose["semver_assessment"]
    assert prose["semver_assessment"]["sources"]
    assert (
        "current target branch commit unavailable locally"
        in prose["semver_assessment"]["fallback_reason"]
    )
    assert "thread_sha256" not in prose["thread_decisions"][0]
    assert "record-prose" in prose_stop["manual_command"]


def test_multiline_target_derives_the_range(fixture: ReviewFixture) -> None:
    target = {"path": "review.txt", "before": "base\nreviewed change"}
    row = render.targeted_suggestion(
        fixture.repo,
        fixture.base_sha,
        fixture.head_sha,
        target,
        "base\nkeyed retry",
        "Keep the key across retries.",
    )
    assert row["path"] == "review.txt"
    assert row["line"] == 2
    assert "```suggestion:-1+0\nbase\nkeyed retry\n```" in row["body"]
    context.validate_suggestion(
        row["body"],
        repo_root=fixture.repo,
        head_sha=fixture.head_sha,
        path=row["path"],
        line=row["line"],
    )


def test_semantic_parts_derive_every_position_and_pass_the_fix_validator(
    fixture: ReviewFixture,
) -> None:
    content = {
        "finding_publications": [
            {
                "finding_id": "parts-1",
                "type": "general",
                "path": None,
                "line": None,
                "old_line": None,
                "body": "<BODY: explain the fix>",
                "fix_mode": "suggestion",
                "patch": None,
            }
        ]
    }
    incoming = {
        "finding_publications": [
            {
                "finding_id": "parts-1",
                "body": "Keep each independent line safe.",
                "parts": [
                    {
                        "target": {"path": "review.txt", "before": "base"},
                        "replacement": "safe base",
                    },
                    {
                        "target": {"path": "review.txt", "before": "reviewed change"},
                        "replacement": "keyed retry",
                    },
                ],
                "split_rationale": "The independent lines remain valid when applied separately.",
            }
        ]
    }
    evidence = {"base_sha": fixture.base_sha, "head_sha": fixture.head_sha}
    review_context = {"exact_git": {"repo_root": str(fixture.repo)}}
    resolved = render.resolve_prose_fixes(content, incoming, review_context, evidence)
    result = render.apply_prose(content, resolved)
    rows = context.validate_finding_publications(result["finding_publications"], {"parts-1"})
    assert [part["line"] for part in rows[0]["suggestions"]] == [1, 2]


def test_presentation_scrub_preserves_fix_code_and_revision_links(fixture: ReviewFixture) -> None:
    sha = fixture.head_sha
    raw = f"Proof at {sha}. [Revision](https://gitlab.example/g/p/-/commit/{sha})\n\n```suggestion\nuse({sha})\n```"
    displayed = render.copied_presentation(raw, {"head_sha": sha}, {})
    assert "Proof at reviewed revision" in displayed
    assert f"/commit/{sha}" in displayed
    assert f"use({sha})" in displayed  # a fix is never silently changed by scrubbing


def fill_prose(prose: dict[str, Any]) -> dict[str, Any]:
    """Only judgment and fix payloads; no stamps, positions, or revisions."""
    result = dict(prose)
    result.update(
        summary="The retry change is bounded.",
        architecture_assessment="Existing ownership is preserved.",
        chat_assessment={
            "necessity": {"status": "supported", "rationale": "The retry needs a key."},
            "relevance": {"status": "current", "rationale": "Checked the exact head."},
            "change": "Bound the retry write.",
        },
        semver_impact="patch",
        semver_rationale="Backward-compatible correction.",
        semver_assessment={
            **prose["semver_assessment"],
            "policy": "No release policy found.",
            "sources": prose["semver_assessment"]["sources"],
            "fallback_reason": prose["semver_assessment"]["fallback_reason"],
            "release_impact": "patch"
            if prose["semver_assessment"]["release_impact"] is not None
            else None,
            "release_rationale": "Backward-compatible correction to the released retry contract."
            if prose["semver_assessment"]["release_impact"] is not None
            else None,
        },
        mr_metadata_assessment={
            name: {
                "status": "ok",
                "rationale": "Sufficient observed metadata.",
                "recommendation": None,
            }
            for name in prose["mr_metadata_assessment"]
        },
        label_assessments=[
            {
                **row,
                "status": "applicable" if row["name"] == "semver::patch" else "inapplicable",
                "rationale": "Matches the contribution.",
            }
            for row in prose["label_assessments"]
        ],
        checks=["Read the exact committed retry path."],
        thread_decisions=[
            {
                **row,
                "assessment": "fixed",
                "rationale": "The head handles the reported path.",
                "outcome": "resolve",
                "proposed_response": "Checked the exact retry path.",
            }
            for row in prose["thread_decisions"]
        ],
    )
    for row in result.get("rejected_candidates", []):
        row["reason"] = "Not observed on the exact head."
    for row in result.get("rejected_candidate_assessments", []):
        row["reason"] = "Not observed on the exact head."
    return result


def test_panel_run_render_prose_finalize_without_structural_authoring(
    fixture: ReviewFixture, capsys: Any
) -> None:
    participants = fixture.tmp / "participants.json"
    contract.write_json(
        participants, {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arb-1"}}
    )
    args = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    assert main([*args, "--participants", str(participants)]) == 0
    critic_stop = output(capsys)
    critic_path = Path(critic_stop["template_path"])
    critic = contract.read_json(critic_path, "critic")
    critic.update(run_id="critic-native-run", session_id="critic-native-session")
    contract.write_json(critic_path, critic)
    assert main(critic_stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    decision_stop = output(capsys)
    decision_path = Path(decision_stop["template_path"])
    decision = contract.read_json(decision_path, "decision")
    decision.update(run_id="arb-native-run", session_id="arb-native-session")
    for response in decision["responses"]:
        response["reason"] = "Confirmed on the exact head."
    contract.write_json(decision_path, decision)
    assert main(decision_stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    prose_stop = output(capsys)
    assert prose_stop["template_kind"] == "prose"
    prose_path = Path(prose_stop["template_path"])
    prose = contract.read_json(prose_path, "prose")
    contract.write_json(prose_path, fill_prose(prose))
    assert main(prose_stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    assert final["report"]["status"] == "ok"
    assert (Path(final["artifact_root"]) / "runbook.md").is_file()


FINDING = {
    "id": "prior-retry",
    "severity": "low",
    "summary": "Retry policy omits the key.",
    "risk": "Retry can repeat a write.",
    "evidence": ["The retry policy requires a stable key."],
    "consequence": "Writes can duplicate.",
    "relation_to_change": "The change introduces the retry.",
    "minimum_fix": "Document the key.",
}
PATCH = (
    "diff --git a/retry-policy.txt b/retry-policy.txt\nnew file mode 100644\n--- /dev/null\n+++ b/retry-policy.txt\n"
    "@@ -0,0 +1 @@\n+reserve idempotency key\n"
)
ISSUE = {
    "id": "prior-followup",
    "title": "Verify retention separately",
    "problem": "Retention is not bounded.",
    "evidence": ["The retention consumer is outside the retry scope."],
    "minimum_fix": "Bound retention.",
    "importance": "Operators need predictable retention.",
    "risk": "Records can accumulate.",
    "reason_out_of_scope": "Retention is an independent contract.",
    "existing_task": None,
}


def complete_run(
    fixture: ReviewFixture,
    capsys: Any,
    sequence: int,
    *,
    changed: bool = False,
    finding_id: str = "prior-retry",
    include_issue: bool = True,
    reject_candidate: bool = False,
    basis: dict[str, str] | None = None,
) -> dict[str, Any]:
    finding = {**FINDING, "id": finding_id}
    args = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    selection = fixture.tmp / "panel-selection.json"
    contract.write_json(
        selection, {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arb-1"}}
    )
    assert main([*args, "--participants", str(selection)]) == 0
    stop = output(capsys)
    path = Path(stop["template_path"])
    receipt = contract.read_json(path, "critic")
    receipt.update(
        run_id=f"critic-native-run-{sequence}",
        session_id=f"critic-native-session-{sequence}",
        findings=[
            finding,
            {**finding, "id": "unsupported", "summary": "Retention consumer duplicates writes."},
        ]
        if reject_candidate
        else [finding],
    )
    contract.write_json(path, receipt)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    path = Path(stop["template_path"])
    decision = contract.read_json(path, "decision")
    decision.update(
        run_id=f"arb-native-run-{sequence}", session_id=f"arb-native-session-{sequence}"
    )
    for response in decision["responses"]:
        response["reason"] = "Verified the exact retry and its dependencies."
        if response["id"] == "unsupported":
            response.update(
                decision="reject", reason="The current retention consumer is outside this change."
            )
    decision["publication_intents"] = [
        {"finding_id": finding_id, "publication": {"kind": "general", "fix_mode": "patch"}}
    ]
    contract.write_json(path, decision)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    path = Path(stop["template_path"])
    prose = fill_prose(contract.read_json(path, "prose"))
    if basis is not None:
        prose["semver_assessment"].update(
            basis=basis,
            fallback_reason=None,
            release_impact="patch",
            release_rationale="Backward-compatible correction on the selected maintenance line.",
        )
    prose["finding_publications"][0].update(
        body="Keep the same retry key."
        if not changed
        else "Keep the key across the new retry path.",
        patch=PATCH,
        patch_reason="The policy file is new and has no existing suggestion anchor.",
    )
    if include_issue and not prose["recommended_issues"]:
        prose["recommended_issues"] = [ISSUE]
    contract.write_json(path, prose)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    if basis is not None:
        addressed = fixture.tmp / "semver-preserved.json"
        contract.write_json(
            addressed, {"summary": "The maintenance-line retry correction is bounded."}
        )
        assert (
            main(
                [
                    "record-prose",
                    "--artifact-root",
                    stop["artifact_root"],
                    "--input",
                    str(addressed),
                ]
            )
            == 0
        )
        capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready", final
    root = Path(final["artifact_root"])
    progress = context.load_progress(root)
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    return plan


def test_run_reuses_rejected_candidate_reason_and_complete_label_form(
    fixture: ReviewFixture, capsys: Any
) -> None:
    plan = complete_run(fixture, capsys, 1, reject_candidate=True)
    assert (
        plan["rejected_candidates"][0]["reason"]
        == "The current retention consumer is outside this change."
    )
    assert plan["rejected_candidates"][0]["finding"]["id"] == "unsupported"
    assert len(plan["label_review"]["assessments"]) == 4
    source = plan["review_source"]["run_authoring"]
    assert all(
        set(row) == {"name", "status", "rationale"} for row in source["prose"]["label_assessments"]
    )


def test_run_derives_semver_basis_and_accepts_a_semantic_line_choice(
    fixture: ReviewFixture, capsys: Any
) -> None:
    fixture.config_path.write_text(
        json.dumps(
            {
                **fixture.read_config(),
                "targetSha": fixture.base_sha,
                "releases": [
                    {"tag_name": "v1.0.0", "commit": {"id": fixture.base_sha}},
                    {"tag_name": "v2.0.0", "commit": {"id": fixture.base_sha}},
                    {"tag_name": "maintenance-v1.0.0", "commit": {"id": fixture.base_sha}},
                ],
            }
        )
    )
    plan = complete_run(
        fixture, capsys, 1, basis={"name": "maintenance-v1.0.0", "source": "releases"}
    )
    assessment = plan["semver_assessment"]
    assert assessment["mode"] == "release"
    assert assessment["baseline"] == {
        "name": "maintenance-v1.0.0",
        "sha": fixture.base_sha,
        "source": "releases",
    }
    assert assessment["fallback_reason"] is None
    assert assessment["target_sha"] == fixture.base_sha
    assert "baseline" not in plan["review_source"]["run_authoring"]["prose"]["semver_assessment"]


def test_run_history_is_context_not_required_authorship(
    fixture: ReviewFixture, capsys: Any
) -> None:
    first = complete_run(fixture, capsys, 1)
    advance_head(fixture, "base\nreviewed change\nsecond retry\n")
    second = complete_run(fixture, capsys, 2, finding_id="current-retry", include_issue=False)
    assert second["findings"][0]["id"] == "current-retry"
    assert second["finding_publications"][0]["revision"] == 1
    assert second["recommended_issues"] == []
    assert second["previous_finding_assessments"] == []
    assert first["recommended_issues"][0]["id"] == ISSUE["id"]
    history = second["incremental"]["history_context"]
    assert history["snapshot"]["head_sha"] == fixture.head_sha
    assert history["findings"][0]["id"] == FINDING["id"]
    assert history["decisions"][0]["reason"] == "Verified the exact retry and its dependencies."


@pytest.mark.parametrize("history_kind", ["release", "contract"])
def test_run_incompatible_history_warns_and_finishes_full(
    fixture: ReviewFixture, capsys: Any, history_kind: str
) -> None:
    first = complete_run(fixture, capsys, 1)
    root = next((fixture.tmp / "state" / "agent-skills" / "gitlab").iterdir())
    artifacts = {path: path.read_bytes() for path in (root / "artifacts").glob("*/*.json")}
    advance_head(fixture, "base\nreviewed change\nsecond retry\n")
    if history_kind == "release":
        config = fixture.read_config()
        config["targetSha"] = fixture.base_sha
        fixture.config_path.write_text(json.dumps(config))
    else:
        pointer_path = root / context.BASELINE_NAME
        pointer = contract.read_json(pointer_path, "baseline")
        pointer["contract_version"] = 99
        contract.write_json(pointer_path, pointer)
    second = complete_run(fixture, capsys, 2, finding_id="current-retry", include_issue=False)
    assert second["incremental"]["mode"] == "full"
    history = second["incremental"]["history_context"]
    if history_kind == "release":
        assert "release evidence or target branch changed" in history["warnings"]
        assert history["recommended_issues"] == first["recommended_issues"]
    else:
        assert any("contract is incompatible" in warning for warning in history["warnings"])
    assert second["previous_finding_assessments"] == []
    assert all(path.read_bytes() == body for path, body in artifacts.items())


def advance_head(fixture: ReviewFixture, content: str) -> str:
    (fixture.repo / "review.txt").write_text(content)
    fixture.git("add", "review.txt")
    fixture.git("commit", "-m", "advance review fixture")
    head = fixture.head()
    fixture.git("push", "-q", "origin", "main")
    fixture._git(fixture.origin, "update-ref", "refs/merge-requests/7/head", head)
    fixture.config_path.write_text(json.dumps({**fixture.read_config(), "headSha": head}))
    return head


def test_full_incremental_run_does_not_inherit_revisions(
    fixture: ReviewFixture, capsys: Any
) -> None:
    first = complete_run(fixture, capsys, 1)
    assert first["finding_publications"][0]["revision"] == 1
    advance_head(fixture, "base\nreviewed change\nsecond retry\n")
    second = complete_run(fixture, capsys, 2)
    assert second["findings"][0]["id"] == FINDING["id"]
    assert second["finding_publications"][0]["revision"] == 1
    advance_head(fixture, "base\nreviewed change\nsecond retry\nthird retry\n")
    third = complete_run(fixture, capsys, 3, changed=True)
    assert third["findings"][0]["id"] == FINDING["id"]
    assert third["finding_publications"][0]["revision"] == 1
    assert third["previous_finding_assessments"] == []
    assert contract.finding_publications_are_valid(
        third["finding_publications"], require_fixes=True
    )


def authored_line_run(
    fixture: ReviewFixture,
    capsys: Any,
    *,
    before: str = "reviewed change",
    existing_thread: bool = False,
    multipart: bool = False,
) -> tuple[list[str], dict[str, Any], dict[str, Any], Path]:
    args = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    selection = fixture.tmp / "line-panel.json"
    contract.write_json(
        selection, {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arb-1"}}
    )
    assert main([*args, "--participants", str(selection)]) == 0
    stop = output(capsys)
    path = Path(stop["template_path"])
    receipt = contract.read_json(path, "critic")
    receipt.update(
        run_id="historical-critic-run", session_id="historical-critic-session", findings=[FINDING]
    )
    receipt["findings"][0] = {
        **FINDING,
        "evidence": [f"Observed on {fixture.head_sha} in review.txt."],
    }
    contract.write_json(path, receipt)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    root = Path(stop["artifact_root"])
    progress = context.load_progress(root)
    assert progress is not None
    receipt_path = Path(progress["critic_receipt_path"])
    path = Path(stop["template_path"])
    decision = contract.read_json(path, "decision")
    decision.update(run_id="historical-arb-run", session_id="historical-arb-session")
    for response in decision["responses"]:
        response["reason"] = "Confirmed on the exact reviewed head."
    decision["publication_intents"] = [
        {
            "finding_id": FINDING["id"],
            "publication": {
                "kind": "existing_thread"
                if existing_thread
                else "general"
                if multipart
                else "line",
                "fix_mode": "suggestion",
                "target": {"path": "review.txt", "before": before},
            },
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": ["42"] if existing_thread else [],
                "metadata_fields": [],
                "ci": False,
            },
        }
    ]
    contract.write_json(path, decision)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    path = Path(stop["template_path"])
    prose = fill_prose(contract.read_json(path, "prose"))
    prose["checks"] = [f"Inspected CI and retry code on {fixture.head_sha}."]
    prose["semver_assessment"]["sources"] = [f"Policy inspection at {fixture.head_sha}."]
    prose["finding_publications"][0]["body"] = "Keep the verified key across retries."
    if existing_thread:
        prose["thread_decisions"][0].update(
            assessment="accepted",
            outcome="reply",
            fix_mode="suggestion",
            proposed_response="Keep the key on the reviewed retry path.",
            target={"path": "review.txt", "before": before},
            replacement="base\nkeyed retry" if before == "base\nreviewed change" else "keyed retry",
        )
    elif multipart:
        prose["finding_publications"][0].update(
            parts=[
                {"target": {"path": "review.txt", "before": "base"}, "replacement": "safe base"},
                {
                    "target": {"path": "review.txt", "before": "reviewed change"},
                    "replacement": "keyed retry",
                },
            ],
            split_rationale="The independent lines remain valid when applied separately.",
        )
    else:
        prose["finding_publications"][0]["replacement"] = (
            "base\nkeyed retry" if before == "base\nreviewed change" else "keyed retry"
        )
    contract.write_json(path, prose)
    assert main(stop["manual_argv"][1:]) == 0
    capsys.readouterr()
    return args, stop, prose, receipt_path


def test_real_run_preserves_a_multiline_goal_through_render_and_apply(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, _stop, authored, _receipt = authored_line_run(
        fixture, capsys, before="base\nreviewed change"
    )
    assert authored["finding_publications"][0]["target"]["before"] == "base\nreviewed change"
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    body = plan["finding_publications"][0]["body"]
    assert "```suggestion:-1+0\nbase\nkeyed retry\n```" in body


def test_run_derives_multiline_thread_fix_positions_from_semantic_input(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, _stop, authored, _receipt = authored_line_run(
        fixture, capsys, before="base\nreviewed change", existing_thread=True
    )
    assert "suggestions" not in authored["thread_decisions"][0]
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    suggestion = plan["thread_decisions"][0]["suggestions"][0]
    assert suggestion["line"] == 2
    assert "```suggestion:-1+0\nbase\nkeyed retry\n```" in suggestion["body"]


def test_run_addressed_update_preserves_semantic_parts(fixture: ReviewFixture, capsys: Any) -> None:
    args, stop, authored, _receipt = authored_line_run(fixture, capsys, multipart=True)
    patch = fixture.tmp / "parts-preserved.json"
    contract.write_json(patch, {"summary": "Only clarified the summary."})
    assert (
        main(["record-prose", "--artifact-root", stop["artifact_root"], "--input", str(patch)]) == 0
    )
    capsys.readouterr()
    state = tail.load(Path(stop["artifact_root"]))
    assert state is not None
    parts = state["prose"]["finding_publications"][0]["parts"]
    assert [(row["target"], row["replacement"]) for row in parts] == [
        (row["target"], row["replacement"]) for row in authored["finding_publications"][0]["parts"]
    ]
    assert main([*args, "--resume"]) == 0
    assert output(capsys)["stage"] == "plan_ready"


def confirm_delta(
    stop: dict[str, Any], capsys: Any, *, altered: bool = False, thread_response: str | None = None
) -> dict[str, Any]:
    path = Path(stop["template_path"])
    check = contract.read_json(path, "delta")
    check.update(run_id="delta-native-run", session_id="delta-native-session")
    for row in check["checks"]:
        row.update(
            verdict="confirmed", evidence="Inspected the new delta and the affected consumers."
        )
        if thread_response is not None and row["id"] == "thread:42":
            row["evidence"] = (
                "Read reply 43 and checked the alternate consumer against the unchanged exact head."
            )
            row["prose"] = {
                "thread_decisions": [
                    {
                        "id": "42",
                        "rationale": "The alternate consumer also preserves the retry key.",
                        "proposed_response": thread_response,
                    }
                ]
            }
        if altered and row["id"] == FINDING["id"]:
            row.update(
                verdict="changed",
                evidence="The failure is now on the renamed retry path.",
                resolution="revise",
                finding={**FINDING, "summary": "The new retry path still lacks the key."},
            )
    contract.write_json(path, check)
    assert main(stop["manual_argv"][1:]) == 0
    return output(capsys)


def test_drift_delta_check_carries_authorship_and_preserves_original_receipt(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, prose_stop, authored, receipt_path = authored_line_run(fixture, capsys)
    original_receipt = receipt_path.read_bytes()
    advance_head(fixture, "base\nintro\nreviewed change\n")
    assert main([*args, "--resume"]) == 0
    delta = output(capsys)
    assert delta["template_kind"] == "delta"
    assert delta["prose_path"] == prose_stop["template_path"]
    assert contract.read_json(Path(delta["prose_path"]), "prose") == authored
    assert FINDING["id"] in {row["id"] for row in delta["targets"]}
    assert confirm_delta(delta, capsys)["status"] == "ok"
    assert receipt_path.read_bytes() == original_receipt
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready", final
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    assert plan["review_source"]["run_authoring"]["content"]["summary"] == authored["summary"]
    assert plan["finding_publications"][0]["line"] == 3
    assert "Keep the verified key across retries." in plan["markdown"]
    context.reject_visible_raw_refs(plan["markdown"], {"head_sha": fixture.head_sha}, {})
    for body in plan["publication_preview"]["body_files"]:
        assert Path(body["path"]).read_text() == body["content"]
        context.reject_visible_raw_refs(body["content"], {"head_sha": fixture.head_sha}, {})


def test_ci_only_drift_checks_ci_without_reanalysing_code(
    fixture: ReviewFixture, capsys: Any
) -> None:
    fixture.config_path.write_text(
        json.dumps({**fixture.read_config(), "pipelineStatus": "running"})
    )
    args, prose_stop, authored, receipt_path = authored_line_run(fixture, capsys)
    original = receipt_path.read_bytes()
    fixture.config_path.write_text(
        json.dumps({**fixture.read_config(), "pipelineStatus": "success"})
    )
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    assert stop["template_kind"] == "delta"
    assert stop["scope"]["changed_paths"] == []
    assert [row["id"] for row in stop["targets"]] == ["ci"]
    assert confirm_delta(stop, capsys)["status"] == "ok"
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    assert receipt_path.read_bytes() == original
    assert contract.read_json(Path(prose_stop["template_path"]), "prose") == authored
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    assert plan["verdict"] == "ready"


def test_run_addressed_prose_update_keeps_other_rows_and_refuses_unknown_ids(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, stop, authored, _receipt = authored_line_run(fixture, capsys)
    root = Path(stop["artifact_root"])
    before = (root / tail.NAME).read_bytes()
    patch = fixture.tmp / "addressed.json"
    contract.write_json(
        patch, {"finding_publications": [{"finding_id": "forged", "body": "Replace it."}]}
    )
    assert main(["record-prose", "--artifact-root", str(root), "--input", str(patch)]) == 2
    refusal = output(capsys)
    assert "finding_publications[*].finding_id" in refusal["error"]["message"]
    assert (root / tail.NAME).read_bytes() == before
    contract.write_json(
        patch,
        {
            "summary": "Addressed clarification only.",
            "label_assessments": [authored["label_assessments"][0]],
        },
    )
    assert main(["record-prose", "--artifact-root", str(root), "--input", str(patch)]) == 0
    capsys.readouterr()
    state = tail.load(root)
    assert state is not None
    assert len(state["prose"]["label_assessments"]) == 4
    assert state["prose"]["finding_publications"] == authored["finding_publications"]
    assert state["prose"]["thread_decisions"] == authored["thread_decisions"]
    advance_head(fixture, "base\nintro\nreviewed change\n")
    assert main([*args, "--resume"]) == 0
    delta = output(capsys)
    assert confirm_delta(delta, capsys)["status"] == "ok"
    assert main([*args, "--resume"]) == 0
    assert output(capsys)["stage"] == "plan_ready"


def test_new_comment_is_checked_without_losing_authorship(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, prose_stop, authored, receipt_path = authored_line_run(fixture, capsys)
    original = receipt_path.read_bytes()
    fixture.config_path.write_text(
        json.dumps(
            {
                **fixture.read_config(),
                "replies": [
                    {
                        "id": 43,
                        "system": False,
                        "author": {"username": "other-reviewer"},
                        "body": "What about the alternate retry consumer?",
                    }
                ],
            }
        )
    )
    assert main([*args, "--resume"]) == 0
    stop = output(capsys)
    assert stop["scope"]["changed_paths"] == []
    assert [row["id"] for row in stop["targets"]] == ["thread:42"]
    response = "The alternate consumer also keeps the same key across retries."
    assert confirm_delta(stop, capsys, thread_response=response)["status"] == "ok"
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    assert receipt_path.read_bytes() == original
    updated = contract.read_json(Path(prose_stop["template_path"]), "prose")
    assert updated["summary"] == authored["summary"]
    assert updated["finding_publications"] == authored["finding_publications"]
    assert updated["thread_decisions"][0]["proposed_response"] == response


def test_new_delta_finding_needs_only_its_missing_fix_prose(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, stop, authored, _receipt = authored_line_run(fixture, capsys)
    advance_head(fixture, "base\nintro\nreviewed change\n")
    assert main([*args, "--resume"]) == 0
    delta = output(capsys)
    check_path = Path(delta["template_path"])
    check = contract.read_json(check_path, "delta")
    check.update(run_id="novel-delta-run", session_id="novel-delta-session")
    for row in check["checks"]:
        row.update(verdict="confirmed", evidence="Checked the new scope and affected consumers.")
    check["new_findings"] = [
        {
            **FINDING,
            "id": "overflow-key",
            "summary": "The overflow retry loses its key.",
            "minimum_fix": "Specify a stable overflow key.",
        }
    ]
    check["new_dispositions"] = [
        {
            "id": "overflow-key",
            "decision": "accept",
            "reason": "Confirmed the added overflow policy gap.",
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
            "publication": {"kind": "general", "fix_mode": "patch"},
        }
    ]
    contract.write_json(check_path, check)
    assert main(delta["manual_argv"][1:]) == 0
    assert output(capsys)["status"] == "needs_targeted_repair"
    assert main([*args, "--resume"]) == 0
    repair = output(capsys)
    assert repair["template_kind"] == "prose"
    assert repair["template_path"] == stop["template_path"]
    prose = contract.read_json(Path(repair["template_path"]), "prose")
    assert prose["summary"] == authored["summary"]
    row = next(row for row in prose["finding_publications"] if row["finding_id"] == "overflow-key")
    row.update(
        body="Keep a stable key for overflow retries.",
        patch=PATCH.replace("retry-policy.txt", "overflow-policy.txt"),
        patch_reason="The policy file is new and has no suggestion anchor.",
    )
    contract.write_json(Path(repair["template_path"]), prose)
    assert main(repair["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready"
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    assert {row["id"] for row in plan["findings"]} == {FINDING["id"], "overflow-key"}


def test_drift_with_changed_conclusion_and_ambiguous_position_is_addressed_only(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, prose_stop, authored, receipt_path = authored_line_run(fixture, capsys)
    before = receipt_path.read_bytes()
    advance_head(fixture, "base\nreviewed change\nreviewed change\n")
    assert main([*args, "--resume"]) == 0
    delta = output(capsys)
    applied = confirm_delta(delta, capsys, altered=True)
    assert applied["status"] == "needs_targeted_repair"
    assert "2 matches" in applied["clarification"]
    assert receipt_path.read_bytes() == before
    assert main([*args, "--resume"]) == 0
    repair = output(capsys)
    assert repair["template_kind"] == "prose"
    assert repair["template_path"] == prose_stop["template_path"]
    assert (
        contract.read_json(Path(repair["template_path"]), "prose")["summary"] == authored["summary"]
    )
    corrected = contract.read_json(Path(repair["template_path"]), "prose")
    corrected["finding_publications"][0]["target"] = {
        "path": "review.txt",
        "before": "base\nreviewed change",
    }
    corrected["finding_publications"][0]["replacement"] = "base\nkeyed retry"
    contract.write_json(Path(repair["template_path"]), corrected)
    assert main(repair["manual_argv"][1:]) == 0
    capsys.readouterr()
    assert main([*args, "--resume"]) == 0
    final = output(capsys)
    assert final["stage"] == "plan_ready", final
    progress = context.load_progress(Path(final["artifact_root"]))
    assert progress is not None
    _, plan = contract.artifact_payload(Path(progress["plan_path"]), "review_plan")
    assert plan["findings"][0]["id"] == FINDING["id"]
    assert plan["findings"][0]["summary"] == "The new retry path still lacks the key."
    assert plan["review_source"]["run_authoring"]["content"]["summary"] == authored["summary"]


def test_unverified_delta_cannot_be_forced_ready_by_a_resolution(
    fixture: ReviewFixture, capsys: Any
) -> None:
    args, prose_stop, authored, receipt_path = authored_line_run(fixture, capsys)
    before = receipt_path.read_bytes()
    advance_head(fixture, "base\nintro\nreviewed change\n")
    assert main([*args, "--resume"]) == 0
    delta = output(capsys)
    path = Path(delta["template_path"])
    check = contract.read_json(path, "delta")
    check.update(run_id="delta-unverified-run", session_id="delta-unverified-session")
    for row in check["checks"]:
        row.update(verdict="confirmed", evidence="Inspected this changed scope.")
        if row["id"] == FINDING["id"]:
            row.update(
                verdict="not_verified",
                resolution="revise",
                evidence="The consumer could not be verified.",
            )
    contract.write_json(path, check)
    assert main(delta["manual_argv"][1:]) == 0
    result = output(capsys)
    assert result["status"] == "needs_targeted_repair"
    assert FINDING["id"] in result["affected"]
    assert receipt_path.read_bytes() == before
    assert contract.read_json(Path(prose_stop["template_path"]), "prose") == authored
    assert main([*args, "--resume"]) == 0
    assert output(capsys)["template_kind"] == "delta"
