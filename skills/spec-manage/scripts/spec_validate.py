#!/usr/bin/env python3
"""Validate mechanical invariants of a canonical specs tree."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = "spec-validate/v1"
Mode = Literal["check", "lifecycle", "help"]
CheckState = Literal["passed", "failed", "not_checked"]

REQUIRED_READMES = (
    "README.md",
    "requirements/README.md",
    "requirements/functional/README.md",
    "requirements/interfaces/README.md",
    "requirements/quality/README.md",
    "requirements/constraints/README.md",
    "architecture/README.md",
    "architecture/01-introduction-and-goals/README.md",
    "architecture/02-architecture-constraints/README.md",
    "architecture/03-context-and-scope/README.md",
    "architecture/04-solution-strategy/README.md",
    "architecture/05-building-block-view/README.md",
    "architecture/06-runtime-view/README.md",
    "architecture/07-deployment-view/README.md",
    "architecture/08-crosscutting-concepts/README.md",
    "architecture/09-architecture-decisions/README.md",
    "architecture/10-quality-requirements/README.md",
    "architecture/11-risks-and-technical-debt/README.md",
    "architecture/12-glossary/README.md",
)
MINIMUM_TOP_LEVEL = frozenset({"architecture", "requirements"})
ADR_DIRECTORY = PurePosixPath("architecture/09-architecture-decisions")
ADR_INDEX = ADR_DIRECTORY / "README.md"

LANGUAGE_DECLARATION = re.compile(r"^Canonical language:\s*(?P<language>\S(?:.*\S)?)\s*$")
EXTENSION_HEADING = "## Extension Index"
EXTENSION_ENTRY = re.compile(
    r"^- \[[^]]+\]\((?:\./)?(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)/README\.md\):\s+\S.*$"
)
REQUIREMENT_HEADING = re.compile(
    r"^### (?P<identifier>REQ-(?P<namespace>[FIQC])-(?P<number>[0-9]{3})) - \S.*$"
)
REQUIREMENT_CANDIDATE = re.compile(r"^#{1,6}\s+(?P<identifier>REQ-[^\s:]+)")
ADR_FILENAME = re.compile(r"^(?P<number>[0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_HEADING = re.compile(r"^# ADR-(?P<number>[0-9]{4}): \S.*$")
ADR_INDEX_ENTRY = re.compile(
    r"^- \[ADR-(?P<number>[0-9]{4}): [^]]+\]\((?P<target>[^)#]+\.md)(?:#[^)]*)?\)(?:\s+.*)?$"
)
INLINE_LINK = re.compile(r"(?<!!)\[[^]\n]+\]\((?P<target>[^()\s]+)\)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")

PLACEHOLDERS = (
    "PROJECT-LANGUAGE",
    "ADR-NNNN",
    "YYYY-MM-DD",
    "<existing-interface>.md",
    r"\[Short decision]",
    r"\[Describe the context, problem, and decision boundary.]",
    r"\[Decision driver.]",
    r"\[Considered alternative.]",
    r"\[Record the selected option and primary rationale.]",
    r"\[Positive consequence.]",
    r"\[Negative consequence or trade-off.]",
    r"\[REQ-\* or related ADR.]",
    r"\[Краткое решение]",
    r"\[Опишите контекст, проблему и границу решения.]",
    r"\[Фактор решения.]",
    r"\[Рассмотренная альтернатива.]",
    r"\[Зафиксируйте выбранный вариант и основное обоснование.]",
    r"\[Положительное последствие.]",
    r"\[Отрицательное последствие или компромисс.]",
    r"\[REQ-\* или связанный ADR.]",
)

USAGE = (
    "python3 -I -S -B scripts/spec_validate.py check --path <specs>\n"
    "python3 -I -S -B scripts/spec_validate.py lifecycle "
    "--baseline <previous-specs> --candidate <current-specs>"
)


class InputError(Exception):
    """An invocation, input, or execution error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    line: int
    column: int
    message: str

    def as_json(self) -> dict[str, object]:
        return {
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "message": self.message,
        }


@dataclass(frozen=True)
class Document:
    relative: PurePosixPath
    text: str

    @property
    def path(self) -> str:
        return self.relative.as_posix()

    def visible_lines(self) -> list[tuple[int, str]]:
        visible: list[tuple[int, str]] = []
        fence: str | None = None
        for number, line in enumerate(self.text.splitlines(), 1):
            marker = FENCE.match(line)
            if marker:
                token = marker.group(1)
                if fence is None:
                    fence = token[0]
                elif token[0] == fence:
                    fence = None
                continue
            if fence is None:
                visible.append((number, line))
        return visible


