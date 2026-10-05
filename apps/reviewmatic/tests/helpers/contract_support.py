"""Payload builders and inline fake ``glab`` binaries for the contract scenarios.

The builders mirror the helper functions at the top of ``contract.test.mjs``.
The fake binaries replace the Node-script ``glab`` the TypeScript tests write
into a temporary ``PATH`` directory with standard-library Python scripts that
keep the same observable behavior.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Any

from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

DIGEST = "a" * 64
CREATED_AT = "2026-09-14T00:00:00Z"


def use_state_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path


def install_glab(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: str) -> Path:
    """Put a Python ``glab`` first on PATH; ``body`` is the script after the shebang."""
    glab_dir = tmp_path / "bin"
    glab_dir.mkdir(parents=True, exist_ok=True)
    script = glab_dir / "glab"
    script.write_text(f"#!{sys.executable}\n{body}")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{glab_dir}:{os.environ.get('PATH', '')}")
    return script


def component() -> dict[str, Any]:
    return {"items": [], "complete": True, "errors": [], "pages": 1, "truncated": False}


def detailed_finding(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "finding-1",
        "severity": "low",
        "summary": "The contract example is concrete.",
        "risk": "Schema drift can invalidate emitted artifacts.",
        "evidence": ["tests/test_json_schemas.py"],
        "consequence": "A consumer could reject an artifact.",
        "relation_to_change": "The schema is part of the maintained contract.",
        "minimum_fix": "Keep the producer and schema aligned.",
        **overrides,
    }


def incremental_state(mode: str = "full") -> dict[str, Any]:
    delta: dict[str, Any] = {
        "from_head": None,
        "to_head": "c",
        "changed_paths": [],
        "changed_thread_ids": [],
        "unchanged_thread_ids": [],
        "changed_note_ids": [],
        "unchanged_note_ids": [],
        "metadata_fields": [],
        "pipelines_changed": False,
    }
    return {
        "contract_version": 1,
        "requested": "auto",
        "mode": mode,
        "reason": "no compatible finalized baseline exists",
        "incremental_baseline": {"plan_path": None, "plan_digest": None, "state_digest": None},
        "previous_findings": [],
        "previous_finding_publications": [],
        "previous_recommended_issues": [],
        "previous_finding_ledger": [],
        "previous_publication_ledger": [],
        "previous_thread_decisions": [],
        "previous_rejected_candidates": [],
        "reconsidered_rejected_candidates": [],
        "incremental_delta": delta,
        "incremental_delta_digest": contract.digest(delta),
        "critic_required": False,
        "fallback_reasons": [],
    }


def evidence_payload() -> dict[str, Any]:
    return {
        "schema_version": contract.ARTIFACT_VERSION,
        "profile": "code-review",
        "external_mutations": False,
        "target": {},
        "project": {},
        "object": {},
        "labels": component(),
        "changed_files": component(),
        "commits": component(),
        "pipelines": component(),
        "discussions": component(),
        "head_sha": "c",
        "base_sha": "a",
        "start_sha": "b",
        "artifact_root": "/tmp/portable-artifacts",
        "prepared_at": CREATED_AT,
        "components_complete": {
            "project": True,
            "labels": True,
            "object": True,
            "changed_files": True,
            "commits": True,
            "pipelines": True,
            "discussions": True,
        },
        "retrieval_complete": True,
    }


def context_payload() -> dict[str, Any]:
    return {
        "schema_version": contract.ARTIFACT_VERSION,
        "profile": "code-review",
        "external_mutations": False,
        "evidence_digest": DIGEST,
        "target": {},
        "role": "reviewer",
        "current_user_id": 23,
        "current_user_username": "reviewer",
        "mr_author_username": "author",
        "discussions": [],
        "notes": [],
        "issue_templates": [],
        "counts": {
            "discussions": 0,
            "notes": 0,
            "content_notes": 0,
            "system_notes": 0,
            "open_resolvable": 0,
            "resolved_resolvable": 0,
            "plain_discussions": 0,
        },
        "exact_git": {
            "repo_root": "/tmp/repository",
            "refs": {},
            "changed_paths": [],
            "diff_sha256": None,
            "complete": True,
            "errors": [],
        },
        "incremental": incremental_state(),
        "complete": True,
        "errors": [],
        "artifact_root": "/tmp/portable-artifacts",
        "prepared_at": CREATED_AT,
    }


def label_review_payload() -> dict[str, Any]:
    catalog = [{"name": "semver::patch", "description": "Backward-compatible fix"}]
    return {
        "complete": True,
        "catalog_sha256": contract.digest(catalog),
        "catalog": catalog,
        "assessments": [
            {
                "name": "semver::patch",
                "description": "Backward-compatible fix",
                "status": "applicable",
                "rationale": "The fix has patch SemVer impact.",
                "current": False,
            }
        ],
        "current": [],
        "add": ["semver::patch"],
        "remove": [],
        "proposed": ["semver::patch"],
        "unresolved": [],
        "semver": {"impact": "patch", "candidates": ["semver::patch"], "selected": "semver::patch"},
    }


def presentation_fixture() -> dict[str, Any]:
    return {
        "title": "Code review publication plan",
        "incremental_notice": None,
        "target_label": "Target",
        "role_label": "Role",
        "role_value": "reviewer",
        "verdict_label": "Verdict",
        "verdict_value": "ready",
        "metadata_heading": "MR metadata",
        "labels_heading": "Project labels",
        "previous_findings_heading": "Previous findings",
        "open_threads_heading": "Open threads",
        "closed_threads_heading": "Closed threads",
        "local_fixes_heading": "Local fixes",
        "new_findings_heading": "Findings",
        "recommended_issues_heading": "Recommended issues",
        "checked_heading": "Reviewed without publication",
        "architecture_heading": "Architecture",
        "semver_heading": "SemVer",
        "checks_heading": "Checks",
        "publication_heading": "Manual publication",
        "no_items": "None.",
        "publication_warning": "No command was executed.",
        "evidence_label": "Evidence",
        "relation_label": "Relation to change",
        "severity_labels": {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        },
        "recovery_label": "If the response succeeds but the state change fails, run only:",
        "previous_table_headers": [
            "ID",
            "Previous status",
            "Current status",
            "Rationale",
            "Action",
        ],
    }


def _metadata_item(name: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "rationale": f"The {name} metadata is sufficient.",
        "recommendation": None,
    }


def review_plan_payload() -> dict[str, Any]:
    return {
        "profile": "code-review",
        "review_contract_version": 5,
        "external_mutations": False,
        "evidence_digest": DIGEST,
        "context_digest": DIGEST,
        "decision_digest": DIGEST,
        "target": {},
        "role": "reviewer",
        "mode": "deep",
        "locale": "en",
        "incremental": incremental_state(),
        "verdict": "ready",
        "complete": True,
        "summary": "The concrete contract example is valid.",
        "architecture_assessment": "The existing ownership boundary is preserved.",
        "semver_impact": "patch",
        "semver_rationale": "The fix changes behavior without changing the public API.",
        "label_review": label_review_payload(),
        "mr_metadata_assessment": {
            "observed": {
                "title": "Fix schema drift",
                "description": "Align the producer and schema.",
                "labels": ["type::bug"],
                "workflow_state": "merged",
            },
            "assessment": {
                name: _metadata_item(name)
                for name in ("title", "description", "labels", "workflow_state", "overall")
            },
        },
        "chat_assessment": {
            "necessity": {"status": "supported", "rationale": "The defect is confirmed."},
            "relevance": {"status": "current", "rationale": "The exact head is current."},
            "change": "The change fixes the reviewed behavior.",
        },
        "publication_preview": {
            "mr_state": "merged",
            "warning": "Actions are prepared but were not executed.",
            "body_files": [],
            "actions": [],
        },
        "presentation": presentation_fixture(),
        "checks": ["task check"],
        "findings": [detailed_finding()],
        "finding_publications": [],
        "previous_finding_assessments": [],
        "recommended_issues": [],
        "finding_ledger": [],
        "publication_ledger": [],
        "rejected_candidates": [],
        "rejected_candidate_assessments": [],
        "rejected_candidate_ledger": [],
        "thread_decisions": [],
        "markdown": "# Review plan",
    }


def critic_payload() -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/critic-receipt/v2",
        "evidence_digest": DIGEST,
        "run_id": "critic-run",
        "session_id": "critic-session",
        "scope_digest": DIGEST,
        "target_finding_ids": [],
        "findings": [
            detailed_finding(
                id="rejected-1", summary="The broader cleanup is not part of this change."
            )
        ],
        "external_mutations": False,
    }


def decision_payload() -> dict[str, Any]:
    return {
        "schema": "portable-gitlab/review-decision/v2",
        "evidence_digest": DIGEST,
        "finalize_digest": DIGEST,
        "context_digest": DIGEST,
        "critic_receipt_digest": DIGEST,
        "mode": "deep",
        "external_mutations": False,
        "run_id": "review-run",
        "session_id": "review-session",
        "verdict": "ready",
        "low_risk": True,
        "blocking_findings": False,
        "blocking_finding_ids": [],
        "owner_decision_reasons": [],
        "findings": [detailed_finding()],
        "unresolved_threads": [],
        "responses": [
            {"id": "finding-1", "decision": "accept", "reason": "confirmed"},
            {"id": "rejected-1", "decision": "reject", "reason": "outside the changed contract"},
        ],
    }


def json_literal(value: object) -> str:
    return json.dumps(value)
