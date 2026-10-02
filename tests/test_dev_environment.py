from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("test_dev_environment", ROOT / "dev/env.py")
assert SPEC is not None and SPEC.loader is not None
DEV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEV)


@pytest.fixture
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(DEV, "ROOT", tmp_path)
    instance = DEV.Environment()
    monkeypatch.setattr(instance, "local_engine", lambda: None)
    return instance


def configuration(environment: Any, service: str = "gitlab") -> dict[str, Any]:
    value = {
        "checkout": environment.owner,
        "volumes": {
            service: {
                "data" if service == "gitlab" else "mattermost-data": {
                    "name": "owned-data",
                    "labels": {"dev.agentomatic.checkout": environment.owner},
                }
            }
        },
    }
    environment.save(value)
    return value


def test_all_grouped_operations_use_service_dependencies() -> None:
    tasks = yaml.safe_load((ROOT / "taskfile.yml").read_text())["tasks"]
    for action in ("up", "stop", "down", "restart", "recreate", "clean", "status", "logs"):
        assert tasks[f"env:{action}"]["deps"] == [
            f"env:gitlab:{action}",
            f"env:mattermost:{action}",
        ]
        for service in DEV.SERVICES:
            assert f"env:{service}:{action}" in tasks
    for service in DEV.SERVICES:
        cmds = tasks[f"env:{service}:up"]["cmds"]
        assert " prepare " in cmds[0]
        assert " up " in cmds[1]
        assert " init " in cmds[2]
        ordinary = str(tasks[f"test:integration:{service}"]["cmds"])
        assert "env:" not in ordinary
        assert f"tests.integration.{service}.scripts.stand test" in ordinary


def test_single_compose_scopes_external_volumes_and_no_host_socket() -> None:
    config = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert config["name"] == "skills-dev"
    assert "docker.sock" not in json.dumps(config)
    for entry in config["volumes"].values():
        assert entry["external"] is True
    for service, names in DEV.SERVICES.items():
        for name in names:
            assert name in config["services"]
        assert config["networks"][f"{service}-backend"]["internal"] is True


