from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/spec-manage"
ARCHITECTURE = SKILL / "templates/specs/architecture"
ARCHITECTURE_RU = SKILL / "templates/ru/specs/architecture"

VIEW_MARKERS = {
    "01-introduction-and-goals": ("stakeholders", "заинтересованных сторон"),
    "02-architecture-constraints": ("REQ-C-*", "REQ-C-*"),
    "03-context-and-scope": ("external subjects", "Внешние субъекты"),
    "04-solution-strategy": ("fundamental design choices", "фундаментальных проектных решений"),
    "05-building-block-view": ("dependency direction", "направление зависимостей"),
    "06-runtime-view": ("terminal conditions", "терминальные условия"),
    "07-deployment-view": ("network exposure", "сетевая доступность"),
    "08-crosscutting-concepts": (
        "sensitive-data lifecycle",
        "жизненный цикл чувствительных данных",
    ),
    "09-architecture-decisions": ("append-only history", "монотонную историю"),
    "10-quality-requirements": ("measurable security", "измеримые свойства безопасности"),
    "11-risks-and-technical-debt": ("fragile assumptions", "хрупкие предположения"),
    "12-glossary": ("canonical meaning", "каноническое значение"),
}


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n\n(?P<body>.*?)(?=\n## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, heading
    return match.group("body").strip()


def test_all_architecture_view_templates_are_specialized_and_mirrored() -> None:
    expected = set(VIEW_MARKERS)
    english = {path.parent.name for path in ARCHITECTURE.glob("*/README.md")}
    russian = {path.parent.name for path in ARCHITECTURE_RU.glob("*/README.md")}
    assert english == expected
    assert russian == expected

    purposes: set[str] = set()
    for name, (english_marker, russian_marker) in VIEW_MARKERS.items():
        english_text = (ARCHITECTURE / name / "README.md").read_text(encoding="utf-8")
        russian_text = (ARCHITECTURE_RU / name / "README.md").read_text(encoding="utf-8")
        for heading in (
            "Purpose",
            "Included",
            "Excluded",
            "Decomposition Rules",
            "Content Template",
        ):
            assert section(english_text, heading)
        for heading in (
            "Назначение",
            "Включено",
            "Исключено",
            "Правила декомпозиции",
            "Шаблон содержания",
        ):
            assert section(russian_text, heading)
        assert english_marker in english_text, name
        assert russian_marker in russian_text, name
        purposes.add(section(english_text, "Purpose"))

    assert len(purposes) == 12
    assert "Describe the canonical target state supported by verified evidence." not in "\n".join(
        path.read_text(encoding="utf-8") for path in ARCHITECTURE.glob("*/README.md")
    )


def test_architecture_decomposition_matches_viewpoint_contract() -> None:
    decomposable = {
        "05-building-block-view",
        "06-runtime-view",
        "08-crosscutting-concepts",
        "09-architecture-decisions",
    }
    for name in VIEW_MARKERS:
        text = (ARCHITECTURE / name / "README.md").read_text(encoding="utf-8")
        rules = section(text, "Decomposition Rules").lower()
        if name in decomposable:
            assert "one file" in rules or "one adr" in rules, name
        else:
            assert "do not create child files" in rules or "creating child files" in rules, name


def test_requirement_creation_and_audit_contracts_align() -> None:
    profile = (SKILL / "references/requirements.md").read_text(encoding="utf-8")
    audit = (SKILL / "references/auditing.md").read_text(encoding="utf-8")
    template = (SKILL / "templates/specs/requirements/README.md").read_text(encoding="utf-8")
    russian = (SKILL / "templates/ru/specs/requirements/README.md").read_text(encoding="utf-8")

    for marker in (
        "independent of a particular transport",
        "external surface",
        "measurable or otherwise verifiable",
        "externally imposed",
    ):
        assert marker in profile
    for text in (profile, audit, template):
        for status in ("deprecated", "superseded", "withdrawn"):
            assert status in text
        for field in ("Changed", "Reason", "Replacement"):
            assert field in text
    for field in ("Changed", "Reason", "Replacement"):
        assert field in russian
    assert "traceability matrices" in profile
    assert "nontrivial active requirement" in audit


def test_adr_creation_and_audit_contracts_align() -> None:
    profile = (SKILL / "references/adr.md").read_text(encoding="utf-8")
    audit = (SKILL / "references/auditing.md").read_text(encoding="utf-8")
    template = (SKILL / "templates/adr.md").read_text(encoding="utf-8")
    russian = (SKILL / "templates/ru/adr.md").read_text(encoding="utf-8")

    concepts = ("Compatibility", "Migration", "Rollback", "Reversibility", "Risks")
    for concept in concepts:
        assert f"## {concept}" in template
    for concept in ("Совместимость", "Миграция", "Откат", "Обратимость", "Риски"):
        assert f"## {concept}" in russian
    for marker in ("compatibility", "migration", "rollback", "reversibility", "risks"):
        assert marker in profile.lower()
        assert marker in audit.lower()
    assert "Not applicable" in profile
    assert "Requirements:" in template
    assert "Related ADRs:" in template


def test_security_and_data_concerns_have_one_architecture_owner() -> None:
    profile = " ".join((SKILL / "references/architecture.md").read_text(encoding="utf-8").split())
    audit = " ".join((SKILL / "references/auditing.md").read_text(encoding="utf-8").split())
    ownership = {
        "03-context-and-scope": "trust boundaries",
        "07-deployment-view": "network exposure",
        "08-crosscutting-concepts": "sensitive-data",
        "10-quality-requirements": "measurable",
    }
    for viewpoint, concern in ownership.items():
        assert viewpoint in profile
        assert concern in profile
        assert concern in audit
    assert "content-free checklists" in audit
