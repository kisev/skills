"""Context-package recording and question-result scenarios against the fake
glab, ported from ``context-package.test.mjs``.

The pure binding and digest rules are covered in ``test_context_package.py``;
these scenarios exercise the draft state machine around them: recording,
supersession history, late answers, mixed-version recovery, and primary
verifications.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract

Q_RETRY = {
    "id": "q-retry",
    "subject": "Does the exact head always set the idempotency key?",
    "source": "Discussion 42 of the collected evidence",
    "critic": True,
}
REVOCATION_SUBJECT = "Is credential revocation enforced when a key is reused?"


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Any:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _read(path: Any) -> dict[str, Any]:
    return contract.read_json(Path(str(path)), "draft")


def _write(path: Any, value: Any) -> None:
    contract.write_json(Path(str(path)), value)


def _errors(result: dict[str, Any]) -> str:
    return json.dumps(result.get("errors"))


def _template_path(started: dict[str, Any]) -> Path:
    return Path(str(started["context_package"]["template_path"]))


def _template_with(started: dict[str, Any], **edits: Any) -> dict[str, Any]:
    template = contract.read_json(_template_path(started), "template")
    template["goal"] = {
        "status": "known",
        "text": "Bound the retry write behind an idempotency key.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template.get("thread_registry") or []:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path; the remark is assessed directly."
    template.update(edits)
    contract.write_json(_template_path(started), template)
    return template


def _pristine(started: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(contract.read_json(_template_path(started), "template"))


def _bound_answer(draft: dict[str, Any], question_id: str, **extra: Any) -> dict[str, Any]:
    _, payload = contract.artifact_payload(
        Path(str(draft["context_package_path"])), "context_package"
    )
    question = next(
        (item for item in payload.get("questions") or [] if item["id"] == question_id), None
    )
    assert question is not None, f"question {question_id} is not in the recorded package"
    answer = {
        "question_id": question_id,
        "verdict": "confirmed",
        "evidence": "Inspected the exact head.",
        "context_digest": question["context_digest"],
        **extra,
    }
    return {key: value for key, value in answer.items() if value is not None}


def _bound_verification(draft: dict[str, Any], question_id: str, **extra: Any) -> dict[str, Any]:
    verification = {
        "question_id": question_id,
        "original": {
            "run_id": "critic-run",
            "session_id": "child-session",
            "verdict": "not_verified",
        },
        "verdict": "confirmed",
        "evidence": "Inspected the exact head.",
        "context_digest": _bound_answer(draft, question_id)["context_digest"],
        **extra,
    }
    return {key: value for key, value in verification.items() if value is not None}


def _write_template(started: dict[str, Any], base: dict[str, Any], **edits: Any) -> dict[str, Any]:
    template = copy.deepcopy(base)
    template["goal"] = {
        "status": "known",
        "text": "Bound the retry write behind an idempotency key.",
    }
    template["acceptance_criteria"] = {"status": "unknown", "items": []}
    for item in template.get("thread_registry") or []:
        item["summary"] = "A reviewer remarked on the retry path."
        item["review_relevance"] = "The change touches this path; the remark is assessed directly."
    template.update(edits)
    contract.write_json(_template_path(started), template)
    return draft_module.record_draft_package(
        str(started["draft_path"]), str(_template_path(started))
    )


def _record(started: dict[str, Any]) -> dict[str, Any]:
    return draft_module.record_draft_package(
        str(started["draft_path"]), str(_template_path(started))
    )


def _start(fixture: ReviewFixture, **options: Any) -> dict[str, Any]:
    return draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo), **options)


def _critic_receipt_payload(root: Path) -> dict[str, Any]:
    directory = root / "artifacts" / "critic_receipt"
    first = sorted(directory.iterdir())[0]
    _, receipt = contract.artifact_payload(first, "critic_receipt")
    return receipt


def test_the_mr_package_template_exposes_every_thread_and_records_with_bindings(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    assert started["context_package"]["status"] == "pending"
    assert started["critic_task"]["context_package_path"] is None
    template = contract.read_json(_template_path(started), "template")
    assert template["schema"] == "portable-gitlab/context-package/v2"
    assert template["goal"] == {"status": "unknown"}
    assert template["acceptance_criteria"] == {"status": "unknown", "items": []}
    assert len(template["thread_registry"]) == 1
    assert template["thread_registry"][0]["id"] == "42"
    assert template["thread_registry"][0]["summary"] == ""
    assert "context package" in started["critic_task"]["instructions"]
    assert "record-package --draft" in started["context_package"]["record_command"]

    requests_before = fixture.request_count()
    recorded = _write_template(started, _pristine(started))
    assert fixture.request_count() == requests_before, "recording never contacts GitLab"
    assert recorded["status"] == "ok"
    assert recorded["digest"]
    assert Path(recorded["artifact_path"]).exists()
    assert recorded["artifact_path"].startswith(f"{started['artifact_root']}/artifacts/")
    assert not recorded["artifact_path"].startswith(str(fixture.repo)), (
        "the package stays outside the checkout"
    )
    assert len(template["thread_registry"]) == recorded["thread_registry_size"]

    resumed = draft_module.resume_review(str(started["artifact_root"]))
    assert resumed["context_package"]["status"] == "recorded"
    assert resumed["context_package"]["package_digest"] == recorded["digest"]
    assert resumed["critic_task"]["context_package_path"] == recorded["artifact_path"]


def test_a_dropped_thread_blocks_recording_and_answers_keep_critic_authorship(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    base = _pristine(started)
    with pytest.raises(contract.WorkflowError, match="missing collected threads"):
        _write_template(started, base, thread_registry=[])
    with pytest.raises(contract.WorkflowError, match="disputes unknown claim"):
        _write_template(
            started,
            base,
            claims=[
                {
                    "id": "claim-a",
                    "kind": "author_claim",
                    "statement": "s",
                    "sources": ["MR description"],
                    "disputed_by": ["claim-z"],
                }
            ],
        )
    with pytest.raises(
        contract.WorkflowError, match=r'claims\[0\]\.kind: Expected one of "author_claim"'
    ):
        _write_template(
            started,
            base,
            claims=[
                {
                    "id": "claim-kind",
                    "kind": "vibes",
                    "statement": "s",
                    "sources": ["MR description"],
                }
            ],
        )

    _write_template(
        started,
        base,
        claims=[
            {
                "id": "claim-description",
                "kind": "author_claim",
                "statement": "The description says the retry is already safe.",
                "sources": ["MR description section 'Behavior'"],
            },
            {
                "id": "claim-agreed",
                "kind": "agreed_requirement",
                "statement": "Retries must stay idempotent.",
                "sources": ["Discussion 42 reviewer request"],
                "disputed_by": ["claim-description"],
            },
        ],
        questions=[
            {
                "id": "q-retry",
                "subject": "Does the exact head always set the idempotency key?",
                "source": "Discussion 42 of the collected evidence",
                "critic": True,
            }
        ],
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critic_count"] = 3
    first = draft["critics"][0]
    draft["critics"] = [
        {
            **first,
            "run_id": "critic-run-1",
            "session_id": "critic-session-1",
            "question_answers": [
                _bound_answer(
                    draft, "q-retry", evidence="The exact head sets the key before write."
                )
            ],
        },
        {
            **first,
            "run_id": "critic-run-2",
            "session_id": "critic-session-2",
            "question_answers": [
                _bound_answer(
                    draft,
                    "q-retry",
                    verdict="refuted",
                    evidence="The exact head leaves the write unkeyed.",
                )
            ],
        },
        {
            **first,
            "run_id": "critic-run-3",
            "session_id": "critic-session-3",
            "question_answers": [
                _bound_answer(
                    draft,
                    "q-retry",
                    verdict="not_verified",
                    reason="Could not trace the retry caller in the exact head.",
                )
            ],
        },
    ]
    _write(started["draft_path"], draft)

    unverified = draft_module.check_review(str(started["draft_path"]))
    assert unverified["status"] == "invalid"
    assert "question_verifications entry that preserves the original answer" in _errors(unverified)

    verified = _read(started["draft_path"])
    verified["question_verifications"] = [
        _bound_verification(
            verified,
            "q-retry",
            original={
                "run_id": "critic-run-3",
                "session_id": "critic-session-3",
                "verdict": "not_verified",
            },
            verdict="unresolved",
            evidence=None,
            reason="No reachable retry caller exists in the exact head; the doubt stays explicit.",
        )
    ]
    _write(started["draft_path"], verified)
    checked = draft_module.check_review(str(started["draft_path"]))
    assert checked["status"] == "ok"
    assert checked["question_status"]["contradicted"] == 1
    assert checked["question_status"]["unverified"] == 1
    assert checked["question_status"]["unresolved"] == 1
    assert checked["question_status"]["assigned"] == 1

    wrong_original = _read(started["draft_path"])
    wrong_original["question_verifications"][0]["original"] = {
        "run_id": "critic-run-3",
        "session_id": "critic-session-3",
        "verdict": "confirmed",
    }
    _write(started["draft_path"], wrong_original)
    rejected = draft_module.check_review(str(started["draft_path"]))
    assert rejected["status"] == "invalid"
    assert "does not match any retained critic answer" in _errors(rejected)


def test_without_a_critic_the_primary_answers_assigned_questions_itself(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture, review_mode="fast")
    _template_with(
        started,
        questions=[
            {
                "id": "q-fast",
                "subject": "Is the fast scope really low risk?",
                "source": "User request",
                "critic": True,
            }
        ],
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critic_count"] = 0
    draft["critics"] = []
    draft["low_risk"] = True
    _write(started["draft_path"], draft)
    missing = draft_module.check_review(str(started["draft_path"]))
    assert missing["status"] == "invalid"
    assert "assigned without a critic" in _errors(missing)

    answered = _read(started["draft_path"])
    answered["question_verifications"] = [
        _bound_verification(
            answered,
            "q-fast",
            original={
                "run_id": "primary-run",
                "session_id": "primary-session",
                "verdict": "not_verified",
            },
            evidence="The diff bounds one retry write with a concrete key.",
        )
    ]
    _write(started["draft_path"], answered)
    assert draft_module.check_review(str(started["draft_path"]))["status"] == "ok"


def test_an_unknown_goal_stays_explicit_and_known_claims_require_text(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    base = _pristine(started)
    recorded = _write_template(started, base, goal={"status": "unknown"})
    assert recorded["status"] == "ok"
    with pytest.raises(contract.WorkflowError, match="goal"):
        _write_template(started, base, goal={"status": "known"})


def test_editing_the_background_never_changes_the_canonical_digest_when_recorded(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    base = _pristine(started)
    first = _write_template(started, base, background="Original conversation background.")
    second = _write_template(started, base, background="Rewritten narrative, same facts.")
    assert first["digest"] != second["digest"]
    assert first["canonical_digest"] == second["canonical_digest"]
    assert first["background_digest"] != second["background_digest"]

    third = _write_template(started, base, supersedes=second["digest"])
    assert third["status"] == "ok"
    with pytest.raises(
        contract.WorkflowError, match="supersedes must name the currently recorded package"
    ):
        _write_template(started, base, supersedes="0" * 64)


def test_refresh_reports_the_previous_package_and_its_stale_threads(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _write_template(started, _pristine(started))
    config = fixture.read_config()
    config["resolved"] = True
    fixture.config_path.write_text(json.dumps(config))
    refreshed = draft_module.refresh_review(str(started["draft_path"]))
    assert refreshed["status"] == "needs_reassessment"
    assert len(refreshed["previous_context_package"]["stale_threads"]) == 1
    assert "record-package --draft" in refreshed["context_package"]["record_command"]
    following = _read(refreshed["draft_path"])
    assert following["context_package_path"] is None
    assert following["question_verifications"] == []


def test_the_local_package_binds_the_prepared_snapshot_and_gates_finalization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "commit.gpgsign", "false")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (repo / "renderer.txt").write_text("base\n")
    git("add", ".")
    git("commit", "-qm", "base")
    (repo / "renderer.txt").write_text("broken\n")

    bundle = local_review.local_bundle(str(repo), "code-review", None)
    root = Path(str(bundle["artifact_root"]))
    snapshot, digest_value = contract.write_artifact(root, "local_wip_snapshot", bundle)
    followup = local_review.prepare_followup(str(root), bundle, digest_value, "auto")
    template_path = Path(str(followup["context_package"]["template_path"]))
    template = contract.read_json(template_path, "template")
    assert template["mode"] == "local"
    assert len(template["binding"]["sections"]["committed"]) == 64
    assert template["binding"]["ref"] is None
    assert "thread_registry" not in template
    assert template["goal"] == {"status": "unknown"}
    assert "record-package --bundle" in followup["context_package"]["record_command"]

    template["goal"] = {
        "status": "known",
        "text": "Link plain text without modifying mixed Markdown.",
    }
    template["acceptance_criteria"] = {"status": "known", "items": ["Plain references link."]}
    template["questions"] = [
        {
            "id": "q-renderer",
            "subject": "Does the staged renderer change touch protected values?",
            "source": "Local conversation with the author",
            "critic": True,
        }
    ]
    contract.write_json(template_path, template)
    recorded = local_review.record_local_package(str(snapshot), str(template_path))
    assert recorded["status"] == "ok"
    assert not recorded["artifact_path"].startswith(str(repo)), (
        "the package stays outside the checkout"
    )
    version = recorded["question_context_versions"]["q-renderer"]
    assert version, "recording reports the meaningful-context version per question"

    report: dict[str, Any] = {
        "evidence_digest": digest_value,
        "previous_review_digest": None,
        "mode": "full",
        "context_package": None,
        "question_answers": [],
        "question_verifications": [],
        "task": {
            "goal": "Link plain text without modifying mixed Markdown.",
            "acceptance_criteria": ["Plain references link."],
            "constraints": [],
            "accepted_risks": [],
            "deferred": [],
            "decision_evidence": "User chose plain-text linking.",
        },
        "task_change_reason": None,
        "findings": [],
        "checks": [
            {"name": "renderer", "status": "passed", "required": True, "evidence": "inspected"}
        ],
        "assessment": "narrow",
        "verdict": "ready",
        "external_mutations": False,
    }
    draft = Path(str(followup["draft_path"]))
    parent = str(draft.parent)
    contract.write_json(draft, report)
    with pytest.raises(contract.WorkflowError, match="must bind the recorded context package"):
        local_review.record_review(parent, str(snapshot), str(draft))

    report["context_package"] = {"path": recorded["artifact_path"], "digest": recorded["digest"]}
    contract.write_json(draft, report)
    with pytest.raises(
        contract.WorkflowError,
        match=(
            "question q-renderer is assigned to critics but no critic answer or primary "
            "verification covers it"
        ),
    ):
        local_review.record_review(parent, str(snapshot), str(draft))

    report["question_verifications"] = [
        {
            "question_id": "q-renderer",
            "original": {
                "run_id": "local-primary",
                "session_id": "local-session",
                "verdict": "not_verified",
            },
            "verdict": "confirmed",
            "evidence": "The staged diff only rewrites plain text values.",
            "context_digest": version,
        }
    ]
    contract.write_json(draft, report)
    saved = local_review.record_review(parent, str(snapshot), str(draft))
    assert saved["verdict"] == "ready"
    finalized = local_review.finalize_local(str(snapshot))
    assert finalized["status"] == "ok"

    (repo / "renderer.txt").write_text("changed\n")
    next_bundle = local_review.local_bundle(str(repo), "code-review", None)
    next_snapshot, next_digest = contract.write_artifact(
        Path(str(next_bundle["artifact_root"])), "local_wip_snapshot", next_bundle
    )
    assert next_digest != digest_value
    following = local_review.prepare_followup(
        str(next_bundle["artifact_root"]), next_bundle, next_digest, "auto"
    )
    assert following["context_package"]["status"] == "pending"
    assert following["context_package"]["package_path"] == recorded["artifact_path"]
    stale_report = copy.deepcopy(report)
    stale_report["evidence_digest"] = next_digest
    stale_report["previous_review_digest"] = saved["digest"]
    stale_report["mode"] = "incremental"
    contract.write_json(draft, stale_report)
    with pytest.raises(
        contract.WorkflowError,
        match=r"does not bind the selected evidence digest|does not match the prepared snapshot",
    ):
        local_review.record_review(parent, str(next_snapshot), str(draft))


def test_every_selected_critic_must_answer_each_assigned_question(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(started, questions=[Q_RETRY])
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critic_count"] = 2
    draft["critics"] = [
        {
            **draft["critics"][0],
            "run_id": "critic-run-1",
            "session_id": "critic-session-1",
            "question_answers": [_bound_answer(draft, "q-retry")],
        },
        {**draft["critics"][0], "run_id": "critic-run-2", "session_id": "critic-session-2"},
    ]
    _write(started["draft_path"], draft)
    missing = draft_module.check_review(str(started["draft_path"]))
    assert missing["status"] == "invalid"
    assert "critic-run-2/critic-session-2 did not answer" in _errors(missing)

    draft["critics"][1]["question_answers"] = [
        _bound_answer(draft, "q-retry", evidence="Independent read confirms the keyed write.")
    ]
    _write(started["draft_path"], draft)
    answered = draft_module.check_review(str(started["draft_path"]))
    assert answered["status"] == "ok", _errors(answered)


def test_an_edited_question_supersedes_answers_collected_for_the_previous_wording(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(started, questions=[Q_RETRY])
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critics"][0]["question_answers"] = [
        _bound_answer(draft, "q-retry", evidence="Inspected idempotency key.")
    ]
    _write(started["draft_path"], draft)
    before = draft_module.check_review(str(started["draft_path"]))
    assert before["status"] == "ok", _errors(before)
    v1_answer = draft["critics"][0]["question_answers"][0]

    v1_digest = _read(started["draft_path"])["context_package_digest"]
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = v1_digest
    template["questions"] = [{**Q_RETRY, "subject": REVOCATION_SUBJECT}]
    contract.write_json(_template_path(started), template)
    rerecorded = _record(started)
    assert rerecorded["superseded_questions"] == ["q-retry"]

    updated = _read(started["draft_path"])
    assert updated["critics"][0]["question_answers"] == []
    assert len(updated["superseded_question_results"]) == 1
    history = updated["superseded_question_results"][0]
    assert history["package_digest"] == v1_digest
    assert len(history["answers"]) == 1
    assert history["answers"][0]["evidence"] == "Inspected idempotency key."
    assert history["answers"][0]["run_id"] == "critic-run"
    assert history["answers"][0]["session_id"] == "child-session"
    assert history["answers"][0]["context_digest"] == v1_answer["context_digest"], (
        "history keeps the binding the answer was collected under"
    )

    stale = draft_module.check_review(str(started["draft_path"]))
    assert stale["status"] == "invalid"
    assert "superseded context package" in _errors(stale)

    updated["critics"][0]["question_answers"] = [
        _bound_answer(updated, "q-retry", evidence="Traced the revocation path in the exact head.")
    ]
    _write(started["draft_path"], updated)
    fresh = draft_module.check_review(str(started["draft_path"]))
    assert fresh["status"] == "ok", _errors(fresh)
    assert len(_read(started["draft_path"])["superseded_question_results"]) == 1, (
        "history is retained"
    )

    # A representation-only edit never invalidates collected results.
    current = _read(started["draft_path"])["context_package_digest"]
    narrative = contract.read_json(_template_path(started), "template")
    narrative["supersedes"] = current
    narrative["background"] = "Rewritten narrative, same facts."
    contract.write_json(_template_path(started), narrative)
    kept = _record(started)
    assert kept["superseded_questions"] == []
    final_draft = _read(started["draft_path"])
    assert len(final_draft["critics"][0]["question_answers"]) == 1
    assert len(final_draft["superseded_question_results"]) == 1
    still_valid = draft_module.check_review(str(started["draft_path"]))
    assert still_valid["status"] == "ok", _errors(still_valid)


def test_a_late_answer_for_the_previous_package_cannot_certify_the_changed_question(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(started, questions=[Q_RETRY])
    draft = complete_draft(_read(started["draft_path"]), started)
    # A real background critic can finish after the primary records a changed
    # package: the receipt is still on its way when the supersession happens.
    pending_v1 = {
        **draft["critics"][0],
        "question_answers": [
            _bound_answer(
                draft,
                "q-retry",
                evidence="Inspected the idempotency key only, before the package changed.",
            )
        ],
    }
    draft["critics"] = []
    _write(started["draft_path"], draft)
    v1 = draft["context_package_digest"]
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = v1
    template["questions"] = [{**Q_RETRY, "subject": REVOCATION_SUBJECT}]
    contract.write_json(_template_path(started), template)
    recorded = _record(started)
    assert recorded["superseded_questions"] == [], "nothing was attached when the package changed"

    updated = _read(started["draft_path"])
    updated["critics"] = [pending_v1]
    _write(started["draft_path"], updated)
    checked = draft_module.check_review(str(started["draft_path"]))
    assert checked["status"] == "invalid", "the stale V1 receipt was accepted for V2"
    assert "is bound to context digest" in _errors(checked)
    assert "q-retry" in _errors(checked)
    finished = draft_module.finish_review(str(started["draft_path"]))
    assert finished["status"] == "invalid", "finalization refused the stale receipt"
    assert "artifact_path" not in finished

    # Recovery: archive the late answer with its original binding and
    # authorship, then answer the current question with a freshly bound receipt.
    updated["superseded_question_results"] = [
        {
            "context_digest": pending_v1["question_answers"][0]["context_digest"],
            "package_digest": v1,
            "answers": [
                {
                    **pending_v1["question_answers"][0],
                    "run_id": pending_v1["run_id"],
                    "session_id": pending_v1["session_id"],
                }
            ],
            "verifications": [],
        }
    ]
    updated["critics"] = [
        {
            **pending_v1,
            "question_answers": [
                _bound_answer(
                    updated, "q-retry", evidence="Traced the revocation path in the exact head."
                )
            ],
        }
    ]
    _write(started["draft_path"], updated)
    recovered = draft_module.check_review(str(started["draft_path"]))
    assert recovered["status"] == "ok", _errors(recovered)
    done = draft_module.finish_review(str(started["draft_path"]))
    assert done["status"] == "ok", json.dumps(done)
    final_draft = _read(started["draft_path"])
    assert len(final_draft["superseded_question_results"]) == 1, "history is retained"
    assert final_draft["superseded_question_results"][0]["answers"][0]["run_id"] == "critic-run"
    assert (
        final_draft["superseded_question_results"][0]["answers"][0]["context_digest"]
        != final_draft["critics"][0]["question_answers"][0]["context_digest"]
    )


def test_an_answer_without_a_context_binding_is_retired_by_re_recording_never_counted(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(started, questions=[Q_RETRY])
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critics"][0]["question_answers"] = [
        {
            "question_id": "q-retry",
            "verdict": "confirmed",
            "evidence": "Collected before binding existed.",
        }
    ]
    _write(started["draft_path"], draft)
    unbound = draft_module.check_review(str(started["draft_path"]))
    assert unbound["status"] == "invalid"
    assert "has no context binding" in _errors(unbound)

    # Re-recording the current package retires the unbound result into history.
    recorded = _read(started["draft_path"])["context_package_digest"]
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = recorded
    contract.write_json(_template_path(started), template)
    rerecorded = _record(started)
    assert rerecorded["superseded_questions"] == ["q-retry"]
    updated = _read(started["draft_path"])
    assert updated["critics"][0]["question_answers"] == []
    assert len(updated["superseded_question_results"]) == 1
    assert (
        updated["superseded_question_results"][0]["answers"][0]["evidence"]
        == "Collected before binding existed."
    )

    demanded = draft_module.check_review(str(started["draft_path"]))
    assert demanded["status"] == "invalid"
    assert "superseded context package" in _errors(demanded)

    updated["critics"][0]["question_answers"] = [_bound_answer(updated, "q-retry")]
    _write(started["draft_path"], updated)
    recovered = draft_module.check_review(str(started["draft_path"]))
    assert recovered["status"] == "ok", _errors(recovered)
    assert len(_read(started["draft_path"])["superseded_question_results"]) == 1


def test_re_recording_an_edited_question_keeps_answers_for_unaffected_questions(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(
        started,
        questions=[
            Q_RETRY,
            {
                "id": "q-caller",
                "subject": "Do existing callers pass a stable key?",
                "source": "Primary inspection of the retry callers",
                "critic": True,
            },
        ],
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critics"][0]["question_answers"] = [
        _bound_answer(draft, "q-retry", evidence="Inspected idempotency key."),
        _bound_answer(draft, "q-caller", evidence="Both callers build the key from the request."),
    ]
    _write(started["draft_path"], draft)
    before = draft_module.check_review(str(started["draft_path"]))
    assert before["status"] == "ok", _errors(before)
    unaffected = draft["critics"][0]["question_answers"][1]

    recorded = _read(started["draft_path"])["context_package_digest"]
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = recorded
    template["questions"][0]["subject"] = REVOCATION_SUBJECT
    contract.write_json(_template_path(started), template)
    rerecorded = _record(started)
    assert rerecorded["superseded_questions"] == ["q-retry"]

    updated = _read(started["draft_path"])
    assert updated["critics"][0]["question_answers"] == [unaffected]
    stale = draft_module.check_review(str(started["draft_path"]))
    assert stale["status"] == "invalid"
    assert "superseded context package" in _errors(stale)

    updated["critics"][0]["question_answers"] = [
        *updated["critics"][0]["question_answers"],
        _bound_answer(updated, "q-retry", evidence="Traced the revocation path."),
    ]
    _write(started["draft_path"], updated)
    fresh = draft_module.check_review(str(started["draft_path"]))
    assert fresh["status"] == "ok", _errors(fresh)
    assert (
        _read(started["draft_path"])["critics"][0]["question_answers"][0]["context_digest"]
        == unaffected["context_digest"]
    ), "the unaffected answer keeps its original binding"


def test_a_significant_prior_decision_change_supersedes_answers_for_the_same_question(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture)
    _template_with(
        started,
        prior_decisions=[
            {
                "id": "scope-deferral",
                "decision": "Credential revocation is deferred; this review checks idempotency only.",
                "source": "Earlier user decision in the supplied conversation.",
            }
        ],
        questions=[
            {
                "id": "q-stable",
                "subject": "Does retry satisfy the agreed safety boundary?",
                "source": "Isolated test conversation",
                "critic": True,
            }
        ],
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    v1_answer = _bound_answer(
        draft, "q-stable", evidence="Checked idempotency under the originally agreed boundary."
    )
    v1_version = v1_answer["context_digest"]
    _write(started["draft_path"], draft)

    # The user withdraws the exception. The question keeps its ID and subject;
    # the significant agreed decision still changes the version it depends on.
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = _read(started["draft_path"])["context_package_digest"]
    template["prior_decisions"].append(
        {
            "id": "scope-correction",
            "decision": "The deferral is withdrawn; credential revocation is required in this review.",
            "source": "Explicit later user correction in the supplied conversation.",
        }
    )
    contract.write_json(_template_path(started), template)
    v2 = _record(started)
    assert v2["superseded_questions"] == []
    assert v2["question_context_versions"]["q-stable"] != v1_version, (
        "the agreed decision change moves the question version"
    )

    # The late V1 answer arrives with its original binding and cannot close V2.
    updated = _read(started["draft_path"])
    late_answer = {k: v for k, v in v1_answer.items() if k not in ("run_id", "session_id")}
    updated["critics"][0]["question_answers"] = [late_answer]
    _write(started["draft_path"], updated)
    checked = draft_module.check_review(str(started["draft_path"]))
    assert checked["status"] == "invalid"
    assert "is bound to context digest" in _errors(checked)
    finished = draft_module.finish_review(str(started["draft_path"]))
    assert finished["status"] == "invalid", "the stale answer must not finalize to ready"
    assert "artifact_path" not in finished

    # Documented recovery: re-record the current package; the stale answer moves
    # to history with its authorship and the binding it was collected under.
    template["supersedes"] = v2["digest"]
    contract.write_json(_template_path(started), template)
    v3 = _record(started)
    assert v3["superseded_questions"] == ["q-stable"]
    recovered = _read(started["draft_path"])
    assert recovered["critics"][0]["question_answers"] == []
    assert len(recovered["superseded_question_results"]) == 1
    history = recovered["superseded_question_results"][0]
    assert len(history["answers"]) == 1
    assert history["answers"][0]["evidence"] == v1_answer["evidence"]
    assert history["answers"][0]["run_id"] == "critic-run"
    assert history["answers"][0]["session_id"] == "child-session"
    assert history["answers"][0]["context_digest"] == v1_version

    demanded = draft_module.check_review(str(started["draft_path"]))
    assert demanded["status"] == "invalid"
    assert "superseded context package" in _errors(demanded)

    # A fresh bound answer finalizes; the finalized receipt carries only the
    # complete fresh evidence, never the retired one.
    recovered["critics"][0]["question_answers"] = [
        _bound_answer(
            recovered,
            "q-stable",
            evidence="Traced credential revocation under the corrected scope.",
        )
    ]
    _write(started["draft_path"], recovered)
    done = draft_module.finish_review(str(started["draft_path"]))
    assert done["status"] == "ok", json.dumps(done)
    receipt = _critic_receipt_payload(Path(str(started["artifact_root"])))
    assert len(receipt["question_answers"]) == 1
    assert (
        receipt["question_answers"][0]["evidence"]
        == "Traced credential revocation under the corrected scope."
    )
    assert (
        receipt["question_answers"][0]["context_digest"]
        == v3["question_context_versions"]["q-stable"]
    )
    assert len(_read(started["draft_path"])["superseded_question_results"]) == 1, (
        "history is retained"
    )


@pytest.mark.parametrize("change_kind", ["question", "prior-decision"])
def test_mixed_version_recovery_keeps_fresh_results_and_retires_only_the_stale_entry(
    fixture: ReviewFixture, change_kind: str
) -> None:
    started = _start(fixture)
    prior_decisions = (
        [
            {
                "id": "scope-deferral",
                "decision": "Credential revocation is deferred.",
                "source": "Earlier user decision.",
            }
        ]
        if change_kind == "prior-decision"
        else []
    )
    _template_with(started, questions=[Q_RETRY], prior_decisions=prior_decisions)
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critics"][0]["question_answers"] = [
        _bound_answer(draft, "q-retry", evidence="Critic A inspected the idempotency key under V1.")
    ]
    _write(started["draft_path"], draft)

    # Either the question or a significant prior decision changes; critic A's
    # V1 answer retires while a fresh V2 answer from critic B remains current.
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = _read(started["draft_path"])["context_package_digest"]
    if change_kind == "question":
        template["questions"][0]["subject"] = REVOCATION_SUBJECT
    else:
        template["prior_decisions"].append(
            {
                "id": "scope-correction",
                "decision": "The deferral is withdrawn; revocation is required in this review.",
                "source": "Explicit later user correction.",
            }
        )
    contract.write_json(_template_path(started), template)
    v2 = _record(started)
    assert v2["superseded_questions"] == ["q-retry"]

    # Critic B already returns a fresh V2 answer that the primary targets.
    updated = _read(started["draft_path"])
    v1_version = updated["superseded_question_results"][0]["answers"][0]["context_digest"]
    fresh_answer = _bound_answer(
        updated,
        "q-retry",
        verdict="not_verified",
        evidence=None,
        reason="Critic B could not trace the revocation path in time.",
    )
    fresh_verification = _bound_verification(
        updated,
        "q-retry",
        original={
            "run_id": "critic-run-b",
            "session_id": "critic-session-b",
            "verdict": "not_verified",
        },
        evidence="Primary traced the revocation path in the exact head.",
    )
    updated["critics"] = [
        updated["critics"][0],
        {
            **updated["critics"][0],
            "run_id": "critic-run-b",
            "session_id": "critic-session-b",
            "question_answers": [fresh_answer],
        },
    ]
    updated["critic_count"] = 2
    updated["question_verifications"] = [fresh_verification]
    _write(started["draft_path"], updated)

    # The late V1 answer from critic A arrives on top.
    updated["critics"][0]["question_answers"] = [
        {
            "question_id": "q-retry",
            "verdict": "confirmed",
            "evidence": "Critic A inspected the idempotency key under V1, late.",
            "context_digest": v1_version,
        }
    ]
    _write(started["draft_path"], updated)

    # Documented recovery: re-record the current package.
    template["supersedes"] = v2["digest"]
    contract.write_json(_template_path(started), template)
    v3 = _record(started)
    assert v3["superseded_questions"] == ["q-retry"]

    after = _read(started["draft_path"])
    assert after["critics"][0]["question_answers"] == [], (
        "only critic A's stale late answer leaves the active results"
    )
    assert after["critics"][1]["question_answers"] == [fresh_answer], "critic B's answer is intact"
    assert after["question_verifications"] == [fresh_verification]
    assert len(after["superseded_question_results"]) == 2
    late_history = after["superseded_question_results"][1]
    assert [item["evidence"] for item in late_history["answers"]] == [
        "Critic A inspected the idempotency key under V1, late."
    ]
    assert late_history["answers"][0]["run_id"] == "critic-run"
    assert late_history["answers"][0]["session_id"] == "child-session"
    assert late_history["answers"][0]["context_digest"] == v1_version
    assert late_history["verifications"] == []

    # A repeated recovery neither duplicates history nor drops fresh results.
    template["supersedes"] = v3["digest"]
    template["background"] = "Presentation-only narrative revision."
    contract.write_json(_template_path(started), template)
    v4 = _record(started)
    assert v4["superseded_questions"] == []
    stable = _read(started["draft_path"])
    assert len(stable["superseded_question_results"]) == 2
    assert stable["critics"][1]["question_answers"] == [fresh_answer]
    assert stable["question_verifications"] == [fresh_verification]

    # Critic A still owes a fresh answer for the assigned question; the retired
    # V1 answer never counts as the required current one.
    demanded = draft_module.check_review(str(started["draft_path"]))
    assert demanded["status"] == "invalid"
    assert "critic-run/child-session did not answer" in _errors(demanded)

    stable["critics"][0]["question_answers"] = [
        _bound_answer(stable, "q-retry", evidence="Critic A traced revocation under V2.")
    ]
    _write(started["draft_path"], stable)
    done = draft_module.finish_review(str(started["draft_path"]))
    assert done["status"] == "ok", json.dumps(done)
    receipt = _critic_receipt_payload(Path(str(started["artifact_root"])))
    receipt_evidence = [item.get("evidence") for item in receipt["question_answers"]]
    assert "Critic A traced revocation under V2." in receipt_evidence, (
        "the finalized receipt carries the fresh answers"
    )
    assert not any(
        isinstance(evidence, str) and "under V1" in evidence for evidence in receipt_evidence
    ), "the retired stale evidence never ships as an active answer"
    assert len(_read(started["draft_path"])["superseded_question_results"]) == 2, (
        "history is retained after finalization"
    )


def test_primary_verifications_follow_their_questions_context_version(
    fixture: ReviewFixture,
) -> None:
    started = _start(fixture, review_mode="fast")
    _template_with(
        started,
        questions=[
            {
                "id": "q-fast",
                "subject": "Is the fast scope really low risk?",
                "source": "User request",
                "critic": True,
            }
        ],
    )
    draft = complete_draft(_read(started["draft_path"]), started)
    draft["critic_count"] = 0
    draft["critics"] = []
    draft["low_risk"] = True
    draft["question_verifications"] = [_bound_verification(draft, "q-fast")]
    _write(started["draft_path"], draft)
    before = draft_module.check_review(str(started["draft_path"]))
    assert before["status"] == "ok", _errors(before)
    original_verification = draft["question_verifications"][0]

    # A verification attached when the question changes retires into history.
    v1 = draft["context_package_digest"]
    template = contract.read_json(_template_path(started), "template")
    template["supersedes"] = v1
    template["questions"][0]["subject"] = "Is the fast scope free of blocking findings?"
    contract.write_json(_template_path(started), template)
    recorded = _record(started)
    assert recorded["superseded_questions"] == ["q-fast"]
    updated = _read(started["draft_path"])
    assert updated["question_verifications"] == []
    assert len(updated["superseded_question_results"][0]["verifications"]) == 1
    assert (
        updated["superseded_question_results"][0]["verifications"][0]["context_digest"]
        == original_verification["context_digest"]
    ), "history keeps the binding the verification was performed under"

    # A late verification still bound to the previous version is rejected.
    updated["question_verifications"] = [_bound_verification(draft, "q-fast")]
    _write(started["draft_path"], updated)
    late = draft_module.check_review(str(started["draft_path"]))
    assert late["status"] == "invalid"
    assert "is bound to context digest" in _errors(late)

    updated["question_verifications"] = [_bound_verification(updated, "q-fast")]
    _write(started["draft_path"], updated)
    fresh = draft_module.check_review(str(started["draft_path"]))
    assert fresh["status"] == "ok", _errors(fresh)
    assert len(_read(started["draft_path"])["superseded_question_results"]) == 1
