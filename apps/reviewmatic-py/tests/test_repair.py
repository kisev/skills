"""Draft repair, refresh, and finalization scenarios against the fake glab,
ported from ``repair.test.mjs``.

The pure helpers (schema diagnostics, bounded suggestions, suggestion bodies)
are covered in ``test_fixes_and_diagnostics.py``. The TUI ``loadPlan`` and
``planItems`` helpers belong to stage 3; here the finalized plan is read
through the progress and baseline pointers, and the plan-item assertions
check the underlying publication preview actions instead.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.publication import command_argv


@pytest.fixture(name="fixtures")
def fake_glab_factory() -> Any:
    created: list[ReviewFixture] = []

    def build(overrides: dict[str, Any] | None = None) -> ReviewFixture:
        fixture = make_review_fixture(overrides)
        created.append(fixture)
        return fixture

    try:
        yield build
    finally:
        for fixture in reversed(created):
            fixture.close()


def _read(path: Any) -> dict[str, Any]:
    return contract.read_json(Path(str(path)), "draft")


def _finding(draft: dict[str, Any], *, grouped: bool = False) -> dict[str, Any]:
    draft["findings"] = [
        {
            "id": "fix-1",
            "severity": "low",
            "summary": "Preserve the agreed output",
            "risk": "The output is wrong.",
            "evidence": ["The exact file has the changed output."],
            "consequence": "Consumers read wrong output.",
            "relation_to_change": "Introduced here.",
            "minimum_fix": "Correct the output.",
        }
    ]
    draft["dispositions"] = [
        {
            "id": "fix-1",
            "decision": "accept",
            "reason": "Confirmed.",
            "dependencies": {
                "paths": ["review.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        }
    ]
    publication: dict[str, Any] = {
        "finding_id": "fix-1",
        "type": "general" if grouped else "line",
        "path": None if grouped else "review.txt",
        "line": None if grouped else 2,
        "old_line": None,
        "body": (
            "Correct the two independent outputs."
            if grouped
            else "Correct the output.\n\n```suggestion\ncorrect output\n```"
        ),
        "fix_mode": "suggestion",
        "patch": None,
    }
    if grouped:
        publication["suggestions"] = [
            {"path": "review.txt", "line": 1, "body": "```suggestion\ncorrect base\n```"},
            {"path": "review.txt", "line": 2, "body": "```suggestion\ncorrect output\n```"},
        ]
        publication["split_rationale"] = (
            "Either independent output can be corrected without changing the other."
        )
    draft["content"]["finding_publications"] = [publication]
    return draft


def _ready(
    fixtures: Any, *, grouped: bool = False
) -> tuple[ReviewFixture, dict[str, Any], dict[str, Any]]:
    fixture: ReviewFixture = fixtures({"resolved": True})
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    contract.write_json(
        Path(str(result["draft_path"])),
        _finding(complete_draft(_read(result["draft_path"]), result), grouped=grouped),
    )
    finished = draft_module.finish_review(str(result["draft_path"]))
    assert finished["status"] == "ok", json.dumps(finished)
    return fixture, result, finished


class Plan:
    def __init__(self, root: Path) -> None:
        progress = review_context.load_progress(root)
        assert progress is not None
        if progress["stage"] != "plan_ready":
            baseline = contract.read_json(root / review_context.BASELINE_NAME, "last finalized")
            progress = {**progress, "plan_path": baseline["plan_path"]}
            progress["plan_digest"] = baseline["plan_digest"]
        self.progress = progress
        self.plan_path = str(progress["plan_path"])
        self.plan_digest = str(progress["plan_digest"])
        _, self.plan = contract.artifact_payload(Path(self.plan_path), "review_plan")


def _errors(result: dict[str, Any]) -> str:
    return json.dumps(result.get("errors"))


def test_related_suggestions_keep_one_finding_separate_actions_and_reject_overlap(
    fixtures: Any,
) -> None:
    _fixture, result, finished = _ready(fixtures, grouped=True)
    _, plan = contract.artifact_payload(Path(str(finished["artifact_path"])), "review_plan")
    assert len(plan["findings"]) == 1
    actions = [a for a in plan["publication_preview"]["actions"] if a["kind"] == "finding"]
    assert len(actions) == 2
    positions = []
    for action in actions:
        argument = next(
            arg for arg in command_argv(str(action["command"])) if arg.startswith("position=")
        )
        positions.append(json.loads(argument[len("position=") :]))
    assert positions[0]["new_line"] == 1
    assert positions[0]["old_line"] == 1
    assert positions[1]["new_line"] == 2
    assert "old_line" not in positions[1]
    assert all(str(item["command"]).startswith("glab api") for item in actions)

    repair = draft_module.repair_review(str(result["artifact_root"]), "fix")
    draft = _read(repair["draft_path"])
    draft["repair"]["rationale"] = "Check the replacement only."
    draft["repair"]["checks"] = ["Reviewed consumers of both independent outputs."]
    draft["content"]["finding_publications"][0]["suggestions"][1]["line"] = 1
    contract.write_json(Path(str(repair["draft_path"])), draft)
    assert "overlap" in _errors(draft_module.check_review(str(repair["draft_path"])))


def test_nested_documentation_fences_cannot_close_a_patch_fence() -> None:
    value = "git apply <<'PATCH'\n context\n ```\n+```yaml\n+x: true\n+```\nPATCH"
    rendered = review_context.code_fence(value, "sh")
    assert rendered.startswith("````sh\n")
    assert rendered.endswith("\n````")
    assert rendered[len("````sh\n") : -len("\n````")] == value


def test_presentation_repair_regenerates_commands_locally_and_dedupes_checks(
    fixtures: Any,
) -> None:
    fixture, result, finished = _ready(fixtures)
    before = Plan(Path(str(result["artifact_root"])))
    repair = draft_module.repair_review(str(result["artifact_root"]), "presentation")
    draft = _read(repair["draft_path"])
    draft["repair"]["rationale"] = (
        "Regenerate transport commands without changing findings or fixes."
    )
    draft["repair"]["checks"] = ["Compared source, findings, positions and critic receipts."]
    draft["content"]["checks"] = [
        "Targeted check passed.",
        "Targeted check passed.",
        "Targeted check was not run.",
    ]
    contract.write_json(Path(str(repair["draft_path"])), draft)
    requests = fixture.request_count()
    repaired = draft_module.finish_review(str(repair["draft_path"]))
    assert repaired["status"] == "ok", json.dumps(repaired)
    assert fixture.request_count() == requests
    after = Plan(Path(str(result["artifact_root"])))
    assert after.plan["findings"] == before.plan["findings"]
    assert after.plan["review_source"]["critics"] == before.plan["review_source"]["critics"]
    assert after.plan["finding_publications"] == before.plan["finding_publications"]
    assert len(after.plan["markdown"].split("- Targeted check passed.")) - 1 == 1
    assert "- Targeted check was not run." in after.plan["markdown"]
    action = next(a for a in after.plan["publication_preview"]["actions"] if a["kind"] == "finding")
    assert re.search(r"-F 'position=\{", str(action["command"]))
    assert "mise exec" not in str(repaired["plan_command"])
    assert finished["status"] == "ok"


def test_presentation_repair_does_not_replace_a_safe_suggestion_with_a_patch(
    fixtures: Any,
) -> None:
    fixture, result, finished = _ready(fixtures)
    root = Path(str(result["artifact_root"]))
    before = Plan(root)
    repair = draft_module.repair_review(str(root), "presentation")
    draft = _read(repair["draft_path"])
    draft["repair"]["rationale"] = (
        "Same assertions and same resulting file; only the fix representation changes."
    )
    draft["repair"]["checks"] = ["Compared old and new prose and all resulting files/modes."]
    draft["content"]["finding_publications"][0].update(
        {
            "fix_mode": "patch",
            "body": "Correct the output.",
            "patch_reason": "Representation equivalence regression fixture.",
            "patch": (
                "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n"
                "@@ -1,2 +1,2 @@\n base\n-reviewed change\n+correct output\n"
            ),
        }
    )
    contract.write_json(Path(str(repair["draft_path"])), draft)
    reads = fixture.request_count()
    assert "safe bounded suggestion" in _errors(
        draft_module.check_review(str(repair["draft_path"]))
    )
    assert fixture.request_count() == reads
    original = cast(
        "dict[str, Any]", before.plan["review_source"]["content"]["finding_publications"][0]
    )
    draft["content"]["finding_publications"][0].update(original)
    draft["content"]["finding_publications"][0].pop("patch_reason", None)
    contract.write_json(Path(str(repair["draft_path"])), draft)
    repaired = draft_module.finish_review(str(repair["draft_path"]))
    assert repaired["status"] == "ok", json.dumps(repaired)
    after = Plan(root)
    assert after.plan_digest != before.plan_digest
    assert after.plan["review_source"]["critics"] == before.plan["review_source"]["critics"]
    assert Path(str(finished["artifact_path"])).stat().st_size > 0
    assert review_context.report_review(str(root))["status"] == "ok"
    markdown = Path(str(repaired["markdown_path"])).read_text(encoding="utf-8")
    assert len(re.findall(r"git apply <<'PATCH_", markdown)) == 0


def test_changed_fix_needs_targeted_checks_but_not_a_new_critic_changed_decisions_do(
    fixtures: Any,
) -> None:
    _fixture, result, _finished = _ready(fixtures)
    root = str(result["artifact_root"])
    presentation = draft_module.repair_review(root, "presentation")
    wrong = _read(presentation["draft_path"])
    wrong["repair"]["rationale"] = "New code."
    wrong["repair"]["checks"] = ["Checked output."]
    wrong["content"]["finding_publications"][0]["body"] = "```suggestion\nnew output\n```"
    contract.write_json(Path(str(presentation["draft_path"])), wrong)
    assert "results differ" in _errors(draft_module.check_review(str(presentation["draft_path"])))
    fix = draft_module.repair_review(root, "fix")
    draft = _read(fix["draft_path"])
    draft["repair"]["rationale"] = "Same confirmed problem, a different complete correction."
    draft["repair"]["checks"] = ["Inspected the affected consumer and verified the new output."]
    draft["content"]["finding_publications"][0]["body"] = "```suggestion\nnew output\n```"
    contract.write_json(Path(str(fix["draft_path"])), draft)
    assert draft_module.finish_review(str(fix["draft_path"]))["status"] == "ok"
    decision = draft_module.repair_review(root, "decision")
    changed = _read(decision["draft_path"])
    changed["repair"]["rationale"] = "Reassessed the release consequence."
    changed["repair"]["checks"] = ["Reviewed affected decision."]
    changed["owner_decision_reasons"] = ["Owner must choose the supported behavior."]
    contract.write_json(Path(str(decision["draft_path"])), changed)
    assert "new independent" in _errors(draft_module.check_review(str(decision["draft_path"])))
    changed["critics"].append(
        {
            **changed["critics"][0],
            "run_id": "targeted-review-run",
            "session_id": "targeted-review-session",
            "findings": [],
        }
    )
    changed["critic_count"] += 1
    contract.write_json(Path(str(decision["draft_path"])), changed)
    assert draft_module.finish_review(str(decision["draft_path"]))["status"] == "ok"


def test_finalization_stays_local_for_ci_only_drift(fixtures: Any) -> None:
    fixture: ReviewFixture = fixtures({"resolved": True, "pipelineStatus": "running"})
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft = complete_draft(_read(result["draft_path"]), result)
    contract.write_json(Path(str(result["draft_path"])), draft)
    config = fixture.read_config()
    config["pipelineStatus"] = "success"
    fixture.config_path.write_text(json.dumps(config))
    requests = fixture.request_count()
    final = draft_module.finish_review(str(result["draft_path"]))
    assert final["status"] == "ok", json.dumps(final)
    assert fixture.request_count() == requests
    assert "CI in the assessed snapshot: running" in Path(str(final["markdown_path"])).read_text(
        encoding="utf-8"
    )
    retained = _read(result["draft_path"])
    assert retained["critics"] == draft["critics"]
    assert retained["evidence_digest"] == draft["evidence_digest"]


def test_material_refresh_preserves_findings_and_decisions_without_critic_receipts(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures()
    result = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft = _finding(complete_draft(_read(result["draft_path"]), result))
    contract.write_json(Path(str(result["draft_path"])), draft)
    config = fixture.read_config()
    config["noteBody"] = "New context about the same problem"
    fixture.config_path.write_text(json.dumps(config))
    following = draft_module.refresh_review(str(result["draft_path"]))
    assert following["status"] == "needs_reassessment"
    retained = _read(following["draft_path"])
    assert retained["findings"] == draft["findings"]
    assert retained["dispositions"] == draft["dispositions"]
    assert retained["critics"] == []
    assert _read(result["draft_path"])["critics"] == draft["critics"]


def test_real_ce_pipeline_and_build_timestamps_are_ci_only_review_inputs_stay_material(
    fixtures: Any,
) -> None:
    fixture: ReviewFixture = fixtures(
        {
            "resolved": True,
            "pipelineStatus": "running",
            "mrPipeline": {"id": 1, "status": "running"},
            "latestBuildStartedAt": "2026-10-01T22:00:00Z",
            "latestBuildFinishedAt": None,
        }
    )
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft = complete_draft(_read(started["draft_path"]), started)
    contract.write_json(Path(str(started["draft_path"])), draft)
    config = fixture.read_config()
    config.update(
        {
            "pipelineStatus": "success",
            "mrPipeline": {"id": 2, "status": "success"},
            "latestBuildStartedAt": "2026-10-01T22:01:00Z",
            "latestBuildFinishedAt": "2026-10-01T22:01:10Z",
        }
    )
    fixture.config_path.write_text(json.dumps(config))
    requests = fixture.request_count()
    assert draft_module.finish_review(str(started["draft_path"]))["status"] == "ok"
    assert fixture.request_count() == requests, "finalization is local-only"
    retained = _read(started["draft_path"])
    assert retained["critics"] == draft["critics"]
    assert retained["evidence_digest"] == draft["evidence_digest"]

    original: dict[str, Any] = {
        "object": {
            "title": "Bound retry",
            "labels": [],
            "sha": fixture.head_sha,
            "has_conflicts": False,
        },
        "pipelines": {"items": []},
    }
    for change in (
        {"title": "Other scope"},
        {"labels": ["blocking"]},
        {"sha": fixture.base_sha},
        {"has_conflicts": True},
    ):
        assert draft_module.analysis_fingerprint(original) != draft_module.analysis_fingerprint(
            {**original, "object": {**original["object"], **change}}
        )


def test_an_unfinished_refreshed_review_does_not_hide_the_last_finalized_plan(
    fixtures: Any,
) -> None:
    fixture, result, finished = _ready(fixtures)
    root = Path(str(result["artifact_root"]))
    old = Plan(root)
    config = fixture.read_config()
    config["noteBody"] = "New conversation evidence"
    fixture.config_path.write_text(json.dumps(config))
    refreshed = draft_module.refresh_review(str(result["draft_path"]))
    assert refreshed["status"] == "needs_reassessment"
    requests = fixture.request_count()
    assert Plan(root).plan_digest == old.plan_digest
    assert fixture.request_count() == requests
    assert Path(str(finished["markdown_path"])).stat().st_size > 0


def test_incomplete_repair_preserves_the_plan_and_historical_plans_cannot_be_repaired(
    fixtures: Any,
) -> None:
    _fixture, result, _finished = _ready(fixtures)
    root = Path(str(result["artifact_root"]))
    original = Plan(root)
    repair = draft_module.repair_review(str(root), "fix")
    assert draft_module.finish_review(str(repair["draft_path"]))["status"] == "invalid"
    assert Plan(root).plan_digest == original.plan_digest
    historical = {**original.plan, "review_contract_version": 6}
    historical.pop("review_source", None)
    path, digest = contract.write_artifact(root, "review_plan", historical)
    contract.write_json(
        root / "review-current.json",
        {**original.progress, "plan_path": str(path), "plan_digest": digest},
    )
    with pytest.raises(contract.WorkflowError, match="historical"):
        draft_module.repair_review(str(root), "presentation")
