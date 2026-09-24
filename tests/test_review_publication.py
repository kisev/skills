"""One-action publication, freshness, and ambiguous-outcome regressions."""

from __future__ import annotations

import copy
import importlib.util
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, Path, dict[str, Any], dict[str, Any]]:
    scripts = ROOT / ".build/skills/code-review/scripts"
    monkeypatch.syspath_prepend(str(scripts))
    for name in list(sys.modules):
        if name == "portable_runtime" or name.startswith("portable_runtime."):
            monkeypatch.delitem(sys.modules, name)
    spec = importlib.util.spec_from_file_location(
        "publication_regression", scripts / "review_publication.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    target = {"hostname": "gitlab.example", "project_id": 10, "kind": "merge_requests", "iid": 2}
    root = module.portable.state_directory("code-review", target)
    mr = {
        "id": 22,
        "iid": 2,
        "project_id": 10,
        "state": "opened",
        "diff_refs": {"base_sha": "a" * 40, "start_sha": "b" * 40, "head_sha": "c" * 40},
        "author": {"id": 8},
        "labels": [],
    }
    discussions = [
        {
            "id": "thread",
            "notes": [{"id": 1, "body": "Please check", "author": {"id": 8}, "resolved": False}],
        }
    ]
    evidence = {"project": {"id": 10, "hostname": "gitlab.example"}, "target": target, "object": mr}
    context = {
        "current_user_id": 7,
        "current_user_username": "reviewer",
        "evidence_digest": "d" * 64,
        "discussions": discussions,
    }
    return module, root, evidence, context


def action(
    publication: tuple[ModuleType, Path, dict[str, Any], dict[str, Any]],
    *,
    operation: str = "reply",
    dependencies: dict[str, str] | None = None,
) -> tuple[Path, str]:
    module, root, evidence, context = publication
    deps = dependencies if dependencies is not None else {}
    base = "projects/10/merge_requests/2/discussions/thread"
    if operation == "reply":
        directory = module.portable.private_directory(root / "artifacts/review_plan/bodies")
        body = directory / "reply.md"
        body.write_text("Verified result.\n")
        argv = ["glab", "api", "--method", "POST", base + "/notes", "-F", f"body=@{body}"]
    else:
        argv = ["glab", "api", "--method", "PUT", base, "-F", "resolved=true"]
    command = module.make_command(
        root, evidence, context, f"thread:one:r1:{operation}", argv, {}, deps
    )
    tokens = shlex.split(command)
    return Path(tokens[tokens.index("--action") + 1]), tokens[-1]


def runtime(
    publication: tuple[ModuleType, Path, dict[str, Any], dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], list[list[str]]]:
    module, _, evidence, context = publication
    observed = {
        "mr": copy.deepcopy(evidence["object"]),
        "notes": module.notes_snapshot(context["discussions"]),
    }
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "finalized_action", lambda *args: None)
    monkeypatch.setattr(module, "observe", lambda guard: copy.deepcopy(observed))
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/glab")

    def mutate(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        value = json.loads(payload)
        if "body" in value:
            observed["notes"]["2"] = {
                "discussion": "thread",
                "body": value["body"],
                "author": 7,
                "resolved": None,
                "position": None,
            }
        elif "resolved" in value:
            observed["notes"]["1"]["resolved"] = value["resolved"]
        return subprocess.CompletedProcess(argv, 0, b"{}", b"")

    monkeypatch.setattr(module, "run_mutation_process", mutate)
    return observed, calls


def test_reply_then_close_requires_receipt_and_rejects_replay(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    observed, calls = runtime(publication, monkeypatch)
    with pytest.raises(module.portable.WorkflowError, match="explanation"):
        module.execute(close, close_digest)
    assert not calls
    assert module.execute(reply, digest)["status"] == "applied"
    assert module.execute(close, close_digest)["status"] == "applied"
    observed["notes"]["1"]["resolved"] = False
    assert module.execute(close, close_digest)["status"] == "already_applied"
    assert len(calls) == 2


def test_later_reply_blocks_closure(publication: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    observed, calls = runtime(publication, monkeypatch)
    module.execute(reply, digest)
    observed["notes"]["3"] = {**observed["notes"]["2"], "author": 8, "body": "Not fixed"}
    with pytest.raises(module.portable.WorkflowError, match="changed"):
        module.execute(close, close_digest)
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "postcondition"])
def test_ambiguous_attempt_blocks_replay_and_read_only_inspection_can_confirm(
    publication: Any, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    observed, calls = runtime(publication, monkeypatch)
    original = module.run_mutation_process

    def fail(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        result = original(argv, payload)
        if failure == "timeout":
            raise module.MutationOutcomeUnknown("timeout")
        if failure == "postcondition":
            observed["notes"].pop("2")
        return subprocess.CompletedProcess(
            argv, 1 if failure == "nonzero" else result.returncode, b"", b""
        )

    monkeypatch.setattr(module, "run_mutation_process", fail)
    result = module.execute(path, digest)
    assert result["mutation_outcome"] == "unknown" and result["external_mutations"] is True
    with pytest.raises(module.portable.WorkflowError, match="unresolved"):
        module.execute(path, digest)
    inspected = module.execute(path, digest, inspect=True)
    assert inspected["status"] == ("blocked" if failure == "postcondition" else "applied")
    assert inspected["external_mutations"] is False and len(calls) == 1


def test_proven_start_failure_allows_fresh_explicit_attempt(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    _, calls = runtime(publication, monkeypatch)
    original = module.run_mutation_process

    def fail(*args: Any) -> Any:
        raise module.MutationNotAttempted("not started")

    monkeypatch.setattr(module, "run_mutation_process", fail)
    with pytest.raises(module.MutationNotAttempted):
        module.execute(path, digest)
    monkeypatch.setattr(module, "run_mutation_process", original)
    assert module.execute(path, digest)["status"] == "applied" and len(calls) == 1


def test_digest_body_expiry_and_unfinalized_plan_fail_before_mutation(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, root, _, _ = publication
    path, digest = action(publication)
    with pytest.raises(module.portable.WorkflowError):
        module.execute(path, "0" * 64)
    with pytest.raises(module.portable.WorkflowError, match="progress"):
        module.execute(path, digest)
    _, calls = runtime(publication, monkeypatch)
    monkeypatch.setattr(module.time, "time", lambda: 10**12)
    with pytest.raises(module.portable.WorkflowError, match="expired"):
        module.execute(path, digest)
    (root / "artifacts/review_plan/bodies/reply.md").write_text("changed")
    with pytest.raises(module.portable.WorkflowError, match="body changed"):
        module.execute(path, digest)
    assert not calls


def test_observe_rejects_changed_identity_and_head(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, evidence, _ = publication
    path, digest = action(publication)
    _, guard = module.load_action(path, digest)
    monkeypatch.setattr(
        module.portable, "glab_json", lambda host, endpoint: {"id": 9, "username": "another"}
    )
    with pytest.raises(module.portable.WorkflowError, match="user changed"):
        module.observe(guard)
    changed = {**evidence["object"], "diff_refs": {"head_sha": "f" * 40}}
    monkeypatch.setattr(
        module.portable,
        "glab_json",
        lambda host, endpoint: guard["user"] if endpoint == "user" else changed,
    )
    with pytest.raises(module.portable.WorkflowError, match="refs"):
        module.observe(guard)


@pytest.mark.parametrize("flag", ["--help", "--capabilities"])
def test_publication_cli_is_available_without_a_checkout(tmp_path: Path, flag: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(ROOT / ".build/skills/code-review/scripts/review_publication.py"),
            flag,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and result.stdout
    if flag == "--capabilities":
        assert json.loads(result.stdout)["operations"] == ["apply", "inspect"]
