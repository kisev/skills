"""The agent-contract test: runtime surface and skill texts move together.

A UX or contract change to the runtime is complete only together with its
wiring into the agent contract in the same change. This test holds both
directions:

1. every ``reviewmatic`` invocation written in the ``code-review`` skill texts
   names a real command and real options of this runtime;
2. every primary-path command the runtime owns is documented in the skill
   texts, so a renamed, added, or removed surface cannot silently lose its
   agent wiring;
3. the reference maps in ``docs/`` (the pipeline map of the review line and
   the release chain map) name the same runtime vocabulary: every documented
   command and runtime stage is on the map, and the map names no command,
   option, or stage the runtime does not own.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reviewmatic.cli import DEFINITIONS, GLOBAL_OPTIONS
from reviewmatic.context import REVIEW_STAGES

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
    # Session modes: explicit XDG profiles (decision 75).
    "profile-setup",
    "profile-show",
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


def invocations_in(documents: list[Path]) -> list[tuple[str, str, set[str], Path]]:
    """Extract (file, command, flags, snippet) for every reviewmatic invocation."""
    options = command_options()
    invocations: list[tuple[str, str, set[str], Path]] = []
    for document in documents:
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


def parse_invocations() -> list[tuple[str, str, set[str], Path]]:
    return invocations_in(skill_documents())


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
    skill = SKILL_DIR / "references"
    workflow = "\n".join(
        (skill / name).read_text(encoding="utf-8")
        for name in (
            "workflow.md",
            "run-path.md",
            "review-panel.md",
            "remote-review-stages.md",
            "inverted-tail.md",
        )
    )
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
    """The skill pins the channel SHA and verifies it with runtime-info.

    The procedure lives once in the SKILL.source.md entrypoint; the workflow
    stage router delegates to it with a one-line pointer (AUDIT.3 dedup).
    """
    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "git ls-remote" in entry
    assert "@<sha>" in entry
    assert "runtime-info" in entry
    assert "runtime selection and pin" in workflow
    assert "SKILL.source.md" in workflow
    assert "runtime-info" in workflow
    assert any(command == "runtime-info" for _file, command, _flags, _doc in parse_invocations()), (
        "the skill must invoke reviewmatic runtime-info"
    )


def test_the_runtime_pin_reads_locally_and_the_banner_opens_the_session() -> None:
    """Decision 76 stage 3: the installed tree carries references/runtime-pin.json;
    a session reads the pinned commit from it (no git ls-remote per run) and
    opens its first response with the local version banner: skill version from
    the pin, reviewmatic from runtime-info, glab from --version."""
    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    workflow = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "references/runtime-pin.json" in entry
    assert "stitched by the distribution build" in entry
    assert "a session never resolves the tip with `git ls-remote`" in entry
    assert "Only when the pin file is absent" in entry
    assert "version banner" in entry
    assert "`glab --version` line" in entry
    assert "no network call belongs to the banner" in entry
    assert "references/runtime-pin.json" in workflow
    assert "never runs `git ls-remote` when the file" in workflow
    assert "version banner" in workflow


def test_the_single_pinned_runtime_ignores_any_path_binary() -> None:
    """REVIEWMATIC_FROM is the one runtime; a PATH reviewmatic is foreign.

    The entrypoint owns the full procedure; the workflow router keeps the
    pointer and the ask-when-unclear channel rule.
    """
    entry = " ".join((SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8").split())
    workflow = " ".join(
        (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8").split()
    )
    pinned = "git+https://github.com/kisev/skills.git@<sha>#subdirectory=apps/reviewmatic"
    assert "REVIEWMATIC_FROM" in entry
    assert pinned in entry, "the pin is a git+URL with an exact @<sha>"
    assert "found on `PATH` as a foreign, possibly outdated binary and ignore it" in entry
    assert 'uvx --from "$REVIEWMATIC_FROM"' in entry
    assert "runtime-info" in entry
    assert "compare the printed resolved commit to the pinned SHA" in entry
    assert "runtime selection and pin" in workflow
    assert "SKILL.source.md" in workflow
    assert "REVIEWMATIC_FROM" in workflow
    assert "PATH-binary ban" in workflow
    assert "runtime-info" in workflow
    assert "never choose silently" in workflow
    assert "repeats" in workflow
    assert "resolution and pin" in workflow


def test_the_contract_test_reads_the_authored_sources() -> None:
    sources: dict[str, Any] = {"SKILL.source.md": SKILL_DIR / "SKILL.source.md"}
    assert sources["SKILL.source.md"].is_file()


def test_the_poll_is_presented_verbatim_with_a_fixed_glossary() -> None:
    """The skill presents the runtime poll text word for word, with fixed terms."""
    run_path = (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8")
    assert "word for word" in run_path
    assert "poll.text" in run_path
    assert "poll-glossary.md" in run_path
    glossary = (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8")
    for term in ("Poll", "Critic", "Engine", "OCR engine", "Arbitrator", "Panel"):
        assert term in glossary


def test_the_poll_stop_prints_the_ready_to_copy_fenced_block() -> None:
    """Decision 67: verbatim presentation is a copy of a printed fenced block.

    The micro-test for the pressure pair (decision 67 / decision on the
    pressure method): the guided text names the runtime surface the stop
    actually prints (`poll_block`) and the no-restyle recipe, while the
    no-guidance control shows blockquote styling of the plain text.
    """
    run_path = (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8")
    panel = (SKILL_DIR / "references" / "review-panel.md").read_text(encoding="utf-8")
    assert "`poll_block`" in run_path
    assert "Copy the fenced `poll_block` into your response exactly as printed" in run_path
    assert "blockquoting" in run_path
    assert "`poll_block`" in panel


def test_the_final_answer_carries_the_sanctioned_self_check() -> None:
    """Decision 67: the final self-check runs over the run's own outputs.

    The micro-test for the pressure pair: the guided text routes the
    verify-before-reporting instinct into the printed `final_checklist` and
    names reference re-reads after the final plan as the forbidden
    out-of-stage path, which is exactly the red class the live acceptance
    caught on the flash model.
    """
    run_path = (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8")
    assert "`final_checklist`" in run_path
    assert "sanctioned self-check" in run_path
    assert "red flag" in run_path
    assert "out-of-stage read the reading discipline forbids" in run_path


def test_the_poll_options_are_grounded_in_installed_profiles() -> None:
    """The agent grounds the critic pool in the harness agent inventory before
    composing poll options; multi-critic options require distinct models or
    engines, and two critics on one model are never offered. The pool counts
    only the agents the user configured (decision 71): bundled agent assets of
    installed packages or plugins — anything under ``node_modules/`` — are
    excluded as installation sources deployed only through ``configure agent``.
    The same rule lives in the runtime poll text and rules (both locales), and no bare
    package CLI is part of the contract."""
    from reviewmatic import run_panel

    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    panel = " ".join(
        (SKILL_DIR / "references" / "review-panel.md").read_text(encoding="utf-8").split()
    )
    glossary = (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8")
    run_path = " ".join(
        (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8").split()
    )
    for text in (entry, panel):
        assert "`agents/*.md` in the harness-global and project config directories" in text
        assert "`agent` key" in text
        assert "distinct models or engines" in text
        assert "two critics on the same single model" in text
        # Decision 71: only user-configured agents; package/plugin installation
        # sources (the live run globbed node_modules assets into the pool) are
        # excluded explicitly, in every grounded text.
        assert "node_modules" in text
        assert "installed packages or plugins" in text
        assert "`configure agent`" in text
    assert "never propose two critics on the same single model" in run_path
    normalized_glossary = " ".join(glossary.split())
    assert (
        "an independent subagent on the current session's agent, provider, and model"
        in normalized_glossary
    )
    assert (
        "a subagent on the same model as the session, or a selected specialist agent."
        in normalized_glossary
    )
    assert "the agent definition carries no model" in normalized_glossary or (
        "An agent defined without a model runs on the primary session's model"
        in normalized_glossary
    )
    # Decision 71: the glossary also fixes the composition question and the
    # empty-pool honesty.
    assert "Composition question" in glossary
    assert (
        "a single model subagent, a subagent plus an OCR critic, and a custom "
        "composition" in normalized_glossary
    )
    assert "a pool that reads as empty recommends the default composition" in normalized_glossary
    assert (
        "the agent fills the selection template from the user's answer to the "
        "composition question" in normalized_glossary
    )
    for locale in ("en", "ru"):
        rules = run_panel.poll_rules(locale)
        assert "~/.config/opencode/agents/*.md" in rules  # runtime text, not the portable archive
        assert ".opencode/agents/*.md" in rules
        # Decision 71: the runtime rule carries the same configured-only
        # grounding and the explicit package-asset exclusion, both locales.
        assert "node_modules" in rules
        assert "installed packages or plugins" in rules or (
            "установленных пакетов или плагинов" in rules
        )
        assert "`configure agent`" in rules
        assert "configured" in rules or "настроенных" in rules
        if locale == "en":
            assert "never propose two critics on the same single model" in rules
            assert "record the installed pool as unknown - never" in rules
            assert "the pool is empty and the honest recommendation" in rules
        else:
            assert "двух критиков на одной и той же модели" in rules
            assert "делает пул неизвестным - не пустым" in rules
            assert "пул пуст и честная рекомендация" in rules
        poll = run_panel.poll(locale, "normal", 500)
        if locale == "en":
            assert (
                "two critics on the same single model are not an independent check" in poll["text"]
            )
            assert "a subagent on the same model or a" in poll["text"]
        else:
            assert "два критика на одной и той же модели - не независимая проверка" in poll["text"]
            assert "субагент на той же модели или выбранный профильный агент" in poll["text"]


def test_the_poll_collects_the_choice_interactively() -> None:
    """Decision 71: after the verbatim fenced presentation the choice is
    collected through the host's native interactive question tool with the
    minimum option set; the agent fills the selection template from the answer
    and runs the printed command itself, so the user never writes JSON, and
    the explicit-skip fast path still records the default. The same rule is
    pinned in the runtime poll rules (both locales)."""
    from reviewmatic import run_panel

    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    panel = " ".join(
        (SKILL_DIR / "references" / "review-panel.md").read_text(encoding="utf-8").split()
    )
    run_path = " ".join(
        (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8").split()
    )
    glossary = " ".join(
        (SKILL_DIR / "references" / "poll-glossary.md").read_text(encoding="utf-8").split()
    )
    minimum = (
        "the recommended composition, a single model subagent, a subagent plus an "
        "OCR critic, and a custom composition"
    )
    fill = "the selection template from"
    for text in (panel, run_path, glossary):
        assert "interactive question tool" in text
        assert minimum in text
        assert fill in text
    assert "the user never writes JSON" in panel
    assert "the user never writes JSON" in run_path
    assert "An explicit skip records exactly the default" in panel
    assert "an explicit skip records exactly the default" in run_path
    assert "collect the user's choice with the host's native interactive question tool" in entry
    assert "the user never writes JSON" in entry
    for locale in ("en", "ru"):
        rules = run_panel.poll_rules(locale)
        if locale == "en":
            assert "host's native interactive question tool" in rules
            assert "a single model subagent" in rules
            assert "a subagent plus an OCR critic" in rules
            assert "custom composition" in rules
            assert "never ask the user to write JSON" in rules
            assert "an explicit skip records exactly the default" in rules
        else:
            assert "интерактивным вопросом хоста" in rules
            assert "одного модельного субагента" in rules
            assert "субагента плюс OCR-критика" in rules
            assert "свой состав" in rules
            assert "не проси пользователя писать JSON" in rules
            assert "явный skip записывает ровно умолчание" in rules


def test_no_bare_package_cli_grounds_the_critic_pool() -> None:
    """The bare ``agentomatic agent list`` is gone from the skill contract;
    the pool is grounded on the host's agent inventory files and the
    ``agent`` key of opencode.json, and an unreadable source records the
    pool as unknown, never empty."""
    for document in skill_documents():
        assert "agentomatic" not in document.read_text(encoding="utf-8"), document.name


def test_the_review_requires_a_user_checkout() -> None:
    """``run``/``start-review`` require ``--repo-root``: the skill asks the
    user for a checkout, the runner never clones for the MR, and a fork MR
    reaches its head through a registered fork remote or an anonymous URL."""
    run_path = " ".join(
        (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8").split()
    )
    for marker in (
        "The checkout is required: ask the",
        "the run never clones or creates a repository for the MR",
        "register the fork as a new remote with `git remote add`",
        "an instructive error naming the missing remote — never substitute silently",
        "--repo-root",
    ):
        assert marker in run_path, marker


def test_the_stage_router_maps_stages_to_single_files_with_per_file_caps() -> None:
    """The router carries a stage → file table and has no single read-list of
    every reference; the mandatory start is `run-path.md`, a stage reads only
    its own file, and every reference file stays within the per-file cap.
    There is no total cap on the corpus — its combined weight is an audit
    signal reported by the executor, never a test (decision 7)."""
    router = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert "| Stage | File |" in router
    assert "The mandatory start is `run-path.md`" in router
    assert "a stage reads only its own file" in router
    assert "never the whole set up front" in router
    stage_rows = {row: "references/run-path.md" in row for row in router.splitlines()}
    assert any(row for row in stage_rows), "the router maps the run path stage"
    # No single read-list: the router never enumerates the whole corpus in one
    # paragraph (the stage table is the only mapping surface), and the forced
    # read-everything pattern of the pre-router wave must not return.
    assert "Read `references/run-path.md`, `references/review-panel.md`," not in router
    assert "For a GitLab MR also read" not in router
    documents = sorted(SKILL_DIR.glob("references/*.md"))
    assert documents, "the reference corpus must exist"
    for document in documents:
        size = document.stat().st_size
        assert size <= 16_384, f"{document.name} is {size} bytes; the per-file cap is 16 KiB"


def test_the_discussion_contract_carries_conventional_comments_and_validation() -> None:
    """Thread replies open with a Conventional Comments label, and the
    validation question ('does the change solve the problem it was made
    for?') is assigned to critics and weighed by the arbitrator."""
    panel = " ".join(
        (SKILL_DIR / "references" / "review-panel.md").read_text(encoding="utf-8").split()
    )
    stages = " ".join(
        (SKILL_DIR / "references" / "remote-review-stages.md").read_text(encoding="utf-8").split()
    )
    boxed = " ".join(
        (SKILL_DIR / "references" / "finding-examples.md").read_text(encoding="utf-8").split()
    )
    assert "does the change solve the problem it was made for" in panel
    assert "the arbitrator weighs those answers" in panel
    assert "Conventional Comments" in stages
    for label in ("`suggestion`", "`issue`", "`question`", "`note`", "`praise`", "`todo`"):
        assert label in stages, label
    assert "the arbitrator resolves that observation as explicitly as a critic" in stages
    assert "no severity or evidence labels" in boxed


def test_the_context_package_contract_lists_related_issues() -> None:
    """The scope lists the MR's related issues collected from `closes_issues`
    with author_text origin, and a failed collection leaves the linkage
    unknown, never empty."""
    stages = " ".join(
        (SKILL_DIR / "references" / "remote-review-stages.md").read_text(encoding="utf-8").split()
    )
    package = " ".join(
        (SKILL_DIR / "references" / "context-package.md").read_text(encoding="utf-8").split()
    )
    assert "`closes_issues`" in stages
    assert "author_text" in stages
    assert "the linkage is unverified" in stages or "leaves the linkage unknown" in stages
    assert "collected related" in package or "related issues" in package


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


def test_the_orchestrator_reads_by_path_within_a_window_budget() -> None:
    """The router pins the reading-budget contract: contracts come from runtime
    responses, never from runtime sources or full schema dumps; the context
    package travels by path; large reads are bounded or delegated."""
    router = " ".join(
        (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8").split()
    )
    for marker in (
        (
            "They never come from reading the runtime's source code or dumping complete "
            "JSON schemas into the conversation to derive input fields"
        ),
        (
            "Never read the whole recorded context package into the main window: "
            "critics and arbitrators receive it by path"
        ),
        "a bounded read (a head, a targeted grep, a single section)",
        (
            "Never re-read an entire artifact into the main window to answer a "
            "question the runtime response already answers"
        ),
    ):
        assert marker in router, marker


def test_post_poll_drift_routes_through_re_anchor_without_a_second_critic() -> None:
    """The stale-pipeline trap is neutralized by the existing delta mechanism:
    a pipeline transition during the poll never restarts the run, and the run's
    OCR measurement stays the pre-poll render."""
    run_path = " ".join(
        (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8").split()
    )
    for marker in (
        "A pipeline transition that arrives while the poll waits",
        "post-collection drift, not a poll answer",
        "never restarts the run, never re-collects evidence, and never adds a second critic",
        "The OCR background was measured before the poll",
        "fingerprint comparison without persisting keeps authorship",
        "one CI delta target checked with `record-delta` while prior checks stay in history",
        "one fresh delta check, never a second critic",
        "A full restart with re-collection is only for changed code or changed notes",
    ):
        assert marker in run_path, marker


def test_run_critic_templates_carry_the_pre_stamped_identity() -> None:
    """Templates the run emits pre-stamp the run identity; the receipt's
    session_id is the critic subagent's real session id."""
    run_path = " ".join(
        (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8").split()
    )
    assert "its `run_id` already carries this reviewmatic run's identity" in run_path
    assert "`session_id` is the real session id of that critic subagent" in run_path


def test_a_content_template_stays_on_the_repair_path() -> None:
    """The run emits only the prose projection; `template-review --kind content`
    is confined to the marked repair and interactive paths."""
    stages = " ".join(
        (SKILL_DIR / "references" / "remote-review-stages.md").read_text(encoding="utf-8").split()
    )
    assert "`template-review --kind content`" in stages
    assert "a run's content stop emits only the prose projection" in stages
    assert "`record-prose` merges the authored prose keys onto the re-rendered content" in stages
    assert "never replaces the prose projection on the run path" in stages


def test_the_bulk_poll_wording_names_the_actual_participants() -> None:
    """``ordinary model critic`` is gone: the texts name a subagent on the
    current model and state the arbitrator's engine explicitly."""
    joined = "\n".join(document.read_text(encoding="utf-8") for document in skill_documents())
    assert "ordinary model critic" not in joined
    assert "ordinary critic and one ordinary arbitrator" not in joined


def test_the_tail_routing_precedence_is_documented() -> None:
    """Render before prose before finalize; structural edits are repair. The
    router preserves the pinned stage order: run path, inverted tail, doctrine."""
    router = (SKILL_DIR / "references" / "workflow.md").read_text(encoding="utf-8")
    assert (
        router.index("Run path: the primary")
        < router.index("The inverted tail")
        < router.index("Necessity and completion")
    )
    tail = (SKILL_DIR / "references" / "inverted-tail.md").read_text(encoding="utf-8")
    section = " ".join(tail[tail.index("The inverted tail") :].split())
    render_at = section.index("render-review --draft")
    prose_at = section.index("record-prose --draft")
    assert render_at < prose_at, "render-review precedes record-prose in the tail"
    assert "re-anchor-review" in section
    assert "requires a recorded repair kind" in section
    assert "primary `run` path" in section
    assert "decision → shared render → record-prose → finalize" in section
    assert "Historical checks certify the old snapshot" in section
    assert "Line mapping proves a publication position, never the truth" in section
    run = (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8")
    primary = " ".join(run[run.index("Run path: the primary") :].split())
    assert "shared renderer" in primary
    assert "record-prose --artifact-root" in primary
    assert "scaffold-review` is the structural repair" in primary
    assert primary.index("shared renderer") < primary.index("record-prose --artifact-root")


def test_standalone_runbook_and_semantic_input_contract_are_documented() -> None:
    run_path = (SKILL_DIR / "references" / "run-path.md").read_text(encoding="utf-8")
    tail = (SKILL_DIR / "references" / "inverted-tail.md").read_text(encoding="utf-8")
    history = " ".join(
        (SKILL_DIR / "references" / "incremental-review.md").read_text(encoding="utf-8").split()
    )
    entry = (SKILL_DIR / "SKILL.source.md").read_text(encoding="utf-8")
    assert "history_context" in entry
    workflow = f"{run_path}\n{tail}"
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


def _normalized(path: Path) -> str:
    # The markdown formatter escapes underscores in prose; unescape them so
    # assertions can use the runtime's literal field names.
    return " ".join(path.read_text(encoding="utf-8").split()).replace("\\_", "_")


def test_the_printed_critic_contract_is_the_pinned_receipt_source() -> None:
    """A1/A4/A8: every critic surface prints the receipt contract; the skill
    pins the printout as the only format source and the digest semantics."""
    panel = _normalized(SKILL_DIR / "references" / "review-panel.md")
    run_path = _normalized(SKILL_DIR / "references" / "run-path.md")
    for fragment in (
        "the complete receipt dictionary",
        "confirmed|refuted|not_verified",
        "the question's own `context_digest` from the recorded package",
        "never the evidence digest",
        "never open a schema or a reference to learn a receipt field",
        "answers every question the package assigns to critics",
    ):
        assert fragment in panel, fragment
    for fragment in (
        "the printed receipt contract",
        "the context_digest semantics",
    ):
        assert fragment in run_path, fragment


def test_the_validate_only_probe_is_documented_as_write_free() -> None:
    """A2: the skill documents the write-free receipt probe."""
    run_path = _normalized(SKILL_DIR / "references" / "run-path.md")
    assert "--validate-only" in run_path
    assert "the stage and every digest stay identical" in run_path
    flags = {command: flags for _file, command, flags, _doc in parse_invocations()}
    assert "--validate-only" in flags.get("record-artifact", set()), (
        "run-path.md must invoke record-artifact --validate-only so the flag stays "
        "checked against the real CLI surface"
    )


def test_the_decision_surface_contract_is_documented() -> None:
    """A3/A9: the decision stop prints vocabularies, the blocking rule, and a
    prefilled template; the skill pins all three."""
    run_path = _normalized(SKILL_DIR / "references" / "run-path.md")
    for fragment in (
        "the template arrives prefilled from the recorded",
        "responses[].decision",
        "`ready|blocked|not_ready`",
        "ci_job_assessments[].classification",
        "arbitration `merge_verdict` ladder",
        "every accepted non-low finding is blocking",
        "`severity_override` to low",
        "`push_back` verdict",
    ):
        assert fragment in run_path, fragment


def test_the_replace_artifact_continuation_is_printed_and_documented() -> None:
    """A5: the runtime prints the rewound stage; repair.md routes by it."""
    repair = _normalized(SKILL_DIR / "references" / "repair.md")
    assert "the response prints" in repair
    assert "the rewound stage and the exact continuation" in repair
    assert "continue from the finalize stage" in repair


def test_the_refresh_prefill_contract_is_documented() -> None:
    """A7: the refreshed package materializes prefilled from the recorded one."""
    repair = _normalized(SKILL_DIR / "references" / "repair.md")
    for fragment in (
        "materialized prefilled from the recorded package",
        "carried verbatim",
        "the binding and thread registry refreshed by the machine",
        "`supersedes` preset to the previous package digest",
        "the printed package contract naming the stale",
    ):
        assert fragment in repair, fragment


def test_release_prepare_pins_reading_discipline_humanize_and_the_helper_contracts() -> None:
    """B1-B5 + C1/C4: the release family prints its contracts, keeps prose in
    assets, treats the illustration as optional, routes staleness through the
    one-step rebind, and pins the humanize pass as a required step."""
    release = REPO_ROOT / "skills" / "release-prepare" / "references"
    workflow = _normalized(release / "workflow.md")
    for fragment in (
        # B1/B2: the printed answer is the only format source.
        "the complete contract of every helper surface is printed",
        "never read runtime sources",
        "content-template --bundle",
        # B5: prose lives in asset files, never in JSON strings.
        "description and the announcement are prose assets",
        "description_file",
        "never inline long prose into the JSON content",
        # B3: the illustration is optional without invented values.
        "The illustration is optional",
        "leave `illustration_prompt` empty",
        "Never invent an artwork prompt",
        # B4: staleness routes through the one-step rebind.
        "rebind --plan",
        "re-walking the prepare → inventory → scaffold → finalize chain",
        # C1/C4: the humanize pass is a pinned workflow step with a done-when.
        "apply the `humanize` skill to the title, description, and announcement",
        "required workflow step, not a suggestion",
        "garden suggestion",
        "no sentence of the final prose relies on those patterns",
    ):
        assert fragment in workflow, fragment


# --- Reference map pins: the docs maps and the runtime vocabulary move together. ---

# The pipeline map is the first section of the review reference, both locales.
REVIEW_MAP_FILES = {
    "en": REPO_ROOT / "docs" / "reference" / "code-review.md",
    "ru": REPO_ROOT / "docs" / "ru" / "reference" / "code-review.md",
}
RELEASE_MAP_FILES = {
    "en": REPO_ROOT / "docs" / "reference" / "release-prepare.md",
    "ru": REPO_ROOT / "docs" / "ru" / "reference" / "release-prepare.md",
}
MAP_SECTIONS = {"en": "## Pipeline map", "ru": "## Карта конвейера"}

# The one-process run emits this waiting stage on top of the progress stages
# in REVIEW_STAGES.
RUN_STAGES = frozenset(REVIEW_STAGES) | {"delta_check_missing"}

# Snake-case surface names on the review map that are not progress stages.
REVIEW_SNAKE_TOKENS = frozenset({"poll_block", "final_checklist"})

# The release chain the release-prepare skill drives: the portable contract
# subcommands behind scripts/prepare_release.py, pinned like REQUIRED_DOCUMENTED.
RELEASE_DOCUMENTED = (
    "prepare",
    "inventory",
    "content-template",
    "scaffold",
    "finalize",
    "rebind",
    "post-merge",
)
RELEASE_STAGES = ("pre_merge", "post_merge")

# The materialized template, the prose assets, and the declined-illustration
# key the content stage owns.
RELEASE_ASSET_MARKERS = (
    "release-content.template.json",
    "release-description.md",
    "release-announcement.md",
    "description_file",
    "announcement_file",
    "illustration_prompt",
)

# Snake-case fields on the release map beyond the two publication stages.
RELEASE_SNAKE_TOKENS = frozenset({"description_file", "announcement_file", "illustration_prompt"})

# Hyphenated tokens on the maps that are neither commands nor options: the
# skill names and the materialized file names printed by the runtime.
MAP_DOMAIN_TOKENS = frozenset(
    {
        "code-review",  # the skill line name
        "release-prepare",  # the skill name
        "out-of-order",  # recorded-artifact ordering class, not a command
        "release-publication",  # the release-publication.json plan pointer
        "release-content",  # the release-content.template.json template
        "release-description",  # the release-description.md prose asset
        "release-announcement",  # the release-announcement.md prose asset
        "prepare_release",  # the portable helper script name
        "work-item",  # the GitLab work-item domain term
    }
)

MAP_TOKEN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z][a-z0-9]+)+")
SNAKE_TOKEN = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")
FLAG_TOKEN = re.compile(r"--[a-z][a-z-]*")

CONTRACT_SOURCE = (
    REPO_ROOT
    / "apps"
    / "reviewmatic"
    / "src"
    / "reviewmatic"
    / "portable"
    / "portable_gitlab"
    / "contract.py"
)


def document_section(path: Path, heading: str) -> str:
    """From the pinned heading to the next same-level heading."""
    text = path.read_text(encoding="utf-8")
    start = text.index(f"{heading}\n") + len(heading)
    rest = text[start:]
    stop = rest.find("\n## ")
    return rest if stop < 0 else rest[:stop]


def map_code_lines(text: str) -> list[str]:
    """One entry per inline code span and fenced-block line, as code_lines does."""
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            lines.append(stripped)
        else:
            lines.extend(match.strip() for match in re.findall(r"`([^`]+)`", line))
    return lines


def map_token_violations(
    text: str,
    *,
    commands: set[str],
    options: set[str],
    stages: set[str],
    snake: set[str],
) -> list[str]:
    """Command, option, and stage tokens on a map that the runtime does not own.

    Angle-bracket placeholders are not tokens; flags are checked by their
    stripped option names against the runtime option vocabulary.
    """
    violations: set[str] = set()
    for line in map_code_lines(text):
        # Mermaid labels carry literal reflow markers; placeholders are not tokens.
        remainder = re.sub(r"\\n", " ", line)
        remainder = re.sub(r"<[^>]*>", " ", remainder)
        for flag in FLAG_TOKEN.findall(remainder):
            if flag[2:] not in options:
                violations.add(flag)
            remainder = remainder.replace(flag, " ")
        for token in MAP_TOKEN.findall(remainder):
            if token not in commands and token not in MAP_DOMAIN_TOKENS:
                violations.add(token)
        for token in SNAKE_TOKEN.findall(remainder):
            if token not in stages and token not in snake and token not in MAP_DOMAIN_TOKENS:
                violations.add(token)
    return sorted(violations)


def runtime_command_vocabulary() -> tuple[set[str], set[str]]:
    commands = set(command_options())
    options = {
        name.removeprefix("--") for names in command_options().values() for name in names
    } | {option.name for option in GLOBAL_OPTIONS}
    return commands, options


def portable_command_vocabulary() -> tuple[set[str], set[str]]:
    """Subcommands and options materialized from the portable GitLab contract."""
    source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    commands = set(re.findall(r'subparsers\.add_parser\("([a-z-]+)"\)', source))
    options = set(re.findall(r'add_argument\("--([a-z-]+)"', source))
    return commands, options


def test_the_pipeline_map_is_the_first_section_of_the_review_reference() -> None:
    for locale, path in REVIEW_MAP_FILES.items():
        text = path.read_text(encoding="utf-8")
        assert text.index(MAP_SECTIONS[locale]) == text.index("\n## ") + 1, (
            f"{locale}: the pipeline map must be the first section"
        )


def test_the_pipeline_map_names_every_runtime_command_and_stage() -> None:
    for locale, path in REVIEW_MAP_FILES.items():
        section = document_section(path, MAP_SECTIONS[locale])
        missing = [
            name for name in (*REQUIRED_DOCUMENTED, *sorted(RUN_STAGES)) if name not in section
        ]
        assert not missing, f"{locale}: the pipeline map must name {missing}"


def test_the_pipeline_map_does_not_invent_runtime_tokens() -> None:
    commands, options = runtime_command_vocabulary()
    for locale, path in REVIEW_MAP_FILES.items():
        section = document_section(path, MAP_SECTIONS[locale])
        violations = map_token_violations(
            section,
            commands=commands,
            options=options,
            stages=set(RUN_STAGES),
            snake=set(REVIEW_SNAKE_TOKENS),
        )
        assert not violations, (
            f"{locale}: the pipeline map names tokens the runtime does not own: {violations}"
        )


def test_the_release_map_names_the_release_chain() -> None:
    for locale, path in RELEASE_MAP_FILES.items():
        text = path.read_text(encoding="utf-8")
        missing = [
            name
            for name in (*RELEASE_DOCUMENTED, *RELEASE_STAGES, *RELEASE_ASSET_MARKERS)
            if name not in text
        ]
        assert not missing, f"{locale}: the release map must name {missing}"


def test_the_release_map_does_not_invent_runtime_tokens() -> None:
    portable_commands, portable_options = portable_command_vocabulary()
    commands, options = runtime_command_vocabulary()
    for locale, path in RELEASE_MAP_FILES.items():
        violations = map_token_violations(
            path.read_text(encoding="utf-8"),
            commands=commands | portable_commands,
            options=options | portable_options,
            stages=set(RELEASE_STAGES),
            snake=set(RELEASE_SNAKE_TOKENS),
        )
        assert not violations, (
            f"{locale}: the release map names tokens the runtime does not own: {violations}"
        )


def test_the_maps_invoke_only_real_reviewmatic_surfaces() -> None:
    documents = [*REVIEW_MAP_FILES.values(), *RELEASE_MAP_FILES.values()]
    invocations = invocations_in(documents)
    assert any(command == "run" for _file, command, _flags, _doc in invocations), (
        "the pipeline map must invoke the runtime it maps"
    )
