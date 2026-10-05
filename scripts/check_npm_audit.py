#!/usr/bin/env python3
"""Fail npm audit for every advisory without a documented acknowledgement."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

ADVISORY_URL = re.compile(r"^https://github\.com/advisories/(?P<identifier>GHSA-[0-9a-z-]+)$")

# Documented compatibility reasons for advisories the gate cannot fix today.
# Every entry must state why the advisory is accepted and when to remove it;
# any advisory missing from this mapping still fails the audit.
ADVISORY_ACKNOWLEDGEMENTS: dict[str, str] = {
    "GHSA-ch52-4w7c-c8xp": (
        "CVE-2026-93748 http-cache-semantics <=4.2.0 can disclose cross-user "
        "cached responses via max-stale; no patched version exists upstream "
        "(reviewed 2026-10-02) and the package is only reachable through "
        "dev-time npm registry fetches of @opencode/plugin tooling; remove "
        "this acknowledgement once a patched release exists"
    ),
}


class AuditError(Exception):
    """The audit report itself could not be trusted or produced."""


def advisory_identifier(entry: Mapping[str, Any], package: str) -> str:
    url = entry.get("url")
    match = ADVISORY_URL.match(url) if isinstance(url, str) else None
    if match is None:
        raise AuditError(f"advisory for {package} has no GHSA url: {entry!r}")
    return match.group("identifier")


def collect_advisories(report: Mapping[str, Any]) -> dict[str, list[str]]:
    """Map advisory identifiers to the vulnerable package names they cover."""
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise AuditError("npm audit report has no vulnerabilities object")
    advisories: dict[str, set[str]] = {}
    for package, entry in sorted(vulnerabilities.items()):
        via = entry.get("via") if isinstance(entry, dict) else None
        if not isinstance(via, list):
            raise AuditError(f"vulnerability {package} has no via list")
        for item in via:
            if isinstance(item, dict):
                identifier = advisory_identifier(item, package)
                advisories.setdefault(identifier, set()).add(package)
    return {identifier: sorted(packages) for identifier, packages in sorted(advisories.items())}


def run_npm_audit(prefix: str | None) -> Mapping[str, Any]:
    command = ["npm", "audit", "--package-lock-only", "--json"]
    if prefix:
        command.extend(("--prefix", prefix))
    process = subprocess.run(  # noqa: S603 - Fixed npm audit snapshot of the lockfile.
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        detail = process.stderr.strip() or f"exit {process.returncode}"
        raise AuditError(f"npm audit returned no JSON report ({detail})") from error
    if not isinstance(report, dict):
        raise AuditError("npm audit report is not an object")
    return report


def evaluate(report: Mapping[str, Any]) -> tuple[dict[str, list[str]], list[str]]:
    """Split advisories into acknowledged entries and unknown failures."""
    advisories = collect_advisories(report)
    unknown = sorted(set(advisories) - set(ADVISORY_ACKNOWLEDGEMENTS))
    acknowledged = {
        identifier: packages
        for identifier, packages in advisories.items()
        if identifier in ADVISORY_ACKNOWLEDGEMENTS
    }
    return acknowledged, unknown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        help="npm --prefix directory to audit (defaults to the repository root)",
    )
    arguments = parser.parse_args(argv)
    scope = arguments.prefix or "."
    try:
        report = run_npm_audit(arguments.prefix)
        acknowledged, unknown = evaluate(report)
    except AuditError as error:
        print(f"npm audit gate failed for {scope}: {error}", file=sys.stderr)
        return 2
    for identifier, packages in acknowledged.items():
        print(f"acknowledged {identifier} in {', '.join(packages)}")
        print(f"  {ADVISORY_ACKNOWLEDGEMENTS[identifier]}")
    for identifier in unknown:
        print(f"unacknowledged advisory {identifier} in {scope}", file=sys.stderr)
    if unknown:
        return 1
    print(f"npm audit clean for {scope} (acknowledged: {len(acknowledged)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
