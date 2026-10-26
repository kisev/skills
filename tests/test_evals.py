from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.eval_runner import (
    EvalError,
    assertions_for_invariants,
    describe_invariant,
    offline_observation,
    print_failure_report,
    result_for,
    run_with_deadline,
    scenario_digest,
    validate_scenario,
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "eval_runner.py"
GOAL_AUTHORIZATION = ROOT / ".build/skills/docs-prepare/scripts/goal_authorization.py"


def run_eval(
    *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *arguments],
        cwd=ROOT,
        env={**os.environ, **(environment or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(result.stdout))


def goal_scenario() -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads(
            (ROOT / "evals/scenarios/goal-mode-authorization.json").read_text(encoding="utf-8")
        ),
    )


def run_goal_authorization(
    *arguments: str, input_value: dict[str, Any] | str | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    input_text = json.dumps(input_value) if isinstance(input_value, dict) else input_value
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(GOAL_AUTHORIZATION), *arguments],
        cwd=cwd or ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def test_goal_authorization_offline_runner_exercises_decision_cases() -> None:
    scenario = goal_scenario()
    assert scenario["input"]["offline_runner"]["protocol"] == "assertions-v1"
    assert all("contains" not in item and "absent" not in item for item in scenario["invariants"])
    contract = (ROOT / "shared/references/interaction-contract.md").read_bytes()
    policy = (ROOT / "shared/references/goal_authorization.py").read_bytes()
    for skill in ("docs-prepare", "spec-manage"):
        assert (
            ROOT / ".build/skills" / skill / "references/interaction-contract.md"
        ).read_bytes() == contract
        assert (
            ROOT / ".build/skills" / skill / "scripts/goal_authorization.py"
        ).read_bytes() == policy
    for skill in ("docs-prepare", "spec-manage"):
        workflow = ROOT / "skills" / skill / "references/workflow.md"
        assert (
            "write it directly" in workflow.read_text(encoding="utf-8")
            or "write it directly" in workflow.read_text(encoding="utf-8").lower()
        )
        assert (ROOT / ".build" / "skills" / skill / "references/workflow.md").read_bytes() == (
            workflow.read_bytes()
        )
    expected = {f"policy:{case['id']}" for case in scenario["input"]["fixture"]["cases"]}

    result = run_eval("--offline", "--scenario", "goal-mode-authorization")

    assert result.returncode == 0
    evaluated = payload(result)["results"][0]
    assertions = {item["id"]: item["status"] for item in evaluated["assertions"]}
    assert expected
    assert expected <= assertions.keys()
    assert all(assertions[identifier] == "passed" for identifier in expected)
    assert assertions["runner:exit"] == "passed"


def test_offline_runner_schema_and_validation_reject_unsafe_configurations() -> None:
    schema = json.loads((ROOT / "evals/schemas/scenario-v1.schema.json").read_text())
    runner_schema = schema["properties"]["input"]["properties"]["offline_runner"]
    assert set(runner_schema["properties"]["protocol"]["enum"]) == {"assertions-v1"}
    script_pattern = runner_schema["properties"]["script"]["pattern"]
    assert re.fullmatch(script_pattern, "scripts/goal_authorization.py")
    assert not re.fullmatch(script_pattern, "../goal_authorization.py")
    assert not re.fullmatch(script_pattern, "/tmp/goal_authorization.py")

    cases = (
        ("protocol", "unknown-v1", "unsupported_runner_protocol"),
        ("skill", "/tmp/docs-prepare", "sandbox_escape"),
        ("skill", "../docs-prepare", "sandbox_escape"),
        ("script", "/tmp/runner.py", "sandbox_escape"),
        ("script", "scripts/../../runner.py", "sandbox_escape"),
        ("script", "scripts/other.py", "unsupported_runner"),
    )
    for field, value, classification in cases:
        scenario = goal_scenario()
        scenario["input"]["offline_runner"][field] = value
        scenario["digest"] = scenario_digest(scenario)
        with pytest.raises(EvalError) as raised:
            validate_scenario(scenario, "unsafe.json")
        assert raised.value.code == classification

    scenario = goal_scenario()
    scenario["input"]["fixture"]["selected"] = []
    scenario["digest"] = scenario_digest(scenario)
    with pytest.raises(EvalError) as raised:
        validate_scenario(scenario, "unselected.json")
    assert raised.value.code == "unselected_runner"

    scenario = goal_scenario()
    scenario["input"]["project_files"] = {"../escape": "unsafe"}
    scenario["digest"] = scenario_digest(scenario)
    with pytest.raises(EvalError) as raised:
        validate_scenario(scenario, "project-path-escape.json")
    assert raised.value.code == "sandbox_escape"

    scenario = goal_scenario()
    scenario["input"]["offline_runner"].pop("protocol")
    scenario["digest"] = scenario_digest(scenario)
    with pytest.raises(EvalError) as raised:
        validate_scenario(scenario, "legacy-fields.json")
    assert raised.value.code == "malformed_scenario"


def test_offline_runner_rejects_symlink_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    outside = tmp_path / "outside.py"
    outside.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8"
    )
    runner = tmp_path / ".build/skills/docs-prepare/scripts/goal_authorization.py"
    runner.parent.mkdir(parents=True)
    runner.symlink_to(outside)

    with pytest.raises(EvalError) as raised:
        offline_observation(goal_scenario(), tmp_path)

    assert raised.value.code == "sandbox_escape"
    assert not marker.exists()


