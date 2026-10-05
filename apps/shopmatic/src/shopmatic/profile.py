"""XDG-scoped profile storage with the mattermost private-path discipline.

Profiles hold marketplace cookies and never live inside the repository.
Directories are real, owned by the current user, and created with mode 0700;
files are 0600. Symlinks are rejected on every boundary check.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
from pathlib import Path

from shopmatic.errors import ShopmaticError

PROFILE_ROOT_ENV = "SHOPMATIC_PROFILE_ROOT"


def _xdg_root(environment: str, default: Path) -> Path:
    configured = Path(os.environ.get(environment) or default)
    if not configured.is_absolute() or configured != Path(os.path.normpath(configured)):
        raise ShopmaticError(f"{environment} must be a normalized absolute path")
    return configured


def config_root() -> Path:
    """Return the shopmatic configuration root under XDG_CONFIG_HOME."""
    default = Path.home() / ".config"
    return _xdg_root("XDG_CONFIG_HOME", default) / "shopmatic"


def private_directory(path: Path) -> Path:
    """Create or verify a private 0700 directory, rejecting symlinks."""
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise ShopmaticError("private directory must be a real directory")
    else:
        path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def require_private_directory(path: Path) -> None:
    """Fail unless the path is a real, owned, 0700 directory."""
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ShopmaticError("private directory is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise ShopmaticError("private directory is unsafe")


def profile_root() -> Path:
    """Return the profile root; override with SHOPMATIC_PROFILE_ROOT for tests."""
    override = os.environ.get(PROFILE_ROOT_ENV)
    if override:
        return private_directory(Path(override))
    return private_directory(config_root() / "profiles")


def anonymous_profile(existing: str | None = None) -> Path:
    """Create a fresh empty anonymous profile directory."""
    token = existing or f"anon-{secrets.token_hex(8)}"
    return private_directory(profile_root() / "anonymous" / token)


def account_profile(marketplace: str) -> Path:
    """Return (creating if needed) the persistent profile of one marketplace."""
    if marketplace not in {"wildberries", "yandex-market", "ozon"}:
        raise ShopmaticError("unknown marketplace profile")
    return private_directory(profile_root() / "accounts" / marketplace)


def discard_profile(path: Path) -> None:
    """Remove an anonymous profile after the browser has been closed."""
    if path.exists() or path.is_symlink():
        require_private_directory(path)
        shutil.rmtree(path)


def wipe_profile(path: Path) -> None:
    """Recreate an account profile from scratch (logout by wiping cookies)."""
    require_private_directory(path)
    shutil.rmtree(path)
    private_directory(path)
