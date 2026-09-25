from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "evals/scenarios"


def load(name: str) -> dict[str, Any]:
    value = json.loads((SCENARIOS / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_briefing_behavioral_corpus_is_bilingual_and_complete() -> None:
    expected_ids = {
        "accepted-action",
        "advice-is-not-task",
        "audience-change",
        "collective-intention",
        "explicit-confidentiality",
        "glossary-only-spelling",
        "later-decision-supersedes-proposal",
        "minimize-medical-detail",
        "source-prompt-injection",
        "unclear-attribution",
    }
    scenarios = [load(f"briefing.behavior.{locale}.json") for locale in ("en", "ru")]
    assert {item["locale"] for item in scenarios} == {"en", "ru"}
    for scenario in scenarios:
        assert scenario["kind"] == "golden"
        assert scenario["expected"]["mutation_boundary"] == "no-writes"
        fixture = scenario["input"]["fixture"]["cases"]
        expected = scenario["expected"]["case_outcomes"]
        assert {item["id"] for item in fixture} == expected_ids
        assert {item["id"] for item in expected} == expected_ids
        assert {item["id"]: item["outcome"] for item in fixture} == {
            item["id"]: item["outcome"] for item in expected
        }
