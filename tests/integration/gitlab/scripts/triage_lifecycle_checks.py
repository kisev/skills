"""Real information-request cycles and stale analysis; decisions remain fixtures."""

from __future__ import annotations

import copy
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.checks import verify
from tests.integration.gitlab.scripts.publication_checks import commands, execute, helper
from tests.integration.gitlab.scripts.stand import ROOT, Stand, private_directory, write_json


def guarded_argv(stand: Stand, text: str) -> list[str]:
    argv = shlex.split(text)
    separator = argv.index("--") if "--" in argv else -1
    runner = ROOT / ".build/skills/task-triage/scripts/triage_task.py"
    if (
        separator < 0
        or argv[:4] != [sys.executable, "-I", "-S", "-B"]
        or Path(argv[4]).resolve() != runner.parent / "portable_runtime/state_artifacts.py"
        or argv[5] != "marker-run"
        or argv[separator + 1 : separator + 6] != [sys.executable, "-I", "-S", "-B", str(runner)]
        or argv[separator + 6 : separator + 8] != ["apply-information", "--guard"]
        or len(argv[separator + 1 :]) != 10
        or argv[-2] != "--stage"
        or argv[-1] not in ("message", "close")
    ):
        raise ValueError("Unrecognized copied information command")
    path = Path(argv[separator + 8])
    if path.is_symlink() or not path.resolve().is_relative_to(stand.state):
        raise ValueError("Information guard outside the isolated fixture state")
    guard = json.loads(path.read_text())
    target = guard["request"]["target"]
    if (
        guard["host"] != "localhost"
        or target["kind"] != "issue"
        or target["project_id"] != stand.manifest["fixtures"]["id"]
        or guard["current_user"]["id"] != stand.manifest["users"]["reviewer"]["id"]
    ):
        raise ValueError("Information command outside fixture role/target")
    return argv


