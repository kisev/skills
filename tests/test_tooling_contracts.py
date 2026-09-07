from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_precommit() -> Any:
    spec = importlib.util.spec_from_file_location("precommit", ROOT / "scripts" / "precommit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_precommit_selects_checks_by_staged_paths() -> None:
    groups = _load_precommit().classify(
        [
            "README.md",
            "packages/opencode/assets/migration-inventory.json",
            "packages/opencode/src/index.ts",
            "tests/test_repository.py",
            "skills/askme/SKILL.md",
            "shared/manifest.json",
            "lefthook.yml",
        ]
    )
    assert groups["docs"] == ["README.md", "skills/askme/SKILL.md"]
    assert groups["data"] == [
        "packages/opencode/assets/migration-inventory.json",
        "shared/manifest.json",
    ]
    assert groups["python"] == ["tests/test_repository.py"]
    assert groups["python_tests"] == ["tests/test_repository.py"]
    assert groups["skills"] == ["shared/manifest.json", "skills/askme/SKILL.md"]
    assert groups["package"] == [
        "packages/opencode/assets/migration-inventory.json",
        "packages/opencode/src/index.ts",
    ]
    assert groups["workflow"] == ["lefthook.yml"]


def test_precommit_skips_package_for_docs_only_change() -> None:
    groups = _load_precommit().classify(["CONTRIBUTING.md"])
    assert groups["docs"] == ["CONTRIBUTING.md"]
    assert groups["package"] == []
    assert groups["python"] == []
    assert groups["workflow"] == []


def test_precommit_matches_root_level_and_nested_files() -> None:
    groups = _load_precommit().classify(["top.json", "skills/usage/scripts/usage.py"])
    assert groups["data"] == ["top.json"]
    assert groups["python"] == ["skills/usage/scripts/usage.py"]
    assert groups["skills"] == ["skills/usage/scripts/usage.py"]
