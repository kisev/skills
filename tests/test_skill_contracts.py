from __future__ import annotations

import ast
import json
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
        "ends with manual continuation",
        "returns decisions to that caller",
        "An explicit interview request takes",
        "Neither mode expands the task",
    ):
        assert marker in workflow
    assert "confirmation of the proposed task permits it to continue" not in workflow


def test_askme_context_and_closing_contract_apply_to_every_invocation() -> None:
    workflow = (ROOT / "skills/askme/references/workflow.md").read_text(encoding="utf-8")
    interview = workflow.split("## Interview\n", 1)[1].split("\n## ", 1)[0]
    closing = workflow.split("## Closing result\n", 1)[1].split("\n## ", 1)[0]
    assert "On every invocation, including the first" in interview
    assert "ordinary discussion before any interview" in interview
    assert "including the first and a no-questions result" in interview
    assert "Preserve confirmed decisions as agreed" in interview
    assert "every agreement still in force numbered as a decision" in closing
    assert "ordinary discussion before the first interview" in closing
    assert "When this call continues an earlier interview" not in interview


def test_askme_repeated_invocations_preserve_topic_agreements() -> None:
    workflow = (ROOT / "skills/askme/references/workflow.md").read_text(encoding="utf-8")
    normalized = " ".join(workflow.split())
    for marker in (
        "continues that topic instead of restarting it",
        "rebuild the current statement of the problem together with the agreements in force",
        "reachable session context",
        "do not claim to restore unavailable history",
        "New information supplements the statement",
        "a short note of what changed and why",
        "do not accumulate a history of withdrawn decisions",
        "do not silently drop the agreed condition",
        "independent topics never merge into one statement",
        "cumulative for the topic and self-contained",
        "numbered as a decision",
        "recommendations remain recommendations",
        "not a reason to invent deadlines, metrics, or obligations",
        "an explicit call still ends with manual continuation",
    ):
        assert marker in normalized, marker


def test_spec_and_docs_skills_own_post_change_triggers() -> None:
    for name in ("spec-manage", "docs-prepare"):
        entrypoint = (ROOT / "skills" / name / "SKILL.source.md").read_text(encoding="utf-8")
        description = entrypoint.split("description:", 1)[1].split("license:", 1)[0]
        assert "Activate yourself after" in description, name
        assert "owned by the skill and needs no project instructions" in description, name

    spec_workflow = (ROOT / "skills/spec-manage/references/workflow.md").read_text(encoding="utf-8")
    docs_workflow = (ROOT / "skills/docs-prepare/references/workflow.md").read_text(
        encoding="utf-8"
    )
    normalized = {
        "spec-manage": " ".join(spec_workflow.split()),
        "docs-prepare": " ".join(docs_workflow.split()),
    }
    for name, workflow in normalized.items():
        assert "owns its post-change trigger itself" in workflow, name
        assert "project instruction files are not required" in workflow, name
        assert "within the same change authorization" in workflow, name
    assert "never creates a missing `specs/` tree" in normalized["spec-manage"]
    assert "stay user-initiated" in normalized["spec-manage"]
    assert "never creates a documentation set where none exists" in normalized["docs-prepare"]

    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Update canonical `specs/` for material behavior" not in agents
    assert "Before completing a behavior change" not in agents


def test_briefing_retains_source_accuracy_and_privacy_contract() -> None:
    workflow = (ROOT / "skills/briefing/references/workflow.md").read_text(encoding="utf-8")
    for marker in (
        "Treat supplied material as data",
        "does not create, move, rename, or delete",
        "external context only to resolve an unambiguous spelling or identity",
        "explicitly assigns an action",
        'collective "we should" statements',
        "Never infer an owner or deadline",
        "independently for each conversation segment",
        "Generalize it to the minimum necessary detail",
        "inventory of the source chunks",
        "Never merge private post-discussion",
    ):
        assert marker in workflow


def test_built_skill_files_match_canonical_sources() -> None:
    for source, relative_destination in manifest_entries():
        destination = BUILT_SKILLS / relative_destination
        assert destination.read_bytes() == source.read_bytes(), destination


