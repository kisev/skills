#!/usr/bin/env python3
"""Read a tightly scoped Mattermost URL through GET-only API calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTH_REQUIRED = 3
MAX_RESPONSE = 32 * 1024 * 1024
PAGE_SIZE = 200
MAX_PAGES = 10_000


class MattermostError(ValueError):
    """Expected safe failure."""


class AuthorizationRequired(MattermostError):
    """No valid origin-bound credential is available."""


class ContractArgumentParser(argparse.ArgumentParser):
    """Return invalid CLI input through the JSON runner contract."""

    def error(self, message: str) -> None:
        raise MattermostError(message)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(code: str, message: str, exit_code: int = 2) -> int:
    print(message, file=sys.stderr)
    emit({"status": "error", "error": {"code": code, "message": message, "retryable": False}})
    return exit_code


def normalized_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise MattermostError("Mattermost URL must use an absolute HTTPS origin")
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    port = parsed.port
    if port == 443:
        port = None
    return f"https://{hostname}{f':{port}' if port else ''}"


def private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise MattermostError("private directory must be a real directory")
    path.chmod(0o700)
    return path


def config_root() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mattermost"


def cache_path() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "mattermost" / "cache.sqlite3"


def origin_token_file(origin: str) -> Path:
    key = hashlib.sha256(normalized_origin(origin).encode()).hexdigest()
    return private_directory(config_root() / key) / "token"


def read_token(origin: str) -> str:
    path = origin_token_file(origin)
    if not path.exists():
        raise AuthorizationRequired("Mattermost authentication is required for this origin")
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise AuthorizationRequired("Mattermost credential file is unsafe")
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token or "\r" in token:
        raise AuthorizationRequired("Mattermost credential is invalid")
    return token


def save_token(origin: str, token: str) -> None:
    if not token or "\n" in token or "\r" in token:
        raise MattermostError("browser did not provide a valid session credential")
    path = origin_token_file(origin)
    temporary = path.with_name(".token.tmp")
    temporary.write_text(token + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def classify_url(value: str) -> dict[str, str | None]:
    parsed = urllib.parse.urlsplit(value)
    origin = normalized_origin(value)
    query = urllib.parse.parse_qs(parsed.query)
    post_id = next((query[key][0] for key in ("post", "post_id", "focusedPostId") if query.get(key)), None)
    pieces = [part for part in parsed.path.split("/") if part]
    if post_id:
        return {"origin": origin, "kind": "post", "post_id": post_id, "team": None, "channel": None}
    if len(pieces) >= 3 and pieces[1] == "channels":
        return {"origin": origin, "kind": "channel", "post_id": None, "team": pieces[0], "channel": pieces[2]}
    if len(pieces) >= 3 and pieces[1] in {"messages", "group"}:
        return {"origin": origin, "kind": "chat", "post_id": None, "team": pieces[0], "channel": pieces[2]}
    raise MattermostError("URL must identify one post, channel, direct, or group chat")


class Client:
    def __init__(self, origin: str, token: str):
        self.origin = normalized_origin(origin)
        self.token = token

    def get(self, path: str) -> object:
        if not path.startswith("/") or "://" in path or ".." in path.split("/"):
            raise MattermostError("unsafe Mattermost API path")
        request = urllib.request.Request(
            f"{self.origin}/api/v4{path}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthorizationRequired("Mattermost session is unavailable for this origin") from exc
            raise MattermostError(f"Mattermost GET failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise MattermostError("Mattermost network request failed") from exc
        if len(data) > MAX_RESPONSE:
            raise MattermostError("Mattermost response exceeds the size limit")
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise MattermostError("Mattermost returned invalid JSON") from exc


def cache_connection() -> sqlite3.Connection:
    path = cache_path()
    private_directory(path.parent)
    connection = sqlite3.connect(path)
    path.chmod(0o600)
    connection.execute("PRAGMA secure_delete=ON")
    connection.execute("CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY, fetched TEXT NOT NULL, payload TEXT NOT NULL)")
    return connection


def resolve_channel(client: Client, target: dict[str, str | None]) -> dict[str, Any]:
    team = target["team"]
    channel = target["channel"]
    if not team or not channel:
        raise MattermostError("channel identity is incomplete")
    team_data = client.get(f"/teams/name/{urllib.parse.quote(team, safe='')}")
    if not isinstance(team_data, dict) or not isinstance(team_data.get("id"), str):
        raise MattermostError("Mattermost team identity is incomplete")
    data = client.get(f"/teams/{team_data['id']}/channels/name/{urllib.parse.quote(channel, safe='')}")
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise MattermostError("Mattermost channel identity is incomplete")
    return data


def normalize_posts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise MattermostError("Mattermost post response is incomplete")
    posts = [post for post in value["posts"].values() if isinstance(post, dict)]
    return sorted(posts, key=lambda post: (post.get("create_at", 0), str(post.get("id", ""))))


def read_post(client: Client, post_id: str) -> tuple[list[dict[str, Any]], bool, list[str]]:
    post = client.get(f"/posts/{urllib.parse.quote(post_id, safe='')}")
    if not isinstance(post, dict) or not isinstance(post.get("id"), str):
        raise MattermostError("Mattermost post is incomplete")
    root_id = post.get("root_id") or post["id"]
    try:
        thread = client.get(f"/posts/{urllib.parse.quote(str(root_id), safe='')}/thread")
        return normalize_posts(thread), True, []
    except AuthorizationRequired:
        raise
    except MattermostError as exc:
        return [post], False, [f"thread retrieval incomplete: {exc}"]


def read_channel(client: Client, target: dict[str, str | None], since: str | None, until: str | None) -> tuple[list[dict[str, Any]], bool, list[str]]:
    channel = resolve_channel(client, target)
    items: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    complete = True
    for page in range(MAX_PAGES):
        try:
            value = client.get(f"/channels/{channel['id']}/posts?page={page}&per_page={PAGE_SIZE}")
            posts = normalize_posts(value)
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            warnings.append(f"pagination stopped: {exc}")
            break
        for post in posts:
            items[str(post.get("id"))] = post
        if since and posts:
            timestamps = [post["create_at"] for post in posts if isinstance(post.get("create_at"), int)]
            if timestamps and datetime.fromtimestamp(min(timestamps) / 1000, UTC).isoformat() < since:
                break
        if len(posts) < PAGE_SIZE:
            break
    else:
        complete = False
        warnings.append("pagination protective limit reached")
    def within(post: dict[str, Any]) -> bool:
        created = post.get("create_at")
        if not isinstance(created, int):
            return False
        instant = datetime.fromtimestamp(created / 1000, UTC).isoformat()
        return (since is None or instant >= since) and (until is None or instant < until)
    return [post for post in sorted(items.values(), key=lambda item: (item.get("create_at", 0), str(item.get("id", "")))) if within(post)], complete, warnings


def read_one(url: str, since: str | None, until: str | None, read_cache: bool, write_cache: bool) -> dict[str, object]:
    target = classify_url(url)
    key = hashlib.sha256(json.dumps({"target": target, "since": since, "until": until}, sort_keys=True).encode()).hexdigest()
    if read_cache:
        try:
            with cache_connection() as database:
                row = database.execute("SELECT payload FROM snapshots WHERE key = ?", (key,)).fetchone()
                if row:
                    value = json.loads(row[0])
                    if isinstance(value, dict):
                        value["cache_hit"] = True
                        return value
        except (sqlite3.Error, json.JSONDecodeError):
            pass
    client = Client(str(target["origin"]), read_token(str(target["origin"])))
    if target["kind"] == "post":
        posts, complete, warnings = read_post(client, str(target["post_id"]))
        period: dict[str, str | None] | None = None
    else:
        posts, complete, warnings = read_channel(client, target, since, until)
        period = {"since": since, "until": until}
    result: dict[str, object] = {"status": "ok", "scope": target["kind"], "target": url, "period": period, "posts": posts, "complete": complete, "errors": [], "warnings": warnings, "counts": {"posts": len(posts), "threads": len({post.get('root_id') or post.get('id') for post in posts})}, "source_timestamp": datetime.now(UTC).isoformat(), "cache_hit": False}
    if write_cache:
        try:
            with cache_connection() as database:
                database.execute("INSERT OR REPLACE INTO snapshots(key, fetched, payload) VALUES (?, ?, ?)", (key, result["source_timestamp"], json.dumps(result, ensure_ascii=False)))
        except sqlite3.Error:
            result["warnings"].append("cache write failed")
    return result


def collect_members(url: str) -> dict[str, object]:
    target = classify_url(url)
    if target["kind"] == "post":
        raise MattermostError("members requires a channel, direct, or group chat URL")
    client = Client(str(target["origin"]), read_token(str(target["origin"])))
    channel = resolve_channel(client, target)
    member_ids: list[str] = []
    seen: set[str] = set()
    warnings: list[str] = []
    complete = True
    for page in range(MAX_PAGES):
        try:
            page_value = client.get(f"/channels/{channel['id']}/members?page={page}&per_page={PAGE_SIZE}")
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            warnings.append(f"member pagination stopped: {exc}")
            break
        if not isinstance(page_value, list):
            complete = False
            warnings.append("member pagination response is incomplete")
            break
        for item in page_value:
            user_id = item.get("user_id") if isinstance(item, dict) else None
            if isinstance(user_id, str) and user_id and user_id not in seen:
                seen.add(user_id)
                member_ids.append(user_id)
        if len(page_value) < PAGE_SIZE:
            break
    else:
        complete = False
        warnings.append("member pagination protective limit reached")
    members: list[dict[str, str]] = []
    for user_id in member_ids:
        try:
            profile = client.get(f"/users/{urllib.parse.quote(user_id, safe='')}")
        except AuthorizationRequired:
            raise
        except MattermostError as exc:
            complete = False
            warnings.append(f"member profile unavailable: {user_id}: {exc}")
            continue
        if not isinstance(profile, dict) or not isinstance(profile.get("username"), str):
            complete = False
            warnings.append(f"member profile is incomplete: {user_id}")
            continue
        members.append(
            {
                "id": user_id,
                "username": profile["username"],
                "display_name": str(profile.get("nickname") or profile.get("first_name") or profile["username"]),
            }
        )
    return {"status": "ok" if complete else "partial", "scope": "members", "target": url, "channel": {"id": channel["id"], "name": channel.get("name")}, "members": members, "complete": complete, "errors": [], "warnings": warnings, "counts": {"members": len(member_ids), "resolved": len(members), "unresolved": len(member_ids) - len(members)}, "source_timestamp": datetime.now(UTC).isoformat()}


def import_browser_cookie(url: str) -> int:
    origin = normalized_origin(url)
    try:
        cookies = json.load(sys.stdin)
    except json.JSONDecodeError:
        return fail("invalid_cookie_input", "browser cookie input must be JSON")
    if not isinstance(cookies, list):
        return fail("invalid_cookie_input", "browser cookie input must be an array")
    hostname = urllib.parse.urlsplit(origin).hostname
    for cookie in cookies:
        if isinstance(cookie, dict) and cookie.get("name") == "MMAUTHTOKEN" and str(cookie.get("domain", "")).lstrip(".").lower() == hostname:
            save_token(origin, str(cookie.get("value", "")))
            emit({"status": "ok", "origin": origin})
            return 0
    return fail("cookie_missing", "browser did not provide an origin-bound session cookie")


def default_since() -> str:
    local = datetime.now().astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC).isoformat()


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
    members = subparsers.add_parser("members")
    members.add_argument("url")
    auth = subparsers.add_parser("auth")
    auth.add_argument("url")
    cache = subparsers.add_parser("cache")
    cache.add_argument("action", choices=("status", "clear"))
    try:
        args = parser.parse_args(argv)
    except MattermostError as exc:
        return fail("invalid_input", str(exc))
    if args.capabilities:
        emit({"schema_version": 1, "payload_version": "1.0.0", "mutation": "local-write", "dry_run": False, "state_protocol": "cache-and-origin-token", "external_tools": {"browser_auth": False}, "destructive_flags": ["cache clear"]})
        return 0
    try:
        if args.command == "auth":
            return import_browser_cookie(args.url)
        if args.command == "cache":
            path = cache_path()
            if args.action == "clear" and path.exists():
                if path.is_symlink():
                    raise MattermostError("cache file is unsafe")
                path.unlink()
            emit({"status": "ok", "cache": str(path), "exists": path.exists()})
            return 0
        if args.command == "read":
            if args.refresh and args.no_cache:
                raise MattermostError("--refresh and --no-cache cannot be combined")
            emit(read_one(args.url, args.since or default_since(), args.until, not args.no_cache and not args.refresh, not args.no_cache))
            return 0
        if args.command == "read-many":
            results: list[dict[str, object]] = []
            for url in dict.fromkeys(args.urls):
                try:
                    results.append(read_one(url, args.since or default_since(), args.until, True, True))
                except MattermostError as exc:
                    results.append({"status": "error", "target": url, "error": str(exc), "complete": False})
            complete = all(result.get("complete") for result in results)
            emit({"status": "ok" if complete else "partial", "targets": results, "complete": complete, "errors": [result.get("error") for result in results if result.get("error")]})
            return 0 if complete else 1
        if args.command == "members":
            result = collect_members(args.url)
            emit(result)
            return 0 if result["complete"] else 1
        return fail("invalid_command", "a supported subcommand is required")
    except AuthorizationRequired as exc:
        return fail("authentication_required", str(exc), AUTH_REQUIRED)
    except MattermostError as exc:
        return fail("invalid_input", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
