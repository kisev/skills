"""Draft and local record-input scenarios, ported from ``draft-input.test.mjs``.

The public CLI scenarios drive ``python -m reviewmatic`` instead of the
TypeScript entrypoint. The TypeScript ``writeInput`` guard against
``undefined`` values has no Python counterpart (JSON ``null`` is explicit).
"""

from __future__ import annotations

import copy
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Callable

SRC = Path(__file__).resolve().parents[1] / "src"

DEPENDENCIES = {"paths": ["review.txt"], "thread_ids": [], "metadata_fields": [], "ci": False}


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


@pytest.fixture(name="write_input")
def write_input_factory(tmp_path: Path) -> Callable[[Any], str]:
    counter = itertools.count()

    def write(value: Any) -> str:
        path = tmp_path / f"input-{next(counter)}" / "input.json"
        path.parent.mkdir()
        contract.write_json(path, value)
        return str(path)

    return write


def spawn(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SRC)
    return subprocess.run(
        [sys.executable, "-m", "reviewmatic", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def _read(path: Any, label: str = "draft") -> dict[str, Any]:
    return contract.read_json(Path(str(path)), label)


def _finding() -> dict[str, Any]:
    return {
        "id": "primary-retry",
        "severity": "low",
        "summary": "The retry path repeats a write without an idempotency key.",
        "risk": "A retried request can duplicate a side effect.",
        "evidence": ["review.txt:2 repeats the write on the retry branch."],
        "consequence": "Duplicated writes surface as duplicated records downstream.",
        "relation_to_change": "The change touches exactly this retry path.",
        "minimum_fix": "Bind the retried write behind an idempotency key.",
    }


def _receipt_response(versions: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": None,
        "run_id": "critic-run-7",
        "session_id": "critic-session-7",
        "findings": [
            {
                "id": "critic-nit",
                "severity": "low",
                "summary": "The retry comment wording is ambiguous.",
                "risk": "A maintainer may misread the retry contract.",
                "evidence": ["review.txt:2 comment says retry loosely."],
                "consequence": "Slower future maintenance.",
                "relation_to_change": "The comment is part of the change.",
                "minimum_fix": "Name the idempotency key in the comment.",
            }
        ],
        "question_answers": [
            {
                "question_id": "q-idempotency",
                "verdict": "confirmed",
                "evidence": "The exact head binds writes behind the key.",
                "context_digest": versions["q-idempotency"],
            }
        ],
        "external_mutations": False,
    }


def _accept_primary() -> dict[str, Any]:
    return {
        "id": "primary-retry",
        "decision": "accept",
        "reason": "The exact retry path repeats a write.",
        "dependencies": copy.deepcopy(DEPENDENCIES),
    }


def _prepared_review(
    fixtures: Any,
) -> tuple[ReviewFixture, dict[str, Any], dict[str, Any]]:
    fixture: ReviewFixture = fixtures()
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
    recorded = draft_module.record_draft_package(str(started["draft_path"]), str(template_path))
    assert recorded["status"] == "ok"
    return fixture, started, recorded


def _thread_decisions_for(draft_path: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": thread["id"],
            "assessment": "fixed",
            "rationale": "The exact reviewed code already addresses the remark.",
            "outcome": "no_publication" if thread["state"] == "resolved" else "resolve",
            "proposed_response": None
            if thread["state"] == "resolved"
            else "The exact reviewed code now handles this path.",
        }
        for thread in _read(draft_path)["content"]["thread_decisions"]
    ]


def _semver_with_policy(draft_path: Any) -> dict[str, Any]:
    semver: dict[str, Any] = _read(draft_path)["content"]["semver_assessment"]
    semver["policy"] = "No publication configuration is available."
    semver["sources"] = ["Fixture repository and empty release catalog"]
    semver["fallback_reason"] = "No published release can be established."
    return semver


def _metadata_ok(draft_path: Any) -> dict[str, Any]:
    return {
        key: {**value, "status": "ok", "rationale": "The observed metadata is sufficient."}
        for key, value in _read(draft_path)["content"]["mr_metadata_assessment"].items()
    }


def _labels_assessed(draft_path: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "status": "applicable" if item["name"] == "semver::patch" else "inapplicable",
            "rationale": "Matches the assessed patch contribution.",
        }
        for item in _read(draft_path)["content"]["label_assessments"]
    ]


