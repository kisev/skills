#!/usr/bin/env python3
"""Validate one shared task release-planning sidecar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.references.work_item_runtime.release_planning import PlanningError, validate
else:
    from portable_runtime.release_planning import PlanningError, validate


def object_file(value: str, label: str) -> dict[str, object]:
    source = Path(value)
    if source.is_symlink() or not source.is_file():
        raise PlanningError(f"{label} must be a regular non-symlink file")
    path = source.resolve()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise PlanningError(f"{label} must contain one JSON object")
    return raw


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="release-plan")
    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--quality-verdict", choices=("ready", "needs_clarification", "blocked"), required=True
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--current-milestone-id", type=int)
    args = parser.parse_args(argv)
    try:
        plan = object_file(args.input, "release plan")
        catalog_value = object_file(args.catalog, "milestone catalog")
        catalog = catalog_value.get("milestones")
        if not isinstance(catalog, list) or not all(isinstance(item, dict) for item in catalog):
            raise PlanningError("milestone catalog must contain a milestones list")
        result = validate(
            plan,
            quality_verdict=args.quality_verdict,
            milestone_catalog=catalog,
            current_milestone_id=args.current_milestone_id,
        )
        print(json.dumps({"status": "ok", **result}, ensure_ascii=False, sort_keys=True))
        return {"ready": 0, "needs_clarification": 1, "blocked": 2}[result["planning_verdict"]]
    except (OSError, UnicodeError, json.JSONDecodeError, PlanningError) as exc:
        print(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, sort_keys=True)
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
