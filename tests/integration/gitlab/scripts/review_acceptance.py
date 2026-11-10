"""User-run mr-review acceptance on the disposable local GitLab stand.

One family run provisions a synthetic project and merge request, checks the
skill out at the exact reviewed revisions, seeds the startup answers, runs the
installed skill through the opencode host, reviews again after the head moves,
and executes the generated draft-note block against the stand. It never
publishes a note and it touches only the local stand fixtures.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.stand import ROOT, load, private_directory, write_json

shared = load("gitlab_live_common", ROOT / "tests/integration/mattermost/scripts/live_checks.py")
live = load("gitlab_review_live_checks", ROOT / "tests/integration/gitlab/scripts/live_checks.py")

REVIEW_FILES = ("runbook.md", "drafts.sh")
RUNBOOK_SECTIONS = (
    "## Target",
    "## Task fulfillment",
    "## OCR runs",
    "## Checks",
    "## Draft notes",
)
COMPARE_GROUPS = ("new", "persisting", "resolved", "not reviewed")
DRAFT_COMMAND = re.compile(r"/drafts\b")


def settings() -> dict[str, Any]:
    configured: dict[str, Any] = live.settings()
    if shutil.which("ocr") is None:
        raise ValueError("Live mr-review acceptance requires the ocr CLI")
    return configured


def _reviewers_from_environment() -> list[dict[str, str]]:
    raw = os.environ.get("EVAL_OCR_REVIEWERS", "")
    entries: list[dict[str, str]] = []
    for chunk in [part.strip() for part in raw.split(",") if part.strip()]:
        alias, _, rest = chunk.partition("=")
        provider, _, model = rest.partition(":")
        entries.append({"alias": alias, "provider": provider, "model": model, "effort": "medium"})
    return entries


def _reviewers_from_profile() -> list[dict[str, str]]:
    path = Path.home() / ".reviewmatic" / "reviewers.json"
    if not path.is_file():
        return []
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    reviewers = profile.get("reviewers") if isinstance(profile, dict) else None
    if not isinstance(reviewers, list):
        return []
    return [
        {
            "alias": str(item["alias"]),
            "provider": str(item["provider"]),
            "model": str(item["model"]),
            "effort": str(item.get("effort", "medium")),
        }
        for item in reviewers
        if isinstance(item, dict) and {"alias", "provider", "model"} <= set(item)
    ]


def reviewer_profile(environment: dict[str, str]) -> dict[str, Any]:
    """Two aliases, each provider validated against ``ocr llm providers``."""
    configured = _reviewers_from_environment() or _reviewers_from_profile()
    if len(configured) < 2:
        raise ValueError(
            "the mr-review acceptance needs two OCR reviewer aliases; set "
            "EVAL_OCR_REVIEWERS=alias=provider:model,alias=provider:model or create "
            "~/.reviewmatic/reviewers.json with two reviewers"
        )
    reviewers = configured[:2]
    completed = subprocess.run(
        ["ocr", "llm", "providers"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=environment,
    )
    if completed.returncode:
        raise ValueError("ocr llm providers failed; the acceptance needs a working ocr CLI")
    known = {
        line.strip().split(" ", maxsplit=1)[0]
        for line in completed.stdout.splitlines()
        if line.strip()
    }
    unknown = sorted({item["provider"] for item in reviewers if item["provider"] not in known})
    if unknown:
        raise ValueError(
            "unknown OCR providers: " + ", ".join(unknown) + "; choose from 'ocr llm providers'"
        )
    return {
        "schema": "mr-review/reviewers/v1",
        "default": reviewers[0]["alias"],
        "reviewers": reviewers,
    }


def _askpass(directory: Path) -> Path:
    script = private_directory(directory / "git") / "askpass.sh"
    script.write_text(
        '#!/bin/sh\ncase "$1" in *sername*) printf "%s\\n" oauth2 ;; '
        '*) printf "%s\\n" "$GITLAB_TOKEN" ;; esac\n',
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def checkout(
    stand: Any, fixture: dict[str, Any], workspace: Path, environment: dict[str, str]
) -> None:
    """Clone the fixture project and bind the exact reviewed revisions."""
    private_directory(workspace)
    env = {
        **environment,
        "GIT_ASKPASS": str(_askpass(workspace.parent)),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_SSL_CAINFO": str(stand.ca),
    }
    for argv in (
        ["git", "clone", "--quiet", fixture["repo_url"], str(workspace)],
        [
            "git",
            "-C",
            str(workspace),
            "fetch",
            "--quiet",
            "origin",
            fixture["branch"],
            fixture["target"],
        ],
        ["git", "-C", str(workspace), "checkout", "--quiet", "--detach", fixture["head"]],
    ):
        subprocess.run(argv, env=env, capture_output=True, text=True, check=True, timeout=300)


def _prompt(
    fixture: dict[str, Any], workspace: Path, reviewers: list[dict[str, str]], *, previous: bool
) -> str:
    names = ", ".join(item["alias"] for item in reviewers)
    prompt = (
        "Use the installed mr-review skill to review this exact merge request: "
        f"{fixture['mr']['web_url']}. The review checkout is {workspace}. "
        f"Reviewers: {names}; effort medium. The startup round is already answered with "
        "those reviewers and effort; the task baseline is the merge request description "
        "and the linked issues, taken as given. Do not ask any question. Write the runbook "
        f"to {workspace / 'runbook.md'} and the draft-note block to {workspace / 'drafts.sh'}. "
        "Never execute a publication command and never change GitLab."
    )
    if previous:
        prompt += (
            " A previous OCR session exists for this merge request: run a fresh review over "
            "the current range and compare it with the previous session."
        )
    return (
        prompt
        + " Write JSON with exactly runbook and drafts (absolute paths) to "
        + str(workspace / "answer.json")
        + "."
    )


def _run_host(
    stand: Any,
    configured: dict[str, Any],
    prompt: str,
    workspace: Path,
    environment: dict[str, str],
    directory: Path,
    label: str,
) -> None:
    adapter = load("gitlab_eval_adapter", ROOT / "scripts/eval_runner.py")
    argv = adapter.host_command(configured["host"], configured["host"], configured["model"], prompt)
    if configured["host"] == "opencode":
        argv.insert(2, "--standalone")
    with subprocess.Popen(
        argv,
        cwd=workspace,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=configured["timeout_seconds"])
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            (directory / f"{label}-agent-output.txt").write_text(
                shared.scrub(stdout + stderr, stand, adapter)
            )
            raise RuntimeError("Live host timed out") from None
    (directory / f"{label}-agent-output.txt").write_text(
        shared.scrub(stdout + stderr, stand, adapter)
    )
    if process.returncode:
        raise RuntimeError(f"Live host exited {process.returncode} during {label}")


def _verify_runbook(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    missing = [section for section in RUNBOOK_SECTIONS if section not in text]
    if missing:
        raise RuntimeError("the runbook lacks sections: " + ", ".join(missing))
    return text


def _verify_drafts(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not DRAFT_COMMAND.search(text):
        raise RuntimeError("the draft block creates no GitLab draft note")
    if re.search(r"--method\s+(PUT|DELETE)|/notes\b|glab\s+mr\s+(note|approve|merge)", text):
        raise RuntimeError("the draft block contains a publication command")
    if not re.search(r"(current|reviewed)_head", text):
        raise RuntimeError("the draft block does not check the reviewed head")
    return text


def _finding_titles(runbook: str) -> set[str]:
    if "## Findings" not in runbook:
        return set()
    section = runbook.split("## Findings", 1)[1].split("## Draft notes", 1)[0]
    return {
        line.removeprefix("### ").strip()
        for line in section.splitlines()
        if line.startswith("### ")
    }


def _compare_groups(runbook: str) -> None:
    lowered = runbook.lower()
    missing = [group for group in COMPARE_GROUPS if group not in lowered]
    if missing:
        raise RuntimeError("the runbook lacks previous-finding groups: " + ", ".join(missing))


def move_head(stand: Any, fixture: dict[str, Any]) -> dict[str, Any]:
    """Commit to the MR source branch and wait for the new exact diff head."""
    pid = stand.manifest["fixtures"]["id"]
    prefix = f"/projects/{pid}"
    commit = stand.request(
        "POST",
        prefix + "/repository/commits",
        {
            "branch": fixture["branch"],
            "commit_message": "Move the review head",
            "actions": [
                {
                    "action": "update",
                    "file_path": "sample.txt",
                    "content": "context\nnew\nkeep\nlast\nadded\nfollow-up\n",
                }
            ],
        },
    )
    for _ in range(60):
        current = stand.request("GET", prefix + f"/merge_requests/{fixture['mr']['iid']}")
        if (current.get("diff_refs") or {}).get("head_sha") == commit["id"]:
            return {**fixture, "mr": current, "head": commit["id"]}
        time.sleep(1)
    raise RuntimeError("GitLab did not prepare the moved MR diff in 60 seconds")


def execute_drafts(
    stand: Any, fixture: dict[str, Any], workspace: Path, environment: dict[str, str]
) -> None:
    """Run the generated block; only draft notes may appear."""
    pid = stand.manifest["fixtures"]["id"]
    endpoint = f"/projects/{pid}/merge_requests/{fixture['mr']['iid']}"
    before = stand.request("GET", endpoint + "/discussions")
    env = {
        **environment,
        "GITLAB_HOST": stand.origin,
        "GITLAB_TOKEN": stand.manifest["users"]["reviewer"]["token"],
        "SSL_CERT_FILE": str(stand.ca_bundle),
        "GIT_SSL_CAINFO": str(stand.ca),
    }
    subprocess.run(
        ["sh", "-e", str(workspace / "drafts.sh")],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    )
    drafts = stand.request("GET", endpoint + "/drafts")
    if not isinstance(drafts, list) or not drafts:
        raise RuntimeError("the executed draft block created no draft note")
    after = stand.request("GET", endpoint + "/discussions")
    if before != after:
        raise RuntimeError("the draft block published a note instead of a draft")


def clean(stand: Any, fixture: dict[str, Any]) -> None:
    pid = stand.manifest["fixtures"]["id"]
    prefix = f"/projects/{pid}"
    with suppress(Exception):
        stand.request("DELETE", prefix + f"/merge_requests/{fixture['mr']['iid']}")
    for branch in (fixture["branch"], fixture["target"]):
        with suppress(Exception):
            stand.request("DELETE", prefix + "/repository/branches/" + branch)


def run(stand: Any, fixture: dict[str, Any], directory: Path) -> dict[str, Any]:
    configured = settings()
    adapter = load("gitlab_eval_adapter", ROOT / "scripts/eval_runner.py")
    isolated = private_directory(stand.state / "review-live" / directory.name)
    workspace = private_directory(isolated / "project")
    environment = adapter.isolated_environment(isolated)
    environment.update(
        {
            key: value
            for key, value in stand.isolated_env("reviewer").items()
            if key
            not in {"HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"}
        }
    )
    for key in (*live.KEYS, "EVAL_OCR_REVIEWERS"):
        if key in os.environ:
            environment[key] = os.environ[key]
    profile = reviewer_profile(environment)
    checkout(stand, fixture, workspace, environment)
    shutil.copytree(
        ROOT / ".build/skills" / "mr-review", workspace / ".agents/skills" / "mr-review"
    )
    write_json(workspace / ".reviewmatic" / "reviewers.json", profile)
    first_fixture = fixture
    second_fixture = fixture
    try:
        _run_host(
            stand,
            configured,
            _prompt(first_fixture, workspace, profile["reviewers"], previous=False),
            workspace,
            environment,
            directory,
            "first",
        )
        first_runbook = _verify_runbook(workspace / "runbook.md")
        _verify_drafts(workspace / "drafts.sh")
        second_fixture = move_head(stand, first_fixture)
        subprocess.run(
            ["git", "-C", str(workspace), "fetch", "--quiet", "origin", second_fixture["head"]],
            env={**environment, "GIT_SSL_CAINFO": str(stand.ca)},
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(workspace),
                "checkout",
                "--quiet",
                "--detach",
                second_fixture["head"],
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        _run_host(
            stand,
            configured,
            _prompt(second_fixture, workspace, profile["reviewers"], previous=True),
            workspace,
            environment,
            directory,
            "second",
        )
        second_runbook = _verify_runbook(workspace / "runbook.md")
        _verify_drafts(workspace / "drafts.sh")
        _compare_groups(second_runbook)
        dropped = sorted(_finding_titles(first_runbook) - _finding_titles(second_runbook))
        if dropped:
            raise RuntimeError("the comparison dropped findings: " + ", ".join(dropped))
        for name in REVIEW_FILES:
            shutil.copy2(workspace / name, directory / name)
        execute_drafts(stand, second_fixture, workspace, environment)
    finally:
        clean(stand, second_fixture)
    result = {
        "status": "passed",
        "host": configured["host"],
        "model": configured["model"],
        "reviewers": [item["alias"] for item in profile["reviewers"]],
        "merge_request": second_fixture["mr"]["web_url"],
        "reviewed_head": second_fixture["head"],
        "artifacts": {name: str(directory / name) for name in REVIEW_FILES},
        "external_mutations": False,
    }
    write_json(directory / "live.json", result)
    return result
