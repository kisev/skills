"""The agent-contract test: runtime surface and skill texts move together.

A UX or contract change to the runtime is complete only together with its
wiring into the agent contract in the same change. This test holds both
directions:

1. every ``reviewmatic`` invocation written in the ``code-review`` skill texts
   names a real command and real options of this runtime;
2. every primary-path command the runtime owns is documented in the skill
   texts, so a renamed, added, or removed surface cannot silently lose its
   agent wiring.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reviewmatic.cli import DEFINITIONS, GLOBAL_OPTIONS

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = REPO_ROOT / "skills" / "code-review"

COMMAND_TOKEN = re.compile(r"^[a-z][a-z0-9-]*$")

# The primary-path commands the agent contract must document. The repair-path
# and local-mode commands stay in the same set: they are documented surfaces,
# not internal ones. Internal/legacy commands (marker-run, publication,
# capabilities, the state-machine primitives behind waiting responses) are
# exempt.
REQUIRED_DOCUMENTED = (
    # Primary path: the one-process run with the panel poll.
    "run",
    "record-run-critic",
    # Runtime identity: SHA pinning and the self report.
    "runtime-info",
    # Finalization preview: the pure raw-SHA scrub.
    "scrub-preview",
    # The inverted tail: render, edit prose, re-anchor on drift.
    "render-review",
    "record-prose",
    "record-delta",
    "re-anchor-review",
    # Marked repair path: the step-by-step panel flow.
    "start-review",
    "resume-review",
    "record-package",
    "record-participants",
    "record-ocr-critic",
    "record-critic",
    "record-arbitration",
    "record-input",
    "check-review",
    "finish-review",
    "repair-review",
    "refresh-review",
    "scope-review",
    # Local WIP mode.
    "prepare-local",
    "finalize-local",
)

GLOBAL_FLAGS = {f"--{option.name}" for option in GLOBAL_OPTIONS}


def command_options() -> dict[str, set[str]]:
    options: dict[str, set[str]] = {}
    for definition in DEFINITIONS:
        name = definition.signature.split()[0]
        options[name] = {f"--{option.name}" for option in definition.options}
    return options


def skill_documents() -> list[Path]:
    documents = sorted(SKILL_DIR.glob("**/*.md"))
    assert documents, "the code-review skill sources must exist in the repository"
    return documents


def code_lines(path: Path) -> list[str]:
    """One entry per inline code span and fenced-block line."""
    lines: list[str] = []
    fenced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            lines.append(stripped)
        else:
            lines.extend(match.strip() for match in re.findall(r"`([^`]+)`", line))
    return lines


def parse_invocations() -> list[tuple[str, str, set[str], Path]]:
    """Extract (file, command, flags, snippet) for every reviewmatic invocation."""
    options = command_options()
    invocations: list[tuple[str, str, set[str], Path]] = []
    for document in skill_documents():
        for snippet in code_lines(document):
            tokens = snippet.replace("=", " ").split()
            if "reviewmatic" not in tokens:
                continue
            index = len(tokens) - 1 - tokens[::-1].index("reviewmatic")
            command = tokens[index + 1] if index + 1 < len(tokens) else ""
            if COMMAND_TOKEN.match(command) is None:
                continue
            assert command in options, (
                f"{document.name}: the skill documents reviewmatic {command}, but the runtime "
                "has no such command"
            )
            flags = {token for token in tokens if token.startswith("--")}
            unknown = flags - options[command] - GLOBAL_FLAGS
            assert not unknown, (
                f"{document.name}: reviewmatic {command} is documented with unknown options "
                f"{', '.join(sorted(unknown))}"
            )
            invocations.append((document.name, command, flags, document))
    return invocations


def test_skill_invocations_name_real_commands_and_options() -> None:
    invocations = parse_invocations()
    assert invocations, "the skill texts must invoke the runtime"


def test_every_primary_path_command_is_documented_in_the_skill() -> None:
    documented = {command for _file, command, _flags, _doc in parse_invocations()}
    missing = [command for command in REQUIRED_DOCUMENTED if command not in documented]
    assert not missing, (
        "the runtime owns primary-path commands the skill never invokes; wire them into "
        f"the agent contract in the same change: {', '.join(missing)}"
    )


def test_run_panel_poll_contract_is_documented() -> None:
    """The poll is the decision point: composition and the engine of every critic."""
    text = "\n".join(document.read_text(encoding="utf-8") for document in skill_documents())
    assert "record-run-critic" in text
    assert '"ocr"' in text or "engine: ocr" in text or "`ocr`" in text
    assert "--participants" in text
    for flag in ("--participants",):
        assert any(
            flag in flags for _file, command, flags, _doc in parse_invocations() if command == "run"
        ), "the skill must invoke reviewmatic run --participants"


def test_publication_skeletons_and_self_documenting_refusals_are_documented() -> None:
    """The pre-rendered publication variants and their refusal contract are wired."""
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "formally complete block per valid variant" in workflow
    assert "fill the placeholders" in workflow
    assert "never passes" in workflow


def test_repair_paths_are_tiered_by_cost() -> None:
    """repair.md routes each repair kind to its cheapest honest path."""
    repair = (SKILL_DIR / "references" / "repair.md").read_text(encoding="utf-8")
    assert "Choose the repair path by cost" in repair
    assert "record-arbitration" in repair
    assert "--kind critic_receipt" in repair
    assert "refresh-review" in repair


def test_runtime_pin_and_self_report_are_documented() -> None:
    """The skill pins the channel SHA and verifies it with runtime-info."""
    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    for text in (entry, workflow):
        assert "git ls-remote" in text
        assert "@<sha>" in text
        assert "runtime-info" in text
    assert any(command == "runtime-info" for _file, command, _flags, _doc in parse_invocations()), (
        "the skill must invoke reviewmatic runtime-info"
    )


def test_the_single_pinned_runtime_ignores_any_path_binary() -> None:
    """REVIEWMATIC_FROM is the one runtime; a PATH reviewmatic is foreign."""
    entry = " ".join((SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8").split())
    workflow = " ".join(
        (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8").split()
    )
    pinned = "git+https://github.com/kisev/skills.git@<sha>#subdirectory=apps/reviewmatic"
    for text in (entry, workflow):
        assert "REVIEWMATIC_FROM" in text
        assert pinned in text, "the pin is a git+URL with an exact @<sha>"
        assert "found on `PATH` as a foreign, possibly outdated binary and ignore it" in text
        assert 'uvx --from "$REVIEWMATIC_FROM"' in text
        assert "runtime-info" in text
    assert "compare the printed resolved commit to the pinned SHA" in entry
    assert "compare the printed `commit` to the pinned SHA" in workflow


def test_the_contract_test_reads_the_authored_sources() -> None:
    sources: dict[str, Any] = {"SKILL.source.md": SKILL_DIR / "SKILL.source.md"}
    assert sources["SKILL.source.md"].is_file()


def test_the_poll_is_presented_verbatim_with_a_fixed_glossary() -> None:
    """The skill presents the runtime poll text word for word, with fixed terms."""
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "word for word" in workflow
    assert "poll.text" in workflow
    assert "poll-glossary.md" in workflow
    glossary = (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8")
    for term in ("Poll", "Critic", "Engine", "OCR engine", "Arbitrator", "Panel"):
        assert term in glossary


def test_the_poll_options_are_grounded_in_installed_profiles() -> None:
    """The agent verifies the installed critic profiles before composing poll
    options; multi-critic options require distinct models or engines, and two
    critics on one model are never offered. The same rule lives in the
    runtime poll text and rules (both locales)."""
    from reviewmatic import run_panel

    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    glossary = (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8")
    for text in (entry, workflow):
        assert "agentomatic agent list" in text
        assert "distinct models or engines" in text
        assert "two critics on the same single model" in text
    normalized_glossary = " ".join(glossary.split())
    assert (
        "an independent subagent on the current session's agent, provider, and model"
        in normalized_glossary
    )
    assert (
        "a subagent on the same model as the session, or a selected specialist profile"
        in normalized_glossary
    )
    for locale in ("en", "ru"):
        rules = run_panel.poll_rules(locale)
        assert "agentomatic agent list" in rules
        if locale == "en":
            assert "never propose two critics on the same single model" in rules
        else:
            assert "двух критиков на одной и той же модели" in rules
        poll = run_panel.poll(locale, "normal", 500)
        if locale == "en":
            assert (
                "two critics on the same single model are not an independent check" in poll["text"]
            )
            assert "a subagent on the same model or a" in poll["text"]
        else:
            assert "два критика на одной и той же модели - не независимая проверка" in poll["text"]
            assert "субагент на той же модели или выбранный профильный агент" in poll["text"]


def test_the_compact_background_contract_is_documented() -> None:
    """The compact render is offered when it fits; the poll note names the
    compacted size and the cut sections, and the executed file is the
    measured one."""
    glossary = " ".join(
        (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8").split()
    )
    assert "Compact background" in glossary
    assert "the poll measures and the OCR critic executes" in glossary
    incremental = " ".join(
        (SKILL_DIR / "references" / "incremental-review.md").read_text(encoding="utf-8").split()
    )
    assert "Only a compact background above the OCR CLI limit" in incremental


def test_the_bulk_poll_wording_names_the_actual_participants() -> None:
    """``ordinary model critic`` is gone: the texts name a subagent on the
    current model and state the arbitrator's engine explicitly."""
    joined = "\n".join(document.read_text(encoding="utf-8") for document in skill_documents())
    assert "ordinary model critic" not in joined
    assert "ordinary critic and one ordinary arbitrator" not in joined


