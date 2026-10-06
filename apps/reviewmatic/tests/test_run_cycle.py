"""The run cycle and artifact replacement, including the MR !297 deadlock.

The scenario: a decision artifact is recorded with ``findings: []``, the
content stage gains a real finding, and ``scaffold-review`` fails because the
plan findings no longer match the recorded decision.  The state machine cannot
re-record a decision from ``content_missing``; ``replace-artifact`` rebinds a
repaired decision and the scaffold passes.

The run tests drive ``reviewmatic run`` end to end against the fake glab:
callbacks automate every authoring stop in one process, and without callbacks
the run prints ready manual commands and ``--resume`` continues.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import render, workflow
from reviewmatic.cli import build_parser
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


def decision_payload(
    fixture: ReviewFixture,
    template: dict[str, Any],
    run_id: str,
    session_id: str,
    *,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = findings
    blocking = [item["id"] for item in accepted if item["severity"] != "low"]
    return {
        **template,
        "run_id": run_id,
        "session_id": session_id,
        "verdict": "not_ready" if blocking else "ready",
        "blocking_findings": bool(blocking),
        "blocking_finding_ids": blocking,
        "findings": findings,
        "accepted_findings": accepted,
        "responses": [
            *(
                {**item, "decision": "accept", "reason": "Confirmed on the exact reviewed head."}
                for item in template["responses"]
            ),
            *[
                {"id": item["id"], "decision": "accept", "reason": "Confirmed on the exact head."}
                for item in findings
            ],
        ],
        "critic_findings": [],
        "critic_target_finding_ids": [],
    }


def filled_content(template: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    publications = [
        {
            "finding_id": item["id"],
            "type": "general",
            "path": None,
            "line": None,
            "old_line": None,
            "body": "Document the idempotency key beside the retry example.",
            "fix_mode": "patch",
            "patch_reason": "The documented setup has no suggestion anchor.",
            "patch": (
                "diff --git a/retry-policy.txt b/retry-policy.txt\n"
                "new file mode 100644\n--- /dev/null\n+++ b/retry-policy.txt\n"
                "@@ -0,0 +1 @@\n+reserve idempotency key\n"
            ),
        }
        for item in findings
    ]
    return {
        **template,
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The retry defect is confirmed."},
            "relevance": {"status": "current", "rationale": "The exact head is current."},
            "change": "The change adds retry behavior and needs the key documented.",
        },
        "summary": "The change is small and preserves the reviewed contract.",
        "architecture_assessment": "The responsibility remains with its existing owner.",
        "semver_impact": "patch",
        "semver_rationale": "The fix changes behavior without changing the public API.",
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
        "findings": findings,
        "finding_publications": publications,
        "previous_finding_assessments": [],
        "recommended_issues": [],
        "rejected_candidates": [
            {**candidate, "reason": "Not observable in the exact reviewed head."}
            for candidate in template.get("rejected_candidates", [])
        ],
        "rejected_candidate_assessments": [
            {**item, "reason": "The exact head does not contain the reported gap."}
            for item in template["rejected_candidate_assessments"]
        ],
        "thread_decisions": [
            {
                **thread,
                "assessment": "fixed",
                "rationale": "The exact reviewed code addresses the remark.",
                "outcome": "resolve"
                if thread.get("state", "open") == "open"
                else thread["outcome"],
                "proposed_response": "The exact reviewed code handles this path.",
            }
            for thread in template["thread_decisions"]
        ],
    }


def prepare_fast_review(fixture: ReviewFixture) -> tuple[Path, str, str, str]:
    """Collect evidence and context in fast mode; return root and key paths."""
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
    )
    prepared = review_context.prepare_context(
        evidence_path, str(fixture.repo), "auto", "fast", "en"
    )
    assert prepared["status"] == "ok"
    return root, evidence_path, str(prepared["artifact_path"]), str(prepared["digest"])


def test_replace_artifact_repairs_a_defective_decision(fixture: ReviewFixture) -> None:
    root, evidence_path, context_path, _context_digest = prepare_fast_review(fixture)
    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    decision = review_context.template_review(str(root), "decision")
    template = contract.read_json(Path(decision["template_path"]), "decision template")
    defective = decision_payload(fixture, template, "primary-run", "primary-session", findings=[])
    recorded = workflow.decide(
        argparse.Namespace(
            evidence=evidence_path,
            report=str(_write(fixture, "defective-decision.json", defective)),
            context=context_path,
            finalize_report=_progress(root, "finalize_report_path"),
            critic_receipt=None,
            mode="fast",
        )
    )
    assert recorded["status"] == "ok"
    assert review_context.review_status(str(root))["stage"] == "content_missing"

    content = review_context.template_review(str(root), "content")
    content_template = contract.read_json(Path(content["template_path"]), "content template")
    edited = filled_content(content_template, [low_finding()])
    edited_path = _write(fixture, "review-content.json", edited)
    with pytest.raises(
        contract.WorkflowError, match="plan content mirrors the decision findings exactly"
    ):
        review_context.scaffold_review(
            evidence_path, context_path, str(_progress(root, "decision_path")), str(edited_path)
        )

    repaired = decision_payload(
        fixture, template, "primary-run", "primary-session", findings=[low_finding()]
    )
    repaired_path = _write(fixture, "repaired-decision.json", repaired)
    previous_digest = _progress(root, "decision_digest")
    parsed = build_parser().parse_args(
        [
            "replace-artifact",
            "--artifact-root",
            str(root),
            "--kind",
            "decision",
            "--path",
            str(repaired_path),
        ]
    )
    assert parsed.artifactRoot == str(root)
    assert parsed.kind == "decision"
    assert parsed.path == str(repaired_path)
    result = workflow.replace_artifact(_replace_args(root, "decision", repaired_path))
    assert result["status"] == "ok"
    assert result["stage"] == "content_missing"
    assert result["previous_digest"] == previous_digest
    # The replaced artifact stays in the content-addressed store.
    assert Path(str(_progress(root, "decision_path"))).read_bytes() != b""
    assert (root / "artifacts" / "review_decision" / f"{previous_digest}.json").exists()
    assert _progress(root, "decision_digest") == result["digest"]
    assert review_context.review_status(str(root))["stage"] == "content_missing"

    plan = review_context.scaffold_review(
        evidence_path, context_path, str(_progress(root, "decision_path")), str(edited_path)
    )
    assert plan["status"] == "ok"
    assert plan["stage"] == "plan_ready"
    assert review_context.load_progress(root) is not None
    assert _progress(root, "stage") == "plan_ready"


def test_replace_artifact_rewinds_downstream_and_rejects_unbound_artifacts(
    fixture: ReviewFixture,
) -> None:
    root, _evidence_path, context_path, _digest = prepare_fast_review(fixture)
    assert workflow.finalize(str(root))["stage"] == "decision_missing"
    decision = review_context.template_review(str(root), "decision")
    template = contract.read_json(Path(decision["template_path"]), "decision template")
    workflow.decide(
        argparse.Namespace(
            evidence=_progress(root, "evidence_path"),
            report=str(
                _write(
                    fixture,
                    "decision.json",
                    decision_payload(fixture, template, "run", "session", findings=[]),
                )
            ),
            context=context_path,
            finalize_report=_progress(root, "finalize_report_path"),
            critic_receipt=None,
            mode="fast",
        )
    )
    assert _progress(root, "stage") == "content_missing"

    stale_decision = dict(
        decision_payload(fixture, template, "run", "session", findings=[]),
        evidence_digest="f" * 64,
    )
    with pytest.raises(contract.WorkflowError, match="does not bind the current review state"):
        workflow.replace_artifact(
            _replace_args(root, "decision", _write(fixture, "bad-decision.json", stale_decision))
        )
    with pytest.raises(contract.WorkflowError, match="no bound critic receipt"):
        workflow.replace_artifact(
            _replace_args(root, "critic_receipt", _write(fixture, "receipt.json", {"schema": "x"}))
        )

    same_context = contract.read_json(Path(context_path), "review context")["payload"]
    result = workflow.replace_artifact(
        _replace_args(root, "context", _write(fixture, "context.json", same_context))
    )
    assert result["status"] == "ok"
    assert result["stage"] == "context_ready"
    progress = _progress(root, "")
    assert progress["context_digest"] == result["digest"]
    for field in ("finalize_report", "decision", "plan"):
        assert progress[f"{field}_path"] is None
        assert progress[f"{field}_digest"] is None
    status = review_context.review_status(str(root))
    assert status["stage"] == "finalize_missing"

    unbound = dict(same_context, evidence_digest="f" * 64)
    with pytest.raises(contract.WorkflowError, match="does not bind the current evidence"):
        workflow.replace_artifact(
            _replace_args(root, "context", _write(fixture, "bad-context.json", unbound))
        )


def test_run_completes_the_cycle_with_callbacks(fixture: ReviewFixture, capsys: Any) -> None:
    callbacks = _write_callbacks(fixture)
    participants = _write(fixture, "participants.json", ONE_MODEL_CRITIC)
    code = cli_main(
        [
            "run",
            "--url",
            fixture.url,
            "--repo-root",
            str(fixture.repo),
            "--review-mode",
            "normal",
            "--participants",
            str(participants),
            "--critic-cmd",
            callbacks["critic"],
            "--arbitrator-cmd",
            callbacks["decision"],
            "--content-cmd",
            callbacks["content"],
            "--json",
        ]
    )
    assert code == 0
    result = _stdout_json(capsys)
    assert result["status"] == "ok"
    assert result["stage"] == "plan_ready"
    steps = [item["step"] for item in result["timings"]]
    for expected in (
        "prepare",
        "begin",
        "context",
        "panel-selection",
        "critic-callback-critic-1",
        "critic-record-critic-1",
        "finalize",
        "decision-template",
        "decision-callback",
        "decision-record",
        "content-render",
        "content-callback",
        "content-prose-apply",
        "content-finalize",
        "report",
    ):
        assert expected in steps, f"{expected} must be logged with its timing"
    assert result["total_seconds"] > 0
    assert result["report"]["status"] == "ok"
    runbook = Path(str(_progress(Path(str(result["artifact_root"])), "plan_path")))
    assert runbook.exists()
    _print_timings("run with callbacks", result)


ONE_MODEL_CRITIC: dict[str, Any] = {
    "critics": [{"name": "critic-1", "engine": "model"}],
    "arbitrator": {"name": "arbitrator-1"},
}


def test_run_waits_prints_manual_commands_and_resumes(fixture: ReviewFixture, capsys: Any) -> None:
    base = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo), "--json"]

    # The first stop is the panel poll: fill the selection template and resume.
    assert cli_main([*base]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "critic_missing"
    assert waiting["template_kind"] == "participants"
    assert waiting["manual_argv"][0] == "reviewmatic"
    contract.write_json(Path(waiting["template_path"]), ONE_MODEL_CRITIC)
    participants = waiting["template_path"]

    # The model critic fills its template in place, then runs the printed
    # record-run-critic command; the completed panel merges into one receipt.
    assert cli_main([*base[:-1], "--resume", "--participants", participants, "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "critic_missing"
    assert waiting["template_kind"] == "critic"
    assert waiting["participant"] == "critic-1"
    assert "record-run-critic" in waiting["manual_command"]
    _fill_template(waiting["template_path"], {"run_id": "critic-run", "session_id": "critic-s"})
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main([*base[:-1], "--resume", "--participants", participants, "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "decision_missing"
    assert "finalize-review" in waiting["manual_command"]

    _fill_template(
        waiting["template_path"],
        {
            "run_id": "primary-run",
            "session_id": "primary-session",
            "responses": [
                {"id": "thread:42", "decision": "accept", "reason": "still open"},
            ],
        },
    )
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main([*base, "--resume"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "content_missing"
    assert "record-prose" in waiting["manual_command"]
    template = contract.read_json(Path(waiting["template_path"]), "content template")
    contract.write_json(
        Path(waiting["template_path"]), render.prose_projection(filled_content(template, []))
    )
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main([*base, "--resume"]) == 0
    final = _stdout_json(capsys)
    assert final["status"] == "ok"
    assert final["stage"] == "plan_ready"
    assert final["report"]["status"] == "ok"
    _print_timings("run with manual stops", final)


def test_run_failure_writes_a_state_dump(fixture: ReviewFixture, capsys: Any) -> None:
    code = cli_main(
        [
            "run",
            "--url",
            fixture.url,
            "--repo-root",
            str(Path(fixture.repo) / "missing"),
            "--json",
        ]
    )
    assert code == 1
    result = _stdout_json(capsys)
    assert result["status"] == "error"
    assert result["stage"] == "prepared"
    assert "checkout" in result["error"] or "Git" in result["error"]
    dump = Path(str(result["artifact_root"])) / "run-failure.json"
    assert dump.exists()
    written = contract.read_json(dump, "run failure")
    assert written["stage"] == "prepared"
    assert written["resume_command"].startswith("reviewmatic run --resume")


def test_run_stops_after_bounded_attempts_on_permanently_incomplete_evidence(
    fixture: ReviewFixture, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Permanently incomplete evidence stops the run loudly, never loops."""
    calls: list[str] = []

    def incomplete(
        evidence_path: str,
        repo_root: str,
        incremental: str = "auto",
        review_mode: str = "normal",
        locale: str = "en",
    ) -> dict[str, Any]:
        calls.append(evidence_path)
        return {
            "status": "incomplete",
            "summary": {
                "tldr": "The evidence did not complete.",
                "scope": [],
                "risks": ["GitLab pagination failed for discussions"],
                "checks": [],
            },
        }

    monkeypatch.setattr(review_context, "prepare_context", incomplete)
    code = cli_main(["run", "--url", fixture.url, "--repo-root", str(fixture.repo), "--json"])
    assert code == 1
    result = _stdout_json(capsys)
    assert result["status"] == "error"
    assert "evidence stays incomplete after 3 attempts" in result["error"]
    assert "GitLab pagination failed for discussions" in result["error"]
    assert len(calls) == 3
    # The state survives for --resume instead of looping without progress.
    dump = Path(str(result["artifact_root"])) / "run-failure.json"
    assert dump.exists()


