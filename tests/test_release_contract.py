from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import build_distribution, check_release

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"


def test_current_release_metadata_is_aligned() -> None:
    assert build_distribution.build(DISTRIBUTION, False) == 0
    result = check_release.validate()
    assert result["version"] == "2.2.0"
    assert (
        result["revision"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )


def test_release_check_rejects_package_version_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
    monkeypatch.setattr(check_release, "PORTABLE_PACKAGE", manifest)

    with pytest.raises(check_release.ReleaseError, match="versions differ"):
        check_release.validate()


def test_release_check_rejects_distribution_revision_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distribution = tmp_path / "distribution"
    distribution.mkdir()
    (distribution / "index.json").write_text(
        json.dumps({"version": "2.2.0", "source_revision": "0" * 40}), encoding="utf-8"
    )
    monkeypatch.setattr(check_release, "DISTRIBUTION", distribution)

    with pytest.raises(check_release.ReleaseError, match="revision"):
        check_release.validate()
