"""Explicit optional agent run using existing eval host and telemetry adapters."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any

from stand import ROOT, load, private_directory, write_json

shared = load("gitlab_live_common", ROOT / "apps/mattermost-test/scripts/live_checks.py")
KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_CLI_CONFIG_CONTENT",
)


def settings() -> dict[str, Any]:
    configured: dict[str, Any] = shared.settings()
    if not any(os.environ.get(key) for key in KEYS):
        raise ValueError("Live requires explicit provider credentials/configuration")
    return configured


def run(stand: Any, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    configured = settings()
    adapter = load("gitlab_eval_adapter", ROOT / "scripts/eval_runner.py")
    isolated = private_directory(stand.state / "live" / directory.name)
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
    for key in KEYS:
        if key in os.environ:
            environment[key] = os.environ[key]
    for name in (
        "code-review",
        "mr-prepare",
        "task-prepare",
        "task-triage",
        "release-prepare",
        "release-review",
    ):
        shutil.copytree(ROOT / ".build/skills" / name, workspace / ".agents/skills" / name)
    output = workspace / "answer.json"
    prompt = (
        f"Use mr-prepare against this exact local fixture: {f['mr']['web_url']}. "
        "Prepare a title/description publication runbook with the installed skill. "
        "Never execute publication commands or change GitLab. Do not access other origins. "
        "Credentials are isolated and already configured. Write JSON with exactly "
        f"runbook (absolute path) and title (observed MR title) to {output}."
    )
    argv = adapter.host_command(configured["host"], configured["host"], configured["model"], prompt)
    if configured["host"] == "opencode":
        argv.insert(1, "--standalone")
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}"
    before = stand.request("GET", endpoint)
    notes_before = stand.request("GET", endpoint + "/discussions")
    with subprocess.Popen(  # noqa: S603 - Existing explicit host adapter in isolated workspace.
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
            (directory / "agent-output.txt").write_text(
                shared.scrub(stdout + stderr, stand, adapter)
            )
            raise RuntimeError("Live host timed out") from None
    (directory / "agent-output.txt").write_text(shared.scrub(stdout + stderr, stand, adapter))
    if process.returncode:
        raise RuntimeError(f"Live host exited {process.returncode}")
    after = stand.request("GET", endpoint)
    if any(
        before[key] != after[key] for key in ("title", "description", "labels", "state", "sha")
    ) or notes_before != stand.request("GET", endpoint + "/discussions"):
        raise RuntimeError("Agent crossed manual publication boundary")
    answer = json.loads(output.read_text())
    if set(answer) != {"runbook", "title"} or answer["title"] != before["title"]:
        raise RuntimeError("Agent did not recover actual MR title")
    artifact = Path(answer["runbook"]).resolve()
    if not artifact.is_relative_to(isolated) or not artifact.is_file():
        raise RuntimeError("Agent runbook outside isolated live state")
    text = artifact.read_text()
    if "glab" not in text or str(f["mr"]["iid"]) not in text:
        raise RuntimeError("Agent did not prepare a bound manual runbook")
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    usage = shared.usage(events, adapter)
    budgets, status = adapter.budget_assertions(usage, configured)
    result = {
        "status": status,
        "host": configured["host"],
        "model": configured["model"],
        "usage": usage,
        "budgets": budgets,
        "artifacts": answer,
    }
    write_json(directory / "live.json", result)
    if status != "passed":
        raise RuntimeError("Live budget/telemetry is " + status)
    return result
