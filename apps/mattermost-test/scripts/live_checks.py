"""Optional real-agent checks using the repository's existing host adapters."""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

from stand import ROOT, load, private_directory, write_json


def settings() -> dict[str, Any]:
    names = ("EVAL_HOST", "EVAL_MODEL", "EVAL_TIMEOUT", "EVAL_MAX_TOKENS", "EVAL_MAX_COST")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ValueError("Live evaluation requires: " + ", ".join(missing))
    host = os.environ["EVAL_HOST"]
    if host not in {"opencode", "codex"}:
        raise ValueError("EVAL_HOST must be opencode or codex")
    values = {
        "host": host,
        "model": os.environ["EVAL_MODEL"],
        "timeout_seconds": float(os.environ["EVAL_TIMEOUT"]),
        "max_tokens": int(os.environ["EVAL_MAX_TOKENS"]),
        "max_cost": float(os.environ["EVAL_MAX_COST"]),
    }
    if any(
        not math.isfinite(values[key]) or values[key] <= 0
        for key in ("timeout_seconds", "max_tokens", "max_cost")
    ):
        raise ValueError("Live evaluation budgets must be positive")
    return values


def scrub(text: str, stand: Any, adapter: Any) -> str:
    text = stand.redact(text)
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
    ):
        if os.environ.get(key):
            text = text.replace(os.environ[key], "[REDACTED]")
    return str(adapter.redact_text(text))


def usage(events: list[dict[str, Any]], adapter: Any) -> dict[str, Any]:
    normalized = adapter.parse_host_output("\n".join(json.dumps(item) for item in events))["usage"]
    if "total_tokens" not in normalized:
        totals = []
        costs = []
        for event in events:
            part = event.get("part", {}) if event.get("type") == "step_finish" else {}
            native = part.get("tokens") or event.get("usage", {})
            if isinstance(native, dict) and native:
                total = native.get("total")
                if total is None:
                    total = sum(
                        native.get(key, 0)
                        for key in ("input", "output", "reasoning", "input_tokens", "output_tokens")
                    )
                totals.append(total)
            if isinstance(part.get("cost"), (int, float)):
                costs.append(part["cost"])
        if totals:
            normalized["total_tokens"] = sum(totals)
        if costs:
            normalized["cost"] = sum(costs)
    normalized["telemetry"] = (
        "complete"
        if all(isinstance(normalized.get(k), (int, float)) for k in ("cost", "total_tokens"))
        else "incomplete"
    )
    return normalized


