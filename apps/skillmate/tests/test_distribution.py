"""Distribution model and source tests against a static fixture, fully offline."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest
from skillmate.distribution import (
    INDEX_SCHEMA,
    DistributionError,
    LocalSource,
    RemoteSource,
    SkillEntry,
    parse_index,
)

FIXTURE = Path(__file__).parent / "fixtures" / "distribution"


def _valid_index() -> dict[str, object]:
    return {
        "package": "@kisev/skills",
        "schema": INDEX_SCHEMA,
        "version": "11.0.0",
        "source_revision": "0" * 40,
        "skills": [
            {
                "name": "alpha",
                "archive": "archives/sha256/" + "a" * 64 + ".tar.gz",
                "sha256": "a" * 64,
            },
        ],
    }


def _index_text(mutate: Callable[[dict[str, object]], None] | None = None) -> str:
    document = _valid_index()
    if mutate is not None:
        mutate(document)
    return json.dumps(document)


def test_parse_index_reads_the_fixture() -> None:
    distribution = LocalSource(FIXTURE).index()
    assert distribution.package == "@kisev/skills"
    assert distribution.version == "11.0.0"
    assert distribution.source_revision == "0" * 40
    assert set(distribution.skills) == {"alpha", "beta"}


def test_local_source_extracts_a_verified_archive() -> None:
    source = LocalSource(FIXTURE)
    archive = source.archive(source.index().skills["alpha"])
    files = {f.path: f.data for f in archive.files}
    assert files["references/note.md"] == b"Alpha reference.\n"
    assert files["SKILL.md"].startswith(b"---\nname: alpha\ndescription:")


def test_local_source_reports_a_missing_index() -> None:
    with pytest.raises(DistributionError, match="cannot read"):
        LocalSource(FIXTURE / "missing").index()


def test_corrupted_archive_fails_integrity(tmp_path: Path) -> None:
    copy = tmp_path / "distribution"
    shutil.copytree(FIXTURE, copy)
    source = LocalSource(copy)
    entry = source.index().skills["alpha"]
    entry_path = copy / entry.archive
    entry_path.write_bytes(entry_path.read_bytes()[:-2] + b"xy")
    with pytest.raises(DistributionError, match="failed integrity"):
        source.archive(entry)


def _archive_with_member(name: str, *, regular: bool = True) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = 3
        if not regular:
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            info.size = 0
        archive.addfile(info, None if not regular else io.BytesIO(b"abc"))
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("name", "regular"),
    [("../escape.md", True), ("/absolute.md", True), ("link.md", False)],
)
def test_extract_rejects_escaping_and_non_regular_members(name: str, regular: bool) -> None:
    blob = _archive_with_member(name, regular=regular)
    from skillmate.distribution import extract_archive

    with pytest.raises(DistributionError):
        extract_archive("alpha", hashlib.sha256(blob).hexdigest(), blob)


@pytest.mark.parametrize(
    "label",
    ["schema", "skills_list", "entry_shape", "duplicate", "escaping_archive"],
)
def test_parse_index_rejects_malformed_documents(label: str) -> None:
    def mutate(document: dict[str, object]) -> None:
        if label == "schema":
            document["schema"] = "@kisev/skills/index/v2"
        elif label == "skills_list":
            document["skills"] = {}
        elif label == "duplicate":
            entry = dict(document["skills"][0])  # type: ignore[index]
            document["skills"] = [entry, dict(entry)]
        elif label == "escaping_archive":
            document["skills"][0]["archive"] = "../../etc/passwd"  # type: ignore[index]
        else:
            document["skills"][0] = {"name": "alpha"}  # type: ignore[index]

    with pytest.raises(DistributionError):
        parse_index(_index_text(mutate))


def test_require_version_accepts_the_pin_and_rejects_a_mismatch() -> None:
    distribution = LocalSource(FIXTURE).index()
    distribution.require_version("11.0.0")
    with pytest.raises(DistributionError, match="does not match the pinned"):
        distribution.require_version("10.0.0")


def test_remote_source_reads_a_file_url_offline() -> None:
    index_url = (FIXTURE / "index.json").as_uri()
    source = RemoteSource(index_url=index_url)
    distribution = source.index()
    entry = distribution.skills["beta"]
    archive = source.archive(entry)
    assert archive.files[0].data.startswith(b"---\nname: beta")


def test_remote_source_fails_loudly_when_unreachable() -> None:
    source = RemoteSource(index_url=(FIXTURE / "missing" / "index.json").as_uri())
    with pytest.raises(DistributionError, match="cannot fetch"):
        source.index()


def test_remote_source_resolves_archive_urls_against_the_index_url() -> None:
    seen: list[str] = []
    archive_bytes = _archive_with_member("SKILL.md")
    entry = SkillEntry(
        name="alpha",
        archive="archives/sha256/x.tar.gz",
        sha256=hashlib.sha256(archive_bytes).hexdigest(),
    )

    def fetch(url: str) -> bytes:
        seen.append(url)
        return archive_bytes if url.endswith("x.tar.gz") else _index_text().encode()

    source = RemoteSource(index_url="https://kisev.github.io/skills/index.json", fetch=fetch)
    source.archive(entry)
    assert seen == ["https://kisev.github.io/skills/archives/sha256/x.tar.gz"]
