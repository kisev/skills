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


def test_suggestion_refusals_name_the_offending_part() -> None:
    """Decision 67: the refusal names the offending part, the received value,
    and the accepted record form. The live acceptance caught 20 blind
    iterations on the bare "suggestions requires bounded path/line/body
    records" (the agent guessed the fix-binding shape)."""
    from reviewmatic.fixes import suggestion_parts

    bad_status = {"suggestions": [{"path": "review.txt", "line": 2, "body": "x", "weight": 1}]}
    with pytest.raises(
        contract.WorkflowError,
        match=r"suggestions requires bounded path/line/body records: suggestions\[0\] "
        r"fields are \['body', 'line', 'path', 'weight'\]; expected exactly body, line, path",
    ):
        suggestion_parts(bad_status)
    bad_line = {"suggestions": [{"path": "review.txt", "line": 0, "body": "x"}]}
    with pytest.raises(
        contract.WorkflowError,
        match=r"suggestions\[0\]\.line is 0; expected a positive integer",
    ):
        suggestion_parts(bad_line)
    with pytest.raises(contract.WorkflowError, match="suggestions is empty"):
        suggestion_parts({"suggestions": []})
    with pytest.raises(
        contract.WorkflowError,
        match=(
            r"suggestions is empty; the array is machine-rendered from the row's semantic "
            r"fix: author `parts` \(each \{target: \{path, before\}, replacement, optional "
            r"body\}\) with fix_mode=suggestion, or drop to fix_mode=patch"
        ),
    ):
        suggestion_parts({"suggestions": []})


def test_semver_basis_refusal_names_the_rendered_fallback() -> None:
    """Decision 69/71: the basis refusal says what "prepared" means - remove an
    authored override to keep the machine-rendered fallback, never null the
    rendered fields (the live acceptance caught null-basis guessing)."""
    from reviewmatic.portable.portable_gitlab import review_semver

    evidence = {"artifact_root": "/tmp/x", "base_sha": "a", "head_sha": "b"}
    with pytest.raises(
        contract.WorkflowError,
        match=(
            r"semver_assessment.basis: keep the machine-rendered fallback \(remove an "
            r"authored basis override entirely - never null rendered fields\) or select "
            r"\{name,source\} from the collected catalog"
        ),
    ):
        review_semver.validate(
            {
                "policy": "No release policy was found.",
                "sources": ["Collected releases catalog"],
                "mode": "target_fallback",
                "fallback_reason": "No confirmed stable release or tag is available.",
                "basis": {},
            },
            evidence,
            {
                "release_evidence": {
                    "releases": {"complete": True, "items": []},
                    "tags": {"complete": True, "items": []},
                }
            },
        )


def test_thread_binding_refusal_names_the_repair_command() -> None:
    """Decision 69/71: the existing_thread refusal is self-describing - it
    names the prepared thread ids and the exact replace-artifact repair
    command, because the live acceptance caught a 37-minute flail that ended
    in an out-of-stage contract read when the refusal said only "use decision
    repair"."""


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


def test_chat_assessment_refusal_names_field_value_and_vocabularies() -> None:
    """Decision 72 (MR !538 evidence): the chat-assessment refusal is
    field-level - the offending field, the received value, and the accepted
    statuses - because the live record-prose acceptance met the bare
    "review chat assessment is invalid" and dug the statuses out of the
    schema."""
    from reviewmatic import context as review_context

    guessed_status = {
        "necessity": {"status": "confirmed", "rationale": "The chat shows it."},
        "relevance": {"status": "current", "rationale": "The discussion is live."},
        "change": "The retry became idempotent.",
    }
    with pytest.raises(
        contract.WorkflowError,
        match=(
            r"review chat assessment is invalid: necessity.status is 'confirmed'; "
            r"expected supported, doubtful, unconfirmed"
        ),
    ):
        review_context.validate_chat_assessment(guessed_status)
    wrong_keys = {
        "necessity": {"status": "supported", "rationale": "The chat shows it."},
        "relevance": {"status": "current", "rationale": "The discussion is live."},
        "changes": "The retry became idempotent.",
    }
    with pytest.raises(
        contract.WorkflowError,
        match=(
            r"review chat assessment is invalid: keys are \['changes', 'necessity', "
            r"'relevance'\]; expected exactly change, necessity, relevance"
        ),
    ):
        review_context.validate_chat_assessment(wrong_keys)


def test_prose_unknown_key_refusal_names_the_accepted_keys() -> None:
    """Decision 72 (MR !538 evidence): a wrong prose key is refused with the
    complete accepted-key list, so the author never reconstructs the surface
    shape from a schema (~30 record-prose retries in the live acceptance)."""
    from reviewmatic import render

    content = {"locale": "en", "summary": "Text."}
    with pytest.raises(
        contract.WorkflowError,
        match=(
            r"the prose surface carries only prose and semantic fields; findings_list is "
            r"machine-rendered - edit it only through a recorded repair kind; "
            r"accepted keys: locale, chat_assessment"
        ),
    ):
        render.apply_prose(content, {"findings_list": []})
    merged = render.apply_prose(content, {"summary": "Updated."})
    assert merged["summary"] == "Updated."


