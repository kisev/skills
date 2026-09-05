#!/usr/bin/env python3
"""Build a read-only, partial-tolerant OpenCode state summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

scripts = Path(__file__).resolve().parent
if str(scripts) not in sys.path:
    sys.path.insert(0, str(scripts))

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error
from portable_runtime.lsp import detect
from portable_runtime.state import StateError, read_json, skill_state_root


def read_component(name: str, root: Path, matcher: str, project: str, selector: Any) -> dict[str, Any]:
    paths: list[str] = []
    values: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if not root.is_dir() or root.is_symlink():
        return {"status": "absent", "source_paths": [str(root)], "data": {name: values}}
    for path in sorted(root.glob(matcher)):
        paths.append(str(path))
        try:
            value = read_json(path, root)
            if value.get("schema_version") != 1:
                raise StateError("unsupported schema_version")
            selected = selector(value, project)
            if selected is not None:
                values.append(selected)
        except StateError as error:
            errors.append({"path": str(path), "error": str(error)})
    return {"status": "partial" if errors else "ok", "source_paths": paths, "data": {name: values, "errors": errors}}


def build(root: Path) -> dict[str, Any]:
    project = str(root.resolve())
    goal = read_component("goals", skill_state_root("goal"), "*.json", project, lambda value, scope: {key: value.get(key) for key in ("goal_id", "session_id", "status", "revision", "updated_at", "objective")} if value.get("project_root") in {"", scope} else None)
    attempt = read_component("attempts", skill_state_root("attempt") / "attempts", "*.json", project, lambda value, scope: {key: value.get(key) for key in ("attempt_id", "parent_session_id", "child_session_id", "status", "revision", "workspace_id")} if value.get("project") == scope else None)
    multi = read_component("groups", skill_state_root("multi-run"), "*.json", project, lambda value, scope: {"multi_run_id": value.get("multi_run_id"), "status": value.get("status"), "attempts": len(value.get("runs", [])) if isinstance(value.get("runs"), list) else None} if value.get("project_root") == scope else None)
    schedule_root = skill_state_root("schedule") / hashlib.sha256(project.encode()).hexdigest() / "definitions"
    schedule = read_component("definitions", schedule_root, "*.json", project, lambda value, _scope: {key: value.get(key) for key in ("id", "name", "schedule", "enabled")})
    lsp = detect(root)
    goals = goal["data"]["goals"]
    counts = {status: sum(item.get("status") == status for item in attempt["data"]["attempts"]) for status in ("queued", "running", "waiting", "completed", "failed", "cancelled", "orphaned")}
    return {"root": project, "status": "partial" if any(item["status"] == "partial" for item in (goal, attempt, multi, schedule)) else "ok", "components": {"goal": goal, "attempts": attempt, "multi_run": multi, "schedule": schedule, "lsp": {"status": lsp["status"], "data": lsp}}, "signals": {"active_goals": sum(item.get("status") == "running" for item in goals), "paused_goals": sum(item.get("status") == "paused" for item in goals), "attempts": counts, "lsp_unavailable": [item["name"] for item in lsp.get("servers", []) if item.get("applicable") and not item.get("active")]}}


def projects(args: argparse.Namespace) -> list[Path]:
    if not args.all:
        return [Path(args.project or os.environ.get("OPENCODE_PROJECT_ROOT") or os.getcwd()).expanduser().resolve()]
    registry = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode" / "projects.json"
    try:
        value = json.loads(registry.read_text(encoding="utf-8"))
        roots = value.get("project_roots") if isinstance(value, dict) and value.get("schema_version") == 1 else None
        if not isinstance(roots, list) or not all(isinstance(item, str) and Path(item).is_absolute() for item in roots):
            raise ValueError("unsupported project registry")
        return [Path(item).resolve() for item in roots]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read project registry: {error}") from error


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="overview")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--project")
    result.add_argument("--all", action="store_true")
    result.add_argument("--format", choices=("json", "text", "both"), default="text")
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="read", supports_dry_run=False):
        return 0
    try:
        args = cli.parse_args(argv)
        values = [build(path) if path.is_dir() and not path.is_symlink() else {"root": str(path), "status": "error", "error": "project root is not a directory", "components": {}, "signals": {}} for path in projects(args)]
    except ValueError as error:
        report_error("invalid_arguments", str(error))
        return 2
    text = "\n".join(f"{item['root']}: {item['signals'].get('active_goals', 0)} active goals" if item["status"] != "error" else f"{item['root']}: unavailable" for item in values)
    output = {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "projects": values, "text": text}
    if args.format in {"json", "both"}:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    if args.format in {"text", "both"}:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