def test_offline_runner_timeout_is_bounded_and_classified(tmp_path: Path) -> None:
    runner = tmp_path / ".build/skills/docs-prepare/scripts/goal_authorization.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    scenario = goal_scenario()
    scenario["budgets"]["timeout_seconds"] = 0.01
    args = argparse.Namespace(offline=True, host=None, model=None, max_tokens=None, max_cost=None)

    result = result_for(scenario, args, tmp_path)

    assert result["status"] == "error"
    assert result["error"] == {
        "classification": "offline_runner_timeout",
        "message": "offline_runner exceeded timeout_seconds=0.01",
    }
    with pytest.raises(EvalError) as raised:
        run_with_deadline(
            ["must-not-run"],
            cwd=tmp_path,
            env={},
            deadline=float("-inf"),
            timeout_seconds=1,
        )
    assert raised.value.code == "offline_runner_timeout"


def test_goal_authorization_cli_capabilities_and_exit_contract(tmp_path: Path) -> None:
    before = list(tmp_path.iterdir())
    capabilities = run_goal_authorization("--capabilities", cwd=tmp_path)
    assert capabilities.returncode == 0
    capability_payload = payload(capabilities)
    assert capability_payload["schema"] == "goal-authorization-capabilities/v1"
    assert capability_payload["version"] == 1
    assert capability_payload["read_only"] is True
    assert capability_payload["exit_codes"] == {
        "0": "capabilities reported or all assertions passed",
        "1": "one or more assertions failed",
        "2": "invalid command, target, or JSON input",
    }
    assert list(tmp_path.iterdir()) == before

    fixture = goal_scenario()["input"]["fixture"]
    passed = run_goal_authorization(
        "verify", "--target", "goal-authorization-v1", input_value=fixture
    )
    assert passed.returncode == 0
    assert payload(passed)["schema"] == "goal-authorization-result/v1"

    mismatch = copy.deepcopy(fixture)
    mismatch["cases"][0]["expected"]["authorized"] = False
    failed = run_goal_authorization(
        "verify", "--target", "goal-authorization-v1", input_value=mismatch
    )
    assert failed.returncode == 1
    assert any(item["status"] == "failed" for item in payload(failed)["assertions"])

    invalid = run_goal_authorization("verify", "--target", "goal-authorization-v1", input_value={})
    assert invalid.returncode == 2
    assert payload(invalid)["schema"] == "goal-authorization-error/v1"

    malformed_objective = copy.deepcopy(fixture)
    malformed_objective["objectives"]["full"] = {}
    malformed_additions = copy.deepcopy(fixture)
    next(
        case for case in malformed_additions["cases"] if case["id"] == "later-prompt-cannot-expand"
    )["later_additions"] = "not-a-list"
    errors = (
        run_goal_authorization(
            "verify",
            "--target",
            "goal-authorization-v1",
            input_value=malformed_objective,
        ),
        run_goal_authorization(
            "verify",
            "--target",
            "goal-authorization-v1",
            input_value=malformed_additions,
        ),
        run_goal_authorization("--unknown-option"),
    )
    for error in errors:
        assert error.returncode == 2
        assert error.stderr == ""
        assert payload(error)["schema"] == "goal-authorization-error/v1"
        assert "Traceback" not in error.stdout


