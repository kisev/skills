#!/usr/bin/env python3
"""Build deterministic, read-only structure for a Git diff."""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path


def _bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


_bootstrap()

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error

DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
HUNK_HEADER = re.compile(r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@")
DEF_RE = re.compile(r"\b(?:def|class|function|interface|type|func)\s+([A-Za-z_][\w$]*)")
PY_IMPORT_SYMBOL_RE = re.compile(r"from\s+([\w./-]+)\s+import\s+([A-Za-z_][\w$]*)")
IMPORT_RE = re.compile(
    r"(?:from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]|from\s+([\w./-]+)\s+import)"
)
CALL_RE = re.compile(r"\b([A-Za-z_][\w$]*)\s*\(")


def run_git(repo: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise ValueError(f"git command failed: {detail.strip()}") from error
    return result.stdout


def repository_root(value: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    if not candidate.is_dir() or candidate.is_symlink():
        raise ValueError("repo root must be an existing non-symlink directory")
    return Path(run_git(candidate, "rev-parse", "--show-toplevel").strip()).resolve()


def collect_diff(repo: Path, diff_range: str | None, diff_file: Path | None) -> str:
    if diff_file is not None:
        candidate = diff_file.expanduser()
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError("diff file must be a regular non-symlink file")
        return candidate.read_text(encoding="utf-8", errors="replace")
    if diff_range:
        return run_git(repo, "diff", "--no-ext-diff", "--unified=3", diff_range, "--")
    tracked = run_git(repo, "diff", "HEAD", "--no-ext-diff", "--unified=3", "--")
    untracked = run_git(repo, "ls-files", "--others", "--exclude-standard")
    pieces = [tracked]
    for name in untracked.splitlines():
        path = repo / name
        if path.is_file() and not path.is_symlink():
            content = path.read_text(encoding="utf-8", errors="replace").splitlines(
                keepends=True
            )
            pieces.append(
                f"diff --git a/{name} b/{name}\nnew file mode 100644\n"
                + "".join(
                    difflib.unified_diff(
                        [],
                        content,
                        fromfile="/dev/null",
                        tofile=f"b/{name}",
                        lineterm="\n",
                    )
                )
            )
    return "".join(pieces)


def safe_diff_path(value: str) -> str:
    path = Path(value)
    if (
        not value
        or "\x00" in value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe path in diff: {value!r}")
    return path.as_posix()


def parse_diff(text: str) -> tuple[list[dict[str, object]], dict[str, list[str]]]:
    files: list[dict[str, object]] = []
    added: dict[str, list[str]] = {}
    current: dict[str, object] | None = None
    hunk: dict[str, object] | None = None
    for line in text.splitlines():
        header = DIFF_HEADER.match(line)
        if header:
            old_path, new_path = (safe_diff_path(value) for value in header.groups())
            current = {
                "path": new_path,
                "old_path": old_path,
                "status": "modified",
                "additions": 0,
                "deletions": 0,
                "hunks": [],
            }
            files.append(current)
            added[new_path] = []
            hunk = None
            continue
        if current is None:
            continue
        if line.startswith("new file mode"):
            current["status"] = "added"
        elif line.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif line.startswith("rename from"):
            current["status"] = "renamed"
        matched_hunk = HUNK_HEADER.match(line)
        if matched_hunk:
            hunk = {
                "old_start": int(matched_hunk.group("old")),
                "new_start": int(matched_hunk.group("new")),
                "header": line,
                "additions": 0,
                "deletions": 0,
            }
            hunks = current["hunks"]
            if not isinstance(hunks, list):
                raise ValueError("invalid hunk accumulator")
            hunks.append(hunk)
        elif line.startswith("+") and not line.startswith("+++"):
            current["additions"] = int(current["additions"]) + 1
            added[str(current["path"])].append(line[1:])
            if hunk is not None:
                hunk["additions"] = int(hunk["additions"]) + 1
        elif line.startswith("-") and not line.startswith("---"):
            current["deletions"] = int(current["deletions"]) + 1
            if hunk is not None:
                hunk["deletions"] = int(hunk["deletions"]) + 1
    return files, added


def category(path: str) -> tuple[int, str]:
    lower = path.lower()
    if any(
        token in lower
        for token in ("schema", "openapi", "interface", "types", "contract")
    ):
        return 0, "contracts"
    if (
        "/test" in lower
        or lower.startswith("test")
        or any(token in lower for token in ("_test.", ".spec."))
    ):
        return 2, "tests"
    if lower.endswith(
        (
            ".yml",
            ".yaml",
            ".toml",
            ".json",
            ".jsonc",
            ".ini",
            ".cfg",
            ".conf",
            ".properties",
        )
    ) or lower.startswith((".github/", ".gitlab/", ".env")):
        return 3, "configs"
    return 1, "logic"


def module(path: str) -> str:
    parts = Path(path).parts
    return "." if len(parts) == 1 else "/".join(parts[: min(2, len(parts) - 1)])


def relationship_content(
    repo: Path, path: str, status: object, added: dict[str, list[str]]
) -> str:
    candidate = repo / path
    if status == "deleted" or not candidate.is_file() or candidate.is_symlink():
        return "\n".join(added.get(path, []))
    return candidate.read_text(encoding="utf-8", errors="replace")


def build_relationships(
    repo: Path, files: list[dict[str, object]], added: dict[str, list[str]]
) -> list[dict[str, str]]:
    changed = {str(item["path"]): item for item in files}
    content = {
        path: relationship_content(repo, path, item["status"], added)
        for path, item in changed.items()
    }
    relations: list[dict[str, str]] = []
    imported_symbols: dict[tuple[str, str], str] = {}
    for source, text in content.items():
        for match in IMPORT_RE.finditer(text):
            imported = next(value for value in match.groups() if value is not None)
            target = next(
                (
                    path
                    for path in changed
                    if imported in path or Path(path).stem == Path(imported).stem
                ),
                None,
            )
            if target and target != source:
                relations.append(
                    {
                        "from": source,
                        "to": target,
                        "kind": "imports",
                        "evidence": imported,
                    }
                )
        for match in PY_IMPORT_SYMBOL_RE.finditer(text):
            imported, symbol = match.groups()
            target = next(
                (
                    path
                    for path in changed
                    if imported in path or Path(path).stem == Path(imported).stem
                ),
                None,
            )
            if target and target != source:
                imported_symbols[(source, symbol)] = target
        for symbol in CALL_RE.findall(text):
            target = imported_symbols.get((source, symbol))
            if target and target != source:
                relations.append(
                    {
                        "from": source,
                        "to": target,
                        "kind": "calls",
                        "evidence": f"{symbol}()",
                    }
                )
    return [
        dict(item)
        for item in sorted({tuple(relation.items()) for relation in relations})
    ]


def build(
    repo: Path,
    diff_range: str | None,
    diff_file: Path | None,
    chunk_size: int,
    chunk_index: int | None,
) -> dict[str, object]:
    files, added = parse_diff(collect_diff(repo, diff_range, diff_file))
    clusters: dict[tuple[str, str], list[dict[str, object]]] = {}
    for item in files:
        path = str(item["path"])
        clusters.setdefault((module(path), category(path)[1]), []).append(item)
    ordered = sorted(
        clusters.items(),
        key=lambda pair: (category(str(pair[1][0]["path"]))[0], pair[0]),
    )
    all_clusters: list[dict[str, object]] = []
    for index, ((name, kind), items) in enumerate(ordered, 1):
        items.sort(key=lambda item: str(item["path"]))
        all_clusters.append(
            {
                "id": f"step-{index}",
                "module": name,
                "kind": kind,
                "intent": {
                    "contracts": "Establish or change the interface and data contract.",
                    "logic": "Change the implementation behavior.",
                    "tests": "Cover observable behavior with tests.",
                    "configs": "Wire or configure the change.",
                }[kind],
                "files": items,
                "read_order": category(str(items[0]["path"]))[0],
            }
        )
    chunks = [
        all_clusters[index : index + chunk_size]
        for index in range(0, len(all_clusters), chunk_size)
    ]
    if chunk_index is not None and not 0 <= chunk_index < len(chunks):
        raise ValueError(f"chunk index is outside 0..{max(len(chunks) - 1, 0)}")
    selected = chunks[chunk_index] if chunk_index is not None else all_clusters
    step_by_path = {
        str(item["path"]): str(cluster["id"])
        for cluster in all_clusters
        for item in cluster["files"]
    }
    relationships = [
        {
            **relation,
            "from_step": step_by_path[relation["from"]],
            "to_step": step_by_path[relation["to"]],
        }
        for relation in build_relationships(repo, files, added)
    ]
    attention: dict[str, set[str]] = {}
    for item in files:
        path = str(item["path"])
        changed_text = "\n".join(added.get(path, [])).lower()
        reasons = ([] if item["status"] != "deleted" else ["deletion"]) + (
            [] if "migration" not in path.lower() else ["migration"]
        )
        if any(term in path.lower() for term in ("permission", "policy", "auth")) or (
            category(path)[1] == "configs"
            and any(term in changed_text for term in ("permission", "policy"))
        ):
            reasons.append("permissions")
        for reason in reasons:
            attention.setdefault(reason, set()).add(path)
    return {
        "schema_version": 1,
        "source": {
            "repo_root": str(repo),
            "range": diff_range or "working-tree",
            "diff_file": str(diff_file) if diff_file else None,
        },
        "statistics": {
            "files": len(files),
            "hunks": sum(len(item["hunks"]) for item in files),
            "additions": sum(int(item["additions"]) for item in files),
            "deletions": sum(int(item["deletions"]) for item in files),
        },
        "clusters": selected,
        "relationships": relationships,
        "coverage": {
            "files_total": len(files),
            "files_clustered": sum(len(cluster["files"]) for cluster in selected),
            "complete": chunk_index is None,
            "uncovered_files": len(files)
            - sum(len(cluster["files"]) for cluster in selected),
            "chunks": len(chunks),
            "chunk_size": chunk_size,
            "chunk_index": chunk_index,
        },
        "chunk_manifest": [
            {
                "index": index,
                "step_ids": [str(cluster["id"]) for cluster in chunk],
                "files": [
                    str(item["path"]) for cluster in chunk for item in cluster["files"]
                ],
            }
            for index, chunk in enumerate(chunks)
        ],
        "attention": [
            {"reason": reason, "files": sorted(paths)}
            for reason, paths in sorted(attention.items())
        ],
    }


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="walkthrough")
    result.add_argument("--capabilities", action="store_true")
    result.add_argument("--repo-root", default=".")
    source = result.add_mutually_exclusive_group()
    source.add_argument("--range", dest="diff_range")
    source.add_argument("--diff-file", type=Path)
    result.add_argument("--chunk-size", type=int, default=8)
    result.add_argument("--chunk-index", type=int)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.0.0",
        mutation="read",
        supports_dry_run=False,
        external_tools=("git",),
    ):
        return 0
    arguments = arguments_parser.parse_args(argv)
    if (
        arguments.chunk_size < 1
        or arguments.chunk_index is not None
        and arguments.chunk_index < 0
    ):
        arguments_parser.error(
            "chunk size must be positive and chunk index must not be negative"
        )
    try:
        repo = repository_root(arguments.repo_root)
        print(
            json.dumps(
                build(
                    repo,
                    arguments.diff_range,
                    arguments.diff_file,
                    arguments.chunk_size,
                    arguments.chunk_index,
                ),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        report_error("walkthrough_error", str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
