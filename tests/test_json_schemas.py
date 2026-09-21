from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
from jsonschema import FormatChecker, ValidationError
from jsonschema.validators import validator_for

from scripts import eval_runner
from shared.references.portable_gitlab.contract import WorkflowError, validate_v2_artifact
from tests.test_review_semver import fallback_assessment, release_assessment
from tests.test_work_item_contract import item as work_item

if TYPE_CHECKING:
    from jsonschema.protocols import Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATHS = {
    "evals/schemas/result-v1.schema.json",
    "evals/schemas/scenario-v1.schema.json",
    "packages/opencode/contracts/critic-report-v1.schema.json",
    "packages/opencode/contracts/execution-card-v1.schema.json",
    "packages/opencode/contracts/mapper-report-v1.schema.json",
    "packages/opencode/contracts/review-report-v1.schema.json",
    "packages/opencode/contracts/routing-receipt-v1.schema.json",
    "packages/opencode/contracts/worker-report-v1.schema.json",
    "shared/references/portable_gitlab/artifact-contracts-v2.schema.json",
    "shared/references/team_runtime/team-context.schema.json",
    "shared/references/work-item-contract.schema.json",
}
DIGEST = "a" * 64
CREATED_AT = "2026-09-14T00:00:00Z"


def load(path: str | Path) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validator(path: str) -> Validator:
    schema = load(path)
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    return validator_type(schema, format_checker=FormatChecker())


def envelope(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"portable-gitlab/{kind}/v2",
        "schema_version": 2,
        "kind": kind,
        "created_at": CREATED_AT,
        "payload": payload,
    }


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
    ).hexdigest()


def component() -> dict[str, Any]:
    return {"items": [], "complete": True, "errors": [], "pages": 1, "truncated": False}


def identity() -> dict[str, str]:
    return {"base_sha": "a", "start_sha": "b", "head_sha": "c"}


