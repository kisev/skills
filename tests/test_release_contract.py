from __future__ import annotations

import hashlib
import json
import subprocess
from email.message import Message
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import HTTPError

import pytest

from scripts import (
    await_ci_success,
    build_distribution,
    build_release_artifacts,
    check_release,
    compose_pages_site,
    create_github_release,
    dev_version,
    release_channel,
    verify_distribution_url,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / ".build" / "packages" / "skills"
RELEASE_VERSION = json.loads(
    (ROOT / "packages" / "skills" / "package.json").read_text(encoding="utf-8")
)["version"]

# Several tests validate the shared `.build/packages/skills` state built by
# `tests/test_distribution.py`; the shared xdist group keeps them serialized.
pytestmark = pytest.mark.xdist_group("distribution-state")


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


def test_release_check_rejects_a_missing_portable_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(check_release, "PORTABLE_PACKAGE", manifest)

    with pytest.raises(check_release.ReleaseError, match="must be a string"):
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


def test_published_release_check_requires_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    version = json.loads((ROOT / "packages/skills/package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    revision = check_release.git("rev-parse", "HEAD")
    (tmp_path / "index.json").write_text(
        json.dumps({"version": version, "source_revision": revision}), encoding="utf-8"
    )
    monkeypatch.setattr(check_release, "DISTRIBUTION", tmp_path)
    with pytest.raises(check_release.ReleaseError, match="requires a tag"):
        check_release.validate(published=True)


def test_release_check_can_require_a_clean_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    real_git = check_release.git

    def dirty_git(*arguments: str) -> str:
        if arguments == ("status", "--porcelain"):
            return " M packages/skills/package.json"
        return real_git(*arguments)

    monkeypatch.setattr(check_release, "git", dirty_git)
    with pytest.raises(check_release.ReleaseError, match="clean working tree"):
        check_release.validate(require_clean=True)


def test_release_channel_resolves_latest_from_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        release_channel, "reachable_from", lambda _revision, ref: ref == "origin/main"
    )
    assert release_channel.resolve("v11.0.0", "a" * 40) == {
        "channel": "latest",
        "deploys_pages": "true",
    }


def test_release_channel_resolves_maintenance_from_its_release_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        release_channel,
        "reachable_from",
        lambda _revision, ref: ref == "origin/release/v11.0",
    )
    assert release_channel.resolve("v11.0.4", "a" * 40) == {
        "channel": "maintenance",
        "deploys_pages": "false",
    }


def test_release_channel_fails_closed_outside_release_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release_channel, "reachable_from", lambda *_args: False)
    with pytest.raises(
        release_channel.ChannelError, match=r"neither origin/main nor origin/release/v11\.0"
    ):
        release_channel.resolve("v11.0.4", "a" * 40)


@pytest.mark.parametrize(
    ("on_main", "expected"),
    [
        (True, "channel=latest\ndeploys-pages=true\n"),
        (False, "channel=maintenance\ndeploys-pages=false\n"),
    ],
)
def test_release_channel_github_output_names_match_the_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    on_main: bool,
    expected: str,
) -> None:
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("RELEASE_TAG", "v11.0.4")
    monkeypatch.setenv("RELEASE_REVISION", "a" * 40)
    expected_ref = "origin/main" if on_main else "origin/release/v11.0"
    monkeypatch.setattr(
        release_channel, "reachable_from", lambda _revision, ref: ref == expected_ref
    )
    assert release_channel.main(["--github-output"]) == 0
    assert output.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("tag", ["11.0.0", "v11.0", "v11.0.0-rc.1", "v011.0.0"])
def test_release_channel_rejects_malformed_stable_tags(tag: str) -> None:
    with pytest.raises(release_channel.ChannelError, match=r"vX\.Y\.Z"):
        release_channel.maintenance_line(tag)


