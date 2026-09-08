#!/usr/bin/env python3
"""Build self-contained portable skills outside the authored source tree."""

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
    # Portable runners retain their canonical shared runtime without exposing the
    # authored shared tree as an installed dependency.
    runtime_targets = {
        "ast-grep": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
        ),
        "rtk": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
        ),
        "skill-improver": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
        ),
        "walkthrough": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
        ),
        "schedule": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
            "python_runtime/state.py",
        ),
        "usage": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
            "python_runtime/state.py",
        ),
        "overview": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
            "python_runtime/state.py",
            "python_runtime/lsp.py",
        ),
        "lsp-report": (
            "python_runtime/__init__.py",
            "python_runtime/capabilities.py",
            "python_runtime/contract.py",
            "python_runtime/lsp.py",
        ),
    }
    for skill, paths in runtime_targets.items():
        for relative in paths:
            source = SHARED / "references" / relative
            destination = Path(skill) / "scripts" / "portable_runtime" / Path(relative).name
            if destination not in destinations:
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


def build(output: Path, check: bool) -> int:
    entries = manifest_entries()
    if output.is_symlink():
        raise BuildError("output must not be a symbolic link")
    stage_parent = output.parent
    stage_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skills-build-", dir=stage_parent) as temporary:
        staged = Path(temporary) / "skills"
        copy_source(staged)
        for source, destination in entries:
            target = staged / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise BuildError(f"materialized target is a symbolic link: {destination}")
            shutil.copyfile(source, target)
            target.chmod(stat.S_IMODE(source.stat().st_mode))
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
    args = parser.parse_args(argv)
    try:
        return build(args.output.resolve(), args.check)
    except BuildError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
