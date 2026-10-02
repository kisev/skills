"""Drive the actual reviewmatic Ink CLI through a bounded Linux pseudo-terminal."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import termios
import time
from typing import TYPE_CHECKING, Any

from tests.integration.gitlab.scripts.stand import ROOT, Stand

if TYPE_CHECKING:
    from pathlib import Path


def run(stand: Stand, f: dict[str, Any], result: dict[str, Any], directory: Path) -> dict[str, Any]:
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
    thread_id = f["threads"][0]["id"]
    before = stand.request("GET", endpoint + "/" + thread_id)
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 140, 0, 0))
    environment = {**stand.isolated_env("reviewer"), "TERM": "xterm-256color", "FORCE_COLOR": "0"}
    data = bytearray()
    node = shutil.which("node", path=environment["PATH"])
    if node is None:
        raise RuntimeError("The pinned Node executable is unavailable")
    process = subprocess.Popen(
        [
            node,
            str(ROOT / "apps/reviewmatic/dist/cli.js"),
            "plan",
            "--artifact-root",
            result["started"]["artifact_root"],
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=environment,
        start_new_session=True,
    )
    os.close(slave)

    def until(expected: bytes) -> None:
        start = len(data)
        deadline = time.monotonic() + 30
        while expected not in data[start:]:
            if time.monotonic() > deadline:
                raise RuntimeError(f"TUI timed out waiting for {expected!r}")
            if select.select([master], [], [], 0.1)[0]:
                try:
                    data.extend(os.read(master, 65536))
                except OSError as exc:
                    raise RuntimeError("TUI exited before the expected frame") from exc

    try:
        # Read the complete synchronized overview frame. Its title may arrive
        # before Ink installs input handling; it is not an input-ready barrier.
        until(b"\x1b[?2026l")
        deadline = time.monotonic() + 10
        while termios.tcgetattr(master)[3] & termios.ICANON:
            if time.monotonic() > deadline:
                raise RuntimeError("TUI did not enter raw input mode")
            select.select([], [], [], 0.02)
        os.write(master, b"\r")
        # The note title occurs in both views. Only the detail action footer
        # establishes that Enter was handled before sending the next key.
        until(b"s send")
        os.write(master, b"s")
        until(b"y confirm")
        if before != stand.request("GET", endpoint + "/" + thread_id):
            raise RuntimeError("TUI published before confirmation")
        os.write(master, b"n")
        until(b"s send")
        if before != stand.request("GET", endpoint + "/" + thread_id):
            raise RuntimeError("TUI cancellation published a reply")
        os.write(master, b"s")
        until(b"y confirm")
        os.write(master, b"y")
        until(b"exit 0")
        after = stand.request("GET", endpoint + "/" + thread_id)
        if len(after["notes"]) != len(before["notes"]) + 1:
            raise RuntimeError("TUI did not publish exactly one confirmed reply")
        note = after["notes"][-1]
        if (
            note["body"] != "Harness reviewmatic reply; correction is still pending."
            or note["author"]["id"] != stand.manifest["users"]["reviewer"]["id"]
            or after["notes"][0]["resolved"] != before["notes"][0]["resolved"]
        ):
            raise RuntimeError("TUI reply content, role or independent thread state mismatch")
        os.write(master, b"q")
        if process.wait(timeout=10):
            raise RuntimeError("TUI exited unsuccessfully")
        return {
            "thread": thread_id,
            "note_id": note["id"],
            "confirmation_cancel_preserved_server": True,
            "resolved": after["notes"][0]["resolved"],
            "transcript": "tui-transcript.txt",
        }
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        (directory / "tui-transcript.txt").write_text(stand.redact(data.decode(errors="replace")))
        os.close(master)
