"""Profiles overlay locally, never hold secrets, and never read OCR's config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from reviewmatic import profiles
from reviewmatic.portable.portable_gitlab import contract


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def reviewer(alias: str, provider: str = "openai", model: str = "gpt-5") -> dict[str, str]:
    return {"alias": alias, "provider": provider, "model": model, "effort": "medium"}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setattr(profiles, "_git_root", lambda cwd: None)
    return home_dir


def test_a_missing_profile_is_reported(home: Path, tmp_path: Path) -> None:
    result = profiles.load(tmp_path)
    assert result["status"] == "missing"
    assert result["sources"] == []
    assert result["default"] is None


def test_the_local_file_overlays_the_global_one(home: Path, tmp_path: Path) -> None:
    write(
        home / ".reviewmatic" / "reviewers.json",
        {
            "default": "fast",
            "reviewers": [reviewer("fast"), reviewer("deep", "anthropic", "claude-opus-5")],
        },
    )
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {
            "default": "custom",
            "reviewers": [
                reviewer("custom", "deepseek", "deepseek-v3"),
                reviewer("fast", "xai", "grok-4"),
            ],
        },
    )
    result = profiles.load(tmp_path)
    by_alias = {item["alias"]: item for item in result["reviewers"]}
    assert result["default"] == "custom"
    assert by_alias["fast"]["provider"] == "xai"
    assert by_alias["fast"]["model"] == "grok-4"
    assert by_alias["deep"]["provider"] == "anthropic"
    assert result["sources"] == [
        str(home / ".reviewmatic" / "reviewers.json"),
        str(tmp_path / ".reviewmatic" / "reviewers.json"),
    ]


def test_the_global_default_survives_without_a_local_default(home: Path, tmp_path: Path) -> None:
    write(
        home / ".reviewmatic" / "reviewers.json",
        {"default": "fast", "reviewers": [reviewer("fast")]},
    )
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {"reviewers": [reviewer("deep", "anthropic", "claude-opus-5")]},
    )
    assert profiles.load(tmp_path)["default"] == "fast"


def test_secret_keys_are_rejected(home: Path, tmp_path: Path) -> None:
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {"reviewers": [{**reviewer("fast"), "api_key": "x"}]},
    )
    with pytest.raises(contract.WorkflowError, match="secrets"):
        profiles.load(tmp_path)


def test_unsupported_keys_are_rejected(home: Path, tmp_path: Path) -> None:
    write(tmp_path / ".reviewmatic" / "reviewers.json", {"reviewers": [], "extra": 1})
    with pytest.raises(contract.WorkflowError, match="unsupported keys"):
        profiles.load(tmp_path)


def test_a_default_must_name_a_reviewer(home: Path, tmp_path: Path) -> None:
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {"default": "missing", "reviewers": [reviewer("fast")]},
    )
    with pytest.raises(contract.WorkflowError, match="default"):
        profiles.load(tmp_path)


def test_the_ocr_configuration_is_never_opened(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = home / ".opencodereview" / "config.json"
    write(secret, {"provider": {"api_key": "do-not-read"}})
    opened: list[str] = []
    original = Path.open

    def tracking_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {"default": "fast", "reviewers": [reviewer("fast")]},
    )
    profiles.load(tmp_path)
    assert not any(".opencodereview" in path for path in opened)


def test_providers_are_validated_against_ocr(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "ocr"
    script.write_text(
        "#!/bin/sh\necho 'Built-in providers:'\n"
        "printf '  openai      openai  https://x\\n'\n"
        "printf '  anthropic   anthropic  https://y\\n'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    validation = profiles.validate_providers([reviewer("a"), reviewer("b", "custom-provider", "m")])
    assert validation["available"] is True
    assert "openai" in validation["providers"]
    assert validation["unknown"] == ["custom-provider"]


def test_select_resolves_aliases_and_the_default(home: Path, tmp_path: Path) -> None:
    write(
        tmp_path / ".reviewmatic" / "reviewers.json",
        {"default": "fast", "reviewers": [reviewer("fast"), reviewer("deep")]},
    )
    profile = profiles.load(tmp_path)
    assert profiles.select(profile, [])[0]["alias"] == "fast"
    assert [item["alias"] for item in profiles.select(profile, ["deep", "fast"])] == [
        "deep",
        "fast",
    ]
    with pytest.raises(contract.WorkflowError, match="unknown reviewer"):
        profiles.select(profile, ["missing"])


def test_the_git_root_is_the_second_local_candidate(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    nested = root / "src"
    nested.mkdir(parents=True)
    monkeypatch.setattr(profiles, "_git_root", lambda cwd: root)
    candidates = profiles.local_candidates(nested)
    assert candidates == [
        nested / ".reviewmatic" / "reviewers.json",
        root / ".reviewmatic" / "reviewers.json",
    ]
