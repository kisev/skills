"""Exercise packed plugins with every OpenCode CLI pinned in Mise."""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_release_artifacts import command  # noqa: E402


def main() -> None:
    mise = shutil.which("mise")
    node = shutil.which("node")
    if not mise or not node:
        raise RuntimeError("Mise and Node are required")
    tools = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))["tools"]
    for backend, script in (
        ("npm:@opencode/cli", "test/smoke.mjs"),
        ("npm:@opencode/cli", "test/smoke-v2.mjs"),
        ("npm:@opencode/cli", "../../apps/memomatic/test/smoke-v2.mjs"),
    ):
        version = tools[backend]["version"]
        binary = command(mise, "which", "--tool", f"{backend}@{version}", "opencode").strip()
        print(f"Checking OpenCode {version}", flush=True)
        print(
            command(
                node,
                script,
                cwd=ROOT / "packages/agentomatic",
                env={**os.environ, "OPENCODE_BINARY": binary},
            ),
            end="",
        )


if __name__ == "__main__":
    main()
