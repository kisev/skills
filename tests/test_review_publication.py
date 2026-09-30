"""One-action publication, freshness, and ambiguous-outcome regressions."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

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
    monkeypatch.setattr(module, "POSTCONDITION_DELAYS", (0.0, 0.0, 0.0))
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
    proposed: list[str] | None = None,
    dependencies: dict[str, str] | None = None,
) -> tuple[Path, str]:
    module, root, evidence, context = publication
    deps = dependencies if dependencies is not None else {}
    base = "projects/10/merge_requests/2/discussions/thread"
    value: dict[str, Any] = {}
    if operation == "labels":
        action_id = "labels:update"
        argv = ["glab", "mr", "update"]
        value = {"proposed": proposed if proposed is not None else ["type::bug"]}
    else:
        action_id = f"thread:one:r1:{operation}"
        directory = module.portable.private_directory(root / "artifacts/review_plan/bodies")
        body = directory / f"{operation}.md"
        body.write_text("Verified result.\n" if operation != "note" else "General summary.\n")
        if operation == "reply":
            argv = ["glab", "api", "--method", "POST", base + "/notes", "-F", f"body=@{body}"]
        elif operation == "note":
            argv = [
                "glab",
                "api",
                "--method",
                "POST",
                "projects/10/merge_requests/2/notes",
                "-F",
                f"body=@{body}",
            ]
        else:
            argv = ["glab", "api", "--method", "PUT", base, "-F", "resolved=true"]
    command = module.make_command(root, evidence, context, action_id, argv, value, deps)
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
            note_id = str(max(int(key) for key in observed["notes"]) + 1)
            endpoint = argv[argv.index("--method") + 2]
            discussion = (
                endpoint.split("/discussions/", 1)[1].split("/")[0]
                if "/discussions/" in endpoint
                else f"general-{note_id}"
            )
            observed["notes"][note_id] = {
                "discussion": discussion,
                "body": value["body"].rstrip("\n"),
                "author": 7,
                "resolved": None,
                "position": None,
            }
        elif "resolved" in value:
            observed["notes"]["1"]["resolved"] = value["resolved"]
        elif "labels" in value:
            observed["mr"]["labels"] = [label for label in value["labels"].split(",") if label]
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


def test_label_drift_does_not_block_note_actions(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    note, note_digest = action(publication, operation="note")
    observed, calls = runtime(publication, monkeypatch)
    observed["mr"]["labels"] = ["semver::patch", "type::bug"]
    assert module.execute(reply, digest)["status"] == "applied"
    assert module.execute(note, note_digest)["status"] == "applied"
    assert len(calls) == 2


def test_unrelated_thread_activity_does_not_block_actions(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    observed, calls = runtime(publication, monkeypatch)
    observed["notes"]["7"] = {
        "discussion": "other",
        "body": "Unrelated comment",
        "author": 8,
        "resolved": False,
        "position": None,
    }
    assert module.execute(reply, digest)["status"] == "applied"
    assert module.execute(close, close_digest)["status"] == "applied"
    assert len(calls) == 2


def test_manually_applied_labels_complete_without_write(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication, operation="labels")
    observed, calls = runtime(publication, monkeypatch)
    observed["mr"]["labels"] = ["type::bug"]
    result = module.execute(path, digest)
    assert result["status"] == "already_applied"
    assert result["mutation_outcome"] == "applied" and result["external_mutations"] is False
    assert module.execute(path, digest)["status"] == "already_applied"
    assert not calls


def test_foreign_label_change_blocks_label_update(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication, operation="labels")
    observed, calls = runtime(publication, monkeypatch)
    observed["mr"]["labels"] = ["semver::patch"]
    with pytest.raises(module.portable.WorkflowError, match="labels changed outside the plan"):
        module.execute(path, digest)
    assert not calls


def test_manually_posted_reply_completes_and_unblocks_state_change(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    observed, calls = runtime(publication, monkeypatch)
    observed["notes"]["9"] = {
        "discussion": "thread",
        "body": "Verified result.\n",
        "author": 7,
        "resolved": None,
        "position": None,
    }
    result = module.execute(reply, digest)
    assert result["status"] == "already_applied" and result["external_mutations"] is False
    assert module.execute(close, close_digest)["status"] == "applied"
    assert len(calls) == 1


def test_manually_resolved_thread_completes_without_write(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    observed, calls = runtime(publication, monkeypatch)
    module.execute(reply, digest)
    observed["notes"]["1"]["resolved"] = True
    result = module.execute(close, close_digest)
    assert result["status"] == "already_applied" and result["external_mutations"] is False
    assert len(calls) == 1


def test_postcondition_matches_gitlab_normalized_body(publication: Any) -> None:
    module, _, evidence, context = publication
    reply, digest = action(publication)
    _, guard = module.load_action(reply, digest)
    snapshot = module.notes_snapshot(context["discussions"])
    note = {
        "discussion": "thread",
        "body": guard["payload"]["body"].rstrip("\n"),
        "author": guard["user"]["id"],
        "resolved": None,
        "position": None,
    }
    observed = {"mr": copy.deepcopy(evidence["object"]), "notes": {**snapshot, "5": note}}
    effect = module.postcondition(guard, observed, {"notes": snapshot})
    assert effect == {"note_id": "5", "note": note}


def test_pending_unknown_suspends_only_its_own_action(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    deps: dict[str, str] = {}
    reply, digest = action(publication, dependencies=deps)
    close, close_digest = action(publication, operation="resolve", dependencies=deps)
    labels, labels_digest = action(publication, operation="labels")
    observed, calls = runtime(publication, monkeypatch)
    original = module.run_mutation_process

    def hide_effect(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        result = original(argv, payload)
        observed["notes"].pop(max(observed["notes"], key=int))
        return cast("subprocess.CompletedProcess[bytes]", result)

    monkeypatch.setattr(module, "run_mutation_process", hide_effect)
    blocked = module.execute(reply, digest)
    assert blocked["status"] == "blocked" and blocked["mutation_outcome"] == "unknown"
    monkeypatch.setattr(module, "run_mutation_process", original)
    assert module.execute(labels, labels_digest)["status"] == "applied"
    with pytest.raises(module.portable.WorkflowError, match="explanation"):
        module.execute(close, close_digest)
    replay = module.execute(reply, digest)
    assert replay["status"] == "blocked" and "inspect --action" in replay["inspect_command"]
    assert len(calls) == 2


def test_legacy_pending_ledger_is_migrated(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, root, _, _ = publication
    reply, digest = action(publication)
    observed, calls = runtime(publication, monkeypatch)
    original = module.run_mutation_process

    def hide_effect(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        result = original(argv, payload)
        observed["notes"].pop(max(observed["notes"], key=int))
        return cast("subprocess.CompletedProcess[bytes]", result)

    monkeypatch.setattr(module, "run_mutation_process", hide_effect)
    module.execute(reply, digest)
    observed["notes"]["2"] = {
        "discussion": "thread",
        "body": "Verified result.",
        "author": 7,
        "resolved": None,
        "position": None,
    }
    ledger_path = root / "code-review-publication" / "ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ledger_path.write_text(
        json.dumps({"receipts": ledger["receipts"], "pending": ledger["pendings"][0]})
    )
    monkeypatch.setattr(module, "run_mutation_process", original)
    inspected = module.execute(reply, digest, inspect=True)
    assert inspected["status"] == "applied"
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "postcondition"])
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
        return cast("subprocess.CompletedProcess[bytes]", result)

    monkeypatch.setattr(module, "run_mutation_process", fail)
    result = module.execute(path, digest)
    assert result["mutation_outcome"] == "unknown" and result["external_mutations"] is True
    blocked = module.execute(path, digest)
    assert blocked["status"] == "blocked" and "inspect --action" in blocked["inspect_command"]
    inspected = module.execute(path, digest, inspect=True)
    assert inspected["status"] == ("blocked" if failure == "postcondition" else "applied")
    assert inspected["external_mutations"] is False and len(calls) == 1


def test_nonzero_process_with_proven_effect_is_successful(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    _, calls = runtime(publication, monkeypatch)
    original = module.run_mutation_process

    def fail(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        original(argv, payload)
        return subprocess.CompletedProcess(argv, 1, b"", b"response lost")

    monkeypatch.setattr(module, "run_mutation_process", fail)
    result = module.execute(path, digest)
    assert result["status"] == "applied" and result["external_mutations"] is True
    assert len(calls) == 1


def test_failed_process_preserves_diagnostic_and_explicit_retry(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    _, calls = runtime(publication, monkeypatch)
    mutate = module.run_mutation_process

    def fail(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, b"", b"HTTP 400 invalid body")

    monkeypatch.setattr(module, "run_mutation_process", fail)
    result = module.execute(path, digest)
    assert result["status"] == "blocked"
    assert "HTTP 400 invalid body" in result["error"]
    assert "inspect --action" in result["inspect_command"]
    assert "retry --action" in result["retry_command"]
    assert "duplicate" in result["retry_warning"]

    monkeypatch.setattr(module, "run_mutation_process", mutate)
    retried = module.execute(path, digest, retry=True)
    assert retried["status"] == "applied" and len(calls) == 2


def test_postcondition_polling_accepts_delayed_effect(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, evidence, context = publication
    path, digest = action(publication)
    observed, calls = runtime(publication, monkeypatch)
    stale = {
        "mr": copy.deepcopy(evidence["object"]),
        "notes": module.notes_snapshot(context["discussions"]),
    }
    observations = 0

    def delayed(guard: dict[str, Any]) -> dict[str, Any]:
        nonlocal observations
        observations += 1
        return copy.deepcopy(observed if observations >= 4 else stale)

    monkeypatch.setattr(module, "observe", delayed)
    result = module.execute(path, digest)
    assert result["status"] == "applied"
    assert observations == 4 and len(calls) == 1


def test_interactive_recovery_inspects_and_confirms_retry(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    _, calls = runtime(publication, monkeypatch)
    mutate = module.run_mutation_process

    def fail(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, b"", b"temporary failure")

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(module, "run_mutation_process", fail)
    blocked = module.execute(path, digest)
    monkeypatch.setattr(module, "run_mutation_process", mutate)
    monkeypatch.setattr(module.sys, "stdin", Tty("y\ny\n"))
    monkeypatch.setattr(module.sys, "stderr", Tty())
    recovered = module.interactive_recovery(path, digest, blocked)
    assert recovered["status"] == "applied" and len(calls) == 2


def test_interactive_recovery_does_not_repeat_explicit_inspection(
    publication: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, _, _, _ = publication
    path, digest = action(publication)
    _, calls = runtime(publication, monkeypatch)
    mutate = module.run_mutation_process

    def fail(argv: list[str], payload: bytes) -> subprocess.CompletedProcess[bytes]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, b"", b"temporary failure")

    class Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(module, "run_mutation_process", fail)
    module.execute(path, digest)
    inspected = module.execute(path, digest, inspect=True)
    monkeypatch.setattr(module, "run_mutation_process", mutate)
    monkeypatch.setattr(module.sys, "stdin", Tty("y\n"))
    monkeypatch.setattr(module.sys, "stderr", Tty())
    recovered = module.interactive_recovery(path, digest, inspected, inspected=True)
    assert recovered["status"] == "applied" and len(calls) == 2


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
        assert json.loads(result.stdout)["operations"] == ["apply", "inspect", "retry"]
