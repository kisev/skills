from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILT_SKILLS = ROOT / ".build" / "skills"


def test_every_skill_has_required_frontmatter() -> None:
    skills = sorted(BUILT_SKILLS.glob("*/SKILL.md"))
    assert skills
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\n"), skill
        frontmatter = text.split("---", 2)[1]
        assert "\nname:" in frontmatter, skill
        assert "\ndescription:" in frontmatter, skill
        assert "\nlicense:" in frontmatter, skill


def test_built_skill_files_match_canonical_sources() -> None:
    manifest = json.loads((ROOT / "shared/manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        source = ROOT / "shared" / entry["source"]
        destination = BUILT_SKILLS / entry["destination"]
        assert destination.read_bytes() == source.read_bytes(), destination
        assert not (ROOT / "skills" / entry["destination"]).exists(), destination


def test_rebuilding_portable_skills_does_not_change_tracked_source() -> None:
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    subprocess.run(
        ["python3", "scripts/build_skills.py"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert after == before
