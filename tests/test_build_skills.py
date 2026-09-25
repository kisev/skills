from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import build_skills


def portable_file_inventory(
    root: Path, *, excluded_parts: frozenset[str] = frozenset()
) -> dict[Path, bytes]:
    inventory: dict[Path, bytes] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or path.is_symlink()
            or "__pycache__" in relative.parts
            or path.suffix in {".pyc", ".pyo"}
            or any(part in excluded_parts for part in relative.parts)
        ):
            continue
        inventory[relative] = path.read_bytes()
    return inventory


def isolated_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shared = tmp_path / "shared"
    sources = tmp_path / "skills"
    (shared / "references").mkdir(parents=True)
    (sources / "foo").mkdir(parents=True)
    (sources / "foo" / "SKILL.source.md").write_text(
        "---\nname: foo\ndescription: Foo\n---\n", encoding="utf-8"
    )
    (sources / "bar").mkdir(parents=True)
    (sources / "bar" / "SKILL.source.md").write_text(
        "---\nname: bar\ndescription: Bar\n---\n", encoding="utf-8"
    )
    (shared / "references" / "canonical.md").write_text("canonical\n", encoding="utf-8")
    (shared / "skill-relations.json").write_text(
        json.dumps(
            {
                "version": 1,
                "relations": [
                    {
                        "from": "foo",
                        "to": "bar",
                        "type": "recommends",
                        "reason": "fixture companion",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
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
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_skills, "SHARED", shared)
    monkeypatch.setattr(build_skills, "SOURCES", sources)
    monkeypatch.setattr(build_skills, "MANIFEST", manifest)
    return sources


@pytest.mark.parametrize("version", ["7.2.3", "8.0.1"])
def test_release_stamp_is_portable_and_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    source_root = build_skills.ROOT
    manifest = tmp_path / "packages/skills/package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"version": version}))
    monkeypatch.setattr(build_skills, "ROOT", tmp_path)
    output = tmp_path / "built"
    build_skills.build(output, False)
    build_skills.build(output, True)
    runner = output / "code-review/scripts/review_context.py"
    assert f'SKILL_VERSION = "{version}"' in runner.read_text()
    assert "@PORTABLE_RELEASE_VERSION@" not in runner.read_text()
    assert (
        "@PORTABLE_RELEASE_VERSION@"
        in (source_root / "skills/code-review/scripts/review_context.py").read_text()
    )


def test_dev_build_stamps_dev_source_without_changing_authored_sources(tmp_path: Path) -> None:
    output = tmp_path / "built"
    dev_source = "https://kisev.github.io/skills/dev"
    assert build_skills.build(output, False, dev_source) == 0
    for entrypoint in output.glob("*/SKILL.md"):
        assert f'  source: "{dev_source}"' in entrypoint.read_text(encoding="utf-8")
    for source in build_skills.SOURCES.glob("*/SKILL.source.md"):
        assert f'  source: "{build_skills.STABLE_SOURCE_URL}"' in source.read_text(encoding="utf-8")


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
            json.dumps({"version": 1, "files": files}),
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
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(build_skills.BuildError):
        build_skills.manifest_entries()


def test_generated_destinations_are_bounded_to_existing_skill_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_manifest(tmp_path, monkeypatch)
    manifest = build_skills.MANIFEST
    for destination in ("../outside", "foo/../outside", "missing/references/file.md"):
        manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "files": [
                        {
                            "source": "references/canonical.md",
                            "destination": destination,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(build_skills.BuildError):
            build_skills.manifest_entries()


def test_source_check_rejects_generated_copy_entrypoint_and_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = isolated_manifest(tmp_path, monkeypatch)
    entries = build_skills.manifest_entries()
    target = sources / "foo/references/canonical.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(entries[0][0].read_bytes())
    with pytest.raises(build_skills.BuildError, match="generated destination committed"):
        build_skills.check_sources(entries)

    target.unlink()
    (sources / "foo/SKILL.md").write_text("generated\n", encoding="utf-8")
    with pytest.raises(build_skills.BuildError, match=r"generated SKILL\.md"):
        build_skills.check_sources(entries)
    (sources / "foo/SKILL.md").unlink()

    target.symlink_to(entries[0][0])
    with pytest.raises(build_skills.BuildError, match="symbolic link"):
        build_skills.check_sources(entries)


def test_built_check_rejects_symlink_content_mode_and_undeclared_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_manifest(tmp_path, monkeypatch)
    entries = build_skills.manifest_entries()
    built = tmp_path / "built"
    build_skills.copy_source(built)
    build_skills.materialize(built, entries)
    target = built / "foo/references/canonical.md"

    target.unlink()
    target.symlink_to(entries[0][0])
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(built, entries)
    target.unlink()
    target.write_bytes(b"modified\n")
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(built, entries)
    target.write_bytes(entries[0][0].read_bytes())
    os.chmod(target, 0o600)
    os.chmod(entries[0][0], 0o644)
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(built, entries)
    os.chmod(target, 0o644)
    extra = built / "other/references/canonical.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("modified\n", encoding="utf-8")
    with pytest.raises(build_skills.BuildError):
        build_skills.check_materialized(built, entries)


def test_check_does_not_create_output_or_change_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = isolated_manifest(tmp_path, monkeypatch)
    output = tmp_path / "missing-output"
    before = {
        path.relative_to(sources): path.read_bytes()
        for path in sources.rglob("*")
        if path.is_file()
    }
    assert build_skills.build(output, True) == 0
    assert not output.exists()
    assert {
        path.relative_to(sources): path.read_bytes()
        for path in sources.rglob("*")
        if path.is_file()
    } == before


def test_build_materializes_only_in_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = isolated_manifest(tmp_path, monkeypatch)
    output = tmp_path / "built"

    assert build_skills.build(output, False) == 0

    assert (output / "foo/SKILL.md").is_file()
    assert not (output / "foo/SKILL.source.md").exists()
    assert (output / "foo/references/canonical.md").read_text(encoding="utf-8") == "canonical\n"
    assert not (sources / "foo/SKILL.md").exists()
    assert not (sources / "foo/references/canonical.md").exists()


def test_portable_file_inventory_ignores_python_bytecode(tmp_path: Path) -> None:
    (tmp_path / "kept.py").write_text("kept\n", encoding="utf-8")
    (tmp_path / "orphan.pyc").write_bytes(b"bytecode")
    (tmp_path / "legacy.pyo").write_bytes(b"optimized bytecode")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "cached.pyc").write_bytes(b"cached bytecode")

    assert portable_file_inventory(tmp_path) == {Path("kept.py"): b"kept\n"}


def test_portable_file_inventory_ignores_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("target\n", encoding="utf-8")
    (tmp_path / "linked.py").symlink_to(target)

    assert portable_file_inventory(tmp_path) == {Path("target.py"): b"target\n"}


def test_spec_manage_portable_inventory_matches_all_authored_and_materialized_files() -> None:
    source = build_skills.SOURCES / "spec-manage"
    built = build_skills.ROOT / ".build/skills/spec-manage"
    authored = portable_file_inventory(source, excluded_parts=frozenset({"ru", "en"}))
    authored[Path("SKILL.md")] = authored.pop(Path("SKILL.source.md"))
    generated = {
        destination.relative_to("spec-manage"): shared.read_bytes()
        for shared, destination in build_skills.manifest_entries()
        if destination.parts[0] == "spec-manage"
    }
    expected = authored | generated
    actual = portable_file_inventory(built)

    assert actual == expected
    assert not any("ru" in path.parts for path in actual)