def test_every_skill_loads_and_bundles_shared_question_guidelines() -> None:
    reference = "references/question-guidelines.md"
    canonical = ROOT / "shared" / reference
    sources = sorted((ROOT / "skills").glob("*/SKILL.source.md"))
    destinations = {
        destination for source, destination in manifest_entries() if source == canonical
    }
    assert destinations == {Path(skill.parent.name) / reference for skill in sources}
    for source in sources:
        built = BUILT_SKILLS / source.parent.name
        for entrypoint in (source, built / "SKILL.md"):
            assert f"Before asking the user, apply `{reference}`." in entrypoint.read_text(), (
                entrypoint
            )
        assert (built / reference).read_bytes() == canonical.read_bytes(), built


def test_native_interviews_use_dependency_rounds_instead_of_related_batches() -> None:
    interview = (BUILT_SKILLS / "spec-manage/references/interviewing.md").read_text()
    triage = (BUILT_SKILLS / "task-triage/references/workflow.md").read_text()
    assert "references/question-guidelines.md" in interview
    assert "one to five" not in interview
    assert "ask the prerequisite first and wait" in interview
    assert "including non-recommended and custom choices" in interview
    assert "rebuild dependent follow-ups" in " ".join(triage.split())


def test_review_followups_preserve_the_decision_boundary() -> None:
    askme = (BUILT_SKILLS / "askme/references/workflow.md").read_text(encoding="utf-8")
    askme_doctrine = (BUILT_SKILLS / "askme/references/necessity-doctrine.md").read_text(
        encoding="utf-8"
    )
    review = (BUILT_SKILLS / "code-review/references/workflow.md").read_text(encoding="utf-8")
    review_doctrine = (BUILT_SKILLS / "code-review/references/necessity-doctrine.md").read_text(
        encoding="utf-8"
    )
    local = (BUILT_SKILLS / "code-review/references/local-review.md").read_text(encoding="utf-8")
    examples = (BUILT_SKILLS / "code-review/references/finding-examples.md").read_text(
        encoding="utf-8"
    )
    assert askme_doctrine == review_doctrine
    assert "necessity check in `references/necessity-doctrine.md`" in askme
    assert "a candidate, not an agreed requirement" in askme
    assert "before asking how to implement" in askme_doctrine
    assert "Independent reviewers receive these decisions" in review
    assert "fault injection alone" in review_doctrine
    assert "Do not automatically recommend another broad review" in review_doctrine
    assert "previous finalized local report and snapshot" in review
    assert "not an implementation regression" in local
    assert "cannot prove" in local
    assert "do not launch a new broad technical audit" in local
    assert "regardless of round count or severity" in local
    assert "unlinked reference inside a Markdown table" in examples
    assert "Corrupting that table is" in examples
    assert "does not prove the model chose" in examples


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
            "mode never edits the reviewed project",
            "scripts/spec_validate.py",
            "lifecycle as `not_checked`",
        ),
        "commit-msg": ("git diff --cached", "exactly one line", "Do not run `git add`"),
        "docs-prepare": (
            "write it directly with atomic replacement",
            "Do not create a private preview artifact",
            "Separate steps may share one change authorization",
        ),
        "docs-review": (
            "spec-manage` in `spec-review` mode",
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
    assert "This mode never edits the reviewed project" in workflow
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
            "--resume-profile PROFILE",
            "agent-skills/team/<profile>/evidence/",
            "`resume.incomplete` is empty",
            '"Data sources" section',
            "artifact-record",
        ),
        "team-roadmap": (
            "evidence matrix",
            "past plans are historical records",
            "Every unfinished goal needs one explicit destination",
            "create issues, epics, milestones",
            "verification_commands",
            "--resume-profile PROFILE",
            '"Data sources" section',
            "artifact-record",
        ),
        "team-sprint-start": (
            '"Data sources" section',
            "evidence-record",
            "artifact-record",
            "agent-skills/team/<profile>/evidence/",
        ),
        "team-sprint-close": (
            '"Data sources" section',
            "evidence-record",
            "artifact-record",
            "--resume-profile PROFILE",
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


def test_team_profile_workflow_documents_the_evidence_store() -> None:
    workflow = (ROOT / "shared/references/team_runtime/team-profile-workflow.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "agent-skills/team-evidence/<profile>/",
        "evidence-plan",
        "evidence-record",
        "evidence-show",
        "evidence-materialize",
        "artifact-record",
        "--resume-profile PROFILE",
        "Never store credentials",
    ):
        assert marker in workflow, marker


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
        # Card publication explicitly supports English and Russian at runtime.
        # Permit localized string data, but keep comments and other source prose
        # under the English-only contract. Do not exempt entire source files.
        if relative in {
            "skills/mattermost/scripts/mattermost.py",
            "skills/mattermost/scripts/mattermost_cards.py",
            "skills/mattermost/tests/test_mattermost_publication.py",
        }:
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
                and cyrillic.search(segment)
            }
            for segment in sorted(localized, key=len, reverse=True):
                text = text.replace(segment, repr("localized card text"))
        if relative == "skills/mattermost/references/cards.md":
            # Only valid Russian JSON examples may contain translated prose.
            def localized_example(match: re.Match[str]) -> str:
                example = json.loads(match.group(1))
                return "" if example.get("locale") == "ru" else match.group(0)

            text = re.sub(r"```json\n(.*?)\n```", localized_example, text, flags=re.S)
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
        "runbook.md",
        "complete absolute filesystem paths",
        "label_assessments",
        "references/publication.md",
        "reviewmatic start-review",
        "check-review --draft",
        "finish-review",
        "reviewmatic plan --artifact-root",
        "never include local",
        "fix_mode=patch",
        "temporary index",
        "one-draft workflow",
        "print its `chat` field verbatim",
        "On every invocation, read every non-system discussion and every reply",
        "resolved thread uses `no_publication`",
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
        "one direct `glab` command per remote action",
        "selected response language",
        "authenticated user's",
        "factual role",
        "informal second-person",
        "Keep current labels, unresolved labels, and exhaustive assessment in",
        "`finish-review` and, for an existing finalized",
        "continues the complete existing conversation naturally",
        "resolve/reopen share one `shell` block",
        "Show every concrete",
        "including thread replies",
    ):
        assert marker in output
    state_machine = (ROOT / "skills/code-review/references/review-state-machine.md").read_text(
        encoding="utf-8"
    )
    normalized_machine = " ".join(state_machine.split())
    for marker in (
        "start-review",
        "check-review",
        "finish-review",
        "resume-review",
        "without GitLab reads, publication artifacts, or progress changes",
        "Set `critic_count` to the selected count",
        "Absence of `critic` is not a blocker",
        "ordinary independent native subagent of the current agent",
        "never replace the agent's semantic assessment",
        "Every accepted non-low finding blocks `ready`",
        "Existing v2 artifacts and low-level",
    ):
        assert marker in normalized_machine
    for marker in (
        "local-review.md",
        "delta-triggered scope",
        "Revalidate every previously accepted finding",
        "independent critic",
    ):
        assert marker in incremental
    publication = (ROOT / "skills/code-review/references/publication.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "reviewmatic plan",
        "State changes follow a successful reply only",
        "actual ID",
        "direct block uses",
    ):
        assert marker in publication
    assert "Local WIP always receives" not in incremental
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
    doctor = (ROOT / "skills/skill-doctor/references/workflow.md").read_text(encoding="utf-8")
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
    assert "Run only on an explicit user request" in doctor
    assert "suspected causes stay" in doctor
    assert "keep them only in private" in doctor


