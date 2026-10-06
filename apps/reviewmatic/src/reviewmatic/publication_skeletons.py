"""Formally complete finding-publication skeletons for agent-filled templates.

The renderer is a pure function over findings: it emits one block per valid
``(type, fix_mode)`` variant, fills every mechanical field (``finding_id``),
and leaves every judgment field as a structurally detectable placeholder. A
placeholder never passes validation: the app-layer validator answers it with a
self-documenting error that names the missing judgment and the accepted form,
so an agent filling the template learns the publication contract from the
template and its refusals instead of by trial and error.
"""

from __future__ import annotations

import re
from typing import Any

# A judgment placeholder is a marked string ("<BODY: ...>", "<PATCH: ...>", ...)
# or an empty string; the validator rejects both with fill-or-delete guidance.
PLACEHOLDER_RE = re.compile(r"^<[A-Z][A-Z0-9_]*:")

BODY_HINT = "<BODY: prose for the publication; no diff headers, no git apply>"
PATCH_HINT = "<PATCH: one unified diff of the complete fix, trailing newline included>"
PATCH_REASON_HINT = (
    "<PATCH_REASON: the concrete technical limitation or unsafe division that"
    " forbids a bounded suggestion>"
)
THREAD_ID_HINT = "<THREAD_ID: the id of the existing open thread that owns this fix>"
PATH_HINT = "<PATH: the changed file path at the reviewed head>"
SPLIT_RATIONALE_HINT = "<SPLIT_RATIONALE: why applying each part separately is safe>"

# What the reviewer-side and author-side variant catalogs look like. Each entry
# mirrors one branch of ``context.validate_finding_publications``: the block is
# formally complete (every required key present, right types), and exactly the
# judgment fields carry placeholders.
_REVIEWER_VARIANTS = ("general+patch", "line+suggestion", "line+patch", "existing_thread")
_AUTHOR_VARIANTS = ("local_fix+patch", "existing_thread")


def is_placeholder(value: object) -> bool:
    return isinstance(value, str) and (value == "" or PLACEHOLDER_RE.match(value) is not None)


def _base(finding_id: str, publication_type: str) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "type": publication_type,
        "path": None,
        "line": None,
        "old_line": None,
        "body": BODY_HINT,
        "fix_mode": "patch",
        "patch": PATCH_HINT,
    }


def _variant_block(finding_id: str, variant: str) -> dict[str, Any]:
    if variant == "general+patch":
        return {
            **_base(finding_id, "general"),
            "patch_reason": PATCH_REASON_HINT,
        }
    if variant == "local_fix+patch":
        # The author applies the fix locally; no publication position exists and
        # the patch is the validated local fix.
        return {
            **_base(finding_id, "local_fix"),
            "patch_reason": PATCH_REASON_HINT,
        }
    if variant == "line+suggestion":
        return {
            **_base(finding_id, "line"),
            "path": PATH_HINT,
            "body": (
                "<BODY: prose, then exactly one ```suggestion block with the bounded replacement>"
            ),
            "fix_mode": "suggestion",
            "patch": None,
        }
    if variant == "line+patch":
        return {
            **_base(finding_id, "line"),
            "path": PATH_HINT,
            "patch_reason": PATCH_REASON_HINT,
        }
    if variant == "existing_thread":
        return {
            **_base(finding_id, "existing_thread"),
            "body": "<BODY: prose continuing the existing thread naturally>",
            "fix_mode": "not_required",
            "patch": None,
            "thread_id": THREAD_ID_HINT,
        }
    raise ValueError(f"unknown publication variant {variant!r}")


def skeleton_variants(finding_id: str, role: str) -> list[dict[str, Any]]:
    """One formally complete block per valid (type, fix_mode) variant."""
    variants = _AUTHOR_VARIANTS if role == "author" else _REVIEWER_VARIANTS
    return [_variant_block(finding_id, variant) for variant in variants]


def publication_skeletons(findings: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    """Render the variant catalog for every finding, mechanical fields filled."""
    blocks: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
            continue
        blocks.extend(skeleton_variants(str(finding["id"]), role))
    return blocks


# The judgment fields of one skeleton row that carry marked placeholders. Line
# positions stay null in the skeleton on purpose: the position rules themselves
# document what belongs there, and a null position in a non-line variant is the
# required form, never a gap.
_TEXT_JUDGMENT_FIELDS = ("body", "patch", "patch_reason", "thread_id", "split_rationale")


def placeholder_fields(item: dict[str, Any]) -> list[str]:
    """The judgment fields of one publication row that still carry placeholders."""
    fields = [
        field for field in _TEXT_JUDGMENT_FIELDS if field in item and is_placeholder(item[field])
    ]
    if is_placeholder(item.get("path")):
        fields.append("path")
    if item.get("type") == "line" and item.get("line") is None and item.get("old_line") is None:
        fields.append("line")
    for part_index, part in enumerate(item.get("suggestions") or []):
        if isinstance(part, dict):
            fields.extend(
                f"suggestions[{part_index}].{field}"
                for field in ("path", "line", "body")
                if is_placeholder(part.get(field)) or part.get(field) is None
            )
    return fields
