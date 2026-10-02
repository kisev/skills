#!/usr/bin/env python3
"""Bounded volume adoption, fixture preparation and cleanup for the root Compose file."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from dev.gitlab.fixtures import runner
from tests.integration.mattermost.scripts import stand as common

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "gitlab": ("gitlab", "gitlab-proxy", "gitlab-runner"),
    "mattermost": ("mattermost-db", "mattermost", "mattermost-proxy"),
}
VOLUMES = {
    "gitlab": ("config", "logs", "data", "ca", "runner-config", "runner-builds"),
    "mattermost": (
        "postgres-data",
        "mattermost-config",
        "mattermost-socket",
        "mattermost-data",
        "mattermost-plugins",
        "mattermost-client-plugins",
        "caddy-data",
        "caddy-config",
    ),
}
LEGACY = {"gitlab": "gitlab-workflows", "mattermost": "mattermost-cards"}


def key(service: str, volume: str) -> str:
    suffix = volume.removeprefix("mattermost-") if service == "mattermost" else volume
    return f"DEV_{service}_{suffix}".upper().replace("-", "_")


class Environment:
    def __init__(self, compose: str = "docker-compose"):
        self.owner = hashlib.sha256(str(ROOT).encode()).hexdigest()
        self.home = common.private_directory(ROOT / ".build/env")
        self.record = self.home / "volumes.json"
        self.envfile = self.home / "compose.env"
        self.compose = [
            *shlex.split(compose),
            "-p",
            "skills-dev",
            "--env-file",
            str(self.envfile),
            "-f",
            str(ROOT / "docker-compose.yml"),
        ]

    def run(self, *args: str) -> str:
        return common.command(list(args), timeout=360).stdout

    def configuration(self) -> dict[str, Any]:
        if self.record.is_symlink() or self.envfile.is_symlink():
            raise RuntimeError("Unsafe dev configuration path")
        if not self.record.exists():
            raise RuntimeError("Development environment is not prepared; run task env:up")
        value = json.loads(self.record.read_text())
        if not isinstance(value, dict):
            raise RuntimeError("Invalid development configuration")
        if value["checkout"] != self.owner:
            raise RuntimeError("Development configuration belongs to another checkout")
        return value

    def save(self, value: dict[str, Any]) -> None:
        common.write_json(self.record, value)
        lines = [f"DEV_CHECKOUT={self.owner}"]
        for service, volumes in value["volumes"].items():
            lines.extend(
                f"{key(service, volume)}={entry['name']}" for volume, entry in volumes.items()
            )
        temporary = self.envfile.with_suffix(".new")
        if self.envfile.is_symlink() or temporary.is_symlink():
            raise RuntimeError("Unsafe Compose environment path")
        temporary.write_text("\n".join(lines) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.envfile)

    def containers(self, project: str) -> list[dict[str, Any]]:
        ids = self.run(
            "docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"
        ).split()
        return json.loads(self.run("docker", "inspect", *ids)) if ids else []

    def local_engine(self) -> None:
        endpoint = (
            os.environ.get("DOCKER_HOST")
            or self.run(
                "docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
            ).strip()
        )
        if not endpoint.startswith("unix://"):
            raise RuntimeError("Only a local Unix-socket Docker Engine is allowed")

    def inspect_volume(self, name: str) -> dict[str, Any] | None:
        found = self.run(
            "docker", "volume", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"
        ).split()
        return (
            json.loads(self.run("docker", "volume", "inspect", name))[0] if name in found else None
        )

    def guard(self, service: str) -> dict[str, Any]:
        self.local_engine()
        value = self.configuration()
        for container in self.containers("skills-dev"):
            labels = container["Config"]["Labels"]
            if labels.get("com.docker.compose.project.working_dir") != str(ROOT):
                raise RuntimeError("Compose project belongs to another checkout")
        networks = self.run(
            "docker",
            "network",
            "ls",
            "--filter",
            "label=com.docker.compose.project=skills-dev",
            "--format",
            "{{.Name}}",
        ).split()
        for name in networks:
            network = json.loads(self.run("docker", "network", "inspect", name))[0]
            if (network.get("Labels") or {}).get("dev.agentomatic.checkout") != self.owner:
                raise RuntimeError("Network belongs to another checkout")
        for entry in value["volumes"][service].values():
            volume = self.inspect_volume(entry["name"])
            if volume and (volume.get("Labels") or {}) != entry["labels"]:
                raise RuntimeError("Volume belongs to another checkout or changed ownership")
        # The generated env file must not redirect lifecycle commands to other volumes.
        config = json.loads(self.run(*self.compose, "config", "--format", "json"))
        for volume, entry in value["volumes"][service].items():
            suffix = volume.removeprefix("mattermost-") if service == "mattermost" else volume
            if config["volumes"][f"{service}-{suffix}"]["name"] != entry["name"]:
                raise RuntimeError("Compose volume mapping changed outside preparation")
        return value

    def prepare(self, service: str) -> None:
        self.local_engine()
        value: dict[str, Any] = (
            self.configuration()
            if self.record.exists()
            else {"checkout": self.owner, "volumes": {}}
        )
        legacy = self.containers(LEGACY[service])
        old_path = ROOT / f"apps/{service}-test"
        for container in legacy:
            if container["Config"]["Labels"].get("com.docker.compose.project.working_dir") != str(
                old_path
            ):
                raise RuntimeError("Legacy Compose project belongs to another checkout")
        if service not in value["volumes"]:
            entries = {}
            mounted = {
                mount.get("Name")
                for container in legacy
                for mount in container["Mounts"]
                if mount["Type"] == "volume"
            }
            for volume in VOLUMES[service]:
                old_name = f"{LEGACY[service]}_{volume}"
                old = self.inspect_volume(old_name)
                if old:
                    labels = old.get("Labels") or {}
                    old_owner = hashlib.sha256(str(old_path).encode()).hexdigest()
                    owned = (
                        labels.get("dev.agentomatic.checkout") == old_owner
                        if service == "gitlab"
                        else old_name in mounted
                    )
                    if not owned or labels.get("com.docker.compose.project") != LEGACY[service]:
                        raise RuntimeError(
                            "Cannot establish ownership of legacy volume; data left untouched"
                        )
                    entries[volume] = {"name": old_name, "labels": labels}
                else:
                    suffix = (
                        volume.removeprefix("mattermost-") if service == "mattermost" else volume
                    )
                    name = f"skills-dev_{service}-{suffix}"
                    labels = {
                        "dev.agentomatic.checkout": self.owner,
                        "dev.agentomatic.service": service,
                    }
                    existing = self.inspect_volume(name)
                    if existing and (existing.get("Labels") or {}) != labels:
                        raise RuntimeError("Volume belongs to another checkout")
                    entries[volume] = {"name": name, "labels": labels}
            value["volumes"][service] = entries
            self.save(value)
        self.guard(service)
        # Stop only independently verified legacy containers, never remove their volumes.
        if legacy:
            ids = [container["Id"] for container in legacy]
            self.run("docker", "stop", *ids)
            self.run("docker", "rm", *ids)
        for entry in value["volumes"][service].values():
            if self.inspect_volume(entry["name"]) is None:
                args = ["docker", "volume", "create"]
                for label, content in entry["labels"].items():
                    args.extend(["--label", f"{label}={content}"])
                self.run(*args, entry["name"])

    def require_ready(self, service: str) -> None:
        containers = {
            item["Config"]["Labels"].get("com.docker.compose.service"): item
            for item in self.containers("skills-dev")
        }
        for name in SERVICES[service]:
            state = containers.get(name, {}).get("State", {})
            if (
                not state.get("Running")
                or state.get("Health", {}).get("Status", "healthy") != "healthy"
            ):
                raise RuntimeError(f"{service} is not ready; run task env:{service}:up")

    def fixture(self, service: str) -> Any:
        module = common.load(
            f"dev_{service}_fixtures", ROOT / f"tests/integration/{service}/scripts/stand.py"
        )
        port = int(
            os.environ.get(
                "GL_TEST_PORT" if service == "gitlab" else "MM_TEST_PORT",
                "443" if service == "gitlab" else "8443",
            )
        )
        return module.Stand(
            LEGACY[service], port, " ".join(self.compose[: self.compose.index("-p")])
        )

    def initialize(self, service: str) -> None:
        self.guard(service)
        stand = self.fixture(service)
        with (stand.home / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            stand.connect(initializing=True)
            stand.bootstrap()
            if service == "gitlab":
                runner(stand)
            print(
                "Manual area: "
                + (
                    stand.origin + "/" + stand.manifest["groups"]["manual"]["path"]
                    if service == "gitlab"
                    else stand.url("free")
                )
            )

    def clean(self, service: str) -> None:
        value = self.guard(service)
        stand = self.fixture(service)
        if any(path.is_symlink() for path in (stand.state, *stand.state.parents)) or any(
            path.is_symlink() for path in stand.state.rglob("*")
        ):
            raise RuntimeError("Cleanup refuses symlink state")
        with (stand.home / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for entry in value["volumes"][service].values():
                if self.inspect_volume(entry["name"]):
                    self.run("docker", "volume", "rm", entry["name"])
            shutil.rmtree(stand.state)
            common.private_directory(stand.state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "guard", "init", "clean"))
    parser.add_argument("service", choices=SERVICES)
    parser.add_argument("--compose", default=os.environ.get("COMPOSE", "docker-compose"))
    args = parser.parse_args()
    environment = Environment(args.compose)
    with (environment.home / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        {
            "prepare": environment.prepare,
            "guard": environment.guard,
            "init": environment.initialize,
            "clean": environment.clean,
        }[args.action](args.service)


if __name__ == "__main__":
    main()
