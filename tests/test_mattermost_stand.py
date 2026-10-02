from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "tests/integration/mattermost/scripts"
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


@pytest.mark.parametrize("action", ["up", "down", "stop", "start", "restart", "rm"])
def test_tests_cannot_manage_containers(local: Any, action: str) -> None:
    with pytest.raises(ValueError, match="cannot manage containers"):
        local.docker(action)


def test_missing_preparation_does_not_initialize(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "resources", dict)
    monkeypatch.setattr(local, "bootstrap", lambda: pytest.fail("Tests initialized fixtures"))
    with pytest.raises(RuntimeError, match="env:mattermost:up"):
        local.connect()


def test_tests_cannot_read_manual_posts(local: Any) -> None:
    local.manifest = {"channels": {"free": "manual"}, "posts": {"free-sentinel": "sentinel"}}
    for path in ("/channels/manual/posts", "/posts/sentinel"):
        with pytest.raises(ValueError, match="manual/free"):
            local.request("GET", path)


@pytest.mark.parametrize("existing", [True, False])
def test_bootstrap_does_not_republish_existing_reaction(
    local: Any, monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    roles = ("admin", "reader", "peer", "third")
    manifest = {
        "owner": "fixture",
        "users": {role: {"id": role, "token": role} for role in roles},
        "posts": {"free-sentinel": "manual"},
        "channels": {"free": "manual"},
    }
    STAND.write_json(local.state / "fixtures.json", manifest)
    calls = []

    def request(
        method: str, path: str, *_args: Any, **_kwargs: Any
    ) -> dict[str, Any] | list[dict[str, Any]]:
        calls.append((method, path))
        if path.endswith("/reactions"):
            return [{"user_id": "peer", "emoji_name": "eyes"}] if existing else []
        return {"id": "fixture-resource", "name": "fixture"}

    monkeypatch.setattr(local, "request", request)
    monkeypatch.setattr(local, "post", lambda *_a: {"id": "root"})
    local.bootstrap()
    assert calls.count(("POST", "/reactions")) == (0 if existing else 1)
    assert not any("/channels/name/free" in path for _method, path in calls)


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
    adapter = STAND.load("mm_test_eval_adapter", SCRIPTS.parents[3] / "scripts/eval_runner.py")
    observation = live.usage(
        [{"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 3}}], adapter
    )
    assert observation["total_tokens"] == 8
    assert (
        adapter.budget_assertions(observation, {"max_tokens": 100, "max_cost": 1})[1]
        == "incomplete"
    )
