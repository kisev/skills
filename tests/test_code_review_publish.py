from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


CONTRACT = load_module(
    ROOT / "shared/references/portable_gitlab/contract.py", "code_review_publish_contract"
)
runtime = ModuleType("portable_runtime")
setattr(runtime, "contract", CONTRACT)
previous_runtime = sys.modules.get("portable_runtime")
sys.modules["portable_runtime"] = runtime
try:
    PUBLISH = load_module(
        ROOT / "skills/code-review/scripts/review_publish.py", "code_review_publish"
    )
finally:
    if previous_runtime is None:
        sys.modules.pop("portable_runtime", None)
    else:
        sys.modules["portable_runtime"] = previous_runtime


def test_glab_request_reports_redacted_definitive_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout=(
                b"HTTP/2.0 422 Unprocessable Entity\r\ncontent-type: application/json\r\n\r\n"
                b'{"message":"token=stdout-secret"}'
            ),
            stderr=(
                b"glab: rejected password=stderr-secret (HTTP 422)\n"
                b"Authorization: Bearer bearer-secret\n"
            ),
        )

    monkeypatch.setattr(PUBLISH.shutil, "which", lambda _name: "/usr/bin/glab")
    monkeypatch.setattr(PUBLISH.subprocess, "run", run)

    with pytest.raises(PUBLISH.MutationRejectedError) as raised:
        PUBLISH.GlabClient("gitlab.example").request(
            "POST", "projects/19/issues", {"title": "safe"}
        )

    message = str(raised.value)
    assert "method=POST" in message
    assert "endpoint=projects/19/issues" in message
    assert "exit_code=1" in message
    assert "http_status=422" in message
    assert "[REDACTED]" in message
    assert "stdout-secret" not in message
    assert "stderr-secret" not in message
    assert "bearer-secret" not in message
    assert "--include" in observed["argv"]
    assert [
        "--header",
        "Content-Type: application/json; charset=utf-8",
        "--input",
        "-",
    ] == observed["argv"][-5:-1]
    assert json.loads(observed["kwargs"]["input"]) == {"title": "safe"}
    assert observed["kwargs"]["shell"] is False
    assert "env" not in observed["kwargs"]


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (
            subprocess.CompletedProcess(
                ["glab"],
                1,
                stdout=b"HTTP/2.0 503 Service Unavailable\r\n\r\nupstream failed",
                stderr=b"glab: unavailable (HTTP 503)\n",
            ),
            "http_status=503",
        ),
        (
            subprocess.CompletedProcess(
                ["glab"],
                1,
                stdout=b"HTTP/2.0 408 Request Timeout\r\n\r\nrequest timed out",
                stderr=b"glab: timed out (HTTP 408)\n",
            ),
            "http_status=408",
        ),
        (subprocess.TimeoutExpired(["glab"], 45, output=b"token=timeout-secret"), "unknown"),
    ],
)
def test_glab_request_keeps_uncertain_mutations_partial(
    monkeypatch: pytest.MonkeyPatch,
    failure: subprocess.CompletedProcess[bytes] | subprocess.TimeoutExpired,
    expected_status: str,
) -> None:
    def run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if isinstance(failure, subprocess.TimeoutExpired):
            raise failure
        return failure

    monkeypatch.setattr(PUBLISH.shutil, "which", lambda _name: "/usr/bin/glab")
    monkeypatch.setattr(PUBLISH.subprocess, "run", run)

    with pytest.raises(PUBLISH.MutationError) as raised:
        PUBLISH.GlabClient("gitlab.example").request("PUT", "projects/19/issues/7", {})

    message = str(raised.value)
    assert "method=PUT" in message
    assert "endpoint=projects/19/issues/7" in message
    assert expected_status in message
    assert "timeout-secret" not in message


def test_diagnostics_are_bounded_after_redaction() -> None:
    diagnostic = PUBLISH.bounded_diagnostic("token=secret-value " + "x" * 5000)

    assert "secret-value" not in diagnostic
    assert diagnostic.endswith("...[truncated]")
    assert len(diagnostic) <= PUBLISH.MAX_DIAGNOSTIC_CHARS + len("...[truncated]")


def test_observe_body_blocks_an_edited_existing_marker() -> None:
    action, _preflight, body = publication_inputs()
    edited = body.replace("Review body", "Edited review body")
    note: dict[str, Any] = {
        "id": 1,
        "system": False,
        "body": edited,
        "author": {"username": "reviewer"},
    }
    discussion: dict[str, Any] = {
        "id": "discussion-1",
        "notes": [note],
    }

    with pytest.raises(PUBLISH.BlockedError, match="body changed"):
        PUBLISH.observe_body(
            action,
            body,
            {"username": "reviewer"},
            [discussion],
            [],
            [],
        )

    note["body"] = body
    observed = PUBLISH.observe_body(
        action,
        body,
        {"username": "reviewer"},
        [discussion],
        [],
        [],
    )
    assert observed[0]["discussion"] == discussion


