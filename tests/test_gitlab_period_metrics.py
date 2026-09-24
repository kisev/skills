from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest

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


def collect_bounded(
    source: str,
    runner: FakeRunner,
    *,
    per_page: int,
    max_pages: int = metrics.DEFAULT_MAX_PAGES,
    max_elements: int = metrics.DEFAULT_MAX_ELEMENTS,
) -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        metrics.collect_metrics(
            [metrics.Project("101", "example")],
            [source],
            metrics.parse_instant("2026-05-01"),
            metrics.parse_instant("2026-06-01"),
            "gitlab.example.test",
            per_page=per_page,
            max_pages=max_pages,
            max_elements=max_elements,
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


def test_metrics_stop_on_repeated_page_with_partial_result() -> None:
    repeated = [merge_request(1, "2026-05-03T00:00:00Z")]
    runner = FakeRunner({("merge_requests", 1): repeated, ("merge_requests", 2): repeated})

    result = collect("merge_requests", runner, per_page=1)
    source = result["projects"][0]["sources"]["merge_requests"]

    assert not source["complete"]
    assert source["count"] == 1
    assert source["errors"] == [
        {
            "project": "101",
            "source": "merge_requests",
            "kind": "repeated_page",
            "message": "GitLab repeated a page",
            "page": 2,
        }
    ]


def test_page_signature_is_canonical_and_fixed_size() -> None:
    first = metrics.page_signature([{"title": "caf\u00e9", "id": 1}])
    reordered = metrics.page_signature([{"id": 1, "title": "caf\u00e9"}])
    different = metrics.page_signature([{"id": 2, "title": "caf\u00e9"}])

    assert first == reordered
    assert first != different
    assert isinstance(first, bytes)
    assert len(first) == 32
    assert first == hashlib.sha256(b'[{"id":1,"title":"caf\xc3\xa9"}]').digest()


def test_metrics_enforce_page_and_element_limits_as_partial_errors() -> None:
    pages = {
        ("merge_requests", page): [merge_request(page, f"2026-05-{page:02d}T00:00:00Z")]
        for page in range(1, 5)
    }
    page_limited = collect_bounded("merge_requests", FakeRunner(pages), per_page=1, max_pages=2)[
        "projects"
    ][0]["sources"]["merge_requests"]
    element_limited = collect_bounded(
        "merge_requests", FakeRunner(pages), per_page=1, max_elements=2
    )["projects"][0]["sources"]["merge_requests"]

    assert page_limited["count"] == 2
    assert page_limited["errors"][0]["kind"] == "page_limit"
    assert element_limited["count"] == 2
    assert element_limited["errors"][0]["kind"] == "element_limit"


def test_default_runner_applies_subprocess_timeout(monkeypatch: Any) -> None:
    monkeypatch.setattr(metrics, "DEFAULT_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(subprocess.TimeoutExpired):
        metrics.default_runner([sys.executable, "-c", "import time; time.sleep(1)"])


def test_default_runner_timeout_covers_wait_after_output_eof(monkeypatch: Any) -> None:
    monkeypatch.setattr(metrics, "DEFAULT_TIMEOUT_SECONDS", 0.05)
    command = "import os, time; os.close(1); os.close(2); time.sleep(5)"

    with pytest.raises(subprocess.TimeoutExpired):
        metrics.default_runner([sys.executable, "-c", command])


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups are required")
def test_default_runner_kills_descendants_on_timeout(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(metrics, "DEFAULT_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(metrics, "TERMINATION_GRACE_SECONDS", 0.05)
    ready_path = tmp_path / "ready"
    terminated_path = tmp_path / "terminated"
    command = (
        "import os, pathlib, signal, sys, time; "
        "pid = os.fork(); "
        f"ready = pathlib.Path({str(ready_path)!r}); "
        f"terminated = pathlib.Path({str(terminated_path)!r}); "
        "pid == 0 and signal.signal(signal.SIGTERM, "
        "lambda *_: (terminated.write_text('yes'), sys.exit(0))); "
        "pid == 0 and ready.write_text('yes'); "
        "pid != 0 and [time.sleep(0.01) for _ in iter(ready.exists, True)]; "
        "time.sleep(5)"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        metrics.default_runner([sys.executable, "-c", command])

    assert terminated_path.read_text() == "yes"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups are required")
def test_default_runner_cleans_descendant_after_successful_leader_wait(tmp_path: Path) -> None:
    ready_path = tmp_path / "ready"
    descendant_pid_path = tmp_path / "descendant-pid"
    command = (
        "import os, pathlib, time; "
        "pid = os.fork(); "
        f"ready = pathlib.Path({str(ready_path)!r}); "
        f"pid_path = pathlib.Path({str(descendant_pid_path)!r}); "
        "pid == 0 and os.close(1); "
        "pid == 0 and os.close(2); "
        "pid == 0 and pid_path.write_text(str(os.getpid())); "
        "pid == 0 and ready.write_text('yes'); "
        "pid == 0 and time.sleep(5); "
        "pid != 0 and [time.sleep(0.01) for _ in iter(ready.exists, True)]; "
        "pid != 0 and print('usable response')"
    )

    completed = metrics.default_runner([sys.executable, "-c", command])

    assert completed.returncode == 0
    assert completed.stdout == "usable response\n"
    descendant_pid = int(descendant_pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(descendant_pid, 0)


def test_default_runner_reports_cleanup_failure_after_successful_wait(monkeypatch: Any) -> None:
    def fail_cleanup(_process: subprocess.Popen[bytes]) -> None:
        raise metrics.MetricsError("process-group cleanup failed")

    monkeypatch.setattr(metrics, "process_group_exists", lambda _process_group: True)
    monkeypatch.setattr(metrics, "terminate_process_group", fail_cleanup)

    with pytest.raises(metrics.MetricsError, match="process-group cleanup failed"):
        metrics.default_runner([sys.executable, "-c", "print('otherwise usable')"])


def test_cleanup_timeout_after_sigkill_is_structured_partial(monkeypatch: Any) -> None:
    class StuckProcess:
        pid = 1234

        def __init__(self) -> None:
            self.wait_timeout: float | None = None

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            assert timeout is not None
            self.wait_timeout = timeout
            raise subprocess.TimeoutExpired("glab", timeout)

    process = StuckProcess()
    signals: list[int] = []
    primary_error = subprocess.TimeoutExpired("glab", 1)
    cleanup_errors: list[BaseException] = []
    monkeypatch.setattr(metrics, "TERMINATION_GRACE_SECONDS", 0)
    monkeypatch.setattr(metrics, "process_group_exists", lambda _process_group: True)
    monkeypatch.setattr(metrics.os, "killpg", lambda _process_group, signum: signals.append(signum))

    def runner(_command: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            raise primary_error
        except subprocess.TimeoutExpired as error:
            try:
                metrics.terminate_after_error(cast("subprocess.Popen[bytes]", process), error)
            except metrics.MetricsError as cleanup_error:
                cleanup_errors.append(cleanup_error)
                raise
        raise AssertionError("cleanup unexpectedly succeeded")

    result = collect("issues", cast("FakeRunner", runner))
    source = result["projects"][0]["sources"]["issues"]

    assert not source["complete"]
    assert "failed to reap" in source["errors"][0]["message"]
    assert metrics.signal.SIGKILL in signals
    assert process.wait_timeout == metrics.PROCESS_REAP_TIMEOUT_SECONDS
    assert cleanup_errors[0].__cause__ is primary_error


@pytest.mark.parametrize("failure", [OSError("popen unavailable"), NotImplementedError()])
def test_popen_capability_failure_is_structured_partial(
    monkeypatch: Any, failure: Exception
) -> None:
    def unavailable_popen(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(metrics.subprocess, "Popen", unavailable_popen)
    runner = cast("FakeRunner", metrics.default_runner)

    result = collect("issues", runner)

    source = result["projects"][0]["sources"]["issues"]
    assert not source["complete"]
    assert source["errors"][0]["kind"] == "fetch"
    assert "POSIX subprocess I/O is unavailable" in source["errors"][0]["message"]


@pytest.mark.parametrize("failure", [OSError("selector unavailable"), NotImplementedError()])
def test_selector_construction_failure_is_structured_partial(
    monkeypatch: Any, failure: Exception
) -> None:
    def unavailable_selector() -> None:
        raise failure

    monkeypatch.setattr(metrics.selectors, "DefaultSelector", unavailable_selector)
    runner = cast(
        "FakeRunner", lambda _command: metrics.default_runner([sys.executable, "-c", "pass"])
    )

    result = collect("issues", runner)

    source = result["projects"][0]["sources"]["issues"]
    assert not source["complete"]
    assert source["errors"][0]["kind"] == "fetch"
    assert "POSIX subprocess I/O is unavailable" in source["errors"][0]["message"]


@pytest.mark.parametrize("failure", [OSError("register unavailable"), ValueError("invalid fd")])
def test_selector_register_failure_is_structured_partial(
    monkeypatch: Any, failure: Exception
) -> None:
    class RegisterFailingSelector:
        def register(self, *_args: Any, **_kwargs: Any) -> None:
            raise failure

        def close(self) -> None:
            pass

    monkeypatch.setattr(metrics.selectors, "DefaultSelector", RegisterFailingSelector)
    runner = cast(
        "FakeRunner", lambda _command: metrics.default_runner([sys.executable, "-c", "pass"])
    )

    result = collect("issues", runner)

    source = result["projects"][0]["sources"]["issues"]
    assert not source["complete"]
    assert source["errors"][0]["kind"] == "fetch"
    assert "POSIX subprocess I/O is unavailable" in source["errors"][0]["message"]


def test_selector_close_failure_is_structured_partial(monkeypatch: Any) -> None:
    selector_factory = metrics.selectors.DefaultSelector

    class CloseFailingSelector:
        def __init__(self) -> None:
            self.delegate = selector_factory()

        def register(self, *args: Any, **kwargs: Any) -> Any:
            return self.delegate.register(*args, **kwargs)

        def unregister(self, *args: Any, **kwargs: Any) -> Any:
            return self.delegate.unregister(*args, **kwargs)

        def select(self, *args: Any, **kwargs: Any) -> Any:
            return self.delegate.select(*args, **kwargs)

        def get_map(self) -> Any:
            return self.delegate.get_map()

        def close(self) -> None:
            self.delegate.close()
            raise OSError("selector close unavailable")

    monkeypatch.setattr(metrics.selectors, "DefaultSelector", CloseFailingSelector)
    runner = cast(
        "FakeRunner", lambda _command: metrics.default_runner([sys.executable, "-c", "pass"])
    )

    result = collect("issues", runner)

    source = result["projects"][0]["sources"]["issues"]
    assert not source["complete"]
    assert source["errors"][0]["kind"] == "fetch"
    assert "selector close unavailable" in source["errors"][0]["message"]


def test_unsupported_platform_is_structured_partial(monkeypatch: Any) -> None:
    monkeypatch.setattr(metrics.os, "name", "nt")
    runner = cast(
        "FakeRunner", lambda _command: metrics.default_runner([sys.executable, "-c", "pass"])
    )

    result = collect("issues", runner)

    source = result["projects"][0]["sources"]["issues"]
    assert not source["complete"]
    assert source["errors"][0]["kind"] == "fetch"
    assert "requires POSIX" in source["errors"][0]["message"]


def test_default_runner_rejects_oversized_response(monkeypatch: Any) -> None:
    monkeypatch.setattr(metrics, "MAX_RESPONSE_BYTES", 8)
    with pytest.raises(metrics.MetricsError, match="size limit"):
        metrics.default_runner([sys.executable, "-c", "print('123456789')"])
