from __future__ import annotations

import json
from pathlib import Path

from scripts.eval_runner import (
    discover,
    validate_compatibility_inventory,
    validate_public_surface_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


def test_stage20_corpus_has_complete_bilingual_skill_matrix_and_unique_prompts() -> None:
    scenarios = discover(ROOT / "evals" / "scenarios")
    validate_public_surface_inventory(ROOT, scenarios)
    skill = [
        item
        for item in scenarios
        if item["surface"] == "skill" and item["id"].startswith("stage20.")
    ]
    assert len(skill) == 116
    assert len({item["input"]["prompt"] for item in skill}) == 116
    for name in json.loads((ROOT / "evals/contracts/public-surfaces.json").read_text())["skills"]:
        selected = [
            item for item in skill if f"skill:{name}" in item["expected"].get("selected", [])
        ]
        rejected = [
            item for item in skill if f"skill:{name}" in item["expected"].get("not_selected", [])
        ]
        assert {(item["locale"], item["kind"]) for item in selected} == {
            ("en", "trigger"),
            ("ru", "trigger"),
        }
        assert {(item["locale"], item["kind"]) for item in rejected} == {
            ("en", "near-miss"),
            ("ru", "near-miss"),
        }


def test_stage20_compatibility_inventory_is_explicit_and_hostless() -> None:
    validate_compatibility_inventory(ROOT)
    inventory = json.loads((ROOT / "evals/contracts/opencode-compatibility.json").read_text())
    assert inventory["versions"] == ["1.18.29", "1.18.30"]
    assert inventory["range"] == ">=1.18.29 <1.19.0"
    assert inventory["credentials"] is False
    assert inventory["network"] is False
