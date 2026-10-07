"""The OpenCodeReview (``ocr``) CLI as a mechanical panel critic.

OCR is one more findings provider: reviewmatic renders the recorded context
package as a Markdown background file, invokes ``ocr review --format json``
against the exact reviewed range, and maps the comments into a critic receipt
with real OCR run identity. The arbitrator verdicts OCR findings exactly like
model critic findings; OCR never answers critic-assigned questions.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import TYPE_CHECKING, Any, cast

from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from pathlib import Path

OCR_TIMEOUT_SECONDS = 300
OCR_SEVERITIES = {"critical", "high", "medium", "low"}
# The external ocr CLI rejects background files above this size; the runtime
# refuses before spawning so the panel never depends on the CLI's own error.
OCR_BACKGROUND_LIMIT = 8000

_LOCAL_SEVERITY_BLOCKING = {"critical", "high"}


# The engine of one selected critic: "ocr" when explicitly selected, "model"
# otherwise, so the existing selections stay model critics without a migration.
def critic_engine(critic: dict[str, Any]) -> str:
    return "ocr" if critic.get("engine") == "ocr" else "model"


def ocr_critics(critics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [critic for critic in critics if critic_engine(critic) == "ocr"]


# Applies the record-participants OCR configuration flags to the selected OCR
# critics. Returns addressed errors when the flags name no OCR critic.
def stamp_ocr_configuration(
    critics: list[dict[str, Any]], provider: str | None, model: str | None
) -> list[dict[str, str]]:
    selected = ocr_critics(critics)
    if provider is None and model is None:
        return []
    if not selected:
        return [
            {
                "path": "$.critics",
                "message": (
                    '--ocr-provider/--ocr-model apply to engine:"ocr" critics, but the '
                    "selection contains none"
                ),
            }
        ]
    for critic in selected:
        if provider is not None:
            critic["provider"] = provider
        if model is not None:
            critic["model"] = model
    return []


def safe_id_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", value).strip("-")
    return cleaned[:40] if cleaned else "root"


def _comment_location(comment: dict[str, Any]) -> str:
    path = str(comment.get("path") or "")
    start = comment.get("start_line")
    end = comment.get("end_line")
    if not isinstance(start, int) or not isinstance(end, int) or start <= 0 or end < start:
        return path
    return f"{path}:{start}-{end}"


# Previously reported findings an incremental OCR critic must re-report on:
# exactly the findings whose previous publication positions or patch text
# reference a path from the incremental delta. Findings without a delta
# intersection stay with the arbitrator's previous-finding assessments and are
# not re-targeted at the critic; this boundary is the documented coverage rule.
def delta_scoped_previous_findings(incremental: dict[str, Any]) -> list[dict[str, Any]]:
    delta = incremental.get("incremental_delta") if isinstance(incremental, dict) else None
    changed = (
        {str(path) for path in cast("list[object]", delta.get("changed_paths") or [])}
        if isinstance(delta, dict)
        else set()
    )
    history = incremental.get("history_context") or {}
    findings = history.get("findings", incremental.get("previous_findings"))
    publications = history.get("publications", incremental.get("previous_finding_publications"))
    by_id = {
        str(item.get("finding_id")): item
        for item in cast("list[object]", publications or [])
        if isinstance(item, dict)
    }
    scoped: list[dict[str, Any]] = []
    for finding in cast("list[object]", findings or []):
        if not isinstance(finding, dict):
            continue
        publication = by_id.get(str(finding.get("id")))
        if publication is None:
            continue
        path = str(publication.get("path") or "")
        patch = str(publication.get("patch") or "")
        if (path and path in changed) or any(item in patch for item in changed):
            scoped.append(finding)
    return scoped


# Renders the recorded context package as the Markdown background file passed
# to ``ocr review --background-file``. Purely derived from the package payload
# (and the explicit previous-findings section for incremental reviews) so a
# re-render of the same inputs is byte-identical.
def render_ocr_background(
    payload: dict[str, Any],
    directory: Path,
    package_digest: str,
    *,
    previous_findings: list[dict[str, Any]] | None = None,
) -> Path:
    lines: list[str] = ["# Review background", ""]
    goal = payload.get("goal")
    lines.append("## Goal")
    lines.append("")
    if isinstance(goal, dict) and isinstance(goal.get("text"), str) and goal["text"]:
        lines.append(str(goal["text"]))
    else:
        lines.append("Unknown: the author did not record a review goal for this change.")
    lines.append("")

    criteria = payload.get("acceptance_criteria")
    lines.append("## Acceptance criteria")
    lines.append("")
    items = criteria.get("items") if isinstance(criteria, dict) else None
    if isinstance(items, list) and items:
        lines.extend(f"- {item}" for item in items if isinstance(item, str) and item)
    else:
        lines.append("- Unknown: no acceptance criteria were recorded.")
    lines.append("")

    claims = payload.get("claims")
    if isinstance(claims, list) and claims:
        lines.append("## Claims")
        lines.append("")
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            prefix = str(claim.get("kind") or "claim")
            sources = ", ".join(str(source) for source in claim.get("sources") or [])
            lines.append(f"- [{prefix}] {claim.get('statement')} (sources: {sources})")
        lines.append("")

    constraints = payload.get("constraints")
    if isinstance(constraints, list) and constraints:
        lines.append("## Constraints")
        lines.append("")
        lines.extend(f"- {item}" for item in constraints if isinstance(item, str) and item)
        lines.append("")

    decisions = payload.get("prior_decisions")
    if isinstance(decisions, list) and decisions:
        lines.append("## Prior decisions")
        lines.append("")
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            source = str(decision.get("source") or "")
            suffix = f" (source: {source})" if source else ""
            lines.append(f"- {decision.get('decision')}{suffix}")
        lines.append("")

    questions = payload.get("questions")
    if isinstance(questions, list) and questions:
        lines.append("## Open questions")
        lines.append("")
        for question in questions:
            if not isinstance(question, dict):
                continue
            assigned = "; assigned to critics" if question.get("critic") is True else ""
            lines.append(f"- {question.get('id')}: {question.get('subject')}{assigned}")
        lines.append("")

    threads = payload.get("thread_registry")
    if isinstance(threads, list) and threads:
        lines.append("## Discussion threads")
        lines.append("")
        for thread in threads:
            if not isinstance(thread, dict):
                continue
            lines.append(
                f"- #{thread.get('id')} ({thread.get('state')}): {thread.get('summary')} "
                f"Relevance: {thread.get('review_relevance')}"
            )
        lines.append("")

    background = payload.get("background")
    if isinstance(background, str) and background.strip():
        lines.append("## Task narrative")
        lines.append("")
        lines.append(background)
        lines.append("")

    if previous_findings:
        lines.append("## Previously reported findings")
        lines.append("")
        lines.append(
            "These findings are advisory context from a previous snapshot, not required "
            "runbook entries. Report every currently observed problem even if it appeared "
            "before; do not copy historical IDs or infer that an old verdict remains true."
        )
        lines.append("")

        for finding in previous_findings:
            if not isinstance(finding, dict):
                continue
            lines.append(
                f"- {finding.get('id')} ({finding.get('severity')}): {finding.get('summary')}"
            )
        lines.append("")

    history = payload.get("history_context")
    if isinstance(history, dict):
        lines.extend(
            [
                "## Advisory review history",
                "",
                (
                    "Previous snapshot, findings, reasons, and decisions are consultation only. "
                    "Do not synchronize ledgers, identities, revisions, or publications."
                ),
                "",
                "```json",
                json.dumps(history, ensure_ascii=False, sort_keys=True, indent=2),
                "```",
                "",
            ]
        )

    identity = package_digest[:16] + (
        f"-{contract.digest(previous_findings)[:16]}" if previous_findings else ""
    )

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"ocr-background-{identity}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _parse_output(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise contract.WorkflowError(
            f"the ocr CLI did not return valid JSON on stdout ({error})"
        ) from error
    if not isinstance(value, dict):
        raise contract.WorkflowError("the ocr CLI JSON output must be an object")
    return value


# Runs one OCR review and returns the parsed JSON output document. ``base`` and
# ``head`` select the committed range mode; passing both as None reviews the
# working-tree workspace (staged, unstaged, and untracked local changes).
def invoke_ocr_critic(
    background: Path,
    base: str | None,
    head: str | None,
    provider: str | None,
    model: str | None,
    *,
    repo: str,
    timeout: int = OCR_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if (base is None) != (head is None):
        raise contract.WorkflowError(
            "the OCR critic needs both --from and --to revisions, or neither for workspace mode"
        )
    # Preflight: refuse an oversized background before spawning the CLI.
    size = background.stat().st_size if background.exists() else len(background.read_bytes())
    if size > OCR_BACKGROUND_LIMIT:
        raise contract.WorkflowError(
            f"the OCR background is {size} bytes, above the ocr CLI limit of "
            f"{OCR_BACKGROUND_LIMIT}; run the panel without OCR critics"
        )
    command = [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
        "--color",
        "never",
        "--repo",
        repo,
        "--background-file",
        str(background),
    ]
    if base is not None and head is not None:
        command.extend(("--from", base, "--to", head))
    if provider:
        command.extend(("--provider", provider))
    if model:
        command.extend(("--model", model))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise contract.WorkflowError(
            "the ocr CLI is not available; install @alibaba-group/open-code-review and "
            "configure a provider, or run the panel without OCR critics"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise contract.WorkflowError(
            f"the ocr CLI did not finish within {timeout} seconds"
        ) from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-800:]
        raise contract.WorkflowError(f"the ocr CLI failed ({completed.returncode}): {detail}")
    return _parse_output(completed.stdout)


# The receipt identity of one OCR run: the CLI's own session and run IDs. A run
# without a persisted session carries no honest identity and is not imported.
def ocr_identity(output: dict[str, Any]) -> tuple[str, str]:
    session = str(output.get("session_id") or "")
    if not session:
        raise contract.WorkflowError(
            "the ocr CLI output has no session_id; the run produced no persistent identity, "
            "so its findings cannot be imported as a critic receipt"
        )
    manifest = output.get("manifest")
    run = ""
    if isinstance(manifest, dict):
        run = str(manifest.get("run_id") or "")
    return (run or session, session)


# Maps one OCR comment into the shared v2 finding shape used by MR receipts.
def _finding_mr(comment: dict[str, Any], index: int) -> dict[str, Any]:
    location = _comment_location(comment)
    content = str(comment.get("content") or "")
    category = str(comment.get("category") or "")
    suggestion = str(comment.get("suggestion_code") or "")
    severity = str(comment.get("severity") or "")
    evidence = [f"OpenCodeReview located the finding at {location}."]
    existing = str(comment.get("existing_code") or "")
    if existing:
        evidence.append(f"Reported existing code:\n{existing}")
    return {
        "id": f"ocr-{index}-{safe_id_fragment(str(comment.get('path') or ''))}",
        "severity": severity if severity in OCR_SEVERITIES else "low",
        "summary": content or f"OpenCodeReview suggested a change at {location}.",
        "risk": (
            f"OpenCodeReview classified the issue as {category or 'uncategorized'}; the "
            "reported risk stays unverified until the arbitrator confirms it."
        ),
        "evidence": evidence,
        "consequence": (
            f"The reported issue remains in the changed code at {location} unless the "
            "arbitrator refutes it."
        ),
        "relation_to_change": f"OCR located the finding inside the reviewed diff at {location}.",
        "minimum_fix": suggestion or content,
    }


# Maps one OCR comment into the local review finding shape. The local report
# fields that require judgment (requirement, scenario, origin) carry honest
# mechanical placeholders; the arbitrator rewrites them when accepting.
def _finding_local(
    comment: dict[str, Any], index: int, session_id: str, goal_text: str | None
) -> dict[str, Any]:
    location = _comment_location(comment)
    content = str(comment.get("content") or "")
    category = str(comment.get("category") or "")
    suggestion = str(comment.get("suggestion_code") or "")
    severity = str(comment.get("severity") or "")
    existing = str(comment.get("existing_code") or "")
    evidence = f"{location}: {content}" if content else f"{location}: {suggestion}"
    if existing:
        evidence = f"{evidence}\nReported existing code:\n{existing}"
    return {
        "id": f"ocr-{index}-{safe_id_fragment(str(comment.get('path') or ''))}",
        "severity": severity if severity in OCR_SEVERITIES else "low",
        "status": "open",
        "summary": content or f"OpenCodeReview suggested a change at {location}.",
        "requirement": goal_text
        or "Assess the OCR-reported issue against the recorded review goal.",
        "scenario": (
            f"OpenCodeReview reported a {category or 'uncategorized'} issue at {location} "
            "while reviewing the recorded change."
        ),
        "evidence": evidence,
        "consequence": (
            f"The reported issue remains in the changed code at {location} unless the "
            "arbitrator refutes it."
        ),
        "origin": "regression",
        "minimum_fix": suggestion or content,
        "blocking": severity in _LOCAL_SEVERITY_BLOCKING,
        "rationale": (
            f"Imported mechanically from OpenCodeReview run {session_id}; the arbitrator "
            "must confirm or refute it on evidence."
        ),
        "decision_evidence": None,
        "reopen_reason": None,
    }


# Maps the complete OCR JSON output into a critic receipt bound to the recorded
# evidence. ``kind`` selects the finding shape: "mr" for the remote MR panel,
# "local" for the local WIP panel. OCR produces findings only; it never answers
# critic-assigned questions.
def map_ocr_receipt(
    output: dict[str, Any],
    *,
    evidence_digest: str,
    kind: str,
    package: dict[str, Any] | None = None,
    scope_digest: str | None = None,
    target_finding_ids: list[str] | None = None,
) -> dict[str, Any]:
    if kind not in {"mr", "local"}:
        raise contract.WorkflowError(f"unknown OCR receipt kind {kind}")
    if scope_digest is not None and kind != "mr":
        raise contract.WorkflowError(
            "incremental scope stamping applies to MR receipts only; the local "
            "receipt schema stays full-scope"
        )
    run_id, session_id = ocr_identity(output)
    comments = output.get("comments")
    if not isinstance(comments, list):
        comments = []
    goal = package.get("goal") if isinstance(package, dict) else None
    goal_text = (
        str(goal.get("text"))
        if isinstance(goal, dict) and isinstance(goal.get("text"), str) and goal["text"]
        else None
    )
    findings = []
    for index, comment in enumerate(comments):
        if not isinstance(comment, dict):
            continue
        if not str(comment.get("content") or "") and not str(comment.get("suggestion_code") or ""):
            continue
        if kind == "mr":
            findings.append(_finding_mr(comment, index))
        else:
            findings.append(_finding_local(comment, index, session_id, goal_text))
    llm = output.get("llm")
    provider = str(llm.get("provider") or "") if isinstance(llm, dict) else ""
    model = str(llm.get("model") or "") if isinstance(llm, dict) else ""
    terminal_state = "unknown"
    manifest = output.get("manifest")
    if isinstance(manifest, dict) and isinstance(manifest.get("terminal_state"), str):
        terminal_state = manifest["terminal_state"]
    elif isinstance(output.get("status"), str):
        terminal_state = output["status"]
    receipt: dict[str, Any] = {
        "schema": (
            "portable-gitlab/critic-receipt/v2"
            if kind == "mr"
            else "code-review/local-critic-receipt/v1"
        ),
        "evidence_digest": evidence_digest,
        "run_id": run_id,
        "session_id": session_id,
        "findings": findings,
        "question_answers": [],
        "external_mutations": False,
        "engine": "ocr",
        "ocr": {
            "provider": provider or "configured",
            "model": model or "configured",
            "terminal_state": terminal_state,
            "comments": len(comments),
        },
    }
    # Incremental MR receipts bind the reviewed delta and name exactly the
    # previously reported findings rendered into the background section.
    if scope_digest is not None:
        receipt["scope_digest"] = scope_digest
        receipt["target_finding_ids"] = list(target_finding_ids or [])
    return receipt
