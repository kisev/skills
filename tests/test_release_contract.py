from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import time
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from scripts import (
    build_distribution,
    build_release_artifacts,
    check_release,
    create_github_release,
    publish_npm_release,
    verify_distribution_url,
)

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"
PACKAGE_METADATA = json.loads(
    (ROOT / "packages" / "opencode" / "package.json").read_text(encoding="utf-8")
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
    with pytest.raises(publish_npm_release.PublicationError, match="11.5.1"):
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
    publish_npm_release.registry_smoke("@kisev/skills-opencode", RELEASE_VERSION)
    install = next(arguments for arguments in calls if arguments[:2] == ("npm", "install"))
    assert f"@kisev/skills-opencode@{RELEASE_VERSION}" in install
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
    monkeypatch.setattr(publish_npm_release, "registry_smoke", lambda *_args: None)
    monkeypatch.setattr(
        publish_npm_release, "command", lambda *_args: pytest.fail("must not republish")
    )
    assert publish_npm_release.publish() == metadata
    metadata["dist"]["integrity"] = "wrong"
    with pytest.raises(publish_npm_release.PublicationError, match="differs"):
        publish_npm_release.publish()


def test_release_manifest_rejects_tampered_tarball(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"validated tarball"
    npm = {
        "filename": "package.tgz",
        "name": "@kisev/skills-opencode",
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

    def api(
        method: str,
        path: str,
        _token: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, object]:
        calls.append((method, path, payload))
        if method == "GET":
            return 404, {}
        return 201, {"html_url": "https://github.example/release"}

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kisev/skills")
    monkeypatch.setenv("RELEASE_TAG", f"v{RELEASE_VERSION}")
    monkeypatch.setenv("RELEASE_REVISION", "a" * 40)
    monkeypatch.setattr(create_github_release, "api", api)
    monkeypatch.setattr(create_github_release, "changelog", lambda _version: release_notes)
    assert create_github_release.create()["html_url"] == "https://github.example/release"
    payload = calls[-1][2]
    assert payload is not None
    assert payload["tag_name"] == f"v{RELEASE_VERSION}"
    assert payload["target_commitish"] == "a" * 40
    assert payload["body"] == release_notes


def test_release_environment_revision_must_match_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASE_REVISION", "0" * 40)
    with pytest.raises(check_release.ReleaseError, match="environment revision"):
        check_release.validate()


def test_release_workflow_gates_publication_and_final_release() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert (
        workflow.index("preflight:") < workflow.index("pages:") < workflow.index("github-release:")
    )
    assert workflow.count("needs: preflight") == 2
    assert "task release:prepare" in workflow
    assert "task release:pages:verify" in workflow
    assert "task release:npm" in workflow
    assert "task release:github" in workflow
    assert "      - pages\n      - npm" in workflow
    assert "needs.preflight.outputs.npm-artifact" in workflow
    assert "needs.preflight.outputs.pages-artifact" in workflow
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
