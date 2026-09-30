#!/usr/bin/env python3
"""Static Agent Skills checker used by the skill-improver workflow."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from bisect import bisect_right
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote


def _bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


_bootstrap()

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Iterator

    from shared.references.python_runtime.capabilities import emit_capabilities
    from shared.references.python_runtime.contract import ContractArgumentParser, report_error
else:
    from portable_runtime.capabilities import emit_capabilities
    from portable_runtime.contract import ContractArgumentParser, report_error

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_LEVEL_RE = re.compile(r"^([A-Za-z0-9_.-]+):\s*(.*)$")
RESOURCE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:(?:references|scripts|templates|assets)/|\.\.?/)[A-Za-z0-9._/-]+)"
)
SCRIPT_RE = re.compile(r"(?<![A-Za-z0-9_.-])(scripts/[A-Za-z0-9._/-]+\.py)")
TODO_RE = re.compile(r"\b(?:TODO|FIXME)(?::|\()")
ALLOWED_FRONTMATTER = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_SKILL_LINES_WITHOUT_REFERENCES = 500
REQUIRED_SESSION_TABLES = ("session", "message", "part")
SKILL_TOOL_NAME = "skill"
UNKNOWN_SKILL_NAME = "(unknown)"
COMMAND_WRAPPERS = frozenset(
    {
        "task",
        "mise",
        "uv",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "npx",
        "git",
        "docker",
        "go",
        "cargo",
        "kubectl",
        "helm",
        "gh",
        "glab",
    }
)
DEFAULT_SESSION_LIMIT = 500
DEFAULT_MIN_PATTERN_COUNT = 5
DEFAULT_MAX_EXAMPLES = 10
MAX_PATTERN_ACTIONS_PER_SESSION = 5000
MAX_FREQUENT_ACTIONS = 20
MAX_PATTERNS = 50
MAX_CANDIDATES = 20
SQL_CHUNK_SIZE = 100


def xdg_data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value else Path.home() / ".local" / "share"


def mimo_database() -> Path:
    home = os.environ.get("MIMOCODE_HOME")
    if home:
        return Path(home) / "data" / "mimocode.db"
    return xdg_data_home() / "mimocode" / "mimocode.db"


HOST_DATABASES: dict[str, Callable[[], Path]] = {
    "opencode": lambda: xdg_data_home() / "opencode" / "opencode.db",
    "kilo": lambda: xdg_data_home() / "kilo" / "kilo.db",
    "mimo": mimo_database,
}


@dataclass(frozen=True)
class Issue:
    severity: str
    rule: str
    line: int
    message: str


class CheckError(Exception):
    """Fatal checker usage error."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], int, list[Issue]]:
    """Parse top-level YAML scalar fields without a YAML dependency."""
    lines = text.splitlines()
    issues: list[Issue] = []
    if not lines or lines[0] != "---":
        return (
            {},
            0,
            [Issue("critical", "frontmatter-missing", 1, "frontmatter block missing")],
        )
    closing = next((index for index, line in enumerate(lines[1:], 1) if line == "---"), -1)
    if closing < 0:
        return (
            {},
            0,
            [Issue("critical", "frontmatter-unclosed", 1, "frontmatter block unclosed")],
        )
    fields: dict[str, str] = {}
    active: str | None = None
    for line in lines[1:closing]:
        match = TOP_LEVEL_RE.match(line)
        if match:
            active, value = match.groups()
            fields[active] = "" if value.strip() in {">", ">-", "|", "|-"} else value.strip()
        elif line.startswith((" ", "\t")) and active is not None:
            fields[active] = f"{fields[active]} {line.strip()}".strip()
        else:
            active = None
    return fields, closing, issues


