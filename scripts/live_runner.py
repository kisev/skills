#!/usr/bin/env python3
"""Synthetic live-run runner (verification speed 2).

One command turns a versioned scenario into a real-model run: load the
pinned profile, stage the fixture into an isolated empty workdir, run the
engine subprocess under a positive environment allowlist, evaluate
declarative assertions, and write a verdict with redacted transcript
evidence under ``.build/live-runs/``.

Nothing is guessed: the engine, engine profile, and budgets come from
``evals/live/profile.json``; a missing or unresolvable profile is a loud
instructive error, never a fallback to whatever happens to resolve.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LIVE_DIR = ROOT / "evals" / "live"
PROFILE_PATH = LIVE_DIR / "profile.json"
REPORT_ROOT = ROOT / ".build" / "live-runs"
BUILD_SKILLS = ROOT / ".build" / "skills"

RUN_SCHEMA = "live-run/v1"
SCENARIO_SCHEMA = "live-scenario/v1"
SENSITIVE_KEY = re.compile(r"(?:token|secret|password|authorization|cookie|api[_-]?key)", re.I)
SECRET_VALUE = re.compile(
    r"\b(?:sk|ghp|glpat)[-_][A-Za-z0-9_-]{8,}|\b(?:bearer|basic)\s+[A-Za-z0-9._-]+", re.I
)

# The engine's environment: tools and paths, never credentials. A positive
# allowlist: every other name is withheld whatever it carries, so a
# credential can never ride along by being named something a filter would
# not recognize. An engine needing another variable is a reviewed change to
# this list, not a config knob.
ENV_NAMES = frozenset({"PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "TMPDIR", "TZ", "LANG"})
ENV_PREFIXES = ("LC_", "XDG_")

RUNNER = Callable[..., subprocess.CompletedProcess[str]]


def allowlisted_env(environ: dict[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environ is None else environ
    return {
        key: value
        for key, value in source.items()
        if key in ENV_NAMES or key.startswith(ENV_PREFIXES)
    }


def redact_text(text: str) -> str:
    return SECRET_VALUE.sub("[REDACTED]", text)


def host_state(dirs: list[Path]) -> dict[str, str]:
    """Bounded fingerprint of engine-owned host directories."""
    state: dict[str, str] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                info = path.stat()
                state[path.as_posix()] = f"{info.st_mtime_ns}:{info.st_size}"
    return state


def host_drift(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _host_watch(profile: dict[str, Any]) -> list[Path]:
    # The engine's own home under ccr: where session artifacts land. Watching
    # all of HOME would be unbounded; this is the bounded, honest scope.
    name = str(profile.get("ccr_profile", ""))
    home = Path.home() / ".claude-code-router" / "profiles" / name
    return [home] if name and home.is_dir() else []


# --- engine adapters ---------------------------------------------------------


@dataclass(frozen=True)
class EngineAdapter:
    """One subprocess pattern per engine; scenarios never learn the engine."""

    engine: str
    build_start: Callable[..., list[str]]
    parse: Callable[[str], tuple[str, str | None]]

    def preflight(self) -> list[str]:
        problems: list[str] = []
        if shutil.which(self.engine) is None:
            problems.append(f"engine CLI '{self.engine}' is not on PATH")
        return problems


def _claude_parse(raw: str) -> tuple[str, str | None]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    if not isinstance(payload, dict):
        return raw, None
    session = payload.get("session_id")
    return str(payload.get("result", "")), str(session) if session else None


def _ccr_start(profile: dict[str, str], prompt: str, allowed_tools: list[str]) -> list[str]:
    # The model is chosen inside the host-side ccr profile, never here.
    # Permissions stay scoped: file edits are auto-accepted inside the
    # staged workdir, and every additional tool grant is declared by the
    # scenario, not granted blanket by the engine adapter.
    argv = [
        "ccr",
        profile["ccr_profile"],
        "--",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
    ]
    if allowed_tools:
        argv += ["--allowedTools", ",".join(allowed_tools)]
    return argv


def _ccr_preflight(profile: dict[str, str]) -> list[str]:
    problems = EngineAdapter("ccr", _ccr_start, _claude_parse).preflight()
    name = profile.get("ccr_profile", "")
    profiles_dir = Path.home() / ".claude-code-router" / "profiles"
    if not name:
        problems.append("profile.json: 'ccr_profile' is not set")
    elif not (profiles_dir / name).is_dir():
        problems.append(
            f"ccr profile '{name}' does not exist ({profiles_dir / name}); "
            "create it per docs/how-to/live-runs-ccr.md"
        )
    return problems


ADAPTERS: dict[str, EngineAdapter] = {
    "ccr": EngineAdapter("ccr", _ccr_start, _claude_parse),
}
PREFLIGHTS: dict[str, Callable[[dict[str, str]], list[str]]] = {"ccr": _ccr_preflight}


# --- profile and scenarios ---------------------------------------------------


class LiveRunError(Exception):
    """Loud, instructive failure: never a silent fallback."""


def load_profile() -> dict[str, Any]:
    if not PROFILE_PATH.is_file():
        raise LiveRunError(
            f"pinned profile is missing: {PROFILE_PATH}; "
            "restore it from the repository or see docs/how-to/live-runs-ccr.md"
        )
    profile: dict[str, Any] = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise LiveRunError("profile.json must be a JSON object")
    if SENSITIVE_KEY.search(json.dumps(profile.get("extra_keys_hint", ""))):
        raise LiveRunError("profile.json must not contain credentials")
    for key in ("engine", "ccr_profile"):
        if not isinstance(profile.get(key), str) or not profile[key]:
            raise LiveRunError(f"profile.json: '{key}' must be a non-empty string")
    if profile["engine"] not in ADAPTERS:
        raise LiveRunError(
            f"profile.json: unknown engine '{profile['engine']}' "
            f"(available: {', '.join(sorted(ADAPTERS))})"
        )
    budgets = profile.get("budgets", {})
    if not isinstance(budgets.get("timeout_seconds", 480), int):
        raise LiveRunError("profile.json: budgets.timeout_seconds must be an integer")
    return profile


def load_scenario(name: str) -> dict[str, Any]:
    directory = LIVE_DIR / name
    manifest = directory / "scenario.json"
    if not manifest.is_file():
        raise LiveRunError(f"scenario '{name}' not found under {LIVE_DIR}")
    scenario: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    if scenario.get("schema") != SCENARIO_SCHEMA:
        raise LiveRunError(f"scenario '{name}': expected schema {SCENARIO_SCHEMA}")
    if not (directory / scenario.get("prompt", "")).is_file():
        raise LiveRunError(f"scenario '{name}': prompt file is missing")
    if not (directory / "fixture").is_dir():
        raise LiveRunError(f"scenario '{name}': fixture/ directory is missing")
    for variant, config in scenario.get("variants", {}).items():
        if not (directory / config.get("assertions", "")).is_file():
            raise LiveRunError(f"scenario '{name}' variant '{variant}': assertions missing")
    return scenario


def list_scenarios() -> list[str]:
    return sorted(p.parent.name for p in LIVE_DIR.glob("*/scenario.json"))


# --- fixture staging and assertions ------------------------------------------


def snapshot(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or ".agents" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            out[rel] = f"symlink:{os.readlink(path)}"
        elif path.is_file():
            out[rel] = "file:" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return out


def stage_fixture(scenario: dict[str, Any], name: str, workdir: Path) -> list[str]:
    """Copy fixture, git-init it, install the declared built skill; return blocked bins."""
    shutil.copytree(LIVE_DIR / name / "fixture", workdir, dirs_exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "live@example.invalid"],
        ["config", "user.name", "Live Run"],
    ):
        subprocess.run(["git", *args], cwd=workdir, check=True, capture_output=True)
    skill = scenario.get("skill")
    if skill:
        source = BUILD_SKILLS / skill
        if not source.is_dir():
            raise LiveRunError(
                f"built skill '{skill}' is missing ({source}); run 'task generate' first"
            )
        shutil.copytree(source, workdir / ".agents" / "skills" / skill)
    variant = scenario["active_variant"]
    blocked: list[str] = list(scenario["variants"][variant].get("block_commands", []))
    if blocked:
        bindir = workdir.parent / "blocked-bin"
        bindir.mkdir(parents=True, exist_ok=True)
        for command in blocked:
            wrapper = bindir / command
            wrapper.write_text(
                f"#!/bin/sh\necho '{command}: blocked by live-run fault injection' >&2\nexit 1\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
    return blocked


def evaluate_assertions(
    checks: list[dict[str, Any]],
    workdir: Path,
    before: dict[str, str],
    after: dict[str, str],
    output: str,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for index, check in enumerate(checks):
        kind = str(check.get("type", ""))
        path = str(check.get("path", ""))
        target = workdir / path
        status = "failed"
        if kind == "file_exists":
            status = "passed" if target.exists() else "failed"
        elif kind == "is_symlink":
            ok = target.is_symlink()
            want = check.get("target")
            if ok and isinstance(want, str):
                ok = os.readlink(target) == want
            status = "passed" if ok else "failed"
        elif kind == "is_regular_file":
            status = "passed" if (target.is_file() and not target.is_symlink()) else "failed"
        elif kind == "content_equals_sibling":
            sibling = workdir / str(check.get("sibling", ""))
            ok = (
                target.is_file()
                and not target.is_symlink()
                and sibling.is_file()
                and target.read_bytes() == sibling.read_bytes()
            )
            status = "passed" if ok else "failed"
        elif kind == "hash_unchanged":
            status = "passed" if before.get(path) == after.get(path) else "failed"
        elif kind == "output_mentions":
            flags = 0
            if "i" in str(check.get("flags", "")):
                flags |= re.IGNORECASE
            status = (
                "passed" if re.search(str(check.get("pattern", "")), output, flags) else "failed"
            )
        else:
            status = "failed"
        results.append({"id": f"{kind}:{path or index}", "status": status})
    return results


# --- run and report ----------------------------------------------------------


def write_report(report: dict[str, Any], stdout: str, stderr: str) -> Path:
    run_dir = (
        REPORT_ROOT / f"{time.strftime('%Y%m%dT%H%M%S')}-{report['scenario']}-{report['variant']}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "transcript.txt").write_text(
        f"--- stdout (redacted) ---\n{redact_text(stdout[-8000:])}\n"
        f"--- stderr (redacted) ---\n{redact_text(stderr[-4000:])}\n",
        encoding="utf-8",
    )
    report["transcript"] = str(run_dir / "transcript.txt")
    (run_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return run_dir


def run_scenario(
    name: str,
    variant: str,
    profile: dict[str, Any],
    runner: RUNNER = subprocess.run,
) -> dict[str, Any]:
    scenario = load_scenario(name)
    variants = scenario.get("variants", {})
    if variant not in variants:
        raise LiveRunError(f"scenario '{name}' has no variant '{variant}'")
    scenario["active_variant"] = variant
    adapter = ADAPTERS[profile["engine"]]
    timeout = int(profile.get("budgets", {}).get("timeout_seconds", 480))
    with tempfile.TemporaryDirectory(prefix=f"live-run-{name}-") as temporary:
        workdir = Path(temporary) / "fixture"
        workdir.mkdir()
        blocked = stage_fixture(scenario, name, workdir)
        before = snapshot(workdir)
        prompt = (LIVE_DIR / name / scenario["prompt"]).read_text(encoding="utf-8").strip()
        argv = adapter.build_start(
            profile={k: str(v) for k, v in profile.items()},
            prompt=prompt,
            allowed_tools=[str(t) for t in scenario.get("allowed_tools", [])],
        )
        env = allowlisted_env()
        if blocked:
            env["PATH"] = f"{Path(temporary) / 'blocked-bin'}:{env['PATH']}"
        watch = _host_watch(profile)
        host_before = host_state(watch)
        started = time.monotonic()
        verdict = "PASS"
        error = ""
        try:
            process = runner(
                argv,
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            process, verdict = None, "TIMEOUT"
        after = snapshot(workdir)
        drift = host_drift(host_before, host_state(watch))
        if drift:
            print(
                f"host drift: {len(drift)} path(s) under the engine profile "
                "(session artifacts; documented cost, not a leak)",
                file=sys.stderr,
            )
        output = adapter.parse(process.stdout)[0] if process is not None else ""
        stderr = process.stderr if process is not None else "run exceeded its timeout budget"
        if process is not None and process.returncode != 0:
            verdict, error = "ERROR", f"engine exited with {process.returncode}"
        checks = json.loads(
            (LIVE_DIR / name / variants[variant]["assertions"]).read_text(encoding="utf-8")
        )
        results = evaluate_assertions(checks, workdir, before, after, output)
        if verdict == "PASS" and any(item["status"] != "passed" for item in results):
            verdict = "FAIL"
        report: dict[str, Any] = {
            "schema": RUN_SCHEMA,
            "scenario": name,
            "variant": variant,
            "engine": profile["engine"],
            "engine_profile": profile.get("ccr_profile", ""),
            "verdict": verdict,
            "error": error,
            "duration_seconds": round(time.monotonic() - started, 1),
            "assertions": results,
            "host_drift": drift,
        }
        run_dir = write_report(report, output, stderr)
    return {**report, "report_dir": str(run_dir)}


def preflight() -> list[str]:
    problems: list[str] = []
    try:
        profile = load_profile()
    except LiveRunError as error:
        return [str(error)]
    problems += PREFLIGHTS[profile["engine"]](
        {k: str(v) for k, v in profile.items() if isinstance(v, str)}
    )
    for name in list_scenarios():
        try:
            scenario = load_scenario(name)
            if scenario.get("skill") and not (BUILD_SKILLS / scenario["skill"]).is_dir():
                problems.append(f"scenario '{name}': built skill missing, run 'task generate'")
        except LiveRunError as error:
            problems.append(str(error))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run"))
    parser.add_argument("--scenario")
    parser.add_argument("--variant", default="default")
    parser.add_argument("--all", action="store_true", dest="sweep")
    args = parser.parse_args(argv)
    if args.command == "preflight":
        problems = preflight()
        for line in problems:
            print(f"FAIL {line}")
        print("preflight: OK" if not problems else "preflight: FAILED")
        return 0 if not problems else 1
    if args.sweep and args.scenario:
        print("run: --scenario and --all are exclusive", file=sys.stderr)
        return 2
    if not args.sweep and not args.scenario:
        print("run requires --scenario or --all", file=sys.stderr)
        return 2
    try:
        profile = load_profile()
    except LiveRunError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 2
    names = list_scenarios() if args.sweep else [args.scenario]
    if not names:
        print(f"no scenarios found under {LIVE_DIR}", file=sys.stderr)
        return 2
    reports: list[dict[str, Any]] = []
    failed = False
    for name in names:
        try:
            report = run_scenario(name, args.variant, profile)
        except LiveRunError as error:
            print(f"FAIL {error}", file=sys.stderr)
            report = {"scenario": name, "variant": args.variant, "verdict": "ERROR"}
            failed = True
        reports.append(report)
        if report["verdict"] != "PASS":
            failed = True
    if args.sweep:
        for report in reports:
            print(f"{report['scenario']}: {report['verdict']}")
        passed = sum(1 for report in reports if report["verdict"] == "PASS")
        print(f"sweep: {passed}/{len(reports)} passed")
    else:
        print(json.dumps(reports[0], ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
