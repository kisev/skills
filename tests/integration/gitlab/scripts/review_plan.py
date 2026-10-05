"""Drive deterministic review, repair, refresh, and runbook checks in Python."""

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

from apps.reviewmatic.tests.helpers.review_fixture import complete_draft  # noqa: E402


def read(path: str | Path) -> dict[str, Any]:
    return contract.read_json(Path(path), "reviewmatic integration input")


def write(path: str | Path, value: object) -> None:
    contract.write_json(Path(path), value)


def finalized_plan(root: str | Path) -> tuple[dict[str, Any], str]:
    progress = context.load_progress(Path(root))
    if progress is None or progress.get("plan_path") is None:
        raise RuntimeError("Finalized review plan is unavailable")
    _, plan = contract.artifact_payload(Path(str(progress["plan_path"])), "review_plan")
    return plan, str(progress["plan_digest"])


def review(input_path: Path) -> dict[str, Any]:
    value = read(input_path)
    started = value.get("started") or draft.start_review(
        url=value["url"], repo_root=value["repo"], locale="en"
    )
    if started.get("status") != "ok":
        raise RuntimeError(json.dumps(started))
    if started.get("role") != "reviewer":
        raise RuntimeError("The reviewer actor did not collect the review")
    if value.get("require_pagination"):
        _, evidence = contract.artifact_payload(
            Path(str(started["evidence_path"])), "evidence_snapshot"
        )
        if evidence.get("labels", {}).get("pages", 0) < 2:
            raise RuntimeError("Reviewmatic did not collect the second label catalog page")
        names = {label["name"] for label in evidence["labels"]["items"]}
        missing = {
            f"matrix-page-{index:03}"
            for index in range(101)
            if f"matrix-page-{index:03}" not in names
        }
        if missing:
            raise RuntimeError(
                f"Reviewmatic dropped labels from the second page: {sorted(missing)}"
            )

    draft_path = Path(str(started["draft_path"]))
    current = (
        read(draft_path) if value.get("started") else complete_draft(read(draft_path), started)
    )
    current["run_id"] = value.get("run", current["run_id"])
    current["session_id"] = "deterministic-harness-" + str(value.get("run", "review"))
    current["critics"][0]["run_id"] = "deterministic-fixture-critic"
    current["critics"][0]["session_id"] = "deterministic-fixture-session"
    content = current["content"]
    content["summary"] = (
        "Synthetic placement and publication probes against the exact fixture head."
    )
    content["architecture_assessment"] = (
        "The fixture contains only text fixtures and synthetic CI jobs."
    )
    content["checks"] = ["Deterministic harness input; no agent or critic invocation is claimed."]
    content["semver_assessment"]["sources"] = [
        "Exact synthetic repository and collected non-versioned harness tags/releases."
    ]
    content["chat_assessment"] = {
        "necessity": {
            "status": "supported",
            "rationale": "Exercise real-server publication transport.",
        },
        "relevance": {
            "status": "current",
            "rationale": "These are the current synthetic fixture positions.",
        },
        "change": "Change synthetic text outputs and exercise shell-CI evidence.",
    }
    current["findings"] = [
        {
            "id": "harness-grouped",
            "severity": "low",
            "summary": "Exercise grouped synthetic outputs",
            "risk": "The two fixture outputs differ from the test's expected replacements.",
            "evidence": [
                "grouped.txt and grouped-extra.txt line 2 contain new first and new second at the exact fixture head."
            ],
            "consequence": "The exact-output assertion would fail until both parts are applied.",
            "relation_to_change": "The added line belongs to the synthetic diff.",
            "minimum_fix": "Replace both independently applicable outputs.",
        }
    ]
    current["dispositions"] = [
        {
            "id": "harness-grouped",
            "decision": "accept",
            "reason": "Synthetic expected-output contract, not a product defect.",
            "dependencies": {
                "paths": ["grouped.txt", "grouped-extra.txt"],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            },
        }
    ]
    content["finding_publications"] = [
        {
            "finding_id": "harness-grouped",
            "type": "general",
            "path": None,
            "line": None,
            "old_line": None,
            "body": "Both independent synthetic replacements are required for the complete expected output.",
            "fix_mode": "suggestion",
            "patch": None,
            "suggestions": [
                {
                    "path": "grouped.txt",
                    "line": 2,
                    "body": "Harness grouped first\n\n```suggestion\nfixed first\n```",
                },
                {
                    "path": "grouped-extra.txt",
                    "line": 2,
                    "body": "Harness grouped second\n\n```suggestion\nfixed second\n```",
                },
            ],
            "split_rationale": "Each line can be replaced independently; one application is not a complete fix.",
        }
    ]
    sample_patch = (
        "diff --git a/sample.txt b/sample.txt\n"
        "--- a/sample.txt\n+++ b/sample.txt\n"
        "@@ -1,5 +1,5 @@\n context\n-new\n+fixed\n keep\n last\n added\n"
    )
    if value.get("same_file"):
        current["dispositions"][0]["dependencies"]["paths"] = ["same.txt"]
        current["findings"][0]["evidence"] = [
            "same.txt lines 2 and 3 at the exact synthetic fixture head."
        ]
        content["finding_publications"][0]["suggestions"][0]["path"] = "same.txt"
        content["finding_publications"][0]["suggestions"][1].update({"path": "same.txt", "line": 3})
    else:
        for side, line, old_line in (("old", None, 2), ("new", 5, None), ("context", 3, None)):
            finding_id = f"harness-direct-{side}"
            current["findings"].append(
                {
                    "id": finding_id,
                    "severity": "low",
                    "summary": f"Exercise direct {side} publication",
                    "risk": "The synthetic expected output differs from the fixture text.",
                    "evidence": [f"sample.txt {side} position at the exact fixture head."],
                    "consequence": "The fixture output assertion would remain unsatisfied.",
                    "relation_to_change": "The position belongs to the synthetic diff hunk.",
                    "minimum_fix": "Replace the synthetic output with the expected text.",
                }
            )
            current["dispositions"].append(
                {
                    "id": finding_id,
                    "decision": "accept",
                    "reason": "Deterministic transport probe, not a product defect.",
                    "dependencies": {
                        "paths": ["sample.txt"],
                        "thread_ids": [],
                        "metadata_fields": [],
                        "ci": False,
                    },
                }
            )
            publication = {
                "finding_id": finding_id,
                "type": "line",
                "path": "sample.txt",
                "line": line,
                "old_line": old_line,
                "body": (
                    "Harness direct new\n\n```suggestion\ndirect added\n```"
                    if side == "new"
                    else f"Harness direct {side}; synthetic patch transport probe."
                ),
                "fix_mode": "suggestion" if side == "new" else "patch",
                "patch": None if side == "new" else sample_patch,
            }
            if side != "new":
                publication["patch_reason"] = (
                    "Exercise exact old/context positioned patch commands."
                )
            content["finding_publications"].append(publication)

    for thread in content["thread_decisions"]:
        thread["assessment"] = "neutral"
        thread["rationale"] = "Synthetic placement probe, not a claimed code defect."
        thread["outcome"] = "reply" if thread["state"] == "open" else "no_publication"
        thread["proposed_response"] = (
            "Harness reviewmatic reply; correction is still pending."
            if thread["state"] == "open"
            else None
        )
    _, review_context = contract.artifact_payload(
        Path(str(started["context_path"])), "review_context"
    )
    for thread in content["thread_decisions"]:
        source = next(
            (
                item
                for item in review_context["discussions"]
                if str(item["root_note_id"]) == str(thread["id"])
            ),
            None,
        )
        body = source["notes"][0]["body"] if source is not None else None
        if body == "Harness state closed":
            thread.update(
                {
                    "assessment": "accepted",
                    "severity": "medium",
                    "outcome": "reopen",
                    "rationale": "The deterministic fixture output remains unchanged and requires correction.",
                    "proposed_response": "Harness reviewmatic state reopen; synthetic correction pending.",
                    "fix_mode": "patch",
                    "patch": sample_patch,
                }
            )
        elif body == "Harness state open":
            thread.update(
                {
                    "assessment": "false_positive",
                    "outcome": "resolve",
                    "rationale": "This fixture remark is intentionally a false positive; no code change is needed.",
                    "proposed_response": "Harness reviewmatic state resolve; deterministic false-positive probe.",
                }
            )
    for job in current["ci_job_assessments"]:
        job.update(
            {
                "classification": "process_gate",
                "rationale": "The fixture explicitly executes exit 1 with allow_failure to exercise real failing traces.",
                "trace_evidence": "HARNESS_FAILURE",
            }
        )
    write(draft_path, current)
    checked = draft.check_review(str(draft_path))
    if checked.get("status") != "ok":
        raise RuntimeError(json.dumps(checked))

    if value.get("phase") == "draft":
        output = {"started": started, "receipts": current["critics"], "external_mutations": False}
        write(value["output"], output)
        return output

    ci_refresh = None
    if value.get("phase") == "ci-finish":
        before = read(draft_path)
        refreshed = draft.finish_review(str(draft_path))
        if refreshed.get("status") != "refresh_required":
            raise RuntimeError(json.dumps(refreshed))
        updated = read(draft_path)
        if (
            updated["findings"] != before["findings"]
            or updated["dispositions"] != before["dispositions"]
            or updated["critics"] != before["critics"]
            or updated["evidence_digest"] != before["evidence_digest"]
            or not updated.get("ci_snapshot")
        ):
            raise RuntimeError("CI-only refresh changed review evidence or receipts")
        for job in updated["ci_job_assessments"]:
            job.update(
                {
                    "classification": "process_gate",
                    "rationale": "The new exact-head fixture pipeline deliberately executes exit 1 with allow_failure.",
                    "trace_evidence": "HARNESS_FAILURE",
                }
            )
        updated["content"]["checks"].append(
            "Refreshed exact-head CI evidence; code and fixture critic receipts were retained without restarting review."
        )
        write(draft_path, updated)
        ci_refresh = {
            "status": refreshed["status"],
            "original_evidence_digest": before["evidence_digest"],
            "ci_snapshot": updated["ci_snapshot"],
            "findings_retained": True,
            "receipts_retained": True,
            "repeated_start_review": False,
        }

    finished = draft.finish_review(str(draft_path))
    if finished.get("status") != "ok":
        raise RuntimeError(json.dumps(finished))
    receipts = read(draft_path)["critics"]
    prior, prior_digest = finalized_plan(started["artifact_root"])
    repair = draft.repair_review(str(started["artifact_root"]), "presentation")
    repair_path = Path(str(repair["draft_path"]))
    repaired_draft = read(repair_path)
    repaired_draft["repair"]["rationale"] = (
        "Retain findings, positions and fixture receipts; clarify the harness check text."
    )
    repaired_draft["repair"]["checks"] = [
        "Compared source findings, suggested outputs and fixture receipts."
    ]
    repaired_draft["content"]["checks"].append(
        "Presentation-only repair exercised without changing the synthetic outputs."
    )
    write(repair_path, repaired_draft)
    repaired = draft.finish_review(str(repair_path))
    if repaired.get("status") != "ok":
        raise RuntimeError(json.dumps(repaired))
    plan, plan_digest = finalized_plan(started["artifact_root"])
    for key in ("findings", "finding_publications"):
        if plan[key] != prior[key]:
            raise RuntimeError(f"Presentation repair changed {key}")
    if plan["review_source"]["critics"] != prior["review_source"]["critics"]:
        raise RuntimeError("Presentation repair changed critic receipts")
    output = {
        "started": started,
        "finished": repaired,
        "receipts": receipts,
        "repair": {"prior_digest": prior_digest, "digest": plan_digest},
        "ci_refresh": ci_refresh,
        "actions": plan["publication_preview"]["actions"],
    }
    write(value["output"], output)
    return output


if __name__ == "__main__":
    print(json.dumps(review(Path(sys.argv[1])), ensure_ascii=False))
