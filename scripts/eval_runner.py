#!/usr/bin/env python3
"""Non-interactive behavioral evaluation harness for supported agent hosts."""

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
import uuid
from pathlib import Path
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
SCENARIO_SCHEMA = "eval-scenario/v1"
RESULT_SCHEMA = "eval-result/v1"
ADAPTER_PROTOCOLS = {"opencode": "opencode-cli-json/v1", "codex": "codex-cli-json/v1"}
SENSITIVE_KEY = re.compile(r"(?:token|secret|password|authorization|cookie|api[_-]?key)", re.I)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ABSOLUTE_PATH = re.compile(r"(?<![\w.-])(?:/[\w.-]+){2,}|[A-Za-z]:\\[^\s\"']+")
SECRET_VALUE = re.compile(
    r"(?:\b(?:bearer|basic)\s+|\b(?:sk|ghp|glpat)_[a-z0-9_-]{8,}|\bAKIA[0-9A-Z]{12,})", re.I
)


class EvalError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 2) -> None:
        self.code = code
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def redact(value: Any, key: str = "") -> Any:
    """Apply the sole redaction policy before values become observable artifacts."""
    if SENSITIVE_KEY.search(key) and key not in {
        "max_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
    }:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(name): redact(item, str(name)) for name, item in sorted(value.items())}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return ABSOLUTE_PATH.sub("[PATH]", CONTROL.sub("", value))
    return value


def contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (
                SENSITIVE_KEY.search(str(key))
                and str(key) not in {"max_tokens", "total_tokens", "input_tokens", "output_tokens"}
            )
            or contains_secret(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_secret(item) for item in value)
    return isinstance(value, str) and bool(SECRET_VALUE.search(value))


def redact_text(value: str) -> Any:
    """Redact opaque host streams without assuming their event schema is valid."""
    lines: list[Any] = []
    for line in value.splitlines():
        try:
            lines.append(redact(json.loads(line)))
        except json.JSONDecodeError:
            lines.append(
                SECRET_VALUE.sub("[REDACTED]", ABSOLUTE_PATH.sub("[PATH]", CONTROL.sub("", line)))
            )
    return lines


