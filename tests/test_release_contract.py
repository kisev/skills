from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import subprocess
import time
import urllib.error
from contextlib import suppress
from email.message import Message
from pathlib import Path

import pytest

from scripts import (
    build_distribution,
    build_release_artifacts,
    check_release,
    compose_pages_site,
    create_github_release,
    dev_version,
    publish_npm_release,
    verify_distribution_url,
)

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"
PACKAGE_METADATA = json.loads(
    (ROOT / "packages" / "agentomatic" / "package.json").read_text(encoding="utf-8")
)
RELEASE_VERSION = PACKAGE_METADATA["version"]


def test_current_release_metadata_is_aligned() -> None:
    assert build_distribution.build(DISTRIBUTION, False) == 0
    result = check_release.validate()
    assert result["version"] == RELEASE_VERSION
    assert (
        result["revision"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )


@pytest.mark.parametrize("version", ["01.2.3", "1.02.3", "1.2.03"])
def test_release_version_rejects_leading_zeroes(version: str) -> None:
    assert check_release.SEMVER.fullmatch(version) is None


def test_dev_version_uses_stable_base_run_and_revision() -> None:
    revision = "a" * 40
    assert dev_version.derive("10.0.0", "418", revision) == "10.0.0-dev.418.gaaaaaaaaaaaa"


@pytest.mark.parametrize(
    ("run_number", "revision"),
    [("0", "a" * 40), ("01", "a" * 40), ("1", "not-a-revision")],
)
def test_dev_version_rejects_ambiguous_identity(run_number: str, revision: str) -> None:
    with pytest.raises(ValueError, match=r"run number|revision"):
        dev_version.derive("10.0.0", run_number, revision)


def test_release_check_rejects_package_version_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps({"version": "9.9.9"}), encoding="utf-8")
    monkeypatch.setattr(check_release, "PORTABLE_PACKAGE", manifest)

    with pytest.raises(check_release.ReleaseError, match="versions differ"):
        check_release.validate()


def test_release_check_rejects_distribution_revision_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distribution = tmp_path / "distribution"
    distribution.mkdir()
    (distribution / "index.json").write_text(
        json.dumps({"version": RELEASE_VERSION, "source_revision": "0" * 40}), encoding="utf-8"
    )
    monkeypatch.setattr(check_release, "DISTRIBUTION", distribution)

    with pytest.raises(check_release.ReleaseError, match="revision"):
        check_release.validate()


def test_pre_tag_check_validates_name_without_requiring_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = f"v{RELEASE_VERSION}"
    real_git = check_release.git

    def git(*arguments: str) -> str:
        empty_results = {
            ("tag", "--list", tag),
            (
                "ls-remote",
                "--tags",
                "origin",
                f"refs/tags/{tag}",
                f"refs/tags/{tag}^{{}}",
            ),
        }
        if arguments in empty_results:
            return ""
        return real_git(*arguments)

    monkeypatch.setattr(check_release, "git", git)

    assert check_release.validate(tag)["version"] == RELEASE_VERSION


@pytest.mark.parametrize("location", ["locally", "on origin"])
def test_pre_tag_check_rejects_existing_tag(monkeypatch: pytest.MonkeyPatch, location: str) -> None:
    tag = f"v{RELEASE_VERSION}"
    real_git = check_release.git

    def git(*arguments: str) -> str:
        if arguments == ("tag", "--list", tag):
            return tag if location == "locally" else ""
        if arguments[:3] == ("ls-remote", "--tags", "origin"):
            return f"{'a' * 40}\trefs/tags/{tag}" if location == "on origin" else ""
        return real_git(*arguments)

    monkeypatch.setattr(check_release, "git", git)
    with pytest.raises(check_release.ReleaseError, match=location):
        check_release.validate(tag)


