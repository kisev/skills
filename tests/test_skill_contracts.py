from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

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
        assert '\n  source: "https://kisev.github.io/skills"' in frontmatter, skill
        assert not re.search(r"^\s*version\s*:", frontmatter, re.MULTILINE), skill


def test_askme_discovery_and_manual_continuation_contract() -> None:
    skill = BUILT_SKILLS / "askme"
    frontmatter = (skill / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    description = frontmatter.split("description:", 1)[1].split("license:", 1)[0]
    for phrase in ("узнай у меня", "уточни у меня", "спроси меня", "ask me", "askme"):
        assert phrase in description
    for marker in ("equivalent intent", "conditionally", "quoted text", "negated requests"):
        assert marker in description

    workflow = (skill / "references/workflow.md").read_text(encoding="utf-8")
    for marker in (
        "do not by themselves activate an interview",
        "A separate invitation to ask questions in the same message does",
        "no clarification questions remain",
        "Always stop and wait for explicit manual continuation",
        "even when there were no questions or the invitation was conditional",
        "An interview answer or confirmation of the proposed task alone is not permission",
        "this also applies to `task-prepare`",
    ):
        assert marker in workflow
    assert "confirmation of the proposed task permits it to continue" not in workflow


def test_built_skill_files_match_canonical_sources() -> None:
    for source, relative_destination in manifest_entries():
        destination = BUILT_SKILLS / relative_destination
        assert destination.read_bytes() == source.read_bytes(), destination


def test_portable_skill_build_output_is_ignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", ".build/skills"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_workflow_references_retain_non_abbreviated_safety_contracts() -> None:
    expected_markers = {
        "agents-md": (
            "rule -> source",
            "at most 20 one-line bullets",
            "uncommitted changes",
            "exact requested revision",
            "merge/pull-request",
            "resulting diff",
        ),
        "askme": ("**Proposed task**", "current frontier", "never simulated self-review"),
        "ast-grep": (
            "--dry-run",
            "rolls back replaced files",
            "must not trigger installation",
        ),
        "spec-manage": (
            "Literal mode tokens remain supported but are optional",
            "Absence of `specs/` alone never proves greenfield",
            "spec-update",
            "mode is completely read-only",
            "scripts/spec_validate.py",
            "lifecycle as `not_checked`",
        ),
        "commit-msg": ("git diff --cached", "exactly one line", "Do not run `git add`"),
        "docs-prepare": (
            "write it directly with atomic replacement",
            "Do not create a private preview artifact",
            "never combine workflows",
        ),
        "docs-review": (
            "spec-manage` in `spec-audit` mode",
            "only confirmed findings",
            "never publish them",
        ),
    }
    for name, markers in expected_markers.items():
        workflow = (ROOT / "skills" / name / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        assert len(workflow.splitlines()) > 4, name
        for marker in markers:
            assert marker in workflow, (name, marker)


def test_project_spec_identifiers_and_decisions_are_append_only() -> None:
    skill = ROOT / "skills/spec-manage"
    requirements = (skill / "references/requirements.md").read_text(encoding="utf-8")
    adr = (skill / "references/adr.md").read_text(encoding="utf-8")
    consolidation = (skill / "references/consolidation.md").read_text(encoding="utf-8")
    audit = (skill / "references/auditing.md").read_text(encoding="utf-8")
    workflow = (skill / "references/workflow.md").read_text(encoding="utf-8")

    assert "greater than the highest number ever assigned" in requirements
    assert "Never fill a gap, renumber an entry, or reuse an ID" in requirements
    assert "Do not delete a requirement when its lifecycle status changes" in requirements
    assert "A superseded or withdrawn entry may be shortened" in requirements
    assert "preserve the ID, former requirement, status-change reason" in requirements
    assert "greater than the highest number ever assigned" in adr
    assert "Never fill a gap, renumber an ADR, reuse a number, or delete" in adr
    assert "reason for deprecation or supersession" in adr
    assert "compacting a withdrawn or superseded requirement" in consolidation
    assert "increase above the historical" in audit
    assert "stable requirements and decisions" in workflow


def test_project_spec_language_authority_and_extension_contract() -> None:
    skill = ROOT / "skills/spec-manage"
    entrypoint = (skill / "SKILL.source.md").read_text(encoding="utf-8")
    contract = (skill / "references/canonical-contract.md").read_text(encoding="utf-8")
    normalized_contract = " ".join(contract.split())
    workflow = (skill / "references/workflow.md").read_text(encoding="utf-8")
    audit = (skill / "references/auditing.md").read_text(encoding="utf-8")
    root_template = (skill / "templates/specs/README.md").read_text(encoding="utf-8")

    assert "English-only canonical project specification" not in entrypoint
    assert "exactly one explicitly declared canonical prose language" in normalized_contract
    assert (
        "A same-language, different-language, or mixed-language user request" in normalized_contract
    )
    assert (
        "obtain the user's explicit project-language choice before writing" in normalized_contract
    )
    assert (
        "all substantive existing canonical prose unambiguously uses one language"
        in normalized_contract
    )
    assert "Changing an existing tree's language requires an explicit" in normalized_contract
    assert "confirmed user decisions are normative" in normalized_contract
    assert (
        "code, tests, configuration, CI, and deployment prove only current behavior"
        in normalized_contract
    )
    assert "existing `specs/` tree is the normative baseline" in normalized_contract
    assert "do not resolve them by silently preferring either side" in normalized_contract
    assert "minimum canonical skeleton, not a closed allowlist" in normalized_contract
    assert "`specs/capabilities/` section is valid" in normalized_contract
    assert "explicit project-language choice before preparing files" in workflow
    assert "Never select the canonical language from the current request" in workflow
    assert "This mode is completely read-only" in workflow
    assert "The conversational report may use a different language" in audit
    assert "Canonical language: PROJECT-LANGUAGE." in root_template
    assert "## Extension Index" in root_template


def test_team_workflows_retain_evidence_and_artifact_quality_contracts() -> None:
    expected_markers = {
        "team-retro": (
            "every profile project where `include` is true",
            "`period.semantics` is `[since, until)`",
            "Do not present `merged`, `tagged`, and `shipped` as synonyms",
            "outcome - purpose",
            "external contributors",
            "verification_command",
        ),
        "team-roadmap": (
            "evidence matrix",
            "past plans are historical records",
            "Every unfinished goal needs one explicit destination",
            "create issues, epics, milestones",
            "verification_commands",
        ),
        "slides-prompts-prepare": (
            "Theme and technical content are complementary layers",
            "research it through current web sources",
            "order of slides",
            "team_reference_policy",
            "Do not modify files matching `image_pattern`",
        ),
    }
    for name, markers in expected_markers.items():
        workflow = (ROOT / "skills" / name / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        for marker in markers:
            assert marker in workflow, (name, marker)


def test_team_profile_contract_is_distributed_without_private_values() -> None:
    schema = ROOT / "shared/references/team_runtime/team-context.schema.json"
    example = ROOT / "shared/references/team_runtime/team-context.example.json"
    assert schema.is_file()
    assert example.is_file()
    example_text = example.read_text(encoding="utf-8")
    assert "gitlab.example.test" in example_text
    assert "wildberries" not in example_text.lower()
    for name in (
        "team-sprint-start",
        "team-sprint-close",
        "team-retro",
        "team-roadmap",
        "slides-prompts-prepare",
    ):
        references = BUILT_SKILLS / name / "references"
        assert (references / "team-context.schema.json").read_bytes() == schema.read_bytes()
        assert (references / "team-context.example.json").read_bytes() == example.read_bytes()


def test_skills_use_english_canonical_workflows_without_locale_references() -> None:
    cyrillic = re.compile(r"[А-Яа-яЁё]")
    for skill in (ROOT / "skills").iterdir():
        if not skill.is_dir() or not (skill / "SKILL.source.md").is_file():
            continue
        skill_text = (skill / "SKILL.source.md").read_text(encoding="utf-8")
        frontmatter, body = skill_text.split("---", 2)[1:]
        assert not cyrillic.search(body), skill / "SKILL.source.md"
        cyrillic_frontmatter_lines = [
            line for line in frontmatter.splitlines() if cyrillic.search(line)
        ]
        assert cyrillic_frontmatter_lines, skill / "SKILL.source.md"
        assert all("Russian discovery terms:" in line for line in cyrillic_frontmatter_lines), (
            skill / "SKILL.source.md"
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
        if path.name == "SKILL.source.md":
            text = text.split("---", 2)[2]
        if relative == "skills/spec-manage/scripts/spec_validate.py":
            tree = ast.parse(text)
            placeholder_assignment = next(
                node
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "PLACEHOLDERS"
                    for target in node.targets
                )
            )
            lines = text.splitlines()
            del lines[placeholder_assignment.lineno - 1 : placeholder_assignment.end_lineno]
            text = "\n".join(lines)
        assert not cyrillic.search(text), path


def test_preparation_workflows_follow_the_shared_language_policy() -> None:
    required = re.compile(
        r"language of the latest user request; use\s+English when that language is ambiguous"
    )
    for name in ("task-prepare", "release-prepare"):
        workflow = (ROOT / "skills" / name / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        assert "references/language-policy.md" in workflow, name
        assert required.search(workflow), name
    # MR preparation uses code-review's session-aware locale selection.
    mr_workflow = (ROOT / "skills/mr-prepare/references/workflow.md").read_text(encoding="utf-8")
    for marker in (
        "references/language-policy.md",
        "explicit user request, applicable agent",
        "established user prose in the session, then English",
        "--locale <en|ru>",
        "locale is bound to evidence and must match the content draft",
        "presentation.fallback_sections",
    ):
        assert marker in mr_workflow


def test_code_review_requires_compact_incremental_manual_publication_contract() -> None:
    workflow = (ROOT / "skills/code-review/references/workflow.md").read_text(encoding="utf-8")
    for marker in (
        "--incremental auto",
        "--incremental off",
        '"full review" alone is not an opt-out',
        "previous_finding_assessments",
        "recommended_issues",
        "review-publication.md",
        "complete absolute filesystem paths",
        "label_assessments",
        "direct manual `glab` commands",
        "advisory XDG marker",
        "not a publication receipt or postcondition",
        "fix_mode=patch",
        "temporary index",
        "runner-owned stages",
        "print its `chat` field verbatim",
        "On every invocation, read every non-system discussion and every reply",
        "resolved thread uses `no_publication`",
        "first publish the explanation, then change thread state",
        "`git apply`",
        "thread_sha256",
        "accepted` requires a valid `suggestion` or `patch`",
    ):
        assert marker in workflow
    output = (ROOT / "skills/code-review/references/output-format.md").read_text(encoding="utf-8")
    incremental = (ROOT / "skills/code-review/references/incremental-review.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "For another author's MR, do not expose finding titles",
        "use a `file://` link",
        "manual checklist, not a publication protocol",
        "selected response language",
        "authenticated user's",
        "factual role",
        "informal second-person",
        "Keep current labels, unresolved labels, and exhaustive assessment in",
        "report-review` owns the labels and layout",
        "continues the complete existing conversation naturally",
        "thread-state command is",
    ):
        assert marker in output
    state_machine = (ROOT / "skills/code-review/references/review-state-machine.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "critic_missing",
        "finalize_missing",
        "decision_missing",
        "content_missing",
        "plan_ready",
        "subagent text is not a critic receipt",
        "print its `chat` value verbatim",
        "An accepted `low` finding is",
    ):
        assert marker in state_machine
    for marker in (
        "Local WIP always receives",
        "delta-triggered scope",
        "Revalidate every previously accepted finding",
        "independent critic",
    ):
        assert marker in incremental
    author_snapshot = (
        (ROOT / "tests/fixtures/code-review/author-chat.snapshot.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    assert author_snapshot in output


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
    goal = (ROOT / "skills/goal/references/workflow.md").read_text(encoding="utf-8")
    humanize = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    improve = (ROOT / "skills/skill-improve/references/workflow.md").read_text(encoding="utf-8")
    assert "Create the root file when no applicable file exists" in agents
    assert "repeat a question answered" in askme
    assert "commitlint/configuration" in commit_msg
    assert "complete user-facing documentation set" in docs_prepare
    assert "canonical specifications" in docs_review
    assert "structured Markdown rather than JSON" in goal
    assert "at or below 4000 characters" in goal
    assert "any human language" in humanize
    assert "Do not invent facts" in humanize
    assert "strong-versus-weak safeguard" in humanize
    assert "punctuation rules below" in humanize
    assert "absence of real" in improve
