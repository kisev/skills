#!/usr/bin/env python3
"""Run only the non-mutating quality checks relevant to staged files.

The Git pre-commit hook delegates here through ``task pre-commit``. Checks are
selected from staged paths so a docs-only change never starts the OpenCode
package lifecycle and a package change does not re-run the full Python matrix.
The authoritative ``task check`` (and CI) still runs every gate unchanged.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SOURCE_DIRS = ("assets", "scripts", "src", "test")
PACKAGE_METADATA = frozenset(
    {
        "packages/opencode/package.json",
        "packages/opencode/package-lock.json",
        "packages/opencode/tsconfig.json",
    }
)
WORKFLOW_FILES = frozenset({"lefthook.yml", "taskfile.yml", ".yamllint.yml"})
PYTHON_ROOTS = ("scripts", "shared", "skills", "tests")


def _posix(path: str) -> str:
    return PurePosixPath(path).as_posix()


def staged_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACM",
            "-z",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(_posix(value) for value in result.stdout.decode("utf-8").split("\0") if value)


def classify(files: Iterable[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "docs": [],
        "data": [],
        "python": [],
        "python_tests": [],
        "skills": [],
        "package": [],
        "workflow": [],
    }
    for value in files:
        path = _posix(value)
        parts = PurePosixPath(path).parts
        root = parts[0] if parts else ""
        if path.endswith(".md"):
            groups["docs"].append(path)
        if path.endswith(".json"):
            groups["data"].append(path)
        if root in PYTHON_ROOTS and path.endswith(".py"):
            groups["python"].append(path)
            if root == "tests":
                groups["python_tests"].append(path)
        if root in ("skills", "shared"):
            groups["skills"].append(path)
        if path in PACKAGE_METADATA or (
            root == "packages"
            and len(parts) > 2
            and parts[1] == "opencode"
            and parts[2] in PACKAGE_SOURCE_DIRS
        ):
            groups["package"].append(path)
        if (root == ".github" and path.endswith((".yml", ".yaml"))) or path in WORKFLOW_FILES:
            groups["workflow"].append(path)
    return {name: sorted(paths) for name, paths in groups.items()}


def _resolve_skills_binary() -> str | None:
    try:
        result = subprocess.run(
            ["mise", "which", "skills"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


class _Runner:
    def __init__(self, *, dry_run: bool, env: dict[str, str]) -> None:
        self.dry_run = dry_run
        self.env = env
        self.failures = 0

    def call(self, label: str, argv: Sequence[str | os.PathLike[str]]) -> None:
        command = [str(part) for part in argv]
        if self.dry_run:
            print(f"[{label}] {' '.join(command)}")
            return
        print(f"[{label}] running", file=sys.stderr)
        if subprocess.run(command, cwd=ROOT, env=self.env).returncode != 0:
            self.failures += 1
            print(f"[{label}] FAILED", file=sys.stderr)

    def batch(self, label: str, prefix: Sequence[str], files: Sequence[str]) -> None:
        if files:
            self.call(label, [*prefix, *files])


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    binary = _resolve_skills_binary()
    if binary:
        env["SKILLS_BINARY"] = binary
    return env


def run(files: Sequence[str], *, dry_run: bool = False) -> int:
    groups = classify(files)
    runner = _Runner(dry_run=dry_run, env=_base_env())
    runner.batch("docs", ["prettier", "--check"], groups["docs"])
    runner.batch("data", ["jq", "empty"], groups["data"])
    runner.batch(
        "python:format",
        ["uv", "run", "--locked", "ruff", "format", "--check", "--force-exclude"],
        groups["python"],
    )
    runner.batch(
        "python:lint",
        ["uv", "run", "--locked", "ruff", "check", "--force-exclude"],
        groups["python"],
    )
    if groups["python_tests"]:
        runner.batch("python:tests", ["uv", "run", "--locked", "pytest"], groups["python_tests"])
    if groups["skills"]:
        runner.call("skills:agnix", ["uv", "run", "--locked", "python", "scripts/check_agnix.py"])
        runner.call(
            "skills:materialize",
            ["uv", "run", "--locked", "python", "scripts/build_skills.py", "--check"],
        )
        runner.call(
            "skills:tests",
            ["uv", "run", "--locked", "pytest", "tests/test_skill_contracts.py"],
        )
    if groups["package"]:
        runner.call("package", ["task", "package:check"])
    if groups["workflow"]:
        runner.batch("workflow:yaml", ["uv", "run", "--locked", "yamllint"], groups["workflow"])
        runner.call("workflow:actionlint", ["actionlint"])
        runner.call("workflow:lefthook", ["lefthook", "validate"])
    return 1 if runner.failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print selected commands only")
    parser.add_argument("files", nargs="*", help="override staged files")
    args = parser.parse_args(argv)
    files = args.files or staged_files()
    return run(files, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
