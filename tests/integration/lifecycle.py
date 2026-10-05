#!/usr/bin/env python3
"""Explicit, nondestructive lifecycle checks for the single development environment."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("dev_lifecycle_environment", ROOT / "dev/env.py")
assert SPEC is not None and SPEC.loader is not None
dev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dev)


def snapshot(service: str, stand: Any) -> dict[str, str]:
    if service == "gitlab":
        return cast(
            "dict[str, str]",
            dev.common.load(
                "dev_gitlab_retention",
                ROOT / "tests/integration/gitlab/scripts/preservation_checks.py",
            ).snapshot(stand),
        )
    result = {}
    for name, post in stand.manifest["posts"].items():
        if name == "free-sentinel":
            continue
        value = stand.request("GET", f"/posts/{post}", actor="reader")
        import hashlib

        result[name] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", default=os.environ.get("COMPOSE", "docker-compose"))
    args = parser.parse_args()
    environment = dev.Environment(args.compose)
    destination = dev.common.private_directory(
        environment.home / "reports" / (time.strftime("%Y%m%dT%H%M%S") + "-lifecycle")
    )
    report: dict[str, Any] = {
        "status": "failed",
        "started_at": datetime.now(UTC).isoformat(),
        "checks": [],
        "manual_contents_inspected": False,
    }
    started = time.monotonic()
    stands: dict[str, Any] = {}
    try:
        stands = {service: environment.fixture(service) for service in dev.SERVICES}
        for stand in stands.values():
            stand.connect()
        before = {service: snapshot(service, stand) for service, stand in stands.items()}
        identities = {service: stand.manifest["owner"] for service, stand in stands.items()}
        dev.common.write_json(destination / "fixtures-before.json", before)
        for mode in ("down-up", "recreate", "repeat-up"):
            if mode == "down-up":
                dev.common.command(
                    ["task", "env:down"], env={**os.environ, "COMPOSE": args.compose}, timeout=600
                )
            task = "env:recreate" if mode == "recreate" else "env:up"
            dev.common.command(
                ["task", task], env={**os.environ, "COMPOSE": args.compose}, timeout=1800
            )
            for service, stand in stands.items():
                stand.connect()
                observed = snapshot(service, stand)
                dev.common.write_json(destination / f"{mode}-{service}.json", observed)
                if before[service] != observed or identities[service] != stand.manifest["owner"]:
                    raise RuntimeError(f"{mode} changed {service} fixture data or identity")
                report["checks"].append(
                    {"name": f"{mode}-{service}", "status": "passed", "fingerprints": len(observed)}
                )
                dev.common.write_json(
                    destination / f"automation-access-{service}.json",
                    {"requests": stand.access_log, "manual_contents_inspected": False},
                )
    except Exception as exc:
        message = str(exc)
        for stand in stands.values():
            message = stand.redact(message)
        report["error"] = message
        raise
    else:
        report["status"] = "passed"
        return 0
    finally:
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        dev.common.write_json(destination / "result.json", report)
        print(destination / "result.json")


if __name__ == "__main__":
    raise SystemExit(main())
