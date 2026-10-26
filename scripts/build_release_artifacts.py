#!/usr/bin/env python3
"""Build the immutable npm artifact and cross-channel release manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import release_channel  # noqa: E402

OUTPUT = ROOT / ".build" / "release"
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


class ArtifactError(Exception):
    """The release provenance cannot be built."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def command(*arguments: str, cwd: Path = ROOT) -> str:
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise ArtifactError(result.stderr.strip() or f"{' '.join(arguments)} failed")
    return result.stdout.strip()


def page_hashes() -> dict[str, Any]:
    pages = OUTPUT.parent / "pages"
    if not pages.is_dir():
        raise ArtifactError(f"composed Pages channel is missing at {pages}")
    files: dict[str, Any] = {}
    for path in sorted(pages.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files[path.relative_to(pages).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
    if not files:
        raise ArtifactError("composed Pages channel is empty")
    return {"files": files}


def build(tag: str, revision: str) -> dict[str, Any]:
    version = json.loads(
        (ROOT / "packages" / "skills" / "package.json").read_text(encoding="utf-8")
    ).get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ArtifactError("portable release version is invalid")
    if tag != f"v{version}":
        raise ArtifactError("release tag and portable version differ")
    actual_revision = command("git", "rev-parse", "HEAD").strip()
    if revision != actual_revision:
        raise ArtifactError("release revision does not match HEAD")
    try:
        channel = release_channel.resolve(tag, revision)
    except release_channel.ChannelError as error:
        raise ArtifactError(str(error)) from error

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    manifest = {
        "schema": "@kisev/skills-release/v3",
        "tag": tag,
        "version": version,
        "revision": revision,
        "channel": channel["channel"],
        "pages": page_hashes(),
    }
    (OUTPUT / "release.json").write_bytes(canonical(manifest))
    return manifest


def main() -> int:
    tag = os.environ.get("RELEASE_TAG", "")
    revision = os.environ.get("RELEASE_REVISION", "")
    if not tag or not revision:
        raise SystemExit("RELEASE_TAG and RELEASE_REVISION are required")
    try:
        result = build(tag, revision)
    except (ArtifactError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(canonical(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
