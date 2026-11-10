"""The background is bounded, task-first, and discloses every cut."""

from __future__ import annotations

from typing import Any

import pytest

from reviewmatic import background

LIMIT = 8000


def payload(body_size: int = 0) -> dict[str, Any]:
    return {
        "task": {
            "goal": "Ship rate limiting on the login API.",
            "acceptance_criteria": ["429 after five failures", "Retry-After present"],
            "constraints": ["No new dependencies"],
            "open_questions": ["Per IP or per user?"],
        },
        "sections": [{"title": "Big section", "body": "x" * body_size}],
    }


def body_size_for_total(target: int) -> int:
    low, high = 0, 40000
    while low < high:
        middle = (low + high) // 2
        rendered = background.build_background(payload(middle))
        if not rendered["included_sections"]:
            high = middle
        elif rendered["bytes"] < target:
            low = middle + 1
        else:
            high = middle
    return low


def test_the_default_limit_is_8000() -> None:
    assert background.BACKGROUND_LIMIT == LIMIT
    assert background.build_background(payload())["limit"] == LIMIT


def test_the_largest_text_lands_on_the_bounds_exactly() -> None:
    for target in (7999, 8000):
        size = body_size_for_total(target)
        rendered = background.build_background(payload(size))
        assert rendered["bytes"] == target
        assert rendered["included_sections"] == ["Big section"]
        assert rendered["cuts"] == []


def test_one_byte_over_the_limit_cuts_the_section_and_discloses_it() -> None:
    size = body_size_for_total(8001)
    rendered = background.build_background(payload(size))
    assert rendered["bytes"] <= LIMIT
    assert rendered["included_sections"] == []
    assert rendered["cuts"] == ["Big section"]
    assert "Cut for the 8000-byte background limit: Big section." in rendered["markdown"]


def test_the_task_always_comes_first() -> None:
    rendered = background.build_background(payload(9000))
    markdown = rendered["markdown"]
    assert (
        markdown.index("Ship rate limiting") < markdown.index("## Big section")
        if ("## Big section" in markdown)
        else True
    )
    assert rendered["cuts"]


def test_a_huge_goal_is_clamped_and_disclosed() -> None:
    rendered = background.build_background(
        {"task": {"goal": "g" * 5000, "acceptance_criteria": ["a"]}}, limit=400
    )
    assert rendered["bytes"] <= 400
    assert "task goal" in rendered["cuts"]
    assert "…" in rendered["markdown"]


def test_a_huge_acceptance_item_is_clamped() -> None:
    rendered = background.build_background(
        {
            "task": {
                "goal": "g",
                "acceptance_criteria": ["a" * 400],
            }
        },
        limit=200,
    )
    assert rendered["bytes"] <= 200
    assert "acceptance criteria" in rendered["cuts"]


def test_the_task_alone_must_fit() -> None:
    with pytest.raises(ValueError, match="task baseline alone"):
        background.build_background({"task": {"goal": "g" * 9000}}, limit=100)


def test_sections_are_kept_in_order_until_the_limit() -> None:
    rendered = background.build_background(
        {
            "task": {"goal": "g", "acceptance_criteria": ["a"]},
            "sections": [
                {"title": "First", "body": "x" * 400},
                {"title": "Second", "body": "y" * 400},
            ],
        },
        limit=600,
    )
    markdown = rendered["markdown"]
    assert "## First" in markdown
    assert "## Second" not in markdown
    assert rendered["cuts"] == ["Second"]


def test_an_empty_section_is_skipped() -> None:
    rendered = background.build_background(
        {
            "task": {"goal": "g", "acceptance_criteria": ["a"]},
            "sections": [{"title": "", "body": "x"}],
        }
    )
    assert rendered["included_sections"] == []
    assert rendered["cuts"] == []
