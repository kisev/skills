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
OFFLINE_RUNNERS = {
    "assertions-v1": {("docs-prepare", "scripts/goal_authorization.py")},
    "portable-gitlab-v2": {("code-review", "scripts/review_mr.py")},
}
LEGACY_GITLAB_V2_DIGEST = "60641989df03379e5a79a39dec59588b7e359f7424ca985b74b08265e8b52979"
LEGACY_GITLAB_V2_RUNNER = {
    "skill": "code-review",
    "script": "scripts/review_mr.py",
    "target": "https://gitlab.example/group/project/-/merge_requests/7",
}
PUBLIC_SURFACES = ROOT / "evals" / "contracts" / "public-surfaces.json"
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
    if (
        path.is_absolute()
        or ".." in path.parts
        or not value
        or "\\" in value
        or path.as_posix() != value
    ):
        raise EvalError("sandbox_escape", "scenario path escapes the repository sandbox")
    return path


def is_legacy_gitlab_v2(scenario: dict[str, Any], runner: dict[str, Any]) -> bool:
    fixture = scenario.get("input", {}).get("fixture")
    return (
        scenario.get("schema") == SCENARIO_SCHEMA
        and scenario.get("id") == "gitlab.evidence-contract"
        and scenario.get("revision") == 2
        and scenario.get("digest") == LEGACY_GITLAB_V2_DIGEST
        and scenario_digest(scenario) == LEGACY_GITLAB_V2_DIGEST
        and fixture == {"selected": []}
        and runner == LEGACY_GITLAB_V2_RUNNER
    )


def offline_runner_config(
    scenario: dict[str, Any], filename: str
) -> tuple[str, str, str, str] | None:
    runner = scenario["input"].get("offline_runner")
    if runner is None:
        return None
    required = {"protocol", "skill", "script", "target"}
    legacy = {"skill", "script", "target"}
    if not isinstance(runner, dict):
        raise EvalError("malformed_scenario", f"{filename}: offline_runner fields are invalid")
    fields = frozenset(runner)
    if fields not in {frozenset(required), frozenset(legacy)}:
        raise EvalError("malformed_scenario", f"{filename}: offline_runner fields are invalid")
    skill, script, target = runner.get("skill"), runner.get("script"), runner.get("target")
    protocol = runner.get("protocol")
    legacy_gitlab = False
    if fields == frozenset(legacy):
        legacy_gitlab = is_legacy_gitlab_v2(scenario, runner)
        if not legacy_gitlab:
            raise EvalError(
                "unsupported_runner_protocol",
                f"{filename}: legacy offline_runner is not allowlisted",
            )
        protocol = "portable-gitlab-v2"
    if not isinstance(protocol, str) or protocol not in OFFLINE_RUNNERS:
        raise EvalError(
            "unsupported_runner_protocol", f"{filename}: offline_runner protocol is unsupported"
        )
    if not all(isinstance(value, str) and value for value in (skill, script, target)):
        raise EvalError("malformed_scenario", f"{filename}: offline_runner values are invalid")
    assert isinstance(skill, str)
    assert isinstance(script, str)
    assert isinstance(target, str)
    skill_path = safe_relative(skill)
    script_path = safe_relative(script)
    if len(skill_path.parts) != 1 or script_path == Path("."):
        raise EvalError("sandbox_escape", f"{filename}: offline_runner path is unsafe")
    fixture = scenario["input"].get("fixture")
    selected = fixture.get("selected") if isinstance(fixture, dict) else None
    if legacy_gitlab:
        selected = [f"skill:{skill}"]
    if not isinstance(selected, list) or f"skill:{skill}" not in selected:
        raise EvalError("unselected_runner", f"{filename}: offline_runner skill is not selected")
    if (skill, script) not in OFFLINE_RUNNERS[protocol]:
        raise EvalError("unsupported_runner", f"{filename}: offline_runner is not allowlisted")
    return protocol, skill, script, target


def materialized_runner_path(root: Path, skill: str, script: str) -> Path:
    current = root
    for part in (".build", "skills", skill, *safe_relative(script).parts):
        current /= part
        if current.is_symlink():
            raise EvalError("sandbox_escape", "offline_runner path contains a symlink")
    if not current.is_file():
        raise EvalError("missing_runner", "offline_runner is not materialized")
    return current


def run_with_deadline(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    deadline: float,
    timeout_seconds: float,
    input_value: str | None = None,
) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EvalError(
            "offline_runner_timeout",
            f"offline_runner exceeded timeout_seconds={timeout_seconds:g}",
            4,
        )
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_value,
            capture_output=True,
            text=True,
            check=False,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired as error:
        raise EvalError(
            "offline_runner_timeout",
            f"offline_runner exceeded timeout_seconds={timeout_seconds:g}",
            4,
        ) from error


