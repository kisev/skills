#!/usr/bin/env python3
"""Apply one digest-confirmed code-review publication action."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, cast
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

if TYPE_CHECKING:
    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable  # noqa: E402


MARKER_RE = re.compile(
    r"<!-- code-review:id=(?P<id>[A-Za-z0-9][A-Za-z0-9._-]{0,63});"
    r"revision=(?P<revision>[1-9][0-9]*);kind=(?P<kind>finding|thread|issue);"
    r"target=(?P<target>[a-f0-9]{16}) -->"
)
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_PAGES = 20


class BlockedError(Exception):
    """The confirmed action cannot be applied to the current remote state."""


class MutationError(Exception):
    """A mutation result is uncertain and requires remote observation."""


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, label: str, *, boundary: Path | None = None) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise portable.WorkflowError(f"{label} path must be an absolute regular file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise portable.WorkflowError(f"{label} is unavailable") from exc
    if resolved != path or boundary is not None and not resolved.is_relative_to(boundary):
        raise portable.WorkflowError(f"{label} path escapes its bounded directory")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise portable.WorkflowError(f"{label} is unreadable") from exc
    if not content or len(content) > portable.MAX_BYTES:
        raise portable.WorkflowError(f"{label} has an invalid size")
    try:
        value = json.loads(content, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise portable.WorkflowError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise portable.WorkflowError(f"{label} must contain a JSON object")
    return value


def file_bytes(path: Path, label: str, boundary: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise portable.WorkflowError(f"{label} path must be an absolute regular file")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise portable.WorkflowError(f"{label} is unavailable") from exc
    if resolved != path or not resolved.is_relative_to(boundary):
        raise portable.WorkflowError(f"{label} path escapes its bounded directory")
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise portable.WorkflowError(f"{label} is unreadable") from exc
    if not value or len(value) > portable.MAX_BYTES:
        raise portable.WorkflowError(f"{label} has an invalid size")
    return value


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_plan(plan_value: str) -> tuple[Path, dict[str, Any], str, Path]:
    supplied = Path(plan_value)
    pointer: dict[str, Any] | None = None
    if supplied.name == "review-baseline.json":
        root = supplied.parent.resolve()
        pointer = read_json(supplied, "review baseline", boundary=root)
        if set(pointer) != {
            "contract_version",
            "target",
            "plan_path",
            "plan_digest",
            "markdown_path",
            "markdown_digest",
            "updated_at",
        }:
            raise portable.WorkflowError("review baseline has an invalid shape")
        plan_digest = pointer.get("plan_digest")
        plan_path = Path(str(pointer.get("plan_path", "")))
        if not portable.is_digest(plan_digest):
            raise portable.WorkflowError("review baseline plan digest is invalid")
        expected = root / "artifacts" / "review_plan" / f"{plan_digest}.json"
        if plan_path != expected:
            raise portable.WorkflowError("review baseline plan path is invalid")
    else:
        plan_path = supplied
        if not plan_path.is_absolute() or len(plan_path.parents) < 3:
            raise portable.WorkflowError("review plan path is invalid")
        root = plan_path.parents[2]
        if plan_path.parent != root / "artifacts" / "review_plan":
            raise portable.WorkflowError("review plan is outside its artifact collection")
        plan_digest = plan_path.stem
        if not portable.is_digest(plan_digest):
            raise portable.WorkflowError("review plan filename is not content-addressed")
    content = file_bytes(plan_path, "review plan", root)
    if sha256(content) != plan_digest:
        raise portable.WorkflowError("review plan digest changed")
    try:
        strict_plan = json.loads(content, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise portable.WorkflowError("review plan is not strict JSON") from exc
    if not isinstance(strict_plan, dict):
        raise portable.WorkflowError("review plan envelope is invalid")
    _, payload = portable.artifact_payload(plan_path, "review_plan")
    if strict_plan.get("payload") != payload:
        raise portable.WorkflowError("review plan payload is ambiguous")
    if pointer is not None and payload.get("target") != pointer.get("target"):
        raise portable.WorkflowError("review baseline target does not match the immutable plan")
    if (
        payload.get("profile") != "code-review"
        or payload.get("review_contract_version") != 2
        or payload.get("complete") is not True
        or payload.get("external_mutations") is not False
    ):
        raise portable.WorkflowError("review plan is incomplete or not executable")
    return plan_path, payload, cast(str, plan_digest), root


def select_action(
    plan: dict[str, Any], action_id: str, confirmation: str, root: Path
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    preview = plan.get("publication_preview")
    if not isinstance(preview, dict):
        raise portable.WorkflowError("review plan has no publication preview")
    actions = preview.get("actions")
    if not isinstance(actions, list):
        raise portable.WorkflowError("review plan has no structured publication actions")
    matches = [item for item in actions if isinstance(item, dict) and item.get("id") == action_id]
    if len(matches) != 1:
        raise portable.WorkflowError("publication action identity is unavailable or ambiguous")
    action = cast(dict[str, Any], matches[0])
    spec = action.get("spec")
    if not isinstance(spec, dict) or action.get("sha256") != portable.digest(spec):
        raise portable.WorkflowError("publication action digest changed")
    if confirmation != action["sha256"]:
        raise portable.WorkflowError("publication action confirmation digest does not match")
    preflight_path = Path(str(preview.get("preflight_path", "")))
    preflight_content = file_bytes(preflight_path, "publication preflight", root)
    if sha256(preflight_content) != preview.get("preflight_sha256") or spec.get(
        "preflight_sha256"
    ) != preview.get("preflight_sha256"):
        raise portable.WorkflowError("publication preflight digest changed")
    try:
        preflight = json.loads(preflight_content, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise portable.WorkflowError("publication preflight is not strict JSON") from exc
    if not isinstance(preflight, dict):
        raise portable.WorkflowError("publication preflight is invalid")
    body_text: str | None = None
    body = spec.get("body")
    if body is not None:
        if not isinstance(body, dict) or set(body) != {"path", "sha256"}:
            raise portable.WorkflowError("publication action body binding is invalid")
        body_path = Path(str(body["path"]))
        body_bytes = file_bytes(body_path, "publication body", root)
        if sha256(body_bytes) != body.get("sha256"):
            raise portable.WorkflowError("publication body digest changed")
        try:
            body_text = body_bytes.decode()
        except UnicodeDecodeError as exc:
            raise portable.WorkflowError("publication body is not UTF-8") from exc
        marker = MARKER_RE.search(body_text)
        publication = spec.get("publication")
        if (
            marker is None
            or body_text[marker.end() :].strip()
            or not isinstance(publication, dict)
            or marker.group("id") != publication.get("id")
            or int(marker.group("revision")) != publication.get("revision")
            or marker.group("kind") != publication.get("kind")
        ):
            raise portable.WorkflowError("publication body marker does not bind the action")
    return action, cast(dict[str, Any], preflight), body_text


class GlabClient:
    def __init__(self, hostname: str) -> None:
        if re.fullmatch(r"[a-z0-9.-]+", hostname) is None:
            raise portable.WorkflowError("publication hostname is invalid")
        executable = shutil.which("glab")
        if executable is None:
            raise portable.WorkflowError("glab is unavailable; install and authenticate it")
        self.executable = executable
        self.hostname = hostname

    def request(self, method: str, endpoint: str, payload: object | None = None) -> object:
        argv = [
            self.executable,
            "api",
            "--hostname",
            self.hostname,
            "--method",
            method,
        ]
        input_value: bytes | None = None
        if payload is not None:
            argv.extend(["--input", "-"])
            input_value = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        argv.append(endpoint)
        try:
            completed = subprocess.run(
                argv,
                input=input_value,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            if method == "GET":
                raise BlockedError("GitLab revalidation could not be completed") from exc
            raise MutationError("GitLab mutation result is unknown") from exc
        if len(completed.stdout) > MAX_OUTPUT_BYTES or len(completed.stderr) > MAX_OUTPUT_BYTES:
            raise BlockedError("GitLab response exceeds the size limit")
        if completed.returncode:
            if method == "GET":
                raise BlockedError("GitLab revalidation failed")
            raise MutationError("GitLab mutation returned a non-zero status")
        if not completed.stdout.strip():
            return None
        try:
            return json.loads(completed.stdout, object_pairs_hook=reject_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            if method == "GET":
                raise BlockedError("GitLab revalidation returned invalid JSON") from exc
            raise MutationError("GitLab mutation returned invalid JSON") from exc

    def paginated(self, endpoint: str) -> list[object]:
        result: list[object] = []
        page_digests: set[str] = set()
        for page in range(1, MAX_PAGES + 1):
            separator = "&" if "?" in endpoint else "?"
            value = self.request("GET", f"{endpoint}{separator}per_page=100&page={page}")
            if not isinstance(value, list):
                raise BlockedError("GitLab pagination response is not an array")
            digest = portable.digest(value)
            if digest in page_digests:
                raise BlockedError("GitLab pagination repeated a page")
            page_digests.add(digest)
            result.extend(value)
            if len(value) < 100:
                return result
        raise BlockedError("GitLab pagination exceeded its protective limit")


def normalized_catalog(values: list[object]) -> list[dict[str, str | None]]:
    result: list[dict[str, str | None]] = []
    names: set[str] = set()
    folded: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or not portable.nonempty_string(value.get("name")):
            raise BlockedError("live project label catalog is invalid")
        name = cast(str, value["name"])
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise BlockedError("live project label description is invalid")
        if name in names or name.casefold() in folded:
            raise BlockedError("live project label catalog contains duplicate names")
        names.add(name)
        folded.add(name.casefold())
        result.append({"name": name, "description": description})
    return sorted(result, key=lambda item: (cast(str, item["name"]).casefold(), item["name"]))


def collect_live(client: GlabClient, preflight: dict[str, Any]) -> dict[str, Any]:
    if (
        set(preflight) != {"schema", "actor", "target", "mr", "labels"}
        or preflight.get("schema") != "code-review/publication-preflight/v1"
    ):
        raise portable.WorkflowError("publication preflight has an invalid shape")
    actor = cast(dict[str, Any], preflight["actor"])
    target = cast(dict[str, Any], preflight["target"])
    expected_mr = cast(dict[str, Any], preflight["mr"])
    expected_labels = cast(dict[str, Any], preflight["labels"])
    current_user = client.request("GET", "user")
    project_path = cast(str, target["project_path"])
    project = client.request("GET", f"projects/{quote(project_path, safe='')}")
    endpoint = f"projects/{target['project_id']}/merge_requests/{target['mr_iid']}"
    mr = client.request("GET", endpoint)
    labels = normalized_catalog(
        client.paginated(f"projects/{target['project_id']}/labels?include_ancestor_groups=true")
    )
    if (
        not isinstance(current_user, dict)
        or current_user.get("id") != actor.get("id")
        or current_user.get("username") != actor.get("username")
        or not isinstance(project, dict)
        or project.get("id") != target.get("project_id")
        or project.get("path_with_namespace") != project_path
        or not isinstance(mr, dict)
        or mr.get("iid") != target.get("mr_iid")
        or mr.get("web_url") != target.get("mr_url")
        or mr.get("state") != expected_mr.get("state")
        or mr.get("diff_refs") != expected_mr.get("diff_refs")
        or portable.digest(labels) != expected_labels.get("catalog_sha256")
        or labels != expected_labels.get("catalog")
    ):
        raise BlockedError("GitLab actor, target, refs, state, or label catalog changed")
    current_labels = mr.get("labels")
    if not isinstance(current_labels, list) or not all(
        isinstance(item, str) for item in current_labels
    ):
        raise BlockedError("live MR labels are invalid")
    normalized_current = sorted(set(cast(list[str], current_labels)), key=str.casefold)
    if len(normalized_current) != len(current_labels) or tuple(normalized_current) not in {
        tuple(expected_labels["current"]),
        tuple(expected_labels["proposed"]),
    }:
        raise BlockedError("MR labels changed outside the confirmed plan")
    return {
        "actor": current_user,
        "project": project,
        "mr": mr,
        "labels": normalized_current,
        "endpoint": endpoint,
    }


def meaningful_notes(discussion: dict[str, Any]) -> list[dict[str, Any]]:
    notes = discussion.get("notes")
    if not isinstance(notes, list):
        raise BlockedError("GitLab discussion notes are invalid")
    return [
        note
        for note in notes
        if isinstance(note, dict)
        and note.get("system") is not True
        and isinstance(note.get("body"), str)
    ]


def load_discussions(client: GlabClient, endpoint: str) -> list[dict[str, Any]]:
    values = client.paginated(f"{endpoint}/discussions")
    if not all(isinstance(item, dict) for item in values):
        raise BlockedError("GitLab discussions are invalid")
    return cast(list[dict[str, Any]], values)


def load_notes(client: GlabClient, endpoint: str) -> list[dict[str, Any]]:
    values = client.paginated(f"{endpoint}/notes?sort=asc")
    if not all(isinstance(item, dict) for item in values):
        raise BlockedError("GitLab notes are invalid")
    return cast(list[dict[str, Any]], values)


def validate_expected_source(
    client: GlabClient, live: dict[str, Any], spec: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    expected = cast(dict[str, Any], spec["expected"])
    discussions = load_discussions(client, cast(str, live["endpoint"]))
    notes = load_notes(client, cast(str, live["endpoint"]))
    expected_thread = expected.get("thread")
    selected: dict[str, Any] | None = None
    if expected_thread is not None:
        if not isinstance(expected_thread, dict):
            raise portable.WorkflowError("publication thread expectation is invalid")
        matches = [
            item
            for item in discussions
            if str(item.get("id")) == str(expected_thread.get("discussion_id"))
        ]
        if len(matches) != 1:
            raise BlockedError("publication discussion changed or disappeared")
        selected = matches[0]
        values = meaningful_notes(selected)
        if not values:
            raise BlockedError("publication discussion has no meaningful notes")
        latest = values[-1]
        root = values[0]
        if (
            str(root.get("id")) != str(expected_thread.get("root_note_id"))
            or root.get("resolvable") is not expected_thread.get("resolvable")
            or root.get("resolved") is not expected_thread.get("resolved")
            or latest.get("id") != expected_thread.get("last_note_id")
            or sha256(cast(str, latest["body"]).encode())
            != expected_thread.get("last_note_body_sha256")
        ):
            raise BlockedError("publication discussion changed after preview")
    expected_note = expected.get("note")
    if expected_note is not None:
        if not isinstance(expected_note, dict):
            raise portable.WorkflowError("publication note expectation is invalid")
        matches = [
            item for item in notes if str(item.get("id")) == str(expected_note.get("note_id"))
        ]
        if (
            len(matches) != 1
            or not isinstance(matches[0].get("body"), str)
            or sha256(cast(str, matches[0]["body"]).encode()) != expected_note.get("body_sha256")
        ):
            raise BlockedError("publication note changed after preview")
    return selected, discussions, notes


def observe_body(
    action: dict[str, Any],
    body_text: str,
    actor: dict[str, Any],
    discussions: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    body_digest = sha256(body_text.encode())
    matches: list[dict[str, Any]] = []
    if action["kind"] == "issue":
        for issue in issues:
            if (
                isinstance(issue.get("description"), str)
                and sha256(cast(str, issue["description"]).encode()) == body_digest
                and isinstance(issue.get("author"), dict)
                and cast(dict[str, Any], issue["author"]).get("username") == actor.get("username")
            ):
                matches.append({"issue": issue})
        return matches
    discussion_note_ids: set[str] = set()
    for discussion in discussions:
        for index, note in enumerate(meaningful_notes(discussion)):
            discussion_note_ids.add(str(note.get("id")))
            if (
                sha256(cast(str, note["body"]).encode()) == body_digest
                and isinstance(note.get("author"), dict)
                and cast(dict[str, Any], note["author"]).get("username") == actor.get("username")
            ):
                matches.append({"discussion": discussion, "note": note, "root": index == 0})
    for note in notes:
        if str(note.get("id")) in discussion_note_ids or not isinstance(note.get("body"), str):
            continue
        if (
            sha256(cast(str, note["body"]).encode()) == body_digest
            and isinstance(note.get("author"), dict)
            and cast(dict[str, Any], note["author"]).get("username") == actor.get("username")
        ):
            matches.append({"note": note, "root": True})
    return matches


def validate_observed_location(
    observed: dict[str, Any], spec: dict[str, Any], preflight: dict[str, Any]
) -> None:
    operation = spec["operation"]
    expected = cast(dict[str, Any], spec["expected"])
    mutation = cast(dict[str, Any], spec["mutation"])
    if operation in {"create_general", "create_line"}:
        if "discussion" not in observed or observed.get("root") is not True:
            raise BlockedError("published finding marker is in the wrong location")
        if operation == "create_line":
            note = cast(dict[str, Any], observed["note"])
            position = note.get("position")
            refs = cast(dict[str, Any], cast(dict[str, Any], preflight["mr"])["diff_refs"])
            if not isinstance(position, dict) or any(
                position.get(key) != refs[key] for key in ("base_sha", "start_sha", "head_sha")
            ):
                raise BlockedError("published line finding position changed")
            if (
                position.get("new_path") != mutation["path"]
                and position.get("old_path") != mutation["path"]
                or mutation.get("line") is not None
                and position.get("new_line") != mutation["line"]
                or mutation.get("old_line") is not None
                and position.get("old_line") != mutation["old_line"]
            ):
                raise BlockedError("published line finding location changed")
    elif operation in {"reply", "resolve", "reopen"}:
        thread = expected.get("thread")
        if isinstance(thread, dict):
            discussion = observed.get("discussion")
            if (
                not isinstance(discussion, dict)
                or str(discussion.get("id")) != str(thread["discussion_id"])
                or observed.get("root") is not False
            ):
                raise BlockedError("published reply marker is in the wrong discussion")
        elif "discussion" in observed:
            raise BlockedError("published standalone reply marker is in a discussion")
    elif operation == "update_issue":
        issue = observed.get("issue")
        expected_issue = expected.get("issue")
        if (
            not isinstance(issue, dict)
            or not isinstance(expected_issue, dict)
            or issue.get("iid") != expected_issue.get("iid")
        ):
            raise BlockedError("updated issue marker is in the wrong issue")


def issues(client: GlabClient, project_id: int) -> list[dict[str, Any]]:
    values = client.paginated(f"projects/{project_id}/issues?scope=all")
    if not all(isinstance(item, dict) for item in values):
        raise BlockedError("GitLab issues are invalid")
    return cast(list[dict[str, Any]], values)


def validate_prior_marker(
    expected: dict[str, Any] | None,
    discussions: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    issue_values: list[dict[str, Any]],
) -> None:
    if expected is None:
        return
    expected_digest = expected.get("body_sha256")
    expected_note_id = expected.get("note_id")
    candidates: list[dict[str, Any]] = []
    if expected.get("resource_type") == "issue":
        candidates = [item for item in issue_values if item.get("iid") == expected_note_id]
        body_key = "description"
    else:
        candidates = [
            note
            for discussion in discussions
            for note in meaningful_notes(discussion)
            if note.get("id") == expected_note_id
        ] + [note for note in notes if note.get("id") == expected_note_id]
        body_key = "body"
    unique = {str(item.get("id") or item.get("iid")): item for item in candidates}
    if len(unique) != 1:
        raise BlockedError("previous publication marker changed or disappeared")
    body = next(iter(unique.values())).get(body_key)
    if not isinstance(body, str) or sha256(body.encode()) != expected_digest:
        raise BlockedError("previous publication body changed")


def mutation_payload(
    spec: dict[str, Any], body: str | None, preflight: dict[str, Any]
) -> tuple[str, str, object]:
    operation = cast(str, spec["operation"])
    target = cast(dict[str, Any], preflight["target"])
    endpoint = f"projects/{target['project_id']}/merge_requests/{target['mr_iid']}"
    expected = cast(dict[str, Any], spec["expected"])
    mutation = cast(dict[str, Any], spec["mutation"])
    if operation == "create_general":
        return "POST", f"{endpoint}/discussions", {"body": body}
    if operation == "create_line":
        refs = cast(dict[str, Any], cast(dict[str, Any], preflight["mr"])["diff_refs"])
        position = {
            "position_type": "text",
            **refs,
            "new_path": mutation["path"],
            "old_path": mutation["path"],
        }
        if mutation.get("line") is not None:
            position["new_line"] = mutation["line"]
        else:
            position["old_line"] = mutation["old_line"]
        return "POST", f"{endpoint}/discussions", {"body": body, "position": position}
    if operation in {"reply", "resolve", "reopen"}:
        thread = expected.get("thread")
        if isinstance(thread, dict):
            return (
                "POST",
                f"{endpoint}/discussions/{thread['discussion_id']}/notes",
                {"body": body},
            )
        return "POST", f"{endpoint}/notes", {"body": body}
    if operation == "create_issue":
        return (
            "POST",
            f"projects/{target['project_id']}/issues",
            {"title": mutation["title"], "description": body},
        )
    if operation == "update_issue":
        issue = cast(dict[str, Any], expected["issue"])
        return (
            "PUT",
            f"projects/{target['project_id']}/issues/{issue['iid']}",
            {"title": mutation["title"], "description": body},
        )
    if operation == "update_labels":
        if any("," in value for value in [*mutation["add"], *mutation["remove"]]):
            raise portable.WorkflowError("label names containing commas cannot be mutated safely")
        return (
            "PUT",
            endpoint,
            {
                "add_labels": ",".join(mutation["add"]),
                "remove_labels": ",".join(mutation["remove"]),
            },
        )
    raise portable.WorkflowError("publication operation is unsupported")


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    directory = portable.private_directory(root / "publication-state")
    path = directory / ".lock"
    if path.is_symlink():
        raise portable.WorkflowError("publication lock must not be a symbolic link")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_state(root: Path, digest: str, value: dict[str, Any]) -> Path:
    directory = portable.private_directory(root / "publication-state")
    path = directory / f"{digest}.json"
    portable.write_json(path, value)
    return path


def load_state(root: Path, digest: str) -> dict[str, Any] | None:
    path = root / "publication-state" / f"{digest}.json"
    if not path.exists() and not path.is_symlink():
        return None
    return read_json(path, "publication state", boundary=root)


def apply_action(
    plan_path: Path,
    plan_digest: str,
    root: Path,
    action: dict[str, Any],
    preflight: dict[str, Any],
    body: str | None,
) -> dict[str, Any]:
    spec = cast(dict[str, Any], action["spec"])
    target = cast(dict[str, Any], preflight["target"])
    client = GlabClient(cast(str, target["hostname"]))
    state_path: Path | None = None
    with publication_lock(root):
        journal = load_state(root, cast(str, action["sha256"]))
        live = collect_live(client, preflight)
        operation = cast(str, spec["operation"])
        mutation = cast(dict[str, Any], spec["mutation"])
        if operation == "update_labels":
            if live["labels"] == mutation["proposed"]:
                status = "already_applied"
            elif live["labels"] != cast(dict[str, Any], preflight["labels"])["current"]:
                raise BlockedError("label action no longer has its exact expected state")
            else:
                if journal is not None and journal.get("phase") in {"attempting", "unknown"}:
                    raise BlockedError(
                        "a previous label mutation is unresolved and cannot be repeated safely"
                    )
                write_state(root, cast(str, action["sha256"]), {"phase": "attempting"})
                method, endpoint, payload = mutation_payload(spec, None, preflight)
                try:
                    client.request(method, endpoint, payload)
                except MutationError:
                    live = collect_live(client, preflight)
                    if live["labels"] != mutation["proposed"]:
                        state_path = write_state(
                            root, cast(str, action["sha256"]), {"phase": "unknown"}
                        )
                        raise
                live = collect_live(client, preflight)
                if live["labels"] != mutation["proposed"]:
                    raise MutationError("label mutation postcondition failed")
                status = "applied"
        else:
            if body is None:
                raise portable.WorkflowError("publication body is unavailable")
            discussions = load_discussions(client, cast(str, live["endpoint"]))
            notes = load_notes(client, cast(str, live["endpoint"]))
            issue_values = (
                issues(client, cast(int, target["project_id"])) if action["kind"] == "issue" else []
            )
            observed = observe_body(
                action, body, cast(dict[str, Any], live["actor"]), discussions, notes, issue_values
            )
            if len(observed) > 1:
                raise BlockedError("publication marker appears more than once")
            if len(observed) == 1:
                validate_observed_location(observed[0], spec, preflight)
            if not observed:
                if journal is not None and journal.get("phase") in {
                    "attempting_body",
                    "unknown",
                    "partial",
                }:
                    raise BlockedError(
                        "a previous publication attempt is unresolved and cannot be repeated safely"
                    )
                _selected, discussions, notes = validate_expected_source(client, live, spec)
                validate_prior_marker(
                    cast(
                        dict[str, Any] | None,
                        cast(dict[str, Any], spec["expected"])["prior_marker"],
                    ),
                    discussions,
                    notes,
                    issue_values,
                )
                write_state(root, cast(str, action["sha256"]), {"phase": "attempting_body"})
                method, endpoint, payload = mutation_payload(spec, body, preflight)
                try:
                    client.request(method, endpoint, payload)
                except MutationError:
                    live = collect_live(client, preflight)
                    discussions = load_discussions(client, cast(str, live["endpoint"]))
                    notes = load_notes(client, cast(str, live["endpoint"]))
                    issue_values = (
                        issues(client, cast(int, target["project_id"]))
                        if action["kind"] == "issue"
                        else []
                    )
                    observed = observe_body(
                        action,
                        body,
                        cast(dict[str, Any], live["actor"]),
                        discussions,
                        notes,
                        issue_values,
                    )
                    if len(observed) != 1:
                        state_path = write_state(
                            root, cast(str, action["sha256"]), {"phase": "unknown"}
                        )
                        raise
                    validate_observed_location(observed[0], spec, preflight)
                live = collect_live(client, preflight)
                discussions = load_discussions(client, cast(str, live["endpoint"]))
                notes = load_notes(client, cast(str, live["endpoint"]))
                issue_values = (
                    issues(client, cast(int, target["project_id"]))
                    if action["kind"] == "issue"
                    else []
                )
                observed = observe_body(
                    action,
                    body,
                    cast(dict[str, Any], live["actor"]),
                    discussions,
                    notes,
                    issue_values,
                )
                if len(observed) != 1:
                    raise MutationError("publication body postcondition failed")
                validate_observed_location(observed[0], spec, preflight)
                status = "applied"
            else:
                status = "already_applied"
            if operation in {"resolve", "reopen"}:
                thread = cast(dict[str, Any], cast(dict[str, Any], spec["expected"])["thread"])
                discussion = next(
                    (
                        item
                        for item in discussions
                        if str(item.get("id")) == str(thread["discussion_id"])
                    ),
                    None,
                )
                if discussion is None:
                    raise BlockedError("publication discussion disappeared during recovery")
                values = meaningful_notes(discussion)
                if not values or sha256(cast(str, values[-1]["body"]).encode()) != sha256(
                    body.encode()
                ):
                    raise BlockedError("an intervening reply blocks thread-state recovery")
                desired = mutation["desired_resolved"]
                if values[0].get("resolved") is not desired:
                    write_state(root, cast(str, action["sha256"]), {"phase": "attempting_state"})
                    try:
                        client.request(
                            "PUT",
                            f"{live['endpoint']}/discussions/{thread['discussion_id']}",
                            {"resolved": desired},
                        )
                    except MutationError:
                        refreshed = client.request(
                            "GET", f"{live['endpoint']}/discussions/{thread['discussion_id']}"
                        )
                        if (
                            not isinstance(refreshed, dict)
                            or not meaningful_notes(refreshed)
                            or meaningful_notes(refreshed)[0].get("resolved") is not desired
                        ):
                            state_path = write_state(
                                root, cast(str, action["sha256"]), {"phase": "partial"}
                            )
                            raise
                    refreshed = client.request(
                        "GET", f"{live['endpoint']}/discussions/{thread['discussion_id']}"
                    )
                    if (
                        not isinstance(refreshed, dict)
                        or not meaningful_notes(refreshed)
                        or meaningful_notes(refreshed)[0].get("resolved") is not desired
                    ):
                        raise MutationError("thread-state postcondition failed")
                    status = "applied" if status == "applied" else "recovered"
        state_path = write_state(
            root,
            cast(str, action["sha256"]),
            {
                "phase": "complete",
                "status": status,
                "plan_path": str(plan_path),
                "plan_sha256": plan_digest,
                "action_id": action["id"],
                "action_sha256": action["sha256"],
            },
        )
    return {
        "status": status,
        "action_id": action["id"],
        "action_sha256": action["sha256"],
        "receipt_path": str(state_path),
        "external_mutations": status in {"applied", "recovered"},
    }


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    apply_parser = subparsers.add_parser("apply")
    apply_parser.add_argument("--plan", required=True)
    apply_parser.add_argument("--action", required=True)
    apply_parser.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.capabilities:
        emit(
            {
                "schema_version": 1,
                "operations": ["apply"],
                "action_scope": "exactly_one",
                "confirmation": "action_sha256",
                "external_mutations": True,
                "environment": "inherited",
            }
        )
        return 0
    if args.command != "apply":
        parser.error("the apply subcommand is required")
    try:
        plan_path, plan, plan_digest, root = load_plan(args.plan)
        action, preflight, body = select_action(plan, args.action, args.confirm, root)
        emit(apply_action(plan_path, plan_digest, root, action, preflight, body))
        return 0
    except MutationError as exc:
        emit(
            {
                "status": "partial",
                "error": str(exc),
                "external_mutations": True,
            }
        )
        return 5
    except BlockedError as exc:
        emit(
            {
                "status": "blocked",
                "error": str(exc),
                "external_mutations": False,
            }
        )
        return 4
    except portable.WorkflowError as exc:
        emit(
            {
                "status": "error",
                "error": str(exc),
                "external_mutations": False,
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
