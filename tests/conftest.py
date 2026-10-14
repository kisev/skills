from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def pytest_sessionstart() -> None:
    if not (ROOT / ".build/skills").is_dir():
        # A missing build self-heals instead of failing every collected test
        # with an "ERROR at setup" wall; the build is idempotent and fast.
        # When even the rebuild fails, exit once with the exact command.
        rebuilt = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_skills.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if rebuilt.returncode != 0 or not (ROOT / ".build/skills").is_dir():
            pytest.exit(
                "built skills are missing and the automatic rebuild failed;"
                " run task skills:build and inspect its output:\n"
                f"{rebuilt.stdout}\n{rebuilt.stderr}",
                returncode=4,
            )
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
