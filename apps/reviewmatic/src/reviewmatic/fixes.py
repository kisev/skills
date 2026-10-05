"""Suggestion-block fixes: bodies, ranges, and whole-file patch synthesis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from reviewmatic.portable.portable_gitlab import contract

SUGGESTION_RE = r"^```suggestion(?::-(?P<before>[0-9]+)\+(?P<after>[0-9]+))?\n(?P<body>[\s\S]*?)\n```[ \t]*(?:\n|$)"


class SuggestionPart:
    __slots__ = ("body", "line", "path")

    def __init__(self, path: str, line: int, body: str) -> None:
        self.path = path
        self.line = line
        self.body = body


def _as_part(value: dict[str, Any]) -> SuggestionPart:
    return SuggestionPart(str(value["path"]), int(value["line"]), str(value["body"]))


# A part with its own explanation is a complete publication body. Bare legacy
# blocks retain the shared explanation so old guided drafts remain readable.
def suggestion_body(shared: str, part: SuggestionPart) -> str:
    prose = re.sub(
        SUGGESTION_RE,
        "",
        part.body,
        flags=re.MULTILINE,
    ).strip()
    return part.body if prose else f"{shared}\n\n{part.body}"


def suggestion_parts(fix: dict[str, Any]) -> list[SuggestionPart]:
    if "suggestions" in fix:
        suggestions = fix["suggestions"]
        if (
            not isinstance(suggestions, list)
            or len(suggestions) == 0
            or len(suggestions) > 50
            or not all(
                isinstance(part, dict)
                and ",".join(sorted(part)) == "body,line,path"
                and contract.nonempty_string(part.get("path"))
                and isinstance(part.get("line"), int)
                and not isinstance(part.get("line"), bool)
                and int(part["line"]) > 0
                and contract.nonempty_string(part.get("body"))
                for part in suggestions
            )
        ):
            raise contract.WorkflowError("suggestions requires bounded path/line/body records")
        if len(suggestions) > 1 and not contract.nonempty_string(fix.get("split_rationale")):
            raise contract.WorkflowError(
                "Related suggestions require split_rationale explaining safe partial application"
            )
        return [_as_part(part) for part in suggestions]
    return [
        SuggestionPart(
            str(fix["path"]),
            int(fix["line"]),
            str(fix["body"]),
        )
    ]


class SuggestionRange:
    __slots__ = ("after", "before", "replacement")

    def __init__(self, before: int, after: int, replacement: list[str]) -> None:
        self.before = before
        self.after = after
        self.replacement = replacement


def suggestion_range(body: str) -> SuggestionRange:
    matches = list(re.finditer(SUGGESTION_RE, body, flags=re.MULTILINE))
    if len(matches) != 1:
        raise contract.WorkflowError(
            "Each suggestion part requires exactly one block: ```suggestion or "
            "```suggestion:-N+M, newline, replacement, newline, ```"
        )
    match = matches[0]
    before = int(match.group("before") or 0)
    after = int(match.group("after") or 0)
    if before > 100 or after > 100:
        raise contract.WorkflowError(
            f"Suggestion range -{before}+{after} exceeds the supported limit; "
            f"expected N and M in 0..100 in suggestion:-N+M"
        )
    replacement_text = match.group("body")
    return SuggestionRange(
        before, after, [] if replacement_text == "" else replacement_text.split("\n")
    )


class _Edit:
    __slots__ = ("after", "before", "line", "part", "path", "replacement")

    def __init__(self, path: str, part: SuggestionPart, span: SuggestionRange) -> None:
        self.path = path
        self.part = part
        self.before = span.before
        self.after = span.after
        self.replacement = span.replacement

    @property
    def start(self) -> int:
        return self.part.line - self.before

    @property
    def end(self) -> int:
        return self.part.line + self.after


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


# Build the complete result against one revision, not a sequence of drifting line numbers.
def suggestions_patch(repo_root: str, head_sha: str, parts: list[SuggestionPart]) -> str:
    groups: dict[str, list[SuggestionPart]] = {}
    for part in parts:
        if part.path.startswith("/") or ".." in part.path.split("/"):
            raise contract.WorkflowError("Suggestion path escapes the repository")
        groups.setdefault(part.path, []).append(part)
    patch = ""
    for path, values in groups.items():
        entry = str(contract.git_read(Path(repo_root), "ls-tree", head_sha, "--", path))
        if not entry.startswith("100644 blob ") and not entry.startswith("100755 blob "):
            raise contract.WorkflowError("Suggestion requires a regular existing file")
        source = str(contract.git_read(Path(repo_root), "show", f"{head_sha}:{path}"))
        trailing_newline = source.endswith("\n")
        original = (source[:-1] if trailing_newline else source).split("\n")
        edits = sorted(
            (_Edit(path, part, suggestion_range(part.body)) for part in values),
            key=lambda edit: edit.start,
        )
        end = 0
        for edit in edits:
            if edit.start < 1 or edit.end > len(original) or edit.start <= end:
                raise contract.WorkflowError(
                    f"Related suggestion ranges overlap or escape the reviewed file: "
                    f"{path}:{edit.start}..{edit.end}; expected a non-overlapping range "
                    f"within 1..{len(original)} on the exact head (anchor line "
                    f"{edit.part.line}, suggestion:-{edit.before}+{edit.after})"
                )
            end = edit.end
        updated = list(original)
        for edit in reversed(edits):
            updated[edit.start - 1 : edit.part.line + edit.after] = edit.replacement
        if "\n".join(updated) == "\n".join(original):
            raise contract.WorkflowError("Suggestion does not change the reviewed file")
        removals = "".join(
            f"-{line}\n"
            + (
                "\\ No newline at end of file\n"
                if not trailing_newline and index == len(original) - 1
                else ""
            )
            for index, line in enumerate(original)
        )
        additions = "".join(
            f"+{line}\n"
            + (
                "\\ No newline at end of file\n"
                if not trailing_newline and index == len(updated) - 1
                else ""
            )
            for index, line in enumerate(updated)
        )
        patch += (
            f"diff --git {_json(f'a/{path}')} {_json(f'b/{path}')}\n"
            f"--- {_json(f'a/{path}')}\n"
            f"+++ {_json(f'b/{path}')}\n"
            f"@@ -1,{len(original)} +{0 if len(updated) == 0 else 1},{len(updated)} @@\n"
            + removals
            + additions
        )
    return patch
