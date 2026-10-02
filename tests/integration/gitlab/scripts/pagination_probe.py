"""Invoke the shipped Python pager against real fixture resource endpoints."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
source = json.loads(Path(sys.argv[1]).read_text())
sys.path.insert(0, str(ROOT / ".build/skills" / source["skill"] / "scripts"))
module = importlib.import_module(
    "portable_runtime.triage" if source["skill"] == "task-triage" else "portable_runtime.contract"
)

results = {}
for name, endpoint in source["endpoints"].items():
    value = module.paginated("localhost", endpoint)
    if isinstance(value, list):
        results[name] = {"items": value, "complete": True}
    else:
        results[name] = value
print(json.dumps(results))