def test_offline_suite_is_hostless_and_has_stable_ordered_assertions() -> None:
    first = run_eval("--offline", "--scenario", "golden.goal.work-item")
    second = run_eval("--offline", "--scenario", "golden.goal.work-item")
    assert first.returncode == second.returncode == 0
    one = payload(first)["results"][0]
    two = payload(second)["results"][0]
    assert one["scenario_digest"] == two["scenario_digest"]
    assert one["digest"] == two["digest"]
    assert [item["id"] for item in one["assertions"]] == sorted(
        item["id"] for item in one["assertions"]
    )


def test_validation_rejects_duplicate_drift_and_sandbox_escape() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        corpus = Path(temporary)
        source = ROOT / "evals/scenarios/skill-goal-trigger.json"
        first = corpus / "first.json"
        second = corpus / "second.json"
        first.write_bytes(source.read_bytes())
        second.write_bytes(source.read_bytes())
        duplicate = run_eval("--corpus", str(corpus), "--validate")
        assert duplicate.returncode == 2
        assert payload(duplicate)["error"]["classification"] == "duplicate_scenario"
        second.unlink()
        drifted = json.loads(first.read_text(encoding="utf-8"))
        drifted["input"]["prompt"] = "drift"
        first.write_text(json.dumps(drifted), encoding="utf-8")
        drift = run_eval("--corpus", str(corpus), "--validate")
        assert payload(drift)["error"]["classification"] == "digest_drift"
        drifted["invariants"][0]["path"] = "../escape"
        drifted["digest"] = scenario_digest(drifted)
        first.write_text(json.dumps(drifted), encoding="utf-8")
        escaped = run_eval("--corpus", str(corpus), "--validate")
        assert payload(escaped)["error"]["classification"] == "sandbox_escape"


def test_validation_rejects_missing_locale_metadata_and_pair_drift() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        corpus = Path(temporary)
        source = json.loads(
            (ROOT / "evals/scenarios/skill-goal-trigger.json").read_text(encoding="utf-8")
        )
        source.pop("locale")
        source["digest"] = scenario_digest(source)
        (corpus / "missing-locale.json").write_text(json.dumps(source), encoding="utf-8")
        missing = run_eval("--corpus", str(corpus), "--validate")
        assert missing.returncode == 2
        assert payload(missing)["error"]["classification"] == "malformed_scenario"

        ru = json.loads(
            (ROOT / "evals/scenarios/skill-goal-trigger.json").read_text(encoding="utf-8")
        )
        en = json.loads(
            (ROOT / "evals/scenarios/skill-goal-trigger.en.json").read_text(encoding="utf-8")
        )
        en["budgets"]["max_tokens"] = 1
        en["digest"] = scenario_digest(en)
        (corpus / "ru.json").write_text(json.dumps(ru), encoding="utf-8")
        (corpus / "en.json").write_text(json.dumps(en), encoding="utf-8")
        (corpus / "missing-locale.json").unlink()
        drift = run_eval("--corpus", str(corpus), "--validate")
        assert drift.returncode == 2
        assert payload(drift)["error"]["classification"] == "scenario_pair_drift"

        en["budgets"]["max_tokens"] = ru["budgets"]["max_tokens"]
        en["invariants"][0]["contains"] = "different invariant content"
        en["digest"] = scenario_digest(en)
        (corpus / "en.json").write_text(json.dumps(en), encoding="utf-8")
        mismatch = run_eval("--corpus", str(corpus), "--validate")
        assert mismatch.returncode == 2
        assert payload(mismatch)["error"]["classification"] == "scenario_pair_drift"


def test_list_selectors_and_capability_detection_are_machine_readable() -> None:
    listed = run_eval("--list", "--kind", "golden", "--surface", "skill")
    assert listed.returncode == 0
    assert payload(listed)["scenarios"] == [
        {"id": "briefing.behavior.en", "kind": "golden", "surface": "skill"},
        {"id": "briefing.behavior.ru", "kind": "golden", "surface": "skill"},
        {"id": "golden.core-contracts.en", "kind": "golden", "surface": "skill"},
        {"id": "golden.core-contracts", "kind": "golden", "surface": "skill"},
        {"id": "golden.goal.work-item.en", "kind": "golden", "surface": "skill"},
        {"id": "golden.goal.work-item", "kind": "golden", "surface": "skill"},
        {"id": "question-guidelines.rounds.en", "kind": "golden", "surface": "skill"},
        {"id": "question-guidelines.rounds.ru", "kind": "golden", "surface": "skill"},
        {"id": "skill.humanize.edit-contract.en", "kind": "golden", "surface": "skill"},
        {"id": "skill.humanize.edit-contract", "kind": "golden", "surface": "skill"},
        {"id": "spec-manage.audit-behavior.en", "kind": "golden", "surface": "skill"},
        {"id": "spec-manage.audit-behavior.ru", "kind": "golden", "surface": "skill"},
        {
            "id": "spec-manage.language-authority-extensions.en",
            "kind": "golden",
            "surface": "skill",
        },
        {
            "id": "spec-manage.language-authority-extensions.ru",
            "kind": "golden",
            "surface": "skill",
        },
        {"id": "spec-manage.mode-selection.en", "kind": "golden", "surface": "skill"},
        {"id": "spec-manage.mode-selection.ru", "kind": "golden", "surface": "skill"},
    ]
    capabilities = run_eval("--capabilities")
    assert capabilities.returncode == 0
    assert set(payload(capabilities)["hosts"]) == {"codex", "opencode"}


