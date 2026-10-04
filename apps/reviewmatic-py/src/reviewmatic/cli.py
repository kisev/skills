"""Reviewmatic command-line surface.

Stage 1 of the Python port: the complete command surface of the TypeScript CLI
(``apps/reviewmatic/src/cli.ts``) with the contract exit codes, implemented
only for the operations that the materialized canonical runtime fully provides
(``capabilities``, ``assess-mode``, the historical ``publication`` stub, and
``marker-run``). Every other subcommand answers an explicit not-implemented
envelope with exit code 5 instead of pretending to work; the business logic
lands in stage 2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reviewmatic import __version__
from reviewmatic.portable import state_artifacts
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Sequence

PROGRAM_DESCRIPTION = "Interactive terminal companion for GitLab code reviews"
PROFILE = "code-review"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2
EXIT_UNSUPPORTED = 4
EXIT_NOT_IMPLEMENTED = 5

NOT_IMPLEMENTED_HINT = "is not implemented in stage 1; reviewmatic business logic lands in stage 2"
INVALID_COMMAND = "a supported subcommand is required"


@dataclass(frozen=True)
class OptionSpec:
    """One option of the CLI surface, mirroring the TypeScript fields."""

    name: str
    description: str
    required: bool = False
    default: str | None = None
    choices: tuple[str, ...] | None = None
    flag: bool = False
    collect: bool = False
    env: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    """One subcommand of the TypeScript CLI surface."""

    signature: str
    description: str
    options: tuple[OptionSpec, ...] = ()


# Transcribed 1:1 from the command definitions in apps/reviewmatic/src/cli.ts.
DEFINITIONS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "repair-review",
        "Open an existing new plan for targeted local repair",
        (
            OptionSpec("artifact-root", "artifact root", required=True),
            OptionSpec(
                "kind",
                "repair scope",
                choices=("presentation", "fix", "decision"),
                default="presentation",
            ),
        ),
    ),
    CommandSpec(
        "refresh-review",
        "Refresh changed evidence while retaining draft findings and decisions",
        (OptionSpec("draft", "existing review draft", required=True),),
    ),
    CommandSpec(
        "start-review",
        "Collect evidence and context once and create one editable review draft",
        (
            OptionSpec("url", "exact HTTPS GitLab merge request URL", required=True),
            OptionSpec("repo-root", "local checkout root; defaults to the current repository"),
            OptionSpec(
                "review-mode",
                "review depth",
                default="normal",
                choices=("fast", "normal", "deep"),
            ),
            OptionSpec("locale", "response language", default="en", choices=("en", "ru")),
            OptionSpec(
                "incremental",
                "incremental baseline policy",
                default="auto",
                choices=("auto", "off"),
            ),
        ),
    ),
    CommandSpec(
        "resume-review",
        "Recover the selected editable draft without recollecting GitLab",
        (OptionSpec("artifact-root", "artifact root", required=True),),
    ),
    CommandSpec(
        "check-review",
        "Validate the entire draft locally without committing review state",
        (OptionSpec("draft", "generated editable review draft", required=True),),
    ),
    CommandSpec(
        "finish-review",
        "Revalidate freshness once and finalize the complete review atomically",
        (OptionSpec("draft", "generated editable review draft", required=True),),
    ),
    CommandSpec(
        "prepare",
        "Collect GET-only GitLab evidence and initialize review progress",
        (
            OptionSpec("url", "exact HTTPS GitLab merge request URL", collect=True),
            OptionSpec("project-url", "exact HTTPS GitLab project URL"),
            OptionSpec("repo-root", "local checkout root"),
            OptionSpec(
                "review-mode",
                "review depth",
                default="normal",
                choices=("fast", "normal", "deep"),
            ),
            OptionSpec("locale", "response language", default="en", choices=("en", "ru")),
            OptionSpec(
                "incremental",
                "incremental baseline policy",
                default="auto",
                choices=("auto", "off"),
            ),
        ),
    ),
    CommandSpec(
        "context",
        "Collect the review context for selected evidence",
        (
            OptionSpec("evidence", "evidence snapshot path", required=True),
            OptionSpec("repo-root", "local checkout root", required=True),
            OptionSpec(
                "incremental",
                "incremental baseline policy",
                default="auto",
                choices=("auto", "off"),
            ),
            OptionSpec(
                "review-mode",
                "review depth",
                default="normal",
                choices=("fast", "normal", "deep"),
            ),
            OptionSpec("locale", "response language", default="en", choices=("en", "ru")),
        ),
    ),
    CommandSpec(
        "scaffold-review",
        "Scaffold the immutable review plan",
        (
            OptionSpec("evidence", "evidence snapshot path", required=True),
            OptionSpec("context", "review context path", required=True),
            OptionSpec("decision", "review decision path", required=True),
            OptionSpec("content", "plan content file", required=True),
        ),
    ),
    CommandSpec(
        "status",
        "Print the current review status",
        (OptionSpec("artifact-root", "artifact root", required=True),),
    ),
    CommandSpec(
        "next",
        "Print the current review status and next action",
        (OptionSpec("artifact-root", "artifact root", required=True),),
    ),
    CommandSpec(
        "template-review",
        "Emit a review template for the current stage",
        (
            OptionSpec("artifact-root", "artifact root", required=True),
            OptionSpec(
                "kind",
                "template kind",
                required=True,
                choices=("critic", "decision", "content"),
            ),
        ),
    ),
    CommandSpec(
        "report-review",
        "Revalidate and report the finished review",
        (OptionSpec("artifact-root", "artifact root", required=True),),
    ),
    CommandSpec(
        "finalize",
        "Recheck evidence freshness and record the finalize report",
        (
            OptionSpec("artifact-root", "artifact root", required=True),
            OptionSpec("report", "readiness report path"),
        ),
    ),
    CommandSpec(
        "record-package",
        "Record the agent-authored context package bound to selected evidence",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "completed context package input", required=True),
        ),
    ),
    CommandSpec(
        "record-input",
        "Apply semantic review sections to the prepared draft, preserving machine bindings",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "semantic sections input file", required=True),
        ),
    ),
    CommandSpec(
        "record-critic",
        "Import one independent critic receipt into the draft verbatim",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "critic receipt response file", required=True),
            OptionSpec("participant", "selected critic participant name this receipt binds to"),
        ),
    ),
    CommandSpec(
        "record-participants",
        "Record the selected critic panel and arbitrator once",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "participant selection input file", required=True),
        ),
    ),
    CommandSpec(
        "record-arbitration",
        "Import one arbitrator receipt with a verdict over every critic finding",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "arbitration receipt response file", required=True),
        ),
    ),
    CommandSpec(
        "scope-review",
        "Print the prepared review scope overview from recorded evidence",
        (OptionSpec("artifact-root", "artifact root", required=True),),
    ),
    CommandSpec(
        "prepare-local",
        "Collect local WIP evidence: staged, unstaged, and untracked",
        (
            OptionSpec("repo-root", "local checkout root", required=True),
            OptionSpec(
                "ref",
                "explicit local comparison revision; adds its commits since the merge base"
                " with HEAD",
            ),
            OptionSpec(
                "incremental",
                "incremental baseline policy",
                default="auto",
                choices=("auto", "off"),
            ),
        ),
    ),
    CommandSpec(
        "finalize-local",
        "Check local WIP evidence freshness",
        (
            OptionSpec("bundle", "local WIP snapshot path", required=True),
            OptionSpec("report", "local review draft path"),
        ),
    ),
    CommandSpec(
        "assess-mode",
        "Check whether a review mode is supported",
        (
            OptionSpec(
                "mode",
                "requested review mode",
                required=True,
                choices=("fast", "normal", "deep"),
            ),
            OptionSpec("critic-available", "an independent critic is available", flag=True),
        ),
    ),
    CommandSpec(
        "finalize-review",
        "Verify the finalized review decision without external mutations",
        (
            OptionSpec("evidence", "evidence snapshot path", required=True),
            OptionSpec("report", "review decision path", required=True),
            OptionSpec(
                "mode",
                "review mode",
                required=True,
                choices=("fast", "normal", "deep", "incremental", "unchanged"),
            ),
            OptionSpec("critic-receipt", "critic receipt path"),
            OptionSpec("finalize-report", "finalize report path", required=True),
            OptionSpec("context", "review context path", required=True),
        ),
    ),
    CommandSpec(
        "record-artifact",
        "Record a private schema-valid review artifact",
        (
            OptionSpec(
                "kind",
                "artifact kind",
                required=True,
                choices=("analysis_report", "critic_receipt", "release_readiness"),
            ),
            OptionSpec("evidence", "evidence snapshot path", required=True),
            OptionSpec("input", "artifact input path", required=True),
        ),
    ),
    CommandSpec(
        "plan",
        "Open the finalized review plan in the experimental TUI",
        (
            OptionSpec("artifact-root", "artifact root; discovered automatically when omitted"),
            OptionSpec("print", "print the plan overview without a terminal UI", flag=True),
        ),
    ),
    CommandSpec(
        "worktree list",
        "List review worktrees recorded by local patch application",
    ),
    CommandSpec(
        "publication [mode]",
        "Historical guarded actions are no longer executable",
        (
            OptionSpec("action", "publication action path"),
            OptionSpec("confirm", "action SHA-256 digest"),
        ),
    ),
    CommandSpec("capabilities", "Print machine capabilities JSON"),
    CommandSpec("marker-run [mutation...]", "Run a mutation and record its post-success marker"),
)

GLOBAL_OPTIONS: tuple[OptionSpec, ...] = (
    OptionSpec(
        "config",
        "JSON configuration file (CLI > env > file > defaults)",
        env="REVIEWMATIC_CONFIG",
    ),
    OptionSpec("json", "machine-readable result on stdout", flag=True, env="REVIEWMATIC_JSON"),
    OptionSpec(
        "log-level",
        "diagnostic verbosity on stderr",
        choices=("debug", "info", "warn", "error", "silent"),
        env="REVIEWMATIC_LOG_LEVEL",
    ),
    OptionSpec(
        "log-format",
        "diagnostic format on stderr",
        choices=("text", "json"),
        env="REVIEWMATIC_LOG_FORMAT",
    ),
    OptionSpec(
        "progress",
        "terminal progress; never written to stdout",
        choices=("auto", "always", "never"),
        env="REVIEWMATIC_PROGRESS",
    ),
    OptionSpec(
        "color",
        "color policy (NO_COLOR disables color)",
        choices=("auto", "always", "never"),
        env="REVIEWMATIC_COLOR",
    ),
    OptionSpec("capabilities", "print machine capabilities JSON and exit", flag=True),
)

MARKER_RUN_FLAGS = (
    "--skill",
    "--action",
    "--binding",
    "--stdin-sha256",
    "--cwd",
    "--git-head-digest",
)


def option_dest(name: str) -> str:
    """Convert an option name to its namespace attribute (TypeScript parity)."""
    head, *rest = name.split("-")
    return head + "".join(part.title() for part in rest)


class _TrackedAction(argparse.Action):
    """Base for actions that record their destination in a shared source set."""

    def __init__(
        self,
        option_strings: list[str],
        dest: str,
        sources: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self._sources = sources if sources is not None else set()
        super().__init__(option_strings, dest, **kwargs)

    def _record(self) -> None:
        self._sources.add(self.dest)


class _ValueAction(_TrackedAction):
    """Store one value and mark the option as CLI-provided."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, values)
        self._record()


