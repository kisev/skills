from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
        "missing-anchor": "missing_evidence",
        "bad-selector": "stale_selector",
        "bad-eval": "unknown_eval",
        "orphan-evidence": "orphan_evidence",
        "stale-evidence": "stale_selector",
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
