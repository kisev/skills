"""Wave-V: located SHA refusals, pure scrub previews, input-key records, echoes.

The tail of a live review bisected sections blindly because one raw-SHA line
said nothing about place or token. Now the scanner is a pure listing, a new
scrub-preview command names every exposure before finalization, the
publication input error separates input keys from runtime-stamped fields, and
scaffold and check echo what they actually read.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic import publication_skeletons
from reviewmatic.cli import main as cli_main
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _stdout_json(capsys: Any) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(capsys.readouterr().out))


def test_raw_ref_refusal_names_the_place_token_and_source(fixture: ReviewFixture) -> None:
    head = fixture.head_sha
    markdown = (
        "# Review\n"
        f"The change lands in {head} today.\n"
        "## Middle\n"
        f"Also visible: {head[:10]} in prose.\n"
    )
    violations = review_context.visible_raw_ref_violations(
        markdown,
        {"head_sha": head, "base_sha": fixture.base_sha, "start_sha": fixture.base_sha},
        None,
    )
    assert [(item["line"], item["source"]) for item in violations] == [
        (2, "evidence head_sha"),
        (4, "evidence head_sha"),
    ]
    with pytest.raises(contract.WorkflowError) as excinfo:
        review_context.reject_visible_raw_refs(
            markdown,
            {"head_sha": head, "base_sha": fixture.base_sha, "start_sha": fixture.base_sha},
            None,
        )
    message = str(excinfo.value)
    assert "first at line 2" in message
    assert f"token '{head[:12]}'" in message
    assert f"(length {len(head)})" in message
    assert "from evidence head_sha" in message
    assert "1 more exposure(s) at line(s) 4" in message
    # The executable glab-position lines keep their exception.
    safe = f"glab api -F 'position[base_sha]={head}' projects/x"
    assert (
        review_context.visible_raw_ref_violations(
            safe, {"head_sha": head, "base_sha": head, "start_sha": head}, None
        )
        == []
    )


def test_scrub_preview_lists_every_exposure_and_writes_nothing(
    fixture: ReviewFixture, capsys: Any
) -> None:
    head = fixture.head_sha
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])
    draft = contract.read_json(Path(draft_path), "draft")
    content = cast("dict[str, Any]", draft["content"])
    content["summary"] = f"The change lands in {head}."
    content["architecture_assessment"] = f"Owner unchanged; see {head[:9]}."
    threads = cast("list[dict[str, Any]]", content["thread_decisions"])
    threads[0]["proposed_response"] = f"Fixed by {head} - the key is now documented."
    contract.write_json(Path(draft_path), draft)

    code = cli_main(["scrub-preview", "--draft", draft_path, "--json"])
    assert code == 1
    result = _stdout_json(capsys)
    assert result["status"] == "violations"
    named = {(item["field"], item["line"]) for item in result["violations"]}
    assert ("$.content.summary", 1) in named
    assert ("$.content.architecture_assessment", 1) in named
    assert ("$.content.thread_decisions[0].proposed_response", 1) in named
    assert len(result["violations"]) >= 3
    assert all(item["source"] == "evidence head_sha" for item in result["violations"])
    assert "Nothing was written" in result["note"]
    # A clean draft answers ok with exit 0.
    content["summary"] = "The change lands today."
    content["architecture_assessment"] = "Owner unchanged."
    threads[0]["proposed_response"] = "The key is now documented."
    contract.write_json(Path(draft_path), draft)
    capsys.readouterr()
    code = cli_main(["scrub-preview", "--draft", draft_path, "--json"])
    assert code == 0
    clean = _stdout_json(capsys)
    field_violations = [
        item for item in clean["violations"] if not str(item["field"]).startswith("plan")
    ]
    assert field_violations == []
    assert "compile_note" in clean or clean["markdown_scrubbed"] is True


def test_publication_input_error_separates_runtime_stamped_fields() -> None:
    row = {
        "finding_id": "docs-1",
        "type": "general",
        "path": None,
        "line": None,
        "old_line": None,
        "body": "Prose.",
        "fix_mode": "patch",
        "patch": "diff --git a/a b/a\n",
        "patch_path": "/state/patches/x.patch",
    }
    with pytest.raises(contract.WorkflowError) as excinfo:
        review_context.validate_finding_publications([row], {"docs-1"})
    message = str(excinfo.value)
    assert "input keys: body, finding_id, fix_mode, line, old_line, patch, path, type" in message
    assert "runtime stamps: patch_path, patch_sha256, revision - do not set them" in message
    assert "unexpected here: patch_path" in message
    # The skeletons never emit the stamped fields.
    skeletons = publication_skeletons.publication_skeletons([{"id": "docs-1"}], "reviewer")
    assert all(not {"patch_path", "patch_sha256", "revision"} & set(item) for item in skeletons)


def test_check_and_scaffold_echo_what_they_read(fixture: ReviewFixture, capsys: Any) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    assert started["status"] == "ok"
    draft_path = str(started["draft_path"])
    checked = draft_module.check_review(draft_path)
    assert checked["status"] == "invalid"
    assert checked["echo"]["publications"] == 0
    assert checked["echo"]["findings"] == 0
    assert isinstance(checked["echo"]["thread_outcomes"], dict)
