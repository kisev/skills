"""Read-only Goal Mode authorization conformance validator.

Exit 0 reports capabilities or passing assertions, exit 1 reports failed
assertions, and exit 2 reports an invalid command, target, or JSON input.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from typing import Any, NoReturn


TRUSTED_ORIGINS = {"trusted-host", "trusted-system"}
OBJECTIVE_KEYS = {"accepted", "actions", "digest", "id", "revision"}
ACTION_KEYS = {"action", "boundary"}
DECISION_KEYS = {"authorized", "reason", "requires_confirmation"}
CASE_KEYS = {
    "continuation",
    "expected",
    "goal_mode",
    "id",
    "later_additions",
    "later_origin",
    "mutate_objective",
    "objective",
    "origin",
    "pending_gate",
    "request",
}
CAPABILITIES = {
    "schema": "goal-authorization-capabilities/v1",
    "version": 1,
    "read_only": True,
    "commands": {"verify": {"input": "stdin-json", "output": "goal-authorization-result/v1"}},
    "exit_codes": {
        "0": "capabilities reported or all assertions passed",
        "1": "one or more assertions failed",
        "2": "invalid command, target, or JSON input",
    },
}


def _error_json(message: str) -> str:
    return json.dumps(
        {"schema": "goal-authorization-error/v1", "error": message},
        sort_keys=True,
        separators=(",", ":"),
    )


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(_error_json(message))
        raise SystemExit(2)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def objective_digest(objective: dict[str, Any]) -> str:
    payload = {key: objective[key] for key in ("accepted", "actions", "id", "revision")}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _exact_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _valid_action(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == ACTION_KEYS
        and _exact_text(value.get("action"))
        and _exact_text(value.get("boundary"))
    )


def _objective_error(objective: Any) -> str | None:
    if not isinstance(objective, dict) or set(objective) != OBJECTIVE_KEYS:
        return "objective-invalid"
    revision = objective.get("revision")
    if (
        objective.get("accepted") is not True
        or not _exact_text(objective.get("id"))
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not isinstance(objective.get("actions"), list)
        or not objective["actions"]
        or not all(_valid_action(action) for action in objective["actions"])
        or len({_canonical(action) for action in objective["actions"]}) != len(objective["actions"])
    ):
        return "objective-invalid"
    digest = objective.get("digest")
    if not isinstance(digest, str) or digest != objective_digest(objective):
        return "objective-digest-mismatch"
    return None


def decide(signal: Any, request: Any, context: Any = None) -> dict[str, Any]:
    pending_gate = context.get("pending_gate") if isinstance(context, dict) else None
    if not isinstance(signal, dict) or signal.get("origin") not in TRUSTED_ORIGINS:
        reason = "untrusted-signal-origin"
    elif signal.get("goal_mode") != "active":
        reason = "goal-mode-inactive"
    elif error := _objective_error(signal.get("accepted_objective")):
        reason = error
    elif not _valid_action(request):
        reason = "ambiguous-action-boundary"
    elif pending_gate is not None and not _valid_action(pending_gate):
        reason = "pending-gate-invalid"
    elif pending_gate == request:
        reason = "pending-confirmation"
    elif request not in signal["accepted_objective"]["actions"]:
        reason = "out-of-objective"
    else:
        return {
            "authorized": True,
            "requires_confirmation": False,
            "reason": "explicit-goal-action",
        }
    return {"authorized": False, "requires_confirmation": True, "reason": reason}


def verify_fixture(fixture: Any, target: str) -> dict[str, Any]:
    if target != "goal-authorization-v1" or not isinstance(fixture, dict):
        raise ValueError("unsupported verification target")
    objectives = fixture.get("objectives")
    cases = fixture.get("cases")
    if not isinstance(objectives, dict) or not isinstance(cases, list) or not cases:
        raise ValueError("objectives and cases are required")
    if not objectives or any(
        not _exact_text(name) or _objective_error(objective) is not None
        for name, objective in objectives.items()
    ):
        raise ValueError("objectives must contain valid accepted objective records")
    assertions = []
    seen = set()
    for case in cases:
        if (
            not isinstance(case, dict)
            or not {"expected", "id", "objective", "origin", "request"} <= set(case)
            or not set(case) <= CASE_KEYS
            or not _exact_text(case.get("id"))
            or case["id"] in seen
        ):
            raise ValueError("case identity must be unique")
        seen.add(case["id"])
        objective_name = case.get("objective")
        expected = case.get("expected")
        later_additions = case.get("later_additions")
        if (
            not _exact_text(case.get("origin"))
            or not _exact_text(objective_name)
            or objective_name not in objectives
            or not isinstance(case.get("request"), dict)
            or not isinstance(expected, dict)
            or set(expected) != DECISION_KEYS
            or not isinstance(expected.get("authorized"), bool)
            or not isinstance(expected.get("requires_confirmation"), bool)
            or not _exact_text(expected.get("reason"))
            or ("goal_mode" in case and not _exact_text(case.get("goal_mode")))
            or ("continuation" in case and not _exact_text(case.get("continuation")))
            or ("later_origin" in case and not _exact_text(case.get("later_origin")))
            or (
                "later_additions" in case
                and (
                    not isinstance(later_additions, list)
                    or not all(_valid_action(action) for action in later_additions)
                )
            )
            or ("pending_gate" in case and not _valid_action(case.get("pending_gate")))
            or (
                "mutate_objective" in case
                and (
                    case.get("mutate_objective") != "append-later-additions"
                    or not isinstance(later_additions, list)
                )
            )
        ):
            raise ValueError(f"case {case['id']} is structurally invalid")
        assert isinstance(objective_name, str)
        objective = copy.deepcopy(objectives[objective_name])
        if case.get("mutate_objective") == "append-later-additions":
            objective["actions"].extend(copy.deepcopy(later_additions))
        signal = {
            "origin": case.get("origin"),
            "goal_mode": case.get("goal_mode", "active"),
            "accepted_objective": objective,
        }
        context = {
            key: copy.deepcopy(case[key])
            for key in ("continuation", "later_additions", "later_origin", "pending_gate")
            if key in case
        }
        actual = decide(signal, case.get("request"), context)
        assertions.append(
            {
                "id": f"policy:{case['id']}",
                "status": "passed" if actual == case.get("expected") else "failed",
            }
        )
    return {
        "schema": "goal-authorization-result/v1",
        "assertions": assertions,
        "trust_boundary": "origin classification is authenticated by the host, not this validator",
    }


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser()
    parser.add_argument("command", nargs="?")
    parser.add_argument("--target")
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args(argv)
    if args.capabilities:
        if args.command is not None or args.target is not None:
            print(_error_json("--capabilities cannot be combined with a command"))
            return 2
        print(json.dumps(CAPABILITIES, sort_keys=True, separators=(",", ":")))
        return 0
    if args.command != "verify" or args.target is None:
        print(_error_json("verify and --target are required"))
        return 2
    try:
        result = verify_fixture(json.load(sys.stdin), args.target)
    except (json.JSONDecodeError, ValueError) as error:
        print(_error_json(str(error)))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if all(item["status"] == "passed" for item in result["assertions"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
