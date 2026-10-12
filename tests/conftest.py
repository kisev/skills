from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart() -> None:
    if not (ROOT / ".build/skills").is_dir():
        raise RuntimeError("built skills are missing; run task build:skills first")
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
