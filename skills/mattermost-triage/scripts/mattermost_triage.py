#!/usr/bin/env python3
"""Collect and publish durable Mattermost triage artifacts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn, cast

SCHEMA_VERSION = 1
MAX_RESPONSE = 32 * 1024 * 1024
PAGE_SIZE = 200
MAX_PAGES = 10_000
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
CANDIDATE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
CONFIDENCE = {"low", "medium", "high"}
STATUSES = {"attention", "disputed", "no_action"}
CLOSURES = {"open", "closed", "uncertain"}


class TriageError(ValueError):
    """Expected input, remote, or local-state failure."""


class AuthenticationRequired(TriageError):
    """An origin-bound credential is missing or invalid."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise TriageError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _load_state_artifacts() -> Any | None:
    candidates = [Path(__file__).with_name("state_artifacts.py")]
    candidates.extend(
        parent / "shared" / "references" / "state_artifacts.py"
        for parent in Path(__file__).resolve().parents
    )
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("mattermost_triage_state_artifacts", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    return None


STATE = _load_state_artifacts()


def canonical_json(value: object) -> bytes:
    if STATE is not None:
        return cast("bytes", STATE.canonical_json(value))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest_bytes(value: bytes) -> str:
    if STATE is not None:
        return cast("str", STATE.content_digest(value))
    return hashlib.sha256(value).hexdigest()


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def diagnostic(message: str) -> None:
    print(message, file=sys.stderr)


def normalized_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise TriageError("origin must be an exact absolute HTTPS origin")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port
    except ValueError as exc:
        raise TriageError("origin has an invalid port") from exc
    return f"https://{host}{f':{port}' if port not in {None, 443} else ''}"


def exact_target(value: str, origin: str) -> dict[str, str]:
    parsed = urllib.parse.urlsplit(value)
    if (
        normalized_url_origin(value) != origin
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
    ):
        raise TriageError("every target must be an exact same-origin Mattermost URL")
    parts = parsed.path.split("/")
    if len(parts) != 4 or parts[0] or not all(parts[1:]):
        raise TriageError("target must identify exactly one channel, chat, group, or post")
    team, route, item = parts[1:]
    for label, token in (("team", team), ("target", item.lstrip("@"))):
        if not IDENTIFIER.fullmatch(token):
            raise TriageError(f"Mattermost {label} is invalid")
    if route not in {"channels", "messages", "group", "pl"}:
        raise TriageError("target route is unsupported")
    return {"url": value, "team": team, "route": route, "item": item}


def normalized_url_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    return normalized_origin(urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")))


def aware_instant(value: str, label: str) -> datetime:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TriageError(f"{label} must be an ISO-8601 timestamp") from exc
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise TriageError(f"{label} must include a timezone")
    return instant.astimezone(UTC)


def iso(instant: datetime) -> str:
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise TriageError(f"Mattermost {label} is invalid")
    return value


def xdg_path(variable: str, fallback: Path) -> Path:
    path = Path(os.environ.get(variable) or fallback)
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise TriageError(f"{variable} must be a normalized absolute path")
    return path


def require_private_dir(path: Path, *, create: bool = False) -> Path:
    if create and not path.exists() and not path.is_symlink():
        path.mkdir(parents=True, mode=0o700)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise TriageError("private state directory is unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o077
    ):
        raise TriageError("private state directory is unsafe")
    return path


def ensure_private_tree(path: Path, boundary: Path) -> Path:
    if STATE is not None:
        return cast("Path", STATE.ensure_private_directory(path, boundary))
    boundary.mkdir(parents=True, exist_ok=True, mode=0o700)
    boundary.chmod(0o700)
    current = boundary
    try:
        relative = path.relative_to(boundary)
    except ValueError as exc:
        raise TriageError("state path escapes its boundary") from exc
    for part in relative.parts:
        current /= part
        if not current.exists() and not current.is_symlink():
            current.mkdir(mode=0o700)
        require_private_dir(current)
    return path


def private_file(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
        ):
            raise TriageError("private state file is unsafe")
        return path.read_bytes()
    except OSError as exc:
        raise TriageError("private state file is unavailable") from exc


def atomic_private(path: Path, content: bytes, boundary: Path) -> None:
    ensure_private_tree(path.parent, boundary)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise TriageError("private state path is unsafe")
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        os.close(descriptor)
        if temporary.exists():
            temporary.unlink()


def immutable_private(path: Path, content: bytes, boundary: Path) -> None:
    ensure_private_tree(path.parent, boundary)
    if path.exists() or path.is_symlink():
        if private_file(path) != content:
            raise TriageError("immutable state artifact changed")
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)


def token_path(origin: str) -> Path:
    root = xdg_path("XDG_CONFIG_HOME", Path.home() / ".config")
    return root / "mattermost" / hashlib.sha256(origin.encode()).hexdigest() / "token"


def read_token(origin: str) -> str:
    path = token_path(origin)
    try:
        require_private_dir(path.parent.parent)
        require_private_dir(path.parent)
        data = private_file(path)
    except TriageError as exc:
        raise AuthenticationRequired(
            "Mattermost authentication is required for this origin"
        ) from exc
    try:
        token = data.decode().strip()
    except UnicodeDecodeError as exc:
        raise AuthenticationRequired("Mattermost credential is invalid") from exc
    if not token or "\n" in token or "\r" in token:
        raise AuthenticationRequired("Mattermost credential is invalid")
    return token


class Client:
    def __init__(self, origin: str, token: str):
        self.origin = normalized_origin(origin)
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, path: str) -> object:
        if not path.startswith("/") or "://" in path or ".." in path.split("/"):
            raise TriageError("unsafe Mattermost API path")
        request = urllib.request.Request(  # noqa: S310 - origin is normalized HTTPS.
            f"{self.origin}/api/v4{path}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise AuthenticationRequired("Mattermost session is unavailable") from exc
            raise TriageError(f"Mattermost GET failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise TriageError("Mattermost network request failed") from exc
        if len(data) > MAX_RESPONSE:
            raise TriageError("Mattermost response exceeds the size limit")
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise TriageError("Mattermost returned invalid JSON") from exc


def profile(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TriageError("Mattermost profile response is malformed")
    return {
        "id": identifier(value.get("id"), "user ID"),
        "username": identifier(value.get("username"), "username"),
        "first_name": value.get("first_name") if isinstance(value.get("first_name"), str) else "",
        "last_name": value.get("last_name") if isinstance(value.get("last_name"), str) else "",
        "nickname": value.get("nickname") if isinstance(value.get("nickname"), str) else "",
    }


def channel(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TriageError("Mattermost channel response is malformed")
    result = {
        "id": identifier(value.get("id"), "channel ID"),
        "name": identifier(value.get("name"), "channel name"),
        "display_name": value.get("display_name")
        if isinstance(value.get("display_name"), str)
        else "",
        "type": value.get("type"),
        "team_id": value.get("team_id") if isinstance(value.get("team_id"), str) else "",
        "last_post_at": value.get("last_post_at")
        if isinstance(value.get("last_post_at"), int)
        else 0,
    }
    if result["type"] not in {"D", "G", "O", "P"}:
        raise TriageError("Mattermost channel type is unsupported")
    return result


def list_value(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TriageError(f"Mattermost {label} response is malformed")
    return value


def team_map(client: Client, user_id: str) -> tuple[dict[str, str], str]:
    teams = list_value(client.get(f"/users/{urllib.parse.quote(user_id, safe='')}/teams"), "teams")
    result: dict[str, str] = {}
    names: list[str] = []
    for item in teams:
        team_id = identifier(item.get("id"), "team ID")
        name = identifier(item.get("name"), "team name")
        result[team_id] = name
        names.append(name)
    if not names:
        raise TriageError("authenticated user has no Mattermost team")
    return result, sorted(names)[0]


def team_channels(
    client: Client, user_id: str, teams: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], int]:
    found: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    successful = 0
    for team_id, team_name in sorted(teams.items(), key=lambda item: (item[1], item[0])):
        endpoint = f"/users/{urllib.parse.quote(user_id, safe='')}/teams/{team_id}/channels"
        try:
            values = list_value(client.get(endpoint), f"channels for team {team_name}")
            parsed = sorted((channel(item) for item in values), key=lambda item: str(item["id"]))
        except AuthenticationRequired:
            raise
        except TriageError as exc:
            errors.append(error_item(team_name, "team_channels_unavailable", str(exc)))
            continue
        successful += 1
        for item in parsed:
            found.setdefault(str(item["id"]), item)
    return [found[item_id] for item_id in sorted(found)], errors, successful


def resolve_extra(
    client: Client,
    parsed: dict[str, str],
    channels: list[dict[str, Any]],
    teams: dict[str, str],
) -> dict[str, Any]:
    item = parsed["item"]
    if parsed["team"] not in teams.values():
        raise TriageError("target team is not available to the authenticated user")
    if parsed["route"] == "pl":
        post = client.get(f"/posts/{urllib.parse.quote(identifier(item, 'post ID'), safe='')}")
        if not isinstance(post, dict):
            raise TriageError("Mattermost post response is malformed")
        wanted = identifier(post.get("channel_id"), "channel ID")
    elif IDENTIFIER.fullmatch(item) and any(entry["id"] == item for entry in channels):
        wanted = item
    elif parsed["route"] == "messages" and item.startswith("@"):
        peer = profile(client.get(f"/users/username/{urllib.parse.quote(item[1:], safe='')}"))
        me = profile(client.get("/users/me"))["id"]
        name = "__".join(sorted((str(me), str(peer["id"]))))
        matches = [entry for entry in channels if entry["type"] == "D" and entry["name"] == name]
        if len(matches) != 1:
            raise TriageError("direct-message target could not be resolved exactly")
        wanted = str(matches[0]["id"])
    else:
        team_ids = [team_id for team_id, name in teams.items() if name == parsed["team"]]
        if len(team_ids) != 1:
            raise TriageError("target team could not be resolved exactly")
        value = client.get(
            f"/teams/{team_ids[0]}/channels/name/{urllib.parse.quote(item, safe='')}"
        )
        wanted = channel(value)["id"]
    matches = [entry for entry in channels if entry["id"] == wanted]
    if len(matches) != 1:
        resolved = channel(client.get(f"/channels/{urllib.parse.quote(wanted, safe='')}"))
        matches = [resolved]
    selected = dict(matches[0])
    if parsed["route"] == "group" and selected["type"] != "G":
        raise TriageError("group target resolved to a different channel type")
    if parsed["route"] == "messages" and selected["type"] not in {"D", "G"}:
        raise TriageError("message target resolved to a different channel type")
    if selected["type"] in {"O", "P"}:
        expected_team_ids = {team_id for team_id, name in teams.items() if name == parsed["team"]}
        if selected["team_id"] not in expected_team_ids:
            raise TriageError("target channel is not in the URL team")
    selected["target"] = parsed["url"]
    selected["selection"] = "explicit_permalink" if parsed["route"] == "pl" else "explicit"
    selected["focus_post_id"] = item if parsed["route"] == "pl" else None
    return selected


def discovered_target(origin: str, team: str, item: dict[str, Any]) -> str:
    route = "messages" if item["type"] == "D" else "group"
    return f"{origin}/{urllib.parse.quote(team, safe='')}/{route}/{item['id']}"


def normalized_post(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TriageError("Mattermost post is malformed")
    post_id = identifier(value.get("id"), "post ID")
    channel_id = identifier(value.get("channel_id"), "channel ID")
    user_id = identifier(value.get("user_id"), "post user ID")
    root = value.get("root_id") or ""
    if root:
        root = identifier(root, "root post ID")
    created = value.get("create_at")
    if not isinstance(created, int) or created <= 0 or not isinstance(value.get("message"), str):
        raise TriageError("Mattermost post content is malformed")
    return {
        "id": post_id,
        "channel_id": channel_id,
        "root_id": root,
        "user_id": user_id,
        "message": value["message"],
        "create_at": created,
        "update_at": value.get("update_at") if isinstance(value.get("update_at"), int) else created,
        "delete_at": value.get("delete_at") if isinstance(value.get("delete_at"), int) else 0,
        "type": value.get("type") if isinstance(value.get("type"), str) else "",
    }


def posts_response(value: object) -> tuple[list[dict[str, object]], int]:
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise TriageError("Mattermost posts response is malformed")
    posts = [normalized_post(item) for item in value["posts"].values()]
    order = value.get("order")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise TriageError("Mattermost post order is malformed")
    if set(order) != {str(item["id"]) for item in posts} or len(order) != len(set(order)):
        raise TriageError("Mattermost post order is incomplete")
    return posts, len(order)


def post_order_key(post: dict[str, object]) -> tuple[int, str]:
    created = post.get("create_at")
    if not isinstance(created, int):
        raise TriageError("normalized Mattermost post has an invalid timestamp")
    return created, str(post.get("id", ""))


def channel_window(
    client: Client, channel_id: str, since_ms: int, until_ms: int
) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for page in range(MAX_PAGES):
        query = urllib.parse.urlencode({"page": page, "per_page": PAGE_SIZE, "since": since_ms})
        posts, count = posts_response(client.get(f"/channels/{channel_id}/posts?{query}"))
        for post in posts:
            created = post["create_at"]
            if not isinstance(created, int):
                raise TriageError("normalized Mattermost post has an invalid timestamp")
            if since_ms <= created < until_ms:
                found[str(post["id"])] = post
        if count < PAGE_SIZE:
            break
    else:
        raise TriageError("Mattermost post pagination exceeded the limit")
    return sorted(found.values(), key=post_order_key)


def full_threads(
    client: Client, window_posts: list[dict[str, object]], channel_id: str
) -> list[dict[str, object]]:
    roots = sorted({str(post["root_id"] or post["id"]) for post in window_posts})
    result: list[dict[str, object]] = []
    for root in roots:
        posts, _count = posts_response(client.get(f"/posts/{root}/thread"))
        if root not in {post["id"] for post in posts}:
            raise TriageError("Mattermost thread does not contain its root")
        if any(post["channel_id"] != channel_id for post in posts):
            raise TriageError("Mattermost thread contains a post from another channel")
        result.extend(posts)
    unique = {str(post["id"]): post for post in result}
    return sorted(unique.values(), key=post_order_key)


def focused_thread(client: Client, post_id: str, channel_id: str) -> list[dict[str, object]]:
    selected = normalized_post(client.get(f"/posts/{urllib.parse.quote(post_id, safe='')}"))
    if selected["id"] != post_id or selected["channel_id"] != channel_id:
        raise TriageError("Mattermost permalink resolved to a different post or channel")
    root_id = str(selected["root_id"] or selected["id"])
    posts = full_threads(client, [selected], channel_id)
    if post_id not in {post["id"] for post in posts} or root_id not in {
        post["id"] for post in posts
    }:
        raise TriageError("Mattermost permalink thread is incomplete")
    return posts


def add_reactions(client: Client, post: dict[str, object]) -> None:
    value = client.get(f"/posts/{post['id']}/reactions")
    if not isinstance(value, list):
        raise TriageError("Mattermost reactions response is malformed")
    reactions: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise TriageError("Mattermost reaction is malformed")
        emoji = item.get("emoji_name")
        user_id = item.get("user_id")
        if not isinstance(emoji, str) or not emoji or not isinstance(user_id, str):
            raise TriageError("Mattermost reaction is malformed")
        reactions.append({"emoji": emoji, "user_id": identifier(user_id, "reaction user ID")})
    post["reactions"] = sorted(reactions, key=lambda item: (item["emoji"], item["user_id"]))


def state_boundary() -> Path:
    return xdg_path("XDG_STATE_HOME", Path.home() / ".local" / "state") / "agent-skills"


def scope_root(origin: str, user_id: str) -> Path:
    key = digest_bytes(canonical_json({"origin": origin, "user_id": user_id}))
    return state_boundary() / "mattermost-triage" / key


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(private_file(path))
    except json.JSONDecodeError as exc:
        raise TriageError("state JSON is malformed") from exc
    if not isinstance(value, dict):
        raise TriageError("state JSON must be an object")
    return value


def previous_complete_until(root: Path, origin: str, user_id: str) -> datetime | None:
    pointer = root / "evidence" / "complete.json"
    if not pointer.exists() and not pointer.is_symlink():
        return None
    current = read_json_file(pointer)
    path = Path(str(current.get("path", "")))
    if not path.is_absolute() or not DIGEST.fullmatch(str(current.get("digest", ""))):
        raise TriageError("current evidence pointer is malformed")
    evidence = read_json_file(path)
    body = canonical_json(evidence)
    if (
        digest_bytes(body) != current["digest"]
        or evidence.get("origin") != origin
        or evidence.get("authenticated_user", {}).get("id") != user_id
        or evidence.get("complete") is not True
    ):
        raise TriageError("current complete evidence is inconsistent")
    return aware_instant(str(evidence.get("period", {}).get("until", "")), "stored until")


def current_analysis(root: Path, origin: str, user_id: str) -> dict[str, Any] | None:
    pointer_path = root / "analysis" / "current.json"
    if not pointer_path.exists() and not pointer_path.is_symlink():
        return None
    require_private_dir(root)
    require_private_dir(root / "analysis")
    require_private_dir(root / "analysis" / "history")
    pointer = read_json_file(pointer_path)
    if set(pointer) != {"digest", "path"} or not DIGEST.fullmatch(str(pointer.get("digest", ""))):
        raise TriageError("current analysis pointer is malformed")
    digest = str(pointer["digest"])
    artifact = Path(str(pointer["path"]))
    expected = root / "analysis" / "history" / f"{digest}.json"
    if artifact != expected:
        raise TriageError("current analysis pointer escapes its immutable history")
    analysis = read_json_file(artifact)
    if (
        digest_bytes(canonical_json(analysis)) != digest
        or analysis.get("schema_version") != 1
        or analysis.get("kind") != "mattermost-triage-analysis"
        or analysis.get("origin") != origin
        or analysis.get("authenticated_user", {}).get("id") != user_id
        or not isinstance(analysis.get("candidates"), list)
    ):
        raise TriageError("current analysis is stale or inconsistent")
    return analysis


def carryover_post_ids(analysis: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for value in analysis["candidates"]:
        if not isinstance(value, dict) or value.get("closure") not in CLOSURES:
            raise TriageError("current analysis candidate closure is invalid")
        if value["closure"] == "closed":
            continue
        candidate_id = value.get("id")
        excerpts = value.get("cited_excerpts")
        if not isinstance(candidate_id, str) or not isinstance(excerpts, list):
            raise TriageError("current analysis carryover is malformed")
        for excerpt in excerpts:
            if not isinstance(excerpt, dict):
                raise TriageError("current analysis carryover citation is malformed")
            post_id = identifier(excerpt.get("post_id"), "carryover post ID")
            result.setdefault(post_id, set()).add(candidate_id)
    return result


def error_item(source: str, code: str, message: str) -> dict[str, str]:
    return {"source": source, "code": code, "message": message}


def collect(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    origin = normalized_origin(args.origin)
    if args.limit < 0 or args.limit > 200:
        raise TriageError("--limit must be between 0 and 200")
    parsed_targets = [exact_target(value, origin) for value in args.target]
    client = Client(origin, read_token(origin))
    me = profile(client.get("/users/me"))
    user_id = str(me["id"])
    root = scope_root(origin, user_id)
    ensure_private_tree(root, state_boundary())
    current_time = datetime.now(UTC)
    until = aware_instant(args.until, "--until") if args.until else current_time
    if args.since:
        since = aware_instant(args.since, "--since")
    else:
        since = previous_complete_until(root, origin, user_id) or current_time - timedelta(days=30)
    if since >= until:
        raise TriageError("collection period must have since before until")
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(until.timestamp() * 1000)
    errors: list[dict[str, str]] = []
    try:
        teams, fallback_team = team_map(client, user_id)
    except AuthenticationRequired:
        raise
    except TriageError as exc:
        teams, fallback_team = {}, ""
        errors.append(error_item(origin, "teams_unavailable", str(exc)))
    channels: list[dict[str, Any]] = []
    successful_team_lists = 0
    if teams:
        channels, team_errors, successful_team_lists = team_channels(client, user_id, teams)
        errors.extend(team_errors)
        if successful_team_lists == 0:
            errors.append(
                error_item(
                    origin,
                    "no_team_channel_lists",
                    "no Mattermost team channel list could be collected",
                )
            )
    selected: dict[str, dict[str, Any]] = {}
    defaults = sorted(
        (item for item in channels if item["type"] in {"D", "G"}),
        key=lambda item: (-int(item["last_post_at"]), str(item["id"])),
    )[: args.limit]
    for item in defaults:
        copy = dict(item)
        team_name = teams.get(str(item["team_id"]), fallback_team)
        copy.update(
            target=discovered_target(origin, team_name, item),
            selection="default_recent",
            focus_post_id=None,
            carryover_candidate_ids=[],
        )
        selected[f"channel:{item['id']}"] = copy
    unresolved_sources: list[dict[str, object]] = []
    for target in parsed_targets:
        try:
            extra = resolve_extra(client, target, channels, teams)
            extra["carryover_candidate_ids"] = []
            key = (
                f"post:{extra['focus_post_id']}"
                if extra["focus_post_id"] is not None
                else f"channel:{extra['id']}"
            )
            selected[key] = extra
        except AuthenticationRequired:
            raise
        except TriageError as exc:
            error = error_item(target["url"], "target_unavailable", str(exc))
            errors.append(error)
            unresolved_sources.append(
                {
                    "target": target["url"],
                    "selection": "explicit",
                    "channel": None,
                    "complete": False,
                    "thread_complete": False,
                    "post_ids": [],
                    "carryover_candidate_ids": [],
                    "errors": [error],
                }
            )

    try:
        prior_analysis = current_analysis(root, origin, user_id)
        carryover = carryover_post_ids(prior_analysis) if prior_analysis is not None else {}
    except TriageError as exc:
        carryover = {}
        errors.append(error_item(origin, "carryover_state_invalid", str(exc)))
    for post_id, candidate_ids in sorted(carryover.items()):
        key = f"post:{post_id}"
        if key in selected:
            selected[key]["carryover_candidate_ids"] = sorted(candidate_ids)
            selected[key]["selection"] = f"{selected[key]['selection']}_carryover_unresolved"
            continue
        carryover_target = source_link(origin, post_id)
        try:
            observed = normalized_post(client.get(f"/posts/{post_id}"))
            channel_id = str(observed["channel_id"])
            resolved = channel(client.get(f"/channels/{channel_id}"))
            team_name = teams.get(str(resolved["team_id"]), fallback_team)
            if not team_name:
                raise TriageError("carryover post team could not be resolved")
            carryover_target = f"{origin}/{urllib.parse.quote(team_name, safe='')}/pl/{post_id}"
            selected[key] = {
                **resolved,
                "target": carryover_target,
                "selection": "carryover_unresolved",
                "focus_post_id": post_id,
                "carryover_candidate_ids": sorted(candidate_ids),
            }
        except AuthenticationRequired:
            raise
        except TriageError as exc:
            error = error_item(carryover_target, "carryover_unavailable", str(exc))
            errors.append(error)
            unresolved_sources.append(
                {
                    "target": carryover_target,
                    "selection": "carryover_unresolved",
                    "channel": None,
                    "complete": False,
                    "thread_complete": False,
                    "post_ids": [post_id],
                    "carryover_candidate_ids": sorted(candidate_ids),
                    "errors": [error],
                }
            )

    sources: list[dict[str, object]] = unresolved_sources
    all_posts: dict[str, dict[str, object]] = {}
    provenance: list[dict[str, object]] = []
    for _selection_key, item in sorted(selected.items()):
        source_errors: list[dict[str, str]] = []
        posts: list[dict[str, object]] = []
        thread_complete = True
        try:
            if item.get("focus_post_id") is not None:
                posts = focused_thread(client, str(item["focus_post_id"]), str(item["id"]))
            else:
                window_posts = channel_window(client, str(item["id"]), since_ms, until_ms)
                posts = window_posts
                if window_posts:
                    try:
                        posts = full_threads(client, window_posts, str(item["id"]))
                    except TriageError as exc:
                        thread_complete = False
                        source_errors.append(
                            error_item(str(item["target"]), "thread_partial", str(exc))
                        )
            for post in posts:
                try:
                    add_reactions(client, post)
                except TriageError as exc:
                    post["reactions"] = []
                    source_errors.append(
                        error_item(
                            str(item["target"]),
                            "reactions_unavailable",
                            f"{post['id']}: {exc}",
                        )
                    )
                all_posts[str(post["id"])] = post
        except AuthenticationRequired:
            raise
        except TriageError as exc:
            thread_complete = False
            source_errors.append(error_item(str(item["target"]), "conversation_partial", str(exc)))
        errors.extend(source_errors)
        source_complete = not source_errors
        for post in posts:
            provenance.append(
                {
                    "post_id": post["id"],
                    "source_target": item["target"],
                    "selection": item["selection"],
                    "source_complete": source_complete,
                    "thread_complete": thread_complete,
                }
            )
        sources.append(
            {
                "target": item["target"],
                "selection": item["selection"],
                "channel": {
                    key: item[key] for key in ("id", "name", "display_name", "type", "last_post_at")
                },
                "complete": source_complete,
                "thread_complete": thread_complete,
                "post_ids": [post["id"] for post in posts],
                "carryover_candidate_ids": item["carryover_candidate_ids"],
                "errors": source_errors,
            }
        )
    user_ids = {str(post["user_id"]) for post in all_posts.values()}
    for post in all_posts.values():
        reactions = post.get("reactions")
        if not isinstance(reactions, list):
            continue
        for reaction in reactions:
            if isinstance(reaction, dict) and isinstance(reaction.get("user_id"), str):
                user_ids.add(reaction["user_id"])
    profiles: list[dict[str, object]] = []
    for observed_id in sorted(user_ids | {user_id}):
        try:
            profiles.append(
                me if observed_id == user_id else profile(client.get(f"/users/{observed_id}"))
            )
        except AuthenticationRequired:
            raise
        except TriageError as exc:
            errors.append(error_item(origin, "profile_unavailable", f"{observed_id}: {exc}"))
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": "mattermost-triage-evidence",
        "origin": origin,
        "authenticated_user": me,
        "period": {"since": iso(since), "until": iso(until)},
        "collected_at": iso(current_time),
        "complete": not errors,
        "sources": sorted(sources, key=lambda item: str(item["target"])),
        "profiles": sorted(profiles, key=lambda item: str(item["id"])),
        "posts": sorted(all_posts.values(), key=post_order_key),
        "post_provenance": sorted(
            provenance,
            key=lambda item: (
                str(item["post_id"]),
                str(item["source_target"]),
                str(item["selection"]),
            ),
        ),
        "errors": errors,
    }
    body = canonical_json(evidence)
    evidence_digest = digest_bytes(body)
    artifact = root / "evidence" / "history" / f"{evidence_digest}.json"
    immutable_private(artifact, body + b"\n", state_boundary())
    pointer = root / "evidence" / "current.json"
    atomic_private(
        pointer,
        canonical_json({"digest": evidence_digest, "path": str(artifact)}) + b"\n",
        state_boundary(),
    )
    complete_pointer = root / "evidence" / "complete.json"
    if not errors:
        atomic_private(
            complete_pointer,
            canonical_json({"digest": evidence_digest, "path": str(artifact)}) + b"\n",
            state_boundary(),
        )
    result = {
        "status": "ok" if not errors else "partial",
        "complete": not errors,
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "evidence_path": str(artifact),
        "current_path": str(pointer),
        "complete_path": str(complete_pointer) if complete_pointer.exists() else None,
        "period": evidence["period"],
        "counts": {"sources": len(sources), "posts": len(all_posts), "profiles": len(profiles)},
        "errors": errors,
    }
    return result, 0 if not errors else 1


def load_evidence(path: Path) -> tuple[dict[str, Any], str, Path]:
    value = read_json_file(path)
    if set(value) == {"digest", "path"}:
        artifact = Path(str(value["path"]))
        expected = value["digest"]
        evidence = read_json_file(artifact)
    else:
        artifact = path
        evidence = value
        expected = digest_bytes(canonical_json(evidence))
    actual = digest_bytes(canonical_json(evidence))
    if expected != actual or not DIGEST.fullmatch(str(expected)):
        raise TriageError("evidence digest does not match its content")
    if evidence.get("kind") != "mattermost-triage-evidence" or evidence.get("schema_version") != 1:
        raise TriageError("evidence schema is unsupported")
    return evidence, actual, artifact


def exact_object(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise TriageError(f"{label} has an invalid shape")
    return value


def nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise TriageError(f"{label} must be non-empty text")
    return value


def source_link(origin: str, post_id: str) -> str:
    return f"{origin}/_redirect/pl/{urllib.parse.quote(post_id, safe='')}"


def validate_analysis(
    raw: object, evidence: dict[str, Any], evidence_digest: str
) -> dict[str, Any]:
    analysis = exact_object(
        raw, {"schema_version", "evidence_digest", "summary", "candidates"}, "analysis"
    )
    if analysis["schema_version"] != 1 or analysis["evidence_digest"] != evidence_digest:
        raise TriageError("analysis is not bound to this evidence digest")
    summary = exact_object(analysis["summary"], {"confidence", "rationale"}, "summary")
    if summary["confidence"] not in CONFIDENCE:
        raise TriageError("summary confidence is invalid")
    nonempty(summary["rationale"], "summary rationale")
    candidates = analysis["candidates"]
    if not isinstance(candidates, list):
        raise TriageError("candidates must be a list")
    posts = {post["id"]: post for post in evidence.get("posts", []) if isinstance(post, dict)}
    provenance: dict[str, list[dict[str, Any]]] = {}
    for binding in evidence.get("post_provenance", []):
        if not isinstance(binding, dict) or not isinstance(binding.get("post_id"), str):
            raise TriageError("evidence post provenance is malformed")
        if (
            not isinstance(binding.get("source_target"), str)
            or not isinstance(binding.get("selection"), str)
            or not isinstance(binding.get("source_complete"), bool)
            or not isinstance(binding.get("thread_complete"), bool)
        ):
            raise TriageError("evidence post provenance is malformed")
        provenance.setdefault(binding["post_id"], []).append(binding)
    targets = {
        source["target"]: source
        for source in evidence.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("channel"), dict)
    }
    seen: set[str] = set()
    durable: list[dict[str, Any]] = []
    keys = {
        "id",
        "status",
        "closure",
        "confidence",
        "rationale",
        "source_post_ids",
        "cited_excerpts",
        "draft_response",
        "response_target",
        "plan",
    }
    for candidate_value in candidates:
        candidate = exact_object(candidate_value, keys, "candidate")
        candidate_id = candidate["id"]
        if (
            not isinstance(candidate_id, str)
            or not CANDIDATE_ID.fullmatch(candidate_id)
            or candidate_id in seen
        ):
            raise TriageError("candidate ID is invalid or duplicated")
        seen.add(candidate_id)
        if candidate["status"] not in STATUSES or candidate["confidence"] not in CONFIDENCE:
            raise TriageError("candidate status or confidence is invalid")
        closure = candidate["closure"]
        if closure not in CLOSURES:
            raise TriageError("candidate closure is invalid")
        if (
            (candidate["status"] == "attention" and closure not in {"open", "uncertain"})
            or (candidate["status"] == "no_action" and closure != "closed")
            or (candidate["status"] == "disputed" and closure != "uncertain")
        ):
            raise TriageError("candidate status and closure are inconsistent")
        nonempty(candidate["rationale"], "candidate rationale")
        excerpts = candidate["cited_excerpts"]
        source_ids = candidate["source_post_ids"]
        if (
            not isinstance(excerpts, list)
            or not excerpts
            or not isinstance(source_ids, list)
            or len(source_ids) != len(set(source_ids))
        ):
            raise TriageError("candidate citations are invalid")
        durable_excerpts: list[dict[str, Any]] = []
        cited_ids: list[str] = []
        incomplete_citation = False
        for excerpt_value in excerpts:
            excerpt = exact_object(excerpt_value, {"post_id", "quote"}, "cited excerpt")
            post_id = excerpt["post_id"]
            quote = nonempty(excerpt["quote"], "cited quote")
            if post_id not in posts or quote not in str(posts[post_id].get("message", "")):
                raise TriageError("cited excerpt is not literal collected evidence")
            bindings = provenance.get(post_id, [])
            if not bindings:
                raise TriageError("cited post has no source provenance")
            bindings = sorted(
                bindings,
                key=lambda item: (str(item["source_target"]), str(item["selection"])),
            )
            complete = all(
                binding["source_complete"] and binding["thread_complete"] for binding in bindings
            )
            incomplete_citation = incomplete_citation or not complete
            cited_ids.append(post_id)
            durable_excerpts.append(
                {
                    "post_id": post_id,
                    "quote": quote,
                    "source_link": source_link(evidence["origin"], post_id),
                    "source_target": bindings[0]["source_target"],
                    "source_complete": complete,
                    "thread_complete": all(binding["thread_complete"] for binding in bindings),
                }
            )
        if source_ids != list(dict.fromkeys(cited_ids)):
            raise TriageError("source_post_ids must exactly match cited excerpts")
        draft = candidate["draft_response"]
        response_target = candidate["response_target"]
        plan = candidate["plan"]
        if draft is not None:
            nonempty(draft, "draft response")
            if (
                candidate["status"] != "attention"
                or response_target not in targets
                or plan is not None
                or incomplete_citation
                or not targets[response_target]["complete"]
                or not targets[response_target]["thread_complete"]
            ):
                raise TriageError("draft response requires complete cited and target evidence")
        else:
            if response_target is not None or plan is None:
                raise TriageError(
                    "candidate without a draft requires one plan and no response target"
                )
            nonempty(plan, "candidate plan")
        durable.append(
            {
                "id": candidate_id,
                "status": candidate["status"],
                "closure": closure,
                "confidence": candidate["confidence"],
                "rationale": candidate["rationale"],
                "cited_excerpts": durable_excerpts,
                "draft_response": draft,
                "response_target": response_target,
                "plan": plan,
            }
        )
    return {
        "schema_version": 1,
        "kind": "mattermost-triage-analysis",
        "evidence_digest": evidence_digest,
        "origin": evidence["origin"],
        "authenticated_user": evidence["authenticated_user"],
        "period": evidence["period"],
        "evidence_complete": evidence["complete"],
        "sources": [
            {
                "target": source["target"],
                "selection": source["selection"],
                "complete": source["complete"],
                "thread_complete": source["thread_complete"],
                "errors": source["errors"],
            }
            for source in evidence["sources"]
        ],
        "errors": evidence["errors"],
        "summary": summary,
        "candidates": durable,
    }


def action_for(
    root: Path,
    evidence: dict[str, Any],
    evidence_digest: str,
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], str, Path]:
    target = next(
        source for source in evidence["sources"] if source["target"] == candidate["response_target"]
    )
    created_at = int(aware_instant(evidence["collected_at"], "evidence collected_at").timestamp())
    action = {
        "schema_version": 1,
        "origin": evidence["origin"],
        "user_id": evidence["authenticated_user"]["id"],
        "evidence_digest": evidence_digest,
        "candidate_id": candidate["id"],
        "target": candidate["response_target"],
        "channel_id": target["channel"]["id"],
        "message": candidate["draft_response"],
        "publication_id": digest_bytes(
            canonical_json([evidence_digest, candidate["id"], candidate["draft_response"]])
        ),
        "created_at": created_at,
        "expires_at": created_at + 24 * 60 * 60,
    }
    action_digest = digest_bytes(canonical_json(action))
    path = root / "actions" / f"{action_digest}.json"
    immutable_private(path, canonical_json(action) + b"\n", state_boundary())
    return action, action_digest, path


def markdown_escape(value: object) -> str:
    return (
        str(value).replace("\\", "\\\\").replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")
    )


def render_report(durable: dict[str, Any], commands: dict[str, str]) -> bytes:
    attention = [item for item in durable["candidates"] if item["status"] == "attention"]
    disputed = [item for item in durable["candidates"] if item["status"] == "disputed"]
    lines = [
        "# Mattermost Triage",
        "",
        f"- Evidence: `{durable['evidence_digest']}`",
        f"- Period: `{durable['period']['since']}` to `{durable['period']['until']}`",
        f"- Evidence complete: `{str(durable['evidence_complete']).lower()}`",
        f"- Primary attention count: `{len(attention)}`",
        f"- Disputed count (excluded from primary): `{len(disputed)}`",
        f"- Confidence: `{durable['summary']['confidence']}`",
        f"- Rationale: {markdown_escape(durable['summary']['rationale'])}",
        "",
        "## Checked Sources",
        "",
    ]
    for source in durable["sources"]:
        state = "complete" if source["complete"] else "partial"
        thread = "complete" if source["thread_complete"] else "partial"
        lines.append(
            f"- [{markdown_escape(source['target'])}]({source['target']}) - "
            f"`{state}`, thread `{thread}`, selection `{source['selection']}`"
        )
    lines.extend(["", "## Partial Errors", ""])
    if durable["errors"]:
        for error in durable["errors"]:
            lines.append(
                f"- `{markdown_escape(error['code'])}` at `{markdown_escape(error['source'])}`: "
                f"{markdown_escape(error['message'])}"
            )
    else:
        lines.append("- None.")
    for heading, items in (
        ("Attention", attention),
        ("Disputed (Excluded From Primary Count)", disputed),
        ("No Action", [item for item in durable["candidates"] if item["status"] == "no_action"]),
    ):
        lines.extend(["", f"## {heading}", ""])
        if not items:
            lines.append("- None.")
            continue
        for item in items:
            lines.extend(
                [
                    f"### {markdown_escape(item['id'])}",
                    "",
                    f"- Confidence: `{item['confidence']}`",
                    f"- Closure: `{item['closure']}`",
                    f"- Rationale: {markdown_escape(item['rationale'])}",
                    "- Evidence:",
                ]
            )
            for excerpt in item["cited_excerpts"]:
                lines.append(
                    f"  - [{excerpt['post_id']}]({excerpt['source_link']}): “{markdown_escape(excerpt['quote'])}”"
                )
            if item["draft_response"] is not None:
                lines.extend(
                    [
                        "- Draft response:",
                        "",
                        "```text",
                        item["draft_response"],
                        "```",
                        "",
                        "- Manual publication command:",
                        f"- Expires at: `{next(action['expires_at'] for action in durable['actions'] if action['candidate_id'] == item['id'])}`",
                        "",
                        "```sh",
                        commands[item["id"]],
                        "```",
                    ]
                )
            else:
                lines.append(f"- Plan: {markdown_escape(item['plan'])}")
    return ("\n".join(lines) + "\n").encode()


def stable_markdown(path: Path, body: bytes, boundary: Path) -> None:
    if STATE is not None:
        body = STATE.versioned_markdown(path, body)
    atomic_private(path, body, boundary)


def publish(args: argparse.Namespace) -> tuple[dict[str, object], int]:
    evidence, evidence_digest, _artifact = load_evidence(Path(args.evidence))
    try:
        raw = json.loads(Path(args.analysis).read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise TriageError("analysis JSON is unavailable or malformed") from exc
    durable = validate_analysis(raw, evidence, evidence_digest)
    user_id = str(evidence["authenticated_user"]["id"])
    root = scope_root(str(evidence["origin"]), user_id)
    ensure_private_tree(root, state_boundary())
    commands: dict[str, str] = {}
    actions: list[dict[str, object]] = []
    helper = Path(__file__).with_name("mattermost_triage_publication.py").resolve()
    for candidate in durable["candidates"]:
        if candidate["draft_response"] is None:
            continue
        action, action_digest, action_path = action_for(root, evidence, evidence_digest, candidate)
        command = shlex.join(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(helper),
                "publish",
                "--action",
                str(action_path),
                "--confirm",
                action_digest,
            ]
        )
        commands[candidate["id"]] = command
        actions.append(
            {
                "candidate_id": candidate["id"],
                "digest": action_digest,
                "path": str(action_path),
                "command": command,
                "expires_at": action["expires_at"],
            }
        )
    durable["actions"] = actions
    durable_body = canonical_json(durable)
    analysis_digest = digest_bytes(durable_body)
    artifact = root / "analysis" / "history" / f"{analysis_digest}.json"
    immutable_private(artifact, durable_body + b"\n", state_boundary())
    pointer = root / "analysis" / "current.json"
    atomic_private(
        pointer,
        canonical_json({"digest": analysis_digest, "path": str(artifact)}) + b"\n",
        state_boundary(),
    )
    report = root / "mattermost-triage.md"
    stable_markdown(report, render_report(durable, commands), state_boundary())
    result = {
        "status": "ok",
        "complete": bool(evidence["complete"]),
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "analysis_digest": analysis_digest,
        "analysis_path": str(artifact),
        "current_path": str(pointer),
        "report_path": str(report),
        "primary_attention_count": sum(
            item["status"] == "attention" for item in durable["candidates"]
        ),
        "disputed_count": sum(item["status"] == "disputed" for item in durable["candidates"]),
        "publication_commands": actions,
    }
    return result, 0 if evidence["complete"] else 1


def capabilities() -> dict[str, object]:
    return {
        "schema_version": 1,
        "commands": ["collect", "publish"],
        "collect": {
            "default_limit": 20,
            "default_first_run_days": 30,
            "extra_targets": "repeated exact same-origin HTTPS URLs",
            "interval": "start-inclusive,end-exclusive",
        },
        "analysis": {
            "statuses": sorted(STATUSES),
            "closures": sorted(CLOSURES),
            "confidence": sorted(CONFIDENCE),
        },
        "external_mutations": False,
        "publication": "separate manual digest-confirmed helper",
    }


def build_parser() -> Parser:
    parser = Parser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    commands = parser.add_subparsers(dest="command")
    collect_parser = commands.add_parser("collect")
    collect_parser.add_argument("--origin", required=True)
    collect_parser.add_argument("--limit", type=int, default=20)
    collect_parser.add_argument("--target", action="append", default=[])
    collect_parser.add_argument("--since")
    collect_parser.add_argument("--until")
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--evidence", required=True)
    publish_parser.add_argument("--analysis", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.capabilities:
            emit(capabilities())
            return 0
        if args.command == "collect":
            result, code = collect(args)
        elif args.command == "publish":
            result, code = publish(args)
        else:
            raise TriageError("one command is required")
    except AuthenticationRequired as exc:
        diagnostic(f"authentication_required: {exc}")
        emit(
            {
                "status": "error",
                "complete": False,
                "external_mutations": False,
                "error": "authentication_required",
            }
        )
        return 3
    except (TriageError, OSError, TypeError, KeyError) as exc:
        diagnostic(f"error: {exc}")
        emit({"status": "error", "complete": False, "external_mutations": False, "error": str(exc)})
        return 2
    else:
        emit(result)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
