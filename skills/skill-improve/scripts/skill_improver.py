#!/usr/bin/env python3
"""Static Agent Skills checker used by the skill-improver workflow."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


def _bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


_bootstrap()

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TOP_LEVEL_RE = re.compile(r"^([A-Za-z0-9_.-]+):\s*(.*)$")
RESOURCE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:(?:references|scripts|templates|assets)/|\.\.?/)[A-Za-z0-9._/-]+)"
)
SCRIPT_RE = re.compile(r"(?<![A-Za-z0-9_.-])(scripts/[A-Za-z0-9._/-]+\.py)")
TODO_RE = re.compile(r"\b(?:TODO|FIXME)(?::|\()")
ALLOWED_FRONTMATTER = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)
MAX_SKILL_NAME_LENGTH = 64
MAX_SKILL_DESCRIPTION_LENGTH = 1024
MAX_SKILL_LINES_WITHOUT_REFERENCES = 500


@dataclass(frozen=True)
class Issue:
    severity: str
    rule: str
    line: int
    message: str


class CheckError(Exception):
    """Fatal checker usage error."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], int, list[Issue]]:
    """Parse top-level YAML scalar fields without a YAML dependency."""
    lines = text.splitlines()
    issues: list[Issue] = []
    if not lines or lines[0] != "---":
        return (
            {},
            0,
            [Issue("critical", "frontmatter-missing", 1, "frontmatter block missing")],
        )
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line == "---"), -1
    )
    if closing < 0:
        return (
            {},
            0,
            [
                Issue(
                    "critical", "frontmatter-unclosed", 1, "frontmatter block unclosed"
                )
            ],
        )
    fields: dict[str, str] = {}
    active: str | None = None
    for line in lines[1:closing]:
        match = TOP_LEVEL_RE.match(line)
        if match:
            active, value = match.groups()
            fields[active] = (
                "" if value.strip() in {">", ">-", "|", "|-"} else value.strip()
            )
        elif line.startswith((" ", "\t")) and active is not None:
            fields[active] = f"{fields[active]} {line.strip()}".strip()
        else:
            active = None
    return fields, closing, issues


def check_frontmatter(skill_dir: Path, fields: dict[str, str]) -> list[Issue]:
    issues: list[Issue] = []
    for key in sorted(set(fields) - ALLOWED_FRONTMATTER):
        issues.append(
            Issue(
                "major",
                "frontmatter-unsupported-field",
                2,
                f"unsupported frontmatter field {key!r}",
            )
        )
    name = fields.get("name", "")
    if not name:
        issues.append(Issue("critical", "name-missing", 2, "frontmatter name missing"))
    else:
        if not NAME_RE.fullmatch(name) or len(name) > MAX_SKILL_NAME_LENGTH:
            issues.append(
                Issue("critical", "name-invalid", 2, f"invalid skill name {name!r}")
            )
        if name != skill_dir.name:
            issues.append(
                Issue(
                    "critical",
                    "name-mismatch",
                    2,
                    f"name {name!r} does not match directory {skill_dir.name!r}",
                )
            )
    description = fields.get("description", "")
    if not description:
        issues.append(
            Issue(
                "critical", "description-missing", 3, "frontmatter description missing"
            )
        )
    elif len(description) > MAX_SKILL_DESCRIPTION_LENGTH:
        issues.append(
            Issue(
                "major",
                "description-too-long",
                3,
                "description exceeds 1024 characters",
            )
        )
    return issues


def safe_resource(skill_dir: Path, token: str) -> tuple[Path | None, str | None]:
    relative = Path(token)
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        return None, "unsafe"
    candidate = skill_dir / relative
    current = skill_dir
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return None, "symlink"
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(skill_dir.resolve())
    except (OSError, ValueError):
        return None, "missing"
    return resolved, None


def check_resources(skill_dir: Path, lines: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[int, str]] = set()
    for number, line in enumerate(lines, 1):
        for match in RESOURCE_RE.finditer(line):
            token = match.group(1).rstrip(".,:;)")
            if (number, token) in seen or "<" in token or "$" in token:
                continue
            seen.add((number, token))
            _path, failure = safe_resource(skill_dir, token)
            if failure is not None:
                rule = (
                    "resource-unsafe"
                    if failure in {"unsafe", "symlink"}
                    else "resource-missing"
                )
                issues.append(
                    Issue(
                        "critical",
                        rule,
                        number,
                        f"resource path {token!r} is {failure}",
                    )
                )
    return issues


def check_scripts(skill_dir: Path, lines: list[str]) -> list[Issue]:
    issues: list[Issue] = []
    checked: set[str] = set()
    for number, line in enumerate(lines, 1):
        for match in SCRIPT_RE.finditer(line):
            token = match.group(1).rstrip(".,:;)")
            if token in checked:
                continue
            checked.add(token)
            script, _failure = safe_resource(skill_dir, token)
            if script is None:
                continue
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(script), "--help"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                issues.append(
                    Issue(
                        "major",
                        "script-help-failed",
                        number,
                        f"script {token!r} does not support --help",
                    )
                )
    return issues


def check_size(skill_dir: Path, lines: list[str]) -> list[Issue]:
    if (
        len(lines) <= MAX_SKILL_LINES_WITHOUT_REFERENCES
        or (skill_dir / "references").is_dir()
    ):
        return []
    return [
        Issue(
            "major",
            "progressive-disclosure-missing",
            1,
            "SKILL.md exceeds 500 lines without references/",
        )
    ]


def check_skill(skill_dir: Path) -> list[Issue]:
    target = skill_dir.resolve()
    skill_md = target / "SKILL.md"
    if not target.is_dir() or not skill_md.is_file():
        raise CheckError(f"directory with SKILL.md not found: {skill_dir}")
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as error:
        raise CheckError(f"cannot read SKILL.md: {error}") from error
    lines = text.splitlines()
    fields, _closing, issues = parse_frontmatter(text)
    if not issues:
        issues.extend(check_frontmatter(target, fields))
    issues.extend(check_resources(target, lines))
    issues.extend(check_scripts(target, lines))
    issues.extend(check_size(target, lines))
    issues.extend(
        Issue("minor", "todo-marker", number, "unresolved TODO/FIXME marker")
        for number, line in enumerate(lines, 1)
        if TODO_RE.search(line)
    )
    order = {"critical": 0, "major": 1, "minor": 2}
    return sorted(
        issues, key=lambda issue: (order[issue.severity], issue.rule, issue.line)
    )


def check_command(path: Path) -> int:
    issues = check_skill(path)
    counts = {
        severity: sum(issue.severity == severity for issue in issues)
        for severity in ("critical", "major", "minor")
    }
    print(
        json.dumps(
            {
                "schema_version": 1,
                "skill": str(path.resolve()),
                "status": "pass"
                if not counts["critical"] and not counts["major"]
                else "fail",
                "counts": counts,
                "issues": [asdict(issue) for issue in issues],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if counts["critical"] or counts["major"] else 0


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="skill-improver")
    result.add_argument("--capabilities", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--path", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.0.0",
        mutation="read",
        supports_dry_run=False,
    ):
        return 0
    arguments = arguments_parser.parse_args(argv)
    try:
        return check_command(Path(arguments.path))
    except (CheckError, OSError, subprocess.TimeoutExpired) as error:
        report_error("check_error", str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