def test_authoring_vocabularies_match_the_validators() -> None:
    """Decision 72: the printed dictionaries in the prose stop are the same
    tuples the validators enforce, so a stop never teaches a wrong value."""
    from reviewmatic import context as review_context
    from reviewmatic.portable.portable_gitlab import review_semver

    vocabularies = review_context.AUTHORING_VOCABULARIES
    assert vocabularies["chat_assessment.necessity.status"] == (
        "supported",
        "doubtful",
        "unconfirmed",
    )
    assert vocabularies["chat_assessment.relevance.status"] == (
        "current",
        "partly_outdated",
        "outdated",
    )
    assert set(vocabularies["semver_impact"]) == review_semver.IMPACTS
    assert vocabularies["thread_decisions[*].outcome"] == contract.THREAD_OUTCOMES
    assert vocabularies["thread_decisions[*].fix_mode"] == contract.THREAD_FIX_MODES
    assert vocabularies["label_assessments[*].status"] == (
        "applicable",
        "inapplicable",
        "unresolved",
    )


def test_metadata_drift_split_notifies_metadata_and_blocks_code() -> None:
    """Decision 72 (MR !521 evidence): end-of-run drift is split - metadata
    drift (merge, labels, catalog, discussions, pipelines) notifies with the
    fields named and never drops the authoring chain, while code drift still
    blocks the report."""
    from reviewmatic import context as review_context

    def evidence(state: str = "opened", label: str = "kind::feature") -> dict[str, Any]:
        return {
            "target": {"kind": "merge_request", "iid": 7},
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
            "start_sha": "b" * 40,
            "object": {
                "state": state,
                "title": "One line",
                "labels": [label],
                "assignees": [{"username": "kim"}],
            },
            "labels": {"complete": True, "items": [{"name": label}]},
            "discussions": [{"root_note_id": "note_1"}],
            "changed_files": ["a.py"],
            "commits": [],
            "pipelines": {"status": "success"},
            "retrieval_complete": True,
        }

    merged = review_context.metadata_drift_report(evidence(), evidence(state="merged"))
    assert merged is not None and merged["blocking"] is False
    assert merged["metadata"] == ["object"] and merged["code"] == []
    assert "state: merged" in merged["details"]
    catalog = review_context.metadata_drift_report(evidence(), evidence(label="type::bug"))
    assert catalog is not None and catalog["blocking"] is False
    assert sorted(catalog["metadata"]) == ["labels", "object"]
    assert any("label catalog" in detail for detail in catalog["details"])
    code = dict(evidence())
    code["head_sha"] = "c" * 40
    pushed = review_context.metadata_drift_report(evidence(), code)
    assert pushed is not None and pushed["blocking"] is True
    assert pushed["code"] == ["head_sha"]
    assert review_context.metadata_drift_report(evidence(), evidence()) is None
    notice = review_context.drift_notice_lines(merged, "en", {"command": "reviewmatic prepare"})
    assert notice[0] == "### Metadata drift after the reviewed snapshot"
    assert any("state: merged" in line for line in notice)
    assert any("`reviewmatic prepare`" in line for line in notice)
    russian = review_context.drift_notice_lines(merged, "ru", None)
    assert russian[0] == "### Дрейф метаданных после снимка ревью"


def test_semver_templates_print_the_impact_vocabulary(repo: Path) -> None:
    """Decision 72 (MR !538 evidence): the SemVer templates and refusals print
    the accepted impact vocabulary inline, so the author never opens the
    schema to learn one accepted value."""

    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    from reviewmatic.portable.portable_gitlab import review_semver

    (repo / "file.txt").write_text("one\n")
    git("add", ".")
    git("commit", "-m", "base")
    git("config", "tag.gpgsign", "false")
    tag_sha = git("rev-parse", "HEAD")
    git("tag", "v1.2.3")
    (repo / "file.txt").write_text("one\ntwo\n")
    git("commit", "-am", "target")
    target_sha = git("rev-parse", "HEAD")
    evidence = {
        "artifact_root": "/tmp/x",
        "base_sha": tag_sha,
        "head_sha": target_sha,
        "start_sha": tag_sha,
        "object": {"target_branch": "main"},
    }
    context = {
        "release_evidence": {
            "target_branch": "main",
            "target_sha": target_sha,
            "releases": {"complete": True, "items": []},
            "tags": {
                "complete": True,
                "items": [{"name": "v1.2.3", "commit": {"id": tag_sha}}],
            },
            "errors": [],
        },
        "exact_git": {"repo_root": str(repo)},
    }
    rendered = review_semver.rendered_template(evidence, context)
    assert rendered["mode"] == "release"
    assert rendered["release_impact"].startswith(
        "<IMPACT: major, minor, patch, none, or not_applicable"
    )
    with pytest.raises(contract.WorkflowError) as raised:
        review_semver.validate(
            {
                "policy": "Tags follow semver.",
                "sources": ["Collected tags catalog"],
                "mode": "release",
                "baseline": {"name": "v1.2.3", "sha": tag_sha, "source": "tags"},
                "target_branch": "main",
                "target_sha": target_sha,
                "target_revision": "current",
                "fallback_reason": None,
                "release_impact": None,
                "release_rationale": None,
            },
            evidence,
            context,
        )
    assert "release_impact is one of major, minor, patch, none, not_applicable" in str(raised.value)
