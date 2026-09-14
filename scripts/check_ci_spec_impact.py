#!/usr/bin/env python3
"""Resolve and enforce the specification impact range for one CI event."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_specs import main as check_specs  # noqa: E402
from scripts.resolve_spec_impact import load_event, resolve_range  # noqa: E402


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if not event_path:
        raise SystemExit("GITHUB_EVENT_PATH is required")
    resolved = resolve_range(
        load_event(Path(event_path)),
        event_name,
        ROOT,
        os.environ.get("GITHUB_SHA"),
    )
    return check_specs(["--range", resolved["base"], resolved["head"]])


if __name__ == "__main__":
    raise SystemExit(main())