@dataclass(frozen=True)
class Snapshot:
    root: Path
    documents: dict[PurePosixPath, Document]
    entries: tuple[PurePosixPath, ...]
    directories: frozenset[PurePosixPath]


@dataclass(frozen=True)
class ParsedArguments:
    mode: Mode
    path: str | None = None
    baseline: str | None = None
    candidate: str | None = None


def parse_arguments(argv: list[str]) -> ParsedArguments:
    if not argv or argv in (["--help"], ["-h"]):
        return ParsedArguments("help")
    if argv[0] in {"--help", "-h"}:
        raise InputError("INVOCATION", "--help does not accept other arguments")
    mode = argv[0]
    if mode == "check":
        values = parse_options(argv[1:], {"--path"})
        return ParsedArguments("check", path=values["--path"])
    if mode == "lifecycle":
        values = parse_options(argv[1:], {"--baseline", "--candidate"})
        return ParsedArguments(
            "lifecycle", baseline=values["--baseline"], candidate=values["--candidate"]
        )
    raise InputError("INVOCATION", f"unknown mode: {mode}")


def parse_options(arguments: list[str], required: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option in {"--help", "-h"}:
            raise InputError("INVOCATION", "use top-level --help without a mode")
        if option not in required:
            raise InputError("INVOCATION", f"unknown option: {option}")
        if option in values:
            raise InputError("INVOCATION", f"duplicate option: {option}")
        index += 1
        if index >= len(arguments) or arguments[index].startswith("--"):
            raise InputError("INVOCATION", f"missing value for {option}")
        values[option] = arguments[index]
        index += 1
    missing = sorted(required - values.keys())
    if missing:
        raise InputError("INVOCATION", f"missing required option: {missing[0]}")
    return values


def safe_root(value: str, label: str) -> Path:
    if not value or "\x00" in value:
        raise InputError("INVALID_PATH", f"{label} must be a non-empty filesystem path")
    root = Path(value)
    try:
        metadata = root.lstat()
    except OSError:
        raise InputError("INVALID_PATH", f"cannot access {label}") from None
    if stat.S_ISLNK(metadata.st_mode):
        raise InputError("UNSAFE_PATH", f"{label} must not be a symbolic link")
    if not stat.S_ISDIR(metadata.st_mode):
        raise InputError("INVALID_PATH", f"{label} must be a directory")
    try:
        return root.resolve(strict=True)
    except OSError:
        raise InputError("INVALID_PATH", f"cannot resolve {label}") from None


def load_snapshot(value: str, label: str) -> Snapshot:
    root = safe_root(value, label)
    documents: dict[PurePosixPath, Document] = {}
    entries: list[PurePosixPath] = []
    directory_entries: set[PurePosixPath] = set()
    try:
        for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            relative_directory = current_path.relative_to(root)
            directories.sort()
            filenames.sort()
            for name in directories:
                path = current_path / name
                metadata = path.lstat()
                relative = PurePosixPath((relative_directory / name).as_posix())
                if stat.S_ISLNK(metadata.st_mode):
                    raise InputError("UNSAFE_PATH", f"symbolic link in {label}: {relative}")
                if not stat.S_ISDIR(metadata.st_mode):
                    raise InputError("UNSAFE_PATH", f"non-directory entry in {label}: {relative}")
                entries.append(relative)
                directory_entries.add(relative)
            for name in filenames:
                path = current_path / name
                metadata = path.lstat()
                relative = PurePosixPath((relative_directory / name).as_posix())
                if stat.S_ISLNK(metadata.st_mode):
                    raise InputError("UNSAFE_PATH", f"symbolic link in {label}: {relative}")
                if not stat.S_ISREG(metadata.st_mode):
                    raise InputError("UNSAFE_PATH", f"non-regular file in {label}: {relative}")
                try:
                    resolved = path.resolve(strict=True)
                    resolved.relative_to(root)
                    if resolved != path:
                        raise InputError(
                            "UNSAFE_PATH", f"symbolic path component in {label}: {relative}"
                        )
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError as error:
                    raise InputError(
                        "INVALID_UTF8",
                        f"file is not UTF-8 in {label}: {relative}:{error.start + 1}",
                    ) from None
                except ValueError:
                    raise InputError("UNSAFE_PATH", f"file escapes {label}: {relative}") from None
                except OSError:
                    raise InputError(
                        "INPUT_READ", f"cannot read file in {label}: {relative}"
                    ) from None
                entries.append(relative)
                if path.suffix.lower() == ".md":
                    documents[relative] = Document(relative, text)
    except InputError:
        raise
    except OSError:
        raise InputError("INPUT_READ", f"cannot traverse {label}") from None
    return Snapshot(root, documents, tuple(sorted(entries)), frozenset(directory_entries))


def add_finding(
    findings: list[Finding],
    code: str,
    path: str,
    message: str,
    line: int = 0,
    column: int = 0,
) -> None:
    findings.append(Finding(code, path, line, column, message))


def check_required_files(snapshot: Snapshot, findings: list[Finding]) -> None:
    entries = set(snapshot.entries)
    for required in REQUIRED_READMES:
        path = PurePosixPath(required)
        if path not in entries:
            add_finding(
                findings, "SNAPSHOT_REQUIRED_FILE_MISSING", required, "required README is missing"
            )


def check_language(snapshot: Snapshot, findings: list[Finding]) -> None:
    document = snapshot.documents.get(PurePosixPath("README.md"))
    if document is None:
        return
    declarations: list[tuple[int, str]] = []
    candidates: list[tuple[int, str]] = []
    for line_number, line in document.visible_lines():
        if line.startswith("Canonical language:"):
            candidates.append((line_number, line))
        match = LANGUAGE_DECLARATION.fullmatch(line)
        if match:
            declarations.append((line_number, match.group("language").rstrip(".")))
    if not candidates:
        add_finding(
            findings,
            "SNAPSHOT_LANGUAGE_DECLARATION_MISSING",
            document.path,
            "exactly one non-empty 'Canonical language:' declaration is required",
        )
        return
    if len(candidates) != 1 or len(declarations) != 1:
        declaration_line = candidates[1][0] if len(candidates) > 1 else candidates[0][0]
        add_finding(
            findings,
            "SNAPSHOT_LANGUAGE_DECLARATION_AMBIGUOUS",
            document.path,
            "canonical language declaration must occur exactly once and be non-empty",
            declaration_line,
            1,
        )
        return
    line_number, language = declarations[0]
    if not language.strip() or language.strip() == "PROJECT-LANGUAGE":
        add_finding(
            findings,
            "SNAPSHOT_LANGUAGE_DECLARATION_EMPTY",
            document.path,
            "canonical language must be a concrete non-empty value",
            line_number,
            len("Canonical language: ") + 1,
        )


def top_level_extensions(snapshot: Snapshot) -> set[str]:
    return {
        entry.name
        for entry in snapshot.directories
        if len(entry.parts) == 1 and entry.as_posix() not in MINIMUM_TOP_LEVEL
    }


def check_extensions(snapshot: Snapshot, findings: list[Finding]) -> None:
    extensions = top_level_extensions(snapshot)
    document = snapshot.documents.get(PurePosixPath("README.md"))
    if document is None:
        return
    headings = [
        (number, line) for number, line in document.visible_lines() if line == EXTENSION_HEADING
    ]
    if len(headings) > 1:
        add_finding(
            findings,
            "SNAPSHOT_EXTENSION_INDEX_AMBIGUOUS",
            document.path,
            "Extension Index heading must occur at most once",
            headings[1][0],
            1,
        )
    indexed: dict[str, list[int]] = {}
    if headings:
        start = headings[0][0]
        for line_number, line in document.visible_lines():
            if line_number <= start:
                continue
            if line.startswith(("# ", "## ")):
                break
            if not line.startswith("- "):
                continue
            match = EXTENSION_ENTRY.fullmatch(line)
            if match is None:
                add_finding(
                    findings,
                    "SNAPSHOT_EXTENSION_INDEX_ENTRY_INVALID",
                    document.path,
                    "extension entry must link <name>/README.md and include a boundary after ': '",
                    line_number,
                    1,
                )
                continue
            indexed.setdefault(match.group("name"), []).append(line_number)
    for name in sorted(extensions - indexed.keys()):
        add_finding(
            findings,
            "SNAPSHOT_EXTENSION_NOT_INDEXED",
            "README.md",
            f"top-level extension is not indexed: {name}",
        )
    for name in sorted(indexed.keys() - extensions):
        add_finding(
            findings,
            "SNAPSHOT_EXTENSION_INDEX_STALE",
            "README.md",
            f"Extension Index names no top-level section: {name}",
            indexed[name][0],
            1,
        )
    for name, lines in sorted(indexed.items()):
        for duplicate_line in lines[1:]:
            add_finding(
                findings,
                "SNAPSHOT_EXTENSION_INDEX_DUPLICATE",
                "README.md",
                f"Extension Index repeats top-level section: {name}",
                duplicate_line,
                1,
            )


def requirement_declarations(
    snapshot: Snapshot, findings: list[Finding] | None = None
) -> dict[str, tuple[str, int]]:
    declarations: dict[str, tuple[str, int]] = {}
    for relative, document in sorted(snapshot.documents.items()):
        for line_number, line in document.visible_lines():
            candidate = REQUIREMENT_CANDIDATE.match(line)
            if candidate is None:
                continue
            match = REQUIREMENT_HEADING.fullmatch(line)
            if match is None:
                if findings is not None:
                    add_finding(
                        findings,
                        "SNAPSHOT_REQUIREMENT_DECLARATION_INVALID",
                        relative.as_posix(),
                        "requirement heading must match '### REQ-F/I/Q/C-NNN - Title'",
                        line_number,
                        1,
                    )
                continue
            identifier = match.group("identifier")
            previous = declarations.get(identifier)
            if previous is not None and findings is not None:
                add_finding(
                    findings,
                    "SNAPSHOT_REQUIREMENT_DUPLICATE",
                    relative.as_posix(),
                    f"requirement identifier duplicates {previous[0]}:{previous[1]}: {identifier}",
                    line_number,
                    5,
                )
            else:
                declarations[identifier] = (relative.as_posix(), line_number)
    return declarations


def adr_declarations(
    snapshot: Snapshot, findings: list[Finding] | None = None
) -> dict[str, tuple[str, int]]:
    declarations: dict[str, tuple[str, int]] = {}
    prefix = ADR_DIRECTORY.as_posix() + "/"
    for entry in snapshot.entries:
        path = entry.as_posix()
        if not path.startswith(prefix) or len(entry.parts) != len(ADR_DIRECTORY.parts) + 1:
            continue
        if entry.name == "README.md":
            continue
        match = ADR_FILENAME.fullmatch(entry.name)
        if match is None:
            if findings is not None:
                add_finding(
                    findings,
                    "SNAPSHOT_ADR_FILENAME_INVALID",
                    path,
                    "ADR filename must match NNNN-lowercase-hyphenated-title.md",
                )
            continue
        identifier = f"ADR-{match.group('number')}"
        document = snapshot.documents.get(entry)
        if document is None:
            if findings is not None:
                add_finding(
                    findings, "SNAPSHOT_ADR_FILE_INVALID", path, "ADR must be a Markdown file"
                )
            continue
        lines = document.text.splitlines()
        heading = ADR_HEADING.fullmatch(lines[0]) if lines else None
        if heading is None:
            if findings is not None:
                add_finding(
                    findings,
                    "SNAPSHOT_ADR_HEADING_INVALID",
                    path,
                    "ADR first line must match '# ADR-NNNN: Title'",
                    1,
                    1,
                )
        elif heading.group("number") != match.group("number") and findings is not None:
            add_finding(
                findings,
                "SNAPSHOT_ADR_HEADING_MISMATCH",
                path,
                "ADR heading number does not match filename",
                1,
                3,
            )
        previous = declarations.get(identifier)
        if previous is not None and findings is not None:
            add_finding(
                findings,
                "SNAPSHOT_ADR_DUPLICATE",
                path,
                f"ADR identifier duplicates {previous[0]}: {identifier}",
                1,
                3,
            )
        else:
            declarations[identifier] = (path, 1)
    return declarations


def check_adr_index(
    snapshot: Snapshot, adrs: dict[str, tuple[str, int]], findings: list[Finding]
) -> None:
    document = snapshot.documents.get(ADR_INDEX)
    if document is None:
        return
    indexed: dict[str, list[tuple[str, int]]] = {}
    for line_number, line in document.visible_lines():
        if not line.startswith("- [ADR-"):
            continue
        match = ADR_INDEX_ENTRY.fullmatch(line)
        if match is None:
            add_finding(
                findings,
                "SNAPSHOT_ADR_INDEX_ENTRY_INVALID",
                document.path,
                "ADR index entry must link an ADR-NNNN label to a relative Markdown file",
                line_number,
                1,
            )
            continue
        identifier = f"ADR-{match.group('number')}"
        indexed.setdefault(identifier, []).append((match.group("target"), line_number))
    for identifier, (path, _) in sorted(adrs.items()):
        expected = PurePosixPath(path).name
        entries = indexed.get(identifier, [])
        if not entries:
            add_finding(
                findings,
                "SNAPSHOT_ADR_NOT_INDEXED",
                ADR_INDEX.as_posix(),
                f"ADR index does not contain {identifier}",
            )
        for target, index_line in entries:
            if target != expected:
                add_finding(
                    findings,
                    "SNAPSHOT_ADR_INDEX_TARGET_MISMATCH",
                    ADR_INDEX.as_posix(),
                    f"{identifier} index target must be {expected}",
                    index_line,
                    1,
                )
    for identifier, entries in sorted(indexed.items()):
        if identifier not in adrs:
            add_finding(
                findings,
                "SNAPSHOT_ADR_INDEX_STALE",
                ADR_INDEX.as_posix(),
                f"ADR index names no ADR file: {identifier}",
                entries[0][1],
                1,
            )
        for _, duplicate_line in entries[1:]:
            add_finding(
                findings,
                "SNAPSHOT_ADR_INDEX_DUPLICATE",
                ADR_INDEX.as_posix(),
                f"ADR index repeats {identifier}",
                duplicate_line,
                1,
            )


def check_links(snapshot: Snapshot, findings: list[Finding]) -> None:
    for relative, document in sorted(snapshot.documents.items()):
        for line_number, line in document.visible_lines():
            for match in INLINE_LINK.finditer(line):
                raw_target = match.group("target")
                parsed = urlsplit(raw_target)
                if parsed.scheme or parsed.netloc:
                    continue
                target_text = unquote(parsed.path)
                if not target_text:
                    continue
                if "\x00" in target_text or "\\" in target_text or target_text.startswith("/"):
                    add_finding(
                        findings,
                        "SNAPSHOT_LINK_PATH_UNSAFE",
                        relative.as_posix(),
                        f"local link is not a safe relative POSIX path: {raw_target}",
                        line_number,
                        match.start("target") + 1,
                    )
                    continue
                combined = relative.parent / PurePosixPath(target_text)
                normalized = PurePosixPath(os.path.normpath(combined.as_posix()))
                if normalized.is_absolute() or normalized.parts[0] == "..":
                    add_finding(
                        findings,
                        "SNAPSHOT_LINK_OUTSIDE_ROOT",
                        relative.as_posix(),
                        f"local link escapes the specs root: {raw_target}",
                        line_number,
                        match.start("target") + 1,
                    )
                    continue
                target = snapshot.root.joinpath(*normalized.parts)
                try:
                    target.relative_to(snapshot.root)
                    metadata = target.lstat()
                except (OSError, ValueError):
                    add_finding(
                        findings,
                        "SNAPSHOT_LINK_TARGET_MISSING",
                        relative.as_posix(),
                        f"local link target does not exist: {raw_target}",
                        line_number,
                        match.start("target") + 1,
                    )
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    add_finding(
                        findings,
                        "SNAPSHOT_LINK_TARGET_INVALID",
                        relative.as_posix(),
                        f"local link target is not a regular file: {raw_target}",
                        line_number,
                        match.start("target") + 1,
                    )


def check_placeholders(snapshot: Snapshot, findings: list[Finding]) -> None:
    for relative, document in sorted(snapshot.documents.items()):
        for line_number, line in enumerate(document.text.splitlines(), 1):
            for placeholder in PLACEHOLDERS:
                column = line.find(placeholder)
                if column >= 0:
                    add_finding(
                        findings,
                        "SNAPSHOT_TEMPLATE_PLACEHOLDER",
                        relative.as_posix(),
                        f"unreplaced template placeholder: {placeholder}",
                        line_number,
                        column + 1,
                    )


def validate_snapshot(snapshot: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    check_required_files(snapshot, findings)
    check_language(snapshot, findings)
    check_extensions(snapshot, findings)
    requirement_declarations(snapshot, findings)
    adrs = adr_declarations(snapshot, findings)
    check_adr_index(snapshot, adrs, findings)
    check_links(snapshot, findings)
    check_placeholders(snapshot, findings)
    return sorted(findings)


def identifier_number(identifier: str) -> int:
    return int(identifier.rsplit("-", 1)[1])


def validate_lifecycle(baseline: Snapshot, candidate: Snapshot) -> list[Finding]:
    findings: list[Finding] = []
    baseline_requirements = requirement_declarations(baseline)
    candidate_requirements = requirement_declarations(candidate)
    baseline_adrs = adr_declarations(baseline)
    candidate_adrs = adr_declarations(candidate)

    for identifier, (path, line) in sorted(baseline_requirements.items()):
        if identifier not in candidate_requirements:
            add_finding(
                findings,
                "LIFECYCLE_REQUIREMENT_REMOVED",
                path,
                f"candidate does not preserve baseline requirement: {identifier}",
                line,
                5,
            )
    maxima: dict[str, int] = {}
    for identifier in baseline_requirements:
        namespace = identifier.split("-")[1]
        maxima[namespace] = max(maxima.get(namespace, -1), identifier_number(identifier))
    for identifier, (path, line) in sorted(candidate_requirements.items()):
        if identifier in baseline_requirements:
            continue
        namespace = identifier.split("-")[1]
        maximum = maxima.get(namespace, -1)
        if identifier_number(identifier) <= maximum:
            add_finding(
                findings,
                "LIFECYCLE_REQUIREMENT_NUMBER_REUSED",
                path,
                f"new {namespace} requirement number must be greater than baseline maximum {maximum:03d}",
                line,
                5,
            )

    for identifier, (path, line) in sorted(baseline_adrs.items()):
        if identifier not in candidate_adrs:
            add_finding(
                findings,
                "LIFECYCLE_ADR_REMOVED",
                path,
                f"candidate does not preserve baseline ADR: {identifier}",
                line,
                3,
            )
    maximum_adr = max((identifier_number(identifier) for identifier in baseline_adrs), default=-1)
    for identifier, (path, line) in sorted(candidate_adrs.items()):
        if identifier not in baseline_adrs and identifier_number(identifier) <= maximum_adr:
            add_finding(
                findings,
                "LIFECYCLE_ADR_NUMBER_REUSED",
                path,
                f"new ADR number must be greater than baseline maximum {maximum_adr:04d}",
                line,
                3,
            )
    return sorted(findings)


def result_document(
    mode: Mode,
    snapshot: CheckState,
    lifecycle: CheckState,
    findings: list[Finding],
    errors: list[dict[str, str]],
) -> dict[str, object]:
    if errors:
        status = "error"
    elif findings:
        status = "invalid"
    else:
        status = "valid"
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "status": status,
        "checks": {"snapshot": snapshot, "lifecycle": lifecycle},
        "findings": [finding.as_json() for finding in findings],
        "errors": errors,
    }


def emit(document: dict[str, object]) -> None:
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    sys.stdout.buffer.write(payload)


def run(arguments: ParsedArguments) -> int:
    if arguments.mode == "help":
        document = result_document("help", "not_checked", "not_checked", [], [])
        document["usage"] = USAGE
        emit(document)
        return 0
    if arguments.mode == "check":
        if arguments.path is None:
            raise InputError("INVOCATION", "check requires --path")
        snapshot = load_snapshot(arguments.path, "path")
        findings = validate_snapshot(snapshot)
        state: CheckState = "failed" if findings else "passed"
        emit(result_document("check", state, "not_checked", findings, []))
        return 1 if findings else 0
    if arguments.baseline is None or arguments.candidate is None:
        raise InputError("INVOCATION", "lifecycle requires --baseline and --candidate")
    baseline = load_snapshot(arguments.baseline, "baseline")
    candidate = load_snapshot(arguments.candidate, "candidate")
    findings = validate_lifecycle(baseline, candidate)
    state = "failed" if findings else "passed"
    emit(result_document("lifecycle", "not_checked", state, findings, []))
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
        return run(arguments)
    except InputError as error:
        emit(
            result_document(
                "help",
                "not_checked",
                "not_checked",
                [],
                [{"code": error.code, "message": str(error)}],
            )
        )
        return 2
    except (OSError, RuntimeError):
        emit(
            result_document(
                "help",
                "not_checked",
                "not_checked",
                [],
                [{"code": "EXECUTION", "message": "validator execution failed"}],
            )
        )
        return 2
    except Exception:
        emit(
            result_document(
                "help",
                "not_checked",
                "not_checked",
                [],
                [{"code": "EXECUTION", "message": "unexpected validator failure"}],
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
