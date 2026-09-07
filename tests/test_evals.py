from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, cast

from scripts.eval_runner import scenario_digest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "eval_runner.py"


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


def test_live_requires_exact_explicit_limits() -> None:
    result = run_eval("--trusted-live", "--host", "opencode", "--model", "test/model")
    assert result.returncode == 2
    assert payload(result)["error"]["classification"] == "live_limits_required"


def test_list_selectors_and_capability_detection_are_machine_readable() -> None:
    listed = run_eval("--list", "--kind", "golden", "--surface", "skill")
    assert listed.returncode == 0
    assert payload(listed)["scenarios"] == [
        {"id": "golden.goal.work-item", "kind": "golden", "surface": "skill"}
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
