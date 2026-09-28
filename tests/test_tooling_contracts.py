from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hooks_keep_precommit_fast_and_prepush_complete() -> None:
    hooks = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
    assert "--diff-filter=ACMR" in hooks
    assert "--staged" in hooks
    assert "        task pre-push" in hooks
    assert "commitlint --edit {1}" in hooks
    assert "--fix" not in hooks
    assert "git add" not in hooks
    assert "mise exec -- editorconfig-checker" in hooks
    assert "mise exec -- ec" not in hooks
    for slow_check in ("pytest", "mypy", "build:skills", "version:check", "package:check"):
        assert slow_check not in hooks


def test_prepush_git_environment_does_not_escape_into_fixture_repositories(tmp_path: Path) -> None:
    hooks = (ROOT / "lefthook.yml").read_text(encoding="utf-8")
    command = textwrap.dedent(
        hooks.split("pre-push:\n", 1)[1].split("run: |\n", 1)[1].split("      fail_text:", 1)[0]
    )
    local_variables = subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], cwd=ROOT, text=True
    ).splitlines()
    environment = {key: value for key, value in os.environ.items() if key not in local_variables}
    repositories = [tmp_path / "hook", tmp_path / "fixture"]
    for repository in repositories:
        subprocess.run(["git", "init", "-q", str(repository)], env=environment, check=True)
    binary = tmp_path / "task"
    binary.write_text(
        '#!/bin/sh\n[ "$1" = pre-push ] || exit 1\n'
        'git -C "$VERIFY_REPO" rev-parse --absolute-git-dir\n',
        encoding="utf-8",
    )
    binary.chmod(0o700)
    environment.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{environment.get('PATH', '')}",
            "VERIFY_REPO": str(repositories[1]),
            "GIT_DIR": str(repositories[0] / ".git"),
            "GIT_WORK_TREE": str(repositories[0]),
            "GIT_INDEX_FILE": str(repositories[0] / ".git" / "index"),
        }
    )
    result = subprocess.run(
        ["sh", "-eu", "-c", command],
        cwd=repositories[0],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == str(repositories[1] / ".git")


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
    # CI artifacts do not preserve file modes, so every built-quality job
    # materializes `.build/skills` itself; byte-identical rebuilds are enforced
    # by distribution:check.
    assert "actions/upload-artifact@" not in ci
    assert "actions/download-artifact@" not in ci
    quality_job = ci[ci.index("  quality:") : ci.index("  built-quality:")]
    built_quality_job = ci[ci.index("  built-quality:") : ci.index("  check:")]
    assert "task: eval:check" not in quality_job
    assert "task: eval:check" in built_quality_job
    assert "task build:skills" in built_quality_job
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
        "apps/taskmatic",
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
    assert "mise exec -- npm --prefix ../../apps/taskmatic test" in taskfile
    assert "mise exec -- npm --prefix ../../apps/taskmatic run pack:check" in taskfile
    for consumer in ("memomatic", "taskmatic", "agentomatic"):
        assert taskfile.index(f"{build_cmd}{consumer}") > safe_fs_pos, (
            f"{consumer} must build after safe-fs"
        )


def test_every_workspace_package_is_wired_into_the_publication_graph() -> None:
    root = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    surfaces = {
        "taskfile.yml": (ROOT / "taskfile.yml").read_text(encoding="utf-8"),
        "scripts/build_dev_artifacts.py": (ROOT / "scripts/build_dev_artifacts.py").read_text(
            encoding="utf-8"
        ),
        "scripts/build_release_artifacts.py": (
            ROOT / "scripts/build_release_artifacts.py"
        ).read_text(encoding="utf-8"),
        "scripts/publish_npm_release.py": (ROOT / "scripts/publish_npm_release.py").read_text(
            encoding="utf-8"
        ),
        "packages/agentomatic/test/smoke.mjs": (
            ROOT / "packages/agentomatic/test/smoke.mjs"
        ).read_text(encoding="utf-8"),
    }
    for workspace in root["workspaces"]:
        name = json.loads((ROOT / workspace / "package.json").read_text(encoding="utf-8"))["name"]
        for surface, content in surfaces.items():
            assert name in content, (
                f"{name} from {workspace} is missing from {surface}; every workspace"
                " package must be wired into the complete publication graph, see"
                " docs/how-to/npm-package-lifecycle.md"
            )
    distribution = (ROOT / "scripts/build_distribution.py").read_text(encoding="utf-8")
    assert "build_skills(BUILT_SKILLS" not in distribution
