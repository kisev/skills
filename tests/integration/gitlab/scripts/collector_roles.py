"""Collect evidence as a selected MR role without preparing a publication."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reviewmatic import draft  # noqa: E402
from reviewmatic.portable.portable_gitlab import contract  # noqa: E402


def run(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    started = draft.start_review(url=value["url"], repo_root=value["repo"], locale="en")
    if started.get("status") != "ok" or started.get("role") != "author":
        raise RuntimeError(f"Author collection failed: {json.dumps(started)}")
    _, evidence = contract.artifact_payload(
        Path(str(started["evidence_path"])), "evidence_snapshot"
    )
    if evidence.get("head_sha") != value["head"]:
        raise RuntimeError("Author collection used another merge-request head")
    if evidence.get("retrieval_complete") is not True:
        raise RuntimeError("Author collection returned incomplete evidence")
    if evidence["labels"].get("pages", 0) < 2:
        raise RuntimeError("Author collection did not consume the second label page")
    if started.get("external_mutations") is not False:
        raise RuntimeError("Author collection performed an external mutation")
    return {
        "started": started,
        "head": evidence["head_sha"],
        "labels_pages": evidence["labels"]["pages"],
    }


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), ensure_ascii=False))
