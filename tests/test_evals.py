from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.eval_runner import (
    EvalError,
    offline_observation,
    result_for,
    run_with_deadline,
    scenario_digest,
    validate_scenario,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "eval_runner.py"
GOAL_AUTHORIZATION = ROOT / "skills/doit/scripts/goal_authorization.py"
LEGACY_GITLAB_V2 = ROOT / "tests/fixtures/evals/gitlab-evidence-contract-v2.json"


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


def fake_host(directory: Path, mode: str) -> Path:
    executable = directory / f"fake-{mode}"
    body = {
        "pass": 'print(json.dumps({"selected": ["skill:goal"], "usage": {"total_tokens": 12, "cost": 0.1}, "host_version": "fake/1"}))',
        "fail": 'print(json.dumps({"selected": [], "usage": {"total_tokens": 12, "cost": 0.1}}))',
        "error": "raise SystemExit(7)",
        "malformed": 'print("not-json")',
        "timeout": "time.sleep(3)",
        "budget": 'print(json.dumps({"selected": ["skill:goal"], "usage": {"total_tokens": 1000, "cost": 99}}))',
        "secret": 'print(json.dumps({"selected": ["skill:goal"], "authorization": "Bearer do-not-leak", "usage": {"total_tokens": 12, "cost": 0.1}}))',
        "escape": '(Path.cwd() / "escape").symlink_to("/tmp"); print(json.dumps({"selected": ["skill:goal"], "usage": {"total_tokens": 12, "cost": 0.1}}))',
        "environment": 'print(json.dumps({"selected": ["skill:goal"] if "SECRET_FOR_EVAL" not in os.environ else [], "usage": {"total_tokens": 12, "cost": 0.1}}))',
    }[mode]
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json
            import os
            import time
            from pathlib import Path
            {body}
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def live_arguments(host: str, executable: Path, output: Path, *extra: str) -> tuple[str, ...]:
    return (
        "--trusted-live",
        "--host",
        host,
        "--model",
        "test/exact-model",
        "--timeout",
        "1",
        "--max-tokens",
        "100",
        "--max-cost",
        "1",
        "--output",
        str(output),
        "--executable",
        str(executable),
        "--scenario",
        "skill.goal.trigger",
        *extra,
    )


def payload(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(result.stdout))


def goal_scenario() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "evals/scenarios/doit.goal-mode-authorization.json").read_text(encoding="utf-8")
        ),
    )


def gitlab_scenario() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "evals/scenarios/gitlab.evidence-contract.json").read_text(encoding="utf-8")
        ),
    )


