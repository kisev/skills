"""Shared live-acceptance helpers that do not belong to one family."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

PROVIDER_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
    "OPENCODE_CONFIG_CONTENT",
    "OPENCODE_CLI_CONFIG_CONTENT",
    "ZAI_API_KEY",
    "ZHIPU_API_KEY",
)

CHEAP_MODEL = re.compile(r"flash|mini|haiku|nano|lite", re.IGNORECASE)


class TransportError(RuntimeError):
    """The host failed to run; a retry is meaningful (timeout, provider error)."""


class VerificationError(RuntimeError):
    """A machine check failed; the acceptance is red and a retry cannot fix it."""


def spawn(
    argv: list[str],
    workspace: Path,
    environment: dict[str, str],
    timeout: float,
    label: str = "acceptance",
) -> tuple[str, str, int]:
    started = time.monotonic()
    with subprocess.Popen(
        argv,
        cwd=workspace,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        quiet = threading.Event()

        def beat() -> None:
            while not quiet.wait(60):
                elapsed = int(time.monotonic() - started)
                print(
                    f"[{label}] agent still running: {elapsed}s elapsed (pid {process.pid})",
                    flush=True,
                )

        watchdog = threading.Thread(target=beat, daemon=True)
        watchdog.start()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            raise TransportError("live host exceeded its timeout") from None
        finally:
            quiet.set()
    print(f"[{label}] agent finished in {int(time.monotonic() - started)}s", flush=True)
    return stdout, stderr, process.returncode


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def parse_events(stdout: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    malformed = ""
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Cosmetic host noise (spinner control sequences and the like) must
            # not consume an attempt; only an eventless stream is a failure.
            malformed = malformed or line[:200]
            continue
        if isinstance(event, dict):
            events.append(event)
    if not events:
        raise TransportError(f"live host emitted no structured events; first noise: {malformed}")
    return events
