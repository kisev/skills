#!/usr/bin/env python3
"""Validate explicit team context and apply confirmed local artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

MAX_BYTES = 2 * 1024 * 1024
TTL_SECONDS = 600
ACTIONS = frozenset({"planning", "sprint-status", "sprint-close", "retro", "roadmap", "slides-prompts"})
FORBIDDEN = frozenset({"credentials", "tokens", "password", "secret", "personal_notes"})


class WorkflowError(ValueError):
    """Expected safe workflow failure."""


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(code: str, message: str, exit_code: int = 2) -> int:
    print(message, file=sys.stderr)
    emit({"status": "error", "error": {"code": code, "message": message, "retryable": False}})
    return exit_code


def private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError("state directory must be a real directory")
    path.chmod(0o700)
    return path.resolve()


def state_root() -> Path:
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return private_directory(home / "agent-skills" / "team-workflow")


def regular(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
        raise WorkflowError(f"{label} must be a small regular non-symlink file")
    return path.resolve()


def read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    source = regular(path, label)
    raw = source.read_bytes()
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain JSON object")
    return value, raw


def atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def validate_context(value: dict[str, Any]) -> dict[str, Any]:
    def scan(item: Any) -> None:
        if isinstance(item, dict):
            if any(str(key).lower() in FORBIDDEN for key in item):
                raise WorkflowError("context contains credentials or personal notes")
            for child in item.values():
                scan(child)
        elif isinstance(item, list):
            for child in item:
                scan(child)
    scan(value)
    required = ("goals", "scope", "cadence", "baseline", "projects", "delivery_signals")
    missing = [key for key in required if key not in value or value[key] in (None, "", [], {})]
    if missing:
        raise WorkflowError("setup-required: " + ", ".join(missing))
    return value


def valid_name(value: str) -> str:
    if not value or len(value) > 63 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value):
        raise WorkflowError("context name is invalid")
    return value


def confirmation(payload: dict[str, Any]) -> tuple[str, Path]:
    root = private_directory(state_root() / "confirmations")
    identifier = uuid4().hex
    document = {"id": identifier, "expires_at": time.time() + TTL_SECONDS, "consumed": False, "digest": hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "payload": payload}
    path = root / f"{identifier}.json"
    atomic(path, json.dumps(document, ensure_ascii=False, sort_keys=True).encode())
    return identifier, path


def consume(identifier: str, payload: dict[str, Any]) -> None:
    if len(identifier) != 32 or any(character not in "0123456789abcdef" for character in identifier):
        raise WorkflowError("confirmation id is invalid")
    path = regular(state_root() / "confirmations" / f"{identifier}.json", "confirmation")
    document, _ = read_json(path, "confirmation")
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if document.get("consumed") or not isinstance(document.get("expires_at"), (int, float)) or document["expires_at"] < time.time():
        raise WorkflowError("confirmation is stale or already consumed")
    if document.get("digest") != digest:
        raise WorkflowError("confirmation payload changed")
    document["consumed"] = True
    atomic(path, json.dumps(document, ensure_ascii=False, sort_keys=True).encode())


def workspace_target(value: str) -> Path:
    root = Path.cwd().resolve()
    candidate = Path(value)
    if candidate.is_absolute():
        raise WorkflowError("artifact target must be workspace-relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise WorkflowError("artifact target is unsafe")
    target = root / candidate
    current = root
    for part in candidate.parts[:-1]:
        current /= part
        if current.exists() and (current.is_symlink() or not current.is_dir()):
            raise WorkflowError("artifact parent is unsafe")
    if (target.exists() or target.is_symlink()) and (target.is_symlink() or not target.is_file()):
        raise WorkflowError("artifact target is unsafe")
    return target


def load_context(args: argparse.Namespace) -> tuple[dict[str, Any], bytes, str]:
    supplied = [value for value in (args.context_file, args.context_name, args.chat_input) if value]
    if len(supplied) != 1:
        raise WorkflowError("exactly one explicit context source is required")
    if args.context_file or args.chat_input:
        path = Path(args.context_file or args.chat_input)
        value, raw = read_json(path, "context")
        return validate_context(value), raw, str(path.resolve())
    path = regular(state_root() / "contexts" / f"{valid_name(args.context_name)}.json", "saved context")
    value, raw = read_json(path, "saved context")
    return validate_context(value), raw, str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    check = subparsers.add_parser("action-check")
    check.add_argument("--action", required=True, choices=sorted(ACTIONS))
    check.add_argument("--context-file")
    check.add_argument("--context-name")
    check.add_argument("--chat-input")
    prepare = subparsers.add_parser("context-prepare")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--name", required=True)
    save = subparsers.add_parser("context-save")
    save.add_argument("--name", required=True)
    save.add_argument("--input", required=True)
    save.add_argument("--confirmation-id", required=True)
    artifact_prepare = subparsers.add_parser("artifact-prepare")
    artifact_prepare.add_argument("--target", required=True)
    artifact_prepare.add_argument("--input", required=True)
    artifact_apply = subparsers.add_parser("artifact-apply")
    artifact_apply.add_argument("--target", required=True)
    artifact_apply.add_argument("--input", required=True)
    artifact_apply.add_argument("--confirmation-id", required=True)
    args = parser.parse_args(argv)
    if args.capabilities:
        emit({"schema_version": 1, "payload_version": "1.0.0", "mutation": "local-write-confirmed", "dry_run": True, "state_protocol": "confirmation-receipts", "external_tools": {}, "destructive_flags": ["context-save", "artifact-apply"]})
        return 0
    try:
        if args.command == "action-check":
            context, _, source = load_context(args)
            emit({"status": "ok", "action": args.action, "context_source": source, "projects": len(context["projects"]), "external_mutations": False})
            return 0
        if args.command == "context-prepare":
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            valid_name(args.name)
            identifier, _ = confirmation({"kind": "context", "name": args.name, "content": raw.decode("utf-8")})
            emit({"status": "confirmation_request", "confirmation_id": identifier, "preview": context})
            return 0
        if args.command == "context-save":
            valid_name(args.name)
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            payload = {"kind": "context", "name": args.name, "content": raw.decode("utf-8")}
            consume(args.confirmation_id, payload)
            root = private_directory(state_root() / "contexts")
            atomic(root / f"{args.name}.json", raw)
            emit({"status": "ok", "name": args.name})
            return 0
        if args.command == "artifact-prepare":
            source = regular(Path(args.input), "artifact input")
            content = source.read_bytes()
            target = workspace_target(args.target)
            identifier, _ = confirmation({"kind": "artifact", "target": args.target, "content": content.decode("utf-8")})
            emit({"status": "confirmation_request", "confirmation_id": identifier, "target": str(target), "preview": content.decode("utf-8")})
            return 0
        if args.command == "artifact-apply":
            source = regular(Path(args.input), "artifact input")
            content = source.read_bytes()
            target = workspace_target(args.target)
            consume(args.confirmation_id, {"kind": "artifact", "target": args.target, "content": content.decode("utf-8")})
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic(target, content)
            emit({"status": "ok", "target": str(target)})
            return 0
        return fail("invalid_command", "a supported subcommand is required")
    except WorkflowError as exc:
        code = "setup_required" if str(exc).startswith("setup-required:") else "invalid_input"
        return fail(code, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
