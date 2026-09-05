"""Small, stdlib-only state helpers for OpenCode-specific portable skills."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StateError(ValueError):
    """State is missing, unsafe, malformed, or has an unsupported schema."""


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home()).expanduser().resolve()


def _xdg(name: str, fallback: str) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else _home() / fallback


def skill_state_root(skill: str) -> Path:
    if not skill.replace("-", "").isalnum() or ".." in skill:
        raise StateError("unsafe skill name")
    return _xdg("XDG_STATE_HOME", ".local/state") / "opencode" / "skills" / skill


def skill_config_root(skill: str) -> Path:
    if not skill.replace("-", "").isalnum() or ".." in skill:
        raise StateError("unsafe skill name")
    return _xdg("XDG_CONFIG_HOME", ".config") / "opencode" / "skill-config" / skill


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def safe_file(path: Path, root: Path, *, missing_ok: bool = False) -> Path | None:
    if not _inside(path, root):
        raise StateError("state path escapes its root")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise StateError(f"symlink is not allowed: {current}")
    if not path.exists():
        if missing_ok:
            return None
        raise StateError(f"state file does not exist: {path}")
    if not path.is_file() or path.is_symlink():
        raise StateError(f"state target is not a regular file: {path}")
    return path


def read_json(path: Path, root: Path) -> dict[str, Any]:
    safe_file(path, root)
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise StateError(f"cannot read JSON: {error}") from error
    if not isinstance(result, dict):
        raise StateError("JSON state must be an object")
    return result


def atomic_write_json(path: Path, root: Path, value: dict[str, Any]) -> None:
    if not _inside(path, root):
        raise StateError("state path escapes its root")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = root
    if current.is_symlink():
        raise StateError(f"symlink is not allowed: {current}")
    for part in path.parent.relative_to(root).parts:
        current /= part
        if current.is_symlink() or not current.is_dir():
            raise StateError(f"state directory is unsafe: {current}")
    if path.exists() and path.is_symlink():
        raise StateError(f"symlink is not allowed: {path}")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def append_json_line(path: Path, root: Path, value: dict[str, Any]) -> None:
    if not _inside(path, root):
        raise StateError("state path escapes its root")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = root
    if current.is_symlink():
        raise StateError(f"symlink is not allowed: {current}")
    for part in path.parent.relative_to(root).parts:
        current /= part
        if current.is_symlink() or not current.is_dir():
            raise StateError(f"state directory is unsafe: {current}")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise StateError(f"state target is not a regular file: {path}")
    with path.open("a", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def revision(value: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
