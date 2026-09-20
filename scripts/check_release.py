#!/usr/bin/env python3
"""Validate release versions, provenance, and the built Pages distribution."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_PACKAGE = ROOT / "packages" / "skills" / "package.json"
OPENCODE_PACKAGE = ROOT / "packages" / "opencode" / "package.json"
OPENCODE_LOCK = ROOT / "packages" / "opencode" / "package-lock.json"
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class ReleaseError(Exception):
    pass


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"expected an object in {path}")
    return value


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ReleaseError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def validate(
    tag: str | None = None, *, published: bool = False, require_clean: bool = False
) -> dict[str, str]:
    portable = read_json(PORTABLE_PACKAGE).get("version")
    opencode = read_json(OPENCODE_PACKAGE).get("version")
    lock = read_json(OPENCODE_LOCK)
    lock_root = lock.get("packages")
    if not isinstance(lock_root, dict) or not isinstance(lock_root.get(""), dict):
        raise ReleaseError("OpenCode package lock root is invalid")
    versions = {
        "portable": portable,
        "opencode": opencode,
        "opencode_lock_document": lock.get("version"),
        "opencode_lock": lock_root[""].get("version"),
    }
    if not all(isinstance(value, str) for value in versions.values()):
        raise ReleaseError("release versions must be strings")
    normalized = {name: str(value) for name, value in versions.items()}
    if len(set(normalized.values())) != 1:
        raise ReleaseError(f"release versions differ: {normalized}")
    version = normalized["portable"]
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"invalid release version: {version}")
    if (
        re.search(
            rf"^## \\?\[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
            CHANGELOG.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        is None
    ):
        raise ReleaseError(f"CHANGELOG.md has no release heading for {version}")

    revision = git("rev-parse", "HEAD")
    if require_clean and git("status", "--porcelain"):
        raise ReleaseError("release validation requires a clean working tree")
    expected_revision = os.environ.get("RELEASE_REVISION")
    if expected_revision is not None and expected_revision != revision:
        raise ReleaseError("release environment revision does not match HEAD")
    release_index = read_json(DISTRIBUTION / "index.json")
    if release_index.get("version") != version:
        raise ReleaseError("Pages distribution version does not match release version")
    if release_index.get("source_revision") != revision:
        raise ReleaseError("Pages distribution revision does not match HEAD")

    if published and tag is None:
        raise ReleaseError("published release validation requires a tag")
    if tag is not None:
        expected = f"v{version}"
        if tag != expected:
            raise ReleaseError(f"tag {tag!r} does not match {expected!r}")
    if published and tag is not None:
        if git("cat-file", "-t", f"refs/tags/{tag}") != "tag":
            raise ReleaseError("release tag must be annotated")
        if git("rev-parse", f"refs/tags/{tag}^{{commit}}") != revision:
            raise ReleaseError("release tag does not reference HEAD")
        stable_tags = [
            value.removeprefix("v")
            for value in git("tag", "--list", "v*").splitlines()
            if SEMVER.fullmatch(value.removeprefix("v"))
        ]
        if stable_tags and tuple(map(int, version.split("."))) != max(
            tuple(map(int, value.split("."))) for value in stable_tags
        ):
            raise ReleaseError("release tag is older than the latest stable tag")
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, "origin/main"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ReleaseError("release commit is not reachable from origin/main")

    return {"version": version, "revision": revision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG"))
    parser.add_argument(
        "--published",
        action="store_true",
        help="require the annotated tag and release commit to exist on origin/main",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="reject uncommitted release inputs",
    )
    args = parser.parse_args(argv)
    try:
        result = validate(args.tag, published=args.published, require_clean=args.require_clean)
    except ReleaseError as error:
        parser.error(str(error))
    print(json.dumps({"status": "ok", **result}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