def scenario_digest(scenario: dict[str, Any]) -> str:
    content = {key: value for key, value in scenario.items() if key != "digest"}
    return digest(content)


def case_outcome_contract(scenario: dict[str, Any], filename: str) -> list[dict[str, Any]] | None:
    expected = scenario["expected"].get("case_outcomes")
    if expected is None:
        return None
    if not isinstance(expected, list) or not expected:
        raise EvalError("malformed_scenario", f"{filename}: case_outcomes must be a nonempty list")
    identifiers: list[str] = []
    for item in expected:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "outcome"}
            or not isinstance(item.get("id"), str)
            or not item["id"]
        ):
            raise EvalError("malformed_scenario", f"{filename}: case_outcomes entries are invalid")
        identifiers.append(item["id"])
    if len(identifiers) != len(set(identifiers)):
        raise EvalError("malformed_scenario", f"{filename}: case_outcomes IDs must be unique")
    fixture = scenario["input"].get("fixture")
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if not isinstance(cases, list) or not all(
        isinstance(item, dict) and isinstance(item.get("id"), str) for item in cases
    ):
        raise EvalError("malformed_scenario", f"{filename}: case_outcomes require fixture cases")
    case_ids = [item["id"] for item in cases]
    if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(identifiers):
        raise EvalError(
            "malformed_scenario", f"{filename}: fixture and expected case IDs must match"
        )
    return expected


