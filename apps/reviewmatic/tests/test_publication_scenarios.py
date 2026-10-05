"""Manual runbook safety and bounded mutation-process scenarios."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from helpers.review_fixture import ReviewFixture, complete_draft, make_review_fixture

from reviewmatic import context as review_context
from reviewmatic import draft as draft_module
from reviewmatic.portable.mutation_process import MutationOutcomeUnknown, run_mutation_process
from reviewmatic.portable.portable_gitlab import contract
from reviewmatic.publication import command_argv, send_command, shell_join

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(name="fixture")
def fake_glab_fixture() -> Iterator[ReviewFixture]:
    fixture = make_review_fixture()
    try:
        yield fixture
    finally:
        fixture.close()


def _review_publication_block(fixture: ReviewFixture, state_action: str) -> str:
    if state_action == "reopen":
        config = fixture.read_config()
        contract.write_json(fixture.config_path, {**config, "resolved": True})
    started = draft_module.start_review(url=fixture.url, repo_root=str(fixture.repo))
    draft_path = Path(str(started["draft_path"]))
    draft = complete_draft(contract.read_json(draft_path, "draft"), started)
    if state_action == "reopen":
        thread = draft["content"]["thread_decisions"][0]
        thread.update(
            {
                "assessment": "accepted",
                "severity": "medium",
                "outcome": "reopen",
                "proposed_response": "The resolved thread still needs this correction.",
                "fix_mode": "suggestion",
                "suggestions": [
                    {
                        "path": "review.txt",
                        "line": 2,
                        "body": "The resolved thread still needs this correction.\n\n"
                        "```suggestion\ncorrected change\n```",
                    }
                ],
            }
        )
    contract.write_json(draft_path, draft)
    finished = draft_module.finish_review(str(draft_path))
    assert finished["status"] == "ok", json.dumps(finished)
    markdown = Path(str(finished["markdown_path"])).read_text(encoding="utf-8")
    for match in re.finditer(r"```shell\n(.*?)\n```", markdown, re.DOTALL):
        block = match.group(1)
        if "# Publish reply:" in block:
            return block
    raise RuntimeError("Review runbook does not contain a reply publication block")


def _run_fake_glab_block(
    tmp_path: Path,
    block: str,
    response: str,
    *,
    get_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, Any]]]:
    binary_dir = tmp_path / "fake-bin"
    binary_dir.mkdir(parents=True)
    log_path = tmp_path / "glab-log.jsonl"
    glab = binary_dir / "glab"
    glab.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "argv = sys.argv[1:]\n"
        "method_index = argv.index('--method')\n"
        "method = argv[method_index + 1]\n"
        "endpoint = argv[method_index + 2]\n"
        "host = argv[argv.index('--hostname') + 1]\n"
        "with open(os.environ['FAKE_GLAB_LOG'], 'a', encoding='utf-8') as log:\n"
        "    log.write(json.dumps({'hostname': host, 'method': method, 'endpoint': endpoint, 'argv': argv}) + '\\n')\n"
        "if method == 'GET':\n"
        "    sys.stdout.write(os.environ['FAKE_GLAB_RESPONSE'])\n"
        "    raise SystemExit(int(os.environ['FAKE_GLAB_EXIT']))\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    glab.chmod(0o700)
    environment = {
        **os.environ,
        "PATH": f"{binary_dir}:{os.environ['PATH']}",
        "FAKE_GLAB_LOG": str(log_path),
        "FAKE_GLAB_RESPONSE": response,
        "FAKE_GLAB_EXIT": str(get_exit),
    }
    result = subprocess.run(
        ["sh", "-c", block],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    return result, calls


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
    # This low-level helper runs only the selected write. The generated shell
    # block's head-check sequence is exercised by the fake-glab test above.
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


@pytest.mark.parametrize("state_action", ["resolve", "reopen"])
def test_manual_head_guard_requires_a_matching_successful_get_before_reply_and_state_change(
    fixture: ReviewFixture,
    tmp_path: Path,
    state_action: str,
) -> None:
    block = _review_publication_block(fixture, state_action)
    assert "set -o pipefail" not in block
    valid_head = json.dumps({"sha": fixture.head_sha})

    sent, calls = _run_fake_glab_block(tmp_path / "sent", block, valid_head)
    assert sent.returncode == 0, sent.stderr
    assert [call["method"] for call in calls] == ["GET", "POST", "PUT"]
    assert {call["hostname"] for call in calls} == {"gitlab.example"}
    assert calls[0]["endpoint"] == "projects/19/merge_requests/7"
    assert calls[1]["endpoint"].endswith("/discussions/discussion-42/notes")
    expected_state = "resolved=true" if state_action == "resolve" else "resolved=false"
    assert expected_state in calls[2]["argv"]

    invalid_gets = (
        (json.dumps({"sha": "f" * 40}), 0),
        ("not-json", 0),
        (valid_head, 23),
    )
    for index, (response, exit_code) in enumerate(invalid_gets):
        blocked, rejected_calls = _run_fake_glab_block(
            tmp_path / f"blocked-{index}", block, response, get_exit=exit_code
        )
        assert blocked.returncode != 0
        assert [call["method"] for call in rejected_calls] == ["GET"]
