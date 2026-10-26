#!/usr/bin/env python3
"""Build the exact dev manifest for one development snapshot."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_distribution, build_release_artifacts  # noqa: E402

OUTPUT = ROOT / ".build" / "release"
# The dev channel serves this payload under /dev; the manifest must describe
# exactly what the deployed /dev subtree contains, not the composed root.
DEV_PAYLOAD = ROOT / ".build" / "packages" / "skills"


class DevArtifactError(Exception):
    pass


def build(version: str, revision: str) -> dict[str, Any]:
    if not build_distribution.DEV_SEMVER.fullmatch(version):
        raise DevArtifactError("development version is invalid")
    actual_revision = build_release_artifacts.command("git", "rev-parse", "HEAD").strip()
    if revision != actual_revision:
        raise DevArtifactError("development revision does not match HEAD")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "@kisev/skills-dev/v3",
        "channel": "dev",
        "version": version,
        "revision": revision,
        "pages": build_release_artifacts.page_hashes(DEV_PAYLOAD),
    }
    (OUTPUT / "dev.json").write_bytes(build_release_artifacts.canonical(manifest))
    return manifest


def main() -> int:
    version = os.environ.get("DEV_VERSION", "")
    revision = os.environ.get("DEV_REVISION", "")
    if not version or not revision:
        raise SystemExit("DEV_VERSION and DEV_REVISION are required")
    try:
        result = build(version, revision)
    except (DevArtifactError, build_release_artifacts.ArtifactError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(build_release_artifacts.canonical(result).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
