"""Revalidation compares a snapshot's exact head with the live head."""

from __future__ import annotations

from typing import Any

import pytest

from reviewmatic import revalidate
from reviewmatic.portable.portable_gitlab import contract

HEAD = "a" * 40


def snapshot(**overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema": "mr-review/context/v1",
        "target": {
            "hostname": "gitlab.example.com",
            "project_path": "group/project",
            "project_id": 11,
            "iid": 7,
        },
        "refs": {"base_sha": "b" * 40, "start_sha": "c" * 40, "head_sha": HEAD},
    }
    data.update(overrides)
    return data


def fake_glab(monkeypatch: pytest.MonkeyPatch, sha: str) -> None:
    def fake(hostname: str, endpoint: str) -> object:
        if endpoint.startswith("projects/group%2Fproject"):
            return {"id": 11}
        if endpoint == "projects/11/merge_requests/7":
            return {"iid": 7, "sha": sha}
        raise AssertionError(endpoint)

    monkeypatch.setattr(contract, "glab_json", fake)


def test_an_unchanged_head_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_glab(monkeypatch, HEAD)
    result = revalidate.revalidate(snapshot())
    assert result["status"] == "unchanged"
    assert result["reviewed_head"] == HEAD
    assert result["external_mutations"] is False


def test_a_moved_head_is_stale_and_instructs_recollection(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_glab(monkeypatch, "d" * 40)
    result = revalidate.revalidate(snapshot())
    assert result["status"] == "stale"
    assert result["current_head"] == "d" * 40
    assert "collect again" in str(result["instruction"])


@pytest.mark.parametrize(
    "broken",
    [
        {"schema": "other"},
        {"refs": {}},
        {"target": {}},
    ],
)
def test_an_incomplete_snapshot_is_rejected(broken: dict[str, object]) -> None:
    with pytest.raises(contract.WorkflowError):
        revalidate.revalidate(snapshot(**broken))