def run(stand: Any, report_dir: Path, _environment: dict[str, str]) -> dict[str, Any]:
    configured = settings()
    adapter = load("mm_stand_eval_adapter", ROOT / "scripts/eval_runner.py")
    workspace = private_directory(stand.state / "live/project")
    isolated = private_directory(stand.state / "live")
    environment = adapter.isolated_environment(isolated)
    environment["SSL_CERT_FILE"] = str(stand.ca_bundle)
    # Provider credentials are passed explicitly by environment, not copied from
    # the operator's global OpenCode/Codex account or configuration directories.
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "GOOGLE_GENERATIVE_AI_API_KEY",
        "OPENCODE_CONFIG_CONTENT",
        "OPENCODE_CLI_CONFIG_CONTENT",
    ):
        if key in os.environ:
            environment[key] = os.environ[key]
    for variable in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        private_directory(Path(environment[variable]))
    for name in ("mattermost", "mattermost-triage"):
        shutil.copytree(
            ROOT / ".build/skills" / name, workspace / ".agents/skills" / name, dirs_exist_ok=True
        )
    mm = load("mm_live_auth", ROOT / ".build/skills/mattermost/scripts/mattermost.py")
    token = (
        Path(environment["XDG_CONFIG_HOME"])
        / "mattermost"
        / mm.hashlib.sha256(stand.origin.encode()).hexdigest()
        / "token"
    )
    private_directory(token.parent.parent)
    private_directory(token.parent)
    token.write_text(stand.manifest["users"]["reader"]["token"] + "\n")
    token.chmod(0o600)
    output = workspace / (report_dir.name + ".json")
    prompt = (
        "Use the installed mattermost and mattermost-triage skills against this local fixture only. "
        f"Read {stand.url('direct')}. Collect and publish local triage artifacts for this exact target. "
        "Prepare one English Issue card (project#123, Retry delivery, https://gitlab.example/project/-/issues/123) "
        f"for {stand.url('cards')}, with unknown metadata marked explicitly. "
        "Do not execute any publication helper, send posts, change the server or access other origins. "
        "Do not ask questions; credentials are already configured in your isolated XDG directory. "
        "When finished, write a JSON object with exactly quote, card_plan, triage_analysis: "
        "quote is the exact review request you read, card_plan is the absolute prepared plan Markdown path, "
        f"triage_analysis is the absolute analysis artifact path. Write it to {output}. "
        "Use the supplied scripts and write only under this isolated workspace and XDG state."
    )
    argv = adapter.host_command(configured["host"], configured["host"], configured["model"], prompt)
    if configured["host"] == "opencode":
        argv.insert(1, "--standalone")
    watched = [
        value
        for name, value in stand.manifest["channels"].items()
        if name not in {"free", "private"}
    ]
    before = {
        cid: stand.request("GET", f"/channels/{cid}", actor="reader")["total_msg_count"]
        for cid in watched
    }
    started = adapter.time.monotonic()
    with subprocess.Popen(  # noqa: S603 - Existing repository host adapter, explicit settings.
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
            (report_dir / "agent-output.txt").write_text(
                scrub(stdout + "\n" + stderr, stand, adapter)
            )
            raise RuntimeError(
                "Live host exceeded its timeout; owned process group terminated"
            ) from None
    (report_dir / "agent-output.txt").write_text(scrub(stdout + "\n" + stderr, stand, adapter))
    if process.returncode:
        raise RuntimeError(f"Live host exited {process.returncode}; see redacted agent-output.txt")
    after = {
        cid: stand.request("GET", f"/channels/{cid}", actor="reader")["total_msg_count"]
        for cid in watched
    }
    if before != after:
        raise RuntimeError("Live agent violated the manual publication boundary")
    events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
    observed_usage = usage(events, adapter)
    budget_checks, budget_status = adapter.budget_assertions(observed_usage, configured)
    answer = json.loads(output.read_text())
    if (
        set(answer) != {"quote", "card_plan", "triage_analysis"}
        or answer["quote"] != "Please review the retry fix."
    ):
        raise RuntimeError("Agent did not recover the exact fixture request")
    for key in ("card_plan", "triage_analysis"):
        path = Path(answer[key]).resolve()
        if not path.is_relative_to(isolated) or not path.is_file():
            raise RuntimeError("Agent artifact is outside the isolated live state")
    plan = Path(answer["card_plan"]).read_text()
    analysis = json.loads(Path(answer["triage_analysis"]).read_text())
    if "props.attachments" not in plan or not analysis.get("candidates"):
        raise RuntimeError("Agent did not prepare a card and nonempty triage analysis")
    with mock.patch.dict(os.environ, environment):
        helper = load(
            "mm_live_publication",
            workspace / ".agents/skills/mattermost/scripts/mattermost_publication.py",
        )
        parent = Path(answer["card_plan"]).parent
        pointer = json.loads((parent / "current-plan.json").read_text())
        sealed = json.loads(Path(pointer["path"]).read_text())
        for entry in sealed["actions"]:
            action, _, _ = helper.load_action(entry["path"], entry["digest"])
            if (
                action.get("target") != stand.url("cards")
                or action.get("card", {}).get("kind") != "issue"
            ):
                raise RuntimeError("Live card action does not match the requested fixture")
        triage = load(
            "mm_live_triage",
            workspace / ".agents/skills/mattermost-triage/scripts/mattermost_triage.py",
        )
        evidence_path = (
            Path(answer["triage_analysis"]).parents[2]
            / "evidence/history"
            / f"{analysis['evidence_digest']}.json"
        )
        evidence, digest, _ = triage.load_evidence(evidence_path)
        candidates = []
        for item in analysis["candidates"]:
            candidate = dict(item)
            candidate["source_post_ids"] = sorted(
                {quote["post_id"] for quote in item["cited_excerpts"]}
            )
            candidate["cited_excerpts"] = [
                {"post_id": q["post_id"], "quote": q["quote"]} for q in item["cited_excerpts"]
            ]
            candidates.append(candidate)
        triage.validate_analysis(
            {
                "schema_version": 1,
                "evidence_digest": digest,
                "summary": analysis["summary"],
                "candidates": candidates,
            },
            evidence,
            digest,
        )
        if not any(
            item["status"] == "attention"
            and stand.manifest["posts"]["direct-root"] in item["source_post_ids"]
            for item in candidates
        ):
            raise RuntimeError("Live triage missed the explicit review request")
    result = {
        "host": configured["host"],
        "model": configured["model"],
        "usage": observed_usage,
        "duration_ms": round((adapter.time.monotonic() - started) * 1000),
        "budgets": budget_checks,
        "status": budget_status,
        "artifacts": answer,
    }
    write_json(report_dir / "live.json", result)
    if budget_status != "passed":
        raise RuntimeError(f"Live budget evidence is {budget_status}; see live.json")
    return result
