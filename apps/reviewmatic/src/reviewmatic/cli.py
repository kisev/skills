"""Python CLI for GitLab review workflows and local WIP reviews."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from reviewmatic import __version__, local_review, scope, workflow, worktree
from reviewmatic import draft as draft_module
from reviewmatic import run as run_module
from reviewmatic.portable import state_artifacts
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Sequence

PROGRAM_DESCRIPTION = "GitLab code review and local WIP review workflows"
PROFILE = "code-review"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2
EXIT_UNSUPPORTED = 4

INVALID_COMMAND = "a supported subcommand is required"


@dataclass(frozen=True)
class OptionSpec:
    """One option in the public CLI contract."""

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
    """One supported public subcommand."""

    signature: str
    description: str
    options: tuple[OptionSpec, ...] = ()


# This table is the source of truth for parser help and command options.
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
        "record-run-critic",
        "Import one run-panel model critic receipt and finish the panel when complete",
        (
            OptionSpec("artifact-root", "artifact root", required=True),
            OptionSpec("input", "critic receipt response file", required=True),
            OptionSpec(
                "participant",
                "selected model critic participant name this receipt binds to",
                required=True,
            ),
        ),
    ),
    CommandSpec(
        "record-participants",
        "Record the selected critic panel and arbitrator once",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("input", "participant selection input file", required=True),
            OptionSpec(
                "ocr-provider",
                'LLM provider override recorded for every engine:"ocr" critic',
            ),
            OptionSpec(
                "ocr-model",
                'LLM model override recorded for every engine:"ocr" critic',
            ),
        ),
    ),
    CommandSpec(
        "record-ocr-critic",
        "Run one selected OCR critic mechanically and import its receipt",
        (
            OptionSpec("draft", "generated editable review draft (remote MR mode)"),
            OptionSpec("bundle", "local WIP snapshot path (local mode)"),
            OptionSpec("participant", "selected OCR critic participant name", required=True),
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
        "run",
        "Drive the whole review cycle in one process with resume and authoring callbacks",
        (
            OptionSpec("url", "exact HTTPS GitLab merge request URL", required=True),
            OptionSpec("repo-root", "local checkout root; defaults to the current directory"),
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
            OptionSpec(
                "critic-cmd",
                "shell command filling one run-panel model critic receipt; the template and "
                "output paths arrive as $1 and $2",
            ),
            OptionSpec(
                "arbitrator-cmd",
                "shell command authoring the review decision that arbitrates critic findings;"
                " template and output paths arrive as $1 and $2",
            ),
            OptionSpec(
                "content-cmd",
                "shell command authoring the plan content; template and output paths arrive"
                " as $1 and $2",
            ),
            OptionSpec("resume", "continue the existing review from its current stage", flag=True),
            OptionSpec(
                "participants",
                "panel selection JSON answering the critic and engine poll; without it the "
                "run stops and prints the selection template",
            ),
            OptionSpec(
                "ocr-provider",
                'LLM provider override recorded for every engine:"ocr" critic',
            ),
            OptionSpec(
                "ocr-model",
                'LLM model override recorded for every engine:"ocr" critic',
            ),
        ),
    ),
    CommandSpec(
        "replace-artifact",
        "Replace one bound review artifact and rewind the review stage",
        (
            OptionSpec("artifact-root", "artifact root", required=True),
            OptionSpec(
                "kind",
                "artifact kind",
                required=True,
                choices=("context", "critic_receipt", "finalize_report", "decision"),
            ),
            OptionSpec("path", "replacement artifact JSON path", required=True),
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
    """Convert a long option name to its argparse namespace attribute."""
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
        collected = [values] if collected is None else [*collected, values]
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
    """Register one option with the declared parser behavior."""
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
    """Report an unexpected CLI failure."""
    print(f"reviewmatic: {message}", file=sys.stderr)
    return EXIT_ERROR


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
    """Parse ``marker-run`` options and the trailing mutation command."""
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
    """Route one parsed invocation with the public exit-code contract."""
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
            contract.emit(
                {
                    "status": "ok",
                    "items": [
                        {
                            "path": record["path"],
                            "branch": record["branch"],
                            "head_sha": record["head_sha"],
                            "mr_url": record["mr_url"],
                            "created_at": record["created_at"],
                            "commit_sha": record["commit_sha"],
                            "pushed": record["pushed"],
                        }
                        for record in worktree.registry_summary()
                    ],
                    "external_mutations": False,
                }
            )
            return EXIT_OK
        return contract.error("invalid_command", INVALID_COMMAND)
    try:
        return _dispatch_business(name, namespace)
    except contract.WorkflowError as error:
        code = "tool_unavailable" if "unavailable" in str(error) else "invalid_input"
        return contract.error(code, str(error), 3 if code == "tool_unavailable" else EXIT_INVALID)


def _one_target(namespace: argparse.Namespace, label: str) -> tuple[bool, bool]:
    has_draft = _field(namespace, "draft") is not None
    has_bundle = _field(namespace, "bundle") is not None
    if has_draft == has_bundle:
        raise contract.WorkflowError(
            f"{label} requires exactly one target: --draft for a remote MR review or --bundle "
            "for a local review"
        )
    return has_draft, has_bundle


def _dispatch_business(name: str, namespace: argparse.Namespace) -> int:
    """Run one business subcommand against the ported modules."""
    if name in {"repair-review", "refresh-review"}:
        result = (
            draft_module.repair_review(
                str(_field(namespace, "artifactRoot")), str(_field(namespace, "kind"))
            )
            if name == "repair-review"
            else draft_module.refresh_review(str(_field(namespace, "draft")))
        )
        contract.emit(result)
        return EXIT_OK if str(result["status"]) in {"ok", "needs_reassessment"} else EXIT_INVALID
    if name in {"start-review", "resume-review", "check-review", "finish-review"}:
        if name == "start-review":
            result = draft_module.start_review(
                url=str(_field(namespace, "url")),
                repo_root=_field(namespace, "repoRoot"),
                review_mode=_field(namespace, "reviewMode"),
                locale=_field(namespace, "locale"),
                incremental=_field(namespace, "incremental"),
            )
        elif name == "resume-review":
            result = draft_module.resume_review(str(_field(namespace, "artifactRoot")))
        elif name == "check-review":
            result = draft_module.check_review(str(_field(namespace, "draft")))
        else:
            result = draft_module.finish_review(str(_field(namespace, "draft")))
        contract.emit(result)
        return EXIT_OK if result["status"] == "ok" else EXIT_INVALID
    if name == "prepare-local":
        return _run_prepare_local(namespace)
    if name == "record-package":
        has_draft, _ = _one_target(namespace, "record-package")
        result = (
            draft_module.record_draft_package(
                str(_field(namespace, "draft")), str(_field(namespace, "input"))
            )
            if has_draft
            else local_review.record_local_package(
                str(_field(namespace, "bundle")), str(_field(namespace, "input"))
            )
        )
        contract.emit(result)
        return EXIT_OK
    if name == "record-ocr-critic":
        return _run_record_ocr(namespace)
    if name in {"record-input", "record-critic", "record-participants", "record-arbitration"}:
        return _run_record(name, namespace)
    if name == "record-run-critic":
        contract.emit(
            workflow.record_run_critic(
                argparse.Namespace(
                    artifact_root=_field(namespace, "artifactRoot"),
                    input=_field(namespace, "input"),
                    participant=_field(namespace, "participant"),
                )
            )
        )
        return EXIT_OK
    if name == "scope-review":
        contract.emit(
            {
                "status": "ok",
                "scope": scope.scope_for_root(str(_field(namespace, "artifactRoot"))),
                "external_mutations": False,
            }
        )
        return EXIT_OK
    if name == "run":
        return run_module.run(namespace)
    if name == "replace-artifact":
        contract.emit(
            workflow.replace_artifact(
                argparse.Namespace(
                    artifact_root=_field(namespace, "artifactRoot"),
                    kind=_field(namespace, "kind"),
                    path=_field(namespace, "path"),
                )
            )
        )
        return EXIT_OK
    if name == "finalize-local":
        return _run_finalize_local(namespace)
    if name == "prepare":
        return _run_prepare(namespace)
    workflow_arguments = _workflow_namespace(name, namespace)
    code = workflow.dispatch(workflow_arguments)
    if code is not None:
        return code
    return contract.error("invalid_command", INVALID_COMMAND)


def _field(namespace: argparse.Namespace, name: str) -> Any:
    """Read one option by its CLI spelling; absent options read as None."""
    return getattr(namespace, name, None)


def _workflow_namespace(name: str, namespace: argparse.Namespace) -> argparse.Namespace:
    # workflow.dispatch and workflow.prepared read snake_case attributes; the
    # parsed namespace stores option dests in camelCase (see option_dest).
    return argparse.Namespace(
        command=name,
        artifact_root=_field(namespace, "artifactRoot"),
        evidence=_field(namespace, "evidence"),
        repo_root=_field(namespace, "repoRoot"),
        incremental=_field(namespace, "incremental"),
        review_mode=_field(namespace, "reviewMode"),
        locale=_field(namespace, "locale"),
        kind=_field(namespace, "kind"),
        report=_field(namespace, "report"),
        finalize_report=_field(namespace, "finalizeReport"),
        context=_field(namespace, "context"),
        mode=_field(namespace, "mode"),
        decision=_field(namespace, "decision"),
        content=_field(namespace, "content"),
        critic_receipt=_field(namespace, "criticReceipt"),
        input=_field(namespace, "input"),
        path=_field(namespace, "path"),
    )


def _run_prepare(namespace: argparse.Namespace) -> int:
    urls = _field(namespace, "url") or []
    project_url = _field(namespace, "projectUrl")
    if bool(urls) == (project_url is not None):
        raise contract.WorkflowError("provide exact --url target or --project-url, but not both")
    if project_url is not None:
        raise contract.WorkflowError("project creation mode is only available for task preparation")
    if len(urls) != 1:
        raise contract.WorkflowError("code-review accepts exactly one --url target")
    target = contract.parse_target(urls[0], {"merge_requests"})
    results: list[dict[str, Any]] = []
    try:
        bundle = contract.collect(
            target, "code-review", locale=getattr(namespace, "locale", None) or "en"
        )
        item: dict[str, Any] = {
            "target": target["url"],
            "status": "ok",
            "artifact_path": bundle["preview_artifact_path"],
            "digest": bundle["preview_digest"],
            "artifact_root": bundle["artifact_root"],
            "head_sha": bundle["head_sha"],
            "base_sha": bundle.get("base_sha"),
            "start_sha": bundle.get("start_sha"),
            "complete": bundle["retrieval_complete"],
            "components_complete": bundle["components_complete"],
        }
        item.update(
            workflow.prepared(
                argparse.Namespace(
                    repo_root=_field(namespace, "repoRoot"),
                    review_mode=_field(namespace, "reviewMode") or "normal",
                    locale=_field(namespace, "locale") or "en",
                    incremental=_field(namespace, "incremental") or "auto",
                ),
                bundle,
            )
        )
        results.append(item)
    except contract.WorkflowError as error:
        results.append({"target": target["url"], "status": "error", "error": str(error)})
    status = "ok" if all(item["status"] == "ok" for item in results) else "partial"
    contract.emit(
        {
            "status": status,
            "summary": {
                "tldr": "Completed GET-only GitLab evidence preparation.",
                "scope": [item["target"] for item in results],
                "risks": [] if status == "ok" else ["one or more targets failed"],
                "checks": [
                    "exact target identity",
                    "endpoint allowlist",
                    "pagination completeness",
                    "exact SHA",
                ],
            },
            "items": results,
            "external_mutations": False,
        }
    )
    return EXIT_OK if status == "ok" else EXIT_ERROR


def _run_prepare_local(namespace: argparse.Namespace) -> int:
    bundle = local_review.local_bundle(
        str(_field(namespace, "repoRoot")), "code-review", _field(namespace, "ref")
    )
    sections = cast("dict[str, dict[str, Any]]", bundle["sections"])
    empty = local_review.empty_scope_reason(bundle)
    if empty is not None:
        contract.emit(
            {
                "status": "empty_scope",
                "reason": empty,
                "summary": {
                    "tldr": "No reviewable local scope exists at the selected boundary.",
                    "scope": [str(bundle["repo_root"])],
                    "risks": [],
                    "checks": ["HEAD", "staged", "unstaged", "non-ignored untracked", "merge base"],
                },
                "head_sha": bundle["head_sha"],
                "base_sha": bundle["base_sha"],
                "ref": bundle["ref"],
                "complete": bundle["retrieval_complete"],
                "external_mutations": False,
            }
        )
        return EXIT_INVALID
    root = contract.artifact_root(Path(str(bundle["artifact_root"])))
    bundle_path, digest_value = contract.write_artifact(root, "local_wip_snapshot", bundle)
    incremental = _field(namespace, "incremental") or "auto"
    review = local_review.prepare_followup(str(root), bundle, digest_value, incremental)
    # Materialize the draft for this snapshot at preparation time: an existing
    # draft bound to the same evidence survives untouched, while a missing or
    # stale draft is rebuilt from the current snapshot and baseline.
    draft_selection = local_review.select_local_draft(str(root), bundle, digest_value, incremental)
    if draft_selection["materialized"]:
        local_review.persist_local_draft(
            str(root),
            digest_value,
            draft_selection,
            cast("dict[str, Any]", draft_selection["draft"]),
        )
    contract.write_json(
        root / "current-local.json",
        {"evidence_path": str(bundle_path), "evidence_digest": digest_value},
    )
    complete = bundle["retrieval_complete"] is True
    contract.emit(
        {
            "status": "ok" if complete else "incomplete",
            "summary": {
                "tldr": "Collected local WIP evidence: staged, unstaged, and untracked.",
                "scope": [str(bundle["repo_root"])],
                "risks": [] if complete else ["local evidence incomplete"],
                "checks": [
                    "HEAD",
                    "staged",
                    "unstaged",
                    "non-ignored untracked",
                    "symlink/binary/size",
                ],
            },
            "bundle": str(bundle_path),
            "artifact_path": str(bundle_path),
            "digest": digest_value,
            "head_sha": bundle["head_sha"],
            "base_sha": bundle["base_sha"],
            "ref": bundle["ref"],
            "scope": {
                "committed": len(str(sections["committed"]["diff"])) > 0,
                "staged": len(str(sections["staged"]["diff"])) > 0,
                "unstaged": len(str(sections["unstaged"]["diff"])) > 0,
                "untracked_files": len(
                    cast("list[dict[str, Any]]", sections["untracked"]["items"])
                ),
            },
            "scope_overview": scope.local_scope(bundle, review, str(bundle_path)),
            "complete": bundle["retrieval_complete"],
            "review": review,
            "external_mutations": False,
        }
    )
    return EXIT_OK if complete else EXIT_INVALID


def _run_record(name: str, namespace: argparse.Namespace) -> int:
    draft_target = _field(namespace, "draft")
    bundle_target = _field(namespace, "bundle")
    input_target = _field(namespace, "input")
    labels = {
        "record-input": "record-input",
        "record-critic": "record-critic",
        "record-participants": "record-participants",
        "record-arbitration": "record-arbitration",
    }
    has_draft, _ = _one_target(namespace, labels[name])
    participant = _field(namespace, "participant") or None
    ocr_provider = _field(namespace, "ocrProvider") or None
    ocr_model = _field(namespace, "ocrModel") or None
    if name == "record-input":
        result = (
            draft_module.record_draft_input(str(draft_target), str(input_target))
            if has_draft
            else local_review.record_local_input(str(bundle_target), str(input_target))
        )
    elif name == "record-critic":
        result = (
            draft_module.record_draft_critic(str(draft_target), str(input_target), participant)
            if has_draft
            else local_review.record_local_critic(
                str(bundle_target), str(input_target), participant
            )
        )
    elif name == "record-participants":
        result = (
            draft_module.record_draft_participants(
                str(draft_target), str(input_target), ocr_provider, ocr_model
            )
            if has_draft
            else local_review.record_local_participants(
                str(bundle_target), str(input_target), ocr_provider, ocr_model
            )
        )
    else:
        result = (
            draft_module.record_draft_arbitration(str(draft_target), str(input_target))
            if has_draft
            else local_review.record_local_arbitration(str(bundle_target), str(input_target))
        )
    contract.emit(result)
    return EXIT_OK if result["status"] == "ok" else EXIT_INVALID


def _run_record_ocr(namespace: argparse.Namespace) -> int:
    has_draft, _ = _one_target(namespace, "record-ocr-critic")
    participant = str(_field(namespace, "participant"))
    result = (
        draft_module.record_ocr_critic(str(_field(namespace, "draft")), participant)
        if has_draft
        else local_review.record_local_ocr_critic(str(_field(namespace, "bundle")), participant)
    )
    contract.emit(result)
    return EXIT_OK if result["status"] == "ok" else EXIT_INVALID


def _run_finalize_local(namespace: argparse.Namespace) -> int:
    result = local_review.finalize_local(str(namespace.bundle))
    _, bundle = contract.artifact_payload(Path(str(namespace.bundle)), "local_wip_snapshot")
    root = contract.artifact_root(Path(str(bundle["artifact_root"])))
    result = contract.finalize_payload(
        result, Path(str(namespace.bundle)), bundle, "local_wip_snapshot"
    )
    report_path, report_digest = contract.write_artifact(root, "finalize_report", result)
    review_result: dict[str, Any] | None = None
    if getattr(namespace, "report", None) is not None and result["status"] == "ok":
        review_result = local_review.record_review(
            str(root), str(namespace.bundle), str(namespace.report)
        )
    contract.emit(
        {
            "status": result["status"],
            "summary": {
                "tldr": "Checked local WIP evidence freshness.",
                "scope": [str(bundle["repo_root"])],
                "risks": cast("list[str]", result.get("changed") or []),
                "checks": ["HEAD", "all WIP sections"],
            },
            "artifact_path": str(report_path),
            "digest": report_digest,
            "result": result,
            "review": review_result,
            "external_mutations": False,
        }
    )
    return EXIT_OK if result["status"] == "ok" else EXIT_INVALID


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the reviewmatic application."""
    tokens = list(sys.argv[1:] if argv is None else argv)
    if not tokens:
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
