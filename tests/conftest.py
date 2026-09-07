from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart() -> None:
    subprocess.run(
        [sys.executable, "scripts/build_skills.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
