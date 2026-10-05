"""Orchestrated review panel against the fake glab, ported from
``panel.test.mjs``.

Covers: one recorded selection, parallel independent critic receipts, one
arbitration receipt, local finalization with the participant bindings kept out
of GitLab bodies, the head guard of the publication block, the fixed
selection and no-silent-replacement rules, the fast-mode rejection, and the
refresh carry-over. Finalized plan artifacts are read through the progress
pointer; there is no terminal viewer.
"""

from __future__ import annotations

import itertools
import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract

_counter = itertools.count()


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


def _write_input(fixture: ReviewFixture, value: Any, name: str = "input.json") -> str:
    path = fixture.tmp / f"{next(_counter)}-{name}"
    contract.write_json(path, value)
    return str(path)


def _critic_finding(identifier: str, summary: str, severity: str = "medium") -> dict[str, Any]:
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


def _participants_selection() -> dict[str, Any]:
    return {
        "critics": [
            {
                "name": "critic-general",
                "profile": "critic-general",
                "provider": "openai",
                "model": "gpt-x",
            },
            {"name": "critic-plain"},
        ],
        "arbitrator": {"name": "arb-main", "provider": "zai", "model": "glm-x"},
    }


def _critic_receipt(
    evidence_digest: str,
    run_id: str,
    session_id: str,
    findings: list[dict[str, Any]],
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": evidence_digest,
        "run_id": run_id,
        "session_id": session_id,
        "findings": findings,
        "question_answers": answers,
        "external_mutations": False,
    }


def _answer(versions: dict[str, str], verdict: str, evidence: str) -> dict[str, Any]:
    return {
        "question_id": "q-idempotency",
        "verdict": verdict,
        "evidence": evidence,
        "context_digest": versions["q-idempotency"],
    }


_NO_DEPENDENCIES = {"paths": ["review.txt"], "thread_ids": [], "metadata_fields": [], "ci": False}


def _disposition(
    identifier: str, decision: str, reason: str, duplicate_of: str | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": identifier,
        "decision": decision,
        "reason": reason,
        "dependencies": dict(_NO_DEPENDENCIES),
    }
    if duplicate_of is not None:
        value["duplicate_of"] = duplicate_of
    return value


def _publication(finding_id: str, body: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": "line",
        "path": "review.txt",
        "line": 2,
        "old_line": None,
        "body": f"{body}\n\n```suggestion:-1+0\nreviewed change (idempotent)\n```",
        "fix_mode": "suggestion",
        "patch": None,
    }


def _arbitration_content(content: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": "The bounded change meets the agreed contract.",
        "architecture_assessment": "Existing ownership is preserved.",
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The existing timeout is unbounded."},
            "relevance": {"status": "current", "rationale": "The current runner uses this path."},
            "change": "Bound the check.",
        },
        "semver_impact": "patch",
        "semver_rationale": "Backward-compatible correction.",
        "semver_assessment": {
            **content["semver_assessment"],
            "policy": "No publication configuration is available.",
            "sources": ["Fixture repository and empty release catalog"],
            "fallback_reason": "No published release can be established.",
        },
        "checks": ["Inspected the exact committed diff; external tests were not run."],
        "mr_metadata_assessment": {
            field: {
                "status": "ok",
                "rationale": "The observed metadata is sufficient.",
                "recommendation": None,
            }
            for field in content["mr_metadata_assessment"]
        },
        "label_assessments": [
            {
                "name": item["name"],
                "status": "applicable" if item["name"] == "semver::patch" else "inapplicable",
                "rationale": "Matches the assessed patch contribution.",
            }
            for item in content["label_assessments"]
        ],
        "previous_finding_assessments": [],
        "recommended_issues": [],
        "thread_decisions": [
            {
                "id": thread["id"],
                "assessment": "fixed",
                "rationale": "The exact reviewed code already addresses the remark.",
                "outcome": "no_publication" if thread["state"] == "resolved" else "resolve",
                "proposed_response": (
                    None
                    if thread["state"] == "resolved"
                    else "The exact reviewed code now handles this path."
                ),
                "fix_mode": "not_required",
                "patch": None,
                "fixing_commit": None,
            }
            for thread in content["thread_decisions"]
        ],
        "finding_publications": [
            _publication("critic-a-key", "Bind the retried write behind the idempotency key."),
            _publication("critic-b-key", "Bind the retried write behind the idempotency key."),
            _publication("arb-merged-key", "Bind both retried writes behind one idempotency key."),
        ],
    }


