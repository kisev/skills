from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "apps/mattermost-test/scripts"
SPEC = importlib.util.spec_from_file_location("stand", SCRIPTS / "stand.py")
assert SPEC is not None and SPEC.loader is not None
STAND = importlib.util.module_from_spec(SPEC)
sys.modules["stand"] = STAND
SPEC.loader.exec_module(STAND)


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    return STAND.Stand("owned-test", 8443)


def test_state_and_reports_have_separate_private_boundaries(local: Any) -> None:
    assert local.state.parent == local.reports.parent
    assert local.state != local.reports
    assert local.state.stat().st_mode & 0o777 == 0o700
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    assert (local.state / "fixtures.json").stat().st_mode & 0o777 == 0o600


def test_reset_digest_binds_resources_and_does_not_delete_on_mismatch(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    monkeypatch.setattr(
        local, "resources", lambda: {"project": "owned-test", "containers": ["one"]}
    )
    plan = local.reset_plan()
    monkeypatch.setattr(
        local, "resources", lambda: {"project": "owned-test", "containers": ["two"]}
    )
    with pytest.raises(RuntimeError, match="confirmation"):
        local.reset(plan["digest"])
    assert (local.state / "fixtures.json").is_file()


def test_reset_retains_reports_and_reinitializes(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    STAND.write_json(local.reports / "previous.json", {"status": "passed"})
    monkeypatch.setattr(
        local, "resources", lambda: {"project": "owned-test", "containers": ["one"]}
    )
    calls = []
    monkeypatch.setattr(local, "docker", lambda *args: calls.append(args))
    monkeypatch.setattr(local, "start", lambda: calls.append("start"))
    monkeypatch.setattr(local, "bootstrap", lambda: calls.append("bootstrap"))
    local.reset(local.reset_plan()["digest"])
    assert calls == [("down", "--volumes"), "start", "bootstrap"]
    assert json.loads((local.reports / "previous.json").read_text()) == {"status": "passed"}
    assert not (local.state / "fixtures.json").exists()


def test_reset_refuses_symlink_state(local: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    monkeypatch.setattr(local, "resources", lambda: {"project": "owned-test"})
    (local.state / "outside").symlink_to(local.reports, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlinks"):
        local.reset(local.reset_plan()["digest"])


@pytest.mark.parametrize(("project", "port"), [("../other", 8443), ("owned", 80), ("owned", 65536)])
def test_invalid_instance_scope_fails_before_docker(project: str, port: int) -> None:
    with pytest.raises(ValueError, match="project name"):
        STAND.Stand(project, port)


def test_live_requires_explicit_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    live = STAND.load("mm_test_live", SCRIPTS / "live_checks.py")
    for key in ("EVAL_HOST", "EVAL_MODEL", "EVAL_TIMEOUT", "EVAL_MAX_TOKENS", "EVAL_MAX_COST"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="EVAL_MODEL"):
        live.settings()


def test_missing_cost_telemetry_cannot_pass_live_budget() -> None:
    live = STAND.load("mm_test_live_usage", SCRIPTS / "live_checks.py")
    adapter = STAND.load("mm_test_eval_adapter", SCRIPTS.parents[2] / "scripts/eval_runner.py")
    observation = live.usage(
        [{"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 3}}], adapter
    )
    assert observation["total_tokens"] == 8
    assert (
        adapter.budget_assertions(observation, {"max_tokens": 100, "max_cost": 1})[1]
        == "incomplete"
    )
