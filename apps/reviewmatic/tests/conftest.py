"""Make the src-layout package and the test helpers importable from any root."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE.parent / "src"
for entry in (str(SRC), str(BASE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

ROOT = BASE.parents[2]


def pytest_sessionstart() -> None:
    # Tests isolate XDG state per AGENTS.md; mise shims (jq, node, python)
    # resolve their trust cache from that isolated state and refuse to run
    # (mise 2026.10.8 checks trust on every shim execution). Re-trust the
    # repository and global mise configs for the session instead of weakening
    # the isolation; an explicitly exported value always wins.
    trusted = [
        str(ROOT),
        str(Path.home() / ".config" / "mise" / "config.toml"),
    ]
    existing = os.environ.get("MISE_TRUSTED_CONFIG_PATHS")
    if existing:
        trusted.append(existing)
    os.environ["MISE_TRUSTED_CONFIG_PATHS"] = os.pathsep.join(trusted)