def _release_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, version: str) -> str:
    revision = "a" * 40
    (tmp_path / "portable.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(f"## \\[{version}] - 2026-09-30\n", encoding="utf-8")
    distribution = tmp_path / "distribution"
    distribution.mkdir()
    (distribution / "index.json").write_text(
        json.dumps({"version": version, "source_revision": revision}), encoding="utf-8"
    )
    monkeypatch.setattr(check_release, "PORTABLE_PACKAGE", tmp_path / "portable.json")
    monkeypatch.setattr(check_release, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(check_release, "DISTRIBUTION", distribution)
    # The stable publication preflight exports RELEASE_REVISION; pin it to the
    # fixture revision so validate() reaches the channel under test.
    monkeypatch.setenv("RELEASE_REVISION", revision)
    return revision


def _published_git(tag: str, revision: str, tags: str) -> Callable[..., str]:
    def git(*arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return revision
        if arguments == ("cat-file", "-t", f"refs/tags/{tag}"):
            return "tag"
        if arguments == ("rev-parse", f"refs/tags/{tag}^{{commit}}"):
            return revision
        if arguments == ("tag", "--list", "v*"):
            return tags
        raise AssertionError(f"unexpected git call: {arguments}")

    return git


def test_published_check_accepts_a_maintenance_tag_below_the_latest_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version, tag = "10.1.1", "v10.1.1"
    revision = _release_environment(tmp_path, monkeypatch, version)
    monkeypatch.setattr(check_release, "git", _published_git(tag, revision, "v11.0.0\nv10.1.1"))
    monkeypatch.setattr(
        release_channel,
        "resolve",
        lambda _tag, _revision: {"channel": "maintenance", "deploys_pages": "false"},
    )
    assert check_release.validate(tag, published=True) == {
        "version": version,
        "revision": revision,
        "channel": "maintenance",
    }


def test_published_check_keeps_the_latest_channel_newest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version, tag = "10.1.1", "v10.1.1"
    revision = _release_environment(tmp_path, monkeypatch, version)
    monkeypatch.setattr(check_release, "git", _published_git(tag, revision, "v11.0.0\nv10.1.1"))
    monkeypatch.setattr(
        release_channel,
        "resolve",
        lambda _tag, _revision: {"channel": "latest", "deploys_pages": "true"},
    )
    with pytest.raises(check_release.ReleaseError, match="older than the latest stable tag"):
        check_release.validate(tag, published=True)


def test_published_check_fails_closed_outside_release_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version, tag = "10.1.1", "v10.1.1"
    revision = _release_environment(tmp_path, monkeypatch, version)
    monkeypatch.setattr(check_release, "git", _published_git(tag, revision, "v10.1.1"))

    def unreachable(_tag: str, _revision: str) -> dict[str, str]:
        raise release_channel.ChannelError(
            "release revision is reachable from neither origin/main nor origin/release/v10.1"
        )

    monkeypatch.setattr(release_channel, "resolve", unreachable)
    with pytest.raises(check_release.ReleaseError, match="reachable from neither"):
        check_release.validate(tag, published=True)


def test_release_provenance_binds_tag_version_channel_and_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = tmp_path / "pages"
    (pages / "deep").mkdir(parents=True)
    (pages / "index.json").write_bytes(b"index\n")
    (pages / "deep/lock.json").write_bytes(b"lock\n")
    output = tmp_path / "release"
    monkeypatch.setattr(build_release_artifacts, "OUTPUT", output)
    monkeypatch.setattr(build_release_artifacts, "page_hashes", lambda: {"files": {"x": 1}})
    version = json.loads((ROOT / "packages/skills/package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    revision = build_release_artifacts.command("git", "rev-parse", "HEAD").strip()
    monkeypatch.setattr(
        release_channel,
        "resolve",
        lambda _tag, _revision: {"channel": "latest", "deploys_pages": "true"},
    )
    manifest = build_release_artifacts.build(f"v{version}", revision)
    assert manifest["schema"] == "@kisev/skills-release/v3"
    assert manifest["version"] == version
    assert manifest["revision"] == revision
    assert manifest["channel"] == "latest"
    assert manifest["pages"] == {"files": {"x": 1}}
    stored = json.loads((output / "release.json").read_text(encoding="utf-8"))
    assert stored["tag"] == f"v{version}"

    with pytest.raises(build_release_artifacts.ArtifactError, match="differ"):
        build_release_artifacts.build("v0.0.1", revision)


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


def test_pages_composition_keeps_stable_root_and_dev_subpath(tmp_path: Path) -> None:
    stable = tmp_path / "stable"
    dev = tmp_path / "dev-source"
    site = tmp_path / "site"
    stable.mkdir()
    dev.mkdir()
    site.mkdir()
    (stable / "index.json").write_text("stable\n", encoding="utf-8")
    (stable / ".nojekyll").write_text("", encoding="utf-8")
    (dev / "index.json").write_text("dev\n", encoding="utf-8")
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    output = tmp_path / "pages"
    compose_pages_site.compose(
        output,
        stable_dir=stable,
        stable_url=None,
        dev_dir=dev,
        dev_url=None,
        site_dir=site,
    )
    assert (output / "index.json").read_text(encoding="utf-8") == "stable\n"
    assert (output / "dev/index.json").read_text(encoding="utf-8") == "dev\n"
    assert (output / "index.html").read_text(encoding="utf-8") == "<html></html>"
    assert (output / ".nojekyll").exists()


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
    missing = HTTPError(
        "https://pages.example/skills/dev/index.json", 404, "Not Found", Message(), None
    )

    def fetch_missing(*_args: object) -> bytes:
        raise missing

    monkeypatch.setattr(compose_pages_site, "fetch", fetch_missing)
    with pytest.raises(HTTPError):
        compose_pages_site.copy_remote("https://pages.example/skills/dev", tmp_path / "dev")


def test_project_release_skill_keeps_manual_publication_gates() -> None:
    skill = (ROOT / ".agents/skills/project-release/SKILL.md").read_text(encoding="utf-8")
    normalized = " ".join(skill.split())
    assert "Never choose the release version" in normalized
    assert "pull request into `main` with a merge commit" in normalized
    assert "confirmation before creating or updating the PR" in normalized
    for action in (
        "committing and pushing the release",
        "merging with a merge commit",
        "creating the annotated",
        "pushing the tag",
    ):
        assert action in normalized
    assert "it deploys the Pages root" in normalized
    assert "release/vX.Y" in normalized
    assert "run `.github/workflows/publish.yml` from the tagged commit" in normalized
    assert "npm" not in normalized


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


def test_ci_trust_decides_only_on_terminal_success() -> None:
    success = {"id": 1, "status": "completed", "conclusion": "success"}
    assert await_ci_success.decide([success]) == "success"
    assert await_ci_success.decide([]) is None
    active = {"id": 2, "status": "in_progress", "conclusion": None}
    assert await_ci_success.decide([active]) is None
    # A cancelled attempt followed by an active re-run keeps waiting.
    cancelled = {"id": 3, "status": "completed", "conclusion": "cancelled"}
    assert await_ci_success.decide([cancelled, active]) is None
    with pytest.raises(await_ci_success.TrustError, match="superseded"):
        await_ci_success.decide([cancelled])
    with pytest.raises(await_ci_success.TrustError, match="failed"):
        await_ci_success.decide([{"id": 4, "status": "completed", "conclusion": "failure"}])


def test_ci_trust_dry_run_classifies_without_publication_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI_REVISION", "a" * 40)
    runs = [
        {"id": 1, "status": "completed", "conclusion": "success", "html_url": "https://run/1"},
        {"id": 2, "status": "in_progress", "conclusion": None, "html_url": "https://run/2"},
    ]
    assert await_ci_success.dry_run_decision(runs) == {"decision": "wait", "runs": 2}
    assert await_ci_success.dry_run_decision(
        [{"id": 1, "status": "completed", "conclusion": "success", "html_url": "https://run/1"}]
    ) == {
        "decision": "success",
        "runs": 1,
        "run": 1,
        "url": "https://run/1",
    }
    failed = await_ci_success.dry_run_decision(
        [{"id": 3, "status": "completed", "conclusion": "failure", "html_url": "https://run/3"}]
    )
    assert failed["decision"] == "stop"
    assert "failed" in failed["reason"]
    superseded = await_ci_success.dry_run_decision(
        [{"id": 4, "status": "completed", "conclusion": "cancelled", "html_url": "https://run/4"}]
    )
    assert superseded["decision"] == "stop"
    assert "superseded" in superseded["reason"]
    assert await_ci_success.dry_run_decision([]) == {"decision": "wait", "runs": 0}


def test_release_workflow_gates_publication_and_final_release() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    assert (
        workflow.index("stable-preflight:")
        < workflow.index("stable-pages:")
        < workflow.index("pypi-publish:")
        < workflow.index("github-release:")
    )
    assert "needs:\n      - stable-pages\n" in workflow
    # PyPI trusted publishing runs only for a latest-channel tag; the untagged
    # dev push and maintenance-channel tags never reach a package registry.
    assert "needs.stable-preflight.outputs.deploys-pages == 'true'" in workflow
    assert "id-token: write" in workflow
    assert "uv publish --trusted-publishing always" in workflow
    assert "built skillmate version does not match" in workflow
    assert "environment:\n      name: pypi" in workflow
    assert "stable-npm" not in workflow and "dev-npm" not in workflow
    assert "task release:prepare" in workflow
    assert "branches:\n      - dev" in workflow
    # The dev publication trusts the terminal CI success of the same revision
    # instead of repeating the complete gate next to CI.
    assert "task dev:await-ci" in workflow
    assert "CI_REVISION: ${{ github.sha }}" in workflow
    assert "actions: read" in workflow
    assert "task check" not in workflow
    assert "workflow_run" not in workflow
    assert "DEV_REVISION: ${{ github.sha }}" in workflow
    assert "cancel-in-progress: ${{ startsWith(github.ref, 'refs/tags/v') }}" in workflow
    assert "github.event.deleted != true" in workflow
    assert "task dev:prepare" in workflow
    # The release manifest hashes the composed Pages channel, so composition
    # must precede both provenance builders; the GitHub Release job never runs
    # for a dev push.
    assert "startsWith(github.ref, 'refs/tags/v')" in workflow
    taskfile = (ROOT / "taskfile.yml").read_text(encoding="utf-8")
    dev_prepare = taskfile.split("dev:prepare:", 1)[1].split("dev:await-ci:", 1)[0]
    assert dev_prepare.index("compose_pages_site.py") < dev_prepare.index("build_dev_artifacts.py")
    release_prepare = taskfile.split("release:prepare:", 1)[1].split("release:pages:verify:", 1)[0]
    assert release_prepare.index("pages:compose:stable") < release_prepare.index(
        "build_release_artifacts.py"
    )
    assert "task dev:pages:verify" in workflow
    assert "task release:pages:verify" in workflow
    assert "task release:github" in workflow
    assert "needs.stable-preflight.outputs.pages-artifact" in workflow
    assert "task release:channel" in workflow
    assert "deploys-pages" in workflow
    assert "steps.channel.outputs.deploys-pages == 'true'" in workflow
    assert (
        "needs.stable-pages.result == 'success' || needs.stable-pages.result == 'skipped'"
        in workflow
    )
    assert (
        "needs.pypi-publish.result == 'success' || needs.pypi-publish.result == 'skipped'"
        in workflow
    )
    assert "npm" not in workflow
    assert "dist-tag" not in workflow
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "dev|release/*|fix/*)" in ci
    assert 'test "$HEAD_REPOSITORY" = "$REPOSITORY"' in ci
    assert 'test "$(git rev-list --parents -n 1 HEAD | wc -w)" -eq 3' in ci
    builder = (ROOT / "scripts/build_release_artifacts.py").read_text(encoding="utf-8")
    pages = (ROOT / "scripts/verify_distribution_url.py").read_text(encoding="utf-8")
    assert "release.json" in builder and "npm pack" not in builder
    assert "deployed Pages file differs from release artifact" in pages