def emit(value: dict[str, Any], exit_code: int) -> NoReturn:
    print(json.dumps(redact(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    raise SystemExit(exit_code)


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvalError("malformed_json", f"cannot read scenario {path.name}: {error}") from error
    if not isinstance(raw, dict):
        raise EvalError("malformed_scenario", f"{path.name} must contain an object")
    return raw


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value:
        raise EvalError("sandbox_escape", "scenario path escapes the repository sandbox")
    return path


def scenario_digest(scenario: dict[str, Any]) -> str:
    content = {key: value for key, value in scenario.items() if key != "digest"}
    return digest(content)


def validate_scenario(scenario: dict[str, Any], filename: str) -> list[str]:
    required = {
        "schema",
        "id",
        "revision",
        "kind",
        "surface",
        "host",
        "input",
        "expected",
        "invariants",
        "sandbox",
        "budgets",
        "digest",
    }
    missing = sorted(required - set(scenario))
    if missing:
        raise EvalError("malformed_scenario", f"{filename}: missing {','.join(missing)}")
    if scenario["schema"] != SCENARIO_SCHEMA:
        raise EvalError("unsupported_schema", f"{filename}: unexpected scenario schema")
    if not isinstance(scenario["id"], str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]{2,80}", scenario["id"]
    ):
        raise EvalError("malformed_scenario", f"{filename}: immutable id is invalid")
    if not isinstance(scenario["revision"], int) or scenario["revision"] < 1:
        raise EvalError("malformed_scenario", f"{filename}: revision must be a positive integer")
    if scenario["kind"] not in {"deterministic", "trigger", "near-miss", "golden"}:
        raise EvalError("malformed_scenario", f"{filename}: kind is invalid")
    if scenario["surface"] not in {"skill", "command", "agent", "plugin"}:
        raise EvalError("malformed_scenario", f"{filename}: surface is invalid")
    if scenario["host"] not in {"opencode", "codex", "any"}:
        raise EvalError("malformed_scenario", f"{filename}: host is invalid")
    if not isinstance(scenario["input"], dict) or not isinstance(scenario["expected"], dict):
        raise EvalError("malformed_scenario", f"{filename}: input and expected must be objects")
    if not isinstance(scenario["invariants"], list) or not scenario["invariants"]:
        raise EvalError("malformed_scenario", f"{filename}: invariants must be a nonempty list")
    if not isinstance(scenario["sandbox"], dict) or scenario["sandbox"].get("network") is not False:
        raise EvalError("malformed_scenario", f"{filename}: sandbox must disable network")
    budgets = scenario["budgets"]
    if not isinstance(budgets, dict) or any(
        key not in budgets for key in ("timeout_seconds", "max_tokens", "max_cost")
    ):
        raise EvalError("malformed_scenario", f"{filename}: complete budgets are required")
    if any(not isinstance(budgets[key], (int, float)) or budgets[key] <= 0 for key in budgets):
        raise EvalError("malformed_scenario", f"{filename}: budgets must be positive")
    if scenario["digest"] != scenario_digest(scenario):
        raise EvalError(
            "digest_drift", f"{filename}: scenario digest does not match canonical content"
        )
    if contains_secret({key: value for key, value in scenario.items() if key != "budgets"}):
        raise EvalError("secret_fixture", f"{filename}: sensitive key is forbidden in corpus")
    for invariant in scenario["invariants"]:
        if not isinstance(invariant, dict) or not isinstance(invariant.get("path"), str):
            raise EvalError(
                "malformed_scenario", f"{filename}: invariant must name a repository path"
            )
        safe_relative(invariant["path"])
    return [scenario["id"]]


def discover(corpus: Path) -> list[dict[str, Any]]:
    if not corpus.is_dir():
        raise EvalError("missing_corpus", "scenario corpus directory does not exist")
    scenarios: list[dict[str, Any]] = []
    ids: set[str] = set()
    revisions: set[tuple[str, int]] = set()
    for path in sorted(corpus.glob("*.json")):
        scenario = load_json(path)
        validate_scenario(scenario, path.name)
        key = (scenario["id"], scenario["revision"])
        if scenario["id"] in ids or key in revisions:
            raise EvalError(
                "duplicate_scenario", f"duplicate immutable scenario identity: {scenario['id']}"
            )
        ids.add(scenario["id"])
        revisions.add(key)
        scenarios.append(scenario)
    if not scenarios:
        raise EvalError("missing_corpus", "scenario corpus is empty")
    return scenarios


def validate_schemas(root: Path) -> None:
    expected = {
        "scenario-v1.schema.json": "https://kisev.dev/schemas/eval-scenario/v1",
        "result-v1.schema.json": "https://kisev.dev/schemas/eval-result/v1",
    }
    for filename, identifier in expected.items():
        try:
            schema = load_json(root / "evals" / "schemas" / filename)
        except EvalError as error:
            raise EvalError("malformed_schema", error.message) from error
        if (
            schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
            or schema.get("$id") != identifier
        ):
            raise EvalError(
                "malformed_schema", f"{filename}: versioned JSON Schema identifier is invalid"
            )


def validate_fixtures(root: Path) -> None:
    fixtures = root / "evals" / "fixtures"
    for path in sorted(fixtures.glob("*.json")):
        value = load_json(path)
        if contains_secret(value):
            raise EvalError("secret_fixture", f"{path.name}: sensitive fixture value is forbidden")
        for item in value.values():
            if isinstance(item, str) and (CONTROL.search(item) or ABSOLUTE_PATH.search(item)):
                raise EvalError(
                    "unsafe_fixture", f"{path.name}: controls and absolute paths are forbidden"
                )


def select(scenarios: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    wanted_ids = set(args.scenario or [])
    selected = [
        item
        for item in scenarios
        if (not wanted_ids or item["id"] in wanted_ids)
        and (args.kind is None or item["kind"] == args.kind)
        and (args.surface is None or item["surface"] == args.surface)
    ]
    unknown = wanted_ids - {item["id"] for item in scenarios}
    if unknown:
        raise EvalError("unknown_scenario", f"unknown scenario: {','.join(sorted(unknown))}")
    return selected


def assertions_for_invariants(scenario: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    for invariant in sorted(scenario["invariants"], key=lambda item: str(item["id"])):
        target = root / safe_relative(invariant["path"])
        passed = target.is_file() and not target.is_symlink()
        contains = invariant.get("contains")
        absent = invariant.get("absent")
        text = target.read_text(encoding="utf-8") if passed else ""
        if isinstance(contains, str):
            passed = passed and contains in text
        if isinstance(absent, str):
            passed = passed and absent not in text
        assertions.append({"id": invariant["id"], "status": "passed" if passed else "failed"})
    return assertions


def expected_assertions(
    scenario: dict[str, Any], observation: dict[str, Any]
) -> list[dict[str, Any]]:
    selected = set(str(item) for item in observation.get("selected", []))
    result: list[dict[str, Any]] = []
    for name in sorted(str(item) for item in scenario["expected"].get("selected", [])):
        result.append(
            {"id": f"selected:{name}", "status": "passed" if name in selected else "failed"}
        )
    for name in sorted(str(item) for item in scenario["expected"].get("not_selected", [])):
        result.append(
            {"id": f"not_selected:{name}", "status": "passed" if name not in selected else "failed"}
        )
    return result


def offline_observation(scenario: dict[str, Any], root: Path) -> dict[str, Any]:
    """Run explicitly declared portable runner checks without a host or network."""
    fixture = scenario["input"].get("fixture", {})
    selected = fixture.get("selected", []) if isinstance(fixture, dict) else []
    runner = scenario["input"].get("offline_runner")
    if not isinstance(runner, dict):
        return {"selected": selected, "usage": {"telemetry": "not-applicable"}}
    skill, script, target = runner.get("skill"), runner.get("script"), runner.get("target")
    if not all(isinstance(value, str) and value for value in (skill, script, target)):
        raise EvalError("malformed_scenario", "offline_runner requires skill, script, and target")
    assert isinstance(skill, str) and isinstance(script, str) and isinstance(target, str)
    executable = root / ".build" / "skills" / skill / script
    if not executable.is_file():
        raise EvalError("missing_runner", "offline_runner is not materialized")
    with tempfile.TemporaryDirectory(prefix="skills-gitlab-eval-") as temporary:
        sandbox = Path(temporary)
        log = sandbox / "glab.jsonl"
        state = sandbox / "state"
        state.write_text("fresh", encoding="utf-8")
        glab = sandbox / "glab"
        glab.write_text(
            """#!%s
import json
import os
import sys
from pathlib import Path
endpoint = sys.argv[-1]
Path(os.environ["FAKE_GLAB_LOG"]).open("a", encoding="utf-8").write(json.dumps(sys.argv[1:]) + "\\n")
changed = Path(os.environ["FAKE_GLAB_STATE"]).read_text(encoding="utf-8") == "changed"
if endpoint.startswith("projects/group%%2Fproject"):
    value = {"id": 19}
elif endpoint == "projects/19/merge_requests/7":
    value = {"iid": 7, "updated_at": "changed" if changed else "fresh", "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"}}
elif endpoint == "projects/19/merge_requests/7/changes":
    value = {"changes": [], "diff_refs": {"base_sha": "a", "start_sha": "b", "head_sha": "c"}}
elif endpoint.startswith("projects/19/merge_requests/7/commits"):
    value = [{"id": "c"}]
else:
    value = []
print(json.dumps(value))
"""
            % sys.executable,
            encoding="utf-8",
        )
        glab.chmod(0o755)
        environment = isolated_environment(sandbox)
        environment.update(
            {
                "PATH": f"{sandbox}:{environment['PATH']}",
                "FAKE_GLAB_LOG": str(log),
                "FAKE_GLAB_STATE": str(state),
            }
        )
        process = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(executable), "prepare", "--url", target],
            cwd=sandbox,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            output = {}
        items = output.get("items", []) if isinstance(output, dict) else []
        review_status = "failed"
        stale_status = "failed"
        if process.returncode == 0 and items and isinstance(items[0], dict):
            evidence = items[0].get("artifact_path")
            artifact_root = items[0].get("artifact_root")
            if isinstance(evidence, str) and isinstance(artifact_root, str):
                finalized = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-S",
                        "-B",
                        str(executable),
                        "finalize",
                        "--artifact-root",
                        artifact_root,
                    ],
                    cwd=sandbox,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                try:
                    final_output = json.loads(finalized.stdout)
                except json.JSONDecodeError:
                    final_output = {}
                final_path = (
                    final_output.get("artifact_path") if isinstance(final_output, dict) else None
                )
                final_digest = (
                    final_output.get("digest") if isinstance(final_output, dict) else None
                )
                if (
                    finalized.returncode == 0
                    and isinstance(final_path, str)
                    and isinstance(final_digest, str)
                ):
                    evidence_digest = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
                    receipt = sandbox / "receipt.json"
                    decision = sandbox / "decision.json"
                    receipt.write_text(
                        json.dumps(
                            {
                                "schema": "portable-gitlab/critic-receipt/v2",
                                "evidence_digest": evidence_digest,
                                "run_id": "critic",
                                "session_id": "critic-session",
                                "findings": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    decision.write_text(
                        json.dumps(
                            {
                                "schema": "portable-gitlab/review-decision/v2",
                                "evidence_digest": evidence_digest,
                                "finalize_digest": final_digest,
                                "verdict": "ready",
                                "run_id": "primary",
                                "session_id": "primary-session",
                                "findings": [],
                                "unresolved_threads": [],
                                "responses": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    review_command = [
                        sys.executable,
                        "-I",
                        "-S",
                        "-B",
                        str(executable),
                        "finalize-review",
                        "--evidence",
                        evidence,
                        "--report",
                        str(decision),
                        "--critic-receipt",
                        str(receipt),
                        "--finalize-report",
                        final_path,
                        "--mode",
                        "deep",
                    ]
                    review_status = (
                        "passed"
                        if subprocess.run(
                            review_command,
                            cwd=sandbox,
                            env=environment,
                            capture_output=True,
                            text=True,
                            check=False,
                        ).returncode
                        == 0
                        else "failed"
                    )
                    state.write_text("changed", encoding="utf-8")
                    stale_status = (
                        "passed"
                        if subprocess.run(
                            review_command,
                            cwd=sandbox,
                            env=environment,
                            capture_output=True,
                            text=True,
                            check=False,
                        ).returncode
                        == 2
                        else "failed"
                    )
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assertions = [
            {"id": "runner:json", "status": "passed" if isinstance(output, dict) else "failed"},
            {"id": "runner:exit", "status": "passed" if process.returncode == 0 else "failed"},
            {
                "id": "runner:exact-sha",
                "status": "passed" if items and items[0].get("head_sha") == "c" else "failed",
            },
            {
                "id": "runner:complete",
                "status": "passed" if items and items[0].get("complete") is True else "failed",
            },
            {
                "id": "runner:get-only",
                "status": "passed"
                if calls and all("GET" in call and "api" in call for call in calls)
                else "failed",
            },
            {
                "id": "runner:external-mutations",
                "status": "passed" if output.get("external_mutations") is False else "failed",
            },
            {"id": "runner:critic-final-decision", "status": review_status},
            {"id": "runner:stale-finalize", "status": stale_status},
        ]
    return {
        "selected": selected,
        "usage": {"telemetry": "not-applicable"},
        "runner_assertions": assertions,
    }


def isolated_environment(sandbox: Path) -> dict[str, str]:
    return {
        "HOME": str(sandbox / "home"),
        "XDG_CONFIG_HOME": str(sandbox / "xdg-config"),
        "XDG_CACHE_HOME": str(sandbox / "xdg-cache"),
        "XDG_STATE_HOME": str(sandbox / "xdg-state"),
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TERM": "dumb",
    }


def parse_host_output(stdout: str) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvalError("malformed_host_output", "host did not emit JSON lines", 4) from error
        if not isinstance(event, dict):
            raise EvalError("malformed_host_output", "host event is not an object", 4)
        events.append(event)
    if not events:
        raise EvalError("malformed_host_output", "host emitted no structured result", 4)
    merged: dict[str, Any] = {"selected": [], "usage": {}}
    for event in events:
        if isinstance(event.get("selected"), list):
            merged["selected"].extend(str(value) for value in event["selected"])
        if isinstance(event.get("usage"), dict):
            merged["usage"].update(event["usage"])
        if event.get("status") == "error":
            raise EvalError("host_error", "host reported an error", 4)
    merged["selected"] = sorted(set(merged["selected"]))
    return merged


def host_command(host: str, executable: str, model: str, prompt: str) -> list[str]:
    if host == "opencode":
        return [executable, "run", "--format", "json", "--model", model, prompt]
    return [executable, "exec", "--json", "--model", model, prompt]


def detect_capabilities() -> dict[str, dict[str, Any]]:
    return {
        host: {"available": shutil.which(host) is not None, "adapter": protocol}
        for host, protocol in sorted(ADAPTER_PROTOCOLS.items())
    }


def private_evidence(args: argparse.Namespace, raw: dict[str, Any]) -> list[dict[str, str]]:
    if args.output is None:
        return []
    content = canonical(
        {
            key: redact_text(value) if isinstance(value, str) else redact(value)
            for key, value in raw.items()
        }
    )
    content_digest = hashlib.sha256(content).hexdigest()
    private = args.output.parent / "private"
    private.mkdir(parents=True, exist_ok=True)
    (private / f"{content_digest}.json").write_bytes(content + b"\n")
    return [{"path": f"private/{content_digest}.json", "digest": content_digest}]


def run_host(
    scenario: dict[str, Any], args: argparse.Namespace
) -> tuple[dict[str, Any], dict[str, Any], str, list[dict[str, str]]]:
    if args.host != scenario["host"] and scenario["host"] != "any":
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "unsupported"},
            "skipped",
            [],
        )
    executable = args.executable or args.host
    if shutil.which(executable) is None and not Path(executable).is_file():
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "unsupported"},
            "skipped",
            [],
        )
    assert args.model is not None and args.timeout is not None
    sandbox_parent = Path(tempfile.mkdtemp(prefix="skills-eval-"))
    sandbox = sandbox_parent / "sandbox"
    project = sandbox / "project"
    for directory in (
        project,
        sandbox / "home",
        sandbox / "xdg-config",
        sandbox / "xdg-cache",
        sandbox / "xdg-state",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    prompt = str(scenario["input"].get("prompt", ""))
    command = host_command(args.host, executable, args.model, prompt)
    started = time.monotonic()
    try:
        process = subprocess.run(
            command,
            cwd=project,
            env=isolated_environment(sandbox),
            capture_output=True,
            text=True,
            timeout=min(args.timeout, float(scenario["budgets"]["timeout_seconds"])),
            start_new_session=True,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        shutil.rmtree(sandbox_parent, ignore_errors=True)
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "timeout", "duration_ms": int((time.monotonic() - started) * 1000)},
            "error",
            private_evidence(args, {"stdout": error.stdout or "", "stderr": error.stderr or ""}),
        )
    except OSError as error:
        shutil.rmtree(sandbox_parent, ignore_errors=True)
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "host_start_error"},
            "error",
            private_evidence(args, {"stderr": str(error)}),
        )
    if process.returncode != 0:
        shutil.rmtree(sandbox_parent, ignore_errors=True)
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "host_error"},
            "error",
            private_evidence(args, {"stdout": process.stdout, "stderr": process.stderr}),
        )
    try:
        observed = parse_host_output(process.stdout)
    except EvalError as error:
        shutil.rmtree(sandbox_parent, ignore_errors=True)
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": error.code},
            "error",
            private_evidence(args, {"stdout": process.stdout, "stderr": process.stderr}),
        )
    escaped = [
        path
        for path in sandbox_parent.rglob("*")
        if path.is_symlink() and not str(path.resolve()).startswith(str(sandbox.resolve()))
    ]
    shutil.rmtree(sandbox_parent, ignore_errors=True)
    if escaped:
        return (
            {"selected": [], "usage": {"telemetry": "incomplete"}},
            {"classification": "sandbox_escape"},
            "error",
            private_evidence(args, {"stdout": process.stdout, "stderr": process.stderr}),
        )
    return (
        observed,
        {"classification": None},
        "passed",
        private_evidence(args, {"stdout": process.stdout, "stderr": process.stderr}),
    )


