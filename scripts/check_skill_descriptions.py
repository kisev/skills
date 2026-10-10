#!/usr/bin/env python3
"""Check every skill description carries a trigger and fits the hard cap.

Complementary static check for `skills:validate`: agentskills validates the
frontmatter shape, this check enforces the discovery contract — a description
must name when to use the skill (a "Use when"-style trigger) and must stay
within the 1024-character description budget.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_DESCRIPTION_LENGTH = 1024
TRIGGER_MARKERS = (
    "Use when",
    "Use this",
    "Use for",
    "Use only",
    "Use before",
    "Load only",
    "Activate yourself",
)
DESCRIPTION = re.compile(r"^description: >-\n((?:  .*\n)+?)(?=\S)", re.MULTILINE)


def check(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    sources = sorted((root / "skills").glob("*/SKILL.source.md"))
    if not sources:
        return ["no SKILL.source.md files found"]
    for source in sources:
        frontmatter = source.read_text(encoding="utf-8").split("---", 2)[1]
        match = DESCRIPTION.search(frontmatter)
        if match is None:
            problems.append(f"{source.parent.name}: description block not found")
            continue
        description = " ".join(line.strip() for line in match.group(1).splitlines())
        if len(description) > MAX_DESCRIPTION_LENGTH:
            problems.append(
                f"{source.parent.name}: description is {len(description)} characters "
                f"(limit {MAX_DESCRIPTION_LENGTH})"
            )
        if not any(marker in description for marker in TRIGGER_MARKERS):
            problems.append(
                f"{source.parent.name}: description carries no trigger "
                f"(expected one of {', '.join(TRIGGER_MARKERS)})"
            )
    return problems


def main() -> int:
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} description contract violation(s)", file=sys.stderr)
        return 1
    print("Every skill description carries a trigger within the length cap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
