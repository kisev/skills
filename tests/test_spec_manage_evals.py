from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "evals/scenarios"
SKILL = ROOT / "skills/spec-manage"


def load(name: str) -> dict[str, Any]:
    value = json.loads((SCENARIOS / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def assert_case_contract(scenario: dict[str, Any], expected_ids: set[str]) -> None:
    fixture = scenario["input"]["fixture"]["cases"]
    expected = scenario["expected"]["case_outcomes"]
    assert {item["id"] for item in fixture} == expected_ids
    assert {item["id"] for item in expected} == expected_ids
    assert {item["id"]: item["outcome"] for item in fixture} == {
        item["id"]: item["outcome"] for item in expected
    }


def test_mode_selection_behavioral_corpus_is_bilingual_and_complete() -> None:
    expected_ids = {
        "natural-init",
        "natural-onboard",
        "natural-update",
        "natural-audit",
        "evidence-init",
        "evidence-onboard",
        "ambiguous-update-audit",
        "explicit-mode",
        "explicit-failed-precondition",
        "near-miss-user-docs",
        "near-miss-implementation",
        "near-miss-planning",
        "ambiguous-review-and-fix",
    }
    scenarios = [load(f"spec-manage.mode-selection.{locale}.json") for locale in ("en", "ru")]
    assert {item["locale"] for item in scenarios} == {"en", "ru"}
    for scenario in scenarios:
        assert scenario["kind"] == "golden"
        assert scenario["expected"]["mutation_boundary"] == "no-writes"
        assert_case_contract(scenario, expected_ids)


def test_content_state_contract_has_three_distinct_non_placeholder_states() -> None:
    guidance = (SKILL / "references/content-states.md").read_text(encoding="utf-8")
    sections = re.findall(r"^## (.+)$", guidance, re.MULTILINE)
    assert sections == ["Confirmed content", "Inapplicable content", "Accepted `UNKNOWN`"]
    normalized = " ".join(guidance.split())
    assert "specific project condition" in normalized
    assert "its bounded area and consequence" in normalized
    assert "evidence needed" in normalized
    assert "user's explicit acceptance" in normalized
    assert "never insert it automatically as a placeholder" in normalized
    assert "not weaker readiness" in normalized


def test_language_authority_extension_behavioral_corpus_is_complete() -> None:
    expected_ids = {
        "init-language-first",
        "onboard-language-first",
        "update-different-language",
        "update-mixed-language",
        "mixed-legacy-tree",
        "normative-conflict",
        "indexed-capabilities",
        "process-extension",
    }
    for locale in ("en", "ru"):
        scenario = load(f"spec-manage.language-authority-extensions.{locale}.json")
        assert scenario["kind"] == "golden"
        assert scenario["expected"]["mutation_boundary"] == "no-writes"
        assert_case_contract(scenario, expected_ids)


def test_audit_contract_and_behavioral_corpus_cover_complete_decision_model() -> None:
    audit = (SKILL / "references/auditing.md").read_text(encoding="utf-8")
    assert re.findall(r"\| \d \| `([A-Z_]+)` \|", audit) == [
        "UNKNOWN",
        "CONFLICT",
        "SPEC_AHEAD",
        "IMPLEMENTATION_AHEAD",
        "OK",
    ]
    assert re.findall(r"^- `(critical|high|medium|low)`:", audit, re.MULTILINE) == [
        "critical",
        "high",
        "medium",
        "low",
    ]
    report = re.search(r"```text\n(?P<body>.*?)\n```", audit, re.DOTALL)
    assert report is not None
    assert report.group("body").splitlines() == [
        "Scope",
        "Formal validation",
        "Quality findings",
        "Drift",
        "Unchecked boundaries",
        "Critic",
        "Overall",
    ]

    expected_ids = {
        "unknown",
        "conflict",
        "spec-ahead",
        "implementation-ahead",
        "qualified-ok",
        "quality-without-drift",
        "mandatory-validation-failed",
        "changed-evidence",
        "focused-critic",
        "full-critic-unavailable",
        "critic-candidate",
    }
    for locale in ("en", "ru"):
        scenario = load(f"spec-manage.audit-behavior.{locale}.json")
        assert scenario["kind"] == "golden"
        assert scenario["expected"]["mutation_boundary"] == "no-writes"
        assert_case_contract(scenario, expected_ids)


def test_stage20_spec_manage_scenarios_are_routing_declarations_only() -> None:
    stage20 = [load(path.name) for path in sorted(SCENARIOS.glob("stage20.*.spec-manage.*.json"))]
    assert stage20
    assert all("case_outcomes" not in scenario["expected"] for scenario in stage20)
