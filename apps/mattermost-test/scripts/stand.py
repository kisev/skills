#!/usr/bin/env python3
"""Persistent, project-bound local Mattermost fixture environment."""

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
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/mattermost-test"


def load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def private_directory(path: Path) -> Path:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise RuntimeError("Test state paths must not contain symlinks")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def write_json(path: Path, value: object) -> None:
    private_directory(path.parent)
    temporary = path.with_name(path.name + ".new")
    if path.is_symlink() or temporary.is_symlink():
        raise RuntimeError("Unsafe test state file")
    with temporary.open("w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(path)


def command(
    args: list[str],
    *,
    data: str | None = None,
    timeout: int = 120,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 - Bounded CLI vectors, never a shell.
        args,
        input=data,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        cwd=ROOT,
        env=env,
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(args[0]).name} failed (exit {result.returncode}): {result.stderr[-1000:]}"
        )
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class Stand:
    def __init__(self, project: str, port: int, compose: str = "docker-compose"):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", project) or not 1024 <= port <= 65535:
            raise ValueError("Use a simple Compose project name and a port from 1024 to 65535")
        self.project, self.port = project, port
        self.origin = f"https://localhost:{port}"
        self.home = private_directory(ROOT / ".build/mattermost-test" / project)
        self.state = private_directory(self.home / "state")
        self.reports = private_directory(self.home / "reports")
        self.compose = [*shlex.split(compose), "-p", project, "-f", str(APP / "compose.yml")]
        self.env = {**os.environ, "MM_TEST_PROJECT": project, "MM_TEST_PORT": str(port)}
        self.manifest: dict[str, Any] = {}
        self.ca = self.state / "root.crt"
        self.ca_bundle = self.state / "trust.pem"
        self.context: ssl.SSLContext | None = None

    def docker(self, *args: str, data: object = None, timeout: int = 360) -> str:
        return command(
            [*self.compose, *args],
            data=json.dumps(data) if data is not None else None,
            timeout=timeout,
            env=self.env,
        ).stdout

    def resources(self) -> dict[str, Any]:
        config = json.loads(self.docker("config", "--format", "json"))
        ids = self.docker("ps", "-aq").split()
        containers = json.loads(command(["docker", "inspect", *ids]).stdout) if ids else []
        for item in containers:
            labels = item["Config"]["Labels"]
            if labels.get("com.docker.compose.project") != self.project or labels.get(
                "com.docker.compose.project.working_dir"
            ) != str(APP):
                raise RuntimeError("Compose project belongs to another checkout")
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
            raise RuntimeError("Unexpected project volumes; refusing ambiguous reset scope")
        return {
            "project": self.project,
            "checkout": str(APP),
            "containers": sorted(ids),
            "volumes": sorted(existing),
            "state": str(self.state),
        }

    def start(self) -> None:
        self.resources()
        self.docker("up", "-d", "--wait", "--wait-timeout", "240")
        if self.ca.is_symlink() or self.ca_bundle.is_symlink():
            raise RuntimeError("Test certificate paths must not be symlinks")
        for attempt in range(15):
            try:
                self.docker("cp", "proxy:/data/caddy/pki/authorities/local/root.crt", str(self.ca))
                break
            except RuntimeError:
                if attempt == 14:
                    raise
                time.sleep(1)
        self.context = ssl.create_default_context(cafile=str(self.ca))
        defaults = ssl.get_default_verify_paths()
        roots = [Path(defaults.cafile)] if defaults.cafile else []
        if defaults.capath:
            roots.extend(sorted(Path(defaults.capath).glob("*.0")))
        self.ca_bundle.write_bytes(
            b"\n".join(path.read_bytes() for path in roots) + b"\n" + self.ca.read_bytes()
        )
        self.request("GET", "/system/ping")

    def local(self, method: str, path: str, data: object = None, *, missing: bool = False) -> Any:
        payload = {"method": method, "path": path}
        if data is not None:
            payload["data"] = data
        result = json.loads(self.docker("run", "--rm", "-T", "--no-deps", "driver", data=payload))
        if result["status"] == 404 and missing:
            return None
        if result["status"] >= 400:
            raise RuntimeError(f"Local fixture API {method} {path}: HTTP {result['status']}")
        return result["body"]

    def request(
        self,
        method: str,
        path: str,
        data: object = None,
        actor: str | None = None,
        *,
        missing: bool = False,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if actor:
            headers["Authorization"] = "Bearer " + self.manifest["users"][actor]["token"]
        request = urllib.request.Request(  # noqa: S310 - Origin is fixed to localhost HTTPS.
            self.origin + "/api/v4" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        try:
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=self.context), NoRedirect()
            )
            with opener.open(request, timeout=30) as response:
                body = response.read()
                value = json.loads(body) if body else None
                if path == "/users/login":
                    return {"token": response.headers["Token"], "id": value["id"]}
                return value
        except urllib.error.HTTPError as exc:
            if missing and exc.code == 404:
                return None
            raise RuntimeError(f"Fixture API {method} {path}: HTTP {exc.code}") from None

    def save(self) -> None:
        write_json(self.state / "fixtures.json", self.manifest)

    def redact(self, text: str) -> str:
        for user in self.manifest.get("users", {}).values():
            for key in ("token", "password"):
                if user.get(key):
                    text = text.replace(user[key], "[REDACTED]")
        return text

    def bootstrap(self) -> None:
        path = self.state / "fixtures.json"
        self.manifest = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "owner": secrets.token_hex(6),
                "users": {},
                "posts": {},
                "channels": {},
            }
        )
        owner = self.manifest["owner"]
        self.save()
        # The local administrator socket is used only to provision owned accounts.
        for role in ("admin", "reader", "peer", "third"):
            username = f"mt-{owner}-{role}"
            user = self.manifest["users"].get(role)
            if user and user.get("token"):
                try:
                    self.request("GET", "/users/me", actor=role)
                    continue
                except RuntimeError:
                    pass
            password = user["password"] if user else secrets.token_urlsafe(24) + "Aa1!"
            if not user:
                created = self.local("GET", "/users/username/" + username, missing=True)
                if created is None:
                    created = self.local(
                        "POST",
                        "/users",
                        {
                            "username": username,
                            "email": username + "@example.invalid",
                            "password": password,
                        },
                    )
                else:
                    self.local(
                        "PUT", f"/users/{created['id']}/password", {"new_password": password}
                    )
                user = {"id": created["id"], "username": username, "password": password}
                self.manifest["users"][role] = user
                self.save()
            if role == "admin":
                self.local(
                    "PUT", f"/users/{user['id']}/roles", {"roles": "system_user system_admin"}
                )
            user.update(
                self.request("POST", "/users/login", {"login_id": username, "password": password})
            )
            self.save()
        team_name = "mt-" + owner
        team = self.request("GET", "/teams/name/" + team_name, actor="admin", missing=True)
        if team is None:
            team = self.request(
                "POST",
                "/teams",
                {
                    "name": team_name,
                    "display_name": "Mattermost tests",
                    "type": "O",
                    "description": "Owned fixture " + owner,
                },
                "admin",
            )
        self.manifest["team"] = team
        for user in self.manifest["users"].values():
            membership = self.request(
                "GET", f"/teams/{team['id']}/members/{user['id']}", actor="admin", missing=True
            )
            if membership is None:
                self.request(
                    "POST",
                    f"/teams/{team['id']}/members",
                    {"team_id": team["id"], "user_id": user["id"]},
                    "admin",
                )
        for name in ("read", "publish", "cards", "private", "free"):
            channel = self.request(
                "GET", f"/teams/{team['id']}/channels/name/{name}", actor="admin", missing=True
            )
            created_channel = channel is None
            if channel is None:
                channel = self.request(
                    "POST",
                    "/channels",
                    {
                        "team_id": team["id"],
                        "name": name,
                        "display_name": name.title(),
                        "type": "P" if name == "private" else "O",
                        "header": "Manual experiments"
                        if name == "free"
                        else "Owned fixture " + owner,
                    },
                    "admin",
                )
            self.manifest["channels"][name] = channel["id"]
            if name != "private" and (name != "free" or created_channel):
                for role in ("reader", "peer", "third"):
                    uid = self.manifest["users"][role]["id"]
                    found = self.request(
                        "GET",
                        f"/channels/{channel['id']}/members/{uid}",
                        actor="admin",
                        missing=True,
                    )
                    if found is None:
                        self.request(
                            "POST", f"/channels/{channel['id']}/members", {"user_id": uid}, "admin"
                        )
        ids = [self.manifest["users"][role]["id"] for role in ("reader", "peer", "third")]
        self.manifest["channels"]["direct"] = self.request(
            "POST", "/channels/direct", ids[:2], "reader"
        )["id"]
        self.manifest["channels"]["group"] = self.request("POST", "/channels/group", ids, "reader")[
            "id"
        ]
        self.save()
        for index in range(205):
            self.post(f"page-{index:03d}", "read", f"Pagination fixture {index:03d}")
        root = self.post("thread-root", "read", "Need a review of the retry fix.")
        self.post("thread-reply", "read", "Please check concurrent retries.", root["id"])
        self.post("direct-root", "direct", "Please review the retry fix.")
        self.post("group-root", "group", "Who can verify the retry fix?")
        if "free-sentinel" not in self.manifest["posts"]:
            self.post(
                "free-sentinel", "free", "Manual area: automated checks preserve this channel."
            )
        self.request(
            "POST",
            "/reactions",
            {"user_id": ids[1], "post_id": root["id"], "emoji_name": "eyes"},
            "peer",
        )
        self.save()

    def post(self, key: str, channel: str, message: str, root: str = "") -> dict[str, Any]:
        existing = self.manifest["posts"].get(key)
        if existing:
            found = self.request("GET", "/posts/" + existing, actor="reader", missing=True)
            if found is not None:
                return found
        result = self.request(
            "POST",
            "/posts",
            {
                "channel_id": self.manifest["channels"][channel],
                "message": message,
                "root_id": root,
                "props": {"mattermost_test_fixture": key},
            },
            "reader",
        )
        self.manifest["posts"][key] = result["id"]
        self.save()
        return result

    def url(self, channel: str) -> str:
        team = self.manifest["team"]["name"]
        if channel == "direct":
            return f"{self.origin}/{team}/messages/@{self.manifest['users']['peer']['username']}"
        if channel == "group":
            return f"{self.origin}/{team}/group/{self.manifest['channels']['group']}"
        return f"{self.origin}/{team}/channels/{channel}"

    def skill_environment(self) -> dict[str, str]:
        environment = {**os.environ, "SSL_CERT_FILE": str(self.ca_bundle)}
        for variable, directory in (
            ("XDG_CONFIG_HOME", "config"),
            ("XDG_STATE_HOME", "xdg-state"),
            ("XDG_CACHE_HOME", "cache"),
        ):
            environment[variable] = str(private_directory(self.state / directory))
        return environment

    def reset_plan(self) -> dict[str, Any]:
        if not (self.state / "fixtures.json").is_file():
            raise RuntimeError("Reset requires an initialized, owned test state")
        scope = self.resources()
        scope["owner"] = json.loads((self.state / "fixtures.json").read_text())["owner"]
        scope["port"] = self.port
        scope["warning"] = (
            "Deletes this test server, free zone, credentials and local skill state; preserves reports"
        )
        scope["digest"] = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        return scope

    def reset(self, confirmation: str) -> None:
        plan = self.reset_plan()
        if not secrets.compare_digest(confirmation, plan["digest"]):
            raise RuntimeError("Reset confirmation does not match the current scope")
        if any(path.is_symlink() for path in self.state.rglob("*")):
            raise RuntimeError("Reset state contains symlinks")
        if (self.state / "browser-config.json").exists():
            self.manifest = json.loads((self.state / "fixtures.json").read_text())
            browser = load("mm_reset_browser", APP / "scripts/browser_checks.py")
            browser.Browser(self, self.reports).close()
        self.docker("down", "--volumes")
        shutil.rmtree(self.state)
        private_directory(self.state)
        self.start()
        self.bootstrap()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "test", "live", "reset", "reset-test"))
    parser.add_argument("--project", default=os.environ.get("MM_TEST_PROJECT", "mattermost-cards"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MM_TEST_PORT", "8443")))
    parser.add_argument("--compose", default=os.environ.get("COMPOSE", "docker-compose"))
    parser.add_argument("--confirm", default=os.environ.get("MM_RESET_CONFIRM"))
    args = parser.parse_args()
    try:
        if args.mode == "live":
            live_runner = load("mm_live_settings", APP / "scripts/live_checks.py")
            live_runner.settings()
        stand = Stand(args.project, args.port, args.compose)
        with (stand.home / "stand.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.mode == "reset":
                if args.confirm:
                    stand.reset(args.confirm)
                    print(json.dumps({"status": "initialized", "origin": stand.origin}))
                else:
                    print(json.dumps(stand.reset_plan(), indent=2))
                return 0
            stand.start()
            stand.bootstrap()
            if args.mode == "init":
                print(
                    json.dumps(
                        {
                            "status": "initialized",
                            "origin": stand.origin,
                            "free_zone": stand.url("free"),
                        }
                    )
                )
                return 0
            if args.mode == "reset-test":
                reset_runner = load("mm_reset_test", APP / "scripts/reset_checks.py")
                print(json.dumps(reset_runner.run(stand)))
                return 0
            runner = load("mattermost_stand_checks", APP / "scripts/checks.py")
            return int(runner.run(stand, live=args.mode == "live"))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
