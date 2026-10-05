"""End-to-end review-worktree preparation scenarios against the fake glab.

Ported from ``review-worktree.test.mjs``. The unit-level slug, remote-parsing,
registry, and locking checks live in ``test_review_worktree.py``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic.context import load_progress
from reviewmatic.local_review import local_bundle
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.review_worktree import (
    prepare_review_worktree,
    review_slug,
    save_review_registry,
)
from reviewmatic.worktree import prepare_application

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

SRC = Path(__file__).resolve().parent.parent / "src"
REGISTRY_SCHEMA = "reviewmatic/review-worktree-registry/v1"
OTHER_URL = "https://gitlab.example/other/project/-/merge_requests/7"


@pytest.fixture(name="make_fixture")
def fixture_factory() -> Iterator[Callable[[], ReviewFixture]]:
    created: list[ReviewFixture] = []

    def make() -> ReviewFixture:
        fixture = make_review_fixture()
        created.append(fixture)
        return fixture

    try:
        yield make
    finally:
        for fixture in reversed(created):
            fixture.close()
        for fixture in created:
            shutil.rmtree(fixture.tmp, ignore_errors=True)


@pytest.fixture(name="fixture")
def single_fixture(make_fixture: Callable[[], ReviewFixture]) -> ReviewFixture:
    return make_fixture()


def git_in(cwd: str | Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def worktree_head(path: str) -> str:
    return git_in(path, "rev-parse", "HEAD")


def service_target_sha(repo: Path, worktree_path: str) -> str:
    return git_in(
        repo, "rev-parse", "--verify", f"refs/reviewmatic/mr/{Path(worktree_path).name}/target"
    )


def registry_file() -> Path:
    return (
        Path(os.environ["XDG_STATE_HOME"])
        / "agent-skills"
        / "reviewmatic"
        / ("review-worktrees.json")
    )


def registry() -> dict[str, Any]:
    return contract.read_json(registry_file(), "review worktree registry")


def assert_no_code_fetches(fixture: ReviewFixture) -> None:
    endpoints = fixture.request_endpoints()
    assert all(not re.search(r"blobs|/files/|/raw/|repository/tree", e) for e in endpoints), (
        f"no per-file code fetches: {', '.join(endpoints)}"
    )


def write_config(fixture: ReviewFixture, **overrides: Any) -> None:
    fixture.config_path.write_text(json.dumps({**fixture.config, **overrides}), encoding="utf-8")


def set_ref(origin: Path, ref: str, sha: str) -> None:
    git_in(origin, "update-ref", ref, sha)


def push_head_from_clone(fixture: ReviewFixture, message: str, branches: list[str]) -> str:
    clone = fixture.tmp / f"origin-push-{re.sub(r'\W+', '-', message)}"
    subprocess.run(["git", "clone", "-q", str(fixture.origin), str(clone)], check=True)
    git_in(clone, "config", "user.email", "author@example.invalid")
    git_in(clone, "config", "user.name", "Author")
    git_in(clone, "config", "commit.gpgsign", "false")
    (clone / "review.txt").write_text(f"base\nreviewed change\n{message}\n", encoding="utf-8")
    git_in(clone, "commit", "-qam", message)
    sha = git_in(clone, "rev-parse", "HEAD")
    for branch in branches:
        git_in(clone, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
    shutil.rmtree(clone, ignore_errors=True)
    return sha


def advance_main_and_dev(fixture: ReviewFixture, content: str, message: str) -> str:
    (fixture.repo / "review.txt").write_text(content, encoding="utf-8")
    fixture.git("commit", "-qam", message)
    new_head = fixture.git("rev-parse", "HEAD")
    fixture.git("push", "-q", "origin", "main")
    fixture.git("push", "-q", "origin", "dev")
    set_ref(fixture.origin, "refs/merge_requests/7/head", new_head)
    write_config(fixture, headSha=new_head)
    return new_head


def make_fork(fixture: ReviewFixture, clone_name: str, url: str, remote_name: str) -> str:
    """Create a fork origin carrying one extra commit and register it as a remote."""
    fork_origin = fixture.tmp / "fork.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--initial-branch=main", str(fork_origin)],
        check=True,
    )
    fork_clone = fixture.tmp / clone_name
    subprocess.run(["git", "clone", "-q", str(fixture.origin), str(fork_clone)], check=True)
    git_in(fork_clone, "config", "user.email", "author@example.invalid")
    git_in(fork_clone, "config", "user.name", "Author")
    git_in(fork_clone, "config", "commit.gpgsign", "false")
    (fork_clone / "review.txt").write_text("base\nreviewed change\nfork change\n", encoding="utf-8")
    git_in(fork_clone, "commit", "-qam", "fork change")
    fork_head = git_in(fork_clone, "rev-parse", "HEAD")
    git_in(fork_clone, "push", "-q", str(fork_origin), "HEAD:refs/heads/dev")
    fixture.git("remote", "add", remote_name, url)
    fixture.git("config", f"url.{fork_origin}.insteadOf", url)
    return fork_head


def add_project(fixture: ReviewFixture, remote: str, url: str) -> None:
    fixture.git("remote", "add", remote, url)
    fixture.git("config", "--add", f"url.{fixture.origin}.insteadOf", url)


def start(fixture: ReviewFixture, url: str | None = None) -> dict[str, Any]:
    return draft_module.start_review(url=url or fixture.url, repo_root=str(fixture.repo))


def ok(result: dict[str, Any]) -> dict[str, Any]:
    assert result["status"] == "ok", json.dumps(result)
    return result


def test_start_review_prepares_one_managed_worktree_from_a_subdirectory(
    fixture: ReviewFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    subdir = fixture.repo / "docs" / "deep"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    (fixture.repo / "scratch.txt").write_text("untracked work\n", encoding="utf-8")
    fixture.git("add", "scratch.txt")
    head_before = fixture.git("rev-parse", "HEAD")
    branch_before = fixture.git("symbolic-ref", "--short", "HEAD")
    status_before = fixture.git("status", "--porcelain")
    branches_before = fixture.git("branch", "--list")

    result = ok(draft_module.start_review(url=fixture.url))
    worktree = result["review_worktree"]
    assert worktree["source_repo_root"] == str(fixture.repo)
    assert worktree["reused"] is False
    assert worktree["switched"] is False
    assert worktree["remote"] == "origin"
    assert re.search(
        r"\.worktrees/reviewmatic/mr-gitlab\.example-group-project-iid7-[0-9a-f]{8}$",
        worktree["path"],
    )
    assert worktree["refs"]["head_sha"] == fixture.head_sha
    assert worktree["refs"]["base_sha"] == fixture.base_sha
    assert worktree["refs"]["start_sha"] == fixture.base_sha
    assert worktree["refs"]["target_ref"] == "main"
    assert service_target_sha(fixture.repo, worktree["path"]) == worktree["refs"]["target_sha"]
    assert worktree_head(worktree["path"]) == fixture.head_sha
    assert git_in(worktree["path"], "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert (Path(worktree["path"]) / "review.txt").read_text() == "base\nreviewed change\n"
    progress = load_progress(Path(result["artifact_root"]))
    assert progress is not None
    assert progress["repo_root"] == worktree["path"]
    assert result["critic_task"]["repo_root"] == worktree["path"]

    assert fixture.git("rev-parse", "HEAD") == head_before
    assert fixture.git("symbolic-ref", "--short", "HEAD") == branch_before
    assert fixture.git("status", "--porcelain") == status_before
    assert fixture.git("branch", "--list") == branches_before
    assert not (fixture.repo / ".worktrees").exists()
    assert not (Path(worktree["path"]) / "scratch.txt").exists()

    repeated = ok(start(fixture))
    assert repeated["review_worktree"]["path"] == worktree["path"]
    assert repeated["review_worktree"]["reused"] is True
    assert len(registry()["items"]) == 1
    assert_no_code_fetches(fixture)


def test_the_fixed_target_revision_never_replaces_the_merge_request_diff_base(
    fixture: ReviewFixture,
) -> None:
    advanced_tip = push_head_from_clone(fixture, "target advanced", ["main"])
    result = ok(start(fixture))
    refs = result["review_worktree"]["refs"]
    assert refs["target_sha"] == advanced_tip
    assert refs["base_sha"] == fixture.base_sha
    assert refs["head_sha"] == fixture.head_sha
    assert worktree_head(result["review_worktree"]["path"]) == fixture.head_sha


def test_a_fork_merge_request_is_fetched_from_the_fork_remote_under_any_name(
    fixture: ReviewFixture,
) -> None:
    fork_head = make_fork(
        fixture, "fork-clone", "https://gitlab.example/fork/project.git", "contrib"
    )
    write_config(fixture, headSha=fork_head, sourceProjectId=21, sourceProjectPath="fork/project")

    result = ok(start(fixture))
    assert result["review_worktree"]["refs"]["head_sha"] == fork_head
    assert result["review_worktree"]["refs"]["base_sha"] == fixture.base_sha
    assert result["review_worktree"]["remote"] == "contrib"
    assert worktree_head(result["review_worktree"]["path"]) == fork_head
    assert "projects/21" in fixture.request_endpoints()
    assert_no_code_fetches(fixture)


def test_an_unrelated_repository_stops_the_review_and_asks_for_the_correct_checkout(
    fixture: ReviewFixture, tmp_path: Path
) -> None:
    fixture.git("remote", "set-url", "origin", "https://gitlab.example/other/project.git")
    result = start(fixture)
    assert result["status"] == "blocked"
    assert "--repo-root" in json.dumps(result["errors"])
    assert not Path(f"{fixture.repo}.worktrees").exists()
    plain = tmp_path / "plain"
    plain.mkdir()
    missing = draft_module.start_review(url=fixture.url, repo_root=str(plain))
    assert missing["status"] == "blocked"
    assert "not a Git checkout" in json.dumps(missing["errors"])


def test_fetch_failures_block_preparation_and_a_later_run_recovers(
    fixture: ReviewFixture,
) -> None:
    new_head = push_head_from_clone(fixture, "unreachable head", ["main", "dev"])
    set_ref(fixture.origin, "refs/merge_requests/7/head", new_head)
    write_config(fixture, headSha=new_head)
    fixture.git("config", "--unset-all", f"url.{fixture.origin}.insteadOf")
    fixture.git("config", "url./nonexistent/reviewmatic-unreachable.insteadOf", fixture.origin_url)

    blocked = start(fixture)
    assert blocked["status"] == "blocked"
    assert re.search(r"unavailable|fetch failed", json.dumps(blocked["errors"]))
    assert not Path(f"{fixture.repo}.worktrees").exists()

    fixture.git("config", "--unset-all", "url./nonexistent/reviewmatic-unreachable.insteadOf")
    fixture.git("config", f"url.{fixture.origin}.insteadOf", fixture.origin_url)
    recovered = ok(start(fixture))
    assert recovered["review_worktree"]["refs"]["head_sha"] == new_head
    assert worktree_head(recovered["review_worktree"]["path"]) == new_head


def test_a_revision_that_no_ref_carries_blocks_preparation_without_creating_a_worktree(
    fixture: ReviewFixture,
) -> None:
    write_config(fixture, headSha="f" * 40)
    blocked = start(fixture)
    assert blocked["status"] == "blocked"
    assert "merge request head" in json.dumps(blocked["errors"])
    assert not Path(f"{fixture.repo}.worktrees").exists()


def test_a_new_head_switches_the_same_worktree_only_when_no_review_is_active(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    worktree_path = first["review_worktree"]["path"]
    new_head = advance_main_and_dev(fixture, "base\nreviewed change\ncorrected\n", "correction")

    blocked = start(fixture)
    assert blocked["status"] == "blocked"
    assert "in progress" in json.dumps(blocked["errors"])
    assert worktree_head(worktree_path) == fixture.head_sha

    refreshed = draft_module.refresh_review(first["draft_path"])
    assert refreshed["status"] == "needs_reassessment", json.dumps(refreshed)
    assert refreshed["review_worktree"]["path"] == worktree_path
    assert refreshed["review_worktree"]["switched"] is True
    assert worktree_head(worktree_path) == new_head
    assert len(registry()["items"]) == 1
    assert registry()["items"][0]["head_sha"] == new_head


def test_a_finalized_review_no_longer_blocks_switching_to_a_new_head(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    draft = complete_draft(contract.read_json(Path(first["draft_path"]), "draft"), first)
    contract.write_json(Path(first["draft_path"]), draft)
    checked = draft_module.check_review(first["draft_path"])
    assert checked["status"] == "ok", json.dumps(checked["errors"])
    assert draft_module.finish_review(first["draft_path"])["status"] == "ok"
    progress = load_progress(Path(first["artifact_root"]))
    assert progress is not None
    plan_path = Path(progress["plan_path"])
    plan_bytes = plan_path.read_bytes()

    new_head = advance_main_and_dev(fixture, "base\nreviewed change\nfollow-up\n", "follow-up")

    second = ok(start(fixture))
    assert second["review_worktree"]["path"] == first["review_worktree"]["path"]
    assert second["review_worktree"]["switched"] is True
    assert worktree_head(second["review_worktree"]["path"]) == new_head
    assert plan_path.read_bytes() == plan_bytes, "the finalized plan stays untouched"


def test_dirty_extended_and_foreign_worktrees_are_blocked_without_reset_or_cleanup(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    worktree_path = Path(first["review_worktree"]["path"])

    (worktree_path / "review.txt").write_text("tampered\n", encoding="utf-8")
    dirty = start(fixture)
    assert dirty["status"] == "blocked"
    assert "not clean" in json.dumps(dirty["errors"])
    assert (worktree_path / "review.txt").read_text() == "tampered\n"
    git_in(worktree_path, "checkout", "--", "review.txt")

    (worktree_path / "experiment.txt").write_text("experiment\n", encoding="utf-8")
    git_in(worktree_path, "add", "-A")
    git_in(worktree_path, "commit", "-qm", "experiment")
    extended_head = worktree_head(str(worktree_path))
    extended = start(fixture)
    assert extended["status"] == "blocked"
    assert "beyond its registered revision" in json.dumps(extended["errors"])
    assert worktree_head(str(worktree_path)) == extended_head

    shutil.rmtree(worktree_path)
    contract.write_json(registry_file(), {"schema": REGISTRY_SCHEMA, "items": []})
    worktree_path.mkdir(parents=True)
    (worktree_path / "keep.txt").write_text("foreign\n", encoding="utf-8")
    foreign = start(fixture)
    assert foreign["status"] == "blocked"
    assert "not a reviewmatic-managed" in json.dumps(foreign["errors"])
    assert (worktree_path / "keep.txt").read_text() == "foreign\n"


def test_concurrent_preparations_serialize_into_one_reused_worktree(
    fixture: ReviewFixture,
) -> None:
    environment = {**os.environ, "PYTHONPATH": str(SRC)}
    command = [
        sys.executable,
        "-m",
        "reviewmatic",
        "start-review",
        "--url",
        fixture.url,
        "--repo-root",
        str(fixture.repo),
        "--json",
    ]
    runs = [
        subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [run.communicate()[0] for run in runs]
    results: list[dict[str, Any]] = [json.loads(output) for output in outputs]
    succeeded = [result for result in results if result["status"] == "ok"]
    superseded = [
        result
        for result in results
        if result["status"] == "error"
        and re.search(
            r"progress (binding )?changed during transition|another review state update is running",
            str((result.get("error") or {}).get("message", "")),
        )
    ]
    assert len(succeeded) + len(superseded) == len(results), json.dumps(results)
    assert len(succeeded) >= 1, "at least one concurrent run completes"
    if len(succeeded) == 2:
        assert any(result["review_worktree"]["reused"] is True for result in succeeded), (
            "one of two successful runs must reuse the prepared worktree"
        )
    assert len(registry()["items"]) == 1
    worktree_path = succeeded[0]["review_worktree"]["path"]
    assert git_in(worktree_path, "status", "--porcelain") == ""
    assert worktree_head(worktree_path) == fixture.head_sha


def test_identical_branch_names_in_different_projects_never_share_a_worktree(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    add_project(fixture, "second", "https://gitlab.example/other/project.git")
    second = ok(start(fixture, OTHER_URL))
    assert second["review_worktree"]["path"] != first["review_worktree"]["path"]
    assert re.search(
        r"mr-gitlab\.example-other-project-iid7-[0-9a-f]{8}$", second["review_worktree"]["path"]
    )
    assert len(registry()["items"]) == 2


def test_local_wip_review_creates_no_worktree_and_manual_fix_application_keeps_working(
    fixture: ReviewFixture,
) -> None:
    bundle = local_bundle(str(fixture.repo), "code-review", None)
    assert bundle["retrieval_complete"] is True
    assert not Path(f"{fixture.repo}.worktrees").exists()

    started = ok(start(fixture))
    patch = (
        "diff --git a/review.txt b/review.txt\n--- a/review.txt\n+++ b/review.txt\n"
        "@@ -1,2 +1,2 @@\n base\n-reviewed change\n+reviewed change corrected\n"
    )
    applied = prepare_application(
        repo_root=started["review_worktree"]["path"],
        branch="dev",
        head_sha=fixture.head_sha,
        patch=patch,
        mr_url=fixture.url,
    )
    assert re.search(r"\.worktrees/reviewmatic/dev$", applied["explanation"]["worktree_path"])
    assert "+reviewed change corrected" in applied["diff"]
    _, evidence = contract.artifact_payload(Path(started["evidence_path"]), "evidence_snapshot")
    assert evidence["head_sha"] == fixture.head_sha


def test_an_interrupted_repeated_preparation_keeps_the_active_review_protected(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    worktree_path = first["review_worktree"]["path"]

    # A repeated preparation of the same head that stops before beginReview
    # must not claim the tree away from the running review.
    _, evidence = contract.artifact_payload(Path(first["evidence_path"]), "evidence_snapshot")
    repeated = prepare_review_worktree(
        repo_root=str(fixture.repo),
        evidence={**evidence, "artifact_root": first["artifact_root"]},
        evidence_digest="b" * 64,
    )
    assert repeated["path"] == worktree_path
    assert repeated["reused"] is True
    marker = registry()["items"][0]["analysis"]
    assert marker["artifact_root"] == first["artifact_root"]
    progress = load_progress(Path(first["artifact_root"]))
    assert progress is not None
    assert marker["evidence_digest"] == progress["evidence_digest"]

    (fixture.repo / "review.txt").write_text("base\nreviewed change\nadvanced\n", encoding="utf-8")
    fixture.git("commit", "-qam", "advanced")
    new_head = fixture.git("rev-parse", "HEAD")
    fixture.git("push", "-q", "origin", "main")
    fixture.git("push", "-q", "origin", "dev")
    set_ref(fixture.origin, "refs/merge-requests/7/head", new_head)
    write_config(fixture, headSha=new_head)

    blocked = start(fixture)
    assert blocked["status"] == "blocked"
    assert "in progress" in json.dumps(blocked["errors"])
    assert worktree_head(worktree_path) == fixture.head_sha

    refreshed = draft_module.refresh_review(first["draft_path"])
    assert refreshed["status"] == "needs_reassessment", json.dumps(refreshed)
    assert refreshed["review_worktree"]["switched"] is True
    assert worktree_head(worktree_path) == new_head


def test_a_retired_layout_worktree_blocks_preparation_until_it_is_migrated_manually(
    fixture: ReviewFixture,
) -> None:
    first = ok(start(fixture))
    new_path = first["review_worktree"]["path"]
    legacy_path = Path(f"{fixture.repo}.worktrees/reviewmatic/mr-gitlab.example-group-project-iid7")
    git_in(fixture.repo, "worktree", "add", "--detach", str(legacy_path), fixture.head_sha)
    state = contract.read_json(registry_file(), "registry")
    state["items"][0]["path"] = str(legacy_path)
    contract.write_json(registry_file(), state)

    blocked = start(fixture)
    assert blocked["status"] == "blocked"
    reported = json.dumps(blocked["errors"])
    assert "retired path layout" in reported
    assert "worktree remove" in reported
    assert re.search(re.escape(new_path), reported)
    assert git_in(legacy_path, "rev-parse", "HEAD") == fixture.head_sha
    assert contract.read_json(registry_file(), "registry")["items"][0]["path"] == str(legacy_path)

    git_in(fixture.repo, "worktree", "remove", str(legacy_path))
    migrated = ok(start(fixture))
    assert migrated["review_worktree"]["path"] == new_path
    assert migrated["review_worktree"]["reused"] is True
    items = registry()["items"]
    assert len(items) == 1
    assert items[0]["path"] == new_path

    save_review_registry({"schema": REGISTRY_SCHEMA, "items": []})
    shutil.rmtree(legacy_path, ignore_errors=True)
    legacy_path.mkdir(parents=True)
    (legacy_path / "keep.txt").write_text("legacy\n", encoding="utf-8")
    unmanaged = start(fixture)
    assert unmanaged["status"] == "blocked"
    assert "retired path layout" in json.dumps(unmanaged["errors"])
    assert (legacy_path / "keep.txt").read_text() == "legacy\n"


REGISTRY_WORKER = """
import json
import sys
import time

