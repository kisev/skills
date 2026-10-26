"""Adapter registry contract tests: frozen table, dialects, command formats."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest
from skillmate.adapters import ADAPTERS, CLAUDE, CODEX, OPENCODE, restore_references
from skillmate.content import SkillContent, skill_content
from skillmate.distribution import DistributionError, SkillArchive

KNOWN = frozenset({"humanize", "commit-msg"})


def _content(files: dict[str, bytes]) -> SkillContent:
    from skillmate.distribution import ArchiveFile

    entries = tuple(ArchiveFile(path=path, data=data) for path, data in files.items())
    return skill_content(SkillArchive(name="humanize", sha256="0" * 64, files=entries))


def test_registry_covers_the_frozen_table() -> None:
    assert set(ADAPTERS) == {"codex", "claude", "opencode"}
    assert ADAPTERS["codex"].skills_project == PurePosixPath(".agents/skills")
    assert ADAPTERS["claude"].skills_project == PurePosixPath(".claude/skills")
    assert ADAPTERS["opencode"].skills_project == PurePosixPath(".opencode/skills")
    assert ADAPTERS["codex"].skills_global == PurePosixPath(".agents/skills")
    assert ADAPTERS["claude"].skills_global == PurePosixPath(".claude/skills")
    assert ADAPTERS["opencode"].skills_global == PurePosixPath(".config/opencode/skills")
    assert not ADAPTERS["codex"].supports_commands()
    for host in ("claude", "opencode"):
        assert ADAPTERS[host].commands_project is not None
        assert ADAPTERS[host].commands_global is not None


def test_claude_and_opencode_copies_are_canonical() -> None:
    content = _content(
        {
            "SKILL.md": b"---\nname: humanize\ndescription: Edit prose.\n---\n\nRun `/humanize`.\n",
            "references/note.md": b"See `/commit-msg` too.\n",
        }
    )
    for host in ("claude", "opencode"):
        assert ADAPTERS[host].materialize(content, KNOWN) == content.files


def test_codex_rewrite_targets_known_names_only_and_is_reversible() -> None:
    content = _content(
        {
            "SKILL.md": (
                b"---\nname: humanize\ndescription: Edit prose.\n---\n\n"
                b"Run `/humanize` and `/commit-msg`, not `/etc/passwd` or `/unknown-cmd`.\n"
            ),
            "scripts/run.py": b"print('/humanize')\n",
        }
    )
    codex_files = CODEX.materialize(content, KNOWN)
    by_path = {f.path: f.data for f in codex_files}
    assert by_path["SKILL.md"] == (
        b"---\nname: humanize\ndescription: Edit prose.\n---\n\n"
        b"Run `$humanize` and `$commit-msg`, not `/etc/passwd` or `/unknown-cmd`.\n"
    )
    assert by_path["scripts/run.py"] == b"print('/humanize')\n"
    restored = restore_references(by_path["SKILL.md"].decode().splitlines()[-1] + "\n", KNOWN)
    assert restored == "Run `/humanize` and `/commit-msg`, not `/etc/passwd` or `/unknown-cmd`.\n"


def test_command_document_shape_for_slash_hosts() -> None:
    content = _content(
        {
            "SKILL.md": b"---\nname: humanize\ndescription: >-\n  Edit prose: naturally.\n---\n\nBody.\n"
        }
    )
    document = CLAUDE.command_document(content)
    assert document is not None
    assert document.startswith('---\ndescription: "Edit prose: naturally."\n---\n\n# /humanize\n')
    assert "uvx skillmate install --skill humanize" in document
    assert document.endswith("$ARGUMENTS\n")


def test_commandless_skill_gets_no_command_and_codex_reports_the_gap() -> None:
    content = _content(
        {
            "SKILL.md": (
                b'---\nname: tdd\ndescription: Red-green.\nmetadata:\n  command: "false"\n---\n\nBody.\n'
            )
        }
    )
    assert CLAUDE.command_document(content) is None
    owning = _content({"SKILL.md": b"---\nname: tdd\ndescription: Red-green.\n---\n\nBody.\n"})
    assert CODEX.command_document(owning) is None


def test_skill_reference_spelling() -> None:
    assert CODEX.skill_reference("tdd") == "$tdd"
    assert CLAUDE.skill_reference("tdd") == "/tdd"
    assert OPENCODE.skill_reference("tdd") == "/tdd"


def test_skill_content_parses_frontmatter_and_rejects_broken_input() -> None:
    from skillmate.distribution import ArchiveFile

    good = SkillArchive(
        name="x",
        sha256="0" * 64,
        files=(
            ArchiveFile(
                path="SKILL.md",
                data=b"---\nname: x\ndescription: >-\n  Multi line\n  text.\nmetadata:\n"
                b'  author: "a"\n  command: "false"\n---\n\nBody.\n',
            ),
        ),
    )
    parsed = skill_content(good)
    assert parsed.name == "x"
    assert parsed.description == "Multi line text."
    assert parsed.owns_command is False

    broken = SkillArchive(
        name="y",
        sha256="0" * 64,
        files=(ArchiveFile(path="SKILL.md", data=b"no frontmatter here"),),
    )
    with pytest.raises(DistributionError):
        skill_content(broken)


def test_config_fragments_are_empty_for_current_content() -> None:
    content = _content(
        {"SKILL.md": b"---\nname: humanize\ndescription: Edit prose.\n---\n\nBody.\n"}
    )
    for adapter in ADAPTERS.values():
        assert adapter.config_fragments((content,)) == ()


def test_install_notices_flag_opencode_duplicate_visibility() -> None:
    from skillmate.adapters import install_notices

    assert install_notices(("opencode",)) == ()
    assert install_notices(("claude", "codex")) == ()
    combined = install_notices(("opencode", "claude", "codex"))
    assert len(combined) == 1
    assert "not documented by OpenCode" in combined[0]