def test_remote_engine_rejected(environment: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKER_HOST", "ssh://foreign.invalid")
    with pytest.raises(RuntimeError, match="local Unix-socket"):
        DEV.Environment.local_engine(environment)


def test_foreign_container_rejected_before_volume_access(
    environment: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration(environment)
    monkeypatch.setattr(
        environment,
        "containers",
        lambda _p: [{"Config": {"Labels": {"com.docker.compose.project.working_dir": "/foreign"}}}],
    )
    monkeypatch.setattr(
        environment, "inspect_volume", lambda _n: pytest.fail("Foreign container was adopted")
    )
    with pytest.raises(RuntimeError, match="another checkout"):
        environment.guard("gitlab")


@pytest.mark.parametrize("owner", ["foreign", None])
def test_foreign_or_unowned_network_rejected(
    environment: Any, monkeypatch: pytest.MonkeyPatch, owner: str | None
) -> None:
    configuration(environment)
    monkeypatch.setattr(environment, "containers", lambda _p: [])
    monkeypatch.setattr(
        environment,
        "run",
        lambda *args: (
            "foreign-network"
            if args[1:3] == ("network", "ls")
            else json.dumps([{"Labels": {"dev.agentomatic.checkout": owner}}])
        ),
    )
    with pytest.raises(RuntimeError, match="Network belongs"):
        environment.guard("gitlab")


def test_changed_volume_ownership_rejected(
    environment: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration(environment)
    monkeypatch.setattr(environment, "containers", lambda _p: [])
    monkeypatch.setattr(environment, "run", lambda *_a: "")
    monkeypatch.setattr(environment, "inspect_volume", lambda _n: {"Labels": {}})
    with pytest.raises(RuntimeError, match="Volume belongs"):
        environment.guard("gitlab")


def test_changed_compose_mapping_rejected(
    environment: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration(environment)
    monkeypatch.setattr(environment, "containers", lambda _p: [])
    monkeypatch.setattr(environment, "inspect_volume", lambda _n: None)
    monkeypatch.setattr(
        environment,
        "run",
        lambda *args: (
            ""
            if args[0] == "docker"
            else json.dumps({"volumes": {"gitlab-data": {"name": "foreign-data"}}})
        ),
    )
    with pytest.raises(RuntimeError, match="mapping changed"):
        environment.guard("gitlab")


@pytest.mark.parametrize("service", ["gitlab", "mattermost"])
def test_legacy_adoption_preserves_volumes_and_is_repeatable(
    environment: Any, monkeypatch: pytest.MonkeyPatch, service: str
) -> None:
    old_path = DEV.ROOT / f"apps/{service}-test"
    names = [f"{DEV.LEGACY[service]}_{volume}" for volume in DEV.VOLUMES[service]]
    labels = {"com.docker.compose.project": DEV.LEGACY[service]}
    if service == "gitlab":
        labels["dev.agentomatic.checkout"] = hashlib.sha256(str(old_path).encode()).hexdigest()
    old = [
        {
            "Id": "legacy-container",
            "Config": {"Labels": {"com.docker.compose.project.working_dir": str(old_path)}},
            "Mounts": [{"Type": "volume", "Name": name} for name in names],
        }
    ]
    monkeypatch.setattr(environment, "containers", lambda _p: old)
    monkeypatch.setattr(
        environment, "inspect_volume", lambda name: {"Labels": labels} if name in names else None
    )
    monkeypatch.setattr(environment, "guard", lambda _s: environment.configuration())
    calls = []

    def run(*args: str) -> str:
        calls.append(args)
        if args[:2] == ("docker", "rm"):
            old.clear()
        return ""

    monkeypatch.setattr(environment, "run", run)
    environment.prepare(service)
    record = environment.configuration()
    assert {entry["name"] for entry in record["volumes"][service].values()} == set(names)
    assert calls == [("docker", "stop", "legacy-container"), ("docker", "rm", "legacy-container")]
    environment.prepare(service)
    assert environment.configuration() == record
    assert len(calls) == 2


def test_foreign_legacy_container_is_not_stopped(
    environment: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        environment,
        "containers",
        lambda _p: [{"Config": {"Labels": {"com.docker.compose.project.working_dir": "/foreign"}}}],
    )
    monkeypatch.setattr(
        environment, "run", lambda *_a: pytest.fail("Foreign resources were mutated")
    )
    with pytest.raises(RuntimeError, match="another checkout"):
        environment.prepare("gitlab")
    assert not environment.record.exists()


def test_configuration_rejects_symlink(environment: Any, tmp_path: Path) -> None:
    environment.record.symlink_to(tmp_path / "foreign.json")
    with pytest.raises(RuntimeError, match="Unsafe dev"):
        environment.configuration()


@pytest.mark.parametrize("health", ["starting", "unhealthy"])
def test_tests_require_ready_service_without_starting_it(
    environment: Any, monkeypatch: pytest.MonkeyPatch, health: str
) -> None:
    containers = [
        {
            "Config": {"Labels": {"com.docker.compose.service": name}},
            "State": {"Running": True, "Health": {"Status": health}},
        }
        for name in DEV.SERVICES["gitlab"]
    ]
    monkeypatch.setattr(environment, "containers", lambda _p: containers)
    monkeypatch.setattr(
        environment, "run", lambda *_a: pytest.fail("Readiness attempted a lifecycle action")
    )
    with pytest.raises(RuntimeError, match="env:gitlab:up"):
        environment.require_ready("gitlab")


def test_clean_needs_no_confirmation_and_preserves_other_service_and_reports(
    environment: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = configuration(environment)
    state = DEV.common.private_directory(tmp_path / "state")
    reports = DEV.common.private_directory(tmp_path / "reports")
    (state / "fixtures.json").write_text("private")
    (reports / "retained.json").write_text("retained")
    fixture = type("Fixture", (), {"state": state, "home": tmp_path})()
    monkeypatch.setattr(environment, "guard", lambda _s: value)
    monkeypatch.setattr(environment, "fixture", lambda _s: fixture)
    monkeypatch.setattr(environment, "inspect_volume", lambda _n: {"Labels": {}})
    calls = []
    monkeypatch.setattr(environment, "run", lambda *args: calls.append(args))
    environment.clean("gitlab")
    assert calls == [
        ("docker", "volume", "rm", "owned-data"),
    ]
    assert not (state / "fixtures.json").exists()
    assert (reports / "retained.json").read_text() == "retained"
    assert all("mattermost" not in arg for call in calls for arg in call)


def test_clean_rejects_symlink_before_docker_mutation(
    environment: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = configuration(environment)
    state = DEV.common.private_directory(tmp_path / "state")
    (state / "outside").symlink_to(tmp_path / "reports", target_is_directory=True)
    fixture = type("Fixture", (), {"state": state, "home": tmp_path})()
    monkeypatch.setattr(environment, "guard", lambda _s: value)
    monkeypatch.setattr(environment, "fixture", lambda _s: fixture)
    monkeypatch.setattr(
        environment, "run", lambda *_a: pytest.fail("Unsafe cleanup mutated Docker")
    )
    with pytest.raises(RuntimeError, match="symlink"):
        environment.clean("gitlab")
