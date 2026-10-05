"""Managed review worktrees per merge request with a locked shared registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from reviewmatic import context, worktree
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.portable.state_artifacts import xdg_state_home

if TYPE_CHECKING:
    from collections.abc import Callable

REGISTRY_SCHEMA = "reviewmatic/review-worktree-registry/v1"
RECORD_SCHEMA = "reviewmatic/review-worktree/v1"
LOCK_ATTEMPTS = 600
LOCK_DELAY_S = 0.1
ANALYSIS_GRACE_S = 15 * 60
FETCH_TIMEOUT_S = 180.0
FAILURE_LIMIT = 900


@dataclass
class RemoteTarget:
    name: str
    host: str
    project: str


@dataclass
class FetchAttempt:
    remote: str
    ref: str | None
    label: str


def _plain_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _revision_value(value: object, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40,64}", value) is None:
        raise contract.WorkflowError(
            f"the exact {name} revision is unavailable in the review evidence"
        )
    return value.lower()


def _by_name(left: RemoteTarget, right: RemoteTarget) -> int:
    if left.name < right.name:
        return -1
    return 1 if left.name > right.name else 0


def _unique_remotes(remotes: list[RemoteTarget]) -> list[RemoteTarget]:
    seen: set[str] = set()
    result: list[RemoteTarget] = []
    for remote in remotes:
        if remote.name not in seen:
            seen.add(remote.name)
            result.append(remote)
    return result


def checkout_root(value: str | Path) -> str:
    repo_input = str(Path(value).resolve())
    try:
        inside = worktree.git(repo_input, ["rev-parse", "--is-inside-work-tree"]).strip()
    except contract.WorkflowError as error:
        raise contract.WorkflowError(
            f"{repo_input} is not a Git checkout; run from the merge request checkout or pass "
            "it with --repo-root"
        ) from error
    if inside != "true":
        raise contract.WorkflowError(
            f"{repo_input} is not a Git checkout; run from the merge request checkout or pass "
            "it with --repo-root"
        )
    return worktree.git(
        repo_input, ["rev-parse", "--path-format=absolute", "--show-toplevel"]
    ).strip()


def _parse_remote_url(raw: str) -> tuple[str, str] | None:
    url = raw.strip()
    if url == "":
        return None
    host: str | None = None
    path: str | None = None
    if re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        scheme = re.match(
            r"^(?:https?|ssh|git)://(?:[^/@]+@)?([^/:?#]+)(?::\d+)?/(.*)$", url, re.IGNORECASE
        )
        if scheme:
            host = scheme.group(1)
            path = scheme.group(2)
    else:
        scp = re.match(r"^(?:[^/@]+@)?([^/:]+):(.+)$", url)
        if scp:
            host = scp.group(1)
            path = scp.group(2)
    if host is None or path is None:
        return None
    path = re.sub(
        r"/+$", "", re.sub(r"\.git$", "", path.split("#")[0].split("?")[0], flags=re.IGNORECASE)
    )
    if path == "":
        return None
    return host.lower(), unquote(path)


def _remotes_for(root: str, host: str, projects: list[str]) -> list[RemoteTarget]:
    wanted = [item.lower() for item in projects]
    result: list[RemoteTarget] = []
    names = [item.strip() for item in worktree.git(root, ["remote"]).split("\n")]
    for name in names:
        if name == "":
            continue
        try:
            urls = worktree.git(root, ["config", "--get-all", f"remote.{name}.url"])
        except contract.WorkflowError:
            continue
        for url in urls.split("\n"):
            parsed = _parse_remote_url(url)
            # Both sides are normalized; the original project path stays on the
            # target for display.
            if parsed and parsed[0] == host and parsed[1].lower() in wanted:
                result.append(RemoteTarget(name=name, host=parsed[0], project=parsed[1]))
                break
    return result


def _source_project_path_for(host: str, project_id: int) -> str:
    try:
        response = contract.glab_json(host, f"projects/{project_id}")
    except contract.WorkflowError as error:
        raise contract.WorkflowError(
            f"the merge request source project {project_id} is unavailable from GitLab: {error}"
        ) from error
    if isinstance(response, dict) and contract.nonempty_string(response.get("path_with_namespace")):
        return str(response["path_with_namespace"])
    raise contract.WorkflowError("the merge request source project path is unavailable")


def _has_commit(root: str, sha: str) -> bool:
    try:
        return (
            worktree.git(root, ["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"])
            .strip()
            .lower()
            == sha
        )
    except contract.WorkflowError:
        return False


def _fetch_revision(root: str, sha: str, what: str, attempts: list[FetchAttempt]) -> str:
    if _has_commit(root, sha):
        return ""
    failures: list[str] = []
    for attempt in attempts:
        try:
            worktree.git(
                root,
                ["fetch", "--no-tags", attempt.remote, attempt.ref or sha],
                None,
                FETCH_TIMEOUT_S,
            )
        except contract.WorkflowError as error:
            failures.append(f"{attempt.remote}: {error!s}"[:200])
            continue
        if _has_commit(root, sha):
            return attempt.remote
        failures.append(f"{attempt.remote}: {attempt.label} does not carry {sha[:12]}")
    message = f"the exact {what} revision {sha} is unavailable; fetch failed: " + " | ".join(
        failures
    )
    raise contract.WorkflowError(message[:FAILURE_LIMIT])


def _fetch_target_revision(
    root: str, target_ref: str, service_ref: str, remotes: list[RemoteTarget]
) -> tuple[str, str]:
    failures: list[str] = []
    for remote in remotes:
        try:
            worktree.git(
                root,
                ["fetch", "--no-tags", remote.name, f"+refs/heads/{target_ref}:{service_ref}"],
                None,
                FETCH_TIMEOUT_S,
            )
            return (
                worktree.git(root, ["rev-parse", "--verify", service_ref]).strip().lower(),
                remote.name,
            )
        except contract.WorkflowError as error:
            failures.append(f"{remote.name}: {error!s}"[:200])
    message = (
        f"the merge request target branch {target_ref} is unavailable; fetch failed: "
        + " | ".join(failures)
    )
    raise contract.WorkflowError(message[:FAILURE_LIMIT])


def _identity_suffix(host: str, project: str, iid: int) -> str:
    digest = hashlib.sha256(f"{host}\n{project}\n{iid}\n".encode()).hexdigest()
    return digest[:8]


# The readable part can collide (group/a-b versus group-a/b) and the readable
# form is truncated for long project paths, so the slug ends with a short hash
# of the full host/project/IID identity. The suffix is appended after
# truncation and is never cut.
def review_slug(host: str, project: str, iid: int) -> str:
    readable = re.sub(r"[^A-Za-z0-9._-]+", "-", f"mr-{host}-{project}-iid{iid}")[:96]
    return f"{readable}-{_identity_suffix(host, project, iid)}"


# Directory layout used before the identity suffix was introduced. Managed
# trees with such paths are never reused; preparation stops with a manual
# migration instruction instead.
def _legacy_review_slug(host: str, project: str, iid: int) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", f"mr-{host}-{project}-iid{iid}")[:120]


def _same_identity(record: dict[str, Any], host: str, project: str, iid: int) -> bool:
    return (
        str(record["host"]) == host
        and str(record["project_path"]) == project
        and record["iid"] == iid
    )


def _review_worktree_base(main_checkout: str) -> str:
    return str(Path(f"{main_checkout}.worktrees") / "reviewmatic")


def review_worktree_path(main_checkout: str, host: str, project: str, iid: int) -> str:
    return str(Path(_review_worktree_base(main_checkout)) / review_slug(host, project, iid))


def _registry_path() -> Path:
    return Path(xdg_state_home()) / "agent-skills" / "reviewmatic" / "review-worktrees.json"


def load_review_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"schema": REGISTRY_SCHEMA, "items": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema") != REGISTRY_SCHEMA
        or not isinstance(value.get("items"), list)
    ):
        raise contract.WorkflowError("review worktree registry is invalid")
    return value


def save_review_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(f"{path}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)


# The registry file is shared by all merge requests, so every read-modify-write
# holds one short global lock. Fetches never run under it: they happen before
# the lock is taken, so parallel preparations of different merge requests only
# serialize the final record update.
def with_review_registry_lock[T](operation: Callable[[], T]) -> T:
    return _with_preparation_lock(str(_registry_path().parent), "registry", operation)


def _path_exists(path: str) -> bool:
    return os.path.lexists(path)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _with_preparation_lock[T](base: str | Path, slug: str, operation: Callable[[], T]) -> T:
    Path(base).mkdir(parents=True, exist_ok=True)
    lock_path = Path(base) / f".{slug}.lock"
    descriptor: int | None = None
    for _ in range(LOCK_ATTEMPTS):
        try:
            descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            stale = False
            try:
                raw = lock_path.read_text(encoding="utf-8").strip()
                # An empty file means the owner created it but has not written its
                # PID yet: a live, just-started holder. Removing it here would let
                # two preparations run the same mutation concurrently.
                if raw != "":
                    owner = int(raw) if raw.isdigit() else None
                    stale = owner is None or owner == os.getpid() or not _process_alive(owner)
            except OSError:
                stale = False
            if stale:
                lock_path.unlink(missing_ok=True)
            else:
                time.sleep(LOCK_DELAY_S)
        except OSError as error:
            raise contract.WorkflowError(f"review worktree lock failed: {error}") from error
    if descriptor is None:
        raise contract.WorkflowError(
            f"another review worktree preparation is running or a stale lock remains at {lock_path}"
        )
        # Best-effort identification; an unwritten PID keeps the lock unstealable.
    with suppress(OSError):
        os.write(descriptor, f"{os.getpid()}\n".encode())
    try:
        return operation()
    finally:
        os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def _live_analysis(
    marker: dict[str, Any] | None, supersede_root: str | None
) -> dict[str, Any] | None:
    if marker is None:
        return None
    if supersede_root is not None and marker["artifact_root"] == supersede_root:
        return None
    progress: dict[str, Any] | None = None
    try:
        progress = context.load_progress(Path(marker["artifact_root"]))
    except contract.WorkflowError:
        progress = None
    if progress is not None:
        # Unfinished progress at the marker's artifact root means the tree is
        # being analyzed even when the progress digest differs from the marker
        # (a reused preparation restarted collection on the same root). Only a
        # finalized plan or an explicit supersede root frees the tree.
        return None if progress.get("stage") == "plan_ready" else marker
    started_at = marker.get("started_at")
    if isinstance(started_at, str):
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
        return marker if (time.time() - started) < ANALYSIS_GRACE_S else None
    return None


def _is_worktree_at(path: str) -> bool:
    try:
        inside = worktree.git(path, ["rev-parse", "--is-inside-work-tree"]).strip() == "true"
        toplevel = (
            worktree.git(path, ["rev-parse", "--path-format=absolute", "--show-toplevel"]).strip()
            == path
        )
    except contract.WorkflowError:
        return False
    return inside and toplevel


def prepare_review_worktree(
    repo_root: str,
    evidence: dict[str, Any],
    evidence_digest: str,
    supersede_root: str | None = None,
) -> dict[str, Any]:
    target = evidence["target"] if isinstance(evidence.get("target"), dict) else None
    evidence_object = evidence["object"] if isinstance(evidence.get("object"), dict) else None
    if target is None or evidence_object is None:
        raise contract.WorkflowError("merge request evidence is incomplete")
    host = target["hostname"].lower() if isinstance(target.get("hostname"), str) else ""
    project_path = target["project_path"] if isinstance(target.get("project_path"), str) else ""
    iid = _plain_int(target.get("iid"))
    project_id = _plain_int(target.get("project_id"))
    diff_refs = (
        evidence_object.get("diff_refs")
        if isinstance(evidence_object.get("diff_refs"), dict)
        else None
    )
    base_sha = _revision_value(
        diff_refs.get("base_sha") if diff_refs else None, "merge request diff base"
    )
    start_sha = _revision_value(
        diff_refs.get("start_sha") if diff_refs else None, "merge request diff start"
    )
    head_source = diff_refs.get("head_sha") if diff_refs else None
    if head_source is None:
        head_source = evidence.get("head_sha")
    head_sha = _revision_value(head_source, "merge request head")
    target_branch = (
        str(evidence_object["target_branch"])
        if contract.nonempty_string(evidence_object.get("target_branch"))
        else ""
    )
    source_branch = (
        str(evidence_object["source_branch"])
        if contract.nonempty_string(evidence_object.get("source_branch"))
        else ""
    )
    artifact_root = (
        str(evidence["artifact_root"])
        if contract.nonempty_string(evidence.get("artifact_root"))
        else ""
    )
    if (
        host == ""
        or project_path == ""
        or iid is None
        or target_branch == ""
        or source_branch == ""
        or artifact_root == ""
        or not isinstance(evidence_digest, str)
        or evidence_digest == ""
    ):
        raise contract.WorkflowError("merge request identity or evidence binding is incomplete")

    toplevel = checkout_root(repo_root)
    main = worktree.main_checkout_root(toplevel)
    slug = review_slug(host, project_path, iid)
    path = review_worktree_path(main, host, project_path, iid)
    service_ref = f"refs/reviewmatic/mr/{slug}/target"

    target_remotes = sorted(_remotes_for(main, host, [project_path]), key=lambda item: item.name)
    source_remotes: list[RemoteTarget] = []
    source_project_path: str | None = None
    source_project_id = _plain_int(evidence_object.get("source_project_id"))
    if source_project_id is not None and project_id is not None and source_project_id != project_id:
        source_project_path = _source_project_path_for(host, source_project_id)
        source_remotes = sorted(
            _remotes_for(main, host, [source_project_path]), key=lambda item: item.name
        )
    all_remotes = _unique_remotes([*source_remotes, *target_remotes])
    if not all_remotes:
        raise contract.WorkflowError(
            f"no remote of {main} points at {host}/{project_path}"
            + ("" if source_project_path is None else f" or {host}/{source_project_path}")
            + "; run from the merge request checkout or pass it with --repo-root; "
            "cloning is not performed"
        )

    head_attempts = (
        [
            FetchAttempt(remote.name, f"refs/merge_requests/{iid}/head", "merge request head ref")
            for remote in target_remotes
        ]
        + [
            FetchAttempt(
                remote.name, f"refs/heads/{source_branch}", f"source branch {source_branch}"
            )
            for remote in all_remotes
        ]
        + [FetchAttempt(remote.name, None, "exact revision fetch") for remote in all_remotes]
    )
    base_attempts = [
        FetchAttempt(remote.name, None, "exact revision fetch") for remote in all_remotes
    ]
    head_remote = _fetch_revision(main, head_sha, "merge request head", head_attempts)

    # Refuse retired layouts before any mutation: a managed tree of the old
    # path scheme is never replaced, moved, or shadowed by a second directory.
    legacy_path = str(
        Path(_review_worktree_base(main)) / _legacy_review_slug(host, project_path, iid)
    )
    for record in load_review_registry()["items"]:
        if not _same_identity(record, host, project_path, iid) or record["path"] == path:
            continue
        if _path_exists(record["path"]):
            raise contract.WorkflowError(
                f"the review worktree for {host}/{project_path}!{iid} is registered under the "
                f"retired path layout at {record['path']}; migrate it manually: keep or finish "
                f"the active review there, check `git -C {record['path']} status --porcelain` "
                f"for local changes, then remove the tree with `git -C {main} worktree remove "
                f"{record['path']}` (--force only after preserving changes) and start the "
                f"review again; it will create {path}. The registry record for the removed "
                "tree is replaced automatically"
            )
    if legacy_path != path and _path_exists(legacy_path):
        raise contract.WorkflowError(
            f"a review worktree of the retired path layout exists at {legacy_path}; it may "
            f"belong to {host}/{project_path}!{iid} or to a merge request whose readable path "
            f"collides with it, and it is not managed by the registry. Inspect it and remove "
            f"it manually with `git -C {main} worktree remove {legacy_path}` only after "
            f"preserving any active review and local changes; the next preparation creates {path}"
        )

    return _with_preparation_lock(
        _review_worktree_base(main),
        slug,
        lambda: _prepare_locked(
            main=main,
            toplevel=toplevel,
            path=path,
            slug=slug,
            host=host,
            project_path=project_path,
            iid=iid,
            base_sha=base_sha,
            start_sha=start_sha,
            head_sha=head_sha,
            head_remote=head_remote,
            target_branch=target_branch,
            service_ref=service_ref,
            target_remotes=target_remotes,
            source_remotes=source_remotes,
            base_attempts=base_attempts,
            head_attempts=head_attempts,
            evidence_digest=evidence_digest,
            artifact_root=artifact_root,
            source_project_path=source_project_path,
            supersede_root=supersede_root,
        ),
    )


def _prepare_locked(  # noqa: PLR0913
    *,
    main: str,
    toplevel: str,
    path: str,
    slug: str,
    host: str,
    project_path: str,
    iid: int,
    base_sha: str,
    start_sha: str,
    head_sha: str,
    head_remote: str,
    target_branch: str,
    service_ref: str,
    target_remotes: list[RemoteTarget],
    source_remotes: list[RemoteTarget],
    base_attempts: list[FetchAttempt],
    head_attempts: list[FetchAttempt],
    evidence_digest: str,
    artifact_root: str,
    source_project_path: str | None,
    supersede_root: str | None,
) -> dict[str, Any]:
    known = load_review_registry()
    existing = next(
        (item for item in known["items"] if _same_identity(item, host, project_path, iid)),
        None,
    )
    if existing is not None and _has_commit(main, str(existing["target_sha"])):
        target_sha = str(existing["target_sha"])
        remote = str(existing["remote"])
    else:
        fetched = _fetch_target_revision(
            main, target_branch, service_ref, [*target_remotes, *source_remotes]
        )
        target_sha, remote = fetched
    if head_remote != "":
        remote = head_remote
    if not _has_commit(main, base_sha):
        _fetch_revision(main, base_sha, "merge request diff base", base_attempts)
    if not _has_commit(main, start_sha):
        _fetch_revision(main, start_sha, "merge request diff start", head_attempts)

    active = _live_analysis(existing.get("analysis") if existing else None, supersede_root)
    reused = False
    switched = False
    if _path_exists(path):
        if existing is None:
            raise contract.WorkflowError(
                f"{path} exists and is not a reviewmatic-managed review worktree; remove it "
                "manually or choose another checkout"
            )
        if not _is_worktree_at(path):
            raise contract.WorkflowError(
                f"the registered review worktree {path} is broken; remove it manually with "
                "git worktree remove --force"
            )
        current = worktree.git(path, ["rev-parse", "HEAD"]).strip().lower()
        if current != head_sha:
            if current != existing["head_sha"]:
                raise contract.WorkflowError(
                    f"the review worktree {path} contains commits beyond its registered "
                    "revision; inspect it and remove the worktree manually if it is no "
                    "longer needed"
                )
            if active is not None and active["head_sha"] != head_sha:
                raise contract.WorkflowError(
                    f"the review of {host}/{project_path}!{iid} is in progress at revision "
                    f"{str(active['head_sha'])[:12]} in {path}; finish that review before "
                    f"switching the worktree to {head_sha[:12]}"
                )
            if worktree.git(path, ["status", "--porcelain"]).strip() != "":
                raise contract.WorkflowError(
                    f"the review worktree {path} holds local changes; resolve them manually "
                    f"before switching to revision {head_sha[:12]}"
                )
            worktree.git(path, ["checkout", "--detach", head_sha])
            switched = True
        else:
            reused = True
    else:
        worktree.git(main, ["worktree", "add", "--detach", path, head_sha], None, 120.0)
    if worktree.git(path, ["rev-parse", "HEAD"]).strip().lower() != head_sha:
        raise contract.WorkflowError(
            "the review worktree head does not match the merge request revision"
        )
    if worktree.git(path, ["status", "--porcelain"]).strip() != "":
        raise contract.WorkflowError(
            f"the review worktree {path} is not clean; resolve its local changes manually"
        )

    now = datetime.now(UTC).isoformat()
    record: dict[str, Any] = {
        "schema": RECORD_SCHEMA,
        "path": path,
        "source_repo_root": toplevel,
        "host": host,
        "project_path": project_path,
        "source_project_path": source_project_path,
        "iid": iid,
        "base_sha": base_sha,
        "start_sha": start_sha,
        "head_sha": head_sha,
        "target_ref": target_branch,
        "target_sha": target_sha,
        "remote": remote,
        # A live analysis keeps its marker: a preparation that has not run
        # beginReview yet must not claim the tree away from the running review.
        "analysis": active
        if active is not None
        else {
            "head_sha": head_sha,
            "evidence_digest": evidence_digest,
            "artifact_root": artifact_root,
            "pid": os.getpid(),
            "started_at": now,
        },
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
    }

    def update() -> None:
        # Re-read and merge under the shared registry lock so parallel
        # preparations of different merge requests cannot lose each other's
        # records. No fetch happens inside this lock.
        registry = load_review_registry()
        same_identity_record = next(
            (item for item in registry["items"] if _same_identity(item, host, project_path, iid)),
            None,
        )
        if (
            same_identity_record is not None
            and same_identity_record["path"] != path
            and _path_exists(same_identity_record["path"])
        ):
            raise contract.WorkflowError(
                f"the review worktree for {host}/{project_path}!{iid} is registered under "
                f"the retired path layout at {same_identity_record['path']}; migrate it "
                "manually as reported before the worktree was prepared"
            )
        save_review_registry(
            {
                "schema": REGISTRY_SCHEMA,
                "items": [
                    *(
                        item
                        for item in registry["items"]
                        if not _same_identity(item, host, project_path, iid)
                    ),
                    record,
                ],
            }
        )

    with_review_registry_lock(update)
    return {
        "path": path,
        "source_repo_root": toplevel,
        "reused": reused,
        "switched": switched,
        "remote": remote,
        "refs": {
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "target_ref": target_branch,
            "target_sha": target_sha,
        },
    }
