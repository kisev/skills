"""Human report regressions using a synthetic project and discussions."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.test_review_semver import fallback_assessment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def review(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    scripts = ROOT / ".build/skills/code-review/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    for name in list(sys.modules):
        if name == "portable_runtime" or name.startswith("portable_runtime."):
            monkeypatch.delitem(sys.modules, name)
    spec = importlib.util.spec_from_file_location(
        "report_regression", scripts / "review_context.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compact_report_keeps_one_decision_and_copyable_local_fix(review: ModuleType) -> None:
    url = "https://gitlab.example/team/chart/-/merge_requests/1"
    patch = (
        "diff --git a/job.txt b/job.txt\n--- a/job.txt\n+++ b/job.txt\n@@ -1 +1 @@\n-old\n+new\n"
    )
    threads = [
        {
            "id": "1",
            "url": url + "#note_1",
            "state": "resolved",
            "outcome": "no_publication",
            "rationale": "Existing explanation confirmed by current code.",
        },
        {
            "id": "2",
            "url": url + "#note_2",
            "state": "resolved",
            "outcome": "no_publication",
            "rationale": "Applied suggestion verified against current code.",
        },
        {
            "id": "3",
            "url": url + "#note_3",
            "state": "resolved",
            "outcome": "reopen",
            "rationale": "The failing path still exists.",
        },
        {
            "id": "4",
            "url": url + "#note_4",
            "state": "open",
            "outcome": "local_fix",
            "rationale": "Repair the local path.",
            "proposed_response": "Use the corrected value.",
            "fix_mode": "patch",
            "patch": patch,
        },
    ]
    content = {
        "locale": "en",
        "summary": "One remaining defect.",
        "presentation": review.localized_presentation("en", "author", "not_ready", "full"),
        "previous_finding_assessments": [],
        "finding_publications": [],
        "recommended_issues": [],
        "findings": [],
        "thread_decisions": threads,
        "label_review": {"add": ["type::feature"], "remove": ["feature"]},
        "architecture_assessment": "Existing ownership is preserved.",
        "semver_impact": "minor",
        "semver_rationale": "Compatible option.",
        "semver_assessment": fallback_assessment(),
        "checks": ["Compared current code."],
    }
    actions: list[dict[str, Any]] = [
        {
            "id": "reply-3",
            "kind": "thread",
            "publication_id": "thread-3",
            "operation": "reply",
            "command": "glab api --method POST discussions/3/notes",
        },
        {
            "id": "reopen-3",
            "kind": "thread",
            "publication_id": "thread-3",
            "operation": "reopen",
            "command": "glab api --method PUT discussions/3 -F resolved=false",
        },
        {
            "id": "labels",
            "kind": "labels",
            "publication_id": None,
            "operation": "update_labels",
            "command": "glab mr update 1 --label type::feature --unlabel feature",
        },
    ]
    publication = {
        "actions": actions,
        "body_files": [
            {
                "publication_id": "thread-3",
                "path": "/private/body.md",
                "content": "The fix misses the retry path.\n\n```sh\ngit apply <<'PATCH'\n"
                + patch
                + "PATCH\n```",
            }
        ],
    }
    metadata = {
        "assessment": {
            field: {"rationale": "Looks correct.", "recommendation": None}
            for field in ("title", "description", "workflow_state", "overall")
        }
    }
    report = review.review_markdown(
        {"target": {"url": url}, "head_sha": "a" * 40},
        {
            "role": "author",
            "target": {"url": url},
            "exact_git": {"repo_root": str(ROOT)},
        },
        {},
        content,
        metadata,
        publication,
    )
    release = json.loads((ROOT / "packages/skills/package.json").read_text())["version"]
    assert f"code-review: {release} · contract: 6" in report
    assert "**Title:** Looks correct." in report
    assert report.index(actions[-1]["command"]) < report.index("## Closed threads")
    for action in actions:
        assert report.count(action["command"]) == 1
    assert report.index("Publish reply:") < report.index("After successful publication, reopen")
    assert report.count("git apply <<'PATCH'") == 1
    assert "marker-run --skill code-review --action patch:" in report
    assert "git -C " in report and " apply --check <<'PATCH_CHECK_" in report
    assert "Existing explanation confirmed" in report
    assert "Applied suggestion verified" in report
    for noise in (
        "operation:",
        "fix_mode:",
        "position:",
        "/private/body.md",
        "## Manual publication",
        "### `title`",
    ):
        assert noise not in report


def test_model_label_assessment_replaces_semantic_plain_alias(review: ModuleType) -> None:
    evidence = {
        "object": {"labels": ["enhancement"]},
        "labels": {
            "complete": True,
            "items": [
                {"name": "enhancement", "description": "New compatible capability"},
                {"name": "type::feature", "description": "New compatible capability"},
            ],
        },
    }
    assessed = [
        {
            "name": "enhancement",
            "status": "inapplicable",
            "rationale": "Equivalent to the preferred scoped type.",
        },
        {
            "name": "type::feature",
            "status": "applicable",
            "rationale": "Describes the feature using the project namespace.",
        },
    ]
    delta = review.validate_label_assessments(evidence, assessed, "none")
    assert delta["add"] == ["type::feature"]
    assert delta["remove"] == ["enhancement"]


def test_patch_markers_are_isolated_by_review_checkout(review: ModuleType, tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    evidence = {
        "target": {"url": "https://gitlab.example/team/chart/-/merge_requests/1"},
        "head_sha": "a" * 40,
    }
    fix = {"patch": "diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-old\n+new\n"}

    first_command = review.render_patch_command(
        evidence, {"exact_git": {"repo_root": str(first)}}, fix
    )
    second_command = review.render_patch_command(
        evidence, {"exact_git": {"repo_root": str(second)}}, fix
    )

    assert first_command != second_command
    assert str(first) in first_command and str(second) not in first_command
    assert str(second) in second_command and str(first) not in second_command
