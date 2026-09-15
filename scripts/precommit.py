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
PACKAGE_SOURCE_DIRS = ("assets", "contracts", "scripts", "src", "test")
PACKAGE_METADATA = frozenset(
    {
        "packages/opencode/package.json",
        "packages/opencode/package-lock.json",
        "packages/opencode/tsconfig.json",
    }
)
WORKFLOW_FILES = frozenset({"lefthook.yml", "taskfile.yml", ".yamllint.yml"})
PYTHON_ROOTS = ("scripts", "shared", "skills", "tests")
TOOLCHAIN_FILES = frozenset({"mise.toml", "pyproject.toml", "tombi.toml", "uv.lock"})
FORMAT_CONFIG_FILES = frozenset({".markdownlint-cli2.mjs", ".prettierignore", ".prettierrc.json"})
MARKDOWNLINT_CONFIG_FILES = frozenset({".markdownlint-cli2.mjs"})
GIT_LOCAL_ENV_VARS = frozenset(
    {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_DIR",
        "GIT_GRAFT_FILE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_INTERNAL_SUPER_PREFIX",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_PREFIX",
        "GIT_REPLACE_REF_BASE",
        "GIT_SHALLOW_FILE",
        "GIT_WORK_TREE",
    }
)


def _posix(path: str) -> str:
    return PurePosixPath(path).as_posix()


def _clean_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key not in GIT_LOCAL_ENV_VARS}


def staged_files(diff_filter: str = "ACMT") -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "diff",
            "--cached",
            "--name-only",
            f"--diff-filter={diff_filter}",
            "--no-renames",
            "-z",
        ],
        cwd=ROOT,
        env=_clean_git_env(),
        check=True,
        capture_output=True,
    )
    return sorted(_posix(value) for value in result.stdout.decode("utf-8").split("\0") if value)


def classify(files: Iterable[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "docs": [],
        "data": [],
        "format_config": [],
        "markdownlint_config": [],
        "python": [],
        "python_tests": [],
        "skills": [],
        "package": [],
        "schemas": [],
        "specs": [],
        "toolchain": [],
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
        if path in FORMAT_CONFIG_FILES:
            groups["format_config"].append(path)
        if path in MARKDOWNLINT_CONFIG_FILES:
            groups["markdownlint_config"].append(path)
        if root in PYTHON_ROOTS and path.endswith(".py"):
            groups["python"].append(path)
            if root == "tests" or "tests" in parts:
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
        if path.endswith(".schema.json"):
            groups["schemas"].append(path)
        if root == "specs":
            groups["specs"].append(path)
        if path in TOOLCHAIN_FILES:
            groups["toolchain"].append(path)
        if (root == ".github" and path.endswith((".yml", ".yaml"))) or path in WORKFLOW_FILES:
            groups["workflow"].append(path)
    return {name: sorted(paths) for name, paths in groups.items()}


def _resolve_skills_binary(env: dict[str, str]) -> str | None:
    try:
        result = subprocess.run(
            ["mise", "which", "skills"],
            cwd=ROOT,
            env=env,
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
    env = _clean_git_env()
    binary = _resolve_skills_binary(env)
    if binary:
        env["SKILLS_BINARY"] = binary
    return env


def run(files: Sequence[str], *, deleted_files: Sequence[str] = (), dry_run: bool = False) -> int:
    groups = classify(files)
    all_files = sorted(set(files) | set(deleted_files))
    all_groups = classify(all_files)
    runner = _Runner(dry_run=dry_run, env=_base_env())
    if all_files:
        runner.call("versions", ["task", "version:check"])
    if any(
        path.startswith(("skills/", "shared/", "packages/opencode/", "packages/skills/", "specs/"))
        for path in all_files
    ):
        runner.call("spec:check", ["uv", "run", "--locked", "python", "scripts/check_specs.py"])
    runner.batch("docs", ["prettier", "--check"], groups["docs"])
    runner.batch("data", ["jq", "empty"], groups["data"])
    if all_groups["format_config"]:
        runner.call("format:check", ["task", "format:check"])
    if all_groups["markdownlint_config"]:
        runner.call("markdownlint", ["markdownlint-cli2"])
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
    if any(path in deleted_files for path in all_groups["python_tests"]):
        runner.call("python:tests", ["uv", "run", "--locked", "pytest"])
    elif groups["python_tests"]:
        runner.batch("python:tests", ["uv", "run", "--locked", "pytest"], groups["python_tests"])
    if all_groups["schemas"]:
        runner.call(
            "schemas",
            ["uv", "run", "--locked", "pytest", "tests/test_json_schemas.py"],
        )
    if all_groups["skills"] or all_groups["docs"]:
        runner.call("locales", ["uv", "run", "--locked", "python", "scripts/check_locales.py"])
    if all_groups["skills"]:
        runner.call(
            "skills:build",
            ["uv", "run", "--locked", "python", "scripts/build_skills.py"],
        )
        runner.call("skills:agnix", ["uv", "run", "--locked", "python", "scripts/check_agnix.py"])
        runner.call(
            "skills:build-check",
            ["uv", "run", "--locked", "python", "scripts/build_skills.py", "--check"],
        )
        runner.call(
            "skills:tests",
            ["uv", "run", "--locked", "pytest", "tests/test_skill_contracts.py"],
        )
    if all_groups["package"]:
        runner.call("package", ["task", "package:check"])
    if any(path in {"pyproject.toml", "uv.lock"} for path in all_files):
        runner.call("python:lock", ["uv", "lock", "--check"])
    if any(path.endswith(".toml") for path in all_groups["toolchain"]):
        runner.call(
            "toolchain:toml-format",
            [
                "tombi",
                "format",
                "--offline",
                "--check",
                "mise.toml",
                "pyproject.toml",
                "tombi.toml",
            ],
        )
        runner.call(
            "toolchain:toml-lint",
            ["tombi", "lint", "--offline", "mise.toml", "pyproject.toml", "tombi.toml"],
        )
    if "mise.toml" in all_files:
        runner.call("toolchain:mise", ["mise", "ls", "--current", "--local"])
    if all_groups["workflow"]:
        runner.batch("workflow:yaml", ["uv", "run", "--locked", "yamllint"], groups["workflow"])
        runner.call("workflow:actionlint", ["actionlint"])
        runner.call("workflow:lefthook", ["lefthook", "validate"])
    return 1 if runner.failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print selected commands only")
    parser.add_argument("files", nargs="*", help="override staged files")
    args = parser.parse_args(argv)
    if args.files:
        files, deleted = args.files, []
    else:
        files, deleted = staged_files(), staged_files("D")
    return run(files, deleted_files=deleted, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
