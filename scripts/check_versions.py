#!/usr/bin/env python3
"""Validate release, installer pin, and documentation version authorities."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
NUMERIC_COMMAND_PIN = re.compile(r"(?:npx\s+--yes\s+)?skills@[0-9]+\.[0-9]+\.[0-9]+")


class VersionError(Exception):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VersionError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise VersionError(f"expected an object in {path}")
    return value


def require_string(value: object, label: str, *, semver: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise VersionError(f"{label} must be a non-empty string")
    if semver and not SEMVER.fullmatch(value):
        raise VersionError(f"{label} must be an X.Y.Z version")
    return value


def public_documents(root: Path) -> list[Path]:
    documents = [
        path
        for name in ("README.md", "README.ru.md", "CONTRIBUTING.md", "CONTRIBUTING.ru.md")
        if (path := root / name).is_file()
    ]
    docs = root / "docs"
    if docs.is_dir():
        documents.extend(path for path in docs.rglob("*.md") if path.is_file())
    packages = root / "packages"
    if packages.is_dir():
        documents.extend(path for path in packages.glob("*/README*.md") if path.is_file())
    return sorted(set(documents))


def validate_public_documents(root: Path, release: str) -> int:
    documents = public_documents(root)
    release_pattern = re.compile(rf"(?<![0-9.]){re.escape(release)}(?![0-9.])")
    for path in documents:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root)
        if release_pattern.search(text):
            raise VersionError(f"public documentation copies current release {release}: {relative}")
        match = NUMERIC_COMMAND_PIN.search(text)
        if match:
            raise VersionError(f"public documentation pins {match.group(0)}: {relative}")
    return len(documents)


def validate_skill_metadata(root: Path) -> int:
    sources = sorted((root / "skills").glob("*/SKILL.source.md"))
    if not sources:
        raise VersionError("no portable skill sources found")
    for path in sources:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise VersionError(f"invalid skill frontmatter: {path.relative_to(root)}")
        frontmatter = text.split("---", 2)[1]
        if re.search(r"^\s*version\s*:", frontmatter, re.MULTILINE):
            raise VersionError(
                f"portable skill metadata carries a version: {path.relative_to(root)}"
            )
    return len(sources)


def validate(root: Path = ROOT) -> dict[str, object]:
    portable = read_json(root / "packages/skills/package.json")
    memomatic = read_json(root / "apps/memomatic/package.json")
    lock = read_json(root / "package-lock.json")
    with (root / "mise.toml").open("rb") as stream:
        mise = tomllib.load(stream)

    release = require_string(portable.get("version"), "portable release", semver=True)
    lock_packages = lock.get("packages")
    if not isinstance(lock_packages, dict) or not isinstance(lock_packages.get(""), dict):
        raise VersionError("workspace package lock root is invalid")
    member = lock_packages.get("apps/memomatic")
    if not isinstance(member, dict) or member.get("version") != memomatic.get("version"):
        raise VersionError("memomatic workspace member version differs from its manifest")
    with (root / "apps/skillmate/pyproject.toml").open("rb") as stream:
        skillmate_project = tomllib.load(stream).get("project")
    if not isinstance(skillmate_project, dict):
        raise VersionError("skillmate project table is missing")
    distribution = require_string(
        skillmate_project.get("version"), "skillmate distribution", semver=True
    )
    if distribution != release:
        raise VersionError("skillmate distribution version differs from the portable release")
    skillmate_init = (root / "apps/skillmate/src/skillmate/__init__.py").read_text(encoding="utf-8")
    init_version = re.search(r'^__version__ = "([^"]+)"$', skillmate_init, re.MULTILINE)
    if not init_version or init_version.group(1) != release:
        raise VersionError("skillmate __version__ differs from the portable release")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.search(
        r"^## \\?\[([0-9]+\.[0-9]+\.[0-9]+)\] - \d{4}-\d{2}-\d{2}$",
        changelog,
        re.MULTILINE,
    )
    if not heading or heading.group(1) != release:
        raise VersionError("first changelog release does not match project release")

    tools = mise.get("tools")
    if not isinstance(tools, dict):
        raise VersionError("mise tools table is missing")
    mise_installer = require_string(tools.get("npm:skills"), "mise npm:skills", semver=True)

    skills = validate_skill_metadata(root)
    documents = validate_public_documents(root, release)
    return {
        "schema": "version-check/v1",
        "status": "passed",
        "release": release,
        "skillmate_distribution": distribution,
        "skills_installer": mise_installer,
        "portable_skills": skills,
        "public_documents": documents,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        result = validate()
    except (OSError, VersionError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
