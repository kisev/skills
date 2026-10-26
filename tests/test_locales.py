from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import check_locales
from tests.pins import assert_pin

ROOT = Path(__file__).resolve().parents[1]


def test_locale_manifest_validates_english_default_pairs() -> None:
    assert check_locales.validate() >= 26


def test_changelog_has_separate_english_and_russian_versions() -> None:
    english = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    russian = (ROOT / "CHANGELOG.ru.md").read_text(encoding="utf-8")

    assert english.startswith("# Changelog\n")
    assert russian.startswith("# История изменений\n")
    assert "[Русская версия](CHANGELOG.ru.md)" in english
    assert "[English version](CHANGELOG.md)" in russian
    assert "[Keep a Changelog](https://keepachangelog.com/en/1.1.0/)" in english
    assert "[Semantic Versioning](https://semver.org/)" in english
    assert "### Добавлено" not in english
    assert "### Added" not in russian


def test_security_policy_has_separate_english_and_russian_versions() -> None:
    english = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    russian = (ROOT / "SECURITY.ru.md").read_text(encoding="utf-8")

    assert english.startswith("# Security Policy\n")
    assert russian.startswith("# Политика безопасности\n")
    assert "[Русский](SECURITY.ru.md)" in english
    assert "[English](SECURITY.md)" in russian


def _missed_defect_registry(text: str, heading: str) -> str:
    assert heading in text, "missed-defect registry section was removed"
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end >= 0 else len(text)]


def test_missed_defect_registry_exists_in_both_locales_and_lists_all_classes() -> None:
    english = _missed_defect_registry(
        (ROOT / "docs/verification.md").read_text(encoding="utf-8"),
        "## Missed-defect Registry",
    )
    russian = _missed_defect_registry(
        (ROOT / "docs/ru/verification.md").read_text(encoding="utf-8"),
        "## Реестр пропущенных дефектов",
    )

    commits = ("b5cf464", "204714f")
    for commit in commits:
        assert commit in english, commit
        assert commit in russian, commit
    for path in (
        "tests/test_application_workflows.py",
        "apps/reviewmatic/tests/test_context_package_records.py",
        "apps/reviewmatic/tests/test_local_review_scenarios.py",
    ):
        assert path in english, path
        assert path in russian, path
    for guard in ("streamed_glab_trace", "_shared_context_inputs"):
        assert guard in english, guard
        assert guard in russian, guard
    for locale, covered, closed, mutation_check in (
        (english, "covered", "closed by PORT-3", "Proof by removal"),
        (russian, "покрыты", "закрыто в PORT-3", "Проверка удалением"),
    ):
        assert covered in locale
        assert closed in locale
        assert mutation_check in locale
    for invariant in (
        "question_context_digest",
        "question_context_version",
        "is_current_result",
    ):
        assert invariant in english, invariant
        assert invariant in russian, invariant


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

    assert len(english_root.splitlines()) < 150
    assert len(russian_root.splitlines()) < 150
    for document in (english_root, russian_root):
        assert "skillmate" in document
        assert "docs/" in document
    assert all(
        heading in english_index
        for heading in ("## Tutorials", "## How-to Guides", "## Reference", "## Explanation")
    )
    assert all(
        heading in russian_index
        for heading in (
            "## Учебные материалы",
            "## Практические руководства",
            "## Справочник",
            "## Объяснение",
        )
    )


def test_integration_documentation_covers_the_same_scenario_cli_flow() -> None:
    english = (ROOT / "docs/how-to/install-skills.md").read_text(encoding="utf-8")
    russian = (ROOT / "docs/ru/how-to/install-skills.md").read_text(encoding="utf-8")
    for document in (english, russian):
        assert "uvx skillmate install" in document
        assert "--hosts claude,opencode" in document
        assert "--scope global" in document
        assert "--skill commit-msg" in document
        assert "uvx skillmate update --version" in document
        assert "uvx skillmate remove --yes" in document
        assert "--confirm-drift" in document
        assert "uvx skillmate doctor" in document
        assert "uvx skillmate status" in document
        assert "--from-checkout /path/to/skills --yes" in document
        assert ".agents/skills/" in document
        assert "~/.claude/skills/" in document
        assert "~/.config/opencode/skills/" in document
        assert "duplicate" in document or "дубликат" in document or "дублирующуюся" in document
        assert "uvx skillmate install --yes" in document
    assert_pin(english, "never falls back to a guessed source", "english")
    assert_pin(russian, "не подменяет источник догадкой", "russian")


