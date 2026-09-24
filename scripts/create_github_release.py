#!/usr/bin/env python3
"""Create or verify the final GitHub Release after both channels succeed."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(Exception):
    """GitHub Release creation or verification failed closed."""


def changelog(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## \\?\[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\n"
        rf"(?P<body>.*?)(?=^## \\?\[|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match or not match.group("body").strip():
        raise ReleaseError(f"CHANGELOG.md has no release notes for {version}")
    return match.group("body").strip() + "\n"


def api(
    method: str, path: str, token: str, payload: dict[str, Any] | None = None
) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "kisev-skills-release",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
            return response.status, json.loads(content) if content else None
    except urllib.error.HTTPError as error:
        content = error.read()
        value = json.loads(content) if content else None
        return error.code, value


def remote_tag_commit(repository: str, tag: str, token: str) -> str:
    encoded_tag = urllib.parse.quote(tag, safe="")
    status, reference = api("GET", f"/repos/{repository}/git/ref/tags/{encoded_tag}", token)
    if status != 200 or not isinstance(reference, dict):
        raise ReleaseError(f"GitHub tag lookup failed with HTTP {status}: {reference}")
    value: object = reference.get("object")
    if not isinstance(value, dict) or value.get("type") != "tag":
        raise ReleaseError("GitHub release tag must be annotated")
    seen: set[str] = set()
    for _ in range(8):
        if not isinstance(value, dict):
            break
        object_type = value.get("type")
        sha = value.get("sha")
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-fA-F]{40}", sha) is None:
            break
        if object_type == "commit":
            return sha.lower()
        if object_type != "tag" or sha in seen:
            break
        seen.add(sha)
        status, tag_object = api("GET", f"/repos/{repository}/git/tags/{sha}", token)
        if status != 200 or not isinstance(tag_object, dict):
            raise ReleaseError(
                f"GitHub annotated tag lookup failed with HTTP {status}: {tag_object}"
            )
        value = tag_object.get("object")
    raise ReleaseError("GitHub tag does not peel to an exact commit")


def verify_release(value: object, tag: str, body: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(
        (
            value.get("tag_name") != tag,
            value.get("name") != tag,
            value.get("draft") is not False,
            value.get("prerelease") is not False,
            value.get("body") != body,
        )
    ):
        raise ReleaseError("GitHub Release differs from the expected release")
    return value


def verify_release_and_tag(
    value: object, repository: str, tag: str, revision: str, body: str, token: str
) -> dict[str, Any]:
    release = verify_release(value, tag, body)
    if remote_tag_commit(repository, tag, token) != revision.lower():
        raise ReleaseError("GitHub tag does not reference RELEASE_REVISION")
    return release


def create() -> dict[str, Any]:
    token = os.environ.get("GH_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    tag = os.environ.get("RELEASE_TAG", "")
    revision = os.environ.get("RELEASE_REVISION", "")
    if (
        not token
        or repository != "kisev/skills"
        or not tag.startswith("v")
        or re.fullmatch(r"[0-9a-fA-F]{40}", revision) is None
    ):
        raise ReleaseError("GitHub release environment is invalid")
    version = tag.removeprefix("v")
    body = changelog(version)
    encoded_tag = urllib.parse.quote(tag, safe="")
    if remote_tag_commit(repository, tag, token) != revision.lower():
        raise ReleaseError("GitHub tag does not reference RELEASE_REVISION")
    status, existing = api("GET", f"/repos/{repository}/releases/tags/{encoded_tag}", token)
    if status == 200:
        return verify_release_and_tag(existing, repository, tag, revision, body, token)
    if status != 404:
        raise ReleaseError(f"GitHub release lookup failed with HTTP {status}: {existing}")
    status, created = api(
        "POST",
        f"/repos/{repository}/releases",
        token,
        {
            "tag_name": tag,
            "target_commitish": revision,
            "name": tag,
            "body": body,
            "draft": False,
            "prerelease": False,
            "make_latest": "true",
        },
    )
    if status != 201 or not isinstance(created, dict):
        raise ReleaseError(f"GitHub release creation failed with HTTP {status}: {created}")
    status, current = api("GET", f"/repos/{repository}/releases/tags/{encoded_tag}", token)
    if status != 200:
        raise ReleaseError(f"GitHub release postcondition failed with HTTP {status}: {current}")
    return verify_release_and_tag(current, repository, tag, revision, body, token)


def main() -> int:
    try:
        release = create()
    except (OSError, ReleaseError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"status": "verified", "url": release.get("html_url")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
