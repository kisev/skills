"""The reviewmatic helper CLI: collect, background, drafts, revalidate, profiles, ocr."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from reviewmatic import __version__, background, drafts, ocr, profiles
from reviewmatic import collect as collect_module
from reviewmatic import revalidate as revalidate_module
from reviewmatic.portable.portable_gitlab import contract

PROGRAM_DESCRIPTION = "Mechanical helper runtime for mr-review"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID = 2

COMMIT_RE = re.compile(r"[0-9a-f]{40}")
DEFAULT_BACKGROUND_LIMIT = 8000


@dataclass(frozen=True)
class OptionSpec:
    """One documented command option."""

    name: str
    description: str
    required: bool = False
    default: str | None = None
    choices: tuple[str, ...] | None = None
    kind: str = "str"


@dataclass(frozen=True)
class CommandSpec:
    """One public subcommand and its options."""

    signature: str
    description: str
    options: tuple[OptionSpec, ...] = field(default_factory=tuple)


DEFINITIONS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "collect",
        "Collect one merge request read-only and bind it to exact revisions",
        (
            OptionSpec("url", "exact HTTPS GitLab merge request URL", required=True),
            OptionSpec("repo-root", "optional review checkout for local ref checks"),
            OptionSpec("output", "write the context JSON to this path"),
        ),
    ),
    CommandSpec(
        "background",
        "Assemble the OCR background file within the 8000-byte limit",
        (
            OptionSpec("input", "manager-authored background JSON", required=True),
            OptionSpec("output", "write the Markdown background to this path"),
            OptionSpec(
                "limit",
                "maximum background size in bytes",
                default=str(DEFAULT_BACKGROUND_LIMIT),
                kind="int",
            ),
        ),
    ),
    CommandSpec(
        "drafts",
        "Generate the head check and the GitLab draft-note shell block",
        (
            OptionSpec("input", "draft-note input JSON", required=True),
            OptionSpec("output", "write the shell block to this path"),
        ),
    ),
    CommandSpec(
        "revalidate",
        "Compare a collected snapshot with the current merge request head",
        (OptionSpec("snapshot", "collected context JSON", required=True),),
    ),
    CommandSpec(
        "profiles",
        "Print the effective review profile and provider validation",
        (OptionSpec("cwd", "directory whose local profile is read"),),
    ),
    CommandSpec(
        "ocr-runs",
        "Run one OCR process per selected reviewer, in parallel",
        (
            OptionSpec("repo", "checkout root for the OCR range", required=True),
            OptionSpec("from", "range start revision", required=True),
            OptionSpec("to", "range end revision", required=True),
            OptionSpec("background", "Markdown background file", required=True),
            OptionSpec("reviewers", "comma-separated profile aliases"),
            OptionSpec("provider", "one-off OCR provider"),
            OptionSpec("model", "one-off OCR model"),
            OptionSpec(
                "effort", "one-off OCR effort", choices=("low", "medium", "high"), default="medium"
            ),
            OptionSpec("output-dir", "directory for per-run JSON output", required=True),
            OptionSpec("timeout", "per-run timeout in seconds", default="900", kind="int"),
            OptionSpec("resume", "OCR session id to resume"),
        ),
    ),
    CommandSpec(
        "ocr-compare",
        "Compare two persisted OCR sessions",
        (
            OptionSpec("before", "previous OCR session id", required=True),
            OptionSpec("after", "current OCR session id", required=True),
            OptionSpec("repo", "checkout root"),
            OptionSpec("timeout", "compare timeout in seconds", default="120", kind="int"),
        ),
    ),
    CommandSpec("runtime-info", "Print the runtime version and resolved install commit"),
)


def build_parser() -> argparse.ArgumentParser:
    """Build the complete parser for the helper command surface."""
    parser = argparse.ArgumentParser(
        prog="reviewmatic", description=PROGRAM_DESCRIPTION, allow_abbrev=False
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    for definition in DEFINITIONS:
        name = definition.signature.partition(" ")[0]
        sub = subparsers.add_parser(name, description=definition.description, allow_abbrev=False)
        for option in definition.options:
            kwargs: dict[str, Any] = {"help": option.description}
            if option.required:
                kwargs["required"] = True
            if option.choices is not None:
                kwargs["choices"] = option.choices
            if option.kind == "int":
                kwargs["type"] = int
                if option.default is not None:
                    kwargs["default"] = int(option.default)
            elif option.default is not None:
                kwargs["default"] = option.default
            sub.add_argument(f"--{option.name}", dest=option_dest(option.name), **kwargs)
    return parser


def option_dest(name: str) -> str:
    """argparse destination for one hyphenated option name."""
    if name in {"from", "to"}:
        return f"{name}_ref"
    return name.replace("-", "_")


def resolve_install_source(direct_url_text: str | None) -> dict[str, Any]:
    """Resolve the installation source from PEP 610 ``direct_url.json`` text."""
    unknown: dict[str, Any] = {"url": None, "vcs": None, "commit": "unknown"}
    if direct_url_text is None:
        return unknown
    try:
        value: object = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return unknown
    if not isinstance(value, dict):
        return unknown
    payload = cast("dict[str, Any]", value)
    url = payload.get("url") if isinstance(payload.get("url"), str) else None
    raw_vcs_info = payload.get("vcs_info")
    vcs_info = cast("dict[str, Any]", raw_vcs_info) if isinstance(raw_vcs_info, dict) else {}
    commit = vcs_info.get("commit_id")
    vcs = vcs_info.get("vcs")
    if not isinstance(vcs, str):
        vcs = payload.get("vcs") if isinstance(payload.get("vcs"), str) else None
    if not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        commit = payload.get("commit")
    if not (isinstance(commit, str) and COMMIT_RE.fullmatch(commit)):
        pinned = re.search(r"@([0-9a-f]{40})", url or "")
        commit = pinned.group(1) if pinned else None
    return {
        "url": url,
        "vcs": vcs,
        "commit": commit if isinstance(commit, str) else "unknown",
    }


def runtime_info() -> dict[str, Any]:
    """The runtime's self report: package version and resolved install commit."""
    try:
        text = importlib.metadata.distribution("reviewmatic").read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        text = None
    return {
        "status": "ok",
        "version": __version__,
        **resolve_install_source(text),
        "external_mutations": False,
    }


