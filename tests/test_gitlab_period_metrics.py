from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "shared/references/team_runtime/gitlab_period_metrics.py"
SPEC = importlib.util.spec_from_file_location("gitlab_period_metrics", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = metrics
SPEC.loader.exec_module(metrics)


class FakeRunner:
    def __init__(self, pages: dict[tuple[str, int], list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, int]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        parsed = urlsplit(command[2])
        source = parsed.path.split("/", 2)[-1]
        page = int(parse_qs(parsed.query)["page"][0])
        self.calls.append((source, page))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(self.pages.get((source, page), [])),
            stderr="",
        )


def merge_request(item_id: int, timestamp: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "iid": item_id,
        "title": f"MR {item_id}",
        "merged_at": timestamp,
        "author": {"username": "author"},
    }


def collect(source: str, runner: FakeRunner, *, per_page: int = 100) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        metrics.collect_metrics(
            [metrics.Project("101", "example")],
            [source],
            metrics.parse_instant("2026-05-01"),
            metrics.parse_instant("2026-06-01"),
            "gitlab.example.test",
            per_page=per_page,
            runner=runner,
            now=lambda: datetime(2026, 6, 2, tzinfo=UTC),
        ),
    )


def test_metrics_paginate_deduplicate_and_keep_fractional_boundary() -> None:
    runner = FakeRunner(
        {
            ("merge_requests", 1): [
                merge_request(1, "2026-05-01T00:00:00Z"),
                merge_request(2, "2026-05-10T10:00:00Z"),
            ],
            ("merge_requests", 2): [
                merge_request(2, "2026-05-10T10:00:00Z"),
                merge_request(3, "2026-05-31T23:59:59.999999Z"),
            ],
            ("merge_requests", 3): [],
        }
    )
    result = collect("merge_requests", runner, per_page=2)
    source = result["projects"][0]["sources"]["merge_requests"]
    assert source["count"] == 3
    assert source["duplicates"] == 1
    assert source["complete"]
    assert result["period"]["semantics"] == "[since, until)"
    assert runner.calls == [
        ("merge_requests", 1),
        ("merge_requests", 2),
        ("merge_requests", 3),
    ]


def test_metrics_exclude_exact_until_boundary() -> None:
    runner = FakeRunner(
        {
            ("merge_requests", 1): [
                merge_request(1, "2026-04-30T23:59:59.999999Z"),
                merge_request(2, "2026-05-01T00:00:00Z"),
                merge_request(3, "2026-05-31T23:59:59.999999Z"),
                merge_request(4, "2026-06-01T00:00:00Z"),
            ]
        }
    )
    result = collect("merge_requests", runner)
    items = result["projects"][0]["sources"]["merge_requests"]["items"]
    assert [item["iid"] for item in items] == [2, 3]


def test_metrics_mark_commit_timestamp_as_tag_proxy() -> None:
    runner = FakeRunner(
        {
            ("repository/tags", 1): [
                {
                    "name": "v1.1.0",
                    "created_at": None,
                    "commit": {
                        "id": "abc",
                        "created_at": "2026-05-20T00:00:00.123456Z",
                    },
                },
                {
                    "name": "v1.2.0",
                    "created_at": "2026-05-21T00:00:00Z",
                    "commit": {"created_at": "2026-04-20T00:00:00Z"},
                },
            ]
        }
    )
    result = collect("tags", runner)
    items = result["projects"][0]["sources"]["tags"]["items"]
    assert items[0]["time_source"] == "commit.created_at proxy"
    assert items[1]["time_source"] == "tag.created_at"


def test_metrics_keep_partial_result_and_structured_error() -> None:
    class FailingRunner(FakeRunner):
        def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
            page = int(parse_qs(urlsplit(command[2]).query)["page"][0])
            if page == 2:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="network error")
            return super().__call__(command)

    runner = FailingRunner(
        {
            ("issues", 1): [
                {
                    "id": 1,
                    "iid": 1,
                    "title": "Issue",
                    "closed_at": "2026-05-03T00:00:00Z",
                }
            ]
        }
    )
    result = collect("issues", runner, per_page=1)
    source = result["projects"][0]["sources"]["issues"]
    assert not result["complete"]
    assert not source["complete"]
    assert source["count"] == 1
    assert source["errors"][0]["page"] == 2
    assert "network error" in source["errors"][0]["message"]