def publication_inputs() -> tuple[dict[str, Any], dict[str, Any], str]:
    body = (
        "Review body\n\n"
        "<!-- code-review:id=finding-1;revision=1;kind=finding;target=0123456789abcdef -->\n"
    )
    spec = {
        "operation": "create_general",
        "expected": {"prior_marker": None},
        "mutation": {},
    }
    action = {
        "id": "finding:finding-1:r1:create_general",
        "sha256": "a" * 64,
        "kind": "finding",
        "spec": spec,
    }
    preflight = {
        "target": {"hostname": "gitlab.example", "project_id": 19, "mr_iid": 7},
    }
    return action, preflight, body


def configure_publication_fakes(monkeypatch: pytest.MonkeyPatch) -> Any:
    class FakeClient:
        def __init__(self) -> None:
            self.mutated = False
            self.mutations = 0
            self.events: list[tuple[str, bool]] = []

        def request(self, method: str, _endpoint: str, _payload: object = None) -> object:
            assert method == "POST"
            self.events.append(("mutation", self.mutated))
            self.mutated = True
            self.mutations += 1
            return {}

    client = FakeClient()
    monkeypatch.setattr(PUBLISH, "GlabClient", lambda _hostname: client)
    monkeypatch.setattr(
        PUBLISH,
        "collect_live",
        lambda _client, _preflight: {
            "actor": {"username": "reviewer"},
            "endpoint": "projects/19/merge_requests/7",
        },
    )
    monkeypatch.setattr(PUBLISH, "load_discussions", lambda _client, _endpoint: [])
    monkeypatch.setattr(PUBLISH, "load_notes", lambda _client, _endpoint: [])
    monkeypatch.setattr(PUBLISH, "validate_expected_source", lambda *_args: (None, [], []))
    monkeypatch.setattr(PUBLISH, "validate_prior_marker", lambda *_args: None)
    monkeypatch.setattr(PUBLISH, "validate_observed_location", lambda *_args: None)

    def observe(*_args: Any) -> list[dict[str, Any]]:
        client.events.append(("observe", client.mutated))
        return [{"root": True}] if client.mutated else []

    monkeypatch.setattr(PUBLISH, "observe_body", observe)
    return client


def test_unknown_retry_requires_fresh_marker_absence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = configure_publication_fakes(monkeypatch)
    action, preflight, body = publication_inputs()
    digest = action["sha256"]
    plan_path = tmp_path / "plan.json"

    PUBLISH.write_state(tmp_path, digest, {"phase": "unknown", "uncertain": True})
    with pytest.raises(PUBLISH.MutationError):
        PUBLISH.apply_action(plan_path, "b" * 64, tmp_path, {}, action, preflight, body)
    assert client.mutations == 0

    PUBLISH.write_state(tmp_path, digest, {"phase": "unknown"})
    result = PUBLISH.apply_action(plan_path, "b" * 64, tmp_path, {}, action, preflight, body)
    assert result["status"] == "applied"
    assert client.mutations == 1
    assert client.events.index(("observe", False)) < client.events.index(("mutation", False))

    repeated = PUBLISH.apply_action(plan_path, "b" * 64, tmp_path, {}, action, preflight, body)
    assert repeated["status"] == "already_applied"
    assert client.mutations == 1

    client.mutated = False
    with pytest.raises(PUBLISH.BlockedError):
        PUBLISH.apply_action(plan_path, "b" * 64, tmp_path, {}, action, preflight, body)
    assert client.mutations == 1

    PUBLISH.write_state(tmp_path, digest, {"phase": "attempting_state"})
    with pytest.raises(PUBLISH.MutationError):
        PUBLISH.apply_action(plan_path, "b" * 64, tmp_path, {}, action, preflight, body)
    assert client.mutations == 1


