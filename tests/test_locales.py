from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_locales


ROOT = Path(__file__).resolve().parents[1]


def test_locale_manifest_validates_english_default_pairs() -> None:
    assert check_locales.validate() >= 26


def test_project_spec_russian_templates_match_all_default_templates() -> None:
    templates = ROOT / "skills/spec-manage/templates"
    default_templates = [path for path in templates.rglob("*.md") if "/ru/" not in path.as_posix()]
    assert default_templates
    for default in default_templates:
        assert (templates / "ru" / default.relative_to(templates)).is_file(), default


def test_skills_use_single_canonical_workflow_without_locale_directories() -> None:
    for skill in (ROOT / "skills").iterdir():
        if skill.is_dir() and (skill / "SKILL.md").is_file():
            assert not (skill / "references/ru").exists()
            assert not (skill / "references/en").exists()


def test_install_reconcile_documentation_covers_the_same_release_flow() -> None:
    english = (ROOT / "packages/opencode/README.md").read_text(encoding="utf-8")
    russian = (ROOT / "packages/opencode/README.ru.md").read_text(encoding="utf-8")
    for document in (english, russian):
        assert "2.0.5" in document
        assert "skills@1.5.23" in document
        assert "install --dry-run" in document
        assert "reconcile" in document
        assert "plugin" in document
        assert "restart" in document or "перезапуск" in document
        assert "Skill command adapters" in document
        assert "Package command adapters" in document
    assert "does not install, update, or remove portable" in english
    assert "не устанавливает, не обновляет и не" in russian


def test_locale_checker_rejects_duplicate_neutral_path(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {"version": 1, "pairs": [], "patterns": [], "neutral": ["README.md", "README.md"]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(check_locales.LocaleError, match="neutral paths"):
        check_locales.validate(tmp_path)


def test_machine_token_fixture_allows_translated_prose_and_rejects_drift(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    en, ru = tmp_path / "en.md", tmp_path / "ru.md"
    en.write_text(
        "Run `task locale:check` with `report_path`.\n",
        encoding="utf-8",
    )
    ru.write_text(
        "Запустите `task locale:check` с `report_path`.\n",
        encoding="utf-8",
    )
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {"version": 1, "pairs": [{"en": "en.md", "ru": "ru.md"}], "patterns": [], "neutral": []}
        ),
        encoding="utf-8",
    )
    en.write_text(en.read_text(encoding="utf-8") + "[Русский](ru.md)\n", encoding="utf-8")
    ru.write_text(ru.read_text(encoding="utf-8") + "[English](en.md)\n", encoding="utf-8")
    assert check_locales.validate(tmp_path) == 1
    ru.write_text("[English](en.md)\nUse `other_path`.\n", encoding="utf-8")
    with pytest.raises(check_locales.LocaleError, match="machine tokens"):
        check_locales.validate(tmp_path)


def test_locale_checker_rejects_language_link_with_wrong_target(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "en.md").write_text("[Русский](en.md)\n", encoding="utf-8")
    (tmp_path / "ru.md").write_text("[English](en.md)\n", encoding="utf-8")
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {"version": 1, "pairs": [{"en": "en.md", "ru": "ru.md"}], "patterns": [], "neutral": []}
        ),
        encoding="utf-8",
    )
    with pytest.raises(check_locales.LocaleError, match="reciprocal language link"):
        check_locales.validate(tmp_path)


def test_locale_checker_rejects_orphan_russian_suffix_and_abbreviated_sections(
    tmp_path: Path,
) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "README.md").write_text(
        "# English\n\n[Русский](README.ru.md)\n\n## Details\n", encoding="utf-8"
    )
    (tmp_path / "README.ru.md").write_text("# Русский\n\n[English](README.md)\n", encoding="utf-8")
    (tmp_path / "orphan.ru.md").write_text("# Сирота\n", encoding="utf-8")
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "pairs": [{"en": "README.md", "ru": "README.ru.md"}],
                "patterns": [],
                "neutral": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(check_locales.LocaleError, match="section structure"):
        check_locales.validate(tmp_path)
    (tmp_path / "README.ru.md").write_text(
        "# Русский\n\n[English](README.md)\n\n## Подробнее\n", encoding="utf-8"
    )
    with pytest.raises(check_locales.LocaleError, match="orphan Russian"):
        check_locales.validate(tmp_path)
