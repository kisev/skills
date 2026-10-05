"""Schema diagnostics and suggestion-fix regressions ported from the TS suite.

Mirrors ``repair.test.mjs`` scenarios that exercise the leaf modules directly
(``schema_issues`` walker and ``fixes`` suggestion synthesis); the full
end-to-end repair scenarios land with the draft state-machine port.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from reviewmatic.fixes import SuggestionPart, suggestion_body, suggestions_patch
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.schema_issues import schema_issues

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(name="repo")
def git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    git("config", "user.email", "fixture@example")
    git("config", "user.name", "Fixture")
    git("config", "commit.gpgsign", "false")
    return root


def test_semver_diagnostic_identifies_invalid_object_keys() -> None:
    schema = contract.artifact_schema()
    issues = schema_issues(
        schema["$defs"]["semver_assessment"],
        {
            "mode": "release",
            "policy": "Tags",
            "sources": ["catalog"],
            "baseline": {"name": "v1.0.0", "commit": "a" * 40, "source": "tags"},
            "target_branch": "main",
            "target_sha": "b" * 40,
            "target_revision": "current",
            "fallback_reason": None,
            "release_impact": "patch",
            "release_rationale": "Existing fix.",
        },
        "$",
        schema,
    )
    assert any(item["path"].endswith("baseline.sha") for item in issues)
    assert any(item["path"].endswith("baseline.commit") for item in issues)
    assert not any(
        item["path"].endswith("baseline") and '"null"' in item["message"] for item in issues
    )


def test_bounded_suggestions_preserve_files_without_a_final_newline(repo: Path) -> None:
    (repo / "review.txt").write_text("base\nreviewed change")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qam", "remove final newline")
    head = _git(repo, "rev-parse", "HEAD")
    patch = suggestions_patch(
        str(repo),
        head,
        [
            SuggestionPart(
                "review.txt",
                2,
                "```suggestion:-1+0\ncorrect base\ncorrect output\n```",
            )
        ],
    )
    (repo / "candidate.patch").write_text(patch)
    _git(repo, "apply", "--check", "candidate.patch")
    _git(repo, "apply", "candidate.patch")
    assert (repo / "review.txt").read_text() == "correct base\ncorrect output"


def test_suggestions_patch_rejects_overlap_escape_and_noop(repo: Path) -> None:
    (repo / "review.txt").write_text("one\ntwo\nthree\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qam", "base")
    head = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(contract.WorkflowError, match="overlap or escape"):
        suggestions_patch(
            str(repo),
            head,
            [
                SuggestionPart("review.txt", 2, "```suggestion:-1+1\nTWO\n```"),
                SuggestionPart("review.txt", 3, "```suggestion:-1+1\nTHREE\n```"),
            ],
        )
    with pytest.raises(contract.WorkflowError, match="escapes the repository"):
        suggestions_patch(
            str(repo), head, [SuggestionPart("../escape.txt", 1, "```suggestion\nx\n```")]
        )
    with pytest.raises(contract.WorkflowError, match="does not change"):
        suggestions_patch(
            str(repo),
            head,
            [SuggestionPart("review.txt", 2, "```suggestion\ntwo\n```")],
        )


def test_complete_suggestion_bodies_do_not_repeat_a_shared_introduction() -> None:
    part = SuggestionPart(
        "review.txt",
        2,
        "Correct this output.\n\n```suggestion\ncorrect output\n```",
    )
    assert suggestion_body("General explanation.", part) == part.body
    bare = SuggestionPart(part.path, part.line, "```suggestion\ncorrect output\n```")
    assert suggestion_body("General explanation.", bare) == (f"General explanation.\n\n{bare.body}")


def _git(root: Path, *arguments: str) -> str:
    result: dict[str, Any] = {}
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    result["stdout"] = completed.stdout
    return completed.stdout.strip()
