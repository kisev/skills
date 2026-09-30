from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "shared/references/team_runtime/evidence_store.py"
SPEC = importlib.util.spec_from_file_location("evidence_store", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
store = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = store
SPEC.loader.exec_module(store)

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
OLD_SINCE = datetime(2026, 9, 1, tzinfo=UTC)
OLD_UNTIL = datetime(2026, 9, 11, tzinfo=UTC)
REQ_SINCE = datetime(2026, 9, 1, tzinfo=UTC)
REQ_UNTIL = datetime(2026, 9, 25, tzinfo=UTC)


def snapshot_document(items: list[dict[str, Any]], sources: list[str]) -> bytes:
    return json.dumps(
        {
            "schema_version": 1,
            "hostname": "gitlab.example.test",
            "period": {"since": "x", "until": "y", "semantics": "[since, until)"},
            "project": {"project_id": "101", "project_name": "Example"},
            "sources": {
                source: {"complete": True, "errors": [], "count": len(items), "items": items}
                for source in sources
            },
        }
    ).encode()


def merged_item(item_id: int, event_at: str) -> dict[str, Any]:
    return {"id": item_id, "iid": item_id, "title": f"MR {item_id}", "event_at": event_at}


@pytest.fixture(autouse=True)
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "state"
    home.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_STATE_HOME", str(home))
    return home


def test_complete_gitlab_window_is_recorded_planned_and_materialized() -> None:
    record = store.record_coverage(
        "pipelines",
        "gitlab:gitlab.example.test:101",
        "gitlab-metrics",
        "gitlab.example.test",
        since=OLD_SINCE,
        until=OLD_UNTIL,
        complete=True,
        evidence=snapshot_document([merged_item(1, "2026-09-02T00:00:00Z")], ["merge_requests"]),
        label="GitLab Example",
        now=NOW,
    )
    assert record["status"] == "recorded"
    assert record["snapshot"] is not None

    plan = store.plan_windows(
        "pipelines", "gitlab:gitlab.example.test:101", REQ_SINCE, REQ_UNTIL, now=NOW
    )
    assert plan["reusable_windows"] == [
        {"since": "2026-09-01T00:00:00Z", "until": "2026-09-11T00:00:00Z"}
    ]
    assert plan["missing_windows"] == [
        {"since": "2026-09-11T00:00:00Z", "until": "2026-09-25T00:00:00Z"}
    ]
    assert not plan["complete"]

    materialized = store.materialize_gitlab(
        "pipelines", "gitlab:gitlab.example.test:101", OLD_SINCE, OLD_UNTIL, now=NOW
    )
    assert materialized["complete"]
    assert materialized["sources"]["merge_requests"]["count"] == 1


def test_complete_gitlab_window_stays_reusable_beyond_every_age_limit() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=REQ_UNTIL,
        complete=True,
        evidence=snapshot_document([], ["merge_requests"]),
        now=NOW,
    )
    late = NOW + timedelta(days=90)
    plan = store.plan_windows("pipelines", "gitlab:h:1", REQ_SINCE, REQ_UNTIL, now=late)
    assert plan["complete"]
    assert plan["missing_windows"] == []


def test_partial_and_snapshotless_records_are_never_reusable() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=REQ_UNTIL,
        complete=False,
        now=NOW,
    )
    plan = store.plan_windows("pipelines", "gitlab:h:1", REQ_SINCE, REQ_UNTIL, now=NOW)
    assert not plan["complete"]
    assert plan["missing_windows"] == [
        {"since": "2026-09-01T00:00:00Z", "until": "2026-09-25T00:00:00Z"}
    ]


def test_mattermost_window_follows_fresh_and_stable_policy() -> None:
    key = "mattermost:https://band.example/team/channels/dev"
    store.record_coverage(
        "pipelines",
        key,
        "mattermost",
        "https://band.example/team/channels/dev",
        since=REQ_SINCE,
        until=REQ_UNTIL,
        complete=True,
        evidence=snapshot_document([], ["posts"]),
        now=NOW,
    )
    fresh = store.plan_windows("pipelines", key, REQ_SINCE, REQ_UNTIL, now=NOW)
    assert fresh["complete"]
    aged = store.plan_windows("pipelines", key, REQ_SINCE, REQ_UNTIL, now=NOW + timedelta(days=1))
    assert not aged["complete"]
    stable = store.plan_windows("pipelines", key, REQ_SINCE, REQ_UNTIL, now=NOW + timedelta(days=8))
    assert stable["complete"]


def test_required_sources_force_recollection_when_snapshot_covers_less() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=REQ_UNTIL,
        complete=True,
        evidence=snapshot_document([merged_item(1, "2026-09-02T00:00:00Z")], ["merge_requests"]),
        now=NOW,
    )
    plan = store.plan_windows(
        "pipelines",
        "gitlab:h:1",
        REQ_SINCE,
        REQ_UNTIL,
        required_sources=frozenset({"merge_requests", "issues"}),
        now=NOW,
    )
    assert not plan["complete"]
    materialized = store.materialize_gitlab(
        "pipelines",
        "gitlab:h:1",
        REQ_SINCE,
        REQ_UNTIL,
        sources=frozenset({"merge_requests", "issues"}),
        now=NOW,
    )
    assert not materialized["complete"]
    assert materialized["errors"][0]["kind"] == "coverage_gap"