def _chat_assessment() -> dict[str, Any]:
    return {
        "necessity": {"status": "supported", "rationale": "The existing timeout is unbounded."},
        "relevance": {"status": "current", "rationale": "The current runner uses this path."},
        "change": "Bound the check.",
    }


def test_record_package_returns_the_ready_critic_task_with_exact_inputs(
    fixtures: Any,
) -> None:
    _fixture, started, recorded = _prepared_review(fixtures)
    task = recorded["critic_task"]
    assert task["launch"] == "now"
    assert task["context_package"]["path"] == recorded["artifact_path"]
    assert task["context_package"]["digest"] == recorded["digest"]
    assert re.fullmatch(
        r"[0-9a-f]{64}", task["context_package"]["question_context_versions"]["q-idempotency"]
    )
    assert task["inputs"]["evidence_path"] == started["evidence_path"]
    assert task["inputs"]["context_path"] == started["context_path"]
    assert task["inputs"]["inspection_path"] == started["inspection_path"]
    assert re.match(
        r"^reviewmatic record-critic", task["response_contract"]["import_command"]["command"]
    )
    assert task["response_contract"]["template"]["schema"] == "portable-gitlab/critic-receipt/v2"


def test_start_review_returns_the_prepared_scope_overview_with_author_claims_flagged(
    fixtures: Any,
) -> None:
    fixture, started, _recorded = _prepared_review(fixtures)
    requests = fixture.request_count()
    scope = started["scope"]
    assert scope["mode"] == "mr"
    assert scope["target"]["title"] == "Current merge request title"
    assert scope["description"]["source"] == "author_text"
    assert scope["description"]["text"] == "Current description"
    assert re.search(r"author or participant claims", scope["claim_notice"])
    assert scope["changed_files"]["paths"] == ["review.txt"]
    assert scope["discussions"]["threads"][0]["id"] == "discussion-42"
    assert scope["discussions"]["threads"][0]["position"]["path"] == "review.txt"
    assert scope["completeness"]["retrieval_complete"] is True
    assert (
        scope["inputs"]["inspection"]["diff_path"]
        == _read(started["inspection_path"], "inspection")["diff_path"]
    )
    assert scope["inputs"]["repo_root"] == started["review_worktree"]["path"]
    assert fixture.request_count() == requests

    printed = spawn("scope-review", "--artifact-root", str(started["artifact_root"]))
    assert printed.returncode == 0, printed.stderr
    emitted = json.loads(printed.stdout)
    assert emitted["status"] == "ok"
    assert emitted["scope"]["mode"] == "mr"
    assert emitted["scope"]["inputs"]["evidence_path"] == started["evidence_path"]
    assert fixture.request_count() == requests


