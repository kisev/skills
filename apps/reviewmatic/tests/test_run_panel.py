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
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import render, run_panel
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
    contract.write_json(
        Path(waiting["template_path"]), render.prose_projection(empty_content(template))
    )
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


def test_record_selection_accepts_ocr_critics_for_incremental_reviews(tmp_path: Path) -> None:
    """The wave-III guard is lifted: an incremental panel may select OCR critics.

    The engine is scoped to the delta by the execution path, not by selection.
    """
    root = tmp_path / "panel-root"
    root.mkdir()
    selection = tmp_path / "selection.json"
    contract.write_json(selection, SELECTION)
    panel = run_panel.record_selection(root, str(selection), None, None, "incremental")
    assert [str(item["name"]) for item in run_panel.selected_critics(panel)] == [
        "ocr-critic",
        "model-critic",
    ]
    assert run_panel.load(root) is not None


def test_engine_offering_and_poll_scope_ocr_for_incremental() -> None:
    offering = run_panel.engine_offering("incremental", 120)
    assert offering == {
        "ocr": True,
        "exclusion": None,
        "background_bytes": 120,
        "background_limit": 8000,
    }
    poll = run_panel.poll("en", "incremental", 120)
    assert "OCR critics are not offered" not in poll["text"]
    assert "reviews the delta from the previous reviewed head" in poll["text"]
    assert "previously reported findings" in poll["text"]
    assert "incremental" in poll["text"]
    russian = run_panel.poll("ru", "incremental", 120)
    assert "ревьюит дельту от прошлого reviewed head" in russian["text"]


