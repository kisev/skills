"""OCR critic integration: background rendering, CLI invocation, receipt
mapping, and the panel wiring in both flows.

Covers: the Markdown background rendered from a recorded package, the mocked
``ocr review`` invocation and its failure paths, the OCR-to-receipt mapping for
both finding shapes, the record-participants OCR configuration flags, a full
local panel e2e with a fake OCR binary, and the MR panel wiring. The real CLI
flag contract is asserted only when an ``ocr`` executable is installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from helpers.review_fixture import make_review_fixture

from reviewmatic import draft as draft_module
from reviewmatic import local_review, ocr_critic
from reviewmatic.portable.portable_gitlab import contract

OCR_OUTPUT: dict[str, Any] = {
    "status": "complete",
    "llm": {"provider": "openai", "model": "gpt-x"},
    "comments": [
        {
            "path": "renderer.txt",
            "content": "The rewrite drops the protected prefix.",
            "suggestion_code": "kept = protect(value)",
            "existing_code": "value = rewrite(value)",
            "start_line": 3,
            "end_line": 3,
            "category": "bug",
            "severity": "high",
        },
        {
            "path": "notes.txt",
            "content": "Consider a clearer helper name.",
            "start_line": 0,
            "end_line": 0,
            "category": "maintainability",
        },
    ],
    "session_id": "ocr-session-1",
    "manifest": {
        "schema_version": "ocr.run-manifest/v1",
        "run_id": "ocr-run-1",
        "operation": "review",
        "terminal_state": "complete",
    },
}

PACKAGE: dict[str, Any] = {
    "schema": "portable-gitlab/context-package/v2",
    "mode": "local",
    "goal": {"status": "known", "text": "Link plain text without modifying mixed Markdown."},
    "acceptance_criteria": {
        "status": "known",
        "items": ["Plain references link.", "Mixed Markdown stays verbatim."],
    },
    "background": "The author confirmed the renderer change in the discussion.",
    "claims": [
        {
            "id": "claim-1",
            "kind": "author_claim",
            "statement": "Only plain text values change.",
            "sources": ["MR description"],
        }
    ],
    "constraints": ["Do not implement a Markdown parser."],
    "prior_decisions": [
        {"id": "prior-1", "decision": "resolve: the head bounds the write.", "source": "thread 42"}
    ],
    "questions": [
        {
            "id": "q-renderer",
            "subject": "Does the change touch protected values?",
            "source": "Local conversation",
            "critic": True,
        }
    ],
    "thread_registry": [
        {
            "id": "42",
            "state": "open",
            "summary": "A reviewer remarked on the renderer.",
            "review_relevance": "The change touches this path.",
        }
    ],
}


@pytest.fixture(name="fake_ocr")
def fake_ocr_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    args_file = tmp_path / "ocr-args.txt"
    output_file = tmp_path / "ocr-output.json"
    output_file.write_text(json.dumps(OCR_OUTPUT), encoding="utf-8")
    script = bin_dir / "ocr"
    script.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$OCR_ARGS_FILE"\ncat "$OCR_OUTPUT_FILE"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("OCR_ARGS_FILE", str(args_file))
    monkeypatch.setenv("OCR_OUTPUT_FILE", str(output_file))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return {"args": args_file, "output": output_file, "bin": bin_dir}


def _argv(args_file: Path) -> list[str]:
    return args_file.read_text(encoding="utf-8").strip().split("\n")


def test_render_ocr_background_renders_the_recorded_package(tmp_path: Path) -> None:
    first = ocr_critic.render_ocr_background(PACKAGE, tmp_path, "b" * 64)
    second = ocr_critic.render_ocr_background(PACKAGE, tmp_path, "b" * 64)
    assert first == second
    assert first.name == "ocr-background-" + "b" * 16 + ".md"
    rendered = first.read_text(encoding="utf-8")
    assert "## Goal" in rendered
    assert "Link plain text without modifying mixed Markdown." in rendered
    assert "- Plain references link." in rendered
    assert "[author_claim] Only plain text values change." in rendered
    assert "- Do not implement a Markdown parser." in rendered
    assert "- q-renderer: Does the change touch protected values?; assigned to critics" in rendered
    assert "#42 (open): A reviewer remarked on the renderer." in rendered
    assert "The author confirmed the renderer change in the discussion." in rendered

    minimal = ocr_critic.render_ocr_background(
        {
            "goal": {"status": "unknown"},
            "acceptance_criteria": {"status": "unknown", "items": []},
        },
        tmp_path,
        "c" * 64,
    )
    plain = minimal.read_text(encoding="utf-8")
    assert "Unknown: the author did not record a review goal" in plain
    assert "- Unknown: no acceptance criteria were recorded." in plain


def test_invoke_ocr_critic_builds_the_expected_command(
    fake_ocr: dict[str, Path], tmp_path: Path
) -> None:
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    output = ocr_critic.invoke_ocr_critic(
        background, "aaa", "bbb", "openai", "gpt-x", repo=str(tmp_path)
    )
    assert output["session_id"] == "ocr-session-1"
    arguments = _argv(fake_ocr["args"])
    assert arguments[:2] == ["review", "--format"]
    assert "--audience" in arguments and "agent" in arguments
    assert "--background-file" in arguments
    assert str(background) in arguments
    assert "--repo" in arguments and str(tmp_path) in arguments
    assert "--from" in arguments and "aaa" in arguments
    assert "--to" in arguments and "bbb" in arguments
    assert "--provider" in arguments and "openai" in arguments
    assert "--model" in arguments and "gpt-x" in arguments

    ocr_critic.invoke_ocr_critic(background, None, None, None, None, repo=str(tmp_path))
    workspace = _argv(fake_ocr["args"])
    assert "--from" not in workspace
    assert "--to" not in workspace
    assert "--provider" not in workspace
    assert "--model" not in workspace

    with pytest.raises(contract.WorkflowError, match="both --from and --to"):
        ocr_critic.invoke_ocr_critic(background, "aaa", None, None, None, repo=str(tmp_path))


def test_invoke_ocr_critic_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    background = tmp_path / "background.md"
    background.write_text("# background\n", encoding="utf-8")
    system_path = os.environ.get("PATH", "")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    with pytest.raises(contract.WorkflowError, match="ocr CLI is not available"):
        ocr_critic.invoke_ocr_critic(background, None, None, None, None, repo=str(tmp_path))

    failing = tmp_path / "failing-bin"
    failing.mkdir()
    script = failing / "ocr"
    script.write_text("#!/bin/sh\necho 'provider exploded' >&2\nexit 7\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{failing}{os.pathsep}{system_path}")
    with pytest.raises(contract.WorkflowError, match="provider exploded") as excinfo:
        ocr_critic.invoke_ocr_critic(background, None, None, None, None, repo=str(tmp_path))
    assert "7" in str(excinfo.value)

    noisy = tmp_path / "noisy-bin"
    noisy.mkdir()
    script = noisy / "ocr"
    script.write_text("#!/bin/sh\necho 'not json'\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{noisy}{os.pathsep}{system_path}")
    with pytest.raises(contract.WorkflowError, match="valid JSON"):
        ocr_critic.invoke_ocr_critic(background, None, None, None, None, repo=str(tmp_path))

    slow = tmp_path / "slow-bin"
    slow.mkdir()
    script = slow / "ocr"
    script.write_text("#!/bin/sh\n/usr/bin/sleep 5\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{slow}{os.pathsep}{system_path}")
    with pytest.raises(contract.WorkflowError, match="did not finish within 1 seconds"):
        ocr_critic.invoke_ocr_critic(
            background, None, None, None, None, repo=str(tmp_path), timeout=1
        )


def test_map_ocr_receipt_maps_findings_for_both_kinds() -> None:
    receipt = ocr_critic.map_ocr_receipt(
        OCR_OUTPUT, evidence_digest="a" * 64, kind="mr", package=PACKAGE
    )
    assert receipt["schema"] == "portable-gitlab/critic-receipt/v2"
    assert receipt["run_id"] == "ocr-run-1"
    assert receipt["session_id"] == "ocr-session-1"
    assert receipt["evidence_digest"] == "a" * 64
    assert receipt["question_answers"] == []
    assert receipt["external_mutations"] is False
    assert receipt["engine"] == "ocr"
    assert receipt["ocr"] == {
        "provider": "openai",
        "model": "gpt-x",
        "terminal_state": "complete",
        "comments": 2,
    }
    issues = draft_module.schema_issues(draft_module._CRITIC_INPUT, receipt)
    assert issues == [], json.dumps(issues)
    first, second = receipt["findings"]
    assert first["id"].startswith("ocr-0-")
    assert first["severity"] == "high"
    assert first["summary"] == "The rewrite drops the protected prefix."
    assert first["evidence"][0] == "OpenCodeReview located the finding at renderer.txt:3-3."
    assert first["minimum_fix"] == "kept = protect(value)"
    assert second["severity"] == "low"
    assert "notes.txt" in second["evidence"][0]

    local = ocr_critic.map_ocr_receipt(
        OCR_OUTPUT, evidence_digest="a" * 64, kind="local", package=PACKAGE
    )
    assert local["schema"] == "code-review/local-critic-receipt/v1"
    issues = draft_module.schema_issues(local_review._LOCAL_CRITIC_RECEIPT_SCHEMA, local)
    assert issues == [], json.dumps(issues)
    finding = local["findings"][0]
    assert finding["status"] == "open"
    assert finding["blocking"] is True
    assert finding["origin"] == "regression"
    assert finding["requirement"] == "Link plain text without modifying mixed Markdown."
    assert finding["decision_evidence"] is None
    assert "renderer.txt:3-3" in finding["evidence"]
    assert local["findings"][1]["blocking"] is False

    without_session = {**OCR_OUTPUT, "session_id": ""}
    with pytest.raises(contract.WorkflowError, match="session_id"):
        ocr_critic.map_ocr_receipt(without_session, evidence_digest="a" * 64, kind="mr")


def test_pure_ocr_output_without_comments_maps_an_empty_receipt() -> None:
    empty = {
        "status": "complete",
        "llm": {"model": "m"},
        "comments": [],
        "session_id": "ocr-session-2",
    }
    receipt = ocr_critic.map_ocr_receipt(empty, evidence_digest="a" * 64, kind="mr")
    assert receipt["findings"] == []
    assert receipt["ocr"]["provider"] == "configured"
    assert receipt["ocr"]["comments"] == 0


@pytest.fixture(name="repo")
def local_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "checkout"
    repo.mkdir()

    def git(*arguments: str) -> None:
        subprocess.run(["git", "-C", str(repo), *arguments], check=True, capture_output=True)

    git("init", "--quiet")
    git("config", "commit.gpgsign", "false")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (repo / "renderer.txt").write_text("base\n")
    git("add", ".")
    git("commit", "-qm", "base")
    (repo / "renderer.txt").write_text("broken\n")
    return repo


def _input(tmp_path: Path, name: str, value: Any) -> str:
    path = tmp_path / f"ocr-{name}"
    contract.write_json(path, value)
    return str(path)


def _prepare_local_panel(
    repo: Path, tmp_path: Path, critics: list[dict[str, Any]]
) -> tuple[Path, Path, str, str, dict[str, str]]:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    artifact_root = Path(str(bundle["artifact_root"]))
    snapshot, digest_value = contract.write_artifact(artifact_root, "local_wip_snapshot", bundle)
    context = local_review.prepare_followup(str(artifact_root), bundle, digest_value, "auto")
    draft_path = str(context["draft_path"])
    template_path = Path(str(context["context_package"]["template_path"]))
    template = contract.read_json(template_path, "template")
    template["goal"] = {
        "status": "known",
        "text": "Link plain text without modifying mixed Markdown.",
    }
    template["questions"] = [
        {
            "id": "q-renderer",
            "subject": "Does the staged renderer change touch protected values?",
            "source": "Local conversation with the author",
            "critic": True,
        }
    ]
    contract.write_json(template_path, template)
    selection = local_review.record_local_participants(
        str(snapshot),
        _input(tmp_path, "selection.json", {"critics": critics, "arbitrator": {"name": "arb"}}),
    )
    assert selection["status"] == "ok", json.dumps(selection)
    recorded = local_review.record_local_package(str(snapshot), str(template_path))
    assert recorded["status"] == "ok", json.dumps(recorded)
    task = local_review.record_local_input(
        str(snapshot),
        _input(
            tmp_path,
            "task.json",
            {
                "task": {
                    "goal": "Link plain text without modifying mixed Markdown.",
                    "acceptance_criteria": ["Plain references link."],
                    "constraints": [],
                    "accepted_risks": [],
                    "deferred": [],
                    "decision_evidence": "User chose plain-text linking.",
                }
            },
        ),
    )
    assert task["status"] == "ok", json.dumps(task.get("errors"))
    versions = recorded["question_context_versions"]
    assert isinstance(versions, dict) and all(isinstance(key, str) for key in versions)
    return artifact_root, snapshot, draft_path, digest_value, cast("dict[str, str]", versions)


def test_participants_record_ocr_engine_and_configuration(repo: Path, tmp_path: Path) -> None:
    bundle = local_review.local_bundle(str(repo), "code-review", None)
    artifact_root = Path(str(bundle["artifact_root"]))
    snapshot, _ = contract.write_artifact(artifact_root, "local_wip_snapshot", bundle)
    selection = local_review.record_local_participants(
        str(snapshot),
        _input(
            tmp_path,
            "selection.json",
            {
                "critics": [{"name": "ocr-critic", "engine": "ocr"}, {"name": "model-critic"}],
                "arbitrator": {"name": "arb"},
            },
        ),
    )
    assert selection["status"] == "ok"
    assert selection["participants"]["critics"][0]["engine"] == "ocr"
    assert "engine" not in selection["participants"]["critics"][1]

    flagged = local_review.record_local_participants(
        str(snapshot),
        _input(
            tmp_path,
            "flagged.json",
            {"critics": [{"name": "ocr-critic", "engine": "ocr"}], "arbitrator": {"name": "arb"}},
        ),
        ocr_provider="openai",
        ocr_model="gpt-x",
    )
    assert flagged["status"] == "ok"
    assert flagged["participants"]["critics"][0]["provider"] == "openai"
    assert flagged["participants"]["critics"][0]["model"] == "gpt-x"

    stray = local_review.record_local_participants(
        str(snapshot),
        _input(
            tmp_path,
            "stray.json",
            {"critics": [{"name": "model-critic"}], "arbitrator": {"name": "arb"}},
        ),
        ocr_model="gpt-x",
    )
    assert stray["status"] == "invalid"
    assert any("ocr" in issue["message"] for issue in stray["errors"])


def test_local_panel_runs_ocr_and_model_critics_end_to_end(
    repo: Path, tmp_path: Path, fake_ocr: dict[str, Path]
) -> None:
    artifact_root, snapshot, draft_path, _digest_value, versions = _prepare_local_panel(
        repo,
        tmp_path,
        [{"name": "ocr-critic", "engine": "ocr"}, {"name": "model-critic"}],
    )
    draft = contract.read_json(Path(draft_path), "draft")

    with pytest.raises(contract.WorkflowError, match="is a model critic"):
        local_review.record_local_ocr_critic(str(snapshot), "model-critic")
    with pytest.raises(contract.WorkflowError, match="Unknown participant"):
        local_review.record_local_ocr_critic(str(snapshot), "nobody")

    ocr_run = local_review.record_local_ocr_critic(str(snapshot), "ocr-critic")
    assert ocr_run["status"] == "ok", json.dumps(ocr_run.get("errors"))
    assert ocr_run["ocr"]["provider"] == "openai"
    assert ocr_run["ocr"]["model"] == "gpt-x"
    assert ocr_run["ocr"]["terminal_state"] == "complete"
    assert ocr_run["ocr"]["mode"] == "workspace"
    background = Path(str(ocr_run["ocr"]["background_path"]))
    assert background.exists()
    assert "Link plain text" in background.read_text(encoding="utf-8")
    assert "--from" not in _argv(fake_ocr["args"])
    receipt_path = Path(str(ocr_run["ocr"]["receipt_path"]))
    assert receipt_path.exists()

    stored = contract.read_json(Path(draft_path), "draft")
    ocr_participant = next(
        item for item in cast_participants(stored) if str(item["name"]) == "ocr-critic"
    )
    assert ocr_participant["receipt"] == {"run_id": "ocr-run-1", "session_id": "ocr-session-1"}
    ocr_receipt = next(
        item
        for item in cast("list[dict[str, Any]]", stored["critics"])
        if str(item.get("session_id")) == "ocr-session-1"
    )
    assert [finding["id"] for finding in ocr_receipt["findings"]] == [
        "ocr-0-renderer.txt",
        "ocr-1-notes.txt",
    ]

    model_receipt = {
        "schema": "code-review/local-critic-receipt/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "run-model",
        "session_id": "session-model",
        "findings": [],
        "question_answers": [
            {
                "question_id": "q-renderer",
                "verdict": "confirmed",
                "evidence": "Protected values stay untouched.",
                "context_digest": versions["q-renderer"],
            }
        ],
        "external_mutations": False,
    }
    model = local_review.record_local_critic(
        str(snapshot), _input(tmp_path, "model.json", model_receipt), "model-critic"
    )
    assert model["status"] == "ok", json.dumps(model.get("errors"))
    assert model["arbitrator_task"]

    arbitration: dict[str, Any] = {
        "schema": "code-review/local-arbitration/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "arb-run",
        "session_id": "arb-session",
        "arbitrator": {"name": "arb"},
        "external_mutations": False,
        "findings": [_local_finding("ocr-0-renderer.txt")],
        "dispositions": [
            {
                "id": "ocr-0-renderer.txt",
                "decision": "accept",
                "reason": "Confirmed against the working tree.",
            },
            {
                "id": "ocr-1-notes.txt",
                "decision": "reject",
                "reason": "A naming remark, not a defect in the recorded change.",
            },
        ],
        "question_verifications": [],
        "checks": [
            {
                "name": "Renderer acceptance cases",
                "status": "passed",
                "required": True,
                "evidence": "Inspected the staged diff.",
            }
        ],
        "assessment": "The staged change meets the recorded goal after the OCR finding.",
        "verdict": "ready",
    }
    imported = local_review.record_local_arbitration(
        str(snapshot), _input(tmp_path, "arbitration.json", arbitration)
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    saved = local_review.record_review(str(artifact_root), str(snapshot), draft_path)
    assert saved["verdict"] == "ready"
    assert saved["question_summary"]["answered"] == 1
    assert saved["question_summary"]["contradicted"] == 0


def cast_participants(draft: dict[str, Any]) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        cast("dict[str, Any]", draft["participants"])["critics"],
    )


def _local_finding(identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "severity": "high",
        "status": "open",
        "summary": "The renderer rewrites protected values.",
        "requirement": "Preserve mixed Markdown verbatim.",
        "scenario": "A user includes an issue reference in a Markdown table.",
        "evidence": "renderer('table #7') rewrites a protected value.",
        "consequence": "The generated table is corrupted.",
        "origin": "regression",
        "minimum_fix": "Keep non-plain-text values unchanged.",
        "blocking": False,
        "rationale": "The arbitrator confirmed the reported defect.",
        "decision_evidence": None,
        "reopen_reason": None,
    }


def test_pure_ocr_panel_resolves_assigned_questions_through_arbitration(
    repo: Path, tmp_path: Path, fake_ocr: dict[str, Path]
) -> None:
    artifact_root, snapshot, draft_path, _digest, versions = _prepare_local_panel(
        repo, tmp_path, [{"name": "ocr-critic", "engine": "ocr"}]
    )
    draft = contract.read_json(Path(draft_path), "draft")
    ocr_run = local_review.record_local_ocr_critic(str(snapshot), "ocr-critic")
    assert ocr_run["status"] == "ok", json.dumps(ocr_run.get("errors"))
    arbitrator_task = cast("dict[str, Any] | None", ocr_run.get("arbitrator_task"))
    assert arbitrator_task is not None

    arbitration: dict[str, Any] = {
        "schema": "code-review/local-arbitration/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "arb-run",
        "session_id": "arb-session",
        "arbitrator": {"name": "arb"},
        "external_mutations": False,
        "findings": [],
        "dispositions": [
            {
                "id": "ocr-0-renderer.txt",
                "decision": "reject",
                "reason": "The working tree keeps the protected prefix; the finding does not "
                "reproduce.",
            },
            {
                "id": "ocr-1-notes.txt",
                "decision": "reject",
                "reason": "A naming remark outside the recorded change.",
            },
        ],
        "question_verifications": [
            {
                "question_id": "q-renderer",
                "original": {
                    "run_id": "ocr-run-1",
                    "session_id": "ocr-session-1",
                    "verdict": "not_verified",
                },
                "verdict": "confirmed",
                "evidence": "The staged diff rewrites plain text values only.",
                "context_digest": versions["q-renderer"],
            }
        ],
        "checks": [
            {
                "name": "Renderer acceptance cases",
                "status": "passed",
                "required": True,
                "evidence": "Inspected the staged diff.",
            }
        ],
        "assessment": "OCR findings were refuted on direct evidence; the question is resolved.",
        "verdict": "ready",
    }
    imported = local_review.record_local_arbitration(
        str(snapshot), _input(tmp_path, "arbitration.json", arbitration)
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    saved = local_review.record_review(str(artifact_root), str(snapshot), draft_path)
    assert saved["verdict"] == "ready"


def test_mr_panel_returns_an_ocr_run_command_and_imports_the_receipt(
    tmp_path: Path, fake_ocr: dict[str, Path]
) -> None:
    fixture = make_review_fixture()
    try:
        started = draft_module.start_review(
            url=fixture.url, repo_root=str(fixture.repo), locale="en"
        )
        assert started["status"] == "ok"
        draft_path = str(started["draft_path"])
        template_path = Path(str(started["context_package"]["template_path"]))
        template = contract.read_json(template_path, "package template")
        template["questions"] = []
        for item in template["thread_registry"]:
            item["summary"] = "A reviewer remarked on the retry path."
            item["review_relevance"] = "The change touches this path."
        contract.write_json(template_path, template)
        selection = draft_module.record_draft_participants(
            draft_path,
            _write_input(tmp_path, selection_with_ocr()),
            ocr_provider="openai",
            ocr_model="gpt-x",
        )
        assert selection["status"] == "ok"
        recorded = draft_module.record_draft_package(draft_path, str(template_path))
        assert recorded["status"] == "ok", json.dumps(recorded)
        tasks = recorded["critic_tasks"]
        ocr_task = next(task for task in tasks if task.get("engine") == "ocr")
        assert ocr_task["participant"] == "ocr-critic"
        assert "record-ocr-critic --draft" in ocr_task["run_command"]["command"]
        assert "--participant ocr-critic" in ocr_task["run_command"]["command"]
        assert "import_command" not in ocr_task
        model_task = next(task for task in tasks if task.get("engine") is None)
        assert "record-critic --draft" in model_task["import_command"]["command"]

        with pytest.raises(contract.WorkflowError, match="is a model critic"):
            draft_module.record_ocr_critic(draft_path, "model-critic")

        run = draft_module.record_ocr_critic(draft_path, "ocr-critic")
        assert run["status"] == "ok", json.dumps(run.get("errors"))
        assert run["ocr"]["terminal_state"] == "complete"
        arguments = _argv(fake_ocr["args"])
        assert "--from" in arguments and "--to" in arguments
        background = Path(str(run["ocr"]["background_path"]))
        assert background.exists()
        stored = contract.read_json(Path(draft_path), "draft")
        participant = next(
            item for item in cast_participants(stored) if str(item["name"]) == "ocr-critic"
        )
        assert participant["receipt"] == {"run_id": "ocr-run-1", "session_id": "ocr-session-1"}
        assert stored["critics"][0]["engine"] == "ocr"
        assert stored["critics"][0]["ocr"]["comments"] == 2

        with pytest.raises(contract.WorkflowError, match="already has an imported receipt"):
            draft_module.record_ocr_critic(draft_path, "ocr-critic")
    finally:
        fixture.close()


def selection_with_ocr() -> dict[str, Any]:
    return {
        "critics": [{"name": "ocr-critic", "engine": "ocr"}, {"name": "model-critic"}],
        "arbitrator": {"name": "arb-main"},
    }


def _write_input(tmp_path: Path, value: Any) -> str:
    path = tmp_path / "participants.json"
    contract.write_json(path, value)
    return str(path)


@pytest.mark.skipif(shutil.which("ocr") is None, reason="the ocr CLI is not installed")
def test_installed_ocr_cli_exposes_the_flags_the_invocation_uses() -> None:
    result = subprocess.run(
        ["ocr", "review", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    for flag in (
        "--background-file",
        "--from",
        "--to",
        "--provider",
        "--model",
        "--repo",
        "--format",
        "--audience",
    ):
        assert flag in result.stdout, flag


def test_invoke_ocr_critic_preflights_the_background_limit(tmp_path: Path) -> None:
    """An oversized background refuses before the CLI spawns."""
    bulky = tmp_path / "oversized-background.md"
    bulky.write_text("x" * (ocr_critic.OCR_BACKGROUND_LIMIT + 1), encoding="utf-8")
    with pytest.raises(contract.WorkflowError, match="above the ocr CLI limit"):
        ocr_critic.invoke_ocr_critic(bulky, "a" * 40, "b" * 40, None, None, repo=str(tmp_path))


def test_delta_scoped_previous_findings_select_by_publication_intersection() -> None:
    incremental = {
        "incremental_delta": {"changed_paths": ["renderer.txt", "notes.txt"]},
        "previous_findings": [
            {"id": "touched-line", "severity": "high", "summary": "Positioned."},
            {"id": "touched-patch", "severity": "low", "summary": "General patch."},
            {"id": "untouched", "severity": "low", "summary": "Elsewhere."},
            {"id": "unpublished", "severity": "low", "summary": "No publication."},
        ],
        "previous_finding_publications": [
            {"finding_id": "touched-line", "path": "renderer.txt", "patch": None},
            {
                "finding_id": "touched-patch",
                "path": None,
                "patch": "diff --git a/notes.txt b/notes.txt\n--- a/notes.txt\n",
            },
            {"finding_id": "untouched", "path": "other.txt", "patch": None},
        ],
    }
    scoped = ocr_critic.delta_scoped_previous_findings(incremental)
    assert [str(item["id"]) for item in scoped] == ["touched-line", "touched-patch"]
    assert ocr_critic.delta_scoped_previous_findings({}) == []
    assert (
        ocr_critic.delta_scoped_previous_findings(
            {
                "incremental_delta": {"changed_paths": []},
                "previous_findings": [],
                "previous_finding_publications": [],
            }
        )
        == []
    )


def test_render_ocr_background_renders_previous_findings_deterministically(
    tmp_path: Path,
) -> None:
    previous = [{"id": "docs-1", "severity": "low", "summary": "Retry lacks the key."}]
    first = ocr_critic.render_ocr_background(
        PACKAGE, tmp_path, "b" * 64, previous_findings=previous
    )
    second = ocr_critic.render_ocr_background(
        PACKAGE, tmp_path, "b" * 64, previous_findings=previous
    )
    assert first == second
    rendered = first.read_text(encoding="utf-8")
    assert "## Previously reported findings" in rendered
    assert "- docs-1 (low): Retry lacks the key." in rendered
    assert "advisory context from a previous snapshot" in rendered
    assert "Report every currently observed problem" in rendered
    # The identity digest accounts for the parameter: different sets never
    # share a file, and the plain render keeps its own name.
    plain = ocr_critic.render_ocr_background(PACKAGE, tmp_path, "b" * 64)
    assert plain.name != first.name
    other = ocr_critic.render_ocr_background(
        PACKAGE,
        tmp_path,
        "b" * 64,
        previous_findings=[{"id": "docs-2", "severity": "low", "summary": "Other."}],
    )
    assert other.name != first.name


def test_map_ocr_receipt_stamps_scope_only_for_mr() -> None:
    output = dict(OCR_OUTPUT, comments=[])
    mr = ocr_critic.map_ocr_receipt(
        output,
        evidence_digest="a" * 64,
        kind="mr",
        scope_digest="d" * 64,
        target_finding_ids=["docs-1"],
    )
    assert mr["scope_digest"] == "d" * 64
    assert mr["target_finding_ids"] == ["docs-1"]
    contract.validate_critic(mr, "a" * 64, "d" * 64)
    # An empty OCR answer on a small delta is a valid receipt without findings.
    empty = ocr_critic.map_ocr_receipt(
        dict(OCR_OUTPUT, comments=[]),
        evidence_digest="a" * 64,
        kind="mr",
        scope_digest="d" * 64,
        target_finding_ids=[],
    )
    contract.validate_critic(empty, "a" * 64, "d" * 64)
    local = ocr_critic.map_ocr_receipt(output, evidence_digest="a" * 64, kind="local")
    assert "scope_digest" not in local
    with pytest.raises(contract.WorkflowError, match="MR receipts only"):
        ocr_critic.map_ocr_receipt(
            output, evidence_digest="a" * 64, kind="local", scope_digest="d" * 64
        )
