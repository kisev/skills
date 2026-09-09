#!/usr/bin/env python3
"""Materialize and verify self-contained portable skills."""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
SOURCES = ROOT / "skills"
MANIFEST = SHARED / "manifest.json"
DEFAULT_OUTPUT = ROOT / ".build" / "skills"


class BuildError(Exception):
    """A build input or path safety error."""


def safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise BuildError(f"{label} must be a non-empty POSIX relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BuildError(f"unsafe {label}: {value!r}")
    return path


def manifest_entries() -> list[tuple[Path, Path]]:
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot read manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise BuildError("manifest version must be 1")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BuildError("manifest files must be a list")
    entries: list[tuple[Path, Path]] = []
    destinations: set[Path] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise BuildError("manifest entries must be objects")
        source = SHARED / safe_relative(entry.get("source"), "source")
        destination = safe_relative(entry.get("destination"), "destination")
        if destination in destinations:
            raise BuildError(f"duplicate destination: {destination}")
        destinations.add(destination)
        if source.is_symlink() or not source.is_file():
            raise BuildError(f"source is not a regular file: {source}")
        try:
            source.resolve().relative_to((SHARED / "references").resolve())
        except ValueError as error:
            raise BuildError("sources must be inside shared/references") from error
        entries.append((source, destination))
    policy_skills = manifest.get("language_policy_skills", [])
    if not isinstance(policy_skills, list) or not all(
        isinstance(name, str) for name in policy_skills
    ):
        raise BuildError("language_policy_skills must be a list of skill names")
    for name in policy_skills:
        source = SHARED / "references" / "language-policy.md"
        destination = Path(name) / "references" / "language-policy.md"
        if destination in destinations:
            raise BuildError(f"duplicate destination: {destination}")
        destinations.add(destination)
        entries.append((source, destination))
    return entries


def copy_source(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        SOURCES,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "ru", "en"),
    )


def check_materialized(root: Path, entries: list[tuple[Path, Path]]) -> None:
    """Verify committed copies without modifying the authored source tree."""
    if root.is_symlink() or not root.is_dir():
        raise BuildError(f"materialization root is not a directory: {root}")
    expected: set[Path] = set()
    canonical_bytes = {source.read_bytes() for source, _ in entries}
    for source, relative in entries:
        expected.add(relative)
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise BuildError(f"missing or symbolic generated copy: {relative}")
        if target.read_bytes() != source.read_bytes():
            raise BuildError(f"generated copy drift: {relative}")
        if stat.S_IMODE(target.stat().st_mode) != stat.S_IMODE(source.stat().st_mode):
            raise BuildError(f"generated copy mode drift: {relative}")
    for skill in root.iterdir():
        if not skill.is_dir() or skill.is_symlink():
            continue
        for path in skill.rglob("*"):
            if path.is_symlink():
                raise BuildError(f"symbolic link in skill source: {path.relative_to(root)}")
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if relative in expected:
                continue
            # The manifest owns only paths whose source lives in shared/references.
            # Authored unique skill files are intentionally outside this check.
            if path.read_bytes() in canonical_bytes and path.name != "SKILL.md":
                raise BuildError(f"undeclared generated copy: {relative}")


def materialize(entries: list[tuple[Path, Path]]) -> int:
    for source, relative in entries:
        target = SOURCES / relative
        if target.is_symlink():
            raise BuildError(f"generated target is a symbolic link: {relative}")
        if any(parent.is_symlink() for parent in target.parents if parent != SOURCES):
            raise BuildError(f"generated target parent is a symbolic link: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(stat.S_IMODE(source.stat().st_mode))
    check_materialized(SOURCES, entries)
    print(f"materialized {len(entries)} shared copies in {SOURCES}")
    return 0


def build(output: Path, check: bool) -> int:
    entries = manifest_entries()
    check_materialized(SOURCES, entries)
    if output.is_symlink():
        raise BuildError("output must not be a symbolic link")
    stage_parent = output.parent
    if not check:
        stage_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="skills-build-", dir=None if check else stage_parent
    ) as temporary:
        staged = Path(temporary) / "skills"
        copy_source(staged)
        if check:
            if not output.is_dir():
                print(
                    f"validated {len(entries)} portable materialization(s) in an isolated staging area"
                )
                return 0
            for source in staged.rglob("*"):
                if (
                    source.is_file()
                    and not source.is_symlink()
                    and "__pycache__" not in source.parts
                ):
                    relative = source.relative_to(staged)
                    target = output / relative
                    if (
                        not target.is_file()
                        or target.is_symlink()
                        or target.read_bytes() != source.read_bytes()
                        or stat.S_IMODE(target.stat().st_mode)
                        != stat.S_IMODE(source.stat().st_mode)
                    ):
                        raise BuildError(f"build artifact drift: {relative}")
            for target in output.rglob("*"):
                if (
                    target.is_file()
                    and not target.is_symlink()
                    and "__pycache__" not in target.parts
                    and not (staged / target.relative_to(output)).is_file()
                ):
                    raise BuildError(f"unexpected build artifact: {target.relative_to(output)}")
            print(f"checked {len(entries)} portable materialization(s)")
            return 0
        if output.exists():
            shutil.rmtree(output)
        shutil.move(str(staged), output)
    print(f"built {len(entries)} portable materialization(s) at {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="materialize declared shared copies into skills/",
    )
    args = parser.parse_args(argv)
    try:
        if args.generate:
            return materialize(manifest_entries())
        return build(args.output.resolve(), args.check)
    except BuildError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
