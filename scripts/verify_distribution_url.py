#!/usr/bin/env python3
"""Verify a deployed well-known portable-skill distribution over HTTPS."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "evals" / "contracts" / "public-surfaces.json"
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class VerificationError(Exception):
    pass


def fetch(url: str) -> bytes:
    require_https(url)
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "kisev-skills-release-check"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
        require_https(response.geturl())
        if response.status != 200:
            raise VerificationError(f"HTTP {response.status}: {url}")
        return bytes(response.read())


def require_https(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise VerificationError("distribution URLs must use credential-free HTTPS")


def verify_manifest_files(base: str, manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = manifest.get("pages") if isinstance(manifest, dict) else None
    files = pages.get("files") if isinstance(pages, dict) else None
    if not isinstance(files, dict) or not files:
        raise VerificationError("release manifest has no Pages file inventory")
    for path, expected in sorted(files.items()):
        candidate = Path(path) if isinstance(path, str) else Path("/")
        if (
            not isinstance(path, str)
            or candidate.is_absolute()
            or ".." in candidate.parts
            or not isinstance(expected, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected) is None
        ):
            raise VerificationError("release manifest contains an unsafe Pages entry")
        content = fetch(urllib.parse.urljoin(base, urllib.parse.quote(path, safe="/")))
        if hashlib.sha256(content).hexdigest() != expected:
            raise VerificationError(f"deployed Pages file differs from release artifact: {path}")
    return len(files)


def verify(base_url: str, version: str, revision: str, manifest_path: Path | None = None) -> int:
    base = base_url.rstrip("/") + "/"
    release = json.loads(fetch(urllib.parse.urljoin(base, "index.json")))
    if release.get("version") != version or release.get("source_revision") != revision:
        raise VerificationError("deployed release metadata does not match the release")
    index_url = urllib.parse.urljoin(base, ".well-known/agent-skills/index.json")
    index = json.loads(fetch(index_url))
    if index.get("$schema") != SCHEMA or not isinstance(index.get("skills"), list):
        raise VerificationError("deployed well-known index is invalid")
    names: set[str] = set()
    expected_names = set(json.loads(INVENTORY.read_text(encoding="utf-8"))["skills"])
    base_path = urllib.parse.urlparse(base).path
    for entry in index["skills"]:
        if not isinstance(entry, dict) or entry.get("type") != "archive":
            raise VerificationError("well-known entry is invalid")
        name, digest = entry.get("name"), entry.get("digest")
        if not isinstance(name, str) or name in names:
            raise VerificationError("well-known skill names must be unique")
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise VerificationError(f"invalid digest for {name}")
        archive_url = urllib.parse.urljoin(index_url, str(entry.get("url", "")))
        parsed_base, parsed_archive = (
            urllib.parse.urlparse(base),
            urllib.parse.urlparse(archive_url),
        )
        if parsed_archive.netloc != parsed_base.netloc or not parsed_archive.path.startswith(
            base_path
        ):
            raise VerificationError(f"archive escapes the Pages distribution: {name}")
        content = fetch(archive_url)
        digest_hex = digest.removeprefix("sha256:")
        if not parsed_archive.path.endswith(f"/archives/sha256/{digest_hex}.tar.gz"):
            raise VerificationError(f"archive URL is not content-addressed: {name}")
        if hashlib.sha256(content).hexdigest() != digest_hex:
            raise VerificationError(f"archive digest mismatch: {name}")
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            members = archive.getmembers()
            if "SKILL.md" not in {member.name for member in members}:
                raise VerificationError(f"archive has no root SKILL.md: {name}")
            if any(
                member.issym()
                or member.islnk()
                or member.name.startswith(("/", "\\"))
                or ".." in member.name.split("/")
                for member in members
            ):
                raise VerificationError(f"archive has an unsafe member: {name}")
        names.add(name)
    if names != expected_names:
        raise VerificationError("deployed skills do not match the public inventory")
    if manifest_path is not None:
        verify_manifest_files(base, manifest_path)
    return len(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--delay", type=float, default=5)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    error: Exception | None = None
    for attempt in range(max(args.attempts, 1)):
        try:
            count = verify(args.base_url, args.version, args.revision, args.manifest)
            print(f"verified {count} deployed skill archives at {args.base_url}")
            return 0
        except (
            VerificationError,
            OSError,
            ValueError,
            tarfile.TarError,
            urllib.error.URLError,
        ) as current:
            error = current
            if attempt + 1 < args.attempts:
                time.sleep(args.delay)
    parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
