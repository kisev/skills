from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_specs import (
    SpecError,
    classify_paths,
    check_evidence,
    read_json,
    requirement_blocks,
)

ROOT = Path(__file__).resolve().parents[1]


def test_spec_checker_passes_and_reports_stable_shape() -> None:
    result = subprocess.run(
        ["python", "scripts/check_specs.py"], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["status"] == "passed"
    assert value["spec_files"] == 108


def test_negative_spec_fixtures_return_stable_codes() -> None:
    expected = {
        "duplicate-id": "duplicate_requirement_id",
        "bad-hash": "requirement_hash",
        "missing-anchor": "missing_anchor",
        "bad-selector": "stale_selector",
        "bad-eval": "unknown_eval",
        "orphan-evidence": "orphan_manual_evidence",
        "stale-evidence": "stale_evidence",
        "retired-surface": "unknown_surface",
        "contract-sidecar": "contract_sidecar",
        "bad-revision": "source_revision",
        "missing-manual-rationale": "manual_evidence",
    }
    for case, code in expected.items():
        result = subprocess.run(
            [
                "python",
                "scripts/check_specs.py",
                "--negative",
                f"tests/fixtures/specs-negative/{case}.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert json.loads(result.stdout)["error"]["code"] == code


def test_hash_tampering_is_rejected_even_when_the_source_block_is_unchanged() -> None:
    trace = read_json(ROOT / "specs/traceability.json")
    trace["requirements"]["REQ-F-001"]["block_sha256"] = "0" * 64
    with pytest.raises(SpecError) as error:
        check_evidence(
            trace, requirement_blocks(), read_json(ROOT / "evals/contracts/public-surfaces.json")
        )
    assert error.value.code == "requirement_hash"


def test_behavioral_classifier_uses_versioned_boundaries() -> None:
    assert classify_paths(["scripts/build_distribution.py"])
    assert classify_paths(["packages/opencode/src/cli.ts"])
    assert not classify_paths(["docs/release-notes.md", "tests/test_specs.py"])