def test_network_git_timeout_is_bounded_and_controlled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "git"
    executable.write_text("#!/bin/sh\nsleep 10\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setattr(check_release, "NETWORK_GIT_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(check_release.ReleaseError, match=r"ls-remote.*timed out"):
        check_release.git("ls-remote", "--tags", "origin")


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups are required")
def test_git_timeout_kills_real_descendant_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "descendant-pid"
    executable = tmp_path / "git"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, signal, time\n"
        "pid = os.fork()\n"
        f"path = pathlib.Path({str(pid_path)!r})\n"
        "if pid == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    path.write_text(str(os.getpid()))\n"
        "    time.sleep(10)\n"
        "while not path.exists():\n"
        "    time.sleep(0.01)\n"
        "time.sleep(10)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setattr(check_release, "LOCAL_GIT_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(check_release, "GIT_TERMINATION_GRACE_SECONDS", 0.05)

    with pytest.raises(check_release.ReleaseError, match="timed out"):
        check_release.git("status")

    descendant_pid = int(pid_path.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 2
    try:
        while time.monotonic() < deadline:
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            status_path = Path(f"/proc/{descendant_pid}/stat")
            # Reaping may remove /proc state after the liveness check.
            with suppress(FileNotFoundError, ProcessLookupError):
                if status_path.read_text().split()[2] == "Z":
                    break
            time.sleep(0.01)
        else:
            pytest.fail("git descendant remained alive after timeout cleanup")
    finally:
        with suppress(ProcessLookupError):
            os.kill(descendant_pid, signal.SIGKILL)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups are required")
def test_successful_git_cleans_real_descendant_and_keeps_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "descendant-pid"
    executable = tmp_path / "git"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, signal, sys, time\n"
        "pid = os.fork()\n"
        f"path = pathlib.Path({str(pid_path)!r})\n"
        "if pid == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    path.write_text(str(os.getpid()))\n"
        "    time.sleep(10)\n"
        "while not path.exists():\n"
        "    time.sleep(0.01)\n"
        "sys.stdout.write('completed stdout')\n"
        "sys.stderr.write('completed stderr')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setattr(check_release, "GIT_TERMINATION_GRACE_SECONDS", 0.05)

    result = check_release.run_git(("status",), 1)

    assert result.returncode == 0
    assert result.stdout == "completed stdout"
    assert result.stderr == "completed stderr"
    descendant_pid = int(pid_path.read_text(encoding="utf-8"))
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                break
            status_path = Path(f"/proc/{descendant_pid}/stat")
            with suppress(FileNotFoundError, ProcessLookupError):
                if status_path.read_text().split()[2] == "Z":
                    break
            time.sleep(0.01)
        else:
            pytest.fail("git descendant remained alive after successful cleanup")
    finally:
        with suppress(ProcessLookupError):
            os.kill(descendant_pid, signal.SIGKILL)


def test_git_reports_unsupported_process_group_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.check_release.os.name", "nt")
    with pytest.raises(check_release.ReleaseError, match="requires POSIX"):
        check_release.git("status")


@pytest.mark.parametrize("descriptor", [1, 2])
def test_git_bounds_stdout_and_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, descriptor: int
) -> None:
    executable = tmp_path / "git"
    executable.write_text(
        f"#!/usr/bin/env python3\nimport os\nos.write({descriptor}, b'x' * 17)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setattr(check_release, "MAX_GIT_OUTPUT_BYTES", 16)

    with pytest.raises(check_release.ReleaseError, match="size limit"):
        check_release.git("status")


def test_published_release_check_requires_tag() -> None:
    with pytest.raises(check_release.ReleaseError, match="requires a tag"):
        check_release.validate(published=True)


def test_release_check_can_require_a_clean_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    real_git = check_release.git

    def dirty_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return " M package.json"
        return real_git(*arguments)

    monkeypatch.setattr(check_release, "git", dirty_git)
    with pytest.raises(check_release.ReleaseError, match="clean working tree"):
        check_release.validate(require_clean=True)


def test_release_artifact_hashes_use_registry_integrity_format() -> None:
    content = b"exact npm artifact"
    result = build_release_artifacts.hashes(content)
    assert result == {
        "integrity": "sha512-9cADN2L/vB2zEFdBHq66/d4Ci/RXK+ncTZhxohgxH1L+4d4ikt8KFcx6DeKr2I9+WiUkgEosZ5y9BzACKIdy5A==",
        "sha1": "b4c0edb8f3c4b04bada4dd57d6bf69f3601c7b5f",
        "sha512": "f5c0033762ffbc1db31057411eaebafdde028bf4572be9dc4d9871a218311f52fee1de2292df0a15cc7a0de2abd88f7e5a2524804a2c679cbd073002288772e4",
    }


def test_release_notes_are_taken_from_the_exact_changelog_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changes\n\n"
        "## [9.9.9] - 2026-09-15\n\n### Added\n\n- Current release.\n\n"
        "## [9.9.8] - 2026-09-14\n\n### Fixed\n\n- Previous release.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(create_github_release, "ROOT", tmp_path)
    assert create_github_release.changelog("9.9.9") == "### Added\n\n- Current release.\n"


def test_npm_provenance_binds_artifact_workflow_and_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    sha512 = "b" * 128
    statement = {
        "subject": [{"digest": {"sha512": sha512}}],
        "predicate": {
            "buildDefinition": {
                "externalParameters": {
                    "workflow": {
                        "path": ".github/workflows/publish.yml",
                        "repository": "https://github.com/kisev/skills",
                    }
                },
                "resolvedDependencies": [{"digest": {"gitCommit": revision}}],
            }
        },
    }
    encoded = base64.b64encode(json.dumps(statement).encode()).decode()
    metadata = {
        "dist": {
            "attestations": {
                "url": "https://registry.example/attestations",
                "provenance": {"predicateType": publish_npm_release.SLSA_PREDICATE},
            }
        }
    }
    document = {
        "attestations": [
            {
                "predicateType": publish_npm_release.SLSA_PREDICATE,
                "bundle": {"dsseEnvelope": {"payload": encoded}},
            }
        ]
    }
    responses = iter([None, document])
    sleeps: list[float] = []
    monkeypatch.setattr(publish_npm_release, "request_json", lambda _url: next(responses))
    monkeypatch.setattr("scripts.publish_npm_release.time.sleep", sleeps.append)
    publish_npm_release.verify_provenance(metadata, sha512, revision, attempts=2, delay=0.01)
    assert sleeps == [0.01]
    monkeypatch.setattr(publish_npm_release, "request_json", lambda _url: document)
    monkeypatch.setattr(
        time,
        "sleep",
        lambda _: pytest.fail("must not retry mismatched provenance"),
    )
    with pytest.raises(publish_npm_release.PublicationError, match="does not bind"):
        publish_npm_release.verify_provenance(metadata, sha512, "c" * 40, attempts=3)

    refreshed_responses = iter([metadata, None, document])
    monkeypatch.setattr(publish_npm_release, "request_json", lambda _url: next(refreshed_responses))
    monkeypatch.setattr(time, "sleep", sleeps.append)
    publish_npm_release.verify_provenance(
        {"dist": {}},
        sha512,
        revision,
        attempts=3,
        delay=0.01,
        metadata_url="https://registry.example/version",
    )


def test_trusted_publishing_rejects_an_old_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publish_npm_release, "command", lambda *_args: "11.5.0\n")
    with pytest.raises(publish_npm_release.PublicationError, match=r"11\.5\.1"):
        publish_npm_release.require_trusted_publishing_npm()


def test_registry_tarball_download_retries_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://registry.example/package.tgz"
    responses: list[object] = [
        urllib.error.HTTPError(url, 404, "Not Found", Message(), None),
        type(
            "Response",
            (),
            {
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "geturl": lambda self: url,
                "read": lambda self: b"tarball",
            },
        )(),
    ]
    sleeps: list[float] = []

    def urlopen(_request: object, timeout: int) -> object:
        assert timeout == 30
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("scripts.publish_npm_release.urllib.request.urlopen", urlopen)
    monkeypatch.setattr("scripts.publish_npm_release.time.sleep", sleeps.append)

    assert publish_npm_release.download_registry_tarball(url, attempts=2, delay=0.01) == b"tarball"
    assert sleeps == [0.01]


@pytest.mark.parametrize(
    "registry",
    ["https://registry.example/base?token=value", "https://registry.example/base#fragment"],
)
def test_registry_base_rejects_query_and_fragment(
    monkeypatch: pytest.MonkeyPatch, registry: str
) -> None:
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", registry)
    with pytest.raises(publish_npm_release.PublicationError, match="credential-free HTTPS"):
        publish_npm_release.registry_url("@example/package", "1.0.0")


def test_registry_response_rejects_https_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    response = type(
        "Response",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *_args: None,
            "geturl": lambda self: "http://registry.example/package",
            "read": lambda self: b"{}",
        },
    )()
    monkeypatch.setattr(
        "scripts.publish_npm_release.urllib.request.urlopen", lambda *_args, **_kwargs: response
    )

    with pytest.raises(publish_npm_release.PublicationError, match="credential-free HTTPS"):
        publish_npm_release.request_json("https://registry.example/package")


