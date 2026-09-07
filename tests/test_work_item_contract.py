from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILT_SKILLS = ROOT / ".build" / "skills"
SKILLS = ("askme", "goal", "task-prepare", "task-review")


def item() -> dict[str, object]:
    return {
        "contract_version": "work-item/v1",
        "item_id": "example-1",
        "problem": "A known problem needs a bounded resolution.",
        "outcome": "The bounded resolution is observable in the final state.",
        "acceptance_criteria": [
            {
                "id": "result",
                "statement": "The final state is observable.",
                "evidence": ["test report"],
                "dependencies": [],
            }
        ],
        "scope": {"in_scope": ["the bounded resolution"], "non_goals": ["unrelated cleanup"]},
        "dependencies": [],
        "external_actions": [],
        "assumptions": ["The repository is available"],
        "safety": {
            "constraints": ["Do not mutate external systems"],
            "operational_constraints": ["Use read-only evidence first"],
        },
        "risks": [],
        "unresolved_questions": [],
        "stop_conditions": ["Evidence cannot be collected"],
    }


def run(
    skill: str, payload: dict[str, object], tmp_path: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    path = BUILT_SKILLS / skill / "scripts/work_item.py"
    input_path = tmp_path / f"work-item-{skill}.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        return subprocess.run(
            [sys.executable, str(path), *arguments, "--input", str(input_path)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        input_path.unlink(missing_ok=True)


def test_ready_report_is_identical_for_all_materialized_clis(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic.json"
    semantic.write_text(json.dumps({"status": "passed", "findings": []}), encoding="utf-8")
    reports = []
    for skill in SKILLS:
        result = run(skill, item(), tmp_path, "validate", "--semantic", str(semantic))
        assert result.returncode == 0, result.stderr
        reports.append(json.loads(result.stdout))
    assert all(report["verdict"] == "ready" for report in reports)
    assert len({report["report_digest"] for report in reports}) == 1


def test_machine_and_semantic_reports_and_exit_codes(tmp_path: Path) -> None:
    semantic = tmp_path / "semantic.json"
    semantic.write_text(json.dumps({"status": "passed", "findings": []}), encoding="utf-8")
    invalid = item()
    invalid.pop("problem")
    (tmp_path / "item.json").write_text(json.dumps(invalid), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(BUILT_SKILLS / "goal/scripts/work_item.py"),
            "validate",
            "--input",
            str(tmp_path / "item.json"),
            "--semantic",
            str(semantic),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["verdict"] == "needs_clarification"
    assert report["machine_findings"][0]["code"] == "MISSING_FIELD"


def test_boundaries_cycles_and_unreachable_conditions_are_machine_findings(tmp_path: Path) -> None:
    value = item()
    value["scope"] = {"in_scope": ["same"], "non_goals": ["same"]}
    value["dependencies"] = [
        {"id": "a", "description": "A", "status": "blocked", "depends_on": ["b"]},
        {"id": "b", "description": "B", "status": "available", "depends_on": ["a"]},
    ]
    value["acceptance_criteria"] = [
        {"id": "result", "statement": "Result", "evidence": ["report"], "dependencies": ["a"]}
    ]
    source = tmp_path / "item.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    semantic = tmp_path / "semantic.json"
    semantic.write_text(json.dumps({"status": "passed", "findings": []}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(BUILT_SKILLS / "goal/scripts/work_item.py"),
            "validate",
            "--input",
            str(source),
            "--semantic",
            str(semantic),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    codes = {finding["code"] for finding in report["machine_findings"]}
    assert {"BOUNDARY_CONFLICT", "DEPENDENCY_CYCLE", "UNREACHABLE_CRITERION"}.issubset(codes)
    assert report["verdict"] == "blocked"


def test_recheck_is_stable_and_all_premortem_outcomes_are_structured(tmp_path: Path) -> None:
    source = tmp_path / "item.json"
    source.write_text(json.dumps(item()), encoding="utf-8")
    semantic = tmp_path / "semantic.json"
    semantic.write_text(json.dumps({"status": "passed", "findings": []}), encoding="utf-8")
    command = [
        sys.executable,
        str(BUILT_SKILLS / "task-review/scripts/work_item.py"),
        "validate",
        "--input",
        str(source),
        "--semantic",
        str(semantic),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout) == json.loads(second.stdout)
    for payload, status in (
        ({"requested": False}, "skipped"),
        ({"requested": True, "independent_agent_available": False}, "skipped"),
        (
            {
                "requested": True,
                "independent_agent_available": True,
                "findings": [
                    {
                        "id": "risk",
                        "probability": "medium",
                        "impact": "high",
                        "proposed_wording_change": "Clarify the boundary.",
                    }
                ],
                "decisions": [
                    {
                        "id": "risk",
                        "decision": "rejected",
                        "reason": "Evidence makes this risk inapplicable.",
                    }
                ],
            },
            "completed",
        ),
        (
            {
                "requested": True,
                "independent_agent_available": True,
                "findings": [{"id": "risk", "probability": "medium", "impact": "high"}],
                "decisions": [],
            },
            "invalid",
        ),
    ):
        path = tmp_path / f"{status}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(BUILT_SKILLS / "askme/scripts/work_item.py"),
                "premortem",
                "--input",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == (0 if status != "invalid" else 2)
        assert json.loads(result.stdout)["status"] == status