class _AppendAction(_TrackedAction):
    """Append one value and mark the option as CLI-provided."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        collected = getattr(namespace, self.dest, None)
        collected = [] if collected is None else [*collected, values]
        setattr(namespace, self.dest, collected)
        self._record()


class _FlagAction(_TrackedAction):
    """Store true and mark the option as CLI-provided."""

    def __init__(
        self,
        option_strings: list[str],
        dest: str,
        sources: set[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(option_strings, dest, sources, nargs=0, const=True, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        setattr(namespace, self.dest, self.const)
        self._record()


def _add_option(
    parser: argparse.ArgumentParser,
    spec: OptionSpec,
    default: Any,
    tracked_sources: set[str],
) -> None:
    """Register one option with TypeScript-compatible parsing behavior."""
    flag = f"--{spec.name}"
    dest = option_dest(spec.name)
    kwargs: dict[str, Any] = {
        "dest": dest,
        "default": default,
        "help": spec.description,
        "sources": tracked_sources,
    }
    if spec.flag:
        parser.add_argument(flag, action=_FlagAction, **kwargs)
        return
    kwargs["action"] = _AppendAction if spec.collect else _ValueAction
    if spec.choices is not None:
        kwargs["choices"] = spec.choices
        kwargs["metavar"] = "value"
    if spec.required:
        kwargs["required"] = True
    parser.add_argument(flag, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete parser for the reviewmatic command surface.

    Global options use ``SUPPRESS`` defaults so that Python 3.12 subparser
    parsing never copies an unset global over a value the main parser already
    recorded; the effective global defaults are installed through
    ``set_defaults`` on the main parser instead.
    """
    tracked_sources: set[str] = set()
    env_sources = {
        option_dest(spec.name) for spec in GLOBAL_OPTIONS if spec.env and os.environ.get(spec.env)
    }
    parser = argparse.ArgumentParser(
        prog="reviewmatic",
        description=PROGRAM_DESCRIPTION,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="show the reviewmatic version and exit",
    )
    global_defaults: dict[str, Any] = {
        option_dest(spec.name): (
            os.environ.get(spec.env) if spec.env is not None and not spec.flag else False
        )
        for spec in GLOBAL_OPTIONS
    }
    parser.set_defaults(sources=tracked_sources, env_sources=env_sources, **global_defaults)
    for spec in GLOBAL_OPTIONS:
        _add_option(parser, spec, argparse.SUPPRESS, tracked_sources)
    globals_parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    for spec in GLOBAL_OPTIONS:
        _add_option(globals_parser, spec, argparse.SUPPRESS, tracked_sources)
    subparsers = parser.add_subparsers(dest="command", metavar="command", required=False)
    for definition in DEFINITIONS:
        name = definition.signature.partition(" ")[0]
        sub = subparsers.add_parser(
            name,
            description=definition.description,
            allow_abbrev=False,
            parents=[globals_parser],
        )
        for option in definition.options:
            _add_option(sub, option, option.default, tracked_sources)
        if name == "worktree":
            sub.add_argument("list", nargs="?", help="list recorded review worktrees")
        elif name == "publication":
            sub.add_argument("mode", nargs="?", help="publication mode")
    return parser


