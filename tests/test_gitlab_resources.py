from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gitlab_resource_test", ROOT / "apps/gitlab-test/scripts/stand.py"
)
assert SPEC is not None and SPEC.loader is not None
STAND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAND)


@pytest.mark.parametrize("owner", ["foreign-checkout", None])
def test_foreign_or_unowned_orphan_network_is_never_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, owner: str | None
) -> None:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    local = STAND.Stand("owned-test", 443)
    monkeypatch.setattr(
        local,
        "docker",
        lambda *_a: json.dumps(
            {"volumes": {}, "networks": {"backend": {"name": "owned-test_backend"}}}
        ),
    )

    def command(args: list[str]) -> CompletedProcess[str]:
        text = ""
        if args[1:3] == ["context", "inspect"]:
            text = "unix:///var/run/docker.sock"
        elif args[1:3] == ["network", "ls"]:
            text = "owned-test_backend"
        elif args[1:3] == ["network", "inspect"]:
            text = json.dumps(
                [
                    {
                        "Id": "foreign-network",
                        "Labels": {"dev.agentomatic.checkout": owner},
                        "Containers": {},
                    }
                ]
            )
        return CompletedProcess(args, 0, text, "")

    monkeypatch.setattr(STAND, "command", command)
    with pytest.raises(RuntimeError, match="Network belongs"):
        local.resources()


def test_foreign_or_unowned_volume_is_never_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    local = STAND.Stand("owned-test", 443)
    monkeypatch.setattr(
        local,
        "docker",
        lambda *_a: json.dumps({"volumes": {"data": {"name": "owned-test_data"}}, "networks": {}}),
    )

    def command(args: list[str]) -> CompletedProcess[str]:
        text = ""
        if args[1:3] == ["context", "inspect"]:
            text = "unix:///var/run/docker.sock"
        elif args[1:3] == ["volume", "ls"]:
            text = "owned-test_data"
        elif args[1:3] == ["volume", "inspect"]:
            text = json.dumps([{"Labels": {}}])
        return CompletedProcess(args, 0, text, "")

    monkeypatch.setattr(STAND, "command", command)
    with pytest.raises(RuntimeError, match="Volume belongs"):
        local.resources()


def test_legacy_owned_network_matches_full_inspected_container_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    local = STAND.Stand("owned-test", 443)
    full_id = "a" * 64
    monkeypatch.setattr(
        local,
        "docker",
        lambda *_a: json.dumps(
            {"volumes": {}, "networks": {"backend": {"name": "owned-test_backend"}}}
        ),
    )

    def command(args: list[str]) -> CompletedProcess[str]:
        text = ""
        if args[1:3] == ["context", "inspect"]:
            text = "unix:///var/run/docker.sock"
        elif args[1:3] == ["ps", "-aq"]:
            text = full_id[:12]
        elif args[1] == "inspect":
            text = json.dumps(
                [
                    {
                        "Id": full_id,
                        "Config": {
                            "Labels": {"com.docker.compose.project.working_dir": str(STAND.APP)}
                        },
                    }
                ]
            )
        elif args[1:3] == ["network", "ls"]:
            text = "owned-test_backend"
        elif args[1:3] == ["network", "inspect"]:
            text = json.dumps([{"Id": "owned-network", "Labels": {}, "Containers": {full_id: {}}}])
        return CompletedProcess(args, 0, text, "")

    monkeypatch.setattr(STAND, "command", command)
    assert local.resources()["containers"] == [full_id]
