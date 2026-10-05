#!/usr/bin/env python3
"""Wait for the terminal CI success of one revision before publishing it.

The dev publication trusts the CI run of the exact revision instead of
repeating the full gate: the workflow awaits a completed ``success`` run of
``ci.yml`` for the revision and refuses to publish when the run failed or
was cancelled. A cancelled run means a newer push superseded the revision,
so the publication stops instead of overtaking it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_ORIGIN = "https://api.github.com"
USER_AGENT = "kisev-skills-ci-trust"
WORKFLOW = "ci.yml"
REVISION = re.compile(r"^[0-9a-fA-F]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9.-]+/[A-Za-z0-9_.-]+$")
ACTIVE_STATES = frozenset({"queued", "in_progress", "waiting"})
FAILED_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "startup_failure", "action_required"}
)


class TrustError(Exception):
    """Terminal CI success for the revision could not be established."""


def workflow_runs(repository: str, revision: str, token: str) -> tuple[int, Any]:
    query = urllib.parse.urlencode({"head_sha": revision, "per_page": 100})
    request = urllib.request.Request(
        f"{API_ORIGIN}/repos/{repository}/actions/workflows/{WORKFLOW}/runs?{query}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None
    except (OSError, json.JSONDecodeError, urllib.error.URLError):
        return 0, None


def run_list(status: int, payload: Any) -> list[dict[str, Any]]:
    if status != 200 or not isinstance(payload, dict):
        return []
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict)]


def completed_conclusions(runs: list[dict[str, Any]]) -> dict[int, str]:
    conclusions: dict[int, str] = {}
    for run in runs:
        identifier = run.get("id")
        conclusion = run.get("conclusion")
        if (
            isinstance(identifier, int)
            and run.get("status") == "completed"
            and isinstance(conclusion, str)
        ):
            conclusions[identifier] = conclusion
    return conclusions


def decide(runs: list[dict[str, Any]]) -> str | None:
    """Return "success" when trusted, None while waiting, or fail closed."""
    if any(run.get("status") in ACTIVE_STATES for run in runs):
        return None
    conclusions = completed_conclusions(runs)
    if not conclusions:
        return None
    if "success" in conclusions.values():
        return "success"
    detail = ", ".join(sorted(set(conclusions.values())))
    if set(conclusions.values()) <= FAILED_CONCLUSIONS:
        if "cancelled" in conclusions.values():
            raise TrustError(
                "CI for this revision was cancelled; a newer push superseded it,"
                " so the publication must stop"
            )
        raise TrustError(f"CI for this revision failed and must not be published: {detail}")
    raise TrustError(f"CI for this revision reached no trusted conclusion: {detail}")


def trusted_result(runs: list[dict[str, Any]], revision: str) -> dict[str, Any]:
    conclusions = completed_conclusions(runs)
    identifier = max(key for key, value in conclusions.items() if value == "success")
    url = next(run.get("html_url") for run in runs if run.get("id") == identifier)
    return {"revision": revision, "run": identifier, "status": "trusted", "url": url}


def await_success(
    repository: str, revision: str, token: str, attempts: int, interval: float
) -> dict[str, Any]:
    problem = "no CI run was observed"
    for attempt in range(attempts):
        status, payload = workflow_runs(repository, revision, token)
        runs = run_list(status, payload)
        if status != 200:
            problem = f"the CI runs lookup returned HTTP {status}"
        elif not runs:
            problem = "no CI run exists for this revision"
        outcome = decide(runs)
        if outcome == "success":
            return trusted_result(runs, revision)
        if outcome is None and runs:
            problem = "the CI runs for this revision never reached a terminal state"
        if attempt < attempts - 1:
            time.sleep(interval)
    raise TrustError(
        f"terminal CI success for {revision} was not observed within {attempts} attempts: {problem}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempts", type=int, default=80)
    parser.add_argument("--interval", type=float, default=30.0)
    arguments = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    revision = os.environ.get("CI_REVISION", "")
    if not token:
        parser.error("GH_TOKEN with actions:read is required")
    if REPOSITORY.fullmatch(repository) is None:
        parser.error("GITHUB_REPOSITORY must identify owner/name")
    if REVISION.fullmatch(revision) is None:
        parser.error("CI_REVISION must be a full commit SHA")
    if arguments.attempts < 1 or arguments.interval <= 0:
        parser.error("attempts and interval must be positive")
    try:
        result = await_success(repository, revision, token, arguments.attempts, arguments.interval)
    except TrustError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