def _write(path: str | None, content: str) -> str | None:
    if path is None:
        return None
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _parse_int(value: int, label: str) -> int:
    if value <= 0:
        raise contract.WorkflowError(f"{label} must be a positive integer")
    return value


def _run_collect(namespace: argparse.Namespace) -> int:
    result = collect_module.collect(
        str(namespace.url), repo_root=cast("str | None", namespace.repo_root)
    )
    written = _write(cast("str | None", namespace.output), _json_text(result))
    payload = dict(result)
    if written is not None:
        payload["output_path"] = written
    contract.emit(payload)
    return EXIT_OK if result["retrieval_complete"] else EXIT_INVALID


def _run_background(namespace: argparse.Namespace) -> int:
    source = contract.read_json(Path(str(namespace.input)), "background input")
    try:
        result = background.build_background(source, limit=_parse_int(namespace.limit, "limit"))
    except ValueError as error:
        raise contract.WorkflowError(str(error)) from error
    written = _write(cast("str | None", namespace.output), str(result.pop("markdown")))
    if written is not None:
        result["output_path"] = written
    contract.emit(result)
    return EXIT_OK


def _run_drafts(namespace: argparse.Namespace) -> int:
    source = contract.read_json(Path(str(namespace.input)), "draft input")
    result = drafts.build_drafts(source)
    shell = str(result.pop("shell"))
    written = _write(cast("str | None", namespace.output), shell)
    if written is not None:
        result["output_path"] = written
    else:
        result["shell"] = shell
    contract.emit(result)
    return EXIT_OK


