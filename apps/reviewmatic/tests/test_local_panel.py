"""Local WIP panel, ported from ``local-panel.test.mjs``.

Covers: one recorded selection, parallel local critics, one arbitration
receipt, a schema-identical finalized report with the receipts preserved as
companions, and the freshness check on a changed working tree.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from reviewmatic import local_review
from reviewmatic.portable.portable_gitlab import contract


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
    path = tmp_path / f"panel-{name}"
    contract.write_json(path, value)
    return str(path)


def _local_finding(identifier: str, summary: str, *, blocking: bool = True) -> dict[str, Any]:
    return {
        "id": identifier,
        "severity": "high" if blocking else "low",
        "status": "open",
        "summary": summary,
        "requirement": "Preserve mixed Markdown verbatim.",
        "scenario": "A user includes an issue reference in a Markdown table.",
        "evidence": "renderer('table #7') rewrites a protected value.",
        "consequence": "The generated table is corrupted.",
        "origin": "regression",
        "minimum_fix": "Keep non-plain-text values unchanged.",
        "blocking": blocking,
        "rationale": "A small correction restores the explicitly agreed behavior.",
        "decision_evidence": None,
        "reopen_reason": None,
    }


def _critic_receipt(
    evidence_digest: str,
    run_id: str,
    session_id: str,
    findings: list[dict[str, Any]],
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": "code-review/local-critic-receipt/v1",
        "evidence_digest": evidence_digest,
        "run_id": run_id,
        "session_id": session_id,
        "findings": findings,
        "question_answers": answers,
        "external_mutations": False,
    }


def test_local_panel_completes_selection_critics_arbitration_and_a_schema_identical_report(
    repo: Path, tmp_path: Path
) -> None:
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
    template["acceptance_criteria"] = {"status": "known", "items": ["Plain references link."]}
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
        _input(
            tmp_path,
            "selection.json",
            {
                "critics": [
                    {"name": "critic-local", "profile": "critic-general"},
                    {"name": "critic-second"},
                ],
                "arbitrator": {"name": "arb-local"},
            },
        ),
    )
    assert selection["status"] == "ok", json.dumps(selection)
    assert selection["critic_count"] == 2
    recorded = local_review.record_local_package(str(snapshot), str(template_path))
    assert recorded["status"] == "ok"
    assert len(recorded["critic_tasks"]) == 2
    assert "--participant critic-local" in recorded["critic_tasks"][0]["import_command"]["command"]

    task = local_review.record_local_input(
        str(snapshot),
        _input(
            tmp_path,
            "task.json",
            {
                "task": {
                    "goal": "Link plain text without modifying mixed Markdown.",
                    "acceptance_criteria": [
                        "Plain references link; mixed Markdown remains unchanged."
                    ],
                    "constraints": ["Do not implement a Markdown parser."],
                    "accepted_risks": [],
                    "deferred": [],
                    "decision_evidence": (
                        "User chose whole-value plain-text linking in the interview."
                    ),
                }
            },
        ),
    )
    assert task["status"] == "ok", json.dumps(task.get("errors"))
    restricted = local_review.record_local_input(
        str(snapshot),
        _input(
            tmp_path,
            "restricted.json",
            {"findings": [_local_finding("host-pass", "Orchestrator finding")]},
        ),
    )
    assert restricted["status"] == "invalid"
    assert any(
        issue["path"] == "$.findings" and "panel" in issue["message"]
        for issue in restricted["errors"]
    )

    versions = recorded["question_context_versions"]

    def answer(verdict: str, evidence: str) -> dict[str, Any]:
        return {
            "question_id": "q-renderer",
            "verdict": verdict,
            "evidence": evidence,
            "context_digest": versions["q-renderer"],
        }

    draft = contract.read_json(Path(draft_path), "draft")
    receipt_a = _input(
        tmp_path,
        "critic-a.json",
        _critic_receipt(
            draft["evidence_digest"],
            "run-a",
            "session-a",
            [_local_finding("local-critic-a", "Renderer rewrites protected table values.")],
            [answer("confirmed", "Protected values stay untouched.")],
        ),
    )
    unbound = local_review.record_local_critic(str(snapshot), receipt_a)
    assert unbound["status"] == "invalid"
    assert any(issue["path"] == "$.participant" for issue in unbound["errors"])

    critic_a = local_review.record_local_critic(str(snapshot), receipt_a, "critic-local")
    assert critic_a["status"] == "ok", json.dumps(critic_a.get("errors"))
    assert "arbitrator_task" not in critic_a
    critic_b = local_review.record_local_critic(
        str(snapshot),
        _input(
            tmp_path,
            "critic-b.json",
            _critic_receipt(
                draft["evidence_digest"],
                "run-b",
                "session-b",
                [
                    _local_finding("local-critic-b", "Protected table values are rewritten."),
                    _local_finding("local-critic-noise", "An unrelated formatting remark."),
                ],
                [answer("refuted", "The staged diff rewrites protected values.")],
            ),
        ),
        "critic-second",
    )
    assert critic_b["status"] == "ok", json.dumps(critic_b.get("errors"))
    assert critic_b["arbitrator_task"]
    arbitration_input = contract.read_json(
        Path(str(critic_b["arbitrator_task"]["input_path"])), "arbitration input"
    )
    assert len(arbitration_input["critic_receipts"]) == 2
    assert arbitration_input["contradictions"] == ["q-renderer"]

    arbitration: dict[str, Any] = {
        "schema": "code-review/local-arbitration/v1",
        "evidence_digest": draft["evidence_digest"],
        "run_id": "arb-run",
        "session_id": "arb-session",
        "arbitrator": {"name": "arb-local"},
        "external_mutations": False,
        "findings": [
            _local_finding(
                "local-critic-a", "Renderer rewrites protected table values.", blocking=False
            )
        ],
        "dispositions": [
            {
                "id": "local-critic-a",
                "decision": "accept",
                "reason": "Confirmed against the staged diff in the working tree.",
            },
            {
                "id": "local-critic-b",
                "decision": "reject",
                "reason": "Duplicates local-critic-a.",
                "duplicate_of": "local-critic-a",
            },
            {
                "id": "local-critic-noise",
                "decision": "reject",
                "reason": "The remark describes intended behavior.",
            },
        ],
        "question_verifications": [
            {
                "question_id": "q-renderer",
                "original": {"run_id": "run-a", "session_id": "session-a", "verdict": "confirmed"},
                "verdict": "confirmed",
                "evidence": "Re-read the staged diff: protected values stay untouched.",
                "context_digest": versions["q-renderer"],
            }
        ],
        "checks": [
            {
                "name": "Renderer acceptance cases",
                "status": "passed",
                "required": True,
                "evidence": "Plain text and protected input examples inspected.",
            }
        ],
        "assessment": "The staged change meets the agreed boundary after the merged correction.",
        "verdict": "ready",
    }
    blocked = local_review.record_local_arbitration(
        str(snapshot),
        _input(tmp_path, "blocked.json", {**arbitration, "question_verifications": []}),
    )
    assert blocked["status"] == "invalid"
    assert any(
        issue["path"] == "$.question_verifications" and "q-renderer" in issue["message"]
        for issue in blocked["errors"]
    ), json.dumps(blocked["errors"])

    mismatch = local_review.record_local_arbitration(
        str(snapshot), _input(tmp_path, "mismatch.json", {**arbitration, "verdict": "not_ready"})
    )
    assert mismatch["status"] == "invalid"
    assert any(issue["path"] == "$.verdict" for issue in mismatch["errors"])

    imported = local_review.record_local_arbitration(
        str(snapshot), _input(tmp_path, "arbitration.json", arbitration)
    )
    assert imported["status"] == "ok", json.dumps(imported.get("errors"))
    saved = local_review.record_review(str(artifact_root), str(snapshot), draft_path)
    assert saved["verdict"] == "ready"
    assert saved["question_summary"]["contradicted"] == 1

    pointer = contract.read_json(artifact_root / "local-review.json", "pointer")
    envelope = contract.read_json(
        artifact_root / "artifacts" / "local_review_report" / f"{pointer['review_digest']}.json",
        "report",
    )
    report = envelope["payload"]
    assert "participants" not in report
    assert "critics" not in report
    assert "arbitration" not in report
    assert [item["id"] for item in report["findings"]] == ["local-critic-a"]

    panel_dir = artifact_root / "local-panel"
    prefix = digest_value[:16]
    assert (panel_dir / f"critics-{prefix}.json").exists()
    assert (panel_dir / f"arbitration-{prefix}.json").exists()
    companions = contract.read_json(panel_dir / f"arbitration-{prefix}.json", "arbitration")
    assert len(companions["dispositions"]) == 3

    # Freshness stays enforced: a changed working tree blocks a repeated
    # finalization against the same snapshot.
    (repo / "renderer.txt").write_text("changed again\n")
    with pytest.raises(
        contract.WorkflowError, match=r"baseline changed|changed before report finalization"
    ):
        local_review.record_review(str(artifact_root), str(snapshot), draft_path)
