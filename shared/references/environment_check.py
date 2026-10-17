#!/usr/bin/env python3
"""Check the external tools this skill declares in references/requirements.json.

The archive ships one materialized manifest; this stdlib-only runner reads it,
runs each ``check`` command locally, and prints one ``OK``/``FAIL`` line per
tool. A failing tool is never a dead end: every failure prints its copy-ready
``install`` command so the first session can repair the environment. The runner
installs nothing itself and makes no network call.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST_RELATIVE = Path("references") / "requirements.json"
LEGACY_PIN_RELATIVE = Path("references") / "runtime-pin.json"
CHECK_TIMEOUT_SECONDS = 20
MAX_DETAIL_CHARS = 120
SCHEMA = "@kisev/skills/requirements/v1"


def manifest_path() -> Path:
    """The manifest beside this runner, at <skill>/references/requirements.json."""
    return Path(__file__).resolve().parent.parent / MANIFEST_RELATIVE


def load_manifest(path: Path) -> dict[str, Any]:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError(f"unsupported requirements schema in {path}")
    if not isinstance(value.get("skill"), str) or not value["skill"]:
        raise ValueError(f"requirements manifest lacks a skill name: {path}")
    if not isinstance(value.get("source_revision"), str) or not value["source_revision"]:
        raise ValueError(f"requirements manifest lacks a source revision: {path}")
    requirements = value.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"requirements manifest declares no tools: {path}")
    for item in requirements:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) and item[field]
            for field in ("tool", "check", "install")
        ):
            raise ValueError(f"requirements manifest has an invalid tool node: {path}")
    return value


def legacy_pin(path: Path) -> dict[str, Any] | None:
    candidate = path.parent / LEGACY_PIN_RELATIVE.name
    if not candidate.is_file():
        return None
    try:
        value: Any = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def shorten(text: str) -> str:
    line = next((item.strip() for item in text.splitlines() if item.strip()), "")
    return line if len(line) <= MAX_DETAIL_CHARS else line[: MAX_DETAIL_CHARS - 1] + "…"


def run_check(command: str) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (False, f"timed out after {CHECK_TIMEOUT_SECONDS}s")
    except OSError as error:
        return (False, str(error))
    if completed.returncode == 0:
        detail = shorten(completed.stdout) or "available"
        return (True, detail)
    output = shorten(completed.stderr) or shorten(completed.stdout)
    return (False, output or f"exit status {completed.returncode}")


def evaluate(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in manifest["requirements"]:
        ready, detail = run_check(str(item["check"]))
        results.append(
            {
                "tool": item["tool"],
                "check": item["check"],
                "install": item["install"],
                "version": item.get("version"),
                "ready": ready,
                "detail": detail,
            }
        )
    return results


def render(manifest: dict[str, Any], results: list[dict[str, Any]]) -> str:
    revision = str(manifest["source_revision"])
    version = str(manifest.get("version", "unknown"))
    lines = [
        f"{manifest['skill']} environment contract (version {version}, revision {revision[:12]})",
    ]
    for result in results:
        marker = "OK  " if result["ready"] else "FAIL"
        lines.append(f"{marker} {result['tool']:<20} {result['detail']}")
        if not result["ready"]:
            lines.append(f"     repair: {result['install']}")
    failed = [result for result in results if not result["ready"]]
    lines.append("")
    if failed:
        lines.append(
            f"{len(results) - len(failed)} of {len(results)} tools are ready. "
            "Repair each FAIL, then re-run this check:"
        )
        for result in failed:
            lines.append(f"  {result['install']}")
    else:
        lines.append(f"all {len(results)} tools are ready.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print a machine-readable report")
    arguments = parser.parse_args(argv)
    path = manifest_path()
    if not path.is_file():
        legacy = legacy_pin(path)
        if legacy is not None:
            print(
                f"environment: {path} is absent; "
                "an archive installed before the environment contract carries "
                "references/runtime-pin.json instead.",
                file=sys.stderr,
            )
            return 0
        print(f"environment: no requirements manifest at {path}", file=sys.stderr)
        return 0
    try:
        manifest = load_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"environment: {error}", file=sys.stderr)
        return 2
    results = evaluate(manifest)
    if arguments.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "skill": manifest["skill"],
                    "version": manifest.get("version"),
                    "source_revision": manifest["source_revision"],
                    "ready": all(result["ready"] for result in results),
                    "results": results,
                },
                sort_keys=True,
            )
        )
    else:
        print(render(manifest, results))
    return 0 if all(result["ready"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
