#!/usr/bin/env python3
"""Collect and publish persistent GitLab task-triage artifacts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from shared.references.work_item_runtime.triage import run
else:
    from portable_runtime.triage import run


if __name__ == "__main__":
    raise SystemExit(run())
