from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUNNER = ROOT / "skills/spec-manage/scripts/spec_validate.py"
BUILT_RUNNER = ROOT / ".build/skills/spec-manage/scripts/spec_validate.py"
REQUIRED_READMES = (
    "README.md",
    "requirements/README.md",
    "requirements/functional/README.md",
    "requirements/interfaces/README.md",
    "requirements/quality/README.md",
    "requirements/constraints/README.md",
    "architecture/README.md",
    "architecture/01-introduction-and-goals/README.md",
    "architecture/02-architecture-constraints/README.md",
    "architecture/03-context-and-scope/README.md",
    "architecture/04-solution-strategy/README.md",
    "architecture/05-building-block-view/README.md",
    "architecture/06-runtime-view/README.md",
    "architecture/07-deployment-view/README.md",
    "architecture/08-crosscutting-concepts/README.md",
    "architecture/09-architecture-decisions/README.md",
    "architecture/10-quality-requirements/README.md",
    "architecture/11-risks-and-technical-debt/README.md",
    "architecture/12-glossary/README.md",
)


def run_validator(
    *arguments: str, runner: Path = SOURCE_RUNNER
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(runner), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def parse_result(process: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert process.stderr == ""
    value = json.loads(process.stdout)
    assert isinstance(value, dict)
    return value


@pytest.fixture
def specs_factory(tmp_path: Path) -> Callable[[str], Path]:
    def create(name: str) -> Path:
        root = tmp_path / name
        for relative in REQUIRED_READMES:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = "# Section\n"
            if relative == "README.md":
                content = "# Specs\n\nCanonical language: English\n"
            path.write_text(content, encoding="utf-8")
        return root

    return create


def add_requirement(root: Path, identifier: str) -> None:
    path = root / "requirements/functional/README.md"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n### {identifier} - Test requirement\n\nThe system shall behave.\n")


def add_adr(root: Path, number: int, slug: str = "test-decision") -> None:
    identifier = f"ADR-{number:04d}"
    filename = f"{number:04d}-{slug}.md"
    directory = root / "architecture/09-architecture-decisions"
    (directory / filename).write_text(f"# {identifier}: Test decision\n", encoding="utf-8")
    with (directory / "README.md").open("a", encoding="utf-8") as stream:
        stream.write(f"\n- [{identifier}: Test decision]({filename})\n")


def test_check_accepts_valid_snapshot_and_is_stable(
    specs_factory: Callable[[str], Path],
) -> None:
    specs = specs_factory("valid")
    add_requirement(specs, "REQ-F-001")
    add_adr(specs, 1)
    first = run_validator("check", "--path", str(specs))
    second = run_validator("check", "--path", str(specs))

    assert first.returncode == 0
    assert first.stdout == second.stdout
    result = parse_result(first)
    assert result == {
        "schema_version": "spec-validate/v1",
        "mode": "check",
        "status": "valid",
        "checks": {"snapshot": "passed", "lifecycle": "not_checked"},
        "findings": [],
        "errors": [],
    }
    assert str(specs) not in first.stdout


def test_check_reports_closed_snapshot_invariants_in_stable_order(
    specs_factory: Callable[[str], Path],
) -> None:
    specs = specs_factory("invalid")
    (specs / "architecture/12-glossary/README.md").unlink()
    (specs / "README.md").write_text(
        "# Specs\n\nCanonical language: PROJECT-LANGUAGE\n\n[Missing](missing.md)\n",
        encoding="utf-8",
    )
    add_requirement(specs, "REQ-F-001")
    with (specs / "requirements/quality/README.md").open("a", encoding="utf-8") as stream:
        stream.write("\n### REQ-F-001 - Duplicate\n\n### REQ-Z-1 - Invalid\n")
    directory = specs / "architecture/09-architecture-decisions"
    (directory / "0001-Bad.md").write_text("# ADR-0002: Wrong\n", encoding="utf-8")

    process = run_validator("check", "--path", str(specs))

    assert process.returncode == 1
    result = parse_result(process)
    assert result["status"] == "invalid"
    assert result["checks"] == {"snapshot": "failed", "lifecycle": "not_checked"}
    findings = result["findings"]
    keys = [(item["code"], item["path"], item["line"], item["column"]) for item in findings]
    assert keys == sorted(keys)
    assert {item["code"] for item in findings} >= {
        "SNAPSHOT_ADR_FILENAME_INVALID",
        "SNAPSHOT_LANGUAGE_DECLARATION_EMPTY",
        "SNAPSHOT_LINK_TARGET_MISSING",
        "SNAPSHOT_REQUIRED_FILE_MISSING",
        "SNAPSHOT_REQUIREMENT_DECLARATION_INVALID",
        "SNAPSHOT_REQUIREMENT_DUPLICATE",
        "SNAPSHOT_TEMPLATE_PLACEHOLDER",
    }
    assert all(not Path(item["path"]).is_absolute() for item in findings)


def test_check_validates_extension_index_and_adr_correspondence(
    specs_factory: Callable[[str], Path],
) -> None:
    specs = specs_factory("extensions")
    extension = specs / "capabilities/README.md"
    extension.parent.mkdir()
    extension.write_text("# Capabilities\n", encoding="utf-8")
    add_adr(specs, 1)
    index = specs / "architecture/09-architecture-decisions/README.md"
    index.write_text("# Decisions\n\n- [ADR-0001: Wrong](0002-wrong.md)\n", encoding="utf-8")

    invalid = run_validator("check", "--path", str(specs))

    assert invalid.returncode == 1
    codes = {item["code"] for item in parse_result(invalid)["findings"]}
    assert "SNAPSHOT_EXTENSION_NOT_INDEXED" in codes
    assert "SNAPSHOT_ADR_INDEX_TARGET_MISMATCH" in codes
    readme = specs / "README.md"
    with readme.open("a", encoding="utf-8") as stream:
        stream.write(
            "\n## Extension Index\n\n"
            "- [Capabilities](capabilities/README.md): Public capability inventory.\n"
        )
    index.write_text(
        "# Decisions\n\n- [ADR-0001: Test decision](0001-test-decision.md)\n",
        encoding="utf-8",
    )

    assert run_validator("check", "--path", str(specs)).returncode == 0


def test_lifecycle_accepts_preserved_ids_above_each_baseline_maximum(
    specs_factory: Callable[[str], Path],
) -> None:
    baseline = specs_factory("baseline")
    candidate = specs_factory("candidate")
    for root in (baseline, candidate):
        add_requirement(root, "REQ-F-005")
        add_requirement(root, "REQ-Q-009")
        add_adr(root, 7)
    add_requirement(candidate, "REQ-F-006")
    add_requirement(candidate, "REQ-Q-010")
    add_adr(candidate, 8, "new-decision")

    process = run_validator("lifecycle", "--baseline", str(baseline), "--candidate", str(candidate))

    assert process.returncode == 0
    result = parse_result(process)
    assert result["checks"] == {"snapshot": "not_checked", "lifecycle": "passed"}
    assert result["findings"] == []


def test_lifecycle_reports_removed_and_reused_ids(
    specs_factory: Callable[[str], Path],
) -> None:
    baseline = specs_factory("baseline-invalid")
    candidate = specs_factory("candidate-invalid")
    add_requirement(baseline, "REQ-F-005")
    add_requirement(baseline, "REQ-Q-009")
    add_adr(baseline, 7)
    add_requirement(candidate, "REQ-F-004")
    add_adr(candidate, 6)

    process = run_validator("lifecycle", "--baseline", str(baseline), "--candidate", str(candidate))

    assert process.returncode == 1
    result = parse_result(process)
    assert result["checks"] == {"snapshot": "not_checked", "lifecycle": "failed"}
    assert {item["code"] for item in result["findings"]} == {
        "LIFECYCLE_ADR_NUMBER_REUSED",
        "LIFECYCLE_ADR_REMOVED",
        "LIFECYCLE_REQUIREMENT_NUMBER_REUSED",
        "LIFECYCLE_REQUIREMENT_REMOVED",
    }


@pytest.mark.parametrize("arguments", [(), ("check",), ("unknown",)])
def test_invocation_errors_are_one_json_document(arguments: tuple[str, ...]) -> None:
    process = run_validator(*arguments)

    if not arguments:
        assert process.returncode == 0
        assert parse_result(process)["mode"] == "help"
    else:
        assert process.returncode == 2
        result = parse_result(process)
        assert result["status"] == "error"
        assert result["findings"] == []


def test_help_is_json_and_documents_both_commands() -> None:
    process = run_validator("--help")

    assert process.returncode == 0
    result = parse_result(process)
    assert result["schema_version"] == "spec-validate/v1"
    assert "check --path <specs>" in result["usage"]
    assert "lifecycle --baseline <previous-specs>" in result["usage"]


def test_unsafe_and_invalid_inputs_exit_two(
    tmp_path: Path, specs_factory: Callable[[str], Path]
) -> None:
    missing = run_validator("check", "--path", str(tmp_path / "missing"))
    assert missing.returncode == 2
    assert parse_result(missing)["errors"][0]["code"] == "INVALID_PATH"

    invalid_utf8 = specs_factory("invalid-utf8")
    (invalid_utf8 / "bad.txt").write_bytes(b"\xff")
    invalid = run_validator("check", "--path", str(invalid_utf8))
    assert invalid.returncode == 2
    assert parse_result(invalid)["errors"][0]["code"] == "INVALID_UTF8"

    symlink_specs = specs_factory("symlink")
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    os.symlink(outside, symlink_specs / "outside.md")
    unsafe = run_validator("check", "--path", str(symlink_specs))
    assert unsafe.returncode == 2
    result = parse_result(unsafe)
    assert result["errors"][0]["code"] == "UNSAFE_PATH"
    assert str(tmp_path) not in unsafe.stdout


def test_local_link_escape_is_a_validation_finding(
    specs_factory: Callable[[str], Path],
) -> None:
    specs = specs_factory("link-escape")
    with (specs / "README.md").open("a", encoding="utf-8") as stream:
        stream.write("\n[Outside](../outside.md)\n")

    process = run_validator("check", "--path", str(specs))

    assert process.returncode == 1
    assert parse_result(process)["findings"][0]["code"] == "SNAPSHOT_LINK_OUTSIDE_ROOT"


def test_runner_is_materialized_exactly() -> None:
    assert BUILT_RUNNER.is_file()
    assert BUILT_RUNNER.read_bytes() == SOURCE_RUNNER.read_bytes()

    process = run_validator("--help", runner=BUILT_RUNNER)
    assert process.returncode == 0
    assert parse_result(process)["schema_version"] == "spec-validate/v1"
