"""Bounded POSIX process execution with conservative mutation outcomes."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import time
from contextlib import suppress


class MutationNotAttempted(ValueError):
    """The child process provably did not start."""


class MutationOutcomeUnknown(ValueError):
    """The child started; failure does not prove absence of mutation."""


def terminate(process: subprocess.Popen[bytes], grace: float) -> None:
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired as exc:
        raise MutationOutcomeUnknown("GitLab mutation cleanup failed; inspect the target") from exc


def run_mutation_process(
    command: list[str],
    payload: bytes,
    *,
    timeout: float = 60,
    output_limit: int = 1024 * 1024,
    grace: float = 0.5,
) -> subprocess.CompletedProcess[bytes]:
    if os.name != "posix" or not callable(getattr(os, "killpg", None)):
        raise MutationNotAttempted("GitLab mutation requires POSIX process groups")
    try:
        process = subprocess.Popen(  # noqa: S603
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except (OSError, ValueError, NotImplementedError) as exc:
        raise MutationNotAttempted("GitLab mutation was not attempted; retry is safe") from exc
    selector: selectors.BaseSelector | None = None
    streams: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise MutationOutcomeUnknown("GitLab mutation pipes are unavailable")
        selector = selectors.DefaultSelector()
        for name, stream in (
            ("stdin", process.stdin),
            ("stdout", process.stdout),
            ("stderr", process.stderr),
        ):
            os.set_blocking(stream.fileno(), False)
            selector.register(
                stream, selectors.EVENT_WRITE if name == "stdin" else selectors.EVENT_READ, name
            )
        written = 0
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MutationOutcomeUnknown("GitLab mutation timed out; inspect the target")
            for key, _ in selector.select(remaining):
                if key.data == "stdin":
                    try:
                        written += os.write(key.fd, payload[written : written + 4096])
                    except BrokenPipeError:
                        written = len(payload)
                    except BlockingIOError:
                        continue
                    if written >= len(payload):
                        selector.unregister(key.fileobj)
                        process.stdin.close()
                else:
                    try:
                        chunk = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        streams[key.data].extend(chunk)
                        if len(streams[key.data]) > output_limit:
                            raise MutationOutcomeUnknown(
                                "GitLab mutation output exceeds the size limit; inspect the target"
                            )
        try:
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise MutationOutcomeUnknown("GitLab mutation timed out; inspect the target") from exc
    except (OSError, ValueError, NotImplementedError) as exc:
        raise MutationOutcomeUnknown(str(exc)) from exc
    finally:
        try:
            terminate(process, grace)
        finally:
            try:
                if selector is not None:
                    selector.close()
                for remaining_stream in (process.stdin, process.stdout, process.stderr):
                    if remaining_stream is not None:
                        remaining_stream.close()
            except (OSError, ValueError, NotImplementedError) as exc:
                raise MutationOutcomeUnknown(
                    "GitLab mutation cleanup failed; inspect the target"
                ) from exc
    return subprocess.CompletedProcess(
        command, code, bytes(streams["stdout"]), bytes(streams["stderr"])
    )
