#!/usr/bin/env python3
"""Build the immutable npm artifact and cross-channel release manifest."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "opencode"
PAGES = ROOT / ".build" / "packages" / "skills"
OUTPUT = ROOT / ".build" / "release"
ALLOWED_PACKAGE_FILES = {"README.md", "README.ru.md", "package.json"}


class ArtifactError(Exception):
    """Release artifact construction failed closed."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def command(*arguments: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(arguments), cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ArtifactError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result.stdout


def hashes(content: bytes) -> dict[str, str]:
    sha512 = hashlib.sha512(content).digest()
    return {
        "sha1": hashlib.sha1(content, usedforsecurity=False).hexdigest(),
        "sha512": hashlib.sha512(content).hexdigest(),
        "integrity": f"sha512-{base64.b64encode(sha512).decode('ascii')}",
    }


def page_hashes() -> dict[str, str]:
    if not PAGES.is_dir():
        raise ArtifactError("Pages distribution is missing")
    result: dict[str, str] = {}
    for path in sorted(PAGES.rglob("*")):
        if path.is_symlink():
            raise ArtifactError(f"Pages artifact contains a symlink: {path.relative_to(PAGES)}")
        if path.is_file():
            result[path.relative_to(PAGES).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    required = {"index.json", ".well-known/agent-skills/index.json"}
    if not result or not required <= result.keys():
        raise ArtifactError("Pages artifact inventory is incomplete")
    return result


def pack() -> tuple[bytes, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="skills-release-pack-") as temporary:
        output = command(
            "npm",
            "pack",
            "--ignore-scripts",
            "--json",
            "--pack-destination",
            temporary,
            cwd=PACKAGE,
        )
        try:
            records = json.loads(output)
        except json.JSONDecodeError as error:
            raise ArtifactError("npm pack returned invalid JSON") from error
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise ArtifactError("npm pack returned an invalid record")
        record = records[0]
        files = record.get("files")
        if not isinstance(files, list):
            raise ArtifactError("npm pack did not report its files")
        paths: list[str] = []
        for item in files:
            path = item.get("path") if isinstance(item, dict) else None
            if not isinstance(path, str):
                raise ArtifactError("npm pack returned an invalid file record")
            paths.append(path)
        paths.sort()
        if not all(path in ALLOWED_PACKAGE_FILES or path.startswith("dist/") for path in paths):
            raise ArtifactError("npm package contains an unexpected file")
        if not set(paths) >= ALLOWED_PACKAGE_FILES or not any(
            path.startswith("dist/") for path in paths
        ):
            raise ArtifactError("npm package allowlist is incomplete")
        filename = record.get("filename")
        if not isinstance(filename, str):
            raise ArtifactError("npm pack filename is missing")
        return (Path(temporary) / filename).read_bytes(), record


def build(tag: str, revision: str) -> dict[str, Any]:
    package = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    name, version = package.get("name"), package.get("version")
    if not isinstance(name, str) or not isinstance(version, str) or tag != f"v{version}":
        raise ArtifactError("release tag and npm package version differ")
    actual_revision = command("git", "rev-parse", "HEAD").strip()
    if revision != actual_revision:
        raise ArtifactError("release revision does not match HEAD")

    content, record = pack()
    digest = hashes(content)
    if record.get("integrity") != digest["integrity"] or record.get("shasum") != digest["sha1"]:
        raise ArtifactError("npm pack digests do not match the exact tarball")

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    tarball = OUTPUT / "package.tgz"
    tarball.write_bytes(content)
    smoke_env = {
        **os.environ,
        "PACKAGE_TARBALL": str(tarball),
        "OPENCODE_BINARY": command("mise", "which", "opencode").strip(),
    }
    command("node", "test/smoke.mjs", cwd=PACKAGE, env=smoke_env)

    manifest = {
        "schema": "@kisev/skills-release/v1",
        "tag": tag,
        "version": version,
        "revision": revision,
        "npm": {
            "name": name,
            "filename": tarball.name,
            "size": len(content),
            **digest,
        },
        "pages": {"files": page_hashes()},
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
