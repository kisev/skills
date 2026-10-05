"""Publication command scenarios ported from ``publication.test.mjs``.

The TypeScript manual-send scenarios drive the TUI send path (head verification
and ``AbortSignal`` cancellation). Python has no TUI, so those two scenarios are
reduced to the underlying command behavior: ``send_command`` runs the planned
``glab`` command through the mutation process, a failed write can be repeated,
no publication state is kept, and a slow request is bounded by the mutation
timeout without blocking a later send.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic.portable.mutation_process import MutationOutcomeUnknown, run_mutation_process
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.publication import command_argv, send_command, shell_join

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Iterator


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def test_direct_commands_preserve_arguments_and_never_evaluate_shell_content() -> None:
    argv = [
        "glab",
        "api",
        "--hostname",
        "gitlab.example",
        "-f",
        "body=it's $(not a command); one\ntwo",
    ]
    assert command_argv(shell_join(argv)) == argv
    with pytest.raises(contract.WorkflowError, match=r"historical"):
        command_argv("reviewmatic publication apply --action old")


def test_manual_sends_make_one_write_can_fail_and_repeat_and_keep_no_publication_state(
    fixture: ReviewFixture,
) -> None:
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    root = Path(str(started["artifact_root"]))
    draft_path = Path(str(started["draft_path"]))
    contract.write_json(
        draft_path, complete_draft(contract.read_json(draft_path, "draft"), started)
    )
    draft_module.finish_review(str(draft_path))
    progress = review_context.load_progress(root)
    assert progress is not None
    _, plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
    reply = next(
        action
        for action in plan["publication_preview"]["actions"]
        if str(action.get("publication_id") or "").startswith("thread-")
        and action["operation"] == "reply"
    )
    requests = fixture.request_count()

    config = fixture.read_config()
    contract.write_json(fixture.config_path, {**config, "mutationError": "connection reset"})
    failed = send_command(str(reply["command"]))
    assert failed.returncode == 1
    assert "connection reset" in failed.stderr.decode()

    contract.write_json(fixture.config_path, config)
    assert send_command(str(reply["command"])).returncode == 0
    assert send_command(str(reply["command"])).returncode == 0
    assert len(fixture.read_config()["publishedNotes"]) == 2
    # The TypeScript TUI adds one head-check GET per send (6 requests); the
    # Python command path performs exactly one write per send.
    assert fixture.request_count() - requests == 3
    assert not (root / "code-review-publication").exists()
    assert not (root / "artifacts" / "publication_actions").exists()
    book = (root / "runbook.md").read_text(encoding="utf-8")
    assert "glab api" in book
    assert "reviewmatic publication" not in book


def test_a_slow_request_is_bounded_and_does_not_block_a_subsequent_send(
    fixture: ReviewFixture,
) -> None:
    binary = fixture.tmp / "bin" / "glab"
    binary.write_text("#!/bin/sh\nsleep 20\n")
    binary.chmod(0o755)
    started = time.monotonic()
    with pytest.raises(MutationOutcomeUnknown, match=r"timed out"):
        run_mutation_process(["glab", "api", "example"], b"", timeout=0.2)
    assert time.monotonic() - started < 10
    binary.write_text("#!/bin/sh\nexit 0\n")
    result: subprocess.CompletedProcess[bytes] = send_command("glab api example")
    assert result.returncode == 0
