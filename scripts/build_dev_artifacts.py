#!/usr/bin/env python3
"""Build the exact npm artifact and manifest for one development snapshot."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_distribution, build_release_artifacts  # noqa: E402

MEMOMATIC = ROOT / "apps" / "memomatic"
SAFE_FS = ROOT / "packages" / "safe-fs"
PACKAGE = ROOT / "packages" / "agentomatic"
OUTPUT = ROOT / ".build" / "release"


class DevArtifactError(Exception):
    pass


def pack(source: Path, version: str, prefixes: tuple[str, ...]) -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="skills-dev-pack-") as temporary:
        staged = Path(temporary) / "package"
        staged.mkdir()
        for name in ("README.md", "README.ru.md", "package.json"):
            shutil.copyfile(source / name, staged / name)
        shutil.copytree(source / "dist", staged / "dist")
        if "assets/" in prefixes:
            shutil.copytree(source / "assets", staged / "assets")
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
            path in build_release_artifacts.PACKAGE_MEMBERS[0].allowed or path.startswith(prefixes)
            for path in normalized_paths
        ):
            raise DevArtifactError("npm package contains an unexpected file")
        if record.get("version") != version:
            raise DevArtifactError("npm pack version differs from the development version")
        filename = record.get("filename")
        if not isinstance(filename, str):
            raise DevArtifactError("npm pack filename is missing")
        return (Path(temporary) / filename).read_bytes(), record


def member_dev_version(base: str, version: str) -> str:
    match = re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-dev\.([0-9]+)\.g([0-9a-f]+)", version)
    if not match:
        raise DevArtifactError("development version is invalid")
    return f"{base}-dev.{match.group(1)}.g{match.group(2)}"


def build(version: str, revision: str) -> dict[str, Any]:
    if not build_distribution.DEV_SEMVER.fullmatch(version):
        raise DevArtifactError("development version is invalid")
    actual_revision = build_release_artifacts.command("git", "rev-parse", "HEAD").strip()
    if revision != actual_revision:
        raise DevArtifactError("development revision does not match HEAD")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    members = (
        (SAFE_FS, "safe-fs.tgz", ("dist/",)),
        (MEMOMATIC, "memomatic.tgz", ("dist/", "assets/")),
        (PACKAGE, "package.tgz", ("dist/",)),
    )
    npm_entries: list[dict[str, Any]] = []
    tarballs: dict[str, Path] = {}
    for source, filename, prefixes in members:
        package = json.loads((source / "package.json").read_text(encoding="utf-8"))
        name, base = package.get("name"), package.get("version")
        if not isinstance(name, str) or not isinstance(base, str) or not base:
            raise DevArtifactError("npm package name or version is invalid")
        member_version = version if source == PACKAGE else member_dev_version(base, version)
        content, record = pack(source, member_version, prefixes)
        digest = build_release_artifacts.hashes(content)
        if record.get("integrity") != digest["integrity"] or record.get("shasum") != digest["sha1"]:
            raise DevArtifactError("npm pack digests do not match the exact tarball")
        tarball = OUTPUT / filename
        tarball.write_bytes(content)
        tarballs[name] = tarball
        npm_entries.append(
            {
                "name": name,
                "version": member_version,
                "filename": filename,
                "size": len(content),
                **digest,
            }
        )

    smoke_env = {
        **os.environ,
        "AGENTOMATIC_TARBALL": str(tarballs["@kisev/agentomatic"]),
        "MEMOMATIC_TARBALL": str(tarballs["@kisev/memomatic"]),
        "SAFE_FS_TARBALL": str(tarballs["@kisev/safe-fs"]),
        "OPENCODE_BINARY": build_release_artifacts.command("mise", "which", "opencode").strip(),
    }
    build_release_artifacts.command(
        "node",
        "test/smoke.mjs",
        cwd=PACKAGE,
        env=smoke_env,
    )

    manifest = {
        "schema": "@kisev/skills-dev/v2",
        "channel": "dev",
        "version": version,
        "revision": revision,
        "npm": npm_entries,
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