def legacy_gitlab_scenario() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(LEGACY_GITLAB_V2.read_text(encoding="utf-8")))


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
    for skill in ("docs-prepare", "doit", "spec-manage"):
        assert (
            ROOT / "skills" / skill / "references/interaction-contract.md"
        ).read_bytes() == contract
    authorization = "ordinary Confirmation or exact frozen trusted Goal authorization"
    for skill in ("docs-prepare", "spec-manage"):
        workflow = ROOT / "skills" / skill / "references/workflow.md"
        assert authorization in workflow.read_text(encoding="utf-8")
        assert (ROOT / ".build" / "skills" / skill / "references/workflow.md").read_bytes() == (
            workflow.read_bytes()
        )
    expected = {f"policy:{case['id']}" for case in scenario["input"]["fixture"]["cases"]}

    result = run_eval("--offline", "--scenario", "doit.goal-mode-authorization")

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
    assert set(runner_schema["properties"]["protocol"]["enum"]) == {
        "assertions-v1",
        "portable-gitlab-v2",
    }
    script_pattern = runner_schema["properties"]["script"]["pattern"]
    assert re.fullmatch(script_pattern, "scripts/goal_authorization.py")
    assert not re.fullmatch(script_pattern, "../goal_authorization.py")
    assert not re.fullmatch(script_pattern, "/tmp/goal_authorization.py")

    cases = (
        ("protocol", "unknown-v1", "unsupported_runner_protocol"),
        ("skill", "/tmp/doit", "sandbox_escape"),
        ("skill", "../doit", "sandbox_escape"),
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


def test_offline_runner_rejects_symlink_without_execution(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    outside = tmp_path / "outside.py"
    outside.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8"
    )
    runner = tmp_path / ".build/skills/doit/scripts/goal_authorization.py"
    runner.parent.mkdir(parents=True)
    runner.symlink_to(outside)

    with pytest.raises(EvalError) as raised:
        offline_observation(goal_scenario(), tmp_path)

    assert raised.value.code == "sandbox_escape"
    assert not marker.exists()


def test_offline_runner_timeout_is_bounded_and_classified(tmp_path: Path) -> None:
    runner = tmp_path / ".build/skills/doit/scripts/goal_authorization.py"
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


def test_portable_gitlab_uses_one_deadline_for_every_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deadlines: list[float] = []

    def recording_deadline(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        deadlines.append(cast(float, kwargs["deadline"]))
        return run_with_deadline(*args, **kwargs)

    monkeypatch.setattr("scripts.eval_runner.run_with_deadline", recording_deadline)

    observation = offline_observation(gitlab_scenario(), ROOT)

    assert observation["runner_assertions"]
    assert len(deadlines) == 4
    assert len(set(deadlines)) == 1


def test_portable_gitlab_timeout_and_exhausted_deadline_are_classified(tmp_path: Path) -> None:
    runner = tmp_path / ".build/skills/code-review/scripts/review_mr.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    scenario = gitlab_scenario()
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


def test_exact_legacy_gitlab_runner_is_normalized_but_arbitrary_legacy_is_rejected() -> None:
    assert gitlab_scenario()["input"]["offline_runner"]["protocol"] == "portable-gitlab-v2"
    legacy = legacy_gitlab_scenario()
    assert legacy["revision"] == 2
    assert legacy["input"]["fixture"]["selected"] == []
    assert "protocol" not in legacy["input"]["offline_runner"]
    assert validate_scenario(legacy, "legacy-gitlab.json") == ["gitlab.evidence-contract"]
    assert offline_observation(legacy, ROOT)["runner_assertions"]

    changed_identity = copy.deepcopy(legacy)
    changed_identity["id"] = "gitlab.other-contract"
    changed_identity["digest"] = scenario_digest(changed_identity)
    changed_config = copy.deepcopy(legacy)
    changed_config["input"]["fixture"]["selected"] = ["skill:code-review"]
    changed_config["digest"] = scenario_digest(changed_config)
    changed_runner = copy.deepcopy(legacy)
    changed_runner["input"]["offline_runner"]["script"] = "scripts/other.py"
    changed_runner["digest"] = scenario_digest(changed_runner)
    arbitrary = goal_scenario()
    arbitrary["input"]["offline_runner"].pop("protocol")
    arbitrary["digest"] = scenario_digest(arbitrary)
    for scenario in (changed_identity, changed_config, changed_runner, arbitrary):
        with pytest.raises(EvalError) as raised:
            validate_scenario(scenario, "legacy-arbitrary.json")
        assert raised.value.code == "unsupported_runner_protocol"


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


def test_live_requires_exact_explicit_limits() -> None:
    result = run_eval("--trusted-live", "--host", "opencode", "--model", "test/model")
    assert result.returncode == 2
    assert payload(result)["error"]["classification"] == "live_limits_required"


def test_list_selectors_and_capability_detection_are_machine_readable() -> None:
    listed = run_eval("--list", "--kind", "golden", "--surface", "skill")
    assert listed.returncode == 0
    assert payload(listed)["scenarios"] == [
        {"id": "golden.core-contracts.en", "kind": "golden", "surface": "skill"},
        {"id": "golden.core-contracts", "kind": "golden", "surface": "skill"},
        {"id": "golden.goal.work-item.en", "kind": "golden", "surface": "skill"},
        {"id": "golden.goal.work-item", "kind": "golden", "surface": "skill"},
    ]
    capabilities = run_eval("--capabilities")
    assert capabilities.returncode == 0
    assert set(payload(capabilities)["hosts"]) == {"codex", "opencode"}


def test_both_adapters_cover_pass_fail_skipped_and_error() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for host in ("opencode", "codex"):
            for mode, expected_code, expected_status in (
                ("pass", 0, "passed"),
                ("fail", 1, "failed"),
                ("error", 4, "error"),
            ):
                result = run_eval(
                    *live_arguments(
                        host,
                        fake_host(root, f"{host}-{mode}".split("-", 1)[1]),
                        root / f"{host}-{mode}.json",
                    )
                )
                assert result.returncode == expected_code
                assert payload(result)["status"] == expected_status
            skipped = run_eval(
                *live_arguments(host, root / "missing-host", root / f"{host}-skip.json")
            )
            assert skipped.returncode == 3
            assert payload(skipped)["status"] == "skipped"


def test_both_adapters_cover_timeout_malformed_and_budget_excess() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for host in ("opencode", "codex"):
            for mode, expected in (
                ("timeout", "error"),
                ("malformed", "error"),
                ("budget", "failed"),
            ):
                result = run_eval(
                    *live_arguments(host, fake_host(root, mode), root / f"{host}-{mode}.json")
                )
                assert result.returncode in {1, 4}
                assert payload(result)["status"] == expected


def test_live_redacts_evidence_and_rejects_sandbox_escape() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        secret = run_eval(
            *live_arguments("opencode", fake_host(root, "secret"), root / "result.json")
        )
        assert "do-not-leak" not in secret.stdout + secret.stderr
        evidence = next((root / "private").glob("*.json")).read_text(encoding="utf-8")
        assert "do-not-leak" not in evidence
        assert "[REDACTED]" in evidence
        escaped = run_eval(
            *live_arguments("opencode", fake_host(root, "escape"), root / "escape.json")
        )
        assert escaped.returncode == 4
        assert payload(escaped)["results"][0]["error"]["classification"] == "sandbox_escape"


def test_child_environment_is_allowlisted() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        result = run_eval(
            *live_arguments("codex", fake_host(root, "environment"), root / "result.json"),
            environment={"SECRET_FOR_EVAL": "must-not-reach-child"},
        )
        assert result.returncode == 0