from reviewmatic.review_worktree import (
    load_review_registry,
    save_review_registry,
    with_review_registry_lock,
)

record = json.loads(sys.argv[1])


def update() -> None:
    registry = load_review_registry()
    time.sleep(0.5)
    save_review_registry({"schema": registry["schema"], "items": [*registry["items"], record]})


with_review_registry_lock(update)
"""


def test_parallel_preparations_of_different_merge_requests_keep_both_registry_records(
    fixture: ReviewFixture,
) -> None:
    environment = {**os.environ, "PYTHONPATH": str(SRC)}

    def write_record(project: str) -> None:
        record = {
            "schema": "reviewmatic/review-worktree/v1",
            "path": f"{fixture.repo}.worktrees/reviewmatic/mr-{project.replace('/', '-')}-iid7",
            "host": "gitlab.example",
            "project_path": project,
            "iid": 7,
        }
        completed = subprocess.run(
            [sys.executable, "-c", REGISTRY_WORKER, json.dumps(record)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, (
            f"registry writer for {project} failed: {completed.returncode} {completed.stderr}"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(write_record, p) for p in ("group/project", "other/project")]:
            future.result()
    raced = sorted(item["project_path"] for item in registry()["items"])
    assert raced == ["group/project", "other/project"]

    add_project(fixture, "second", "https://gitlab.example/other/project.git")
    first = start(fixture)
    second = start(fixture, OTHER_URL)
    ok(first)
    ok(second)

    repeated_first = start(fixture)
    repeated_second = start(fixture, OTHER_URL)
    assert repeated_first["review_worktree"]["reused"] is True
    assert repeated_second["review_worktree"]["reused"] is True
    kept = sorted(item["project_path"] for item in registry()["items"])
    assert kept == ["group/project", "other/project"]


def test_worktree_paths_separate_the_full_host_project_and_iid_identity(
    fixture: ReviewFixture,
) -> None:
    long_a = f"long/{'a' * 120}"
    long_b = f"long/{'a' * 119}b"
    assert review_slug("gitlab.example", long_a, 7) != review_slug("gitlab.example", long_b, 7)

    first = ok(start(fixture))
    results = [first]
    for remote, project in (
        ("slash", "group/a-b"),
        ("dashed", "group-a/b"),
        ("long-a", long_a),
        ("long-b", long_b),
    ):
        add_project(fixture, remote, f"https://gitlab.example/{project}.git")
        results.append(ok(start(fixture, f"https://gitlab.example/{project}/-/merge_requests/7")))

    paths = [result["review_worktree"]["path"] for result in results]
    assert len(set(paths)) == 5
    for path in paths:
        name = Path(path).name
        assert re.fullmatch(r"mr-gitlab\.example-.*-[0-9a-f]{8}", name)
        assert len(name) <= 96 + 1 + 8
    assert Path(paths[3]).name[:-9] == Path(paths[4]).name[:-9]
    assert len(registry()["items"]) == 5


def test_remote_matching_normalizes_the_project_path_case_on_both_sides(
    make_fixture: Callable[[], ReviewFixture],
) -> None:
    fixture = make_fixture()
    fixture.git("remote", "set-url", "origin", "https://gitlab.example/Group/Project.git")
    fixture.git(
        "config",
        "--add",
        f"url.{fixture.origin}.insteadOf",
        "https://gitlab.example/Group/Project.git",
    )
    result = ok(start(fixture))
    assert result["review_worktree"]["remote"] == "origin"

    fork_fixture = make_fixture()
    fork_head = make_fork(
        fork_fixture, "fork-clone-case", "https://gitlab.example/Fork/Project.git", "contrib"
    )
    write_config(
        fork_fixture, headSha=fork_head, sourceProjectId=21, sourceProjectPath="Fork/Project"
    )
    forked = ok(start(fork_fixture))
    assert forked["review_worktree"]["remote"] == "contrib"
    assert forked["review_worktree"]["refs"]["head_sha"] == fork_head
