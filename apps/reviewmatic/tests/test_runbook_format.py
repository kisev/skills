"""The runbook keeps its format with only the specified section changes."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
GOLDEN = Path(__file__).resolve().parent / "golden"
SKILL = ROOT / "skills" / "mr-review" / "references"

REQUIRED = (
    "Task fulfillment",
    "OCR runs",
    "Architecture assessment",
    "SemVer impact",
    "Checks",
    "Draft notes",
)
REMOVED = ("Local fixes", "Project labels", "MR metadata", "Manual publication preflight")


def fixtures() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8") for path in sorted(GOLDEN.glob("runbook-*.md"))
    }


def test_both_runbook_fixtures_exist() -> None:
    assert set(fixtures()) == {"runbook-one-run.md", "runbook-two-runs.md"}


@pytest.mark.parametrize("name", ["runbook-one-run.md", "runbook-two-runs.md"])
def test_required_sections_are_present(name: str) -> None:
    text = fixtures()[name]
    for section in REQUIRED:
        assert f"## {section}" in text, section


@pytest.mark.parametrize("name", ["runbook-one-run.md", "runbook-two-runs.md"])
def test_removed_sections_are_absent(name: str) -> None:
    text = fixtures()[name]
    for section in REMOVED:
        assert section not in text, section


def test_one_run_produces_no_arbitration() -> None:
    assert "Arbitration verdicts" not in fixtures()["runbook-one-run.md"]


def test_two_runs_record_every_arbitration_reason() -> None:
    text = fixtures()["runbook-two-runs.md"]
    assert "## Arbitration verdicts" in text
    normalized = " ".join(text.split())
    for reason in ("merged once", "Chosen severity", "out of scope"):
        assert reason in normalized


@pytest.mark.parametrize("name", ["runbook-one-run.md", "runbook-two-runs.md"])
def test_the_draft_block_checks_the_head_and_never_publishes(name: str) -> None:
    text = fixtures()[name]
    block = text[text.index("## Draft notes") :]
    assert "reviewed_head=" in block
    assert "current_head=$(glab api" in block
    assert "exit 1" in block
    assert "--method POST" in block
    assert "publish" not in block.lower()


def test_the_output_reference_lists_the_same_sections() -> None:
    reference = (SKILL / "output-format.md").read_text(encoding="utf-8")
    for section in REQUIRED:
        assert section in reference, section
    for section in REMOVED:
        assert section in reference, "the reference must name what the runbook omits"


def test_the_fixtures_are_authored_not_runtime_output() -> None:
    readme = (GOLDEN / "README.md").read_text(encoding="utf-8")
    assert "not runtime output" in readme
    assert "not regenerated" in readme
