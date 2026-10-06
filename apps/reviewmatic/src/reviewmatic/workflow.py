"""Review-owned command orchestration; the shared runtime supplies primitives."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from reviewmatic import context, run_panel, tail
from reviewmatic import draft as draft_module

if TYPE_CHECKING:
    import argparse

from reviewmatic.portable.portable_gitlab import contract as portable

# replace-artifact contract: CLI kind -> (artifact store kind, progress prefix,
# the stage that owns the artifact, downstream progress prefixes to clear).
REPLACEMENT_KINDS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "context": (
        "review_context",
        "context",
        "context_ready",
        ("critic_receipt", "finalize_report", "decision", "plan"),
    ),
    "critic_receipt": (
        "critic_receipt",
        "critic_receipt",
        "finalize_missing",
        ("finalize_report", "decision", "plan"),
    ),
    "finalize_report": (
        "finalize_report",
        "finalize_report",
        "decision_missing",
        ("decision", "plan"),
    ),
    "decision": ("review_decision", "decision", "content_missing", ("plan",)),
}


def prepared(args: argparse.Namespace, bundle: dict[str, Any]) -> dict[str, Any]:
    root = portable.artifact_root(Path(str(bundle["artifact_root"])))
    context.begin_review(
        bundle["preview_artifact_path"],
        bundle["preview_digest"],
        bundle["artifact_root"],
        args.repo_root,
        args.review_mode,
        args.locale,
        args.incremental,
    )
    # A fresh run starts a new review cycle: the per-cycle run panel from any
    # previous cycle is invalidated, so the poll is asked and answered anew
    # and no older receipt is silently rebound.
    run_panel.panel_path(root).unlink(missing_ok=True)
    return {
        "stage": "prepared",
        "next_action": context.runner_action(
            "context",
            "--evidence",
            bundle["preview_artifact_path"],
            "--repo-root",
            str(Path(args.repo_root).resolve()) if args.repo_root is not None else "<checkout>",
            "--incremental",
            args.incremental,
            "--review-mode",
            args.review_mode,
            "--locale",
            args.locale,
            required_inputs=("repo_root",) if args.repo_root is None else (),
        ),
    }


def selected(root: Path, stages: set[str]) -> dict[str, Any]:
    status = context.review_status(str(root))
    stage = status.get("resume_stage") or status.get("stage")
    progress = context.load_progress(root)
    if stage not in stages or progress is None:
        raise portable.WorkflowError(f"review command is out of order; current stage is {stage}")
    return progress


def replace_artifact(args: argparse.Namespace) -> dict[str, Any]:
    """Validate one replacement artifact, rebind it, and rewind the stage.

    The replaced artifact stays in the content-addressed store; only the
    progress pointer moves, and every artifact derived from the replaced one
    is cleared so the machine never mixes old and new decisions.
    """
    kind = str(args.kind)
    dir_kind, prefix, target_stage, downstream = REPLACEMENT_KINDS[kind]
    root = portable.artifact_root(Path(args.artifact_root))
    progress = context.load_progress(root)
    if progress is None:
        raise portable.WorkflowError("replace-artifact requires existing review progress")
    if progress.get(f"{prefix}_path") is None:
        raise portable.WorkflowError(f"no bound {kind.replace('_', ' ')} artifact to replace")
    evidence_path, evidence = context.review_evidence_from_root(root)
    evidence_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    replacement = portable.regular_file(Path(args.path), f"replacement {kind.replace('_', ' ')}")
    value = portable.read_json(replacement, f"replacement {kind.replace('_', ' ')}")
    _validate_replacement(
        kind, value, replacement, root, progress, evidence_path, evidence, evidence_digest
    )
    path, digest = portable.write_artifact(root, dir_kind, value)
    changes: dict[str, Any] = {f"{prefix}_path": str(path), f"{prefix}_digest": digest}
    for item in downstream:
        changes[f"{item}_path"] = None
        changes[f"{item}_digest"] = None
    context.advance_progress(root, target_stage, **changes)
    return {
        "status": "ok",
        "kind": kind,
        "artifact_path": str(path),
        "digest": digest,
        "previous_digest": progress.get(f"{prefix}_digest"),
        "stage": target_stage,
        "cleared": sorted(f"{item}_*" for item in downstream),
        "external_mutations": False,
    }


def _validate_replacement(
    kind: str,
    value: dict[str, Any],
    replacement: Path,
    root: Path,
    progress: dict[str, Any],
    evidence_path: Path,
    evidence: dict[str, Any],
    evidence_digest: str,
) -> None:
    if kind == "context":
        if (
            value.get("evidence_digest") != evidence_digest
            or value.get("target") != evidence.get("target")
            or value.get("complete") is not True
        ):
            raise portable.WorkflowError(
                "replacement review context does not bind the current evidence or is incomplete"
            )
        return
    if kind == "critic_receipt":
        context_artifact = context.progress_artifact(root, progress, "context", "review_context")
        if context_artifact is None or progress.get("mode") not in context.REVIEW_MODES:
            raise portable.WorkflowError(
                "critic receipt replacement requires the selected review context and mode"
            )
        scope = (
            cast("dict[str, Any]", context_artifact[1]["incremental"])["incremental_delta_digest"]
            if progress["mode"] == "incremental"
            else None
        )
        portable.validate_critic(value, evidence_digest, scope)
        if not portable.detailed_findings_are_valid(value.get("findings")):
            raise portable.WorkflowError("critic findings require complete structured evidence")
        return
    if kind == "finalize_report":
        portable.validate_finalize_report(replacement, evidence_path, evidence)
        return
    _validate_decision_replacement(value, root, progress, evidence, evidence_digest)


def _validate_decision_replacement(
    value: dict[str, Any],
    root: Path,
    progress: dict[str, Any],
    evidence: dict[str, Any],
    evidence_digest: str,
) -> None:
    context_artifact = context.progress_artifact(root, progress, "context", "review_context")
    finalize_artifact = context.progress_artifact(
        root, progress, "finalize_report", "finalize_report"
    )
    if context_artifact is None or finalize_artifact is None:
        raise portable.WorkflowError(
            "decision replacement requires the bound context and finalize report"
        )
    _, _, context_digest = context_artifact
    _, _, finalize_digest = finalize_artifact
    critic_artifact = context.progress_artifact(root, progress, "critic_receipt", "critic_receipt")
    receipt = critic_artifact[1] if critic_artifact is not None else None
    critic_digest = critic_artifact[2] if critic_artifact is not None else None
    mode = progress.get("mode")
    if not isinstance(mode, str):
        raise portable.WorkflowError("decision replacement requires the selected review mode")
    if (
        value.get("schema") != "portable-gitlab/review-decision/v2"
        or value.get("evidence_digest") != evidence_digest
        or value.get("context_digest") != context_digest
        or value.get("finalize_digest") != finalize_digest
        or value.get("critic_receipt_digest") != critic_digest
        or value.get("mode") != mode
    ):
        raise portable.WorkflowError("replacement decision does not bind the current review state")
    portable.validate_decision(value, evidence_digest, receipt, mode, context_digest, critic_digest)
    if value.get("finalize_digest") != finalize_digest:
        raise portable.WorkflowError("review decision does not bind exact finalize report")
    if not portable.detailed_findings_are_valid(value.get("findings")):
        raise portable.WorkflowError("review findings require complete structured evidence")
    critic_findings = receipt["findings"] if receipt else []
    candidates = [*value["findings"], *critic_findings]
    ids = [item["id"] for item in candidates]
    if len(ids) != len(set(ids)) or any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(item)) is None for item in ids
    ):
        raise portable.WorkflowError("primary and critic finding IDs must be unique")
    responses = {item["id"]: item for item in value["responses"]}
    if any(item["id"] not in responses for item in candidates):
        raise portable.WorkflowError("every finding requires one response decision")
    accepted = [item for item in candidates if responses[item["id"]]["decision"] == "accept"]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    accepted.sort(key=lambda item: order[item["severity"]])
    context.validate_review_verdict(value, accepted, evidence)
    if not evidence.get("retrieval_complete") or (
        value.get("verdict") == "ready" and value.get("blocking_findings")
    ):
        raise portable.WorkflowError(
            "incomplete evidence or unresolved blocking findings prohibit ready"
        )


def finalize(root_value: str) -> dict[str, Any]:
    root = portable.artifact_root(Path(root_value))
    progress = selected(root, {"context_ready", "finalize_missing"})
    result = portable.finalize(root_value, "review-evidence.json")
    evidence_path, evidence = portable.evidence_from_root(root, "review-evidence.json")
    result = portable.finalize_payload(result, evidence_path, evidence, "evidence_snapshot")
    path, digest = portable.write_artifact(root, "finalize_report", result)
    response: dict[str, Any] = {
        "status": result["status"],
        "result": result,
        "artifact_path": str(path),
        "digest": digest,
        "external_mutations": False,
    }
    if result["status"] == "ok":
        context.advance_progress(
            root,
            "decision_missing",
            expected_stages={"context_ready", "finalize_missing"},
            expected={
                key: progress[key]
                for key in (
                    "evidence_path",
                    "evidence_digest",
                    "context_path",
                    "context_digest",
                    "critic_receipt_path",
                    "critic_receipt_digest",
                )
            },
            finalize_report_path=str(path),
            finalize_report_digest=digest,
            decision_path=None,
            decision_digest=None,
            plan_path=None,
            plan_digest=None,
        )
        response.update(
            stage="decision_missing",
            next_action=context.runner_action(
                "template-review", "--artifact-root", str(root), "--kind", "decision"
            ),
        )
    return response


def record(args: argparse.Namespace) -> dict[str, Any]:
    evidence_doc, evidence = portable.artifact_payload(Path(args.evidence), "evidence_snapshot")
    evidence_digest = portable.digest(evidence_doc)
    root = portable.artifact_root(Path(evidence["artifact_root"]))
    value = portable.read_json(Path(args.input), "artifact input")
    if args.kind != "critic_receipt":
        if args.kind == "release_readiness":
            portable.validate_release_readiness(value, evidence, evidence_digest)
        elif (
            value.get("schema") != "portable-gitlab/analysis-report/v2"
            or value.get("evidence_digest") != evidence_digest
        ):
            raise portable.WorkflowError("analysis report does not bind evidence")
        if args.kind == "analysis_report" and not portable.detailed_findings_are_valid(
            value.get("findings")
        ):
            raise portable.WorkflowError(
                "new code review findings require complete structured evidence"
            )
    else:
        progress = selected(root, {"critic_missing"})
        if str(Path(args.evidence).resolve()) != progress["evidence_path"]:
            raise portable.WorkflowError("critic receipt does not bind selected evidence")
        artifact = context.progress_artifact(root, progress, "context", "review_context")
        if artifact is None:
            raise portable.WorkflowError("critic receipt requires the selected review context")
        scope = (
            artifact[1]["incremental"]["incremental_delta_digest"]
            if progress["mode"] == "incremental"
            else None
        )
        portable.validate_critic(value, evidence_digest, scope)
        if not portable.detailed_findings_are_valid(value.get("findings")):
            raise portable.WorkflowError("critic findings require complete structured evidence")
    path, digest = portable.write_artifact(root, args.kind, value)
    response: dict[str, Any] = {
        "status": "ok",
        "artifact_path": str(path),
        "digest": digest,
        "external_mutations": False,
    }
    if args.kind == "critic_receipt":
        bind_critic_receipt(root, progress, path, digest)
        response.update(
            stage="finalize_missing",
            next_action=context.runner_action("finalize", "--artifact-root", str(root)),
        )
    return response


def bind_critic_receipt(root: Path, progress: dict[str, Any], path: Path, digest: str) -> None:
    """Bind a recorded critic receipt and advance the state machine one stage."""
    context.advance_progress(
        root,
        "finalize_missing",
        expected_stages={"context_ready"},
        expected={
            key: progress[key]
            for key in ("evidence_path", "evidence_digest", "context_path", "context_digest")
        },
        critic_receipt_path=str(path),
        critic_receipt_digest=digest,
        finalize_report_path=None,
        finalize_report_digest=None,
        decision_path=None,
        decision_digest=None,
        plan_path=None,
        plan_digest=None,
    )


def record_run_critic(args: argparse.Namespace) -> dict[str, Any]:
    """Import one run-panel model critic receipt; finish the panel when complete."""
    root = portable.artifact_root(Path(args.artifact_root))
    progress = selected(root, {"critic_missing"})
    panel = run_panel.load(root)
    if panel is None:
        raise portable.WorkflowError(
            "the run panel is not recorded; answer the panel poll and pass the selection "
            "to reviewmatic run --participants"
        )
    receipt = portable.read_json(
        portable.regular_file(Path(args.input), "critic receipt"), "critic receipt"
    )
    context_artifact = context.progress_artifact(root, progress, "context", "review_context")
    if context_artifact is None:
        raise portable.WorkflowError("the run panel requires the selected review context")
    scope = (
        context_artifact[1]["incremental"]["incremental_delta_digest"]
        if progress["mode"] == "incremental"
        else None
    )
    panel = run_panel.bind_receipt(
        root,
        panel,
        str(args.participant),
        receipt,
        str(progress["evidence_digest"]),
        scope,
    )
    pending = run_panel.pending_critics(panel)
    if not pending:
        return complete_run_panel(str(root))
    participant = str(pending[0]["name"])
    template_path = run_panel.critic_template(
        root,
        context_artifact[1],
        str(progress["mode"]),
        str(progress["context_digest"]),
        participant,
    )
    return {
        "status": "ok",
        "stage": "critic_missing",
        "artifact_root": str(root),
        "participant": str(args.participant),
        "panel": run_panel.summary(panel),
        "next_action": context.runner_action(
            "record-run-critic",
            "--artifact-root",
            str(root),
            "--input",
            str(template_path),
            "--participant",
            participant,
        ),
        "external_mutations": False,
    }


def complete_run_panel(root_value: str) -> dict[str, Any]:
    """Merge the complete run panel into one aggregate critic receipt and bind it."""
    root = portable.artifact_root(Path(root_value))
    progress = selected(root, {"critic_missing"})
    panel = run_panel.load(root)
    if panel is None:
        raise portable.WorkflowError(
            "the run panel is not recorded; answer the panel poll and pass the selection "
            "to reviewmatic run --participants"
        )
    pending = run_panel.pending_critics(panel)
    if pending:
        raise portable.WorkflowError(
            "the run panel is still waiting for " + ", ".join(str(item["name"]) for item in pending)
        )
    context_artifact = context.progress_artifact(root, progress, "context", "review_context")
    if context_artifact is None:
        raise portable.WorkflowError("the run panel requires the selected review context")
    scope = (
        context_artifact[1]["incremental"]["incremental_delta_digest"]
        if progress["mode"] == "incremental"
        else None
    )
    merged = run_panel.aggregate(panel, str(progress["evidence_digest"]), scope)
    path, digest = portable.write_artifact(root, "critic_receipt", merged)
    bind_critic_receipt(root, progress, path, digest)
    return {
        "status": "ok",
        "stage": "finalize_missing",
        "artifact_path": str(path),
        "digest": digest,
        "panel": run_panel.summary(panel),
        "next_action": context.runner_action("finalize", "--artifact-root", str(root)),
        "external_mutations": False,
    }


def decide(args: argparse.Namespace) -> dict[str, Any]:
    evidence_doc, evidence = portable.artifact_payload(Path(args.evidence), "evidence_snapshot")
    evidence_digest = portable.digest(evidence_doc)
    root = portable.artifact_root(Path(evidence["artifact_root"]))
    progress = selected(root, {"decision_missing"})
    if (
        any(
            (str(Path(actual).resolve()) if actual is not None else None) != progress[key]
            for actual, key in (
                (args.evidence, "evidence_path"),
                (args.context, "context_path"),
                (args.finalize_report, "finalize_report_path"),
                (args.critic_receipt, "critic_receipt_path"),
            )
        )
        or args.mode != progress["mode"]
    ):
        raise portable.WorkflowError(
            "finalize-review arguments do not match the selected review progress"
        )
    current = portable.collect(evidence["target"], "code-review", persist=False)
    if not current.get("retrieval_complete") or portable.fingerprint(
        evidence
    ) != portable.fingerprint(current):
        raise portable.WorkflowError("evidence is stale or incomplete at final review")
    _, selected_context, context_digest = context.validate_context_binding(
        args.context, args.evidence
    )
    fresh_context = context.refresh_context(selected_context, args.evidence)
    if (
        selected_context.get("complete") is not True
        or fresh_context.get("complete") is not True
        or not context.contexts_match(selected_context, fresh_context)
    ):
        raise portable.WorkflowError("review context is stale or incomplete at final review")
    _, finalize_digest = portable.validate_finalize_report(
        Path(args.finalize_report), Path(args.evidence), evidence
    )
    report = portable.read_json(Path(args.report), "review decision")
    # Authoring-only intent never enters the stored v2 decision artifact.
    publication_intents = report.pop("publication_intents", [])
    if not isinstance(publication_intents, list) or any(
        not isinstance(row, dict) for row in publication_intents
    ):
        raise portable.WorkflowError(
            "publication_intents must be an array of semantic publication choices"
        )
    for index, intent in enumerate(publication_intents):
        if not portable.nonempty_string(intent.get("finding_id")) or set(intent) - {
            "finding_id",
            "publication",
            "dependencies",
        }:
            raise portable.WorkflowError(
                f"$.publication_intents[{index}] needs finding_id, publication, and optional dependencies; no positions or stamps"
            )
        publication_schema = cast("dict[str, Any]", draft_module._DISPOSITION["properties"])[
            "publication"
        ]
        issues = draft_module.schema_issues(
            publication_schema,
            intent.get("publication"),
            f"$.publication_intents[{index}].publication",
        )
        if issues:
            raise portable.WorkflowError(
                "; ".join(f"{issue['path']}: {issue['message']}" for issue in issues)
            )
        if "dependencies" in intent:
            issues = draft_module.schema_issues(
                draft_module._DEPENDENCIES,
                intent["dependencies"],
                f"$.publication_intents[{index}].dependencies",
            )
            if issues:
                raise portable.WorkflowError(
                    "; ".join(f"{issue['path']}: {issue['message']}" for issue in issues)
                )
    receipt = None
    receipt_digest = None
    if args.critic_receipt:
        _, receipt, receipt_digest = context.content_addressed_artifact(
            args.critic_receipt, root, "critic_receipt"
        )
        scope = (
            selected_context["incremental"]["incremental_delta_digest"]
            if args.mode == "incremental"
            else None
        )
        portable.validate_critic(receipt, evidence_digest, scope)
        if not portable.detailed_findings_are_valid(receipt.get("findings")):
            raise portable.WorkflowError("critic findings require complete structured evidence")
        if receipt["run_id"] == report.get("run_id") or receipt["session_id"] == report.get(
            "session_id"
        ):
            raise portable.WorkflowError("critic receipt is not independent of the primary review")
    if not portable.detailed_findings_are_valid(report.get("findings")):
        raise portable.WorkflowError("review findings require complete structured evidence")
    portable.validate_decision(
        report, evidence_digest, receipt, args.mode, context_digest, receipt_digest
    )
    if report["finalize_digest"] != finalize_digest:
        raise portable.WorkflowError("review decision does not bind exact finalize report")
    if not evidence.get("retrieval_complete") or (
        report.get("verdict") == "ready" and report.get("blocking_findings")
    ):
        raise portable.WorkflowError(
            "incomplete evidence or unresolved blocking findings prohibit ready"
        )
    critic_findings = receipt["findings"] if receipt else []
    candidates = [*report["findings"], *critic_findings]
    ids = [item["id"] for item in candidates]
    if len(ids) != len(set(ids)) or any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(item)) is None for item in ids
    ):
        raise portable.WorkflowError("primary and critic finding IDs must be unique")
    responses = {item["id"]: item for item in report["responses"]}
    accepted = [item for item in candidates if responses[item["id"]]["decision"] == "accept"]
    if {str(row["finding_id"]) for row in publication_intents} - set(ids):
        raise portable.WorkflowError(
            "publication_intents must refer to known primary or critic finding ids"
        )
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    accepted.sort(key=lambda item: order[item["severity"]])
    context.validate_review_verdict(report, accepted, evidence)
    payload = {
        **report,
        "critic_findings": critic_findings,
        "accepted_findings": accepted,
        "critic_target_finding_ids": receipt.get("target_finding_ids", []) if receipt else [],
    }
    path, digest = portable.write_artifact(root, "review_decision", payload)
    context.advance_progress(
        root,
        "content_missing",
        expected_stages={"decision_missing"},
        expected={
            key: progress[key]
            for key in (
                "evidence_path",
                "evidence_digest",
                "context_path",
                "context_digest",
                "critic_receipt_path",
                "critic_receipt_digest",
                "finalize_report_path",
                "finalize_report_digest",
            )
        },
        decision_path=str(path),
        decision_digest=digest,
        plan_path=None,
        plan_digest=None,
    )
    tail.remember_intents(root, digest, publication_intents)
    return {
        "status": "ok",
        "artifact_path": str(path),
        "digest": digest,
        "external_mutations": False,
        "stage": "content_missing",
        "next_action": context.runner_action(
            "template-review", "--artifact-root", str(root), "--kind", "content"
        ),
    }


def dispatch(args: argparse.Namespace) -> int | None:
    result: dict[str, Any]
    if args.command == "context":
        result = context.prepare_context(
            args.evidence, args.repo_root, args.incremental, args.review_mode, args.locale
        )
    elif args.command in {"status", "next"}:
        result = context.review_status(args.artifact_root)
        portable.emit(result)
        return 0
    elif args.command == "template-review":
        result = context.template_review(args.artifact_root, args.kind)
    elif args.command == "report-review":
        result = context.report_review(args.artifact_root)
        portable.emit(result)
        return 0 if result["status"] == "ok" else 4
    elif args.command == "finalize":
        result = finalize(args.artifact_root)
    elif args.command == "record-artifact":
        result = record(args)
    elif args.command == "finalize-review":
        result = decide(args)
    elif args.command == "scaffold-review":
        _, evidence = portable.artifact_payload(Path(args.evidence), "evidence_snapshot")
        progress = selected(
            portable.artifact_root(Path(evidence["artifact_root"])), {"content_missing"}
        )
        if any(
            str(Path(actual).resolve()) != progress[key]
            for actual, key in (
                (args.evidence, "evidence_path"),
                (args.context, "context_path"),
                (args.decision, "decision_path"),
            )
        ):
            raise portable.WorkflowError(
                "scaffold-review arguments do not match the selected review progress"
            )
        result = context.scaffold_review(args.evidence, args.context, args.decision, args.content)
    else:
        return None
    portable.emit(result)
    return 0 if result.get("status", "ok") == "ok" else 2
