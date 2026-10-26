"""The canonical content model: what a built skill archive carries.

A skill's command surface is derived from its own ``SKILL.md`` frontmatter:
``name`` and ``description`` shape the thin command adapter, and
``metadata.command: "false"`` opts a skill out of owning one. Nothing else
about a command is stored outside the skill itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from skillmate.distribution import ArchiveFile, DistributionError, SkillArchive


@dataclass(frozen=True)
class SkillContent:
    """One skill, parsed from its archive."""

    name: str
    description: str
    owns_command: bool
    files: tuple[ArchiveFile, ...]


def _folded(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines).strip()


def _literal(lines: list[str]) -> str:
    return "\n".join(line.strip() for line in lines).rstrip("\n")


def _unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return stripped[1:-1]
    return stripped


def _parse_frontmatter(text: str) -> dict[str, str | dict[str, str]]:
    """Parse the frontmatter subset the built skills use.

    Supported: plain and quoted scalars, ``>``/``>-`` folded and ``|``/``|-``
    literal blocks, and one nested mapping level (``metadata``). Anything
    else fails loudly rather than being guessed.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise DistributionError("SKILL.md has no frontmatter")
    fields: dict[str, str | dict[str, str]] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        if line.strip() == "---":
            return fields
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if line.startswith((" ", "\t")):
            raise DistributionError(f"unexpected indented frontmatter line: {stripped!r}")
        key, separator, rest = stripped.partition(":")
        if not separator:
            raise DistributionError(f"malformed frontmatter line: {stripped!r}")
        key, rest = key.strip(), rest.strip()
        if not rest:
            index += 1
            nested: dict[str, str] = {}
            while index < len(lines) and (
                not lines[index].strip() or lines[index].startswith((" ", "\t"))
            ):
                child = lines[index].strip()
                if child:
                    child_key, child_separator, child_value = child.partition(":")
                    if not child_separator:
                        raise DistributionError(f"malformed metadata line: {child!r}")
                    nested[child_key.strip()] = _unquote(child_value)
                index += 1
            fields[key] = nested
            continue
        if rest in {">", ">-", "|", "|-"}:
            block: list[str] = []
            index += 1
            while index < len(lines) and (
                not lines[index].strip() or lines[index].startswith((" ", "\t"))
            ):
                block.append(lines[index])
                index += 1
            fields[key] = _folded(block) if rest.startswith(">") else _literal(block)
            continue
        fields[key] = _unquote(rest)
        index += 1
    raise DistributionError("SKILL.md frontmatter is not closed")


def skill_content(archive: SkillArchive) -> SkillContent:
    """Parse a skill archive into the canonical content model."""
    entry = next((f for f in archive.files if f.path == "SKILL.md"), None)
    if entry is None:
        raise DistributionError(f"skill {archive.name!r} has no SKILL.md")
    try:
        fields = _parse_frontmatter(entry.data.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise DistributionError(f"skill {archive.name!r} SKILL.md is not UTF-8") from error
    name = fields.get("name")
    description = fields.get("description")
    if not isinstance(name, str) or not name or not isinstance(description, str):
        raise DistributionError(f"skill {archive.name!r} lacks a name or description")
    metadata = fields.get("metadata", {})
    if not isinstance(metadata, dict):
        raise DistributionError(f"skill {archive.name!r} has malformed metadata")
    return SkillContent(
        name=name,
        description=description,
        owns_command=metadata.get("command") != "false",
        files=archive.files,
    )


def frontmatter_description(content: SkillContent) -> str:
    """The description as a quoted single-line frontmatter value."""
    return json.dumps(content.description, ensure_ascii=False)
