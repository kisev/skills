"""The helper command surface is the whole runtime."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from reviewmatic import __version__, cli

EXPECTED = {
    "collect",
    "background",
    "drafts",
    "revalidate",
    "profiles",
    "ocr-runs",
    "ocr-compare",
    "runtime-info",
}


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "reviewmatic", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_public_surface_is_exactly_the_helper_commands() -> None:
    names = {definition.signature.split()[0] for definition in cli.DEFINITIONS}
    assert names == EXPECTED


def test_help_exposes_only_the_helper_surface() -> None:
    completed = run_cli("--help")
    assert completed.returncode == 0
    for name in EXPECTED:
        assert name in completed.stdout
    for removed in (
        "run",
        "start-review",
        "finish-review",
        "prepare-local",
        "repair-review",
        "record-critic",
        "record-arbitration",
        "profile-setup",
        "marker-run",
        "publication",
    ):
        assert removed not in completed.stdout.split()


def test_removed_commands_are_rejected() -> None:
    for removed in ("run", "start-review", "prepare-local", "record-critic", "profile-setup"):
        completed = run_cli(removed)
        assert completed.returncode != 0, removed


def test_every_definition_option_is_real() -> None:
    for definition in cli.DEFINITIONS:
        name = definition.signature.split()[0]
        completed = run_cli(name, "--help")
        assert completed.returncode == 0, name
        for option in definition.options:
            assert f"--{option.name}" in completed.stdout, f"{name} --{option.name}"


def test_without_a_profile_or_one_off_ocr_uses_its_configured_default() -> None:
    namespace = cli.build_parser().parse_args(
        [
            "ocr-runs",
            "--repo",
            ".",
            "--from",
            "a",
            "--to",
            "b",
            "--background",
            "bg.md",
            "--output-dir",
            "out",
        ]
    )
    assert cli._resolve_reviewers(namespace) == [
        {"alias": "configured", "provider": "", "model": "", "effort": "medium"}
    ]


def test_runtime_info_reports_the_runtime() -> None:
    completed = run_cli("runtime-info")
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["version"] == __version__
    assert "commit" in payload
    assert payload["external_mutations"] is False


def test_resolve_install_source_reads_the_nested_pep610_form() -> None:
    text = json.dumps(
        {
            "url": "https://example.invalid/repo",
            "vcs_info": {"vcs": "git", "commit_id": "a" * 40},
        }
    )
    assert cli.resolve_install_source(text)["commit"] == "a" * 40


def test_resolve_install_source_recovers_a_pinned_url() -> None:
    text = json.dumps({"url": f"git+https://example.invalid/repo@{'b' * 40}"})
    assert cli.resolve_install_source(text)["commit"] == "b" * 40


@pytest.mark.parametrize("text", [None, "not json", "[]", "{}"])
def test_resolve_install_source_is_honest_about_unknown(text: str | None) -> None:
    assert cli.resolve_install_source(text)["commit"] == "unknown"
