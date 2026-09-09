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
SCHEMA_VERSION = 2
CACHE_TTL_SECONDS = 300
MAX_RESPONSE = 32 * 1024 * 1024
PAGE_SIZE = 200
MAX_PAGES = 10_000
RECEIPT_TTL_SECONDS = 300
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\Z")


class MattermostError(ValueError):
    """Expected safe failure."""


class AuthorizationRequired(MattermostError):
    """No valid origin-bound credential is available."""


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


def classify_url(value: str) -> dict[str, str | None]:
    parsed = urllib.parse.urlsplit(value)
    origin = normalized_origin(value)
    if not parsed.path or "%" in parsed.path:
        raise MattermostError("Mattermost URL path is invalid")
    pieces = parsed.path.split("/")
    if len(pieces) != 4 or pieces[0] or not all(pieces[1:]):
        raise MattermostError("Mattermost URL must identify exactly one supported target")
    team, route, item = (identifier(piece, "path component") for piece in pieces[1:])
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
            "team": team,
            "channel": None,
            "post_id": identifier(item, "post ID"),
        }
    if route == "channels":
        return {
            "origin": origin,
            "kind": "post" if post_id else "channel",
            "team": team,
            "channel": item,
            "post_id": post_id,
        }
    if route in {"messages", "group"}:
        return {
            "origin": origin,
            "kind": "post" if post_id else "chat",
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


def resolve_channel(client: Client, target: dict[str, str | None]) -> dict[str, Any]:
    team = identifier(target["team"], "team")
    channel = identifier(target["channel"], "channel")
    team_data = client.get(f"/teams/name/{urllib.parse.quote(team, safe='')}")
    if not isinstance(team_data, dict) or not isinstance(team_data.get("id"), str):
        raise MattermostError("Mattermost team identity is incomplete")
    team_id = identifier(team_data["id"], "team ID")
    data = client.get(f"/teams/{team_id}/channels/name/{urllib.parse.quote(channel, safe='')}")
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise MattermostError("Mattermost channel identity is incomplete")
    identifier(data["id"], "channel ID")
    return data


def revalidate_access(
    client: Client, target: dict[str, str | None]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if target["kind"] == "post":
        post = client.get(
            f"/posts/{urllib.parse.quote(identifier(target['post_id'], 'post ID'), safe='')}"
        )
        if not isinstance(post, dict) or post.get("id") != target["post_id"]:
            raise MattermostError("Mattermost post access response is incomplete")
        return post, None
    return None, resolve_channel(client, target)


def cache_connection() -> sqlite3.Connection:
    root = private_directory(cache_root())
    path = root / "cache.sqlite3"
    if path.exists():
        private_file(path)
    connection = sqlite3.connect(path)
    path.chmod(0o600)
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS snapshots_v2 (
        key TEXT PRIMARY KEY, schema_version INTEGER NOT NULL, origin TEXT NOT NULL,
        user_id TEXT NOT NULL, target TEXT NOT NULL, period TEXT NOT NULL,
        fetched INTEGER NOT NULL, payload TEXT NOT NULL)"""
    )
    return connection


def cache_key(origin: str, user_id: str, target: dict[str, str | None], period: object) -> str:
    content = {
        "schema_version": SCHEMA_VERSION,
        "origin": origin,
        "user_id": user_id,
        "target": normalized_target(target),
        "period": period,
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def cache_read(
    key: str, *, origin: str, user_id: str, target: dict[str, str | None], period: object
) -> tuple[dict[str, object] | None, int | None]:
    try:
        with cache_connection() as database:
            row = database.execute(
                "SELECT schema_version, origin, user_id, target, period, fetched, payload FROM snapshots_v2 WHERE key = ?",
                (key,),
            ).fetchone()
    except sqlite3.Error:
        return None, None
    if not row:
        return None, None
    schema, row_origin, row_user, row_target, row_period, fetched, payload = row
    age = now() - fetched if isinstance(fetched, int) else None
    expected_target = json.dumps(normalized_target(target), sort_keys=True, separators=(",", ":"))
    expected_period = json.dumps(period, sort_keys=True, separators=(",", ":"))
    if (
        schema != SCHEMA_VERSION
        or row_origin != origin
        or row_user != user_id
        or row_target != expected_target
        or row_period != expected_period
        or age is None
        or age < 0
        or age > CACHE_TTL_SECONDS
    ):
        return None, age
    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        return None, age
    return (value if isinstance(value, dict) else None), age


def cache_write(
    key: str,
    *,
    origin: str,
    user_id: str,
    target: dict[str, str | None],
    period: object,
    value: dict[str, object],
) -> None:
    with cache_connection() as database:
        database.execute(
            "INSERT OR REPLACE INTO snapshots_v2(key, schema_version, origin, user_id, target, period, fetched, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                SCHEMA_VERSION,
                origin,
                user_id,
                json.dumps(normalized_target(target), sort_keys=True, separators=(",", ":")),
                json.dumps(period, sort_keys=True, separators=(",", ":")),
                now(),
                json.dumps(value, ensure_ascii=False, sort_keys=True),
            ),
        )


def valid_posts(value: object) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise MattermostError("Mattermost post response is incomplete")
    posts: list[dict[str, Any]] = []
    malformed = False
    for post in value["posts"].values():
        if (
            not isinstance(post, dict)
            or not isinstance(post.get("id"), str)
            or not isinstance(post.get("create_at"), int)
        ):
            malformed = True
            continue
        posts.append(post)
    return sorted(posts, key=lambda post: (post["create_at"], post["id"])), malformed


def safe_post(post: dict[str, Any]) -> dict[str, Any]:
    """Keep message fields and exact reaction identity, never attachment files."""
    result = {key: value for key, value in post.items() if key not in {"attachments", "reactions"}}
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
            value = client.get(f"/posts/{urllib.parse.quote(identifier(post['id'], 'post ID'), safe='')}/reactions")
            if not isinstance(value, list):
                raise MattermostError("Mattermost reaction response is malformed")
            clean["reactions"] = [
                {"emoji": item["emoji_name"], "user": item["user_id"]}
                for item in value
                if isinstance(item, dict)
                and isinstance(item.get("emoji_name"), str)
                and isinstance(item.get("user_id"), str)
            ]
        except (MattermostError, AuthorizationRequired):
            complete = False
            errors.append(error_item("reactions_unavailable", "Mattermost reactions could not be fully read", retryable=True))
            clean["reactions"] = []
        result.append(clean)
    return result, complete, errors


def warning(code: str, message: str) -> dict[str, object]:
    return {"code": code, "message": message}


def result_list(result: dict[str, object], key: str) -> list[object]:
    value = result.get(key)
    return value if isinstance(value, list) else []


def read_post(
    client: Client, post: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool, list[dict[str, object]], list[dict[str, object]]]:
    root_id = post.get("root_id") or post["id"]
    try:
        root_id = identifier(root_id, "root post ID")
        thread = client.get(f"/posts/{urllib.parse.quote(root_id, safe='')}/thread")
        posts, malformed = valid_posts(thread)
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
        return posts, not malformed, errors, []
    except (MattermostError, AuthorizationRequired) as exc:
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
        )


def in_period(post: dict[str, Any], period: dict[str, str | None]) -> bool:
    created = datetime.fromtimestamp(post["create_at"] / 1000, UTC)
    since = (
        datetime.fromisoformat(period["since"].replace("Z", "+00:00")) if period["since"] else None
    )
    until = (
        datetime.fromisoformat(period["until"].replace("Z", "+00:00")) if period["until"] else None
    )
    return (since is None or created >= since) and (until is None or created < until)


def read_channel(
    client: Client, channel: dict[str, Any], period: dict[str, str | None]
) -> tuple[list[dict[str, Any]], bool, int, list[dict[str, object]], list[dict[str, object]]]:
    channel_id = identifier(channel.get("id"), "channel ID")
    items: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    signatures: set[tuple[str, ...]] = set()
    complete = True
    pages = 0
    for page in range(MAX_PAGES):
        try:
            value = client.get(
                f"/channels/{urllib.parse.quote(channel_id, safe='')}/posts?page={page}&per_page={PAGE_SIZE}"
            )
            posts, malformed = valid_posts(value)
        except (MattermostError, AuthorizationRequired) as exc:
            complete = False
            errors.append(
                error_item(
                    "page_unavailable", "Mattermost post page could not be read", retryable=True
                )
            )
            warnings.append(warning("page_unavailable", str(exc)))
            break
        pages += 1
        signature = tuple(sorted(post["id"] for post in posts))
        if signature in signatures and posts:
            complete = False
            errors.append(error_item("repeated_page", "Mattermost returned a repeated post page"))
            break
        signatures.add(signature)
        if malformed:
            complete = False
            errors.append(
                error_item("malformed_page", "Mattermost post page contained malformed posts")
            )
        for post in posts:
            items[post["id"]] = post
        if len(posts) < PAGE_SIZE:
            break
        if period["since"] and posts:
            oldest = min(post["create_at"] for post in posts)
            since = datetime.fromisoformat(period["since"].replace("Z", "+00:00"))
            if datetime.fromtimestamp(oldest / 1000, UTC) < since:
                break
    else:
        complete = False
        errors.append(error_item("pagination_limit", "Mattermost post pagination limit reached"))
    return (
        [
            post
            for post in sorted(items.values(), key=lambda item: (item["create_at"], item["id"]))
            if in_period(post, period)
        ],
        complete,
        pages,
        errors,
        warnings,
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
    if not posts and not members and not complete and not result["errors"]:
        result["errors"] = [error_item("no_data", "Mattermost did not return safe data")]
    if not posts and not members and complete:
        result["complete"] = False
        result["errors"] = [
            *result_list(result, "errors"),
            error_item("no_data", "Mattermost target returned no data"),
        ]
        complete = False
    result["status"] = "ok" if complete else "partial"
    if not posts and not members and result["errors"]:
        result["status"] = "error"
    return result


def read_one(
    url: str, since: str | None, until: str | None, read_cache: bool, write_cache: bool
) -> dict[str, object]:
    target = classify_url(url)
    period = parse_period(since, until, allowed=target["kind"] != "post")
    token = read_token(str(target["origin"]))
    client = Client(str(target["origin"]), token)
    user_id = user_identity(client)
    access_post, access_channel = revalidate_access(client, target)
    key = cache_key(str(target["origin"]), user_id, target, period)
    if read_cache:
        cached, age = cache_read(
            key, origin=str(target["origin"]), user_id=user_id, target=target, period=period
        )
        if cached is not None:
            if isinstance(cached.get("posts"), list):
                cached["posts"] = [
                    safe_post(post) for post in cached["posts"] if isinstance(post, dict)
                ]
            cached["cache_hit"] = True
            cached["cache_age"] = age
            cached["access_revalidated"] = True
            cached["external_mutations"] = False
            return cached
    result = result_base(scope=str(target["kind"]), target=normalized_target(target), period=period)
    result["access_revalidated"] = True
    if target["kind"] == "post":
        assert access_post is not None
        posts, complete, errors, warnings = read_post(client, access_post)
        posts, reactions_complete, reaction_errors = read_reactions(client, posts)
        complete = complete and reactions_complete
        errors.extend(reaction_errors)
        result.update(
            {
                "posts": posts,
                "complete": complete,
                "errors": errors,
                "warnings": warnings,
                "pages": {"posts": 1, "members": 0},
            }
        )
    else:
        assert access_channel is not None and period is not None
        posts, complete, pages, errors, warnings = read_channel(client, access_channel, period)
        posts, reactions_complete, reaction_errors = read_reactions(client, posts)
        complete = complete and reactions_complete
        errors.extend(reaction_errors)
        result.update(
            {
                "posts": posts,
                "channel": {"id": access_channel["id"], "name": access_channel.get("name")},
                "complete": complete,
                "errors": errors,
                "warnings": warnings,
                "pages": {"posts": pages, "members": 0},
            }
        )
    result = finalize_result(result)
    if write_cache and result["status"] != "error":
        try:
            cache_write(
                key,
                origin=str(target["origin"]),
                user_id=user_id,
                target=target,
                period=period,
                value=result,
            )
        except (MattermostError, sqlite3.Error):
            result["warnings"] = [
                *result_list(result, "warnings"),
                warning("cache_write_failed", "Mattermost cache could not be updated"),
            ]
    return result


def collect_members(url: str) -> dict[str, object]:
    target = classify_url(url)
    if target["kind"] == "post":
        raise MattermostError("members requires a channel, direct, or group chat URL")
    token = read_token(str(target["origin"]))
    client = Client(str(target["origin"]), token)
    user_identity(client)
    _, channel = revalidate_access(client, target)
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
        except (MattermostError, AuthorizationRequired) as exc:
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
        except (MattermostError, AuthorizationRequired) as exc:
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


def cookie_token(origin: str) -> str:
    try:
        cookies = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise MattermostError("browser cookie input must be JSON") from exc
    if not isinstance(cookies, list):
        raise MattermostError("browser cookie input must be an array")
    hostname = urllib.parse.urlsplit(origin).hostname
    for cookie in cookies:
        if (
            isinstance(cookie, dict)
            and cookie.get("name") == "MMAUTHTOKEN"
            and str(cookie.get("domain", "")).lstrip(".").lower() == hostname
        ):
            token = cookie.get("value")
            if isinstance(token, str) and token and "\n" not in token and "\r" not in token:
                return token
    raise MattermostError("browser did not provide an origin-bound session cookie")


def agent_browser_token(origin: str) -> str:
    """Use the explicitly consented host adapter without exposing credentials."""
    try:
        opened = subprocess.run(
            ["agent-browser", "open", origin], capture_output=True, check=False, text=True, timeout=30
        )
        if opened.returncode != 0:
            raise MattermostError("agent-browser could not open the exact origin")
        cookies = subprocess.run(
            ["agent-browser", "cookies", "--json"], capture_output=True, check=False, text=True, timeout=30
        )
        if cookies.returncode != 0:
            raise MattermostError("agent-browser could not read browser cookies")
        values = json.loads(cookies.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise MattermostError("agent-browser authentication failed") from exc
    if not isinstance(values, list):
        raise MattermostError("agent-browser returned invalid cookie data")
    hostname = urllib.parse.urlsplit(origin).hostname
    for cookie in values:
        if isinstance(cookie, dict) and cookie.get("name") == "MMAUTHTOKEN" and str(cookie.get("domain", "")).lstrip(".").lower() == hostname:
            token = cookie.get("value")
            if isinstance(token, str) and token and "\n" not in token and "\r" not in token:
                return token
    raise MattermostError("agent-browser did not provide an origin-bound session cookie")


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
    many = subparsers.add_parser("read-many")
    many.add_argument("urls", nargs="+")
    many.add_argument("--since")
    many.add_argument("--until")
    many.add_argument("--refresh", action="store_true")
    many.add_argument("--no-cache", action="store_true")
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
                    "payload_version": "2.0.0",
                    "mutation": "private-confirmed-only",
                    "dry_run": True,
                    "state_protocol": "origin-token-and-identity-cache",
                    "external_tools": {"browser_auth": False},
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
                exists = path.exists() and not path.is_symlink()
                if exists:
                    private_file(path)
                emit(
                    {
                        "status": "ok",
                        "cache": str(path),
                        "exists": exists,
                        "ttl_seconds": CACHE_TTL_SECONDS,
                        "external_mutations": False,
                    }
                )
                return 0
            if not args.confirm:
                emit(prepare_receipt("cache-clear", path=path))
                return 0
            consume_receipt(args.confirm, "cache-clear", path=path)
            if path.exists():
                private_file(path)
                path.unlink()
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
                        )
                    )
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
                any(error.get("code") == "authentication_required" for error in result_list(result, "errors"))
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
            return 0 if complete else 1 if status == "partial" else AUTH_REQUIRED if authentication_required else 2
        if args.command == "members":
            result = collect_members(args.url)
            emit(result)
            return 0 if result["status"] == "ok" else 1 if result["status"] == "partial" else 2
        raise MattermostError("a supported subcommand is required")
    except AuthorizationRequired as exc:
        return fail("authentication_required", str(exc), AUTH_REQUIRED)
    except MattermostError as exc:
        return fail("invalid_input", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