def run(stand: Stand, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    directory = private_directory(directory / "triage-lifecycle")
    runner = ROOT / ".build/skills/task-triage/scripts/triage_task.py"
    template = json.loads(
        (directory.parent / "task-triage-workflows/reviewer-analysis-input.json").read_text()
    )["items"][0]
    issue = stand.request(
        "POST",
        f["prefix"] + "/issues",
        {
            "title": "Information cycle " + directory.parent.name,
            "milestone_id": template["release_plan"]["milestone"]["candidate"]["id"],
        },
    )
    endpoint = f["prefix"] + f"/issues/{issue['iid']}"
    target = {
        "kind": "issue",
        "project_id": stand.manifest["fixtures"]["id"],
        "iid": issue["iid"],
        "discussion_id": None,
    }
    prior: list[int] = []
    cycles = []
    last_analysis: Path | None = None
    for action in ("new", "ping_1", "ping_2", "close"):
        before = stand.request("GET", endpoint)
        discussions_before = stand.request("GET", endpoint + "/discussions")
        collection = helper(stand, runner, ["collect", "--source", issue["web_url"]], "reviewer")
        verify(collection["status"] == "ok", "Information collection incomplete")
        item = copy.deepcopy(template)
        item.update(
            evidence_digest=collection["items"][0]["evidence_digest"],
            issue_relations=[],
            proposed_changes={},
            information_requests=[
                {
                    "action": action,
                    "target": dict(target),
                    "body": f"Harness information {action}; literal `code`, $value and @here.",
                    "prior_note_ids": list(prior),
                    "rationale": "Deterministic request sequence against a real fixture conversation.",
                    "standalone_reason": "No discussion exists for the new fixture."
                    if action == "new"
                    else None,
                }
            ],
        )
        source = directory / (action + "-analysis.json")
        write_json(
            source,
            {
                "collection_digest": collection["collection_digest"],
                "items": [item],
                "top_five": [],
                "parallel_groups": [],
                "questions": [],
            },
        )
        pointer = str(Path(collection["artifact_root"]) / "current.json")
        prepared = helper(
            stand,
            runner,
            ["publish", "--collection", pointer, "--analysis", str(source)],
            "reviewer",
        )
        write_json(directory / (action + "-plan.json"), prepared)
        (directory / (action + "-runbook.md")).write_text(
            Path(prepared["reports"][0]["report"]).read_text()
        )
        verify(
            prepared["status"] == "ok" and prepared["external_mutations"] is False,
            "Information preparation failed",
        )
        verify(
            before == stand.request("GET", endpoint)
            and discussions_before == stand.request("GET", endpoint + "/discussions"),
            "Information preparation wrote to GitLab",
        )
        copied = commands(Path(prepared["reports"][0]["report"]).read_text())
        information = [text for text in copied if "apply-information" in shlex.split(text)]
        verify(
            len(information) == (2 if action == "close" else 1),
            "Information runbook lost separate message/close commands",
        )
        for index, text in enumerate(copied):
            if text not in information:
                execute(stand, text, directory, f"{action}-{index}-metadata")
                continue
            result = subprocess.run(
                guarded_argv(stand, text),
                cwd=ROOT,
                env=stand.isolated_env("reviewer"),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            write_json(
                directory / f"{action}-{index}-command.json",
                {
                    "command": text,
                    "exit_code": result.returncode,
                    "stdout": stand.redact(result.stdout),
                    "stderr": stand.redact(result.stderr),
                },
            )
            verify(
                result.returncode == 0,
                "Copied information command failed: " + stand.redact(result.stderr),
            )
            if action == "close" and text == information[0]:
                verify(
                    stand.request("GET", endpoint)["state"] == "opened",
                    "Closure message implicitly closed the issue",
                )
        discussions = stand.request("GET", endpoint + "/discussions")
        matches = [
            thread
            for thread in discussions
            if any(
                note["body"] == item["information_requests"][0]["body"] for note in thread["notes"]
            )
        ]
        verify(len(matches) == 1, "Information message missing or duplicated")
        thread = matches[0]
        if target["discussion_id"] is not None:
            verify(
                thread["id"] == target["discussion_id"], "Follow-up escaped the observed discussion"
            )
        target["discussion_id"] = thread["id"]
        note = next(
            note
            for note in thread["notes"]
            if note["body"] == item["information_requests"][0]["body"]
        )
        verify(
            note["author"]["id"] == stand.manifest["users"]["reviewer"]["id"],
            "Information author differs from collected role",
        )
        prior.append(note["id"])
        verify(
            stand.request("GET", endpoint)["state"]
            == ("closed" if action == "close" else "opened"),
            "Information state postcondition differs",
        )
        cycles.append(
            {
                "action": action,
                "discussion": thread["id"],
                "note_ids": list(prior),
                "commands": copied,
            }
        )
        last_analysis = source
    assert last_analysis is not None
    fresh = helper(stand, runner, ["collect", "--source", issue["web_url"]], "reviewer")
    before = stand.request("GET", endpoint + "/discussions")
    stale = subprocess.run(
        [
            sys.executable,
            str(runner),
            "publish",
            "--collection",
            str(Path(fresh["artifact_root"]) / "current.json"),
            "--analysis",
            str(last_analysis),
        ],
        cwd=ROOT,
        env=stand.isolated_env("reviewer"),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    write_json(
        directory / "stale-analysis.json",
        {
            "exit_code": stale.returncode,
            "stdout": stand.redact(stale.stdout),
            "stderr": stand.redact(stale.stderr),
        },
    )
    verify(
        stale.returncode != 0 and "stale" in stale.stdout,
        "Old analysis was accepted against a changed collection",
    )
    verify(
        before == stand.request("GET", endpoint + "/discussions"), "Stale analysis mutated GitLab"
    )

    # Recreate an absent supported CE relationship from fresh helper evidence.
    links = stand.request("GET", f["prefix"] + f"/issues/{f['issue']['iid']}/links")
    link = next(link for link in links if link["iid"] == f["issues"][2]["iid"])
    stand.request(
        "DELETE", f["prefix"] + f"/issues/{f['issue']['iid']}/links/{link['issue_link_id']}"
    )
    collection = helper(stand, runner, ["collect", "--source", f["issue"]["web_url"]], "reviewer")
    item = copy.deepcopy(template)
    item["evidence_digest"] = collection["items"][0]["evidence_digest"]
    relation = item["issue_relations"][0]
    relation["existing_link"] = None
    item["proposed_changes"] = {
        "links": [
            {
                "target_project_id": relation["target_project_id"],
                "target_issue_iid": relation["target_issue_iid"],
                "link_type": "relates_to",
            }
        ]
    }
    source = directory / "relationship-recovery.json"
    write_json(
        source,
        {
            "collection_digest": collection["collection_digest"],
            "items": [item],
            "top_five": [],
            "parallel_groups": [],
            "questions": [],
        },
    )
    prepared = helper(
        stand,
        runner,
        [
            "publish",
            "--collection",
            str(Path(collection["artifact_root"]) / "current.json"),
            "--analysis",
            str(source),
        ],
        "reviewer",
    )
    copied = commands(Path(prepared["reports"][0]["report"]).read_text())
    for index, text in enumerate(copied):
        execute(stand, text, directory, f"recovery-{index}")
    restored = stand.request("GET", f["prefix"] + f"/issues/{f['issue']['iid']}/links")
    verify(
        sum(
            link["iid"] == relation["target_issue_iid"] and link["link_type"] == "relates_to"
            for link in restored
        )
        == 1,
        "CE relationship recovery missing or duplicated",
    )
    return {
        "origin": "real server with deterministic fixture analysis",
        "cycles": cycles,
        "stale_analysis_rejected": True,
        "relationship_restored": True,
    }
