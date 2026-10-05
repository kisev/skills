"""Legacy publication command rendering; guarded actions remain historical only.

The TypeScript runtime keeps the same module as the renderer for the review
plan's manual commands and the TUI send path. The historical guarded actions
are not executable: ``command_argv`` rejects every non-``glab`` command.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from reviewmatic.portable.mutation_process import run_mutation_process
from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Sequence


def shell_quote(value: str) -> str:
    if re.fullmatch(r"[\w@%+=:,./-]+", value):
        return value
    return f"'{value.replace("'", "'\\''")}'"


def shell_join(argv: Sequence[str]) -> str:
    return " ".join(shell_quote(item) for item in argv)


# Parse only the quoting emitted by shell_join. Commands are never executed by a shell.
def command_argv(command: str) -> list[str]:
    result: list[str] = []
    token = ""
    quote = ""
    started = False
    index = 0
    while index < len(command):
        character = command[index]
        if quote != "":
            if character == quote:
                quote = ""
            else:
                token += character
        elif character == "'":
            quote = character
            started = True
        elif character == "\\":
            index += 1
            if index >= len(command):
                raise contract.WorkflowError("Incomplete command escape")
            token += command[index]
            started = True
        elif character.isspace():
            if started:
                result.append(token)
            token = ""
            started = False
        else:
            token += character
            started = True
        index += 1
    if quote != "":
        raise contract.WorkflowError("Incomplete command quote")
    if started:
        result.append(token)
    if not result or result[0] != "glab":
        raise contract.WorkflowError(
            "Legacy guarded actions are historical only; prepare a new runbook"
        )
    return result


def make_command(
    root: str | Path,
    evidence: dict[str, Any],
    context: dict[str, Any],
    action_id: str,
    argv: list[str],
    value: object,
    dependencies: dict[str, str],
    stdin_sha256: str | None = None,
) -> str:
    """Rewrite a ``glab mr note`` command into one exact line discussion command."""
    if argv[1:3] != ["mr", "note"]:
        return shell_join(argv)
    directory = Path(root) / "artifacts" / "review_plan" / "bodies"
    name = next(
        (
            entry.name
            for entry in sorted(directory.iterdir())
            if entry.name.endswith(".md")
            and hashlib.sha256(entry.read_bytes()).hexdigest() == stdin_sha256
        ),
        None,
    )
    if name is None:
        raise contract.WorkflowError("Line publication body is unavailable")
    side = "new" if "--line" in argv else "old"
    path = argv[argv.index("--file") + 1]
    changed_files = cast_component_items(evidence["changed_files"])
    changes = [item for item in changed_files if item.get(f"{side}_path") == path]
    if len(changes) != 1:
        raise contract.WorkflowError("Line publication requires one exact changed file")
    project = cast("dict[str, Any]", evidence["project"])
    refs = cast("dict[str, Any]", cast("dict[str, Any]", evidence["object"])["diff_refs"])
    line_key = "--line" if side == "new" else "--old-line"
    position: dict[str, Any] = {
        "position_type": "text",
        **refs,
        "new_path": changes[0]["new_path"],
        "old_path": changes[0]["old_path"],
        f"{side}_line": int(argv[argv.index(line_key) + 1]),
    }
    if side == "new":
        wanted = int(position["new_line"])
        repository = str(cast("dict[str, Any]", context["exact_git"])["repo_root"])
        diff = str(
            contract.git_read(
                Path(repository),
                "diff",
                "--unified=3",
                str(evidence["base_sha"]),
                str(evidence["head_sha"]),
                "--",
                path,
            )
        )
        old_line = 0
        new_line = 0
        for row in diff.split("\n"):
            hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", row)
            if hunk:
                old_line = int(hunk.group(1))
                new_line = int(hunk.group(2))
                continue
            if row.startswith(" "):
                if new_line == wanted:
                    position["old_line"] = old_line
                old_line += 1
                new_line += 1
            elif row.startswith("+") and not row.startswith("+++"):
                new_line += 1
            elif row.startswith("-") and not row.startswith("---"):
                old_line += 1
    return shell_join(
        [
            "glab",
            "api",
            "--hostname",
            str(project["hostname"]),
            "--method",
            "POST",
            (
                f"projects/{project['id']}/merge_requests/"
                f"{cast('dict[str, Any]', evidence['target'])['iid']}/discussions"
            ),
            "--silent",
            "-F",
            f"body=@{directory}/{name}",
            "-F",
            f"position={json.dumps(position, separators=(',', ':'), ensure_ascii=False)}",
        ]
    )


def cast_component_items(component: object) -> list[dict[str, Any]]:
    value = cast("dict[str, Any]", component)
    return cast("list[dict[str, Any]]", value["items"])


def send_command(command: str) -> subprocess.CompletedProcess[bytes]:
    return run_mutation_process(command_argv(command), b"")