class ConfigError(Exception):
    """The configuration file is unreadable or not a JSON object."""


def load_config(path: str | None) -> dict[str, Any]:
    """Load the JSON configuration file (``configFile`` parity)."""
    if path is None:
        return {}
    try:
        value: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(str(error)) from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigError("configuration must be a JSON object")
    return value


def apply_config(
    namespace: argparse.Namespace,
    config: dict[str, Any],
    specs: dict[str, OptionSpec],
) -> None:
    """Apply configuration-file values under the CLI > env > file > defaults order."""
    sources: set[str] = getattr(namespace, "sources", set()) | getattr(
        namespace, "env_sources", set()
    )
    for key, value in config.items():
        if key in {"yes", "config"} or key not in specs or key in sources:
            continue
        spec = specs[key]
        if spec.flag:
            if not isinstance(value, bool):
                raise ConfigError(f"{key} must be boolean")
            setattr(namespace, key, value)
            continue
        if not isinstance(value, str):
            raise ConfigError(f"invalid configuration value for {key}")
        if spec.choices is not None and value not in spec.choices:
            raise ConfigError(f"invalid configuration value for {key}")
        setattr(namespace, key, value)


def all_specs() -> dict[str, OptionSpec]:
    """Map every option destination to its specification."""
    specs: dict[str, OptionSpec] = {option_dest(s.name): s for s in GLOBAL_OPTIONS}
    for definition in DEFINITIONS:
        for option in definition.options:
            specs[option_dest(option.name)] = option
    return specs