def test_definitive_rejection_writes_retryable_state_and_returns_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    action, preflight, body = publication_inputs()
    endpoint = "projects/19/merge_requests/7/discussions"

    class RejectingClient:
        def __init__(self) -> None:
            self.calls = 0

        def request(self, method: str, request_endpoint: str, _payload: object = None) -> object:
            self.calls += 1
            raise PUBLISH.MutationRejectedError(
                "GitLab request was rejected",
                method=method,
                endpoint=request_endpoint,
                exit_code=1,
                http_status=400,
                stdout=b'{"token":"secret-value"}',
                stderr=b"glab: rejected (HTTP 400)",
            )

    client = RejectingClient()
    monkeypatch.setattr(PUBLISH, "GlabClient", lambda _hostname: client)
    monkeypatch.setattr(
        PUBLISH,
        "collect_live",
        lambda *_args: {
            "actor": {"username": "reviewer"},
            "endpoint": "projects/19/merge_requests/7",
        },
    )
    monkeypatch.setattr(PUBLISH, "load_discussions", lambda *_args: [])
    monkeypatch.setattr(PUBLISH, "load_notes", lambda *_args: [])
    monkeypatch.setattr(PUBLISH, "observe_body", lambda *_args: [])
    monkeypatch.setattr(PUBLISH, "validate_expected_source", lambda *_args: (None, [], []))
    monkeypatch.setattr(PUBLISH, "validate_prior_marker", lambda *_args: None)

    output = io.StringIO()
    diagnostics = io.StringIO()
    monkeypatch.setattr(
        PUBLISH,
        "load_plan",
        lambda _path: (tmp_path / "plan.json", {}, "b" * 64, tmp_path),
    )
    monkeypatch.setattr(PUBLISH, "select_action", lambda *_args: (action, preflight, body))
    with redirect_stdout(output), redirect_stderr(diagnostics):
        exit_code = PUBLISH.main(
            ["apply", "--plan", "/ignored", "--action", action["id"], "--confirm", "a" * 64]
        )

    result = json.loads(output.getvalue())
    assert exit_code == 4
    assert result["status"] == "blocked"
    assert result["external_mutations"] is False
    assert "secret-value" not in result["error"]
    assert "review-publish: blocked:" in diagnostics.getvalue()
    assert client.calls == 1
    journal = PUBLISH.load_state(tmp_path, action["sha256"])
    assert journal == {
        "phase": "unknown",
        "retryable": True,
        "definitive_rejection": {
            "method": "POST",
            "endpoint": endpoint,
            "exit_code": 1,
            "http_status": 400,
        },
    }


def test_load_plan_rejects_incomplete_contract_3_envelope(tmp_path: Path) -> None:
    artifact_directory = tmp_path / "artifacts" / "review_plan"
    artifact_directory.mkdir(parents=True)
    preflight_digest = "c" * 64
    spec = {
        "schema": "code-review/publication-action/v1",
        "preflight_sha256": preflight_digest,
        "operation": "update_labels",
        "publication": None,
        "body": None,
        "expected": {"thread": None, "note": None, "prior_marker": None, "issue": None},
        "mutation": {"add": ["type::bug"], "remove": [], "proposed": ["type::bug"]},
    }
    preview = {
        "mr_state": "opened",
        "warning": "manual digest-confirmed publication; no action was executed",
        "preflight_path": str(tmp_path / "preflight.json"),
        "preflight_sha256": preflight_digest,
        "helper_path": str(tmp_path / "review_publish.py"),
        "body_files": [],
        "actions": [
            {
                "id": "labels:update",
                "sha256": CONTRACT.digest(spec),
                "kind": "labels",
                "publication_id": None,
                "revision": None,
                "operation": "update_labels",
                "command": "python3 review_publish.py apply --action labels:update",
                "spec": spec,
            }
        ],
    }
    payload = {
        "profile": "code-review",
        "review_contract_version": 3,
        "complete": True,
        "external_mutations": False,
        "publication_preview": preview,
    }
    envelope = {
        "schema": "portable-gitlab/review_plan/v2",
        "schema_version": 2,
        "kind": "review_plan",
        "created_at": "2026-09-16T00:00:00+00:00",
        "payload": payload,
    }
    content = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    path = artifact_directory / f"{digest}.json"
    path.write_bytes(content)

    with pytest.raises(CONTRACT.WorkflowError):
        PUBLISH.load_plan(str(path))


def test_load_plan_rejects_structurally_duplicate_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    finding = {
        "id": "primary-1",
        "severity": "low",
        "summary": "Documentation contradicts behavior",
        "risk": "Readers rely on the wrong behavior.",
        "evidence": ["docs/example.md:7 contradicts src/example.py:12."],
        "consequence": "Invalid configuration is harder to diagnose.",
        "relation_to_change": "The change adds the contradictory text.",
        "minimum_fix": "Describe the actual behavior.",
    }
    payload = {
        "profile": "code-review",
        "review_contract_version": 4,
        "complete": True,
        "external_mutations": False,
        "findings": [finding, {**finding, "id": "critic-1"}],
    }
    envelope = {
        "schema": "portable-gitlab/review_plan/v2",
        "schema_version": 2,
        "kind": "review_plan",
        "created_at": "2026-09-16T00:00:00+00:00",
        "payload": payload,
    }
    content = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    digest = hashlib.sha256(content).hexdigest()
    artifact_directory = tmp_path / "artifacts" / "review_plan"
    artifact_directory.mkdir(parents=True)
    path = artifact_directory / f"{digest}.json"
    path.write_bytes(content)
    monkeypatch.setattr(PUBLISH.portable, "artifact_payload", lambda *_args: (envelope, payload))
    monkeypatch.setattr(PUBLISH, "validate_active_plan", lambda *_args: None)

    with pytest.raises(CONTRACT.WorkflowError, match="structurally duplicate"):
        PUBLISH.load_plan(str(path))
