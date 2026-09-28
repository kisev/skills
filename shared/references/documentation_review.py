#!/usr/bin/env python3
"""Select documentation impact and retain private, snapshot-bound review evidence."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
if TYPE_CHECKING:
    from shared.references.state_artifacts import (
        StateArtifactError,
        archive_bytes,
        canonical_json,
        content_digest,
        ensure_private_directory,
        read_immutable,
        xdg_state_home,
    )
else:
    from state_artifacts import (
        StateArtifactError,
        archive_bytes,
        canonical_json,
        content_digest,
        ensure_private_directory,
        read_immutable,
        xdg_state_home,
    )

VERSION = 1
EXCLUDED = {
    ".git",
    ".build",
    ".venv",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def inventory(root: Path) -> dict[str, str]:
    git = shutil.which("git")
    # Git is optional and resolved through the user's PATH; all arguments are fixed.
    result = (
        subprocess.run(  # noqa: S603
            [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=False,
        )
        if git
        else None
    )
    names = (
        (set(os.fsdecode(result.stdout).split("\0")) - {""})
        if result and result.returncode == 0
        else {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if not EXCLUDED.intersection(path.relative_to(root).parts) and path.is_file()
        }
    )
    snapshot = {}
    for name in sorted(names):
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"review source must not escape or be a symlink: {name}")
        if path.is_file():
            snapshot[name] = content_digest(path.read_bytes())
    return snapshot


def safe_pattern(value: str) -> bool:
    return (
        bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and ".." not in value.split("/")
    )


def read_annotations(root: Path, snapshot: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    records = {}
    for name in snapshot:
        if not name.endswith(".md"):
            continue
        text = (root / name).read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        frontmatter = text.split("---", 2)
        for line in frontmatter[1].splitlines():
            if not line.startswith("review:"):
                continue
            value = json.loads(line.removeprefix("review:").strip())
            if not isinstance(value, dict) or set(value) != {"components", "sources", "contracts"}:
                raise ValueError(f"{name}: review metadata requires components, sources, contracts")
            for field, items in value.items():
                if not isinstance(items, list) or not all(
                    isinstance(item, str) and item for item in items
                ):
                    raise ValueError(f"{name}: {field} must contain nonempty strings")
            if not value["components"]:
                raise ValueError(f"{name}: components must not be empty")
            for pattern in value["sources"] + value["contracts"]:
                if not safe_pattern(pattern) or not any(
                    fnmatch.fnmatchcase(path, pattern) for path in snapshot
                ):
                    raise ValueError(f"{name}: missing or unsafe dependency {pattern}")
            records[name] = value
    return records


def affected_documents(
    records: dict[str, dict[str, list[str]]], changed: set[str]
) -> tuple[list[str], list[str]]:
    affected = set(changed.intersection(records))
    covered = set(affected)
    while True:
        previous = set(affected)
        for name, record in records.items():
            for path in changed | affected:
                if any(
                    fnmatch.fnmatchcase(path, pattern)
                    for pattern in record["sources"] + record["contracts"]
                ):
                    affected.add(name)
                    covered.add(path)
        if affected == previous:
            break
    return sorted(affected), sorted(changed - covered)


def state_root(root: Path, scope: str) -> Path:
    key = content_digest(canonical_json([str(root), scope]))
    state = xdg_state_home() / "agent-skills" / "documentation-review" / key
    if state.is_relative_to(root):
        raise ValueError("review state must be outside the reviewed workspace")
    return state


def load_state(path: Path, state: Path) -> dict[str, Any]:
    if not path.is_relative_to(state):
        raise ValueError("review record is outside its workspace state")
    data = read_immutable(path, state)
    if path.stem != content_digest(data):
        raise ValueError("review record digest does not match its name")
    value = json.loads(data)
    if not isinstance(value, dict) or value.get("version") != VERSION:
        raise ValueError("unsupported review record")
    return value


def latest(state: Path) -> tuple[Path | None, dict[str, Any] | None]:
    choices = [
        (path, load_state(path, state))
        for path in (state / "history" / "review-result").glob("*.json")
    ]
    return max(choices, key=lambda item: item[1]["created_ns"], default=(None, None))


def prepare(root: Path, scope: str, session: str, full: bool = False) -> dict[str, Any]:
    if scope != "." and not safe_pattern(scope):
        raise ValueError("scope must be a relative workspace path")
    snapshot = inventory(root)
    records = read_annotations(root, snapshot)
    state = state_root(root, scope)
    prior_path, prior = latest(state)
    prior_snapshot = prior["snapshot"] if prior else {}
    changed = {
        path
        for path in snapshot.keys() | prior_snapshot.keys()
        if snapshot.get(path) != prior_snapshot.get(path)
    }
    if prior is None:
        changed.clear()
    affected, unowned = affected_documents(records, changed)
    documents = sorted(
        path
        for path in snapshot
        if path.endswith(".md")
        and (scope in {".", path} or path.startswith(scope.rstrip("/") + "/"))
    )
    if not documents:
        raise ValueError("scope contains no Markdown documents")
    mode = "full" if full or prior is None else "incremental" if changed else "unchanged"
    unresolved = set(prior["report"]["unverified"]) if prior else set()
    selected = (
        documents
        if mode == "full"
        else sorted(set(documents).intersection(set(affected) | changed | unresolved))
    )
    if prior is None:
        unowned = sorted(set(documents) - records.keys())
    pending = {
        "version": VERSION,
        "root": str(root),
        "scope": scope,
        "session": session,
        "mode": mode,
        "critic_required": mode == "full"
        or bool(
            prior
            and prior.get("critic_required")
            and prior["report"]["critic"]["status"] != "complete"
        ),
        "snapshot": snapshot,
        "documents": documents,
        "selected": selected,
        "changed": sorted(changed),
        "unmapped": unowned,
        "previous": str(prior_path) if prior_path else None,
        "created_ns": time.time_ns(),
    }
    ensure_private_directory(state, state)
    path = archive_bytes(state, "review-pending", ".json", canonical_json(pending))
    return {
        "mode": mode,
        "record": str(path),
        "previous": pending["previous"],
        "selected": selected,
        "changed": pending["changed"],
        "unmapped": unowned,
        "critic_required": pending["critic_required"],
        "limitation": "Dependencies select evidence; unmapped changes require semantic impact assessment, not automatic exclusion.",
    }


def finalize(root: Path, scope: str, pending_path: Path, report: dict[str, Any]) -> dict[str, Any]:
    state = state_root(root, scope)
    pending = load_state(pending_path, state)
    if (
        pending["root"] != str(root)
        or pending["scope"] != scope
        or pending["snapshot"] != inventory(root)
    ):
        raise ValueError("review evidence changed; prepare a fresh review")
    previous_path, previous = latest(state)
    if pending["previous"] != (str(previous_path) if previous_path else None):
        raise ValueError("review baseline changed; prepare a fresh review")
    required = {"checked", "unverified", "findings", "decisions", "impact", "critic", "checks"}
    if set(report) != required or not all(
        isinstance(report[field], list) for field in required - {"critic", "impact"}
    ):
        raise ValueError(
            "report requires checked, unverified, findings, decisions, impact, critic, checks"
        )
    if not all(
        isinstance(path, str) and path in pending["documents"]
        for path in report["checked"] + report["unverified"]
    ):
        raise ValueError("checked and unverified must identify scoped documents")
    if not set(pending["selected"]).issubset(set(report["checked"] + report["unverified"])):
        raise ValueError("every selected document needs a disposition")
    impact = report["impact"]
    if (
        not isinstance(impact, dict)
        or not set(pending["unmapped"]).issubset(impact)
        or not all(isinstance(reason, str) and reason.strip() for reason in impact.values())
    ):
        raise ValueError("every unmapped change needs a concrete impact assessment")
    ids = set()
    for finding in report["findings"]:
        if (
            not isinstance(finding, dict)
            or not isinstance(finding.get("id"), str)
            or finding["id"] in ids
            or finding.get("status")
            not in {"open", "fixed", "accepted_risk", "deferred", "rejected"}
            or not finding.get("evidence")
        ):
            raise ValueError("findings require unique IDs, dispositions, and evidence")
        ids.add(finding["id"])
    if previous and not {item["id"] for item in previous["report"]["findings"]}.issubset(ids):
        raise ValueError("previous findings must retain their IDs and dispositions")
    critic = report["critic"]
    if not isinstance(critic, dict) or critic.get("status") not in {
        "complete",
        "not_checked",
        "not_required",
    }:
        raise ValueError("critic must declare its actual status")
    complete_critic = (
        critic["status"] == "complete"
        and bool(critic.get("session"))
        and critic["session"] != pending["session"]
    )
    if critic["status"] == "complete" and not complete_critic:
        raise ValueError("critic must use an independent session")
    for check in report["checks"]:
        if (
            not isinstance(check, dict)
            or check.get("status") not in {"passed", "failed", "not_checked"}
            or not isinstance(check.get("required"), bool)
            or not check.get("evidence")
        ):
            raise ValueError("checks need actual status, required flag, and evidence")
    partial = (
        bool(report["unverified"])
        or (pending["critic_required"] and not complete_critic)
        or any(check["required"] and check["status"] != "passed" for check in report["checks"])
    )
    outcome = (
        "partial"
        if partial
        else "findings"
        if any(item["status"] == "open" for item in report["findings"])
        else "clean"
    )
    result = {**pending, "created_ns": time.time_ns(), "report": report, "outcome": outcome}
    path = archive_bytes(state, "review-result", ".json", canonical_json(result))
    return {
        "outcome": outcome,
        "record": str(path),
        "limitation": "Retained evidence is not proof of semantic correctness.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "prepare", "finalize"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scope", default=".")
    parser.add_argument("--session")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--record", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        if args.command == "check":
            records = read_annotations(root, inventory(root))
            result: dict[str, Any] = {
                "status": "valid",
                "annotated_documents": sorted(records),
                "limitation": "Metadata validation does not prove semantic consistency or complete coverage.",
            }
        elif args.command == "prepare":
            if not args.session:
                raise ValueError(
                    "prepare requires --session with the current host session identity"
                )
            result = prepare(root, args.scope, args.session, args.full)
        else:
            if args.record is None or args.report is None:
                raise ValueError("finalize requires --record and --report")
            result = finalize(
                root,
                args.scope,
                args.record.absolute(),
                json.loads(args.report.read_text(encoding="utf-8")),
            )
    except (ValueError, OSError, StateArtifactError) as error:
        print(json.dumps({"status": "error", "message": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
