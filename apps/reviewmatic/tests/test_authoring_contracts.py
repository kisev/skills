"""The printed authoring contracts (decision 80/A1-A10).

Every authoring surface prints its own contract: the critic receipt dictionary
with the assigned questions and the context_digest semantics, the decision
vocabularies with the blocking rule, a write-free validate-only probe, the
replace-artifact continuation, the fix=none session policy in the draft flow,
and the refreshed package materialized prefilled from the recorded one.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic import run as run_module
from reviewmatic import run_panel, workflow
from reviewmatic.cli import main as cli_main
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


def _write(fixture: ReviewFixture, name: str, value: Any) -> str:
    path = fixture.tmp / name
    contract.write_json(path, value)
    return str(path)


def _read(path: str | Path) -> dict[str, Any]:
    return contract.read_json(Path(path), "json document")


def _finding(identifier: str, summary: str, severity: str = "medium") -> dict[str, Any]:
    return {
        "id": identifier,
        "severity": severity,
        "summary": summary,
        "risk": "A retried request can duplicate a side effect.",
        "evidence": ["review.txt:2 repeats the write on the retry branch."],
        "consequence": "Duplicated writes surface as duplicated records downstream.",
        "relation_to_change": "The change touches exactly this retry path.",
        "minimum_fix": "Bind the retried write behind an idempotency key.",
    }


def _receipt(
    evidence_digest: str,
    run_id: str,
    session_id: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": evidence_digest,
        "run_id": run_id,
        "session_id": session_id,
        "findings": findings,
        "question_answers": [],
        "external_mutations": False,
    }


def _prepared_review(fixture: ReviewFixture, mode: str = "normal") -> tuple[Path, str]:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    evidence_path = str(bundle["preview_artifact_path"])
    root = Path(str(bundle["artifact_root"]))
    review_context.begin_review(
        evidence_path,
        str(bundle["preview_digest"]),
        str(root),
        str(fixture.repo),
        mode,
        "en",
        "auto",
    )
    prepared = review_context.prepare_context(evidence_path, str(fixture.repo), "auto", mode, "en")
    assert prepared["status"] == "ok"
    return root, evidence_path


def _progress(root: Path, field: str) -> Any:
    progress = review_context.load_progress(root)
    assert progress is not None
    return progress[field]


def _state(root: Path) -> dict[str, Any]:
    progress = review_context.load_progress(root)
    assert progress is not None
    return {
        "stage": progress["stage"],
        **{key: progress[key] for key in progress if key.endswith("_digest")},
        "artifacts": sorted(str(path.name) for path in (root / "artifacts").rglob("*.json")),
    }


# ---------- A1/A4/A8: the printed critic receipt contract ----------


def test_critic_receipt_contract_prints_field_dictionaries_and_rules() -> None:
    printed = review_context.critic_receipt_contract()
    assert set(printed["findings[*]"]) == {
        "id",
        "severity",
        "summary",
        "risk",
        "evidence",
        "consequence",
        "relation_to_change",
        "minimum_fix",
    }
    assert printed["findings[*]"]["severity"] == "one of: critical, high, medium, low"
    assert printed["findings[*]"]["evidence"].startswith("array")
    answers = printed["question_answers[*]"]
    assert answers["verdict"] == "one of: confirmed, refuted, not_verified"
    assert answers["context_digest"].startswith("the answered question's own context_digest")
    # A8: the digest semantics names the context package, never the evidence.
    assert "never the evidence digest" in printed["context_digest_rule"]
    # A4: the assigned-question rule is explicit about the coverage duty.
    assert "critic: true" in printed["assigned_questions_rule"]
    assert "never covers another critic's assignment" in printed["assigned_questions_rule"]


def test_draft_panel_tasks_print_the_contract_and_assigned_questions(
    fixture: ReviewFixture,
) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])
    template_path = Path(str(started["context_package"]["template_path"]))
    template = _read(template_path)
    template["goal"] = {"status": "known", "text": "Bound the retry write behind a key."}
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    template["questions"] = [
        {
            "id": "q-idempotency",
            "subject": "Does the exact head bind retried writes behind the key?",
            "source": "Primary inspection of the committed diff.",
            "critic": True,
        },
        {
            "id": "q-primary",
            "subject": "Does the change solve the problem it was made for?",
            "source": "Context-package contract.",
            "critic": False,
        },
    ]
    contract.write_json(template_path, template)
    selection = {
        "critics": [{"name": "critic-1"}],
        "arbitrator": {"name": "arbitrator-1"},
    }
    recorded_participants = draft_module.record_draft_participants(
        draft_path, _write(fixture, "participants.json", selection)
    )
    assert recorded_participants["status"] == "ok"
    recorded = draft_module.record_draft_package(draft_path, str(template_path))
    assert recorded["status"] == "ok"
    # The package response prints the receipt contract with the assigned ids.
    response_contract = recorded["critic_task"]["response_contract"]
    assert "findings[*]" in response_contract["contract"]
    assert response_contract["assigned_question_ids"] == ["q-idempotency"]
    assert "never the evidence digest" in response_contract["contract"]["context_digest_rule"]
    tasks = recorded["critic_tasks"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["contract"]["question_answers[*]"]["verdict"].startswith("one of:")
    assert task["assigned_question_ids"] == ["q-idempotency"]
    assert "never open a schema" in task["rules"]


def test_run_panel_stop_prints_the_contract_for_the_pending_critic(
    fixture: ReviewFixture,
) -> None:
    root, _evidence_path = _prepared_review(fixture)
    selection_path = _write(
        fixture,
        "participants.json",
        {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arbitrator-1"}},
    )
    run_panel.record_selection(root, selection_path, None, None, "normal")
    panel = run_panel.load(root)
    assert panel is not None
    runner = run_module.ReviewRun(
        argparse.Namespace(
            url=fixture.url,
            repoRoot=str(fixture.repo),
            reviewMode="normal",
            locale="en",
            incremental="auto",
            sessionMode="manual",
            fixPolicy=None,
            participants=None,
            ocrProvider=None,
            ocrModel=None,
            resume=True,
            criticCmd=None,
            arbitratorCmd=None,
            contentCmd=None,
            deltaCmd=None,
        )
    )
    runner.root = root
    runner.stage = "critic_missing"
    waiting = runner._waiting_panel(panel, {"reason": None})
    contract_payload = cast("dict[str, Any]", waiting["contract"])
    assert contract_payload["findings[*]"]["severity"] == "one of: critical, high, medium, low"
    assert contract_payload["question_answers[*]"]["verdict"].startswith("one of:")
    assert "never the evidence digest" in contract_payload["context_digest_rule"]
    # The run path reviews the collected context directly: without a recorded
    # package nothing is assigned and the stop says so instead of inventing ids.
    assert waiting["assigned_question_ids"] is None


# ---------- A2: the write-free validate-only probe ----------


def test_validate_only_probe_leaves_stage_and_digests_identical(
    fixture: ReviewFixture,
) -> None:
    root, evidence_path = _prepared_review(fixture)
    assert review_context.review_status(str(root))["stage"] == "critic_missing"
    before = _state(root)
    receipt = _receipt(
        str(_progress(root, "evidence_digest")),
        "critic-run",
        "critic-session",
        [_finding("critic-key", "The retry path repeats a write.")],
    )
    receipt_path = _write(fixture, "receipt.json", receipt)
    probed = workflow.record(
        argparse.Namespace(
            kind="critic_receipt",
            evidence=evidence_path,
            input=receipt_path,
            validate_only=True,
        )
    )
    assert probed == {
        "status": "valid",
        "kind": "critic_receipt",
        "validate_only": True,
        "note": workflow.VALIDATE_ONLY_NOTE,
        "external_mutations": False,
    }
    assert _state(root) == before, "the probe must not mutate run state"
    # An invalid receipt still fails loudly under the probe.
    broken = _write(
        fixture,
        "broken.json",
        {**receipt, "findings": [{**_finding("x", "y"), "severity": "catastrophic"}]},
    )
    with pytest.raises(contract.WorkflowError):
        workflow.record(
            argparse.Namespace(
                kind="critic_receipt", evidence=evidence_path, input=broken, validate_only=True
            )
        )
    assert _state(root) == before
    # The real record advances the stage exactly once.
    recorded = workflow.record(
        argparse.Namespace(
            kind="critic_receipt", evidence=evidence_path, input=receipt_path, validate_only=False
        )
    )
    assert recorded["status"] == "ok"
    assert recorded["stage"] == "finalize_missing"
    assert "contract" in recorded
    after = _state(root)
    assert after["stage"] == "finalize_missing"
    assert after != before


def test_record_run_critic_validate_only_probe_leaves_the_panel_unbound(
    fixture: ReviewFixture,
) -> None:
    root, _evidence_path = _prepared_review(fixture)
    selection_path = _write(
        fixture,
        "participants.json",
        {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arbitrator-1"}},
    )
    run_panel.record_selection(root, selection_path, None, None, "normal")
    receipt = _receipt(str(_progress(root, "evidence_digest")), "critic-run", "critic-session", [])
    receipt_path = _write(fixture, "receipt.json", receipt)
    probed = workflow.record_run_critic(
        argparse.Namespace(
            artifact_root=str(root),
            input=receipt_path,
            participant="critic-1",
            validate_only=True,
        )
    )
    assert probed["status"] == "valid"
    assert probed["validate_only"] is True
    panel = run_panel.load(root)
    assert panel is not None
    assert panel["receipts"] == []
    assert all("receipt" not in critic for critic in run_panel.selected_critics(panel))
    bound = workflow.record_run_critic(
        argparse.Namespace(
            artifact_root=str(root),
            input=receipt_path,
            participant="critic-1",
            validate_only=False,
        )
    )
    assert bound["status"] == "ok"
    assert "contract" in bound


# ---------- A3/A9: the decision surface prints its contract ----------


def test_decision_template_prints_vocabularies_blocking_rule_and_prefill(
    fixture: ReviewFixture,
) -> None:
    root, _evidence_path = _prepared_review(fixture, "fast")
    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    template = review_context.template_review(str(root), "decision")
    vocabularies = cast("dict[str, list[str]]", template["vocabularies"])
    assert vocabularies["responses[].decision"] == ["accept", "reject"]
    assert vocabularies["verdict"] == ["ready", "blocked", "not_ready"]
    assert vocabularies["merge_verdict"] == ["decline", "push_back", "merge_then_fix", "merge"]
    assert vocabularies["ci_job_assessments[].classification"] == [
        "process_gate",
        "code_failure",
        "infrastructure_failure",
        "unknown",
    ]
    blocking_rule = str(template["blocking_rule"])
    assert "severity_override" in blocking_rule and "push_back" in blocking_rule
    assert "never a hidden accepted finding" in blocking_rule
    assert "machine-" in str(template["prefill"])


def test_arbitration_receipt_maps_to_the_recorded_decision_mechanically(
    fixture: ReviewFixture,
) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])
    template_path = Path(str(started["context_package"]["template_path"]))
    template = _read(template_path)
    template["goal"] = {"status": "known", "text": "Bound the retry write behind a key."}
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(template_path, template)
    draft_module.record_draft_participants(
        draft_path,
        _write(
            fixture,
            "participants.json",
            {"critics": [{"name": "critic-1"}], "arbitrator": {"name": "arbitrator-1"}},
        ),
    )
    draft_module.record_draft_package(draft_path, str(template_path))
    draft_module.record_draft_input(
        draft_path, _write(fixture, "identity.json", {"run_id": "run-p", "session_id": "ses-p"})
    )
    draft = _read(draft_path)
    answers: list[dict[str, Any]] = []
    draft_module.record_draft_critic(
        draft_path,
        _write(
            fixture,
            "receipt.json",
            {
                **_receipt(
                    draft["evidence_digest"],
                    "run-c",
                    "ses-c",
                    [_finding("critic-key", "The retry path repeats a write.")],
                ),
                "question_answers": answers,
            },
        ),
        "critic-1",
    )
    dispositions = [
        {
            "id": "critic-key",
            "decision": "accept",
            "reason": "Confirmed against the exact head snapshot.",
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        }
    ]
    arbitration = {
        "schema": "code-review/arbitration/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "run-a",
        "session_id": "ses-a",
        "arbitrator": {"name": "arbitrator-1"},
        "external_mutations": False,
        "merge_verdict": "push_back",
        "merge_verdict_rationale": "The missing knowledge lives with the author.",
        "findings": [],
        "dispositions": dispositions,
        "ci_job_assessments": [],
        "owner_decision_reasons": [],
        "question_verifications": [],
        "content": {
            "summary": "The bounded change meets the agreed contract.",
            "architecture_assessment": "Existing ownership is preserved.",
            "chat_assessment": {
                "necessity": {"status": "supported", "rationale": "The timeout is unbounded."},
                "relevance": {"status": "current", "rationale": "The runner uses this path."},
                "change": "Bound the check.",
            },
            "semver_impact": "patch",
            "semver_rationale": "Backward-compatible correction.",
            "semver_assessment": {
                **draft["content"]["semver_assessment"],
                "policy": "No publication configuration is available.",
                "sources": ["Fixture repository and empty release catalog"],
                "fallback_reason": "No published release can be established.",
            },
            "checks": ["Inspected the exact committed diff."],
            "mr_metadata_assessment": {
                field: {
                    "status": "ok",
                    "rationale": "Observed metadata is sufficient.",
                    "recommendation": None,
                }
                for field in (
                    "title",
                    "description",
                    "labels",
                    "workflow_state",
                    "milestone",
                    "overall",
                )
            },
            "label_assessments": [
                {
                    "name": item["name"],
                    "status": "applicable" if item["name"] == "semver::patch" else "inapplicable",
                    "rationale": "Matches the assessed patch contribution.",
                }
                for item in draft["content"]["label_assessments"]
            ],
            "previous_finding_assessments": [],
            "recommended_issues": [],
            "thread_decisions": [
                {
                    "id": thread["id"],
                    "assessment": "fixed",
                    "rationale": "The exact reviewed code addresses the remark.",
                    "outcome": "no_reply" if thread["state"] == "resolved" else "resolve",
                    "proposed_response": (
                        None
                        if thread["state"] == "resolved"
                        else "note: The exact reviewed code handles this path."
                    ),
                    "fix_mode": "not_required",
                    "patch": None,
                    "fixing_commit": None,
                }
                for thread in draft["content"]["thread_decisions"]
            ],
            "finding_publications": [
                {
                    "finding_id": "critic-key",
                    "type": "line",
                    "path": "review.txt",
                    "line": 2,
                    "old_line": None,
                    "body": "Bind the retried write.\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
                    "fix_mode": "suggestion",
                    "patch": None,
                }
            ],
        },
    }
    imported = draft_module.record_draft_arbitration(
        draft_path, _write(fixture, "arbitration.json", arbitration)
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    finished = draft_module.finish_review(draft_path)
    assert finished["status"] == "ok", json.dumps(finished)
    root = Path(str(started["artifact_root"]))
    progress = review_context.load_progress(root)
    assert progress is not None
    _, decision = contract.artifact_payload(Path(str(progress["decision_path"])), "review_decision")
    # The machine moved the verdicts: no hand transcription happened.
    assert decision["responses"][0] == {
        "id": "critic-key",
        "decision": "accept",
        "reason": "Confirmed against the exact head snapshot.",
    }
    assert decision["blocking_finding_ids"] == ["critic-key"]
    assert decision["blocking_findings"] is True
    assert decision["verdict"] == "not_ready"
    assert decision["critic_findings"][0]["id"] == "critic-key"
    assert decision["ci_job_assessments"] == arbitration["ci_job_assessments"]
    assert decision["blocking_finding_ids"] == ["critic-key"]
    assert decision["blocking_findings"] is True
    assert decision["verdict"] == "not_ready"
    assert decision["critic_findings"][0]["id"] == "critic-key"
    assert decision["ci_job_assessments"] == arbitration["ci_job_assessments"]
    # The machine moved the verdicts: no hand transcription happened.
    assert decision["responses"][0] == {
        "id": "critic-key",
        "decision": "accept",
        "reason": "Confirmed against the exact head snapshot.",
    }
    _, plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
    assert "push_back" in json.dumps(plan["review_source"]["arbitration"])


# ---------- A5: the replace-artifact continuation ----------


def test_replace_artifact_prints_the_continuation(fixture: ReviewFixture) -> None:
    root, evidence_path = _prepared_review(fixture, "fast")
    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    decision = review_context.template_review(str(root), "decision")
    template = _read(decision["template_path"])
    body = {
        **template,
        "run_id": "primary-run",
        "session_id": "primary-session",
        "verdict": "ready",
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "findings": [],
        "accepted_findings": [],
        "responses": [
            {**item, "decision": "accept", "reason": "Confirmed on the exact reviewed head."}
            for item in template["responses"]
        ],
        "critic_findings": [],
        "critic_target_finding_ids": [],
    }
    recorded = workflow.decide(
        argparse.Namespace(
            evidence=evidence_path,
            report=str(_write(fixture, "decision.json", body)),
            context=str(_progress(root, "context_path")),
            finalize_report=str(_progress(root, "finalize_report_path")),
            critic_receipt=None,
            mode="fast",
        )
    )
    assert recorded["status"] == "ok"
    replacement_path = _write(fixture, "decision-repaired.json", body)
    result = workflow.replace_artifact(
        argparse.Namespace(artifact_root=str(root), kind="decision", path=replacement_path)
    )
    assert result["status"] == "ok"
    assert "continue from the content_missing stage" in str(result["continuation"])
    next_action = cast("dict[str, Any]", result["next_action"])
    assert next_action["argv"][:3] == ["reviewmatic", "run", "--resume"]
    assert "--url" in next_action["argv"]


# ---------- A9: the blocking semantics stay enforced next to the dictionaries ----------


def test_accepted_non_low_findings_stay_blocking() -> None:
    with pytest.raises(
        contract.WorkflowError, match="every accepted non-low finding must be blocking"
    ):
        review_context.validate_review_verdict(
            {
                "verdict": "ready",
                "blocking_findings": False,
                "blocking_finding_ids": [],
                "blocking_thread_ids": [],
                "owner_decision_reasons": [],
                "ci_job_assessments": [],
            },
            [_finding("critic-key", "The retry path repeats a write.", "high")],
            {},
        )


# ---------- A10: fix=none is expressible in the draft flow ----------


def test_fix_none_session_policy_expressible_in_the_draft_flow(
    fixture: ReviewFixture, capsys: Any
) -> None:
    code = cli_main(
        [
            "start-review",
            "--url",
            fixture.url,
            "--repo-root",
            str(fixture.repo),
            "--fix-policy",
            "none",
            "--json",
        ]
    )
    assert code == 0, capsys.readouterr().out
    started = cast("dict[str, Any]", json.loads(capsys.readouterr().out))
    root = Path(str(started["artifact_root"]))
    assert _progress(root, "fix_policy") == "none"
    # The comment-only publication is exactly the fix=none shape: prose, no patch.
    comment_only = {
        "finding_id": "docs-1",
        "type": "general",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "note: Document the idempotency key beside the retry example.",
        "fix_mode": "not_required",
        "patch": None,
    }
    accepted = review_context.validate_finding_publications(
        [comment_only], {"docs-1"}, fix_policy="none"
    )
    assert accepted[0]["body"].startswith("note:")
    with pytest.raises(contract.WorkflowError):
        review_context.validate_finding_publications([comment_only], {"docs-1"})


# ---------- A7: the refreshed package materializes prefilled ----------


def test_refresh_materializes_the_package_prefilled_from_the_recorded_one(
    fixture: ReviewFixture,
) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])
    template_path = Path(str(started["context_package"]["template_path"]))
    template = _read(template_path)
    template["goal"] = {"status": "known", "text": "Bound the retry write behind a key."}
    template["acceptance_criteria"] = {
        "status": "known",
        "items": ["Retried writes cannot repeat side effects."],
    }
    template["constraints"] = ["Callers stay unchanged."]
    template["background"] = "The retry path shipped without a key."
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    contract.write_json(template_path, template)
    recorded = draft_module.record_draft_package(draft_path, str(template_path))
    assert recorded["status"] == "ok"
    previous_digest = str(recorded["digest"])
    previous_goal = "Bound the retry write behind a key."
    # Live drift: the discussion gains a new note, so the context changes.
    config = fixture.read_config()
    config["noteBody"] = "New context after the drift."
    fixture.config_path.write_text(json.dumps(config))
    refreshed = draft_module.refresh_review(draft_path)
    assert refreshed["status"] == "needs_reassessment"
    section = cast("dict[str, Any]", refreshed["context_package"])
    prefill = cast("dict[str, Any]", section["prefilled_from"])
    assert prefill["package_digest"] == previous_digest
    assert "goal" in prefill["carried_fields"]
    assert "contract" in prefill and "context_digest_rule" in prefill["contract"]
    assert "stale_threads" in prefill
    prefilled_template = _read(section["template_path"])
    # The authored narrative fields moved verbatim; nothing is rebuilt by hand.
    assert prefilled_template["goal"] == {"status": "known", "text": previous_goal}
    assert prefilled_template["acceptance_criteria"]["items"] == [
        "Retried writes cannot repeat side effects."
    ]
    assert prefilled_template["constraints"] == ["Callers stay unchanged."]
    assert prefilled_template["background"] == "The retry path shipped without a key."
    assert prefilled_template["supersedes"] == previous_digest
    # Machine-owned fields stay fresh from the collected context, while the
    # authored thread prose of the still-present thread is rebound by machine.
    assert prefilled_template["binding"]["evidence_digest"] != ""
    assert prefilled_template["binding"]["evidence_digest"] != recorded["digest"]
    registry = prefilled_template["thread_registry"]
    assert len(registry) == 1
    assert registry[0]["summary"] == "A reviewer remarked on the retry path."
    assert registry[0]["review_relevance"] == "The change touches this path."
    assert registry[0]["state"] in {"open", "resolved", "plain"}


def test_prefill_leaves_question_bindings_to_record_package() -> None:
    template = {
        "schema": "portable-gitlab/context-package/v2",
        "binding": {"evidence_digest": "fresh"},
        "thread_registry": [{"id": "discussion-42", "state": "open"}],
        "supersedes": None,
    }
    previous = {
        "goal": {"status": "known", "text": "Goal text."},
        "questions": [
            {"id": "q-1", "subject": "S", "source": "X", "critic": True, "context_digest": "old"}
        ],
    }
    from reviewmatic import context_package

    prefilled = context_package.prefill_package_from_previous(
        previous, copy.deepcopy(template), "abc"
    )
    assert prefilled["goal"] == {"status": "known", "text": "Goal text."}
    assert prefilled["questions"][0]["id"] == "q-1"
    assert "context_digest" not in prefilled["questions"][0]
    assert prefilled["supersedes"] == "abc"
    assert prefilled["thread_registry"] == template["thread_registry"]
