"""Synthetic CLI transport failure, explicitly distinct from GitLab rejections."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.preservation_checks import pages
from tests.integration.gitlab.scripts.publication_checks import (
    commands,
    execute,
    helper,
    validated_argv,
)
from tests.integration.gitlab.scripts.stand import ROOT, Stand, private_directory, write_json


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
        result = subprocess.run(
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
        "mutations": mutation_faults(stand, f, directory),
    }


def mutation_faults(stand: Stand, f: dict[str, Any], directory: Path) -> list[dict[str, Any]]:
    runner = ROOT / ".build/skills/task-prepare/scripts/prepare_publication.py"
    real_glab = shutil.which("glab")
    if real_glab is None:
        raise RuntimeError("The pinned real glab is unavailable")
    results = []
    for phase in ("cancel-before-send", "cancel-after-write", "timeout-after-write"):
        isolated = private_directory(stand.state / "mutation-faults" / directory.name / phase)
        task = json.loads((directory / "task-input.json").read_text())
        task["plan_key"] += "-" + phase
        title = f"Mutation fault {directory.name} {phase}"
        task["items"][0]["title"] = title
        source = isolated / "task.json"
        write_json(source, task)
        prepared = helper(stand, runner, ["--input", str(source)], "author")
        copied = commands(Path(prepared["output"]).read_text())
        if len(copied) != 1:
            raise RuntimeError(
                "Mutation fault requires one actual helper-generated creation command"
            )
        argv, _endpoint = validated_argv(stand, copied[0])
        barrier = isolated / "barrier.json"
        wrapper = isolated / "glab"
        wrapper.write_text(
            f"#!{sys.executable}\n"
            "import json, subprocess, sys, time\nfrom pathlib import Path\n"
            + (
                f"result = subprocess.run([{real_glab!r}, *sys.argv[1:]], capture_output=True, text=True)\n"
                "if result.returncode: sys.stderr.write(result.stderr); sys.exit(result.returncode)\n"
                if phase != "cancel-before-send"
                else ""
            )
            + f"Path({str(barrier)!r}).write_text(json.dumps({{'phase': {phase!r}, 'origin': 'fault-injection'}}))\n"
            "sys.stderr.write('INJECTED response unavailable; server outcome must be reconciled before repetition\\n')\nsys.stderr.flush()\n"
            "time.sleep(300)\n"
        )
        wrapper.chmod(0o700)
        env = stand.isolated_env("author")
        env["PATH"] = str(isolated) + os.pathsep + env["PATH"]
        started = time.monotonic()
        process = subprocess.Popen(
            argv,
            env=env,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            deadline = time.monotonic() + 30
            while not barrier.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Mutation fault did not reach its controlled barrier")
                time.sleep(0.02)
            if phase == "timeout-after-write":
                try:
                    process.communicate(timeout=0.2)
                except subprocess.TimeoutExpired:
                    timed_out = True
                else:
                    raise RuntimeError("Injected timeout unexpectedly completed")
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            if process.returncode == 0:
                raise RuntimeError("Cancellation/timeout was accepted as success")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        matches = [
            item
            for item in pages(stand, f["prefix"] + "/issues?state=all")
            if item["title"] == title
        ]
        if phase == "cancel-before-send":
            if matches:
                raise RuntimeError("Cancelled pre-send command unexpectedly published")
            execute(stand, copied[0], directory, phase + "-controlled-retry", "author")
            matches = [
                item
                for item in pages(stand, f["prefix"] + "/issues?state=all")
                if item["title"] == title
            ]
        if (
            len(matches) != 1
            or matches[0]["description"] != task["items"][0]["description"]
            or matches[0]["author"]["id"] != stand.manifest["users"]["author"]["id"]
            or matches[0]["labels"] != f["issue"]["labels"]
            or matches[0]["milestone"]["id"] != f["issue"]["milestone"]["id"]
        ):
            raise RuntimeError("Server reconciliation did not establish exactly one complete issue")
        observation = {
            "phase": phase,
            "origin": "fault-injection",
            "server_postcondition_origin": "real-server",
            "command": shlex.join(argv),
            "exit_code": process.returncode,
            "stdout": stand.redact(stdout),
            "stderr": stand.redact(stderr),
            "timeout": timed_out,
            "duration_seconds": round(time.monotonic() - started, 3),
            "issue": matches[0],
            "ambiguous_write_repeated": False,
            "controlled_retry": "actual copied creation"
            if phase == "cancel-before-send"
            else "read-only reconciliation; confirmed write must not be repeated",
        }
        write_json(directory / (phase + ".json"), observation)
        results.append(observation)
    return results
