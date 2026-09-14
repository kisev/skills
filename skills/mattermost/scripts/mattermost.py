#!/usr/bin/env python3
"""Read one explicit Mattermost target through GET-only API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

AUTH_REQUIRED = 3
CACHE_ERROR_EXIT = 4
SCHEMA_VERSION = 2
CACHE_TTL_SECONDS = 300
CACHE_SCHEMA_VERSION = 3
CACHE_STABLE_AGE_SECONDS = 7 * 24 * 60 * 60
MAX_RESPONSE = 32 * 1024 * 1024
PAGE_SIZE = 200
MAX_PAGES = 10_000
RECEIPT_TTL_SECONDS = 300
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\Z")
MATTERMOST_ID = re.compile(r"[a-z0-9]{26}\Z")


class MattermostError(ValueError):
    """Expected safe failure."""


class AuthorizationRequired(MattermostError):
    """No valid origin-bound credential is available."""


class CacheError(MattermostError):
    """The local cache cannot be trusted."""


class ContractArgumentParser(argparse.ArgumentParser):
    """Return invalid CLI input through the JSON runner contract."""

    def error(self, message: str) -> NoReturn:
        raise MattermostError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep every request at the origin explicitly selected by the caller."""

    def redirect_request(self, *arguments: object, **keywords: object) -> None:
        return None


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def now() -> int:
    return int(time.time())


def error_item(code: str, message: str, *, retryable: bool = False) -> dict[str, object]:
    return {"code": code, "message": message, "retryable": retryable}


def result_base(
    *, scope: str = "unknown", target: object = None, period: object = None
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "complete": False,
        "scope": scope,
        "target": target,
        "period": period,
        "errors": [],
        "warnings": [],
        "counts": {"posts": 0, "threads": 0, "members": 0, "resolved": 0},
        "pages": {"posts": 0, "members": 0},
        "unresolved_ids": [],
        "cache_hit": False,
        "cache_age": None,
        "access_revalidated": False,
        "external_mutations": False,
    }


def fail(code: str, message: str, exit_code: int = 2) -> int:
    result = result_base()
    result["errors"] = [error_item(code, message)]
    emit(result)
    return exit_code


def normalized_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise MattermostError(
            "Mattermost URL must use an absolute HTTPS origin without credentials"
        )
    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except ValueError as exc:
        raise MattermostError("Mattermost URL has an invalid port") from exc
    if port == 443:
        port = None
    return f"https://{hostname}{f':{port}' if port else ''}"


def identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise MattermostError(f"Mattermost {label} is invalid")
    return value


def private_directory(path: Path) -> Path:
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
            raise MattermostError("private directory must be a real directory")
    else:
        path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def private_file(path: Path) -> None:
    if not path.exists() or path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise MattermostError("private file is unsafe")
    path.chmod(0o600)


def config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mattermost"


def cache_root() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "mattermost"


def cache_path() -> Path:
    return cache_root() / "cache.sqlite3"


def origin_token_file(origin: str) -> Path:
    key = hashlib.sha256(normalized_origin(origin).encode()).hexdigest()
    return private_directory(private_directory(config_root()) / key) / "token"


def read_token(origin: str) -> str:
    path = origin_token_file(origin)
    if not path.exists():
        raise AuthorizationRequired("Mattermost authentication is required for this origin")
    try:
        private_file(path)
    except MattermostError as exc:
        raise AuthorizationRequired("Mattermost credential file is unsafe") from exc
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token or "\r" in token:
        raise AuthorizationRequired("Mattermost credential is invalid")
    return token


