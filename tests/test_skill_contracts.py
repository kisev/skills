from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_skill_has_required_frontmatter() -> None:
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    assert skills
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\n"), skill
        frontmatter = text.split("---", 2)[1]
        assert "\nname:" in frontmatter, skill
        assert "\ndescription:" in frontmatter, skill
        assert "\nlicense:" in frontmatter, skill


def test_materialized_skill_files_match_canonical_sources() -> None:
    manifest = json.loads((ROOT / "shared/manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        source = ROOT / "shared" / entry["source"]
        destination = ROOT / "skills" / entry["destination"]
        assert destination.read_bytes() == source.read_bytes(), destination