def test_record_input_applies_semantic_sections_mechanically_and_preserves_machine_fields(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, _recorded = _prepared_review(fixtures)
    draft_path = str(started["draft_path"])
    before = _read(draft_path)
    before_digest = contract.digest(before)

    invalid = draft_module.record_draft_input(
        draft_path,
        write_input(
            {
                "unknown_section": [1],
                "content": {"summary": "", "issue_templates": []},
                "findings": [{"id": "broken"}],
            }
        ),
    )
    assert invalid["status"] == "invalid"
    paths = [issue["path"] for issue in invalid["errors"]]
    assert "$.unknown_section" in paths
    assert "$.content.issue_templates" in paths
    assert "$.content.summary" in paths
    assert "$.findings[0].severity" in paths
    envelope_path = write_input(
        {"schema": "portable-gitlab/analysis_report/v2", "payload": {"findings": []}}
    )
    with pytest.raises(
        contract.WorkflowError,
        match=r"(?s)envelope wrapper.*pass the object stored in the payload field",
    ):
        draft_module.record_draft_input(draft_path, envelope_path)
    assert contract.digest(_read(draft_path)) == before_digest, (
        "failed inputs never touch the draft"
    )

    first = draft_module.record_draft_input(
        draft_path,
        write_input(
            {
                "run_id": "primary-run-9",
                "session_id": "primary-session-9",
                "findings": [_finding()],
            }
        ),
    )
    assert first["status"] == "ok"
    assert first["applied"] == {
        "run_id": "primary-run-9",
        "session_id": "primary-session-9",
        "findings": 1,
    }
    assert first["pending"]["dispositions_missing_for"] == ["primary-retry"]
    after_first = _read(draft_path)
    assert after_first["evidence_digest"] == before["evidence_digest"]
    assert after_first["context_package_path"] == before["context_package_path"]
    assert after_first["critics"] == []

    second = draft_module.record_draft_input(
        draft_path,
        write_input(
            {
                "dispositions": [_accept_primary()],
                "content": {
                    "summary": "The bounded change meets the agreed contract.",
                    "architecture_assessment": "Existing ownership is preserved.",
                    "chat_assessment": _chat_assessment(),
                    "semver_impact": "patch",
                    "semver_rationale": "Backward-compatible correction.",
                    "semver_assessment": _semver_with_policy(draft_path),
                    "mr_metadata_assessment": _metadata_ok(draft_path),
                    "label_assessments": _labels_assessed(draft_path),
                    "thread_decisions": _thread_decisions_for(draft_path),
                    "checks": ["Inspected the exact committed diff; external tests were not run."],
                },
            }
        ),
    )
    assert second["status"] == "ok", json.dumps(second.get("errors"))
    assert second["pending"]["dispositions_missing_for"] == []
    assert second["pending"]["identity_missing"] == []
    assert second["pending"]["context_package"] == []
    assert second["pending"]["critics_expected"] == [
        "1 of 1 independent critic receipts are still expected"
    ]
    assert second["pending"]["labels_unresolved"] == 0


def test_record_critic_imports_a_receipt_verbatim_and_rejects_stale_answers(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, recorded = _prepared_review(fixtures)
    draft_path = str(started["draft_path"])
    draft_module.record_draft_input(
        draft_path,
        write_input(
            {
                "run_id": "primary-run-9",
                "session_id": "primary-session-9",
                "findings": [_finding()],
                "dispositions": [_accept_primary()],
            }
        ),
    )
    versions = recorded["question_context_versions"]

    stale = draft_module.record_draft_critic(
        draft_path,
        write_input(
            {
                **_receipt_response(versions),
                "evidence_digest": _read(draft_path)["evidence_digest"],
                "question_answers": [
                    {
                        "question_id": "q-idempotency",
                        "verdict": "confirmed",
                        "context_digest": "0" * 64,
                    }
                ],
            }
        ),
    )
    assert stale["status"] == "invalid"
    stale_issue = next(
        issue
        for issue in stale["errors"]
        if issue["path"] == "$.question_answers[0].context_digest"
    )
    assert re.search(re.escape(versions["q-idempotency"]), stale_issue["message"])
    assert re.search(r"Do not rebind an old answer", stale_issue["message"])
    assert _read(draft_path)["critics"] == []

    imported = draft_module.record_draft_critic(
        draft_path,
        write_input(
            {**_receipt_response(versions), "evidence_digest": _read(draft_path)["evidence_digest"]}
        ),
    )
    assert imported["status"] == "ok"
    assert imported["source_envelope_unwrapped"] is False
    assert imported["pending_critic_questions"] == []
    draft = _read(draft_path)
    assert len(draft["critics"]) == 1
    assert (
        draft["critics"][0]["findings"][0]["summary"] == "The retry comment wording is ambiguous."
    )
    assert draft["critics"][0]["question_answers"][0]["context_digest"] == versions["q-idempotency"]
    assert draft["critics"][0]["run_id"] == "critic-run-7"
    assert len(draft["dispositions"]) == 1, "the runtime never creates dispositions for critics"
    assert re.search(r"record-input", imported["dispositions"])

    duplicate = draft_module.record_draft_critic(
        draft_path,
        write_input(
            {
                **_receipt_response(versions),
                "evidence_digest": _read(draft_path)["evidence_digest"],
                "session_id": "critic-session-other",
            }
        ),
    )
    assert duplicate["status"] == "invalid"
    assert any(issue["path"] == "$.findings[0].id" for issue in duplicate["errors"]), (
        "a colliding critic finding id is named"
    )


def test_a_wrapped_review_report_envelope_is_unwrapped_mechanically(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, recorded = _prepared_review(fixtures)
    draft_path = str(started["draft_path"])
    draft_module.record_draft_input(
        draft_path, write_input({"run_id": "primary-run-9", "session_id": "primary-session-9"})
    )
    imported = draft_module.record_draft_critic(
        draft_path,
        write_input(
            {
                "schema": "portable-gitlab/review_report/v2",
                "kind": "review_report",
                "payload": {
                    **_receipt_response(recorded["question_context_versions"]),
                    "evidence_digest": _read(draft_path)["evidence_digest"],
                },
            }
        ),
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    assert imported["source_envelope_unwrapped"] is True
    assert len(_read(draft_path)["critics"]) == 1


def test_the_new_interface_completes_the_full_mr_cycle_without_manual_assembly(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    fixture, started, recorded = _prepared_review(fixtures)
    draft_path = str(started["draft_path"])
    draft_module.record_draft_input(
        draft_path,
        write_input(
            {
                "run_id": "primary-run-9",
                "session_id": "primary-session-9",
                "low_risk": False,
                "findings": [_finding()],
                "dispositions": [
                    _accept_primary(),
                    {
                        "id": "critic-nit",
                        "decision": "reject",
                        "reason": (
                            "Wording preference without a concrete consequence; "
                            "covered by primary-retry."
                        ),
                        "duplicate_of": "primary-retry",
                        "dependencies": {
                            "paths": [],
                            "thread_ids": [],
                            "metadata_fields": [],
                            "ci": False,
                        },
                    },
                ],
                "content": {
                    "summary": "The bounded change meets the agreed contract.",
                    "architecture_assessment": "Existing ownership is preserved.",
                    "chat_assessment": _chat_assessment(),
                    "semver_impact": "patch",
                    "semver_rationale": "Backward-compatible correction.",
                    "semver_assessment": _semver_with_policy(draft_path),
                    "mr_metadata_assessment": _metadata_ok(draft_path),
                    "label_assessments": _labels_assessed(draft_path),
                    "thread_decisions": _thread_decisions_for(draft_path),
                    "finding_publications": [
                        {
                            "finding_id": "primary-retry",
                            "type": "line",
                            "path": "review.txt",
                            "line": 2,
                            "old_line": None,
                            "body": (
                                "Bind the retried write behind the idempotency key.\n\n"
                                "```suggestion:-1+0\nreviewed change (idempotent)\n```"
                            ),
                            "fix_mode": "suggestion",
                            "patch": None,
                        }
                    ],
                    "checks": ["Inspected the exact committed diff; external tests were not run."],
                },
            }
        ),
    )
    draft_module.record_draft_critic(
        draft_path,
        write_input(
            {
                **_receipt_response(recorded["question_context_versions"]),
                "evidence_digest": _read(draft_path)["evidence_digest"],
            }
        ),
    )
    checked = draft_module.check_review(draft_path)
    assert checked["status"] == "ok", json.dumps(checked["errors"])
    requests = fixture.request_count()
    finished = draft_module.finish_review(draft_path)
    assert finished["status"] == "ok", json.dumps(finished)
    assert re.search(r"review", finished["chat"])
    assert fixture.request_count() - requests == 0, "finalization is local-only"
    assert re.search(
        r"reviewed change|retry", Path(str(finished["markdown_path"])).read_text(encoding="utf-8")
    )


def test_record_input_rejects_an_unwritable_shape_at_the_cli_boundary(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, _recorded = _prepared_review(fixtures)
    draft_path = Path(str(started["draft_path"]))
    before = draft_path.read_bytes()
    broken = spawn(
        "record-input", "--draft", str(draft_path), "--input", write_input({"verdict": "ready"})
    )
    assert broken.returncode == 2
    emitted = json.loads(broken.stdout)
    assert emitted["status"] == "invalid"
    assert any(issue["path"] == "$.verdict" for issue in emitted["errors"])
    assert draft_path.read_bytes() == before


def _local_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, filename: str) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "repository"
    repo.mkdir()

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)

    git("init", "--quiet", "--initial-branch=main")
    git("config", "user.email", "author@example.invalid")
    git("config", "user.name", "Local Author")
    git("config", "commit.gpgsign", "false")
    (repo / filename).write_text("base\n")
    git("add", filename)
    git("commit", "-qm", "base")
    return repo


def test_local_record_input_completes_the_prepared_template_and_finalizes_without_gitlab(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_input: Callable[[Any], str]
) -> None:
    repo = _local_repository(monkeypatch, tmp_path, "local.txt")
    (repo / "local.txt").write_text("base\nchanged\n")
    (repo / "notes.txt").write_text("untracked\n")
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    root = str(bundle["artifact_root"])
    bundle_path, _ = contract.write_artifact(Path(root), "local_wip_snapshot", bundle)
    followup = local_review.prepare_followup(
        root, bundle, contract.digest(contract.read_json(bundle_path, "evidence")), "auto"
    )
    template_path = Path(str(followup["context_package"]["template_path"]))
    template = contract.read_json(template_path, "local package template")
    template["questions"] = [
        {
            "id": "q-local-scope",
            "subject": "Do unstaged edits belong to the same task boundary?",
            "source": "Primary inspection of the working tree.",
            "critic": True,
        }
    ]
    contract.write_json(template_path, template)
    invalid = local_review.record_local_input(str(bundle_path), write_input({"mode": "full"}))
    assert invalid["status"] == "invalid"
    assert any(issue["path"] == "$.mode" for issue in invalid["errors"])

    applied = local_review.record_local_input(
        str(bundle_path),
        write_input(
            {
                "task": {
                    "goal": "Rename the local flag without touching mixed output.",
                    "acceptance_criteria": ["The flag rename is complete."],
                    "constraints": [],
                    "accepted_risks": [],
                    "deferred": [],
                    "decision_evidence": (
                        "The requester confirmed the rename boundary in the task interview."
                    ),
                },
                "findings": [
                    {
                        "id": "local-flag",
                        "severity": "low",
                        "status": "open",
                        "summary": "The renamed flag misses one call site.",
                        "requirement": "Every call site uses the new flag.",
                        "scenario": "A script passes the old flag name.",
                        "evidence": "scripts/run.sh still passes --old-flag.",
                        "consequence": "The script silently ignores the rename.",
                        "origin": "regression",
                        "minimum_fix": "Update the call site.",
                        "blocking": False,
                        "rationale": "A one-line correction restores the behavior.",
                        "decision_evidence": None,
                        "reopen_reason": None,
                    }
                ],
                "checks": [
                    {
                        "name": "Call sites",
                        "status": "passed",
                        "required": True,
                        "evidence": "grep found no old flag.",
                    }
                ],
                "assessment": "The rename is complete and safe to accept.",
                "verdict": "ready",
            }
        ),
    )
    assert applied["status"] == "ok", json.dumps(applied.get("errors"))
    draft_path = str(applied["draft_path"])
    assert Path(draft_path).exists()
    draft = _read(draft_path, "local draft")
    assert draft["mode"] == followup["mode"]
    assert draft["evidence_digest"] == contract.digest(contract.read_json(bundle_path, "evidence"))
    assert draft["findings"][0]["id"] == "local-flag"

    recorded = local_review.record_local_package(str(bundle_path), str(template_path))
    assert recorded["status"] == "ok"
    assert re.search(
        r"record-input", recorded["critic_task"]["response_contract"]["import_command"]["command"]
    )
    assert (
        recorded["critic_task"]["context_package"]["question_context_versions"]["q-local-scope"]
        == recorded["question_context_versions"]["q-local-scope"]
    )
    answered = local_review.record_local_input(
        str(bundle_path),
        write_input(
            {
                "question_answers": [
                    {
                        "question_id": "q-local-scope",
                        "verdict": "confirmed",
                        "evidence": (
                            "The unstaged edit continues the same rename; "
                            "no boundary change is visible."
                        ),
                        "run_id": "critic-run-local",
                        "session_id": "critic-session-local",
                        "context_digest": recorded["question_context_versions"]["q-local-scope"],
                    }
                ]
            }
        ),
    )
    assert answered["status"] == "ok", json.dumps(answered.get("errors"))
    fresh = local_review.finalize_local(str(bundle_path))
    assert fresh["status"] == "ok"
    review = local_review.record_review(root, str(bundle_path), draft_path)
    assert review["mode"] == followup["mode"]
    assert review["verdict"] == "ready"
    assert not (Path(root) / "gitlab").exists(), "local mode never creates GitLab state"


def test_canonical_schema_failures_name_the_offending_fields(fixtures: Any) -> None:
    fixture: ReviewFixture = fixtures()
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo), locale="en")
    with pytest.raises(contract.WorkflowError, match=r"canonical schema:\n - \$"):
        draft_module.record_draft_package(
            str(started["draft_path"]), str(started["context_package"]["template_path"])
        )


def test_record_input_updates_an_existing_thread_by_id_and_rejects_forged_bindings(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, _recorded = _prepared_review(fixtures)
    draft_path = Path(str(started["draft_path"]))
    thread = _read(draft_path)["content"]["thread_decisions"][0]
    machine = {
        "url": thread["url"],
        "state": thread["state"],
        "last_note_id": thread["last_note_id"],
        "last_note_body_sha256": thread["last_note_body_sha256"],
        "thread_sha256": thread["thread_sha256"],
    }

    # A semantic update carries the id and the decision fields only.
    applied = draft_module.record_draft_input(
        str(draft_path),
        write_input(
            {
                "content": {
                    "thread_decisions": [
                        {
                            "id": thread["id"],
                            "assessment": "fixed",
                            "rationale": "The exact reviewed code already addresses the remark.",
                            "outcome": "resolve",
                            "proposed_response": "The exact reviewed code now handles this path.",
                        }
                    ]
                }
            }
        ),
    )
    assert applied["status"] == "ok", json.dumps(applied.get("errors"))
    updated = _read(draft_path)["content"]["thread_decisions"][0]
    for field, value in machine.items():
        assert updated[field] == value, f"{field} stays with the runtime"
    assert updated["assessment"] == "fixed"
    assert updated["rationale"] == "The exact reviewed code already addresses the remark."

    # An unknown thread id cannot smuggle a hand-assembled record in.
    unknown = draft_module.record_draft_input(
        str(draft_path),
        write_input(
            {
                "content": {
                    "thread_decisions": [
                        {
                            "id": "not-collected",
                            "assessment": "fixed",
                            "rationale": "x",
                            "outcome": "resolve",
                        }
                    ]
                }
            }
        ),
    )
    assert unknown["status"] == "invalid"
    assert any(
        issue["path"] == "$.content.thread_decisions[0].url" for issue in unknown["errors"]
    ), "a new thread record still requires the full prepared shape"

    # A machine field that disagrees with the prepared binding is rejected and
    # the draft keeps the previously applied decision unchanged.
    draft_before = draft_path.read_bytes()
    forged = draft_module.record_draft_input(
        str(draft_path),
        write_input(
            {
                "content": {
                    "thread_decisions": [
                        {
                            "id": thread["id"],
                            "assessment": "neutral",
                            "url": "https://forged.example/t",
                        }
                    ]
                }
            }
        ),
    )
    assert forged["status"] == "invalid"
    forged_issue = next(
        issue for issue in forged["errors"] if issue["path"] == "$.content.thread_decisions[0].url"
    )
    assert re.search(r"Runtime-owned thread binding", forged_issue["message"])
    assert re.search(re.escape(thread["url"]), forged_issue["message"])
    assert draft_path.read_bytes() == draft_before
    preserved = _read(draft_path)["content"]["thread_decisions"][0]
    assert preserved["assessment"] == "fixed", "the previously applied decision survives"
    assert preserved["url"] == machine["url"]


def test_malformed_list_shapes_return_addressed_diagnostics_and_never_touch_the_draft(
    fixtures: Any, write_input: Callable[[Any], str]
) -> None:
    _fixture, started, recorded = _prepared_review(fixtures)
    draft_path = Path(str(started["draft_path"]))
    before = draft_path.read_bytes()
    shapes: tuple[Any, ...] = (None, {}, [None])
    for value in shapes:
        local = draft_module.record_draft_input(str(draft_path), write_input({"findings": value}))
        assert local["status"] == "invalid", json.dumps(value)
        item_level = isinstance(value, list)
        assert any(
            issue["path"] == ("$.findings[0]" if item_level else "$.findings")
            for issue in local["errors"]
        ), f"findings {json.dumps(value)} names the offending path"
        threads = draft_module.record_draft_input(
            str(draft_path), write_input({"content": {"thread_decisions": value}})
        )
        assert threads["status"] == "invalid"
        assert any(
            issue["path"].startswith("$.content.thread_decisions") for issue in threads["errors"]
        ), f"thread_decisions {json.dumps(value)} names the offending path"
        assert draft_path.read_bytes() == before, "the draft is unchanged after each error"
    critic = draft_module.record_draft_critic(
        str(draft_path),
        write_input(
            {
                **recorded["critic_task"]["response_contract"]["template"],
                "run_id": "critic-run-shape",
                "session_id": "critic-session-shape",
                "findings": [None],
            }
        ),
    )
    assert critic["status"] == "invalid"
    assert any(issue["path"] == "$.findings[0]" for issue in critic["errors"])
    assert draft_path.read_bytes() == before


def test_the_documented_local_cycle_keeps_original_critic_answers_across_imports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_input: Callable[[Any], str]
) -> None:
    repo = _local_repository(monkeypatch, tmp_path, "review.txt")
    (repo / "review.txt").write_text("base\nreviewed change\nlocal edit\n")

    prepared = spawn("prepare-local", "--repo-root", str(repo))
    assert prepared.returncode == 0, prepared.stderr
    emitted = json.loads(prepared.stdout)
    bundle_path = emitted["bundle"]
    root = emitted["scope_overview"]["inputs"]["artifact_root"]

    # Documented order: record-package before record-input; the draft already
    # exists and binds the recorded package without any manual field copying.
    template_path = Path(str(emitted["review"]["context_package"]["template_path"]))
    template = contract.read_json(template_path, "local package template")
    template["questions"] = [
        {"id": "q", "subject": "Is retry bounded?", "source": "Task", "critic": True}
    ]
    contract.write_json(template_path, template)
    packaged = spawn("record-package", "--bundle", bundle_path, "--input", str(template_path))
    assert packaged.returncode == 0, packaged.stderr
    package_result = json.loads(packaged.stdout)
    versions = package_result["question_context_versions"]

    filled = spawn(
        "record-input",
        "--bundle",
        bundle_path,
        "--input",
        write_input(
            {
                "task": {
                    "goal": "Bound retry",
                    "acceptance_criteria": ["Bounded"],
                    "constraints": [],
                    "accepted_risks": [],
                    "deferred": [],
                    "decision_evidence": "Fixture task",
                },
                "checks": [
                    {
                        "name": "Fixture read-only inspection",
                        "status": "passed",
                        "required": True,
                        "evidence": "Inspected",
                    }
                ],
                "assessment": "Inspected",
                "verdict": "ready",
            }
        ),
    )
    assert filled.returncode == 0, filled.stderr
    draft_path = json.loads(filled.stdout)["draft_path"]
    assert (
        _read(draft_path, "local draft")["context_package"]["path"]
        == package_result["artifact_path"]
    ), "record-package binds into the draft prepared for this snapshot"

    def answer(identity: str, verdict: str, **extra: str) -> dict[str, Any]:
        return {
            "question_id": "q",
            "context_digest": versions["q"],
            "run_id": identity,
            "session_id": identity,
            "verdict": verdict,
            **extra,
        }

    def import_answer(entry: dict[str, Any]) -> dict[str, Any]:
        return local_review.record_local_input(
            bundle_path, write_input({"question_answers": [entry]})
        )

    def stored() -> list[str]:
        return [
            f"{item['run_id']}:{item['verdict']}"
            for item in _read(draft_path, "local draft")["question_answers"]
        ]

    assert (
        import_answer(answer("critic-one", "not_verified", reason="Cannot verify"))["status"]
        == "ok"
    )
    assert (
        import_answer(answer("critic-two", "refuted", evidence="Refuted by trace"))["status"]
        == "ok"
    )
    assert stored() == ["critic-one:not_verified", "critic-two:refuted"], (
        "the second import keeps the first critic's original answer"
    )

    # A repeat of the same result is not duplicated.
    assert (
        import_answer(answer("critic-two", "refuted", evidence="Refuted by trace"))["status"]
        == "ok"
    )
    assert len(stored()) == 2

    # A different result under the same identity is rejected, not merged away.
    before = Path(draft_path).read_bytes()
    conflict = import_answer(answer("critic-two", "confirmed", evidence="Rewritten"))
    assert conflict["status"] == "invalid"
    assert [issue["path"] for issue in conflict["errors"]] == ["$.question_answers[0]"]
    assert Path(draft_path).read_bytes() == before
    assert stored() == ["critic-one:not_verified", "critic-two:refuted"]

    # The preserved not_verified answer still demands a primary verification.
    with pytest.raises(contract.WorkflowError, match=r"critic answer for q is not_verified"):
        local_review.record_review(root, bundle_path, draft_path)
    verified = local_review.record_local_input(
        bundle_path,
        write_input(
            {
                "question_verifications": [
                    {
                        "question_id": "q",
                        "context_digest": versions["q"],
                        "verdict": "confirmed",
                        "evidence": "Primary traced the bounded retry",
                        "original": {
                            "run_id": "critic-one",
                            "session_id": "critic-one",
                            "verdict": "not_verified",
                        },
                    }
                ]
            }
        ),
    )
    assert verified["status"] == "ok", json.dumps(verified.get("errors"))
    finalized = local_review.record_review(root, bundle_path, draft_path)
    assert finalized["verdict"] == "ready"
    assert finalized["question_summary"]["unverified"] == 0
    assert [item["run_id"] for item in _read(draft_path, "local draft")["question_answers"]] == [
        "critic-one",
        "critic-two",
    ], "finalization keeps both independent answers"


def test_a_repeated_local_scope_review_restores_task_baseline_and_paths_without_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, write_input: Callable[[Any], str]
) -> None:
    repo = _local_repository(monkeypatch, tmp_path, "review.txt")

    # First run: no scope exists yet.
    empty = spawn("prepare-local", "--repo-root", str(repo))
    assert empty.returncode == 2, empty.stderr
    assert json.loads(empty.stdout)["status"] == "empty_scope"

    # Unfinished draft: the task and paths survive a read-only reprint.
    (repo / "review.txt").write_text("base\nedited\n")
    prepared = spawn("prepare-local", "--repo-root", str(repo))
    assert prepared.returncode == 0, prepared.stderr
    first = json.loads(prepared.stdout)
    root = first["scope_overview"]["inputs"]["artifact_root"]
    draft_path = first["review"]["draft_path"]
    local_review.record_local_input(
        first["bundle"],
        write_input(
            {
                "task": {
                    "goal": "Bound retry",
                    "acceptance_criteria": ["Bounded"],
                    "constraints": [],
                    "accepted_risks": [],
                    "deferred": [],
                    "decision_evidence": "Fixture task",
                }
            }
        ),
    )
    draft_before = _read(draft_path, "local draft")
    reprepare = spawn("prepare-local", "--repo-root", str(repo))
    assert reprepare.returncode == 0, reprepare.stderr
    redrafted = _read(draft_path, "local draft")
    assert redrafted["evidence_digest"] == json.loads(reprepare.stdout)["digest"]
    assert redrafted["task"] == draft_before["task"], "the same content never resets the draft"
    template_file = Path(str(first["review"]["context_package"]["template_path"]))
    template_bytes = template_file.read_bytes()
    reprint = spawn("scope-review", "--artifact-root", root)
    assert reprint.returncode == 0, reprint.stderr
    scope = json.loads(reprint.stdout)["scope"]
    assert scope["task"]["goal"] == "Bound retry"
    assert scope["inputs"]["draft_path"] == draft_path
    assert scope["inputs"]["context_package_template"] == str(template_file)
    assert _read(draft_path, "local draft") == redrafted, "reprint never rewrites the draft"
    assert template_file.read_bytes() == template_bytes, (
        "reprint never rewrites the package template"
    )

    # Finalized baseline: the reprint still exposes the recorded baseline. The
    # cycle continues on the re-prepared snapshot the runtime selected.
    current = json.loads(reprepare.stdout)
    current_template = Path(str(current["review"]["context_package"]["template_path"]))
    contract.write_json(current_template, contract.read_json(current_template, "template"))
    packaged = spawn(
        "record-package", "--bundle", current["bundle"], "--input", str(current_template)
    )
    assert packaged.returncode == 0, packaged.stderr
    local_review.record_local_input(
        current["bundle"],
        write_input(
            {
                "checks": [
                    {
                        "name": "Inspection",
                        "status": "passed",
                        "required": True,
                        "evidence": "Inspected",
                    }
                ],
                "assessment": "Inspected",
                "verdict": "ready",
            }
        ),
    )
    finished = spawn("finalize-local", "--bundle", current["bundle"], "--report", draft_path)
    assert finished.returncode == 0, finished.stderr
    assert json.loads(finished.stdout)["review"]["verdict"] == "ready"
    baseline = spawn("scope-review", "--artifact-root", root)
    assert baseline.returncode == 0, baseline.stderr
    baseline_scope = json.loads(baseline.stdout)["scope"]
    assert (
        baseline_scope["previous_review"]["digest"]
        == json.loads(finished.stdout)["review"]["digest"]
    )
    assert baseline_scope["previous_review"]["mode"] == "unchanged"

    # Next snapshot: the runtime rebinds its own fields; unfinished prior work
    # on the same snapshot was never lost and the new draft follows the new
    # evidence digest without manual repair.
    (repo / "review.txt").write_text("base\nedited twice\n")
    following = spawn("prepare-local", "--repo-root", str(repo))
    assert following.returncode == 0, following.stderr
    second = json.loads(following.stdout)
    assert second["digest"] == second["review"]["report_template"]["evidence_digest"]
    assert second["review"]["report_template"]["evidence_digest"] != first["digest"]
    assert second["review"]["report_template"]["task"]["goal"] == "Bound retry"
    local_review.record_local_input(
        second["bundle"], write_input({"assessment": "Rechecked updated source"})
    )
    redraft = _read(draft_path, "local draft")
    assert redraft["evidence_digest"] == second["digest"]
    assert redraft["mode"] == "incremental"
    assert redraft["assessment"] == "Rechecked updated source"