def test_humanize_activates_only_on_explicit_invocation() -> None:
    entrypoint = (ROOT / "skills/humanize/SKILL.source.md").read_text(encoding="utf-8")
    normalized = " ".join(entrypoint.split())
    for marker in (
        "Load this skill only on an explicit invocation",
        "including the `/humanize` command",
        "explicit text-preparation step of another skill's workflow",
        "never activates this skill by itself",
        "never become a standing profile or a global default",
    ):
        assert marker in normalized, marker
    assert "Other skills should always load humanize" not in normalized
    assert "writing or editing any user-facing prose" not in normalized

    workflow = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    assert "Run only on an explicit invocation" in workflow
    assert "references/patterns.md" in workflow


def test_humanize_prioritizes_meaning_constraints_then_voice() -> None:
    workflow = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    meaning = workflow.index("Meaning and protected fragments")
    constraints = workflow.index("Mandatory constraints")
    voice = workflow.index("Voice adaptation")
    assert meaning < constraints < voice
    assert "A writing sample never cancels them" in workflow
    assert "A sample guides the voice, not the defects" in workflow
    assert (
        "Do not invent facts, names, numbers, dates, quotations, citations, "
        "opinions, reactions, or sources" in workflow
    )


def test_humanize_punctuation_rule_and_check_cover_forbidden_code_points() -> None:
    workflow = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    for point in ("U+2013", "U+2014", "U+00AB", "U+00BB", "U+201C", "U+201D"):
        assert point in workflow, point
    assert "rg -n -P '[\\x{2013}\\x{2014}\\x{00AB}\\x{00BB}\\x{201C}\\x{201D}]'" in workflow
    assert (
        "Keep matches that belong to exact quotations, code, commands, paths, "
        "identifiers, or source data" in workflow
    )


