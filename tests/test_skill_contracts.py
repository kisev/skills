from __future__ import annotations

import subprocess
from pathlib import Path
import re

from scripts.build_skills import manifest_entries

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
    for source, relative_destination in manifest_entries():
        destination = BUILT_SKILLS / relative_destination
        assert destination.read_bytes() == source.read_bytes(), destination
        assert not (ROOT / "skills" / relative_destination).exists(), destination


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


def test_workflow_references_retain_non_abbreviated_safety_contracts() -> None:
    expected_markers = {
        "agents-md": ("rule -> source", "at most 20 one-line bullets", "exact diff"),
        "askme": ("**Proposed task**", "current frontier", "never simulated self-review"),
        "ast-grep": (
            "--apply --confirm <DIGEST>",
            "rolls back replaced files",
            "must not trigger installation",
        ),
        "attempt": (
            "`background_attempts` is the sole owner",
            "expected_revision",
            "unconfirmed abort do not delete state",
        ),
        "commit-msg": ("git diff --cached", "exactly one line", "Do not run `git add`"),
        "docs-prepare": (
            "content-addressed preview artifact",
            "Do not print the draft or diff",
            "never combine workflows",
        ),
        "docs-review": (
            "project-spec` in `spec-audit` mode",
            "only confirmed findings",
            "never publish them",
        ),
        "doit": ("Never push", "separate confirmation", "Do not require a particular host"),
    }
    for name, markers in expected_markers.items():
        workflow = (ROOT / "skills" / name / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        assert len(workflow.splitlines()) > 4, name
        for marker in markers:
            assert marker in workflow, (name, marker)


def test_skills_use_english_canonical_workflows_without_locale_references() -> None:
    cyrillic = re.compile(r"[А-Яа-яЁё]")
    for skill in (ROOT / "skills").iterdir():
        if not skill.is_dir() or not (skill / "SKILL.md").is_file():
            continue
        skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
        frontmatter, body = skill_text.split("---", 2)[1:]
        assert not cyrillic.search(body), skill / "SKILL.md"
        cyrillic_frontmatter_lines = [
            line for line in frontmatter.splitlines() if cyrillic.search(line)
        ]
        assert cyrillic_frontmatter_lines, skill / "SKILL.md"
        assert all("Russian discovery terms:" in line for line in cyrillic_frontmatter_lines), (
            skill / "SKILL.md"
        )
        workflows = list(skill.glob("references/workflow.md"))
        assert len(workflows) == 1, skill
        assert not cyrillic.search(workflows[0].read_text(encoding="utf-8")), workflows[0]
        assert not (skill / "references/ru").exists(), skill
        assert not (skill / "references/en").exists(), skill

    for path in (ROOT / "shared" / "references").rglob("*.md"):
        assert not cyrillic.search(path.read_text(encoding="utf-8")), path
    for path in (ROOT / "skills" / "project-spec").glob("templates/**/*.md"):
        if "/ru/" in path.as_posix():
            continue
        assert not cyrillic.search(path.read_text(encoding="utf-8")), path
