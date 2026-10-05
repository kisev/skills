"""Make the src-layout package and the test helpers importable from any root."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE.parent / "src"
for entry in (str(SRC), str(BASE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)
