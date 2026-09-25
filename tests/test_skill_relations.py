from __future__ import annotations

import json
import re

from scripts.build_skills import (
    ROOT,
    SOURCE_ENTRYPOINT,
    SOURCES,
    load_relations,
    render_related_section,
)

BUILT_SKILLS = ROOT / ".build" / "skills"
RELATIONS = ROOT / "shared" / "skill-relations.json"
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


def test_relations_graph_is_well_formed() -> None:
    related = load_relations()
    assert related
    payload = json.loads(RELATIONS.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert len(payload["relations"]) == sum(len(edges) for edges in related.values())
    for source, edges in related.items():
        assert (SOURCES / source / SOURCE_ENTRYPOINT).is_file()
        for edge in edges:
            assert edge["type"] in {"requires", "uses", "recommends"}
            assert edge["name"] != source
            assert (SOURCES / edge["name"] / SOURCE_ENTRYPOINT).is_file()
            assert edge["reason"].strip() == edge["reason"]
            assert CYRILLIC.search(edge["reason"]) is None
    types = [edge["type"] for edges in related.values() for edge in edges]
    assert types.count("requires") >= 1
    assert types.count("uses") >= 1
    assert types.count("recommends") >= 1


def test_curated_edges_are_present() -> None:
    related = load_relations()
    edges = {
        (source, edge["name"], edge["type"])
        for source, outgoing in related.items()
        for edge in outgoing
    }
    assert ("mattermost-triage", "mattermost", "requires") in edges
    for source in (
        "task-prepare",
        "task-triage",
        "code-review",
        "mr-prepare",
        "commit-msg",
        "briefing",
        "docs-prepare",
        "release-prepare",
        "mattermost-triage",
        "team-retro",
        "team-roadmap",
        "team-sprint-start",
        "team-sprint-close",
        "slides-prompts-prepare",
    ):
        assert (source, "humanize", "uses") in edges
    for edge in (
        ("task-prepare", "task-review", "uses"),
        ("task-prepare", "task-triage", "uses"),
        ("task-prepare", "askme", "uses"),
        ("task-triage", "task-review", "uses"),
        ("task-triage", "code-review", "uses"),
        ("mr-prepare", "askme", "uses"),
        ("docs-prepare", "spec-manage", "uses"),
        ("docs-review", "spec-manage", "uses"),
        ("code-review", "release-review", "recommends"),
        ("code-explain", "code-review", "recommends"),
        ("goal", "task-prepare", "recommends"),
        ("task-prepare", "goal", "recommends"),
        ("briefing", "team-retro", "recommends"),
        ("team-retro", "briefing", "recommends"),
        ("release-prepare", "release-review", "recommends"),
        ("release-review", "release-prepare", "recommends"),
        ("mattermost", "mattermost-triage", "recommends"),
    ):
        assert edge in edges
    for source in ("team-retro", "team-roadmap", "team-sprint-start", "team-sprint-close"):
        assert (source, "mattermost", "recommends") in edges


def test_built_skills_materialize_the_related_section() -> None:
    related = load_relations()
    skills = [path for path in BUILT_SKILLS.iterdir() if path.is_dir()]
    assert len(skills) >= 28
    for skill in sorted(skills):
        entrypoint = skill / "SKILL.md"
        assert entrypoint.is_file(), skill.name
        text = entrypoint.read_text(encoding="utf-8")
        assert CYRILLIC.search(text.split("---", 2)[2]) is None, skill.name
        if skill.name in related:
            section = render_related_section(related[skill.name])
            assert text.endswith(section), skill.name
        else:
            assert "## Related skills" not in text, skill.name
