"""The user-selected critic panel for one-process review runs.

The run stores the poll answer (the critic composition and the engine of every
critic) and the imported per-critic receipts in one private file at the
artifact root. OCR critics execute mechanically inside the run; model critics
stop the run for a callback or a manual ``record-run-critic`` import. When
every selected critic has its receipt, the panel merges into one aggregate
critic receipt through the shared ``contributors`` convention and the run
continues into finalization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from reviewmatic import context, ocr_critic
from reviewmatic import draft as draft_module
from reviewmatic.portable.portable_gitlab import contract

PANEL_NAME = "review-panel.json"
PANEL_SCHEMA = "code-review/run-panel/v1"


def panel_path(root: Path) -> Path:
    return root / PANEL_NAME


def load(root: Path) -> dict[str, Any] | None:
    """Read the run panel, or None when the review has no recorded panel."""
    path = panel_path(root)
    if not path.exists() and not path.is_symlink():
        return None
    value = contract.read_json(contract.regular_file(path, "run panel"), "run panel")
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "participants", "receipts"}
        or value.get("schema") != PANEL_SCHEMA
        or not isinstance(value.get("participants"), dict)
        or not isinstance(value.get("receipts"), list)
    ):
        raise contract.WorkflowError("the run panel file has an invalid shape")
    panel = value
    participants = cast("dict[str, Any]", panel["participants"])
    critics = participants.get("critics")
    if not isinstance(critics, list) or not isinstance(participants.get("arbitrator"), dict):
        raise contract.WorkflowError("the run panel selection has an invalid shape")
    receipts = cast("list[object]", panel["receipts"])
    bound = {
        (
            str(cast("dict[str, Any]", critic["receipt"])["run_id"]),
            str(cast("dict[str, Any]", critic["receipt"])["session_id"]),
        )
        for critic in cast("list[object]", critics)
        if isinstance(critic, dict) and isinstance(critic.get("receipt"), dict)
    }
    imported = {
        (str(receipt.get("run_id")), str(receipt.get("session_id")))
        for receipt in receipts
        if isinstance(receipt, dict)
    }
    if len(receipts) != len(imported) or bound != imported:
        raise contract.WorkflowError(
            "the run panel receipts and participant bindings disagree; the panel file is corrupt"
        )
    return panel


def write(root: Path, panel: dict[str, Any]) -> None:
    contract.write_json(panel_path(root), panel)


def selection_template(root: Path, context_digest: str) -> Path:
    """Materialize the empty poll answer the agent fills after asking the user."""
    return context.write_review_draft(
        root,
        "participants",
        context_digest,
        {
            "critics": [{"name": "critic-1", "engine": "model"}],
            "arbitrator": {"name": "arbitrator-1"},
        },
    )


def record_selection(
    root: Path,
    selection_path: str,
    ocr_provider: str | None,
    ocr_model: str | None,
    mode: str,
) -> dict[str, Any]:
    """Validate the poll answer and record it as the run panel selection."""
    user_input = contract.read_json(
        contract.regular_file(Path(selection_path), "participant selection"),
        "participant selection",
    )
    contract.reject_envelope_wrapper(user_input, "participant selection")
    errors = draft_module.participant_selection_issues(user_input)
    if not errors:
        errors.extend(
            ocr_critic.stamp_ocr_configuration(
                cast("list[dict[str, Any]]", user_input["critics"]), ocr_provider, ocr_model
            )
        )
    if (
        not errors
        and mode == "incremental"
        and ocr_critic.ocr_critics(cast("list[dict[str, Any]]", user_input["critics"]))
    ):
        errors = [
            {
                "path": "$.critics",
                "message": (
                    "OCR critics review the complete base..head range and do not produce "
                    "delta-scoped incremental receipts; run the panel without OCR critics "
                    "for incremental reviews"
                ),
            }
        ]
    if errors:
        raise contract.WorkflowError(
            "the panel selection is invalid: "
            + "; ".join(f"{issue['path']}: {issue['message']}" for issue in errors)
        )
    panel: dict[str, Any] = {
        "schema": PANEL_SCHEMA,
        "participants": user_input,
        "receipts": [],
    }
    write(root, panel)
    return panel


def selected_critics(panel: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", cast("dict[str, Any]", panel["participants"])["critics"])


def pending_critics(panel: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        critic for critic in selected_critics(panel) if not isinstance(critic.get("receipt"), dict)
    ]


def summary(panel: dict[str, Any]) -> dict[str, Any]:
    critics = [
        {
            "name": str(critic["name"]),
            "engine": ocr_critic.critic_engine(critic),
            **(
                {
                    "run_id": str(critic["receipt"]["run_id"]),
                    "session_id": str(critic["receipt"]["session_id"]),
                }
                if isinstance(critic.get("receipt"), dict)
                else {"bound": False}
            ),
        }
        for critic in selected_critics(panel)
    ]
    return {
        "critics": critics,
        "arbitrator": str(
            cast("dict[str, Any]", panel["participants"]).get("arbitrator", {}).get("name", "")
        ),
    }


def bind_receipt(
    root: Path,
    panel: dict[str, Any],
    participant: str,
    receipt: dict[str, Any],
    evidence_digest: str,
    scope_digest: str | None,
    *,
    mechanical: bool = False,
) -> dict[str, Any]:
    """Validate one critic receipt and bind it to its participant.

    The manual import path (``record-run-critic``) refuses OCR participants;
    the runtime's own mechanical execution binds OCR receipts directly.
    """
    selected = next(
        (item for item in selected_critics(panel) if str(item["name"]) == participant), None
    )
    if selected is None:
        raise contract.WorkflowError(
            f"Unknown run-panel participant {participant}; the selected critics are "
            + ", ".join(str(item["name"]) for item in selected_critics(panel))
        )
    if not mechanical and ocr_critic.critic_engine(selected) == "ocr":
        raise contract.WorkflowError(
            f"Participant {participant} is an OCR critic; the run executes it mechanically "
            "on the next resume"
        )
    if isinstance(selected.get("receipt"), dict):
        raise contract.WorkflowError(
            f"Participant {participant} already has a bound receipt; each selected critic "
            "is imported exactly once"
        )
    contract.validate_critic(receipt, evidence_digest, scope_digest)
    if not contract.detailed_findings_are_valid(receipt.get("findings")):
        raise contract.WorkflowError("critic findings require complete structured evidence")
    identity = (str(receipt.get("run_id")), str(receipt.get("session_id")))
    if not all(identity) or any(
        identity == (str(item.get("run_id")), str(item.get("session_id")))
        for item in cast("list[dict[str, Any]]", panel["receipts"])
    ):
        raise contract.WorkflowError("each critic must have its own real run and session identity")
    updated_critics = [
        {**item, "receipt": {"run_id": identity[0], "session_id": identity[1]}}
        if str(item.get("name")) == participant
        else item
        for item in selected_critics(panel)
    ]
    updated: dict[str, Any] = {
        **panel,
        "participants": {
            **cast("dict[str, Any]", panel["participants"]),
            "critics": updated_critics,
        },
        "receipts": [*cast("list[object]", panel["receipts"]), receipt],
    }
    write(root, updated)
    return updated


def aggregate(
    panel: dict[str, Any], evidence_digest: str, scope_digest: str | None
) -> dict[str, Any]:
    """Merge the imported receipts into one critic receipt (shared convention)."""
    receipts = cast("list[dict[str, Any]]", panel["receipts"])
    if not receipts:
        raise contract.WorkflowError("the run panel has no imported critic receipts")
    merged: dict[str, Any]
    if len(receipts) == 1:
        merged = receipts[0]
    else:
        merged = {
            **receipts[0],
            "findings": [
                finding
                for item in receipts
                for finding in cast("list[dict[str, Any]]", item.get("findings") or [])
            ],
            "target_finding_ids": sorted(
                {
                    target
                    for item in receipts
                    for target in cast("list[str]", item.get("target_finding_ids") or [])
                }
            ),
            "question_answers": [
                answer
                for item in receipts
                for answer in cast("list[dict[str, Any]]", item.get("question_answers") or [])
            ],
            "contributors": receipts,
        }
    contract.validate_critic(merged, evidence_digest, scope_digest)
    return merged


def ocr_background(review_context: dict[str, Any]) -> dict[str, Any]:
    """Honest mechanical background for a run OCR critic: no package exists."""
    threads = []
    for discussion in cast("list[dict[str, Any]]", review_context.get("discussions") or []):
        if discussion.get("root_system") is True:
            continue
        notes = cast("list[dict[str, Any]]", discussion.get("notes") or [])
        body = str(notes[0].get("body") or "").strip() if notes else ""
        threads.append(
            {
                "id": str(discussion.get("id")),
                "state": "resolved" if discussion.get("root_resolved") is True else "open",
                "summary": body[:280] or "(no text)",
                "review_relevance": (
                    "uncollected: the run reviews the discussion registry, not a recorded package"
                ),
            }
        )
    return {"thread_registry": threads}


def run_ocr_critic(
    root: Path,
    progress: dict[str, Any],
    review_context: dict[str, Any],
    context_digest: str,
    evidence: dict[str, Any],
    critic: dict[str, Any],
    scope_digest: str | None,
) -> dict[str, Any]:
    """Execute one OCR critic mechanically and bind its receipt."""
    participant = str(critic["name"])
    drafts = contract.private_directory(root / "review-drafts")
    background = ocr_critic.render_ocr_background(
        ocr_background(review_context), drafts, context_digest
    )
    repo_root = str(progress.get("repo_root") or "")
    if not repo_root:
        raise contract.WorkflowError("the OCR critic requires the selected repository root")
    output = ocr_critic.invoke_ocr_critic(
        background,
        str(evidence["base_sha"]),
        str(evidence["head_sha"]),
        critic.get("provider"),
        critic.get("model"),
        repo=repo_root,
    )
    receipt = ocr_critic.map_ocr_receipt(
        output,
        evidence_digest=str(progress["evidence_digest"]),
        kind="mr",
        package=ocr_background(review_context),
    )
    contract.write_json(
        drafts / f"ocr-critic-{ocr_critic.safe_id_fragment(participant)}.json", receipt
    )
    panel = load(root)
    if panel is None:
        raise contract.WorkflowError("the run panel disappeared during the OCR critic run")
    return bind_receipt(
        root,
        panel,
        participant,
        receipt,
        str(progress["evidence_digest"]),
        scope_digest,
        mechanical=True,
    )


def critic_template(
    root: Path, review_context: dict[str, Any], mode: str, context_digest: str, participant: str
) -> Path:
    """Materialize the per-critic receipt template for one model critic."""
    return context.write_review_draft(
        root,
        f"critic-{ocr_critic.safe_id_fragment(participant)}",
        context_digest,
        draft_module._critic_receipt(review_context, mode),
    )
