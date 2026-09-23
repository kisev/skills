#!/usr/bin/env python3
"""Resolve and atomically write a workspace-scoped stopit handoff."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import secrets
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from shared.references.state_artifacts import versioned_markdown
else:
    _state_path = Path(__file__).with_name("state_artifacts.py")
    if not _state_path.exists():
        _state_path = next(
            parent / "shared" / "references" / "state_artifacts.py"
            for parent in Path(__file__).resolve().parents
            if (parent / "shared" / "references" / "state_artifacts.py").is_file()
        )
    _state_spec = importlib.util.spec_from_file_location("state_artifacts", _state_path)
    if _state_spec is None or _state_spec.loader is None:
        raise ImportError("state_artifacts runtime is unavailable") from None
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    versioned_markdown = _state_module.versioned_markdown

MAX_HANDOFF_BYTES = 256 * 1024
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


class HandoffError(ValueError):
    """Expected safe failure."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise HandoffError(message)


def canonical_workspace(value: str) -> Path:
    try:
        workspace = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise HandoffError("workspace must be an existing path") from error
    if not workspace.is_dir():
        raise HandoffError("workspace must be an existing directory")
    return workspace


def state_root() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    root = Path(configured) if configured else Path.home() / ".local" / "state"
    if not root.is_absolute() or any(part in {"", ".", ".."} for part in root.parts[1:]):
        raise HandoffError("XDG state home must be an absolute normalized path")
    return root


def handoff_path(workspace: Path) -> tuple[Path, int]:
    workspace_id = hashlib.sha256(os.fsencode(workspace)).hexdigest()
    root = state_root()
    path = root / "agent-skills" / "stopit" / workspace_id / "handoff.md"
    return path, len(root.parts) - 1


def directory_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory:
        raise HandoffError("safe XDG state traversal is not supported on this platform")
    return os.O_RDONLY | directory | no_follow


def validate_directory(metadata: os.stat_result, *, state_root_directory: bool) -> None:
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        raise HandoffError("XDG state path contains an unsafe directory")
    forbidden = 0o022 if state_root_directory else 0o077
    if metadata.st_mode & forbidden:
        raise HandoffError("XDG state path contains a non-private directory")


def open_handoff_directory(path: Path, state_parts: int, *, create: bool) -> int | None:
    flags = directory_flags()
    current = os.open("/", flags)
    try:
        for index, part in enumerate(path.parent.parts[1:], start=1):
            created = False
            try:
                child = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    return None
                try:
                    os.mkdir(part, PRIVATE_DIRECTORY_MODE, dir_fd=current)
                except FileExistsError:
                    pass
                except OSError as error:
                    raise HandoffError("failed to create the XDG state path") from error
                else:
                    created = True
                try:
                    child = os.open(part, flags, dir_fd=current)
                except OSError as error:
                    raise HandoffError("XDG state path is unsafe") from error
            except OSError as error:
                raise HandoffError("XDG state path is unsafe") from error

            os.close(current)
            current = child
            metadata = os.fstat(current)
            if created:
                os.fchmod(current, PRIVATE_DIRECTORY_MODE)
                metadata = os.fstat(current)
            if index >= state_parts:
                validate_directory(metadata, state_root_directory=index == state_parts)
        result = current
        current = -1
        return result
    finally:
        if current >= 0:
            os.close(current)


def validate_existing_handoff(directory: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        raise HandoffError("handoff path is unsafe") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o077
    ):
        raise HandoffError("handoff path is unsafe")


def inspect_path(path: Path, state_parts: int) -> None:
    directory = open_handoff_directory(path, state_parts, create=False)
    if directory is None:
        return
    try:
        validate_existing_handoff(directory, path.name)
    finally:
        os.close(directory)


def read_handoff() -> bytes:
    content = sys.stdin.buffer.read(MAX_HANDOFF_BYTES + 1)
    if len(content) > MAX_HANDOFF_BYTES:
        raise HandoffError(f"handoff exceeds {MAX_HANDOFF_BYTES} bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HandoffError("handoff must be valid UTF-8") from error
    if not text.strip():
        raise HandoffError("handoff must not be empty")
    if "\x00" in text:
        raise HandoffError("handoff must not contain NUL characters")
    return content


def atomic_write(path: Path, state_parts: int, content: bytes) -> None:
    directory = open_handoff_directory(path, state_parts, create=True)
    if directory is None:
        raise HandoffError("failed to create the handoff directory")
    temporary_name = f".handoff.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    descriptor = -1
    try:
        validate_existing_handoff(directory, path.name)
        content = versioned_markdown(path, content)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, flags, PRIVATE_FILE_MODE, dir_fd=directory)
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written == 0:
                raise HandoffError("failed to write the complete handoff")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary_name, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except HandoffError:
        raise
    except OSError as error:
        raise HandoffError("failed to atomically write the handoff") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


def parser() -> Parser:
    result = Parser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    path = commands.add_parser("path")
    path.add_argument("--workspace", required=True)
    write = commands.add_parser("write")
    write.add_argument("--workspace", required=True)
    write.add_argument("--expected-path", required=True)
    return result


def main() -> int:
    try:
        arguments = parser().parse_args()
        workspace = canonical_workspace(arguments.workspace)
        path, state_parts = handoff_path(workspace)
        if arguments.command == "path":
            inspect_path(path, state_parts)
        else:
            if Path(arguments.expected_path) != path:
                raise HandoffError("handoff destination changed after confirmation")
            atomic_write(path, state_parts, read_handoff())
    except HandoffError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    else:
        print(path)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
