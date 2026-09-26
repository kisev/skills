from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hooks_keep_precommit_fast_and_prepush_complete() -> None:
    hooks = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
    assert "--diff-filter=ACMR" in hooks
    assert "--staged" in hooks
    assert "run: task pre-push" in hooks
    assert "commitlint --edit {1}" in hooks
    assert "--fix" not in hooks
    assert "git add" not in hooks
    assert "mise exec -- editorconfig-checker" in hooks
    assert "mise exec -- ec" not in hooks
    for slow_check in ("pytest", "mypy", "build:skills", "version:check", "package:check"):
        assert slow_check not in hooks


def test_workflows_delegate_quality_checks_to_task() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    publish = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    live = (ROOT / ".github/workflows/evals-live.yml").read_text(encoding="utf-8")
    assert not (ROOT / ".github/workflows/pages.yml").exists()
    assert 'task "$CHECK_TASK"' in ci
    assert "task build:skills" in ci
    for task in (
        "version:check",
        "lint",
        "typecheck",
        "test:python",
        "locale:check",
        "distribution:check",
        "skills:validate",
        "eval:check",
        "package:check",
        "security",
    ):
        assert f"task: {task}" in ci
    assert "ci:" not in ci
    assert "name: built-skills" in ci
    assert "path: .build/skills" in ci
    assert "actions/upload-artifact@" in ci
    assert "actions/download-artifact@" in ci
    quality_job = ci[ci.index("  quality:") : ci.index("  built-quality:")]
    built_quality_job = ci[ci.index("  built-quality:") : ci.index("  check:")]
    assert "task: eval:check" not in quality_job
    assert "task: eval:check" in built_quality_job
    for task in ("release:prepare", "release:pages:verify", "release:npm", "release:github"):
        assert task in publish
    assert "fetch-depth: 0" in publish
    assert 'tags:\n      - "v*"' in publish
    assert "path: .build/pages" in publish
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
    assert "fetch-depth: 0" in ci
    for workflow in (ci, publish, live):
        for reference in re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow):
            assert re.fullmatch(r"[0-9a-f]{40}", reference)
    for duplicated in ("ruff ", "pytest", "npm ci", "npm test", "agentskills"):
        assert duplicated not in ci
        assert duplicated not in publish


def test_root_npm_workspace_is_private_exact_and_python_stays_detached() -> None:
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert set(root) == {"private", "workspaces"}
    assert root["private"] is True
    assert root["workspaces"] == [
        "apps/memomatic",
        "packages/agentomatic",
        "packages/safe-fs",
    ]
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in pyproject
    assert "skills-ref==0.1.1" in pyproject


def test_task_graph_builds_skills_once_before_consumers() -> None:
    taskfile = (ROOT / "taskfile.yml").read_text(encoding="utf-8")
    assert re.search(r"^  ci:", taskfile, flags=re.MULTILINE) is None
    assert "  build:skills:\n    desc: Materialize portable skills\n    run: once" in taskfile
    assert "  distribution:build:" in taskfile
    assert "    deps: [build:skills]" in taskfile
    assert "deps: [package:test]" in taskfile
    assert "package:quick-check:" not in taskfile
    assert "package:generate:check:" not in taskfile
    assert "generate:distribution:check:" not in taskfile
    assert "build:distribution:" not in taskfile
    assert "npm run format" not in taskfile
    assert "npm run lint" not in taskfile
    assert "npm run typecheck" not in taskfile
    assert "npm run generate-assets" not in taskfile
    for script in ("build", "smoke", "pack:check"):
        assert f"mise exec -- npm run {script}" in taskfile
    assert "mise exec -- npm test" in taskfile
    assert "mise exec -- gitleaks" in taskfile
    assert "mise exec -- uv" in taskfile
    assert "mise exec -- editorconfig-checker" in taskfile
    assert "mise exec -- ec" not in taskfile
    assert "      - task: build:skills\n      - task: version:check" in taskfile
    assert "deps: [check, dependency:audit]" in taskfile
    assert "  release:preflight:" in taskfile
    assert "task release:check -- --published" in taskfile
    build_cmd = "mise exec -- npm run build --workspace @kisev/"
    assert (
        "  typecheck:typescript:\n    desc: Check types in typescript\n"
        "    deps: [package:build]" in taskfile
    ), "typecheck must build workspace packages so clean checkouts resolve types"
    safe_fs_pos = taskfile.index(f"{build_cmd}safe-fs")
    for consumer in ("memomatic", "agentomatic"):
        assert taskfile.index(f"{build_cmd}{consumer}") > safe_fs_pos, (
            f"{consumer} must build after safe-fs"
        )
    distribution = (ROOT / "scripts/build_distribution.py").read_text(encoding="utf-8")
    assert "build_skills(BUILT_SKILLS" not in distribution
