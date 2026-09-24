#!/usr/bin/env python3
"""Collect normalized GitLab events for a strict half-open UTC period."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

SCHEMA_VERSION = 1
DEFAULT_PER_PAGE = 100
MAX_PER_PAGE = 100
DEFAULT_WORKERS = 8
MAX_WORKERS = 32
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MAX_PAGES = 100
DEFAULT_MAX_ELEMENTS = 10_000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TERMINATION_GRACE_SECONDS = 0.5
PROCESS_REAP_TIMEOUT_SECONDS = 0.5
DATE_ONLY_LENGTH = 10
SOURCE_NAMES = ("merge_requests", "issues", "releases", "tags")

JsonObject = dict[str, Any]
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class Project:
    key: str
    name: str | None = None


@dataclass(frozen=True)
class SourceSpec:
    endpoint: str
    query: dict[str, str]
    timestamp_fields: tuple[str, ...]


SOURCE_SPECS: dict[str, SourceSpec] = {
    "merge_requests": SourceSpec(
        endpoint="merge_requests",
        query={"state": "merged"},
        timestamp_fields=("merged_at",),
    ),
    "issues": SourceSpec(
        endpoint="issues",
        query={"state": "closed"},
        timestamp_fields=("closed_at",),
    ),
    "releases": SourceSpec(
        endpoint="releases",
        query={},
        timestamp_fields=("released_at",),
    ),
    "tags": SourceSpec(
        endpoint="repository/tags",
        query={},
        timestamp_fields=("tag.created_at", "commit.created_at proxy"),
    ),
}


class MetricsError(RuntimeError):
    """Invalid input or an unusable GitLab response."""


def parse_instant(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise MetricsError("timestamp must not be empty")
    try:
        if len(text) == DATE_ONLY_LENGTH:
            parsed_date = date.fromisoformat(text)
            return datetime(
                parsed_date.year,
                parsed_date.month,
                parsed_date.day,
                tzinfo=UTC,
            )
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetricsError(f"invalid ISO 8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise MetricsError(f"timestamp must contain a UTC offset: {value}")
    return parsed.astimezone(UTC)


def format_instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        with suppress(ProcessLookupError):
            process.kill()

    deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    while process_group_exists(process_group):
        process.poll()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.01, remaining))

    if process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            with suppress(ProcessLookupError):
                process.kill()
    if process.poll() is None:
        with suppress(ProcessLookupError):
            process.kill()
    try:
        process.wait(timeout=PROCESS_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise MetricsError("failed to reap glab api process after forced termination") from error
    deadline = time.monotonic() + PROCESS_REAP_TIMEOUT_SECONDS
    while process_group_exists(process_group):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MetricsError("failed to terminate glab api process group")
        time.sleep(min(0.01, remaining))


def terminate_after_error(process: subprocess.Popen[bytes], error: BaseException) -> None:
    try:
        terminate_process_group(process)
    except MetricsError as cleanup_error:
        raise cleanup_error from error


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    if os.name != "posix" or not callable(getattr(os, "killpg", None)):
        raise MetricsError("GitLab metrics collection requires POSIX process groups")
    argv = list(command)
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    cleanup_attempted = False
    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    try:
        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
        if process.stdout is None or process.stderr is None:
            raise MetricsError("glab api output pipes are unavailable")
        stdout_fd = process.stdout.fileno()
        stderr_fd = process.stderr.fileno()
        streams = {stdout_fd: stdout_buffer, stderr_fd: stderr_buffer}
        selector = selectors.DefaultSelector()
        for descriptor in streams:
            selector.register(descriptor, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, DEFAULT_TIMEOUT_SECONDS)
            events = selector.select(remaining)
            if not events:
                raise subprocess.TimeoutExpired(argv, DEFAULT_TIMEOUT_SECONDS)
            for key, _ in events:
                descriptor = key.fd
                chunk = os.read(descriptor, 64 * 1024)
                if not chunk:
                    selector.unregister(descriptor)
                    continue
                buffer = streams[descriptor]
                buffer.extend(chunk)
                if len(buffer) > MAX_RESPONSE_BYTES:
                    raise MetricsError("glab api response exceeds the size limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(argv, DEFAULT_TIMEOUT_SECONDS)
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise subprocess.TimeoutExpired(argv, DEFAULT_TIMEOUT_SECONDS) from error
        if process_group_exists(process.pid):
            cleanup_attempted = True
            terminate_process_group(process)
        selector.close()
        selector = None
    except (subprocess.TimeoutExpired, MetricsError) as error:
        if process is not None and not cleanup_attempted:
            terminate_after_error(process, error)
        raise
    except (OSError, ValueError, NotImplementedError) as error:
        if process is not None and not cleanup_attempted:
            terminate_after_error(process, error)
        raise MetricsError(f"POSIX subprocess I/O is unavailable: {error}") from error
    except BaseException as error:
        if process is not None and not cleanup_attempted:
            terminate_after_error(process, error)
        raise
    finally:
        if selector is not None:
            with suppress(OSError, ValueError, NotImplementedError):
                selector.close()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
    return subprocess.CompletedProcess(
        argv,
        returncode,
        bytes(stdout_buffer).decode(errors="replace"),
        bytes(stderr_buffer).decode(errors="replace"),
    )


class GlabClient:
    def __init__(
        self,
        hostname: str,
        *,
        per_page: int = DEFAULT_PER_PAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_elements: int = DEFAULT_MAX_ELEMENTS,
        runner: Runner = default_runner,
    ) -> None:
        self.hostname = hostname
        self.per_page = per_page
        self.max_pages = max_pages
        self.max_elements = max_elements
        self.runner = runner

    def fetch_page(
        self,
        project: Project,
        source: str,
        page: int,
        since: datetime,
    ) -> list[JsonObject]:
        spec = SOURCE_SPECS[source]
        query = dict(spec.query)
        if source in {"merge_requests", "issues"}:
            query["updated_after"] = format_instant(since)
        query["per_page"] = str(self.per_page)
        query["page"] = str(page)
        endpoint = f"projects/{quote(project.key, safe='')}/{spec.endpoint}?{urlencode(query)}"
        command = ["glab", "api", endpoint, "--hostname", self.hostname]
        try:
            completed = self.runner(command)
        except subprocess.TimeoutExpired as exc:
            raise MetricsError(f"glab api timed out after {exc.timeout} seconds") from exc
        except OSError as exc:
            raise MetricsError(f"failed to run glab api: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise MetricsError(detail or f"glab api exited with {completed.returncode}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise MetricsError(f"glab api returned invalid JSON: {exc}") from exc
        if not isinstance(payload, list):
            raise MetricsError(f"expected a JSON array, got {type(payload).__name__}")
        if not all(isinstance(item, dict) for item in payload):
            raise MetricsError("expected every page item to be a JSON object")
        return payload


def nested_value(item: JsonObject, field: str) -> Any:
    value: Any = item
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def event_timestamp(item: JsonObject, source: str) -> tuple[datetime, str]:
    for field in SOURCE_SPECS[source].timestamp_fields:
        actual_field = field.removesuffix(" proxy")
        if actual_field == "tag.created_at":
            actual_field = "created_at"
        raw_value = nested_value(item, actual_field)
        if raw_value is None:
            continue
        if not isinstance(raw_value, str):
            raise MetricsError(f"{actual_field} is not a string")
        return parse_instant(raw_value), field
    fields = ", ".join(SOURCE_SPECS[source].timestamp_fields)
    raise MetricsError(f"missing source timestamp: {fields}")


def username(item: JsonObject) -> str | None:
    author = item.get("author")
    if not isinstance(author, dict):
        return None
    value = author.get("username")
    return value if isinstance(value, str) else None


def normalize_item(
    item: JsonObject,
    source: str,
    event_at: datetime,
    time_source: str,
) -> JsonObject:
    common = {"event_at": format_instant(event_at), "time_source": time_source}
    if source == "merge_requests":
        return {
            "id": item.get("id"),
            "iid": item.get("iid"),
            "title": item.get("title"),
            "description": item.get("description"),
            "author": username(item),
            "web_url": item.get("web_url"),
            **common,
        }
    if source == "issues":
        return {
            "id": item.get("id"),
            "iid": item.get("iid"),
            "title": item.get("title"),
            "author": username(item),
            "web_url": item.get("web_url"),
            **common,
        }
    if source == "releases":
        return {
            "name": item.get("name"),
            "tag_name": item.get("tag_name"),
            "description": item.get("description"),
            "_links": item.get("_links"),
            **common,
        }
    commit = item.get("commit")
    commit_id = commit.get("id") if isinstance(commit, dict) else None
    return {
        "name": item.get("name"),
        "commit_id": commit_id,
        "message": item.get("message"),
        "release": item.get("release"),
        **common,
    }


def item_key(item: JsonObject, source: str) -> str:
    if source in {"merge_requests", "issues"}:
        value = item.get("id")
        if value is None:
            value = item.get("iid")
    elif source == "releases":
        value = item.get("tag_name") or item.get("name")
    else:
        value = item.get("name")
    if value is None:
        raise MetricsError(f"missing stable key for {source}")
    return str(value)


def error_record(
    project: Project,
    source: str,
    kind: str,
    message: str,
    *,
    page: int | None = None,
) -> JsonObject:
    result: JsonObject = {
        "project": project.key,
        "source": source,
        "kind": kind,
        "message": message,
    }
    if page is not None:
        result["page"] = page
    return result


def page_signature(page_items: list[JsonObject]) -> bytes:
    canonical = json.dumps(
        page_items, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def collect_source(
    client: GlabClient,
    project: Project,
    source: str,
    since: datetime,
    until: datetime,
) -> JsonObject:
    page = 1
    successful_pages = 0
    received = 0
    duplicates = 0
    errors: list[JsonObject] = []
    normalized: dict[str, JsonObject] = {}
    seen_pages: set[bytes] = set()
    while True:
        if page > client.max_pages:
            errors.append(
                error_record(
                    project,
                    source,
                    "page_limit",
                    f"pagination exceeded {client.max_pages} pages",
                    page=page,
                )
            )
            break
        try:
            page_items = client.fetch_page(project, source, page, since)
        except MetricsError as exc:
            errors.append(error_record(project, source, "fetch", str(exc), page=page))
            break
        signature = page_signature(page_items)
        if signature in seen_pages:
            errors.append(
                error_record(project, source, "repeated_page", "GitLab repeated a page", page=page)
            )
            break
        seen_pages.add(signature)
        successful_pages += 1
        remaining = client.max_elements - received
        bounded_items = page_items[: max(remaining, 0)]
        received += len(bounded_items)
        for raw_item in bounded_items:
            try:
                key = item_key(raw_item, source)
                timestamp, time_source = event_timestamp(raw_item, source)
            except MetricsError as exc:
                errors.append(error_record(project, source, "item", str(exc), page=page))
                continue
            if not since <= timestamp < until:
                continue
            if key in normalized:
                duplicates += 1
                continue
            normalized[key] = normalize_item(raw_item, source, timestamp, time_source)
        if len(page_items) > len(bounded_items) or (
            received >= client.max_elements and len(page_items) == client.per_page
        ):
            errors.append(
                error_record(
                    project,
                    source,
                    "element_limit",
                    f"pagination reached {client.max_elements} elements",
                    page=page,
                )
            )
            break
        if len(page_items) < client.per_page:
            break
        page += 1
    items = sorted(
        normalized.values(),
        key=lambda value: (
            parse_instant(str(value["event_at"])),
            str(value.get("iid", value.get("tag_name", value.get("name", "")))),
        ),
    )
    return {
        "complete": not errors,
        "errors": errors,
        "source_timestamps": list(SOURCE_SPECS[source].timestamp_fields),
        "pages": successful_pages,
        "received": received,
        "duplicates": duplicates,
        "count": len(items),
        "items": items,
    }


def collect_metrics(
    projects: Sequence[Project],
    sources: Sequence[str],
    since: datetime,
    until: datetime,
    hostname: str,
    *,
    per_page: int = DEFAULT_PER_PAGE,
    workers: int = DEFAULT_WORKERS,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_elements: int = DEFAULT_MAX_ELEMENTS,
    runner: Runner = default_runner,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> JsonObject:
    if since >= until:
        raise MetricsError("--since must be earlier than --until")
    if not 1 <= per_page <= MAX_PER_PAGE:
        raise MetricsError(f"--per-page must be between 1 and {MAX_PER_PAGE}")
    if not 1 <= workers <= MAX_WORKERS:
        raise MetricsError(f"--workers must be between 1 and {MAX_WORKERS}")
    if max_pages < 1:
        raise MetricsError("--max-pages must be positive")
    if max_elements < 1:
        raise MetricsError("--max-elements must be positive")
    client = GlabClient(
        hostname,
        per_page=per_page,
        max_pages=max_pages,
        max_elements=max_elements,
        runner=runner,
    )
    tasks = [
        (project_index, source_index, project, source)
        for project_index, project in enumerate(projects)
        for source_index, source in enumerate(sources)
    ]
    results: dict[tuple[int, int], JsonObject] = {}
    if tasks:
        with ThreadPoolExecutor(
            max_workers=min(workers, len(tasks)),
            thread_name_prefix="gitlab-metrics",
        ) as executor:
            futures = {
                executor.submit(collect_source, client, project, source, since, until): (
                    project_index,
                    source_index,
                )
                for project_index, source_index, project, source in tasks
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    project_results: list[JsonObject] = []
    all_errors: list[JsonObject] = []
    for project_index, project in enumerate(projects):
        source_results: JsonObject = {}
        project_errors: list[JsonObject] = []
        for source_index, source in enumerate(sources):
            source_result = results[(project_index, source_index)]
            source_results[source] = source_result
            project_errors.extend(source_result["errors"])
        all_errors.extend(project_errors)
        project_results.append(
            {
                "project_id": project.key,
                "project_name": project.name,
                "complete": not project_errors,
                "errors": project_errors,
                "sources": source_results,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "hostname": hostname,
        "generated_at": format_instant(now()),
        "period": {
            "since": format_instant(since),
            "until": format_instant(until),
            "semantics": "[since, until)",
        },
        "workers": min(workers, len(tasks)) if tasks else 0,
        "complete": not all_errors,
        "errors": all_errors,
        "projects": project_results,
    }


def parse_project(value: str) -> Project:
    key, separator, name = value.partition("=")
    if not key.strip():
        raise argparse.ArgumentTypeError("project ID or path must not be empty")
    return Project(key=key.strip(), name=name.strip() if separator and name.strip() else None)


def write_result(result: JsonObject, output: Path | None) -> None:
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            delete=False,
        ) as temporary:
            temporary.write(rendered)
            temporary_name = temporary.name
        os.replace(temporary_name, output)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect GitLab events for a strict half-open UTC period."
    )
    parser.add_argument(
        "--project",
        action="append",
        required=True,
        type=parse_project,
        help="GitLab project ID or encoded path, optionally ID=display-name",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=SOURCE_NAMES,
        help="Source to collect; repeat as needed. Default: all sources",
    )
    parser.add_argument("--since", required=True, help="Inclusive ISO 8601 boundary")
    parser.add_argument("--until", required=True, help="Exclusive ISO 8601 boundary")
    parser.add_argument("--hostname", required=True, help="GitLab hostname for glab")
    parser.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-elements", type=int, default=DEFAULT_MAX_ELEMENTS)
    parser.add_argument("--output", type=Path, help="Write JSON atomically to this file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        since = parse_instant(arguments.since)
        until = parse_instant(arguments.until)
        result = collect_metrics(
            arguments.project,
            arguments.source or SOURCE_NAMES,
            since,
            until,
            arguments.hostname,
            per_page=arguments.per_page,
            workers=arguments.workers,
            max_pages=arguments.max_pages,
            max_elements=arguments.max_elements,
        )
        write_result(result, arguments.output)
    except MetricsError as exc:
        parser.error(str(exc))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
