#!/usr/bin/env python3
"""Publish exactly one prepared Mattermost triage text response."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, NoReturn, cast

sys.dont_write_bytecode = True

_RUNNER = Path(__file__).with_name("mattermost_triage.py")
_SPEC = importlib.util.spec_from_file_location("mattermost_triage_publication_support", _RUNNER)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Mattermost triage publication support is unavailable")
triage = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = triage
_SPEC.loader.exec_module(triage)


class PublicationError(ValueError):
    """The publication action is invalid, stale, or unsafe."""


class AmbiguousPost(PublicationError):
    """A text post may have reached Mattermost."""


class NotApplied(PublicationError):
    """Mattermost explicitly rejected the POST before acceptance."""

    def __init__(self, status: int):
        super().__init__(f"Mattermost rejected the post with HTTP {status}")
        self.status = status


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PublicationError(message)


def emit(status: str, outcome: str, external: bool, **extra: object) -> None:
    print(
        json.dumps(
            {
                "status": status,
                "mutation_outcome": outcome,
                "external_mutations": external,
                **extra,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def load_action(path_value: str, confirmation: str) -> tuple[dict[str, Any], Path, str]:
    path = Path(path_value)
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise PublicationError("action path must be normalized and absolute")
    if not triage.DIGEST.fullmatch(confirmation):
        raise PublicationError("confirmation digest is invalid")
    action = triage.read_json_file(path)
    if triage.digest_bytes(triage.canonical_json(action)) != confirmation:
        raise PublicationError("action digest does not match --confirm")
    required = {
        "schema_version",
        "origin",
        "user_id",
        "evidence_digest",
        "candidate_id",
        "target",
        "channel_id",
        "message",
        "publication_id",
        "created_at",
        "expires_at",
    }
    if set(action) != required or action.get("schema_version") != 1:
        raise PublicationError("action schema is invalid")
    try:
        origin = triage.normalized_origin(action["origin"])
        user_id = triage.identifier(action["user_id"], "user ID")
        triage.identifier(action["channel_id"], "channel ID")
        triage.exact_target(action["target"], origin)
    except (KeyError, TypeError, triage.TriageError) as exc:
        raise PublicationError("action identity or target is invalid") from exc
    if (
        not triage.DIGEST.fullmatch(str(action["evidence_digest"]))
        or not triage.DIGEST.fullmatch(str(action["publication_id"]))
        or not isinstance(action["message"], str)
        or not action["message"].strip()
        or not isinstance(action["created_at"], int)
        or not isinstance(action["expires_at"], int)
        or action["expires_at"] != action["created_at"] + 24 * 60 * 60
    ):
        raise PublicationError("action content is invalid")
    root = triage.scope_root(origin, user_id)
    expected = root / "actions" / f"{confirmation}.json"
    if path != expected:
        raise PublicationError("action path does not match its origin and identity")
    return action, root, confirmation


def open_lock(root: Path) -> Any:
    triage.ensure_private_tree(root, triage.state_boundary())
    path = root / "publication.lock"
    if not path.exists() and not path.is_symlink():
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o077
    ):
        os.close(descriptor)
        raise PublicationError("publication lock is unsafe")
    stream = os.fdopen(descriptor, "r+")
    fcntl.flock(stream, fcntl.LOCK_EX)
    return stream


def ledger_path(root: Path, digest: str) -> Path:
    return root / "publication" / f"{digest}.json"


def read_ledger(root: Path, digest: str) -> dict[str, Any] | None:
    path = ledger_path(root, digest)
    if not path.exists() and not path.is_symlink():
        return None
    value = triage.read_json_file(path)
    if (
        set(value) != {"schema_version", "action_digest", "status", "post_id"}
        or value.get("schema_version") != 1
        or value.get("action_digest") != digest
        or value.get("status") not in {"pending", "complete", "not_applied"}
        or (value["post_id"] is not None and not isinstance(value["post_id"], str))
    ):
        raise PublicationError("publication ledger is malformed")
    return cast("dict[str, Any]", value)


def write_ledger(root: Path, digest: str, status: str, post_id: str | None) -> None:
    value = {
        "schema_version": 1,
        "action_digest": digest,
        "status": status,
        "post_id": post_id,
    }
    triage.atomic_private(
        ledger_path(root, digest),
        triage.canonical_json(value) + b"\n",
        triage.state_boundary(),
    )


class PublicationClient:
    def __init__(self, origin: str, token: str):
        self.reader = triage.Client(origin, token)
        self.origin = self.reader.origin
        self.token = token
        self.opener = self.reader.opener

    def get(self, path: str) -> object:
        return self.reader.get(path)

    def post_text(self, payload: dict[str, object]) -> object:
        data = triage.canonical_json(payload)
        request = urllib.request.Request(  # noqa: S310 - origin is normalized HTTPS.
            f"{self.origin}/api/v4/posts",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                content = response.read(triage.MAX_RESPONSE + 1)
            if len(content) > triage.MAX_RESPONSE:
                raise ValueError("response exceeds size limit")
            return json.loads(content)
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 405, 413, 422}:
                raise NotApplied(exc.code) from exc
            raise AmbiguousPost("Mattermost POST outcome is unknown") from exc
        except Exception as exc:
            raise AmbiguousPost("Mattermost POST outcome is unknown") from exc


def expected_payload(action: dict[str, Any]) -> dict[str, object]:
    return {
        "channel_id": action["channel_id"],
        "message": action["message"],
        "props": {"agent_skill_publication_id": action["publication_id"]},
    }


def post_matches(value: object, expected: dict[str, object]) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        return False
    props = value.get("props")
    expected_props = expected["props"]
    return (
        value.get("channel_id") == expected["channel_id"]
        and value.get("message") == expected["message"]
        and isinstance(props, dict)
        and isinstance(expected_props, dict)
        and props.get("agent_skill_publication_id")
        == expected_props.get("agent_skill_publication_id")
    )


def revalidate(action: dict[str, Any]) -> PublicationClient:
    try:
        client = PublicationClient(action["origin"], triage.read_token(action["origin"]))
        me = triage.profile(client.get("/users/me"))
        if me["id"] != action["user_id"]:
            raise PublicationError("authenticated identity changed")
        resolved = triage.channel(client.get(f"/channels/{action['channel_id']}"))
        if resolved["id"] != action["channel_id"]:
            raise PublicationError("target channel changed")
        parsed = triage.exact_target(action["target"], action["origin"])
        teams, _fallback = triage.team_map(client, action["user_id"])
        channels, _errors, successful = triage.team_channels(client, action["user_id"], teams)
        if successful == 0:
            raise PublicationError("no Mattermost team channel list could be revalidated")
        target = triage.resolve_extra(client, parsed, channels, teams)
        if target["id"] != action["channel_id"]:
            raise PublicationError("exact target no longer resolves to the prepared channel")
        if not any(item["id"] == action["channel_id"] for item in channels):
            raise PublicationError("target membership could not be revalidated")
    except triage.TriageError as exc:
        raise PublicationError(str(exc)) from exc
    else:
        return client


def inspect_exact(client: PublicationClient, action: dict[str, Any]) -> str | None:
    since = max(0, int(action["created_at"]) * 1000 - 60_000)
    query = urllib.parse.urlencode({"page": 0, "per_page": triage.PAGE_SIZE, "since": since})
    value = client.get(f"/channels/{action['channel_id']}/posts?{query}")
    if not isinstance(value, dict) or not isinstance(value.get("posts"), dict):
        raise PublicationError("Mattermost inspection response is malformed")
    expected = expected_payload(action)
    matches = [item for item in value["posts"].values() if post_matches(item, expected)]
    if len(matches) > 1:
        raise PublicationError("publication ID matched more than one post")
    return str(matches[0]["id"]) if matches else None


def publish(
    action: dict[str, Any], root: Path, digest: str
) -> tuple[str, str, bool, dict[str, object]]:
    lock = open_lock(root)
    try:
        current, current_root, current_digest = load_action(
            str(root / "actions" / f"{digest}.json"), digest
        )
        if current != action or current_root != root or current_digest != digest:
            raise PublicationError("publication action changed before apply")
        ledger = read_ledger(root, digest)
        if ledger is not None and ledger["status"] == "complete":
            return "already_applied", "already_applied", False, {"post_id": ledger["post_id"]}
        if action["expires_at"] <= int(time.time()):
            raise PublicationError(
                f"publication action expired at {action['expires_at']}; prepare a new analysis"
            )
        client = revalidate(action)
        if ledger is not None and ledger["status"] == "pending":
            post_id = inspect_exact(client, action)
            if post_id is None:
                return "blocked", "unknown", False, {"blocked_stage": "post"}
            write_ledger(root, digest, "complete", post_id)
            return "applied", "applied", False, {"post_id": post_id, "recovered": True}
        write_ledger(root, digest, "pending", None)
        expected = expected_payload(action)
        try:
            response = client.post_text(expected)
            if not post_matches(response, expected):
                raise AmbiguousPost("Mattermost post response is malformed")
            if not isinstance(response, dict):
                raise AmbiguousPost("Mattermost post response is malformed")
            post_id = triage.identifier(response.get("id"), "post ID")
            confirmed = client.get(f"/posts/{urllib.parse.quote(post_id, safe='')}")
            if (
                not isinstance(confirmed, dict)
                or not post_matches(confirmed, expected)
                or confirmed.get("id") != post_id
            ):
                raise AmbiguousPost("Mattermost postcondition could not be verified")
        except NotApplied as exc:
            write_ledger(root, digest, "not_applied", None)
            return "not_applied", "not_applied", False, {"http_status": exc.status}
        except (AmbiguousPost, triage.TriageError):
            return "blocked", "unknown", True, {"blocked_stage": "post"}
        write_ledger(root, digest, "complete", post_id)
        return "applied", "applied", True, {"post_id": post_id}
    finally:
        lock.close()


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    parser.add_argument("command", choices=("publish",))
    parser.add_argument("--action", required=True)
    parser.add_argument("--confirm", required=True)
    try:
        args = parser.parse_args(argv)
        action, root, digest = load_action(args.action, args.confirm)
        status, outcome, external, extra = publish(action, root, digest)
    except (PublicationError, triage.TriageError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        emit("invalid", "not_attempted", False, error=str(exc))
        return 2
    else:
        emit(status, outcome, external, **extra)
        return 1 if status in {"blocked", "not_applied"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
