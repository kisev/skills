#!/usr/bin/env python3
"""Validate English-default public documentation and Russian counterparts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)#]+)(?:#[^)]+)?\)")
FENCE = re.compile(r"^```([^\n]*)$", re.MULTILINE)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
CODE = re.compile(r"`([^`\n]+)`")
COMMAND = re.compile(
    r"^\s*((?:npx|npm|uv|python3?|task|mise|lefthook|git|node)\b[^\n]*)", re.MULTILINE
)
PATH = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


class LocaleError(Exception):
    pass


def load_manifest(root: Path = ROOT) -> dict[str, object]:
    try:
        manifest = json.loads((root / "shared/locale-manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocaleError(f"cannot read locale manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise LocaleError("locale manifest version must be 1")
    if not all(isinstance(manifest.get(key), list) for key in ("pairs", "patterns", "neutral")):
        raise LocaleError("locale manifest pairs, patterns, and neutral must be lists")
    return manifest


def _pair(value: object, label: str) -> tuple[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(value.get(key), str) for key in ("en", "ru")
    ):
        raise LocaleError(f"{label} must contain en and ru paths")
    return value["en"], value["ru"]


def _records(root: Path, manifest: dict[str, object]) -> list[tuple[str, str, bool]]:
    pairs = cast(list[object], manifest["pairs"])
    patterns = cast(list[object], manifest["patterns"])
    records = [(*_pair(item, f"pair {index}"), True) for index, item in enumerate(pairs)]
    for index, item in enumerate(patterns):
        english, russian = _pair(item, f"pattern {index}")
        if "*" not in english or "/ru/" not in russian:
            raise LocaleError("patterns require an English glob and Russian /ru/ path")
        exception = item.get("language_link_exception") if isinstance(item, dict) else None
        if exception is not None and (not isinstance(exception, str) or not exception.strip()):
            raise LocaleError("language link exception must be a non-empty justification")
        for path in root.glob(english):
            if path.is_file() and "/ru/" not in path.relative_to(root).as_posix():
                relative = path.relative_to(root).as_posix()
                records.append(
                    (
                        relative,
                        relative.replace("templates/", "templates/ru/", 1),
                        exception is None,
                    )
                )
    return records


def _machine_text(text: str) -> str:
    """Return code-bearing text without treating translated prose as machine data."""
    fenced = "\n".join(
        match.group(1)
        for match in re.finditer(r"^```[^\n]*\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    )
    inline = "\n".join(CODE.findall(text))
    return f"{fenced}\n{inline}"


def _tokens(text: str) -> set[str]:
    machine_text = _machine_text(text)
    tokens = set(COMMAND.findall(machine_text))
    tokens.update(
        value
        for value in CODE.findall(text)
        if value.startswith("--") or "=" in value or "_" in value
    )
    tokens.update(PATH.findall(machine_text))
    return tokens


def _headings(text: str) -> list[int]:
    return [len(match.group(1)) for match in HEADING.finditer(text)]


def _block_signature(text: str) -> list[str]:
    """Describe translatable Markdown structure without comparing prose or wrapping."""
    signature: list[str] = []
    paragraph = False
    quote = False
    table_rows = 0
    table_columns: int | None = None
    fence: str | None = None
    list_item = False

    def flush() -> None:
        nonlocal paragraph, quote, table_rows, table_columns
        if paragraph:
            signature.append("paragraph")
            paragraph = False
        if quote:
            signature.append("quote")
            quote = False
        if table_rows:
            signature.append(f"table:{table_rows}:{table_columns}")
            table_rows = 0
            table_columns = None

    for line in text.splitlines():
        stripped = line.strip()
        fence_match = re.fullmatch(r"```([^`]*)", stripped)
        if fence_match:
            flush()
            if fence is None:
                fence = fence_match.group(1)
                signature.append(f"fence:{fence}")
            else:
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"^(#{1,6})\s+", line)
        if heading:
            flush()
            signature.append(f"heading:{len(heading.group(1))}")
            continue
        if TABLE_ROW.fullmatch(line):
            if paragraph or quote:
                flush()
            columns = len([cell for cell in stripped.strip("|").split("|")])
            if table_columns is None:
                table_columns = columns
            elif table_columns != columns:
                signature.append("table:invalid")
            table_rows += 1
            continue
        if table_rows:
            flush()
        if LIST_ITEM.match(line):
            if paragraph or quote:
                flush()
            marker = "ordered-item" if re.match(r"^\s*\d+[.)]\s+", line) else "unordered-item"
            signature.append(marker)
            list_item = True
            continue
        if list_item and line[:1].isspace() and stripped:
            continue
        list_item = False
        if stripped.startswith(">"):
            if paragraph:
                flush()
            quote = True
            continue
        if not stripped:
            list_item = False
            flush()
            continue
        paragraph = True
    flush()
    if fence is not None:
        signature.append("fence:unclosed")
    return signature


def _public_documents(root: Path) -> set[str]:
    public = {
        path
        for path in (
            "README.md",
            "README.ru.md",
            "CONTRIBUTING.md",
            "CONTRIBUTING.ru.md",
            "SECURITY.md",
            "CHANGELOG.md",
        )
        if (root / path).is_file()
    }
    docs = root / "docs"
    if docs.is_dir():
        public.update(path.relative_to(root).as_posix() for path in docs.rglob("*.md"))
    packages = root / "packages"
    if packages.is_dir():
        public.update(path.relative_to(root).as_posix() for path in packages.glob("*/README*.md"))
    return public


def _links(root: Path, source: str, text: str) -> set[str]:
    links = set()
    for raw in LINK.findall(text):
        if "://" in raw or raw.startswith(("/", "#", "mailto:")):
            continue
        resolved = (root / source).parent.joinpath(raw).resolve()
        try:
            relative = resolved.relative_to(root.resolve()).as_posix()
        except ValueError as error:
            raise LocaleError(f"relative link escapes repository: {source}: {raw}") from error
        if not resolved.exists():
            raise LocaleError(f"relative link does not resolve: {source}: {raw}")
        links.add(relative)
    return links


def validate(root: Path = ROOT, built: Path | None = None) -> int:
    manifest = load_manifest(root)
    records = _records(root, manifest)
    paths = [path for english, russian, _ in records for path in (english, russian)]
    if len(paths) != len(set(paths)):
        raise LocaleError("duplicate translated path")
    neutral = cast(list[str], manifest["neutral"])
    if len(neutral) != len(set(neutral)):
        raise LocaleError("neutral paths must be unique")
    for english, russian, require_language_link in records:
        en_file, ru_file = root / english, root / russian
        if not en_file.is_file() or not ru_file.is_file():
            raise LocaleError(f"missing documentation pair: {english}, {russian}")
        en_text, ru_text = en_file.read_text(encoding="utf-8"), ru_file.read_text(encoding="utf-8")
        if set(FENCE.findall(en_text)) != set(FENCE.findall(ru_text)):
            raise LocaleError(f"code fences differ: {english}, {russian}")
        if _tokens(en_text) != _tokens(ru_text):
            raise LocaleError(f"machine tokens differ: {english}, {russian}")
        if _headings(en_text) != _headings(ru_text):
            raise LocaleError(f"section structure differs: {english}, {russian}")
        if _block_signature(en_text) != _block_signature(ru_text):
            raise LocaleError(f"block structure differs: {english}, {russian}")
        en_links = _links(root, english, en_text)
        ru_links = _links(root, russian, ru_text)
        if russian in ru_links:
            raise LocaleError(f"Russian documentation links to itself: {russian}")
        if require_language_link and (russian not in en_links or english not in ru_links):
            raise LocaleError(f"missing reciprocal language link: {english}, {russian}")
    documented = set(paths) | set(neutral)
    for relative in _public_documents(root):
        if relative not in documented:
            raise LocaleError(f"public documentation is neither translated nor neutral: {relative}")
    for path in root.rglob("*.md"):
        relative = path.relative_to(root).as_posix()
        if "/en/" in relative or relative.endswith(".en.md"):
            raise LocaleError(f"obsolete English locale path: {relative}")
        if ("/ru/" in relative or relative.endswith(".ru.md")) and relative not in paths:
            raise LocaleError(f"orphan Russian locale document: {relative}")
    if built is not None:
        if not built.is_dir():
            raise LocaleError("built skills directory does not exist")
        for path in built.rglob("*"):
            if path.is_file() and {"ru", "en"}.intersection(path.relative_to(built).parts):
                raise LocaleError(f"locale-specific built machine file: {path.relative_to(built)}")
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path)
    args = parser.parse_args(argv)
    try:
        print(f"checked {validate(built=args.built)} documentation pair(s)")
    except LocaleError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
