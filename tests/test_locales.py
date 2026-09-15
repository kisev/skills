from __future__ import annotations

import json
import re
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
        if skill.is_dir() and (skill / "SKILL.source.md").is_file():
            assert not (skill / "references/ru").exists()
            assert not (skill / "references/en").exists()


def test_documentation_has_a_diataxis_index_and_compact_project_entrypoint() -> None:
    english_root = (ROOT / "README.md").read_text(encoding="utf-8")
    russian_root = (ROOT / "README.ru.md").read_text(encoding="utf-8")
    english_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    russian_index = (ROOT / "docs/ru/README.md").read_text(encoding="utf-8")

    assert len(english_root.splitlines()) < 100
    assert len(russian_root.splitlines()) < 100
    for document in (english_root, russian_root):
        assert "skills-opencode" in document
        assert "docs/" in document
    for document in (english_index, russian_index):
        assert all(
            heading in document
            for heading in ("## Tutorials", "## How-to", "## Reference", "## Explanation")
        )


def test_install_reconcile_documentation_covers_the_same_release_flow() -> None:
    english = (ROOT / "docs/how-to/opencode-integration.md").read_text(encoding="utf-8")
    russian = (ROOT / "docs/ru/how-to/opencode-integration.md").read_text(encoding="utf-8")
    for document in (english, russian):
        assert "npx --yes skills@latest" in document
        assert "install --dry-run" in document
        assert "reconcile" in document
        assert "plugin" in document
        assert "restart" in document or "перезапуск" in document
        assert "Skill command adapters" in document
        assert "Package command adapters" in document
        assert "npm install --save-exact @kisev/skills-opencode" in document
        assert "npx --yes @kisev/skills-opencode@latest" in document
        assert "npm exec -- skills-opencode" not in document
    assert "does not install, update, or remove portable" in english
    assert "не устанавливает, не обновляет и не" in russian

    package_english = (ROOT / "packages/opencode/README.md").read_text(encoding="utf-8")
    package_russian = (ROOT / "packages/opencode/README.ru.md").read_text(encoding="utf-8")
    assert "/docs/how-to/opencode-integration.md" in package_english
    assert "/docs/ru/how-to/opencode-integration.md" in package_russian
    for document in (package_english, package_russian):
        assert "npm install --save-exact @kisev/skills-opencode" in document
        assert "npx --yes @kisev/skills-opencode@latest" in document
        assert "npm exec -- skills-opencode" not in document


def test_current_user_documentation_uses_stable_cli_channels() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "README.ru.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "CONTRIBUTING.ru.md",
        ROOT / "packages/opencode/README.md",
        ROOT / "packages/opencode/README.ru.md",
        ROOT / "packages/skills/README.md",
        ROOT / "packages/skills/README.ru.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    numeric_pin = re.compile(r"(?:\bskills|@kisev/skills-opencode)@\d+\.\d+\.\d+")
    for path in documents:
        text = path.read_text(encoding="utf-8")
        assert not numeric_pin.search(text), path

    for path in (
        ROOT / "README.md",
        ROOT / "README.ru.md",
        ROOT / "docs/tutorials/getting-started.md",
        ROOT / "docs/ru/tutorials/getting-started.md",
        ROOT / "docs/how-to/portable-skills.md",
        ROOT / "docs/ru/how-to/portable-skills.md",
        ROOT / "docs/verification.md",
        ROOT / "docs/ru/verification.md",
    ):
        assert "npx --yes skills@latest" in path.read_text(encoding="utf-8"), path


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


def test_locale_checker_rejects_russian_self_link(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "en.md").write_text("[Русский](ru.md)\n", encoding="utf-8")
    (tmp_path / "ru.md").write_text(
        "[English](en.md) | [Русский](ru.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {"version": 1, "pairs": [{"en": "en.md", "ru": "ru.md"}], "patterns": [], "neutral": []}
        ),
        encoding="utf-8",
    )
    with pytest.raises(check_locales.LocaleError, match="links to itself"):
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
