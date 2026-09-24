#!/usr/bin/env python3
"""Validate release, installer, compatibility, and documentation version authorities."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
NUMERIC_COMMAND_PIN = re.compile(
    r"(?:npx\s+--yes\s+)?(?:skills|@kisev/skills-opencode)@[0-9]+\.[0-9]+\.[0-9]+"
)


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
    opencode = read_json(root / "packages/opencode/package.json")
    lock = read_json(root / "packages/opencode/package-lock.json")
    compatibility = read_json(root / "evals/contracts/opencode-compatibility.json")
    with (root / "mise.toml").open("rb") as stream:
        mise = tomllib.load(stream)

    release = require_string(portable.get("version"), "portable release", semver=True)
    lock_packages = lock.get("packages")
    if not isinstance(lock_packages, dict) or not isinstance(lock_packages.get(""), dict):
        raise VersionError("OpenCode package lock root is invalid")
    release_mirrors = {
        "packages/opencode/package.json": opencode.get("version"),
        "packages/opencode/package-lock.json": lock.get("version"),
        "packages/opencode/package-lock.json packages root": lock_packages[""].get("version"),
    }
    drift = {name: value for name, value in release_mirrors.items() if value != release}
    if drift:
        raise VersionError(f"project release mirrors differ from {release}: {drift}")
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
    installer = require_string(
        opencode.get("skillsInstallerVersion"), "package skills installer", semver=True
    )
    mise_installer = require_string(tools.get("npm:skills"), "mise npm:skills", semver=True)
    if installer != mise_installer:
        raise VersionError(
            f"skills installer versions differ: package={installer}, mise={mise_installer}"
        )

    compatibility_range = require_string(compatibility.get("range"), "compatibility range")
    peer_dependencies = opencode.get("peerDependencies")
    if not isinstance(peer_dependencies, dict):
        raise VersionError("OpenCode peer dependencies are missing")
    if peer_dependencies.get("@opencode-ai/plugin") != compatibility_range:
        raise VersionError("OpenCode peer range differs from compatibility authority")
    versions = compatibility.get("versions")
    if (
        not isinstance(versions, list)
        or not versions
        or not all(isinstance(item, str) for item in versions)
    ):
        raise VersionError("OpenCode compatibility versions are invalid")
    compatible = set(versions)
    dev_dependencies = opencode.get("devDependencies")
    if not isinstance(dev_dependencies, dict):
        raise VersionError("OpenCode development dependencies are missing")
    checked_versions = {
        "package dev dependency": dev_dependencies.get("@opencode-ai/plugin"),
        "mise OpenCode": tools.get("aqua:anomalyco/opencode"),
    }
    unsupported = {
        name: value for name, value in checked_versions.items() if value not in compatible
    }
    if unsupported:
        raise VersionError(
            f"OpenCode checked versions are outside compatibility authority: {unsupported}"
        )

    skills = validate_skill_metadata(root)
    documents = validate_public_documents(root, release)
    return {
        "schema": "version-check/v1",
        "status": "passed",
        "release": release,
        "skills_installer": installer,
        "portable_skills": skills,
        "public_documents": documents,
        "opencode_compatibility": sorted(compatible),
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
