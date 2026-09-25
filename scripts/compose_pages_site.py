#!/usr/bin/env python3
"""Compose one Pages deployment containing stable and moving dev channels."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

STATIC_FILES = (
    "index.json",
    "skills-lock.json",
    ".well-known/skills/index.json",
    ".well-known/skills/lock.json",
    ".well-known/agent-skills/index.json",
)
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_DISTRIBUTION_BYTES = 256 * 1024 * 1024


class ComposeError(Exception):
    pass


def safe_path(value: object) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ComposeError("distribution contains an unsafe path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ComposeError("distribution contains an unsafe path")
    return path


def fetch(base_url: str, relative: str) -> bytes:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ComposeError("distribution URL must use credential-free HTTPS")
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", urllib.parse.quote(relative, safe="/"))
    request = urllib.request.Request(  # noqa: S310
        url, headers={"User-Agent": "kisev-skills-pages-compose"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        final = urllib.parse.urlsplit(response.geturl())
        base_path = parsed.path.rstrip("/") + "/"
        if (
            final.scheme != "https"
            or final.hostname != parsed.hostname
            or final.username
            or final.password
            or not final.path.startswith(base_path)
            or response.status != 200
        ):
            raise ComposeError(f"invalid distribution response for {relative}")
        content = bytes(response.read(MAX_FILE_BYTES + 1))
    if len(content) > MAX_FILE_BYTES:
        raise ComposeError(f"distribution file exceeds size limit: {relative}")
    return content


def copy_remote(base_url: str, target: Path) -> None:
    index_content = fetch(base_url, "index.json")
    payloads = {"index.json": index_content}
    for static_name in STATIC_FILES[1:]:
        payloads[static_name] = fetch(base_url, static_name)
    try:
        index = json.loads(payloads["index.json"])
    except json.JSONDecodeError as error:
        raise ComposeError("remote distribution index is invalid") from error
    skills = index.get("skills") if isinstance(index, dict) else None
    if not isinstance(skills, list) or not skills:
        raise ComposeError("remote distribution has no skills")
    if payloads[".well-known/skills/index.json"] != payloads["index.json"]:
        raise ComposeError("remote distribution indexes differ")
    if payloads[".well-known/skills/lock.json"] != payloads["skills-lock.json"]:
        raise ComposeError("remote distribution locks differ")
    try:
        lock = json.loads(payloads["skills-lock.json"])
        agent_index = json.loads(payloads[".well-known/agent-skills/index.json"])
    except json.JSONDecodeError as error:
        raise ComposeError("remote distribution metadata is invalid") from error
    archives = lock.get("archives") if isinstance(lock, dict) else None
    agent_skills = agent_index.get("skills") if isinstance(agent_index, dict) else None
    if (
        not isinstance(archives, dict)
        or not isinstance(agent_skills, list)
        or lock.get("version") != index.get("version")
        or lock.get("source_revision") != index.get("source_revision")
    ):
        raise ComposeError("remote distribution metadata differs")
    total = sum(len(content) for content in payloads.values())
    observed: dict[str, str] = {}
    for entry in skills:
        archive = safe_path(entry.get("archive") if isinstance(entry, dict) else None)
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or archive.as_posix() != f"archives/sha256/{digest}.tar.gz"
        ):
            raise ComposeError("remote distribution archive identity is invalid")
        content = fetch(base_url, archive.as_posix())
        if hashlib.sha256(content).hexdigest() != digest:
            raise ComposeError("remote distribution archive digest differs")
        payloads[archive.as_posix()] = content
        skill_name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(skill_name, str) or skill_name in observed:
            raise ComposeError("remote distribution skill identity is invalid")
        observed[skill_name] = digest
        total += len(content)
        if total > MAX_DISTRIBUTION_BYTES:
            raise ComposeError("remote distribution exceeds size limit")
    if archives != observed:
        raise ComposeError("remote distribution lock differs from its index")
    agent_observed = {
        entry.get("name"): str(entry.get("digest", "")).removeprefix("sha256:")
        for entry in agent_skills
        if isinstance(entry, dict)
    }
    if agent_observed != observed or len(agent_observed) != len(agent_skills):
        raise ComposeError("remote agent-skills index differs from its lock")
    for relative, content in payloads.items():
        destination = target / safe_path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)


def copy_local(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise ComposeError(f"local distribution is invalid: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ComposeError("local distribution contains a symlink")
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def compose(
    output: Path,
    *,
    stable_dir: Path | None,
    stable_url: str | None,
    dev_dir: Path | None,
    dev_url: str | None,
) -> None:
    if (stable_dir is None) == (stable_url is None) or (dev_dir is None) == (dev_url is None):
        raise ComposeError("choose exactly one local or remote source for each channel")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skills-pages-", dir=output.parent) as temporary:
        staged = Path(temporary) / "site"
        staged.mkdir()
        if stable_dir is not None:
            copy_local(stable_dir, staged)
        else:
            if stable_url is None:
                raise ComposeError("stable source is missing")
            copy_remote(stable_url, staged)
            (staged / ".nojekyll").write_bytes(b"")
        dev_target = staged / "dev"
        if dev_dir is not None:
            copy_local(dev_dir, dev_target)
        else:
            if dev_url is None:
                raise ComposeError("dev source is missing")
            copy_remote(dev_url, dev_target)
        if output.exists():
            shutil.rmtree(output)
        shutil.move(staged, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stable-dir", type=Path)
    parser.add_argument("--stable-url")
    parser.add_argument("--dev-dir", type=Path)
    parser.add_argument("--dev-url")
    args = parser.parse_args(argv)
    try:
        compose(
            args.output.resolve(),
            stable_dir=args.stable_dir.resolve() if args.stable_dir else None,
            stable_url=args.stable_url,
            dev_dir=args.dev_dir.resolve() if args.dev_dir else None,
            dev_url=args.dev_url,
        )
    except (ComposeError, OSError, ValueError, urllib.error.URLError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
