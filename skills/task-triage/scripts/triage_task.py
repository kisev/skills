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
    portable_runtime = Path(__file__).resolve().parent / "portable_runtime" / "triage.py"
    if portable_runtime.is_file():
        from portable_runtime.triage import run
    else:
        source_root = Path(__file__).resolve().parents[3]
        source_runtime = source_root / "shared" / "references" / "work_item_runtime" / "triage.py"
        if not source_runtime.is_file():
            raise ImportError("task-triage runtime is unavailable")
        sys.path.insert(0, str(source_root))
        from shared.references.work_item_runtime.triage import run


if __name__ == "__main__":
    raise SystemExit(run())
