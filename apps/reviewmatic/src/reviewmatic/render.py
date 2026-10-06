"""Decision-driven content rendering, the prose surface, and drift re-anchoring.

The live-review tail inverted: once the decision (arbitration receipt or
dispositions) is recorded, the runtime renders the complete content draft -
machine fields (anchors, bindings, revisions, stamps) derived by calling the
same functions the validators call, prose fields as structurally detectable
placeholders. The agent edits only prose and semantic choices through one
file and one command; evidence drift re-anchors the machine fields instead of
re-authoring the review.
"""

from __future__ import annotations

import copy
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from reviewmatic import context, publication_skeletons
from reviewmatic.portable.portable_gitlab import contract

# Prose and semantic keys the agent may edit through the prose surface; every
# other content key is machine-rendered and rejected here.
PROSE_KEYS = (
    "locale",
    "chat_assessment",
    "summary",
    "architecture_assessment",
    "semver_impact",
    "semver_rationale",
    "semver_assessment",
    "mr_metadata_assessment",
    "label_assessments",
    "checks",
    "previous_finding_assessments",
    "recommended_issues",
    "rejected_candidates",
    "rejected_candidate_assessments",
    "thread_decisions",
    "finding_publications",
)
STRUCTURAL_THREAD_KEYS = {
    "url",
    "state",
    "last_note_id",
    "last_note_body_sha256",
    "thread_sha256",
}
STRUCTURAL_PUBLICATION_KEYS = {
    "type",
    "path",
    "line",
    "old_line",
    "fix_mode",
    "suggestions",
    "patch_path",
    "patch_sha256",
    "revision",
}
STRUCTURAL_ASSESSMENT_KEYS = {"critic_required", "previous_status", "revision", "update_issue"}
SEMVER_PROSE_KEYS = {"policy", "sources", "fallback_reason", "release_impact", "release_rationale"}


