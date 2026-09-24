#!/usr/bin/env python3
"""Run portable merge request and local WIP review collection."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from shared.references.portable_gitlab.contract import run
else:
    from portable_runtime.contract import run


if __name__ == "__main__":
    import review_workflow

    raise SystemExit(run("code-review", {"merge_requests"}, review_workflow=review_workflow))
