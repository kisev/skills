from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart() -> None:
    if not (ROOT / ".build/skills").is_dir():
        raise RuntimeError("built skills are missing; run task build:skills first")
