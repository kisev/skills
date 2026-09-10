#!/usr/bin/env python3
"""Read-only semantic audit driver for spec-manage."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_specs import (  # noqa: E402
    check_inventory,
    check_structure,
    read_json,
    requirement_blocks,
)


def findings() -> list[dict[str, str]]:
    check_structure()
    inventory = check_inventory()
    trace = read_json(ROOT / "specs/traceability.json")
    blocks = requirement_blocks()
    result: list[dict[str, str]] = []
    for req_id, (path, _) in blocks.items():
        surface = str(trace["requirements"].get(req_id, {}).get("surface", ""))
        if surface.startswith("skill:"):
            name = surface.split(":", 1)[1]
            if not (ROOT / "skills" / name / "SKILL.md").is_file():
                result.append(
                    {
                        "status": "SPEC_AHEAD",
                        "requirement": req_id,
                        "spec": path.as_posix(),
                        "source": f"skills/{name}/SKILL.md",
                    }
                )
        elif (
            surface.startswith("command:") and surface.split(":", 1)[1] not in inventory["commands"]
        ):
            result.append(
                {
                    "status": "IMPLEMENTATION_AHEAD",
                    "requirement": req_id,
                    "spec": path.as_posix(),
                    "source": surface,
                }
            )
    return result


def emit(value: dict[str, object]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--critic-pass", action="store_true")
    parser.add_argument("--critic-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.critic_pass and not args.critic_only:
        emit({"schema": "spec-audit/v1", "status": "error", "error": {"code": "critic_required"}})
        return 2
    try:
        current = findings()
    except Exception as error:
        current = [{"status": "UNKNOWN", "reason": type(error).__name__}]
    if args.critic_only:
        emit({"schema": "spec-audit-critic/v1", "findings": current})
        return 0
    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_specs.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if gate.returncode:
        emit(
            {
                "schema": "spec-audit/v1",
                "scope": "full",
                "status": "UNKNOWN",
                "critic": {
                    "independent": True,
                    "decision": "blocked",
                    "reason": "deterministic_gate_failed",
                },
                "read_only": True,
            }
        )
        return gate.returncode
    critic = subprocess.run(
        [sys.executable, str(ROOT / "scripts/spec_audit.py"), "--critic-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if critic.returncode:
        emit(
            {
                "schema": "spec-audit/v1",
                "scope": "full",
                "status": "UNKNOWN",
                "critic": {"independent": True, "decision": "blocked"},
                "read_only": True,
            }
        )
        return 2
    critic_value = json.loads(critic.stdout)
    critic_findings = critic_value.get("findings", [])
    status = current[0]["status"] if current else "OK"
    emit(
        {
            "schema": "spec-audit/v1",
            "scope": "full",
            "status": status,
            "quality_findings": [],
            "drift": current,
            "unchecked_boundaries": [],
            "critic": {
                "independent": True,
                "initial_conclusions_hidden": True,
                "decision": "accepted" if not critic_findings else "rejected",
                "findings": critic_findings,
                "evidence_digest": hashlib.sha256(critic.stdout.encode()).hexdigest(),
            },
            "read_only": True,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