def save_token(origin: str, token: str) -> None:
    if not token or "\n" in token or "\r" in token:
        raise MattermostError("browser did not provide a valid session credential")
    path = origin_token_file(origin)
    temporary = path.with_name(f".token-{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(token + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)
        private_file(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parse_period(
    since: str | None, until: str | None, *, allowed: bool
) -> dict[str, str | None] | None:
    if not allowed and (since is not None or until is not None):
        raise MattermostError("--since and --until are only valid for channel and chat reads")
    if not allowed:
        return None
    parsed: list[datetime | None] = []
    for value in (since, until):
        if value is None:
            parsed.append(None)
            continue
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MattermostError("period values must be ISO-8601 timestamps") from exc
        if instant.tzinfo is None:
            raise MattermostError("period values must include a timezone")
        parsed.append(instant.astimezone(UTC))
    if parsed[0] and parsed[1] and parsed[0] >= parsed[1]:
        raise MattermostError("--since must be before --until")
    return {"since": since, "until": until}


def default_since() -> str:
    local = datetime.now().astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()


def datetime_millis_ceiling(value: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = value.astimezone(UTC) - epoch
    return (
        delta.days * 24 * 60 * 60 * 1000 + delta.seconds * 1000 + (delta.microseconds + 999) // 1000
    )


def period_bounds(period: dict[str, str | None], current_ms: int) -> tuple[int, int]:
    since = (
        datetime.fromisoformat(period["since"].replace("Z", "+00:00"))
        if period["since"]
        else datetime(1970, 1, 1, tzinfo=UTC)
    )
    until = (
        datetime.fromisoformat(period["until"].replace("Z", "+00:00"))
        if period["until"]
        else datetime.fromtimestamp(current_ms / 1000, UTC)
    )
    since_ms = datetime_millis_ceiling(since)
    until_ms = min(datetime_millis_ceiling(until), current_ms)
    if since_ms >= until_ms:
        raise MattermostError("Mattermost period has not started or is empty")
    return since_ms, until_ms


def classify_url(value: str) -> dict[str, str | None]:
    parsed = urllib.parse.urlsplit(value)
    origin = normalized_origin(value)
    if not parsed.path or "%" in parsed.path:
        raise MattermostError("Mattermost URL path is invalid")
    pieces = parsed.path.split("/")
    if len(pieces) != 4 or pieces[0] or not all(pieces[1:]):
        raise MattermostError("Mattermost URL must identify exactly one supported target")
    team = identifier(pieces[1], "team")
    route = identifier(pieces[2], "route")
    item = (
        f"@{identifier(pieces[3][1:], 'username')}"
        if route == "messages" and pieces[3].startswith("@")
        else identifier(pieces[3], "path component")
    )
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    post_values = [item for key, item in pairs if key in {"post", "post_id", "focusedPostId"}]
    if len(post_values) > 1 or any(not value for value in post_values):
        raise MattermostError("Mattermost post query is ambiguous")
    post_id = identifier(post_values[0], "post ID") if post_values else None
    if route == "pl":
        if parsed.query:
            raise MattermostError("Mattermost permalink must not contain a query")
        return {
            "origin": origin,
            "kind": "post",
            "route": route,
            "team": team,
            "channel": None,
            "post_id": identifier(item, "post ID"),
        }
    if route == "channels":
        return {
            "origin": origin,
            "kind": "post" if post_id else "channel",
            "route": route,
            "team": team,
            "channel": item,
            "post_id": post_id,
        }
    if route in {"messages", "group"}:
        return {
            "origin": origin,
            "kind": "post" if post_id else "chat",
            "route": route,
            "team": team,
            "channel": item,
            "post_id": post_id,
        }
    raise MattermostError("URL must identify one post, channel, direct, or group chat")


def normalized_target(target: dict[str, str | None]) -> dict[str, str | None]:
    return {
        "origin": target["origin"],
        "kind": target["kind"],
        "team": target["team"],
        "channel": target["channel"],
        "post_id": target["post_id"],
    }


class Client:
    def __init__(self, origin: str, token: str):
        self.origin = normalized_origin(origin)
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, path: str) -> object:
        if not path.startswith("/") or "://" in path or ".." in path.split("/"):
            raise MattermostError("unsafe Mattermost API path")
        request = urllib.request.Request(
            f"{self.origin}/api/v4{path}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthorizationRequired(
                    "Mattermost session is unavailable for this origin"
                ) from exc
            raise MattermostError(f"Mattermost GET failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise MattermostError("Mattermost network request failed") from exc
        if len(data) > MAX_RESPONSE:
            raise MattermostError("Mattermost response exceeds the size limit")
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise MattermostError("Mattermost returned invalid JSON") from exc


def user_identity(client: Client) -> str:
    value = client.get("/users/me")
    if not isinstance(value, dict):
        raise MattermostError("Mattermost identity response is incomplete")
    return identifier(value.get("id"), "user ID")


def channel_response(value: object, *, expected_id: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        raise MattermostError("Mattermost channel identity is incomplete")
    channel_id = identifier(value["id"], "channel ID")
    if expected_id is not None and channel_id != expected_id:
        raise MattermostError("Mattermost returned a different channel")
    return value


def team_identity(client: Client, team: str) -> str:
    value = client.get(f"/teams/name/{urllib.parse.quote(team, safe='')}")
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        raise MattermostError("Mattermost team identity is incomplete")
    return identifier(value["id"], "team ID")


def user_team_channels(client: Client, user_id: str, team_id: str) -> list[dict[str, Any]]:
    value = client.get(
        f"/users/{urllib.parse.quote(user_id, safe='')}/teams/"
        f"{urllib.parse.quote(team_id, safe='')}/channels"
    )
    if not isinstance(value, list):
        raise MattermostError("Mattermost user channel list is incomplete")
    return [item for item in value if isinstance(item, dict)]


def validate_chat_type(channel: dict[str, Any], route: str | None) -> None:
    channel_type = channel.get("type")
    expected = {"G"} if route == "group" else {"D", "G"}
    if channel_type not in expected:
        raise MattermostError("Mattermost chat URL resolved to a different channel type")


def resolve_channel(client: Client, target: dict[str, str | None], user_id: str) -> dict[str, Any]:
    team = identifier(target["team"], "team")
    channel_value = target["channel"]
    channel = (
        f"@{identifier(channel_value[1:], 'username')}"
        if isinstance(channel_value, str) and channel_value.startswith("@")
        else identifier(channel_value, "channel")
    )
    team_id = team_identity(client, team)
    if MATTERMOST_ID.fullmatch(channel):
        data = channel_response(
            client.get(f"/channels/{urllib.parse.quote(channel, safe='')}"),
            expected_id=channel,
        )
        if data.get("type") in {"D", "G"}:
            matches = [
                item
                for item in user_team_channels(client, user_id, team_id)
                if item.get("id") == channel
            ]
            if len(matches) != 1:
                raise MattermostError("Mattermost chat is not available in the URL team")
        elif data.get("team_id") != team_id:
            raise MattermostError("Mattermost channel is not in the URL team")
        if target["kind"] == "chat":
            validate_chat_type(data, target.get("route"))
        return data

    if target["kind"] == "chat" and channel.startswith("@"):
        username = identifier(channel[1:], "username")
        peer = client.get(f"/users/username/{urllib.parse.quote(username, safe='')}")
        if not isinstance(peer, dict) or not isinstance(peer.get("id"), str):
            raise MattermostError("Mattermost direct-message peer is incomplete")
        peer_id = identifier(peer["id"], "user ID")
        expected_name = "__".join(sorted((user_id, peer_id)))
        matches = [
            item
            for item in user_team_channels(client, user_id, team_id)
            if item.get("type") == "D" and item.get("name") == expected_name
        ]
        if len(matches) != 1:
            raise MattermostError("Mattermost direct chat could not be resolved exactly")
        resolved = channel_response(matches[0])
        validate_chat_type(resolved, target.get("route"))
        return resolved

    direct_parts = channel.split("__")
    if len(direct_parts) == 2 and all(MATTERMOST_ID.fullmatch(part) for part in direct_parts):
        matches = [
            item
            for item in user_team_channels(client, user_id, team_id)
            if item.get("type") == "D" and item.get("name") == channel
        ]
        if len(matches) != 1:
            raise MattermostError("Mattermost direct chat could not be resolved exactly")
        resolved = channel_response(matches[0])
        if target["kind"] == "chat":
            validate_chat_type(resolved, target.get("route"))
        return resolved

    data = channel_response(
        client.get(
            f"/teams/{urllib.parse.quote(team_id, safe='')}/channels/name/"
            f"{urllib.parse.quote(channel, safe='')}"
        )
    )
    if target["kind"] == "chat":
        validate_chat_type(data, target.get("route"))
    return data


def revalidate_access(
    client: Client, target: dict[str, str | None], user_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if target["kind"] == "post":
        post = client.get(
            f"/posts/{urllib.parse.quote(identifier(target['post_id'], 'post ID'), safe='')}"
        )
        if (
            not isinstance(post, dict)
            or post.get("id") != target["post_id"]
            or not isinstance(post.get("channel_id"), str)
            or not isinstance(post.get("create_at"), int)
            or post["create_at"] <= 0
        ):
            raise MattermostError("Mattermost post access response is incomplete")
        return post, None
    return None, resolve_channel(client, target, user_id)


class CacheStore:
    def __init__(self, origin: str | None = None, user_id: str | None = None):
        self.origin = normalized_origin(origin) if origin is not None else ""
        self.user_id = identifier(user_id, "user ID") if user_id is not None else ""
        self.path = cache_path()
        try:
            root = private_directory(self.path.parent)
            self.path = root / self.path.name
            if self.path.exists():
                private_file(self.path)
            self.database = sqlite3.connect(self.path, timeout=5)
            self.database.row_factory = sqlite3.Row
            self.path.chmod(0o600)
            self.database.execute("PRAGMA busy_timeout=5000")
            self.database.execute("PRAGMA journal_mode=DELETE")
            self.database.execute("PRAGMA secure_delete=ON")
            self._initialize()
        except (MattermostError, OSError, sqlite3.Error) as exc:
            database = getattr(self, "database", None)
            if database is not None:
                database.close()
            raise CacheError(f"Mattermost cache is unavailable: {exc}") from exc

    def __enter__(self) -> "CacheStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.database.close()

    def _initialize(self) -> None:
        version = int(self.database.execute("PRAGMA user_version").fetchone()[0])
        if version not in {0, CACHE_SCHEMA_VERSION}:
            raise CacheError(f"Mattermost cache schema {version} is unsupported; clear the cache")
        if version == 0:
            self.database.execute("DROP TABLE IF EXISTS snapshots_v2")
            self.database.execute("DROP TABLE IF EXISTS posts_v3")
            self.database.execute("DROP TABLE IF EXISTS threads_v3")
            self.database.execute("DROP TABLE IF EXISTS coverages_v3")
        self.database.executescript(
            """
            CREATE TABLE IF NOT EXISTS posts_v3 (
                origin TEXT NOT NULL,
                user_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                root_id TEXT NOT NULL,
                create_at INTEGER NOT NULL,
                activity_at INTEGER NOT NULL,
                fetched_at INTEGER NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (origin, user_id, post_id)
            );
            CREATE INDEX IF NOT EXISTS posts_v3_range
                ON posts_v3 (origin, user_id, channel_id, create_at, post_id);
            CREATE TABLE IF NOT EXISTS threads_v3 (
                origin TEXT NOT NULL,
                user_id TEXT NOT NULL,
                root_id TEXT NOT NULL,
                post_ids TEXT NOT NULL,
                fetched_at INTEGER NOT NULL,
                complete INTEGER NOT NULL,
                PRIMARY KEY (origin, user_id, root_id)
            );
            CREATE TABLE IF NOT EXISTS coverages_v3 (
                origin TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                since_ms INTEGER NOT NULL,
                until_ms INTEGER NOT NULL,
                fetched_at INTEGER NOT NULL,
                PRIMARY KEY (origin, user_id, channel_id, since_ms, until_ms),
                CHECK (since_ms < until_ms)
            );
            CREATE INDEX IF NOT EXISTS coverages_v3_range
                ON coverages_v3 (origin, user_id, channel_id, since_ms, until_ms);
            """
        )
        expected_columns = {
            "posts_v3": (
                ("origin", "TEXT", 1, 1),
                ("user_id", "TEXT", 1, 2),
                ("post_id", "TEXT", 1, 3),
                ("channel_id", "TEXT", 1, 0),
                ("root_id", "TEXT", 1, 0),
                ("create_at", "INTEGER", 1, 0),
                ("activity_at", "INTEGER", 1, 0),
                ("fetched_at", "INTEGER", 1, 0),
                ("payload", "TEXT", 1, 0),
            ),
            "threads_v3": (
                ("origin", "TEXT", 1, 1),
                ("user_id", "TEXT", 1, 2),
                ("root_id", "TEXT", 1, 3),
                ("post_ids", "TEXT", 1, 0),
                ("fetched_at", "INTEGER", 1, 0),
                ("complete", "INTEGER", 1, 0),
            ),
            "coverages_v3": (
                ("origin", "TEXT", 1, 1),
                ("user_id", "TEXT", 1, 2),
                ("channel_id", "TEXT", 1, 3),
                ("since_ms", "INTEGER", 1, 4),
                ("until_ms", "INTEGER", 1, 5),
                ("fetched_at", "INTEGER", 1, 0),
            ),
        }
        for table, expected in expected_columns.items():
            observed = tuple(
                (
                    str(row["name"]),
                    str(row["type"]).upper(),
                    int(row["notnull"]),
                    int(row["pk"]),
                )
                for row in self.database.execute(f"PRAGMA table_info({table})").fetchall()
            )
            if observed != expected:
                raise CacheError(f"Mattermost cache table {table} has an invalid schema")
        coverage_schema = self.database.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='coverages_v3'"
        ).fetchone()
        coverage_sql = str(coverage_schema["sql"]) if coverage_schema is not None else ""
        if "CHECK (since_ms < until_ms)" not in coverage_sql:
            raise CacheError("Mattermost cache coverage constraint is missing")
        self.database.execute(f"PRAGMA user_version={CACHE_SCHEMA_VERSION}")
        self.database.commit()

    @staticmethod
    def _cacheable_post(post: dict[str, Any]) -> tuple[str, str, str, int, int, str]:
        post_id = identifier(post.get("id"), "post ID")
        channel_id = identifier(post.get("channel_id"), "channel ID")
        root_value = post.get("root_id") or ""
        root_id = identifier(root_value, "root post ID") if root_value else ""
        create_at = post.get("create_at")
        if not isinstance(create_at, int) or create_at <= 0:
            raise CacheError("Mattermost cache received a post without create_at")
        activity_values = [
            value
            for key in ("create_at", "update_at", "edit_at", "delete_at")
            if isinstance((value := post.get(key)), int)
        ]
        clean = safe_post(post, include_reactions=False)
        clean.pop("context_only", None)
        payload = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return post_id, channel_id, root_id, create_at, max(activity_values), payload

    @classmethod
    def _decoded_post(cls, row: sqlite3.Row, current_ms: int) -> dict[str, Any]:
        try:
            payload = row["payload"]
            value = json.loads(payload) if isinstance(payload, str) else None
        except json.JSONDecodeError as exc:
            raise CacheError("Mattermost cache contains invalid post JSON") from exc
        if not isinstance(value, dict):
            raise CacheError("Mattermost cache contains an invalid post")
        post_id, channel_id, root_id, create_at, activity_at, _payload = cls._cacheable_post(value)
        expected = (
            str(row["post_id"]),
            str(row["channel_id"]),
            str(row["root_id"]),
            int(row["create_at"]),
            int(row["activity_at"]),
        )
        if (post_id, channel_id, root_id, create_at, activity_at) != expected:
            raise CacheError("Mattermost cache post index does not match its payload")
        if int(row["fetched_at"]) < 0 or int(row["fetched_at"]) > current_ms:
            raise CacheError("Mattermost cache post has an invalid fetch time")
        return value

    def _put_posts(self, posts: list[dict[str, Any]], fetched_at: int) -> None:
        values = []
        for post in posts:
            cached = self._cacheable_post(post)
            post_id, channel_id, _root_id, create_at, _activity_at, _payload = cached
            existing = self.database.execute(
                """
                SELECT 1 FROM posts_v3
                WHERE origin=? AND user_id=? AND post_id=?
                """,
                (self.origin, self.user_id, post_id),
            ).fetchone()
            newer_coverage = self.database.execute(
                """
                SELECT 1 FROM coverages_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND since_ms<=? AND until_ms>? AND fetched_at>?
                LIMIT 1
                """,
                (self.origin, self.user_id, channel_id, create_at, create_at, fetched_at),
            ).fetchone()
            if existing is None and newer_coverage is not None:
                continue
            values.append((self.origin, self.user_id, *cached, fetched_at))
        if not values:
            return
        self.database.executemany(
            """
            INSERT INTO posts_v3 (
                origin, user_id, post_id, channel_id, root_id,
                create_at, activity_at, payload, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (origin, user_id, post_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                root_id=excluded.root_id,
                create_at=excluded.create_at,
                activity_at=excluded.activity_at,
                payload=excluded.payload,
                fetched_at=excluded.fetched_at
            WHERE excluded.activity_at > posts_v3.activity_at
               OR (
                    excluded.activity_at = posts_v3.activity_at
                    AND excluded.fetched_at >= posts_v3.fetched_at
               )
            """,
            values,
        )

    def put_posts(self, posts: list[dict[str, Any]], fetched_at: int) -> None:
        try:
            self.database.execute("BEGIN IMMEDIATE")
            self._put_posts(posts, fetched_at)
            self.database.commit()
        except (MattermostError, ValueError, TypeError, sqlite3.Error) as exc:
            self.database.rollback()
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache write failed: {exc}") from exc

    def get_post(
        self, post_id: str, current_ms: int | None = None
    ) -> tuple[dict[str, Any], int] | None:
        checked_at = current_ms if current_ms is not None else int(time.time() * 1000)
        try:
            row = self.database.execute(
                """
                SELECT post_id, channel_id, root_id, create_at, activity_at,
                       payload, fetched_at FROM posts_v3
                WHERE origin=? AND user_id=? AND post_id=?
                """,
                (self.origin, self.user_id, post_id),
            ).fetchone()
            if row is None:
                return None
            return self._decoded_post(row, checked_at), int(row["fetched_at"])
        except (ValueError, TypeError, sqlite3.Error) as exc:
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache read failed: {exc}") from exc

    def posts_by_ids(
        self, post_ids: list[str], current_ms: int | None = None
    ) -> list[dict[str, Any]]:
        if not post_ids:
            return []
        checked_at = current_ms if current_ms is not None else int(time.time() * 1000)
        try:
            placeholders = ",".join("?" for _ in post_ids)
            rows = self.database.execute(
                f"""
                SELECT post_id, channel_id, root_id, create_at, activity_at,
                       payload, fetched_at FROM posts_v3
                WHERE origin=? AND user_id=? AND post_id IN ({placeholders})
                """,
                (self.origin, self.user_id, *post_ids),
            ).fetchall()
            found = {str(row["post_id"]): self._decoded_post(row, checked_at) for row in rows}
            return [found[post_id] for post_id in post_ids if post_id in found]
        except (ValueError, TypeError, sqlite3.Error) as exc:
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache read failed: {exc}") from exc

    def posts_between(
        self,
        channel_id: str,
        since_ms: int,
        until_ms: int,
        current_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        checked_at = current_ms if current_ms is not None else int(time.time() * 1000)
        try:
            rows = self.database.execute(
                """
                SELECT post_id, channel_id, root_id, create_at, activity_at,
                       payload, fetched_at FROM posts_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND create_at>=? AND create_at<?
                ORDER BY create_at, post_id
                """,
                (self.origin, self.user_id, channel_id, since_ms, until_ms),
            ).fetchall()
            return [self._decoded_post(row, checked_at) for row in rows]
        except (ValueError, TypeError, sqlite3.Error) as exc:
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache read failed: {exc}") from exc

    def coverage(
        self,
        channel_id: str,
        since_ms: int,
        until_ms: int,
        *,
        fetched_after: int | None,
        current_ms: int,
    ) -> tuple[bool, int | None]:
        try:
            query = """
                SELECT since_ms, until_ms, fetched_at FROM coverages_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND until_ms>? AND since_ms<?
            """
            parameters: list[object] = [
                self.origin,
                self.user_id,
                channel_id,
                since_ms,
                until_ms,
            ]
            if fetched_after is not None:
                query += " AND fetched_at>=?"
                parameters.append(fetched_after)
            query += " ORDER BY since_ms, until_ms"
            rows = self.database.execute(query, parameters).fetchall()
            covered_until = since_ms
            used_fetched_at: list[int] = []
            for row in rows:
                row_since = int(row["since_ms"])
                row_until = int(row["until_ms"])
                row_fetched_at = int(row["fetched_at"])
                if row_since >= row_until or row_fetched_at < 0 or row_fetched_at > current_ms:
                    raise CacheError("Mattermost cache contains invalid coverage")
                if row_since > covered_until:
                    return False, None
                if row_until > covered_until:
                    covered_until = row_until
                    used_fetched_at.append(row_fetched_at)
                if covered_until >= until_ms:
                    age = max(0, (current_ms - min(used_fetched_at)) // 1000)
                    return True, age
            return False, None
        except (ValueError, TypeError, sqlite3.Error) as exc:
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache coverage read failed: {exc}") from exc

    def replace_segment(
        self,
        channel_id: str,
        since_ms: int,
        until_ms: int,
        posts: list[dict[str, Any]],
        fetched_at: int,
    ) -> None:
        try:
            selected = [
                post
                for post in posts
                if post.get("channel_id") == channel_id
                and isinstance(post.get("create_at"), int)
                and since_ms <= post["create_at"] < until_ms
            ]
            self.database.execute("BEGIN IMMEDIATE")
            newer = self.database.execute(
                """
                SELECT 1 FROM coverages_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND until_ms>? AND since_ms<? AND fetched_at>=?
                LIMIT 1
                """,
                (
                    self.origin,
                    self.user_id,
                    channel_id,
                    since_ms,
                    until_ms,
                    fetched_at,
                ),
            ).fetchone()
            if newer is not None:
                self.database.rollback()
                return
            existing_rows = self.database.execute(
                """
                SELECT post_id, channel_id, root_id, create_at, activity_at,
                       payload, fetched_at FROM posts_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND create_at>=? AND create_at<?
                """,
                (self.origin, self.user_id, channel_id, since_ms, until_ms),
            ).fetchall()
            selected_by_id = {post["id"]: post for post in selected}
            checked_at = max(fetched_at, int(time.time() * 1000))
            for row in existing_rows:
                existing = self._decoded_post(row, checked_at)
                incoming = selected_by_id.get(existing["id"])
                if incoming is not None:
                    incoming_activity = self._cacheable_post(incoming)[4]
                    if int(row["activity_at"]) > incoming_activity:
                        selected_by_id[existing["id"]] = existing
            selected = list(selected_by_id.values())
            self.database.execute(
                """
                DELETE FROM coverages_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND until_ms>? AND since_ms<? AND fetched_at<=?
                """,
                (
                    self.origin,
                    self.user_id,
                    channel_id,
                    since_ms,
                    until_ms,
                    fetched_at,
                ),
            )
            self.database.execute(
                """
                DELETE FROM posts_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND create_at>=? AND create_at<? AND fetched_at<=?
                """,
                (
                    self.origin,
                    self.user_id,
                    channel_id,
                    since_ms,
                    until_ms,
                    fetched_at,
                ),
            )
            self._put_posts(selected, fetched_at)
            self.database.execute(
                """
                INSERT INTO coverages_v3 (
                    origin, user_id, channel_id, since_ms, until_ms, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.origin, self.user_id, channel_id, since_ms, until_ms, fetched_at),
            )
            self.database.commit()
        except (MattermostError, ValueError, TypeError, sqlite3.Error) as exc:
            self.database.rollback()
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache segment write failed: {exc}") from exc

    def invalidate_coverage(
        self, channel_id: str, since_ms: int, until_ms: int, fetched_at: int
    ) -> None:
        try:
            self.database.execute(
                """
                DELETE FROM coverages_v3
                WHERE origin=? AND user_id=? AND channel_id=?
                  AND until_ms>? AND since_ms<? AND fetched_at<=?
                """,
                (
                    self.origin,
                    self.user_id,
                    channel_id,
                    since_ms,
                    until_ms,
                    fetched_at,
                ),
            )
            self.database.commit()
        except sqlite3.Error as exc:
            self.database.rollback()
            raise CacheError(f"Mattermost cache invalidation failed: {exc}") from exc

    def get_thread(
        self, root_id: str, fetched_after: int, current_ms: int
    ) -> tuple[list[dict[str, Any]], int] | None:
        try:
            row = self.database.execute(
                """
                SELECT post_ids, fetched_at, complete FROM threads_v3
                WHERE origin=? AND user_id=? AND root_id=?
                """,
                (self.origin, self.user_id, root_id),
            ).fetchone()
            if row is None or not bool(row["complete"]) or int(row["fetched_at"]) < fetched_after:
                return None
            if int(row["fetched_at"]) > current_ms:
                raise CacheError("Mattermost cache contains a future thread snapshot")
            post_ids = json.loads(row["post_ids"])
            if (
                not isinstance(post_ids, list)
                or len(post_ids) != len(set(post_ids))
                or not all(
                    isinstance(item, str) and IDENTIFIER.fullmatch(item) for item in post_ids
                )
            ):
                raise CacheError("Mattermost cache contains an invalid thread snapshot")
            posts = self.posts_by_ids(post_ids, current_ms)
            if len(posts) != len(post_ids):
                return None
            age = max(0, (current_ms - int(row["fetched_at"])) // 1000)
            return posts, age
        except (ValueError, TypeError, sqlite3.Error) as exc:
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache thread read failed: {exc}") from exc

    def put_thread(
        self,
        root_id: str,
        posts: list[dict[str, Any]],
        fetched_at: int,
        *,
        complete: bool,
    ) -> None:
        try:
            self.database.execute("BEGIN IMMEDIATE")
            self._put_posts(posts, fetched_at)
            self.database.execute(
                """
                INSERT INTO threads_v3 (
                    origin, user_id, root_id, post_ids, fetched_at, complete
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (origin, user_id, root_id) DO UPDATE SET
                    post_ids=excluded.post_ids,
                    fetched_at=excluded.fetched_at,
                    complete=excluded.complete
                WHERE excluded.fetched_at>=threads_v3.fetched_at
                """,
                (
                    self.origin,
                    self.user_id,
                    root_id,
                    json.dumps([post["id"] for post in posts], separators=(",", ":")),
                    fetched_at,
                    int(complete),
                ),
            )
            self.database.commit()
        except (MattermostError, ValueError, TypeError, sqlite3.Error) as exc:
            self.database.rollback()
            if isinstance(exc, CacheError):
                raise
            raise CacheError(f"Mattermost cache thread write failed: {exc}") from exc

    def status(self) -> dict[str, object]:
        try:
            counts = {
                name: int(self.database.execute(f"SELECT COUNT(*) FROM {name}_v3").fetchone()[0])
                for name in ("posts", "threads", "coverages")
            }
            return {
                "status": "ok",
                "cache": str(self.path),
                "exists": True,
                "schema_version": CACHE_SCHEMA_VERSION,
                "ttl_seconds": CACHE_TTL_SECONDS,
                "stable_age_seconds": CACHE_STABLE_AGE_SECONDS,
                "counts": counts,
                "external_mutations": False,
            }
        except sqlite3.Error as exc:
            raise CacheError(f"Mattermost cache status failed: {exc}") from exc


def valid_posts(value: object) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise MattermostError("Mattermost post response is incomplete")
    posts: list[dict[str, Any]] = []
    malformed = False
    seen_ids: set[str] = set()
    for post in value["posts"].values():
        if (
            not isinstance(post, dict)
            or not isinstance(post.get("id"), str)
            or not IDENTIFIER.fullmatch(post["id"])
            or not isinstance(post.get("channel_id"), str)
            or not IDENTIFIER.fullmatch(post["channel_id"])
            or not isinstance(post.get("create_at"), int)
            or post["create_at"] <= 0
            or (
                bool(post.get("root_id"))
                and (
                    not isinstance(post.get("root_id"), str)
                    or not IDENTIFIER.fullmatch(post["root_id"])
                )
            )
        ):
            malformed = True
            continue
        if post["id"] in seen_ids:
            malformed = True
            continue
        seen_ids.add(post["id"])
        posts.append(post)
    return sorted(posts, key=lambda post: (post["create_at"], post["id"])), malformed


def thread_response_posts(value: object) -> tuple[list[dict[str, Any]], bool]:
    posts, malformed = valid_posts(value)
    if not isinstance(value, dict) or "order" not in value:
        return posts, malformed
    order = value.get("order")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        return posts, True
    post_ids = {post["id"] for post in posts}
    ordered_ids = set(order)
    return (
        posts,
        malformed
        or len(order) != len(set(order))
        or any(post_id not in post_ids for post_id in order)
        or any(post_id not in ordered_ids for post_id in post_ids),
    )


def safe_post(post: dict[str, Any], *, include_reactions: bool = True) -> dict[str, Any]:
    """Keep message fields and exact reaction identity, never attachment files."""
    result = {key: value for key, value in post.items() if key not in {"attachments", "reactions"}}
    if not include_reactions:
        return result
    reactions = post.get("reactions", [])
    if isinstance(reactions, list):
        result["reactions"] = [
            {"emoji": item["emoji_name"], "user": item["user_id"]}
            for item in reactions
            if isinstance(item, dict)
            and isinstance(item.get("emoji_name"), str)
            and isinstance(item.get("user_id"), str)
        ]
    return result


def read_reactions(
    client: Client, posts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], bool, list[dict[str, object]]]:
    result: list[dict[str, Any]] = []
    errors: list[dict[str, object]] = []
    complete = True
    for post in posts:
        clean = safe_post(post)
        try:
            value = client.get(
                f"/posts/{urllib.parse.quote(identifier(post['id'], 'post ID'), safe='')}/reactions"
            )
            if not isinstance(value, list):
                raise MattermostError("Mattermost reaction response is malformed")
            clean["reactions"] = [
                {"emoji": item["emoji_name"], "user": item["user_id"]}
                for item in value
                if isinstance(item, dict)
                and isinstance(item.get("emoji_name"), str)
                and isinstance(item.get("user_id"), str)
            ]
        except AuthorizationRequired:
            raise
        except MattermostError:
            complete = False
            errors.append(
                error_item(
                    "reactions_unavailable",
                    "Mattermost reactions could not be fully read",
                    retryable=True,
                )
            )
            clean["reactions"] = []
        result.append(clean)
    return result, complete, errors


def without_reactions(
    posts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool, list[dict[str, object]]]:
    return [safe_post(post, include_reactions=False) for post in posts], True, []


def enrich_posts(
    client: Client, posts: list[dict[str, Any]], *, include_reactions: bool
) -> tuple[list[dict[str, Any]], bool, list[dict[str, object]]]:
    if include_reactions:
        return read_reactions(client, posts)
    return without_reactions(posts)


def warning(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message}


def result_list(result: dict[str, object], key: str) -> list[object]:
    value = result.get(key)
    return value if isinstance(value, list) else []


def scoped_thread_posts(
    posts: list[dict[str, Any]], root_id: str, selected_id: str, channel_id: str
) -> tuple[list[dict[str, Any]], bool]:
    scoped: list[dict[str, Any]] = []
    malformed = False
    root_seen = False
    selected_seen = False
    for post in posts:
        post_id = post["id"]
        if post["channel_id"] != channel_id:
            malformed = True
            continue
        if post_id == root_id:
            if post.get("root_id"):
                malformed = True
                continue
            root_seen = True
        elif post.get("root_id") != root_id:
            malformed = True
            continue
        selected_seen = selected_seen or post_id == selected_id
        scoped.append(post)
    return (
        sorted(scoped, key=lambda item: (item["create_at"], item["id"])),
        malformed or not root_seen or not selected_seen,
    )


def read_post(
    client: Client,
    post: dict[str, Any],
    cache: CacheStore | None,
    *,
    read_cache: bool,
    write_cache: bool,
    current_ms: int,
) -> tuple[
    list[dict[str, Any]],
    bool,
    list[dict[str, object]],
    list[dict[str, object]],
    bool,
    int | None,
]:
    root_id = post.get("root_id") or post["id"]
    root_id = identifier(root_id, "root post ID")
    if cache is not None and read_cache:
        cached = cache.get_thread(
            root_id,
            current_ms - CACHE_TTL_SECONDS * 1000,
            current_ms,
        )
        if cached is not None:
            posts, age = cached
            posts, malformed = scoped_thread_posts(posts, root_id, post["id"], post["channel_id"])
            if malformed:
                raise CacheError("Mattermost cache contains an invalid thread snapshot")
            posts = [post if item["id"] == post["id"] else item for item in posts]
            if write_cache:
                cache.put_posts([post], current_ms)
            return posts, True, [], [], True, age
    try:
        thread = client.get(f"/posts/{urllib.parse.quote(root_id, safe='')}/thread")
        posts, malformed = thread_response_posts(thread)
        posts, scope_malformed = scoped_thread_posts(posts, root_id, post["id"], post["channel_id"])
        malformed = malformed or scope_malformed
        if not any(item.get("id") == post["id"] for item in posts):
            posts.append(post)
            posts.sort(key=lambda item: (item["create_at"], item["id"]))
            malformed = True
        errors = (
            [
                error_item(
                    "malformed_thread", "Mattermost thread response omitted or malformed posts"
                )
            ]
            if malformed
            else []
        )
        if cache is not None and write_cache:
            cache.put_thread(root_id, posts, current_ms, complete=not malformed)
        return posts, not malformed, errors, [], False, None
    except AuthorizationRequired:
        raise
    except MattermostError as exc:
        if isinstance(exc, CacheError):
            raise
        if cache is not None and write_cache:
            cache.put_thread(root_id, [post], current_ms, complete=False)
        return (
            [post],
            False,
            [
                error_item(
                    "thread_unavailable",
                    "Mattermost thread could not be fully read",
                    retryable=True,
                )
            ],
            [warning("thread_unavailable", str(exc))],
            False,
            None,
        )


def in_period(post: dict[str, Any], since_ms: int, until_ms: int) -> bool:
    created = post.get("create_at")
    return isinstance(created, int) and since_ms <= created < until_ms


def channel_post_page(
    value: object,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], bool]:
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise MattermostError("Mattermost post page is incomplete")
    posts, malformed = valid_posts(value)
    by_id = {post["id"]: post for post in posts}
    order = value.get("order")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise MattermostError("Mattermost post page order is incomplete")
    clean_order = [item for item in order if IDENTIFIER.fullmatch(item)]
    malformed = malformed or len(clean_order) != len(order)
    malformed = malformed or len(clean_order) != len(set(clean_order))
    malformed = malformed or bool(posts) and not clean_order
    missing = [post_id for post_id in clean_order if post_id not in by_id]
    malformed = malformed or bool(missing)
    ordered = [by_id[post_id] for post_id in clean_order if post_id in by_id]
    return posts, ordered, clean_order, malformed


def read_channel(
    client: Client, channel: dict[str, Any], since_ms: int, until_ms: int
) -> tuple[list[dict[str, Any]], bool, int, list[dict[str, object]], list[dict[str, object]]]:
    channel_id = identifier(channel.get("id"), "channel ID")
    items: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    used_cursors: set[str] = set()
    complete = True
    pages = 0
    before: str | None = None
    filtered_after_until = 0
    for _page in range(MAX_PAGES):
        query = {
            "page": "0",
            "per_page": str(PAGE_SIZE),
            "skipFetchThreads": "false",
            "collapsedThreads": "false",
        }
        if before is not None:
            query["before"] = before
        try:
            value = client.get(
                f"/channels/{urllib.parse.quote(channel_id, safe='')}/posts?"
                f"{urllib.parse.urlencode(query)}"
            )
            posts, ordered, order, malformed = channel_post_page(value)
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            errors.append(
                error_item(
                    "page_unavailable", "Mattermost post page could not be read", retryable=True
                )
            )
            warnings.append(warning("page_unavailable", str(exc)))
            break
        pages += 1
        cross_channel = [post for post in posts if post["channel_id"] != channel_id]
        if cross_channel:
            posts = [post for post in posts if post["channel_id"] == channel_id]
            malformed = True
        if malformed:
            complete = False
            errors.append(
                error_item("malformed_page", "Mattermost post page contained malformed posts")
            )
        for post in posts:
            if in_period(post, since_ms, until_ms):
                items[post["id"]] = post
            elif post["create_at"] >= until_ms:
                filtered_after_until += 1
        page_times = [post["create_at"] for post in ordered]
        if not page_times or min(page_times) < since_ms or len(order) < PAGE_SIZE:
            break
        cursor = order[-1]
        if cursor in used_cursors:
            complete = False
            errors.append(error_item("repeated_page", "Mattermost returned a repeated post cursor"))
            break
        used_cursors.add(cursor)
        before = cursor
    else:
        complete = False
        errors.append(error_item("pagination_limit", "Mattermost post pagination limit reached"))
    if filtered_after_until:
        warnings.append(
            warning(
                "posts_after_until_filtered",
                f"Mattermost returned {filtered_after_until} posts after the upper bound; they were excluded",
            )
        )
    return (
        sorted(items.values(), key=lambda item: (item["create_at"], item["id"])),
        complete,
        pages,
        errors,
        warnings,
    )


def cached_channel_posts(
    client: Client,
    channel: dict[str, Any],
    since_ms: int,
    until_ms: int,
    cache: CacheStore | None,
    *,
    read_cache: bool,
    write_cache: bool,
    current_ms: int,
) -> tuple[
    list[dict[str, Any]],
    bool,
    int,
    list[dict[str, object]],
    list[dict[str, object]],
    bool,
    int | None,
    int,
    int,
]:
    channel_id = identifier(channel.get("id"), "channel ID")
    segments: list[tuple[int, int, bool]]
    if cache is None or not read_cache:
        segments = [(since_ms, until_ms, False)]
    else:
        stable_until = min(until_ms, current_ms - CACHE_STABLE_AGE_SECONDS * 1000)
        segments = []
        if since_ms < stable_until:
            segments.append((since_ms, stable_until, True))
        recent_since = max(since_ms, stable_until)
        if recent_since < until_ms:
            segments.append((recent_since, until_ms, False))

    selected: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    complete = True
    pages = 0
    cache_hit = False
    cache_ages: list[int] = []
    cached_ids: set[str] = set()
    fetched_ids: set[str] = set()

    for segment_since, segment_until, stable in segments:
        covered = False
        age: int | None = None
        if cache is not None and read_cache:
            covered, age = cache.coverage(
                channel_id,
                segment_since,
                segment_until,
                fetched_after=(None if stable else current_ms - CACHE_TTL_SECONDS * 1000),
                current_ms=current_ms,
            )
        if covered and cache is not None:
            cached = cache.posts_between(channel_id, segment_since, segment_until, current_ms)
            for post in cached:
                selected[post["id"]] = post
                cached_ids.add(post["id"])
            cache_hit = True
            if age is not None:
                cache_ages.append(age)
            continue

        if cache is not None and write_cache and not read_cache:
            cache.invalidate_coverage(channel_id, segment_since, segment_until, current_ms)
        posts, segment_complete, segment_pages, segment_errors, segment_warnings = read_channel(
            client,
            channel,
            segment_since,
            segment_until,
        )
        complete = complete and segment_complete
        pages += segment_pages
        errors.extend(segment_errors)
        warnings.extend(segment_warnings)
        for post in posts:
            selected[post["id"]] = post
            fetched_ids.add(post["id"])
        if cache is not None and write_cache:
            if segment_complete:
                cache.replace_segment(
                    channel_id,
                    segment_since,
                    segment_until,
                    posts,
                    current_ms,
                )
            else:
                cache.put_posts(posts, current_ms)

    return (
        sorted(selected.values(), key=lambda item: (item["create_at"], item["id"])),
        complete,
        pages,
        errors,
        warnings,
        cache_hit,
        max(cache_ages) if cache_ages else None,
        len(cached_ids),
        len(fetched_ids),
    )


def add_context_roots(
    client: Client,
    posts: list[dict[str, Any]],
    since_ms: int,
    until_ms: int,
    cache: CacheStore | None,
    *,
    read_cache: bool,
    write_cache: bool,
    current_ms: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, object]],
    int,
    int,
    int | None,
    int,
    bool,
]:
    selected_ids = {post["id"] for post in posts}
    expected_channels = {
        post["root_id"]: post["channel_id"]
        for post in posts
        if isinstance(post.get("root_id"), str) and post["root_id"]
    }
    root_ids = sorted(
        {
            post["root_id"]
            for post in posts
            if isinstance(post.get("root_id"), str)
            and post["root_id"]
            and post["root_id"] not in selected_ids
        }
    )
    earliest_replies = {
        root_id: min(
            post["create_at"]
            for post in posts
            if post.get("root_id") == root_id and isinstance(post.get("create_at"), int)
        )
        for root_id in root_ids
    }
    roots: list[dict[str, Any]] = []
    warnings: list[dict[str, object]] = []
    cached_roots = 0
    fetched_roots = 0
    cache_ages: list[int] = []
    context_ids: set[str] = set()
    roots_complete = True
    for root_id in root_ids:
        root: dict[str, Any] | None = None
        root_from_cache = False
        root_cache_age: int | None = None
        if cache is not None and read_cache:
            cached = cache.get_post(root_id, current_ms)
            if cached is not None:
                candidate, fetched_at = cached
                activity = max(
                    value
                    for key in ("create_at", "update_at", "edit_at", "delete_at")
                    if isinstance((value := candidate.get(key)), int)
                )
                if (
                    (
                        activity <= current_ms - CACHE_STABLE_AGE_SECONDS * 1000
                        or fetched_at >= current_ms - CACHE_TTL_SECONDS * 1000
                    )
                    and candidate.get("channel_id") == expected_channels[root_id]
                    and not candidate.get("root_id")
                ):
                    root = candidate
                    root_from_cache = True
                    root_cache_age = max(0, (current_ms - fetched_at) // 1000)
        if root is None:
            try:
                value = client.get(f"/posts/{urllib.parse.quote(root_id, safe='')}")
            except AuthorizationRequired:
                raise
            except MattermostError as exc:
                if isinstance(exc, CacheError):
                    raise
                warnings.append(
                    warning(
                        "context_root_unavailable",
                        f"Mattermost root post {root_id} could not be read: {exc}",
                    )
                )
                continue
            if (
                not isinstance(value, dict)
                or value.get("id") != root_id
                or not isinstance(value.get("create_at"), int)
                or value["create_at"] <= 0
                or not isinstance(value.get("channel_id"), str)
                or value["channel_id"] != expected_channels[root_id]
                or bool(value.get("root_id"))
            ):
                roots_complete = False
                warnings.append(
                    warning(
                        "malformed_context_root",
                        f"Mattermost root post {root_id} response is incomplete",
                    )
                )
                continue
            root = value
        if root["create_at"] > earliest_replies[root_id] or root["create_at"] >= until_ms:
            roots_complete = False
            warnings.append(
                warning(
                    "malformed_context_root",
                    f"Mattermost root post {root_id} is not older than its in-period reply",
                )
            )
            continue
        if root_from_cache:
            cached_roots += 1
            if root_cache_age is not None:
                cache_ages.append(root_cache_age)
        else:
            fetched_roots += 1
            if cache is not None and write_cache:
                cache.put_posts([root], current_ms)
        if root["create_at"] >= since_ms:
            roots_complete = False
            warnings.append(
                warning(
                    "in_period_root_recovered",
                    f"Mattermost root post {root_id} was recovered outside channel pagination",
                )
            )
        else:
            context_ids.add(root_id)
        roots.append(root)
    combined = [*posts, *roots]
    combined.sort(key=lambda item: (item["create_at"], item["id"]))
    for post in combined:
        post["context_only"] = post["id"] in context_ids
    return (
        combined,
        warnings,
        cached_roots,
        fetched_roots,
        max(cache_ages) if cache_ages else None,
        len(context_ids),
        roots_complete,
    )


def finalize_result(result: dict[str, object]) -> dict[str, object]:
    complete = bool(result["complete"])
    posts = result.get("posts", [])
    members = result.get("members", [])
    counts = result.get("counts")
    base_counts = counts if isinstance(counts, dict) else {}
    if isinstance(posts, list):
        result["counts"] = {
            **base_counts,
            "posts": len(posts),
            "threads": len(
                {post.get("root_id") or post.get("id") for post in posts if isinstance(post, dict)}
            ),
        }
    if "members" in result and isinstance(members, list):
        result["counts"] = {**base_counts, "resolved": len(members)}
    if result.get("scope") == "members" and not members and complete:
        result["complete"] = False
        result["errors"] = [
            *result_list(result, "errors"),
            error_item("no_data", "Mattermost channel returned no members"),
        ]
        complete = False
    if not posts and not members and not complete and not result["errors"]:
        result["errors"] = [error_item("no_data", "Mattermost did not return safe data")]
    result["status"] = "ok" if complete else "partial"
    if not posts and not members and result["errors"]:
        result["status"] = "error"
    return result


def read_one(
    url: str,
    since: str | None,
    until: str | None,
    read_cache: bool,
    write_cache: bool,
    *,
    include_reactions: bool = True,
) -> dict[str, object]:
    target = classify_url(url)
    period = parse_period(since, until, allowed=target["kind"] != "post")
    token = read_token(str(target["origin"]))
    client = Client(str(target["origin"]), token)
    user_id = user_identity(client)
    access_post, access_channel = revalidate_access(client, target, user_id)
    current_ms = int(time.time() * 1000)
    cache = CacheStore(str(target["origin"]), user_id) if read_cache or write_cache else None
    try:
        result = result_base(
            scope=str(target["kind"]), target=normalized_target(target), period=period
        )
        result["access_revalidated"] = True
        if target["kind"] == "post":
            assert access_post is not None
            posts, complete, errors, warnings, cache_hit, cache_age = read_post(
                client,
                access_post,
                cache,
                read_cache=read_cache,
                write_cache=write_cache,
                current_ms=current_ms,
            )
            posts, reactions_complete, reaction_errors = enrich_posts(
                client, posts, include_reactions=include_reactions
            )
            complete = complete and reactions_complete
            errors.extend(reaction_errors)
            result.update(
                {
                    "posts": posts,
                    "complete": complete,
                    "errors": errors,
                    "warnings": warnings,
                    "pages": {"posts": 0 if cache_hit else 1, "members": 0},
                    "cache_hit": cache_hit,
                    "cache_age": cache_age,
                }
            )
        else:
            assert access_channel is not None and period is not None
            since_ms, until_ms = period_bounds(period, current_ms)
            (
                posts,
                complete,
                pages,
                errors,
                warnings,
                cache_hit,
                cache_age,
                cached_posts,
                fetched_posts,
            ) = cached_channel_posts(
                client,
                access_channel,
                since_ms,
                until_ms,
                cache,
                read_cache=read_cache,
                write_cache=write_cache,
                current_ms=current_ms,
            )
            (
                posts,
                root_warnings,
                cached_roots,
                fetched_roots,
                root_cache_age,
                context_roots,
                roots_complete,
            ) = add_context_roots(
                client,
                posts,
                since_ms,
                until_ms,
                cache,
                read_cache=read_cache,
                write_cache=write_cache,
                current_ms=current_ms,
            )
            warnings.extend(root_warnings)
            complete = complete and roots_complete
            if not roots_complete and cache is not None and write_cache:
                cache.invalidate_coverage(str(access_channel["id"]), since_ms, until_ms, current_ms)
            cache_hit = cache_hit or cached_roots > 0
            ages = [age for age in (cache_age, root_cache_age) if age is not None]
            posts, reactions_complete, reaction_errors = enrich_posts(
                client, posts, include_reactions=include_reactions
            )
            complete = complete and reactions_complete
            errors.extend(reaction_errors)
            result.update(
                {
                    "scope": "chat" if access_channel.get("type") in {"D", "G"} else "channel",
                    "posts": posts,
                    "channel": {"id": access_channel["id"], "name": access_channel.get("name")},
                    "complete": complete,
                    "errors": errors,
                    "warnings": warnings,
                    "pages": {"posts": pages, "members": 0},
                    "counts": {
                        "posts": 0,
                        "threads": 0,
                        "members": 0,
                        "resolved": 0,
                        "context_roots": context_roots,
                        "cached_posts": cached_posts + cached_roots,
                        "fetched_posts": fetched_posts + fetched_roots,
                    },
                    "cache_hit": cache_hit,
                    "cache_age": max(ages) if ages else None,
                }
            )
        return finalize_result(result)
    finally:
        if cache is not None:
            cache.close()


def collect_members(url: str) -> dict[str, object]:
    target = classify_url(url)
    if target["kind"] == "post":
        raise MattermostError("members requires a channel, direct, or group chat URL")
    token = read_token(str(target["origin"]))
    client = Client(str(target["origin"]), token)
    user_id = user_identity(client)
    _, channel = revalidate_access(client, target, user_id)
    assert channel is not None
    channel_id = identifier(channel.get("id"), "channel ID")
    result = result_base(scope="members", target=normalized_target(target), period=None)
    result["access_revalidated"] = True
    result["channel"] = {"id": channel_id, "name": channel.get("name")}
    member_ids: list[str] = []
    seen: set[str] = set()
    signatures: set[tuple[str, ...]] = set()
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    complete = True
    pages = 0
    for page in range(MAX_PAGES):
        try:
            page_value = client.get(
                f"/channels/{urllib.parse.quote(channel_id, safe='')}/members?page={page}&per_page={PAGE_SIZE}"
            )
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            errors.append(
                error_item(
                    "member_page_unavailable",
                    "Mattermost member page could not be read",
                    retryable=True,
                )
            )
            warnings.append(warning("member_page_unavailable", str(exc)))
            break
        pages += 1
        if not isinstance(page_value, list):
            complete = False
            errors.append(
                error_item("malformed_member_page", "Mattermost member page is malformed")
            )
            break
        page_ids: list[str] = []
        malformed = False
        for item in page_value:
            value = item.get("user_id") if isinstance(item, dict) else None
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
                malformed = True
                continue
            page_ids.append(value)
            if value not in seen:
                seen.add(value)
                member_ids.append(value)
        signature = tuple(sorted(page_ids))
        if signature in signatures and page_ids:
            complete = False
            errors.append(
                error_item("repeated_member_page", "Mattermost returned a repeated member page")
            )
            break
        signatures.add(signature)
        if malformed:
            complete = False
            errors.append(
                error_item(
                    "malformed_member_page", "Mattermost member page contained malformed members"
                )
            )
        if len(page_value) < PAGE_SIZE:
            break
    else:
        complete = False
        errors.append(
            error_item("member_pagination_limit", "Mattermost member pagination limit reached")
        )
    members: list[dict[str, str]] = []
    unresolved: list[str] = []
    for user_id in member_ids:
        try:
            profile = client.get(f"/users/{urllib.parse.quote(user_id, safe='')}")
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            unresolved.append(user_id)
            errors.append(
                error_item(
                    "profile_unavailable",
                    "Mattermost member profile could not be read",
                    retryable=True,
                )
            )
            warnings.append(warning("profile_unavailable", str(exc)))
            continue
        if not isinstance(profile, dict) or not isinstance(profile.get("username"), str):
            complete = False
            unresolved.append(user_id)
            errors.append(error_item("malformed_profile", "Mattermost member profile is malformed"))
            continue
        members.append(
            {
                "id": user_id,
                "username": profile["username"],
                "display_name": str(
                    profile.get("nickname") or profile.get("first_name") or profile["username"]
                ),
            }
        )
    result.update(
        {
            "members": members,
            "complete": complete,
            "errors": errors,
            "warnings": warnings,
            "unresolved_ids": unresolved,
            "pages": {"posts": 0, "members": pages},
            "counts": {
                "posts": 0,
                "threads": 0,
                "members": len(member_ids),
                "resolved": len(members),
            },
        }
    )
    return finalize_result(result)


def receipt_root() -> Path:
    return private_directory(private_directory(config_root()) / "receipts")


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def receipt_path(digest: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise MattermostError("confirmation digest is invalid")
    return receipt_root() / f"{digest}.json"


def prepare_receipt(
    action: str, *, origin: str | None = None, path: Path | None = None
) -> dict[str, object]:
    content = {
        "schema_version": SCHEMA_VERSION,
        "action": action,
        "origin": origin,
        "path": str(path) if path else None,
        "expires_at": now() + RECEIPT_TTL_SECONDS,
        "nonce": secrets.token_hex(16),
    }
    digest = hashlib.sha256(canonical(content)).hexdigest()
    receipt = {**content, "digest": digest, "used": False}
    destination = receipt_path(digest)
    destination.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    destination.chmod(0o600)
    apply_command = (
        f"mattermost.py auth apply <HTTPS-URL> --confirm {digest}"
        if action == "auth"
        else f"mattermost.py cache clear --confirm {digest}"
    )
    return {
        "status": "prepared",
        "action": action,
        "origin": origin,
        "path": str(path) if path else None,
        "digest": digest,
        "expires_at": content["expires_at"],
        "apply_command": apply_command,
        "external_mutations": False,
    }


def consume_receipt(
    digest: str, action: str, *, origin: str | None = None, path: Path | None = None
) -> None:
    destination = receipt_path(digest)
    try:
        private_file(destination)
        receipt = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, MattermostError) as exc:
        raise MattermostError("confirmation receipt is unavailable") from exc
    content = {
        key: receipt.get(key)
        for key in ("schema_version", "action", "origin", "path", "expires_at", "nonce")
    }
    expires_at = content["expires_at"]
    if (
        receipt.get("digest") != digest
        or not isinstance(receipt.get("used"), bool)
        or not isinstance(expires_at, int)
        or not isinstance(content["nonce"], str)
        or hashlib.sha256(canonical(content)).hexdigest() != digest
        or receipt["used"]
        or expires_at <= now()
        or content["action"] != action
        or content["origin"] != origin
        or content["path"] != (str(path) if path else None)
    ):
        raise MattermostError(
            "confirmation receipt is stale, tampered, replayed, or does not match"
        )
    receipt["used"] = True
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.tmp")
    temporary.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, destination)


def browser_cookies(value: object) -> list[dict[str, Any]]:
    candidate = value
    if isinstance(candidate, dict):
        if "success" in candidate and candidate.get("success") is not True:
            raise MattermostError("browser cookie adapter reported failure")
        candidate = candidate.get("cookies", candidate.get("data"))
    if isinstance(candidate, dict):
        if "success" in candidate and candidate.get("success") is not True:
            raise MattermostError("browser cookie adapter reported failure")
        candidate = candidate.get("cookies")
    if not isinstance(candidate, list):
        raise MattermostError("browser cookie input does not contain a cookie array")
    return [item for item in candidate if isinstance(item, dict)]


def cookie_matches_host(cookie: dict[str, Any], hostname: str) -> bool:
    raw_domain = str(cookie.get("domain") or "").lower()
    domain = raw_domain.lstrip(".")
    return bool(domain) and (
        hostname == domain or (raw_domain.startswith(".") and hostname.endswith(f".{domain}"))
    )


def cookie_expiry(cookie: dict[str, Any]) -> int | None:
    value = cookie.get("expires")
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def cookie_is_current(cookie: dict[str, Any]) -> bool:
    expires = cookie_expiry(cookie)
    return expires is not None and (expires <= 0 or expires > now())


def token_from_cookies(origin: str, value: object) -> str:
    hostname = urllib.parse.urlsplit(normalized_origin(origin)).hostname
    if hostname is None:
        raise MattermostError("Mattermost origin does not contain a hostname")
    matches = [
        cookie
        for cookie in browser_cookies(value)
        if cookie.get("name") == "MMAUTHTOKEN"
        and isinstance(cookie.get("value"), str)
        and cookie["value"]
        and "\n" not in cookie["value"]
        and "\r" not in cookie["value"]
        and cookie_matches_host(cookie, hostname)
        and cookie_is_current(cookie)
    ]
    matches.sort(
        key=lambda cookie: (
            str(cookie.get("domain") or "").lower().lstrip(".") == hostname,
            len(str(cookie.get("domain") or "")),
            cookie_expiry(cookie) or 0,
        ),
        reverse=True,
    )
    if matches:
        return str(matches[0]["value"])
    raise MattermostError("browser did not provide an origin-bound session cookie")


def cookie_token(origin: str) -> str:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise MattermostError("browser cookie input must be JSON") from exc
    return token_from_cookies(origin, value)


def agent_browser_token(origin: str) -> str:
    """Use the explicitly consented host adapter without exposing credentials."""
    try:
        opened = subprocess.run(
            ["agent-browser", "open", origin],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        if opened.returncode != 0:
            raise MattermostError("agent-browser could not open the exact origin")
        cookies = subprocess.run(
            ["agent-browser", "cookies", "--json"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        if cookies.returncode != 0:
            raise MattermostError("agent-browser could not read browser cookies")
        values = json.loads(cookies.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise MattermostError("agent-browser authentication failed") from exc
    return token_from_cookies(origin, values)


def main(argv: list[str] | None = None) -> int:
    parser = ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    read = subparsers.add_parser("read")
    read.add_argument("url")
    read.add_argument("--since")
    read.add_argument("--until")
    read.add_argument("--refresh", action="store_true")
    read.add_argument("--no-cache", action="store_true")
    read.add_argument("--no-reactions", action="store_true")
    many = subparsers.add_parser("read-many")
    many.add_argument("urls", nargs="+")
    many.add_argument("--since")
    many.add_argument("--until")
    many.add_argument("--refresh", action="store_true")
    many.add_argument("--no-cache", action="store_true")
    many.add_argument("--no-reactions", action="store_true")
    members = subparsers.add_parser("members")
    members.add_argument("url")
    auth = subparsers.add_parser("auth")
    auth_subparsers = auth.add_subparsers(
        dest="auth_action", required=True, parser_class=ContractArgumentParser
    )
    auth_preview = auth_subparsers.add_parser("preview")
    auth_preview.add_argument("url")
    auth_apply = auth_subparsers.add_parser("apply")
    auth_apply.add_argument("url")
    auth_apply.add_argument("--confirm", required=True)
    auth_apply.add_argument("--browser-consent", action="store_true")
    cache = subparsers.add_parser("cache")
    cache_subparsers = cache.add_subparsers(
        dest="cache_action", required=True, parser_class=ContractArgumentParser
    )
    cache_subparsers.add_parser("status")
    clear = cache_subparsers.add_parser("clear")
    clear.add_argument("--confirm")
    try:
        args = parser.parse_args(argv)
        if args.capabilities:
            emit(
                {
                    "schema_version": 1,
                    "payload_version": "2.1.0",
                    "mutation": "private-confirmed-only",
                    "dry_run": True,
                    "state_protocol": "origin-identity-segmented-history-cache",
                    "external_tools": {"browser_auth": True},
                    "destructive_flags": ["auth apply --confirm", "cache clear --confirm"],
                    "external_mutations": False,
                }
            )
            return 0
        if args.command == "auth":
            origin = normalized_origin(args.url)
            if args.auth_action == "preview":
                emit(prepare_receipt("auth", origin=origin))
                return 0
            token = agent_browser_token(origin) if args.browser_consent else cookie_token(origin)
            consume_receipt(args.confirm, "auth", origin=origin)
            save_token(origin, token)
            emit({"status": "ok", "origin": origin, "external_mutations": False})
            return 0
        if args.command == "cache":
            path = cache_path()
            if args.cache_action == "status":
                if path.is_symlink():
                    raise CacheError("Mattermost cache path is a symbolic link")
                exists = path.exists() and not path.is_symlink()
                if not exists:
                    emit(
                        {
                            "status": "ok",
                            "cache": str(path),
                            "exists": False,
                            "schema_version": CACHE_SCHEMA_VERSION,
                            "ttl_seconds": CACHE_TTL_SECONDS,
                            "stable_age_seconds": CACHE_STABLE_AGE_SECONDS,
                            "counts": {"posts": 0, "threads": 0, "coverages": 0},
                            "external_mutations": False,
                        }
                    )
                    return 0
                with CacheStore() as store:
                    emit(store.status())
                return 0
            if not args.confirm:
                emit(prepare_receipt("cache-clear", path=path))
                return 0
            consume_receipt(args.confirm, "cache-clear", path=path)
            for candidate in (
                path,
                Path(f"{path}-journal"),
                Path(f"{path}-wal"),
                Path(f"{path}-shm"),
            ):
                if candidate.exists() or candidate.is_symlink():
                    try:
                        private_file(candidate)
                        candidate.unlink()
                    except (MattermostError, OSError) as exc:
                        raise CacheError(
                            f"Mattermost cache could not be cleared safely: {exc}"
                        ) from exc
            emit(
                {
                    "status": "ok",
                    "cache": str(path),
                    "exists": path.exists(),
                    "external_mutations": False,
                }
            )
            return 0
        if args.command in {"read", "read-many"}:
            if args.refresh and args.no_cache:
                raise MattermostError("--refresh and --no-cache cannot be combined")
            read_cache, write_cache = (not args.no_cache and not args.refresh), not args.no_cache
            if args.command == "read":
                target = classify_url(args.url)
                result = read_one(
                    args.url,
                    args.since
                    if args.since is not None
                    else (None if target["kind"] == "post" else default_since()),
                    args.until,
                    read_cache,
                    write_cache,
                    include_reactions=not args.no_reactions,
                )
                emit(result)
                return 0 if result["status"] == "ok" else 1 if result["status"] == "partial" else 2
            results: list[dict[str, object]] = []
            for url in dict.fromkeys(args.urls):
                try:
                    target = classify_url(url)
                    results.append(
                        read_one(
                            url,
                            args.since
                            if args.since is not None
                            else (None if target["kind"] == "post" else default_since()),
                            args.until,
                            read_cache,
                            write_cache,
                            include_reactions=not args.no_reactions,
                        )
                    )
                except CacheError:
                    raise
                except AuthorizationRequired as exc:
                    results.append(
                        {
                            **result_base(target=url),
                            "errors": [error_item("authentication_required", str(exc))],
                        }
                    )
                except MattermostError as exc:
                    results.append(
                        {
                            **result_base(target=url),
                            "errors": [error_item("invalid_input", str(exc))],
                        }
                    )
            complete = all(result["status"] == "ok" for result in results)
            authentication_required = any(
                any(
                    isinstance(error, dict) and error.get("code") == "authentication_required"
                    for error in result_list(result, "errors")
                )
                for result in results
            )
            status = (
                "ok"
                if complete
                else "partial"
                if any(result["status"] != "error" for result in results)
                else "error"
            )
            emit(
                {
                    **result_base(scope="many", target=args.urls),
                    "status": status,
                    "complete": complete,
                    "targets": results,
                    "errors": [
                        error for result in results for error in result_list(result, "errors")
                    ],
                    "counts": {"targets": len(results)},
                    "external_mutations": False,
                }
            )
            return (
                0
                if complete
                else 1
                if status == "partial"
                else AUTH_REQUIRED
                if authentication_required
                else 2
            )
        if args.command == "members":
            result = collect_members(args.url)
            emit(result)
            return 0 if result["status"] == "ok" else 1 if result["status"] == "partial" else 2
        raise MattermostError("a supported subcommand is required")
    except CacheError as exc:
        return fail("cache_error", str(exc), CACHE_ERROR_EXIT)
    except AuthorizationRequired as exc:
        return fail("authentication_required", str(exc), AUTH_REQUIRED)
    except MattermostError as exc:
        return fail("invalid_input", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
