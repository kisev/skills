from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import FormatChecker, ValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for

from scripts import eval_runner
from shared.references.portable_gitlab.contract import WorkflowError, validate_v2_artifact
from tests.test_work_item_contract import item as work_item

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
            "errors": [],
            "warnings": [],
            "complete": True,
            "artifact_root": "/tmp/portable-artifacts",
            "prepared_at": CREATED_AT,
            "counts": {
                "commits": 0,
                "merge_requests": 0,
                "direct_commits": 0,
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
            "current_user_username": "reviewer",
            "mr_author_username": "author",
            "discussions": [],
            "notes": [],
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
            "plan_name": "publication",
        },
    )
    review_plan = envelope(
        "review_plan",
        {
            "profile": "code-review",
            "external_mutations": False,
            "evidence_digest": DIGEST,
            "context_digest": DIGEST,
            "decision_digest": DIGEST,
            "target": {},
            "role": "reviewer",
            "mode": "deep",
            "verdict": "ready",
            "complete": True,
            "summary": "The concrete contract example is valid.",
            "architecture_assessment": "The existing ownership boundary is preserved.",
            "semver_impact": "patch",
            "checks": ["task check"],
            "findings": [finding],
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
            "mode": "deep",
            "external_mutations": False,
            "run_id": "review-run",
            "session_id": "review-session",
            "verdict": "ready",
            "low_risk": True,
            "blocking_findings": False,
            "findings": [finding],
            "unresolved_threads": [],
            "responses": [{"id": "finding-1", "decision": "accept", "reason": "confirmed"}],
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
    assert len(scenarios) == 226
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
    validator("shared/references/work-item-contract.schema.json").validate(cast(Any, work_item()))
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
    release_inventory = copy.deepcopy(artifacts["release_inventory"])
    release_inventory["payload"]["counts"] = {}
    review_context = copy.deepcopy(artifacts["review_context"])
    review_context["payload"]["exact_git"] = {}
    for kind, instance in (
        ("release_inventory", release_inventory),
        ("review_context", review_context),
    ):
        with pytest.raises(ValidationError):
            artifact_validator.validate(instance)
        with pytest.raises(WorkflowError):
            validate_v2_artifact(instance, kind)