def fail(message: str) -> int:
    """Report an unexpected CLI failure (``fail()`` parity for stage-1 paths)."""
    print(f"reviewmatic: {message}", file=sys.stderr)
    return EXIT_ERROR


def not_implemented(command: str) -> int:
    """Answer with the explicit stage-1 not-implemented contract."""
    return contract.error(
        "not_implemented", f"{command} {NOT_IMPLEMENTED_HINT}", EXIT_NOT_IMPLEMENTED
    )


def run_assess_mode(namespace: argparse.Namespace) -> int:
    """Check whether a review mode is supported (contract operation)."""
    mode: str = namespace.mode
    if mode in ("normal", "deep") and namespace.criticAvailable is not True:
        contract.emit(
            {
                "status": "unsupported",
                "reason": "independent critic receipt is required",
                "details": {"mode": mode},
            }
        )
        return EXIT_UNSUPPORTED
    contract.emit(
        {
            "status": "ok",
            "mode": mode,
            "independent_critic_required": mode in ("normal", "deep"),
        }
    )
    return EXIT_OK


def run_publication() -> int:
    """Historical guarded actions remain blocked (contract operation)."""
    contract.emit(
        {
            "status": "blocked",
            "error": (
                "Legacy guarded actions are historical only; prepare a new runbook"
                " with direct glab commands"
            ),
            "external_mutations": False,
        }
    )
    return EXIT_INVALID


