"""Mutation process contract, ported from ``mutation-process.test.mjs``."""

from __future__ import annotations

import pytest

from reviewmatic.portable.mutation_process import (
    MutationNotAttempted,
    MutationOutcomeUnknown,
    run_mutation_process,
)


def test_successful_mutation_run_captures_stdout_stderr_and_exit_code() -> None:
    result = run_mutation_process(["sh", "-c", "printf ok; printf err 1>&2"], b"")
    assert result.returncode == 0
    assert result.stdout == b"ok"
    assert result.stderr == b"err"


def test_mutation_stdin_payload_reaches_the_child() -> None:
    result = run_mutation_process(["cat"], b"payload\n")
    assert result.returncode == 0
    assert result.stdout == b"payload\n"


def test_nonzero_exit_code_is_reported_without_raising() -> None:
    assert run_mutation_process(["sh", "-c", "exit 3"], b"").returncode == 3


def test_timeout_raises_mutation_outcome_unknown() -> None:
    with pytest.raises(MutationOutcomeUnknown) as raised:
        run_mutation_process(["sh", "-c", "sleep 5"], b"", timeout=0.2)
    assert str(raised.value) == "GitLab mutation timed out; inspect the target"


def test_output_limit_raises_mutation_outcome_unknown() -> None:
    with pytest.raises(MutationOutcomeUnknown) as raised:
        run_mutation_process(
            ["sh", "-c", "dd if=/dev/zero bs=1024 count=64 status=none"],
            b"",
            output_limit=1024,
            timeout=10,
        )
    assert str(raised.value) == "GitLab mutation output exceeds the size limit; inspect the target"


def test_missing_binary_raises_mutation_not_attempted() -> None:
    with pytest.raises(MutationNotAttempted) as raised:
        run_mutation_process(["reviewmatic-nonexistent-binary-4f2a"], b"")
    assert str(raised.value) == "GitLab mutation was not attempted; retry is safe"
