from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "tests/integration/gitlab/scripts"
SPEC = importlib.util.spec_from_file_location("gitlab_stand_test", SCRIPTS / "stand.py")
assert SPEC is not None and SPEC.loader is not None
STAND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAND)


@pytest.fixture
def local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(STAND, "ROOT", tmp_path)
    return STAND.Stand("owned-test", 9443)


@pytest.mark.parametrize(
    ("project", "port"), [("../foreign", 9443), ("valid", 0), ("valid", 65536)]
)
def test_invalid_scope_rejected_before_docker(project: str, port: int) -> None:
    with pytest.raises(ValueError, match="project name"):
        STAND.Stand(project, port)


def test_private_state_and_atomic_credentials(local: Any) -> None:
    STAND.write_json(local.state / "fixtures.json", {"owner": "fixture"})
    assert local.state.stat().st_mode & 0o777 == 0o700
    assert (local.state / "fixtures.json").stat().st_mode & 0o777 == 0o600
    assert local.state != local.reports


@pytest.mark.parametrize("action", ["up", "down", "stop", "start", "restart", "rm"])
def test_tests_cannot_manage_containers(local: Any, action: str) -> None:
    with pytest.raises(ValueError, match="cannot manage containers"):
        local.docker(action)


def test_service_mapping_preserves_rails_runner_command() -> None:
    assert STAND.shared.service_arguments(
        ("exec", "-T", "gitlab", "gitlab-rails", "runner", "/bootstrap.rb"),
        {"runner": "gitlab-runner"},
    ) == ["exec", "-T", "gitlab", "gitlab-rails", "runner", "/bootstrap.rb"]
    assert STAND.shared.service_arguments(
        ("exec", "-T", "runner", "gitlab-runner", "--version"), {"runner": "gitlab-runner"}
    ) == ["exec", "-T", "gitlab-runner", "gitlab-runner", "--version"]