def parse_marker_run_arguments(tokens: Sequence[str]) -> argparse.Namespace:
    """Parse ``marker-run`` options and the trailing mutation (TypeScript parity)."""
    values: dict[str, str] = {}
    mutation: list[str] = []
    index = 0
    while index < len(tokens):
        argument = tokens[index]
        if argument == "--" or not argument.startswith("-") or argument == "-":
            mutation = list(tokens[index:])
            break
        if argument not in MARKER_RUN_FLAGS:
            raise state_artifacts.StateArtifactError(f"unrecognized arguments: {argument}")
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        if (
            following is None
            or following == "--"
            or (following.startswith("-") and following != "-")
        ):
            raise state_artifacts.StateArtifactError(f"argument {argument}: expected one argument")
        values[argument] = following
        index += 2
    missing = [flag for flag in ("--skill", "--action", "--binding") if flag not in values]
    if missing:
        raise state_artifacts.StateArtifactError(
            f"the following arguments are required: {', '.join(missing)}"
        )
    return argparse.Namespace(
        skill=values["--skill"],
        action=values["--action"],
        binding=values["--binding"],
        stdin_sha256=values.get("--stdin-sha256"),
        cwd=values.get("--cwd"),
        git_head_digest=values.get("--git-head-digest"),
        mutation=mutation,
    )


def run_marker_run(tokens: Sequence[str]) -> int:
    """Run one mutation and record its post-success marker (contract operation)."""
    try:
        return state_artifacts.marker_run(parse_marker_run_arguments(tokens))
    except state_artifacts.StateArtifactError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVALID


def dispatch(namespace: argparse.Namespace, tokens: Sequence[str]) -> int:
    """Route one parsed invocation with the TypeScript exit-code contract."""
    name: str = namespace.command
    if name == "publication" and "--capabilities" in tokens[tokens.index(name) + 1 :]:
        contract.emit(
            {
                "operations": [],
                "publication": "manual glab commands",
                "external_mutations": False,
            }
        )
        return EXIT_OK
    if namespace.capabilities or name == "capabilities":
        return contract.capabilities(PROFILE)
    if name == "publication":
        return run_publication()
    if name == "assess-mode":
        return run_assess_mode(namespace)
    if name == "worktree":
        if getattr(namespace, "list", None) == "list":
            return not_implemented("worktree list")
        return contract.error("invalid_command", INVALID_COMMAND)
    return not_implemented(name)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point implementing the stage-1 CLI contract."""
    tokens = list(sys.argv[1:] if argv is None else argv)
    if not tokens:
        if sys.stdout.isatty() and sys.stdin.isatty():
            return not_implemented("plan")
        build_parser().print_help(sys.stdout)
        return EXIT_OK
    if tokens[0] == "marker-run":
        return run_marker_run(tokens[1:])
    parser = build_parser()
    namespace = parser.parse_args(tokens)
    if namespace.command is None:
        if namespace.capabilities:
            return contract.capabilities(PROFILE)
        return contract.error("invalid_command", INVALID_COMMAND)
    try:
        apply_config(namespace, load_config(namespace.config), all_specs())
    except ConfigError as error:
        return fail(str(error))
    try:
        return dispatch(namespace, tokens)
    except contract.WorkflowError as error:
        code = "tool_unavailable" if "unavailable" in str(error) else "invalid_input"
        return contract.error(code, str(error), 3 if code == "tool_unavailable" else EXIT_INVALID)
