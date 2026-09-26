#!/usr/bin/env python3
"""Build the exact npm artifact and manifest for one development snapshot."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_distribution, build_release_artifacts  # noqa: E402

PACKAGE = ROOT / "packages" / "agentomatic"
OUTPUT = ROOT / ".build" / "release"


class DevArtifactError(Exception):
    pass


def pack(version: str) -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="skills-dev-pack-") as temporary:
        staged = Path(temporary) / "package"
        staged.mkdir()
        for name in ("README.md", "README.ru.md", "package.json"):
            shutil.copyfile(PACKAGE / name, staged / name)
        shutil.copytree(PACKAGE / "dist", staged / "dist")
        package = json.loads((staged / "package.json").read_text(encoding="utf-8"))
        package["version"] = version
        (staged / "package.json").write_text(
            json.dumps(package, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
        )
        output = build_release_artifacts.command(
            "npm",
            "pack",
            "--ignore-scripts",
            "--json",
            "--pack-destination",
            temporary,
            cwd=staged,
        )
        records = json.loads(output)
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise DevArtifactError("npm pack returned an invalid record")
        record = records[0]
        files = record.get("files")
        if not isinstance(files, list):
            raise DevArtifactError("npm pack did not report its files")
        paths = [item.get("path") if isinstance(item, dict) else None for item in files]
        if not all(isinstance(path, str) for path in paths):
            raise DevArtifactError("npm pack returned an invalid file record")
        normalized_paths = sorted(str(path) for path in paths)
        if not all(
            path in build_release_artifacts.ALLOWED_PACKAGE_FILES or path.startswith("dist/")
            for path in normalized_paths
        ):
            raise DevArtifactError("npm package contains an unexpected file")
        if record.get("version") != version:
            raise DevArtifactError("npm pack version differs from the development version")
        filename = record.get("filename")
        if not isinstance(filename, str):
            raise DevArtifactError("npm pack filename is missing")
        return (Path(temporary) / filename).read_bytes(), record


def build(version: str, revision: str) -> dict[str, Any]:
    if not build_distribution.DEV_SEMVER.fullmatch(version):
        raise DevArtifactError("development version is invalid")
    actual_revision = build_release_artifacts.command("git", "rev-parse", "HEAD").strip()
    if revision != actual_revision:
        raise DevArtifactError("development revision does not match HEAD")
    package = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    name = package.get("name")
    if not isinstance(name, str) or not name:
        raise DevArtifactError("npm package name is invalid")

    content, record = pack(version)
    digest = build_release_artifacts.hashes(content)
    if record.get("integrity") != digest["integrity"] or record.get("shasum") != digest["sha1"]:
        raise DevArtifactError("npm pack digests do not match the exact tarball")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    tarball = OUTPUT / "package.tgz"
    tarball.write_bytes(content)
    smoke_env = {
        **os.environ,
        "PACKAGE_TARBALL": str(tarball),
        "OPENCODE_BINARY": build_release_artifacts.command("mise", "which", "opencode").strip(),
    }
    build_release_artifacts.command("node", "test/smoke.mjs", cwd=PACKAGE, env=smoke_env)

    manifest = {
        "schema": "@kisev/skills-dev/v1",
        "channel": "dev",
        "version": version,
        "revision": revision,
        "npm": {
            "name": name,
            "filename": tarball.name,
            "size": len(content),
            **digest,
        },
        "pages": {"files": build_release_artifacts.page_hashes()},
    }
    (OUTPUT / "release.json").write_bytes(build_release_artifacts.canonical(manifest))
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
