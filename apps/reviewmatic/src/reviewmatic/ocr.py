"""The external OpenCodeReview (``ocr``) engine integration.

The runtime checks the minimum OCR version, runs one process per selected
reviewer in parallel, parses the JSON output tolerantly, and exposes session
compare and resume. It never reviews anything itself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, cast

from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from pathlib import Path

OCR_MINIMUM = (1, 13, 6)
OCR_BACKGROUND_LIMIT = 8000
OCR_TIMEOUT_SECONDS = 900
OCR_INSTALL = "npm install -g @alibaba-group/open-code-review@latest"
VERSION_RE = re.compile(r"\bv?(\d+)\.(\d+)\.(\d+)\b")
SEVERITIES = {"critical", "high", "medium", "low"}
GROUP_KEYS = ("new", "persisting", "resolved", "not_reviewed")
GROUP_ALIASES = {
    "new": ("new", "added"),
    "persisting": ("persisting", "persistent", "unchanged", "still_present"),
    "resolved": ("resolved", "fixed", "gone", "disappeared"),
    "not_reviewed": ("not_reviewed", "notReviewed", "unreviewed", "not_reviewed_items"),
}


def _ocr() -> str | None:
    return shutil.which("ocr")


def installed_version() -> tuple[int, int, int] | None:
    """Read the installed OCR version from ``ocr version``."""
    executable = _ocr()
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, "version"], capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode:
        return None
    match = VERSION_RE.search(completed.stdout)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def version_check() -> dict[str, Any]:
    """The minimum-version gate with the install or upgrade command."""
    version = installed_version()
    if version is None:
        return {
            "status": "missing",
            "minimum": ".".join(str(part) for part in OCR_MINIMUM),
            "instruction": f"install ocr with: {OCR_INSTALL}",
        }
    rendered = ".".join(str(part) for part in version)
    if version < OCR_MINIMUM:
        return {
            "status": "old",
            "installed": rendered,
            "minimum": ".".join(str(part) for part in OCR_MINIMUM),
            "instruction": f"upgrade ocr with: {OCR_INSTALL}",
        }
    return {
        "status": "ok",
        "installed": rendered,
        "minimum": ".".join(str(part) for part in OCR_MINIMUM),
    }


def _comment(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    comment = cast("dict[str, Any]", item)
    content = str(comment.get("content") or "")
    suggestion = str(comment.get("suggestion_code") or "")
    if not content and not suggestion:
        return None
    severity = str(comment.get("severity") or "")
    return {
        "path": contract.redact(str(comment.get("path") or "")),
        "old_path": contract.redact(str(comment.get("old_path") or "")),
        "new_path": contract.redact(str(comment.get("new_path") or "")),
        "start_line": comment.get("start_line")
        if isinstance(comment.get("start_line"), int)
        else None,
        "end_line": comment.get("end_line") if isinstance(comment.get("end_line"), int) else None,
        "category": contract.redact(str(comment.get("category") or "")),
        "severity": severity if severity in SEVERITIES else "low",
        "content": contract.redact(content),
        "suggestion_code": contract.redact(suggestion),
        "existing_code": contract.redact(str(comment.get("existing_code") or "")),
    }


def parse_review(raw: str) -> dict[str, Any]:
    """Parse one OCR JSON document tolerantly."""
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise contract.WorkflowError(f"the ocr CLI did not return valid JSON ({error})") from error
    if not isinstance(value, dict):
        raise contract.WorkflowError("the ocr CLI JSON output must be an object")
    output = cast("dict[str, Any]", value)
    comments: list[dict[str, Any]] = []
    raw_comments = output.get("comments")
    if isinstance(raw_comments, list):
        for item in cast("list[object]", raw_comments):
            comment = _comment(item)
            if comment is not None:
                comments.append(comment)
    manifest = output.get("manifest")
    manifest = cast("dict[str, Any]", manifest) if isinstance(manifest, dict) else {}
    llm = output.get("llm")
    llm = cast("dict[str, Any]", llm) if isinstance(llm, dict) else {}
    session_id = output.get("session_id")
    return {
        "session_id": session_id if isinstance(session_id, str) and session_id else None,
        "run_id": str(manifest.get("run_id") or "") or None,
        "terminal_state": str(manifest.get("terminal_state") or output.get("status") or "unknown"),
        "provider": str(llm.get("provider") or ""),
        "model": str(llm.get("model") or ""),
        "comments": comments,
        "comments_count": len(comments),
    }


def _run_one(
    reviewer: dict[str, str],
    *,
    repo: str,
    from_ref: str,
    to_ref: str,
    background: Path,
    output_path: Path,
    timeout: int,
    resume: str | None,
) -> dict[str, Any]:
    command = [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
        "--color",
        "never",
        "--repo",
        repo,
        "--background-file",
        str(background),
        "--from",
        from_ref,
        "--to",
        to_ref,
        "--effort",
        reviewer["effort"],
        "--output",
        str(output_path),
    ]
    if reviewer["provider"]:
        command.extend(("--provider", reviewer["provider"]))
    if reviewer["model"]:
        command.extend(("--model", reviewer["model"]))
    if resume:
        command.extend(("--resume", resume))
    started = time.monotonic()
    record: dict[str, Any] = {
        "alias": reviewer["alias"],
        "provider": reviewer["provider"],
        "model": reviewer["model"],
        "effort": reviewer["effort"],
        "output_path": str(output_path),
    }
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError:
        record.update(
            exit_code=None,
            duration_seconds=round(time.monotonic() - started, 3),
            error="the ocr CLI is unavailable",
            comments=[],
            comments_count=0,
        )
        return record
    except subprocess.TimeoutExpired:
        record.update(
            exit_code=None,
            duration_seconds=round(time.monotonic() - started, 3),
            error=f"the ocr CLI did not finish within {timeout} seconds",
            comments=[],
            comments_count=0,
        )
        return record
    record["exit_code"] = completed.returncode
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    if completed.returncode:
        record["error"] = contract.redact(
            (completed.stderr or completed.stdout).strip()[-800:] or "ocr failed"
        )
        record["comments"] = []
        record["comments_count"] = 0
        return record
    try:
        raw = output_path.read_text(encoding="utf-8") if output_path.is_file() else completed.stdout
        parsed = parse_review(raw)
    except (OSError, contract.WorkflowError) as error:
        record["error"] = str(error)
        record["comments"] = []
        record["comments_count"] = 0
        return record
    record.update(
        session_id=parsed["session_id"],
        run_id=parsed["run_id"],
        terminal_state=parsed["terminal_state"],
        comments=parsed["comments"],
        comments_count=parsed["comments_count"],
        error=None,
    )
    return record


def run_reviews(
    *,
    repo: str,
    from_ref: str,
    to_ref: str,
    background: Path,
    reviewers: list[dict[str, str]],
    output_dir: Path,
    timeout: int = OCR_TIMEOUT_SECONDS,
    resume: str | None = None,
) -> dict[str, Any]:
    """Run one OCR process per reviewer, in parallel, each with its own output."""
    if not reviewers:
        raise contract.WorkflowError("no reviewers were selected")
    if resume and len(reviewers) != 1:
        raise contract.WorkflowError("an OCR resume applies to exactly one reviewer")
    size = background.stat().st_size if background.is_file() else -1
    if size < 0:
        raise contract.WorkflowError("the OCR background file is unavailable")
    if size > OCR_BACKGROUND_LIMIT:
        raise contract.WorkflowError(
            f"the OCR background is {size} bytes, above the limit of {OCR_BACKGROUND_LIMIT}"
        )
    check = version_check()
    if check["status"] != "ok":
        raise contract.WorkflowError(str(check["instruction"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(reviewer, output_dir / f"ocr-{reviewer['alias']}.json") for reviewer in reviewers]
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [
            executor.submit(
                _run_one,
                reviewer,
                repo=repo,
                from_ref=from_ref,
                to_ref=to_ref,
                background=background,
                output_path=path,
                timeout=timeout,
                resume=resume,
            )
            for reviewer, path in jobs
        ]
        runs = [future.result() for future in futures]
    return {
        "status": "ok" if all(run["exit_code"] == 0 for run in runs) else "failed",
        "parallel": len(runs) > 1,
        "duration_seconds": round(time.monotonic() - started, 3),
        "runs": runs,
        "external_mutations": False,
    }


def normalize_compare(value: object) -> dict[str, list[Any]]:
    """Map any reasonable ``ocr session compare --json`` shape to four groups."""
    groups: dict[str, list[Any]] = {key: [] for key in GROUP_KEYS}
    if isinstance(value, dict):
        payload = cast("dict[str, Any]", value)
        for key in GROUP_KEYS:
            for alias in GROUP_ALIASES[key]:
                items = payload.get(alias)
                if isinstance(items, list):
                    groups[key] = list(items)
                    break
        return groups
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                groups["new"].append(item)
                continue
            status = str(cast("dict[str, Any]", item).get("status") or "new")
            matched = next((key for key in GROUP_KEYS if status in GROUP_ALIASES[key]), None)
            groups[matched or "new"].append(item)
        return groups
    return groups


def compare(
    before: str, after: str, *, repo: str | None = None, timeout: int = 120
) -> dict[str, Any]:
    """Compare two persisted OCR sessions into new/persisting/resolved/not-reviewed."""
    command = ["ocr", "session", "compare", "--json", before, after]
    if repo:
        command.extend(("--repo", repo))
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError as error:
        raise contract.WorkflowError("the ocr CLI is unavailable") from error
    except subprocess.TimeoutExpired as error:
        raise contract.WorkflowError("ocr session compare timed out") from error
    if completed.returncode:
        raise contract.WorkflowError(
            "ocr session compare failed: "
            + contract.redact((completed.stderr or completed.stdout).strip()[-800:])
        )
    try:
        value: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        raise contract.WorkflowError("ocr session compare did not return JSON") from None
    groups = normalize_compare(value)
    return {
        "status": "ok",
        "before": before,
        "after": after,
        "groups": groups,
        "counts": {key: len(items) for key, items in groups.items()},
        "external_mutations": False,
    }
