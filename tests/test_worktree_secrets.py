from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from scripts.check_worktree_secrets import snapshot

if TYPE_CHECKING:
    from pathlib import Path


def test_snapshot_keeps_tracked_ignored_and_pending_files_but_not_private_state(
    tmp_path: Path,
) -> None:
    repo, target = tmp_path / "repo", tmp_path / "snapshot"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / ".gitignore").write_text("private/\n")
    (repo / "private").mkdir()
    (repo / "private/local.json").write_text("local runtime state")
    (repo / "private/tracked.json").write_text("forced into Git")
    subprocess.run(["git", "add", "-f", "private/tracked.json"], cwd=repo, check=True)
    (repo / "pending.txt").write_text("not yet staged")
    snapshot(repo, target)
    assert not (target / "private/local.json").exists()
    assert (target / "private/tracked.json").read_text() == "forced into Git"
    assert (target / "pending.txt").read_text() == "not yet staged"


def test_snapshot_scans_symlink_bytes_without_following_outside_checkout(tmp_path: Path) -> None:
    repo, target = tmp_path / "repo", tmp_path / "snapshot"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    outside = tmp_path / "private.txt"
    outside.write_text("must not copy this")
    (repo / "link").symlink_to(outside)
    snapshot(repo, target)
    assert not (target / "link").is_symlink()
    assert (target / "link").read_text() == str(outside)


def test_replaced_tracked_directory_does_not_follow_new_parent_symlink(tmp_path: Path) -> None:
    repo, target = tmp_path / "repo", tmp_path / "snapshot"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    directory = repo / "directory"
    directory.mkdir()
    (directory / "file").write_text("tracked")
    subprocess.run(["git", "add", "directory/file"], cwd=repo, check=True)
    (directory / "file").unlink()
    directory.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_text("private bytes")
    directory.symlink_to(outside, target_is_directory=True)
    snapshot(repo, target)
    assert (target / "directory").is_file()
    assert (target / "directory").read_text() == str(outside)
