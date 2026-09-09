from __future__ import annotations

import gzip
import hashlib
import http.server
import io
import json
import os
import shutil
import tarfile
import threading
import urllib.request
from functools import partial
from pathlib import Path
from subprocess import run

import pytest

from scripts import build_distribution


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build" / "packages" / "skills"
PINNED_SKILLS = ["npx", "--yes", "skills@1.5.23"]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def test_distribution_has_reproducible_well_known_archives_and_lock() -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    index = json.loads((OUTPUT / ".well-known/agent-skills/index.json").read_text(encoding="utf-8"))
    lock = json.loads((OUTPUT / "skills-lock.json").read_text(encoding="utf-8"))
    assert index["$schema"] == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    assert index["skills"]
    for entry in index["skills"]:
        source = (ROOT / "skills" / entry["name"] / "SKILL.md").read_text(encoding="utf-8")
        assert entry["description"] in source
        archive = OUTPUT / entry["url"].removeprefix("../../")
        assert entry["digest"] == f"sha256:{hashlib.sha256(archive.read_bytes()).hexdigest()}"
        assert lock["archives"][entry["name"]] == entry["digest"].removeprefix("sha256:")
        with tarfile.open(archive, mode="r:gz") as document:
            assert "SKILL.md" in document.getnames()
            names = set(document.getnames())
            assert not any(part in {"ru", "en"} for name in names for part in name.split("/"))
            if entry["name"] == "project-spec":
                assert not any(name.startswith("templates/ru/") for name in names)
            if entry["name"] == "mattermost":
                assert "scripts/mattermost.py" in document.getnames()


def test_distribution_check_rejects_unexpected_file(tmp_path: Path) -> None:
    output = tmp_path / "skills"
    assert build_distribution.build(output, False) == 0
    (output / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    try:
        build_distribution.build(output, True)
    except build_distribution.DistributionError as error:
        assert "unexpected distribution artifact" in str(error)
    else:
        raise AssertionError("expected unexpected artifact rejection")


def test_well_known_http_add_and_update_use_pinned_skills_lock(tmp_path: Path) -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    fixture = tmp_path / "fixture"
    shutil.copytree(OUTPUT, fixture)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        source = f"http://127.0.0.1:{server.server_port}"
        assert (
            run(
                [*PINNED_SKILLS, "--version"], capture_output=True, text=True, check=True
            ).stdout.strip()
            == "1.5.23"
        )
        for agent in ("opencode", "codex"):
            home, state = tmp_path / agent / "home", tmp_path / agent / "state"
            environment = {
                **os.environ,
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_STATE_HOME": str(state),
            }
            added = run(
                [
                    *PINNED_SKILLS,
                    "add",
                    source,
                    "--skill",
                    "mattermost",
                    "--agent",
                    agent,
                    "--global",
                    "--copy",
                    "--yes",
                ],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert added.returncode == 0, added.stderr
            lock_path = state / "skills" / ".skill-lock.json"
            before = json.loads(lock_path.read_text(encoding="utf-8"))["skills"]["mattermost"]
            assert before["sourceType"] == "well-known"
            assert before["sourceBaseUrl"] == source
            update_archive(fixture, "mattermost")
            served = json.loads(
                urllib.request.urlopen(f"{source}/.well-known/agent-skills/index.json").read()
            )
            expected = next(item for item in served["skills"] if item["name"] == "code-review")[
                "digest"
            ]
            assert expected != before["wellKnownDigest"]
            updated = run(
                [*PINNED_SKILLS, "update", "--global", "--yes"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert updated.returncode == 0, updated.stderr
            after = json.loads(lock_path.read_text(encoding="utf-8"))["skills"]["mattermost"]
            assert after["wellKnownDigest"] != before["wellKnownDigest"], updated.stdout
            assert (home / ".agents/skills/mattermost/update-marker.txt").is_file()
    finally:
        server.shutdown()
        thread.join()
        build_distribution.build(OUTPUT, False)


def test_direct_git_install_is_self_contained_for_both_hosts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(source)], check=True)
    if not (source / "skills/ast-grep/scripts/portable_runtime").is_dir():
        pytest.skip("direct Git fixture requires committed generated copies")
    skills = sorted(
        path.name for path in (source / "skills").iterdir() if (path / "SKILL.md").is_file()
    )
    assert len(skills) == 29

    for agent in ("opencode", "codex"):
        for scope in ("global", "project"):
            home = tmp_path / agent / scope / "home"
            project = tmp_path / agent / scope / "project"
            home.mkdir(parents=True)
            project.mkdir(parents=True)
            environment = {
                **os.environ,
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_STATE_HOME": str(home / ".state"),
                "PYTHONPATH": str(tmp_path / "missing-pythonpath"),
            }
            command = [
                *PINNED_SKILLS,
                "add",
                str(source),
                "--skill",
                "*",
                "--agent",
                agent,
                "--copy",
                "--yes",
            ]
            if scope == "global":
                command.append("--global")
            installed = run(
                command,
                cwd=project,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            assert installed.returncode == 0, installed.stderr

            shutil.rmtree(source)
            root = (
                home / ".agents" / "skills" if scope == "global" else project / ".agents" / "skills"
            )
            for skill in skills:
                installed_skill = root / skill
                assert (installed_skill / "SKILL.md").is_file()
                for runner in installed_skill.glob("scripts/*.py"):
                    help_result = run(
                        ["python3", str(runner), "--help"],
                        cwd=tmp_path,
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    assert help_result.returncode == 0, (runner, help_result.stderr)
            source = tmp_path / f"source-{agent}-{scope}"
            run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(source)], check=True)


def update_archive(distribution: Path, skill: str) -> None:
    archive = distribution / "archives" / f"{skill}.tar.gz"
    previous_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    files: dict[str, bytes] = {}
    with tarfile.open(archive, mode="r:gz") as document:
        for member in document.getmembers():
            if member.isfile():
                extracted = document.extractfile(member)
                assert extracted is not None
                files[member.name] = extracted.read()
    files["update-marker.txt"] = f"updated:{previous_digest}\n".encode()
    payload = io.BytesIO()
    with gzip.GzipFile(fileobj=payload, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as document:
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size, info.mode, info.mtime = len(content), 0o644, 0
                document.addfile(info, io.BytesIO(content))
    archive.write_bytes(payload.getvalue())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    index_path = distribution / ".well-known/agent-skills/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    next(item for item in index["skills"] if item["name"] == skill)["digest"] = f"sha256:{digest}"
    index_path.write_text(
        json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
