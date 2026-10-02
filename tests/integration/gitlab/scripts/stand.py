#!/usr/bin/env python3
"""Checkout-bound GitLab CE environment; no external GitLab endpoints."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shlex
import ssl
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, unquote, urlsplit

from tests.integration.mattermost.scripts import stand as shared

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "tests/integration/gitlab"

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
        self.owner = hashlib.sha256(str(ROOT).encode()).hexdigest()
        self.home = private_directory(ROOT / ".build/gitlab-test" / project)
        self.state = private_directory(self.home / "state")
        self.reports = private_directory(self.home / "reports")
        self.compose = [
            *shlex.split(compose),
            "-p",
            "skills-dev",
            "--env-file",
            str(ROOT / ".build/env/compose.env"),
            "-f",
            str(ROOT / "docker-compose.yml"),
        ]
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
        self.access_log: list[dict[str, str]] = []

    def docker(self, *args: str, data: str | None = None, timeout: int = 120) -> str:
        forbidden = {"up", "down", "stop", "start", "restart", "rm"}
        if args and args[0] in forbidden:
            raise ValueError("Tests cannot manage containers; use task env:gitlab:* explicitly")
        mapped = shared.service_arguments(
            args, {"proxy": "gitlab-proxy", "runner": "gitlab-runner"}
        )
        return command([*self.compose, *mapped], data=data, env=self.env, timeout=timeout).stdout

    def resources(self) -> dict[str, Any]:
        environment = load("gitlab_dev_environment", ROOT / "dev/env.py").Environment(
            " ".join(self.compose[: self.compose.index("-p")])
        )
        return cast("dict[str, Any]", environment.guard("gitlab"))

    def connect(self, *, initializing: bool = False) -> None:
        self.resources()
        if not initializing:
            fixture = self.state / "fixtures.json"
            if fixture.is_symlink() or not fixture.is_file():
                raise RuntimeError("GitLab fixtures are not initialized; run task env:gitlab:up")
            self.manifest = json.loads(fixture.read_text())
        load("gitlab_dev_readiness", ROOT / "dev/env.py").Environment(
            " ".join(self.compose[: self.compose.index("-p")])
        ).require_ready("gitlab")
        if self.ca.is_symlink() or self.ca_bundle.is_symlink():
            raise RuntimeError("Test certificate paths must not be symlinks")
        if initializing:
            self.docker("cp", "proxy:/data/caddy/pki/authorities/local/root.crt", str(self.ca))
        if not self.ca.is_file():
            raise RuntimeError("GitLab CA is missing; run task env:gitlab:up")
        self.context = ssl.create_default_context(cafile=str(self.ca))
        if initializing:
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
        _initialize_fixture: bool = False,
    ) -> Any:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only stand-relative paths are allowed")
        if not api and (method != "GET" or path not in ("/users/sign_in", "/-/readiness")):
            raise ValueError("Automation cannot browse arbitrary non-API resources")
        if api:
            if _initialize_fixture:
                expected = {
                    "name": "fixtures",
                    "namespace_id": self.manifest["groups"]["fixtures"]["id"],
                    "visibility": "private",
                    "initialize_with_readme": True,
                }
                if method != "POST" or path != "/projects" or data != expected or actor != "author":
                    raise ValueError("Only exact fixture initialization is allowed")
            else:
                self.fixture_scope(path)
            if actor not in ("author", "reviewer", "outsider"):
                raise ValueError(
                    "Manual credentials are initialization-only, never an automation actor"
                )
            self.access_log.append({"method": method, "path": path, "actor": actor})
        headers = {"Content-Type": "application/json"}
        if api:
            headers["PRIVATE-TOKEN"] = self.manifest["users"][actor]["token"]
        request = urllib.request.Request(
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

    def fixture_scope(self, path: str) -> None:
        """Reject unbounded enumeration and non-fixture resources before transport."""
        endpoint = unquote(urlsplit(path).path)
        if endpoint in ("/version", "/user", "/user/runners"):
            return
        fixture = self.manifest.get("fixtures", {})
        identities = (str(fixture.get("id", "")), fixture.get("path_with_namespace", ""))
        if any(
            identity
            and (
                endpoint == f"/projects/{identity}" or endpoint.startswith(f"/projects/{identity}/")
            )
            for identity in identities
        ) and not any(part in (".", "..") for part in endpoint.split("/")):
            return
        raise ValueError(
            "Automation may access only the fixtures project, never manual or project catalogs"
        )

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
        initialize_manual = not self.manifest.get("groups", {}).get("manual")
        if initialize_manual and "manual" not in self.manifest["users"]:
            self.manifest["users"]["manual"] = {
                "password": secrets.token_urlsafe(30),
                "token": "glpat-" + secrets.token_urlsafe(30),
            }
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
            data=json.dumps({**self.manifest, "initialize_manual": initialize_manual}),
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
        self.manifest.setdefault("groups", {}).update(result["groups"])
        write_json(fixture, self.manifest)
        group = self.manifest["groups"]["fixtures"]
        if self.manifest.get("fixtures"):
            project = self.manifest["fixtures"]
            if project["namespace"]["id"] != group["id"]:
                project = self.request(
                    "PUT", f"/projects/{project['id']}/transfer", {"namespace": group["id"]}
                )
        else:
            # Recover a partially completed initialization by exact identity,
            # without enumerating any namespace or touching the manual group.
            self.manifest["fixtures"] = {"path_with_namespace": group["path"] + "/fixtures"}
            try:
                project = self.request(
                    "GET",
                    "/projects/" + quote(self.manifest["fixtures"]["path_with_namespace"], safe=""),
                )
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                project = self.create_fixture_project(group)
        self.manifest["fixtures"] = project
        project = self.request("GET", "/projects/" + quote(project["path_with_namespace"], safe=""))
        self.manifest["fixtures"] = project
        write_json(fixture, self.manifest)
        project_id = self.manifest["fixtures"]["id"]
        members = self.request("GET", f"/projects/{project_id}/members/all")
        for role in ("author", "reviewer"):
            user_id = self.manifest["users"][role]["id"]
            if not any(member["id"] == user_id for member in members):
                self.request(
                    "POST",
                    f"/projects/{project_id}/members",
                    {"user_id": user_id, "access_level": 40},
                )
        write_json(fixture, self.manifest)

    def create_fixture_project(self, group: dict[str, Any]) -> dict[str, Any]:
        return cast(
            "dict[str, Any]",
            self.request(
                "POST",
                "/projects",
                {
                    "name": "fixtures",
                    "namespace_id": group["id"],
                    "visibility": "private",
                    "initialize_with_readme": True,
                },
                _initialize_fixture=True,
            ),
        )

    def isolated_env(self, actor: str = "author") -> dict[str, str]:
        if actor not in ("author", "reviewer", "outsider"):
            raise ValueError("Manual credentials are not available to automation")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("preflight", "test", "browser", "live"),
    )
    parser.add_argument("--compose", default="docker-compose")
    args = parser.parse_args()
    stand = Stand(
        "gitlab-workflows",
        int(os.environ.get("GL_TEST_PORT", "443")),
        args.compose,
    )
    report: dict[str, Any] = {
        "action": args.action,
        "status": "failed",
        "checks": [],
        "live": "not-run",
        "started_at": datetime.now(UTC).isoformat(),
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
            if args.action == "preflight":
                report["preflight"] = shared.load(
                    "gitlab_preflight", APP / "scripts/preflight.py"
                ).run(stand, destination, browser=False)
            else:
                report["preflight"] = shared.load(
                    "gitlab_preflight", APP / "scripts/preflight.py"
                ).run(stand, destination, browser=args.action == "browser")
                stand.connect()
                if args.action in ("test", "browser", "live"):
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
                                "automation_scope": "fixtures only; manual contents not inspected",
                            },
                        }
                    )
                    report["resources"] = stand.docker(
                        "stats", "--no-stream", "--format", "{{json .}}"
                    )
                    if args.action in ("test", "browser", "live"):
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
            write_json(
                destination / "automation-access.json",
                {
                    "requests": stand.access_log,
                    "scope": "fixtures only",
                    "manual_contents_inspected": False,
                },
            )
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            if "resources" in report:
                try:
                    report["resources_final"] = stand.docker(
                        "stats", "--no-stream", "--format", "{{json .}}"
                    )
                except Exception as exc:
                    report["resources_final_error"] = stand.redact(str(exc))
            write_json(destination / "result.json", report)
            write_json(
                stand.reports / "latest.json",
                {"report": str(destination / "result.json"), "status": report["status"]},
            )
            print("Report: " + str(destination / "result.json"))


if __name__ == "__main__":
    sys.exit(main())
