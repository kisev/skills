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
from tests.test_work_item_contract import item as work_item

if TYPE_CHECKING:
    from jsonschema.protocols import Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATHS = {
    "evals/schemas/result-v1.schema.json",
    "evals/schemas/scenario-v1.schema.json",
    "packages/agentomatic/contracts/critic-report-v1.schema.json",
    "packages/agentomatic/contracts/execution-card-v1.schema.json",
    "packages/agentomatic/contracts/mapper-report-v1.schema.json",
    "packages/agentomatic/contracts/review-report-v1.schema.json",
    "packages/agentomatic/contracts/routing-receipt-v1.schema.json",
    "packages/agentomatic/contracts/worker-report-v1.schema.json",
    "shared/references/portable_gitlab/artifact-contracts-v2.schema.json",
    "shared/references/post-success-marker.schema.json",
    "shared/references/team_runtime/team-context.schema.json",
    "shared/references/people_runtime/people-context.schema.json",
    "shared/references/work-item-contract.schema.json",
    "skills/taskmatic/references/snapshot.schema.json",
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
    gate = {"status": "passed", "evidence": ["task check"], "range": identity()}
    evidence = envelope(
        "evidence_snapshot",
        {
            "schema_version": 2,
            "profile": "mr-prepare",
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
    return [evidence, inventory, publication, readiness, finalized]


def test_every_committed_json_schema_uses_a_valid_meta_schema() -> None:
    paths = set(
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.schema.json"],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    assert paths == SCHEMA_PATHS
    for path in sorted(paths):
        validator(path)


def validate_eval_contract_instances() -> None:
    scenario_validator = validator("evals/schemas/scenario-v1.schema.json")
    scenarios = sorted((ROOT / "evals/scenarios").glob("*.json"))
    assert len(scenarios) == 276
    for path in scenarios:
        scenario_validator.validate(load(path.relative_to(ROOT)))

    scenario = load("evals/scenarios/golden-goal.en.json")
    args = argparse.Namespace(offline=True, host="offline", model=None)
    result = eval_runner.result_for(scenario, args, ROOT)
    validator("evals/schemas/result-v1.schema.json").validate(result)


def validate_shared_contract_instances() -> None:
    validator("shared/references/post-success-marker.schema.json").validate(
        {
            "schema": "agent-skills/post-success-marker/v1",
            "marker_id": DIGEST,
            "skill": "code-review",
            "action_id": "finding:example:create",
            "binding_digest": DIGEST,
            "mutation_digest": DIGEST,
            "exit_status": 0,
            "succeeded_at": CREATED_AT,
        }
    )
    validator("shared/references/team_runtime/team-context.schema.json").validate(
        load("shared/references/team_runtime/team-context.example.json")
    )
    people_validator = validator("shared/references/people_runtime/people-context.schema.json")
    people_validator.validate(load("shared/references/people_runtime/people-context.example.json"))
    people_validator.validate(
        {
            "schema_version": 1,
            "profile": "minimal-team",
            "reports": [
                {
                    "name": "Minimal Report",
                    "one_on_one": {"frequency": "monthly", "minutes": 45},
                }
            ],
        }
    )
    validator("shared/references/work-item-contract.schema.json").validate(cast("Any", work_item()))
    artifact_validator = validator(
        "shared/references/portable_gitlab/artifact-contracts-v2.schema.json"
    )
    instances = artifact_instances()
    assert {instance["kind"] for instance in instances} == {
        "evidence_snapshot",
        "finalize_report",
        "publication_plan",
        "release_inventory",
        "release_readiness",
    }
    for instance in instances:
        artifact_validator.validate(instance)
        validate_v2_artifact(instance, instance["kind"])


def validate_opencode_contract_instances() -> None:
    instances = load("packages/agentomatic/contracts/instances-v1.json")
    schema_names = {path.rsplit("/", 1)[-1] for path in SCHEMA_PATHS if "/contracts/" in path}
    assert set(instances) == schema_names
    for name, instance in instances.items():
        validator(f"packages/agentomatic/contracts/{name}").validate(instance)


def taskmatic_snapshot_instance() -> dict[str, Any]:
    return cast("dict[str, Any]", load("skills/taskmatic/references/snapshot.example.json"))


def validate_taskmatic_contract_instances() -> None:
    taskmatic_validator = validator("skills/taskmatic/references/snapshot.schema.json")
    instance = taskmatic_snapshot_instance()
    taskmatic_validator.validate(instance)
    assert {card["title"] for card in instance["cards"]} == {
        "Review the snapshot contract",
        "Child card",
    }
    for change in (
        {"schema": "taskmatic/snapshot/v2"},
        {"generated_at": "yesterday"},
        {"cards": [{"id": "nothex"}]},
    ):
        invalid = copy.deepcopy(instance)
        invalid.update(change)
        with pytest.raises(ValidationError):
            taskmatic_validator.validate(invalid)
    bad_card = copy.deepcopy(instance)
    bad_card["cards"][0]["status"] = "archived"
    with pytest.raises(ValidationError):
        taskmatic_validator.validate(bad_card)
    bad_claim = copy.deepcopy(instance)
    bad_claim["cards"][0]["claim_remaining_seconds"] = -1
    with pytest.raises(ValidationError):
        taskmatic_validator.validate(bad_claim)


def test_every_committed_json_schema_has_a_concrete_contract() -> None:
    validate_eval_contract_instances()
    validate_shared_contract_instances()
    validate_opencode_contract_instances()
    validate_taskmatic_contract_instances()
    validate_schema_runtime_rejections()


def validate_schema_runtime_rejections() -> None:
    opencode = load("packages/agentomatic/contracts/instances-v1.json")
    routing_validator = validator("packages/agentomatic/contracts/routing-receipt-v1.schema.json")
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
    with pytest.raises(ValidationError):
        artifact_validator.validate(release_inventory)
    with pytest.raises(WorkflowError):
        validate_v2_artifact(release_inventory, "release_inventory")
