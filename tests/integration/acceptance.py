#!/usr/bin/env python3
"""The skill acceptance umbrella: one launcher over every live skill family.

``task acceptance`` runs the explicitly configured live acceptance for all
44 skills; ``task acceptance SKILL=<name>`` runs one skill's entry. Under the
hood it drives the existing harnesses (the fake-glab code-review acceptance,
the GitLab live run, the Mattermost live run) plus minimal behavioral probes
for every skill the harnesses do not cover. Every run leaves machine
(``result.json``) and human (``summary.md``) reports; the terminal shows
line-by-line progress (skill, family, stage, model, elapsed). The exit code
aggregates the family verdicts; a skip is an honest non-run with a printed
reason, never a green check.

The umbrella is explicitly optional (same class as ``live:run``): it needs
provider credentials and never runs inside ``task check``, ``check:core``,
Lefthook hooks, CI, or the gate registry. It is user-run; the report is meant
to be pasted back into the master session.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tests.integration.acceptance_probes import PROBES, SKIPS
from tests.integration.gitlab.scripts.skill_acceptance import (
    CHEAP_MODEL,
    PROVIDER_KEYS,
    TransportError,
    VerificationError,
    parse_events,
    read_json_file,
    spawn,
)
from tests.integration.mattermost.scripts.stand import (
    ROOT,
    load,
    private_directory,
    write_json,
)

LIVE_CHECKS = ROOT / "tests/integration/mattermost/scripts/live_checks.py"
EVAL_RUNNER = ROOT / "scripts/eval_runner.py"
BUILT_SKILLS = ROOT / ".build/skills"
REPORT_ROOT = ROOT / ".build/acceptance"
SKILL_ACCEPTANCE_REPORTS = ROOT / ".build/skill-acceptance"
GITLAB_REPORTS = ROOT / ".build/gitlab-test/gitlab-workflows/reports"
GITLAB_FIXTURES = ROOT / ".build/gitlab-test/gitlab-workflows/state/fixtures.json"
MATTERMOST_REPORTS = ROOT / ".build/mattermost-test/mattermost-cards/reports"

FAMILY_TASKS: dict[str, list[str]] = {
    "code-review-acceptance": [
        "mise",
        "exec",
        "--",
        "uv",
        "run",
        "--project",
        "apps/reviewmatic",
        "--locked",
        "python",
        "-m",
        "tests.integration.gitlab.scripts.skill_acceptance",
    ],
    "gitlab-live": [
        "mise",
        "exec",
        "--",
        "uv",
        "run",
        "--project",
        "apps/reviewmatic",
        "--locked",
        "python",
        "-m",
        "tests.integration.gitlab.scripts.stand",
        "live",
        "--compose",
        "docker-compose",
    ],
    "mattermost-live": [
        "mise",
        "exec",
        "--",
        "python",
        "-m",
        "tests.integration.mattermost.scripts.stand",
        "live",
        "--compose",
        "docker-compose",
    ],
}

FAMILY_REPORTS: dict[str, Path] = {
    "code-review-acceptance": SKILL_ACCEPTANCE_REPORTS / "latest.json",
    "gitlab-live": GITLAB_REPORTS / "latest.json",
    "mattermost-live": MATTERMOST_REPORTS / "latest.json",
}

HARNESS_SKILLS: dict[str, tuple[str, ...]] = {
    "code-review-acceptance": ("code-review",),
    "mattermost-live": ("mattermost", "mattermost-triage"),
    "gitlab-live": ("mr-prepare",),
}


class UmbrellaError(RuntimeError):
    """The umbrella is misconfigured; nothing ran."""


def settings(accept_expensive: bool) -> dict[str, Any]:
    os.environ.setdefault("EVAL_HOST", "opencode")
    os.environ.setdefault("EVAL_MODEL", "zai-coding-plan/glm-5.3-flash")
    os.environ.setdefault("EVAL_TIMEOUT", "5400")
    os.environ.setdefault("EVAL_MAX_TOKENS", "4000000")
    os.environ.setdefault("EVAL_MAX_COST", "40")
    if not any(os.environ.get(key) for key in PROVIDER_KEYS):
        raise UmbrellaError(
            "the acceptance umbrella requires explicit provider "
            "credentials/configuration (OPENCODE_CONFIG_CONTENT or a provider "
            "API key)"
        )
    if os.environ["EVAL_HOST"] != "opencode":
        # The probes and the code-review acceptance read opencode's stdout
        # JSONL events, so the umbrella is defined for the opencode host only.
        raise UmbrellaError("the acceptance umbrella drives the opencode host only")
    model = os.environ["EVAL_MODEL"]
    if not CHEAP_MODEL.search(model) and not (
        accept_expensive or os.environ.get("ACCEPT_EXPENSIVE") == "1"
    ):
        raise UmbrellaError(
            f"EVAL_MODEL={model} is not a known cheap (flash-class) model; "
            "pass --yes or export ACCEPT_EXPENSIVE=1 to accept the cost "
            "explicitly"
        )
    return {
        "host": os.environ["EVAL_HOST"],
        "model": model,
        "timeout_seconds": float(os.environ["EVAL_TIMEOUT"]),
        "max_tokens": int(os.environ["EVAL_MAX_TOKENS"]),
        "max_cost": float(os.environ["EVAL_MAX_COST"]),
    }


def cost_estimate() -> str:
    """The last measured costs across families, for the pre-flight line."""
    measured: list[float] = []
    for pointer in FAMILY_REPORTS.values():
        for attempt in (pointer_report(pointer) or {}).get("attempts", []):
            usage = attempt.get("usage") if isinstance(attempt, dict) else None
            if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
                measured.append(float(usage["cost"]))
    for live in (
        pointer_report(GITLAB_REPORTS / "latest.json"),
        pointer_report(MATTERMOST_REPORTS / "latest.json"),
    ):
        usage = (live or {}).get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
            measured.append(float(usage["cost"]))
    if not measured:
        return "unknown (no measured prior run)"
    return f"~${sum(measured):.2f} measured in prior runs"


def pointer_report(pointer: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
        report = Path(value["report"]) if "report" in value else Path(value["path"])
        return cast("dict[str, Any]", json.loads(report.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def progress(skill: str, family: str, stage: str, model: str, started: float) -> None:
    print(
        f"[umbrella] skill={skill} family={family} stage={stage} model={model} "
        f"elapsed={int(time.monotonic() - started)}s",
        flush=True,
    )


def all_skills() -> list[str]:
    if not BUILT_SKILLS.is_dir():
        raise UmbrellaError("the built skill archives are missing; run task skills:build")
    return sorted(path.name for path in BUILT_SKILLS.iterdir() if (path / "SKILL.md").is_file())


def plan(skill: str | None, inventory: list[str]) -> list[dict[str, Any]]:
    """One entry per family (harnesses) or per skill (probes, skips)."""
    entries: list[dict[str, Any]] = [
        {"skills": list(members), "family": family} for family, members in HARNESS_SKILLS.items()
    ]
    entries += [{"skills": [name], "family": "behavior-probe"} for name in sorted(PROBES)]
    entries += [{"skills": [name], "family": "skip"} for name in sorted(SKIPS)]
    registered = {name for entry in entries for name in entry["skills"]}
    missing = sorted(set(inventory) - registered)
    extra = sorted(registered - set(inventory))
    if missing or extra:
        raise UmbrellaError(
            "the acceptance registry and the built skills disagree; "
            f"unregistered: {missing}, unknown registry entries: {extra}"
        )
    if skill is not None:
        entries = [entry for entry in entries if skill in entry["skills"]]
        if not entries:
            raise UmbrellaError(
                f"unknown skill {skill!r}; run with --plan-only to list the registry"
            )
    return entries


def container_status(name: str) -> str:
    try:
        completed = subprocess.run(
            ["docker", "ps", "--filter", f"name={name}", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip()


def family_prereq(family: str) -> str | None:
    """None when the family can run; otherwise the honest skip reason."""
    if family == "mattermost-live":
        status = container_status("skills-dev-mattermost-1")
        if "healthy" not in status:
            return (
                "the dev Mattermost stack is not healthy (container status: "
                f"{status or 'docker unavailable'}); start it with task env:mattermost:up"
            )
        return None
    if family == "gitlab-live":
        status = container_status("skills-dev-gitlab-1")
        if "healthy" not in status:
            return (
                "the dev GitLab stack is not healthy (container status: "
                f"{status or 'docker unavailable'}); start it with task env:gitlab:up"
            )
        if not GITLAB_FIXTURES.is_file():
            return "the GitLab fixtures are not initialized; run task env:gitlab:up"
        return None
    return None


def family_environment(configured: dict[str, Any]) -> dict[str, str]:
    """The child-process environment: the same EVAL_* config, explicit credentials."""
    environment = dict(os.environ)
    environment.update(
        {
            "EVAL_HOST": configured["host"],
            "EVAL_MODEL": configured["model"],
            "EVAL_TIMEOUT": str(configured["timeout_seconds"]),
            "EVAL_MAX_TOKENS": str(configured["max_tokens"]),
            "EVAL_MAX_COST": str(configured["max_cost"]),
        }
    )
    return environment


def run_family(
    family: str, directory: Path, configured: dict[str, Any], started: float
) -> dict[str, Any]:
    reason = family_prereq(family)
    if reason is not None:
        return {"status": "skipped", "reason": reason, "duration_ms": 0}
    for member in HARNESS_SKILLS[family]:
        progress(member, family, "running", configured["model"], started)
    family_started = time.monotonic()
    try:
        completed = subprocess.run(
            FAMILY_TASKS[family],
            cwd=ROOT,
            env=family_environment(configured),
            timeout=configured["timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "reason": (
                f"the {family} family exceeded the {configured['timeout_seconds']:.0f}s budget"
            ),
            "duration_ms": round((time.monotonic() - family_started) * 1000),
        }
    duration_ms = round((time.monotonic() - family_started) * 1000)
    report = pointer_report(FAMILY_REPORTS[family])
    result: dict[str, Any] = {
        "report": str(FAMILY_REPORTS[family]),
        "duration_ms": duration_ms,
    }
    if completed.returncode != 0:
        result["status"] = "failed"
        result["reason"] = f"the {family} family exited {completed.returncode}"
        return result
    result["status"] = "passed"
    result["detail"] = report
    return result


def run_probe(
    name: str, directory: Path, configured: dict[str, Any], started: float
) -> dict[str, Any]:
    spec = PROBES[name]
    adapter = load("acceptance_probe_adapter", EVAL_RUNNER)
    live_checks = load("acceptance_probe_usage", LIVE_CHECKS)
    last_error: Exception | None = None
    for attempt_number in (1, 2):
        attempt_dir = private_directory(directory / f"attempt-{attempt_number}")
        progress(
            name,
            "behavior-probe",
            f"running (attempt {attempt_number})",
            configured["model"],
            started,
        )
        try:
            return run_probe_once(name, spec, attempt_dir, configured, adapter, live_checks)
        except TransportError as error:
            last_error = error
            (attempt_dir / "note.txt").write_text(str(error), encoding="utf-8")
            if attempt_number == 1:
                # Rate limits and provider blips are transient; wait before
                # the retry instead of retrying into the same blip.
                time.sleep(30)
    raise VerificationError(f"both probe attempts failed; last error: {last_error}")


def run_probe_once(
    name: str,
    spec: dict[str, Any],
    attempt_dir: Path,
    configured: dict[str, Any],
    adapter: Any,
    live_checks: Any,
) -> dict[str, Any]:
    workspace = private_directory(attempt_dir / "workspace")
    built = BUILT_SKILLS / name
    if not (built / "SKILL.md").is_file():
        raise UmbrellaError(f"the built {name} archive is missing; run task skills:build")
    shutil.copytree(built, workspace / ".agents/skills" / name)
    for relative, content in spec["fixture"].items():
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    artifact = workspace / ("artifact.json" if "json_list" in spec["checks"] else "artifact.md")
    answer = workspace / "answer.json"
    prompt = spec["prompt"].format(artifact=artifact, answer=answer)
    sandbox = private_directory(attempt_dir / "host")
    environment = adapter.isolated_environment(sandbox)
    environment["PATH"] = os.environ["PATH"]
    environment["NO_COLOR"] = "1"
    for key in PROVIDER_KEYS:
        if key in os.environ:
            environment[key] = os.environ[key]
    argv = cast(
        "list[str]", adapter.host_command("opencode", "opencode", configured["model"], prompt)
    )
    argv.insert(2, "--standalone")
    timeout = min(float(spec["timeout"]), configured["timeout_seconds"])
    started = time.monotonic()
    stdout, stderr, code = spawn(argv, workspace, environment, timeout, label=f"probe:{name}")
    (attempt_dir / "agent-output.txt").write_text(
        str(adapter.redact_text(stdout + "\n" + stderr)), encoding="utf-8"
    )
    if code != 0:
        raise TransportError(f"the probe host exited {code}")
    events = parse_events(stdout)
    usage = live_checks.usage(events, adapter)
    budgets, budget_status = adapter.budget_assertions(
        usage,
        {"max_tokens": configured["max_tokens"], "max_cost": configured["max_cost"]},
    )
    if budget_status == "blocked":
        raise VerificationError("the probe budget evidence is blocked")
    checks = evaluate_checks(spec, workspace, artifact, answer)
    failed = [item["id"] for item in checks if item["status"] != "passed"]
    if failed:
        raise VerificationError(f"probe checks failed: {failed}")
    return {
        "status": "passed",
        "duration_ms": round((time.monotonic() - started) * 1000),
        "model": configured["model"],
        "checks": checks,
        "usage": usage,
        "budgets": budgets,
        "attempt_dir": str(attempt_dir),
    }


def evaluate_checks(
    spec: dict[str, Any], workspace: Path, artifact: Path, answer: Path
) -> list[dict[str, Any]]:
    contract: dict[str, Any] = spec["checks"]
    checks: list[dict[str, Any]] = []

    def record(identifier: str, passed: bool) -> None:
        checks.append({"id": identifier, "status": "passed" if passed else "failed"})

    if not answer.is_file():
        raise VerificationError("the probe did not write answer.json")
    answer_value = read_json_file(answer)
    if answer_value is None:
        raise VerificationError("answer.json is not a JSON object")
    expected_keys = set(contract.get("answer_keys", ("artifact",)))
    record("answer:keys", set(answer_value) == expected_keys)
    for key, expected in contract.get("answer_equal", {}).items():
        record(f"answer:{key}", answer_value.get(key) == expected)
    reported = answer_value.get("artifact")
    record(
        "answer:artifact",
        isinstance(reported, str) and Path(reported).resolve() == artifact.resolve(),
    )
    if not artifact.is_file():
        record("artifact:exists", False)
        return checks
    record("artifact:exists", True)
    text = artifact.read_text(encoding="utf-8")
    for item in contract.get("contains", []):
        record(f"artifact:contains:{item[:40]}", item in text)
    for item in contract.get("not_contains", []):
        record(f"artifact:not_contains:{item[:40]}", item not in text)
    if "max_chars" in contract:
        record("artifact:max_chars", len(text) <= int(contract["max_chars"]))
    if "first_line_regex" in contract:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        record(
            "artifact:first_line",
            re.fullmatch(contract["first_line_regex"], first_line) is not None
            and len(first_line) <= int(contract.get("first_line_max", 10**6)),
        )
    if "json_list" in contract:
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        items = value if isinstance(value, list) else []
        limits = contract["json_list"]
        between = int(limits["min"]) <= len(items) <= int(limits["max"])
        shaped = all(
            isinstance(item, dict) and set(item) == set(limits["item_keys"]) for item in items
        )
        record("artifact:json_list", between and shaped)
    if "rerun" in contract:
        try:
            completed = subprocess.run(
                contract["rerun"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            record("artifact:rerun", completed.returncode == 0)
        except subprocess.SubprocessError:
            record("artifact:rerun", False)
    return checks


def write_summary(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Acceptance umbrella report",
        "",
        f"- started at: {report.get('started_at')}",
        f"- verdict: **{report.get('status')}**",
        f"- model: `{report.get('model')}`",
        f"- pre-flight cost estimate: {report.get('cost_estimate')}",
        f"- wall clock: {round((report.get('duration_ms') or 0) / 1000)}s",
        "",
        "## Coverage",
        "",
        "| skill | family | status | wall (s) | report / reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [row for entry in report.get("entries", []) for row in coverage_rows(entry)]
    timings = [
        f"- {entry['skills'][0]} ({entry['family']}): "
        f"{round((entry['result'].get('duration_ms') or 0) / 1000)}s"
        for entry in report.get("entries", [])
        if entry["result"]["status"] != "skipped"
    ]
    skipped = [
        f"- **{entry['skills'][0]}** ({entry['family']}): {entry['result'].get('reason')}"
        for entry in report.get("entries", [])
        if entry["result"]["status"] == "skipped"
    ]
    failures = [
        f"- **{entry['skills'][0]}** ({entry['family']}): {entry['result'].get('reason')}"
        for entry in report.get("entries", [])
        if entry["result"]["status"] == "failed"
    ]
    if skipped:
        lines += ["", "## Skips", *skipped]
    if timings:
        lines += ["", "## Timings", *timings]
    if failures:
        lines += ["", "## Failures", *failures]
    lines += [
        "",
        "## Handing this report to the master session",
        "",
        (
            "Paste the verdict line, the coverage table, and the failure reasons into the "
            "master session; the machine evidence is `result.json` next to this file, and "
            "each family/probe report keeps its raw attempt outputs."
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def coverage_rows(entry: dict[str, Any]) -> list[str]:
    result = entry["result"]
    pointer = result.get("report") or result.get("attempt_dir") or ""
    detail = result.get("reason") or pointer
    wall = round((result.get("duration_ms") or 0) / 1000)
    return [
        f"| {name} | {entry['family']} | {result['status']} | {wall} | {detail} |"
        for name in entry["skills"]
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", help="run one skill's acceptance entry only")
    parser.add_argument("--plan-only", action="store_true", help="print the plan and exit")
    parser.add_argument("--yes", action="store_true", help="accept a non-cheap EVAL_MODEL")
    arguments = parser.parse_args(argv)
    inventory = all_skills()
    entries = plan(arguments.skill, inventory)
    if arguments.plan_only:
        for entry in entries:
            for name in entry["skills"]:
                print(f"{name:28} {entry['family']}")
        print(
            f"total: {sum(len(entry['skills']) for entry in entries)} entries over {len(inventory)} skills"
        )
        return 0
    started = time.monotonic()
    configured = settings(arguments.yes)
    print(
        f"[umbrella] model: {configured['model']} | timeout: "
        f"{configured['timeout_seconds']:.0f}s | guardrails: <=${configured['max_cost']:.2f}, "
        f"<= {configured['max_tokens']} tokens | last measured: {cost_estimate()}",
        flush=True,
    )
    report: dict[str, Any] = {
        "action": "acceptance-umbrella",
        "started_at": datetime.now(UTC).isoformat(),
        "model": configured["model"],
        "cost_estimate": cost_estimate(),
        "entries": [],
        "status": "failed",
    }
    root = private_directory(
        REPORT_ROOT / (time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3))
    )
    verdict = "passed"
    try:
        for entry in entries:
            for name in entry["skills"]:
                progress(name, entry["family"], "starting", configured["model"], started)
            if entry["family"] == "skip":
                result = {"status": "skipped", "reason": SKIPS[entry["skills"][0]]}
            elif entry["family"] == "behavior-probe":
                probe_dir = private_directory(root / "probes" / entry["skills"][0])
                try:
                    result = run_probe(entry["skills"][0], probe_dir, configured, started)
                except VerificationError as error:
                    result = {"status": "failed", "reason": str(error)}
            else:
                family_dir = private_directory(root / "families" / entry["family"])
                result = run_family(entry["family"], family_dir, configured, started)
            entry["result"] = result
            report["entries"].append(
                {
                    "skills": entry["skills"],
                    "family": entry["family"],
                    "result": {
                        key: value
                        for key, value in result.items()
                        if key != "detail" or value is not None
                    },
                }
            )
            for name in entry["skills"]:
                progress(
                    name,
                    entry["family"],
                    f"done: {result['status']}",
                    configured["model"],
                    started,
                )
            if result["status"] == "failed":
                verdict = "failed"
    finally:
        report["status"] = verdict
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        write_json(root / "result.json", report)
        write_json(
            REPORT_ROOT / "latest.json",
            {"report": str(root / "result.json"), "status": report["status"]},
        )
        write_summary(root / "summary.md", report)
        print(f"Report: {root / 'result.json'}")
        print(f"Summary: {root / 'summary.md'}")
    return 0 if verdict == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
