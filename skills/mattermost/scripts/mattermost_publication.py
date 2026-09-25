#!/usr/bin/env python3
"""Apply or inspect one immutable Mattermost publication action."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

sys.dont_write_bytecode = True

_SCRIPT = Path(__file__).with_name("mattermost.py")
_SPEC = importlib.util.spec_from_file_location("mattermost_publication_support", _SCRIPT)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Mattermost publication support is unavailable")
mm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mm
_SPEC.loader.exec_module(mm)

MAX_RESPONSE = 32 * 1024 * 1024


class PublicationError(ValueError):
    """The action is invalid, stale, or unsafe."""


class AmbiguousMutation(PublicationError):
    """A POST may have reached Mattermost and must not be retried."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise PublicationError(message)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


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


def read_private_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(mm.read_private_bytes(path, limit=1024 * 1024))
    except (OSError, json.JSONDecodeError, mm.MattermostError) as exc:
        raise PublicationError("publication state is unavailable or unsafe") from exc
    if not isinstance(value, dict):
        raise PublicationError("publication state is malformed")
    return value


def secure_body(path: Path, digest: str) -> str:
    try:
        data: bytes = mm.read_private_bytes(path)
        value: str = data.decode("utf-8")
    except (OSError, UnicodeDecodeError, mm.MattermostError) as exc:
        raise PublicationError("publication body is unavailable or unsafe") from exc
    if hashlib.sha256(data).hexdigest() != digest:
        raise PublicationError("publication body digest does not match")
    return value


def load_action(path_value: str, confirmation: str) -> tuple[dict[str, Any], Path, Path]:
    path = Path(path_value)
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise PublicationError("action path must be normalized and absolute")
    if not mm.re.fullmatch(r"[a-f0-9]{64}", confirmation):
        raise PublicationError("confirmation digest is invalid")
    action = read_private_json(path)
    if hashlib.sha256(canonical(action)).hexdigest() != confirmation:
        raise PublicationError("action is stale or tampered")
    required = {
        "schema_version",
        "plan_id",
        "origin",
        "user_id",
        "target",
        "channel_id",
        "channel_type",
        "team_id",
        "root_id",
        "body_digest",
        "body_path",
        "files",
        "publication_id",
        "created_at",
        "expires_at",
    }
    if set(action) != required or action.get("schema_version") != 1:
        raise PublicationError("action schema is invalid")
    try:
        root = mm.publication_state_root(action["origin"], action["user_id"], create=False)
    except (KeyError, TypeError, mm.MattermostError) as exc:
        raise PublicationError("action identity is invalid") from exc
    expected = root / "actions" / f"{confirmation}.json"
    if path != expected:
        raise PublicationError("action path does not match its bound identity")
    mm.require_private_directory(root / "actions")
    mm.require_private_directory(root / "bodies")
    mm.require_private_directory(root / "plans")
    mm.require_private_directory(root / "plan-index")
    pointer = read_private_json(root / "plan-index" / f"{action['plan_id']}.json")
    plan_path = Path(pointer.get("path", ""))
    plan = read_private_json(plan_path)
    plan_digest = hashlib.sha256(canonical(plan)).hexdigest()
    if (
        pointer != {"digest": plan_digest, "path": str(plan_path), "plan_id": plan.get("plan_id")}
        or plan_path != root / "plans" / f"{plan_digest}.json"
        or not plan.get("finalized")
        or plan.get("plan_id") != action["plan_id"]
        or plan.get("origin") != action["origin"]
        or plan.get("user_id") != action["user_id"]
        or plan.get("expires_at") != action["expires_at"]
        or {"digest": confirmation, "path": str(path)} not in plan.get("actions", [])
    ):
        raise PublicationError("action is not a member of its finalized plan")
    if not isinstance(action.get("expires_at"), int):
        raise PublicationError("action expiry is invalid")
    return action, root, path


def validate_sources(action: dict[str, Any]) -> tuple[str, list[dict[str, object]]]:
    body_path = Path(action["body_path"])
    body = secure_body(body_path, action["body_digest"])
    files = action.get("files")
    if not isinstance(files, list) or len(files) > 5:
        raise PublicationError("action file list is invalid")
    observed: list[dict[str, object]] = []
    for expected in files:
        if not isinstance(expected, dict):
            raise PublicationError("action file metadata is invalid")
        try:
            metadata = mm.publication_file_metadata(expected.get("path"))
        except mm.MattermostError as exc:
            raise PublicationError(str(exc)) from exc
        if metadata != expected:
            raise PublicationError("publication source file changed after preparation")
        observed.append(metadata)
    if not body and not observed:
        raise PublicationError("empty publication has no files")
    return body, observed


