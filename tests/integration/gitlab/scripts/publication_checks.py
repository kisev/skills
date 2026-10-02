"""Exercise generated publication commands, never reconstructed API equivalents."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.stand import ROOT, Stand, command, write_json


def commands(markdown: str) -> list[str]:
    return [
        line
        for block in re.findall(r"```(?:sh|shell)\n(.*?)\n```", markdown, re.DOTALL)
        for line in block.splitlines()
        if line.strip() and not line.startswith("#")
    ]


def validated_argv(stand: Stand, text: str) -> tuple[list[str], str]:
    argv = shlex.split(text)
    # Marker wrappers are part of the copied command, not bypassed by the test.
    glab = argv.index("glab") if "glab" in argv else -1
    if glab < 0:
        raise ValueError("Publication command must invoke glab")
    if glab:
        helper = Path(argv[4]).resolve() if argv[1:4] == ["-I", "-S", "-B"] else None
        if (
            helper is None
            or Path(argv[0]).resolve() != Path(sys.executable).resolve()
            or not helper.is_relative_to(ROOT / ".build/skills")
            or helper.name != "state_artifacts.py"
            or argv[5] != "marker-run"
            or argv[glab - 1] != "--"
        ):
            raise ValueError("Unrecognized publication wrapper")
    args = argv[glab:]
    pid = stand.manifest["fixtures"]["id"]
    if args[1] in ("mr", "release"):
        repo_flags = [flag for flag in ("--repo", "-R") if flag in args]
        if (
            len(repo_flags) != 1
            or args.count(repo_flags[0]) != 1
            or args[args.index(repo_flags[0]) + 1] != stand.manifest["fixtures"]["web_url"]
        ):
            raise ValueError("MR publication outside the synthetic fixture project")
        if args[1] == "mr" and args[2] in ("update", "merge"):
            endpoint = f"projects/{pid}/merge_requests/{int(args[3])}"
        elif args[1:4] == ["mr", "note", "create"]:
            endpoint = f"projects/{pid}/merge_requests/{int(args[4])}/notes"
        elif args[1:3] == ["release", "create"]:
            endpoint = f"projects/{pid}/releases"
        else:
            raise ValueError("Unsupported generated publication command")
    elif args[1] == "api":
        if args.count("--hostname") != 1 or args[args.index("--hostname") + 1] != "localhost":
            raise ValueError("Publication must target localhost explicitly")
        endpoint = args[args.index("--method") + 2]
    else:
        raise ValueError("Unsupported generated glab publication command")
    if not endpoint.startswith(f"projects/{pid}/") and endpoint != "graphql":
        raise ValueError("Publication outside the synthetic fixture project")
    if any(part in (".", "..") for part in endpoint.split("/")) or "%" in endpoint:
        raise ValueError("Publication outside the literal synthetic endpoint scope")
    for flag in ("--input", "--description-file", "--notes-file", "--attach"):
        if flag in args:
            source = Path(args[args.index(flag) + 1]).resolve()
            if not source.is_relative_to(stand.home):
                raise ValueError("Publication input outside the selected stand")
    if endpoint == "graphql":
        payload = json.loads(Path(args[args.index("--input") + 1]).read_text())
        variables = payload["variables"]["input"]
        query = "mutation CreateIssue($input: CreateIssueInput!) { createIssue(input: $input) { issue { iid webUrl } errors } }"
        if variables.get("projectPath") != stand.manifest["fixtures"][
            "path_with_namespace"
        ] or re.sub(r"\s+", "", payload["query"]) != re.sub(r"\s+", "", query):
            raise ValueError("GraphQL publication outside the synthetic fixture project")
    return argv, endpoint


def execute(
    stand: Stand, text: str, directory: Path, name: str, actor: str = "reviewer"
) -> dict[str, Any]:
    argv, endpoint = validated_argv(stand, text)
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env=stand.isolated_env(actor),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    observation = {
        "command": text,
        "exit_code": result.returncode,
        "stdout": stand.redact(result.stdout),
        "stderr": stand.redact(result.stderr),
    }
    write_json(directory / (name + ".json"), observation)
    if result.returncode:
        raise RuntimeError(f"Copied {name} command failed: {observation['stderr']}")
    if endpoint == "graphql" and json.loads(result.stdout).get("errors"):
        raise RuntimeError("Copied GraphQL command returned errors despite exit zero")
    return observation


def mr(stand: Stand, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}"
    runner = ROOT / ".build/skills/mr-prepare/scripts/prepare_mr.py"
    evidence: dict[str, Any] = {}
    for actor in ("reviewer", "author"):
        before = stand.request("GET", endpoint)
        discussions = human_notes(stand.request("GET", endpoint + "/discussions"))
        prepared = helper(stand, runner, ["prepare", "--url", before["web_url"]], actor)
        item = prepared["items"][0]
        if item["status"] != "ok" or item["complete"] is not True:
            raise RuntimeError("MR helper returned incomplete evidence")
        bundle = json.loads(Path(item["artifact_path"]).read_text())["payload"]
        content = {
            "locale": "en",
            "title": f"Harness {actor} publication {directory.name}",
            "description": before["description"]
            + f"\n\nLiteral `code`, $value and @here: {actor}.",
            "change_summary": ["Exercise synthetic metadata publication."],
            "limitations": ["Deterministic content is not an agent semantic assessment."],
            "template": {"id": None, "rationale": "The fixture contains no MR templates."},
            "preservation_notes": ["Retain the original description and discussion history."],
            "semver_impact": "none",
            "semver_rationale": "This publishes synthetic metadata, not a product release.",
            "label_assessments": [
                {
                    "name": label["name"],
                    "status": "applicable"
                    if label["name"] in f["issue"]["labels"]
                    else "inapplicable",
                    "rationale": "Only the current run's synthetic label belongs to this MR.",
                }
                for label in bundle["labels"]["items"]
            ],
        }
        source = directory / f"mr-{actor}-content.json"
        write_json(source, content)
        plan = helper(
            stand,
            runner,
            ["scaffold", "--bundle", item["artifact_path"], "--content", str(source)],
            actor,
        )
        after_prepare = stand.request("GET", endpoint)
        if any(
            before[key] != after_prepare[key]
            for key in ("title", "description", "labels", "sha", "state")
        ):
            raise RuntimeError("MR scaffold published metadata")
        text = Path(plan["markdown_path"]).read_text()
        (directory / f"mr-{actor}-runbook.md").write_text(text)
        copied = commands(text)
        mutations = [command for command in copied if " glab api " in command]
        if len(mutations) != (3 if actor == "reviewer" else 2):
            raise RuntimeError("Missing exact title/description/label publication commands")
        for index, copied_command in enumerate(mutations):
            execute(stand, copied_command, directory, f"mr-{actor}-{index}", actor)
        actual = stand.request("GET", endpoint)
        if any(actual[key] != content[key] for key in ("title", "description")) or set(
            actual["labels"]
        ) != set(f["issue"]["labels"]):
            raise RuntimeError(
                "MR copied command server postcondition differs from prepared content"
            )
        if discussions != human_notes(stand.request("GET", endpoint + "/discussions")):
            raise RuntimeError("MR metadata publication changed discussions")
        evidence[actor] = {
            "user_id": stand.manifest["users"][actor]["id"],
            "commands": mutations,
            "title": actual["title"],
            "labels": actual["labels"],
        }
    return evidence


def human_notes(discussions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [note for thread in discussions for note in thread["notes"] if not note["system"]]


def helper(stand: Stand, runner: Path, args: list[str], actor: str) -> dict[str, Any]:
    result = json.loads(
        command(
            [sys.executable, str(runner), *args], env=stand.isolated_env(actor), timeout=180
        ).stdout
    )
    if not isinstance(result, dict):
        raise RuntimeError("Publication helper returned a non-object result")
    return result


def task(stand: Stand, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    return {
        "roles": {actor: task_actor(stand, f, directory, actor) for actor in ("author", "reviewer")}
    }


def task_actor(stand: Stand, f: dict[str, Any], directory: Path, actor: str) -> dict[str, Any]:
    plan = json.loads((directory / ("task-prepare-" + actor + ".json")).read_text())
    text = Path(plan["output"]).read_text()
    copied = commands(text)
    if len(copied) != 1:
        raise RuntimeError("Expected one copied synthetic task creation command")
    response = execute(stand, copied[0], directory, "task-copied-create-" + actor, actor)
    result = json.loads(response["stdout"])
    mutation = result["data"]["createIssue"]
    if mutation.get("errors") or not mutation.get("issue"):
        raise RuntimeError("Task creation returned no issue or mutation errors")
    iid = mutation["issue"]["iid"]
    actual = stand.request("GET", f["prefix"] + f"/issues/{iid}")
    if (
        actual["title"] != "Synthetic task " + directory.name + " " + actor
        or actual["labels"] != f["issue"]["labels"]
        or actual["milestone"]["id"] != f["issue"]["milestone"]["id"]
        or actual["author"]["id"] != stand.manifest["users"][actor]["id"]
    ):
        raise RuntimeError("Task copied command did not preserve title, labels and milestone")
    return {
        "iid": iid,
        "url": actual["web_url"],
        "command": copied[0],
        "labels": actual["labels"],
        "milestone_id": actual["milestone"]["id"],
        "actor_id": actual["author"]["id"],
    }
