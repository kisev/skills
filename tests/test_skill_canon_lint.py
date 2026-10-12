"""Contract tests for the fast skill-canon preselect (scripts/check_skill_canon.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import check_skill_canon

ROOT = Path(__file__).resolve().parents[1]


def test_canon_lint_passes_on_the_repository() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_skill_canon.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_skill_source_scan_flags_cyrillic_outside_discovery_terms(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "demo"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.source.md").write_text(
        "---\nname: demo\ndescription: d\nRussian discovery terms: демо\n---\n"
        "English body with кириллица inside.\n",
        encoding="utf-8",
    )
    (skill / "references" / "workflow.md").write_text("English workflow.\n", encoding="utf-8")
    violations = check_skill_canon.skill_source_violations(tmp_path / "skills")

    assert any("cyrillic in the canonical body" in item for item in violations)

    (skill / "SKILL.source.md").write_text(
        "---\nname: demo\ndescription: d\nRussian discovery terms: демо\n---\nEnglish body.\n",
        encoding="utf-8",
    )
    (skill / "references" / "workflow.md").write_text(
        "Workflow with «дальше без вопросов» leaked.\n", encoding="utf-8"
    )
    violations = check_skill_canon.skill_source_violations(tmp_path / "skills")

    assert violations == ["skills/demo/references/workflow.md: cyrillic in the workflow"]


def test_localized_string_data_exemptions_keep_prose_checked() -> None:
    source = (
        "# cyrillic comment должен быть виден\n"
        'CARD = {"title": "Локализованная карточка"}\n'
        'PLAIN = "Обычная строка данных"\n'
    )
    stripped = check_skill_canon.strip_localized_string_data(source)

    assert "Локализованная карточка" not in stripped
    assert "Обычная строка данных" not in stripped
    assert "должен быть виден" in stripped


def test_byte_caps_flag_oversized_references(tmp_path: Path) -> None:
    capped = tmp_path / "skills/spec-manage/references/openspec.md"
    capped.parent.mkdir(parents=True)
    capped.write_bytes(
        b"x" * (check_skill_canon.BYTE_CAPS[capped.relative_to(tmp_path).as_posix()] + 1)
    )
    violations = check_skill_canon.cap_violations(tmp_path)

    assert violations == [
        "skills/spec-manage/references/openspec.md: 16385 bytes exceeds the 16384 cap"
    ]
