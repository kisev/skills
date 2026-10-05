"""Worktree application regressions ported from the TypeScript worktree suite."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from reviewmatic import worktree
from reviewmatic.portable.portable_gitlab import contract


def git(root: Path, *arguments: str, check: bool = True, stdin: str | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        input=stdin,
        capture_output=True,
        text=True,
        check=check,
    )
    return completed.stdout


@pytest.fixture(name="state_home")
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home


@pytest.fixture(name="repo")
def plain_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "--initial-branch=main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    return root


def test_suggestion_to_patch_replaces_the_anchored_line(repo: Path) -> None:
    (repo / "src.txt").write_text("one\ntwo\nthree\n")
    git(repo, "add", "src.txt")
    git(repo, "commit", "-q", "-m", "init")
    head = git(repo, "rev-parse", "HEAD").strip()
    patch = worktree.suggestion_to_patch(
        str(repo), head, "src.txt", "src.txt", 2, None, "TWO\nTWO-B"
    )
    git(repo, "apply", "--check", "-", stdin=patch)
    git(repo, "apply", "-", stdin=patch)
    assert (repo / "src.txt").read_text() == "one\nTWO\nTWO-B\nthree\n"


def test_prepare_and_commit_application_run_in_a_dedicated_worktree(
    tmp_path: Path, state_home: Path
) -> None:
    area = tmp_path / "area"
    area.mkdir()
    origin = area / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "--initial-branch=main")
    checkout = area / "checkout"
    checkout.mkdir()
    git(checkout, "clone", "-q", str(origin), ".")
    git(checkout, "config", "user.email", "t@example.com")
    git(checkout, "config", "user.name", "t")
    git(checkout, "config", "commit.gpgsign", "false")
    (checkout / "a.txt").write_text("1\n2\n")
    git(checkout, "add", "a.txt")
    git(checkout, "commit", "-q", "-m", "init")
    git(checkout, "push", "-q", "origin", "main")
    head = git(checkout, "rev-parse", "HEAD").strip()
    patch = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n 1\n-2\n+22\n"
    result = worktree.prepare_application(
        repo_root=str(checkout),
        branch="main",
        head_sha=head,
        patch=patch,
        mr_url="https://gitlab.example/group/project/-/merge_requests/1",
    )
    explanation: dict[str, Any] = result["explanation"]
    assert explanation["branch"] == "main"
    assert explanation["head_sha"] == head
    assert explanation["files"] == ["a.txt"]
    assert "+22" in result["diff"]
    assert explanation["worktree_path"].endswith(".worktrees/reviewmatic/main")
    committed = worktree.commit_application(explanation["worktree_path"], "fix: apply review patch")
    assert len(committed["commit_sha"]) == 40
    record = worktree.load_registry()["items"][0]
    assert record["commit_sha"] == committed["commit_sha"]
    assert record["pushed"] is False
    with pytest.raises(contract.WorkflowError, match="nothing to commit"):
        worktree.commit_application(explanation["worktree_path"], "again")


def test_remove_worktree_rejects_unknown_pushed_and_dirty_entries(
    tmp_path: Path, state_home: Path
) -> None:
    area = tmp_path / "remove-area"
    area.mkdir()
    origin = area / "origin"
    origin.mkdir()
    git(origin, "init", "-q", "--bare", "--initial-branch=main")
    checkout = area / "checkout"
    checkout.mkdir()
    git(checkout, "clone", "-q", str(origin), ".")
    git(checkout, "config", "user.email", "t@example.com")
    git(checkout, "config", "user.name", "t")
    git(checkout, "config", "commit.gpgsign", "false")
    (checkout / "a.txt").write_text("1\n2\n")
    git(checkout, "add", "a.txt")
    git(checkout, "commit", "-q", "-m", "init")
    git(checkout, "push", "-q", "origin", "main")
    head = git(checkout, "rev-parse", "HEAD").strip()
    patch = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1,2 +1,2 @@\n 1\n-2\n+22\n"
    result = worktree.prepare_application(
        repo_root=str(checkout), branch="main", head_sha=head, patch=patch, mr_url="m"
    )
    target = result["explanation"]["worktree_path"]
    with pytest.raises(contract.WorkflowError, match="unknown review worktree"):
        worktree.remove_worktree(str(target) + "-other")
    # The applied patch is uncommitted, so removal stays guarded.
    with pytest.raises(contract.WorkflowError, match="uncommitted changes"):
        worktree.remove_worktree(target)
    worktree.commit_application(target, "fix: apply")
    worktree.remove_worktree(target)
    assert worktree.load_registry()["items"] == []
