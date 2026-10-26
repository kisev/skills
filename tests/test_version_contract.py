from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import check_versions

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def version_root(root: Path) -> Path:
    write_json(root / "packages/skills/package.json", {"version": "2.2.3"})
    write_json(
        root / "apps/memomatic/package.json",
        {"version": "1.0.0"},
    )
    write_json(
        root / "package-lock.json",
        {
            "version": "2.2.3",
            "packages": {
                "": {"version": "2.2.3"},
                "apps/memomatic": {"version": "1.0.0"},
            },
        },
    )
    (root / "mise.toml").write_text('[tools]\n"npm:skills" = "1.5.23"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text("## [2.2.3] - 2026-09-15\n", encoding="utf-8")
    skill = root / "skills/example/SKILL.source.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        '---\nname: example\ndescription: Example\nmetadata:\n  author: "Example"\n---\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text("Use `npx --yes skills@latest`.\n", encoding="utf-8")
    skillmate = root / "apps/skillmate/pyproject.toml"
    skillmate.parent.mkdir(parents=True, exist_ok=True)
    skillmate.write_text('[project]\nname = "skillmate"\nversion = "2.2.3"\n', encoding="utf-8")
    package = root / "apps/skillmate/src/skillmate/__init__.py"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text('__version__ = "2.2.3"\n', encoding="utf-8")
    return root


def test_repository_version_contract_is_centralized() -> None:
    result = check_versions.validate(ROOT)
    assert result["status"] == "passed"
    assert result["portable_skills"] == 44
    installer = result["skills_installer"]
    assert isinstance(installer, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", installer)


def test_version_contract_rejects_skillmate_distribution_drift(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    pyproject = root / "apps/skillmate/pyproject.toml"
    pyproject.write_text('[project]\nname = "skillmate"\nversion = "9.9.9"\n', encoding="utf-8")
    with pytest.raises(check_versions.VersionError, match="skillmate distribution"):
        check_versions.validate(root)


def test_version_contract_rejects_skillmate_cli_version_drift(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    package = root / "apps/skillmate/src/skillmate/__init__.py"
    package.write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    with pytest.raises(check_versions.VersionError, match="skillmate __version__"):
        check_versions.validate(root)


def test_version_contract_rejects_memomatic_member_drift(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    document = check_versions.read_json(root / "package-lock.json")
    document["packages"]["apps/memomatic"]["version"] = "9.9.9"
    write_json(root / "package-lock.json", document)
    with pytest.raises(check_versions.VersionError, match="memomatic workspace member"):
        check_versions.validate(root)


def test_version_contract_rejects_numeric_public_documentation_pin(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    (root / "README.md").write_text(
        "Run `npx --yes skills@1.5.23 add`.\n",
        encoding="utf-8",
    )
    with pytest.raises(check_versions.VersionError, match="public documentation"):
        check_versions.validate(root)


def test_version_contract_rejects_authored_skill_version(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    (root / "skills/example/SKILL.source.md").write_text(
        '---\nname: example\ndescription: Example\nmetadata:\n  author: "Example"\n  version: "2.2.3"\n---\n',
        encoding="utf-8",
    )
    with pytest.raises(check_versions.VersionError, match="skill metadata carries a version"):
        check_versions.validate(root)


def test_version_contract_reports_the_mise_installer_pin(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    result = check_versions.validate(root)
    assert result["skills_installer"] == "1.5.23"
