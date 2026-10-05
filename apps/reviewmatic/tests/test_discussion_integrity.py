"""Discussion-integrity regressions: degraded discussions fail loudly.

The context collector refuses to continue when the discussion evidence is
unusable: a note without a non-empty body, or a discussion without a root
note, stops the review with an addressed error instead of degrading into a
silently empty artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, make_review_fixture

from reviewmatic import context as review_context
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


def collect_to_context(fixture: ReviewFixture) -> Path:
    target = contract.parse_target(fixture.url, {"merge_requests"})
    bundle: dict[str, Any] = contract.collect(target, "code-review", persist=True)
    root = Path(str(bundle["artifact_root"]))
    review_context.begin_review(
        str(bundle["preview_artifact_path"]),
        str(bundle["preview_digest"]),
        str(root),
        str(fixture.repo),
        "normal",
        "en",
        "auto",
    )
    review_context.prepare_context(
        str(bundle["preview_artifact_path"]), str(fixture.repo), "auto", "normal", "en"
    )
    return root


def test_empty_note_body_is_a_loud_refusal() -> None:
    fixture = make_review_fixture(
        {"replies": [{"id": 43, "system": False, "body": ""}]},
    )
    try:
        with pytest.raises(contract.WorkflowError, match="empty or missing body"):
            collect_to_context(fixture)
        stores = [path for path in (fixture.tmp / "state").rglob("review_context") if path.is_dir()]
        assert all(not any(path.iterdir()) for path in stores)
    finally:
        fixture.close()


def test_discussion_without_root_note_is_a_loud_refusal() -> None:
    with pytest.raises(contract.WorkflowError, match="has no root note"):
        review_context.annotate_discussion(
            {"id": "discussion-42", "individual_note": False, "notes": []},
            "https://gitlab.example/group/project/-/merge_requests/7",
        )


def test_nonempty_bodies_still_collect() -> None:
    fixture = make_review_fixture()
    try:
        root = collect_to_context(fixture)
        progress = review_context.load_progress(root)
        assert progress is not None
        assert progress["stage"] == "context_ready"
        artifact = review_context.progress_artifact(root, progress, "context", "review_context")
        assert artifact is not None
        _path, payload, _digest = artifact
        assert payload["counts"]["discussions"] == 1
        assert payload["counts"]["content_notes"] == 1
    finally:
        fixture.close()