def test_runner_initializes_only_once_without_container_restart(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dev.gitlab.fixtures import runner

    local.manifest = {"fixtures": {"id": 2}}
    writes = []
    config = ""

    def request(*args: Any, **_kwargs: Any) -> dict[str, str]:
        writes.append(args)
        return {"token": "private-runner-token"}

    def docker(*args: str, data: str | None = None, **_kwargs: Any) -> str:
        nonlocal config
        assert args[0] == "exec"
        if data is not None:
            config = data
            return ""
        return config

    monkeypatch.setattr(local, "request", request)
    monkeypatch.setattr(local, "docker", docker)
    assert runner(local) is True
    assert runner(local) is False
    assert len(writes) == 1


def test_missing_fixture_preparation_does_not_initialize(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "resources", dict)
    monkeypatch.setattr(local, "bootstrap", lambda: pytest.fail("Tests initialized fixtures"))
    with pytest.raises(RuntimeError, match="env:gitlab:up"):
        local.connect()


def test_glab_environment_does_not_inherit_user_credentials(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "foreign")
    monkeypatch.setenv("GITLAB_HOST", "https://foreign.invalid")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    local.manifest = {"users": {"author": {"token": "owned", "password": "private"}}}
    env = local.isolated_env()
    assert env["GITLAB_TOKEN"] == "owned"
    assert env["GITLAB_HOST"] == "https://localhost:9443"
    assert "GIT_CONFIG_COUNT" not in env
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert local.redact("owned private") == "[REDACTED] [REDACTED]"


def test_requests_reject_external_and_scheme_relative_paths(local: Any) -> None:
    for path in ("https://foreign.invalid", "//foreign.invalid"):
        with pytest.raises(ValueError, match="stand-relative"):
            local.request("POST", path)


def test_bootstrap_refuses_symlink_credentials_before_reading(local: Any) -> None:
    outside = local.reports / "outside.json"
    STAND.write_json(outside, {"private": "unchanged"})
    (local.state / "fixtures.json").symlink_to(outside)
    with pytest.raises(RuntimeError, match="must not be symlinks"):
        local.bootstrap()
    assert json.loads(outside.read_text()) == {"private": "unchanged"}


def test_browser_config_refuses_symlinks_before_writing(local: Any) -> None:
    browser = STAND.load(
        "gitlab_browser_security_test",
        ROOT / "tests/integration/mattermost/scripts/browser_checks.py",
    )
    local.manifest = {"owner": "test-owner"}
    outside = local.reports / "outside.json"
    STAND.write_json(outside, {"private": "unchanged"})
    (local.state / "browser-config.json").symlink_to(outside)
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        browser.Browser(local, local.reports)
    assert json.loads(outside.read_text()) == {"private": "unchanged"}


def test_missing_live_settings_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    live = STAND.load("gitlab_live_settings_test", SCRIPTS / "live_checks.py")
    for key in ("EVAL_HOST", "EVAL_MODEL", "EVAL_TIMEOUT", "EVAL_MAX_TOKENS", "EVAL_MAX_COST"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="EVAL_MODEL"):
        live.settings()


def test_compose_pins_versions_and_never_mounts_docker_socket() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "gitlab/gitlab-ce:18.11.11-ce.0" in compose
    assert "gitlab/gitlab-runner:v18.11.0" in compose
    assert "docker.sock" not in compose
    assert "privileged:" not in compose
    assert "127.0.0.1:" in compose
    assert "http://127.0.0.1:8080/-/readiness?all=1" in compose


def test_startup_health_waits_for_reconfigure_before_readiness(tmp_path: Path) -> None:
    import subprocess

    compose = (ROOT / "docker-compose.yml").read_text()
    marker = "/run/gitlab-test/startup-complete"
    assert f"GITLAB_PRE_RECONFIGURE_SCRIPT: rm -f {marker}" in compose
    assert f"GITLAB_POST_RECONFIGURE_SCRIPT: touch {marker}" in compose
    assert "tmpfs: [/run/gitlab-test]" in compose
    probe = next(line.strip()[2:] for line in compose.splitlines() if "- test -f " in line)
    local_marker = tmp_path / "startup-complete"
    called = tmp_path / "readiness-called"
    curl = tmp_path / "curl"
    curl.write_text(f"#!/bin/sh\ntouch '{called}'\nexit \"${{PROBE_EXIT:-0}}\"\n")
    curl.chmod(0o700)
    probe = probe.replace(marker, str(local_marker))
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin"}
    assert subprocess.run(["sh", "-c", probe], env=env, check=False).returncode != 0
    assert not called.exists()
    local_marker.touch()
    assert subprocess.run(["sh", "-c", probe], env=env, check=False).returncode == 0
    assert called.exists()
    assert (
        subprocess.run(["sh", "-c", probe], env={**env, "PROBE_EXIT": "22"}, check=False).returncode
        == 22
    )
    local_marker.unlink()
    called.unlink()
    assert subprocess.run(["sh", "-c", probe], env=env, check=False).returncode != 0
    assert not called.exists()


def test_standard_https_origin_omits_port(local: Any) -> None:
    assert STAND.Stand("standard-test", 443).origin == "https://localhost"


@pytest.fixture
def publication(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    return STAND.load("gitlab_publication_test", SCRIPTS / "publication_checks.py")


@pytest.mark.parametrize(
    "command",
    [
        "glab api --hostname external.invalid --method POST projects/19/issues",
        "glab api --hostname localhost --method POST projects/20/issues",
        "glab api --hostname localhost --method POST ../graphql",
        "glab api --hostname localhost --hostname external.invalid --method POST projects/19/issues",
        "glab api --hostname localhost --method POST projects/19/../20/issues",
        "sh -c glab api --hostname localhost --method POST projects/19/issues",
    ],
)
def test_copied_publication_refuses_foreign_targets_and_wrappers(
    publication: Any, local: Any, command: str
) -> None:
    local.manifest = {"fixtures": {"id": 19}}
    with pytest.raises(ValueError, match=r"localhost|outside|wrapper"):
        publication.execute(local, command, local.reports, "denied")


def test_human_notes_preserve_thread_state_but_exclude_metadata_system_notes(
    publication: Any,
) -> None:
    note = {"system": False, "body": "Literal `code`, $value and @here", "resolved": False}
    before = [{"notes": [note]}]
    after = [*before, {"notes": [{"system": True, "body": "Changed title"}]}]
    assert publication.human_notes(before) == publication.human_notes(after)
    assert publication.human_notes(before) != publication.human_notes(
        [{"notes": [{**note, "resolved": True}]}]
    )


def test_copied_commands_are_extracted_verbatim_not_reconstructed(publication: Any) -> None:
    text = "# Plan\n\n```sh\n# execution-status=not_run\nglab api --input 'path with spaces'\n```\n"
    assert publication.commands(text) == ["glab api --input 'path with spaces'"]


def test_graphql_publication_refuses_a_foreign_project_before_execution(
    publication: Any, local: Any
) -> None:
    local.manifest = {"fixtures": {"id": 19, "path_with_namespace": "owned/fixtures"}}
    payload = local.state / "payload.json"
    STAND.write_json(
        payload,
        {
            "query": "mutation { createIssue(input: $input) { errors } }",
            "variables": {"input": {"projectPath": "foreign/project"}},
        },
    )
    with pytest.raises(ValueError, match="outside the synthetic"):
        publication.execute(
            local,
            f"glab api --hostname localhost --method POST graphql --input {payload}",
            local.reports,
            "denied",
        )


@pytest.fixture
def preservation(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    return STAND.load("gitlab_preservation_test", SCRIPTS / "preservation_checks.py")


def test_fixture_pagination_and_drift_are_not_silently_accepted(
    preservation: Any, local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def request(_method: str, path: str) -> list[dict[str, int]]:
        calls.append(path)
        return (
            [{"id": index} for index in range(100)] if path.endswith("&page=1") else [{"id": 100}]
        )

    monkeypatch.setattr(local, "request", request)
    assert len(preservation.pages(local, "/issues?state=all")) == 101
    assert calls[-1].endswith("&per_page=100&page=2")
    with pytest.raises(RuntimeError, match="fingerprints changed: issues"):
        preservation.verify({"issues": "old"}, {"issues": "new"})


def test_fixture_snapshot_never_walks_local_manual_or_free_files(
    preservation: Any, local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    local.manifest = {"fixtures": {"id": 7}, "manual": {"id": 99}}
    calls = []

    def request(_method: str, path: str) -> Any:
        calls.append(path)
        if path == "/projects/7":
            return {"id": 7}
        if "/repository/branches?" in path:
            return [{"name": "experiment", "commit": {"id": "exact-sha"}}]
        if "/issues?" in path:
            return [{"iid": 1, "description": "Outside the repository tree"}]
        return []

    monkeypatch.setattr(local, "request", request)

    def forbidden_walk(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Automation must not walk personal files")

    monkeypatch.setattr(Path, "rglob", forbidden_walk)
    first = preservation.snapshot(local)
    assert {
        "issues",
        "issues/1/discussions",
        "issues/1/links",
        "tree/exact-sha",
    } <= first.keys()
    assert any("ref=exact-sha&recursive=true" in path for path in calls)
    assert not any("manual" in name or "free" in name for name in first)
    assert all(path.startswith("/projects/7") for path in calls)
    preservation.verify(first, preservation.snapshot(local))


@pytest.mark.parametrize(
    "path",
    [
        "/projects",
        "/projects?owned=true",
        "/groups",
        "/groups/99/projects",
        "/projects/99/issues",
        "/projects/manual%2Fpersonal/issues",
        "/projects/7/../99/issues",
        "/projects/7/%2e%2e/99/issues",
    ],
)
def test_automation_scope_denies_manual_and_unbounded_catalogs_before_transport(
    local: Any,
    path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local.manifest = {"fixtures": {"id": 7, "path_with_namespace": "owned/fixtures"}}
    monkeypatch.setattr(
        STAND.urllib.request, "build_opener", lambda *_args: pytest.fail("Transport must not start")
    )
    with pytest.raises(ValueError, match="only the fixtures"):
        local.request("GET", path)
    assert local.access_log == []


def test_automation_scope_allows_exact_fixture_and_denies_manual_credentials(local: Any) -> None:
    local.manifest = {"fixtures": {"id": 7, "path_with_namespace": "owned/fixtures"}}
    for path in ("/projects/7", "/projects/7/issues?page=2", "/projects/owned%2Ffixtures"):
        local.fixture_scope(path)
    with pytest.raises(ValueError, match="not available"):
        local.isolated_env("manual")


@pytest.mark.parametrize("partial", [False, True])
def test_reconcile_reuses_groups_without_manual_provisioning_or_catalog_reads(
    local: Any,
    monkeypatch: pytest.MonkeyPatch,
    partial: bool,
) -> None:
    manifest: dict[str, Any] = {
        "owner": "owned",
        "users": {
            role: {"id": index, "token": "token", "password": "password"}
            for index, role in enumerate(("author", "reviewer", "outsider", "manual"), 1)
        },
        "groups": {
            "fixtures": {"id": 10, "path": "owned-fixtures"},
            "manual": {"id": 20, "path": "owned-manual"},
        },
        "fixtures": {
            "id": 7,
            "namespace": {"id": 10},
            "path_with_namespace": "owned-fixtures/fixtures",
        },
    }
    project = manifest["fixtures"]
    if partial:
        del manifest["fixtures"]
    STAND.write_json(local.state / "fixtures.json", manifest)

    def docker(*args: str, **kwargs: Any) -> str:
        if args[0] == "exec":
            value = json.loads(kwargs["data"])
            assert value["initialize_manual"] is False
            return "HARNESS_JSON=" + json.dumps(
                {"users": {}, "groups": {"fixtures": manifest["groups"]["fixtures"]}}
            )
        return ""

    calls = []

    def request(method: str, path: str, *_args: Any) -> Any:
        calls.append((method, path))
        if path.endswith("/members/all"):
            return [{"id": 1}, {"id": 2}]
        assert path == "/projects/owned-fixtures%2Ffixtures"
        return project

    monkeypatch.setattr(local, "docker", docker)
    monkeypatch.setattr(local, "request", request)
    monkeypatch.setattr(
        local,
        "create_fixture_project",
        lambda *_args: pytest.fail("Existing fixture must not be recreated"),
    )
    local.bootstrap()
    expected = [("GET", "/projects/owned-fixtures%2Ffixtures"), ("GET", "/projects/7/members/all")]
    if partial:
        expected.insert(0, expected[0])
    assert calls == expected
    assert local.manifest["groups"]["manual"] == manifest["groups"]["manual"]


def test_preflight_missing_pinned_image_retains_diagnostics_without_substitution(
    local: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from subprocess import CompletedProcess

    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    preflight = STAND.load("gitlab_preflight_security_test", SCRIPTS / "preflight.py")
    monkeypatch.setattr(local, "resources", dict)
    calls = []

    def run(args: list[str], **_kwargs: Any) -> CompletedProcess[str]:
        calls.append(args)
        value = "Docker Compose version v2.29.7" if args[0] == "docker-compose" else "glab 1.120.0"
        if args[1] == "info":
            value = json.dumps({"MemTotal": 16 * 1024**3, "NCPU": 4})
        missing = args[1:3] == ["image", "inspect"]
        return CompletedProcess(
            args,
            1 if missing else 0,
            value if not missing else "",
            "pinned image missing" if missing else "",
        )

    monkeypatch.setattr(preflight.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="server_image unavailable"):
        preflight.run(local, local.reports, browser=False)
    saved = json.loads((local.reports / "preflight.json").read_text())
    assert saved["status"] == "failed"
    assert saved["server_image"]["exit_code"] == 1
    assert calls[-1][-1] == "gitlab/gitlab-ce:18.11.11-ce.0"
    assert not any("pull" in args or "up" in args for args in calls)


def test_browser_refresh_waits_for_server_position_then_navigates_once(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    monkeypatch.setattr(STAND, "ROOT", ROOT)
    browser_module = STAND.load("gitlab_browser_refresh_test", SCRIPTS / "browser_checks.py")
    monkeypatch.setattr(local, "request", lambda *_args: {"diff_refs": {"head_sha": "exact"}})
    monkeypatch.setattr(browser_module.time, "sleep", lambda _seconds: None)
    calls = []
    answers = iter(
        (
            {"status": 200, "id": "thread", "active": True, "position": {"head_sha": "old"}},
            {"status": 200, "id": "thread", "active": True, "position": {"head_sha": "exact"}},
        )
    )

    class Browser:
        def call(self, *args: str) -> None:
            calls.append(args)

        def evaluate(self, _expression: str) -> Any:
            return next(answers)

    fixture: dict[str, Any] = {
        "prefix": "/projects/7",
        "mr": {"iid": 2, "web_url": "https://localhost/owned/fixtures/-/merge_requests/2"},
        "grouped_threads": [{"id": "thread", "notes": [{"body": "remaining suggestion"}]}],
    }
    browser_module.refresh(
        Browser(), local, fixture, "exact", "remaining suggestion", local.reports
    )
    assert fixture["browser_refreshes"] == [
        {
            "head": "exact",
            "thread": "thread",
            "body": "remaining suggestion",
            "navigation_attempts": 1,
            "server_observations": 2,
        }
    ]
    assert [args[0] for args in calls] == ["open", "wait"]
    evidence = json.loads((local.reports / "browser-remap-exact.json").read_text())
    assert [item["position"]["head_sha"] for item in evidence["observations"]] == ["old", "exact"]


def test_browser_refresh_missing_notes_is_a_bounded_failure(
    local: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    monkeypatch.setattr(STAND, "ROOT", ROOT)
    browser_module = STAND.load(
        "gitlab_browser_refresh_timeout_test", SCRIPTS / "browser_checks.py"
    )
    monkeypatch.setattr(local, "request", lambda *_args: {"diff_refs": {"head_sha": "exact"}})
    ticks = iter((0, 1, 61))
    monkeypatch.setattr(browser_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(browser_module.time, "sleep", lambda _seconds: None)

    class Browser:
        def call(self, *_args: str) -> None:
            pass

        def evaluate(self, _expression: str) -> Any:
            return {"status": 200, "id": None, "active": None, "position": None}

    fixture: dict[str, Any] = {
        "prefix": "/projects/7",
        "mr": {"iid": 2, "web_url": "https://localhost/owned/fixtures/-/merge_requests/2"},
        "grouped_threads": [{"id": "thread", "notes": [{"body": "remaining suggestion"}]}],
    }
    with pytest.raises(RuntimeError, match="active exact-head"):
        browser_module.refresh(
            Browser(), local, fixture, "exact", "remaining suggestion", local.reports
        )
    assert (local.reports / "browser-remap-exact.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"mr_head": "stale"},
        {"active": False},
        {"position": {"head_sha": "stale"}},
        {"status": 502},
        {"id": "another-thread"},
        {"position": None},
    ],
)
def test_exact_mr_head_alone_does_not_prove_ui_discussion_readiness(
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    browser = STAND.load("gitlab_remap_contract_test", SCRIPTS / "browser_checks.py")
    ready = {
        "status": 200,
        "id": "thread",
        "mr_head": "exact",
        "active": True,
        "position": {"head_sha": "exact"},
    }
    assert browser.remapped(ready, "exact", "thread")
    assert not browser.remapped({**ready, **change}, "exact", "thread")


def test_browser_network_metadata_keeps_failures_without_credentials_or_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "stand", STAND)
    browser_module = STAND.load("gitlab_browser_network_test", SCRIPTS / "browser_checks.py")
    result = browser_module.network_metadata(
        {
            "success": True,
            "data": {
                "requests": [
                    {
                        "requestId": "request-1",
                        "url": "https://localhost/discussions.json",
                        "method": "GET",
                        "status": 0,
                        "errorText": "net::ERR_CONNECTION_RESET",
                        "resourceType": "XHR",
                        "headers": {"Cookie": "private-cookie"},
                        "body": "private-body",
                        "cookies": ["private-cookie"],
                    }
                ]
            },
        }
    )
    assert result == {
        "origin": "real-browser",
        "fault_injection": False,
        "requests": [
            {
                "requestId": "request-1",
                "url": "https://localhost/discussions.json",
                "method": "GET",
                "status": 0,
                "errorText": "net::ERR_CONNECTION_RESET",
                "resourceType": "XHR",
            }
        ],
    }
    for payload in ({"success": False}, {"success": True, "data": {}}):
        with pytest.raises(RuntimeError, match="diagnostics are incomplete"):
            browser_module.network_metadata(payload)
