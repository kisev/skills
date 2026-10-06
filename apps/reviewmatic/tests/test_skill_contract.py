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
    assert "fill its judgment placeholders" in workflow
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