def test_the_tail_routing_precedence_is_documented() -> None:
    """Render before prose before finalize; structural edits are repair."""
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    tail = workflow.index("The inverted tail")
    section = " ".join(workflow[tail:].split())
    render_at = section.index("render-review --draft")
    prose_at = section.index("record-prose --draft")
    assert render_at < prose_at, "render-review precedes record-prose in the tail"
    assert "re-anchor-review" in section
    assert "requires a recorded repair kind" in section
    assert "primary `run` path" in section
    assert "decision → shared render → record-prose → finalize" in section
    assert "Historical checks certify the old snapshot" in section
    assert "Line mapping proves a publication position, never the truth" in section
    primary = workflow[
        workflow.index("Run path: the primary") : workflow.index("Necessity and completion")
    ]
    assert "shared renderer" in primary
    assert "record-prose --artifact-root" in primary
    assert "scaffold-review` is the structural repair" in primary
    assert primary.index("shared renderer") < primary.index("record-prose --artifact-root")


def test_standalone_runbook_and_semantic_input_contract_are_documented() -> None:
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    history = " ".join(
        (SKILL_DIR / "references" / "incremental-review.md").read_text(encoding="utf-8").split()
    )
    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    assert "history_context" in entry
    for fragment in (
        "History is advisory",
        "prepared `finding_id` unchanged",
        "{name,status,rationale}",
        "semver_assessment.basis: {name,source}",
        "Recorded rejected-candidate reasons are reused",
        "Thread fixes use the same semantic",
        "Addressed prose updates retain other filled rows",
        "CI-only changes",
    ):
        assert fragment in workflow, fragment
    for fragment in (
        "replaces mandatory",
        "historical synchronization",
        "including OCR",
        "currently observed defect",
        "fallback_reasons",
        "Incomplete **current** evidence",
        "Green",  # Timing acceptance must not be inferred from offline tests.
    ):
        assert fragment in history, fragment
