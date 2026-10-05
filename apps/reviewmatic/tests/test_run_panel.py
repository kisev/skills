"""The run panel: OCR critics execute mechanically, model critics stop.

The composition scenario drives ``reviewmatic run`` end to end with a mixed
panel (one engine:"ocr" critic and one model critic) and no callbacks: the OCR
critic runs inside the run without an authoring stop, the model critic stops
the run for its per-critic template and ``record-run-critic`` import, the
complete panel merges into one aggregate critic receipt with both
contributors, and the review reaches ``plan_ready``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import run_panel
from reviewmatic.cli import main as cli_main
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Iterator

OCR_OUTPUT: dict[str, Any] = {
    "status": "complete",
    "llm": {"provider": "openai", "model": "gpt-x"},
    "comments": [],
    "session_id": "ocr-session-1",
    "manifest": {"run_id": "ocr-run-1", "terminal_state": "complete"},
}

SELECTION: dict[str, Any] = {
    "critics": [
        {"name": "ocr-critic", "engine": "ocr"},
        {"name": "model-critic", "engine": "model"},
    ],
    "arbitrator": {"name": "arbitrator-1"},
}


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


@pytest.fixture(name="fake_ocr")
def fake_ocr_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "ocr-bin"
    bin_dir.mkdir()
    args_file = tmp_path / "ocr-args.txt"
    output_file = tmp_path / "ocr-output.json"
    output_file.write_text(json.dumps(OCR_OUTPUT), encoding="utf-8")
    script = bin_dir / "ocr"
    script.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$OCR_ARGS_FILE"\ncat "$OCR_OUTPUT_FILE"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("OCR_ARGS_FILE", str(args_file))
    monkeypatch.setenv("OCR_OUTPUT_FILE", str(output_file))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return {"args": args_file, "output": output_file}


def selection_path(fixture: ReviewFixture, value: dict[str, Any]) -> str:
    path = fixture.tmp / "participants.json"
    contract.write_json(path, value)
    return str(path)


def _stdout_json(capsys: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(capsys.readouterr().out))


def _run_manual(capsys: Any, argv: list[str]) -> dict[str, Any]:
    assert argv[0] == "reviewmatic"
    code = cli_main([*argv[1:], "--json"])
    assert code == 0, capsys.readouterr().out
    return _stdout_json(capsys)


def _fill_template(path: str, changes: dict[str, Any]) -> None:
    value = contract.read_json(Path(path), "template")
    contract.write_json(Path(path), {**value, **changes})


def _progress(root: Path, field: str) -> Any:
    progress = review_context.load_progress(root)
    assert progress is not None
    return progress if not field else progress[field]


def empty_content(template: dict[str, Any]) -> dict[str, Any]:
    """A complete no-findings plan content over the generated template."""
    return {
        **template,
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The reviewed change is complete."},
            "relevance": {"status": "current", "rationale": "The exact head is current."},
            "change": "The change keeps the reviewed contract intact.",
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
        "thread_decisions": [
            {
                **thread,
                "assessment": "fixed",
                "rationale": "The exact reviewed code addresses the remark.",
                "outcome": "resolve" if thread["state"] == "open" else thread["outcome"],
                "proposed_response": "The exact reviewed code handles this path.",
            }
            for thread in template["thread_decisions"]
        ],
    }


def model_receipt(root: Path, fixture: ReviewFixture) -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": str(_progress(root, "evidence_digest")),
        "run_id": "model-run-1",
        "session_id": "model-session-1",
        "findings": [],
        "question_answers": [],
        "external_mutations": False,
    }


def test_run_panel_composes_ocr_and_model_critics(
    fixture: ReviewFixture, fake_ocr: dict[str, Path], capsys: Any
) -> None:
    base = [
        "run",
        "--url",
        fixture.url,
        "--repo-root",
        str(fixture.repo),
        "--participants",
        selection_path(fixture, SELECTION),
        "--ocr-provider",
        "openai",
        "--ocr-model",
        "gpt-x",
    ]
    json_base = [*base, "--json"]

    # The OCR critic executes mechanically; the run stops for the model critic.
    assert cli_main(json_base) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "critic_missing"
    assert waiting["participant"] == "model-critic"
    assert waiting["panel"] == {
        "critics": [
            {
                "name": "ocr-critic",
                "engine": "ocr",
                "run_id": "ocr-run-1",
                "session_id": "ocr-session-1",
            },
            {"name": "model-critic", "engine": "model", "bound": False},
        ],
        "arbitrator": "arbitrator-1",
    }
    root = Path(str(waiting["artifact_root"]))
    arguments = fake_ocr["args"].read_text(encoding="utf-8").strip().split("\n")
    assert "--repo" in arguments and str(fixture.repo) in arguments
    assert "--from" in arguments and fixture.base_sha in arguments
    assert "--to" in arguments and fixture.head_sha in arguments
    assert "--provider" in arguments and "openai" in arguments
    assert "--model" in arguments and "gpt-x" in arguments
    background = Path(arguments[arguments.index("--background-file") + 1])
    assert background.exists()

    # The model critic fills its template in place; the import finishes the panel.
    _fill_template(
        waiting["template_path"],
        {"run_id": "model-run-1", "session_id": "model-session-1"},
    )
    imported = _run_manual(capsys, waiting["manual_argv"])
    assert imported["status"] == "ok"
    assert imported["stage"] == "finalize_missing"
    assert imported["panel"]["critics"][1]["run_id"] == "model-run-1"

    # The aggregate critic receipt carries both contributors with their engines.
    receipt_path = Path(str(_progress(root, "critic_receipt_path")))
    _meta, receipt = contract.artifact_payload(receipt_path, "critic_receipt")
    contributors = cast("list[dict[str, Any]]", receipt["contributors"])
    assert [item.get("engine", "model") for item in contributors] == ["ocr", "model"]
    assert {item["run_id"] for item in contributors} == {"ocr-run-1", "model-run-1"}

    # The rest of the cycle is unchanged: finalize, decision, content, plan.
    resume = [*base, "--resume", "--json"]
    assert cli_main(resume) == 0
    waiting = _stdout_json(capsys)
    assert waiting["stage"] == "decision_missing"
    template = contract.read_json(Path(waiting["template_path"]), "decision template")
    contract.write_json(
        Path(waiting["template_path"]),
        {
            **template,
            "run_id": "primary-run",
            "session_id": "primary-session",
            "responses": [
                {**item, "decision": "accept", "reason": "Confirmed on the exact reviewed head."}
                for item in cast("list[dict[str, Any]]", template["responses"])
            ],
        },
    )
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main(resume) == 0
    waiting = _stdout_json(capsys)
    assert waiting["stage"] == "content_missing"
    template = contract.read_json(Path(waiting["template_path"]), "content template")
    contract.write_json(Path(waiting["template_path"]), empty_content(template))
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main(resume) == 0
    final = _stdout_json(capsys)
    assert final["status"] == "ok"
    assert final["stage"] == "plan_ready"
    assert final["panel"]["arbitrator"] == "arbitrator-1"
    assert final["report"]["status"] == "ok"


def test_run_without_participants_stops_at_the_poll(fixture: ReviewFixture, capsys: Any) -> None:
    base = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo), "--json"]
    assert cli_main(base) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["template_kind"] == "participants"
    selection = contract.read_json(Path(waiting["template_path"]), "participants template")
    assert selection == {
        "critics": [{"name": "critic-1", "engine": "model"}],
        "arbitrator": {"name": "arbitrator-1"},
    }
    assert waiting["manual_argv"] == [
        "reviewmatic",
        "run",
        "--resume",
        "--url",
        fixture.url,
        "--participants",
        waiting["template_path"],
        "--repo-root",
        str(fixture.repo),
    ]
    root = Path(str(waiting["artifact_root"]))

    # An invalid poll answer is a loud refusal that records nothing.
    contract.write_json(
        Path(waiting["template_path"]),
        {"critics": [], "arbitrator": {"name": "arbitrator-1"}},
    )
    code = cli_main([*base[:-1], "--resume", "--participants", waiting["template_path"], "--json"])
    assert code == 1
    failure = _stdout_json(capsys)
    assert failure["status"] == "error"
    assert "panel selection is invalid" in failure["error"]
    assert run_panel.load(root) is None


def test_record_run_critic_rejects_unknown_engines_and_reuse(
    fixture: ReviewFixture, fake_ocr: dict[str, Path], capsys: Any
) -> None:
    selection = {
        "critics": [
            {"name": "ocr-critic", "engine": "ocr"},
            {"name": "model-a", "engine": "model"},
            {"name": "model-b", "engine": "model"},
        ],
        "arbitrator": {"name": "arbitrator-1"},
    }
    assert (
        cli_main(
            [
                "run",
                "--url",
                fixture.url,
                "--repo-root",
                str(fixture.repo),
                "--participants",
                selection_path(fixture, selection),
                "--json",
            ]
        )
        == 0
    )
    waiting = _stdout_json(capsys)
    root = Path(str(waiting["artifact_root"]))
    receipt_path = fixture.tmp / "receipt.json"
    contract.write_json(receipt_path, model_receipt(root, fixture))
    arguments = [
        "record-run-critic",
        "--artifact-root",
        str(root),
        "--input",
        str(receipt_path),
        "--participant",
        "nobody",
        "--json",
    ]
    assert cli_main(arguments) == 2
    assert "Unknown run-panel participant" in capsys.readouterr().out

    arguments[-2] = "ocr-critic"
    assert cli_main(arguments) == 2
    assert "is an OCR critic" in capsys.readouterr().out

    arguments[-2] = "model-a"
    assert cli_main(arguments) == 0
    imported = _stdout_json(capsys)
    # The panel stays at the critic stage while model-b is pending, and the
    # next action names the next model critic.
    assert imported["stage"] == "critic_missing"
    assert imported["panel"]["critics"][1]["run_id"] == "model-run-1"
    assert imported["panel"]["critics"][2] == {
        "name": "model-b",
        "engine": "model",
        "bound": False,
    }
    assert "--participant model-b" in imported["next_action"]["command"]

    assert cli_main(arguments) == 2
    assert "already has a bound receipt" in capsys.readouterr().out


def test_run_panel_aggregate_carries_merged_findings(fixture: ReviewFixture) -> None:
    """The shared merge convention: one aggregate receipt, findings preserved."""
    panel: dict[str, Any] = {
        "schema": run_panel.PANEL_SCHEMA,
        "participants": SELECTION,
        "receipts": [
            {
                "schema": "portable-gitlab/critic-receipt/v2",
                "evidence_digest": "a" * 64,
                "run_id": "ocr-run-1",
                "session_id": "ocr-session-1",
                "findings": [
                    {
                        "id": "ocr-1-renderer",
                        "severity": "high",
                        "summary": "The prefix is dropped.",
                        "risk": "Values lose protection.",
                        "evidence": ["renderer.txt:3"],
                        "consequence": "Protected values are rewritten.",
                        "relation_to_change": "Inside the reviewed diff.",
                        "minimum_fix": "Keep the protected prefix.",
                    }
                ],
                "question_answers": [],
                "external_mutations": False,
                "engine": "ocr",
                "ocr": {
                    "provider": "openai",
                    "model": "gpt-x",
                    "terminal_state": "complete",
                    "comments": 1,
                },
            },
            {
                "schema": "portable-gitlab/critic-receipt/v2",
                "evidence_digest": "a" * 64,
                "run_id": "model-run-1",
                "session_id": "model-session-1",
                "findings": [
                    {
                        "id": "docs-1",
                        "severity": "low",
                        "summary": "The retry lacks the key.",
                        "risk": "Deployments repeat writes.",
                        "evidence": ["review.txt:2"],
                        "consequence": "A deployment repeats writes.",
                        "relation_to_change": "The change adds the retry.",
                        "minimum_fix": "Document the idempotency key.",
                    }
                ],
                "question_answers": [],
                "external_mutations": False,
            },
        ],
    }
    merged = run_panel.aggregate(panel, "a" * 64, None)
    assert merged["schema"] == "portable-gitlab/critic-receipt/v2"
    assert [item["id"] for item in merged["findings"]] == ["ocr-1-renderer", "docs-1"]
    assert [item.get("engine", "model") for item in merged["contributors"]] == ["ocr", "model"]
    with pytest.raises(contract.WorkflowError, match="no imported critic receipts"):
        run_panel.aggregate(
            {"schema": run_panel.PANEL_SCHEMA, "participants": SELECTION, "receipts": []},
            "a" * 64,
            None,
        )