def test_materialize_merges_windows_and_deduplicates_overlap() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=datetime(2026, 9, 1, tzinfo=UTC),
        until=datetime(2026, 9, 11, tzinfo=UTC),
        complete=True,
        evidence=snapshot_document(
            [merged_item(1, "2026-09-02T00:00:00Z"), merged_item(2, "2026-09-05T00:00:00Z")],
            ["merge_requests"],
        ),
        now=NOW,
    )
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=datetime(2026, 9, 11, tzinfo=UTC),
        until=datetime(2026, 9, 25, tzinfo=UTC),
        complete=True,
        evidence=snapshot_document(
            [merged_item(2, "2026-09-05T00:00:00Z"), merged_item(3, "2026-09-20T00:00:00Z")],
            ["merge_requests"],
        ),
        now=NOW,
    )
    merged = store.materialize_gitlab("pipelines", "gitlab:h:1", REQ_SINCE, REQ_UNTIL, now=NOW)
    assert merged["complete"]
    identities = [item["id"] for item in merged["sources"]["merge_requests"]["items"]]
    assert identities == [1, 2, 3]


def test_materialize_reports_gap_for_uncovered_requested_period() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=OLD_UNTIL,
        complete=True,
        evidence=snapshot_document([merged_item(1, "2026-09-02T00:00:00Z")], ["merge_requests"]),
        now=NOW,
    )
    merged = store.materialize_gitlab("pipelines", "gitlab:h:1", REQ_SINCE, REQ_UNTIL, now=NOW)
    assert not merged["complete"]
    assert merged["errors"][0]["windows"] == [
        {"since": "2026-09-11T00:00:00Z", "until": "2026-09-25T00:00:00Z"}
    ]


def test_show_reports_window_coverage_and_point_reads() -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=OLD_UNTIL,
        complete=True,
        evidence=snapshot_document([], ["merge_requests"]),
        label="GitLab Example",
        now=NOW,
    )
    store.record_coverage(
        "pipelines",
        "file:protocols",
        "file",
        "MANAGEMENT/transcripts/2026-09-11.md",
        at=datetime(2026, 9, 24, 10, 0, tzinfo=UTC),
        complete=True,
        label="Planning protocol",
        now=datetime(2026, 9, 24, 10, 0, tzinfo=UTC),
    )
    report = store.show_manifest("pipelines", since=REQ_SINCE, until=REQ_UNTIL)
    by_kind = {item["kind"]: item for item in report["sources"]}
    assert by_kind["gitlab-metrics"]["window_coverage"] == "partial"
    assert by_kind["file"]["points"][0]["at"] == "2026-09-24T10:00:00Z"
    assert by_kind["gitlab-metrics"]["label"] == "GitLab Example"


def test_artifact_record_snapshots_content_and_binds_sources(tmp_path: Path) -> None:
    store.record_coverage(
        "pipelines",
        "gitlab:h:1",
        "gitlab-metrics",
        "h",
        since=REQ_SINCE,
        until=REQ_UNTIL,
        complete=True,
        evidence=snapshot_document([], ["merge_requests"]),
        now=NOW,
    )
    tmp_target = tmp_path / "artifact" / "W38-39-retro.md"
    tmp_target.parent.mkdir()
    tmp_target.write_text("# Retro\n", encoding="utf-8")
    artifact = store.record_artifact(
        "pipelines",
        tmp_target,
        since=REQ_SINCE,
        until=REQ_UNTIL,
        sources=["gitlab:h:1"],
        now=NOW,
    )
    assert artifact["status"] == "recorded"
    assert artifact["artifact"]["sources"] == ["gitlab:h:1"]
    assert artifact["artifact"]["suffix"] == ".md"
    assert artifact["snapshot"].startswith("history/artifact/")
    report = store.show_manifest("pipelines")
    assert report["artifacts"][0]["target"] == str(tmp_target)

    with pytest.raises(store.EvidenceError, match="unknown source"):
        store.record_artifact(
            "pipelines",
            tmp_target,
            since=REQ_SINCE,
            until=REQ_UNTIL,
            sources=["missing:key"],
            now=NOW,
        )


def test_corrupted_manifest_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "state" / "agent-skills" / "team-evidence" / "pipelines"
    (root / "history").mkdir(parents=True)
    (root / "manifest.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(store.EvidenceError):
        store.load_manifest(root)


def test_cli_contract_covers_capabilities_and_plan() -> None:
    assert store.main(["--capabilities"]) == 0
    assert (
        store.main(
            [
                "evidence-plan",
                "--profile",
                "pipelines",
                "--source",
                "gitlab:h:1",
                "--since",
                "2026-09-01T00:00:00Z",
                "--until",
                "2026-09-25T00:00:00Z",
            ]
        )
        == 0
    )
    assert (
        store.main(
            [
                "evidence-plan",
                "--profile",
                "ПРОФИЛЬ",
                "--source",
                "k",
                "--since",
                "2026-09-01T00:00:00Z",
                "--until",
                "2026-09-25T00:00:00Z",
            ]
        )
        == 2
    )


def test_window_subtraction_and_merging() -> None:
    requested = (datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC))
    covered = [
        (datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 10, tzinfo=UTC)),
        (datetime(2026, 9, 8, tzinfo=UTC), datetime(2026, 9, 12, tzinfo=UTC)),
        (datetime(2026, 9, 20, tzinfo=UTC), datetime(2026, 9, 22, tzinfo=UTC)),
    ]
    missing = store.subtract_spans(requested, covered)
    assert [(item[0].day, item[1].day) for item in missing] == [(12, 20), (22, 30)]
    assert store.subtract_spans(requested, [requested]) == []
