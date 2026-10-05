"""Bounded local prerequisites, recorded before any optional stand operation."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tests.integration.gitlab.scripts.stand import ROOT, command, write_json

if TYPE_CHECKING:
    from tests.integration.gitlab.scripts.stand import Stand


def run(stand: Stand, directory: Path, *, browser: bool) -> dict[str, Any]:
    evidence: dict[str, Any] = {}

    def observe(name: str, argv: list[str]) -> str:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
        evidence[name] = {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        if result.returncode:
            raise RuntimeError(f"Prerequisite {name} unavailable; see preflight.json")
        return result.stdout

    try:
        stand.resources()
        info = json.loads(observe("docker", ["docker", "info", "--format", "{{json .}}"]))
        compose = observe("compose", [*stand.compose[:-4], "version"])
        if not re.search(r"\bv2\.", compose):
            raise RuntimeError("Docker Compose v2 is required")
        cli = observe("glab", ["glab", "--version"])
        if not re.search(r"\b1\.120\.0\b", cli):
            raise RuntimeError("Pinned glab 1.120.0 is required")
        for name, image in (
            ("server_image", "gitlab/gitlab-ce:18.11.11-ce.0"),
            ("runner_image", "gitlab/gitlab-runner:v18.11.0"),
        ):
            observe(name, ["docker", "image", "inspect", image])
        available = next(
            int(line.split()[1]) * 1024
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        )
        disk = shutil.disk_usage(ROOT)
        evidence["resources"] = {
            "engine_memory_bytes": info["MemTotal"],
            "cpus": info["NCPU"],
            "available_memory_bytes": available,
            "free_disk_bytes": disk.free,
        }
        if available < 4 * 1024**3 or disk.free < 20 * 1024**3:
            raise RuntimeError(
                "Insufficient resources: require 4 GiB available RAM and 20 GiB disk"
            )
        evidence["checkout"] = {
            "sha": command(["git", "rev-parse", "HEAD"]).stdout.strip(),
            "dirty": bool(command(["git", "status", "--porcelain"]).stdout.strip()),
        }
        if browser:
            observe("agent_browser", ["agent-browser", "--version"])
            session = "gl-preflight-" + secrets.token_hex(8)
            env = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("AGENT_BROWSER_")
            }
            argv = [
                "agent-browser",
                "--config",
                str(stand.state / "preflight-browser.json"),
                "--session",
                session,
            ]
            write_json(stand.state / "preflight-browser.json", {})
            try:
                result = command([*argv, "open", "about:blank"], env=env, timeout=60)
                evidence["browser_launch"] = result.stdout.strip()
                evidence["browser_version"] = command(
                    [*argv, "eval", "navigator.userAgent"], env=env, timeout=30
                ).stdout.strip()
            finally:
                command([*argv, "close"], env=env, timeout=30)
    except Exception as exc:
        evidence.update(status="failed", error=str(exc))
        raise
    else:
        evidence["status"] = "passed"
        return evidence
    finally:
        write_json(directory / "preflight.json", evidence)