def test_run_resume_requires_existing_state(fixture: ReviewFixture, capsys: Any) -> None:
    code = cli_main(
        ["run", "--resume", "--url", fixture.url, "--repo-root", str(fixture.repo), "--json"]
    )
    assert code == 1
    result = _stdout_json(capsys)
    assert result["status"] == "error"
    assert "no review state exists" in result["error"]


def _write(fixture: ReviewFixture, name: str, value: dict[str, Any]) -> Path:
    path = fixture.tmp / name
    path.write_text(json.dumps(value))
    return path


def _replace_args(root: Path, kind: str, path: Path) -> argparse.Namespace:
    return argparse.Namespace(artifact_root=str(root), kind=kind, path=str(path))


def _progress(root: Path, field: str) -> Any:
    progress = review_context.load_progress(root)
    assert progress is not None
    return progress if not field else progress[field]


def _stdout_json(capsys: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(capsys.readouterr().out))


def _run_manual(capsys: Any, argv: list[str]) -> None:
    assert argv[0] == "reviewmatic"
    capsys.readouterr()
    code = cli_main([*argv[1:], "--json"])
    assert code == 0, capsys.readouterr().out
    capsys.readouterr()


def _fill_template(path: str, changes: dict[str, Any]) -> None:
    value = contract.read_json(Path(path), "template")
    contract.write_json(Path(path), {**value, **changes})


