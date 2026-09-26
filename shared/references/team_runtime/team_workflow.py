#!/usr/bin/env python3
"""Resolve private team profiles and apply confirmed local artifacts."""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import sys
import time
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, Protocol, cast
from uuid import uuid4


class FileLocking(Protocol):
    LOCK_EX: int
    LOCK_NB: int

    def flock(self, descriptor: int, operation: int) -> None: ...


fcntl: FileLocking | None
try:
    fcntl = cast("FileLocking", import_module("fcntl"))
except ImportError:
    fcntl = None

if TYPE_CHECKING:
    from ..state_artifacts import (
        archive_json,
        canonical_json,
        content_digest,
        ensure_private_directory,
        inspect_private_directory,
        record_success,
        xdg_state_home,
    )
else:
    _state_path = Path(__file__).with_name("state_artifacts.py")
    if not _state_path.exists():
        _state_path = Path(__file__).parents[1] / "state_artifacts.py"
    _state_spec = importlib.util.spec_from_file_location("state_artifacts", _state_path)
    if _state_spec is None or _state_spec.loader is None:
        raise ImportError("state_artifacts runtime is unavailable")
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    archive_json = _state_module.archive_json
    canonical_json = _state_module.canonical_json
    content_digest = _state_module.content_digest
    ensure_private_directory = _state_module.ensure_private_directory
    inspect_private_directory = _state_module.inspect_private_directory
    record_success = _state_module.record_success
    xdg_state_home = _state_module.xdg_state_home

MAX_BYTES = 2 * 1024 * 1024
LEGACY_JOURNAL_MAX_BYTES = 6 * 1024 * 1024
TTL_SECONDS = 600
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_RETRY_SECONDS = 0.05
SKILL_ACTIONS = {
    "team-sprint-start": "planning",
    "team-sprint-close": "sprint-close",
    "team-retro": "retro",
    "team-roadmap": "roadmap",
    "slides-prompts-prepare": "slides-prompts",
}
SKILL_NAME = Path(__file__).resolve().parents[1].name
if SKILL_NAME not in SKILL_ACTIONS:
    SKILL_NAME = "team-workflow"
FIXED_ACTION = SKILL_ACTIONS.get(SKILL_NAME, "planning")
FORBIDDEN = frozenset(
    {
        "access_token",
        "api_key",
        "credentials",
        "password",
        "personal_notes",
        "private_key",
        "refresh_token",
        "secret",
        "tokens",
    }
)
PROFILE_TOP_LEVEL = frozenset(
    {
        "$schema",
        "schema_version",
        "profile",
        "team",
        "projects",
        "technologies",
        "goals",
        "cadence",
        "baseline",
        "delivery_signals",
        "sources",
        "actions",
        "provenance",
        "extensions",
    }
)
ACTION_KEYS = frozenset({"planning", "sprint-close", "retro", "roadmap", "slides-prompts"})
PROFILE_KINDS = frozenset({"team", "people"})
PROFILE_FILENAMES = {"team": "context.json", "people": "people.json"}
PROFILE_JOURNALS = {
    "team": ".profile-save.transaction.json",
    "people": ".people-save.transaction.json",
}
PEOPLE_TOP_LEVEL = frozenset(
    {
        "$schema",
        "schema_version",
        "profile",
        "manager",
        "reports",
        "stakeholders",
        "extensions",
    }
)
PEOPLE_ENTRY_TYPES = frozenset({"1on1", "agreement", "fact", "note", "feedback"})
PEOPLE_TEXT_MAX = 4000


class WorkflowError(ValueError):
    """Expected safe workflow failure."""


