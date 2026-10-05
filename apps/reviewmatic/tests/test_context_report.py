"""Human report regressions revived from the pre-port review report suite.

The ancestors loaded the skill archive build through an importlib hook; the
package revival imports ``reviewmatic.context`` directly and keeps the same
scenarios, including the materialized release version assertion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reviewmatic import __version__
from reviewmatic import context as review
from reviewmatic.portable.portable_gitlab.label_assessment import validate_label_assessments

ROOT = Path(__file__).resolve().parents[3]


def fallback_assessment() -> dict[str, Any]:
    # Mirrors tests/test_review_semver.py so the package stays self-contained.
    return {
        "mode": "target_fallback",
        "policy": "No publication policy could be established from repository documentation or CI.",
        "sources": ["README.md and CI configuration at the reviewed head; empty release catalog"],
        "baseline": None,
        "target_branch": "main",
        "target_sha": "b",
        "target_revision": "mr_snapshot",
        "fallback_reason": "No confirmed publication baseline is available.",
        "release_impact": None,
        "release_rationale": None,
    }


def test_compact_report_keeps_one_decision_and_copyable_local_fix() -> None:
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
        {
            "target": {"url": url, "iid": 1},
            "project": {"id": 7, "hostname": "gitlab.example"},
            "head_sha": "a" * 40,
        },
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
    assert f"code-review: {__version__} · contract: {review.REVIEW_CONTRACT_VERSION}" in report
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


def test_model_label_assessment_replaces_semantic_plain_alias() -> None:
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
    delta = validate_label_assessments(evidence, assessed, "none")
    assert delta["add"] == ["type::feature"]
    assert delta["remove"] == ["enhancement"]


def test_patch_markers_are_isolated_by_review_checkout(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    evidence = {
        "target": {"url": "https://gitlab.example/team/chart/-/merge_requests/1", "iid": 1},
        "project": {"id": 7, "hostname": "gitlab.example"},
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


def test_publication_make_command_keeps_plain_glab_commands(tmp_path: Path) -> None:
    # The revived publication module only rewrites exact line notes; every other
    # glab command passes through the shared shell quoting unchanged.
    from reviewmatic import publication as publication_module

    assert (
        publication_module.make_command(
            str(tmp_path), {}, {}, "reply", ["glab", "mr", "update"], {}, {}
        )
        == "glab mr update"
    )


def test_structured_preview_accepts_manual_actions() -> None:
    from reviewmatic.portable.portable_gitlab import contract

    value = {
        "mr_state": "opened",
        "warning": "No command was executed.",
        "body_files": [
            {
                "publication_id": "p1",
                "revision": 1,
                "kind": "finding",
                "path": "/private/body.md",
                "content": "body",
            }
        ],
        "actions": [
            {
                "id": "a1",
                "kind": "finding",
                "publication_id": "p1",
                "operation": "create_general",
                "command": "glab api ...",
                "path": None,
                "line": None,
            }
        ],
    }
    assert contract.review_publication_preview_is_valid(value)
    assert not contract.review_publication_preview_is_valid({**value, "preflight": 1})
