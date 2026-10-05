"""Bounded agent-browser subprocess driver.

Every command runs as a fixed argument vector without a shell, captures
output, and enforces a timeout, following the mattermost.py subprocess
discipline. The driver never interprets marketplace content; it moves
command results and JavaScript payloads between the process and callers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING

from shopmatic.errors import BrowserTimeout, BrowserUnavailable

if TYPE_CHECKING:
    from pathlib import Path

NAMESPACE = "shopmatic"
CLEAN_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)
CLEAN_LAUNCH_ARGS = "--disable-blink-features=AutomationControlled"
EXECUTABLE_ENV = "SHOPMATIC_AGENT_BROWSER"

OPEN_TIMEOUT = 60.0
EVAL_TIMEOUT = 60.0
COOKIE_TIMEOUT = 30.0
CLOSE_TIMEOUT = 30.0
SCROLL_TIMEOUT = 20.0
WAIT_TIMEOUT = 30.0
DEFAULT_PROBES = 8
PROBE_SETTLE_MS = 4000


class AgentBrowser:
    """One named agent-browser session bound to one Chrome profile."""

    def __init__(
        self,
        session: str,
        profile: Path,
        *,
        headed: bool = False,
        executable: str | None = None,
    ) -> None:
        self.session = session
        self.profile = profile
        self.headed = headed
        self.executable = executable

    def _vector(self, *command: str) -> list[str]:
        resolved = (
            self.executable or os.environ.get(EXECUTABLE_ENV) or shutil.which("agent-browser")
        )
        if not resolved:
            raise BrowserUnavailable("agent-browser executable was not found on PATH")
        vector = [
            resolved,
            "--namespace",
            NAMESPACE,
            "--session",
            self.session,
            "--profile",
            str(self.profile),
            "--user-agent",
            CLEAN_USER_AGENT,
            "--args",
            CLEAN_LAUNCH_ARGS,
            *command,
        ]
        if self.headed:
            vector.append("--headed")
        return vector

    def run(
        self,
        *command: str,
        timeout: float,
        stdin: str | None = None,
    ) -> str:
        """Execute one bounded command vector and return stdout."""
        try:
            completed = subprocess.run(
                self._vector(*command),
                capture_output=True,
                text=True,
                timeout=timeout,
                input=stdin,
                check=False,
            )
        except FileNotFoundError as exc:
            raise BrowserUnavailable("agent-browser executable is not runnable") from exc
        except subprocess.TimeoutExpired as exc:
            raise BrowserTimeout(f"agent-browser {command[0]} timed out") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise BrowserUnavailable(f"agent-browser {command[0]} failed: {detail[:300]}")
        return completed.stdout

    def cookies(self) -> list[dict[str, object]]:
        """Return the session cookies as parsed JSON payloads."""
        raw = self.run("cookies", "get", "--json", timeout=COOKIE_TIMEOUT)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrowserUnavailable("agent-browser returned malformed cookie JSON") from exc
        cookies = payload.get("data", {}).get("cookies")
        if not isinstance(cookies, list):
            raise BrowserUnavailable("agent-browser cookie response is malformed")
        return [cookie for cookie in cookies if isinstance(cookie, dict)]

    def open(self, url: str) -> None:
        """Navigate the active tab to one URL."""
        self.run("open", url, timeout=OPEN_TIMEOUT)

    def settle(self, milliseconds: int) -> None:
        """Wait a bounded number of milliseconds for SPA work."""
        self.run("wait", str(milliseconds), timeout=WAIT_TIMEOUT)

    def scroll(self, direction: str, pixels: int) -> None:
        """Scroll the page to trigger lazy rendering."""
        self.run("scroll", direction, str(pixels), timeout=SCROLL_TIMEOUT)

    def evaluate(self, script: str, *, timeout: float = EVAL_TIMEOUT) -> str:
        """Run JavaScript in the page and return the raw eval output."""
        return self.run("eval", "--stdin", timeout=timeout, stdin=script)

    def close(self) -> None:
        """Close the browser behind this session, ignoring absence."""
        with suppress(BrowserUnavailable):
            self.run("close", timeout=CLOSE_TIMEOUT)
