#!/usr/bin/env python3
"""Validate explicit team context and apply confirmed local artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

MAX_BYTES = 2 * 1024 * 1024
TTL_SECONDS = 600
FIXED_ACTION = "retro"
FORBIDDEN = frozenset({"credentials", "tokens", "password", "secret", "personal_notes"})


class WorkflowError(ValueError):
    """Expected safe workflow failure."""


class ContractArgumentParser(argparse.ArgumentParser):
    """Return invalid CLI input through the JSON runner contract."""

    def error(self, message: str) -> None:
        raise WorkflowError(message)

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


def assert_safe_context(value: dict[str, Any]) -> None:
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


def validate_context(value: dict[str, Any]) -> dict[str, Any]:
    assert_safe_context(value)
    missing = context_missing(value)
    if missing:
        raise WorkflowError("setup-required: " + ", ".join(missing))
    return value


def context_missing(value: dict[str, Any]) -> list[str]:
    required = ("goals", "scope", "cadence", "baseline", "projects", "delivery_signals")
    return [key for key in required if key not in value or value[key] in (None, "", [], {})]


def valid_name(value: str) -> str:
    if not value or len(value) > 63 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value):
        raise WorkflowError("context name is invalid")
    return value


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_once(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if regular(path, "prepared plan").read_bytes() != content:
            raise WorkflowError("prepared plan digest conflicts with existing artifact")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def prepare_plan(payload: dict[str, Any]) -> tuple[str, Path, float]:
    plan_digest = digest(payload)
    path = private_directory(state_root() / "plans") / f"{plan_digest}.json"
    if path.exists():
        document, _ = read_json(path, "prepared plan")
        expires_at = document.get("expires_at")
        if document.get("digest") != plan_digest or not isinstance(expires_at, (int, float)):
            raise WorkflowError("prepared plan is invalid")
        return plan_digest, path, expires_at
    expires_at = time.time() + TTL_SECONDS
    document = {
        "schema_version": 1,
        "digest": plan_digest,
        "expires_at": expires_at,
        "payload": payload,
    }
    write_once(path, canonical_bytes(document))
    return plan_digest, path, expires_at


def consume(plan_digest: str, payload: dict[str, Any]) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", plan_digest):
        raise WorkflowError("preview digest is invalid")
    path = regular(state_root() / "plans" / f"{plan_digest}.json", "prepared plan")
    document, _ = read_json(path, "prepared plan")
    if document.get("digest") != plan_digest or document.get("payload") != payload or digest(payload) != plan_digest:
        raise WorkflowError("prepared plan changed or digest does not match")
    if not isinstance(document.get("expires_at"), (int, float)) or document["expires_at"] < time.time():
        raise WorkflowError("prepared plan is stale or expired")
    receipt = private_directory(state_root() / "receipts") / f"{plan_digest}.json"
    try:
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise WorkflowError("prepared plan is already consumed") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_bytes({"digest": plan_digest, "consumed_at": time.time()}))
        handle.flush()
        os.fsync(handle.fileno())


def report(plan_digest: str, result: dict[str, object]) -> tuple[Path, str]:
    document = {"schema_version": 1, "digest": plan_digest, "result": result, "checks": ["digest", "expiry", "single_use", "safe_path"]}
    report_digest = digest(document)
    path = private_directory(state_root() / "reports") / f"{report_digest}.json"
    write_once(path, canonical_bytes(document))
    return path, report_digest


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
    parser = ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    check = subparsers.add_parser("action-check")
    check.add_argument("--context-file")
    check.add_argument("--context-name")
    check.add_argument("--chat-input")
    inspect = subparsers.add_parser("context-inspect")
    inspect.add_argument("--input", required=True)
    subparsers.add_parser("context-list")
    show = subparsers.add_parser("context-show")
    show.add_argument("--name", required=True)
    prepare = subparsers.add_parser("context-prepare")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--name", required=True)
    save = subparsers.add_parser("context-save")
    save.add_argument("--name", required=True)
    save.add_argument("--input", required=True)
    save.add_argument("--digest", required=True)
    artifact_prepare = subparsers.add_parser("artifact-prepare")
    artifact_prepare.add_argument("--target", required=True)
    artifact_prepare.add_argument("--input", required=True)
    artifact_apply = subparsers.add_parser("artifact-apply")
    artifact_apply.add_argument("--target", required=True)
    artifact_apply.add_argument("--input", required=True)
    artifact_apply.add_argument("--digest", required=True)
    try:
        args = parser.parse_args(argv)
    except WorkflowError as exc:
        return fail("invalid_input", str(exc))
    if args.capabilities:
        emit({"schema_version": 1, "payload_version": "1.0.0", "mutation": "local-write-confirmed", "dry_run": True, "state_protocol": "digest-bound-preview", "external_tools": {}, "destructive_flags": ["context-save", "artifact-apply"]})
        return 0
    try:
        if args.command == "action-check":
            context, _, source = load_context(args)
            emit({"status": "ok", "action": FIXED_ACTION, "context_source": source, "projects": len(context["projects"]), "external_mutations": False})
            return 0
        if args.command == "context-inspect":
            context, _ = read_json(Path(args.input), "context input")
            assert_safe_context(context)
            missing = context_missing(context)
            emit({"status": "ok" if not missing else "setup-required", "context": context, "missing": missing, "external_mutations": False})
            return 0 if not missing else 3
        if args.command == "context-list":
            root = state_root() / "contexts"
            names = []
            if root.exists():
                if root.is_symlink() or not root.is_dir():
                    raise WorkflowError("contexts directory is unsafe")
                for path in sorted(root.iterdir()):
                    if path.suffix == ".json" and path.is_file() and not path.is_symlink():
                        names.append(path.stem)
            emit({"status": "ok", "contexts": names, "external_mutations": False})
            return 0
        if args.command == "context-show":
            name = valid_name(args.name)
            context, _ = read_json(state_root() / "contexts" / f"{name}.json", "saved context")
            emit({"status": "ok", "name": name, "context": validate_context(context), "external_mutations": False})
            return 0
        if args.command == "context-prepare":
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            valid_name(args.name)
            payload = {"kind": "context", "name": args.name, "content": raw.decode("utf-8")}
            plan_digest, path, expires_at = prepare_plan(payload)
            emit({"status": "prepared", "summary": {"tldr": "Saving explicit team context.", "scope": [args.name], "risks": [], "checks": ["context validation", "safe state path"]}, "artifact_path": str(path), "digest": plan_digest, "expires_at": expires_at, "ttl_seconds": TTL_SECONDS, "apply_command": f"context-save --name {args.name} --input {args.input} --digest {plan_digest}"})
            return 0
        if args.command == "context-save":
            valid_name(args.name)
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            payload = {"kind": "context", "name": args.name, "content": raw.decode("utf-8")}
            consume(args.digest, payload)
            root = private_directory(state_root() / "contexts")
            atomic(root / f"{args.name}.json", raw)
            report_path, report_digest = report(args.digest, {"status": "applied", "name": args.name})
            emit({"status": "applied", "summary": {"tldr": "Context saved.", "scope": [args.name], "risks": [], "checks": ["digest", "expiry", "single_use", "safe_path"]}, "report_path": str(report_path), "report_digest": report_digest})
            return 0
        if args.command == "artifact-prepare":
            source = regular(Path(args.input), "artifact input")
            content = source.read_bytes()
            target = workspace_target(args.target)
            payload = {"kind": "artifact", "target": args.target, "content": content.decode("utf-8")}
            plan_digest, path, expires_at = prepare_plan(payload)
            emit({"status": "prepared", "summary": {"tldr": "Writing local artifact.", "scope": [str(target)], "risks": ["existing file will be replaced"] if target.exists() else [], "checks": ["regular input", "safe workspace path"]}, "artifact_path": str(path), "digest": plan_digest, "expires_at": expires_at, "ttl_seconds": TTL_SECONDS, "apply_command": f"artifact-apply --target {args.target} --input {args.input} --digest {plan_digest}"})
            return 0
        if args.command == "artifact-apply":
            source = regular(Path(args.input), "artifact input")
            content = source.read_bytes()
            target = workspace_target(args.target)
            consume(args.digest, {"kind": "artifact", "target": args.target, "content": content.decode("utf-8")})
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic(target, content)
            report_path, report_digest = report(args.digest, {"status": "applied", "target": str(target)})
            emit({"status": "applied", "summary": {"tldr": "Artifact written.", "scope": [str(target)], "risks": [], "checks": ["digest", "expiry", "single_use", "safe_path"]}, "report_path": str(report_path), "report_digest": report_digest})
            return 0
        return fail("invalid_command", "a supported subcommand is required")
    except WorkflowError as exc:
        code = "setup_required" if str(exc).startswith("setup-required:") else "invalid_input"
        return fail(code, str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
