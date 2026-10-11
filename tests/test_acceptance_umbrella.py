"""Contract tests for the live acceptance umbrella (no live host needed)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import tests.integration.acceptance_probes as probes
from tests.integration import acceptance
from tests.integration.gitlab.scripts import skill_acceptance

INVENTORY = sorted(
    path.name
    for path in (Path(__file__).resolve().parents[1] / ".build/skills").iterdir()
    if (path / "SKILL.md").is_file()
)


def test_registry_partitions_the_skill_inventory() -> None:
    entries = acceptance.plan(None, INVENTORY)
    covered = [name for entry in entries for name in entry["skills"]]
    assert sorted(covered) == INVENTORY
    assert len(covered) == len(set(covered)) == 44
    families = {entry["family"] for entry in entries}
    assert families == set(acceptance.HARNESS_SKILLS) | {"behavior-probe", "skip"}
    assert not set(probes.PROBES) & set(probes.SKIPS)
    assert all(reason.strip() for reason in probes.SKIPS.values())


def test_probe_specs_are_formattable_and_minimal() -> None:
    artifact = Path("/tmp/unused/artifact.md")
    answer = Path("/tmp/unused/answer.json")
    for name, spec in probes.PROBES.items():
        assert spec["fixture"], name
        assert spec["timeout"] > 0, name
        # Every prompt must accept the engine's placeholders and nothing else.
        spec["prompt"].format(artifact=artifact, answer=answer)
        assert set(spec["checks"]) <= {
            "answer_keys",
            "answer_equal",
            "contains",
            "not_contains",
            "max_chars",
            "first_line_regex",
            "first_line_max",
            "json_list",
            "rerun",
        }, name


def test_plan_only_prints_the_registry(capsys: pytest.CaptureFixture[str]) -> None:
    assert acceptance.main(["--plan-only"]) == 0
    output = capsys.readouterr().out
    assert "code-review" in output and "behavior-probe" in output
    assert "total: 44 entries over 44 skills" in output


def test_plan_filter_and_unknown_skill() -> None:
    entries = acceptance.plan("eli5", INVENTORY)
    assert [(entry["family"], entry["skills"]) for entry in entries] == [
        ("behavior-probe", ["eli5"])
    ]
    entries = acceptance.plan("code-review", INVENTORY)
    assert [(entry["family"], entry["skills"]) for entry in entries] == [
        ("code-review-acceptance", ["code-review"])
    ]
    with pytest.raises(acceptance.UmbrellaError, match="unknown skill"):
        acceptance.plan("not-a-skill", INVENTORY)


def test_settings_refuse_expensive_models_without_explicit_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCEPT_EXPENSIVE", raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"provider":{}}')
    monkeypatch.setenv("EVAL_MODEL", "zai-coding-plan/glm-5.3")
    with pytest.raises(acceptance.UmbrellaError, match="ACCEPT_EXPENSIVE"):
        acceptance.settings(accept_expensive=False)
    configured = acceptance.settings(accept_expensive=True)
    assert configured["model"] == "zai-coding-plan/glm-5.3"
    monkeypatch.setenv("ACCEPT_EXPENSIVE", "1")
    assert acceptance.settings(accept_expensive=False)["model"] == "zai-coding-plan/glm-5.3"


def test_settings_default_to_the_cheap_flash_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCEPT_EXPENSIVE", raising=False)
    for name in ("EVAL_MODEL", "EVAL_HOST", "EVAL_TIMEOUT", "EVAL_MAX_TOKENS", "EVAL_MAX_COST"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"provider":{}}')
    configured = acceptance.settings(accept_expensive=False)
    assert configured["model"] == "zai-coding-plan/glm-5.3-flash"
    assert skill_acceptance.CHEAP_MODEL.search(configured["model"])


def test_settings_require_explicit_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*skill_acceptance.PROVIDER_KEYS, "ACCEPT_EXPENSIVE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(acceptance.UmbrellaError, match="credentials"):
        acceptance.settings(accept_expensive=False)


def test_family_prereq_skips_with_reasons_when_stacks_are_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acceptance, "container_status", lambda name: "")
    mattermost = acceptance.family_prereq("mattermost-live")
    assert mattermost and "Mattermost" in mattermost and "env:mattermost:up" in mattermost
    gitlab = acceptance.family_prereq("gitlab-live")
    assert gitlab and "GitLab" in gitlab
    assert acceptance.family_prereq("code-review-acceptance") is None


def test_gitlab_prereq_requires_initialized_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance, "container_status", lambda name: "Up 2 minutes (healthy)")
    monkeypatch.setattr(acceptance, "GITLAB_FIXTURES", Path("/tmp/unused/fixtures.json"))
    gitlab = acceptance.family_prereq("gitlab-live")
    assert gitlab and "fixtures" in gitlab


def _write_answer(workspace: Path, value: dict[str, Any]) -> None:
    (workspace / "answer.json").write_text(json.dumps(value), encoding="utf-8")


def test_evaluate_checks_accepts_a_conforming_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.md"
    artifact.write_text(
        "## Red\npython3 test_calc.py failed\n## Green\nall passed\n", encoding="utf-8"
    )
    _write_answer(tmp_path, {"artifact": str(artifact)})
    spec: dict[str, Any] = {
        "checks": {
            "contains": ["## Red", "## Green"],
            "not_contains": ["refactor everything"],
            "rerun": ["true"],
        }
    }
    checks = acceptance.evaluate_checks(spec, tmp_path, artifact, tmp_path / "answer.json")
    assert all(item["status"] == "passed" for item in checks)


def test_evaluate_checks_reports_each_violation(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.md"
    artifact.write_text("x" * 30, encoding="utf-8")
    _write_answer(tmp_path, {"artifact": str(artifact), "extra": True})
    spec: dict[str, Any] = {
        "checks": {
            "contains": ["## Missing"],
            "max_chars": 10,
            "first_line_regex": r"^feat: \S",
        }
    }
    checks = acceptance.evaluate_checks(spec, tmp_path, artifact, tmp_path / "answer.json")
    failed = {item["id"] for item in checks if item["status"] == "failed"}
    assert {
        "answer:keys",
        "artifact:contains:## Missing",
        "artifact:max_chars",
        "artifact:first_line",
    } <= failed


def test_evaluate_checks_json_list_contract(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps(
            [
                {"question": "Which scope?", "options": ["a", "b"]},
                {"question": "Which budget?", "options": ["low", "high"]},
            ]
        ),
        encoding="utf-8",
    )
    _write_answer(tmp_path, {"artifact": str(artifact)})
    spec: dict[str, Any] = {
        "checks": {"json_list": {"min": 2, "max": 4, "item_keys": ["question", "options"]}}
    }
    checks = acceptance.evaluate_checks(spec, tmp_path, artifact, tmp_path / "answer.json")
    assert all(item["status"] == "passed" for item in checks)


def test_evaluate_checks_rerun_must_exit_zero(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.md"
    artifact.write_text("ok", encoding="utf-8")
    _write_answer(tmp_path, {"artifact": str(artifact)})
    spec: dict[str, Any] = {"checks": {"rerun": ["false"]}}
    checks = acceptance.evaluate_checks(spec, tmp_path, artifact, tmp_path / "answer.json")
    assert any(item["id"] == "artifact:rerun" and item["status"] == "failed" for item in checks)


def test_stage_timeline_orders_and_gaps() -> None:
    timeline = skill_acceptance.stage_timeline(
        {"prepare": 2, "context": 30, "critic": 600, "finalize": 800}
    )
    observed = [item for item in timeline if item["at_seconds"] is not None]
    assert [item["stage"] for item in observed] == ["prepare", "context", "critic", "finalize"]
    assert observed[-1]["gap_seconds"] == 200
    assert timeline[0]["stage"] == "prepare"


def test_watch_stages_marks_first_sightings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    state = tmp_path / "xdg-state" / "agent-skills" / "gitlab" / "abc"
    state.mkdir(parents=True)
    monkeypatch.setattr(skill_acceptance, "WATCH_INTERVAL", 0.02)
    stages: dict[str, int] = {}
    stop = threading.Event()
    watcher = threading.Thread(
        target=skill_acceptance.watch_stages, args=(tmp_path, stop, stages), daemon=True
    )
    watcher.start()
    (state / "review-current.json").write_text(
        json.dumps({"context_path": None, "plan_path": None}), encoding="utf-8"
    )
    (state / "review-panel.json").write_text(
        json.dumps(
            {"participants": {"critics": [{"name": "critic-1", "receipt": {"run_id": "r"}}]}}
        ),
        encoding="utf-8",
    )
    (state / "run-authoring.json").write_text(json.dumps({"applied": True}), encoding="utf-8")
    (state / "review-current.json").write_text(
        json.dumps({"context_path": "c", "plan_path": "p"}), encoding="utf-8"
    )
    for _ in range(100):
        if {"prepare", "poll-panel", "critic", "prose", "context", "finalize"} <= set(stages):
            break
        threading.Event().wait(0.02)
    stop.set()
    watcher.join(timeout=2)
    assert {"prepare", "poll-panel", "critic", "prose", "context", "finalize"} <= set(stages)
    assert stages["prepare"] <= stages["poll-panel"] <= stages["prose"]


def test_harness_summary_and_budget_fields(tmp_path: Path) -> None:
    report = {
        "action": "skill-acceptance",
        "started_at": "2026-10-11T00:00:00+00:00",
        "status": "passed",
        "acceptance_budget_seconds": 1800,
        "fixture": {
            "mr_url": "https://gitlab.example/group/project/-/merge_requests/7",
            "changed_path": "review.txt",
            "related_issue_iid": 5,
        },
        "attempts": [
            {
                "attempt": 1,
                "status": "passed",
                "model": "zai-coding-plan/glm-5.3-flash",
                "duration_ms": 1_500_000,
                "within_budget": True,
                "timeline": skill_acceptance.stage_timeline({"prepare": 1, "finalize": 900}),
                "checks": [{"name": "plan_ready", "status": "passed"}],
                "usage": {"total_tokens": 90_000, "cost": 0.1},
            }
        ],
    }
    destination = tmp_path / "summary.md"
    skill_acceptance.write_summary(destination, report)
    text = destination.read_text(encoding="utf-8")
    assert "verdict: **passed**" in text
    assert "merge_requests/7" in text and "review.txt" in text
    assert "| 1 | passed |" in text and "yes" in text
    assert "master session" in text


def test_cost_estimate_sums_measured_families(monkeypatch: pytest.MonkeyPatch) -> None:
    reports: dict[Path, dict[str, Any]] = {
        acceptance.SKILL_ACCEPTANCE_REPORTS / "latest.json": {
            "attempts": [{"usage": {"cost": 0.2}}, {"usage": {"cost": 0.1}}]
        },
        acceptance.GITLAB_REPORTS / "latest.json": {"usage": {"cost": 0.05}},
        acceptance.MATTERMOST_REPORTS / "latest.json": {"usage": {"cost": 0.05}},
    }

    def lookup(pointer: Path) -> dict[str, Any] | None:
        return reports.get(pointer)

    monkeypatch.setattr(acceptance, "pointer_report", lookup)
    assert acceptance.cost_estimate() == "~$0.40 measured in prior runs"
    monkeypatch.setattr(acceptance, "pointer_report", lambda pointer: None)
    assert acceptance.cost_estimate() == "unknown (no measured prior run)"


def test_umbrella_summary_lists_coverage_skips_and_failures(tmp_path: Path) -> None:
    report = {
        "action": "acceptance-umbrella",
        "started_at": "2026-10-11T00:00:00+00:00",
        "status": "failed",
        "model": "zai-coding-plan/glm-5.3-flash",
        "cost_estimate": "~$0.30 measured in prior runs",
        "duration_ms": 60_000,
        "entries": [
            {
                "skills": ["code-review"],
                "family": "code-review-acceptance",
                "result": {"status": "passed", "report": "/tmp/unused/latest.json"},
            },
            {
                "skills": ["eli5"],
                "family": "behavior-probe",
                "result": {"status": "passed", "attempt_dir": "/tmp/unused/eli5"},
            },
            {
                "skills": ["taskmatic"],
                "family": "skip",
                "result": {"status": "skipped", "reason": "no board service"},
            },
            {
                "skills": ["goal"],
                "family": "behavior-probe",
                "result": {"status": "failed", "reason": "probe checks failed: ['answer:keys']"},
            },
        ],
    }
    destination = tmp_path / "summary.md"
    acceptance.write_summary(destination, report)
    text = destination.read_text(encoding="utf-8")
    assert "| code-review | code-review-acceptance | passed |" in text
    assert "| eli5 | behavior-probe | passed |" in text
    assert "## Skips" in text and "no board service" in text
    assert "## Failures" in text and "answer:keys" in text
    assert "master session" in text
