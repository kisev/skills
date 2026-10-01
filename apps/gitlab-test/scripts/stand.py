#!/usr/bin/env python3
"""Checkout-bound GitLab CE environment; no external GitLab endpoints."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import ssl
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/gitlab-test"
SPEC = importlib.util.spec_from_file_location(
    "gitlab_shared_stand", ROOT / "apps/mattermost-test/scripts/stand.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Shared stand utilities are unavailable")
shared = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shared)
command, private_directory, write_json = (
    shared.command,
    shared.private_directory,
    shared.write_json,
)
load = shared.load


class Stand:
    def __init__(self, project: str, port: int, compose: str = "docker-compose"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", project) or not 1 <= port <= 65535:
            raise ValueError("Invalid project name or localhost port")
        self.project, self.port = project, port
        self.origin = "https://localhost" + (f":{port}" if port != 443 else "")
        self.owner = hashlib.sha256(str(APP).encode()).hexdigest()
        self.home = private_directory(ROOT / ".build/gitlab-test" / project)
        self.state = private_directory(self.home / "state")
        self.reports = private_directory(self.home / "reports")
        self.compose = [*shlex.split(compose), "-p", project, "-f", str(APP / "compose.yml")]
        self.env = {
            **os.environ,
            "GL_TEST_PROJECT": project,
            "GL_TEST_PORT": str(port),
            "GL_TEST_OWNER": self.owner,
        }
        self.manifest: dict[str, Any] = {}
        self.ca = self.state / "root.crt"
        self.ca_bundle = self.state / "trust.pem"
        self.context: ssl.SSLContext | None = None

    def docker(self, *args: str, data: str | None = None, timeout: int = 120) -> str:
        return command([*self.compose, *args], data=data, env=self.env, timeout=timeout).stdout

    def resources(self) -> dict[str, Any]:
        endpoint = (
            os.environ.get("DOCKER_HOST")
            or command(
                ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"]
            ).stdout.strip()
        )
        if not endpoint.startswith("unix://"):
            raise RuntimeError("Only a local Unix-socket Docker Engine is allowed")
        config = json.loads(self.docker("config", "--format", "json"))
        names = sorted(value["name"] for value in config["volumes"].values())
        existing = command(
            [
                "docker",
                "volume",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                "{{.Name}}",
            ]
        ).stdout.split()
        if set(existing) - set(names):
            raise RuntimeError("Unexpected volumes in selected project")
        # Also inspect expected names: an unlabeled/foreign volume must not be adopted.
        for name in names:
            probe = command(
                ["docker", "volume", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"]
            )
            if probe.stdout.strip():
                volume = json.loads(command(["docker", "volume", "inspect", name]).stdout)[0]
                labels = volume.get("Labels") or {}
                if labels.get("dev.agentomatic.checkout") != self.owner:
                    raise RuntimeError("Volume belongs to another checkout or has no owner")
        ids = command(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={self.project}"]
        ).stdout.split()
        containers = json.loads(command(["docker", "inspect", *ids]).stdout) if ids else []
        for item in containers:
            if item["Config"]["Labels"].get("com.docker.compose.project.working_dir") != str(APP):
                raise RuntimeError("Compose project belongs to another checkout")
        ids = [item["Id"] for item in containers]
        network_names = sorted(value["name"] for value in config["networks"].values())
        networks = command(
            [
                "docker",
                "network",
                "ls",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                "{{.Name}}",
            ]
        ).stdout.split()
        if set(networks) - set(network_names):
            raise RuntimeError("Unexpected networks in selected project")
        owned_networks = []
        for name in network_names:
            found = command(
                ["docker", "network", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"]
            )
            if not found.stdout.strip():
                continue
            network = json.loads(command(["docker", "network", "inspect", name]).stdout)[0]
            labels = network.get("Labels") or {}
            attached = set(network.get("Containers") or {})
            # Older harness networks are accepted only while attached exclusively
            # to containers whose checkout was independently verified above.
            legacy_owned = (
                not labels.get("dev.agentomatic.checkout")
                and bool(attached)
                and attached <= set(ids)
            )
            if labels.get("dev.agentomatic.checkout") != self.owner and not legacy_owned:
                raise RuntimeError("Network belongs to another checkout or is unowned")
            owned_networks.append({"name": name, "id": network["Id"]})
        return {
            "project": self.project,
            "checkout": str(APP),
            "containers": sorted(ids),
            "volumes": sorted(existing),
            "networks": owned_networks,
            "state": str(self.state),
        }

    def start(self) -> None:
        self.resources()
        self.docker("up", "-d", "--wait", "--wait-timeout", "1200", timeout=1800)
        if self.ca.is_symlink() or self.ca_bundle.is_symlink():
            raise RuntimeError("Test certificate paths must not be symlinks")
        self.docker("cp", "proxy:/data/caddy/pki/authorities/local/root.crt", str(self.ca))
        self.context = ssl.create_default_context(cafile=str(self.ca))
        shared.write_ca_bundle(self.ca, self.ca_bundle)
        command(
            [
                "curl",
                "--fail",
                "--silent",
                "--head",
                "--cacert",
                str(self.ca),
                self.origin + "/users/sign_in",
            ]
        )

    def request(
        self,
        method: str,
        path: str,
        data: object = None,
        actor: str = "author",
        *,
        api: bool = True,
    ) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only stand-relative paths are allowed")
        headers = {"Content-Type": "application/json"}
        if api:
            headers["PRIVATE-TOKEN"] = self.manifest["users"][actor]["token"]
        request = urllib.request.Request(  # noqa: S310 - Fixed localhost origin, no redirects.
            self.origin + ("/api/v4" if api else "") + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.context), shared.NoRedirect()
        )
        try:
            with opener.open(request, timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as exc:
            exc.msg = self.redact(exc.read(4096).decode(errors="replace"))
            raise

    def bootstrap(self) -> None:
        fixture = self.state / "fixtures.json"
        if fixture.is_symlink():
            raise RuntimeError("Fixture credentials must not be symlinks")
        self.manifest = (
            json.loads(fixture.read_text())
            if fixture.exists()
            else {
                "owner": secrets.token_hex(6),
                "users": {
                    role: {
                        "password": secrets.token_urlsafe(30),
                        "token": "glpat-" + secrets.token_urlsafe(30),
                    }
                    for role in ("author", "reviewer", "outsider")
                },
            }
        )
        write_json(fixture, self.manifest)
        self.docker(
            "cp", str(APP / "scripts/bootstrap.rb"), "gitlab:/opt/gitlab/harness-bootstrap.rb"
        )
        output = self.docker(
            "exec",
            "-T",
            "gitlab",
            "gitlab-rails",
            "runner",
            "/opt/gitlab/harness-bootstrap.rb",
            data=json.dumps(self.manifest),
            timeout=240,
        )
        result = json.loads(
            next(
                line.removeprefix("HARNESS_JSON=")
                for line in output.splitlines()
                if line.startswith("HARNESS_JSON=")
            )
        )
        for role, user in result["users"].items():
            self.manifest["users"][role].update(user)
        write_json(fixture, self.manifest)
        projects = self.request("GET", "/projects?owned=true&per_page=100")
        for name in ("free", "fixtures"):
            project = next((p for p in projects if p["path"] == name), None)
            if project is None:
                project = self.request(
                    "POST",
                    "/projects",
                    {"name": name, "visibility": "private", "initialize_with_readme": True},
                )
            self.manifest[name] = project
        project_id = self.manifest["fixtures"]["id"]
        members = self.request("GET", f"/projects/{project_id}/members")
        for role in ("author", "reviewer"):
            user_id = self.manifest["users"][role]["id"]
            if not any(member["id"] == user_id for member in members):
                self.request(
                    "POST",
                    f"/projects/{project_id}/members",
                    {"user_id": user_id, "access_level": 40},
                )
        write_json(fixture, self.manifest)

    def isolated_env(self, actor: str = "author") -> dict[str, str]:
        home = private_directory(self.state / actor)
        return {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / "config"),
            "XDG_DATA_HOME": str(home / "data"),
            "XDG_STATE_HOME": str(home / "state"),
            "XDG_CACHE_HOME": str(home / "cache"),
            "GLAB_CONFIG_DIR": str(home / "glab"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "GITLAB_HOST": self.origin,
            "GITLAB_TOKEN": self.manifest["users"][actor]["token"],
            "SSL_CERT_FILE": str(self.ca_bundle),
            "GIT_SSL_CAINFO": str(self.ca),
            "NO_COLOR": "1",
        }

    def redact(self, text: str) -> str:
        for user in self.manifest.get("users", {}).values():
            for key in ("token", "password"):
                text = text.replace(user[key], "[REDACTED]")
        return text

    def reset_plan(self) -> dict[str, Any]:
        scope = self.resources()
        return {
            "scope": scope,
            "digest": hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest(),
        }

    def reset(self, confirmation: str) -> None:
        plan = self.reset_plan()
        if confirmation != plan["digest"]:
            raise RuntimeError("Reset requires matching scope confirmation")
        if any(path.is_symlink() for path in (self.state, *self.state.parents)) or any(
            path.is_symlink() for path in self.state.rglob("*")
        ):
            raise RuntimeError("Reset refuses symlinks")
        self.docker("down", "--volumes", timeout=240)
        # Only the validated private state tree is deleted; reports survive.
        shutil.rmtree(self.state)
        private_directory(self.state)
        self.start()
        self.bootstrap()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("config", "init", "up", "test", "live", "logs", "down", "reset", "reset-test"),
    )
    parser.add_argument("--compose", default="docker-compose")
    args = parser.parse_args()
    stand = Stand(
        os.environ.get("GL_TEST_PROJECT", "gitlab-workflows"),
        int(os.environ.get("GL_TEST_PORT", "443")),
        args.compose,
    )
    report: dict[str, Any] = {
        "action": args.action,
        "status": "failed",
        "checks": [],
        "live": "not-run",
        "declared_versions": {
            "server_image": "gitlab/gitlab-ce:18.11.11-ce.0",
            "runner_image": "gitlab/gitlab-runner:v18.11.0",
            "glab": "1.120.0",
        },
    }
    started = time.monotonic()
    destination = private_directory(
        stand.reports / (time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3))
    )
    with (stand.home / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.action == "live":
                shared.load("gitlab_live", APP / "scripts/live_checks.py").settings()
            if args.action == "config":
                stand.docker("config", "--quiet")
            elif args.action in ("logs", "down"):
                stand.resources()
                print(
                    stand.redact(
                        stand.docker("logs", "--tail=100")
                        if args.action == "logs"
                        else stand.docker("down")
                    )
                )
            elif args.action == "reset":
                confirmation = os.environ.get("GL_RESET_CONFIRM", "")
                if not confirmation:
                    print(json.dumps(stand.reset_plan(), indent=2))
                else:
                    stand.reset(confirmation)
            else:
                stand.start()
                report["startup_seconds"] = round(time.monotonic() - started, 3)
                if args.action != "up":
                    stand.bootstrap()
                    report["versions"] = {
                        "server": stand.request("GET", "/version"),
                        "runner": stand.docker(
                            "exec", "-T", "runner", "gitlab-runner", "--version"
                        ),
                        "cli": command(["glab", "--version"]).stdout.strip(),
                    }
                    versions = report["versions"]
                    if (
                        versions["server"]["version"] != "18.11.11"
                        or not re.search(r"Version:\s+18\.11\.0\b", versions["runner"])
                        or not re.search(r"\b1\.120\.0\b", versions["cli"])
                    ):
                        raise RuntimeError(
                            "Observed server/Runner/glab version differs from the pinned contract"
                        )
                    report["checks"].append(
                        {
                            "name": "owned-bootstrap",
                            "status": "passed",
                            "evidence": {
                                "owner": stand.manifest["owner"],
                                "users": {
                                    role: user["id"]
                                    for role, user in stand.manifest["users"].items()
                                },
                                "fixtures_project": stand.manifest["fixtures"]["id"],
                                "free_project": stand.manifest["free"]["id"],
                            },
                        }
                    )
                    report["resources"] = stand.docker(
                        "stats", "--no-stream", "--format", "{{json .}}"
                    )
                    print("Free zone: " + stand.manifest["free"]["web_url"])
                    if args.action in ("test", "live", "reset-test"):
                        checks = shared.load("gitlab_checks", APP / "scripts/checks.py")
                        checks.run(stand, destination, report, args.action)
        except Exception as exc:
            report["error"] = stand.redact(str(exc))
            (destination / "failure.txt").write_text(stand.redact(traceback.format_exc()))
            report["checks"].append(
                {"name": "operation", "status": "failed", "evidence": report["error"]}
            )
            print(report["error"], file=sys.stderr)
            return 1
        else:
            report["status"] = "passed"
            return 0
        finally:
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            write_json(destination / "result.json", report)
            write_json(
                stand.reports / "latest.json",
                {"report": str(destination / "result.json"), "status": report["status"]},
            )
            print("Report: " + str(destination / "result.json"))


if __name__ == "__main__":
    sys.exit(main())
