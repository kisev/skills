#!/usr/bin/env python3
"""Smoke-test reviewmatic Git, wheel, and sdist installs outside the checkout."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "reviewmatic"
IGNORED = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


class SmokeError(Exception):
    """A bounded reviewmatic installation smoke failed."""


def git_head(path: Path, environment: dict[str, str]) -> str | None:
    git_executable = environment.get("REVIEWMATIC_GIT_EXECUTABLE") or shutil.which(
        "git", path=environment.get("PATH")
    )
    if git_executable is None:
        return None
    result = subprocess.run(
        [git_executable, "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def record(log: list[dict[str, Any]], **event: object) -> None:
    log.append(dict(event))


def run(
    log: list[dict[str, Any]],
    label: str,
    argv: list[str],
    cwd: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    before = git_head(cwd, environment)
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    after = git_head(cwd, environment)
    record(
        log,
        event="command",
        label=label,
        argv=argv,
        cwd=str(cwd),
        head_before=before,
        head_after=after,
        returncode=result.returncode,
        stdout=result.stdout[-1000:],
        stderr=result.stderr[-1000:],
    )
    if result.returncode != 0:
        raise SmokeError(f"{label} failed ({result.returncode}): {result.stderr[-1000:]}")
    return result


def make_environment(root: Path, tool_bin: Path) -> dict[str, str]:
    executables = {
        "git": shutil.which("git"),
        "python3": sys.executable,
        "uv": shutil.which("uv"),
        "uvx": shutil.which("uvx"),
    }
    for name, target in executables.items():
        if target is None:
            raise SmokeError(f"required executable is unavailable: {name}")
        (tool_bin / name).symlink_to(target)
    git_executable = executables["git"]
    if git_executable is None:
        raise SmokeError("the Git executable is unavailable")
    blocked_log = root / "forbidden-tool-calls.txt"
    for name in ("node", "nodejs", "npm", "npx", "corepack"):
        blocker = tool_bin / name
        blocker.write_text(
            f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(name)} >> \"$FORBIDDEN_TOOL_LOG\"\nexit 127\n",
            encoding="utf-8",
        )
        blocker.chmod(0o700)
    path_value = f"{tool_bin}:/usr/bin:/bin"
    if shutil.which("node", path=path_value) != str(tool_bin / "node"):
        raise SmokeError("the smoke PATH does not block the system Node executable")
    if shutil.which("reviewmatic", path=path_value) is not None:
        raise SmokeError("the isolated smoke PATH unexpectedly contains reviewmatic")
    home = root / "home"
    state = root / "state"
    cache = root / "uv-cache"
    for directory in (home, state, cache):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "PATH": path_value,
        "PYTHONNOUSERSITE": "1",
        "UV_CACHE_DIR": str(cache),
        "UV_NO_PROGRESS": "1",
        "XDG_CACHE_HOME": str(root / "xdg-cache"),
        "XDG_CONFIG_HOME": str(root / "xdg-config"),
        "XDG_STATE_HOME": str(state),
        "FORBIDDEN_TOOL_LOG": str(blocked_log),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "REVIEWMATIC_GIT_EXECUTABLE": str(Path(git_executable).resolve()),
    }


def git(log: list[dict[str, Any]], cwd: Path, env: dict[str, str], *args: str) -> str:
    return run(
        log,
        "git " + " ".join(args),
        [env["REVIEWMATIC_GIT_EXECUTABLE"], "-C", str(cwd), *args],
        cwd,
        env,
    ).stdout.strip()


def copy_application(snapshot: Path) -> None:
    destination = snapshot / "apps" / "reviewmatic"
    destination.parent.mkdir(parents=True)

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in IGNORED or name.endswith((".pyc", ".egg-info"))}

    shutil.copytree(APP, destination, ignore=ignore)


def uvx_command(uvx: str, source: str, command: list[str]) -> list[str]:
    return [
        uvx,
        "--isolated",
        "--no-config",
        "--no-env-file",
        "--python",
        sys.executable,
        "--from",
        source,
        "reviewmatic",
        *command,
    ]


def verify_source_continuation(
    log: list[dict[str, Any]],
    temp: Path,
    source: str,
    uvx: str,
    environment: dict[str, str],
) -> None:
    """Exercise the helper surface from the selected Git source."""
    info = json.loads(
        run(
            log,
            "uvx runtime-info",
            uvx_command(uvx, source, ["runtime-info"]),
            temp,
            environment,
        ).stdout
    )
    if info.get("status") != "ok" or info.get("external_mutations") is not False:
        raise SmokeError(f"runtime-info did not complete: {json.dumps(info)}")

    profile = json.loads(
        run(
            log,
            "uvx profiles",
            uvx_command(uvx, source, ["profiles"]),
            temp,
            environment,
        ).stdout
    )
    if profile.get("status") != "missing":
        raise SmokeError(f"the isolated profile was not missing: {json.dumps(profile)}")

    background_input = temp / "background.json"
    background_input.write_text(
        json.dumps(
            {
                "task": {"goal": "Verify the helper surface.", "acceptance_criteria": ["Runs."]},
                "sections": [{"title": "Context", "body": "The selected Git ref runs."}],
            }
        ),
        encoding="utf-8",
    )
    background_output = temp / "background.md"
    assembled = json.loads(
        run(
            log,
            "uvx background",
            uvx_command(
                uvx,
                source,
                [
                    "background",
                    "--input",
                    str(background_input),
                    "--output",
                    str(background_output),
                ],
            ),
            temp,
            environment,
        ).stdout
    )
    if assembled.get("status") != "ok" or not background_output.is_file():
        raise SmokeError(f"background did not complete: {json.dumps(assembled)}")

    draft_input = temp / "drafts.json"
    draft_input.write_text(
        json.dumps(
            {
                "hostname": "gitlab.example",
                "project_id": 7,
                "mr_iid": 1,
                "head_sha": "a" * 40,
                "general_notes": ["A smoke draft."],
            }
        ),
        encoding="utf-8",
    )
    draft_output = temp / "drafts.sh"
    drafted = json.loads(
        run(
            log,
            "uvx drafts",
            uvx_command(
                uvx,
                source,
                ["drafts", "--input", str(draft_input), "--output", str(draft_output)],
            ),
            temp,
            environment,
        ).stdout
    )
    block = draft_output.read_text(encoding="utf-8")
    if drafted.get("status") != "ok" or "reviewed_head=" not in block:
        raise SmokeError(f"drafts did not complete: {json.dumps(drafted)}")
    if "publish" in block.lower():
        raise SmokeError("the draft block must not carry a publish command")

    for removed in ("run", "marker-run", "prepare-local", "record-critic"):
        rejected = subprocess.run(
            uvx_command(uvx, source, [removed]),
            cwd=temp,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if rejected.returncode == 0:
            raise SmokeError(f"the removed command still succeeds: {removed}")
    record(log, event="verified", label="Git helper surface", commands=7)


def check(log: list[dict[str, Any]]) -> None:
    uvx = shutil.which("uvx")
    uv = shutil.which("uv")
    if uvx is None or uv is None:
        raise SmokeError("the Mise uv/uvx executable is unavailable")
    temp_root_arg = tempfile.gettempdir()
    with tempfile.TemporaryDirectory(prefix="reviewmatic-smoke-", dir=temp_root_arg) as raw:
        temp = Path(raw)
        tool_bin = temp / "bin"
        tool_bin.mkdir()
        environment = make_environment(temp, tool_bin)
        snapshot = temp / "git-snapshot"
        copy_application(snapshot)
        # The snapshot contains a subdirectory package, so initialize its Git
        # repository after copying and commit only the copied application.
        git(log, snapshot, environment, "init", "--quiet", "--initial-branch=main")
        git(log, snapshot, environment, "config", "user.name", "Reviewmatic smoke")
        git(log, snapshot, environment, "config", "user.email", "reviewmatic-smoke@example.invalid")
        # This synthetic source snapshot is not a commit in the working repository.
        git(log, snapshot, environment, "config", "commit.gpgsign", "false")
        git(log, snapshot, environment, "add", "apps/reviewmatic")
        git(log, snapshot, environment, "commit", "--quiet", "-m", "local install snapshot")
        revision = git(log, snapshot, environment, "rev-parse", "HEAD")
        source = f"git+{snapshot.as_uri()}@{revision}#subdirectory=apps/reviewmatic"
        app_dir = snapshot / "apps" / "reviewmatic"
        distributions = temp / "distributions"
        distributions.mkdir()
        run(
            log,
            "uv build wheel and sdist",
            [uv, "build", "--out-dir", str(distributions)],
            app_dir,
            environment,
        )
        wheel = next(distributions.glob("*.whl"), None)
        sdist = next(distributions.glob("*.tar.gz"), None)
        if wheel is None or sdist is None:
            raise SmokeError("uv build did not create both wheel and source distribution")
        for label, package in (
            ("local Git source", source),
            ("wheel", str(wheel)),
            ("sdist", str(sdist)),
        ):
            for arguments in (["--version"], ["--help"]):
                output = run(
                    log,
                    f"uvx {label} {' '.join(arguments)}",
                    uvx_command(uvx, package, list(arguments)),
                    temp,
                    environment,
                )
                if arguments == ["--version"] and output.stdout.strip() != str(
                    tomllib.loads((app_dir / "pyproject.toml").read_text(encoding="utf-8"))[
                        "project"
                    ]["version"]
                ):
                    raise SmokeError(f"uvx {label} reported an unexpected version")
        verify_source_continuation(log, temp, source, uvx, environment)
        forbidden_log = Path(environment["FORBIDDEN_TOOL_LOG"])
        if forbidden_log.exists():
            raise SmokeError(
                f"smoke invoked a forbidden Node/npm command: {forbidden_log.read_text(encoding='utf-8')}"
            )


def main() -> int:
    log: list[dict[str, Any]] = []
    log_path = ROOT / ".build" / "reviewmatic-smoke.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root_head_before = git_head(ROOT, dict(os.environ))
    record(log, event="boundary", phase="before", cwd=str(Path.cwd()), head=root_head_before)
    try:
        check(log)
        status = 0
    except (OSError, SmokeError, ValueError, json.JSONDecodeError) as error:
        record(log, event="failure", message=str(error))
        status = 1
    finally:
        root_head_after = git_head(ROOT, dict(os.environ))
        record(log, event="boundary", phase="after", cwd=str(Path.cwd()), head=root_head_after)
        log_path.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in log),
            encoding="utf-8",
        )
    print(f"Reviewmatic uvx smoke {'passed' if status == 0 else 'failed'}; log: {log_path}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
