"""Review worktree application: fetch, apply, commit, push, and removal."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reviewmatic.fixes import SuggestionPart, suggestions_patch
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.portable.state_artifacts import xdg_state_home


def git(
    cwd: str | Path, arguments: list[str], stdin: str | None = None, timeout_s: float = 45
) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=str(cwd),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise contract.WorkflowError(f"git {arguments[0]} failed: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:500]
        raise contract.WorkflowError(f"git {arguments[0]} failed: {detail}")
    return result.stdout


def branch_slug(branch: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch)[:80]


def main_checkout_root(repo_root: str | Path) -> str:
    if not Path(repo_root).exists():
        raise contract.WorkflowError("repository root is unavailable")
    common_dir = git(repo_root, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).strip()
    root = git(repo_root, ["rev-parse", "--path-format=absolute", "--show-toplevel"]).strip()
    if "/worktrees/" in common_dir:
        grandparent = str(Path(common_dir).parent.parent.parent)
        return root if grandparent == root else str(Path(common_dir).parent.parent)
    if os.path.join(common_dir, ".git") == os.path.join(root, ".git"):
        return root
    return root if str(Path(common_dir).parent) == root else str(Path(common_dir).parent)


def worktree_base(repo_root: str | Path) -> str:
    return str(Path(f"{main_checkout_root(repo_root)}.worktrees") / "reviewmatic")


def worktree_path(repo_root: str | Path, branch: str) -> str:
    return str(Path(worktree_base(repo_root)) / branch_slug(branch))


def _registry_path() -> Path:
    return Path(xdg_state_home()) / "agent-skills" / "reviewmatic" / "worktrees.json"


def load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {"schema": "reviewmatic/worktree-registry/v1", "items": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema") != "reviewmatic/worktree-registry/v1"
        or not isinstance(value.get("items"), list)
    ):
        raise contract.WorkflowError("worktree registry is invalid")
    return value


def save_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = f"{path}.{os.getpid()}.tmp"
    temporary_path = Path(temporary)
    temporary_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary_path.chmod(0o600)
    os.replace(temporary, path)


def _patch_files(patch: str) -> list[str]:
    files: list[str] = []
    for line in patch.split("\n"):
        match = re.fullmatch(r"diff --git a/(\S+) b/(\S+)", line)
        if match and match.group(2) not in files:
            files.append(match.group(2))
    return files


def prepare_application(
    repo_root: str,
    branch: str,
    head_sha: str,
    patch: str,
    mr_url: str,
) -> dict[str, Any]:
    repository = main_checkout_root(repo_root)
    git(repository, ["fetch", "origin", branch])
    fetched = git(repository, ["rev-parse", "FETCH_HEAD"]).strip()
    if fetched != head_sha:
        raise contract.WorkflowError(
            "the merge request branch moved after the review; regenerate the plan before applying"
        )
    target = worktree_path(repo_root, branch)
    if Path(target).exists():
        status = git(target, ["status", "--porcelain"])
        if status.strip() != "":
            raise contract.WorkflowError(
                f"the review worktree already exists with local changes: {target}"
            )
        current = git(target, ["rev-parse", "HEAD"]).strip()
        if current != head_sha:
            raise contract.WorkflowError(
                f"the review worktree exists at a different commit: {target}"
            )
    else:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        git(repository, ["worktree", "add", "--detach", target, fetched])
    check = subprocess.run(
        ["git", "apply", "--check", "-"],
        cwd=target,
        input=patch,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    if check.returncode == 0:
        applied = subprocess.run(
            ["git", "apply", "-"],
            cwd=target,
            input=patch,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if applied.returncode != 0:
            raise contract.WorkflowError(
                f"git apply failed: {(applied.stderr or applied.stdout).strip()[:500]}"
            )
    elif not re.search(r"already applied|does not match|patch does not apply", check.stderr):
        raise contract.WorkflowError(f"git apply --check failed: {check.stderr.strip()[:500]}")
    diff = git(target, ["diff"])
    record: dict[str, Any] = {
        "path": target,
        "branch": branch,
        "head_sha": head_sha,
        "mr_url": mr_url,
        "patch_sha256": contract.digest({"text": patch}),
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": None,
        "pushed": False,
    }
    registry = load_registry()
    registry["items"] = [*(item for item in registry["items"] if item["path"] != target), record]
    save_registry(registry)
    return {
        "explanation": {
            "repository": repository,
            "branch": branch,
            "head_sha": head_sha,
            "worktree_path": target,
            "files": _patch_files(patch),
            "fetch_command": f"git fetch origin {branch}",
            "create_command": f"git worktree add --detach {target} {head_sha}",
            "apply_preview": "git apply -",
        },
        "applied": diff.strip() != "",
        "diff": diff,
        "record": record,
    }


def commit_application(worktree: str | Path, message: str) -> dict[str, str]:
    worktree_str = str(worktree)
    status = git(worktree_str, ["status", "--porcelain"])
    if status.strip() == "":
        raise contract.WorkflowError("nothing to commit in the review worktree")
    git(worktree_str, ["add", "-A"])
    git(worktree_str, ["commit", "-m", message])
    sha = git(worktree_str, ["rev-parse", "HEAD"]).strip()
    registry = load_registry()
    for record in registry["items"]:
        if record["path"] == worktree_str:
            record["commit_sha"] = sha
            save_registry(registry)
            break
    return {"commit_sha": sha}


def push_application(worktree: str | Path, branch: str) -> dict[str, bool]:
    worktree_str = str(worktree)
    git(worktree_str, ["push", "origin", f"HEAD:refs/heads/{branch}"], None, 120)
    registry = load_registry()
    for record in registry["items"]:
        if record["path"] == worktree_str:
            record["pushed"] = True
            save_registry(registry)
            break
    return {"pushed": True}


def push_preview(worktree: str | Path, branch: str) -> str:
    return f"git push origin HEAD:refs/heads/{branch}"


def remote_url(repo_root: str | Path) -> str:
    return git(main_checkout_root(repo_root), ["remote", "get-url", "origin"]).strip()


def suggestion_to_patch(
    repo_root: str,
    head_sha: str,
    new_path: str,
    old_path: str,
    new_line: int | None,
    old_line: int | None,
    suggestion: str,
) -> str:
    if "```suggestion" in suggestion:
        return suggestions_patch(
            main_checkout_root(repo_root),
            head_sha,
            [SuggestionPart(new_path, int(new_line or 0), suggestion)],
        )
    side = "new" if new_line is not None else "old"
    path = new_path if side == "new" else old_path
    line = new_line if side == "new" else old_line
    if line is None or line < 1:
        raise contract.WorkflowError("suggestion position is invalid")
    blob = git(main_checkout_root(repo_root), ["show", f"{head_sha}:{path}"])
    lines = blob.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if line > len(lines):
        raise contract.WorkflowError("suggestion position is outside the file")
    replacement = re.sub(r"\n$", "", suggestion).split("\n")
    before = lines[: line - 1]
    after = lines[line:]
    context = 3
    start = max(0, len(before) - context)
    before_context = before[start:]
    after_context = after[:context]
    old_count = len(before_context) + 1 + len(after_context)
    new_count = len(before_context) + len(replacement) + len(after_context)
    start_line = line - len(before_context)
    hunk = [f"@@ -{start_line},{old_count} +{start_line},{new_count} @@"]
    for item in before_context:
        hunk.append(f" {item}")
    hunk.append(f"-{lines[line - 1]}")
    for item in replacement:
        hunk.append(f"+{item}")
    for item in after_context:
        hunk.append(f" {item}")
    return "\n".join(
        [
            f"diff --git a/{old_path} b/{new_path}",
            f"--- a/{old_path}",
            f"+++ b/{new_path}",
            *hunk,
            "",
        ]
    )


def registry_summary() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = load_registry()["items"]
    return items


def remove_worktree(worktree: str | Path) -> None:
    worktree_str = str(worktree)
    registry = load_registry()
    record = next((item for item in registry["items"] if item["path"] == worktree_str), None)
    if record is None:
        raise contract.WorkflowError("unknown review worktree")
    if record["pushed"] is True:
        raise contract.WorkflowError("a pushed review worktree is removed without protection")
    status = git(worktree_str, ["status", "--porcelain"])
    if status.strip() != "":
        raise contract.WorkflowError("the review worktree holds uncommitted changes")
    # Resolve the owning checkout from the linked tree; the registry directory
    # is only a sibling and is not itself a Git repository.
    git(main_checkout_root(worktree_str), ["worktree", "remove", worktree_str])
    registry["items"] = [item for item in registry["items"] if item["path"] != worktree_str]
    save_registry(registry)


def worktree_label(worktree: str | Path) -> str:
    return Path(worktree).name
