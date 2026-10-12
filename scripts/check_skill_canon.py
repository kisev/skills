#!/usr/bin/env python3
"""Fast source-only canon lint for skill texts.

This is the seconds-scale preselect that runs before builds and heavy tests:
the cyrillic-free English canon and the per-file caps are checked against
authored sources only, so a Cyrillic edit cannot slip through a wave whose
executor runs only application tests. The same rules used to live inside the
root pytest suite; this script is their single home now, and the contract
test invokes the script instead of duplicating the logic.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

# Cyrillic detection range: A-Ya-ya (U+0410-U+044F) plus Yo/yo (U+0401/U+0451).
CYRILLIC = re.compile("[\u0410-\u044f\u0401\u0451]")

# Per-file caps keep reference material bounded; entries map repository
# relative paths to their limit in bytes.
BYTE_CAPS = {
    "skills/spec-manage/references/openspec.md": 16384,
}

# Files whose localized string data is allowed by the AST-scoped exemption
# below; comments and other prose in the same files stay under the contract.
LOCALIZED_STRING_DATA = {
    "skills/mattermost/scripts/mattermost.py",
    "skills/mattermost/scripts/mattermost_cards.py",
    "skills/mattermost/tests/test_mattermost_publication.py",
}


def strip_localized_string_data(text: str) -> str:
    """Blank out localized card string data, keeping source prose checked."""
    tree = ast.parse(text)
    prose = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    localized = {
        segment
        for node in ast.walk(tree)
        if isinstance(node, (ast.Constant, ast.JoinedStr))
        and id(node) not in prose
        and (segment := ast.get_source_segment(text, node))
        and CYRILLIC.search(segment)
    }
    for segment in sorted(localized, key=len, reverse=True):
        text = text.replace(segment, repr("localized card text"))
    return text


def strip_spec_validate_placeholders(text: str) -> str:
    """Blank the PLACEHOLDERS assignment that legitimately lists RU strings."""
    tree = ast.parse(text)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "PLACEHOLDERS" for target in node.targets
        )
    )
    lines = text.splitlines()
    del lines[assignment.lineno - 1 : assignment.end_lineno]
    return "\n".join(lines)


def strip_localized_json_examples(text: str) -> str:
    """Blank fenced JSON examples whose objects declare locale "ru"."""

    def localized_example(match: re.Match[str]) -> str:
        example = json.loads(match.group(1))
        return "" if example.get("locale") == "ru" else match.group(0)

    return re.sub(r"```json\n(.*?)\n```", localized_example, text, flags=re.S)


def skill_source_violations(sources: Path) -> list[str]:
    """Cyrillic-free EN canon for SKILL.source.md files and their workflows."""
    violations: list[str] = []
    for skill in sorted(sources.iterdir()):
        if not skill.is_dir() or not (skill / "SKILL.source.md").is_file():
            continue
        skill_text = (skill / "SKILL.source.md").read_text(encoding="utf-8")
        frontmatter, body = skill_text.split("---", 2)[1:]
        relative = skill.relative_to(sources.parent).as_posix()
        if CYRILLIC.search(body):
            violations.append(f"{relative}/SKILL.source.md: cyrillic in the canonical body")
        cyrillic_lines = [line for line in frontmatter.splitlines() if CYRILLIC.search(line)]
        if not cyrillic_lines:
            violations.append(f"{relative}/SKILL.source.md: missing Russian discovery terms")
        elif not all("Russian discovery terms:" in line for line in cyrillic_lines):
            violations.append(
                f"{relative}/SKILL.source.md: cyrillic outside Russian discovery terms"
            )
        workflows = list(skill.glob("references/workflow.md"))
        if len(workflows) != 1:
            violations.append(f"{relative}: expected exactly one references/workflow.md")
        elif CYRILLIC.search(workflows[0].read_text(encoding="utf-8")):
            violations.append(f"{relative}/references/workflow.md: cyrillic in the workflow")
        for locale_dir in ("references/ru", "references/en"):
            if (skill / locale_dir).exists():
                violations.append(f"{relative}/{locale_dir}: locale references are forbidden")
    return violations


def shared_canon_violations(root: Path) -> list[str]:
    """Cyrillic-free EN canon for shared references and spec templates."""
    violations: list[str] = []
    for path in sorted((root / "shared" / "references").rglob("*.md")):
        if CYRILLIC.search(path.read_text(encoding="utf-8")):
            violations.append(f"{path.relative_to(root).as_posix()}: cyrillic in shared canon")
    for path in sorted((root / "skills" / "spec-manage").glob("templates/**/*.md")):
        if "/ru/" in path.as_posix():
            continue
        if CYRILLIC.search(path.read_text(encoding="utf-8")):
            violations.append(f"{path.relative_to(root).as_posix()}: cyrillic outside ru templates")
    return violations


def tracked_skill_material_violations(root: Path) -> list[str]:
    """Cyrillic-free EN canon over every tracked skills/ file, AST-scoped."""
    tracked = subprocess.run(
        ["git", "ls-files", "skills"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    violations: list[str] = []
    for relative in tracked:
        path = root / relative
        if not path.is_file():
            continue
        if "skills/spec-manage/templates/ru/" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "SKILL.source.md":
            text = text.split("---", 2)[2]
        if relative == "skills/spec-manage/scripts/spec_validate.py":
            text = strip_spec_validate_placeholders(text)
        if relative in LOCALIZED_STRING_DATA:
            text = strip_localized_string_data(text)
        if relative == "skills/mattermost/references/cards.md":
            # Only valid Russian JSON examples may contain translated prose.
            text = strip_localized_json_examples(text)
        if CYRILLIC.search(text):
            violations.append(f"{relative}: cyrillic in tracked skill material")
    return violations


def cap_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for relative, cap in sorted(BYTE_CAPS.items()):
        path = root / relative
        if path.is_file() and path.stat().st_size > cap:
            violations.append(f"{relative}: {path.stat().st_size} bytes exceeds the {cap} cap")
    return violations


def collect(root: Path) -> list[str]:
    return [
        *skill_source_violations(root / "skills"),
        *shared_canon_violations(root),
        *tracked_skill_material_violations(root),
        *cap_violations(root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root (defaults to this checkout)")
    arguments = parser.parse_args(argv)
    root = (arguments.root or Path(__file__).resolve().parents[1]).resolve()
    violations = collect(root)
    for violation in violations:
        print(f"skill canon violation: {violation}", file=sys.stderr)
    if violations:
        return 1
    print("skill canon sources are clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
