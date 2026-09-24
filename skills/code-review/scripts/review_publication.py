#!/usr/bin/env python3
"""Apply or inspect one digest-confirmed code-review publication action."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from collections.abc import Iterator

    from shared.references.mutation_process import (
        MutationNotAttempted,
        MutationOutcomeUnknown,
        run_mutation_process,
    )
    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable
    from portable_runtime.mutation_process import (
        MutationNotAttempted,
        MutationOutcomeUnknown,
        run_mutation_process,
    )

SCHEMA = "code-review/publication/v1"


def notes_snapshot(discussions: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for discussion in discussions:
        for note in discussion.get("notes", []):
            if note.get("system") is True:
                continue
            if not isinstance(note.get("id"), int) or not isinstance(note.get("body"), str):
                raise portable.WorkflowError("publication conversation is incomplete")
            result[str(note["id"])] = {
                "discussion": str(discussion["id"]),
                "body": note["body"],
                "author": note.get("author", {}).get("id"),
                "resolved": note.get("resolved"),
                "position": note.get("position"),
            }
    return result


def mr_binding(mr: dict[str, Any]) -> dict[str, Any]:
    return {key: mr.get(key) for key in ("id", "iid", "project_id", "state", "diff_refs", "author")}


def make_command(
    root: Path,
    evidence: dict[str, Any],
    context: dict[str, Any],
    action_id: str,
    argv: list[str],
    value: Any,
    dependencies: dict[str, str],
    *,
    stdin_sha256: str | None = None,
) -> str:
    """Convert runner-owned command arguments into a closed, immutable HTTP action."""
    project = evidence["project"]
    base = f"projects/{project['id']}/merge_requests/{evidence['target']['iid']}"
    body: dict[str, str] | None = None
    payload: dict[str, Any] = {}
    endpoint = base
    method = "POST"
    if argv[1:3] == ["mr", "update"]:
        method = "PUT"
        payload = {"labels": ",".join(value["proposed"])}
    elif argv[1:4] == ["mr", "note", "create"]:
        body_path = next(
            (
                path
                for path in (root / "artifacts" / "review_plan" / "bodies").glob("*.md")
                if hashlib.sha256(path.read_bytes()).hexdigest() == stdin_sha256
            ),
            None,
        )
        if body_path is None:
            raise portable.WorkflowError("line publication body is unavailable")
        body = {"path": str(body_path), "sha256": str(stdin_sha256)}
        payload["body"] = body_path.read_text()
        file_name = argv[argv.index("--file") + 1]
        side = "new" if "--line" in argv else "old"
        flag = "--line" if side == "new" else "--old-line"
        changes = [
            item
            for item in evidence["changed_files"]["items"]
            if item.get(f"{side}_path") == file_name
        ]
        if len(changes) != 1:
            raise portable.WorkflowError(
                "line publication requires one exact changed-file identity"
            )
        payload["position"] = {
            "position_type": "text",
            **evidence["object"]["diff_refs"],
            "new_path": changes[0]["new_path"],
            "old_path": changes[0]["old_path"],
            f"{side}_line": int(argv[argv.index(flag) + 1]),
        }
        endpoint += "/discussions"
    elif argv[1] == "api":
        method = argv[argv.index("--method") + 1]
        endpoint = argv[argv.index("--method") + 2]
        for index, token in enumerate(argv):
            if token not in {"-F", "-f"}:
                continue
            key, text = argv[index + 1].split("=", 1)
            if key in {"body", "description"} and text.startswith("@"):
                path = Path(text[1:])
                content = portable.regular_file(path, "publication body").read_bytes()
                body = {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}
                payload[key] = content.decode()
            else:
                payload[key] = text == "true" if key == "resolved" else text
    else:
        raise portable.WorkflowError("unsupported publication command")
    dependency = None
    if action_id.endswith((":resolve", ":reopen")):
        dependency = dependencies.get(action_id.rsplit(":", 1)[0] + ":reply")
        if dependency is None:
            raise portable.WorkflowError("thread state requires its explanation action")
    guard = {
        "schema": SCHEMA,
        "action_id": action_id,
        "host": project["hostname"],
        "project_id": project["id"],
        "mr_iid": evidence["target"]["iid"],
        "method": method,
        "endpoint": endpoint,
        "payload": payload,
        "body": body,
        "user": {"id": context["current_user_id"], "username": context["current_user_username"]},
        "mr": mr_binding(evidence["object"]),
        "labels": sorted(evidence["object"].get("labels", [])),
        "notes": notes_snapshot(context["discussions"]),
        "dependency": dependency,
        "evidence_digest": context["evidence_digest"],
        "expires_at": int(time.time()) + 24 * 60 * 60,
    }
    validate_guard(guard)
    content = portable.canonical(guard)
    digest = hashlib.sha256(content).hexdigest()
    directory = portable.private_directory(root / "artifacts" / "publication_actions")
    path, _ = portable.write_companion(directory / f"{digest}.json", content.decode())
    dependencies[action_id] = digest
    return shlex.join(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(Path(__file__).resolve()),
            "apply",
            "--action",
            str(path),
            "--confirm",
            digest,
        ]
    )


def validate_guard(guard: dict[str, Any]) -> None:
    if guard.get("schema") != SCHEMA:
        raise portable.WorkflowError("legacy publication requires regeneration")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", str(guard.get("host", ""))):
        raise portable.WorkflowError("invalid publication host")
    for key in ("project_id", "mr_iid"):
        if type(guard.get(key)) is not int or guard[key] < 1:
            raise portable.WorkflowError("invalid publication identity")
    base = f"projects/{guard['project_id']}/merge_requests/{guard['mr_iid']}"
    endpoint, method, payload = guard.get("endpoint"), guard.get("method"), guard.get("payload")
    if not isinstance(endpoint, str) or not isinstance(payload, dict):
        raise portable.WorkflowError("invalid publication request")
    allowed = False
    if method == "PUT" and endpoint == base:
        allowed = set(payload) == {"labels"} and isinstance(payload["labels"], str)
    elif method == "PUT" and re.fullmatch(
        re.escape(base) + r"/discussions/[A-Za-z0-9_-]+", endpoint
    ):
        allowed = (
            set(payload) == {"resolved"}
            and type(payload["resolved"]) is bool
            and portable.is_digest(guard.get("dependency"))
        )
    elif method == "POST" and endpoint == f"projects/{guard['project_id']}/issues":
        allowed = set(payload) == {"title", "description"} and all(
            portable.nonempty_string(x) for x in payload.values()
        )
    elif method == "POST" and (
        endpoint in {base + "/notes", base + "/discussions"}
        or re.fullmatch(re.escape(base) + r"/discussions/[A-Za-z0-9_-]+/notes", endpoint)
    ):
        allowed = set(payload) in ({"body"}, {"body", "position"}) and portable.nonempty_string(
            payload.get("body")
        )
        if "position" in payload:
            position = payload["position"]
            allowed = allowed and endpoint == base + "/discussions" and isinstance(position, dict)
            if allowed:
                side = "new_line" if "new_line" in position else "old_line"
                allowed = (
                    set(position)
                    == {
                        "position_type",
                        "base_sha",
                        "start_sha",
                        "head_sha",
                        "new_path",
                        "old_path",
                        side,
                    }
                    and position["position_type"] == "text"
                    and type(position[side]) is int
                    and position[side] > 0
                )
    if (
        not allowed
        or not isinstance(guard.get("notes"), dict)
        or not isinstance(guard.get("mr"), dict)
    ):
        raise portable.WorkflowError("publication action is outside the closed operation set")
    if not isinstance(guard.get("user"), dict) or type(guard["user"].get("id")) is not int:
        raise portable.WorkflowError("publication identity is incomplete")
    if type(guard.get("expires_at")) is not int or not portable.is_digest(
        guard.get("evidence_digest")
    ):
        raise portable.WorkflowError("publication binding is incomplete")


def load_action(path: Path, digest: str) -> tuple[Path, dict[str, Any]]:
    if (
        not portable.is_digest(digest)
        or path.name != f"{digest}.json"
        or path.parent.name != "publication_actions"
        or path.parent.parent.name != "artifacts"
    ):
        raise portable.WorkflowError("publication action path or digest is invalid")
    root = portable.artifact_root(path.parents[2])
    if path != root / "artifacts" / "publication_actions" / path.name or path != path.resolve():
        raise portable.WorkflowError("publication action path escapes its owner")
    data = portable.regular_file(path, "publication action").read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise portable.WorkflowError("publication action digest changed")
    guard = json.loads(data)
    if not isinstance(guard, dict):
        raise portable.WorkflowError("publication action must be an object")
    validate_guard(guard)
    body = guard["body"]
    if body is not None:
        body_path = Path(body["path"])
        if (
            body_path.parent != root / "artifacts" / "review_plan" / "bodies"
            or body_path != body_path.resolve()
        ):
            raise portable.WorkflowError("publication body escapes its owner")
        data = portable.regular_file(body_path, "publication body").read_bytes()
        if hashlib.sha256(data).hexdigest() != body["sha256"] or data.decode() != guard[
            "payload"
        ].get("body", guard["payload"].get("description")):
            raise portable.WorkflowError("publication body changed")
    return root, guard


@contextmanager
def publication_lock(root: Path) -> Iterator[Path]:
    directory = portable.private_directory(root / "code-review-publication")
    descriptor = os.open(directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o077
        ):
            raise portable.WorkflowError("unsafe publication lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise portable.WorkflowError("another publication is running") from exc
        yield directory
    finally:
        os.close(descriptor)


def page(host: str, endpoint: str) -> list[dict[str, Any]]:
    value = portable.paginated(host, endpoint)
    if value.get("complete") is not True or not all(
        isinstance(item, dict) for item in cast("list[Any]", value["items"])
    ):
        raise portable.WorkflowError("publication evidence is incomplete")
    return cast("list[dict[str, Any]]", value["items"])


def observe(guard: dict[str, Any]) -> dict[str, Any]:
    host = guard["host"]
    base = f"projects/{guard['project_id']}/merge_requests/{guard['mr_iid']}"
    user = portable.glab_json(host, "user")
    mr = portable.glab_json(host, base)
    if (
        not isinstance(user, dict)
        or {key: user.get(key) for key in ("id", "username")} != guard["user"]
    ):
        raise portable.WorkflowError("authenticated publication user changed")
    if not isinstance(mr, dict) or mr_binding(mr) != guard["mr"]:
        raise portable.WorkflowError("reviewed MR identity, refs, author, or state changed")
    result: dict[str, Any] = {"mr": mr, "notes": notes_snapshot(page(host, base + "/discussions"))}
    if guard["endpoint"].endswith("/issues"):
        result["issues"] = page(
            host, guard["endpoint"] + "?state=all&order_by=created_at&sort=desc"
        )
    return result


def postcondition(
    guard: dict[str, Any], observed: dict[str, Any], before: dict[str, Any]
) -> dict[str, Any] | None:
    payload = guard["payload"]
    if "labels" in payload:
        desired = sorted(payload["labels"].split(",")) if payload["labels"] else []
        return {"labels": desired} if sorted(observed["mr"].get("labels", [])) == desired else None
    if "resolved" in payload:
        discussion = guard["endpoint"].rsplit("/", 1)[1]
        notes = [
            note
            for note in observed["notes"].values()
            if note["discussion"] == discussion and note["resolved"] is not None
        ]
        return (
            {"discussion": discussion, "resolved": payload["resolved"]}
            if notes and all(note["resolved"] == payload["resolved"] for note in notes)
            else None
        )
    if "description" in payload:
        previous = {issue["id"] for issue in before.get("issues", [])}
        matches = [
            issue
            for issue in observed.get("issues", [])
            if issue.get("id") not in previous
            and issue.get("project_id") == guard["project_id"]
            and issue.get("author", {}).get("id") == guard["user"]["id"]
            and issue.get("title") == payload["title"]
            and issue.get("description") == payload["description"]
        ]
        return (
            {"issue_id": matches[0]["id"], "issue_iid": matches[0]["iid"]}
            if len(matches) == 1
            else None
        )
    matches = []
    for note_id, note in observed["notes"].items():
        if (
            note_id in before["notes"]
            or note["body"] != payload["body"]
            or note["author"] != guard["user"]["id"]
        ):
            continue
        if (
            "/discussions/" in guard["endpoint"]
            and note["discussion"] != guard["endpoint"].split("/discussions/", 1)[1].split("/")[0]
        ):
            continue
        if "position" in payload and (
            not isinstance(note["position"], dict)
            or any(note["position"].get(key) != value for key, value in payload["position"].items())
        ):
            continue
        matches.append({"note_id": note_id, "note": note})
    return matches[0] if len(matches) == 1 else None


def revalidate(
    guard: dict[str, Any], observed: dict[str, Any], receipts: list[dict[str, Any]]
) -> None:
    expected_notes = dict(guard["notes"])
    labels = guard["labels"]
    for receipt in receipts:
        effect = receipt["effect"]
        if "note_id" in effect:
            expected_notes[effect["note_id"]] = effect["note"]
        if "discussion" in effect:
            expected_notes = {
                key: {**note, "resolved": effect["resolved"]}
                if note["discussion"] == effect["discussion"] and note["resolved"] is not None
                else note
                for key, note in expected_notes.items()
            }
        if "labels" in effect:
            labels = effect["labels"]
    if expected_notes != observed["notes"] or sorted(labels) != sorted(
        observed["mr"].get("labels", [])
    ):
        raise portable.WorkflowError("review conversation or labels changed; regenerate the plan")


def finalized_action(root: Path, guard: dict[str, Any], digest: str) -> None:
    progress = portable.read_json(root / "review-current.json", "review progress")
    if progress.get("stage") != "plan_ready":
        raise portable.WorkflowError("publication requires a finalized current review plan")
    plan_path = Path(progress["plan_path"])
    plan_digest = progress["plan_digest"]
    if plan_path != root / "artifacts" / "review_plan" / f"{plan_digest}.json":
        raise portable.WorkflowError("publication plan path is invalid")
    if (
        hashlib.sha256(portable.regular_file(plan_path, "review plan").read_bytes()).hexdigest()
        != plan_digest
    ):
        raise portable.WorkflowError("publication plan changed")
    _, plan = portable.artifact_payload(plan_path, "review_plan")
    if plan["evidence_digest"] != guard["evidence_digest"] or not any(
        action["id"] == guard["action_id"] and f"--confirm {digest}" in action["command"]
        for action in plan["publication_preview"]["actions"]
    ):
        raise portable.WorkflowError(
            "action does not belong to the current plan; regenerate legacy plans"
        )


def execute(path: Path, digest: str, *, inspect: bool = False) -> dict[str, Any]:
    root, guard = load_action(path, digest)
    with publication_lock(root) as directory:
        ledger_path = directory / "ledger.json"
        ledger = (
            portable.read_json(ledger_path, "publication ledger")
            if ledger_path.exists()
            else {"receipts": [], "pending": None}
        )
        if set(ledger) != {"receipts", "pending"} or not isinstance(ledger["receipts"], list):
            raise portable.WorkflowError("invalid publication ledger")
        receipts = ledger["receipts"]
        if any(receipt["digest"] == digest for receipt in receipts):
            return {
                "status": "already_applied",
                "mutation_outcome": "applied",
                "external_mutations": False,
            }
        pending = ledger["pending"]
        if inspect:
            if pending is None or pending["digest"] != digest:
                return {
                    "status": "not_attempted",
                    "mutation_outcome": "none",
                    "external_mutations": False,
                }
            effect = postcondition(guard, observe(guard), pending["before"])
            if effect is None:
                return {
                    "status": "blocked",
                    "mutation_outcome": "unknown",
                    "external_mutations": False,
                }
        else:
            if pending is not None:
                raise portable.WorkflowError(
                    "unresolved publication blocks writes; inspect its exact action first"
                )
            finalized_action(root, guard, digest)
            if time.time() > guard["expires_at"]:
                raise portable.WorkflowError("publication action expired; regenerate the plan")
            if guard["dependency"] is not None and not any(
                receipt["digest"] == guard["dependency"] for receipt in receipts
            ):
                raise portable.WorkflowError(
                    "publish the thread explanation before changing its state"
                )
            observed = observe(guard)
            related = [
                receipt
                for receipt in receipts
                if receipt["evidence_digest"] == guard["evidence_digest"]
            ]
            revalidate(guard, observed, related)
            executable = shutil.which("glab")
            if executable is None:
                raise portable.WorkflowError("glab is unavailable")
            pending = {"digest": digest, "before": observed}
            ledger["pending"] = pending
            portable.write_json(ledger_path, ledger)
            try:
                result = run_mutation_process(
                    [
                        executable,
                        "api",
                        "--hostname",
                        guard["host"],
                        "--method",
                        guard["method"],
                        guard["endpoint"],
                        "--header",
                        "Content-Type: application/json",
                        "--input",
                        "-",
                    ],
                    portable.canonical(guard["payload"]),
                )
                if result.returncode != 0:
                    raise MutationOutcomeUnknown("publication process failed")
                effect = postcondition(guard, observe(guard), observed)
                if effect is None:
                    raise MutationOutcomeUnknown("publication postcondition is unverified")
            except MutationNotAttempted:
                ledger["pending"] = None
                portable.write_json(ledger_path, ledger)
                raise
            except (MutationOutcomeUnknown, portable.WorkflowError, OSError, ValueError):
                return {
                    "status": "blocked",
                    "mutation_outcome": "unknown",
                    "external_mutations": True,
                }
        receipts.append(
            {"digest": digest, "evidence_digest": guard["evidence_digest"], "effect": effect}
        )
        ledger["pending"] = None
        try:
            portable.write_json(ledger_path, ledger)
        except OSError:
            return {
                "status": "blocked",
                "mutation_outcome": "unknown",
                "external_mutations": not inspect,
            }
        return {
            "status": "applied",
            "mutation_outcome": "applied",
            "external_mutations": not inspect,
        }


def main(argv: list[str] | None = None) -> int:
    parser = portable.ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("mode", nargs="?", choices=("apply", "inspect"))
    parser.add_argument("--action", type=Path)
    parser.add_argument("--confirm")
    try:
        args = parser.parse_args(argv)
        if args.capabilities:
            portable.emit(
                {
                    "schema": SCHEMA,
                    "operations": ["apply", "inspect"],
                    "platform": "posix",
                    "confirmation": "one action SHA-256",
                    "external_mutations": False,
                }
            )
            return 0
        if args.mode is None or args.action is None or args.confirm is None:
            raise portable.WorkflowError("mode, --action and --confirm are required")
        result = execute(args.action, args.confirm, inspect=args.mode == "inspect")
        portable.emit(result)
        return 0 if result["status"] != "blocked" else 1
    except (
        portable.WorkflowError,
        MutationNotAttempted,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        portable.emit(
            {"status": "blocked", "error": portable.redact(str(exc)), "external_mutations": False}
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
