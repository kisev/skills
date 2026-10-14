#!/usr/bin/env python3
"""Append one dated hyperfine layer benchmark section to docs/gate-benchmarks.md.

The hyperfine JSON export stays untracked under ``.build/``; the tracked
benchmark file is human-curated: this script only appends the section of one
run and never rewrites or reorders the recorded history, so the owner can
annotate the timings afterwards. Rows carry the timing per command in seconds
with the same label hyperfine used, minus the ``task`` prefix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class RecordError(Exception):
    """The benchmark export or the repository state cannot be recorded."""


def repository_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RecordError("cannot resolve the HEAD revision for the benchmark section")
    return result.stdout.strip()


def _statistics(result: dict[str, Any], primary: str) -> tuple[float, float, float, float, int]:
    """Return wall mean, stddev, min, max, and run count for one benchmark."""
    summary = result.get("summary")
    if not isinstance(summary, dict):  # hyperfine 1.x exports flat statistics.
        times = result.get("times")
        return (
            float(result["mean"]),
            float(result.get("stddev", 0.0)),
            float(result["min"]),
            float(result["max"]),
            len(times) if isinstance(times, list) else 0,
        )
    metric = summary.get(primary)
    if not isinstance(metric, dict):
        raise RecordError(f"the hyperfine export has no {primary} statistics")
    count = metric.get("count")
    if not isinstance(count, int) or count < 1:
        raise RecordError(f"the hyperfine export has no run count for {primary}")
    return (
        float(metric["mean"]),
        float(metric.get("stddev", 0.0)),
        float(metric["min"]),
        float(metric["max"]),
        count,
    )


def render_section(export: Path, revision: str) -> str:
    try:
        payload = json.loads(export.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecordError(f"cannot read the hyperfine export {export}: {error}") from error
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise RecordError("the hyperfine export has no results")
    primary = str(payload.get("primary_metric", "time_wall_clock"))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    rows: list[str] = []
    counts: list[int] = []
    for result in results:
        if not isinstance(result, dict):
            raise RecordError("every hyperfine result must be an object")
        command = re.sub(r"^task ", "", str(result.get("command", "")))
        mean, stddev, minimum, maximum, count = _statistics(result, primary)
        counts.append(count)
        rows.append(f"| `{command}` | {mean:.2f} | {stddev:.2f} | {minimum:.2f} | {maximum:.2f} |")
    runs = max(counts, default=0)
    if runs < 1:
        raise RecordError("the hyperfine export has no run count")
    lines = [
        f"## {stamp} — {revision} — {runs} runs per layer",
        "",
        "| Command | Mean (s) | Stddev (s) | Min (s) | Max (s) |",
        "| - | - | - | - | - |",
        *rows,
        "",
        f"Raw hyperfine export: `.build/{export.name}` (untracked).",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=Path(".build/gates-bench.json"))
    parser.add_argument("--file", type=Path, default=Path("docs/gate-benchmarks.md"))
    parser.add_argument("--root", type=Path, help="repository root (defaults to this checkout)")
    arguments = parser.parse_args(argv)
    root = (arguments.root or Path(__file__).resolve().parents[1]).resolve()
    export = arguments.json if arguments.json.is_absolute() else root / arguments.json
    target = arguments.file if arguments.file.is_absolute() else root / arguments.file
    try:
        revision = repository_revision(root)
        section = render_section(export, revision)
    except RecordError as error:
        print(f"benchmark recording failed: {error}", file=sys.stderr)
        return 1
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    # Atomic replacement: the curated file only ever grows by one section.
    content = existing if existing.endswith("\n") or not existing else existing + "\n"
    content += section
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=target.name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, target)
    except BaseException:
        os.unlink(temporary)
        raise
    try:
        rendered = f"appended the benchmark section to {target.relative_to(root)}"
    except ValueError:
        rendered = f"appended the benchmark section to {target}"
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
