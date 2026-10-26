"""OpenCode configuration fragments, ported from the legacy config-setup contract.

The retired integration's behaviors that survive here (its REQ-F-514): only
absent preset values are added; user entries, comments, and formatting
outside the edit are preserved; an existing different value at a fragment
path is a conflict that is reported and never merged; repeated application
is a byte-identical no-op; every written document re-parses as JSONC.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

type JSONValue = str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None


class ConfigError(Exception):
    """An unreadable configuration document or a malformed fragment."""


class ConfigConflictError(ConfigError):
    """The document already carries a different value at a fragment path."""


@dataclass(frozen=True)
class FragmentEntry:
    """One preset value: ``key`` inside the object at ``path`` (root when empty)."""

    path: tuple[str, ...]
    key: str
    value: JSONValue

    def label(self) -> str:
        return ".".join((*self.path, self.key))


@dataclass(frozen=True)
class ConfigFragment:
    """A named set of preset values applied together or not at all."""

    name: str
    entries: tuple[FragmentEntry, ...]


@dataclass(frozen=True)
class Evaluation:
    """What applying a fragment to a document would do."""

    operations: tuple[str, ...]
    conflicts: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.conflicts

    @property
    def changes_needed(self) -> bool:
        return bool(self.operations)


def strip_comments(text: str) -> str:
    """Blank out // and /* */ comments outside strings, preserving positions."""
    output: list[str] = []
    index = 0
    length = len(text)
    in_string = False
    while index < length:
        char = text[index]
        if in_string:
            output.append(char)
            if char == "\\" and index + 1 < length:
                output.append(text[index + 1])
                index += 2
                continue
            if char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                output.append(" ")
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            end = text.find("*/", index + 2)
            end = length if end == -1 else end + 2
            for position in range(index, end):
                output.append("\n" if text[position] == "\n" else " ")
            index = end
            continue
        output.append(char)
        index += 1
    return "".join(output)


def parse_jsonc(text: str) -> JSONValue:
    """Parse a JSONC document (comments and trailing commas tolerated)."""
    stripped = strip_comments(text).strip()
    stripped = re.sub(r",\s*([}\]])", r"\1", stripped)
    if not stripped:
        raise ConfigError("configuration document is empty")
    try:
        value: JSONValue = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ConfigError(f"configuration document is not valid JSONC: {error}") from error
    return value


@dataclass(frozen=True)
class _Token:
    kind: str  # "string" | "literal" | "punct" | "comment" | "ws"
    start: int
    end: int
    text: str = ""


