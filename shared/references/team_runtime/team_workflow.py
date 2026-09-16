#!/usr/bin/env python3
"""Resolve private team profiles and apply confirmed local artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

MAX_BYTES = 2 * 1024 * 1024
TTL_SECONDS = 600
FIXED_ACTION = {
    "team-sprint-start": "planning",
    "team-sprint-close": "sprint-close",
    "team-retro": "retro",
    "team-roadmap": "roadmap",
    "slides-prompts-prepare": "slides-prompts",
}.get(Path(__file__).resolve().parents[1].name, "planning")
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


class WorkflowError(ValueError):
    """Expected safe workflow failure."""


class SetupRequired(WorkflowError):
    """The selected action needs more profile data before it can run."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = sorted(set(missing))
        super().__init__("setup-required: " + ", ".join(self.missing))


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
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError("state directory must be a real directory")
    path.chmod(0o700)
    return path.resolve()


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
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    path = home / "agent-skills" / "team-workflow"
    if create:
        return private_directory(path)
    if not path.exists():
        return path
    return existing_private_directory(path, "state directory")


def config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured and Path(configured).is_absolute():
        return Path(configured)
    return Path.home() / ".config"


def profile_root(*, create: bool = False) -> Path:
    path = config_home() / "opencode" / "team-contexts"
    if create:
        return private_directory(path)
    if not path.exists():
        return path
    return existing_private_directory(path, "team profile directory")


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
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


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
                or isinstance(project["id"], int)
                and not isinstance(project["id"], bool)
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
        if "status_legend" in action_value and not isinstance(action_value["status_legend"], dict):
            invalid.append(f"{path}.status_legend")
        elif "status_legend" in action_value and any(
            not is_text(key) or not is_text(value)
            for key, value in action_value["status_legend"].items()
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


def valid_name(value: str) -> str:
    if (
        not value
        or len(value) > 63
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value)
    ):
        raise WorkflowError("context name is invalid")
    return value


def profile_path(name: str, *, must_exist: bool = True) -> Path:
    root = profile_root(create=False)
    path = root / f"{valid_name(name)}.json"
    if must_exist:
        return private_regular(path, "team profile")
    return path


def settings_path() -> Path:
    return profile_root(create=False) / "settings.json"


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
    root = profile_root(create=False)
    if not root.exists():
        raise SetupRequired(["profile.default"])
    settings = root / "settings.json"
    if not settings.exists():
        fallback = root / "default.json"
        if fallback.exists():
            private_regular(fallback, "default team profile")
            return "default"
        raise SetupRequired(["profile.default"])
    value, _ = read_private_json(settings, "team profile settings")
    if set(value) != {"schema_version", "default_profile"}:
        raise WorkflowError("team profile settings contain invalid fields")
    if value.get("schema_version") != 1 or isinstance(value.get("schema_version"), bool):
        raise WorkflowError("team profile settings schema_version must be 1")
    name = value.get("default_profile")
    if not isinstance(name, str):
        raise WorkflowError("team profile settings default_profile is invalid")
    return valid_name(name)


def read_profile(name: str) -> tuple[dict[str, Any], bytes, Path]:
    path = profile_path(name, must_exist=False)
    if not path.exists():
        raise SetupRequired([f"profile.{name}"])
    path = private_regular(path, "team profile")
    value, raw = read_private_json(path, "team profile")
    if value.get("profile") != name:
        raise WorkflowError("team profile name does not match its file name")
    return validate_profile(value, FIXED_ACTION), raw, path


def profile_change_payload(
    name: str,
    raw: bytes,
    *,
    set_default: bool,
) -> dict[str, Any]:
    target = profile_path(name, must_exist=False)
    settings = settings_path()
    return {
        "kind": "profile",
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
        os.fsync(handle.fileno())


def prepare_plan(payload: dict[str, Any]) -> tuple[str, Path, float]:
    plan_digest = digest(payload)
    path = private_directory(state_root() / "plans") / f"{plan_digest}.json"
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


def consume(plan_digest: str, payload: dict[str, Any]) -> None:
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
    receipt = private_directory(state_root() / "receipts") / f"{plan_digest}.json"
    try:
        descriptor = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise WorkflowError("prepared plan is already consumed") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_bytes({"digest": plan_digest, "consumed_at": time.time()}))
        handle.flush()
        os.fsync(handle.fileno())


def report(plan_digest: str, result: dict[str, object]) -> tuple[Path, str]:
    document = {
        "schema_version": 1,
        "digest": plan_digest,
        "result": result,
        "checks": ["digest", "expiry", "single_use", "safe_path"],
    }
    report_digest = digest(document)
    path = private_directory(state_root() / "reports") / f"{report_digest}.json"
    write_once(path, canonical_bytes(document))
    return path, report_digest


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
    if not supplied:
        name = default_profile_name()
        context, raw, path = read_profile(name)
        return context, raw, f"profile:{name}", path
    if args.profile:
        name = valid_name(args.profile)
        context, raw, path = read_profile(name)
        return context, raw, f"profile:{name}", path
    if args.context_file or args.chat_input:
        path = Path(args.context_file or args.chat_input)
        value, raw = read_json(path, "context")
        resolved = path.resolve()
        if value.get("schema_version") == 1 and "profile" in value:
            return validate_profile(value, FIXED_ACTION), raw, "explicit-profile", resolved
        return validate_context(value), raw, "explicit-context", resolved
    state = state_root(create=False)
    path = regular(state / "contexts" / f"{valid_name(args.context_name)}.json", "saved context")
    value, raw = read_json(path, "saved context")
    return validate_context(value), raw, f"saved-context:{args.context_name}", path