def _arbitration_body(
    draft: dict[str, Any], versions: dict[str, str] | None, *, minimal: bool = False
) -> dict[str, Any]:
    content = cast("dict[str, Any]", draft["content"])
    findings: list[dict[str, Any]] = (
        []
        if minimal
        else [
            {
                "id": "arb-merged-key",
                "severity": "high",
                "summary": (
                    "The retried write needs one shared idempotency key across both call sites."
                ),
                "risk": "Either call site can still duplicate the side effect.",
                "evidence": ["review.txt:2 repeats the write on the retry branch."],
                "consequence": "Duplicated writes surface as duplicated records downstream.",
                "relation_to_change": "The change introduces the retry path.",
                "minimum_fix": "Bind both retried writes behind one idempotency key.",
            }
        ]
    )
    dispositions: list[dict[str, Any]] = (
        []
        if minimal
        else [
            _disposition(
                "critic-a-key",
                "accept",
                "The exact head repeats the write; the evidence was re-read in the worktree.",
            ),
            _disposition(
                "critic-a-dup",
                "reject",
                "Duplicates critic-b-key: the same retried write on the same line.",
                "critic-b-key",
            ),
            _disposition("critic-b-key", "accept", "Confirmed against the exact head snapshot."),
            _disposition(
                "critic-b-refuted",
                "reject",
                "The named helper exists at the exact head; the concern does not reproduce.",
            ),
            _disposition(
                "arb-merged-key",
                "accept",
                "Arbitrator-authored merge of both partial key findings.",
            ),
        ]
    )
    verification: dict[str, Any] = {
        "question_id": "q-idempotency",
        "original": {"run_id": "run-a", "session_id": "session-a", "verdict": "confirmed"},
        "verdict": "confirmed",
        "evidence": "The exact head binds the retried write behind the key.",
    }
    if versions is not None:
        verification["context_digest"] = versions["q-idempotency"]
    return {
        "schema": "code-review/arbitration/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "arb-run",
        "session_id": "arb-session",
        "arbitrator": {"name": "arb-main", "provider": "zai", "model": "glm-x"},
        "external_mutations": False,
        "findings": findings,
        "dispositions": dispositions,
        "ci_job_assessments": draft["ci_job_assessments"],
        "owner_decision_reasons": [],
        "question_verifications": [verification],
        "content": {} if minimal else _arbitration_content(content),
    }


def _read_draft(path: str) -> dict[str, Any]:
    return contract.read_json(Path(path), "draft")


