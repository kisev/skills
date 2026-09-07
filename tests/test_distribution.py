from __future__ import annotations

import hashlib
import http.server
import io
import json
import subprocess
import tarfile
import threading
import urllib.request
from functools import partial
from pathlib import Path

from scripts import build_distribution


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build" / "packages" / "skills"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def test_distribution_has_well_known_index_root_skill_archives_and_digest_lock() -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(OUTPUT))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        index = json.loads(urllib.request.urlopen(f"{base}/.well-known/skills/index.json").read())
        lock = json.loads(urllib.request.urlopen(f"{base}/.well-known/skills/lock.json").read())
        assert index["schema"] == "@kisev/skills/index/v1"
        assert index["source_revision"] == lock["source_revision"]
        assert index["skills"]
        for skill in index["skills"]:
            archive = urllib.request.urlopen(f"{base}/{skill['archive']}").read()
            assert (
                hashlib.sha256(archive).hexdigest()
                == lock["archives"][skill["name"]]
                == skill["sha256"]
            )
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as document:
                assert "SKILL.md" in document.getnames()
    finally:
        server.shutdown()
        thread.join()


def test_local_http_fixture_installs_and_updates_with_pinned_skills_for_both_agents(
    tmp_path: Path,
) -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(OUTPUT))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    binary = subprocess.check_output(["mise", "which", "skills"], cwd=ROOT, text=True).strip()
    assert subprocess.check_output([binary, "--version"], text=True).strip() == "1.5.23"
    try:
        index = f"http://127.0.0.1:{server.server_port}/.well-known/skills/index.json"
        for agent in ("opencode", "codex"):
            home = tmp_path / agent
            command = [
                "python3",
                "scripts/install_distribution.py",
                "--index-url",
                index,
                "--skill",
                "code-review",
                "--agent",
                agent,
                "--skills-binary",
                binary,
                "--home",
                str(home),
            ]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
            assert first.returncode == second.returncode == 0, first.stderr + second.stderr
            assert json.loads(first.stdout)["status"] == "added"
            assert json.loads(second.stdout)["status"] == "updated"
            assert (home / ".agents" / "skills" / "code-review" / "SKILL.md").is_file()
            assert (
                stat_mode(home / ".local" / "state" / "kisev-skills" / "distribution-lock.json")
                == 0o600
            )
    finally:
        server.shutdown()
        thread.join()


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777