@pytest.mark.parametrize(
    "scenario",
    [
        "spec-manage.mode-selection.en",
        "question-guidelines.rounds.en",
        "question-guidelines.rounds.ru",
        "skill.humanize.edit-contract.en",
    ],
)
def test_case_outcomes_are_declared_but_not_observed_offline(scenario: str) -> None:
    offline = run_eval("--offline", "--scenario", scenario)

    assert offline.returncode == 0
    result = payload(offline)["results"][0]
    assert result["observation_mode"] == "hostless-contract"
    assert result["case_outcomes"] == []
    assert {item["id"]: item["status"] for item in result["assertions"]}[
        "case-outcomes:not-observed"
    ] == "not_observed"


def test_invariant_pins_survive_paragraph_reflow(tmp_path: Path) -> None:
    target = tmp_path / "reference.md"
    target.write_text(
        "The rule says one thing here and the very same wording\ncontinues on"
        " the next line after reflow.\n",
        encoding="utf-8",
    )
    scenario = {
        "invariants": [
            {
                "id": "wrapped-contains",
                "path": "reference.md",
                "contains": "wording continues on the next",
            },
            {
                "id": "wrapped-absent",
                "path": "reference.md",
                "absent": "absent phrase across\nlines",
            },
        ]
    }
    statuses = {
        item["id"]: item["status"] for item in assertions_for_invariants(scenario, tmp_path)
    }

    assert statuses == {"wrapped-contains": "passed", "wrapped-absent": "passed"}


def test_offline_failure_report_names_scenarios_and_assertions(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results: list[dict[str, Any]] = [
        {
            "scenario_id": "skill.humanize.edit-contract",
            "status": "failed",
            "assertions": [
                {"id": "humanize-weak-alone-set", "status": "failed"},
                {"id": "selected:skill:humanize", "status": "passed"},
            ],
            "error": {"classification": None},
        },
        {
            "scenario_id": "broken.runner",
            "status": "error",
            "assertions": [],
            "error": {"classification": "offline_runner_timeout", "message": "timed out"},
        },
    ]
    selected = [
        {
            "id": "skill.humanize.edit-contract",
            "invariants": [
                {
                    "id": "humanize-weak-alone-set",
                    "path": "shared/references/humanize-patterns.md",
                    "contains": "the weak-alone set is 6, 7",
                }
            ],
        }
    ]

    print_failure_report(results, selected)
    report = capsys.readouterr().err

    assert "evaluation is not passed: 2 of 2 scenarios failed" in report
    assert "[failed] skill.humanize.edit-contract" in report
    assert (
        "assertion humanize-weak-alone-set: shared/references/humanize-patterns.md"
        " must contain 'the weak-alone set is 6, 7'" in report
    )
    assert "[error] broken.runner" in report
    assert "error offline_runner_timeout: timed out" in report
    assert "selected:skill:humanize" not in report


def test_describe_invariant_renders_absent_and_bare_paths() -> None:
    result = {"scenario_id": "scenario", "status": "failed", "assertions": [], "error": {}}
    scenarios = {
        "scenario": {
            "id": "scenario",
            "invariants": [
                {"id": "gone", "path": "docs/x.md", "absent": "retired phrase"},
                {"id": "bare", "path": "docs/y.md"},
            ],
        }
    }

    assert (
        describe_invariant(scenarios, result, "gone")
        == "docs/x.md must not contain 'retired phrase'"
    )
    assert describe_invariant(scenarios, result, "bare") == "docs/y.md"
    assert describe_invariant(scenarios, result, "unknown") == ""
