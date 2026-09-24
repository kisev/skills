#!/usr/bin/env python3
"""Validate release versions, provenance, and the built Pages distribution."""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORTABLE_PACKAGE = ROOT / "packages" / "skills" / "package.json"
OPENCODE_PACKAGE = ROOT / "packages" / "opencode" / "package.json"
OPENCODE_LOCK = ROOT / "packages" / "opencode" / "package-lock.json"
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
LOCAL_GIT_TIMEOUT_SECONDS = 30
NETWORK_GIT_TIMEOUT_SECONDS = 45
MAX_GIT_OUTPUT_BYTES = 1024 * 1024
GIT_TERMINATION_GRACE_SECONDS = 0.5
GIT_REAP_TIMEOUT_SECONDS = 0.5
GIT_PROCESS_POLL_INTERVAL_SECONDS = 0.01


class ReleaseError(Exception):
    pass


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"expected an object in {path}")
    return value


def git_process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def terminate_git_process_group(process: subprocess.Popen[bytes]) -> None:
    process_group = process.pid
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError:
        with suppress(ProcessLookupError):
            process.kill()

    deadline = time.monotonic() + GIT_TERMINATION_GRACE_SECONDS
    while git_process_group_exists(process_group):
        process.poll()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.01, remaining))

    if git_process_group_exists(process_group):
        try:
            os.killpg(process_group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            with suppress(ProcessLookupError):
                process.kill()
    if process.poll() is None:
        with suppress(ProcessLookupError):
            process.kill()
    try:
        process.wait(timeout=GIT_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise ReleaseError("git process could not be reaped after forced termination") from error


def run_git(arguments: tuple[str, ...], timeout: float) -> subprocess.CompletedProcess[str]:
    if os.name != "posix" or not callable(getattr(os, "killpg", None)):
        raise ReleaseError("git execution requires POSIX process-group capabilities")
    argv = ["git", *arguments]
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    stdout = bytearray()
    stderr = bytearray()
    deadline = time.monotonic() + timeout
    process_group_cleaned = False
    try:
        process = subprocess.Popen(
            argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise ReleaseError("git output pipes are unavailable")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, stdout)
        selector.register(process.stderr, selectors.EVENT_READ, stderr)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ReleaseError(f"git {' '.join(arguments)} timed out after {timeout} seconds")
            if process.poll() is not None and not process_group_cleaned:
                terminate_git_process_group(process)
                process_group_cleaned = True
                deadline = max(deadline, time.monotonic() + GIT_REAP_TIMEOUT_SECONDS)
            remaining = deadline - time.monotonic()
            events = selector.select(min(remaining, GIT_PROCESS_POLL_INTERVAL_SECONDS))
            if not events:
                continue
            for key, _ in events:
                target = key.data
                available = MAX_GIT_OUTPUT_BYTES - len(target)
                chunk = os.read(key.fd, min(64 * 1024, available + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target.extend(chunk)
                if len(target) > MAX_GIT_OUTPUT_BYTES:
                    raise ReleaseError("git output exceeds the size limit")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReleaseError(f"git {' '.join(arguments)} timed out after {timeout} seconds")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            raise ReleaseError(
                f"git {' '.join(arguments)} timed out after {timeout} seconds"
            ) from error
        result = subprocess.CompletedProcess(
            argv,
            returncode,
            bytes(stdout).decode(errors="replace"),
            bytes(stderr).decode(errors="replace"),
        )
    except ReleaseError as error:
        if process is not None:
            try:
                terminate_git_process_group(process)
            except ReleaseError as cleanup_error:
                raise cleanup_error from error
        raise
    except (OSError, ValueError, NotImplementedError) as error:
        if process is not None:
            try:
                terminate_git_process_group(process)
            except ReleaseError as cleanup_error:
                raise cleanup_error from error
        raise ReleaseError("git POSIX subprocess execution is unavailable") from error
    except BaseException:
        if process is not None:
            terminate_git_process_group(process)
        raise
    else:
        if not process_group_cleaned:
            terminate_git_process_group(process)
        return result
    finally:
        if selector is not None:
            with suppress(OSError, ValueError, NotImplementedError):
                selector.close()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def git(*arguments: str) -> str:
    timeout = (
        NETWORK_GIT_TIMEOUT_SECONDS
        if arguments[:1] == ("ls-remote",)
        else LOCAL_GIT_TIMEOUT_SECONDS
    )
    result = run_git(arguments, timeout)
    if result.returncode:
        raise ReleaseError(result.stderr.strip() or f"git {' '.join(arguments)} failed")
    return result.stdout.strip()


def validate(
    tag: str | None = None, *, published: bool = False, require_clean: bool = False
) -> dict[str, str]:
    portable = read_json(PORTABLE_PACKAGE).get("version")
    opencode = read_json(OPENCODE_PACKAGE).get("version")
    lock = read_json(OPENCODE_LOCK)
    lock_root = lock.get("packages")
    if not isinstance(lock_root, dict) or not isinstance(lock_root.get(""), dict):
        raise ReleaseError("OpenCode package lock root is invalid")
    versions = {
        "portable": portable,
        "opencode": opencode,
        "opencode_lock_document": lock.get("version"),
        "opencode_lock": lock_root[""].get("version"),
    }
    if not all(isinstance(value, str) for value in versions.values()):
        raise ReleaseError("release versions must be strings")
    normalized = {name: str(value) for name, value in versions.items()}
    if len(set(normalized.values())) != 1:
        raise ReleaseError(f"release versions differ: {normalized}")
    version = normalized["portable"]
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"invalid release version: {version}")
    if (
        re.search(
            rf"^## \\?\[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
            CHANGELOG.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        is None
    ):
        raise ReleaseError(f"CHANGELOG.md has no release heading for {version}")

    revision = git("rev-parse", "HEAD")
    if require_clean and git("status", "--porcelain"):
        raise ReleaseError("release validation requires a clean working tree")
    expected_revision = os.environ.get("RELEASE_REVISION")
    if expected_revision is not None and expected_revision != revision:
        raise ReleaseError("release environment revision does not match HEAD")
    release_index = read_json(DISTRIBUTION / "index.json")
    if release_index.get("version") != version:
        raise ReleaseError("Pages distribution version does not match release version")
    if release_index.get("source_revision") != revision:
        raise ReleaseError("Pages distribution revision does not match HEAD")

    if published and tag is None:
        raise ReleaseError("published release validation requires a tag")
    if tag is not None:
        expected = f"v{version}"
        if tag != expected:
            raise ReleaseError(f"tag {tag!r} does not match {expected!r}")
        if not published:
            if git("tag", "--list", tag):
                raise ReleaseError(f"release tag {tag!r} already exists locally")
            if git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"):
                raise ReleaseError(f"release tag {tag!r} already exists on origin")
    if published and tag is not None:
        if git("cat-file", "-t", f"refs/tags/{tag}") != "tag":
            raise ReleaseError("release tag must be annotated")
        if git("rev-parse", f"refs/tags/{tag}^{{commit}}") != revision:
            raise ReleaseError("release tag does not reference HEAD")
        stable_tags = [
            value.removeprefix("v")
            for value in git("tag", "--list", "v*").splitlines()
            if SEMVER.fullmatch(value.removeprefix("v"))
        ]
        if stable_tags and tuple(map(int, version.split("."))) != max(
            tuple(map(int, value.split("."))) for value in stable_tags
        ):
            raise ReleaseError("release tag is older than the latest stable tag")
        result = run_git(
            ("merge-base", "--is-ancestor", revision, "origin/main"),
            LOCAL_GIT_TIMEOUT_SECONDS,
        )
        if result.returncode:
            raise ReleaseError("release commit is not reachable from origin/main")

    return {"version": version, "revision": revision}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG"))
    parser.add_argument(
        "--published",
        action="store_true",
        help="require the annotated tag and release commit to exist on origin/main",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="reject uncommitted release inputs",
    )
    args = parser.parse_args(argv)
    try:
        result = validate(args.tag, published=args.published, require_clean=args.require_clean)
    except ReleaseError as error:
        parser.error(str(error))
    print(json.dumps({"status": "ok", **result}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
