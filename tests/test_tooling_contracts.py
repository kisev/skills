from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_TASKS = {
    "tools",
    "format",
    "format:check",
    "lint",
    "typecheck",
    "test",
    "generate",
    "generate:check",
    "skills:validate",
    "package:check",
    "security",
    "check",
    "pre-commit",
    "pre-push",
}


def test_public_task_api_is_complete() -> None:
    taskfile = (ROOT / "taskfile.yml").read_text(encoding="utf-8")
    declared = set(re.findall(r"^  ([a-z][a-z:-]+):$", taskfile, flags=re.MULTILINE))
    assert PUBLIC_TASKS <= declared


def test_hooks_only_delegate_to_public_tasks() -> None:
    hooks = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
    assert "run: task pre-commit" in hooks
    assert "run: task pre-push" in hooks
    assert "--fix" not in hooks
    assert "git add" not in hooks


def test_workflows_delegate_quality_checks_to_task() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    publish = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert "run: task check" in ci
    assert "run: task package:check" in publish
    assert "fetch-depth: 0" in ci
    assert "fetch-depth: 0" in publish
    for duplicated in ("ruff ", "pytest", "npm ci", "npm test", "agentskills"):
        assert duplicated not in ci
        assert duplicated not in publish


def test_no_root_npm_workspace_or_runtime_python_dependencies() -> None:
    assert not (ROOT / "package.json").exists()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in pyproject
    assert "skills-ref==0.1.1" in pyproject
