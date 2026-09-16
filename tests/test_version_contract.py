from __future__ import annotations

import json
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
        root / "packages/opencode/package.json",
        {
            "version": "2.2.3",
            "skillsInstallerVersion": "1.5.23",
            "peerDependencies": {"@opencode-ai/plugin": ">=1.18.29 <1.19.0"},
            "devDependencies": {"@opencode-ai/plugin": "1.18.29"},
        },
    )
    write_json(
        root / "packages/opencode/package-lock.json",
        {"version": "2.2.3", "packages": {"": {"version": "2.2.3"}}},
    )
    write_json(root / "specs/traceability.json", {"target": "2.2.3"})
    write_json(
        root / "evals/contracts/opencode-compatibility.json",
        {"range": ">=1.18.29 <1.19.0", "versions": ["1.18.29", "1.18.30"]},
    )
    (root / "mise.toml").write_text(
        '[tools]\n"npm:skills" = "1.5.23"\nopencode = "1.18.29"\n',
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text("## [2.2.3] - 2026-09-15\n", encoding="utf-8")
    skill = root / "skills/example/SKILL.source.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        '---\nname: example\ndescription: Example\nmetadata:\n  author: "Example"\n---\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "Use `npx --yes skills@latest` and `@kisev/skills-opencode@latest`.\n",
        encoding="utf-8",
    )
    return root


def test_repository_version_contract_is_centralized() -> None:
    result = check_versions.validate(ROOT)
    assert result["status"] == "passed"
    assert result["portable_skills"] == 27
    assert result["skills_installer"] == "1.5.23"


def test_version_contract_rejects_release_mirror_drift(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    package = check_versions.read_json(root / "packages/opencode/package.json")
    package["version"] = "9.9.9"
    write_json(root / "packages/opencode/package.json", package)
    with pytest.raises(check_versions.VersionError, match="release mirrors"):
        check_versions.validate(root)


def test_version_contract_rejects_numeric_public_documentation_pin(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    (root / "README.md").write_text(
        "Run `npx --yes @kisev/skills-opencode@2.2.3 doctor --global`.\n",
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


def test_version_contract_rejects_installer_pin_drift(tmp_path: Path) -> None:
    root = version_root(tmp_path)
    package = check_versions.read_json(root / "packages/opencode/package.json")
    package["skillsInstallerVersion"] = "1.5.22"
    write_json(root / "packages/opencode/package.json", package)
    with pytest.raises(check_versions.VersionError, match="installer versions differ"):
        check_versions.validate(root)