def _tokenize(text: str) -> list[_Token]:
    """Split JSONC text into tokens carrying original offsets."""
    tokens: list[_Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            start = index
            while index < length and text[index].isspace():
                index += 1
            tokens.append(_Token("ws", start, index))
            continue
        if char == '"':
            start = index
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                index += 1
            tokens.append(_Token("string", start, index, text[start:index]))
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            start = index
            while index < length and text[index] != "\n":
                index += 1
            tokens.append(_Token("comment", start, index))
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            start = index
            end = text.find("*/", index + 2)
            index = length if end == -1 else end + 2
            tokens.append(_Token("comment", start, index))
            continue
        if char in "{}[],:":
            tokens.append(_Token("punct", index, index + 1, char))
            index += 1
            continue
        start = index
        while index < length and not text[index].isspace() and text[index] not in '{}[],:"/':
            index += 1
        tokens.append(_Token("literal", start, index, text[start:index]))
    return tokens


@dataclass
class _Frame:
    kind: str  # "object" | "array"
    path: tuple[str, ...]
    open_start: int = 0
    pending_key: str | None = None
    first_child: int | None = None
    last_child_end: int | None = None


@dataclass(frozen=True)
class _Span:
    is_object: bool
    close_offset: int
    first_child: int | None
    last_child_end: int | None


def _structure(tokens: list[_Token]) -> dict[tuple[str, ...], _Span]:
    """Map every object and array path to its span in the original text."""
    significant = [token for token in tokens if token.kind not in ("ws", "comment")]
    spans: dict[tuple[str, ...], _Span] = {}
    stack: list[_Frame] = []
    index = 0
    while index < len(significant):
        token = significant[index]
        frame = stack[-1] if stack else None
        if token.text in ("{", "["):
            if frame is None:
                path: tuple[str, ...] = ()
            elif frame.kind == "object":
                if frame.pending_key is None:
                    raise ConfigError("object opens without a key where one is required")
                path = (*frame.path, frame.pending_key)
                frame.pending_key = None
            else:
                path = frame.path
            stack.append(
                _Frame(
                    kind="object" if token.text == "{" else "array",
                    path=path,
                    open_start=token.start,
                )
            )
            index += 1
            continue
        if token.text in ("}", "]"):
            closing = stack.pop()
            spans[closing.path] = _Span(
                is_object=closing.kind == "object",
                close_offset=token.start,
                first_child=closing.first_child,
                last_child_end=closing.last_child_end,
            )
            parent = stack[-1] if stack else None
            if parent is not None:
                _note_child(parent, closing.open_start, token.end)
            index += 1
            continue
        if frame is None:
            index += 1
            continue
        if (
            frame.kind == "object"
            and token.kind == "string"
            and index + 1 < len(significant)
            and significant[index + 1].text == ":"
        ):
            frame.pending_key = _decode_string(token)
        elif token.text not in {":", ","}:
            _note_child(frame, token.start, token.end)
        index += 1
    return spans


def _note_child(frame: _Frame, start: int, end: int) -> None:
    if frame.first_child is None:
        frame.first_child = start
    frame.last_child_end = end


def _decode_string(token: _Token) -> str:
    try:
        value = json.loads(token.text)
    except json.JSONDecodeError as error:  # pragma: no cover - tokenizer guarantees form
        raise ConfigError(f"unreadable string token: {error}") from error
    return value if isinstance(value, str) else ""


def _navigate(document: JSONValue, path: tuple[str, ...]) -> JSONValue | None:
    current: JSONValue = document
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def evaluate(text: str, fragment: ConfigFragment) -> Evaluation:
    """Report the operations and conflicts a fragment has against a document."""
    document = parse_jsonc(text)
    if not isinstance(document, dict):
        raise ConfigError("the configuration document root must be an object")
    operations: list[str] = []
    conflicts: list[str] = []
    for entry in fragment.entries:
        parent = _navigate(document, entry.path)
        if parent is None:
            operations.append(f"create {entry.label()}")
            continue
        if not isinstance(parent, dict):
            raise ConfigError(f"fragment path {'.'.join(entry.path)} is not an object")
        if entry.key in parent:
            if parent[entry.key] != entry.value:
                conflicts.append(f"{entry.label()}: present value differs from the fragment preset")
        else:
            operations.append(f"set {entry.label()}")
    return Evaluation(operations=tuple(operations), conflicts=tuple(conflicts))


def _render_entry(entry: FragmentEntry) -> str:
    return f'"{entry.key}": {json.dumps(entry.value, ensure_ascii=False)}'


def _indent_at(text: str, offset: int) -> str:
    line_start = text.rfind("\n", 0, offset) + 1
    indent = ""
    for char in text[line_start:offset]:
        if char not in " \t":
            break
        indent += char
    return indent


def apply_fragment(text: str, fragment: ConfigFragment) -> str:
    """Apply a fragment to a JSONC document, preserving everything else.

    Conflicts abort with :class:`ConfigConflictError`; a document needing no
    change comes back byte-identical. The comma after the last existing
    value lands before that value's trailing comment, and new lines land
    after it, so line comments stay attached to what they annotate.
    """
    evaluation = evaluate(text, fragment)
    if evaluation.conflicts:
        raise ConfigConflictError(
            f"fragment {fragment.name!r} conflicts: " + "; ".join(evaluation.conflicts)
        )
    if not evaluation.operations:
        return text

    document = parse_jsonc(text)
    tokens = _tokenize(text)
    spans = _structure(tokens)
    lines_by_container: dict[tuple[str, ...], list[str]] = {}
    trees_by_container: dict[tuple[str, ...], dict[str, JSONValue]] = {}
    for entry in fragment.entries:
        parent = _navigate(document, entry.path)
        if parent is None:
            ancestor = _deepest_ancestor(spans, entry.path)
            tree = trees_by_container.setdefault(ancestor, {})
            node: dict[str, JSONValue] = tree
            for key in entry.path[len(ancestor) :]:
                existing = node.get(key)
                child: dict[str, JSONValue] = existing if isinstance(existing, dict) else {}
                node[key] = child
                node = child
            node[entry.key] = entry.value
        elif not isinstance(parent, dict):
            raise ConfigError(f"fragment path {'.'.join(entry.path)} is not an object")
        elif entry.key not in parent:
            lines_by_container.setdefault(entry.path, []).append(_render_entry(entry))
    for ancestor, tree in trees_by_container.items():
        for key, subtree in tree.items():
            lines_by_container.setdefault(ancestor, []).append(
                f"{json.dumps(key, ensure_ascii=False)}: {json.dumps(subtree, ensure_ascii=False)}"
            )

    insertions: list[tuple[int, str]] = []
    for path, lines in lines_by_container.items():
        span = spans.get(path)
        if span is None:
            raise ConfigError(f"fragment container {'.'.join(path)} is missing from the document")
        if not span.is_object:
            raise ConfigError(f"fragment container {'.'.join(path)} is not an object")
        container_indent = _indent_at(text, span.close_offset)
        child_indent = _indent_at(text, span.first_child or span.close_offset)
        body = (",\n" + child_indent).join(lines)
        if span.last_child_end is not None:
            insertions.append((span.last_child_end, ","))
            content_end = _content_end(tokens, span.last_child_end, span.close_offset)
            insertions.append((content_end, f"\n{child_indent}{body}"))
        else:
            insertions.append((span.close_offset, f"\n{child_indent}{body}\n{container_indent}"))
    # Descending offsets keep earlier spans valid; at equal offsets the
    # comma lands closest to the anchor, so it ends up before the new lines.
    ordered = sorted(
        insertions,
        key=lambda item: (item[0], 0 if item[1] == "," else 1),
        reverse=True,
    )
    for offset, insertion in ordered:
        text = text[:offset] + insertion + text[offset:]

    result = parse_jsonc(text)
    if not isinstance(result, dict):
        raise ConfigError("merged configuration does not reparse as an object")
    for entry in fragment.entries:
        current = _navigate(result, entry.path)
        if not isinstance(current, dict) or current.get(entry.key) != entry.value:
            raise ConfigError(f"merged configuration lost the preset {entry.label()}")
    return text


def _content_end(tokens: list[_Token], last_child_end: int, close_offset: int) -> int:
    """End of the last content on the final line, including a trailing comment."""
    end = last_child_end
    for token in tokens:
        if token.kind == "comment" and last_child_end <= token.start < close_offset:
            end = max(end, token.end)
    return end


def _deepest_ancestor(
    spans: dict[tuple[str, ...], _Span], path: tuple[str, ...]
) -> tuple[str, ...]:
    """The longest prefix of ``path`` that exists as an object container."""
    for length in range(len(path), -1, -1):
        candidate = path[:length]
        span = spans.get(candidate)
        if span is not None and span.is_object:
            return candidate
    raise ConfigError(f"fragment path {'.'.join(path)} has no object ancestor in the document")
