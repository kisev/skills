from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shared.references.portable_gitlab import contract as portable_gitlab
from shared.references.state_artifacts import (
    StateArtifactError,
    canonical_json,
    content_digest,
    ensure_private_directory,
    execution_status,
    mutation_digest,
    record_success,
    versioned_markdown,
    xdg_state_home,
)
from shared.references.team_runtime import team_workflow
from shared.references.work_item_runtime import triage

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "shared" / "references" / "state_artifacts.py"
DIGEST = "a" * 64


def test_versioned_markdown_retains_body_only_history(tmp_path: Path) -> None:
    stable = tmp_path / "publication.md"
    first = b"# First\n"
    stable.write_bytes(versioned_markdown(stable, first))

    assert stable.read_text().endswith("\n## History\n\n")
    first_snapshot = tmp_path / "history" / "publication" / f"{content_digest(first)}.md"
    assert not first_snapshot.exists()

    stable.write_bytes(versioned_markdown(stable, b"# Second\n"))
    assert stable.read_text().endswith(f"\n## History\n\n- `{first_snapshot}`\n")
    assert first_snapshot.read_bytes() == first

    unchanged = versioned_markdown(stable, b"# Second\n")
    assert unchanged == stable.read_bytes()
    assert len(list((tmp_path / "history" / "publication").glob("*.md"))) == 1


def test_versioned_markdown_rejects_forged_history_path(tmp_path: Path) -> None:
    stable = tmp_path / "publication.md"
    (tmp_path / "history" / "publication").mkdir(parents=True)
    forged = tmp_path / "history" / "publication" / ".." / f"{'a' * 64}.md"
    stable.write_text(f"current\n\n## History\n\n- `{forged}`\n")

    with pytest.raises(StateArtifactError, match="history path is invalid"):
        versioned_markdown(stable, b"replacement\n")


def test_versioned_markdown_rejects_malformed_owned_footer(tmp_path: Path) -> None:
    stable = tmp_path / "publication.md"
    (tmp_path / "history" / "publication").mkdir(parents=True)
    stable.write_text("current\n\n## History\n\nnot a snapshot path\n")

    with pytest.raises(StateArtifactError, match="footer is malformed"):
        versioned_markdown(stable, b"replacement\n")


def test_versioned_markdown_archives_legacy_current(tmp_path: Path) -> None:
    stable = tmp_path / "handoff.md"
    stable.write_text("legacy\n")

    stable.write_bytes(versioned_markdown(stable, b"current\n"))

    legacy = tmp_path / "history" / "handoff" / f"{content_digest(b'legacy\n')}.md"
    assert legacy.read_text() == "legacy\n"
    assert f"- `{legacy}`" in stable.read_text()


def test_legacy_markdown_may_end_with_ordinary_history_section(tmp_path: Path) -> None:
    stable = tmp_path / "handoff.md"
    legacy = b"legacy\n\n## History\n\nordinary prose\n"
    stable.write_bytes(legacy)

    stable.write_bytes(versioned_markdown(stable, b"current\n"))

    snapshot = stable.parent / "history" / stable.stem / f"{content_digest(legacy)}.md"
    assert snapshot.read_bytes() == legacy


def test_legacy_history_migration_retries_after_failed_current_write(tmp_path: Path) -> None:
    stable = tmp_path / "handoff.md"
    legacy = b"legacy\n\n## History\n\nordinary prose\n"
    stable.write_bytes(legacy)

    versioned_markdown(stable, b"first candidate\n")
    replacement = versioned_markdown(stable, b"second candidate\n")
    stable.write_bytes(replacement)

    snapshot = stable.parent / "history" / stable.stem / f"{content_digest(legacy)}.md"
    assert snapshot.read_bytes() == legacy
    assert stable.read_text().startswith("second candidate\n\n## History\n")


def test_legacy_safe_directory_modes_are_migrated(
    tmp_path: Path,
) -> None:
    boundary = tmp_path / "state"
    legacy = boundary / "agent-skills"
    legacy.mkdir(parents=True, mode=0o755)
    legacy.chmod(0o755)

    target = ensure_private_directory(legacy / "skill", boundary)

    assert target.is_dir()
    assert boundary.stat().st_mode & 0o077 == 0
    assert legacy.stat().st_mode & 0o077 == 0


def test_uncommitted_markdown_candidate_is_not_archived(tmp_path: Path) -> None:
    stable = tmp_path / "publication.md"
    first = b"first\n"
    second = b"second\n"
    stable.write_bytes(versioned_markdown(stable, first))

    versioned_markdown(stable, second)

    history = stable.parent / "history" / stable.stem
    assert (history / f"{content_digest(first)}.md").is_file()
    assert not (history / f"{content_digest(second)}.md").exists()


def test_failed_snapshot_write_removes_partial_immutable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stable = tmp_path / "publication.md"
    first = b"first\n"
    stable.write_bytes(versioned_markdown(stable, first))
    snapshot = stable.parent / "history" / stable.stem / f"{content_digest(first)}.md"

    monkeypatch.setattr(os, "fsync", lambda _descriptor: (_ for _ in ()).throw(OSError("fail")))
    with pytest.raises(OSError, match="fail"):
        versioned_markdown(stable, b"second\n")
    assert not snapshot.exists()


