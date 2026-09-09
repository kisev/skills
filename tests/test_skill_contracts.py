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
        source_copy = ROOT / "skills" / relative_destination
        assert source_copy.read_bytes() == source.read_bytes(), source_copy


def test_rebuilding_portable_skills_does_not_change_repository_state() -> None:
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
        "spec-manage": (
            "user must explicitly provide one mode",
            "spec-update",
            "mode is completely read-only",
        ),
        "commit-msg": ("git diff --cached", "exactly one line", "Do not run `git add`"),
        "docs-prepare": (
            "content-addressed preview artifact",
            "Do not print the draft or diff",
            "never combine workflows",
        ),
        "docs-review": (
            "spec-manage` in `spec-audit` mode",
            "only confirmed findings",
            "never publish them",
        ),
        "doit": (
            "exact action is included in the approved plan",
            "separate confirmations",
            "Do not require a particular host",
        ),
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
    for path in (ROOT / "skills" / "spec-manage").glob("templates/**/*.md"):
        if "/ru/" in path.as_posix():
            continue
        assert not cyrillic.search(path.read_text(encoding="utf-8")), path


def test_all_english_canonical_skill_material_is_cyrillic_free() -> None:
    cyrillic = re.compile(r"[А-Яа-яЁё]")
    tracked = subprocess.run(
        ["git", "ls-files", "skills"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    for relative in tracked:
        path = ROOT / relative
        if not path.is_file():
            continue
        if "skills/spec-manage/templates/ru/" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "SKILL.md":
            text = text.split("---", 2)[2]
        assert not cyrillic.search(text), path


def test_preparation_workflows_follow_the_shared_language_policy() -> None:
    required = re.compile(
        r"language of the latest user request; use\s+English when that language is ambiguous"
    )
    for name in ("mr-prepare", "task-prepare", "release-prepare"):
        workflow = (ROOT / "skills" / name / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        assert "references/language-policy.md" in workflow, name
        assert required.search(workflow), name


def test_stage_16_shared_contracts_cover_completeness_ownership_and_risk_boundaries() -> None:
    interaction = (ROOT / "shared/references/interaction-contract.md").read_text(encoding="utf-8")
    language = (ROOT / "shared/references/language-policy.md").read_text(encoding="utf-8")
    questions = (ROOT / "shared/references/question-guidelines.md").read_text(encoding="utf-8")
    work_item = (ROOT / "shared/references/work-item-contract.md").read_text(encoding="utf-8")
    for marker in (
        "Do not declare a result complete",
        "partial",
        "blocked",
        "error",
        "safe escalation",
        "same mutation boundary",
        "External publication",
        "history rewrite",
        "destructive cleanup",
        "one explicit owner",
    ):
        assert marker in interaction, marker
    assert "all response prose" in language
    assert "independent decisions" in questions
    assert "quality-complete" in work_item


def test_stage_16_core_workflow_boundaries_are_observable() -> None:
    agents = (ROOT / "skills/agents-md/references/workflow.md").read_text(encoding="utf-8")
    askme = (ROOT / "skills/askme/references/workflow.md").read_text(encoding="utf-8")
    commit_msg = (ROOT / "skills/commit-msg/references/workflow.md").read_text(encoding="utf-8")
    docs_prepare = (ROOT / "skills/docs-prepare/references/workflow.md").read_text(encoding="utf-8")
    docs_review = (ROOT / "skills/docs-review/references/workflow.md").read_text(encoding="utf-8")
    doit = (ROOT / "skills/doit/references/workflow.md").read_text(encoding="utf-8")
    goal = (ROOT / "skills/goal/references/workflow.md").read_text(encoding="utf-8")
    humanize = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    improve = (ROOT / "skills/skill-improve/references/workflow.md").read_text(encoding="utf-8")
    assert "Create the root file when no applicable file exists" in agents
    assert "repeat a question answered" in askme
    assert "commitlint/configuration" in commit_msg
    assert "complete user-facing documentation set" in docs_prepare
    assert "canonical specifications" in docs_review
    assert "exact action is included in the approved plan" in doit
    assert "structured Markdown rather than JSON" in goal
    assert "at or below 4000 characters" in goal
    assert "any human language" in humanize
    assert "absence of real" in improve
    assert "Never push" not in doit
