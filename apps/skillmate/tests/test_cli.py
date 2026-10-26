"""CLI contract: parsing, preview-before-write, lifecycle end to end.

Runs against the fixture distribution through a ``file://`` index URL, so
every test is offline and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from skillmate.cli import main

FIXTURE = (Path(__file__).parent / "fixtures" / "distribution" / "index.json").as_uri()
FIXTURE_V2 = (Path(__file__).parent / "fixtures" / "distribution-v2" / "index.json").as_uri()


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    assert main(argv) == 0
    document: dict[str, Any] = json.loads(capsys.readouterr().out)
    return document


def test_help_and_version_have_no_side_effects(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    for argv in (["--help"], ["install", "--help"], ["--version"]):
        with pytest.raises(SystemExit) as caught:
            main(argv)
        assert caught.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()
    assert list(tmp_path.iterdir()) == []


def test_install_previews_without_yes_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _run(
        ["install", "--json", "--index-url", FIXTURE, "--project-dir", str(tmp_path)], capsys
    )
    assert document["executed"] is False
    assert document["source"] == "distribution"
    assert document["target_version"] == "11.0.0"
    assert not (tmp_path / ".claude").exists()


def test_install_with_yes_writes_all_hosts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _run(
        [
            "install",
            "--json",
            "--yes",
            "--index-url",
            FIXTURE,
            "--project-dir",
            str(tmp_path),
        ],
        capsys,
    )
    assert document["executed"] is True
    assert len(document["reports"]) == 3
    assert (tmp_path / ".claude/skills/alpha/SKILL.md").is_file()
    assert (tmp_path / ".agents/skills/alpha/SKILL.md").is_file()
    assert (tmp_path / ".opencode/skills/alpha/SKILL.md").is_file()
    assert (tmp_path / ".claude/commands/alpha.md").is_file()
    assert not (tmp_path / ".agents/commands/alpha.md").exists()


def test_codex_copy_carries_the_dollar_dialect(tmp_path: Path) -> None:
    assert (
        main(
            [
                "install",
                "--json",
                "--yes",
                "--hosts",
                "codex",
                "--skill",
                "alpha",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert (tmp_path / ".agents/skills/alpha/SKILL.md").is_file()


def test_config_file_selects_hosts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"hosts": "claude"}), encoding="utf-8")
    document = _run(
        [
            "install",
            "--json",
            "--yes",
            "--config",
            str(config),
            "--index-url",
            FIXTURE,
            "--project-dir",
            str(tmp_path),
        ],
        capsys,
    )
    assert document["hosts"] == ["claude"]
    assert (tmp_path / ".claude/skills/alpha/SKILL.md").is_file()
    assert not (tmp_path / ".opencode").exists()


def test_update_moves_to_the_new_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install = ["install", "--json", "--yes", "--index-url", FIXTURE, "--project-dir", str(tmp_path)]
    assert main(install) == 0
    capsys.readouterr()
    document = _run(
        [
            "update",
            "--json",
            "--yes",
            "--index-url",
            FIXTURE_V2,
            "--project-dir",
            str(tmp_path),
        ],
        capsys,
    )
    assert document["target_version"] == "11.1.0"
    assert (tmp_path / ".claude/skills/alpha/SKILL.md").read_bytes().endswith(b"Alpha body v2.\n")
    assert (tmp_path / ".claude/skills/beta/extra.md").is_file()


def test_remove_takes_back_only_owned_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["install", "--json", "--yes", "--index-url", FIXTURE, "--project-dir", str(tmp_path)])
        == 0
    )
    foreign = tmp_path / ".claude/skills/other/SKILL.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"foreign")
    capsys.readouterr()
    document = _run(["remove", "--json", "--yes", "--project-dir", str(tmp_path)], capsys)
    assert document["executed"] is True
    assert not (tmp_path / ".claude/skills/alpha").exists()
    assert not (tmp_path / ".claude/commands").exists()
    assert foreign.read_bytes() == b"foreign"


def test_doctor_names_broken_installations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "doctor",
                "--json",
                "--hosts",
                "claude",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    kinds = {finding["kind"] for finding in document["findings"]}
    assert kinds == {"not-installed"}
    assert (
        main(
            [
                "install",
                "--json",
                "--yes",
                "--hosts",
                "claude",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    (tmp_path / ".claude/skills/alpha/SKILL.md").unlink()
    assert (
        main(
            [
                "doctor",
                "--json",
                "--hosts",
                "claude",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    kinds = {finding["kind"] for finding in document["findings"]}
    assert kinds == {"missing-file"}
    repair = document["findings"][0]["repair"]
    assert "skillmate update" in repair


def test_doctor_reports_foreign_files_at_distribution_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "install",
                "--json",
                "--yes",
                "--hosts",
                "claude",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    foreign = tmp_path / ".claude/skills/beta/extra.md"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("not skillmate's file\n", encoding="utf-8")
    document = _run(
        [
            "doctor",
            "--json",
            "--hosts",
            "claude",
            "--index-url",
            FIXTURE_V2,
            "--project-dir",
            str(tmp_path),
        ],
        capsys,
    )
    finding = next(item for item in document["findings"] if item["kind"] == "foreign-path")
    assert "skills/beta/extra.md" in finding["detail"]
    assert "skillmate update --hosts claude" in finding["repair"]


def test_status_reports_installed_versions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "install",
                "--json",
                "--yes",
                "--hosts",
                "claude",
                "--index-url",
                FIXTURE,
                "--project-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    document = _run(["status", "--json", "--project-dir", str(tmp_path)], capsys)
    record = document["records"][0]
    assert record == {
        "host": "claude",
        "scope": "project",
        "version": "11.0.0",
        "source": "distribution",
        "files": 5,
    }


def test_unreachable_source_fails_loudly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = (tmp_path / "missing" / "index.json").as_uri()
    assert main(["install", "--json", "--index-url", missing, "--project-dir", str(tmp_path)]) == 1
    assert "cannot fetch" in capsys.readouterr().err


def test_version_and_checkout_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["install", "--from-checkout", "/tmp/repo", "--version", "1.0.0"])
    assert caught.value.code == 2


def test_unknown_option_fails() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["install", "--nope"])
    assert caught.value.code == 2