def artifact_instances() -> list[dict[str, Any]]:
    finding = {
        "id": "finding-1",
        "severity": "low",
        "summary": "The contract example is concrete.",
        "risk": "Schema drift can invalidate emitted artifacts.",
        "evidence": ["tests/test_json_schemas.py"],
        "consequence": "A consumer could reject an artifact.",
        "relation_to_change": "The schema is part of the maintained contract.",
        "minimum_fix": "Keep the producer and schema aligned.",
    }
    rejected_finding = {
        **finding,
        "id": "rejected-1",
        "summary": "The broader cleanup is not part of this change.",
    }
    patch_content = (
        "diff --git a/example.txt b/example.txt\n"
        "--- a/example.txt\n"
        "+++ b/example.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    patch_digest = hashlib.sha256(patch_content.encode()).hexdigest()
    body_content = "Finding body\n\n```diff\n" + patch_content.rstrip() + "\n```\n"
    body_digest = hashlib.sha256(body_content.encode()).hexdigest()
    issue_content = "Issue body\n"
    issue_digest = hashlib.sha256(issue_content.encode()).hexdigest()
    incremental_delta: dict[str, Any] = {
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
    incremental = {
        "contract_version": 1,
        "requested": "auto",
        "mode": "full",
        "reason": "no compatible finalized baseline exists",
        "incremental_baseline": {
            "plan_path": None,
            "plan_digest": None,
            "state_digest": None,
        },
        "previous_findings": [],
        "previous_finding_publications": [],
        "previous_recommended_issues": [],
        "previous_finding_ledger": [],
        "previous_publication_ledger": [],
        "previous_thread_decisions": [],
        "previous_rejected_candidates": [],
        "reconsidered_rejected_candidates": [],
        "incremental_delta": incremental_delta,
        "incremental_delta_digest": hashlib.sha256(
            json.dumps(
                incremental_delta,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        ).hexdigest(),
        "critic_required": False,
        "fallback_reasons": [],
    }
    presentation = {
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
    gate = {"status": "passed", "evidence": ["task check"], "range": identity()}
    evidence = envelope(
        "evidence_snapshot",
        {
            "schema_version": 2,
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
        },
    )
    local = envelope(
        "local_wip_snapshot",
        {
            "schema_version": 2,
            "profile": "code-review",
            "external_mutations": False,
            "repo_root": "/tmp/repository",
            "base_sha": "a",
            "head_sha": "b",
            "ref": "main",
            "sections": {"committed": {}, "staged": {}, "unstaged": {}, "untracked": {}},
            "artifact_root": "/tmp/portable-artifacts",
            "retrieval_complete": True,
        },
    )
    inventory = envelope(
        "release_inventory",
        {
            "schema_version": 2,
            "profile": "release-prepare",
            "external_mutations": False,
            "evidence_digest": DIGEST,
            "target": {},
            "repo_root": "/tmp/repository",
            "project_id": 1,
            "hostname": "gitlab.example",
            "head_sha": "c",
            "component_target_branch": "main",
            "previous_ref": "v1.0.0",
            "previous_ref_explicit": True,
            "previous_sha": "a",
            "previous_tag": {},
            "revision_range": "a..c",
            "commits": [],
            "merge_requests": [],
            "direct_commits": [],
            "contributors": [],
            "reviewers": [],
            "milestone_candidates": [],
            "work_item_candidates": [],
            "collection_completeness": {
                "component_merge_requests": True,
                "project_milestones": True,
                "work_items": True,
            },
            "errors": [],
            "warnings": [],
            "complete": True,
            "artifact_root": "/tmp/portable-artifacts",
            "prepared_at": CREATED_AT,
            "counts": {
                "commits": 0,
                "merge_requests": 0,
                "direct_commits": 0,
                "contributors": 0,
                "reviewers": 0,
                "milestone_candidates": 0,
                "work_item_candidates": 0,
                "errors": 0,
                "warnings": 0,
            },
        },
    )
    context = envelope(
        "review_context",
        {
            "schema_version": 2,
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
            "release_evidence": {
                "target_branch": "main",
                "target_sha": "b",
                "releases": component(),
                "tags": component(),
                "errors": [],
            },
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
            "incremental": incremental,
            "complete": True,
            "errors": [],
            "artifact_root": "/tmp/portable-artifacts",
            "prepared_at": CREATED_AT,
        },
    )
    publication = envelope(
        "publication_plan",
        {
            "profile": "mr-prepare",
            "target": {},
            "external_mutations": False,
            "evidence_digest": DIGEST,
            "complete": True,
            "markdown": "# Publication plan",
            "plan_name": "mr-publication.md",
            "mr_content": {
                "locale": "en",
                "title": "Clarify the observed behavior",
                "description": "## Context\n\nExplain verified behavior.",
                "change_summary": ["Preserve the purpose and clarify checks."],
                "limitations": [],
                "template": {"id": None, "rationale": "No templates were found."},
                "preservation_notes": ["Retained all verified facts."],
                "label_assessments": [],
                "semver_impact": "none",
                "semver_rationale": "Documentation only.",
            },
            "requests": [],
            "label_review": {
                "complete": True,
                "catalog_sha256": canonical_digest([]),
                "catalog": [],
                "assessments": [],
                "current": [],
                "add": [],
                "remove": [],
                "proposed": [],
                "unresolved": [],
                "semver": {"impact": "none", "candidates": [], "selected": None},
            },
        },
    )
    finding_action_spec = {
        "schema": "code-review/publication-action/v1",
        "preflight_sha256": DIGEST,
        "operation": "create_general",
        "publication": {"id": "finding-1", "revision": 1, "kind": "finding"},
        "body": {"path": "/tmp/portable-artifacts/finding-1.md", "sha256": body_digest},
        "expected": {"thread": None, "note": None, "prior_marker": None, "issue": None},
        "mutation": {"path": None, "line": None, "old_line": None},
    }
    issue_action_spec = {
        "schema": "code-review/publication-action/v1",
        "preflight_sha256": DIGEST,
        "operation": "create_issue",
        "publication": {"id": "issue-1", "revision": 1, "kind": "issue"},
        "body": {"path": "/tmp/portable-artifacts/issue-1.md", "sha256": issue_digest},
        "expected": {"thread": None, "note": None, "prior_marker": None, "issue": None},
        "mutation": {"title": "Track broader schema cleanup"},
    }
    label_action_spec = {
        "schema": "code-review/publication-action/v1",
        "preflight_sha256": DIGEST,
        "operation": "update_labels",
        "publication": None,
        "body": None,
        "expected": {"thread": None, "note": None, "prior_marker": None, "issue": None},
        "mutation": {"add": ["semver::patch"], "remove": [], "proposed": ["semver::patch"]},
    }
    review_plan = envelope(
        "review_plan",
        {
            "profile": "code-review",
            "review_contract_version": 6,
            "external_mutations": False,
            "evidence_digest": DIGEST,
            "context_digest": DIGEST,
            "decision_digest": DIGEST,
            "target": {},
            "role": "reviewer",
            "mode": "deep",
            "locale": "en",
            "incremental": incremental,
            "verdict": "ready",
            "complete": True,
            "summary": "The concrete contract example is valid.",
            "architecture_assessment": "The existing ownership boundary is preserved.",
            "semver_impact": "patch",
            "semver_rationale": "The fix changes behavior without changing the public API.",
            "semver_assessment": release_assessment(),
            "mr_metadata_assessment": {
                "observed": {
                    "title": "Fix schema drift",
                    "description": "Align the producer and schema.",
                    "labels": ["type::bug"],
                    "workflow_state": "merged",
                },
                "assessment": {
                    field: {
                        "status": "ok",
                        "rationale": f"The {field} metadata is sufficient.",
                        "recommendation": None,
                    }
                    for field in ("title", "description", "labels", "workflow_state", "overall")
                },
            },
            "label_review": {
                "complete": True,
                "catalog_sha256": canonical_digest(
                    [{"name": "semver::patch", "description": "Backward-compatible fix"}]
                ),
                "catalog": [{"name": "semver::patch", "description": "Backward-compatible fix"}],
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
                "semver": {
                    "impact": "patch",
                    "candidates": ["semver::patch"],
                    "selected": "semver::patch",
                },
            },
            "publication_preview": {
                "mr_state": "merged",
                "warning": "Actions are prepared but were not executed.",
                "preflight_path": "/tmp/portable-artifacts/preflight.json",
                "preflight_sha256": DIGEST,
                "body_files": [
                    {
                        "publication_id": "finding-1",
                        "revision": 1,
                        "kind": "finding",
                        "path": "/tmp/portable-artifacts/finding-1.md",
                        "sha256": body_digest,
                        "content": body_content,
                    },
                    {
                        "publication_id": "issue-1",
                        "revision": 1,
                        "kind": "issue",
                        "path": "/tmp/portable-artifacts/issue-1.md",
                        "sha256": issue_digest,
                        "content": issue_content,
                    },
                ],
                "actions": [
                    {
                        "id": "finding:finding-1:r1:create_general",
                        "sha256": canonical_digest(finding_action_spec),
                        "kind": "finding",
                        "publication_id": "finding-1",
                        "revision": 1,
                        "operation": "create_general",
                        "command": "glab api --method POST projects/1/merge_requests/1/discussions -F body=@/tmp/portable-artifacts/finding-1.md",
                        "spec": finding_action_spec,
                    },
                    {
                        "id": "issue:issue-1:r1:create_issue",
                        "sha256": canonical_digest(issue_action_spec),
                        "kind": "issue",
                        "publication_id": "issue-1",
                        "revision": 1,
                        "operation": "create_issue",
                        "command": "glab api --method POST projects/1/issues -F description=@/tmp/portable-artifacts/issue-1.md",
                        "spec": issue_action_spec,
                    },
                    {
                        "id": "labels:update",
                        "sha256": canonical_digest(label_action_spec),
                        "kind": "labels",
                        "publication_id": None,
                        "revision": None,
                        "operation": "update_labels",
                        "command": "glab mr update 1 --repo https://gitlab.example/group/project --label semver::patch",
                        "spec": label_action_spec,
                    },
                ],
            },
            "presentation": presentation,
            "chat_assessment": {
                "necessity": {"status": "supported", "rationale": "The defect is confirmed."},
                "relevance": {"status": "current", "rationale": "The exact head is current."},
                "change": "The change fixes the reviewed behavior.",
            },
            "checks": ["task check"],
            "findings": [finding],
            "finding_publications": [
                {
                    "finding_id": "finding-1",
                    "revision": 1,
                    "type": "general",
                    "path": None,
                    "line": None,
                    "old_line": None,
                    "body": "Finding body",
                    "fix_mode": "patch",
                    "patch": patch_content,
                    "patch_path": "/tmp/portable-artifacts/finding-1.patch",
                    "patch_sha256": patch_digest,
                }
            ],
            "previous_finding_assessments": [],
            "recommended_issues": [
                {
                    "id": "issue-1",
                    "revision": 1,
                    "title": "Track broader schema cleanup",
                    "problem": "Related schemas use inconsistent naming.",
                    "risk": "Future consumers can drift.",
                    "evidence": ["shared/schema.json"],
                    "reason_out_of_scope": "The file is not changed by this review.",
                    "minimum_fix": "Align the schemas in a separate change.",
                    "body": "Issue body",
                }
            ],
            "finding_ledger": [
                {
                    "id": "finding-1",
                    "kind": "finding",
                    "status": "active",
                    "revision": 1,
                    "record": {
                        "finding": finding,
                        "publication": {
                            "finding_id": "finding-1",
                            "revision": 1,
                            "type": "general",
                            "path": None,
                            "line": None,
                            "old_line": None,
                            "body": "Finding body",
                            "fix_mode": "patch",
                            "patch": patch_content,
                            "patch_path": "/tmp/portable-artifacts/finding-1.patch",
                            "patch_sha256": patch_digest,
                        },
                    },
                },
                {
                    "id": "issue-1",
                    "kind": "issue",
                    "status": "active",
                    "revision": 1,
                    "record": {
                        "issue": {
                            "id": "issue-1",
                            "revision": 1,
                            "title": "Track broader schema cleanup",
                            "problem": "Related schemas use inconsistent naming.",
                            "risk": "Future consumers can drift.",
                            "evidence": ["shared/schema.json"],
                            "reason_out_of_scope": "The file is not changed by this review.",
                            "minimum_fix": "Align the schemas in a separate change.",
                            "body": "Issue body",
                        }
                    },
                },
            ],
            "publication_ledger": [],
            "rejected_candidates": [
                {
                    "id": "rejected-1",
                    "source": "critic",
                    "finding": rejected_finding,
                    "reason": "The evidence is outside the changed contract.",
                    "paths": ["shared/schema.json"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                }
            ],
            "rejected_candidate_assessments": [],
            "rejected_candidate_ledger": [
                {
                    "id": "rejected-1",
                    "source": "critic",
                    "finding": rejected_finding,
                    "reason": "The evidence is outside the changed contract.",
                    "paths": ["shared/schema.json"],
                    "thread_ids": [],
                    "metadata_fields": [],
                    "ci": False,
                }
            ],
            "thread_decisions": [],
            "markdown": "# Review plan",
        },
    )
    analysis = envelope(
        "analysis_report",
        {
            "schema": "portable-gitlab/analysis-report/v2",
            "evidence_digest": DIGEST,
            "run_id": "analysis-run",
            "session_id": "analysis-session",
            "findings": [finding],
            "external_mutations": False,
        },
    )
    critic = envelope(
        "critic_receipt",
        {
            "schema": "portable-gitlab/critic-receipt/v2",
            "evidence_digest": DIGEST,
            "run_id": "critic-run",
            "session_id": "critic-session",
            "scope_digest": DIGEST,
            "target_finding_ids": [],
            "findings": [finding],
            "external_mutations": False,
        },
    )
    decision = envelope(
        "review_decision",
        {
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
            "ci_job_assessments": [
                {
                    "project_id": 1,
                    "pipeline_id": 2,
                    "job_id": 3,
                    "classification": "process_gate",
                    "rationale": "The trace reports an unmet approval policy.",
                    "trace_evidence": "Approval is required.",
                }
            ],
            "findings": [finding],
            "critic_findings": [rejected_finding],
            "accepted_findings": [finding],
            "critic_target_finding_ids": [],
            "unresolved_threads": [],
            "responses": [
                {"id": "finding-1", "decision": "accept", "reason": "confirmed"},
                {
                    "id": "rejected-1",
                    "decision": "reject",
                    "reason": "outside the changed contract",
                },
            ],
        },
    )
    readiness = envelope(
        "release_readiness",
        {
            "schema": "portable-gitlab/release-readiness/v2",
            "evidence_digest": DIGEST,
            "verdict": "ready",
            "readiness": True,
            "gates": {
                "semver": gate,
                "compatibility": gate,
                "migration": gate,
                "rollback": gate,
                "ci": gate,
            },
            "external_mutations": False,
        },
    )
    finalized = envelope(
        "finalize_report",
        {
            "status": "ok",
            "changed": [],
            "complete": True,
            "evidence_digest": DIGEST,
            "evidence_kind": "evidence_snapshot",
            "evidence_fingerprint_digest": DIGEST,
            "external_mutations": False,
            "head_sha": "c",
        },
    )
    return [
        evidence,
        local,
        inventory,
        context,
        publication,
        review_plan,
        analysis,
        critic,
        decision,
        readiness,
        finalized,
    ]


def test_every_committed_json_schema_uses_a_valid_meta_schema() -> None:
    paths = set(
        subprocess.check_output(
            ["git", "ls-files", "*.schema.json"], cwd=ROOT, text=True
        ).splitlines()
    )
    assert paths == SCHEMA_PATHS
    for path in sorted(paths):
        validator(path)


def validate_eval_contract_instances() -> None:
    scenario_validator = validator("evals/schemas/scenario-v1.schema.json")
    scenarios = sorted((ROOT / "evals/scenarios").glob("*.json"))
    assert len(scenarios) == 206
    for path in scenarios:
        scenario_validator.validate(load(path.relative_to(ROOT)))

    scenario = load("evals/scenarios/golden-goal.en.json")
    args = argparse.Namespace(offline=True, host="offline", model=None)
    result = eval_runner.result_for(scenario, args, ROOT)
    validator("evals/schemas/result-v1.schema.json").validate(result)


def validate_shared_contract_instances() -> None:
    validator("shared/references/team_runtime/team-context.schema.json").validate(
        load("shared/references/team_runtime/team-context.example.json")
    )
    validator("shared/references/work-item-contract.schema.json").validate(cast("Any", work_item()))
    artifact_validator = validator(
        "shared/references/portable_gitlab/artifact-contracts-v2.schema.json"
    )
    instances = artifact_instances()
    assert {instance["kind"] for instance in instances} == {
        "analysis_report",
        "critic_receipt",
        "evidence_snapshot",
        "finalize_report",
        "local_wip_snapshot",
        "publication_plan",
        "release_inventory",
        "release_readiness",
        "review_context",
        "review_decision",
        "review_plan",
    }
    for instance in instances:
        artifact_validator.validate(instance)
        validate_v2_artifact(instance, instance["kind"])


def validate_opencode_contract_instances() -> None:
    instances = load("packages/opencode/contracts/instances-v1.json")
    schema_names = {path.rsplit("/", 1)[-1] for path in SCHEMA_PATHS if "/contracts/" in path}
    assert set(instances) == schema_names
    for name, instance in instances.items():
        validator(f"packages/opencode/contracts/{name}").validate(instance)


def test_every_committed_json_schema_has_a_concrete_contract() -> None:
    validate_eval_contract_instances()
    validate_shared_contract_instances()
    validate_opencode_contract_instances()
    validate_schema_runtime_rejections()


def validate_schema_runtime_rejections() -> None:
    opencode = load("packages/opencode/contracts/instances-v1.json")
    routing_validator = validator("packages/opencode/contracts/routing-receipt-v1.schema.json")
    lowercase_date = copy.deepcopy(opencode["routing-receipt-v1.schema.json"])
    lowercase_date["expires_at"] = "2099-01-01t00:00:00z"
    routing_validator.validate(lowercase_date)
    for change in (
        {"host_inventory_revision": "not-a-digest"},
        {"task_digest": "not-a-digest"},
        {"requirements_digest": "not-a-digest"},
        {"card_digest": "not-a-digest"},
        {"nonce": "too-short"},
        {"expires_at": "January 1, 2099"},
        {"expires_at": "2099-02-30T00:00:00Z"},
        {"unexpected": True},
    ):
        routing = copy.deepcopy(opencode["routing-receipt-v1.schema.json"])
        routing.update(change)
        with pytest.raises(ValidationError):
            routing_validator.validate(routing)

    artifacts = {instance["kind"]: instance for instance in artifact_instances()}
    artifact_validator = validator(
        "shared/references/portable_gitlab/artifact-contracts-v2.schema.json"
    )
    legacy_context = copy.deepcopy(artifacts["review_context"])
    legacy_context["payload"].pop("incremental")
    legacy_context["payload"].pop("issue_templates")
    legacy_context["payload"].pop("current_user_id")
    legacy_context["payload"].pop("release_evidence")
    artifact_validator.validate(legacy_context)
    validate_v2_artifact(legacy_context, "review_context")
    structured_v2 = copy.deepcopy(artifacts["review_plan"])
    structured_v2["payload"]["review_contract_version"] = 2
    structured_v2["payload"].pop("chat_assessment")
    structured_v2["payload"].pop("locale")
    structured_v2["payload"].pop("semver_assessment")
    for publication in structured_v2["payload"]["finding_publications"]:
        for key in ("fix_mode", "patch", "patch_path", "patch_sha256"):
            publication.pop(key)
    for entry in structured_v2["payload"]["finding_ledger"]:
        publication = entry["record"].get("publication")
        if publication is not None:
            for key in ("fix_mode", "patch", "patch_path", "patch_sha256"):
                publication.pop(key)
    artifact_validator.validate(structured_v2)
    validate_v2_artifact(structured_v2, "review_plan")
    fallback_plan = copy.deepcopy(artifacts["review_plan"])
    fallback_plan["payload"]["semver_assessment"] = fallback_assessment()
    artifact_validator.validate(fallback_plan)
    validate_v2_artifact(fallback_plan, "review_plan")
    semver_mutations: list[dict[str, Any]] = [
        {"fallback_reason": ""},
        {"release_impact": "patch"},
        {"sources": []},
    ]
    for mutation in semver_mutations:
        invalid_semver = copy.deepcopy(fallback_plan)
        invalid_semver["payload"]["semver_assessment"].update(mutation)
        with pytest.raises(ValidationError):
            artifact_validator.validate(invalid_semver)
        with pytest.raises(WorkflowError):
            validate_v2_artifact(invalid_semver, "review_plan")
    legacy_plan = copy.deepcopy(artifacts["review_plan"])
    for key in (
        "review_contract_version",
        "incremental",
        "presentation",
        "finding_publications",
        "previous_finding_assessments",
        "recommended_issues",
        "finding_ledger",
        "publication_ledger",
        "rejected_candidates",
        "rejected_candidate_assessments",
        "rejected_candidate_ledger",
        "label_review",
        "chat_assessment",
        "locale",
        "semver_assessment",
    ):
        legacy_plan["payload"].pop(key)
    structured_preview = legacy_plan["payload"]["publication_preview"]
    legacy_plan["payload"]["publication_preview"] = {
        "mr_state": structured_preview["mr_state"],
        "warning": structured_preview["warning"],
        "preflight_command": "glab api --method GET projects/1/merge_requests/1",
        "body_files": [
            {
                "finding_id": item["publication_id"],
                "path": item["path"],
                "sha256": item["sha256"],
                "content": item["content"],
            }
            for item in structured_preview["body_files"]
        ],
        "commands": [
            {"finding_id": item["publication_id"], "command": item["command"]}
            for item in structured_preview["actions"]
            if item["publication_id"] is not None
        ],
    }
    artifact_validator.validate(legacy_plan)
    validate_v2_artifact(legacy_plan, "review_plan")
    minimal_legacy_plan = copy.deepcopy(legacy_plan)
    for key in ("semver_rationale", "mr_metadata_assessment", "publication_preview"):
        minimal_legacy_plan["payload"].pop(key)
    minimal_legacy_plan["payload"]["findings"] = [{"id": "finding-1"}]
    artifact_validator.validate(minimal_legacy_plan)
    validate_v2_artifact(minimal_legacy_plan, "review_plan")
    release_inventory = copy.deepcopy(artifacts["release_inventory"])
    release_inventory["payload"]["counts"] = {}
    review_context = copy.deepcopy(artifacts["review_context"])
    review_context["payload"]["exact_git"] = {}
    review_plan = copy.deepcopy(artifacts["review_plan"])
    review_plan["payload"]["publication_preview"]["body_files"][0]["revision"] = 0
    invalid_nullable = copy.deepcopy(artifacts["review_plan"])
    invalid_nullable["payload"]["finding_publications"][0]["path"] = {}
    invalid_patch = copy.deepcopy(artifacts["review_plan"])
    invalid_patch["payload"]["finding_publications"][0]["patch"] = None
    invalid_ledger_patch = copy.deepcopy(artifacts["review_plan"])
    invalid_ledger_patch["payload"]["finding_ledger"][0]["record"]["publication"]["patch"] = None
    invalid_headers = copy.deepcopy(artifacts["review_plan"])
    invalid_headers["payload"]["presentation"]["previous_table_headers"].append("Extra")
    for kind, instance in (
        ("release_inventory", release_inventory),
        ("review_context", review_context),
        ("review_plan", review_plan),
        ("review_plan", invalid_nullable),
        ("review_plan", invalid_patch),
        ("review_plan", invalid_ledger_patch),
        ("review_plan", invalid_headers),
    ):
        with pytest.raises(ValidationError):
            artifact_validator.validate(instance)
        with pytest.raises(WorkflowError):
            validate_v2_artifact(instance, kind)

    inconsistent_incremental = copy.deepcopy(artifacts["review_context"])
    inconsistent_incremental["payload"]["incremental"]["mode"] = "incremental"
    inconsistent_incremental["payload"]["incremental"]["critic_required"] = True
    artifact_validator.validate(inconsistent_incremental)
    with pytest.raises(WorkflowError):
        validate_v2_artifact(inconsistent_incremental, "review_context")
