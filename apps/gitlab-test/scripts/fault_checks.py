"""Synthetic CLI transport failure, explicitly distinct from GitLab rejections."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from stand import ROOT, Stand, private_directory, write_json

if TYPE_CHECKING:
    from pathlib import Path


def run(stand: Stand, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}"
    before = stand.request("GET", endpoint)
    notes = stand.request("GET", endpoint + "/discussions")
    isolated = private_directory(stand.state / "faults" / directory.name)
    wrapper = isolated / "glab"
    wrapper.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stderr.write('INJECTED transport unavailable; no server request sent\\n')\nsys.exit(1)\n"
    )
    wrapper.chmod(0o700)
    env = stand.isolated_env("reviewer")
    runner = ROOT / ".build/skills/mr-prepare/scripts/prepare_mr.py"
    argv = [sys.executable, str(runner), "prepare", "--url", f["mr"]["web_url"]]
    observations = []
    for name, environment in (
        ("injected-failure", {**env, "PATH": str(isolated) + os.pathsep + env["PATH"]}),
        ("real-retry", env),
    ):
        result = subprocess.run(  # noqa: S603 - Fixed read-only helper under owned isolated environments.
            argv,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        observation = {
            "name": name,
            "origin": "fault-injection" if name == "injected-failure" else "real-server",
            "exit_code": result.returncode,
            "stdout": stand.redact(result.stdout),
            "stderr": stand.redact(result.stderr),
        }
        write_json(directory / (name + ".json"), observation)
        observations.append(observation)
        payload = json.loads(result.stdout)
        if name == "injected-failure":
            if result.returncode == 0 or payload["status"] == "ok":
                raise RuntimeError(
                    "Transport fault was incorrectly accepted as successful evidence"
                )
        elif (
            result.returncode
            or payload["status"] != "ok"
            or not all(item["complete"] for item in payload["items"])
        ):
            raise RuntimeError("Real-server retry did not restore complete collection")
    after = stand.request("GET", endpoint)
    if any(
        before[key] != after[key] for key in ("title", "description", "labels", "state", "sha")
    ) or notes != stand.request("GET", endpoint + "/discussions"):
        raise RuntimeError("Read-only failure/retry mutated the server")
    return {
        "origin": "fault-injection plus explicit real-server retry",
        "observations": [
            {key: value for key, value in item.items() if key not in ("stdout", "stderr")}
            for item in observations
        ],
        "server_unchanged": True,
    }
