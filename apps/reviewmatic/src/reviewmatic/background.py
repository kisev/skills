"""Background-file assembly with the OCR 8000-byte limit.

The manager authors the task baseline and the context sections; this module
renders them as one Markdown file, keeps the task first, and discloses every
cut it makes to fit the limit. The full context stays with the manager.
"""

from __future__ import annotations

from typing import Any, cast

BACKGROUND_LIMIT = 8000
ELLIPSIS = "…"


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _clamp(text: str, limit: int) -> str:
    """Fit text into ``limit`` bytes without splitting a UTF-8 sequence."""
    if _bytes(text) <= limit:
        return text
    budget = max(limit - _bytes(ELLIPSIS), 0)
    encoded = text.encode("utf-8")[:budget]
    while encoded:
        try:
            return encoded.decode("utf-8") + ELLIPSIS
        except UnicodeDecodeError:
            encoded = encoded[:-1]
    return ELLIPSIS


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast("list[object]", value) if isinstance(item, str) and item]


def _task_lines(
    task: dict[str, Any], goal_limit: int, item_limit: int, cuts: list[str]
) -> list[str]:
    goal = str(task.get("goal") or "").strip()
    criteria = _strings(task.get("acceptance_criteria"))
    constraints = _strings(task.get("constraints"))
    questions = _strings(task.get("open_questions"))
    lines = ["# Review background", "", "## Task goal", ""]
    if goal:
        clamped = _clamp(goal, goal_limit)
        if clamped != goal:
            cuts.append("task goal")
        lines.append(clamped)
    else:
        lines.append("Unknown: the task goal could not be established.")
    lines.extend(["", "## Acceptance criteria", ""])
    if criteria:
        for item in criteria:
            clamped = _clamp(item, item_limit)
            if clamped != item and "acceptance criteria" not in cuts:
                cuts.append("acceptance criteria")
            lines.append(f"- {clamped}")
    else:
        lines.append("- Unknown: no acceptance criteria were established.")
    if constraints:
        lines.extend(["", "## Constraints", ""])
        for item in constraints:
            clamped = _clamp(item, item_limit)
            if clamped != item and "constraints" not in cuts:
                cuts.append("constraints")
            lines.append(f"- {clamped}")
    if questions:
        lines.extend(["", "## Open questions", ""])
        for item in questions:
            clamped = _clamp(item, item_limit)
            if clamped != item and "open questions" not in cuts:
                cuts.append("open questions")
            lines.append(f"- {clamped}")
    return lines


def _section_block(section: dict[str, Any]) -> str:
    title = str(section.get("title") or "").strip()
    body = str(section.get("body") or "").strip()
    if not title or not body:
        return ""
    return f"\n## {title}\n\n{body}\n"


def _cut_trailer(cuts: list[str], limit: int) -> str:
    if not cuts:
        return ""
    return f"\n_Cut for the {limit}-byte background limit: {', '.join(cuts)}._\n"


def build_background(payload: dict[str, Any], limit: int = BACKGROUND_LIMIT) -> dict[str, Any]:
    """Render the background and fit it into ``limit`` bytes, task first."""
    if limit <= 0:
        raise ValueError("the background limit must be positive")
    task = payload.get("task")
    task = cast("dict[str, Any]", task) if isinstance(task, dict) else {}
    task_cuts: list[str] = []
    goal_limit = limit
    item_limit = limit
    task_text = "\n".join(_task_lines(task, goal_limit, item_limit, task_cuts)).rstrip("\n") + "\n"
    if _bytes(task_text) > limit:
        goal_limit = max(limit // 4, 0)
        item_limit = max(limit // 20, 0)
        while _bytes(task_text) > limit and (goal_limit > 0 or item_limit > 0):
            goal_limit = max(goal_limit - max(limit // 40, 1), 0)
            item_limit = max(item_limit - max(limit // 200, 1), 0)
            task_cuts.clear()
            task_text = (
                "\n".join(_task_lines(task, goal_limit, item_limit, task_cuts)).rstrip("\n") + "\n"
            )
        if _bytes(task_text) > limit:
            raise ValueError(
                "the task baseline alone exceeds the background limit; shorten the goal"
            )

    sections = [
        cast("dict[str, Any]", item)
        for item in cast("list[object]", payload.get("sections") or [])
        if isinstance(item, dict)
    ]
    included: list[int] = []
    text = task_text
    for index, section in enumerate(sections):
        block = _section_block(section)
        if not block:
            continue
        candidate = text + block
        if _bytes(candidate) <= limit:
            text = candidate
            included.append(index)
    while True:
        cut_titles = [
            str(section.get("title") or "").strip()
            for index, section in enumerate(sections)
            if index not in included and str(section.get("title") or "").strip()
        ]
        all_cuts = list(dict.fromkeys([*task_cuts, *cut_titles]))
        trailer = _cut_trailer(all_cuts, limit)
        if _bytes(text) + _bytes(trailer) <= limit:
            break
        if included:
            included.pop()
            text = task_text + "".join(_section_block(sections[index]) for index in included)
            continue
        raise ValueError("the background disclosure does not fit the background limit")
    result = text + trailer
    return {
        "status": "ok",
        "markdown": result,
        "bytes": _bytes(result),
        "limit": limit,
        "included_sections": [
            str(sections[index].get("title") or "").strip() for index in included
        ],
        "cuts": all_cuts,
        "external_mutations": False,
    }