def test_humanize_relations_carry_explicit_workflow_invocations() -> None:
    relations = json.loads((ROOT / "shared/skill-relations.json").read_text(encoding="utf-8"))
    sources = sorted(entry["from"] for entry in relations["relations"] if entry["to"] == "humanize")
    assert len(sources) == 23
    for source in sources:
        workflow = (ROOT / "skills" / source / "references/workflow.md").read_text(encoding="utf-8")
        assert "humanize" in workflow, source


def test_humanize_patterns_catalog_maps_all_26_upstream_categories() -> None:
    catalog = (ROOT / "skills/humanize/references/patterns.md").read_text(encoding="utf-8")
    assert "26 categories" in catalog
    assert "A writing sample never overrides" in catalog
    assert "did not express" in catalog
    for heading in (
        "### 1. Not X but Y",
        "### 2. One-line closers and dramatic fragments",
        "### 3. Sayings that sound deep",
        "### 4. Staged run-up before the point",
        "### 5. Arguing with no one",
        "### 6. Forced triads (weak alone)",
        "### 7. Repeated sentence openings (weak alone)",
        "### 8. Dashes as the universal connector",
        "### 9. Stacked qualifiers (weak alone)",
        "### 10. Hyphenated pairs everywhere (weak alone)",
        "### 11. Passive voice and missing subjects (weak alone)",
        "### 12. Overused AI words (weak alone)",
        "### 13. Inflated significance",
        "### 14. Vague connection or association",
        "### 15. Shallow participial riders (weak alone)",
        "### 16. Sales language",
        "### 17. Borrowed authority",
        "### 18. Avoiding is, are, and has (weak alone)",
        "### 19. Bold as decoration (weak alone)",
        "### 20. Decorative headings (weak alone)",
        "### 21. Curly quotation marks",
        "### 22. Chatbot residue",
        "### 23. Knowledge-limit disclaimers and guesses",
        "### 24. A heading repeated in the first sentence (weak alone)",
        "### 25. Writing about the document instead of its subject (weak alone)",
        "### 26. Re-explaining what the reader knows",
    ):
        assert heading in catalog, heading

    english = (ROOT / "docs/reference/humanize-patterns.md").read_text(encoding="utf-8")
    russian = (ROOT / "docs/ru/reference/humanize-patterns.md").read_text(encoding="utf-8")
    for heading in (
        "### 6. Forced triads (weak alone)",
        "### 12. Overused AI words (weak alone)",
        "### 25. Writing about the document instead of its subject (weak alone)",
    ):
        assert heading in english, heading
    for heading in (
        "### 6. Вынужденные триады (слабо в одиночку)",
        "### 12. Заезженные слова ИИ (слабо в одиночку)",
        "### 25. Текст о самом тексте вместо предмета (слабо в одиночку)",
    ):
        assert heading in russian, heading