def _write_callbacks(fixture: ReviewFixture) -> dict[str, str]:
    scripts = fixture.tmp / "callbacks"
    scripts.mkdir(exist_ok=True)
    (scripts / "critic.py").write_text(
        "import json, sys\n"
        "value = json.load(open(sys.argv[1]))\n"
        'value["run_id"] = "critic-run"\n'
        'value["session_id"] = "critic-session"\n'
        "json.dump(value, open(sys.argv[2], 'w'))\n"
    )
    (scripts / "decision.py").write_text(
        "import json, sys\n"
        "value = json.load(open(sys.argv[1]))\n"
        'value["run_id"] = "primary-run"\n'
        'value["session_id"] = "primary-session"\n'
        'value["responses"] = [\n'
        "    {**item, 'decision': 'accept', 'reason': 'Confirmed on the exact reviewed head.'}\n"
        "    for item in value['responses']\n"
        "]\n"
        "json.dump(value, open(sys.argv[2], 'w'))\n"
    )
    (scripts / "content.py").write_text(
        "import json, sys\n"
        "value = json.load(open(sys.argv[1]))\n"
        "value.update({\n"
        "    'chat_assessment': {\n"
        "        'necessity': {'status': 'supported', 'rationale': 'The defect is confirmed.'},\n"
        "        'relevance': {'status': 'current', 'rationale': 'The exact head is current.'},\n"
        "        'change': 'The change needs the retry key documented.',\n"
        "    },\n"
        "    'summary': 'The change is small and preserves the reviewed contract.',\n"
        "    'architecture_assessment': 'The responsibility remains with its owner.',\n"
        "    'semver_impact': 'patch',\n"
        "    'semver_rationale': 'Backward-compatible correction.',\n"
        "    'semver_assessment': {\n"
        "        **value['semver_assessment'],\n"
        "        'policy': 'No release policy was found in the fixture.',\n"
        "        'sources': ['Fixture repository and empty release catalog'],\n"
        "        'fallback_reason': 'No confirmed release is available.',\n"
        "    },\n"
        "    'mr_metadata_assessment': {\n"
        "        field: {'status': 'ok', 'rationale': 'The observed metadata is sufficient.',\n"
        "                'recommendation': None}\n"
        "        for field in ('title', 'description', 'labels', 'workflow_state', 'overall')\n"
        "    },\n"
        "    'label_assessments': [\n"
        "        {'name': item['name'],\n"
        "         'status': 'applicable' if item['name'] == 'semver::patch' "
        "else 'inapplicable',\n"
        "         'rationale': 'Matches the assessed patch contribution.'}\n"
        "        for item in value['label_assessments']\n"
        "    ],\n"
        "    'checks': ['Compared the exact base and head revisions.'],\n"
        "})\n"
        "for thread in value['thread_decisions']:\n"
        "    thread.update({\n"
        "        'assessment': 'fixed',\n"
        "        'rationale': 'The exact reviewed code addresses the remark.',\n"
        "        'outcome': 'resolve' if thread.get('state', 'open') == 'open' else thread['outcome'],\n"
        "        'proposed_response': 'The exact reviewed code handles this path.',\n"
        "    })\n"
        "for candidate in value.get('rejected_candidates', []):\n"
        "    candidate['reason'] = 'Not observable in the exact reviewed head.'\n"
        "for item in value['rejected_candidate_assessments']:\n"
        "    item['reason'] = 'The exact head does not contain the reported gap.'\n"
        "json.dump(value, open(sys.argv[2], 'w'))\n"
    )
    executable = sys.executable
    return {
        "critic": f'{executable} {scripts / "critic.py"} "$1" "$2"',
        "decision": f'{executable} {scripts / "decision.py"} "$1" "$2"',
        "content": f'{executable} {scripts / "content.py"} "$1" "$2"',
    }


def _print_timings(label: str, result: dict[str, Any]) -> None:
    steps = ", ".join(
        f"{item['step']}={item['seconds']:.3f}s" for item in result.get("timings", [])
    )
    print(f"\n[timings] {label}: total={result['total_seconds']}s; {steps}")