def test_marker_runner_records_only_success(tmp_path: Path) -> None:
    environment = {**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")}
    mutation = [sys.executable, "-c", "print('ok')"]
    previous = os.environ.get("XDG_STATE_HOME")
    os.environ["XDG_STATE_HOME"] = environment["XDG_STATE_HOME"]
    try:
        assert (
            execution_status(mutation, skill="test-skill", action="publish", binding=DIGEST)
            == "not_run"
        )
    finally:
        if previous is None:
            del os.environ["XDG_STATE_HOME"]
        else:
            os.environ["XDG_STATE_HOME"] = previous
    success = subprocess.run(
        [
            sys.executable,
            str(RUNTIME),
            "marker-run",
            "--skill",
            "test-skill",
            "--action",
            "publish",
            "--binding",
            DIGEST,
            "--",
            *mutation,
        ],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert success.returncode == 0
    assert success.stdout == "ok\n"
    markers = list((tmp_path / "state").rglob("*.json"))
    assert len(markers) == 1
    marker = json.loads(markers[0].read_text())
    assert marker["schema"] == "agent-skills/post-success-marker/v1"
    assert marker["exit_status"] == 0
    assert markers[0].stat().st_mode & 0o077 == 0
    previous = os.environ.get("XDG_STATE_HOME")
    os.environ["XDG_STATE_HOME"] = environment["XDG_STATE_HOME"]
    try:
        assert (
            execution_status(mutation, skill="test-skill", action="publish", binding=DIGEST)
            == "run_unverified"
        )
    finally:
        if previous is None:
            del os.environ["XDG_STATE_HOME"]
        else:
            os.environ["XDG_STATE_HOME"] = previous

    failure = subprocess.run(
        [
            sys.executable,
            str(RUNTIME),
            "marker-run",
            "--skill",
            "test-skill",
            "--action",
            "fail",
            "--binding",
            DIGEST,
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        env=environment,
        check=False,
    )
    assert failure.returncode == 7
    assert len(list((tmp_path / "state").rglob("*.json"))) == 1


def test_marker_runner_checks_stdin_before_mutation(tmp_path: Path) -> None:
    touched = tmp_path / "touched"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNTIME),
            "marker-run",
            "--skill",
            "test-skill",
            "--action",
            "stdin",
            "--binding",
            DIGEST,
            "--stdin-sha256",
            "b" * 64,
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(touched)!r}).touch()",
        ],
        input=b"payload",
        env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")},
        check=False,
    )
    assert result.returncode == 2
    assert not touched.exists()


def test_marker_runner_preserves_success_when_marker_write_fails(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.write_text("not a directory")
    touched = tmp_path / "touched"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNTIME),
            "marker-run",
            "--skill",
            "test-skill",
            "--action",
            "write-failure",
            "--binding",
            DIGEST,
            "--",
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(touched)!r}).touch()",
        ],
        env={**os.environ, "XDG_STATE_HOME": str(state)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert touched.is_file()
    assert "revalidate the target before retrying" in result.stderr


def test_marker_runner_checks_exact_git_head(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / "tracked").write_text("value\n")
    subprocess.run(["git", "add", "tracked"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=repository,
        check=True,
    )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    touched = tmp_path / "touched"
    base = [
        sys.executable,
        str(RUNTIME),
        "marker-run",
        "--skill",
        "test-skill",
        "--action",
        "git-apply",
        "--binding",
        DIGEST,
        "--cwd",
        str(repository),
        "--git-head-digest",
    ]
    mutation = [
        "--",
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(touched)!r}).touch()",
    ]
    stale = subprocess.run(
        [*base, "b" * 64, *mutation],
        env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")},
        check=False,
    )
    assert stale.returncode == 3
    assert not touched.exists()

    current = subprocess.run(
        [*base, content_digest(canonical_json({"git_head": head})), *mutation],
        env={**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")},
        check=False,
    )
    assert current.returncode == 0
    assert touched.is_file()


def test_marker_reader_rejects_naive_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    argv = ["true"]
    mutation = mutation_digest(argv, None)
    path = record_success("test-skill", "timestamp", DIGEST, mutation)
    marker = json.loads(path.read_text())
    marker["succeeded_at"] = "2026-09-23T12:00:00"
    path.write_text(json.dumps(marker))

    with pytest.raises(StateArtifactError, match="timestamp is invalid"):
        execution_status(argv, skill="test-skill", action="timestamp", binding=DIGEST)


def test_xdg_state_rejects_relative_and_symlink_ancestor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", "relative-state")
    with pytest.raises(StateArtifactError, match="absolute normalized"):
        xdg_state_home()

    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(linked))
    with pytest.raises(StateArtifactError, match="state directory is unsafe"):
        execution_status(["true"], skill="test-skill", action="symlink", binding=DIGEST)
    with pytest.raises(StateArtifactError, match="state directory is unsafe"):
        record_success("test-skill", "symlink", DIGEST, DIGEST)


def test_state_directory_rejects_lexical_traversal(tmp_path: Path) -> None:
    boundary = tmp_path / "state"
    target = boundary / "private" / ".." / ".." / "outside"
    with pytest.raises(StateArtifactError, match="normalized"):
        ensure_private_directory(target, boundary)


def test_all_python_state_runtimes_reject_relative_xdg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", "relative-state")
    target = {
        "hostname": "gitlab.example",
        "project_id": 1,
        "kind": "merge_request",
        "iid": 2,
    }
    with pytest.raises(ValueError, match="absolute normalized"):
        portable_gitlab.state_directory("code-review", target)
    with pytest.raises(ValueError, match="absolute normalized"):
        triage.state_root({"target": "example"})
    with pytest.raises(ValueError, match="absolute normalized"):
        team_workflow.state_root()


def test_team_profile_rejects_symlinked_config_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "config"
    outside = tmp_path / "outside"
    config.mkdir()
    outside.mkdir()
    (config / "opencode").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    with pytest.raises(team_workflow.WorkflowError, match="unsafe"):
        team_workflow.profile_root(create=True)