WEAK_ALONE_CATEGORIES = frozenset({6, 7, 9, 10, 11, 12, 15, 18, 19, 20, 24, 25})


def test_humanize_weak_alone_classification_is_consistent() -> None:
    import re

    catalog = (ROOT / "skills/humanize/references/patterns.md").read_text(encoding="utf-8")
    marked: set[int] = set()
    for match in re.finditer(r"^### (\d+)\. .+?( \(weak alone\))?$", catalog, re.MULTILINE):
        if match.group(2):
            marked.add(int(match.group(1)))
    assert marked == WEAK_ALONE_CATEGORIES

    workflow = (ROOT / "skills/humanize/references/workflow.md").read_text(encoding="utf-8")
    assert "as weak alone: 6, 7, 9, 10, 11, 12, 15, 18, 19, 20, 24, and 25" in workflow
    # The mandatory punctuation bans hold regardless of the strong/weak split.
    assert "do not follow this classification" in workflow
    assert "regardless of this classification" in catalog


def test_humanize_dependent_workflows_invoke_at_a_concrete_artifact() -> None:
    relations = json.loads((ROOT / "shared/skill-relations.json").read_text(encoding="utf-8"))
    consumers = sorted(
        entry["from"] for entry in relations["relations"] if entry["to"] == "humanize"
    )
    assert len(consumers) == 23
    for source in consumers:
        workflow = (ROOT / "skills" / source / "references/workflow.md").read_text(encoding="utf-8")
        assert "humanize" in workflow, source
        lowered = " ".join(workflow.lower().split())
        assert "for all drafted prose" not in lowered, source
        assert "before drafting prose" not in lowered, source
    for entry in relations["relations"]:
        if entry["to"] == "humanize":
            assert "all drafted prose" not in entry["reason"], entry
    code_review = (ROOT / "skills/code-review/references/workflow.md").read_text(encoding="utf-8")
    assert "Apply `humanize` to each drafted thread reply" in code_review
    assert "do not invoke it" in code_review
    mr_prepare = (ROOT / "skills/mr-prepare/references/workflow.md").read_text(encoding="utf-8")
    assert "Apply `humanize` to the drafted `title` and `description`" in mr_prepare
    task_prepare = (ROOT / "skills/task-prepare/references/workflow.md").read_text(encoding="utf-8")
    assert "Apply `humanize` to the drafted task" in task_prepare


def test_humanize_documentation_carries_bilingual_examples() -> None:
    english = (ROOT / "docs/reference/humanize-patterns.md").read_text(encoding="utf-8")
    russian = (ROOT / "docs/ru/reference/humanize-patterns.md").read_text(encoding="utf-8")
    for document in (english, russian):
        for heading in (
            "### 1. ",
            "### 13. ",
            "### 26. ",
            "**Before (en):**" if document is english else "**До (en):**",
        ):
            assert heading in document, heading
        assert "**Before (ru):**" in document or "**До (ru):**" in document
        assert "**After (ru):**" in document or "**После (ru):**" in document
    assert "A writing sample never overrides" in english
    assert "образец" in russian.lower() or "Образец" in russian
    readme = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    readme_ru = (ROOT / "docs/ru/README.md").read_text(encoding="utf-8")
    assert "reference/humanize-patterns.md" in readme
    assert "reference/humanize-patterns.md" in readme_ru


