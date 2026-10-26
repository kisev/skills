"""The environment contract: one requirements manifest per archive with dependencies.

These tests pin the authored inventory, the deterministic materialization the
distribution build stitches into every archive with external dependencies, the
stdlib environment runner shipped inside each archive, and the local channel
cross-check (manifest pin, Pages index, workspace npm pin).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, cast

import pytest

from scripts import build_distribution

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "shared" / "references" / "environment_check.py"
SOURCE = ROOT / "shared" / "runtime-requirements.json"

pytestmark = pytest.mark.xdist_group("distribution-state")

# The complete inventory of archives with external dependencies, derived from
# each skill's SKILL.source.md, references, and scripts.
EXPECTED_SKILLS = {
    "ast-grep": ["ast-grep"],
    "code-review": ["git", "glab", "uv"],
    "commit-msg": ["git"],
    "mr-prepare": ["glab"],
    "release-prepare": ["glab"],
    "release-review": ["glab"],
    "rtk": ["git", "rtk"],
    "task-prepare": ["glab"],
    "task-triage": ["git", "glab"],
    "taskmatic": ["@kisev/taskmatic"],
    "team-retro": ["glab"],
}


def authored_source() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(SOURCE.read_text(encoding="utf-8")))


def archive_member(archive: Path, name: str) -> bytes | None:
    with tarfile.open(archive, mode="r:gz") as document:
        if name not in document.getnames():
            return None
        extracted = document.extractfile(name)
        assert extracted is not None
        return extracted.read()


def test_authored_inventory_covers_every_archive_with_external_dependencies() -> None:
    source = authored_source()
    assert source["version"] == 1
    assert source["skills"] == EXPECTED_SKILLS
    tools = source["tools"]
    for dependencies in EXPECTED_SKILLS.values():
        for tool in dependencies:
            record = tools[tool]
            assert record["check"] and record["install"]
            assert "version" in record or "version_ref" in record


def test_distribution_materializes_requirements_per_dependency_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "skills"
    assert build_distribution.build(output, False) == 0
    verdict = capsys.readouterr().out
    assert "channel:" in verdict and "verdict=ok" in verdict
    index = json.loads((output / "index.json").read_text(encoding="utf-8"))
    lock = json.loads((output / "skills-lock.json").read_text(encoding="utf-8"))
    for entry in index["skills"]:
        archive = output / entry["archive"]
        manifest = archive_member(archive, "references/requirements.json")
        runtime_pin = archive_member(archive, "references/runtime-pin.json")
        if entry["name"] in EXPECTED_SKILLS:
            assert manifest is not None, entry["name"]
            parsed = json.loads(manifest)
            assert parsed["schema"] == "@kisev/skills/requirements/v1"
            assert parsed["skill"] == entry["name"]
            assert parsed["version"] == index["version"]
            assert parsed["source_revision"] == index["source_revision"]
            assert [node["tool"] for node in parsed["requirements"]] == EXPECTED_SKILLS[
                entry["name"]
            ]
            for node in parsed["requirements"]:
                assert node["source_revision"] == index["source_revision"]
                assert node["check"] and node["install"]
            # The materialized manifest absorbs the legacy runtime pin.
            assert runtime_pin is None, entry["name"]
        else:
            assert manifest is None, entry["name"]
            assert runtime_pin is None, entry["name"]
    assert lock["source_revision"] == index["source_revision"]
    assert lock["version"] == index["version"]


def test_retired_npm_package_is_absent_from_the_workspace_lock() -> None:
    lockfile = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    packages = lockfile["packages"]
    assert "packages/agentomatic" not in packages
    assert not any(name.startswith("node_modules/@kisev/agentomatic") for name in packages)


def test_runner_reports_ok_fail_and_repair(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references").mkdir()
    shutil.copyfile(RUNNER, skill / "scripts" / "check_environment.py")
    (skill / "references" / "requirements.json").write_text(
        json.dumps(
            {
                "schema": "@kisev/skills/requirements/v1",
                "skill": "demo",
                "version": "1.2.3",
                "source_revision": "a" * 40,
                "requirements": [
                    {
                        "tool": "present",
                        "check": "python3 -c 'print(\"ready\")'",
                        "install": "install present",
                        "version": None,
                        "source_revision": "a" * 40,
                    },
                    {
                        "tool": "absent",
                        "check": "this-tool-does-not-exist --version",
                        "install": "npm install --global absent@1.2.3",
                        "version": "1.2.3",
                        "source_revision": "a" * 40,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(skill / "scripts" / "check_environment.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "OK   present" in completed.stdout
    assert "FAIL absent" in completed.stdout
    assert "repair: npm install --global absent@1.2.3" in completed.stdout
    assert completed.stdout.rstrip().endswith("npm install --global absent@1.2.3")


def test_runner_reports_a_missing_manifest(tmp_path: Path) -> None:
    skill = tmp_path / "demo"
    (skill / "scripts").mkdir(parents=True)
    shutil.copyfile(RUNNER, skill / "scripts" / "check_environment.py")
    completed = subprocess.run(
        [sys.executable, str(skill / "scripts" / "check_environment.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "no requirements manifest" in completed.stderr


def test_runner_help_is_available(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "requirements.json" in completed.stdout
