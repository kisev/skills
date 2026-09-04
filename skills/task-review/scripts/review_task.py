#!/usr/bin/env python3
"""Run portable read-only GitLab metadata collection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portable_runtime.contract import run


if __name__ == "__main__":
    raise SystemExit(run("task-review", {"issues", "merge_requests"}))
