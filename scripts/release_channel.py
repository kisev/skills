#!/usr/bin/env python3
"""Resolve the publication channel of a stable release tag."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STABLE_TAG = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
MAINTENANCE_DIST_TAG = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")


class ChannelError(Exception):
    """Release channel resolution failed closed."""


def maintenance_line(tag: str) -> str:
    """Return the `vX.Y` maintenance line of a stable `vX.Y.Z` tag."""
    if STABLE_TAG.fullmatch(tag) is None:
        raise ChannelError(f"stable release tags must match vX.Y.Z, got {tag!r}")
    major, minor, _patch = tag[1:].split(".")
    return f"v{major}.{minor}"


def dist_tag(tag: str, requested: str | None = None) -> str:
    """Validate a requested dist-tag against a stable tag (`latest` by default).

    Pre-tag builds cannot prove reachability yet, so the requested channel is
    validated against the tag line instead of the git refs; the published check
    re-resolves the channel from the refs after the tag exists.
    """
    if requested is None or requested == "latest":
        return "latest"
    if MAINTENANCE_DIST_TAG.fullmatch(requested) and requested == maintenance_line(tag):
        return requested
    raise ChannelError(f"dist-tag {requested!r} does not match the {tag!r} release line")


def reachable_from(revision: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise ChannelError(result.stderr.strip() or f"cannot compare {revision!r} with {ref!r}")
    return result.returncode == 0


def resolve(tag: str, revision: str) -> dict[str, str]:
    """Bind a tagged revision to exactly one publication channel.

    A revision reachable from `origin/main` publishes the `latest` npm dist-tag
    and the Pages root. A revision reachable only from its
    `origin/release/vX.Y` maintenance branch publishes the `vX.Y` npm dist-tag
    without touching the Pages root. Anything else fails closed: tag pushes run
    the workflow from the tagged commit, so an unknown channel must never
    guess.
    """
    line = maintenance_line(tag)
    if reachable_from(revision, "origin/main"):
        channel, dist_tag = "latest", "latest"
    elif reachable_from(revision, f"origin/release/{line}"):
        channel, dist_tag = "maintenance", line
    else:
        raise ChannelError(
            f"release revision {revision} is reachable from neither origin/main "
            f"nor origin/release/{line}"
        )
    return {
        "channel": channel,
        "dist_tag": dist_tag,
        "deploys_pages": "true" if channel == "latest" else "false",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG"))
    parser.add_argument("--revision", default=os.environ.get("RELEASE_REVISION"))
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="append the resolution to GITHUB_OUTPUT instead of printing JSON",
    )
    args = parser.parse_args(argv)
    if not args.tag or not args.revision:
        parser.error("--tag and --revision (or RELEASE_TAG/RELEASE_REVISION) are required")
    try:
        result = resolve(args.tag, args.revision)
    except ChannelError as error:
        raise SystemExit(str(error)) from error
    if args.github_output:
        output_path = os.environ.get("GITHUB_OUTPUT")
        if not output_path:
            raise SystemExit("GITHUB_OUTPUT is required with --github-output")
        with open(output_path, "a", encoding="utf-8") as handle:
            for key, value in result.items():
                handle.write(f"{key}={value}\n")
    else:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
