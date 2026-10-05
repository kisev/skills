"""Reassess exact same-file suggestion outputs without agent judgment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reviewmatic import context, draft  # noqa: E402
from reviewmatic.portable.portable_gitlab import contract  # noqa: E402


def run(path: Path) -> dict[str, Any]:
    value = contract.read_json(path, "same-file reassessment input")
    before = contract.read_json(Path(value["draft"]), "original draft")
    progress = context.load_progress(Path(value["artifact_root"]))
    if progress is None or progress.get("plan_path") is None:
        raise RuntimeError("Previously finalized plan is missing")
    plan_path = Path(str(progress["plan_path"]))
    contract.artifact_payload(plan_path, "review_plan")
    prior_digest = str(progress["plan_digest"])

    refreshed = draft.refresh_review(str(value["draft"]))
    if refreshed.get("status") != "needs_reassessment":
        raise RuntimeError(json.dumps(refreshed))
    next_draft = contract.read_json(Path(str(refreshed["draft_path"])), "refreshed draft")
    _, evidence = contract.artifact_payload(Path(next_draft["evidence_path"]), "evidence_snapshot")
    _, review_context = contract.artifact_payload(
        Path(next_draft["context_path"]), "review_context"
    )
    actual = str(
        contract.git_read(
            Path(review_context["exact_git"]["repo_root"]),
            "show",
            f"{evidence['head_sha']}:same.txt",
        )
    )
    complete_fix = actual == "before\nfixed first\nfixed second\nend\n"
    if (
        evidence.get("head_sha") != value["head"]
        or next_draft["findings"] != before["findings"]
        or next_draft["dispositions"] != before["dispositions"]
        or next_draft["critics"] != []
        or contract.read_json(Path(value["draft"]), "original draft") != before
        or complete_fix is not value["complete_fix"]
        or not refreshed["refresh_scope"]["changed_evidence_fields"]
    ):
        raise RuntimeError("Same-file reassessment changed or misclassified review evidence")
    progress_after = context.load_progress(Path(value["artifact_root"]))
    if progress_after is None or progress_after.get("plan_digest") != prior_digest:
        raise RuntimeError("Same-file refresh replaced the last finalized plan")
    contract.artifact_payload(plan_path, "review_plan")
    return {
        "status": refreshed["status"],
        "refreshed_draft_path": refreshed["draft_path"],
        "head": evidence["head_sha"],
        "exact_file": actual,
        "complete_fix": complete_fix,
        "prior_plan_preserved": True,
        "original_draft_preserved": True,
        "new_receipts": [],
        "refresh_scope": refreshed["refresh_scope"],
        "origin": "deterministic exact-output reassessment, not an agent or critic run",
    }


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), ensure_ascii=False))
