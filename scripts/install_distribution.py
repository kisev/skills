#!/usr/bin/env python3
"""Install one verified build distribution skill through a pinned skills CLI."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, NoReturn


class InstallError(ValueError):
    """An expected distribution or local-install failure."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InstallError(message)


def read_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            value = json.loads(response.read())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise InstallError("distribution JSON is unavailable or invalid") from error
    if not isinstance(value, dict):
        raise InstallError("distribution JSON must be an object")
    return value


def extract(archive: bytes, destination: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as document:
            for member in document.getmembers():
                target = destination / member.name
                try:
                    target.resolve().relative_to(destination.resolve())
                except ValueError:
                    raise InstallError("distribution archive contains an unsafe member") from None
                if member.issym() or member.islnk() or not member.isfile():
                    raise InstallError("distribution archive contains an unsafe member")
            document.extractall(destination, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise InstallError("distribution archive is invalid") from error
    if not (destination / "SKILL.md").is_file():
        raise InstallError("distribution archive does not have root SKILL.md")


def lock_path(home: Path) -> Path:
    return home / ".local" / "state" / "kisev-skills" / "distribution-lock.json"


def install(index_url: str, skill: str, agent: str, binary: str, home: Path) -> dict[str, object]:
    index = read_json(index_url)
    lock = read_json(urllib.parse.urljoin(index_url, "lock.json"))
    entries = index.get("skills")
    hashes = lock.get("archives")
    if (
        index.get("schema") != "@kisev/skills/index/v1"
        or lock.get("schema") != "@kisev/skills/lock/v1"
        or not isinstance(entries, list)
        or not isinstance(hashes, dict)
    ):
        raise InstallError("distribution index or lock schema is invalid")
    entry = next(
        (item for item in entries if isinstance(item, dict) and item.get("name") == skill), None
    )
    if (
        not isinstance(entry, dict)
        or not isinstance(entry.get("archive"), str)
        or not isinstance(entry.get("sha256"), str)
        or hashes.get(skill) != entry["sha256"]
    ):
        raise InstallError("distribution lock does not bind the requested skill")
    archive_url = urllib.parse.urljoin(index_url, f"../../{entry['archive']}")
    try:
        with urllib.request.urlopen(archive_url, timeout=20) as response:
            archive = response.read()
    except OSError as error:
        raise InstallError("distribution archive is unavailable") from error
    actual = hashlib.sha256(archive).hexdigest()
    if actual != entry["sha256"]:
        raise InstallError("distribution archive digest does not match the lock")
    path = lock_path(home)
    previous: dict[str, Any] = {}
    if path.is_file() and not path.is_symlink():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InstallError("local distribution lock is invalid") from error
    with tempfile.TemporaryDirectory(prefix="kisev-skills-") as temporary:
        directory = Path(temporary) / skill
        directory.mkdir()
        extract(archive, directory)
        completed = subprocess.run(
            [
                binary,
                "add",
                str(directory),
                "--skill",
                skill,
                "--agent",
                agent,
                "--copy",
                "--global",
                "--yes",
            ],
            cwd=temporary,
            env={**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
            check=False,
            capture_output=True,
            text=True,
        )
    if completed.returncode:
        raise InstallError("pinned skills CLI rejected the verified archive")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "@kisev/skills/local-lock/v1",
                "index": index_url,
                "source_revision": index.get("source_revision"),
                "skills": {**previous.get("skills", {}), skill: actual},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return {
        "status": "updated" if skill in previous.get("skills", {}) else "added",
        "skill": skill,
        "agent": agent,
        "digest": actual,
        "lock_path": str(path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    parser.add_argument("--index-url", required=True)
    parser.add_argument("--skill", required=True)
    parser.add_argument("--agent", choices=("opencode", "codex"), required=True)
    parser.add_argument("--skills-binary", required=True)
    parser.add_argument("--home", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        print(
            json.dumps(
                install(args.index_url, args.skill, args.agent, args.skills_binary, args.home),
                sort_keys=True,
            )
        )
        return 0
    except InstallError as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
