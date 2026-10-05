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


def init_repo(
    log: list[dict[str, Any]], path: Path, env: dict[str, str], files: dict[str, str]
) -> str:
    path.mkdir(parents=True)
    git(log, path, env, "init", "--quiet", "--initial-branch=main")
    git(log, path, env, "config", "user.name", "Reviewmatic smoke")
    git(log, path, env, "config", "user.email", "reviewmatic-smoke@example.invalid")
    # These commits exist only in disposable smoke repositories, not project history.
    git(log, path, env, "config", "commit.gpgsign", "false")
    for relative, content in files.items():
        destination = path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    git(log, path, env, "add", ".")
    git(log, path, env, "commit", "--quiet", "-m", "smoke baseline")
    return git(log, path, env, "rev-parse", "HEAD")


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
    checkout = temp / "local-wip"
    init_repo(log, checkout, environment, {"review.txt": "before\n"})
    (checkout / "review.txt").write_text("before\nchanged\n", encoding="utf-8")
    prepared = json.loads(
        run(
            log,
            "uvx prepare-local",
            uvx_command(
                uvx,
                source,
                ["prepare-local", "--repo-root", str(checkout), "--incremental", "auto", "--json"],
            ),
            temp,
            environment,
        ).stdout
    )
    if prepared.get("status") != "ok":
        raise SmokeError(f"prepare-local did not complete: {json.dumps(prepared)}")
    review = prepared["review"]
    package = review["context_package"]
    command = shlex.split(package["record_command"])
    if not command or command[0] != "reviewmatic":
        raise SmokeError("prepare-local returned an invalid continuation command")
    template_path = Path(package["template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    template["goal"] = {"status": "known", "text": "Verify the selected Git runtime."}
    template["acceptance_criteria"] = {
        "status": "known",
        "items": ["The returned continuation runs from the selected Git ref."],
    }
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n")
    continued = json.loads(
        run(
            log,
            "uvx returned continuation",
            uvx_command(uvx, source, [*command[1:], "--json"]),
            temp,
            environment,
        ).stdout
    )
    if continued.get("status") != "ok":
        raise SmokeError(f"returned continuation failed: {json.dumps(continued)}")

    request_log = temp / "fake-glab.jsonl"
    fake_glab = Path(environment["PATH"].split(os.pathsep, maxsplit=1)[0]) / "glab"
    fake_glab.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "host = args[args.index('--hostname') + 1]\n"
        "method_index = args.index('--method')\n"
        "method, endpoint = args[method_index + 1:method_index + 3]\n"
        "with open(os.environ['FAKE_GLAB_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps({'hostname': host, 'method': method, 'endpoint': endpoint}) + '\\n')\n"
        "print('{}')\n",
        encoding="utf-8",
    )
    fake_glab.chmod(0o700)
    marker_env = {**environment, "FAKE_GLAB_LOG": str(request_log)}
    binding = "a" * 64
    run(
        log,
        "uvx marker-run fake transport",
        uvx_command(
            uvx,
            source,
            [
                "marker-run",
                "--skill",
                "code-review",
                "--action",
                "patch:install-smoke",
                "--binding",
                binding,
                "--",
                "glab",
                "api",
                "--hostname",
                "gitlab.example",
                "--method",
                "POST",
                "projects/7/merge_requests/1/discussions",
            ],
        ),
        temp,
        marker_env,
    )
    requests = [json.loads(line) for line in request_log.read_text(encoding="utf-8").splitlines()]
    if requests != [
        {
            "hostname": "gitlab.example",
            "method": "POST",
            "endpoint": "projects/7/merge_requests/1/discussions",
        }
    ]:
        raise SmokeError(f"fake transport target mismatch: {requests}")
    marker_root = Path(environment["XDG_STATE_HOME"]) / "agent-skills" / "post-success" / "v1"
    markers = list((marker_root / "markers").glob("*/*.json"))
    if len(markers) != 1:
        raise SmokeError(f"marker-run recorded {len(markers)} markers, expected one")
    record(log, event="verified", label="Git continuation and marker block", markers=1)


def check(log: list[dict[str, Any]]) -> None:
    uvx = shutil.which("uvx")
    uv = shutil.which("uv")
    if uvx is None or uv is None:
        raise SmokeError("the Mise uv/uvx executable is unavailable")
    temp_root_arg = tempfile.gettempdir()
    with tempfile.TemporaryDirectory(prefix="reviewmatic-install-", dir=temp_root_arg) as raw:
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
    log_path = ROOT / ".build" / "reviewmatic-install-smoke.jsonl"
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
