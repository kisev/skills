"""Cross-check authored skill surfaces against the public inventory and catalog.

The authored authority is the ``skills/`` tree itself: every directory with a
``SKILL.source.md`` is a skill, and every skill without the
``metadata.command: "false"`` opt-out owns a thin command adapter generated
by skillmate. The committed inventory and the bilingual catalog must match
that authority exactly.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def authored_skills(root: Path) -> set[str]:
    return {path.parent.name for path in (root / "skills").glob("*/SKILL.source.md")}


def authored_commands(root: Path) -> set[str]:
    commands = set()
    for path in (root / "skills").glob("*/SKILL.source.md"):
        text = path.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
        if re.search(r'^\s+command:\s*"false"\s*$', frontmatter, re.MULTILINE):
            continue
        commands.add(path.parent.name)
    return commands


def validate(root: Path = ROOT) -> None:
    inventory = json.loads((root / "evals/contracts/public-surfaces.json").read_text())
    actual = {"skills": authored_skills(root), "commands": authored_commands(root)}
    for kind, nameset in actual.items():
        if set(inventory[kind]) != nameset:
            raise ValueError(f"{kind}: authored surface differs from inventory")
    for path in ("docs/reference/skill-catalog.md", "docs/ru/reference/skill-catalog.md"):
        documented = set(
            re.findall(r"^\| `([a-z0-9-]+)` \|", (root / path).read_text(), re.MULTILINE)
        )
        if documented != actual["skills"]:
            raise ValueError(f"skill catalog differs from authored skills: {path}")


if __name__ == "__main__":
    validate()
