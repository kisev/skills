#!/usr/bin/env python3
"""Safe JSON search and explicitly confirmed AST rewrites."""

from __future__ import annotations

import difflib
import hashlib
import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


_bootstrap()

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import (
    ContractArgumentParser,
    emit_escalation,
    report_error,
)


class ToolUnavailable(Exception):
    """The required external binary is absent."""


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="ast-grep")
    result.add_argument("--capabilities", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("search", "rewrite"):
        command = commands.add_parser(name)
        command.add_argument("--pattern", required=True)
        command.add_argument("--lang", required=True)
        command.add_argument("paths", nargs="*")
        if name == "rewrite":
            command.add_argument("--rewrite", required=True)
            command.add_argument("--workspace", default=".")
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--apply", action="store_true")
            command.add_argument("--confirm")
    return result


def executable() -> str:
    value = shutil.which("ast-grep")
    if value is None:
        raise ToolUnavailable("ast-grep CLI is unavailable.")
    return value


def run_ast_grep(
    lang: str, pattern: str, paths: list[str], rewrite: str | None = None
) -> list[dict[str, Any]]:
    command = [executable(), "run", "--lang", lang, "--pattern", pattern]
    if rewrite is not None:
        command.extend(("--rewrite", rewrite))
    command.extend(("--json=compact", *paths))
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise ValueError(
            completed.stderr.strip()
            or completed.stdout.strip()
            or f"ast-grep exited with status {completed.returncode}"
        )
    try:
        value = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as error:
        raise ValueError("ast-grep returned invalid JSON") from error
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("ast-grep returned an invalid JSON result")
    return value


def workspace_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        raise ValueError("workspace must not be a symlink")
    resolved = candidate.resolve()
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError("workspace must be an existing non-symlink directory")
    return resolved


def checked_target(value: str | Path, workspace: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    if candidate.is_symlink():
        raise ValueError(f"rewrite target is a symlink: {candidate}")
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(workspace)
    except (OSError, ValueError) as error:
        raise ValueError(f"rewrite target is outside workspace: {candidate}") from error
    current = workspace
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"rewrite target uses a symlink: {current}")
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"rewrite target is not a regular file: {resolved}")
    return resolved


def rewrite_paths(values: list[str], workspace: Path) -> list[str]:
    raw_paths = values or [str(workspace)]
    targets: list[str] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(workspace)
        except ValueError as error:
            raise ValueError(
                f"rewrite input path is outside workspace: {raw}"
            ) from error
        if candidate.is_symlink():
            raise ValueError(f"rewrite input path is a symlink: {raw}")
        if not resolved.exists():
            raise ValueError(f"rewrite input path does not exist: {raw}")
        targets.append(str(resolved))
    return targets


def apply_changes(original: bytes, changes: list[dict[str, Any]]) -> bytes:
    updated = original
    for change in sorted(changes, key=lambda item: int(item["start"]), reverse=True):
        updated = (
            updated[: int(change["start"])]
            + str(change["replacement"]).encode()
            + updated[int(change["end"]) :]
        )
    return updated


