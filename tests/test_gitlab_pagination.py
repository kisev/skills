from __future__ import annotations

from typing import Any

import pytest

from shared.references.portable_gitlab import contract
from shared.references.work_item_runtime import triage


@pytest.mark.parametrize("module", [contract, triage])
def test_issue_links_are_a_complete_single_response_at_the_ce_boundary(
    monkeypatch: pytest.MonkeyPatch, module: Any
) -> None:
    values = [{"id": index, "issue_link_id": index + 1000} for index in range(1, 101)]
    calls = []

    def get(host: str, endpoint: str) -> object:
        calls.append((host, endpoint))
        return values

    monkeypatch.setattr(module, "glab_json", get)
    result = module.paginated("localhost", "projects/7/issues/3/links")
    if module is contract:
        assert result["complete"] is True and result["pages"] == 1
        result = result["items"]
    assert result == values
    assert calls == [("localhost", "projects/7/issues/3/links?per_page=100&page=1")]


def test_issue_link_compatibility_does_not_allow_other_repeated_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract, "glab_json", lambda *_args: [{"id": i} for i in range(100)])
    result = contract.paginated("localhost", "projects/7/issues", max_pages=3)
    assert result["complete"] is False
    assert result["errors"] == ["GitLab pagination repeated a page"]


def test_issue_link_compatibility_does_not_accept_invalid_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract, "glab_json", lambda *_args: {"error": "bad response"})
    assert contract.paginated("localhost", "projects/7/issues/3/links")["complete"] is False
