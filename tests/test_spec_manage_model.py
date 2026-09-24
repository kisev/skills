from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/spec-manage"
ARCHITECTURE = SKILL / "templates/specs/architecture"
ARCHITECTURE_RU = SKILL / "templates/ru/specs/architecture"
EXAMPLE = SKILL / "references/minimal-example.md"

VIEWPOINTS = tuple(
    f"{number:02d}-{name}"
    for number, name in enumerate(
        (
            "introduction-and-goals",
            "architecture-constraints",
            "context-and-scope",
            "solution-strategy",
            "building-block-view",
            "runtime-view",
            "deployment-view",
            "crosscutting-concepts",
            "architecture-decisions",
            "quality-requirements",
            "risks-and-technical-debt",
            "glossary",
        ),
        1,
    )
)


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\n\n(?P<body>.*?)(?=\n## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, heading
    return match.group("body").strip()


def test_all_architecture_view_templates_are_specialized_and_mirrored() -> None:
    expected = set(VIEWPOINTS)
    english = {path.parent.name for path in ARCHITECTURE.glob("*/README.md")}
    russian = {path.parent.name for path in ARCHITECTURE_RU.glob("*/README.md")}
    assert english == expected
    assert russian == expected

    purposes: set[str] = set()
    content_templates: set[str] = set()
    for name in VIEWPOINTS:
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
        assert english_text.startswith(f"# {name[:2]} "), name
        assert russian_text.startswith(f"# {name[:2]} "), name
        purposes.add(section(english_text, "Purpose"))
        content_templates.add(section(english_text, "Content Template"))

    assert len(purposes) == 12
    assert len(content_templates) == 12


def test_every_template_has_a_translation_with_the_same_machine_placeholders() -> None:
    # Translation may restructure prose; stable identifiers remain shared contracts.
    templates = SKILL / "templates"
    english = {
        path.relative_to(templates): path
        for path in templates.rglob("*.md")
        if "ru" not in path.relative_to(templates).parts
    }
    russian = {
        path.relative_to(templates / "ru"): path for path in (templates / "ru").rglob("*.md")
    }
    assert set(english) == set(russian)
    for relative, english_path in english.items():
        source = english_path.read_text(encoding="utf-8")
        translated = russian[relative].read_text(encoding="utf-8")
        assert translated.strip(), relative
        for marker in re.findall(r"(?:REQ-[FIQC]-[0-9]+|ADR-[0-9]+|spec-validate/v[0-9]+)", source):
            assert marker in translated, (relative, marker)


def test_architecture_decomposition_matches_viewpoint_contract() -> None:
    decomposable = {
        "05-building-block-view",
        "06-runtime-view",
        "08-crosscutting-concepts",
        "09-architecture-decisions",
    }
    for name in VIEWPOINTS:
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


def test_compact_example_covers_all_required_documents_without_process_content() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    entries = re.findall(r"^\d+\. `([^`]+README\.md)`: (.+)$", text, flags=re.MULTILINE)
    expected = {
        path.relative_to(SKILL / "templates").as_posix()
        for path in (SKILL / "templates/specs").rglob("README.md")
    }
    assert len(entries) == 19
    assert {path for path, _ in entries} == expected
    assert all(len(body.split()) >= 10 for _, body in entries)
    example_body = "\n".join(body.lower() for _, body in entries)
    for forbidden in ("roadmap", "proposal", "delivery status", "implementation sequence"):
        assert forbidden not in example_body
    assert "guidance, not a template" in text
    assert "do not copy it mechanically" in " ".join(text.lower().split())