def test_humanize_eval_scenarios_define_explicit_activation_matrix() -> None:
    scenarios = ROOT / "evals/scenarios"
    trigger_ru = json.loads((scenarios / "stage20.skill.humanize.trigger.json").read_text())
    trigger_en = json.loads((scenarios / "stage20.skill.humanize.trigger.en.json").read_text())
    near_miss_ru = json.loads((scenarios / "stage20.skill.humanize.near-miss.json").read_text())
    near_miss_en = json.loads((scenarios / "stage20.skill.humanize.near-miss.en.json").read_text())
    for scenario in (trigger_ru, trigger_en):
        assert scenario["expected"]["selected"] == ["skill:humanize"]
        assert "humanize" in scenario["input"]["prompt"].lower()
    for scenario in (near_miss_ru, near_miss_en):
        assert scenario["expected"]["not_selected"] == ["skill:humanize"]
        assert scenario["expected"]["selected"] == []
    prompts = [
        trigger_ru["input"]["prompt"],
        trigger_en["input"]["prompt"],
        near_miss_ru["input"]["prompt"],
        near_miss_en["input"]["prompt"],
    ]
    assert len(set(prompts)) == 4
    assert "намеренно не относится" not in near_miss_ru["input"]["prompt"]

    chained_ru = json.loads((scenarios / "skill.humanize.workflow-step.json").read_text())
    chained_en = json.loads((scenarios / "skill.humanize.workflow-step.en.json").read_text())
    for scenario in (chained_ru, chained_en):
        assert scenario["expected"]["selected"] == ["skill:briefing", "skill:humanize"]
        assert scenario["kind"] == "trigger"
        # A workflow-step invocation names only the caller skill; humanize is
        # reached through its workflow, never named by the user.
        assert "humanize" not in scenario["input"]["prompt"].lower()
        assert "briefing" in scenario["input"]["prompt"].lower()
        assert scenario["revision"] == 2

    edit_ru = json.loads((scenarios / "skill.humanize.edit-contract.json").read_text())
    edit_en = json.loads((scenarios / "skill.humanize.edit-contract.en.json").read_text())
    # The RU scenario gained the strengthened whole-rewrite claim after the EN
    # pair, so its revision moved past the shared revision 3.
    assert (edit_ru["revision"], edit_en["revision"]) == (4, 3)
    for scenario in (edit_ru, edit_en):
        assert scenario["kind"] == "golden"
        cases = scenario["input"]["fixture"]["cases"]
        expected_ids = {item["id"] for item in scenario["expected"]["case_outcomes"]}
        assert (
            expected_ids
            == {item["id"] for item in cases}
            == {
                "protected-tokens",
                "sample-conflict",
                "caveat-preserved",
                "isolated-weak-tell",
                "quote-keeps-marks",
            }
        )
        for case in cases:
            assert case["text"] and case["expect"]
            # Every case carries a machine-checkable rewrite contract, and the
            # quote case keeps a forbidden mark inside a protected quotation.
            verify = case["verify"]
            assert set(verify) == {"protected", "claims", "avoid"}
            assert all(
                isinstance(entry, str) and entry for group in verify.values() for entry in group
            )
            assert any(verify.values())
        quote = next(case for case in cases if case["id"] == "quote-keeps-marks")
        assert any("\u2014" in item for item in quote["verify"]["protected"])
        # The protected-tokens claims bind the original author and both core
        # actions, not just the object nouns.
        protected = next(case for case in cases if case["id"] == "protected-tokens")
        claims = [item.casefold() for item in protected["verify"]["claims"]]
        assert any(item.startswith(("we ", "мы ")) for item in claims)
        pipeline_claims = [item for item in claims if "pipeline" in item or "конвейер" in item]
        assert pipeline_claims
        assert all(item not in {"the whole pipeline", "конвейер"} for item in pipeline_claims)
        # A pipeline claim binds the whole rewrite scope, never a bare action.
        assert all("whole pipeline" in item or "целиком" in item for item in pipeline_claims)
        assert all(item["outcome"] is True for item in scenario["expected"]["case_outcomes"])
        prompt = scenario["input"]["prompt"]
        assert "humanize" in prompt.lower()
        # The scenario consumes the returned rewrite itself; a boolean
        # self-report alone is not an observed result.
        assert "rewrite" in prompt
    # The bilingual cases must differ; the protected-token pair exercises an
    # exact quotation and a command in both languages.
    for key in ("text", "expect"):
        assert (
            edit_ru["input"]["fixture"]["cases"][0][key]
            != edit_en["input"]["fixture"]["cases"][0][key]
        )
    assert edit_ru["input"]["fixture"]["cases"][1].get("sample")
    assert edit_en["input"]["fixture"]["cases"][1].get("sample")