def _run_revalidate(namespace: argparse.Namespace) -> int:
    source = contract.read_json(Path(str(namespace.snapshot)), "collected snapshot")
    result = revalidate_module.revalidate(source)
    contract.emit(result)
    return EXIT_OK


def _run_profiles(namespace: argparse.Namespace) -> int:
    cwd = cast("str | None", namespace.cwd)
    profile = profiles.load(Path(cwd) if cwd else None)
    profile["provider_validation"] = profiles.validate_providers(
        cast("list[dict[str, str]]", profile["reviewers"])
    )
    contract.emit(profile)
    return EXIT_OK


def _resolve_reviewers(namespace: argparse.Namespace) -> list[dict[str, str]]:
    aliases_value = cast("str | None", namespace.reviewers)
    provider = cast("str | None", namespace.provider)
    model = cast("str | None", namespace.model)
    if aliases_value is not None and (provider is not None or model is not None):
        raise contract.WorkflowError(
            "use either --reviewers or a one-off --provider/--model, not both"
        )
    if provider is not None or model is not None:
        if not provider or not model:
            raise contract.WorkflowError("a one-off OCR run needs both --provider and --model")
        return [
            {
                "alias": "one-off",
                "provider": provider,
                "model": model,
                "effort": str(namespace.effort),
            }
        ]
    if aliases_value is None:
        # No profile choice and no one-off: use OCR's own configured default.
        return [
            {
                "alias": "configured",
                "provider": "",
                "model": "",
                "effort": str(namespace.effort),
            }
        ]
    profile = profiles.load()
    aliases = (
        [alias.strip() for alias in aliases_value.split(",") if alias.strip()]
        if aliases_value is not None
        else []
    )
    return profiles.select(profile, aliases)


def _run_ocr_runs(namespace: argparse.Namespace) -> int:
    reviewers = _resolve_reviewers(namespace)
    result = ocr.run_reviews(
        repo=str(namespace.repo),
        from_ref=str(namespace.from_ref),
        to_ref=str(namespace.to_ref),
        background=Path(str(namespace.background)),
        reviewers=reviewers,
        output_dir=Path(str(namespace.output_dir)),
        timeout=_parse_int(namespace.timeout, "timeout"),
        resume=cast("str | None", namespace.resume),
    )
    result["provider_validation"] = profiles.validate_providers(reviewers)
    contract.emit(result)
    return EXIT_OK if result["status"] == "ok" else EXIT_ERROR


def _run_ocr_compare(namespace: argparse.Namespace) -> int:
    result = ocr.compare(
        str(namespace.before),
        str(namespace.after),
        repo=cast("str | None", namespace.repo),
        timeout=_parse_int(namespace.timeout, "timeout"),
    )
    contract.emit(result)
    return EXIT_OK


DISPATCH = {
    "collect": _run_collect,
    "background": _run_background,
    "drafts": _run_drafts,
    "revalidate": _run_revalidate,
    "profiles": _run_profiles,
    "ocr-runs": _run_ocr_runs,
    "ocr-compare": _run_ocr_compare,
}


def main(argv: list[str] | None = None) -> int:
    """Parse and dispatch one helper invocation."""
    parser = build_parser()
    namespace = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if namespace.command is None:
        parser.print_help(sys.stderr)
        return EXIT_INVALID
    if namespace.command == "runtime-info":
        contract.emit(runtime_info())
        return EXIT_OK
    handler = DISPATCH.get(namespace.command)
    if handler is None:
        return contract.error("invalid_command", "a supported subcommand is required")
    try:
        return handler(namespace)
    except contract.WorkflowError as error:
        return contract.error("invalid_input", str(error))
    except OSError as error:
        return contract.error("io_error", str(error))