def test_current_user_documentation_uses_stable_cli_channels() -> None:
    documents = [
        ROOT / "README.md",
        ROOT / "README.ru.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "CONTRIBUTING.ru.md",
        ROOT / "packages/skills/README.md",
        ROOT / "packages/skills/README.ru.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    numeric_pin = re.compile(r"\bskills@\d+\.\d+\.\d+|@kisev/agentomatic")
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


def test_locale_checker_rejects_different_markdown_blocks(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    (tmp_path / "en.md").write_text(
        "# English\n\n[Русский](ru.md)\n\n- First.\n- Second.\n",
        encoding="utf-8",
    )
    (tmp_path / "ru.md").write_text(
        "# Русский\n\n[English](en.md)\n\nОдин абзац.\n",
        encoding="utf-8",
    )
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps(
            {"version": 1, "pairs": [{"en": "en.md", "ru": "ru.md"}], "patterns": [], "neutral": []}
        ),
        encoding="utf-8",
    )
    with pytest.raises(check_locales.LocaleError, match="block structure"):
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


def _write_pair_tree(
    tmp_path: Path, english_body: str, russian_body: str, pair_extra: dict[str, object] | None
) -> None:
    (tmp_path / "shared").mkdir(exist_ok=True)
    pair: dict[str, object] = {"en": "en.md", "ru": "ru.md"}
    if pair_extra:
        pair.update(pair_extra)
    (tmp_path / "shared/locale-manifest.json").write_text(
        json.dumps({"version": 1, "pairs": [pair], "patterns": [], "neutral": []}),
        encoding="utf-8",
    )
    (tmp_path / "en.md").write_text(
        "# Title\n\n[Русский](ru.md)\n\n" + english_body, encoding="utf-8"
    )
    (tmp_path / "ru.md").write_text(
        "# Заголовок\n\n[English](en.md)\n\n" + russian_body, encoding="utf-8"
    )


def test_locale_checker_rejects_glued_quote_markers(tmp_path: Path) -> None:
    _write_pair_tree(
        tmp_path,
        "> Wrapped quote line glued > by a formatter accident.\n",
        "> Строка цитаты со склейкой > от форматтера.\n",
        None,
    )
    with pytest.raises(check_locales.LocaleError, match="glued '>' markers"):
        check_locales.validate(tmp_path)


def test_locale_checker_enforces_shared_example_quotes(tmp_path: Path) -> None:
    _write_pair_tree(
        tmp_path,
        "> Shared example sentence.\n",
        "> Другой текст примера.\n",
        {"shared_quotes": True},
    )
    with pytest.raises(check_locales.LocaleError, match="shared example quotes differ"):
        check_locales.validate(tmp_path)
    (tmp_path / "ru.md").write_text(
        "# Заголовок\n\n[English](en.md)\n\n> Shared example sentence.\n", encoding="utf-8"
    )
    assert check_locales.validate(tmp_path) == 1


def test_locale_checker_rejects_back_to_back_repeated_sentences(tmp_path: Path) -> None:
    _write_pair_tree(
        tmp_path,
        "> One sentence pasted twice. One sentence pasted twice.\n",
        "> Одно предложение вставлено дважды. Одно предложение вставлено дважды.\n",
        None,
    )
    with pytest.raises(check_locales.LocaleError, match="repeats a sentence back to back"):
        check_locales.validate(tmp_path)
    # Non-adjacent repeats (dramatic closers) stay legitimate.
    _write_pair_tree(
        tmp_path,
        "> Statement one. Вот ценность. Statement two. Вот ценность.\n",
        "> Утверждение раз. Вот ценность. Утверждение два. Вот ценность.\n",
        None,
    )
    assert check_locales.validate(tmp_path) == 1
