from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

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
    "distribution:build",
    "distribution:check",
    "release:check",
    "locale:check",
    "skills:validate",
    "package:check",
    "package:quick-check",
    "dependency:audit",
    "eval:live",
    "ci:portable",
    "ci:python",
    "ci:spec-impact",
    "ci:static",
    "release:github",
    "release:npm",
    "release:pages:verify",
    "release:prepare",
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
    live = (ROOT / ".github/workflows/evals-live.yml").read_text(encoding="utf-8")
    assert not (ROOT / ".github/workflows/pages.yml").exists()
    for task in ("ci:spec-impact", 'task "$CHECK_TASK"'):
        assert task in ci
    for task in ("release:prepare", "release:pages:verify", "release:npm", "release:github"):
        assert task in publish
    assert "fetch-depth: 0" in ci
    assert "fetch-depth: 0" in publish
    assert 'tags:\n      - "v*"' in publish
    assert "path: .build/packages/skills" in publish
    assert "include-hidden-files: true" in publish
    assert "pages: write" in publish
    assert "id-token: write" in publish
    assert "name: github-pages" in publish
    assert "deploy-pages" in publish
    assert "task eval:live" in live
    live_command = re.search(
        r"- name: Run explicitly trusted live suite\n\s+run: (?P<run>.+)", live
    )
    assert live_command is not None
    assert "${{ inputs." not in live_command.group("run")
    assert "github.event.deleted != true" in ci
    assert 'test "$DELETED_REF" = true' in ci
    for workflow in (ci, publish, live):
        for reference in re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow):
            assert re.fullmatch(r"[0-9a-f]{40}", reference)
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
            "skills/askme/SKILL.source.md",
            "shared/manifest.json",
            "lefthook.yml",
            "specs/README.md",
            "uv.lock",
            ".prettierignore",
            ".markdownlint-cli2.mjs",
            "packages/opencode/contracts/instances-v1.json",
        ]
    )
    assert groups["docs"] == ["README.md", "skills/askme/SKILL.source.md", "specs/README.md"]
    assert groups["data"] == [
        "packages/opencode/assets/migration-inventory.json",
        "packages/opencode/contracts/instances-v1.json",
        "shared/manifest.json",
    ]
    assert groups["python"] == ["tests/test_repository.py"]
    assert groups["python_tests"] == ["tests/test_repository.py"]
    assert groups["skills"] == ["shared/manifest.json", "skills/askme/SKILL.source.md"]
    assert groups["package"] == [
        "packages/opencode/assets/migration-inventory.json",
        "packages/opencode/contracts/instances-v1.json",
        "packages/opencode/src/index.ts",
    ]
    assert groups["workflow"] == ["lefthook.yml"]
    assert groups["specs"] == ["specs/README.md"]
    assert groups["toolchain"] == ["uv.lock"]
    assert groups["format_config"] == [".markdownlint-cli2.mjs", ".prettierignore"]
    assert groups["markdownlint_config"] == [".markdownlint-cli2.mjs"]


def test_precommit_skips_package_for_docs_only_change() -> None:
    groups = _load_precommit().classify(["CONTRIBUTING.md"])
    assert groups["docs"] == ["CONTRIBUTING.md"]
    assert groups["package"] == []
    assert groups["python"] == []
    assert groups["workflow"] == []


def test_precommit_uses_the_quick_package_gate(capsys: pytest.CaptureFixture[str]) -> None:
    result = _load_precommit().run(["packages/opencode/src/index.ts"], dry_run=True)
    output = capsys.readouterr().out
    assert result == 0
    assert "task package:quick-check" in output
    assert "task package:check" not in output


def test_prepush_parallelizes_the_complete_gate_and_dependency_audit() -> None:
    taskfile = (ROOT / "taskfile.yml").read_text(encoding="utf-8")
    assert "deps: [build:skills, package:quick-check]" in taskfile
    assert "deps: [check, dependency:audit]" in taskfile


def test_precommit_matches_root_level_and_nested_files() -> None:
    groups = _load_precommit().classify(
        [
            "top.json",
            "skills/lsp-report/scripts/lsp_report.py",
            "skills/mattermost/tests/test_mattermost.py",
            "evals/schemas/result-v1.schema.json",
            "packages/opencode/contracts/execution-card-v1.schema.json",
        ]
    )
    assert groups["data"] == [
        "evals/schemas/result-v1.schema.json",
        "packages/opencode/contracts/execution-card-v1.schema.json",
        "top.json",
    ]
    assert groups["python"] == [
        "skills/lsp-report/scripts/lsp_report.py",
        "skills/mattermost/tests/test_mattermost.py",
    ]
    assert groups["python_tests"] == ["skills/mattermost/tests/test_mattermost.py"]
    assert groups["skills"] == [
        "skills/lsp-report/scripts/lsp_report.py",
        "skills/mattermost/tests/test_mattermost.py",
    ]
    assert groups["schemas"] == [
        "evals/schemas/result-v1.schema.json",
        "packages/opencode/contracts/execution-card-v1.schema.json",
    ]
    assert groups["package"] == ["packages/opencode/contracts/execution-card-v1.schema.json"]


def test_precommit_deletions_trigger_broad_non_file_checks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _load_precommit().run(
        [],
        deleted_files=[
            "skills/mattermost/tests/test_mattermost.py",
            "specs/requirements/README.md",
            "evals/schemas/result-v1.schema.json",
            "tombi.toml",
            ".markdownlint-cli2.mjs",
        ],
        dry_run=True,
    )
    output = capsys.readouterr().out
    assert result == 0
    assert "task version:check" in output
    assert "scripts/check_specs.py" in output
    assert "pytest tests/test_json_schemas.py" in output
    assert "uv run --locked pytest" in output
    assert "test_mattermost.py" not in output
    assert "tombi format --offline --check" in output
    assert "markdownlint-cli2" in output


def test_precommit_removes_repository_local_git_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_precommit()
    for name in module.GIT_LOCAL_ENV_VARS:
        monkeypatch.setenv(name, f"poisoned-{name.lower()}")
    monkeypatch.setattr(module, "_resolve_skills_binary", lambda _env: None)

    env = module._base_env()
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, env=env, check=True)

    assert module.GIT_LOCAL_ENV_VARS.isdisjoint(env)
    assert (repository / ".git").is_dir()
    assert os.environ["GIT_DIR"] == "poisoned-git_dir"
