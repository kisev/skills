from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/release-prepare/scripts/release_inventory.py"


class WorkflowError(Exception):
    pass


@pytest.fixture
def inventory(monkeypatch: pytest.MonkeyPatch) -> Any:
    contract = types.SimpleNamespace(
        ARTIFACT_VERSION=2,
        MAX_BYTES=1_000_000,
        WorkflowError=WorkflowError,
        redact=lambda value: str(value).replace("secret", "[REDACTED]"),
    )
    runtime = types.ModuleType("portable_runtime")
    cast("Any", runtime).contract = contract
    monkeypatch.setitem(sys.modules, "portable_runtime", runtime)
    spec = importlib.util.spec_from_file_location("test_release_inventory_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = cast("Any", importlib.util.module_from_spec(spec))
    spec.loader.exec_module(module)
    module.portable = contract
    return module


def test_commit_details_uses_mailmap_aware_author_format(inventory: Any, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def git_read(_root: Path, *arguments: str) -> str:
        calls.append(arguments)
        if arguments[0] == "rev-parse":
            return "abc1234\n"
        return "mapped@example.test\0Mapped Author\0Subject\0Body\0parent\n"

    inventory.portable.git_read = git_read
    result = inventory.commit_details(tmp_path, "a" * 40)

    assert result["author"] == {"email": "mapped@example.test", "name": "Mapped Author"}
    assert calls[1] == (
        "show",
        "-s",
        "--format=%aE%x00%aN%x00%s%x00%B%x00%P",
        "a" * 40,
    )


def test_participants_apply_human_approval_comment_and_author_rules(inventory: Any) -> None:
    merge_requests = [
        {
            "iid": 7,
            "author": {"username": "author", "name": "Author"},
            "approved_by": [
                {"username": "approved", "name": "Approved"},
                {"username": "robot", "bot": True},
            ],
            "notes": [
                {"id": 1, "system": False, "author": {"username": "author"}},
                {"id": 2, "system": False, "author": {"username": "reviewer"}},
                {"id": 3, "system": True, "author": {"username": "system-user"}},
                {
                    "id": 4,
                    "system": False,
                    "author": {"username": "comment-bot", "user_type": "project_bot"},
                },
            ],
        }
    ]
    assert [item["username"] for item in inventory.reviewer_candidates(merge_requests)] == [
        "approved",
        "reviewer",
    ]

    commits = [
        {
            "sha": "a",
            "parent_count": 1,
            "author": {"name": "One", "email": "42-one@users.noreply.gitlab.com"},
        },
        {
            "sha": "b",
            "parent_count": 1,
            "author": {"name": "One Again", "email": "42-one@users.noreply.gitlab.com"},
        },
        {
            "sha": "c",
            "parent_count": 2,
            "author": {"name": "Merge Author", "email": "merge@example.test"},
        },
        {
            "sha": "d",
            "parent_count": 0,
            "author": {"name": "No Account", "email": "plain@example.test"},
        },
        {
            "sha": "e",
            "parent_count": 1,
            "author": {"name": "no account", "email": "other@example.test"},
        },
    ]
    contributors = inventory.contributor_candidates(commits, merge_requests)
    assert [(item["display"], item["commit_shas"]) for item in contributors] == [
        ("No Account", ["d", "e"]),
        ("@one", ["a", "b"]),
    ]


def test_notes_are_deduplicated_by_stable_id(inventory: Any) -> None:
    first = {"id": 3, "body": "discussion copy"}
    second = {"id": 3, "body": "standalone copy"}
    notes, errors = inventory.normalize_notes([first, second, {"id": 2}], 9)
    assert errors == []
    assert notes == [{"id": 2}, first]


def test_milestones_are_deduplicated_with_sorted_provenance(inventory: Any) -> None:
    milestone = {"id": 5, "iid": 2, "title": "Release", "state": "active"}
    candidates, errors = inventory.milestone_candidates(
        {"milestone": milestone},
        [{"iid": 11, "milestone": dict(milestone)}],
        [dict(milestone), {"id": 7, "title": "Later", "state": "active"}],
    )
    assert errors == []
    assert [item["id"] for item in candidates] == [5, 7]
    assert candidates[0]["provenance"] == [
        {"source": "component_merge_request", "merge_request_iid": 11},
        {"source": "project_milestone"},
        {"source": "release_merge_request"},
    ]


def test_work_items_stay_same_project_and_expand_only_one_link_level(inventory: Any) -> None:
    calls: list[str] = []

    def paginated(_hostname: str, path: str) -> dict[str, object]:
        calls.append(path)
        if path.endswith("issues/1/links"):
            return {"items": [{"iid": 2}], "errors": [], "complete": True}
        if path.endswith("issues/3/links"):
            return {"items": [], "errors": [], "complete": True}
        raise AssertionError(f"unexpected pagination call: {path}")

    def glab_json(_hostname: str, path: str) -> dict[str, object]:
        iid = int(path.rsplit("/", 1)[1])
        return {"iid": iid, "title": f"Issue {iid}"}

    inventory.portable.paginated = paginated
    inventory.portable.glab_json = glab_json
    candidates, errors, complete = inventory.collect_work_items(
        "gitlab.example",
        19,
        "group/project",
        {"iid": 7, "title": "Release", "description": "Also closes #3", "closes_issues": []},
        [
            {
                "iid": 8,
                "title": "Closes #1 and other/project#99",
                "description": "See https://other.example/group/project/-/issues/98",
                "closes_issues": [],
            }
        ],
        [],
        2,
    )
    assert complete is True
    assert errors == []
    assert [item["iid"] for item in candidates] == [1, 2, 3]
    assert calls == ["projects/19/issues/1/links", "projects/19/issues/3/links"]
    assert candidates[1]["provenance"] == [
        {
            "source": "issue_link",
            "source_project_id": 19,
            "source_iid": 1,
            "depth": 1,
        }
    ]


def test_failed_required_collection_is_redacted_and_incomplete(inventory: Any) -> None:
    def paginated(_hostname: str, _path: str) -> dict[str, object]:
        return {"items": [], "errors": ["request secret failed"], "complete": False}

    inventory.portable.paginated = paginated
    inventory.portable.glab_json = lambda *_args: {"iid": 1}
    candidates, errors, complete = inventory.collect_work_items(
        "gitlab.example",
        19,
        "group/project",
        {"iid": 7, "title": "Release", "description": "", "closes_issues": []},
        [],
        [
            {
                "sha": "a",
                "subject": "Fix #1",
                "body": "",
                "parent_count": 1,
                "author": {"name": "Author", "email": "author@example.test"},
            }
        ],
        1,
    )

    assert candidates == [
        {
            "project_id": 19,
            "iid": 1,
            "details": {"iid": 1},
            "provenance": [{"source": "commit_message", "commit_sha": "a"}],
        }
    ]
    assert complete is False
    assert errors == [
        {
            "scope": "work_item_links_api",
            "project_id": 19,
            "iid": 1,
            "message": "request [REDACTED] failed",
        }
    ]
