from __future__ import annotations

import base64
import hashlib
import json
import subprocess
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


def test_current_release_metadata_is_aligned() -> None:
    assert build_distribution.build(DISTRIBUTION, False) == 0
    result = check_release.validate()
    assert result["version"] == "2.2.3"
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
        json.dumps({"version": "2.2.3", "source_revision": "0" * 40}), encoding="utf-8"
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


def test_release_notes_are_taken_from_the_exact_changelog_section() -> None:
    notes = create_github_release.changelog("2.2.3")
    assert "plain absolute artifact paths" in notes
    assert "## [2.2.1]" not in notes


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
    with pytest.raises(publish_npm_release.PublicationError, match="does not bind"):
        publish_npm_release.verify_provenance(metadata, sha512, "c" * 40, attempts=1)


def test_trusted_publishing_rejects_an_old_npm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publish_npm_release, "command", lambda *_args: "11.5.0\n")
    with pytest.raises(publish_npm_release.PublicationError, match="11.5.1"):
        publish_npm_release.require_trusted_publishing_npm()


def test_registry_smoke_installs_the_optional_runtime_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def command(*arguments: str, **_kwargs: object) -> str:
        calls.append(arguments)
        if arguments[-1:] == ("--version",):
            return "2.2.3\n"
        if arguments[-2:] == ("capabilities", "--json"):
            return '{"status":"ok","version":"2.2.3"}\n'
        return ""

    monkeypatch.setattr(publish_npm_release, "command", command)
    publish_npm_release.registry_smoke("@kisev/skills-opencode", "2.2.3")
    install = next(arguments for arguments in calls if arguments[:2] == ("npm", "install"))
    assert "@kisev/skills-opencode@2.2.3" in install
    assert "@opencode-ai/plugin@1.18.29" in install
    assert ("npm", "audit", "signatures", "--json") in calls


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
    monkeypatch.setenv("RELEASE_TAG", "v2.2.3")
    monkeypatch.setenv("RELEASE_REVISION", "a" * 40)
    monkeypatch.setattr(create_github_release, "api", api)
    assert create_github_release.create()["html_url"] == "https://github.example/release"
    payload = calls[-1][2]
    assert payload is not None
    assert payload["tag_name"] == "v2.2.3"
    assert payload["target_commitish"] == "a" * 40
    assert "plain absolute artifact paths" in str(payload["body"])


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
    assert "task: ci:spec-impact" in (ROOT / "taskfile.yml").read_text(encoding="utf-8")

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