def _panel_prepared(
    fixtures: Any, overrides: dict[str, Any] | None = None
) -> tuple[ReviewFixture, dict[str, Any]]:
    fixture: ReviewFixture = fixtures(overrides)
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo), locale="en")
    assert started["status"] == "ok"
    template_path = Path(str(started["context_package"]["template_path"]))
    template = contract.read_json(template_path, "package template")
    template["goal"] = {
        "status": "known",
        "text": "Bound the retry write behind an idempotency key.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template["thread_registry"]:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path."
    template["questions"] = [
        {
            "id": "q-idempotency",
            "subject": "Does the exact head bind retried writes behind the idempotency key?",
            "source": "Primary inspection of the committed diff.",
            "critic": True,
        }
    ]
    contract.write_json(template_path, template)
    return fixture, started


def _panel_running(
    fixtures: Any, overrides: dict[str, Any] | None = None
) -> tuple[ReviewFixture, dict[str, Any], str, dict[str, Any]]:
    fixture, started = _panel_prepared(fixtures, overrides)
    draft_path = str(started["draft_path"])
    draft_module.record_draft_participants(
        draft_path, _write_input(fixture, _participants_selection())
    )
    recorded = draft_module.record_draft_package(
        draft_path, str(started["context_package"]["template_path"])
    )
    assert recorded["status"] == "ok"
    draft_module.record_draft_input(
        draft_path,
        _write_input(fixture, {"run_id": "orchestrator-run", "session_id": "orchestrator-session"}),
    )
    return fixture, started, draft_path, recorded


def _record_both_critics(
    fixture: ReviewFixture,
    draft_path: str,
    versions: dict[str, str],
    *,
    findings: bool = False,
) -> None:
    current = _read_draft(draft_path)
    answers = [_answer(versions, "confirmed", "The exact head binds writes behind the key.")]
    for name, run in (("critic-general", "a"), ("critic-plain", "b")):
        receipt = _critic_receipt(
            current["evidence_digest"],
            f"run-{run}",
            f"session-{run}",
            [_critic_finding(f"critic-{run}-key", "The retry path repeats a write.")]
            if findings
            else [],
            answers,
        )
        result = draft_module.record_draft_critic(
            draft_path, _write_input(fixture, receipt, f"critic-{run}.json"), name
        )
        assert result["status"] == "ok", json.dumps(result.get("errors"))


def test_panel_review_runs_selection_critics_arbitration_and_local_finalization(
    fixtures: Any,
) -> None:
    fixture, started, draft_path, recorded = _panel_running(fixtures)
    requests = fixture.request_count()

    inspection = contract.read_json(Path(str(started["inspection_path"])), "inspection index")
    assert inspection["file_relations"]["complete"] is True
    assert isinstance(inspection["file_relations"]["entries"], list)
    relation = next(
        (item for item in inspection["file_relations"]["entries"] if item["path"] == "review.txt"),
        None,
    )
    assert relation is not None, "changed paths receive a relation entry"
    assert relation["referenced_by"] == ["index.txt"]
    assert "not a semantic dependency map" in str(inspection["file_relations"]["notice"])

    assert len(recorded["critic_tasks"]) == 2
    assert [task["participant"] for task in recorded["critic_tasks"]] == [
        "critic-general",
        "critic-plain",
    ]
    assert (
        "--participant critic-general" in recorded["critic_tasks"][0]["import_command"]["command"]
    )
    assert recorded["critic_tasks"][1]["profile"] is None

    restricted = draft_module.record_draft_input(
        draft_path,
        _write_input(
            fixture,
            {"findings": [_critic_finding("host-own-pass", "The orchestrator adds a finding.")]},
            "restricted.json",
        ),
    )
    assert restricted["status"] == "invalid"
    assert any(
        issue["path"] == "$.findings" and "panel" in issue["message"]
        for issue in restricted["errors"]
    )

    versions = recorded["question_context_versions"]
    draft = _read_draft(draft_path)
    unbound = draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(
                draft["evidence_digest"],
                "run-a",
                "session-a",
                [_critic_finding("critic-a-key", "A")],
                [_answer(versions, "confirmed", "The key exists.")],
            ),
            "critic-a.json",
        ),
    )
    assert unbound["status"] == "invalid"
    assert any(issue["path"] == "$.participant" for issue in unbound["errors"])

    with pytest.raises(contract.WorkflowError, match="Every selected critic receipt must be"):
        draft_module.record_draft_arbitration(
            draft_path, _write_input(fixture, _arbitration_body(draft, versions), "early.json")
        )

    critic_a = draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(
                draft["evidence_digest"],
                "run-a",
                "session-a",
                [
                    _critic_finding("critic-a-key", "The retry path repeats a write."),
                    _critic_finding("critic-a-dup", "Retried write lacks a key."),
                ],
                [_answer(versions, "confirmed", "The exact head binds writes behind the key.")],
            ),
            "critic-a.json",
        ),
        "critic-general",
    )
    assert critic_a["status"] == "ok", json.dumps(critic_a.get("errors"))
    assert "arbitrator_task" not in critic_a
    critic_b = draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(
                draft["evidence_digest"],
                "run-b",
                "session-b",
                [
                    _critic_finding("critic-b-key", "Retried write lacks a key."),
                    _critic_finding("critic-b-refuted", "Missing helper for the retry path."),
                ],
                [_answer(versions, "refuted", "The retry branch still writes without the key.")],
            ),
            "critic-b.json",
        ),
        "critic-plain",
    )
    assert critic_b["status"] == "ok", json.dumps(critic_b.get("errors"))
    assert critic_b["arbitrator_task"]["launch"] == "now_after_every_critic_receipt"
    arbitration_input = contract.read_json(
        Path(str(critic_b["arbitrator_task"]["input_path"])), "arbitration input"
    )
    assert len(arbitration_input["critic_receipts"]) == 2
    assert arbitration_input["contradictions"] == ["q-idempotency"]
    assert (
        "record-arbitration" in arbitration_input["response_contract"]["import_command"]["command"]
    )
    assert arbitration_input["participants"]["critics"][0]["name"] == "critic-general"

    wrong_arbitration = _arbitration_body(_read_draft(draft_path), versions)
    wrong_arbitration["arbitrator"] = {"name": "critic-plain"}
    wrong = draft_module.record_draft_arbitration(
        draft_path, _write_input(fixture, wrong_arbitration, "wrong-arb.json")
    )
    assert wrong["status"] == "invalid"
    assert any(issue["path"] == "$.arbitrator.name" for issue in wrong["errors"]), json.dumps(
        wrong["errors"]
    )

    no_resolution = _arbitration_body(_read_draft(draft_path), versions)
    no_resolution["question_verifications"] = []
    blocked = draft_module.record_draft_arbitration(
        draft_path, _write_input(fixture, no_resolution, "no-resolution.json")
    )
    assert blocked["status"] == "invalid"
    assert any(
        issue["path"] == "$.question_verifications" and "q-idempotency" in issue["message"]
        for issue in blocked["errors"]
    )

    imported = draft_module.record_draft_arbitration(
        draft_path,
        _write_input(
            fixture, _arbitration_body(_read_draft(draft_path), versions), "arbitration.json"
        ),
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    assert imported["imported"]["verdicts"] == 5

    checked = draft_module.check_review(draft_path)
    assert checked["status"] == "ok", json.dumps(checked.get("errors"))
    assert fixture.request_count() == requests, "recording and validation stay local"

    finished = draft_module.finish_review(draft_path)
    assert finished["status"] == "ok", json.dumps(finished)
    assert fixture.request_count() == requests, "finalization is local-only"

    book = Path(str(finished["markdown_path"])).read_text(encoding="utf-8")
    assert "## Review panel" in book
    assert (
        "critic `critic-general` — profile: critic-general · provider: openai · model: gpt-x"
        in book
    )
    assert "arbitrator `arb-main` — provider: zai · model: glm-x" in book
    assert "## Arbitration verdicts" in book
    assert re.search(r"`critic-b-refuted`[\s\S]*?refuted", book)
    assert "duplicate of `critic-b-key`" in book
    assert "Raised by: critic-general" in book
    assert "Merged by the arbitrator from: `critic-a-dup`" in book
    assert "current_head_json=$(glab api --hostname gitlab.example --method GET" in book

    root = Path(str(started["artifact_root"]))
    progress = review_context.load_progress(root)
    assert progress is not None
    _, plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
    bodies = "\n".join(str(item["content"]) for item in plan["publication_preview"]["body_files"])
    for internal in ("critic-general", "critic-plain", "arb-main", "zai", "glm-x", "gpt-x"):
        assert internal not in bodies, f"{internal} must stay out of GitLab bodies"
    assert all(
        critic.get("receipt") for critic in plan["review_source"]["participants"]["critics"]
    ), "participant receipt bindings survive into the plan"
    assert plan["review_source"]["arbitration"]["session_id"] == "arb-session"

    # The head guard stops a publication block before any write when the MR
    # moved after the review.
    block = next(
        match
        for match in re.findall(r"```shell\n([\s\S]*?)\n```", book)
        if "/discussions/discussion-42/notes" in match
    )
    config = fixture.read_config()
    config["headSha"] = fixture.base_sha
    fixture.config_path.write_text(json.dumps(config))
    moved = subprocess.run(["sh", "-c", block], capture_output=True, text=True, check=False)
    assert moved.returncode != 0
    assert re.search(r"head differs|nothing was published", moved.stderr)
    assert len(fixture.read_config().get("publishedNotes") or []) == 0


def test_panel_selection_is_fixed_once_receipts_exist_and_arbitration_is_not_replaced(
    fixtures: Any,
) -> None:
    fixture, started, draft_path, _recorded = _panel_running(fixtures, {"resolved": True})
    pointer = contract.read_json(
        Path(str(started["artifact_root"])) / "context-package.json", "pointer"
    )
    package_payload = contract.read_json(Path(str(pointer["package_path"])), "package")["payload"]
    versions = {
        question["id"]: question["context_digest"] for question in package_payload["questions"]
    }
    current = _read_draft(draft_path)
    answers = [_answer(versions, "confirmed", "The exact head binds writes behind the key.")]
    draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(current["evidence_digest"], "run-a", "session-a", [], answers),
            "critic-a.json",
        ),
        "critic-general",
    )
    with pytest.raises(contract.WorkflowError, match="fixed once critic receipts exist"):
        draft_module.record_draft_participants(
            draft_path, _write_input(fixture, _participants_selection(), "again.json")
        )
    double_binding = draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(current["evidence_digest"], "run-a", "session-a", [], answers),
            "critic-a2.json",
        ),
        "critic-plain",
    )
    assert double_binding["status"] == "invalid"
    assert any(issue["path"] == "$.participant" for issue in double_binding["errors"])
    draft_module.record_draft_critic(
        draft_path,
        _write_input(
            fixture,
            _critic_receipt(current["evidence_digest"], "run-b", "session-b", [], answers),
            "critic-b.json",
        ),
        "critic-plain",
    )
    receipt = _arbitration_body(_read_draft(draft_path), versions, minimal=True)
    imported = draft_module.record_draft_arbitration(
        draft_path, _write_input(fixture, receipt, "arbitration.json")
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    with pytest.raises(contract.WorkflowError, match="already recorded"):
        draft_module.record_draft_arbitration(
            draft_path,
            _write_input(
                fixture, _arbitration_body(_read_draft(draft_path), versions), "replace.json"
            ),
        )


def test_fast_mode_rejects_a_panel_and_the_resume_overview_reports_an_unrecorded_panel(
    fixtures: Any,
) -> None:
    fixture, _started = _panel_prepared(fixtures, {"resolved": True})
    fast = draft_module.start_review(
        url=fixture.url, repo_root=str(fixture.repo), review_mode="fast"
    )
    with pytest.raises(
        contract.WorkflowError, match="fast and unchanged reviews run without a panel"
    ):
        draft_module.record_draft_participants(
            str(fast["draft_path"]), _write_input(fixture, _participants_selection())
        )
    resumed = draft_module.resume_review(str(fast["artifact_root"]))
    assert resumed["panel"]["recorded"] is False
    assert resumed["panel"]["required"] is False
    assert "record-participants" in resumed["panel"]["record_command"]


def test_refresh_review_carries_the_panel_selection_without_receipt_bindings(
    fixtures: Any,
) -> None:
    fixture, _started, draft_path, recorded = _panel_running(fixtures)
    versions = recorded["question_context_versions"]
    _record_both_critics(fixture, draft_path, versions)
    receipt = _arbitration_body(_read_draft(draft_path), versions, minimal=True)
    assert (
        draft_module.record_draft_arbitration(
            draft_path, _write_input(fixture, receipt, "arbitration.json")
        )["status"]
        == "ok"
    )
    config = fixture.read_config()
    config["noteBody"] = "New context"
    fixture.config_path.write_text(json.dumps(config))
    refreshed = draft_module.refresh_review(draft_path)
    assert refreshed["status"] == "needs_reassessment"
    following = _read_draft(str(refreshed["draft_path"]))
    assert len(following["participants"]["critics"]) == 2
    assert all("receipt" not in critic for critic in following["participants"]["critics"])
    assert following["critic_count"] == 2
    assert "arbitration" not in following
    assert len(following["findings"]) == 0
    assert len(_read_draft(draft_path)["critics"]) == 2
