#!/usr/bin/env python3
"""Resolve a safe commit range from a GitHub Actions event."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ZERO_SHA = "0" * 40
SHA = re.compile(r"[0-9a-f]{40}\Z")


class RangeError(Exception):
    """A malformed or unsafe event cannot be resolved."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RangeError("unreachable_sha")
    return result.stdout.strip()


def _sha(value: Any, field: str) -> str:
    if value is None:
        raise RangeError("missing_sha")
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise RangeError(f"malformed_{field}")
    if value == ZERO_SHA:
        raise RangeError("zero_sha")
    return value


def _commit(root: Path, value: Any, field: str) -> str:
    sha = _sha(value, field)
    try:
        actual_type = _git(root, "cat-file", "-t", sha)
    except RangeError as error:
        raise RangeError("unreachable_sha") from error
    if actual_type != "commit":
        raise RangeError("unreachable_sha")
    return sha


def _ancestor(root: Path, base: str, head: str, code: str = "unreachable_range") -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head], cwd=root, check=False
    )
    if result.returncode:
        raise RangeError(code)


def _parent(root: Path, head: str) -> str:
    try:
        parent = _git(root, "rev-parse", "--verify", f"{head}^1")
    except RangeError as error:
        raise RangeError("root_commit") from error
    if not SHA.fullmatch(parent) or parent == ZERO_SHA:
        raise RangeError("root_commit")
    return _commit(root, parent, "parent")


def _tag_head(root: Path, event_after: Any, github_sha: str | None) -> str:
    after = _sha(event_after, "after")
    try:
        object_type = _git(root, "cat-file", "-t", after)
    except RangeError as error:
        raise RangeError("unreachable_sha") from error
    if object_type == "commit":
        event_head = after
    elif object_type == "tag":
        event_head = _commit(
            root, _git(root, "rev-parse", "--verify", f"{after}^{{commit}}"), "head"
        )
    else:
        raise RangeError("unreachable_sha")
    if github_sha is None:
        return event_head
    head = _commit(root, github_sha, "github_head")
    if head != event_head:
        raise RangeError("head_mismatch")
    return head


def resolve_range(
    event: dict[str, Any],
    event_name: str,
    root: Path = ROOT,
    github_sha: str | None = None,
) -> dict[str, str]:
    """Resolve and validate the exact base/head pair for one Actions event."""
    if not isinstance(event, dict) or event_name not in {"pull_request", "push"}:
        raise RangeError("unknown_event")

    if event_name == "pull_request":
        pull_request = event.get("pull_request")
        if not isinstance(pull_request, dict):
            raise RangeError("missing_pull_request")
        base_data = pull_request.get("base")
        head_data = pull_request.get("head")
        if not isinstance(base_data, dict) or not isinstance(head_data, dict):
            raise RangeError("missing_sha")
        base = _commit(root, base_data.get("sha"), "base")
        head = _commit(root, head_data.get("sha"), "head")
        return {
            "schema": "spec-impact-range/v1",
            "status": "resolved",
            "event": event_name,
            "kind": "pull_request",
            "base": base,
            "head": head,
        }

    ref = event.get("ref")
    if not isinstance(ref, str):
        raise RangeError("missing_ref")
    before = event.get("before")
    if ref.startswith("refs/tags/"):
        head = _tag_head(root, event.get("after"), github_sha)
        parent = _parent(root, head)
        remote_main = _commit(
            root, _git(root, "rev-parse", "--verify", "refs/remotes/origin/main"), "origin_main"
        )
        _ancestor(root, head, remote_main, "tag_unreachable")
        return {
            "schema": "spec-impact-range/v1",
            "status": "resolved",
            "event": event_name,
            "kind": "tag",
            "base": parent,
            "head": head,
        }
    if not ref.startswith("refs/heads/"):
        raise RangeError("unknown_ref")
    head = _commit(root, event.get("after"), "head")
    if github_sha is not None and head != _commit(root, github_sha, "github_head"):
        raise RangeError("head_mismatch")
    if before == ZERO_SHA:
        config = json.loads((ROOT / "scripts/spec_gate_config.json").read_text(encoding="utf-8"))
        base = _commit(root, config.get("bootstrap_boundary"), "bootstrap_boundary")
        _ancestor(root, base, head)
        kind = "branch_bootstrap"
    else:
        base = _commit(root, before, "base")
        _ancestor(root, base, head)
        kind = "branch"
    return {
        "schema": "spec-impact-range/v1",
        "status": "resolved",
        "event": event_name,
        "kind": kind,
        "base": base,
        "head": head,
    }


def load_event(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RangeError("malformed_event") from error
    if not isinstance(value, dict):
        raise RangeError("malformed_event")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--event-file", type=Path, default=Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    )
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--repository", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = resolve_range(
            load_event(args.event_file),
            args.event_name,
            args.repository,
            os.environ.get("GITHUB_SHA"),
        )
    except RangeError as error:
        print(
            json.dumps(
                {
                    "schema": "spec-impact-range/v1",
                    "status": "error",
                    "error": {"code": error.code},
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
