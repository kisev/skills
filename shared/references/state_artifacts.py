"""Portable content history and post-success mutation markers."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

DIGEST = re.compile(r"[0-9a-f]{64}")
SKILL = re.compile(r"[a-z][a-z0-9-]{0,63}")
HISTORY_HEADING = "## History"
MARKER_SCHEMA = "agent-skills/post-success-marker/v1"
EXECUTION_STATUS = re.compile(r"# execution-status=(?:not_run|run_unverified)\n")


class StateArtifactError(ValueError):
    """State history or marker input is unsafe or inconsistent."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise StateArtifactError(message)


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def content_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _open_directory(path: Path, boundary: Path, *, create: bool) -> int:
    if any(part in {"", ".", ".."} for part in [*path.parts[1:], *boundary.parts[1:]]):
        raise StateArtifactError("state path must be normalized")
    try:
        path.relative_to(boundary)
    except ValueError as error:
        raise StateArtifactError("state path escapes its boundary") from error
    if not path.is_absolute() or not boundary.is_absolute():
        raise StateArtifactError("state path must be absolute")
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory:
        raise StateArtifactError("safe state traversal is unsupported")
    flags = os.O_RDONLY | directory | no_follow
    descriptor = os.open(path.anchor, flags)
    boundary_index = len(boundary.parts) - 1
    try:
        for index, part in enumerate(path.parts[1:], start=1):
            created = False
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                with contextlib.suppress(FileExistsError):
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
                created = True
            os.close(descriptor)
            descriptor = child
            metadata = os.fstat(descriptor)
            if index >= boundary_index:
                if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
                    raise StateArtifactError("state directory is unsafe")
                if metadata.st_mode & 0o022:
                    raise StateArtifactError("state directory is not private")
                if created or (create and metadata.st_mode & 0o077):
                    os.fchmod(descriptor, 0o700)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise StateArtifactError("state directory is unsafe") from error
    else:
        result = descriptor
        descriptor = -1
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return result


def _safe_directory(path: Path, boundary: Path) -> None:
    descriptor = _open_directory(path, boundary, create=True)
    os.close(descriptor)


def ensure_private_directory(path: Path, boundary: Path) -> Path:
    _safe_directory(path, boundary)
    return path


def inspect_private_directory(path: Path, boundary: Path) -> Path:
    descriptor = _open_directory(path, boundary, create=False)
    os.close(descriptor)
    return path


