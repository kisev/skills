#!/usr/bin/env python3
"""Run portable release merge request preparation collection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portable_runtime.contract import run


if __name__ == "__main__":
    raise SystemExit(run("release-prepare", {"merge_requests"}))