def test_run_refuses_unused_participants_when_the_review_selects_unchanged(
    fixture: ReviewFixture, capsys: Any
) -> None:
    callbacks = _write_callbacks(fixture)
    participants = fixture.tmp / "participants.json"
    contract.write_json(participants, ONE_MODEL_CRITIC)
    base = [
        "run",
        "--url",
        fixture.url,
        "--repo-root",
        str(fixture.repo),
        "--participants",
        str(participants),
    ]
    # First cycle: the panel review completes and writes the plan baseline.
    assert (
        cli_main(
            [
                *base,
                "--critic-cmd",
                callbacks["critic"],
                "--arbitrator-cmd",
                callbacks["decision"],
                "--content-cmd",
                callbacks["content"],
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["stage"] == "plan_ready"

    # Second cycle over the same unchanged head selects the unchanged mode: no
    # critic stage exists, so the provided poll answer can never be used.
    assert (
        cli_main(
            [
                *base,
                "--arbitrator-cmd",
                callbacks["decision"],
                "--content-cmd",
                callbacks["content"],
                "--json",
            ]
        )
        == 1
    )
    failure = _stdout_json(capsys)
    assert failure["status"] == "error"
    assert "unchanged mode without a panel" in failure["error"]


ONE_MODEL_CRITIC: dict[str, Any] = {
    "critics": [{"name": "critic-1", "engine": "model"}],
    "arbitrator": {"name": "arbitrator-1"},
}


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
        "        'necessity': {'status': 'supported', 'rationale': 'The change is complete.'},\n"
        "        'relevance': {'status': 'current', 'rationale': 'The exact head is current.'},\n"
        "        'change': 'The change keeps the reviewed contract intact.',\n"
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


def test_resume_participants_replaces_an_unbound_panel(fixture: ReviewFixture, capsys: Any) -> None:
    """While no critic receipt is bound, a resumed --participants answer replaces
    the recorded selection instead of being silently ignored."""
    first = fixture.tmp / "participants-first.json"
    contract.write_json(
        first,
        {"critics": [{"name": "model-a", "engine": "model"}], "arbitrator": {"name": "arb-1"}},
    )
    base = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    assert cli_main([*base, "--participants", str(first), "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["participant"] == "model-a"

    second = fixture.tmp / "participants-second.json"
    contract.write_json(
        second,
        {"critics": [{"name": "model-b", "engine": "model"}], "arbitrator": {"name": "arb-2"}},
    )
    assert cli_main([*base, "--resume", "--participants", str(second), "--json"]) == 0
    replaced = _stdout_json(capsys)
    assert replaced["status"] == "waiting"
    assert replaced["participant"] == "model-b"
    assert replaced["panel"]["critics"] == [{"name": "model-b", "engine": "model", "bound": False}]
    assert replaced["panel"]["arbitrator"] == "arb-2"


def test_resume_participants_refuses_a_bound_panel(
    fixture: ReviewFixture, fake_ocr: dict[str, Path], capsys: Any
) -> None:
    """Bound receipts fix the panel: --participants refuses loudly with the
    bound names and the honest path instead of ignoring the answer."""
    participants = selection_path(fixture, SELECTION)
    base = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    assert cli_main([*base, "--participants", participants, "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["panel"]["critics"][0]["run_id"] == "ocr-run-1"

    assert cli_main([*base, "--resume", "--participants", participants, "--json"]) == 1
    failure = _stdout_json(capsys)
    assert failure["status"] == "error"
    assert "bound critic receipts exist for ocr-critic" in failure["error"]
    assert "fresh reviewmatic run" in failure["error"]
    # The recorded panel is untouched by the refusal.
    root = Path(str(failure["artifact_root"]))
    panel = run_panel.load(root)
    assert panel is not None
    assert run_panel.summary(panel)["critics"][0]["run_id"] == "ocr-run-1"


def test_poll_still_excludes_ocr_for_oversized_backgrounds() -> None:
    """Only the size limit excludes the OCR engine; the mode never does."""
    offering = run_panel.engine_offering("incremental", 9000)
    assert offering["ocr"] is False
    assert offering["exclusion"] == "oversized"
    poll = run_panel.poll("en", "incremental", 9000)
    assert "the background file is 9000 bytes" in poll["text"]
    assert "above the ocr CLI limit of 8000" in poll["text"]


def test_engine_offering_and_poll_exclude_ocr_for_oversized_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The offline render measures the same background the critic would run."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    root = state / "agent-skills" / "gitlab" / "panel"
    root.mkdir(parents=True)
    bulky = {
        "discussions": [
            {
                "id": f"discussion-{index}",
                "root_system": False,
                "root_resolved": False,
                "notes": [{"body": f"thread {index}: " + "x" * 260}],
            }
            for index in range(40)
        ]
    }
    background, size = run_panel.render_run_background(root, bulky, "d" * 64)
    assert size > 8000
    offering = run_panel.engine_offering("normal", size)
    assert offering["ocr"] is False
    assert offering["exclusion"] == "oversized"
    poll = run_panel.poll("en", "normal", size)
    assert f"the background file is {size} bytes" in poll["text"]
    assert "above the ocr CLI limit of 8000" in poll["text"]
    assert background.exists()


def test_poll_presents_the_verbatim_locale_keyed_text() -> None:
    poll = run_panel.poll("en", "deep", 500)
    assert poll["ocr"] is True
    assert poll["exclusion"] is None
    for line in ("Critics:", "Arbitrator:", "Mode: deep review."):
        assert line in poll["text"]
    assert "OCR critics are not offered" not in poll["text"]
    assert run_panel.poll_rules("ru").startswith("Предъяви текст опроса дословно")
    assert run_panel.poll_rules("en").startswith("Present the poll text verbatim")


LOW_FINDING: dict[str, Any] = {
    "id": "docs-1",
    "severity": "low",
    "summary": "Retry documentation omits the idempotency key",
    "risk": "Operators can deploy the retry without the required key.",
    "evidence": ["The reviewed README documents the retry without the key argument."],
    "consequence": "A deployment following the documented steps repeats writes.",
    "relation_to_change": "The reviewed change introduces the retry path.",
    "minimum_fix": "Document the idempotency key next to the retry example.",
}

REVIEW_PATCH = (
    "diff --git a/retry-policy.txt b/retry-policy.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/retry-policy.txt\n"
    "@@ -0,0 +1 @@\n"
    "+reserve idempotency key\n"
)


def finding_content(template: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    """A complete plan content over one accepted low finding with a patch fix."""
    base = empty_content(template)
    return {
        **base,
        "findings": [finding],
        "finding_publications": [
            {
                "finding_id": finding["id"],
                "type": "general",
                "path": None,
                "line": None,
                "old_line": None,
                "body": "The documented retry needs the idempotency key; the patch adds it.",
                "fix_mode": "patch",
                "patch": REVIEW_PATCH,
                "patch_reason": "The documented setup has no suggestion anchor in prose.",
            }
        ],
    }


def test_run_composes_ocr_into_an_incremental_review(
    fixture: ReviewFixture, fake_ocr: dict[str, Path], capsys: Any
) -> None:
    """Run 1 finalizes a finding; run 2 reviews the delta with an OCR critic."""
    ocr_only = {
        "critics": [{"name": "ocr-critic", "engine": "ocr"}],
        "arbitrator": {"name": "arbitrator-1"},
    }
    first_head = fixture.head_sha
    base = ["run", "--url", fixture.url, "--repo-root", str(fixture.repo)]
    empty_ocr = json.dumps(
        {
            **OCR_OUTPUT,
            "comments": [],
            "session_id": "ocr-session-1",
            "manifest": {"run_id": "ocr-run-1", "terminal_state": "complete"},
        }
    )
    fake_ocr["output"].write_text(empty_ocr, encoding="utf-8")

    # Run 1: a full review that accepts one primary low finding fixed by a patch.
    assert cli_main([*base, "--participants", selection_path(fixture, ocr_only), "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "decision_missing"
    template = contract.read_json(Path(waiting["template_path"]), "decision template")
    contract.write_json(
        Path(waiting["template_path"]),
        {
            **template,
            "run_id": "primary-run",
            "session_id": "primary-session",
            "findings": [LOW_FINDING],
            "accepted_findings": [LOW_FINDING],
            "responses": [
                *[
                    {
                        **item,
                        "decision": "accept",
                        "reason": "Confirmed on the exact reviewed head.",
                    }
                    for item in template["responses"]
                ],
                {"id": "docs-1", "decision": "accept", "reason": "Confirmed on the exact head."},
            ],
        },
    )
    _run_manual(capsys, waiting["manual_argv"])

    assert cli_main([*base, "--resume", "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["stage"] == "content_missing"
    template = contract.read_json(Path(waiting["template_path"]), "content template")
    authored = render.prose_projection(finding_content(template, LOW_FINDING))
    authored["finding_publications"][0] = {
        "finding_id": "docs-1",
        "publication": {"kind": "general", "fix_mode": "patch"},
        "body": "The documented retry needs the key.",
        "patch": REVIEW_PATCH,
        "patch_reason": "The documented setup has no suggestion anchor in prose.",
    }
    contract.write_json(Path(waiting["template_path"]), authored)
    _run_manual(capsys, waiting["manual_argv"])
    assert cli_main([*base, "--resume", "--json"]) == 0
    final = _stdout_json(capsys)
    assert final["stage"] == "plan_ready"
    assert final["report"]["status"] == "ok"

    # Advance the MR head: a real code delta that touches the run-1 fix.
    (fixture.repo / "review.txt").write_text("base\nreviewed change\ndelta line\n")
    (fixture.repo / "retry-policy.txt").write_text("reserve idempotency key, changed\n")
    fixture.git("add", "review.txt", "retry-policy.txt")
    fixture.git("commit", "-m", "delta")
    second_head = fixture.head()
    assert second_head != first_head
    fixture.git("push", "-q", "origin", "main")
    fixture._git(fixture.origin, "update-ref", "refs/merge-requests/7/head", second_head)
    fixture.config_path.write_text(
        json.dumps(
            {
                **fixture.read_config(),
                "headSha": second_head,
                "changedPaths": ["review.txt", "retry-policy.txt"],
            }
        )
    )

    # Run 2: the moved MR selects the incremental mode; the OCR critic runs
    # the delta range and its receipt binds the scoped previous findings.
    fake_ocr["output"].write_text(
        json.dumps(
            {
                **OCR_OUTPUT,
                "comments": [],
                "session_id": "ocr-session-2",
                "manifest": {"run_id": "ocr-run-2", "terminal_state": "complete"},
            }
        ),
        encoding="utf-8",
    )
    assert cli_main([*base, "--participants", selection_path(fixture, ocr_only), "--json"]) == 0
    waiting = _stdout_json(capsys)
    assert waiting["status"] == "waiting"
    assert waiting["stage"] == "decision_missing"
    root = Path(str(waiting["artifact_root"]))
    progress = review_context.load_progress(root) or {}
    artifact = review_context.progress_artifact(root, progress, "context", "review_context")
    assert artifact is not None
    incremental = artifact[1]["incremental"]
    assert incremental["mode"] == "incremental", (
        f"reason={incremental.get('reason')} from={incremental.get('incremental_delta', {}).get('from_head')}"
        f" to={incremental.get('incremental_delta', {}).get('to_head')}"
        f" first={first_head} second={second_head}"
    )
    arguments = fake_ocr["args"].read_text(encoding="utf-8").strip().split("\n")
    assert arguments[arguments.index("--from") + 1] == first_head
    assert arguments[arguments.index("--to") + 1] == second_head

    root = Path(str(waiting["artifact_root"]))
    receipt_path = Path(str(_progress(root, "critic_receipt_path")))
    _meta, receipt = contract.artifact_payload(receipt_path, "critic_receipt")
    assert receipt["scope_digest"] == incremental["incremental_delta_digest"]
    assert receipt["target_finding_ids"] == ["docs-1"]
    ocr_background_files = (root / "review-drafts").glob("ocr-background-*.md")
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in ocr_background_files)
    assert "## Previously reported findings" in rendered
    assert "- docs-1 (low): Retry documentation omits the idempotency key" in rendered
    assert "## Advisory review history" in rendered
    assert "Do not synchronize ledgers" in rendered
    assert incremental["previous_findings"] == []
    assert incremental["history_context"]["findings"][0]["id"] == "docs-1"
    decision = contract.read_json(Path(waiting["template_path"]), "decision template")
    decision.update(run_id="arb-run-2", session_id="arb-session-2")
    for response in decision["responses"]:
        response["reason"] = "Checked the current retry policy and complete discussion."
    contract.write_json(Path(waiting["template_path"]), decision)
    _run_manual(capsys, waiting["manual_argv"])
    assert cli_main([*base, "--resume", "--json"]) == 0
    prose_stop = _stdout_json(capsys)
    prose_path = Path(prose_stop["template_path"])
    prose = contract.read_json(prose_path, "prose")
    contract.write_json(prose_path, render.prose_projection(empty_content(prose)))
    _run_manual(capsys, prose_stop["manual_argv"])
    assert cli_main([*base, "--resume", "--json"]) == 0
    final = _stdout_json(capsys)
    assert final["stage"] == "plan_ready"
    _, plan = contract.artifact_payload(Path(str(_progress(root, "plan_path"))), "review_plan")
    assert plan["findings"] == []
    assert plan["previous_finding_assessments"] == []
    assert (root / "runbook.md").is_file()