def check_frontmatter(skill_dir: Path, fields: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(set(fields) - ALLOWED_FRONTMATTER):
        issues.append(
            Issue(
                "major",
                "frontmatter-unsupported-field",
                2,
                f"unsupported frontmatter field {key!r}",
            )
        )
    name = fields.get("name", "")
    if not name:
        issues.append(Issue("critical", "name-missing", 2, "frontmatter name missing"))
    else:
        if not NAME_RE.fullmatch(name) or len(name) > MAX_SKILL_NAME_LENGTH:
            issues.append(Issue("critical", "name-invalid", 2, f"invalid skill name {name!r}"))
        if name != skill_dir.name:
            issues.append(
                Issue(
                    "critical",
                    "name-mismatch",
                    2,
                    f"name {name!r} does not match directory {skill_dir.name!r}",
                )
            )
    description = fields.get("description", "")
    if not description:
        issues.append(
            Issue("critical", "description-missing", 3, "frontmatter description missing")
        )
    elif len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        issues.append(
            Issue(
                "major",
                "description-too-long",
                3,
                "description exceeds 1024 characters",
            )
        )
    return issues


def safe_resource(skill_dir: Path, token: str) -> tuple[Path | None, str | None]:
    relative = Path(token)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None, "unsafe"
    candidate = skill_dir / relative
    current = skill_dir
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return None, "symlink"
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(skill_dir.resolve())
    except (OSError, ValueError):
        return None, "missing"
    return resolved, None


def check_resources(skill_dir: Path, lines: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[int, str]] = set()
    for number, line in enumerate(lines, 1):
        for match in RESOURCE_RE.finditer(line):
            token = match.group(1).rstrip(".,:;)")
            if (number, token) in seen or "<" in token or "$" in token:
                continue
            seen.add((number, token))
            _path, failure = safe_resource(skill_dir, token)
            if failure is not None:
                rule = "resource-unsafe" if failure in {"unsafe", "symlink"} else "resource-missing"
                issues.append(
                    Issue(
                        "critical",
                        rule,
                        number,
                        f"resource path {token!r} is {failure}",
                    )
                )
    return issues


def check_scripts(skill_dir: Path, lines: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    checked: set[str] = set()
    for number, line in enumerate(lines, 1):
        for match in SCRIPT_RE.finditer(line):
            token = match.group(1).rstrip(".,:;)")
            if token in checked:
                continue
            checked.add(token)
            script, _failure = safe_resource(skill_dir, token)
            if script is None:
                continue
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(script), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                issues.append(
                    Issue(
                        "major",
                        "script-help-failed",
                        number,
                        f"script {token!r} does not support --help",
                    )
                )
    return issues


def check_size(skill_dir: Path, lines: list[str]) -> list[Issue]:
    if len(lines) <= MAX_SKILL_LINES_WITHOUT_REFERENCES or (skill_dir / "references").is_dir():
        return []
    return [
        Issue(
            "major",
            "progressive-disclosure-missing",
            1,
            "SKILL.md exceeds 500 lines without references/",
        )
    ]


def check_skill(skill_dir: Path) -> list[Issue]:
    target = skill_dir.resolve()
    skill_md = target / "SKILL.md"
    if not target.is_dir() or not skill_md.is_file():
        raise CheckError(f"directory with SKILL.md not found: {skill_dir}")
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as error:
        raise CheckError(f"cannot read SKILL.md: {error}") from error
    lines = text.splitlines()
    fields, _closing, issues = parse_frontmatter(text)
    if not issues:
        issues.extend(check_frontmatter(target, fields))
    issues.extend(check_resources(target, lines))
    issues.extend(check_scripts(target, lines))
    issues.extend(check_size(target, lines))
    issues.extend(
        Issue("minor", "todo-marker", number, "unresolved TODO/FIXME marker")
        for number, line in enumerate(lines, 1)
        if TODO_RE.search(line)
    )
    order = {"critical": 0, "major": 1, "minor": 2}
    return sorted(issues, key=lambda issue: (order[issue.severity], issue.rule, issue.line))


def check_command(path: Path) -> int:
    issues = check_skill(path)
    counts = {
        severity: sum(issue.severity == severity for issue in issues)
        for severity in ("critical", "major", "minor")
    }
    print(
        json.dumps(
            {
                "schema_version": 1,
                "skill": str(path.resolve()),
                "status": "pass" if not counts["critical"] and not counts["major"] else "fail",
                "counts": counts,
                "issues": [asdict(issue) for issue in issues],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if counts["critical"] or counts["major"] else 0


@dataclass(frozen=True)
class SessionCall:
    session_id: str
    session_title: str
    call_id: str
    name: str
    status: str
    error: str | None
    input_text: str | None
    time_created: int
    duration_ms: int | None


@dataclass(frozen=True)
class DatabaseCollection:
    host: str
    path: str
    sessions_scanned: int
    skill_calls: list[SessionCall]
    user_texts: list[tuple[str, int, str]]
    segments: list[tuple[str, list[tuple[str, str]]]]
    skipped_parts: int


def resolve_session_databases(host: str, explicit: str | None) -> list[tuple[str, Path]]:
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise CheckError(f"session database not found: {explicit}")
        label = host if host in HOST_DATABASES else "custom"
        return [(label, path)]
    hosts = list(HOST_DATABASES) if host == "auto" else [host]
    found = [(name, HOST_DATABASES[name]()) for name in hosts]
    existing = [(name, path) for name, path in found if path.is_file()]
    if not existing:
        expected = ", ".join(str(path) for _name, path in found)
        raise CheckError(f"no session database found for host {host!r}: {expected}")
    return existing


def open_database(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def require_tables(connection: sqlite3.Connection, path: Path) -> None:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    present = {row["name"] for row in rows}
    missing = [table for table in REQUIRED_SESSION_TABLES if table not in present]
    if missing:
        raise CheckError(f"session database {path} misses tables {', '.join(missing)}")


def chunked(values: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_in(
    connection: sqlite3.Connection,
    sql: str,
    keys: list[str],
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    for chunk in chunked(keys, SQL_CHUNK_SIZE):
        placeholders = ",".join("?" * len(chunk))
        rows.extend(connection.execute(sql.format(placeholders=placeholders), chunk))
    return rows


def parse_part(data: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def state_field(part: dict[str, object], key: str) -> object:
    state = part.get("state")
    if not isinstance(state, dict):
        return None
    return state.get(key)


def skill_call(
    part: dict[str, object],
    session_id: str,
    session_title: str,
    time_created: int,
) -> SessionCall:
    state_input = state_field(part, "input")
    name = UNKNOWN_SKILL_NAME
    if isinstance(state_input, dict):
        value = state_input.get("name")
        if isinstance(value, str) and value:
            name = value
    error = state_field(part, "error")
    time = state_field(part, "time")
    duration = None
    if isinstance(time, dict):
        start, end = time.get("start"), time.get("end")
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            duration = end - start
    status = state_field(part, "status")
    call_id = part.get("callID")
    return SessionCall(
        session_id=session_id,
        session_title=session_title,
        call_id=call_id if isinstance(call_id, str) else "",
        name=name,
        status=status if isinstance(status, str) else "unknown",
        error=error if isinstance(error, str) else None,
        input_text=(
            json.dumps(state_input, ensure_ascii=False, sort_keys=True)
            if isinstance(state_input, dict) and state_input
            else None
        ),
        time_created=time_created,
        duration_ms=duration,
    )


def normalize_command(command: object) -> str:
    if not isinstance(command, str) or not command.strip():
        return "bash"
    tokens = command.strip().splitlines()[0].split()
    index = 0
    while index < len(tokens) - 1 and (
        tokens[index] == "sudo" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index])
    ):
        index += 1
    head = tokens[index]
    if head in COMMAND_WRAPPERS and index + 1 < len(tokens):
        return f"{head} {tokens[index + 1]}"
    return head


def bash_command(part: dict[str, object]) -> str | None:
    state_input = state_field(part, "input")
    if isinstance(state_input, dict):
        command = state_input.get("command")
        if isinstance(command, str):
            return command
    return None


def action_name(part: dict[str, object]) -> str:
    tool = part.get("tool")
    if tool == "bash":
        return f"bash:{normalize_command(bash_command(part))}"
    return f"tool:{tool if isinstance(tool, str) else 'unknown'}"


def action_example(part: dict[str, object]) -> str:
    command = first_line(bash_command(part))
    if command:
        return command
    state_input = state_field(part, "input")
    if isinstance(state_input, dict) and state_input:
        return first_line(json.dumps(state_input, ensure_ascii=False, sort_keys=True))
    return ""


def first_line(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().splitlines()[0]


def excerpt(value: str | None, limit: int) -> str | None:
    if value is None or limit <= 0 or len(value) <= limit:
        return value
    return value[:limit]


def collect_database(
    host: str,
    path: Path,
    since_ms: int | None,
    limit: int,
) -> DatabaseCollection:
    connection = open_database(path)
    try:
        require_tables(connection, path)
        conditions: list[str] = []
        parameters: list[object] = []
        if since_ms is not None:
            conditions.append("time_created >= ?")
            parameters.append(since_ms)
        query = "SELECT id, title, directory, time_created FROM session"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY time_created DESC"
        if limit > 0:
            query += " LIMIT ?"
            parameters.append(limit)
        sessions = connection.execute(query, parameters).fetchall()
        session_ids = [row["id"] for row in sessions]
        titles = {row["id"]: row["title"] for row in sessions}
        if not session_ids:
            return DatabaseCollection(
                host=host,
                path=str(path),
                sessions_scanned=0,
                skill_calls=[],
                user_texts=[],
                segments=[],
                skipped_parts=0,
            )
        part_rows = fetch_in(
            connection,
            "SELECT session_id, message_id, time_created, id, data FROM part"
            " WHERE session_id IN ({placeholders})",
            session_ids,
        )
        message_rows = fetch_in(
            connection,
            "SELECT id, data FROM message WHERE session_id IN ({placeholders})",
            session_ids,
        )
    finally:
        connection.close()
    roles: dict[str, str] = {}
    for row in message_rows:
        parsed = parse_part(row["data"])
        role = parsed.get("role") if parsed else None
        roles[row["id"]] = role if isinstance(role, str) else "unknown"
    parts: list[tuple[str, str, int, str, dict[str, object]]] = []
    skipped = 0
    for row in part_rows:
        parsed = parse_part(row["data"])
        if parsed is None:
            skipped += 1
            continue
        parts.append((row["session_id"], row["message_id"], row["time_created"], row["id"], parsed))
    parts.sort(key=lambda item: (item[2], item[3]))
    skill_calls: list[SessionCall] = []
    user_texts: list[tuple[str, int, str]] = []
    segments: list[tuple[str, list[tuple[str, str]]]] = []
    current_by_session: dict[str, list[tuple[str, str]]] = {}
    actions_per_session: dict[str, int] = {}
    for session_id, message_id, time_created, _part_id, part in parts:
        part_type = part.get("type")
        if part_type == "tool":
            if part.get("tool") == SKILL_TOOL_NAME:
                skill_calls.append(
                    skill_call(
                        part,
                        session_id,
                        titles.get(session_id, ""),
                        time_created,
                    )
                )
                closed = current_by_session.pop(session_id, None)
                if closed:
                    segments.append((session_id, closed))
            elif actions_per_session.get(session_id, 0) < MAX_PATTERN_ACTIONS_PER_SESSION:
                actions_per_session[session_id] = actions_per_session.get(session_id, 0) + 1
                current_by_session.setdefault(session_id, []).append(
                    (action_name(part), action_example(part))
                )
        elif part_type == "text" and roles.get(message_id) == "user":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                user_texts.append((session_id, time_created, text))
    segments.extend(current_by_session.items())
    return DatabaseCollection(
        host=host,
        path=str(path),
        sessions_scanned=len(session_ids),
        skill_calls=skill_calls,
        user_texts=user_texts,
        segments=segments,
        skipped_parts=skipped,
    )


def build_skills_report(
    collections: list[DatabaseCollection],
    user_texts: dict[str, list[tuple[int, str]]],
    skill_filter: str | None,
    max_examples: int,
    max_excerpt_chars: int,
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[SessionCall]] = {}
    for collection in collections:
        for call in collection.skill_calls:
            if skill_filter is None or call.name == skill_filter:
                grouped.setdefault(call.name, []).append(call)
    report: dict[str, dict[str, object]] = {}
    for name in sorted(grouped):
        calls = sorted(grouped[name], key=lambda call: (call.time_created, call.call_id))
        sessions: dict[str, list[SessionCall]] = {}
        for call in calls:
            sessions.setdefault(call.session_id, []).append(call)
        errors = [
            {
                "session": call.session_id,
                "title": call.session_title,
                "call_id": call.call_id,
                "input": excerpt(call.input_text, max_excerpt_chars),
                "error": excerpt(call.error, max_excerpt_chars),
            }
            for call in calls
            if call.status == "error"
        ][:max_examples]
        durations = [call.duration_ms for call in calls if call.duration_ms is not None]
        followups: list[dict[str, object]] = []
        for call in calls:
            texts = user_texts.get(call.session_id, [])
            position = bisect_right([time for time, _text in texts], call.time_created)
            if position >= len(texts):
                continue
            followups.append(
                {
                    "session": call.session_id,
                    "call_id": call.call_id,
                    "gap_ms": texts[position][0] - call.time_created,
                    "text": excerpt(texts[position][1], max_excerpt_chars),
                }
            )
            if len(followups) >= max_examples:
                break
        report[name] = {
            "invocations": len(calls),
            "sessions": len(sessions),
            "first_seen": calls[0].time_created,
            "last_seen": calls[-1].time_created,
            "status_counts": dict(sorted(Counter(call.status for call in calls).items())),
            "error_count": sum(call.status == "error" for call in calls),
            "errors": errors,
            "retry_sessions": [
                {
                    "session": session_id,
                    "title": session_calls[0].session_title,
                    "count": len(session_calls),
                }
                for session_id, session_calls in sorted(sessions.items())
                if len(session_calls) > 1
            ][:max_examples],
            "durations_ms": {
                "samples": len(durations),
                "avg": round(statistics.mean(durations)) if durations else None,
                "max": max(durations) if durations else None,
            },
            "followups": followups,
        }
    return report


def mine_patterns(
    collections: list[DatabaseCollection],
    min_count: int,
    max_examples: int,
    max_excerpt_chars: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    bigram_counts: Counter[tuple[str, str]] = Counter()
    bigram_sessions: dict[tuple[str, str], set[str]] = {}
    bigram_examples: dict[tuple[str, str], list[str]] = {}
    unigram_counts: Counter[str] = Counter()
    for collection in collections:
        for session_id, segment in collection.segments:
            for index, (action, _example) in enumerate(segment):
                unigram_counts[action] += 1
                if index + 1 >= len(segment):
                    continue
                pair = (action, segment[index + 1][0])
                bigram_counts[pair] += 1
                bigram_sessions.setdefault(pair, set()).add(session_id)
                example = segment[index + 1][1]
                if example and len(bigram_examples.setdefault(pair, [])) < max_examples:
                    bigram_examples[pair].append(excerpt(example, max_excerpt_chars) or "")
    frequent_actions = [
        {"action": action, "count": count}
        for action, count in sorted(unigram_counts.items(), key=lambda item: (-item[1], item[0]))[
            :MAX_FREQUENT_ACTIONS
        ]
    ]
    patterns: list[dict[str, object]] = []
    pattern_sessions: list[int] = []
    for pair, count in sorted(bigram_counts.items(), key=lambda item: (-item[1], item[0])):
        if count < min_count or len(patterns) >= MAX_PATTERNS:
            continue
        patterns.append(
            {
                "actions": list(pair),
                "count": count,
                "sessions": len(bigram_sessions[pair]),
                "example_sessions": sorted(bigram_sessions[pair])[:max_examples],
                "example_commands": bigram_examples.get(pair, []),
            }
        )
        pattern_sessions.append(len(bigram_sessions[pair]))
    candidates = [
        dict(pattern, kind="new-skill-candidate")
        for pattern, sessions in zip(patterns, pattern_sessions, strict=True)
        if sessions >= 2
    ][:MAX_CANDIDATES]
    return frequent_actions, patterns, candidates


def sessions_command(arguments: argparse.Namespace) -> int:
    since_ms = None
    if arguments.since > 0:
        since_ms = int(time.time() * 1000) - arguments.since * 86400000
    databases = resolve_session_databases(arguments.host, arguments.db)
    collections: list[DatabaseCollection] = []
    databases_report: list[dict[str, object]] = []
    for host, path in databases:
        collection = collect_database(host, path, since_ms, arguments.limit)
        collections.append(collection)
        databases_report.append(
            {
                "host": collection.host,
                "path": collection.path,
                "sessions_scanned": collection.sessions_scanned,
                "skill_calls": len(collection.skill_calls),
                "skipped_parts": collection.skipped_parts,
            }
        )
    user_texts: dict[str, list[tuple[int, str]]] = {}
    for collection in collections:
        for session_id, time_created, text in collection.user_texts:
            user_texts.setdefault(session_id, []).append((time_created, text))
    for texts in user_texts.values():
        texts.sort()
    skills = build_skills_report(
        collections,
        user_texts,
        arguments.skill,
        arguments.max_examples,
        arguments.max_excerpt_chars,
    )
    frequent_actions, patterns, candidates = mine_patterns(
        collections,
        arguments.min_pattern_count,
        arguments.max_examples,
        arguments.max_excerpt_chars,
    )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "command": "sessions",
                "filters": {
                    "host": arguments.host,
                    "db": arguments.db,
                    "skill": arguments.skill,
                    "since_days": arguments.since or None,
                    "limit": arguments.limit,
                    "min_pattern_count": arguments.min_pattern_count,
                    "max_excerpt_chars": arguments.max_excerpt_chars,
                    "max_examples": arguments.max_examples,
                },
                "databases": databases_report,
                "skills": skills,
                "frequent_actions": frequent_actions,
                "patterns": patterns,
                "candidates": candidates,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="skill-improver")
    result.add_argument("--capabilities", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--path", required=True)
    sessions = commands.add_parser("sessions")
    sessions.add_argument("--db", help="explicit session database path")
    sessions.add_argument(
        "--host",
        choices=[*HOST_DATABASES, "auto"],
        default="auto",
        help="host profile used to locate databases without --db",
    )
    sessions.add_argument("--skill", help="restrict the skills section to one name")
    sessions.add_argument(
        "--since",
        type=int,
        default=0,
        help="only sessions created within this many days; 0 scans all history",
    )
    sessions.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SESSION_LIMIT,
        help="most recent sessions per database; 0 scans all",
    )
    sessions.add_argument(
        "--min-pattern-count",
        type=int,
        default=DEFAULT_MIN_PATTERN_COUNT,
        help="minimum recurrences for an uncovered action pair",
    )
    sessions.add_argument(
        "--max-excerpt-chars",
        type=int,
        default=0,
        help="character cap for verbatim excerpts; 0 keeps them full",
    )
    sessions.add_argument(
        "--max-examples",
        type=int,
        default=DEFAULT_MAX_EXAMPLES,
        help="bounded examples per report entry",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.1.0",
        mutation="read",
        supports_dry_run=False,
    ):
        return 0
    arguments = arguments_parser.parse_args(argv)
    try:
        if arguments.command == "check":
            return check_command(Path(arguments.path))
        return sessions_command(arguments)
    except (CheckError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        report_error(f"{arguments.command}_error", str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