def main(argv: list[str] | None = None) -> int:
    parser = ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    check = subparsers.add_parser("action-check")
    check.add_argument("--context-file")
    check.add_argument("--context-name")
    check.add_argument("--chat-input")
    check.add_argument("--profile")
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
    subparsers.add_parser("profile-list")
    profile_prepare = subparsers.add_parser("profile-prepare")
    profile_prepare.add_argument("--name", required=True)
    profile_prepare.add_argument("--input", required=True)
    profile_prepare.add_argument("--set-default", action="store_true")
    profile_save = subparsers.add_parser("profile-save")
    profile_save.add_argument("--name", required=True)
    profile_save.add_argument("--input", required=True)
    profile_save.add_argument("--digest", required=True)
    profile_save.add_argument("--set-default", action="store_true")
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
                "payload_version": "1.1.0",
                "mutation": "local-write",
                "dry_run": True,
                "state_protocol": "confirmed-config-direct-workspace",
                "profile_schema": "references/team-context.schema.json",
                "profile_location": "${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts",
                "external_tools": {},
                "destructive_flags": ["context-save", "profile-save"],
            }
        )
        return 0
    try:
        if args.command == "action-check":
            context, _, source, path = load_context(args)
            emit(
                {
                    "status": "ok",
                    "action": FIXED_ACTION,
                    "context_source": source,
                    "context_path": str(path),
                    "profile": context.get("profile"),
                    "projects": len(context["projects"]),
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
            valid_name(args.name)
            context, raw = read_json(Path(args.input), "context input")
            validate_context(context)
            payload = context_change_payload(args.name, raw)
            consume(args.digest, payload)
            root = private_directory(state_root() / "contexts")
            atomic(root / f"{args.name}.json", raw)
            report_path, report_digest = report(
                args.digest, {"status": "applied", "name": args.name}
            )
            emit(
                {
                    "status": "applied",
                    "summary": {
                        "tldr": "Context saved.",
                        "scope": [args.name],
                        "risks": [],
                        "checks": ["digest", "expiry", "single_use", "safe_path"],
                    },
                    "report_path": str(report_path),
                    "report_digest": report_digest,
                }
            )
            return 0
        if args.command == "profile-inspect":
            profile, _ = read_json(Path(args.input), "profile input")
            missing, invalid = inspect_profile(profile, FIXED_ACTION)
            emit(
                {
                    "status": "invalid" if invalid else "setup-required" if missing else "ok",
                    "action": FIXED_ACTION,
                    "profile": profile.get("profile"),
                    "missing": missing,
                    "invalid": invalid,
                    "external_mutations": False,
                }
            )
            return 2 if invalid else 3 if missing else 0
        if args.command == "profile-list":
            root = profile_root(create=False)
            profile_names: list[str] = []
            if root.exists():
                for path in sorted(root.iterdir()):
                    if path.name == "settings.json" or path.suffix != ".json":
                        continue
                    private_regular(path, "team profile")
                    profile_names.append(path.stem)
            try:
                default = default_profile_name()
            except SetupRequired:
                default = None
            emit(
                {
                    "status": "ok",
                    "profiles": profile_names,
                    "default_profile": default,
                    "external_mutations": False,
                }
            )
            return 0
        if args.command == "profile-prepare":
            name = valid_name(args.name)
            profile, raw = read_json(Path(args.input), "profile input")
            validate_profile(profile, FIXED_ACTION)
            if profile.get("profile") != name:
                raise WorkflowError("team profile name does not match --name")
            payload = profile_change_payload(name, raw, set_default=args.set_default)
            target = profile_path(name, must_exist=False)
            plan_digest, path, expires_at = prepare_plan(payload)
            emit(
                {
                    "status": "prepared",
                    "summary": {
                        "tldr": "Saving a private team profile.",
                        "scope": [f"profile:{name}"],
                        "risks": ["existing profile will be replaced"] if target.exists() else [],
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
                        f"--digest {plan_digest}" + (" --set-default" if args.set_default else "")
                    ),
                }
            )
            return 0
        if args.command == "profile-save":
            name = valid_name(args.name)
            profile, raw = read_json(Path(args.input), "profile input")
            validate_profile(profile, FIXED_ACTION)
            if profile.get("profile") != name:
                raise WorkflowError("team profile name does not match --name")
            payload = profile_change_payload(name, raw, set_default=args.set_default)
            consume(args.digest, payload)
            root = profile_root(create=True)
            atomic(root / f"{name}.json", raw)
            if args.set_default:
                atomic(
                    root / "settings.json",
                    canonical_bytes({"schema_version": 1, "default_profile": name}),
                )
            report_path, report_digest = report(
                args.digest,
                {"status": "applied", "profile": name, "default": args.set_default},
            )
            emit(
                {
                    "status": "applied",
                    "summary": {
                        "tldr": "Private team profile saved.",
                        "scope": [f"profile:{name}"],
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
    except WorkflowError as exc:
        return fail("invalid_input", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
