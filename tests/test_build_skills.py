from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_skills


def isolated_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shared = tmp_path / "shared"
    sources = tmp_path / "skills"
    (shared / "references").mkdir(parents=True)
    (sources / "foo").mkdir(parents=True)
    (sources / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
    (shared / "references" / "canonical.md").write_text("canonical\n", encoding="utf-8")
    manifest = shared / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "files": [
                    {
                        "source": "references/canonical.md",
                        "destination": "foo/references/canonical.md",
                    }
                ],
                "language_policy_skills": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_skills, "SHARED", shared)
    monkeypatch.setattr(build_skills, "SOURCES", sources)
    monkeypatch.setattr(build_skills, "MANIFEST", manifest)
    return sources


def test_manifest_rejects_duplicate_missing_symlink_and_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_manifest(tmp_path, monkeypatch)
    manifest = build_skills.MANIFEST

    cases = [
        [
            {"source": "references/canonical.md", "destination": "foo/a"},
            {"source": "references/canonical.md", "destination": "foo/a"},
        ],
        [{"source": "references/missing.md", "destination": "foo/a"}],
        [{"source": "../outside", "destination": "foo/a"}],
        [{"source": "references/canonical.md", "destination": "../outside"}],
    ]
    for files in cases:
        manifest.write_text(
            json.dumps({"version": 1, "files": files, "language_policy_skills": []}),
            encoding="utf-8",
        )
        with pytest.raises(build_skills.BuildError):
            build_skills.manifest_entries()

    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    (build_skills.SHARED / "references-link").symlink_to(outside)
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "files": [{"source": "references-link", "destination": "foo/a"}],
                "language_policy_skills": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(build_skills.BuildError):
        build_skills.manifest_entries()


def test_policy_skill_names_are_bounded_to_existing_skill_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_manifest(tmp_path, monkeypatch)
    manifest = build_skills.MANIFEST
    for name in ("../outside", "foo/nested", "missing"):
        manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": [],
                    "language_policy_skills": [name],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(build_skills.BuildError):
            build_skills.manifest_entries()


def test_check_rejects_destination_symlink_mode_drift_and_undeclared_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = isolated_manifest(tmp_path, monkeypatch)
    entries = build_skills.manifest_entries()
    target = sources / "foo/references/canonical.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(entries[0][0].read_bytes())

    target.unlink()
    target.symlink_to(entries[0][0])
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(sources, entries)
    target.unlink()
    target.write_bytes(b"modified\n")
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(sources, entries)
    target.write_bytes(entries[0][0].read_bytes())
    os.chmod(target, 0o600)
    os.chmod(entries[0][0], 0o644)
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(sources, entries)
    os.chmod(target, 0o644)
    extra = sources / "other/references/canonical.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("modified\n", encoding="utf-8")
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(sources, entries)


def test_check_does_not_create_output_or_change_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = isolated_manifest(tmp_path, monkeypatch)
    entries = build_skills.manifest_entries()
    target = sources / "foo/references/canonical.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(entries[0][0].read_bytes())
    output = tmp_path / "missing-output"
    before = target.read_bytes()
    assert build_skills.build(output, True) == 0
    assert not output.exists()
    assert target.read_bytes() == before
