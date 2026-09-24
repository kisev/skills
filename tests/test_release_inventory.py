from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest

from shared.references.portable_gitlab import contract as portable_contract

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
        parse_semver=portable_contract.parse_semver,
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


def test_first_parent_tag_skips_ineligible_tags_and_selects_nearest_stable_semver(
    inventory: Any, tmp_path: Path
) -> None:
    head = "a" * 40
    previous = "b" * 40
    older = "c" * 40
    tags = "\n".join(
        (
            f"v2.0.0-rc.1\0\0{head}",
            f"v1.9.0+build.1\0\0{head}",
            f"v0.9.0\0\0{head}",
            f"v01.2.3\0\0{head}",
            f"v1.4.0\0{'d' * 40}\0{'e' * 40}",
            f"v1.3.0\0\0{older}",
        )
    )
    calls: list[tuple[str, ...]] = []

    def git_read(_root: Path, *arguments: str) -> str:
        calls.append(arguments)
        return (
            tags if arguments[0] == "for-each-ref" else f"{head}\n{previous}\n{'d' * 40}\n{older}\n"
        )

    inventory.portable.git_read = git_read
    assert inventory.first_parent_tag(tmp_path, head) == "v1.4.0"
    assert calls == [
        (
            "for-each-ref",
            f"--count={inventory.MAX_RELEASE_TAGS + 1}",
            "--format=%(refname:strip=2)%00%(*objectname)%00%(objectname)",
            "refs/tags/v*",
        ),
        (
            "rev-list",
            "--first-parent",
            f"--max-count={inventory.MAX_RELEASE_COMMITS + 1}",
            head,
        ),
    ]


def test_first_parent_tag_chooses_highest_stable_version_on_nearest_commit(
    inventory: Any, tmp_path: Path
) -> None:
    head = "a" * 40
    outputs = iter(
        (
            f"v1.2.3\0\0{head}\nv2.0.0\0\0{head}\n",
            f"{head}\n",
        )
    )
    inventory.portable.git_read = lambda *_args: next(outputs)
    assert inventory.first_parent_tag(tmp_path, head) == "v2.0.0"


def test_first_parent_tag_returns_none_without_eligible_tags(
    inventory: Any, tmp_path: Path
) -> None:
    head = "a" * 40
    inventory.portable.git_read = lambda *_args: (
        f"v0.9.0\0\0{head}\nv1.0.0-rc.1\0\0{head}\nv1.0.0+build\0\0{head}\n"
    )
    assert inventory.first_parent_tag(tmp_path, head) is None


def test_first_parent_tag_bounds_local_tag_list(inventory: Any, tmp_path: Path) -> None:
    line = f"v1.0.0\0\0{'a' * 40}"
    inventory.portable.MAX_BYTES = 10_000_000
    inventory.portable.git_read = lambda *_args: "\n".join(
        [line] * (inventory.MAX_RELEASE_TAGS + 1)
    )
    with pytest.raises(WorkflowError, match="tag list exceeds the protective limit"):
        inventory.first_parent_tag(tmp_path, "a" * 40)


def test_first_parent_tag_bounds_first_parent_history(inventory: Any, tmp_path: Path) -> None:
    head = "a" * 40
    outputs = iter(
        (
            f"v1.0.0\0\0{'b' * 40}\n",
            "\n".join([head] * (inventory.MAX_RELEASE_COMMITS + 1)),
        )
    )
    inventory.portable.MAX_BYTES = 10_000_000
    inventory.portable.git_read = lambda *_args: next(outputs)
    with pytest.raises(WorkflowError, match="history exceeds the protective limit"):
        inventory.first_parent_tag(tmp_path, head)


def test_explicit_previous_ref_resolves_exact_peeled_local_tag(
    inventory: Any, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def git_read(_root: Path, *arguments: str) -> str:
        calls.append(arguments)
        return "a" * 40

    inventory.portable.git_read = git_read
    assert inventory.explicit_previous_commit(tmp_path, "v1.2.3") == "a" * 40
    assert calls == [("rev-parse", "--verify", "refs/tags/v1.2.3^{commit}")]


def test_explicit_previous_ref_rejects_same_name_branch(inventory: Any, tmp_path: Path) -> None:
    def git_read(_root: Path, *arguments: str) -> str:
        assert arguments == ("rev-parse", "--verify", "refs/tags/v1.2.3^{commit}")
        raise WorkflowError("missing tag")

    inventory.portable.git_read = git_read
    with pytest.raises(WorkflowError, match="exact local tag"):
        inventory.explicit_previous_commit(tmp_path, "v1.2.3")


def test_explicit_previous_ref_accepts_exact_full_sha(inventory: Any, tmp_path: Path) -> None:
    reference = "A" * 40
    calls: list[tuple[str, ...]] = []

    def git_read(_root: Path, *arguments: str) -> str:
        calls.append(arguments)
        return reference.lower()

    inventory.portable.git_read = git_read
    assert inventory.explicit_previous_commit(tmp_path, reference) == reference.lower()
    assert calls == [("rev-parse", "--verify", f"{reference}^{{commit}}")]


def test_explicit_previous_ref_rejects_sha_resolving_elsewhere(
    inventory: Any, tmp_path: Path
) -> None:
    inventory.portable.git_read = lambda *_args: "b" * 40
    with pytest.raises(WorkflowError, match="exact commit SHA"):
        inventory.explicit_previous_commit(tmp_path, "a" * 40)


@pytest.mark.parametrize(
    "reference",
    [
        "main",
        "a" * 39,
        "HEAD~1",
        "refs/tags/v1.2.3",
        "v0.9.0",
        "v1.2.3-rc.1",
        "v1.2.3+build",
    ],
)
def test_explicit_previous_ref_rejects_unsupported_revision(
    inventory: Any, tmp_path: Path, reference: str
) -> None:
    inventory.portable.git_read = lambda *_args: pytest.fail("invalid boundary must not reach Git")
    with pytest.raises(WorkflowError, match=r"stable SemVer tag.*full 40-hex"):
        inventory.explicit_previous_commit(tmp_path, reference)


def test_semver_parser_rejects_unbounded_numeric_identifiers() -> None:
    assert portable_contract.parse_semver(f"{'9' * 65}.0.0") is None


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
