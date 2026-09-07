#!/usr/bin/env python3
"""Create a deterministic, build-only @kisev/skills distribution."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_skills import DEFAULT_OUTPUT as BUILT_SKILLS  # noqa: E402
from scripts.build_skills import build as build_skills  # noqa: E402

PACKAGE = ROOT / "packages" / "skills"
DEFAULT_OUTPUT = ROOT / ".build" / "packages" / "skills"


class DistributionError(Exception):
    """An invalid distribution input or output."""


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )


def revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode or not completed.stdout.strip():
        raise DistributionError("Git source revision is unavailable")
    return completed.stdout.strip()


def archive(skill: Path) -> bytes:
    payload = io.BytesIO()
    with gzip.GzipFile(fileobj=payload, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as document:
            for source in sorted(skill.rglob("*")):
                if source.is_symlink() or not source.is_file():
                    continue
                info = tarfile.TarInfo(source.relative_to(skill).as_posix())
                content = source.read_bytes()
                info.size = len(content)
                info.mode = 0o644
                info.mtime = 0
                document.addfile(info, io.BytesIO(content))
    return payload.getvalue()


def build(output: Path, check: bool) -> int:
    build_skills(BUILT_SKILLS, False)
    manifest = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str):
        raise DistributionError("distribution package version is invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skills-dist-", dir=output.parent) as temporary:
        staged = Path(temporary) / "skills"
        archives = staged / "archives"
        archives.mkdir(parents=True)
        entries = []
        for skill in sorted(BUILT_SKILLS.iterdir()):
            if not skill.is_dir() or not (skill / "SKILL.md").is_file():
                continue
            content = archive(skill)
            name = f"{skill.name}.tar.gz"
            destination = archives / name
            destination.write_bytes(content)
            entries.append(
                {
                    "name": skill.name,
                    "archive": f"archives/{name}",
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        index = {
            "schema": "@kisev/skills/index/v1",
            "package": "@kisev/skills",
            "version": version,
            "source_revision": revision(),
            "skills": entries,
        }
        lock = {
            "schema": "@kisev/skills/lock/v1",
            "package": "@kisev/skills",
            "version": version,
            "source_revision": index["source_revision"],
            "archives": {entry["name"]: entry["sha256"] for entry in entries},
        }
        (staged / "index.json").write_bytes(canonical(index))
        (staged / "skills-lock.json").write_bytes(canonical(lock))
        well_known = staged / ".well-known" / "skills"
        well_known.mkdir(parents=True)
        (well_known / "index.json").write_bytes(canonical(index))
        (well_known / "lock.json").write_bytes(canonical(lock))
        agent_skills = staged / ".well-known" / "agent-skills"
        agent_skills.mkdir(parents=True)
        agent_index = {
            "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
            "skills": [
                {
                    "name": entry["name"],
                    "description": f"Kisev portable skill {entry['name']}.",
                    "type": "archive",
                    "url": f"../../{entry['archive']}",
                    "digest": f"sha256:{entry['sha256']}",
                }
                for entry in entries
            ],
        }
        (agent_skills / "index.json").write_bytes(canonical(agent_index))
        (staged / "package.json").write_bytes(canonical({**manifest, "private": False}))
        if check:
            if not output.is_dir():
                print("validated distribution in isolated staging area")
                return 0
            for source in staged.rglob("*"):
                if source.is_file() and (
                    not (output / source.relative_to(staged)).is_file()
                    or (output / source.relative_to(staged)).read_bytes() != source.read_bytes()
                ):
                    raise DistributionError(
                        f"distribution artifact drift: {source.relative_to(staged)}"
                    )
            print(f"checked {len(entries)} skill archives")
            return 0
        if output.exists():
            import shutil

            shutil.rmtree(output)
        import shutil

        shutil.move(str(staged), output)
    print(f"built {len(entries)} skill archives at {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        return build(args.output.resolve(), args.check)
    except DistributionError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
