#!/usr/bin/env python3
"""Materialize shared maintainer sources into portable skills."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
SHARED_REFERENCES = SHARED / "references"
SKILLS = ROOT / "skills"
MANIFEST = SHARED / "manifest.json"


class SyncError(Exception):
    """A manifest or filesystem safety error."""


def safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SyncError(f"{label} must be a non-empty relative path")
    if "\\" in value:
        raise SyncError(f"{label} must use POSIX separators")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SyncError(f"unsafe {label}: {value!r}")
    return path


def confined(root: Path, relative: Path, label: str) -> Path:
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise SyncError(f"{label} escapes its allowed root") from error
    return candidate


def reject_symlink(path: Path, root: Path, label: str) -> None:
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise SyncError(f"symlink is not allowed for {label}: {current}")


def load_manifest() -> list[tuple[Path, Path]]:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"cannot read manifest: {error}") from error
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SyncError("manifest version must be 1")
    entries = data.get("files")
    if not isinstance(entries, list):
        raise SyncError("manifest files must be a list")

    result: list[tuple[Path, Path]] = []
    destinations: set[Path] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SyncError("manifest entries must be objects")
        source_rel = safe_relative(entry.get("source"), "source")
        destination_rel = safe_relative(entry.get("destination"), "destination")
        source_raw = SHARED / source_rel
        destination_raw = SKILLS / destination_rel
        reject_symlink(source_raw, SHARED, "source")
        reject_symlink(destination_raw, SKILLS, "destination")
        source = confined(SHARED, source_rel, "source")
        destination = confined(SKILLS, destination_rel, "destination")
        if not source.is_relative_to(SHARED_REFERENCES.resolve()):
            raise SyncError("sources must be inside shared/references")
        if destination_rel.parts[0] not in {
            path.name for path in SKILLS.iterdir() if path.is_dir()
        }:
            raise SyncError("destinations must be inside an existing skill")
        if destination in destinations:
            raise SyncError(f"duplicate destination: {destination_rel}")
        destinations.add(destination)
        if not source.is_file():
            raise SyncError(f"source is not a regular file: {source_rel}")
        result.append((source, destination))
    result.sort(key=lambda pair: pair[1].relative_to(SKILLS).as_posix())
    return result


def materialize(entries: list[tuple[Path, Path]], check: bool) -> int:
    drift: list[str] = []
    payload: list[tuple[Path, bytes]] = []
    for source, destination in entries:
        source_bytes = source.read_bytes()
        payload.append((destination, source_bytes))
        if not destination.is_file() or destination.read_bytes() != source_bytes:
            drift.append(str(destination.relative_to(ROOT)))
    if check:
        if drift:
            print("drift detected:\n" + "\n".join(drift), file=sys.stderr)
            return 1
        print(f"checked {len(entries)} materialized file(s)")
        return 0
    if not payload:
        print("nothing to materialize")
        return 0

    stage = Path(tempfile.mkdtemp(prefix="sync-shared-", dir=ROOT))
    backups: list[tuple[Path, Path | None]] = []
    try:
        for index, (destination, content) in enumerate(payload):
            staged = stage / str(index)
            staged.write_bytes(content)
        for index, (destination, _) in enumerate(payload):
            staged = stage / str(index)
            destination.parent.mkdir(parents=True, exist_ok=True)
            backup: Path | None = None
            if destination.exists():
                backup = stage / f"backup-{index}"
                os.replace(destination, backup)
            backups.append((destination, backup))
            os.replace(staged, destination)
    except (OSError, ValueError) as error:
        for destination, backup in reversed(backups):
            try:
                if destination.exists():
                    destination.unlink()
                if backup is not None and backup.exists():
                    os.replace(backup, destination)
            except OSError:
                pass
        raise SyncError(f"materialization failed and was rolled back: {error}") from error
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print(f"materialized {len(payload)} file(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check drift without writing")
    args = parser.parse_args(argv)
    try:
        return materialize(load_manifest(), args.check)
    except SyncError as error:
        print(f"sync_shared: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
