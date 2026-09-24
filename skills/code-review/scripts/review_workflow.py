"""Review-owned command orchestration; the shared runtime supplies primitives."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import review_context as context

if TYPE_CHECKING:
    import argparse

    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable


def prepared(args: argparse.Namespace, bundle: dict[str, Any]) -> dict[str, Any]:
    context.begin_review(
        bundle["preview_artifact_path"],
        bundle["preview_digest"],
        bundle["artifact_root"],
        args.repo_root,
        args.review_mode,
        args.locale,
        args.incremental,
    )
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
        response.update(
            stage="finalize_missing",
            next_action=context.runner_action("finalize", "--artifact-root", str(root)),
        )
    return response


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
