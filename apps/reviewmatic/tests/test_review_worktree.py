"""Review-worktree unit regressions: slugs, remotes, registry, and locking."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.review_worktree import (
    _parse_remote_url,
    _remotes_for,
    _with_preparation_lock,
    checkout_root,
    load_review_registry,
    review_slug,
    review_worktree_path,
    save_review_registry,
)


@pytest.fixture(name="state_home")
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home


def test_review_slug_separates_full_identity() -> None:
    assert review_slug("gitlab.example", "group/a-b", 7) != review_slug(
        "gitlab.example", "group-a/b", 7
    )
    assert review_slug("gitlab.example", "group/project", 7) != review_slug(
        "gitlab.example", "group/project", 8
    )
    long_a = f"long/{'a' * 120}"
    long_b = f"long/{'a' * 119}b"
    slug_a = review_slug("gitlab.example", long_a, 7)
    slug_b = review_slug("gitlab.example", long_b, 7)
    assert slug_a != slug_b
    for slug in (slug_a, slug_b):
        assert len(slug) <= 96 + 1 + 8
        identity_suffix = slug.rsplit("-", 1)[1]
        assert len(identity_suffix) == 8
        assert all(character in "0123456789abcdef" for character in identity_suffix)
    # The readable prefixes are identical after truncation; only the suffix differs.
    assert slug_a[:-9] == slug_b[:-9]


def test_review_worktree_path_uses_the_suffix_slug(tmp_path: Path) -> None:
    path = review_worktree_path(str(tmp_path), "gitlab.example", "group/project", 7)
    assert Path(path).parent == Path(f"{tmp_path}.worktrees") / "reviewmatic"
    assert Path(path).name == review_slug("gitlab.example", "group/project", 7)


def test_remote_url_parsing_normalizes_hosts_and_paths() -> None:
    assert _parse_remote_url("https://GitLab.example/Group/Project.git") == (
        "gitlab.example",
        "Group/Project",
    )
    assert _parse_remote_url("git@gitlab.example:group/project.git") == (
        "gitlab.example",
        "group/project",
    )
    assert _parse_remote_url("ssh://git@gitlab.example:2222/group/project") == (
        "gitlab.example",
        "group/project",
    )
    assert _parse_remote_url("https://gitlab.example/group/project?x=1#f") == (
        "gitlab.example",
        "group/project",
    )
    assert _parse_remote_url("") is None
    assert _parse_remote_url("https://gitlab.example/") is None


def test_remotes_for_matches_host_and_project_case_insensitively(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git = ["git", "-C", str(root)]

    def run(*arguments: str) -> None:
        subprocess.run([*git, *arguments], check=True, capture_output=True)

    run("init", "-q", "--initial-branch=main")
    run("remote", "add", "origin", "https://gitlab.example/Group/Project.git")
    matched = _remotes_for(str(root), "gitlab.example", ["group/project"])
    assert [item.name for item in matched] == ["origin"]
    assert matched[0].project == "Group/Project"
    run("remote", "add", "other", "https://elsewhere.example/group/project.git")
    assert [item.name for item in _remotes_for(str(root), "gitlab.example", ["group/project"])] == [
        "origin"
    ]


def test_checkout_root_rejects_a_foreign_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(contract.WorkflowError, match="is not a Git checkout"):
        checkout_root(outside)


def test_registry_roundtrip_and_invalid_documents(state_home: Path) -> None:
    assert load_review_registry() == {
        "schema": "reviewmatic/review-worktree-registry/v1",
        "items": [],
    }
    record = {
        "schema": "reviewmatic/review-worktree/v1",
        "path": "/tmp/wt",
        "host": "gitlab.example",
        "project_path": "g/p",
        "iid": 7,
        "head_sha": "a" * 40,
    }
    save_review_registry({"schema": "reviewmatic/review-worktree-registry/v1", "items": [record]})
    stored = load_review_registry()
    assert stored["items"] == [record]
    assert stored["items"][0]["path"] == "/tmp/wt"
    path = state_home / "agent-skills" / "reviewmatic" / "review-worktrees.json"
    path.write_text('{"schema": "other", "items": []}', encoding="utf-8")
    with pytest.raises(contract.WorkflowError, match="review worktree registry is invalid"):
        load_review_registry()


def test_preparation_lock_reclaims_stale_owners(state_home: Path) -> None:
    base = state_home / "locks"

    # A lock whose owner is dead is reclaimed; the winner records its own PID.
    lock = base / ".slug.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("999999999\n", encoding="utf-8")

    def observe() -> str:
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
        return "reclaimed"

    assert _with_preparation_lock(base, "slug", observe) == "reclaimed"
    assert not lock.exists()

    # A lock held by this process is also stale by definition (same owner) and
    # gets reclaimed rather than deadlocking.
    lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert _with_preparation_lock(base, "slug", lambda: "again") == "again"
    assert not lock.exists()
