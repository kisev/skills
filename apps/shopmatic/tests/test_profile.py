"""Profile discipline tests: private paths, modes, symlinks, and roots."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from shopmatic.errors import ShopmaticError
from shopmatic.profile import (
    account_profile,
    anonymous_profile,
    config_root,
    discard_profile,
    private_directory,
    profile_root,
    require_private_directory,
    wipe_profile,
)


def test_anonymous_profile_creates_private_directory(fake_environment: Path) -> None:
    profile = anonymous_profile("anon-test")
    assert profile.is_dir()
    assert profile.parent.parent == fake_environment
    assert (os.stat(profile).st_mode & 0o777) == 0o700


def test_private_directory_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ShopmaticError, match="real directory"):
        private_directory(link)


def test_require_private_directory_rejects_loose_mode(tmp_path: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o755)
    with pytest.raises(ShopmaticError, match="unsafe"):
        require_private_directory(loose)


def test_require_private_directory_rejects_file(tmp_path: Path) -> None:
    candidate = tmp_path / "file"
    candidate.write_text("x", encoding="utf-8")
    with pytest.raises(ShopmaticError, match="unsafe"):
        require_private_directory(candidate)


def test_config_root_rejects_relative_xdg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/path")
    with pytest.raises(ShopmaticError, match="normalized absolute path"):
        config_root()


def test_profile_root_uses_override(fake_environment: Path) -> None:
    assert profile_root() == fake_environment


def test_account_profile_rejects_unknown_marketplace(fake_environment: Path) -> None:
    with pytest.raises(ShopmaticError, match="unknown marketplace"):
        account_profile("avito")


def test_account_profile_is_persistent(fake_environment: Path) -> None:
    first = account_profile("wildberries")
    second = account_profile("wildberries")
    assert first == second
    assert first.parent.name == "accounts"


def test_discard_profile_removes_tree(fake_environment: Path) -> None:
    profile = anonymous_profile("anon-gone")
    inner = profile / "Default"
    inner.mkdir()
    (inner / "Cookies").write_text("data", encoding="utf-8")
    discard_profile(profile)
    assert not profile.exists()


def test_wipe_profile_recreates_empty(fake_environment: Path) -> None:
    profile = account_profile("yandex-market")
    (profile / "Cookies").write_text("data", encoding="utf-8")
    wipe_profile(profile)
    assert profile.is_dir()
    assert list(profile.iterdir()) == []
