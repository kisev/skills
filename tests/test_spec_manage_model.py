from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/spec-manage"
ARCHITECTURE = SKILL / "templates/specs/architecture"
ARCHITECTURE_RU = SKILL / "templates/ru/specs/architecture"
EXAMPLE = SKILL / "references/minimal-example.md"

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


def test_mode_selection_uses_intent_evidence_and_safe_ambiguity_stop() -> None:
    source = " ".join((SKILL / "SKILL.source.md").read_text(encoding="utf-8").lower().split())
    workflow = " ".join(
        (SKILL / "references/workflow.md").read_text(encoding="utf-8").lower().split()
    )

    for mode in ("spec-init", "spec-onboard", "spec-update", "spec-audit"):
        assert mode in source
        assert mode in workflow
    for evidence in ("source code", "tests", "schemas", "configuration", "ci", "deployment"):
        assert evidence in workflow
    assert "absence of `specs/` alone never proves greenfield" in workflow
    assert "a clearly read-only request always stays read-only" in workflow
    assert "ask one short question" in workflow
    assert "stop without writing until the user answers" in workflow
    assert "implementation, plans, roadmaps" in source
    assert "change canonical specs" in workflow


def test_content_states_are_specific_and_do_not_weaken_readiness() -> None:
    raw_guidance = (SKILL / "references/content-states.md").read_text(encoding="utf-8")
    guidance = " ".join(raw_guidance.split())
    for heading in ("## Confirmed content", "## Inapplicable content", "## Accepted `UNKNOWN`"):
        assert heading in raw_guidance
    for marker in (
        "project-specific target-state fact",
        "specific project condition",
        "unknown fact",
        "its bounded area and consequence",
        "evidence needed",
        "user's explicit acceptance",
        "never insert it automatically as a placeholder",
        "not weaker readiness",
    ):
        assert marker in guidance


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


def test_public_mode_help_and_bilingual_eval_cases_stay_aligned() -> None:
    english = (ROOT / "docs/reference/skill-catalog.md").read_text(encoding="utf-8")
    russian = (ROOT / "docs/ru/reference/skill-catalog.md").read_text(encoding="utf-8")
    capability = (ROOT / "specs/capabilities/commands/spec-manage.md").read_text(encoding="utf-8")
    for text in (english, russian, capability):
        for mode in ("spec-init", "spec-onboard", "spec-update", "spec-audit"):
            assert mode in text

    scenarios = []
    for locale in ("en", "ru"):
        path = ROOT / f"evals/scenarios/spec-manage.mode-selection.{locale}.json"
        scenarios.append(__import__("json").loads(path.read_text(encoding="utf-8")))
    assert {item["locale"] for item in scenarios} == {"en", "ru"}
    cases = [item["input"]["fixture"]["cases"] for item in scenarios]
    assert [case["id"] for case in cases[0]] == [case["id"] for case in cases[1]]
    assert {case["outcome"] for case in cases[0]} == {
        "spec-init",
        "spec-onboard",
        "spec-update",
        "spec-audit",
        "ask-no-writes",
        "explicit-spec-audit",
        "near-miss",
    }

    near_misses = [
        __import__("json").loads(path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "evals/scenarios").glob("spec-manage.*-near-miss.*.json"))
    ]
    assert len(near_misses) == 4
    assert {(item["locale"], item["pair_id"]) for item in near_misses} == {
        ("en", "spec-manage.implementation-near-miss"),
        ("ru", "spec-manage.implementation-near-miss"),
        ("en", "spec-manage.planning-near-miss"),
        ("ru", "spec-manage.planning-near-miss"),
    }
    assert all(item["expected"]["not_selected"] == ["skill:spec-manage"] for item in near_misses)


def test_audit_contract_is_deterministic_and_scenario_complete() -> None:
    audit = (SKILL / "references/auditing.md").read_text(encoding="utf-8")
    normalized = " ".join(audit.split())

    report_sections = (
        "Scope",
        "Formal validation",
        "Quality findings",
        "Drift",
        "Unchecked boundaries",
        "Critic",
        "Overall",
    )
    report = section(audit, "Conversational report")
    positions = [report.index(name) for name in report_sections]
    assert positions == sorted(positions)

    rows = re.findall(r"\| \d \| `([A-Z_]+)` \|", audit)
    assert rows == [
        "UNKNOWN",
        "CONFLICT",
        "SPEC_AHEAD",
        "IMPLEMENTATION_AHEAD",
        "OK",
    ]
    for severity in ("critical", "high", "medium", "low"):
        assert f"`{severity}`:" in audit
    for marker in (
        "claim** is one observable behavior or one verifiable property",
        "boundary** is one interface, ownership, trust, deployment, or dependency",
        "first matching row",
        "Absence of evidence is not automatically `SPEC_AHEAD`",
        "Drift: OK (<exact scope>; checked: <evidence boundaries>)",
        "same bounded evidence snapshot",
        "primary reviewer's conclusions",
        "`accepted`, `rejected`, or `duplicate`",
        "A repeated pass in the primary context is not independent",
        "`Overall: partial`",
        "`Overall: findings`",
        "`Overall: clean`",
    ):
        assert marker in normalized

    scenario = json.loads(
        (ROOT / "evals/scenarios/spec-manage.audit-determinism.json").read_text(encoding="utf-8")
    )
    cases = {case["id"]: case for case in scenario["input"]["fixture"]["cases"]}
    assert set(cases) == {
        "direct-contradiction",
        "missing-implementation",
        "undocumented-behavior",
        "insufficient-evidence",
        "quality-without-drift",
        "critic-unavailable",
    }
    assert cases["direct-contradiction"]["drift"] == "CONFLICT"
    assert cases["missing-implementation"]["drift"] == "SPEC_AHEAD"
    assert cases["undocumented-behavior"]["drift"] == "IMPLEMENTATION_AHEAD"
    assert cases["insufficient-evidence"]["drift"] == "UNKNOWN"
    assert cases["insufficient-evidence"]["overall"] == "partial"
    assert cases["quality-without-drift"]["overall"] == "findings"
    assert cases["critic-unavailable"]["critic"] == "not_checked"
    assert cases["critic-unavailable"]["overall"] == "partial"
