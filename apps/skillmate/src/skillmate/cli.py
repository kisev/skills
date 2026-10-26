"""Command-line surface.

The five lifecycle commands resolve one content source, build a safety-model
plan per host, preview it, and write only after explicit confirmation. The
shared CLI conventions apply: arguments beat the config file beat the
environment beat defaults, unknown options fail, and help and version have
no side effects.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from skillmate import __version__
from skillmate.distribution import DEFAULT_INDEX_URL, DistributionError
from skillmate.installer import (
    InstallRecord,
    doctor,
    plan_install,
    plan_remove,
    resolve_source,
    status,
)
from skillmate.safety import SafetyError, execute

PLAN_SCHEMA = "skillmate-plan/v1"
HOSTS = ("codex", "claude", "opencode")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillmate",
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("--version", action="version", version=f"skillmate {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=None, help="JSON configuration file")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument(
        "--project-dir", type=Path, default=None, help="project root (default: cwd)"
    )
    common.add_argument("--home", type=Path, default=None, help="home directory (default: $HOME)")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "update"):
        command = commands.add_parser(name, parents=[common])
        command.add_argument("--hosts", default=None, help="comma-separated hosts")
        command.add_argument("--scope", choices=("project", "global"), default=None)
        command.add_argument(
            "--skill", action="append", dest="skills", help="install only this skill (repeatable)"
        )
        command.add_argument(
            "--yes", action="store_true", help="apply the previewed plan without a prompt"
        )
        command.add_argument("--index-url", default=None, help="distribution index URL")
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--version", dest="target_version", default=None)
        selection.add_argument(
            "--from-checkout",
            dest="from_checkout",
            type=Path,
            default=None,
            help="dev-only source: a working tree of this repository",
        )
    remove = commands.add_parser("remove", parents=[common])
    remove.add_argument("--hosts", default=None, help="comma-separated hosts")
    remove.add_argument("--scope", choices=("project", "global"), default=None)
    remove.add_argument(
        "--yes", action="store_true", help="apply the previewed plan without a prompt"
    )
    remove.add_argument(
        "--confirm-drift",
        action="store_true",
        help="also delete drifted owned files (explicit drift confirmation)",
    )
    doctor_command = commands.add_parser("doctor", parents=[common])
    doctor_command.add_argument("--hosts", default=None, help="comma-separated hosts")
    doctor_command.add_argument("--scope", choices=("project", "global"), default=None)
    doctor_command.add_argument("--index-url", default=None, help="distribution index URL")
    doctor_command.add_argument(
        "--from-checkout",
        dest="from_checkout",
        type=Path,
        default=None,
        help="diagnose against a working tree of this repository",
    )
    status_command = commands.add_parser("status", parents=[common])
    status_command.add_argument("--hosts", default=None, help="comma-separated hosts")
    return parser


def config_path(argv: list[str]) -> Path | None:
    """Resolve the config file: CLI argument beats SKILLMATE_CONFIG."""
    for index, argument in enumerate(argv):
        if argument == "--config" and index + 1 < len(argv):
            return Path(argv[index + 1])
    env = os.environ.get("SKILLMATE_CONFIG")
    return Path(env) if env else None


def load_config(path: Path | None) -> dict[str, Any]:
    """Read the JSON configuration file, rejecting unknown keys."""
    if path is None:
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliError(f"config file {path} is unreadable: {error}") from error
    if not isinstance(document, dict):
        raise CliError(f"config file {path} must be a JSON object")
    unknown = sorted(set(document) - CONFIG_KEYS)
    if unknown:
        raise CliError(f"config file {path} has unknown keys: {', '.join(unknown)}")
    return document


CONFIG_KEYS = {
    "hosts",
    "scope",
    "version",
    "from_checkout",
    "skills",
    "index_url",
    "project_dir",
    "home",
    "json",
}


class CliError(Exception):
    """A usage error the CLI reports without a traceback."""


def _hosts(argument: str | None, config: dict[str, Any]) -> tuple[str, ...]:
    value = argument or config.get("hosts") or ",".join(HOSTS)
    return tuple(host for host in value.split(",") if host)


def _emit(document: dict[str, Any], lines: list[str], as_json: bool) -> None:
    if as_json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        print("\n".join(lines))


def _confirm(as_json: bool, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if as_json or not sys.stdin.isatty():
        return False
    try:
        answer = input("Proceed? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() == "y"


def _lifecycle(
    namespace: argparse.Namespace, config: dict[str, Any], project: Path, home: Path
) -> int:
    hosts = _hosts(namespace.hosts, config)
    scope = namespace.scope or config.get("scope") or "project"
    as_json = namespace.json or bool(config.get("json"))
    document: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "command": namespace.command,
        "hosts": list(hosts),
        "scope": scope,
    }
    lines: list[str] = [f"{namespace.command} for {', '.join(hosts)} ({scope} scope)"]
    confirm_drift = False
    try:
        if namespace.command == "remove":
            entries = plan_remove(hosts, scope, project, home)
            plans = [plan for _, plan in entries if plan is not None]
            absent = [host for host, plan in entries if plan is None]
            document["not_installed"] = absent
            lines.extend(f"{host}: nothing installed" for host in absent)
            confirm_drift = namespace.confirm_drift
        else:
            from_checkout = namespace.from_checkout or (
                Path(config["from_checkout"]) if config.get("from_checkout") else None
            )
            target_version = namespace.target_version or config.get("version")
            index_url = namespace.index_url or config.get("index_url")
            selection = resolve_source(
                from_checkout, index_url or DEFAULT_INDEX_URL, target_version
            )
            skills = namespace.skills or config.get("skills")
            plans = list(
                plan_install(
                    selection,
                    hosts,
                    scope,
                    project,
                    home,
                    tuple(skills) if skills else None,
                )
            )
            document["source"] = selection.label
            document["target_version"] = selection.distribution.version
            if from_checkout is not None:
                document["checkout"] = str(from_checkout)
            lines.append(f"source: {selection.label} {selection.distribution.version}")
        document["plans"] = [plan.machine() for plan in plans]
        for plan in plans:
            lines.extend(plan.preview().splitlines())
            lines.append("")
        confirmed = _confirm(as_json, namespace.yes)
        if confirmed and plans:
            reports = []
            for plan in plans:
                report = execute(plan, confirmed=True, confirm_drift=confirm_drift)
                reports.append(
                    {
                        "root": str(plan.root),
                        "written": list(report.written),
                        "removed": list(report.removed),
                        "manifest": report.manifest,
                    }
                )
            document["executed"] = True
            document["reports"] = reports
            applied = sum(len(plan.steps) for plan in plans)
            lines.append(f"applied {applied} writes")
        else:
            document["executed"] = False
            lines.append("not confirmed; nothing written")
    except (DistributionError, SafetyError) as error:
        print(f"skillmate: {error}", file=sys.stderr)
        return 1
    _emit(document, lines, as_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        config = load_config(config_path(args))
        namespace = build_parser().parse_args(args)
    except CliError as error:
        print(f"skillmate: {error}", file=sys.stderr)
        return 2
    project = namespace.project_dir or (
        Path(config["project_dir"]) if config.get("project_dir") else Path.cwd()
    )
    home = namespace.home or (Path(config["home"]) if config.get("home") else Path.home())
    as_json = namespace.json or bool(config.get("json"))

    if namespace.command in ("install", "update", "remove"):
        return _lifecycle(namespace, config, project, home)

    if namespace.command == "doctor":
        hosts = _hosts(namespace.hosts, config)
        scope = namespace.scope or config.get("scope") or "project"
        index_url = namespace.index_url or config.get("index_url")
        selection = None
        source_problem = None
        try:
            selection = resolve_source(
                namespace.from_checkout, index_url or DEFAULT_INDEX_URL, None
            )
        except (DistributionError, SafetyError) as error:
            source_problem = str(error)
        findings = doctor(hosts, scope, project, home, selection)
        document = {
            "schema": "skillmate-doctor/v1",
            "hosts": list(hosts),
            "scope": scope,
            "source_unavailable": source_problem,
            "findings": [finding.__dict__ for finding in findings],
        }
        lines = [f"source unavailable: {source_problem}"] if source_problem else []
        lines.extend(
            f"{finding.host} ({finding.scope}) {finding.kind}: {finding.detail} -> {finding.repair}"
            for finding in findings
        )
        if not lines:
            lines = ["healthy"]
        _emit(document, lines, as_json)
        return 0

    hosts = _hosts(namespace.hosts, config)
    records: list[InstallRecord] = []
    for scope_name in ("project", "global"):
        records.extend(status(hosts, scope_name, project, home))
    document = {
        "schema": "skillmate-status/v1",
        "hosts": list(hosts),
        "records": [record.__dict__ for record in records],
    }
    lines = [
        f"{record.host} {record.scope}: {record.version} ({record.source}, {record.files} files)"
        for record in records
    ] or ["nothing installed"]
    _emit(document, lines, as_json)
    return 0