def source_bytes(expected: dict[str, object]) -> bytes:
    path = Path(str(expected["path"]))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        data = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            data.extend(chunk)
            if len(data) > mm.MAX_PUBLICATION_FILE:
                raise PublicationError("publication file exceeds 100 MiB")
        after = os.fstat(descriptor)
    except OSError as exc:
        raise PublicationError("publication source file is unavailable") from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    stable = (
        stat.S_ISREG(before.st_mode)
        and before.st_uid == os.getuid()
        and before.st_nlink == 1
        and all(
            getattr(before, key) == getattr(after, key)
            for key in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        )
    )
    metadata = {
        "path": str(path),
        "name": path.name,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if not stable or metadata != expected:
        raise PublicationError("publication source file changed after preparation")
    return bytes(data)


def validate_access(action: dict[str, Any]) -> tuple[str, Any]:
    try:
        token = mm.read_token(action["origin"])
        client = PublicationClient(action["origin"], token)
        user_id = mm.user_identity(client)
        if user_id != action["user_id"]:
            raise PublicationError("current Mattermost identity does not match the action")
        target = mm.classify_url(action["target"])
        frozen = mm.publication_channel(client, target, user_id)
    except (KeyError, TypeError, mm.MattermostError) as exc:
        if isinstance(exc, PublicationError):
            raise
        raise PublicationError(str(exc)) from exc
    expected = {key: action[key] for key in ("channel_id", "channel_type", "team_id", "root_id")}
    if frozen != expected:
        raise PublicationError("Mattermost target no longer matches the prepared action")
    return token, client


class PublicationClient:
    def __init__(self, origin: str, token: str):
        self.reader = mm.Client(origin, token)
        self.origin: str = self.reader.origin
        self.token = token
        self.opener: Any = self.reader.opener

    def get(self, path: str) -> object:
        return self.reader.get(path)

    def _post(self, path: str, data: bytes, content_type: str) -> object:
        if not path.startswith("/") or "://" in path or ".." in path.split("/"):
            raise PublicationError("unsafe Mattermost API path")
        # The origin was normalized to exact HTTPS and redirects are disabled.
        request = urllib.request.Request(  # noqa: S310
            f"{self.origin}/api/v4{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                result = response.read(MAX_RESPONSE + 1)
            if len(result) > MAX_RESPONSE:
                raise ValueError("response too large")
            return json.loads(result)
        except Exception as exc:
            raise AmbiguousMutation("Mattermost POST outcome is unknown") from exc

    def upload(self, channel_id: str, name: str, data: bytes) -> object:
        query = urllib.parse.urlencode({"channel_id": channel_id, "filename": name})
        return self._post(f"/files?{query}", data, "application/octet-stream")

    def create_post(self, payload: dict[str, object]) -> object:
        return self._post("/posts", canonical(payload), "application/json")


def replace_ledger(path: Path, value: dict[str, Any]) -> None:
    try:
        mm.replace_private(path, canonical(value) + b"\n")
    except mm.MattermostError as exc:
        raise PublicationError("publication ledger could not be persisted") from exc


def open_lock(root: Path) -> Any:
    path = root / "publication.lock"
    if not path.exists() and not path.is_symlink():
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
        except OSError as exc:
            raise PublicationError("publication lock could not be created") from exc
    try:
        descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise PublicationError("publication lock is unsafe")
        stream = os.fdopen(descriptor, "r+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX)
        except OSError:
            stream.close()
            raise
    except (OSError, mm.MattermostError) as exc:
        raise PublicationError("publication lock is unsafe") from exc
    else:
        return stream


def ledger_state(root: Path, digest: str) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    path = root / "publication-ledger.json"
    if path.exists() or path.is_symlink():
        ledger = read_private_json(path)
        if set(ledger) != {"schema_version", "actions"} or ledger["schema_version"] != 1:
            raise PublicationError("publication ledger is malformed")
        if not isinstance(ledger.get("actions"), dict):
            raise PublicationError("publication ledger is malformed")
    else:
        ledger = {"schema_version": 1, "actions": {}}
    state = ledger["actions"].get(digest)
    if state is not None and not isinstance(state, dict):
        raise PublicationError("publication ledger action is malformed")
    return path, ledger, state


def expected_post(action: dict[str, Any], body: str, file_ids: list[str]) -> dict[str, object]:
    return {
        "channel_id": action["channel_id"],
        "message": body,
        "root_id": action["root_id"],
        "file_ids": file_ids,
        "props": {"agent_skill_publication_id": action["publication_id"]},
    }


def post_matches(value: object, expected: dict[str, object]) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        return False
    props = value.get("props")
    expected_props = expected.get("props")
    return (
        all(
            value.get(key) == expected[key]
            for key in ("channel_id", "message", "root_id", "file_ids")
        )
        and isinstance(props, dict)
        and isinstance(expected_props, dict)
        and props.get("agent_skill_publication_id")
        == expected_props.get("agent_skill_publication_id")
    )


def inspect_remote(
    client: PublicationClient, action: dict[str, Any], expected: dict[str, object]
) -> str | None:
    root_id = action["root_id"]
    if root_id:
        value = client.get(f"/posts/{urllib.parse.quote(root_id, safe='')}/thread")
        posts, malformed = mm.valid_posts(value)
        if malformed:
            raise PublicationError("Mattermost inspection response is malformed")
    else:
        posts = []
        before: str | None = None
        cursors: set[str] = set()
        boundary = int(action["created_at"]) * 1000
        for _page in range(mm.MAX_PAGES):
            query = {"page": "0", "per_page": str(mm.PAGE_SIZE)}
            if before is not None:
                query["before"] = before
            value = client.get(
                f"/channels/{urllib.parse.quote(action['channel_id'], safe='')}/posts?"
                f"{urllib.parse.urlencode(query)}"
            )
            page_posts, ordered, order, malformed = mm.channel_post_page(value)
            if malformed:
                raise PublicationError("Mattermost inspection response is malformed")
            posts.extend(post for post in page_posts if post["create_at"] >= boundary)
            if not ordered or len(order) < mm.PAGE_SIZE or ordered[-1]["create_at"] < boundary:
                break
            before = order[-1]
            if before in cursors:
                raise PublicationError("Mattermost inspection pagination repeated a cursor")
            cursors.add(before)
        else:
            raise PublicationError("Mattermost inspection exceeded the page limit")
    matches = [post for post in posts if post_matches(post, expected)]
    if len(matches) > 1:
        raise PublicationError("publication ID matched more than one post")
    return str(matches[0]["id"]) if matches else None


def verify_upload(value: object, expected_name: str) -> str:
    if not isinstance(value, dict) or not isinstance(value.get("file_infos"), list):
        raise AmbiguousMutation("Mattermost upload response is malformed")
    infos = value["file_infos"]
    if len(infos) != 1 or not isinstance(infos[0], dict):
        raise AmbiguousMutation("Mattermost upload response is malformed")
    info = infos[0]
    try:
        file_id = mm.identifier(info.get("id"), "file ID")
    except mm.MattermostError as exc:
        raise AmbiguousMutation("Mattermost upload response is malformed") from exc
    if info.get("name") != expected_name:
        raise AmbiguousMutation("Mattermost upload response did not confirm the exact file")
    return str(file_id)


def apply(  # noqa: PLR0911
    action: dict[str, Any], root: Path, digest: str
) -> tuple[str, str, bool, dict[str, object]]:
    lock = open_lock(root)
    try:
        current, current_root, _path = load_action(str(root / "actions" / f"{digest}.json"), digest)
        if current_root != root or current != action:
            raise PublicationError("publication action changed before apply")
        ledger_path, ledger, state = ledger_state(root, digest)
        if state is not None and state.get("status") == "complete":
            return "already_applied", "already_applied", False, {"post_id": state.get("post_id")}
        if state is None and action["expires_at"] <= mm.now():
            raise PublicationError("action has expired; prepare a new plan")
        if state is None:
            state = {"status": "pending", "uploads": [], "stage": None}
            ledger["actions"][digest] = state
            replace_ledger(ledger_path, ledger)
        uploads = state.get("uploads")
        if not isinstance(uploads, list) or not all(isinstance(item, str) for item in uploads):
            raise PublicationError("publication ledger upload progress is malformed")
        stage = state.get("stage")
        if action["expires_at"] <= mm.now() and not uploads and stage is None:
            raise PublicationError("action expired before any external mutation started")
        if isinstance(stage, dict) and stage.get("kind") == "upload":
            return "blocked", "unknown", False, {"blocked_stage": f"upload:{stage.get('index')}"}
        try:
            body = secure_body(Path(action["body_path"]), action["body_digest"])
        except PublicationError:
            if isinstance(stage, dict) and stage.get("kind") == "post":
                return "blocked", "unknown", False, {"blocked_stage": "post"}
            raise
        expected = expected_post(action, body, uploads)
        if isinstance(stage, dict) and stage.get("kind") == "post":
            try:
                _token, client = validate_access(action)
                post_id = inspect_remote(client, action, expected)
            except (PublicationError, mm.MattermostError):
                return "blocked", "unknown", False, {"blocked_stage": "post"}
            if post_id is None:
                return "blocked", "unknown", False, {"blocked_stage": "post"}
            state.update({"status": "complete", "stage": None, "post_id": post_id})
            replace_ledger(ledger_path, ledger)
            return "applied", "applied", False, {"post_id": post_id, "recovered": True}
        body, files = validate_sources(action)
        _token, client = validate_access(action)
        for index in range(len(uploads), len(files)):
            data = source_bytes(files[index])
            state["stage"] = {"kind": "upload", "index": index}
            replace_ledger(ledger_path, ledger)
            try:
                response = client.upload(action["channel_id"], str(files[index]["name"]), data)
                file_id = verify_upload(response, str(files[index]["name"]))
            except AmbiguousMutation:
                return "blocked", "unknown", True, {"blocked_stage": f"upload:{index}"}
            uploads.append(file_id)
            state["stage"] = None
            try:
                replace_ledger(ledger_path, ledger)
            except PublicationError:
                return "blocked", "unknown", True, {"blocked_stage": f"upload:{index}"}
        payload = expected_post(action, body, uploads)
        state["stage"] = {"kind": "post"}
        replace_ledger(ledger_path, ledger)
        result: tuple[str, str, bool, dict[str, object]]
        try:
            response = client.create_post(payload)
            if not post_matches(response, payload):
                raise AmbiguousMutation("Mattermost post response is malformed")
            post_id = mm.identifier(response.get("id"), "post ID")
            confirmed = client.get(f"/posts/{urllib.parse.quote(post_id, safe='')}")
            if not post_matches(confirmed, payload) or confirmed.get("id") != post_id:
                raise AmbiguousMutation("Mattermost postcondition could not be verified")
        except (AmbiguousMutation, mm.MattermostError):
            result = "blocked", "unknown", True, {"blocked_stage": "post"}
        else:
            state.update({"status": "complete", "stage": None, "post_id": post_id})
            try:
                replace_ledger(ledger_path, ledger)
            except PublicationError:
                result = "blocked", "unknown", True, {"blocked_stage": "post"}
            else:
                result = "applied", "applied", True, {"post_id": post_id}
        return result
    finally:
        lock.close()


def inspect(
    action: dict[str, Any], root: Path, digest: str
) -> tuple[str, str, bool, dict[str, object]]:
    lock = open_lock(root)
    try:
        current, current_root, _path = load_action(str(root / "actions" / f"{digest}.json"), digest)
        if current_root != root or current != action:
            raise PublicationError("publication action changed before inspect")
        ledger_path = root / "publication-ledger.json"
        if not ledger_path.exists() and not ledger_path.is_symlink():
            return "blocked", "not_started", False, {}
        path, ledger, state = ledger_state(root, digest)
        result: tuple[str, str, bool, dict[str, object]]
        if state is None:
            result = "blocked", "not_started", False, {}
        elif state.get("status") == "complete":
            result = "already_applied", "already_applied", False, {"post_id": state.get("post_id")}
        else:
            uploads = state.get("uploads")
            stage = state.get("stage")
            if not isinstance(uploads, list) or not all(isinstance(item, str) for item in uploads):
                raise PublicationError("publication ledger upload progress is malformed")
            if isinstance(stage, dict) and stage.get("kind") == "upload":
                result = (
                    "blocked",
                    "unknown",
                    False,
                    {"blocked_stage": f"upload:{stage.get('index')}"},
                )
            elif isinstance(stage, dict) and stage.get("kind") == "post":
                try:
                    body = secure_body(Path(action["body_path"]), action["body_digest"])
                    _token, client = validate_access(action)
                    post_id = inspect_remote(client, action, expected_post(action, body, uploads))
                except (PublicationError, mm.MattermostError):
                    result = "blocked", "unknown", False, {"blocked_stage": "post"}
                    return result
                if post_id is None:
                    result = "blocked", "unknown", False, {"blocked_stage": "post"}
                else:
                    state.update({"status": "complete", "stage": None, "post_id": post_id})
                    replace_ledger(path, ledger)
                    result = "applied", "applied", False, {"post_id": post_id, "recovered": True}
            else:
                result = "blocked", "in_progress", False, {"uploaded_files": len(uploads)}
        return result
    finally:
        lock.close()


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    parser.add_argument("mode", choices=("apply", "inspect"))
    parser.add_argument("--action", required=True)
    parser.add_argument("--confirm", required=True)
    try:
        args = parser.parse_args(argv)
        action, root, _path = load_action(args.action, args.confirm)
        result = (
            apply(action, root, args.confirm)
            if args.mode == "apply"
            else inspect(action, root, args.confirm)
        )
        status, outcome, external, extra = result
        emit(status, outcome, external, **extra)
    except (PublicationError, mm.MattermostError, OSError, KeyError, TypeError) as exc:
        emit("invalid", "not_attempted", False, error=str(exc))
        return 2
    else:
        return 1 if status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
