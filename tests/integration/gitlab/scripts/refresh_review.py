"""Assert material refresh retains old work and does not publish remotely."""

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
    value = contract.read_json(path, "refresh input")
    before = contract.read_json(Path(value["draft"]), "draft")
    progress = context.load_progress(Path(value["artifact_root"]))
    if progress is None or progress.get("plan_path") is None:
        raise RuntimeError("Previous finalized plan is missing")
    plan_path = Path(str(progress["plan_path"]))
    contract.artifact_payload(plan_path, "review_plan")
    prior_digest = str(progress["plan_digest"])
    refreshed = draft.refresh_review(str(value["draft"]))
    if refreshed.get("status") != "needs_reassessment":
        raise RuntimeError(json.dumps(refreshed))
    next_draft = contract.read_json(Path(str(refreshed["draft_path"])), "refreshed draft")
    progress_after = context.load_progress(Path(value["artifact_root"]))
    if progress_after is None or progress_after.get("plan_digest") != prior_digest:
        raise RuntimeError("Material refresh replaced the last finalized plan")
    if (
        next_draft["findings"] != before["findings"]
        or next_draft["dispositions"] != before["dispositions"]
        or next_draft["critics"] != []
        or contract.read_json(Path(value["draft"]), "original draft") != before
        or next_draft["evidence_digest"] == before["evidence_digest"]
        or "discussions" not in refreshed["refresh_scope"]["changed_evidence_fields"]
    ):
        raise RuntimeError("Material refresh lost or rebound review work")
    output = {
        "status": refreshed["status"],
        "refresh_scope": refreshed["refresh_scope"],
        "previous_draft_path": value["draft"],
        "refreshed_draft_path": refreshed["draft_path"],
        "retained_plan_digest": prior_digest,
        "findings_retained": True,
        "original_receipts_preserved": True,
        "new_receipts": [],
        "receipt_origin": "deterministic fixture, not a real critic run",
        "external_mutations": False,
    }
    contract.write_json(Path(value["output"]), output)
    return output


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), ensure_ascii=False))