def _accepted_findings(draft: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [
        *_records_flat(draft.get("findings")),
        *[
            finding
            for receipt in _records_flat(draft.get("critics"))
            for finding in _records_flat(receipt.get("findings"))
        ],
    ]
    dispositions = {str(item.get("id")): item for item in _records_flat(draft.get("dispositions"))}
    accepted = []
    for finding in findings:
        disposition = dispositions.get(str(finding.get("id")))
        if disposition is not None and disposition.get("decision") == "accept":
            override = disposition.get("severity_override") or {}
            accepted.append(
                {**finding, "severity": override.get("severity") or finding["severity"]}
            )
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(accepted, key=lambda finding: order[finding["severity"]])


def _records_flat(value: object) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", value) if isinstance(value, list) else []


def _publication_intents(draft: dict[str, Any]) -> dict[str, dict[str, Any]]:
    arbitration = draft.get("arbitration")
    if isinstance(arbitration, dict):
        rows = _records_flat(arbitration.get("dispositions"))
    else:
        rows = _records_flat(draft.get("dispositions"))
    intents: dict[str, dict[str, Any]] = {}
    for row in rows:
        publication = row.get("publication")
        if isinstance(publication, dict):
            intents[str(row.get("id"))] = publication
    return intents


def _first_changed_line(
    repo_root: Path, base: str, head: str, paths: list[str]
) -> tuple[str, int] | None:
    anchors: list[tuple[str, int]] = []
    for path in paths:
        _, visible = context.changed_diff_lines(repo_root, base, head, path)
        diff = str(contract.git_read(repo_root, "diff", "--unified=0", base, head, "--", path))
        for match in re.finditer(r"^@@ -[^ ]+ \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
            start, count = int(match[1]), int(match[2]) if match[2] is not None else 1
            anchors.extend((path, line) for line in range(start, start + count) if line in visible)
    if len(anchors) > 1:
        raise contract.WorkflowError(
            "line intent has multiple possible anchors; use decision repair to supply a "
            "verified publication instead of guessing a changed line"
        )
    return anchors[0] if anchors else None


def render_content(
    draft: dict[str, Any],
    review_context: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Render the complete content from the recorded decision.

    Machine fields are derived by the same functions the validators call;
    prose fields carry structurally detectable placeholders.
    """
    decision = _decision_for_content(draft)
    exact = cast("dict[str, Any]", review_context["exact_git"])
    repo_root = Path(str(exact["repo_root"]))
    base, head = str(evidence["base_sha"]), str(evidence["head_sha"])
    locale = "ru" if str(draft.get("content", {}).get("locale", "en")) == "ru" else "en"
    content = context.content_template(evidence, review_context, decision, locale)
    accepted = _accepted_findings(draft)
    intents = _publication_intents(draft)
    role = str(review_context.get("role", "reviewer"))
    rows: list[dict[str, Any]] = []
    for finding in accepted:
        finding_id = str(finding.get("id"))
        intent = intents.get(finding_id)
        if intent is None or intent.get("kind") == "none":
            raise contract.WorkflowError(
                f"accepted finding {finding_id} requires a publication intent with a concrete "
                "fix; none cannot hide an accepted finding - reject or merge it in arbitration"
            )
        if intent.get("kind") == "existing_thread":
            block = publication_skeletons._variant_block(finding_id, "existing_thread")
            thread_ids = [
                str(thread_id)
                for row in _records_flat(draft.get("dispositions"))
                if row.get("id") == finding_id
                for thread_id in (row.get("dependencies") or {}).get("thread_ids", [])
            ]
            bindings = context.expected_thread_bindings(review_context)
            if len(thread_ids) != 1 or thread_ids[0] not in bindings:
                raise contract.WorkflowError(
                    f"existing_thread intent for {finding_id} needs one prepared thread in "
                    "dependencies.thread_ids; use decision repair rather than guessing a thread"
                )
            block["thread_id"] = thread_ids[0]
            rows.append(block)
            continue
        if intent.get("kind") == "local_fix" and role == "author":
            rows.append(publication_skeletons._variant_block(finding_id, "local_fix+patch"))
            continue
        if intent.get("kind") == "line":
            block = publication_skeletons._variant_block(
                finding_id,
                "line+suggestion" if intent.get("fix_mode") == "suggestion" else "line+patch",
            )
            dependencies = _dependencies_of(draft, finding_id)
            anchor = _first_changed_line(repo_root, base, head, dependencies)
            if anchor is not None:
                block["path"], block["line"] = anchor[0], anchor[1]
            else:
                raise contract.WorkflowError(
                    f"line intent for {finding_id} has no changed-line anchor; use decision repair"
                )
            rows.append(block)
            continue
        rows.append(
            publication_skeletons._variant_block(
                finding_id,
                "general+patch",
            )
        )
    content["finding_publications"] = rows
    content["findings"] = accepted
    # Scrub at render time on machine-copied texts: semver sources and the
    # previous-finding rows are copied by the runtime, so a raw SHA inside
    # them is refused here, at the moment of copying.
    sources = cast("list[str]", content.get("semver_assessment", {}).get("sources", []))
    context.reject_visible_raw_refs("\n".join(sources), evidence, review_context)
    return content


def _dependencies_of(draft: dict[str, Any], finding_id: str) -> list[str]:
    arbitration = draft.get("arbitration")
    rows = (
        _records_flat(arbitration.get("dispositions"))
        if isinstance(arbitration, dict)
        else _records_flat(draft.get("dispositions"))
    )
    for row in rows:
        if str(row.get("id")) == finding_id:
            dependencies = row.get("dependencies")
            if isinstance(dependencies, dict):
                return [str(item) for item in cast("list[object]", dependencies.get("paths") or [])]
    return []


def _decision_for_content(draft: dict[str, Any]) -> dict[str, Any]:
    accepted = _accepted_findings(draft)
    return {
        "accepted_findings": accepted,
        "findings": accepted,
        "responses": [
            {"id": str(item.get("id")), "decision": "accept", "reason": "recorded"}
            for item in accepted
        ],
    }


def prose_file(root: Path, context_digest: str) -> Path:
    return root / "review-drafts" / f"content-prose-{context_digest[:16]}.json"


def prose_projection(content: dict[str, Any]) -> dict[str, Any]:
    """The prose surface: agent-editable fields only, machine keys stripped."""
    projection: dict[str, Any] = {}
    for key in PROSE_KEYS:
        if key not in content:
            continue
        value = copy.deepcopy(content[key])
        if key == "thread_decisions" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_THREAD_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "finding_publications" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_PUBLICATION_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "previous_finding_assessments" and isinstance(value, list):
            projection[key] = [
                {field: item[field] for field in item if field not in STRUCTURAL_ASSESSMENT_KEYS}
                for item in value
                if isinstance(item, dict)
            ]
        elif key == "semver_assessment" and isinstance(value, dict):
            projection[key] = {field: value[field] for field in SEMVER_PROSE_KEYS if field in value}
        else:
            projection[key] = value
    return projection


def apply_prose(content: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Apply the prose surface onto rendered content; structural keys refuse."""
    structural_rejections: list[str] = []
    merged = copy.deepcopy(content)
    for key, value in incoming.items():
        if key not in PROSE_KEYS:
            raise contract.WorkflowError(
                f"the prose surface carries only prose and semantic fields; {key} is "
                "machine-rendered - edit it only through a recorded repair kind"
            )
        if key == "semver_assessment":
            if not isinstance(value, dict) or set(value) - SEMVER_PROSE_KEYS:
                raise contract.WorkflowError(
                    "semver_assessment machine-rendered bindings cannot be set in record-prose; "
                    "edit policy, sources, fallback_reason, release_impact, or release_rationale"
                )
            merged[key] = {**merged[key], **copy.deepcopy(value)}
            continue
        if key in {"thread_decisions", "finding_publications", "previous_finding_assessments"} and (
            not isinstance(value, list) or any(not isinstance(row, dict) for row in value)
        ):
            raise contract.WorkflowError(
                f"{key} requires an array of prose objects; draft unchanged"
            )
        if key == "thread_decisions" and isinstance(value, list):
            rows: list[dict[str, Any]] = []
            current = {
                str(item.get("id")): item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                allowed = set(current.get(str(row.get("id"))) or {}) - STRUCTURAL_THREAD_KEYS
                leak = sorted(set(row) - allowed)
                if leak:
                    structural_rejections.append(f"thread_decisions[{row.get('id')}]: {leak}")
                    continue
                base = current.get(str(row.get("id")))
                if base is None:
                    structural_rejections.append(
                        f"thread_decisions: unknown thread id {row.get('id')}"
                    )
                    continue
                rows.append({**base, **row})
            merged[key] = rows
            continue
        if key == "finding_publications" and isinstance(value, list):
            rows = []
            current = {
                str(item.get("finding_id")): item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                allowed = (
                    set(current.get(str(row.get("finding_id"))) or {})
                    | {"body", "patch", "patch_reason", "split_rationale"}
                ) - STRUCTURAL_PUBLICATION_KEYS
                leak = sorted(set(row) - allowed)
                if leak:
                    structural_rejections.append(
                        f"finding_publications[{row.get('finding_id')}]: {leak}"
                    )
                    continue
                base = current.get(str(row.get("finding_id")))
                if base is None:
                    structural_rejections.append(
                        f"finding_publications: unknown finding id {row.get('finding_id')}"
                    )
                    continue
                rows.append({**base, **row})
            merged[key] = rows
            continue
        if key == "previous_finding_assessments" and isinstance(value, list):
            rows = []
            current = {
                f"{item.get('id')}\x00{item.get('kind') or ''}": item
                for item in cast("list[dict[str, Any]]", merged.get(key) or [])
                if isinstance(item, dict)
            }
            for row in value:
                if not isinstance(row, dict):
                    continue
                leak = sorted(STRUCTURAL_ASSESSMENT_KEYS & set(row))
                if leak:
                    structural_rejections.append(
                        f"previous_finding_assessments[{row.get('id')}]: {leak}"
                    )
                    continue
                matches = [
                    item for key2, item in current.items() if key2.split("\x00")[0] == row.get("id")
                ]
                if not matches:
                    structural_rejections.append(
                        f"previous_finding_assessments: unknown id {row.get('id')}"
                    )
                    continue
                base = matches[0]
                base_dict: dict[str, Any] = matches[0]
                identity_key = f"{row.get('id')}\x00{base_dict.get('kind') or ''}"
                rows.append({**base_dict, **row})
                del current[identity_key]
            merged[key] = rows
            continue
        merged[key] = value
    if structural_rejections:
        raise contract.WorkflowError(
            "structural keys are machine-rendered and were rejected: "
            + "; ".join(structural_rejections)
        )
    return merged


def placeholder_guidance(content: dict[str, Any]) -> list[dict[str, str]]:
    """Fill guidance for every unfilled prose placeholder, rule errors skipped."""
    guidance: list[dict[str, str]] = []
    for index, row in enumerate(_records_flat(content.get("finding_publications"))):
        fields = publication_skeletons.placeholder_fields(row)
        if fields:
            guidance.append(
                {
                    "path": f"$.content.finding_publications[{index}]",
                    "message": (
                        "unfilled template variant: fill the judgment fields "
                        f"{', '.join(fields)} or delete the unused variant rows"
                    ),
                }
            )
    for key in ("summary", "architecture_assessment", "semver_rationale"):
        value = content.get(key)
        if isinstance(value, str) and publication_skeletons.is_placeholder(value):
            guidance.append(
                {
                    "path": f"$.content.{key}",
                    "message": "fill the prose through the content prose file and record-prose",
                }
            )
    return guidance


def re_anchor_line(
    repo_root: Path, old_head: str, new_head: str, publications: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministic old-to-new line mapping for positioned publications."""
    remapped = copy.deepcopy(publications)
    for row in remapped:
        if row.get("type") != "line":
            continue
        path, line = str(row.get("path") or ""), row.get("line")
        if not path or not isinstance(line, int):
            continue
        diff = str(
            contract.git_read(repo_root, "diff", "--unified=0", old_head, new_head, "--", path)
        )
        offset = 0
        for match in re.finditer(
            r"^@@ -(?P<old>[0-9]+)(?:,(?P<old_count>[0-9]+))? \+(?P<new>[0-9]+)(?:,(?P<new_count>[0-9]+))? @@",
            diff,
            re.MULTILINE,
        ):
            old_start = int(match.group("old"))
            old_count = int(match.group("old_count")) if match.group("old_count") else 1
            new_count = int(match.group("new_count")) if match.group("new_count") else 1
            # An insertion (-N,0) occurs after N, not before N.
            if old_count == 0:
                if line > old_start:
                    offset += new_count
                continue
            if old_start <= line < old_start + old_count:
                raise contract.WorkflowError(
                    "the anchor is inside a changed hunk and has no unique image on the new "
                    f"head ({path}:{line}); use decision repair, never a guess"
                )
            if line >= old_start + old_count:
                offset += new_count - old_count
        row["line"] = line + offset
    return remapped


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