def test_distribution_fetch_rejects_https_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    response = type(
        "Response",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *_args: None,
            "geturl": lambda self: "http://pages.example/index.json",
            "read": lambda self: b"{}",
            "status": 200,
        },
    )()
    monkeypatch.setattr(
        "scripts.verify_distribution_url.urllib.request.urlopen",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(verify_distribution_url.VerificationError, match="credential-free HTTPS"):
        verify_distribution_url.fetch("https://pages.example/index.json")


def test_registry_smoke_installs_the_optional_runtime_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def command(*arguments: str, **_kwargs: object) -> str:
        calls.append(arguments)
        if arguments[-1:] == ("--version",):
            return f"{RELEASE_VERSION}\n"
        if arguments[-2:] == ("capabilities", "--json"):
            return json.dumps({"status": "ok", "version": RELEASE_VERSION}) + "\n"
        return ""

    monkeypatch.setattr(publish_npm_release, "command", command)
    publish_npm_release.registry_smoke("@kisev/agentomatic", RELEASE_VERSION)
    install = next(arguments for arguments in calls if arguments[:2] == ("npm", "install"))
    assert f"@kisev/agentomatic@{RELEASE_VERSION}" in install
    assert "@opencode-ai/plugin@1.18.29" in install
    assert ("npm", "audit", "signatures", "--json") in calls


def test_registry_wait_survives_four_minute_propagation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clock = [0.0]
    pauses: list[float] = []

    def sleep(seconds: float) -> None:
        pauses.append(seconds)
        clock[0] += seconds

    def read() -> bytes:
        if clock[0] < 240:
            raise publish_npm_release.RegistryPending("HTTP 404")
        return b"exact artifact"

    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", sleep)
    assert publish_npm_release.wait_for_registry("tarball", read, 60, 5) == b"exact artifact"
    assert pauses[:4] == [5, 10, 20, 30]
    assert max(pauses) == 30
    assert "waiting for registry propagation" in capsys.readouterr().err


def test_registry_stages_share_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [590.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    assert publish_npm_release.wait_for_registry("provenance", lambda: None, 60, 5, 600) is None
    assert clock[0] == 600


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_registry_metadata_transient_errors_are_retryable(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://registry.example/", status, "unavailable", Message(), None
        )

    monkeypatch.setattr("scripts.publish_npm_release.urllib.request.urlopen", unavailable)
    with pytest.raises(publish_npm_release.RegistryPending):
        publish_npm_release.request_json("https://registry.example/")


def test_registry_authorization_failure_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError("https://registry.example/", 403, "forbidden", Message(), None)

    monkeypatch.setattr("scripts.publish_npm_release.urllib.request.urlopen", forbidden)
    monkeypatch.setattr(time, "sleep", lambda _: pytest.fail("must not retry 403"))
    with pytest.raises(publish_npm_release.PublicationError, match="HTTP 403"):
        publish_npm_release.download_registry_tarball("https://registry.example/archive")


def test_existing_registry_version_is_verified_without_republication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    content = b"exact artifact"
    npm = {"name": "@example/package", **build_release_artifacts.hashes(content)}
    release = {"npm": npm, "version": "1.0.0", "revision": "a" * 40}
    metadata = {
        "dist": {"integrity": npm["integrity"], "tarball": "https://registry.example/archive"}
    }
    monkeypatch.setattr(publish_npm_release, "require_trusted_publishing_npm", lambda: None)
    monkeypatch.setattr(
        publish_npm_release, "manifest", lambda: (release, tmp_path / "package.tgz")
    )
    monkeypatch.setattr(publish_npm_release, "request_json", lambda _url: metadata)
    monkeypatch.setattr(
        publish_npm_release, "download_registry_tarball", lambda *_args, **_kwargs: content
    )
    monkeypatch.setattr(publish_npm_release, "verify_provenance", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(publish_npm_release, "verify_dist_tag", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(publish_npm_release, "registry_smoke", lambda *_args: None)
    monkeypatch.setattr(
        publish_npm_release, "command", lambda *_args: pytest.fail("must not republish")
    )
    assert publish_npm_release.publish() == metadata
    metadata["dist"]["integrity"] = "wrong"
    with pytest.raises(publish_npm_release.PublicationError, match="differs"):
        publish_npm_release.publish()


def test_dev_manifest_requires_dev_dist_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = {
        "schema": "@kisev/skills-dev/v1",
        "npm": {"name": "@example/package"},
        "version": "1.0.0-dev.1.gabcdef0",
        "revision": "a" * 40,
    }
    monkeypatch.setattr(publish_npm_release, "require_trusted_publishing_npm", lambda: None)
    monkeypatch.setattr(
        publish_npm_release, "manifest", lambda: (release, tmp_path / "package.tgz")
    )
    monkeypatch.setenv("NPM_DIST_TAG", "latest")
    with pytest.raises(publish_npm_release.PublicationError, match="requires npm dist-tag 'dev'"):
        publish_npm_release.publish()


def test_pages_composition_keeps_stable_root_and_dev_subpath(tmp_path: Path) -> None:
    stable = tmp_path / "stable"
    dev = tmp_path / "dev-source"
    stable.mkdir()
    dev.mkdir()
    (stable / "index.json").write_text("stable\n", encoding="utf-8")
    (stable / ".nojekyll").write_text("", encoding="utf-8")
    (dev / "index.json").write_text("dev\n", encoding="utf-8")
    output = tmp_path / "site"
    compose_pages_site.compose(
        output,
        stable_dir=stable,
        stable_url=None,
        dev_dir=dev,
        dev_url=None,
    )
    assert (output / "index.json").read_text(encoding="utf-8") == "stable\n"
    assert (output / "dev/index.json").read_text(encoding="utf-8") == "dev\n"


def test_remote_pages_copy_rejects_lock_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    assert build_distribution.build(source, False) == 0
    payloads = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        compose_pages_site,
        "fetch",
        lambda _base, relative: payloads[relative],
    )
    target = tmp_path / "target"
    compose_pages_site.copy_remote("https://pages.example/skills", target)
    assert (target / "index.json").read_bytes() == payloads["index.json"]

    lock = json.loads(payloads["skills-lock.json"])
    lock["archives"].pop(next(iter(lock["archives"])))
    payloads["skills-lock.json"] = json.dumps(lock).encode()
    payloads[".well-known/skills/lock.json"] = payloads["skills-lock.json"]
    with pytest.raises(compose_pages_site.ComposeError, match="lock differs"):
        compose_pages_site.copy_remote("https://pages.example/skills", tmp_path / "bad")


def test_remote_pages_copy_fails_closed_when_channel_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = urllib.error.HTTPError(
        "https://pages.example/skills/dev/index.json", 404, "Not Found", Message(), None
    )

    def fetch_missing(*_args: object) -> bytes:
        raise missing

    monkeypatch.setattr(compose_pages_site, "fetch", fetch_missing)
    with pytest.raises(urllib.error.HTTPError):
        compose_pages_site.copy_remote("https://pages.example/skills/dev", tmp_path / "dev")


def test_project_release_skill_keeps_manual_publication_gates() -> None:
    skill = (ROOT / ".agents/skills/project-release/SKILL.md").read_text(encoding="utf-8")
    normalized = " ".join(skill.split())
    assert "Never choose the release version" in normalized
    assert "base is `main` and head is `dev`" in normalized
    assert "merge commit" in normalized
    assert "confirmation before creating or updating the PR" in normalized
    for action in ("pushing `dev`", "merging", "creating the annotated", "pushing the tag"):
        assert action in normalized


def test_release_manifest_rejects_tampered_tarball(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"validated tarball"
    npm = {
        "filename": "package.tgz",
        "name": "@kisev/agentomatic",
        "size": len(content),
        **build_release_artifacts.hashes(content),
    }
    release = tmp_path / "release"
    release.mkdir()
    (release / "package.tgz").write_bytes(content)
    (release / "release.json").write_text(
        json.dumps({"schema": "@kisev/skills-release/v1", "npm": npm}), encoding="utf-8"
    )
    monkeypatch.setattr(publish_npm_release, "RELEASE", release)
    assert publish_npm_release.manifest()[1].read_bytes() == content
    (release / "package.tgz").write_bytes(content + b"tampered")
    with pytest.raises(publish_npm_release.PublicationError, match="does not match"):
        publish_npm_release.manifest()


def test_pages_manifest_verifies_every_exact_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {"index.json": b"index\n", ".well-known/skills/lock.json": b"lock\n"}
    manifest = tmp_path / "release.json"
    manifest.write_text(
        json.dumps(
            {
                "pages": {
                    "files": {
                        path: hashlib.sha256(content).hexdigest() for path, content in files.items()
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        verify_distribution_url,
        "fetch",
        lambda url: files[url.removeprefix("https://pages.example/")],
    )
    assert verify_distribution_url.verify_manifest_files("https://pages.example/", manifest) == 2
    files["index.json"] = b"changed\n"
    with pytest.raises(verify_distribution_url.VerificationError, match="differs"):
        verify_distribution_url.verify_manifest_files("https://pages.example/", manifest)


def test_github_release_creation_binds_tag_revision_and_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object] | None]] = []
    release_notes = "### Added\n\n- Exact release notes.\n"
    tag = f"v{RELEASE_VERSION}"
    revision = "a" * 40
    expected_release = {
        "html_url": "https://github.example/release",
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": False,
        "body": release_notes,
    }
    release_lookups = 0
    tag_object = "b" * 40

    def api(
        method: str,
        path: str,
        _token: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        nonlocal release_lookups
        calls.append((method, path, payload))
        if path.endswith(f"/git/ref/tags/{tag}"):
            return 200, {"object": {"type": "tag", "sha": tag_object}}
        if path.endswith(f"/git/tags/{tag_object}"):
            return 200, {"object": {"type": "commit", "sha": revision}}
        if method == "GET":
            release_lookups += 1
            return (404, {}) if release_lookups == 1 else (200, expected_release)
        return 201, expected_release

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kisev/skills")
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setenv("RELEASE_REVISION", revision)
    monkeypatch.setattr(create_github_release, "api", api)
    monkeypatch.setattr(create_github_release, "changelog", lambda _version: release_notes)
    assert create_github_release.create()["html_url"] == "https://github.example/release"
    payload = next(payload for method, _path, payload in calls if method == "POST")
    assert payload is not None
    assert payload["tag_name"] == tag
    assert payload["target_commitish"] == revision
    assert payload["body"] == release_notes


def test_existing_github_release_verifies_peeled_tag_and_postcondition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v1.2.3"
    revision = "a" * 40
    tag_object = "b" * 40
    release = {
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": False,
        "body": "notes\n",
    }

    def api(method: str, path: str, _token: str, _payload: object = None) -> tuple[int, object]:
        assert method == "GET"
        if "/git/ref/tags/" in path:
            return 200, {"object": {"type": "tag", "sha": tag_object}}
        if "/git/tags/" in path:
            return 200, {"object": {"type": "commit", "sha": revision}}
        return 200, release

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kisev/skills")
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setenv("RELEASE_REVISION", revision)
    monkeypatch.setattr(create_github_release, "api", api)
    monkeypatch.setattr(create_github_release, "changelog", lambda _version: "notes\n")
    assert create_github_release.create() == release

    monkeypatch.setenv("RELEASE_REVISION", "c" * 40)
    with pytest.raises(create_github_release.ReleaseError, match="RELEASE_REVISION"):
        create_github_release.create()


def test_remote_tag_commit_rejects_lightweight_tag_even_at_expected_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = "a" * 40
    monkeypatch.setattr(
        create_github_release,
        "api",
        lambda *_args: (200, {"object": {"type": "commit", "sha": revision}}),
    )
    with pytest.raises(create_github_release.ReleaseError, match="must be annotated"):
        create_github_release.remote_tag_commit("kisev/skills", "v1.2.3", "token")


def test_remote_tag_commit_peels_annotated_tag_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    outer = "b" * 40
    inner = "c" * 40
    revision = "a" * 40

    def api(_method: str, path: str, _token: str) -> tuple[int, object]:
        if "/git/ref/tags/" in path:
            return 200, {"object": {"type": "tag", "sha": outer}}
        if path.endswith(outer):
            return 200, {"object": {"type": "tag", "sha": inner}}
        return 200, {"object": {"type": "commit", "sha": revision}}

    monkeypatch.setattr(create_github_release, "api", api)
    assert create_github_release.remote_tag_commit("kisev/skills", "v1.2.3", "token") == revision


def test_new_github_release_rejects_failed_postcondition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tag = "v1.2.3"
    revision = "a" * 40
    tag_object = "b" * 40
    release_lookups = 0

    def api(method: str, path: str, _token: str, _payload: object = None) -> tuple[int, object]:
        nonlocal release_lookups
        if "/git/ref/tags/" in path:
            return 200, {"object": {"type": "tag", "sha": tag_object}}
        if "/git/tags/" in path:
            return 200, {"object": {"type": "commit", "sha": revision}}
        if method == "POST":
            return 201, {"tag_name": tag}
        release_lookups += 1
        if release_lookups == 1:
            return 404, {}
        return 200, {
            "tag_name": tag,
            "name": tag,
            "draft": False,
            "prerelease": False,
            "body": "different notes\n",
        }

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kisev/skills")
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setenv("RELEASE_REVISION", revision)
    monkeypatch.setattr(create_github_release, "api", api)
    monkeypatch.setattr(create_github_release, "changelog", lambda _version: "notes\n")
    with pytest.raises(create_github_release.ReleaseError, match="differs"):
        create_github_release.create()


@pytest.mark.parametrize("existing", [False, True])
def test_github_release_rechecks_peeled_tag_after_final_get(
    monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    tag = "v1.2.3"
    revision = "a" * 40
    release = {
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": False,
        "body": "notes\n",
    }
    tag_lookups = 0
    tag_object_lookups = 0
    release_lookups = 0
    calls: list[tuple[str, str]] = []

    def api(method: str, path: str, _token: str, _payload: object = None) -> tuple[int, object]:
        nonlocal release_lookups, tag_object_lookups, tag_lookups
        calls.append((method, path))
        if "/git/ref/tags/" in path:
            tag_lookups += 1
            return 200, {"object": {"type": "tag", "sha": "b" * 40}}
        if "/git/tags/" in path:
            tag_object_lookups += 1
            sha = revision if tag_object_lookups == 1 else "c" * 40
            return 200, {"object": {"type": "commit", "sha": sha}}
        if method == "POST":
            return 201, release
        release_lookups += 1
        if not existing and release_lookups == 1:
            return 404, {}
        return 200, release

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kisev/skills")
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setenv("RELEASE_REVISION", revision)
    monkeypatch.setattr(create_github_release, "api", api)
    monkeypatch.setattr(create_github_release, "changelog", lambda _version: "notes\n")

    with pytest.raises(create_github_release.ReleaseError, match="RELEASE_REVISION"):
        create_github_release.create()
    assert tag_lookups == 2
    assert tag_object_lookups == 2
    assert "/git/ref/tags/" in calls[-2][1]
    assert "/git/tags/" in calls[-1][1]


def test_release_environment_revision_must_match_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASE_REVISION", "0" * 40)
    with pytest.raises(check_release.ReleaseError, match="environment revision"):
        check_release.validate()


def test_release_workflow_gates_publication_and_final_release() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert (
        workflow.index("stable-preflight:")
        < workflow.index("stable-pages:")
        < workflow.index("github-release:")
    )
    assert workflow.count("needs: stable-preflight") == 2
    assert "task release:prepare" in workflow
    assert "branches:\n      - dev" in workflow
    assert "task check" in workflow
    assert "workflow_run" not in workflow
    assert "DEV_REVISION: ${{ github.sha }}" in workflow
    assert "cancel-in-progress: ${{ startsWith(github.ref, 'refs/tags/v') }}" in workflow
    assert "github.event.deleted != true" in workflow
    assert "task dev:prepare" in workflow
    assert "task dev:npm" in workflow
    assert "task dev:pages:verify" in workflow
    assert "task release:pages:verify" in workflow
    assert "task release:npm" in workflow
    assert "task release:github" in workflow
    assert "      - stable-pages\n      - stable-npm" in workflow
    assert "needs.stable-preflight.outputs.npm-artifact" in workflow
    assert "needs.stable-preflight.outputs.pages-artifact" in workflow
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'test "$HEAD_REF" = dev' in ci
    assert 'test "$HEAD_REPOSITORY" = "$REPOSITORY"' in ci
    assert "git merge-base --is-ancestor HEAD^2 origin/dev" in ci
    builder = (ROOT / "scripts/build_release_artifacts.py").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts/publish_npm_release.py").read_text(encoding="utf-8")
    pages = (ROOT / "scripts/verify_distribution_url.py").read_text(encoding="utf-8")
    assert "npm pack" not in workflow and '"npm",\n            "pack"' in builder
    for contract in (
        "registry_smoke",
        "verify_provenance",
        "npm 11.5.1 or newer",
        "registry npm artifact differs",
    ):
        assert contract in publisher
    assert "deployed Pages file differs from release artifact" in pages