def budget_assertions(
    usage: dict[str, Any], budgets: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    assertions: list[dict[str, Any]] = []
    status = "passed"
    telemetry = usage.get("telemetry")
    for usage_key, budget_key in (("total_tokens", "max_tokens"), ("cost", "max_cost")):
        value = usage.get(usage_key)
        if not isinstance(value, (int, float)):
            assertions.append({"id": f"budget:{usage_key}", "status": "incomplete"})
            continue
        passed = value <= budgets[budget_key]
        assertions.append({"id": f"budget:{usage_key}", "status": "passed" if passed else "failed"})
        if not passed:
            status = "blocked"
    if telemetry == "incomplete":
        status = status if status == "blocked" else "incomplete"
    return assertions, status


def result_for(scenario: dict[str, Any], args: argparse.Namespace, root: Path) -> dict[str, Any]:
    started_at = time.time()
    if args.offline:
        observation = offline_observation(scenario, root)
        run_status = "passed"
        error: dict[str, Any] = {"classification": None}
        evidence: list[dict[str, str]] = []
    else:
        observation, error, run_status, evidence = run_host(scenario, args)
    assertions = assertions_for_invariants(scenario, root) + expected_assertions(
        scenario, observation
    )
    assertions.extend(observation.get("runner_assertions", []))
    effective_budgets = dict(scenario["budgets"])
    if not args.offline:
        assert args.max_tokens is not None and args.max_cost is not None
        effective_budgets["max_tokens"] = min(effective_budgets["max_tokens"], args.max_tokens)
        effective_budgets["max_cost"] = min(effective_budgets["max_cost"], args.max_cost)
    if args.offline:
        budget_status = "passed"
    else:
        budget_items, budget_status = budget_assertions(
            observation.get("usage", {}), effective_budgets
        )
        assertions.extend(budget_items)
    assertions.sort(key=lambda item: item["id"])
    if run_status not in {"error", "skipped"} and any(
        item["status"] == "failed" for item in assertions
    ):
        run_status = "failed" if budget_status != "blocked" else "blocked"
    elif run_status == "passed" and budget_status == "incomplete":
        run_status = "incomplete"
    result = {
        "schema": RESULT_SCHEMA,
        "run_id": str(uuid.uuid4()),
        "scenario_id": scenario["id"],
        "scenario_revision": scenario["revision"],
        "scenario_digest": scenario["digest"],
        "host": args.host if not args.offline else "offline",
        "host_version": observation.get("host_version", "unavailable"),
        "adapter": ADAPTER_PROTOCOLS.get(args.host, "offline/v1")
        if not args.offline
        else "offline/v1",
        "adapter_version": 1,
        "model": args.model if not args.offline else None,
        "model_version": args.model if not args.offline else None,
        "status": run_status,
        "assertions": assertions,
        "started_at": int(started_at),
        "duration_ms": int((time.time() - started_at) * 1000),
        "usage": observation.get("usage", {"telemetry": "incomplete"}),
        "evidence": evidence,
        "error": error,
    }
    result["digest"] = digest(
        {
            key: value
            for key, value in result.items()
            if key not in {"run_id", "started_at", "duration_ms", "digest"}
        }
    )
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "evals" / "scenarios")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--trusted-live", action="store_true")
    parser.add_argument("--host", choices=("opencode", "codex"))
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--max-tokens", type=int)
    parser.add_argument("--max-cost", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--executable")
    parser.add_argument("--scenario", action="append")
    parser.add_argument("--kind", choices=("deterministic", "trigger", "near-miss", "golden"))
    parser.add_argument("--surface", choices=("skill", "command", "agent", "plugin"))
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args(argv)
    if args.trusted_live:
        required = (
            args.host,
            args.model,
            args.timeout,
            args.max_tokens,
            args.max_cost,
            args.output,
        )
        if not all(value is not None for value in required):
            raise EvalError(
                "live_limits_required",
                "trusted live mode requires host, model, all limits, and output",
            )
        if args.offline:
            raise EvalError("invalid_mode", "offline and trusted live modes are exclusive")
    elif not args.offline and not args.list and not args.validate and not args.capabilities:
        raise EvalError("mode_required", "choose --offline or --trusted-live")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        if args.capabilities:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "hosts": detect_capabilities(),
                    "modes": ["offline", "trusted-live"],
                },
                0,
            )
        validate_schemas(args.root.resolve())
        validate_fixtures(args.root.resolve())
        scenarios = discover(args.corpus)
        selected = select(scenarios, args)
        if args.list:
            emit(
                {
                    "schema_version": SCHEMA_VERSION,
                    "scenarios": [
                        {"id": item["id"], "kind": item["kind"], "surface": item["surface"]}
                        for item in selected
                    ],
                },
                0,
            )
        if args.validate:
            emit(
                {"schema_version": SCHEMA_VERSION, "status": "passed", "scenarios": len(selected)},
                0,
            )
        results = [result_for(scenario, args, args.root.resolve()) for scenario in selected]
        statuses = [item["status"] for item in results]
        summary = {"schema": RESULT_SCHEMA, "status": "passed", "results": results}
        if any(status in {"failed", "blocked"} for status in statuses):
            summary["status"] = "failed"
            exit_code = 1
        elif any(status == "error" for status in statuses):
            summary["status"] = "error"
            exit_code = 4
        elif all(status == "skipped" for status in statuses):
            summary["status"] = "skipped"
            exit_code = 3
        else:
            exit_code = 0
        if args.trusted_live:
            assert args.output is not None
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical(redact(summary)) + b"\n")
        emit(summary, exit_code)
    except EvalError as error:
        emit(
            {
                "schema": RESULT_SCHEMA,
                "status": "error",
                "error": {"classification": error.code, "message": error.message},
            },
            error.exit_code,
        )


if __name__ == "__main__":
    main()