class SetupRequired(WorkflowError):
    """The selected action needs more profile data before it can run."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = sorted(set(missing))
        super().__init__("setup-required: " + ", ".join(self.missing))


class MutationIOError(WorkflowError):
    """A confirmed local mutation failed safely."""


class ContractArgumentParser(argparse.ArgumentParser):
    """Return invalid CLI input through the JSON runner contract."""

    def error(self, message: str) -> NoReturn:
        raise WorkflowError(message)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(code: str, message: str, exit_code: int = 2) -> int:
    print(message, file=sys.stderr)
    emit({"status": "error", "error": {"code": code, "message": message, "retryable": False}})
    return exit_code


def setup_required(missing: list[str]) -> int:
    emit(
        {
            "status": "setup-required",
            "action": FIXED_ACTION,
            "missing": sorted(set(missing)),
            "external_mutations": False,
        }
    )
    return 3


def private_directory(path: Path) -> Path:
    try:
        return ensure_private_directory(path, config_home())
    except (OSError, ValueError) as error:
        raise WorkflowError("team profile directory is unsafe") from error


def existing_private_directory(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError(f"{label} must be a real directory")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise WorkflowError(f"{label} must not be accessible by group or other users")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise WorkflowError(f"{label} must be owned by the current user")
    return path.resolve()


def state_root(*, create: bool = True) -> Path:
    home = xdg_state_home()
    path = home / "agent-skills" / "team-workflow"
    if create:
        return ensure_private_directory(path, home)
    if not path.exists():
        return path
    try:
        return inspect_private_directory(path, home)
    except (OSError, ValueError) as error:
        raise WorkflowError("state directory is unsafe") from error


def state_private_directory(path: Path) -> Path:
    try:
        return ensure_private_directory(path, xdg_state_home())
    except (OSError, ValueError) as error:
        raise WorkflowError("state directory is unsafe") from error


def config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        path = Path(configured)
        if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
            raise WorkflowError("XDG_CONFIG_HOME must be an absolute normalized path")
        return path
    return Path.home() / ".config"


def profile_root(*, create: bool = False) -> Path:
    path = config_home() / "agent-skills" / "team"
    if create:
        return private_directory(path)
    if not path.exists():
        return path
    try:
        return inspect_private_directory(path, config_home())
    except (OSError, ValueError) as error:
        raise WorkflowError("team profile directory is unsafe") from error


def legacy_profile_root() -> Path:
    return config_home() / "opencode" / "team-contexts"


def valid_kind(value: str) -> str:
    if value not in PROFILE_KINDS:
        raise WorkflowError("profile kind must be team or people")
    return value


def profile_directory(name: str, *, create: bool = False) -> Path:
    root = profile_root(create=create)
    directory = root / valid_name(name)
    if create:
        return private_directory(directory)
    if not directory.exists():
        return directory
    try:
        return inspect_private_directory(directory, root)
    except (OSError, ValueError) as error:
        raise WorkflowError("team profile directory is unsafe") from error


def regular(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
        raise WorkflowError(f"{label} must be a small regular non-symlink file")
    return path.resolve()


def private_regular(path: Path, label: str) -> Path:
    source = regular(path, label)
    metadata = source.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise WorkflowError(f"{label} must not be accessible by group or other users")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise WorkflowError(f"{label} must be owned by the current user")
    return source


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowError(f"JSON object contains duplicate key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> NoReturn:
    raise WorkflowError(f"JSON contains unsupported numeric constant: {value}")


def read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    source = regular(path, label)
    raw = source.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain JSON object")
    return value, raw


def read_private_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    source = private_regular(path, label)
    raw = source.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain JSON object")
    return value, raw


def atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            sync_file(handle.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0)
    if os.name != "posix" or not flags:
        raise MutationIOError("durable profile transactions require POSIX directory fsync")
    try:
        descriptor = os.open(path, os.O_RDONLY | flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise MutationIOError("durable profile transactions require POSIX directory fsync") from exc


def sync_file(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise MutationIOError("durable profile transactions require POSIX file fsync") from exc


def require_profile_locking() -> FileLocking:
    if (
        os.name != "posix"
        or fcntl is None
        or not callable(getattr(fcntl, "flock", None))
        or not isinstance(getattr(fcntl, "LOCK_EX", None), int)
        or not isinstance(getattr(fcntl, "LOCK_NB", None), int)
    ):
        raise MutationIOError("profile mutations require POSIX fcntl locking")
    return fcntl


def acquire_profile_lock(root: Path) -> int:
    locking = require_profile_locking()
    descriptor = -1
    try:
        descriptor = os.open(
            root / ".profile-save.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise MutationIOError("profile mutation lock is unsafe")
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                locking.flock(descriptor, locking.LOCK_EX | locking.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MutationIOError(
                        "timed out waiting for the profile mutation lock"
                    ) from exc
                time.sleep(min(LOCK_RETRY_SECONDS, remaining))
            else:
                return descriptor
    except MutationIOError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise MutationIOError("failed to acquire the profile mutation lock") from exc


def durable_unlink(
    path: Path, *, missing_ok: bool = False, sync_parent_if_missing: bool = False
) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        if missing_ok:
            if sync_parent_if_missing and path.parent.exists():
                sync_directory(path.parent)
            return
        raise
    sync_directory(path.parent)


def versioned_json_write(path: Path, content: bytes, history_root: Path) -> None:
    if path.exists():
        archive_json(path, path.read_bytes(), history_root)
    atomic(path, content)


def mark_save(action: str, binding: str, content: bytes, *, required: bool = False) -> None:
    mutation = content_digest(
        canonical_json({"action": action, "binding": binding, "content": content_digest(content)})
    )
    try:
        record_success(SKILL_NAME, action, binding, mutation)
    except (OSError, ValueError) as error:
        if required:
            raise MutationIOError("context save marker could not be committed") from error
        print(
            "warning: mutation exited 0, but its advisory marker was not written; "
            f"revalidate the target before retrying ({error})",
            file=sys.stderr,
        )


def assert_safe_context(value: dict[str, Any]) -> None:
    def scan(item: Any) -> None:
        if isinstance(item, dict):
            if any(str(key).lower() in FORBIDDEN for key in item):
                raise WorkflowError("context contains credentials or personal notes")
            for child in item.values():
                scan(child)
        elif isinstance(item, list):
            for child in item:
                scan(child)

    scan(value)


def validate_context(value: dict[str, Any]) -> dict[str, Any]:
    assert_safe_context(value)
    missing = context_missing(value)
    if missing:
        raise SetupRequired(missing)
    return value


def context_missing(value: dict[str, Any]) -> list[str]:
    required = ("goals", "scope", "cadence", "baseline", "projects", "delivery_signals")
    return [key for key in required if key not in value or value[key] in (None, "", [], {})]


def is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def inspect_object(
    value: Any,
    path: str,
    *,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    if not isinstance(value, dict):
        return None, ([] if value is not None else [path]), ([] if value is None else [path])
    missing = [f"{path}.{key}" for key in sorted(required) if key not in value]
    invalid = [f"{path}.{key}" for key in sorted(set(value) - allowed)]
    return value, missing, invalid


def inspect_text(value: Any, path: str, missing: list[str], invalid: list[str]) -> None:
    if value is None:
        missing.append(path)
    elif not is_text(value):
        invalid.append(path)


def inspect_text_list(
    value: Any,
    path: str,
    missing: list[str],
    invalid: list[str],
    *,
    required: bool = True,
) -> None:
    if value is None:
        if required:
            missing.append(path)
        return
    if (
        not isinstance(value, list)
        or (required and not value)
        or any(not is_text(item) for item in value)
        or len(set(value)) != len(value)
    ):
        invalid.append(path)


def inspect_profile(value: dict[str, Any], action: str) -> tuple[list[str], list[str]]:
    assert_safe_context(value)
    missing: list[str] = []
    invalid: list[str] = []

    unknown = sorted(set(value) - PROFILE_TOP_LEVEL)
    invalid.extend(unknown)
    schema_version = value.get("schema_version")
    if schema_version is None:
        missing.append("schema_version")
    elif isinstance(schema_version, bool) or schema_version != 1:
        invalid.append("schema_version")
    profile = value.get("profile")
    if profile is None:
        missing.append("profile")
    elif not is_text(profile):
        invalid.append("profile")
    else:
        try:
            valid_name(profile)
        except WorkflowError:
            invalid.append("profile")

    team, found_missing, found_invalid = inspect_object(
        value.get("team"),
        "team",
        allowed=frozenset({"name", "description", "members", "external_contributors"}),
        required=frozenset({"name", "members", "external_contributors"}),
    )
    missing.extend(found_missing)
    invalid.extend(found_invalid)
    if team is not None:
        inspect_text(team.get("name"), "team.name", missing, invalid)
        if "description" in team and not is_text(team["description"]):
            invalid.append("team.description")
        members = team.get("members")
        if not isinstance(members, list) or not members:
            if members is None:
                missing.append("team.members")
            else:
                invalid.append("team.members")
        else:
            member_ids: list[str] = []
            for index, item in enumerate(members):
                member, item_missing, item_invalid = inspect_object(
                    item,
                    f"team.members[{index}]",
                    allowed=frozenset(
                        {
                            "id",
                            "display_name",
                            "role",
                            "groups",
                            "active",
                            "active_from",
                            "active_until",
                        }
                    ),
                    required=frozenset({"id", "groups", "active"}),
                )
                missing.extend(item_missing)
                invalid.extend(item_invalid)
                if member is None:
                    continue
                inspect_text(member.get("id"), f"team.members[{index}].id", missing, invalid)
                if is_text(member.get("id")):
                    member_ids.append(member["id"])
                for field in ("display_name", "role", "active_from", "active_until"):
                    if field in member and not is_text(member[field]):
                        invalid.append(f"team.members[{index}].{field}")
                inspect_text_list(
                    member.get("groups"),
                    f"team.members[{index}].groups",
                    missing,
                    invalid,
                )
                if "active" in member and not isinstance(member["active"], bool):
                    invalid.append(f"team.members[{index}].active")
            if len(member_ids) != len(set(member_ids)):
                invalid.append("team.members.id")
        contributors, item_missing, item_invalid = inspect_object(
            team.get("external_contributors"),
            "team.external_contributors",
            allowed=frozenset({"policy", "included_groups"}),
            required=frozenset({"policy", "included_groups"}),
        )
        missing.extend(item_missing)
        invalid.extend(item_invalid)
        if contributors is not None:
            inspect_text(
                contributors.get("policy"),
                "team.external_contributors.policy",
                missing,
                invalid,
            )
            inspect_text_list(
                contributors.get("included_groups"),
                "team.external_contributors.included_groups",
                missing,
                invalid,
            )

    projects = value.get("projects")
    if not isinstance(projects, list) or not projects:
        if projects is None:
            missing.append("projects")
        else:
            invalid.append("projects")
    else:
        project_keys: list[str] = []
        for index, item in enumerate(projects):
            project, item_missing, item_invalid = inspect_object(
                item,
                f"projects[{index}]",
                allowed=frozenset(
                    {
                        "key",
                        "name",
                        "id",
                        "path",
                        "category",
                        "description",
                        "owner_group",
                        "include",
                    }
                ),
                required=frozenset({"key", "name", "category", "description", "include"}),
            )
            missing.extend(item_missing)
            invalid.extend(item_invalid)
            if project is None:
                continue
            for field in ("key", "name", "category", "description"):
                inspect_text(project.get(field), f"projects[{index}].{field}", missing, invalid)
            if is_text(project.get("key")):
                project_keys.append(project["key"])
            for field in ("path", "owner_group"):
                if field in project and not is_text(project[field]):
                    invalid.append(f"projects[{index}].{field}")
            if "id" in project and not (
                is_text(project["id"])
                or (isinstance(project["id"], int) and not isinstance(project["id"], bool))
            ):
                invalid.append(f"projects[{index}].id")
            if "include" in project and not isinstance(project["include"], bool):
                invalid.append(f"projects[{index}].include")
        if len(project_keys) != len(set(project_keys)):
            invalid.append("projects.key")

    inspect_text_list(
        value.get("technologies"),
        "technologies",
        missing,
        invalid,
        required=action == "slides-prompts",
    )

    goals = value.get("goals")
    goals_required = action in {"planning", "roadmap"}
    if goals is None:
        if goals_required:
            missing.append("goals")
    elif not isinstance(goals, list) or (goals_required and not goals):
        invalid.append("goals")
    else:
        goal_ids: list[str] = []
        for index, item in enumerate(goals):
            goal, item_missing, item_invalid = inspect_object(
                item,
                f"goals[{index}]",
                allowed=frozenset({"id", "title", "status", "source"}),
                required=frozenset({"id", "title", "status", "source"}),
            )
            missing.extend(item_missing)
            invalid.extend(item_invalid)
            if goal is None:
                continue
            for field in ("id", "title", "status", "source"):
                inspect_text(goal.get(field), f"goals[{index}].{field}", missing, invalid)
            if is_text(goal.get("id")):
                goal_ids.append(goal["id"])
        if len(goal_ids) != len(set(goal_ids)):
            invalid.append("goals.id")

    cadence, found_missing, found_invalid = inspect_object(
        value.get("cadence"),
        "cadence",
        allowed=frozenset({"timezone", "sprint", "retro", "roadmap"}),
        required=frozenset({"timezone"}),
    )
    missing.extend(found_missing)
    invalid.extend(found_invalid)
    if cadence is not None:
        inspect_text(cadence.get("timezone"), "cadence.timezone", missing, invalid)
        cadence_field = {
            "planning": "sprint",
            "sprint-close": "sprint",
            "retro": "retro",
            "roadmap": "roadmap",
            "slides-prompts": "retro",
        }[action]
        inspect_text(cadence.get(cadence_field), f"cadence.{cadence_field}", missing, invalid)
        for field in ("sprint", "retro", "roadmap"):
            if field in cadence and not is_text(cadence[field]):
                invalid.append(f"cadence.{field}")

    baseline, found_missing, found_invalid = inspect_object(
        value.get("baseline"),
        "baseline",
        allowed=frozenset({"description", "references"}),
        required=frozenset({"description", "references"}),
    )
    missing.extend(found_missing)
    invalid.extend(found_invalid)
    if baseline is not None:
        inspect_text(baseline.get("description"), "baseline.description", missing, invalid)
        inspect_reference_list(baseline.get("references"), "baseline.references", missing, invalid)

    signals = value.get("delivery_signals")
    if not isinstance(signals, list) or not signals:
        if signals is None:
            missing.append("delivery_signals")
        else:
            invalid.append("delivery_signals")
    else:
        for index, item in enumerate(signals):
            signal, item_missing, item_invalid = inspect_object(
                item,
                f"delivery_signals[{index}]",
                allowed=frozenset({"name", "source", "state", "timestamp"}),
                required=frozenset({"name", "source", "state", "timestamp"}),
            )
            missing.extend(item_missing)
            invalid.extend(item_invalid)
            if signal is not None:
                for field in ("name", "source", "state", "timestamp"):
                    inspect_text(
                        signal.get(field),
                        f"delivery_signals[{index}].{field}",
                        missing,
                        invalid,
                    )

    sources = value.get("sources")
    sources_required = action in {"retro", "roadmap"}
    if sources is None:
        if sources_required:
            missing.append("sources")
    elif not isinstance(sources, list) or (sources_required and not sources):
        invalid.append("sources")
    else:
        for index, item in enumerate(sources):
            source, item_missing, item_invalid = inspect_object(
                item,
                f"sources[{index}]",
                allowed=frozenset({"name", "kind", "tool", "location", "purpose"}),
                required=frozenset({"name", "kind", "tool", "location", "purpose"}),
            )
            missing.extend(item_missing)
            invalid.extend(item_invalid)
            if source is not None:
                for field in ("name", "kind", "tool", "location", "purpose"):
                    inspect_text(source.get(field), f"sources[{index}].{field}", missing, invalid)

    actions, found_missing, found_invalid = inspect_object(
        value.get("actions"),
        "actions",
        allowed=ACTION_KEYS,
        required=frozenset({action}),
    )
    missing.extend(found_missing)
    invalid.extend(found_invalid)
    if actions is not None:
        for action_name, action_config in actions.items():
            if action_name in ACTION_KEYS:
                inspect_action(action_config, action_name, missing, invalid)
    if actions is not None and action in actions:
        action_value = actions[action]
        if (
            action in {"retro", "roadmap"}
            and isinstance(action_value, dict)
            and action_value.get("use_gitlab_metrics") is True
        ):
            gitlab_sources = (
                [
                    item
                    for item in sources
                    if isinstance(item, dict) and item.get("kind") == "gitlab"
                ]
                if isinstance(sources, list)
                else []
            )
            if not gitlab_sources:
                missing.append("sources.gitlab")
            if isinstance(projects, list):
                for index, project in enumerate(projects):
                    if not isinstance(project, dict) or project.get("include") is not True:
                        continue
                    if "id" not in project and not is_text(project.get("path")):
                        missing.append(f"projects[{index}].id-or-path")

    provenance = value.get("provenance")
    if provenance is not None:
        inspect_reference_list(provenance, "provenance", missing, invalid, allow_reviewed=True)
    if "extensions" in value and not isinstance(value["extensions"], dict):
        invalid.append("extensions")
    return sorted(set(missing)), sorted(set(invalid))


def inspect_reference_list(
    value: Any,
    path: str,
    missing: list[str],
    invalid: list[str],
    *,
    allow_reviewed: bool = False,
) -> None:
    if not isinstance(value, list) or not value:
        if value is None:
            missing.append(path)
        else:
            invalid.append(path)
        return
    allowed = {"kind", "location", "purpose"}
    if allow_reviewed:
        allowed.add("reviewed_at")
    for index, item in enumerate(value):
        reference, item_missing, item_invalid = inspect_object(
            item,
            f"{path}[{index}]",
            allowed=frozenset(allowed),
            required=frozenset({"kind", "location", "purpose"}),
        )
        missing.extend(item_missing)
        invalid.extend(item_invalid)
        if reference is None:
            continue
        for field in ("kind", "location", "purpose"):
            inspect_text(reference.get(field), f"{path}[{index}].{field}", missing, invalid)
        if "reviewed_at" in reference and not is_text(reference["reviewed_at"]):
            invalid.append(f"{path}[{index}].reviewed_at")


def inspect_action(value: Any, action: str, missing: list[str], invalid: list[str]) -> None:
    path = f"actions.{action}"
    action_shapes: dict[str, tuple[frozenset[str], frozenset[str]]] = {
        "planning": (
            frozenset({"rules", "verification_commands"}),
            frozenset({"rules"}),
        ),
        "sprint-close": (
            frozenset({"rules", "verification_commands"}),
            frozenset({"rules"}),
        ),
        "retro": (
            frozenset(
                {
                    "output",
                    "project_detail_threshold",
                    "required_sections",
                    "rules",
                    "use_gitlab_metrics",
                }
            ),
            frozenset({"output", "required_sections", "rules"}),
        ),
        "roadmap": (
            frozenset(
                {
                    "document",
                    "period",
                    "history_policy",
                    "status_legend",
                    "rules",
                    "verification_commands",
                    "use_gitlab_metrics",
                }
            ),
            frozenset({"document", "period", "history_policy", "rules"}),
        ),
        "slides-prompts": (
            frozenset(
                {
                    "input_pattern",
                    "output_pattern",
                    "image_pattern",
                    "default_theme",
                    "default_style",
                    "theme_library",
                    "team_reference_policy",
                    "rendered_text_policy",
                    "rules",
                }
            ),
            frozenset(
                {
                    "input_pattern",
                    "output_pattern",
                    "image_pattern",
                    "team_reference_policy",
                    "rules",
                }
            ),
        ),
    }
    allowed, required = action_shapes[action]
    action_value, item_missing, item_invalid = inspect_object(
        value, path, allowed=allowed, required=required
    )
    missing.extend(item_missing)
    invalid.extend(item_invalid)
    if action_value is None:
        return
    if action == "retro":
        output, output_missing, output_invalid = inspect_object(
            action_value.get("output"),
            f"{path}.output",
            allowed=frozenset({"format", "target_pattern", "verification_command"}),
            required=frozenset({"format", "target_pattern"}),
        )
        missing.extend(output_missing)
        invalid.extend(output_invalid)
        if output is not None:
            inspect_text(output.get("format"), f"{path}.output.format", missing, invalid)
            inspect_text(
                output.get("target_pattern"),
                f"{path}.output.target_pattern",
                missing,
                invalid,
            )
            if "verification_command" in output and not is_text(output["verification_command"]):
                invalid.append(f"{path}.output.verification_command")
        threshold = action_value.get("project_detail_threshold")
        if threshold is not None and (
            isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1
        ):
            invalid.append(f"{path}.project_detail_threshold")
        inspect_text_list(
            action_value.get("required_sections"),
            f"{path}.required_sections",
            missing,
            invalid,
        )
    elif action == "roadmap":
        for field in ("document", "period", "history_policy"):
            inspect_text(action_value.get(field), f"{path}.{field}", missing, invalid)
        if (
            "status_legend" in action_value and not isinstance(action_value["status_legend"], dict)
        ) or (
            "status_legend" in action_value
            and any(
                not is_text(key) or not is_text(value)
                for key, value in action_value["status_legend"].items()
            )
        ):
            invalid.append(f"{path}.status_legend")
    elif action == "slides-prompts":
        for field in (
            "input_pattern",
            "output_pattern",
            "image_pattern",
            "team_reference_policy",
        ):
            inspect_text(action_value.get(field), f"{path}.{field}", missing, invalid)
        for field in ("default_theme", "default_style", "rendered_text_policy"):
            if field in action_value and not is_text(action_value[field]):
                invalid.append(f"{path}.{field}")
        for field in ("output_pattern", "image_pattern"):
            if is_text(action_value.get(field)) and "{NN}" not in action_value[field]:
                invalid.append(f"{path}.{field}")
        themes = action_value.get("theme_library")
        if themes is not None:
            if not isinstance(themes, list) or not themes:
                invalid.append(f"{path}.theme_library")
            else:
                for index, item in enumerate(themes):
                    theme, theme_missing, theme_invalid = inspect_object(
                        item,
                        f"{path}.theme_library[{index}]",
                        allowed=frozenset(
                            {"name", "description", "style", "integration", "constraints"}
                        ),
                        required=frozenset(
                            {"name", "description", "style", "integration", "constraints"}
                        ),
                    )
                    missing.extend(theme_missing)
                    invalid.extend(theme_invalid)
                    if theme is None:
                        continue
                    for field in ("name", "description", "style", "integration"):
                        inspect_text(
                            theme.get(field),
                            f"{path}.theme_library[{index}].{field}",
                            missing,
                            invalid,
                        )
                    inspect_text_list(
                        theme.get("constraints"),
                        f"{path}.theme_library[{index}].constraints",
                        missing,
                        invalid,
                    )
    inspect_text_list(action_value.get("rules"), f"{path}.rules", missing, invalid)
    if "verification_commands" in action_value:
        inspect_text_list(
            action_value["verification_commands"],
            f"{path}.verification_commands",
            missing,
            invalid,
            required=False,
        )
    if "use_gitlab_metrics" in action_value and not isinstance(
        action_value["use_gitlab_metrics"], bool
    ):
        invalid.append(f"{path}.use_gitlab_metrics")


def validate_profile(value: dict[str, Any], action: str) -> dict[str, Any]:
    missing, invalid = inspect_profile(value, action)
    if invalid:
        raise WorkflowError("profile contains invalid fields: " + ", ".join(invalid))
    if missing:
        raise SetupRequired(missing)
    return value


def inspect_people_profile(value: dict[str, Any]) -> tuple[list[str], list[str]]:
    if not isinstance(value, dict):
        return [], ["profile"]
    assert_safe_context(value)
    missing: list[str] = []
    invalid: list[str] = []

    unknown = sorted(set(value) - PEOPLE_TOP_LEVEL)
    if unknown:
        invalid.append("profile unknown fields: " + ", ".join(unknown))
    if value.get("schema_version") != 1 or isinstance(value.get("schema_version"), bool):
        invalid.append("schema_version")
    inspect_text(value.get("profile"), "profile", missing, invalid)

    manager = value.get("manager")
    if manager is not None:
        manager_object, manager_missing, manager_invalid = inspect_object(
            manager, "manager", allowed=frozenset({"name", "notes"})
        )
        missing.extend(manager_missing)
        invalid.extend(manager_invalid)
        if manager_object is not None:
            if manager_object.get("name") is not None:
                inspect_text(manager_object.get("name"), "manager.name", missing, invalid)
            inspect_text_list(
                manager_object.get("notes"), "manager.notes", missing, invalid, required=False
            )

    reports = value.get("reports")
    if reports is None or reports == []:
        missing.append("reports")
    elif not isinstance(reports, list):
        invalid.append("reports")
    else:
        names: list[str] = []
        for index, report in enumerate(reports):
            path = f"reports.{index}"
            if not isinstance(report, dict):
                invalid.append(path)
                continue
            report_object, report_missing, report_invalid = inspect_object(
                report,
                path,
                allowed=frozenset(
                    {
                        "name",
                        "handle",
                        "role",
                        "level",
                        "since",
                        "strengths",
                        "growth_areas",
                        "motivators",
                        "caution",
                        "notes",
                        "one_on_one",
                    }
                ),
                required=frozenset({"name"}),
            )
            missing.extend(report_missing)
            invalid.extend(report_invalid)
            if report_object is None:
                continue
            name = report_object.get("name")
            inspect_text(name, f"{path}.name", missing, invalid)
            if is_text(name):
                names.append(cast("str", name).strip().lower())
            for key in ("handle", "role", "level", "since"):
                if report_object.get(key) is not None:
                    inspect_text(report_object[key], f"{path}.{key}", missing, invalid)
            for key in ("strengths", "growth_areas", "motivators", "caution", "notes"):
                inspect_text_list(
                    report_object.get(key), f"{path}.{key}", missing, invalid, required=False
                )
            one_on_one = report_object.get("one_on_one")
            if one_on_one is not None:
                one_object, one_missing, one_invalid = inspect_object(
                    one_on_one,
                    f"{path}.one_on_one",
                    allowed=frozenset({"frequency", "minutes"}),
                )
                missing.extend(one_missing)
                invalid.extend(one_invalid)
                if one_object is not None:
                    if one_object.get("frequency") is not None:
                        inspect_text(
                            one_object.get("frequency"),
                            f"{path}.one_on_one.frequency",
                            missing,
                            invalid,
                        )
                    minutes = one_object.get("minutes")
                    if minutes is not None and (
                        isinstance(minutes, bool)
                        or not isinstance(minutes, int)
                        or not 5 <= minutes <= 240
                    ):
                        invalid.append(f"{path}.one_on_one.minutes")
        if len(names) != len(set(names)):
            invalid.append("reports duplicate names")

    stakeholders = value.get("stakeholders")
    if stakeholders is not None:
        if not isinstance(stakeholders, list):
            invalid.append("stakeholders")
        else:
            for index, stakeholder in enumerate(stakeholders):
                path = f"stakeholders.{index}"
                if not isinstance(stakeholder, dict):
                    invalid.append(path)
                    continue
                stakeholder_object, stakeholder_missing, stakeholder_invalid = inspect_object(
                    stakeholder,
                    path,
                    allowed=frozenset({"name", "role", "notes"}),
                    required=frozenset({"name"}),
                )
                missing.extend(stakeholder_missing)
                invalid.extend(stakeholder_invalid)
                if stakeholder_object is None:
                    continue
                inspect_text(stakeholder_object.get("name"), f"{path}.name", missing, invalid)
                if stakeholder_object.get("role") is not None:
                    inspect_text(stakeholder_object.get("role"), f"{path}.role", missing, invalid)
                inspect_text_list(
                    stakeholder_object.get("notes"),
                    f"{path}.notes",
                    missing,
                    invalid,
                    required=False,
                )

    extensions = value.get("extensions")
    if extensions is not None and not isinstance(extensions, dict):
        invalid.append("extensions")
    return missing, invalid


def validate_people_profile(value: dict[str, Any]) -> dict[str, Any]:
    missing, invalid = inspect_people_profile(value)
    if invalid:
        raise WorkflowError("people profile contains invalid fields: " + ", ".join(invalid[:30]))
    if missing:
        raise SetupRequired(missing)
    return value


def valid_name(value: str) -> str:
    if (
        not value
        or len(value) > 63
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value)
    ):
        raise WorkflowError("context name is invalid")
    return value


def profile_path(name: str, *, must_exist: bool = True, kind: str = "team") -> Path:
    path = profile_directory(name) / PROFILE_FILENAMES[valid_kind(kind)]
    if must_exist:
        return private_regular(path, "team profile")
    return path


def legacy_profile_path(name: str, *, must_exist: bool = True) -> Path:
    path = legacy_profile_root() / f"{valid_name(name)}.json"
    if must_exist:
        return private_regular(path, "legacy team profile")
    return path


def settings_path() -> Path:
    return profile_root(create=False) / "settings.json"


def legacy_settings_path() -> Path:
    return legacy_profile_root() / "settings.json"


def file_digest(path: Path, *, private: bool = False) -> str | None:
    if not path.exists():
        return None
    source = (
        private_regular(path, "existing private file")
        if private
        else regular(path, "existing file")
    )
    return hashlib.sha256(source.read_bytes()).hexdigest()


def default_profile_name() -> str:
    settings = settings_path()
    legacy = legacy_settings_path()
    source = None
    if settings.exists():
        source = settings
    elif legacy.exists():
        source = legacy
    if source is not None:
        value, _ = read_private_json(source, "team profile settings")
        if set(value) != {"schema_version", "default_profile"}:
            raise WorkflowError("team profile settings contain invalid fields")
        if value.get("schema_version") != 1 or isinstance(value.get("schema_version"), bool):
            raise WorkflowError("team profile settings schema_version must be 1")
        name = value.get("default_profile")
        if not isinstance(name, str):
            raise WorkflowError("team profile settings default_profile is invalid")
        return valid_name(name)
    fallback = legacy_profile_root() / "default.json"
    if fallback.exists():
        private_regular(fallback, "default team profile")
        return "default"
    raise SetupRequired(["profile.default"])


def read_profile(name: str, *, kind: str = "team") -> tuple[dict[str, Any], bytes, Path, str]:
    valid_kind(kind)
    path = profile_path(name, must_exist=False, kind=kind)
    location = "current"
    if not path.exists() and kind == "team":
        legacy = legacy_profile_path(name, must_exist=False)
        if legacy.exists():
            path = legacy
            location = "legacy"
    if location == "current" and not path.exists():
        raise SetupRequired([f"profile.{kind}.{name}"])
    path = private_regular(path, "team profile")
    value, raw = read_private_json(path, "team profile")
    if value.get("profile") != name:
        raise WorkflowError("team profile name does not match its file name")
    if kind == "people":
        return validate_people_profile(value), raw, path, location
    return validate_profile(value, FIXED_ACTION), raw, path, location


def profile_change_payload(
    name: str,
    raw: bytes,
    *,
    set_default: bool,
    kind: str = "team",
) -> dict[str, Any]:
    target = profile_path(name, must_exist=False, kind=valid_kind(kind))
    settings = settings_path()
    return {
        "kind": "profile",
        "profile_kind": kind,
        "name": name,
        "action": FIXED_ACTION,
        "content_digest": hashlib.sha256(raw).hexdigest(),
        "previous_digest": file_digest(target, private=True),
        "set_default": set_default,
        "previous_settings_digest": file_digest(settings, private=True) if set_default else None,
    }


def context_change_payload(name: str, raw: bytes) -> dict[str, Any]:
    return {
        "kind": "context",
        "name": name,
        "content_digest": hashlib.sha256(raw).hexdigest(),
    }


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_once(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if regular(path, "prepared plan").read_bytes() != content:
            raise WorkflowError("prepared plan digest conflicts with existing artifact")
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        sync_file(handle.fileno())
    sync_directory(path.parent)


def prepare_plan(payload: dict[str, Any]) -> tuple[str, Path, float]:
    plan_digest = digest(payload)
    path = state_private_directory(state_root() / "plans") / f"{plan_digest}.json"
    if path.exists():
        document, _ = read_json(path, "prepared plan")
        expires_at = document.get("expires_at")
        if document.get("digest") != plan_digest or not isinstance(expires_at, (int, float)):
            raise WorkflowError("prepared plan is invalid")
        return plan_digest, path, expires_at
    expires_at = time.time() + TTL_SECONDS
    document = {
        "schema_version": 1,
        "digest": plan_digest,
        "expires_at": expires_at,
        "payload": payload,
    }
    write_once(path, canonical_bytes(document))
    return plan_digest, path, expires_at


def validate_plan(plan_digest: str, payload: dict[str, Any]) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", plan_digest):
        raise WorkflowError("preview digest is invalid")
    path = regular(state_root() / "plans" / f"{plan_digest}.json", "prepared plan")
    document, _ = read_json(path, "prepared plan")
    if (
        document.get("digest") != plan_digest
        or document.get("payload") != payload
        or digest(payload) != plan_digest
    ):
        raise WorkflowError("prepared plan changed or digest does not match")
    if (
        not isinstance(document.get("expires_at"), (int, float))
        or document["expires_at"] < time.time()
    ):
        raise WorkflowError("prepared plan is stale or expired")
    receipt = state_private_directory(state_root() / "receipts") / f"{plan_digest}.json"
    if receipt.exists():
        raise WorkflowError("prepared plan is already consumed")
    return receipt


def create_receipt(receipt: Path, plan_digest: str) -> None:
    temporary = receipt.with_name(f".{receipt.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(
                canonical_bytes(
                    {"schema_version": 1, "digest": plan_digest, "consumed_at": time.time()}
                )
            )
            handle.flush()
            sync_file(handle.fileno())
        try:
            os.link(temporary, receipt, follow_symlinks=False)
        except FileExistsError as exc:
            raise WorkflowError("prepared plan is already consumed") from exc
        sync_directory(receipt.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def restore_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        durable_unlink(path, missing_ok=True, sync_parent_if_missing=True)
    else:
        atomic(path, previous)


def decoded_legacy_file(value: object, label: str) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise MutationIOError(f"profile transaction {label} is invalid")
    try:
        content = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise MutationIOError(f"profile transaction {label} is invalid") from exc
    if len(content) > MAX_BYTES:
        raise MutationIOError(f"profile transaction {label} is too large")
    return content


def valid_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def valid_receipt(value: dict[str, Any], plan_digest: str) -> bool:
    consumed_at = value.get("consumed_at")
    return (
        set(value) == {"schema_version", "digest", "consumed_at"}
        and type(value.get("schema_version")) is int
        and value["schema_version"] == 1
        and value.get("digest") == plan_digest
        and isinstance(consumed_at, (int, float))
        and not isinstance(consumed_at, bool)
        and math.isfinite(consumed_at)
    )


def validate_postcondition(value: object, label: str) -> tuple[bool, str | None]:
    if not isinstance(value, dict) or set(value) != {"exists", "digest"}:
        raise MutationIOError(f"profile transaction {label} postcondition is invalid")
    exists = value.get("exists")
    expected_digest = value.get("digest")
    if not isinstance(exists, bool) or (
        (exists and not valid_digest(expected_digest))
        or (not exists and expected_digest is not None)
    ):
        raise MutationIOError(f"profile transaction {label} postcondition is invalid")
    return exists, cast("str | None", expected_digest)


def file_postcondition(path: Path, *, private: bool = True) -> dict[str, object]:
    actual_digest = file_digest(path, private=private)
    return {"exists": actual_digest is not None, "digest": actual_digest}


def matches_postcondition(path: Path, expected: object, label: str) -> bool:
    exists, expected_digest = validate_postcondition(expected, label)
    try:
        actual_digest = file_digest(path, private=True)
    except WorkflowError as exc:
        raise MutationIOError(f"committed profile transaction {label} is unsafe") from exc
    return (actual_digest is not None) == exists and actual_digest == expected_digest


def read_transaction_journal(path: Path) -> dict[str, Any]:
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > LEGACY_JOURNAL_MAX_BYTES
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise WorkflowError("profile transaction must be a private regular file")
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, WorkflowError) as exc:
        raise MutationIOError("profile transaction journal is invalid") from exc
    if not isinstance(value, dict):
        raise MutationIOError("profile transaction journal is invalid")
    if value.get("schema_version") != 2 and len(raw) > MAX_BYTES:
        raise MutationIOError("profile transaction journal is invalid")
    return value


def backup_reference(transaction_id: str, label: str, content: bytes) -> dict[str, str]:
    backup_digest = hashlib.sha256(content).hexdigest()
    root = state_private_directory(state_root() / "profile-backups")
    digest_root = state_private_directory(root / backup_digest)
    canonical = digest_root / "content"
    canonical_created = not canonical.exists()
    if not canonical_created:
        source = private_regular(canonical, "profile transaction backup")
        if hashlib.sha256(source.read_bytes()).hexdigest() != backup_digest:
            raise MutationIOError("profile transaction backup digest is invalid")
    else:
        write_once(canonical, content)
    reference = digest_root / f"{transaction_id}-{label}"
    try:
        os.link(canonical, reference, follow_symlinks=False)
        sync_directory(digest_root)
    except FileExistsError:
        existing = private_regular(reference, "profile transaction backup reference")
        if existing.stat().st_ino != canonical.stat().st_ino:
            raise MutationIOError("profile transaction backup reference conflicts") from None
        sync_directory(digest_root)
    except OSError as exc:
        if canonical_created:
            durable_unlink(canonical, missing_ok=True, sync_parent_if_missing=True)
        raise MutationIOError("failed to create profile transaction backup") from exc
    return {
        "digest": backup_digest,
        "reference": str(reference.relative_to(state_root())),
    }


def create_backup(transaction_id: str, label: str, content: bytes | None) -> dict[str, str] | None:
    return None if content is None else backup_reference(transaction_id, label, content)


def load_backup(value: object, transaction_id: str, label: str) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"digest", "reference"}:
        raise MutationIOError(f"profile transaction {label} backup is invalid")
    backup_digest = value.get("digest")
    expected_reference = (
        f"profile-backups/{backup_digest}/{transaction_id}-{label}"
        if valid_digest(backup_digest)
        else None
    )
    if value.get("reference") != expected_reference:
        raise MutationIOError(f"profile transaction {label} backup reference is invalid")
    try:
        backup_root = existing_private_directory(
            state_root() / "profile-backups", "profile transaction backup directory"
        )
        digest_root = existing_private_directory(
            backup_root / cast("str", backup_digest),
            "profile transaction backup digest directory",
        )
        path = digest_root / f"{transaction_id}-{label}"
        source = private_regular(path, f"profile transaction {label} backup")
        content = source.read_bytes()
    except WorkflowError as exc:
        raise MutationIOError(f"profile transaction {label} backup is unsafe") from exc
    if hashlib.sha256(content).hexdigest() != backup_digest:
        raise MutationIOError(f"profile transaction {label} backup digest is invalid")
    return content


def cleanup_backups(document: dict[str, Any]) -> None:
    if document.get("schema_version") != 3:
        return
    for field in ("previous_profile", "previous_settings"):
        value = document[field]
        if value is None:
            continue
        reference = state_root() / value["reference"]
        digest_root = reference.parent
        canonical = digest_root / "content"
        durable_unlink(reference, missing_ok=True, sync_parent_if_missing=True)
        try:
            metadata = canonical.lstat()
        except FileNotFoundError:
            continue
        if metadata.st_nlink == 1:
            durable_unlink(canonical)
            try:
                digest_root.rmdir()
            except OSError:
                pass
            else:
                sync_directory(digest_root.parent)


def cleanup_completed_backups(document: dict[str, Any]) -> None:
    try:
        cleanup_backups(document)
    except (OSError, ValueError) as exc:
        print(
            f"warning: profile transaction completed but backup cleanup failed ({exc})",
            file=sys.stderr,
        )


def previous_condition(content: bytes | None) -> dict[str, object]:
    return {
        "exists": content is not None,
        "digest": hashlib.sha256(content).hexdigest() if content is not None else None,
    }


def transaction_matches(
    paths: tuple[Path, Path, Path],
    previous: tuple[object, object, object],
    intended: tuple[object, object, object],
) -> tuple[bool, bool, bool]:
    prior_matches: list[bool] = []
    intended_matches: list[bool] = []
    for path, prior, postcondition, label in zip(
        paths, previous, intended, ("profile", "settings", "report"), strict=True
    ):
        prior_match = matches_postcondition(path, prior, label)
        intended_match = matches_postcondition(path, postcondition, label)
        prior_matches.append(prior_match)
        intended_matches.append(intended_match)
        if not prior_match and not intended_match:
            return False, False, False
    return all(prior_matches), all(intended_matches), True


def validate_transaction(
    document: dict[str, Any],
) -> tuple[str, str, bool, bytes | None, bytes | None, dict[str, Any], dict[str, object]]:
    version = document.get("schema_version")
    common = {
        "schema_version",
        "name",
        "set_default",
        "plan_digest",
        "previous_profile",
        "previous_settings",
        "report_digest",
        "report_existed",
        "postconditions",
    }
    required = common | ({"previous_report", "transaction_id"} if version == 3 else set())
    if (
        type(version) is not int
        or version not in {2, 3}
        or set(document) != required
        or not isinstance(document.get("name"), str)
    ):
        raise MutationIOError("profile transaction journal is invalid")
    try:
        journal_name = valid_name(document["name"])
    except WorkflowError as exc:
        raise MutationIOError("profile transaction journal is invalid") from exc
    if (
        journal_name != document["name"]
        or not isinstance(document.get("set_default"), bool)
        or not valid_digest(document.get("plan_digest"))
        or not valid_digest(document.get("report_digest"))
        or not isinstance(document.get("report_existed"), bool)
        or not isinstance(document.get("postconditions"), dict)
        or set(document["postconditions"]) != {"profile", "settings", "report"}
    ):
        raise MutationIOError("profile transaction journal is invalid")
    plan_digest = document["plan_digest"]
    if version == 2:
        previous_profile = decoded_legacy_file(document["previous_profile"], "profile backup")
        previous_settings = decoded_legacy_file(document["previous_settings"], "settings backup")
    else:
        transaction_id = document.get("transaction_id")
        if (
            not isinstance(transaction_id, str)
            or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None
        ):
            raise MutationIOError("profile transaction journal is invalid")
        previous_profile = load_backup(document["previous_profile"], transaction_id, "profile")
        previous_settings = load_backup(document["previous_settings"], transaction_id, "settings")
    if not document["set_default"] and previous_settings is not None:
        raise MutationIOError("profile transaction journal is invalid")
    postconditions = document["postconditions"]
    profile_expected = validate_postcondition(postconditions["profile"], "profile")
    settings_expected = validate_postcondition(postconditions["settings"], "settings")
    report_expected = validate_postcondition(postconditions["report"], "report")
    if (
        not profile_expected[0]
        or not report_expected[0]
        or report_expected[1] != document["report_digest"]
        or (document["set_default"] and not settings_expected[0])
    ):
        raise MutationIOError("profile transaction journal is invalid")
    previous_report = (
        validate_postcondition(document["previous_report"], "previous report")
        if version == 3
        else (
            document["report_existed"],
            document["report_digest"] if document["report_existed"] else None,
        )
    )
    if previous_report[0] != document["report_existed"]:
        raise MutationIOError("profile transaction journal is invalid")
    return (
        journal_name,
        plan_digest,
        document["set_default"],
        previous_profile,
        previous_settings,
        postconditions,
        {"exists": previous_report[0], "digest": previous_report[1]},
    )


def recover_profile_transaction(root: Path, *, kind: str = "team") -> str | None:
    journal = root / PROFILE_JOURNALS[valid_kind(kind)]
    if not journal.exists():
        return None
    document = read_transaction_journal(journal)
    (
        journal_name,
        plan_digest,
        set_default,
        previous_profile,
        previous_settings,
        postconditions,
        previous_report,
    ) = validate_transaction(document)
    receipt = state_root() / "receipts" / f"{plan_digest}.json"
    receipt_valid = False
    if receipt.exists():
        try:
            receipt_value, _ = read_private_json(
                private_regular(receipt, "profile receipt"), "profile receipt"
            )
        except WorkflowError:
            pass
        else:
            receipt_valid = valid_receipt(receipt_value, plan_digest)
    if receipt.parent.exists():
        sync_directory(receipt.parent)
    report = state_root() / "reports" / f"{document['report_digest']}.json"
    paths = (
        profile_directory(journal_name, create=False) / PROFILE_FILENAMES[kind],
        root / "settings.json",
        report,
    )
    previous = (
        previous_condition(previous_profile),
        previous_condition(previous_settings) if set_default else postconditions["settings"],
        previous_report,
    )
    intended = (
        postconditions["profile"],
        postconditions["settings"],
        postconditions["report"],
    )
    all_previous, all_intended, safe = transaction_matches(paths, previous, intended)
    if receipt_valid:
        if all_intended:
            sync_directory(root)
            sync_directory(report.parent)
            durable_unlink(journal)
            cleanup_completed_backups(document)
            return "commit"
        if not safe:
            raise MutationIOError(
                "profile transaction recovery stopped because current files match neither prior nor intended state"
            )
        raise MutationIOError(
            "profile transaction recovery stopped because a consumed plan does not match its intended state"
        )
    if not safe:
        raise MutationIOError(
            "profile transaction recovery stopped because current files match neither prior nor intended state"
        )
    durable_unlink(receipt, missing_ok=True, sync_parent_if_missing=True)
    if not all_previous:
        restore_file(paths[0], previous_profile)
        if set_default:
            restore_file(paths[1], previous_settings)
        if not document["report_existed"]:
            durable_unlink(paths[2], missing_ok=True, sync_parent_if_missing=True)
    if not transaction_matches(paths, previous, intended)[0]:
        raise MutationIOError("profile transaction rollback did not restore its prior state")
    durable_unlink(journal)
    cleanup_completed_backups(document)
    return "rollback"


def apply_context(name: str, raw: bytes, plan_digest: str) -> tuple[Path, str]:
    root = state_private_directory(state_root() / "contexts")
    lock = acquire_profile_lock(root)
    try:
        payload = context_change_payload(name, raw)
        receipt = validate_plan(plan_digest, payload)
        target = root / f"{name}.json"
        previous = (
            private_regular(target, "saved context").read_bytes() if target.exists() else None
        )
        report_path, report_digest, report_content = report_artifact(
            plan_digest, {"status": "applied", "name": name}
        )
        report_existed = report_path.exists()
        try:
            versioned_json_write(target, raw, root)
            write_once(report_path, report_content)
            mark_save(f"context-save:{name}", plan_digest, raw, required=True)
            create_receipt(receipt, plan_digest)
        except (OSError, ValueError) as exc:
            try:
                receipt_value, _ = read_private_json(receipt, "context receipt")
                receipt_committed = (
                    valid_receipt(receipt_value, plan_digest)
                    and file_digest(target, private=True) == hashlib.sha256(raw).hexdigest()
                    and file_digest(report_path, private=True) == report_digest
                )
            except (OSError, WorkflowError):
                receipt_committed = False
            if receipt_committed:
                return report_path, report_digest
            try:
                restore_file(target, previous)
                if not report_existed:
                    durable_unlink(report_path, missing_ok=True, sync_parent_if_missing=True)
            except (OSError, ValueError) as rollback_error:
                raise MutationIOError(
                    "context mutation failed and rollback stopped"
                ) from rollback_error
            raise MutationIOError("context mutation failed and was rolled back") from exc
        return report_path, report_digest
    finally:
        os.close(lock)


def apply_profile(
    name: str, raw: bytes, plan_digest: str, *, set_default: bool, kind: str = "team"
) -> tuple[Path, str]:
    valid_kind(kind)
    require_profile_locking()
    root = profile_root(create=True)
    directory = profile_directory(name, create=True)
    lock = acquire_profile_lock(root)
    try:
        recover_profile_transaction(root, kind=kind)
        payload = profile_change_payload(name, raw, set_default=set_default, kind=kind)
        receipt = validate_plan(plan_digest, payload)
        profile = directory / PROFILE_FILENAMES[kind]
        settings = root / "settings.json"
        previous_profile = (
            private_regular(profile, "team profile").read_bytes() if profile.exists() else None
        )
        previous_settings = (
            private_regular(settings, "team profile settings").read_bytes()
            if set_default and settings.exists()
            else None
        )
        report_path, report_digest, report_content = report_artifact(
            plan_digest,
            {"status": "applied", "profile": name, "default": set_default},
        )
        report_existed = report_path.exists()
        previous_report = (
            file_postcondition(report_path)
            if report_existed
            else {
                "exists": False,
                "digest": None,
            }
        )
        settings_content = canonical_bytes({"schema_version": 1, "default_profile": name})
        expected_settings = (
            {"exists": True, "digest": hashlib.sha256(settings_content).hexdigest()}
            if set_default
            else file_postcondition(settings)
        )
        postconditions = {
            "profile": {
                "exists": True,
                "digest": hashlib.sha256(raw).hexdigest(),
            },
            "settings": expected_settings,
            "report": {"exists": True, "digest": report_digest},
        }
        journal = root / PROFILE_JOURNALS[kind]
        transaction_id = uuid4().hex
        previous_profile_backup: dict[str, str] | None = None
        previous_settings_backup: dict[str, str] | None = None
        try:
            previous_profile_backup = create_backup(transaction_id, "profile", previous_profile)
            previous_settings_backup = create_backup(transaction_id, "settings", previous_settings)
        except (OSError, ValueError):
            cleanup_backups(
                {
                    "schema_version": 3,
                    "previous_profile": previous_profile_backup,
                    "previous_settings": previous_settings_backup,
                }
            )
            raise
        document = {
            "schema_version": 3,
            "transaction_id": transaction_id,
            "name": name,
            "set_default": set_default,
            "plan_digest": plan_digest,
            "previous_profile": previous_profile_backup,
            "previous_settings": previous_settings_backup,
            "previous_report": previous_report,
            "report_digest": report_digest,
            "report_existed": report_existed,
            "postconditions": postconditions,
        }
        try:
            atomic(journal, canonical_bytes(document))
        except (OSError, ValueError):
            cleanup_backups(document)
            raise
        try:
            versioned_json_write(
                profile,
                raw,
                state_private_directory(state_root() / "profiles"),
            )
            if set_default:
                atomic(settings, settings_content)
            write_once(report_path, report_content)
            if not all(
                (
                    matches_postcondition(profile, postconditions["profile"], "profile"),
                    matches_postcondition(settings, postconditions["settings"], "settings"),
                    matches_postcondition(report_path, postconditions["report"], "report"),
                )
            ):
                raise MutationIOError(
                    "profile transaction does not match its durable postconditions"
                )
            create_receipt(receipt, plan_digest)
            if not all(
                (
                    matches_postcondition(profile, postconditions["profile"], "profile"),
                    matches_postcondition(settings, postconditions["settings"], "settings"),
                    matches_postcondition(report_path, postconditions["report"], "report"),
                )
            ):
                raise MutationIOError("profile transaction changed while its receipt was committed")
            durable_unlink(journal)
            cleanup_completed_backups(document)
        except (OSError, ValueError) as exc:
            try:
                outcome = recover_profile_transaction(root, kind=kind)
            except (OSError, ValueError) as rollback_error:
                raise MutationIOError(
                    "profile mutation failed and recovery stopped"
                ) from rollback_error
            if outcome == "commit":
                return report_path, report_digest
            raise MutationIOError("profile mutation failed and was rolled back") from exc
        else:
            return report_path, report_digest
    except OSError as exc:
        raise MutationIOError("profile mutation failed before it could be applied") from exc
    finally:
        os.close(lock)


def report_artifact(plan_digest: str, result: dict[str, object]) -> tuple[Path, str, bytes]:
    document = {
        "schema_version": 1,
        "digest": plan_digest,
        "result": result,
        "checks": ["digest", "expiry", "single_use", "safe_path"],
    }
    report_digest = digest(document)
    path = state_private_directory(state_root() / "reports") / f"{report_digest}.json"
    return path, report_digest, canonical_bytes(document)


def workspace_target(value: str) -> Path:
    root = Path.cwd().resolve()
    candidate = Path(value)
    if candidate.is_absolute():
        raise WorkflowError("artifact target must be workspace-relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise WorkflowError("artifact target is unsafe")
    target = root / candidate
    current = root
    for part in candidate.parts[:-1]:
        current /= part
        if current.exists() and (current.is_symlink() or not current.is_dir()):
            raise WorkflowError("artifact parent is unsafe")
    if (target.exists() or target.is_symlink()) and (target.is_symlink() or not target.is_file()):
        raise WorkflowError("artifact target is unsafe")
    return target


def load_context(args: argparse.Namespace) -> tuple[dict[str, Any], bytes, str, Path]:
    supplied = [
        value
        for value in (args.context_file, args.context_name, args.chat_input, args.profile)
        if value
    ]
    if len(supplied) > 1:
        raise WorkflowError("at most one explicit context source is allowed")
    kind = valid_kind(getattr(args, "kind", "team") or "team")
    if not supplied:
        name = default_profile_name()
        context, raw, path, location = read_profile(name, kind=kind)
        suffix = "@legacy" if location == "legacy" else ""
        return context, raw, f"profile:{name}{suffix}", path
    if args.profile:
        name = valid_name(args.profile)
        context, raw, path, location = read_profile(name, kind=kind)
        suffix = "@legacy" if location == "legacy" else ""
        return context, raw, f"profile:{name}{suffix}", path
    if args.context_file or args.chat_input:
        path = Path(args.context_file or args.chat_input)
        value, raw = read_json(path, "context")
        resolved = path.resolve()
        if value.get("schema_version") == 1 and "profile" in value:
            if kind == "people":
                return validate_people_profile(value), raw, "explicit-people-profile", resolved
            if "reports" in value and "projects" not in value:
                return validate_people_profile(value), raw, "explicit-people-profile", resolved
            return validate_profile(value, FIXED_ACTION), raw, "explicit-profile", resolved
        return validate_context(value), raw, "explicit-context", resolved
    state = state_root(create=False)
    path = regular(state / "contexts" / f"{valid_name(args.context_name)}.json", "saved context")
    value, raw = read_json(path, "saved context")
    return validate_context(value), raw, f"saved-context:{args.context_name}", path


def run_profile_command(args: argparse.Namespace) -> int | None:
    """Dispatch the profile subcommands; return None for other commands."""
    if args.command == "profile-inspect":
        profile, _ = read_json(Path(args.input), "profile input")
        if valid_kind(args.kind) == "people":
            missing, invalid = inspect_people_profile(profile)
            action = "people"
        else:
            missing, invalid = inspect_profile(profile, FIXED_ACTION)
            action = FIXED_ACTION
        emit(
            {
                "status": "invalid" if invalid else "setup-required" if missing else "ok",
                "action": action,
                "profile_kind": args.kind,
                "profile": profile.get("profile"),
                "missing": missing,
                "invalid": invalid,
                "external_mutations": False,
            }
        )
        return 2 if invalid else 3 if missing else 0
    if args.command == "profile-list":
        root = profile_root(create=False)
        profiles: list[dict[str, Any]] = []
        if root.exists():
            for path in sorted(root.iterdir()):
                if path.name == "settings.json" or not path.is_dir() or path.is_symlink():
                    continue
                kinds = sorted(
                    kind
                    for kind, filename in PROFILE_FILENAMES.items()
                    if (path / filename).exists()
                )
                if kinds:
                    profiles.append({"name": path.name, "kinds": kinds, "location": "current"})
        legacy_names: list[str] = []
        legacy_root = legacy_profile_root()
        if legacy_root.exists():
            for path in sorted(legacy_root.iterdir()):
                if path.name == "settings.json" or path.suffix != ".json":
                    continue
                private_regular(path, "legacy team profile")
                legacy_names.append(path.stem)
        try:
            default = default_profile_name()
        except SetupRequired:
            default = None
        emit(
            {
                "status": "ok",
                "profiles": profiles,
                "legacy_profiles": legacy_names,
                "default_profile": default,
                "external_mutations": False,
            }
        )
        return 0
    if args.command == "profile-prepare":
        name = valid_name(args.name)
        kind = valid_kind(args.kind)
        profile, raw = read_json(Path(args.input), "profile input")
        if kind == "people":
            validate_people_profile(profile)
        else:
            validate_profile(profile, FIXED_ACTION)
        if profile.get("profile") != name:
            raise WorkflowError("team profile name does not match --name")
        payload = profile_change_payload(name, raw, set_default=args.set_default, kind=kind)
        target = profile_path(name, must_exist=False, kind=kind)
        legacy_target = legacy_profile_path(name, must_exist=False) if kind == "team" else None
        risks = []
        if target.exists():
            risks.append("existing profile will be replaced")
        if legacy_target is not None and legacy_target.exists() and not target.exists():
            risks.append("legacy profile stays in place; remove it manually after verifying")
        plan_digest, path, expires_at = prepare_plan(payload)
        emit(
            {
                "status": "prepared",
                "summary": {
                    "tldr": (
                        "Saving a private people profile."
                        if kind == "people"
                        else "Saving a private team profile."
                    ),
                    "scope": [f"profile:{kind}:{name}"],
                    "risks": risks,
                    "checks": [
                        "profile schema",
                        "action completeness",
                        "private path",
                        "previous digest",
                    ],
                },
                "artifact_path": str(path),
                "digest": plan_digest,
                "expires_at": expires_at,
                "ttl_seconds": TTL_SECONDS,
                "apply_command": (
                    f"profile-save --name {name} --input {args.input} "
                    f"--digest {plan_digest} --kind {kind}"
                    + (" --set-default" if args.set_default else "")
                ),
            }
        )
        return 0
    if args.command == "profile-save":
        name = valid_name(args.name)
        kind = valid_kind(args.kind)
        profile, raw = read_json(Path(args.input), "profile input")
        if kind == "people":
            validate_people_profile(profile)
        else:
            validate_profile(profile, FIXED_ACTION)
        if profile.get("profile") != name:
            raise WorkflowError("team profile name does not match --name")
        report_path, report_digest = apply_profile(
            name, raw, args.digest, set_default=args.set_default, kind=kind
        )
        mark_save(f"profile-save:{kind}:{name}", args.digest, raw)
        emit(
            {
                "status": "applied",
                "summary": {
                    "tldr": (
                        "Private people profile saved."
                        if kind == "people"
                        else "Private team profile saved."
                    ),
                    "scope": [f"profile:{kind}:{name}"],
                    "risks": [],
                    "checks": [
                        "digest",
                        "expiry",
                        "single_use",
                        "private_path",
                        "previous_digest",
                    ],
                },
                "report_path": str(report_path),
                "report_digest": report_digest,
            }
        )
        return 0
    if args.command == "profile-migrate":
        name = valid_name(args.name)
        legacy = legacy_profile_path(name)
        current = profile_path(name, must_exist=False)
        if current.exists():
            raise WorkflowError("profile already exists in the current location")
        profile, raw = read_json(legacy, "legacy profile input")
        validate_profile(profile, FIXED_ACTION)
        if profile.get("profile") != name:
            raise WorkflowError("team profile name does not match --name")
        payload = profile_change_payload(name, raw, set_default=args.set_default, kind="team")
        plan_digest, path, expires_at = prepare_plan(payload)
        emit(
            {
                "status": "prepared",
                "summary": {
                    "tldr": "Migrating a legacy team profile into the current location.",
                    "scope": [f"profile:team:{name}"],
                    "risks": ["legacy profile stays in place; remove it manually after verifying"],
                    "checks": ["profile schema", "private path", "previous digest"],
                },
                "artifact_path": str(path),
                "digest": plan_digest,
                "expires_at": expires_at,
                "ttl_seconds": TTL_SECONDS,
                "apply_command": (
                    f"profile-save --name {name} --input {legacy} "
                    f"--digest {plan_digest} --kind team"
                    + (" --set-default" if args.set_default else "")
                ),
                "legacy_path": str(legacy),
                "current_path": str(current),
            }
        )
        return 0
    return None


def main(argv: list[str] | None = None) -> int:
    parser = ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    check = subparsers.add_parser("action-check")
    check.add_argument("--context-file")
    check.add_argument("--context-name")
    check.add_argument("--chat-input")
    check.add_argument("--profile")
    check.add_argument("--kind", choices=("team", "people"), default="team")
    inspect = subparsers.add_parser("context-inspect")
    inspect.add_argument("--input", required=True)
    subparsers.add_parser("context-list")
    show = subparsers.add_parser("context-show")
    show.add_argument("--name", required=True)
    prepare = subparsers.add_parser("context-prepare")
    prepare.add_argument("--input", required=True)
    prepare.add_argument("--name", required=True)
    save = subparsers.add_parser("context-save")
    save.add_argument("--name", required=True)
    save.add_argument("--input", required=True)
    save.add_argument("--digest", required=True)
    profile_inspect = subparsers.add_parser("profile-inspect")
    profile_inspect.add_argument("--input", required=True)
    profile_inspect.add_argument("--kind", choices=("team", "people"), default="team")
    subparsers.add_parser("profile-list")
    profile_prepare = subparsers.add_parser("profile-prepare")
    profile_prepare.add_argument("--name", required=True)
    profile_prepare.add_argument("--input", required=True)
    profile_prepare.add_argument("--set-default", action="store_true")
    profile_prepare.add_argument("--kind", choices=("team", "people"), default="team")
    profile_save = subparsers.add_parser("profile-save")
    profile_save.add_argument("--name", required=True)
    profile_save.add_argument("--input", required=True)
    profile_save.add_argument("--digest", required=True)
    profile_save.add_argument("--set-default", action="store_true")
    profile_save.add_argument("--kind", choices=("team", "people"), default="team")
    profile_migrate = subparsers.add_parser("profile-migrate")
    profile_migrate.add_argument("--name", required=True)
    profile_migrate.add_argument("--set-default", action="store_true")
    artifact_write = subparsers.add_parser("artifact-write")
    artifact_write.add_argument("--target", required=True)
    artifact_write.add_argument("--input", required=True)
    try:
        args = parser.parse_args(argv)
    except WorkflowError as exc:
        return fail("invalid_input", str(exc))
    if args.capabilities:
        emit(
            {
                "schema_version": 1,
                "payload_version": "1.2.0",
                "mutation": "local-write",
                "dry_run": True,
                "state_protocol": "confirmed-config-direct-workspace",
                "profile_kinds": ["team", "people"],
                "profile_schema": "references/team-context.schema.json",
                "people_profile_schema": "references/people-context.schema.json",
                "profile_location": (
                    "${XDG_CONFIG_HOME:-~/.config}/agent-skills/team/<profile>/<kind>.json"
                ),
                "legacy_profile_location": "${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts",
                "external_tools": {},
                "destructive_flags": ["context-save", "profile-save"],
            }
        )
        return 0
    try:
        if args.command == "action-check":
            context, _, source, path = load_context(args)
            kind = valid_kind(getattr(args, "kind", "team") or "team")
            emit(
                {
                    "status": "ok",
                    "action": FIXED_ACTION,
                    "profile_kind": kind,
                    "context_source": source,
                    "context_path": str(path),
                    "context_location": "legacy" if source.endswith("@legacy") else "current",
                    "profile": context.get("profile"),
                    "projects": len(context["projects"]) if kind == "team" else None,
                    "reports": len(context["reports"]) if kind == "people" else None,
                    "external_mutations": False,
                }
            )
            return 0
        if args.command == "context-inspect":
            context, _ = read_json(Path(args.input), "context input")
            assert_safe_context(context)
            missing = context_missing(context)
            emit(
                {
                    "status": "ok" if not missing else "setup-required",
                    "context": context,
                    "missing": missing,
                    "external_mutations": False,
                }
            )
            return 0 if not missing else 3
        if args.command == "context-list":
            root = state_root(create=False) / "contexts"
            names = []
            if root.exists():
                if root.is_symlink() or not root.is_dir():
                    raise WorkflowError("contexts directory is unsafe")
                for path in sorted(root.iterdir()):
                    if path.suffix == ".json" and path.is_file() and not path.is_symlink():
                        names.append(path.stem)
            emit({"status": "ok", "contexts": names, "external_mutations": False})
            return 0
        if args.command == "context-show":
            name = valid_name(args.name)
            context, _ = read_json(
                state_root(create=False) / "contexts" / f"{name}.json", "saved context"
            )
            emit(
                {
                    "status": "ok",
                    "name": name,
                    "context": validate_context(context),
                    "external_mutations": False,
                }
            )
            return 0
        if args.command == "context-prepare":
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            valid_name(args.name)
            existing = state_root(create=False) / "contexts" / f"{args.name}.json"
            payload = context_change_payload(args.name, raw)
            plan_digest, path, expires_at = prepare_plan(payload)
            emit(
                {
                    "status": "prepared",
                    "summary": {
                        "tldr": "Saving explicit team context.",
                        "scope": [args.name],
                        "risks": ["existing context will be replaced"] if existing.exists() else [],
                        "checks": ["context validation", "safe state path"],
                    },
                    "artifact_path": str(path),
                    "digest": plan_digest,
                    "expires_at": expires_at,
                    "ttl_seconds": TTL_SECONDS,
                    "apply_command": f"context-save --name {args.name} --input {args.input} --digest {plan_digest}",
                }
            )
            return 0
        if args.command == "context-save":
            name = valid_name(args.name)
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            report_path, report_digest = apply_context(name, raw, args.digest)
            emit(
                {
                    "status": "applied",
                    "summary": {
                        "tldr": "Context saved.",
                        "scope": [name],
                        "risks": [],
                        "checks": ["digest", "expiry", "single_use", "safe_path"],
                    },
                    "report_path": str(report_path),
                    "report_digest": report_digest,
                }
            )
            return 0
        profile_result = run_profile_command(args)
        if profile_result is not None:
            return profile_result
        if args.command == "artifact-write":
            artifact_source = regular(Path(args.input), "artifact input")
            content = artifact_source.read_bytes()
            target = workspace_target(args.target)
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic(target, content)
            emit(
                {
                    "status": "written",
                    "summary": {
                        "tldr": "Artifact written.",
                        "scope": [str(target)],
                        "risks": [],
                        "checks": ["regular input", "safe workspace path", "atomic replace"],
                    },
                    "target": str(target),
                    "digest": hashlib.sha256(content).hexdigest(),
                }
            )
            return 0
        return fail("invalid_command", "a supported subcommand is required")
    except SetupRequired as exc:
        return setup_required(exc.missing)
    except MutationIOError as exc:
        return fail("io_error", str(exc))
    except WorkflowError as exc:
        return fail("invalid_input", str(exc))
    except OSError as exc:
        return fail("io_error", f"local I/O failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
