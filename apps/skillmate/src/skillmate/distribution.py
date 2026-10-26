"""The portable distribution model and its sources.

A distribution is a directory (remote base URL or local path) holding an
``index.json`` in the published Pages schema and content-addressed skill
archives under ``archives/sha256/``. Sources never fall back to each
other: an unreachable, malformed, or unpinned source is a loud error.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urljoin

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

INDEX_SCHEMA = "@kisev/skills/index/v1"
DEFAULT_INDEX_URL = "https://kisev.github.io/skills/index.json"


class DistributionError(Exception):
    """An unreachable, malformed, or integrity-failing distribution source."""


@dataclass(frozen=True)
class SkillEntry:
    """One skill in the distribution index."""

    name: str
    archive: str
    sha256: str


@dataclass(frozen=True)
class Distribution:
    """A parsed distribution index."""

    package: str
    version: str
    source_revision: str
    skills: Mapping[str, SkillEntry]

    def require_version(self, pin: str) -> None:
        """Fail loudly unless the distribution carries exactly the pinned version."""
        if self.version != pin:
            raise DistributionError(
                f"distribution version {self.version} does not match the pinned {pin}"
            )


@dataclass(frozen=True)
class ArchiveFile:
    """One regular file extracted from a skill archive, as bytes."""

    path: str
    data: bytes


@dataclass(frozen=True)
class SkillArchive:
    """A verified, fully extracted skill archive."""

    name: str
    sha256: str
    files: tuple[ArchiveFile, ...]


def parse_index(text: str) -> Distribution:
    """Parse and validate an index document against the published schema."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise DistributionError(f"index is not valid JSON: {error}") from error
    if not isinstance(document, dict):
        raise DistributionError("index must be a JSON object")
    schema = document.get("schema")
    if schema != INDEX_SCHEMA:
        raise DistributionError(f"unsupported index schema {schema!r}, expected {INDEX_SCHEMA!r}")
    package = document.get("package")
    version = document.get("version")
    revision = document.get("source_revision")
    entries = document.get("skills")
    if (
        not isinstance(package, str)
        or not isinstance(version, str)
        or not isinstance(revision, str)
    ):
        raise DistributionError("index fields package, version, source_revision must be strings")
    if not isinstance(entries, list):
        raise DistributionError("index field skills must be a list")
    skills: dict[str, SkillEntry] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise DistributionError("each skill entry must be a JSON object")
        name = entry.get("name")
        archive = entry.get("archive")
        sha256 = entry.get("sha256")
        if not (
            isinstance(name, str)
            and isinstance(archive, str)
            and isinstance(sha256, str)
            and name
            and archive
            and len(sha256) == 64
        ):
            raise DistributionError(f"skill entry {name!r} has invalid name, archive, or sha256")
        if name in skills:
            raise DistributionError(f"duplicate skill name {name!r} in index")
        archive_path = PurePosixPath(archive)
        if archive_path.is_absolute() or ".." in archive_path.parts:
            raise DistributionError(f"skill entry {name!r} has an escaping archive path")
        skills[name] = SkillEntry(name=name, archive=archive, sha256=sha256)
    return Distribution(package=package, version=version, source_revision=revision, skills=skills)


def extract_archive(name: str, sha256: str, blob: bytes) -> SkillArchive:
    """Verify an archive's digest and extract every member in memory.

    Only regular files under the archive root are accepted; absolute
    paths, ``..`` segments, and non-regular members are rejected.
    """
    digest = hashlib.sha256(blob).hexdigest()
    if digest != sha256:
        raise DistributionError(
            f"archive for {name!r} failed integrity: expected {sha256}, got {digest}"
        )
    files: list[ArchiveFile] = []
    seen: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            members: Sequence[tarfile.TarInfo] = archive.getmembers()
            for member in members:
                if member.isdir():
                    continue
                if not member.isfile():
                    raise DistributionError(
                        f"archive for {name!r} contains a non-regular member {member.name!r}"
                    )
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or not member.name:
                    raise DistributionError(
                        f"archive for {name!r} contains an escaping member path {member.name!r}"
                    )
                if member.name in seen:
                    raise DistributionError(
                        f"archive for {name!r} contains duplicate member {member.name!r}"
                    )
                extracted = archive.extractfile(member)
                if extracted is None:  # pragma: no cover - guarded by isfile
                    raise DistributionError(f"member {member.name!r} of {name!r} unreadable")
                seen.add(member.name)
                files.append(ArchiveFile(path=member.name, data=extracted.read()))
    except tarfile.TarError as error:
        raise DistributionError(
            f"archive for {name!r} is not a readable tar.gz: {error}"
        ) from error
    return SkillArchive(name=name, sha256=sha256, files=tuple(files))


def _default_fetch(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
            blob: bytes = response.read()
            return blob
    except (urllib.error.URLError, OSError) as error:
        raise DistributionError(f"cannot fetch {url}: {error}") from error


@dataclass(frozen=True)
class RemoteSource:
    """The primary source: the published Pages distribution over HTTP(S).

    ``fetch`` exists so tests can serve the same layout offline.
    """

    index_url: str = DEFAULT_INDEX_URL
    fetch: Callable[[str], bytes] = _default_fetch

    def index(self) -> Distribution:
        return parse_index(self.fetch(self.index_url).decode("utf-8"))

    def archive(self, entry: SkillEntry) -> SkillArchive:
        blob = self.fetch(urljoin(self.index_url, entry.archive))
        return extract_archive(entry.name, entry.sha256, blob)


@dataclass(frozen=True)
class LocalSource:
    """A distribution directory: the layout of a checkout build or a mirror."""

    base: Path

    def index(self) -> Distribution:
        index_path = self.base / "index.json"
        try:
            return parse_index(index_path.read_text(encoding="utf-8"))
        except OSError as error:
            raise DistributionError(f"cannot read {index_path}: {error}") from error

    def archive(self, entry: SkillEntry) -> SkillArchive:
        archive_path = self.base / entry.archive
        if not archive_path.is_relative_to(self.base):
            raise DistributionError(f"archive path {entry.archive!r} escapes the source directory")
        try:
            blob = archive_path.read_bytes()
        except OSError as error:
            raise DistributionError(f"cannot read {archive_path}: {error}") from error
        return extract_archive(entry.name, entry.sha256, blob)