def preview(arguments: Any) -> dict[str, Any]:
    workspace = workspace_path(arguments.workspace)
    targets = rewrite_paths(arguments.paths, workspace)
    matches = run_ast_grep(
        arguments.lang, arguments.pattern, targets, arguments.rewrite
    )
    changes: list[dict[str, Any]] = []
    for item in matches:
        target = checked_target(str(item.get("file", "")), workspace)
        offsets = item.get("replacementOffsets")
        replacement = item.get("replacement")
        start = offsets.get("start") if isinstance(offsets, dict) else None
        end = offsets.get("end") if isinstance(offsets, dict) else None
        if (
            not isinstance(replacement, str)
            or not isinstance(start, int)
            or not isinstance(end, int)
        ):
            raise TypeError("ast-grep result lacks rewrite offsets")
        original = target.read_bytes()
        if start < 0 or end < start or end > len(original):
            raise ValueError("ast-grep result contains invalid rewrite offsets")
        changes.append(
            {
                "file": str(target),
                "start": start,
                "end": end,
                "replacement": replacement,
                "original_sha256": hashlib.sha256(original).hexdigest(),
            }
        )
    changes.sort(
        key=lambda item: (str(item["file"]), int(item["start"]), int(item["end"]))
    )
    for previous, current in itertools.pairwise(changes):
        if previous["file"] == current["file"] and int(previous["end"]) > int(
            current["start"]
        ):
            raise ValueError("overlapping AST rewrites are not supported")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(str(change["file"]), []).append(change)
    diff: list[str] = []
    for name, file_changes in grouped.items():
        original = Path(name).read_bytes()
        updated = apply_changes(original, file_changes)
        diff.extend(
            difflib.unified_diff(
                original.decode("utf-8", errors="replace").splitlines(keepends=True),
                updated.decode("utf-8", errors="replace").splitlines(keepends=True),
                fromfile=name,
                tofile=name,
            )
        )
    digest = (
        hashlib.sha256(
            json.dumps(changes, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if changes
        else None
    )
    return {
        "schema_version": 1,
        "workspace": str(workspace),
        "changes": changes,
        "match_count": len(changes),
        "diff": "".join(diff),
        "confirmation": digest,
        "confirmation_request": {"digest": digest} if digest else None,
    }


def atomic_replace(updates: list[tuple[Path, bytes]]) -> None:
    if not updates:
        return
    common = Path(os.path.commonpath([str(path.parent) for path, _content in updates]))
    stage = Path(tempfile.mkdtemp(prefix=".ast-grep-", dir=common))
    replaced: list[tuple[Path, Path]] = []
    try:
        staged: list[Path] = []
        for index, (path, content) in enumerate(updates):
            candidate = stage / f"update-{index}"
            candidate.write_bytes(content)
            candidate.chmod(stat.S_IMODE(path.stat().st_mode))
            staged.append(candidate)
        for index, ((path, _content), candidate) in enumerate(
            zip(updates, staged, strict=True)
        ):
            backup = stage / f"backup-{index}"
            os.replace(path, backup)
            try:
                os.replace(candidate, path)
            except OSError:
                os.replace(backup, path)
                raise
            replaced.append((path, backup))
    except OSError:
        for path, backup in reversed(replaced):
            try:
                if path.exists():
                    path.unlink()
                if backup.exists():
                    os.replace(backup, path)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def apply_preview(document: dict[str, Any], expected: str) -> None:
    if document["confirmation"] != expected:
        raise ValueError("digest_mismatch: confirmation digest does not match preview")
    workspace = workspace_path(str(document["workspace"]))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in document["changes"]:
        grouped.setdefault(str(change["file"]), []).append(change)
    updates: list[tuple[Path, bytes]] = []
    for name, changes in grouped.items():
        path = checked_target(name, workspace)
        original = path.read_bytes()
        if any(
            hashlib.sha256(original).hexdigest() != str(change["original_sha256"])
            for change in changes
        ):
            raise ValueError(
                f"digest_mismatch: rewrite target changed after preview: {path}"
            )
        updates.append((path, apply_changes(original, changes)))
    atomic_replace(updates)


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.0.0",
        mutation="write",
        supports_dry_run=True,
        external_tools=("ast-grep",),
        destructive_flags=("--apply", "--confirm"),
        confirmation=True,
    ):
        return 0
    arguments = arguments_parser.parse_args(argv)
    try:
        if arguments.command == "search":
            print(
                json.dumps(
                    run_ast_grep(
                        arguments.lang, arguments.pattern, arguments.paths or ["."]
                    ),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        if arguments.apply and arguments.dry_run:
            raise ValueError("--apply cannot be used with --dry-run")
        document = preview(arguments)
        if not document["match_count"]:
            document["applied"] = False
        elif arguments.apply:
            if not arguments.confirm:
                raise ValueError("rewrite apply requires explicit --confirm DIGEST")
            apply_preview(document, arguments.confirm)
            document["applied"] = True
        else:
            document["applied"] = False
        print(json.dumps(document, ensure_ascii=False, sort_keys=True))
        return 0
    except ToolUnavailable as error:
        emit_escalation(
            str(error),
            {
                "executable": "ast-grep",
                "action": "Install ast-grep using the host's normal toolchain.",
            },
        )
    except (OSError, TypeError, ValueError, UnicodeError) as error:
        message = str(error)
        report_error(
            "digest_mismatch"
            if message.startswith("digest_mismatch:")
            else "ast_grep_error",
            message.removeprefix("digest_mismatch: ").strip(),
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
