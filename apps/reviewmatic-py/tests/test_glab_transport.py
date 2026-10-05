"""Real glab transport of positioned note bodies, ported from
``glab-transport.test.mjs``.

The pinned ``glab`` binary posts to a loopback server; the test asserts the
nested JSON the server receives and that invalid bracket fields fail before
any HTTP request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any

from reviewmatic.publication import command_argv, make_command

if TYPE_CHECKING:
    from pathlib import Path


def test_real_glab_serializes_positioned_bodies_as_nested_json_without_bracket_fields(
    tmp_path: Path,
) -> None:
    root = tmp_path
    config = root / "config"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(root),
        "XDG_CONFIG_HOME": str(config),
        "GLAB_CONFIG_DIR": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GITLAB_TOKEN": "synthetic-test-token",
        "NO_COLOR": "1",
    }

    def run(*argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv, env=env, cwd=root, capture_output=True, text=True, timeout=10, check=check
        )

    version = run("glab", "version")
    assert re.search(r"glab 1\.120\.0\b", version.stdout)

    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length))
            requests.append({"method": self.command, "url": self.path, "body": body})
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id":"synthetic"}')

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = "gitlab.example"
        config.mkdir(parents=True, exist_ok=True)
        (config / "config.yml").write_text(
            f"hosts:\n  {host}:\n    api_protocol: http\n"
            f"    api_host: 127.0.0.1:{server.server_address[1]}\n"
        )
        repo = root / "repo"
        repo.mkdir()

        def git(*arguments: str) -> str:
            return subprocess.run(
                ["git", "-C", str(repo), *arguments],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        git("init", "-q")
        git("config", "user.name", "Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "commit.gpgsign", "false")
        path = "file with spaces.txt"
        (repo / path).write_text("context\nold\n")
        git("add", ".")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (repo / path).write_text("context\nnew\n")
        git("commit", "-qam", "head")
        head = git("rev-parse", "HEAD")
        body = "Текст 'quoted' \"double\" $(literal)\\path\n\n```suggestion\nvalue\n```\n"
        bodies = root / "artifacts" / "review_plan" / "bodies"
        bodies.mkdir(parents=True)
        (bodies / "body.md").write_text(body, encoding="utf-8")
        evidence = {
            "project": {"hostname": host, "id": 7},
            "target": {"iid": 3},
            "base_sha": base,
            "head_sha": head,
            "object": {"diff_refs": {"base_sha": base, "start_sha": base, "head_sha": head}},
            "changed_files": {"items": [{"old_path": path, "new_path": path}]},
        }
        for flag, line, expected in (
            ("--line", 2, {"new_line": 2}),
            ("--line", 1, {"new_line": 1, "old_line": 1}),
            ("--old-line", 2, {"old_line": 2}),
        ):
            command = make_command(
                root,
                evidence,
                {"exact_git": {"repo_root": str(repo)}},
                "test",
                ["glab", "mr", "note", "create", "3", "--file", path, flag, str(line)],
                {},
                {},
                hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
            argv = command_argv(command)
            run(*argv)
            assert requests[-1] == {
                "method": "POST",
                "url": "/api/v4/projects/7/merge_requests/3/discussions",
                "body": {
                    "body": body,
                    "position": {
                        "position_type": "text",
                        "base_sha": base,
                        "start_sha": base,
                        "head_sha": head,
                        "new_path": path,
                        "old_path": path,
                        **expected,
                    },
                },
            }
            direct_request = requests[-1]
            run("sh", "-c", command)
            assert requests[-1] == direct_request, "copied shell command matches argv transport"
        count = len(requests)
        rejected = run(
            "glab",
            "api",
            "--hostname",
            host,
            "--method",
            "POST",
            "projects/7/merge_requests/3/discussions",
            "-f",
            "position[new_line]=2",
            check=False,
        )
        assert rejected.returncode != 0
        assert "bracket" in rejected.stderr + rejected.stdout
        assert len(requests) == count, "invalid fields fail before HTTP"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