def validate_scenario(scenario: dict[str, Any], filename: str) -> list[str]:
    required = {
        "schema",
        "id",
        "revision",
        "locale",
        "pair_id",
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
    locale = scenario["locale"]
    pair_id = scenario["pair_id"]
    if locale not in {"ru", "en", "neutral"}:
        raise EvalError("malformed_scenario", f"{filename}: locale is invalid")
    if scenario["kind"] == "deterministic":
        if locale != "neutral" or pair_id is not None:
            raise EvalError(
                "malformed_scenario",
                f"{filename}: deterministic scenarios are neutral and unpaired",
            )
    elif locale not in {"ru", "en"} or not isinstance(pair_id, str) or not pair_id:
        raise EvalError(
            "malformed_scenario", f"{filename}: user-facing scenarios require locale and pair_id"
        )
    if scenario["kind"] not in {"deterministic", "trigger", "near-miss", "golden"}:
        raise EvalError("malformed_scenario", f"{filename}: kind is invalid")
    if scenario["surface"] not in {
        "skill",
        "command",
        "agent",
        "plugin",
        "package-tool",
        "infrastructure",
    }:
        raise EvalError("malformed_scenario", f"{filename}: surface is invalid")
    if scenario["host"] not in {"opencode", "codex", "any"}:
        raise EvalError("malformed_scenario", f"{filename}: host is invalid")
    if not isinstance(scenario["input"], dict) or not isinstance(scenario["expected"], dict):
        raise EvalError("malformed_scenario", f"{filename}: input and expected must be objects")
    offline_runner_config(scenario, filename)
    case_outcome_contract(scenario, filename)
    project_files = scenario["input"].get("project_files", {})
    if not isinstance(project_files, dict) or any(
        not isinstance(path, str) or not isinstance(content, str)
        for path, content in project_files.items()
    ):
        raise EvalError("malformed_scenario", f"{filename}: project_files must map paths to text")
    for path in project_files:
        safe_relative(path)
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
    pairs: dict[str, list[dict[str, Any]]] = {}
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
        if scenario.get("locale") in {"ru", "en"}:
            pairs.setdefault(scenario["pair_id"], []).append(scenario)
    if not scenarios:
        raise EvalError("missing_corpus", "scenario corpus is empty")
    for pair_id, items in pairs.items():
        if len(items) != 2 or {item["locale"] for item in items} != {"ru", "en"}:
            raise EvalError("unpaired_scenario", f"pair {pair_id}: ru/en scenarios are required")
        first, second = items
        for pair_field in ("kind", "surface", "host", "expected", "sandbox", "budgets"):
            if first[pair_field] != second[pair_field]:
                raise EvalError("scenario_pair_drift", f"pair {pair_id}: {pair_field} differs")
        if first["invariants"] != second["invariants"]:
            raise EvalError("scenario_pair_drift", f"pair {pair_id}: invariants differ")
    return scenarios


def validate_public_surface_inventory(root: Path, scenarios: list[dict[str, Any]]) -> None:
    """Keep deterministic coverage tied to the public catalog, not a second trace system."""
    try:
        inventory = json.loads(
            (root / "evals" / "contracts" / "public-surfaces.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise EvalError(
            "stale_package_inventory", f"cannot read public surface inventory: {error}"
        ) from error
    if not isinstance(inventory, dict) or inventory.get("version") != 1:
        raise EvalError("stale_package_inventory", "public surface inventory version is invalid")
    expected = {
        "skill": set(inventory.get("skills", [])),
        "command": set(inventory.get("commands", [])),
        "agent": set(inventory.get("agents", [])),
        "plugin": set(inventory.get("plugins", [])),
        "package-tool": set(inventory.get("package_tools", [])),
        "infrastructure": set(inventory.get("infrastructure", [])),
    }
    if any(
        not values or any(not isinstance(value, str) for value in values)
        for values in expected.values()
    ):
        raise EvalError(
            "stale_package_inventory", "public surface inventory contains invalid entries"
        )
    covered: dict[str, set[str]] = {surface: set() for surface in expected}
    for scenario in scenarios:
        selected = scenario["expected"].get("selected", [])
        for value in selected:
            if not isinstance(value, str) or ":" not in value:
                continue
            surface, name = value.split(":", 1)
            if surface in covered:
                covered[surface].add(name)
    for surface, names in expected.items():
        if covered[surface] != names:
            raise EvalError(
                "surface_coverage_drift", f"{surface} coverage does not match inventory"
            )
    if (
        len(expected["skill"]) != 38
        or len(expected["command"]) != 39
        or len(expected["agent"]) != 6
        or len(expected["plugin"]) != 3
        or len(expected["package-tool"]) != 1
    ):
        raise EvalError("stale_package_inventory", "public surface counts do not match stage 20")
    skill_scenarios = [
        item
        for item in scenarios
        if item["surface"] == "skill" and item["kind"] in {"trigger", "near-miss"}
    ]
    if len(skill_scenarios) < 152:
        raise EvalError(
            "skill_corpus_incomplete", "skill trigger/near-miss corpus is below 152 scenarios"
        )
    for name in expected["skill"]:
        items = [
            item
            for item in skill_scenarios
            if f"skill:{name}" in item["expected"].get("selected", [])
            or f"skill:{name}" in item["expected"].get("not_selected", [])
        ]
        if len(items) < 4:
            raise EvalError(
                "skill_corpus_incomplete", f"skill {name} lacks the four bilingual scenarios"
            )


def validate_compatibility_inventory(root: Path = ROOT) -> None:
    compatibility = root / "evals" / "contracts" / "opencode-compatibility.json"
    try:
        value = json.loads(compatibility.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvalError(
            "stale_package_inventory", f"cannot read compatibility inventory: {error}"
        ) from error
    if (
        not isinstance(value, dict)
        or value.get("schema") != "opencode-compatibility/v1"
        or value.get("range") != ">=1.18.29 <1.19.0"
        or value.get("versions") != ["1.18.29", "1.18.31"]
        or value.get("credentials") is not False
        or value.get("network") is not False
    ):
        raise EvalError("stale_package_inventory", "OpenCode compatibility inventory is stale")


def validate_negative_fixtures(root: Path) -> None:
    fixtures = root / "evals" / "negative"
    expected_codes = {
        "duplicate-id": "duplicate_scenario",
        "bad-digest": "digest_drift",
        "missing-pair": "unpaired_scenario",
        "unknown-surface": "unknown_surface",
        "path-escape": "sandbox_escape",
        "malformed-invariant": "malformed_scenario",
        "malformed-result": "malformed_result",
        "missing-budgets": "malformed_scenario",
        "secret-leakage": "secret_fixture",
        "unsupported-host": "unsupported_host",
        "stale-package-inventory": "stale_package_inventory",
    }
    for name, code in expected_codes.items():
        path = fixtures / f"{name}.json"
        try:
            value = load_json(path)
            if value.get("case") != name:
                raise EvalError("negative_fixture_drift", f"{name} has the wrong case")
            if name == "duplicate-id":
                ids = value.get("ids")
                if not isinstance(ids, list) or len(ids) != 2 or ids[0] != ids[1]:
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("duplicate_scenario", name)
            if name == "bad-digest":
                validate_scenario(value, path.name)
            elif name == "missing-pair":
                locales = value.get("locales")
                if not isinstance(locales, list) or set(locales) == {"ru", "en"}:
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("unpaired_scenario", name)
            elif name == "secret-leakage":
                if not contains_secret(value):
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("secret_fixture", name)
            elif name == "path-escape":
                safe_relative(value.get("path", "../escape"))
            elif name == "unknown-surface":
                if value.get("surface") not in {
                    "skill",
                    "command",
                    "agent",
                    "plugin",
                    "package-tool",
                    "infrastructure",
                }:
                    raise EvalError("unknown_surface", name)
            elif name == "unsupported-host":
                if value.get("host") not in {"opencode", "codex", "any"}:
                    raise EvalError("unsupported_host", name)
            elif name == "malformed-invariant":
                if isinstance(value.get("invariants"), list) and all(
                    isinstance(item, dict) for item in value["invariants"]
                ):
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("malformed_scenario", name)
            elif name == "missing-budgets":
                budgets = value.get("budgets")
                if isinstance(budgets, dict) and all(
                    key in budgets for key in ("timeout_seconds", "max_tokens", "max_cost")
                ):
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("malformed_scenario", name)
            elif name == "malformed-result":
                result = value.get("result")
                if not isinstance(result, dict) or not isinstance(result.get("assertions"), list):
                    raise EvalError("malformed_result", name)
                raise EvalError("negative_fixture_not_rejected", name)
            elif name == "stale-package-inventory":
                if value.get("version") == 1:
                    raise EvalError("negative_fixture_not_rejected", name)
                raise EvalError("stale_package_inventory", name)
            else:
                raise EvalError(code, name)
        except EvalError as error:
            if error.code != code:
                raise EvalError(
                    "negative_fixture_drift", f"{name} returned {error.code}, expected {code}"
                ) from error
            continue
        raise EvalError("negative_fixture_not_rejected", f"{name} was accepted")


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
    scenario: dict[str, Any], observation: dict[str, Any], *, behavioral: bool
) -> list[dict[str, Any]]:
    selected = {str(item) for item in observation.get("selected", [])}
    result: list[dict[str, Any]] = []
    for name in sorted(str(item) for item in scenario["expected"].get("selected", [])):
        result.append(
            {"id": f"selected:{name}", "status": "passed" if name in selected else "failed"}
        )
    for name in sorted(str(item) for item in scenario["expected"].get("not_selected", [])):
        result.append(
            {"id": f"not_selected:{name}", "status": "passed" if name not in selected else "failed"}
        )
    expected_cases = case_outcome_contract(scenario, str(scenario.get("id", "scenario")))
    if expected_cases is not None:
        if not behavioral:
            result.append({"id": "case-outcomes:trusted-live-required", "status": "not_observed"})
        else:
            observed_cases = {
                item["id"]: item["outcome"] for item in observation.get("case_outcomes", [])
            }
            expected_ids = {item["id"] for item in expected_cases}
            for item in expected_cases:
                result.append(
                    {
                        "id": f"case:{item['id']}",
                        "status": "passed"
                        if observed_cases.get(item["id"], object()) == item["outcome"]
                        else "failed",
                    }
                )
            for identifier in sorted(set(observed_cases) - expected_ids):
                result.append({"id": f"case:extra:{identifier}", "status": "failed"})
    return result


def offline_observation(scenario: dict[str, Any], root: Path) -> dict[str, Any]:
    """Run explicitly declared portable runner checks without a host or network."""
    timeout_seconds = float(scenario["budgets"]["timeout_seconds"])
    deadline = time.monotonic() + timeout_seconds
    fixture = scenario["input"].get("fixture", {})
    selected = fixture.get("selected", []) if isinstance(fixture, dict) else []
    config = offline_runner_config(scenario, str(scenario.get("id", "scenario")))
    if config is None:
        return {"selected": selected, "usage": {"telemetry": "not-applicable"}}
    protocol, skill, script, target = config
    executable = materialized_runner_path(root, skill, script)
    if protocol == "assertions-v1":
        with tempfile.TemporaryDirectory(prefix="skills-assertions-eval-") as temporary:
            sandbox = Path(temporary)
            process = run_with_deadline(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(executable),
                    "verify",
                    "--target",
                    target,
                ],
                cwd=sandbox,
                env=isolated_environment(sandbox),
                input_value=json.dumps(fixture, sort_keys=True, separators=(",", ":")),
                deadline=deadline,
                timeout_seconds=timeout_seconds,
            )
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise EvalError(
                "malformed_runner_output", "assertions runner returned invalid JSON"
            ) from error
        raw_assertions = output.get("assertions") if isinstance(output, dict) else None
        if not isinstance(raw_assertions, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("status") in {"passed", "failed"}
            for item in raw_assertions
        ):
            raise EvalError(
                "malformed_runner_output", "assertions runner returned invalid assertions"
            )
        return {
            "selected": selected,
            "usage": {"telemetry": "not-applicable"},
            "runner_assertions": [
                {"id": "runner:exit", "status": "passed" if process.returncode == 0 else "failed"},
                *raw_assertions,
            ],
        }
    with tempfile.TemporaryDirectory(prefix="skills-gitlab-eval-") as temporary:
        sandbox = Path(temporary)
        repository = sandbox / "repository"
        repository.mkdir()
        for arguments in (
            ("init", "-q"),
            ("config", "commit.gpgsign", "false"),
            ("config", "user.email", "reviewer@example.invalid"),
            ("config", "user.name", "Example Reviewer"),
        ):
            subprocess.run(["git", *arguments], cwd=repository, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-qm", "review fixture"],
            cwd=repository,
            check=True,
        )
        review_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip()
        log = sandbox / "glab.jsonl"
        state = sandbox / "state"
        state.write_text("fresh", encoding="utf-8")
        glab = sandbox / "glab"
        glab.write_text(
            f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path
endpoint = sys.argv[-1]
Path(os.environ["FAKE_GLAB_LOG"]).open("a", encoding="utf-8").write(json.dumps(sys.argv[1:]) + "\\n")
changed = Path(os.environ["FAKE_GLAB_STATE"]).read_text(encoding="utf-8") == "changed"
review_sha = os.environ["FAKE_REVIEW_SHA"]
if endpoint.startswith("projects/group%2Fproject"):
    value = {{"id": 19}}
elif endpoint == "projects/19/merge_requests/7":
    value = {{"iid": 7, "title": "Review fixture", "description": "Fixture", "source_branch": "feature", "target_branch": "main", "web_url": "https://gitlab.example/group/project/-/merge_requests/7", "author": {{"username": "author"}}, "state": "opened", "labels": [], "updated_at": "changed" if changed else "fresh", "diff_refs": {{"base_sha": review_sha, "start_sha": review_sha, "head_sha": review_sha}}}}
elif endpoint == "projects/19/merge_requests/7/changes":
    value = {{"changes": [], "diff_refs": {{"base_sha": review_sha, "start_sha": review_sha, "head_sha": review_sha}}}}
elif endpoint.startswith("projects/19/merge_requests/7/commits"):
    value = [{{"id": review_sha}}]
elif endpoint.startswith("projects/19/merge_requests/7/pipelines"):
    value = [{{"id": 41, "sha": review_sha, "status": "success"}}]
elif endpoint.startswith("projects/19/pipelines/41/jobs"):
    value = [{{"id": 51, "name": "test", "stage": "test", "status": "success"}}]
elif endpoint.startswith("projects/19/pipelines/41/bridges"):
    value = []
elif endpoint == "user":
    value = {{"id": 23, "username": "reviewer"}}
else:
    value = []
print(json.dumps(value))
""",
            encoding="utf-8",
        )
        glab.chmod(0o755)
        environment = isolated_environment(sandbox)
        environment.update(
            {
                "PATH": f"{sandbox}:{environment['PATH']}",
                "FAKE_GLAB_LOG": str(log),
                "FAKE_GLAB_STATE": str(state),
                "FAKE_REVIEW_SHA": review_sha,
            }
        )
        process = run_with_deadline(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(executable),
                "prepare",
                "--url",
                target,
                "--repo-root",
                str(repository),
                "--review-mode",
                "deep",
                "--locale",
                "en",
            ],
            cwd=sandbox,
            env=environment,
            deadline=deadline,
            timeout_seconds=timeout_seconds,
        )
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            output = {}
        items = output.get("items", []) if isinstance(output, dict) else []
        review_status = "failed"
        stale_status = "failed"
        out_of_order_status = "failed"
        premature_report_status = "failed"
        if process.returncode == 0 and items and isinstance(items[0], dict):
            evidence = items[0].get("artifact_path")
            artifact_root = items[0].get("artifact_root")
            if isinstance(evidence, str) and isinstance(artifact_root, str):
                context_process = run_with_deadline(
                    [
                        sys.executable,
                        "-I",
                        "-S",
                        "-B",
                        str(executable),
                        "context",
                        "--evidence",
                        evidence,
                        "--repo-root",
                        str(repository),
                        "--review-mode",
                        "deep",
                    ],
                    cwd=sandbox,
                    env=environment,
                    deadline=deadline,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    context_output = json.loads(context_process.stdout)
                except json.JSONDecodeError:
                    context_output = {}
                context_path = (
                    context_output.get("artifact_path")
                    if isinstance(context_output, dict)
                    else None
                )
                context_digest = (
                    context_output.get("digest") if isinstance(context_output, dict) else None
                )
                if (
                    context_process.returncode == 0
                    and isinstance(context_path, str)
                    and isinstance(context_digest, str)
                ):
                    premature_finalize = run_with_deadline(
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
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    out_of_order_status = (
                        "passed" if premature_finalize.returncode == 2 else "failed"
                    )
                    premature_report = run_with_deadline(
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            str(executable),
                            "report-review",
                            "--artifact-root",
                            artifact_root,
                        ],
                        cwd=sandbox,
                        env=environment,
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    try:
                        premature_output = json.loads(premature_report.stdout)
                    except json.JSONDecodeError:
                        premature_output = {}
                    premature_report_status = (
                        "passed"
                        if premature_report.returncode == 4
                        and premature_output.get("status") == "blocked"
                        and premature_output.get("stage") == "critic_missing"
                        else "failed"
                    )
                    evidence_digest = hashlib.sha256(Path(evidence).read_bytes()).hexdigest()
                    receipt = sandbox / "receipt.json"
                    decision = sandbox / "decision.json"
                    receipt.write_text(
                        json.dumps(
                            {
                                "schema": "portable-gitlab/critic-receipt/v2",
                                "external_mutations": False,
                                "evidence_digest": evidence_digest,
                                "run_id": "critic",
                                "session_id": "critic-session",
                                "findings": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    recorded = run_with_deadline(
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            str(executable),
                            "record-artifact",
                            "--kind",
                            "critic_receipt",
                            "--evidence",
                            evidence,
                            "--input",
                            str(receipt),
                        ],
                        cwd=sandbox,
                        env=environment,
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    try:
                        recorded_output = json.loads(recorded.stdout)
                    except json.JSONDecodeError:
                        recorded_output = {}
                    recorded_path = (
                        recorded_output.get("artifact_path")
                        if isinstance(recorded_output, dict)
                        else None
                    )
                    recorded_digest = (
                        recorded_output.get("digest") if isinstance(recorded_output, dict) else None
                    )
                    finalized = run_with_deadline(
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
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    try:
                        final_output = json.loads(finalized.stdout)
                    except json.JSONDecodeError:
                        final_output = {}
                    final_path = (
                        final_output.get("artifact_path")
                        if isinstance(final_output, dict)
                        else None
                    )
                    final_digest = (
                        final_output.get("digest") if isinstance(final_output, dict) else None
                    )
                    if not (
                        recorded.returncode == 0
                        and isinstance(recorded_path, str)
                        and isinstance(recorded_digest, str)
                        and finalized.returncode == 0
                        and isinstance(final_path, str)
                        and isinstance(final_digest, str)
                    ):
                        raise EvalError(
                            "offline_runner_contract",
                            "code-review lifecycle did not reach decision_missing",
                        )
                    decision.write_text(
                        json.dumps(
                            {
                                "schema": "portable-gitlab/review-decision/v2",
                                "mode": "deep",
                                "external_mutations": False,
                                "evidence_digest": evidence_digest,
                                "finalize_digest": final_digest,
                                "context_digest": context_digest,
                                "critic_receipt_digest": recorded_digest,
                                "verdict": "ready",
                                "blocking_findings": False,
                                "blocking_finding_ids": [],
                                "owner_decision_reasons": [],
                                "ci_job_assessments": [],
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
                        "--context",
                        context_path,
                        "--critic-receipt",
                        recorded_path,
                        "--finalize-report",
                        final_path,
                        "--mode",
                        "deep",
                    ]
                    review_process = run_with_deadline(
                        review_command,
                        cwd=sandbox,
                        env=environment,
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    try:
                        review_output = json.loads(review_process.stdout)
                    except json.JSONDecodeError:
                        review_output = {}
                    decision_path = (
                        review_output.get("artifact_path")
                        if isinstance(review_output, dict)
                        else None
                    )
                    content = sandbox / "content.json"
                    content.write_text(
                        json.dumps(
                            {
                                "locale": "en",
                                "chat_assessment": {
                                    "necessity": {
                                        "status": "supported",
                                        "rationale": "The fixture change is intentional.",
                                    },
                                    "relevance": {
                                        "status": "current",
                                        "rationale": "The exact head is current.",
                                    },
                                    "change": "The fixture preserves its reviewed behavior.",
                                },
                                "summary": "The fixture preserves its reviewed behavior.",
                                "architecture_assessment": "Ownership remains unchanged.",
                                "semver_impact": "none",
                                "semver_rationale": "No versioned behavior changes.",
                                "semver_assessment": {
                                    "mode": "target_fallback",
                                    "policy": "The fixture has no established release policy.",
                                    "sources": ["Fixture repository and empty release catalog"],
                                    "baseline": None,
                                    "target_branch": "main",
                                    "target_sha": review_sha,
                                    "target_revision": "mr_snapshot",
                                    "fallback_reason": "No published release could be established.",
                                    "release_impact": None,
                                    "release_rationale": None,
                                },
                                "mr_metadata_assessment": {
                                    field: {
                                        "status": "ok",
                                        "rationale": f"The {field} fixture is sufficient.",
                                        "recommendation": None,
                                    }
                                    for field in (
                                        "title",
                                        "description",
                                        "labels",
                                        "workflow_state",
                                        "overall",
                                    )
                                },
                                "label_assessments": [],
                                "checks": ["Checked the exact fixture head."],
                                "findings": [],
                                "finding_publications": [],
                                "previous_finding_assessments": [],
                                "issue_templates": [],
                                "recommended_issues": [],
                                "rejected_candidates": [],
                                "rejected_candidate_assessments": [],
                                "thread_decisions": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    scaffold = (
                        run_with_deadline(
                            [
                                sys.executable,
                                "-I",
                                "-S",
                                "-B",
                                str(executable),
                                "scaffold-review",
                                "--evidence",
                                evidence,
                                "--context",
                                context_path,
                                "--decision",
                                decision_path,
                                "--content",
                                str(content),
                            ],
                            cwd=sandbox,
                            env=environment,
                            deadline=deadline,
                            timeout_seconds=timeout_seconds,
                        )
                        if review_process.returncode == 0 and isinstance(decision_path, str)
                        else None
                    )
                    report = (
                        run_with_deadline(
                            [
                                sys.executable,
                                "-I",
                                "-S",
                                "-B",
                                str(executable),
                                "report-review",
                                "--artifact-root",
                                artifact_root,
                            ],
                            cwd=sandbox,
                            env=environment,
                            deadline=deadline,
                            timeout_seconds=timeout_seconds,
                        )
                        if scaffold is not None and scaffold.returncode == 0
                        else None
                    )
                    try:
                        report_output = json.loads(report.stdout) if report is not None else {}
                    except json.JSONDecodeError:
                        report_output = {}
                    report_chat = report_output.get("chat")
                    report_plan = report_output.get("publication_plan_path")
                    review_status = (
                        "passed"
                        if report is not None
                        and report.returncode == 0
                        and report_output.get("status") == "ok"
                        and isinstance(report_chat, str)
                        and report_chat.startswith("### MR assessment")
                        and "No findings." in report_chat
                        and "<!-- code-review:" not in report_chat
                        and isinstance(report_plan, str)
                        and Path(report_plan).is_absolute()
                        else "failed"
                    )
                    state.write_text("changed", encoding="utf-8")
                    refreshed_prepare = run_with_deadline(
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            str(executable),
                            "prepare",
                            "--url",
                            target,
                        ],
                        cwd=sandbox,
                        env=environment,
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    stale_process = run_with_deadline(
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            str(executable),
                            "report-review",
                            "--artifact-root",
                            artifact_root,
                        ],
                        cwd=sandbox,
                        env=environment,
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                    try:
                        stale_output = json.loads(stale_process.stdout)
                    except json.JSONDecodeError:
                        stale_output = {}
                    stale_status = (
                        "passed"
                        if refreshed_prepare.returncode == 0
                        and stale_process.returncode == 4
                        and stale_output.get("status") == "blocked"
                        and stale_output.get("stage") == "stale"
                        else "failed"
                    )
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assertions = [
            {"id": "runner:json", "status": "passed" if isinstance(output, dict) else "failed"},
            {"id": "runner:exit", "status": "passed" if process.returncode == 0 else "failed"},
            {
                "id": "runner:exact-sha",
                "status": "passed"
                if items and items[0].get("head_sha") == review_sha
                else "failed",
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
            {"id": "runner:critic-final-report", "status": review_status},
            {"id": "runner:out-of-order-finalize", "status": out_of_order_status},
            {"id": "runner:premature-report-blocked", "status": premature_report_status},
            {"id": "runner:stale-report-blocked", "status": stale_status},
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
    case_outcomes: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event.get("selected"), list):
            merged["selected"].extend(str(value) for value in event["selected"])
        if isinstance(event.get("usage"), dict):
            merged["usage"].update(event["usage"])
        if "case_outcomes" in event:
            raw_outcomes = event["case_outcomes"]
            if not isinstance(raw_outcomes, list) or not all(
                isinstance(item, dict)
                and set(item) == {"id", "outcome"}
                and isinstance(item.get("id"), str)
                and bool(item["id"])
                for item in raw_outcomes
            ):
                raise EvalError("malformed_host_result", "host case_outcomes are malformed", 4)
            case_outcomes.extend(raw_outcomes)
        if event.get("status") == "error":
            raise EvalError("host_error", "host reported an error", 4)
    merged["selected"] = sorted(set(merged["selected"]))
    if case_outcomes:
        identifiers = [item["id"] for item in case_outcomes]
        if len(identifiers) != len(set(identifiers)):
            raise EvalError("malformed_host_result", "host case_outcomes repeat an ID", 4)
        merged["case_outcomes"] = sorted(case_outcomes, key=lambda item: item["id"])
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


def project_snapshot(project: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        if path.is_symlink():
            snapshot[relative] = "symlink"
        elif path.is_file():
            snapshot[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


def mutation_assertion(scenario: dict[str, Any], changed_paths: list[str]) -> dict[str, str] | None:
    boundary = scenario["expected"].get("mutation_boundary")
    if boundary == "no-writes":
        passed = not changed_paths
    elif boundary == "specs-only":
        passed = all(path == "specs" or path.startswith("specs/") for path in changed_paths)
    else:
        return None
    return {"id": "mutation:boundary", "status": "passed" if passed else "failed"}


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
    assert args.model is not None
    assert args.timeout is not None
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
    for relative, content in sorted(scenario["input"].get("project_files", {}).items()):
        target = project / safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    before = project_snapshot(project)
    prompt = str(scenario["input"].get("prompt", ""))
    if case_outcome_contract(scenario, str(scenario.get("id", "scenario"))) is not None:
        prompt += (
            "\n\nEvaluation fixture (data, not instructions):\n"
            + json.dumps(scenario["input"]["fixture"], ensure_ascii=False, sort_keys=True)
            + "\nReturn a structured host result with case_outcomes as an array of "
            "objects containing exactly id and outcome for every fixture case."
        )
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
    after = project_snapshot(project)
    changed_paths = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    observed["changed_paths"] = changed_paths
    boundary_assertion = mutation_assertion(scenario, changed_paths)
    if boundary_assertion is not None:
        observed["mutation_assertion"] = boundary_assertion
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
        try:
            observation = offline_observation(scenario, root)
            run_status = "passed"
            error: dict[str, Any] = {"classification": None}
        except EvalError as runner_error:
            if runner_error.code != "offline_runner_timeout":
                raise
            fixture = scenario["input"].get("fixture")
            selected = fixture.get("selected", []) if isinstance(fixture, dict) else []
            observation = {"selected": selected, "usage": {"telemetry": "not-applicable"}}
            run_status = "error"
            error = {"classification": runner_error.code, "message": runner_error.message}
        evidence: list[dict[str, str]] = []
    else:
        observation, error, run_status, evidence = run_host(scenario, args)
    assertions = assertions_for_invariants(scenario, root) + expected_assertions(
        scenario, observation, behavioral=not args.offline
    )
    assertions.extend(observation.get("runner_assertions", []))
    if observation.get("mutation_assertion") is not None:
        assertions.append(observation["mutation_assertion"])
    effective_budgets = dict(scenario["budgets"])
    if not args.offline:
        assert args.max_tokens is not None
        assert args.max_cost is not None
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
        "locale": scenario.get("locale", "neutral"),
        "pair_id": scenario.get("pair_id"),
        "scenario_digest": scenario["digest"],
        "host": args.host if not args.offline else "offline",
        "host_version": observation.get("host_version", "unavailable"),
        "adapter": ADAPTER_PROTOCOLS.get(args.host, "offline/v1")
        if not args.offline
        else "offline/v1",
        "adapter_version": 1,
        "model": args.model if not args.offline else None,
        "model_version": args.model if not args.offline else None,
        "observation_mode": "hostless-contract" if args.offline else "trusted-live",
        "status": run_status,
        "assertions": assertions,
        "started_at": int(started_at),
        "duration_ms": int((time.time() - started_at) * 1000),
        "usage": observation.get("usage", {"telemetry": "incomplete"}),
        "evidence": evidence,
        "case_outcomes": observation.get("case_outcomes", []),
        "changed_paths": observation.get("changed_paths", []),
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
    parser.add_argument(
        "--surface",
        choices=("skill", "command", "agent", "plugin", "package-tool", "infrastructure"),
    )
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
        validate_public_surface_inventory(args.root.resolve(), scenarios)
        validate_compatibility_inventory(args.root.resolve())
        validate_negative_fixtures(args.root.resolve())
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
