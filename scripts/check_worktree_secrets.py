#!/usr/bin/env python3
"""Scan Git-eligible worktree bytes without copying ignored private runtime state."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot(root: Path, destination: Path) -> int:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],  # noqa: S607 - Repository Git prerequisite.
        cwd=root,
        capture_output=True,
        check=True,
    )
    count = 0
    for raw in sorted(set(result.stdout.split(b"\0")) - {b""}):
        relative = Path(os.fsdecode(raw))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Git inventory contains an unsafe path")
        if any((root / parent).is_symlink() for parent in relative.parents):
            continue
        source, target = root / relative, destination / relative
        if source.is_symlink():
            data = os.fsencode(os.readlink(source))
        elif source.is_file():
            data = source.read_bytes()
        else:
            # Deleted files are covered by the separate Git-history scan;
            # submodule gitlinks contain no worktree blob to scan here.
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        count += 1
    return count


def main() -> int:
    report = ROOT / ".build/gitleaks-worktree.json"
    report.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skills-source-scan-") as temporary:
        snapshot(ROOT, Path(temporary))
        result = subprocess.run(  # noqa: S603 - Fixed secret scanner with bounded snapshot/config paths.
            [  # noqa: S607 - Pinned Mise tool.
                "gitleaks",
                "dir",
                temporary,
                "--config",
                str(ROOT / ".gitleaks.toml"),
                "--redact",
                "--no-banner",
                "--report-format",
                "json",
                "--report-path",
                str(report),
            ],
            check=False,
        )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
