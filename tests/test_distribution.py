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
from typing import TYPE_CHECKING

from scripts import build_distribution

if TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build" / "packages" / "skills"
PACKAGE_METADATA = json.loads(
    (ROOT / "packages" / "opencode" / "package.json").read_text(encoding="utf-8")
)
RELEASE_VERSION = PACKAGE_METADATA["version"]
SKILLS_INSTALLER_VERSION = PACKAGE_METADATA["skillsInstallerVersion"]
PINNED_SKILLS = ["npx", "--yes", f"skills@{SKILLS_INSTALLER_VERSION}"]


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def test_distribution_requires_materialized_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-skills"
    monkeypatch.setattr(build_distribution, "BUILT_SKILLS", missing)
    try:
        build_distribution.build(tmp_path / "distribution", False)
    except build_distribution.DistributionError as error:
        assert "run task build:skills first" in str(error)
    else:
        raise AssertionError("expected missing built skills to be rejected")


def test_distribution_has_reproducible_well_known_archives_and_lock() -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    index = json.loads((OUTPUT / ".well-known/agent-skills/index.json").read_text(encoding="utf-8"))
    lock = json.loads((OUTPUT / "skills-lock.json").read_text(encoding="utf-8"))
    release = json.loads((OUTPUT / "index.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())
    assert index["$schema"] == "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    assert release["version"] == RELEASE_VERSION
    assert (
        release["source_revision"]
        == run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    assert [entry["name"] for entry in index["skills"]] == sorted(inventory["skills"])
    assert (OUTPUT / ".nojekyll").is_file()
    assert not (OUTPUT / "package.json").exists()
    for entry in index["skills"]:
        source = (ROOT / ".build/skills" / entry["name"] / "SKILL.md").read_text(encoding="utf-8")
        assert entry["description"] in source
        assert entry["url"].startswith("../../archives/sha256/")
        archive = OUTPUT / entry["url"].removeprefix("../../")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        assert archive.name == f"{digest}.tar.gz"
        assert entry["digest"] == f"sha256:{digest}"
        assert lock["archives"][entry["name"]] == entry["digest"].removeprefix("sha256:")
        with tarfile.open(archive, mode="r:gz") as document:
            assert "SKILL.md" in document.getnames()
            names = set(document.getnames())
            assert not any(part in {"ru", "en"} for name in names for part in name.split("/"))
            if entry["name"] == "spec-manage":
                assert not any(name.startswith("templates/ru/") for name in names)
            if entry["name"] == "mattermost":
                assert "scripts/mattermost.py" in document.getnames()


def test_distribution_is_byte_reproducible(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    assert build_distribution.build(first, False) == 0
    assert build_distribution.build(second, False) == 0
    first_files = {
        path.relative_to(first): path.read_bytes() for path in first.rglob("*") if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }
    assert first_files == second_files


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
    fixture = tmp_path / "site" / "skills"
    fixture.parent.mkdir(parents=True)
    shutil.copytree(OUTPUT, fixture)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture.parent))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        source = f"http://127.0.0.1:{server.server_port}/skills"
        assert (
            run(
                [*PINNED_SKILLS, "--version"], capture_output=True, text=True, check=True
            ).stdout.strip()
            == SKILLS_INSTALLER_VERSION
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
            expected = next(item for item in served["skills"] if item["name"] == "mattermost")[
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


def test_pages_install_is_self_contained_for_both_hosts_and_scopes(tmp_path: Path) -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    site = tmp_path / "site"
    fixture = site / "skills"
    shutil.copytree(OUTPUT, fixture)
    index = json.loads((fixture / ".well-known/agent-skills/index.json").read_text())
    skills = sorted(entry["name"] for entry in index["skills"])
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(site))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    installed_roots: list[tuple[Path, dict[str, str]]] = []

    try:
        source = f"http://127.0.0.1:{server.server_port}/skills"
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
                    source,
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
                root = (
                    home / ".agents" / "skills"
                    if scope == "global"
                    else project / ".agents" / "skills"
                )
                installed_roots.append((root, environment))
    finally:
        server.shutdown()
        thread.join()
        shutil.rmtree(site)

    for root, environment in installed_roots:
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


def test_authored_repository_is_not_an_install_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(
        ROOT,
        source,
        ignore=shutil.ignore_patterns(
            ".git",
            ".build",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "node_modules",
            "dist",
            "__pycache__",
        ),
    )
    assert not list((source / "skills").glob("*/SKILL.md"))
    result = run(
        [*PINNED_SKILLS, "add", str(source), "--list"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "No valid skills found" in result.stdout


def update_archive(distribution: Path, skill: str) -> None:
    index_path = distribution / ".well-known/agent-skills/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    entry = next(item for item in index["skills"] if item["name"] == skill)
    archive = distribution / entry["url"].removeprefix("../../")
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
    content = payload.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    updated_archive = distribution / "archives" / "sha256" / f"{digest}.tar.gz"
    updated_archive.write_bytes(content)
    entry["url"] = f"../../archives/sha256/{digest}.tar.gz"
    entry["digest"] = f"sha256:{digest}"
    index_path.write_text(
        json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
