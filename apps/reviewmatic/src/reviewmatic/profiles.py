"""Review profile loading (``~/.reviewmatic`` and ``./.reviewmatic``).

A profile holds reviewer aliases, provider, model, and effort. It never holds
secrets, and the skill never reads ``~/.opencodereview/config.json``. The local
file overlays the global one: a matching alias replaces, a new alias adds, and
the local ``default`` wins.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

from reviewmatic.portable.portable_gitlab import contract

PROFILE_SCHEMA = "mr-review/reviewers/v1"
EFFORTS = ("low", "medium", "high")
ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
PROFILE_DIR = ".reviewmatic"
PROFILE_FILE = "reviewers.json"
FORBIDDEN_KEY_RE = re.compile(
    r"(?i)(token|secret|password|passwd|credential|api[_-]?key|access[_-]?key|private[_-]?key)"
)
REVIEWER_KEYS = {"alias", "provider", "model", "effort"}
PROFILE_KEYS = {"default", "reviewers"}


def global_path() -> Path:
    return Path.home() / PROFILE_DIR / PROFILE_FILE


def _git_root(cwd: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode:
        return None
    value = completed.stdout.strip()
    return Path(value) if value else None


def local_candidates(cwd: Path) -> list[Path]:
    """The current directory first, then the git root, without duplicates."""
    candidates = [cwd / PROFILE_DIR / PROFILE_FILE]
    root = _git_root(cwd)
    if root is not None:
        candidate = root / PROFILE_DIR / PROFILE_FILE
        if candidate != candidates[0]:
            candidates.append(candidate)
    return candidates


def _reject_forbidden(value: object, label: str, *, depth: int = 0) -> None:
    if depth > 4:
        raise contract.WorkflowError(f"{label} nests too deeply")
    if isinstance(value, dict):
        for key, item in cast("dict[str, Any]", value).items():
            if FORBIDDEN_KEY_RE.search(str(key)):
                raise contract.WorkflowError(
                    f"{label} must not contain secrets: the {key!r} key is forbidden"
                )
            _reject_forbidden(item, label, depth=depth + 1)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            _reject_forbidden(item, label, depth=depth + 1)


def _reviewer(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise contract.WorkflowError(f"{label} reviewers must be objects")
    reviewer = cast("dict[str, Any]", value)
    unknown = set(reviewer) - REVIEWER_KEYS
    if unknown:
        raise contract.WorkflowError(
            f"{label} reviewer has unsupported keys: {', '.join(sorted(unknown))}"
        )
    alias = reviewer.get("alias")
    provider = reviewer.get("provider")
    model = reviewer.get("model")
    effort = reviewer.get("effort", "medium")
    if not isinstance(alias, str) or ALIAS_RE.fullmatch(alias) is None:
        raise contract.WorkflowError(f"{label} reviewer alias is invalid")
    if not isinstance(provider, str) or NAME_RE.fullmatch(provider) is None:
        raise contract.WorkflowError(f"{label} reviewer provider is invalid")
    if not isinstance(model, str) or not model.strip():
        raise contract.WorkflowError(f"{label} reviewer model is invalid")
    if not isinstance(effort, str) or effort not in EFFORTS:
        raise contract.WorkflowError(f"{label} reviewer effort must be low, medium, or high")
    return {"alias": alias, "provider": provider, "model": model, "effort": effort}


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise contract.WorkflowError(f"review profile {path} is unreadable") from error
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise contract.WorkflowError(f"review profile {path} is not valid JSON") from error
    if not isinstance(value, dict):
        raise contract.WorkflowError(f"review profile {path} must be a JSON object")
    profile = cast("dict[str, Any]", value)
    _reject_forbidden(profile, f"review profile {path}")
    unknown = set(profile) - PROFILE_KEYS - {"schema"}
    if unknown:
        raise contract.WorkflowError(
            f"review profile {path} has unsupported keys: {', '.join(sorted(unknown))}"
        )
    reviewers = profile.get("reviewers")
    if not isinstance(reviewers, list):
        raise contract.WorkflowError(f"review profile {path} must list reviewers")
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in cast("list[object]", reviewers):
        reviewer = _reviewer(item, str(path))
        if reviewer["alias"] in seen:
            raise contract.WorkflowError(f"review profile {path} repeats alias {reviewer['alias']}")
        seen.add(reviewer["alias"])
        parsed.append(reviewer)
    default = profile.get("default")
    if default is not None and (not isinstance(default, str) or default not in seen):
        raise contract.WorkflowError(
            f"review profile {path} default must name one of its reviewers"
        )
    return {"default": default, "reviewers": parsed}


def load(cwd: Path | None = None) -> dict[str, Any]:
    """Load the effective profile: global, overlaid by the local file."""
    directory = (cwd or Path.cwd()).resolve()
    sources: list[str] = []
    reviewers: dict[str, dict[str, str]] = {}
    default: str | None = None
    global_file = global_path()
    if global_file.is_file():
        parsed = _read(global_file)
        sources.append(str(global_file))
        reviewers = {item["alias"]: item for item in parsed["reviewers"]}
        default = cast("str | None", parsed["default"])
    for candidate in local_candidates(directory):
        if candidate.is_file():
            parsed = _read(candidate)
            sources.append(str(candidate))
            for item in parsed["reviewers"]:
                reviewers[item["alias"]] = item
            if parsed["default"] is not None:
                default = cast("str | None", parsed["default"])
            break
    ordered = [reviewers[alias] for alias in sorted(reviewers)]
    effective_default = default or (ordered[0]["alias"] if ordered else None)
    return {
        "status": "ok" if ordered else "missing",
        "sources": sources,
        "default": effective_default,
        "reviewers": ordered,
        "external_mutations": False,
    }


def select(profile: dict[str, Any], aliases: list[str]) -> list[dict[str, str]]:
    """Resolve aliases to reviewer records; the default stands in when empty."""
    available = {item["alias"]: item for item in cast("list[dict[str, str]]", profile["reviewers"])}
    if not aliases:
        default = profile.get("default")
        if not isinstance(default, str):
            raise contract.WorkflowError(
                "no reviewers are available; create ~/.reviewmatic/reviewers.json"
            )
        aliases = [default]
    missing = [alias for alias in aliases if alias not in available]
    if missing:
        raise contract.WorkflowError(f"unknown reviewer aliases: {', '.join(missing)}")
    return [available[alias] for alias in aliases]


def validate_providers(reviewers: list[dict[str, str]]) -> dict[str, Any]:
    """Check provider names against ``ocr llm providers`` (built-ins only)."""
    try:
        completed = subprocess.run(
            ["ocr", "llm", "providers"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "providers": [], "unknown": []}
    if completed.returncode:
        return {"available": False, "providers": [], "unknown": []}
    providers: set[str] = set()
    for line in completed.stdout.splitlines():
        name = line.strip().split(" ", maxsplit=1)[0] if line.strip() else ""
        if NAME_RE.fullmatch(name) is not None and name != "name":
            providers.add(name)
    unknown = sorted({item["provider"] for item in reviewers if item["provider"] not in providers})
    return {"available": True, "providers": sorted(providers), "unknown": unknown}
