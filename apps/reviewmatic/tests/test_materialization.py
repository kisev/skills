"""Manifest-driven materialization: byte-identical canon, exact package tree."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "shared" / "manifest.json"


def python_runtime() -> dict[str, Any]:
    payload: Any = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runtime = payload["pythonRuntime"]
    assert runtime["destination"] == "apps/reviewmatic/src/reviewmatic/portable"
    return dict(runtime)


def test_materialized_files_are_byte_identical_to_the_canon() -> None:
    destination = ROOT / python_runtime()["destination"]
    for entry in python_runtime()["entries"]:
        source = ROOT / "shared" / entry["source"]
        materialized = destination / entry["target"]
        assert materialized.is_file(), entry["target"]
        assert materialized.read_bytes() == source.read_bytes(), entry["target"]


def test_the_portable_package_contains_exactly_the_declared_entries() -> None:
    destination = ROOT / python_runtime()["destination"]
    declared = {destination / entry["target"] for entry in python_runtime()["entries"]}
    actual = {
        path
        for path in destination.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert actual == declared


def test_materialized_targets_stay_inside_the_portable_package() -> None:
    for entry in python_runtime()["entries"]:
        parts = Path(entry["target"]).parts
        assert parts
        assert all(part not in {"", ".", ".."} for part in parts)


def test_the_canonical_modules_import_from_the_materialized_package() -> None:
    from reviewmatic.portable import state_artifacts
    from reviewmatic.portable.portable_gitlab import contract, review_semver
    from reviewmatic.portable.portable_gitlab.label_assessment import (
        validate_label_assessments,
    )

    assert callable(contract.digest)
    assert callable(review_semver.assessment_is_valid)
    assert callable(validate_label_assessments)
    assert callable(state_artifacts.marker_run)
    # The schema sits next to the materialized contract module.
    schema = contract.artifact_schema()
    assert schema["$id"] == "https://kisev.dev/schemas/portable-gitlab-artifacts/v2"
