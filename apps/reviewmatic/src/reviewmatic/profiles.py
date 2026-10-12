"""XDG-stored code-review session profiles (decision 75).

A profile holds the session defaults: locale, fix policy, review depth, and
the panel selection. It is written only by an explicit ``profile-setup``
invocation - never as a side effect of a confirmed question round - and read
by ``profile-show`` or by the agent before resolving session arguments. A
missing profile stops an auto session with an instruction and invites a poll
in a manual session.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from reviewmatic.portable.portable_gitlab import contract

PROFILE_SCHEMA = "code-review/profile/v1"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")
LOCALES = ("en", "ru")
FIX_POLICIES = ("none", "suggestion", "patch")
REVIEW_MODES = ("fast", "normal")


def profile_directory() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "agent-skills" / "code-review" / "profiles"


def profile_path(name: str) -> Path:
    if NAME_RE.fullmatch(name) is None:
        raise contract.WorkflowError(
            "profile name must match [A-Za-z0-9][A-Za-z0-9._-]{0,31}; "
            "traversal and empty names are rejected"
        )
    return profile_directory() / f"{name}.json"


def _validated(
    name: str,
    locale: str | None,
    fix_policy: str | None,
    review_mode: str | None,
    participants: object,
) -> dict[str, Any]:
    if locale is not None and locale not in LOCALES:
        raise contract.WorkflowError("profile locale must be en or ru")
    if fix_policy is not None and fix_policy not in FIX_POLICIES:
        raise contract.WorkflowError("profile fix policy must be none, suggestion, or patch")
    if review_mode is not None and review_mode not in REVIEW_MODES:
        raise contract.WorkflowError("profile review mode must be fast or normal")
    if participants is not None and not isinstance(participants, dict):
        raise contract.WorkflowError(
            "profile participants must be a recorded panel selection object or null"
        )
    return {
        "schema": PROFILE_SCHEMA,
        "name": name,
        "locale": locale,
        "fix_policy": fix_policy,
        "review_mode": review_mode,
        "participants": participants,
    }


def write_profile(
    name: str,
    *,
    locale: str | None = None,
    fix_policy: str | None = None,
    review_mode: str | None = None,
    participants: object = None,
) -> dict[str, Any]:
    """Create or update one profile explicitly (the profile=setup flow)."""
    path = profile_path(name)
    existing: dict[str, Any] = {}
    if path.is_file():
        existing = contract.read_json(path, "code-review profile")
    payload = _validated(
        name,
        locale or existing.get("locale"),
        fix_policy or existing.get("fix_policy"),
        review_mode or existing.get("review_mode"),
        participants if participants is not None else existing.get("participants"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    contract.write_json(path, payload)
    return {"status": "ok", "path": str(path), "profile": payload, "external_mutations": False}


def read_profile(name: str) -> dict[str, Any]:
    path = profile_path(name)
    if not path.exists():
        return {
            "status": "missing",
            "name": name,
            "path": str(path),
            "instruction": (
                "no profile is stored under this name; create one explicitly with "
                "reviewmatic profile-setup --name <name> [--locale en|ru] "
                "[--fix-policy none|suggestion|patch] [--review-mode fast|normal] "
                "[--participants <selection.json>]"
            ),
            "external_mutations": False,
        }
    payload = contract.read_json(contract.regular_file(path, "code-review profile"), "profile")
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != PROFILE_SCHEMA
        or payload.get("name") != name
        or set(payload) != {"schema", "name", "locale", "fix_policy", "review_mode", "participants"}
    ):
        raise contract.WorkflowError(
            f"code-review profile {name} is invalid; rewrite it with profile-setup"
        )
    return {
        "status": "ok",
        "name": name,
        "path": str(path),
        "profile": payload,
        "external_mutations": False,
    }
