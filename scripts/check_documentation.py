#!/usr/bin/env python3
"""Check the public documentation inventory against authored public surfaces."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def validate(root: Path = ROOT) -> None:
    inventory = json.loads((root / "evals/contracts/public-surfaces.json").read_text())
    package = json.loads((root / "packages/agentomatic/package.json").read_text())
    registry = (root / "packages/agentomatic/src/registry.ts").read_text()
    names = re.search(r"const SKILL_NAMES = \[(.*?)\]", registry, re.DOTALL)
    if names is None:
        raise ValueError("command adapter registry is missing")
    adapters = set(re.findall(r'"([a-z0-9-]+)"', names.group(1)))
    actual = {
        "skills": {path.parent.name for path in (root / "skills").glob("*/SKILL.source.md")},
        "commands": adapters | set(re.findall(r'name: "([a-z0-9-]+)"', registry)),
        "plugins": {
            name.removeprefix("./plugins/")
            for name in package["exports"]
            if name.startswith("./plugins/")
        },
        "agents": {
            path.stem for path in (root / "packages/agentomatic/assets/agents").glob("*.md")
        },
    }
    index = (root / "specs/capabilities/README.md").read_text()
    for kind, nameset in actual.items():
        if nameset != set(inventory[kind]):
            raise ValueError(f"{kind}: authored surface differs from inventory")
        for name in nameset:
            record = f"{kind}/{name}.md"
            if not (root / "specs/capabilities" / record).is_file() or f"]({record})" not in index:
                raise ValueError(f"missing canonical capability or index link: {record}")
    for path in ("docs/reference/skill-catalog.md", "docs/ru/reference/skill-catalog.md"):
        documented = set(
            re.findall(r"^\| `([a-z0-9-]+)` \|", (root / path).read_text(), re.MULTILINE)
        )
        if documented != actual["skills"]:
            raise ValueError(f"skill catalog differs from authored skills: {path}")


if __name__ == "__main__":
    validate()
    print("Public catalogs, capability records, and source inventories agree.")
