"""Collection is read-only, exact, complete, and redacted."""

from __future__ import annotations

from typing import Any, cast

import pytest

from reviewmatic import collect
from reviewmatic.portable.portable_gitlab import contract

URL = "https://gitlab.example.com/group/project/-/merge_requests/7"
BASE = "b" * 40
START = "c" * 40
HEAD = "a" * 40


def result(complete: bool = True, **extra: object) -> dict[str, object]:
    return {
        "items": [],
        "complete": complete,
        "errors": [] if complete else ["failed"],
        "pages": 1,
        "truncated": not complete,
        **extra,
    }


def responses(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "projects/group%2Fproject": {"id": 11},
        "projects/11/merge_requests/7": {
            "iid": 7,
            "sha": HEAD,
            "title": "Add retry",
            "description": "Implements retries. token=supersecret",
            "state": "opened",
            "labels": ["feature"],
            "source_branch": "retry",
            "target_branch": "dev",
            "web_url": URL,
            "author": {"username": "dev"},
            "diff_refs": {"base_sha": BASE, "start_sha": START, "head_sha": HEAD},
        },
        "projects/11/merge_requests/7/changes": {
            "diff_refs": {"base_sha": BASE, "start_sha": START, "head_sha": HEAD},
            "changes": [{"old_path": "a.py", "new_path": "a.py", "diff": "@@ -1 +1 @@"}],
        },
        "projects/11/issues/2": {
            "iid": 2,
            "title": "Retry lost responses",
            "description": "Retry safely.",
            "labels": ["bug"],
            "state": "opened",
            "web_url": "https://gitlab.example.com/group/project/-/issues/2",
        },
    }
    data.update(overrides)
    return data


def pages(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "projects/11/merge_requests/7/discussions": result(
            items=[
                {
                    "id": "abc",
                    "notes": [{"body": "is retry idempotent? token=leaked"}],
                }
            ]
        ),
        "projects/11/merge_requests/7/pipelines": result(
            items=[{"id": 100, "sha": HEAD, "status": "failed", "web_url": "u"}]
        ),
        "projects/11/pipelines/100/jobs": result(
            items=[
                {"name": "lint", "stage": "test", "status": "failed", "web_url": "j"},
                {"name": "build", "stage": "build", "status": "success", "web_url": "b"},
            ]
        ),
        "projects/11/merge_requests/7/closes_issues": result(items=[{"project_id": 11, "iid": 2}]),
    }
    data.update(overrides)
    return data


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": []}
    table = responses()
    page_table = pages()

    def fake_glab(hostname: str, endpoint: str) -> object:
        state["calls"].append(("glab_json", hostname, endpoint))
        return table[endpoint]

    def fake_paginated(hostname: str, endpoint: str, *, max_pages: int = 100) -> dict[str, object]:
        state["calls"].append(("paginated", hostname, endpoint))
        value = page_table[endpoint]
        assert isinstance(value, dict)
        return cast("dict[str, object]", value)

    monkeypatch.setattr(contract, "glab_json", fake_glab)
    monkeypatch.setattr(contract, "paginated", fake_paginated)
    state["update_glab"] = table.update
    state["update_pages"] = page_table.update
    return state


def test_successful_collection_records_exact_refs_and_completeness(fake: dict[str, Any]) -> None:
    payload = collect.collect(URL)
    assert payload["status"] == "complete"
    assert payload["retrieval_complete"] is True
    assert payload["refs"] == {"base_sha": BASE, "start_sha": START, "head_sha": HEAD}
    assert payload["components_complete"]["changed_files"] is True
    assert payload["components_complete"]["discussions"] is True
    assert payload["linked_issues"]["items"][0]["title"] == "Retry lost responses"
    assert payload["external_mutations"] is False
    assert all(call[0] in {"glab_json", "paginated"} for call in fake["calls"])


def test_redaction_applies_to_every_text_field(fake: dict[str, Any]) -> None:
    payload = collect.collect(URL)
    rendered = str(payload)
    assert "supersecret" not in rendered
    assert "leaked" not in rendered
    assert "[REDACTED]" in rendered


def test_a_failed_page_makes_the_result_partial(fake: dict[str, Any]) -> None:
    fake["update_pages"]({"projects/11/merge_requests/7/discussions": result(complete=False)})
    payload = collect.collect(URL)
    assert payload["status"] == "partial"
    assert payload["components_complete"]["discussions"] is False
    assert payload["discussions"]["errors"] == ["failed"]


def test_missing_discussions_are_named_not_empty(fake: dict[str, Any]) -> None:
    fake["update_pages"](
        {
            "projects/11/merge_requests/7/discussions": result(
                complete=False, items=[], errors=["GitLab pagination failed"]
            )
        }
    )
    payload = collect.collect(URL)
    assert payload["status"] == "partial"
    assert payload["discussions"]["items"] == []
    assert payload["discussions"]["complete"] is False
    assert payload["discussions"]["errors"] == ["GitLab pagination failed"]


def test_changed_file_overflow_is_partial(fake: dict[str, Any]) -> None:
    fake["update_glab"](
        {
            "projects/11/merge_requests/7/changes": {
                "overflow": True,
                "diff_refs": {"base_sha": BASE, "start_sha": START, "head_sha": HEAD},
                "changes": [],
            }
        }
    )
    payload = collect.collect(URL)
    assert payload["status"] == "partial"
    assert payload["components_complete"]["changed_files"] is False


def test_mismatched_changed_file_refs_are_partial(fake: dict[str, Any]) -> None:
    fake["update_glab"](
        {
            "projects/11/merge_requests/7/changes": {
                "diff_refs": {"base_sha": "d" * 40, "start_sha": START, "head_sha": HEAD},
                "changes": [],
            }
        }
    )
    payload = collect.collect(URL)
    assert payload["components_complete"]["changed_files"] is False


def test_missing_refs_are_named(fake: dict[str, Any]) -> None:
    fake["update_glab"](
        {
            "projects/11/merge_requests/7": {
                "iid": 7,
                "sha": HEAD,
                "title": "x",
                "diff_refs": {},
            }
        }
    )
    payload = collect.collect(URL)
    assert payload["status"] == "partial"
    assert payload["components_complete"]["exact_refs"] is False


def test_checks_report_failed_jobs_one_line_each(fake: dict[str, Any]) -> None:
    payload = collect.collect(URL)
    assert payload["checks"]["status"] == "failed"
    assert [job["name"] for job in payload["checks"]["failed_jobs"]] == ["lint"]


def test_a_branch_name_is_not_a_target() -> None:
    with pytest.raises(contract.WorkflowError):
        collect.collect("https://gitlab.example.com/group/project/-/tree/feature")