def _write_immutable(path: Path, content: bytes, boundary: Path) -> None:
    directory = _open_directory(path.parent, boundary, create=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        created = False
        try:
            descriptor = os.open(path.name, flags, 0o600, dir_fd=directory)
            created = True
        except FileExistsError:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                metadata = os.fstat(descriptor)
                with os.fdopen(descriptor, "rb", closefd=False) as handle:
                    existing = handle.read()
                if not stat.S_ISREG(metadata.st_mode) or existing != content:
                    raise StateArtifactError("immutable state history was changed") from None
            finally:
                os.close(descriptor)
            return
        try:
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb", closefd=False) as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.fsync(directory)
            except BaseException:
                if created:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(path.name, dir_fd=directory)
                    with contextlib.suppress(OSError):
                        os.fsync(directory)
                raise
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def _read_immutable(path: Path, boundary: Path) -> bytes:
    directory = _open_directory(path.parent, boundary, create=False)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise StateArtifactError("state file is unsafe")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except OSError as error:
        raise StateArtifactError("state file is unsafe") from error
    finally:
        os.close(directory)


def _read_optional_immutable(path: Path, boundary: Path) -> bytes | None:
    try:
        directory = _open_directory(path.parent, boundary, create=False)
    except FileNotFoundError:
        return None
    try:
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise StateArtifactError("state file is unsafe")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except OSError as error:
        raise StateArtifactError("state file is unsafe") from error
    finally:
        os.close(directory)


def _snapshot(history: Path, suffix: str, content: bytes) -> Path:
    digest = content_digest(content)
    path = history / f"{digest}{suffix}"
    _write_immutable(path, content, history.parent)
    return path


def _managed_history_exists(history: Path) -> bool:
    try:
        descriptor = _open_directory(history, history.parent, create=False)
    except FileNotFoundError:
        return False
    os.close(descriptor)
    return True


def _split_history(content: bytes, history: Path, *, managed: bool) -> tuple[bytes, list[Path]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise StateArtifactError("stable Markdown must be UTF-8") from error
    separator = f"\n{HISTORY_HEADING}\n"
    if not managed or separator not in text:
        return content, []
    body, footer = text.rsplit(separator, 1)
    lines = [line for line in footer.strip().splitlines() if line]
    paths: list[Path] = []
    for line in lines:
        match = re.fullmatch(r"- `([^`]+)`", line)
        if match is None:
            legacy_snapshot = history / f"{content_digest(content)}.md"
            try:
                archived_legacy = _read_immutable(legacy_snapshot, history.parent)
            except StateArtifactError:
                archived_legacy = None
            if archived_legacy == content:
                return content, []
            raise StateArtifactError("stable Markdown history footer is malformed")
        path = Path(match.group(1))
        if (
            not path.is_absolute()
            or path.parent != history
            or not DIGEST.fullmatch(path.stem)
            or path.suffix != ".md"
        ):
            raise StateArtifactError("stable Markdown history path is invalid")
        snapshot = _read_immutable(path, history.parent)
        if content_digest(snapshot) != path.stem:
            raise StateArtifactError("stable Markdown history snapshot changed")
        if path in paths:
            raise StateArtifactError("stable Markdown history path is duplicated")
        paths.append(path)
    return body.encode(), paths


def versioned_markdown(path: Path, body: bytes, *, legacy: bytes | None = None) -> bytes:
    """Create immutable snapshots and return the stable document with its history footer."""
    if path.suffix != ".md" or not path.is_absolute():
        raise StateArtifactError("stable Markdown path must be an absolute .md path")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise StateArtifactError("stable Markdown path is unsafe")
    if not body.endswith(b"\n"):
        body += b"\n"
    history = path.parent / "history" / path.stem
    previous: list[Path] = []
    if path.exists():
        old_body, previous = _split_history(
            path.read_bytes(), history, managed=_managed_history_exists(history)
        )
        if old_body == body:
            return path.read_bytes()
        old_snapshot = _snapshot(history, ".md", old_body)
        if old_snapshot not in previous:
            previous.append(old_snapshot)
    elif legacy is not None:
        legacy_body, _ = _split_history(legacy, history, managed=False)
        legacy_snapshot = _snapshot(history, ".md", legacy_body)
        if legacy_body != body:
            previous.append(legacy_snapshot)
    footer = [HISTORY_HEADING, "", *[f"- `{item}`" for item in previous]]
    _safe_directory(history, history.parent)
    return body + ("\n" + "\n".join(footer) + "\n").encode()


def markdown_body(path: Path) -> bytes:
    """Read the current body without the runtime-owned history footer."""
    history = path.parent / "history" / path.stem
    body, _ = _split_history(path.read_bytes(), history, managed=_managed_history_exists(history))
    return body


def archive_json(path: Path, body: bytes, boundary: Path) -> Path:
    """Store one canonical JSON state version in a content-addressed history."""
    history = boundary / "history" / path.stem
    return _snapshot(history, ".json", body)


def xdg_state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    path = Path(configured) if configured else Path.home() / ".local" / "state"
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise StateArtifactError("XDG_STATE_HOME must be an absolute normalized path")
    return path


def mutation_digest(argv: list[str], stdin_sha256: str | None) -> str:
    return content_digest(canonical_json({"argv": argv, "stdin_sha256": stdin_sha256}))


def marker_identity(skill: str, action: str, binding: str, mutation: str) -> str:
    return content_digest(canonical_json([MARKER_SCHEMA, skill, action, binding, mutation]))


def _validate_marker(skill: str, action: str, binding: str, mutation: str) -> None:
    if not SKILL.fullmatch(skill):
        raise StateArtifactError("marker skill is unsafe")
    if not action or "\x00" in action or len(action.encode()) > 512:
        raise StateArtifactError("marker action is unsafe")
    if not DIGEST.fullmatch(binding) or not DIGEST.fullmatch(mutation):
        raise StateArtifactError("marker digest is invalid")


def marker_path(skill: str, action: str, binding: str, mutation: str) -> Path:
    _validate_marker(skill, action, binding, mutation)
    marker_id = marker_identity(skill, action, binding, mutation)
    root = xdg_state_home() / "agent-skills" / "post-success" / "v1"
    return root / "markers" / marker_id[:2] / f"{marker_id}.json"


def execution_status(
    argv: list[str],
    *,
    skill: str,
    action: str,
    binding: str,
    stdin_sha256: str | None = None,
) -> str:
    mutation = mutation_digest(argv, stdin_sha256)
    path = marker_path(skill, action, binding, mutation)
    root = xdg_state_home() / "agent-skills" / "post-success" / "v1"
    marker_content = _read_optional_immutable(path, root)
    if marker_content is None:
        return "not_run"
    try:
        value = json.loads(marker_content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, StateArtifactError) as error:
        raise StateArtifactError("marker is unreadable") from error
    marker_id = path.stem
    expected = {
        "schema": MARKER_SCHEMA,
        "marker_id": marker_id,
        "skill": skill,
        "action_id": action,
        "binding_digest": binding,
        "mutation_digest": mutation,
        "exit_status": 0,
    }
    if (
        not isinstance(value, dict)
        or set(value) != {*expected, "succeeded_at"}
        or any(value.get(key) != item for key, item in expected.items())
    ):
        raise StateArtifactError("marker does not match its action")
    succeeded_at = value.get("succeeded_at")
    if not isinstance(succeeded_at, str):
        raise StateArtifactError("marker timestamp is invalid")
    try:
        timestamp = datetime.fromisoformat(succeeded_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise StateArtifactError("marker timestamp is invalid") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise StateArtifactError("marker timestamp is invalid")
    return "run_unverified"


def command_without_execution_status(command: str | None) -> str | None:
    if command is None:
        return None
    return EXECUTION_STATUS.sub("", command, count=1)


def record_success(skill: str, action: str, binding: str, mutation: str) -> Path:
    path = marker_path(skill, action, binding, mutation)
    marker_id = path.stem
    root = xdg_state_home() / "agent-skills" / "post-success" / "v1"
    payload = {
        "schema": MARKER_SCHEMA,
        "marker_id": marker_id,
        "skill": skill,
        "action_id": action,
        "binding_digest": binding,
        "mutation_digest": mutation,
        "exit_status": 0,
        "succeeded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    directory = _open_directory(path.parent, root, create=True)
    temporary = f".marker-{secrets.token_hex(16)}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(canonical_json(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        try:
            metadata = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(metadata.st_mode):
                raise StateArtifactError("marker path is unsafe")
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)
    return path


def render_mutation_command(
    argv: list[str],
    *,
    skill: str,
    action: str,
    binding: str,
    helper: Path | None = None,
    stdin_sha256: str | None = None,
    cwd: Path | None = None,
    git_head: str | None = None,
) -> str:
    if helper is None:
        helper = Path(__file__).resolve()
    command = [
        sys.executable,
        "-I",
        "-S",
        "-B",
        str(helper),
        "marker-run",
        "--skill",
        skill,
        "--action",
        action,
        "--binding",
        binding,
    ]
    if stdin_sha256 is not None:
        command.extend(["--stdin-sha256", stdin_sha256])
    if cwd is not None:
        command.extend(["--cwd", str(cwd)])
    if git_head is not None:
        command.extend(
            ["--git-head-digest", content_digest(canonical_json({"git_head": git_head}))]
        )
    status = execution_status(
        argv,
        skill=skill,
        action=action,
        binding=binding,
        stdin_sha256=stdin_sha256,
    )
    return f"# execution-status={status}\n" + shlex.join([*command, "--", *argv])


def marker_run(arguments: argparse.Namespace) -> int:
    argv = arguments.mutation
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise StateArtifactError("mutation command is required")
    stdin_content: bytes | None = None
    if arguments.stdin_sha256 is not None:
        if not DIGEST.fullmatch(arguments.stdin_sha256):
            raise StateArtifactError("stdin digest is invalid")
        stdin_content = sys.stdin.buffer.read()
        if content_digest(stdin_content) != arguments.stdin_sha256:
            raise StateArtifactError("mutation stdin does not match its digest")
    mutation = mutation_digest(argv, arguments.stdin_sha256)
    _validate_marker(arguments.skill, arguments.action, arguments.binding, mutation)
    if arguments.cwd is not None:
        cwd = Path(arguments.cwd)
        try:
            resolved_cwd = cwd.resolve(strict=True)
        except OSError as error:
            raise StateArtifactError("mutation cwd is unavailable") from error
        if not cwd.is_absolute() or cwd != resolved_cwd or not resolved_cwd.is_dir():
            raise StateArtifactError("mutation cwd is unsafe")
    else:
        resolved_cwd = None
    if arguments.git_head_digest is not None:
        if resolved_cwd is None or not DIGEST.fullmatch(arguments.git_head_digest):
            raise StateArtifactError("git head precondition is invalid")
        git = shutil.which("git")
        if git is None:
            raise StateArtifactError("git is unavailable")
        current = subprocess.run(  # noqa: S603
            [git, "-C", str(resolved_cwd), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        current_digest = content_digest(canonical_json({"git_head": current.stdout.strip()}))
        if current.returncode != 0 or current_digest != arguments.git_head_digest:
            print("error: mutation git head changed; regenerate before applying", file=sys.stderr)
            return 3
    result = subprocess.run(argv, input=stdin_content, check=False)  # noqa: S603
    if result.returncode != 0:
        return result.returncode
    try:
        record_success(arguments.skill, arguments.action, arguments.binding, mutation)
    except (OSError, StateArtifactError) as error:
        print(
            "warning: mutation exited 0, but its advisory marker was not written; "
            f"revalidate the target before retrying ({error})",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("marker-run")
    run.add_argument("--skill", required=True)
    run.add_argument("--action", required=True)
    run.add_argument("--binding", required=True)
    run.add_argument("--stdin-sha256")
    run.add_argument("--cwd")
    run.add_argument("--git-head-digest")
    run.add_argument("mutation", nargs=argparse.REMAINDER)
    try:
        arguments = parser.parse_args(argv)
        if arguments.command == "marker-run":
            return marker_run(arguments)
        raise StateArtifactError("unsupported command")
    except StateArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
