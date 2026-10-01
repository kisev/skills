from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "apps/gitlab-test/scripts"
SPEC = importlib.util.spec_from_file_location("gitlab_stand_test", SCRIPTS / "stand.py")
assert SPEC is not None and SPEC.loader is not None
STAND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAND)


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    return STAND.Stand("owned-test", 9443)


@pytest.mark.parametrize(
    ("project", "port"), [("../foreign", 9443), ("valid", 0), ("valid", 65536)]
)
def test_invalid_scope_rejected_before_docker(project: str, port: int) -> None:
    with pytest.raises(ValueError, match="project name"):
        STAND.Stand(project, port)


def test_private_state_and_atomic_credentials(local: Any) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    assert local.state.stat().st_mode & 0o777 == 0o700
    assert (local.state / "fixtures.json").stat().st_mode & 0o777 == 0o600
    assert local.state != local.reports


def test_reset_changed_scope_never_deletes(local: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    monkeypatch.setattr(local, "resources", lambda: {"containers": ["one"]})
    plan = local.reset_plan()
    monkeypatch.setattr(local, "resources", lambda: {"containers": ["two"]})
    with pytest.raises(RuntimeError, match="confirmation"):
        local.reset(plan["digest"])
    assert (local.state / "fixtures.json").exists()


def test_reset_requires_confirmation_and_rejects_symlinks(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "resources", lambda: {"project": "owned-test"})
    (local.state / "outside").symlink_to(local.reports, target_is_directory=True)
    with pytest.raises(RuntimeError, match="confirmation"):
        local.reset("")
    with pytest.raises(RuntimeError, match="symlinks"):
        local.reset(local.reset_plan()["digest"])


def test_reset_retains_reports(local: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    STAND.write_json(local.reports / "previous.json", {"status": "failed"})
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    monkeypatch.setattr(local, "resources", lambda: {"project": "owned-test"})
    calls = []
    monkeypatch.setattr(local, "docker", lambda *args, **_kw: calls.append(args))
    monkeypatch.setattr(local, "start", lambda: calls.append("start"))
    monkeypatch.setattr(local, "bootstrap", lambda: calls.append("bootstrap"))
    local.reset(local.reset_plan()["digest"])
    assert calls == [("down", "--volumes"), "start", "bootstrap"]
    assert (local.reports / "previous.json").exists()
    assert not (local.state / "fixtures.json").exists()


def test_glab_environment_does_not_inherit_user_credentials(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "foreign")
    monkeypatch.setenv("GITLAB_HOST", "https://foreign.invalid")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    local.manifest = {"users": {"author": {"token": "owned", "password": "private"}}}
    env = local.isolated_env()
    assert env["GITLAB_TOKEN"] == "owned"
    assert env["GITLAB_HOST"] == "https://localhost:9443"
    assert "GIT_CONFIG_COUNT" not in env
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert local.redact("owned private") == "[REDACTED] [REDACTED]"


def test_requests_reject_external_and_scheme_relative_paths(local: Any) -> None:
    for path in ("https://foreign.invalid", "//foreign.invalid"):
        with pytest.raises(ValueError, match="stand-relative"):
            local.request("POST", path)


def test_bootstrap_refuses_symlink_credentials_before_reading(local: Any) -> None:
    outside = local.reports / "outside.json"
    STAND.write_json(outside, {"private": "unchanged"})
    (local.state / "fixtures.json").symlink_to(outside)
    with pytest.raises(RuntimeError, match="must not be symlinks"):
        local.bootstrap()
    assert json.loads(outside.read_text()) == {"private": "unchanged"}


def test_browser_config_refuses_symlinks_before_writing(local: Any) -> None:
    browser = STAND.load(
        "gitlab_browser_security_test", ROOT / "apps/mattermost-test/scripts/browser_checks.py"
    )
    local.manifest = {"owner": "test-owner"}
    outside = local.reports / "outside.json"
    STAND.write_json(outside, {"private": "unchanged"})
    (local.state / "browser-config.json").symlink_to(outside)
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        browser.Browser(local, local.reports)
    assert json.loads(outside.read_text()) == {"private": "unchanged"}


def test_foreign_checkout_container_rejected(local: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from subprocess import CompletedProcess

    monkeypatch.setattr(local, "docker", lambda *_a: json.dumps({"volumes": {}, "networks": {}}))

    def command(args: list[str]) -> CompletedProcess[str]:
        if args[1:3] == ["context", "inspect"]:
            return CompletedProcess(args, 0, "unix:///var/run/docker.sock", "")
        if args[1:3] == ["ps", "-aq"]:
            return CompletedProcess(args, 0, "foreign-id", "")
        if args[1] == "inspect":
            return CompletedProcess(
                args,
                0,
                json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "com.docker.compose.project.working_dir": "/foreign/checkout"
                                }
                            }
                        }
                    ]
                ),
                "",
            )
        return CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(STAND, "command", command)
    with pytest.raises(RuntimeError, match="another checkout"):
        local.resources()


def test_remote_docker_engine_rejected_before_resource_adoption(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "ssh://foreign.invalid")
    with pytest.raises(RuntimeError, match="local Unix-socket"):
        local.resources()


def test_missing_live_settings_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    live = STAND.load("gitlab_live_settings_test", SCRIPTS / "live_checks.py")
    for key in ("EVAL_HOST", "EVAL_MODEL", "EVAL_TIMEOUT", "EVAL_MAX_TOKENS", "EVAL_MAX_COST"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="EVAL_MODEL"):
        live.settings()


def test_compose_pins_versions_and_never_mounts_docker_socket() -> None:
    compose = (ROOT / "apps/gitlab-test/compose.yml").read_text()
    assert "gitlab/gitlab-ce:18.11.11-ce.0" in compose
    assert "gitlab/gitlab-runner:v18.11.0" in compose
    assert "docker.sock" not in compose
    assert "privileged:" not in compose
    assert "127.0.0.1:" in compose


def test_standard_https_origin_omits_port(local: Any) -> None:
    assert STAND.Stand("standard-test", 443).origin == "https://localhost"
