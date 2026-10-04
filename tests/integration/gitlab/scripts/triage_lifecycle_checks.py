"""Real information-request cycles and stale analysis; decisions remain fixtures."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.checks import verify
from tests.integration.gitlab.scripts.publication_checks import blocks, execute_block, helper
from tests.integration.gitlab.scripts.stand import ROOT, Stand, private_directory, write_json


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
        copied = blocks(Path(prepared["reports"][0]["report"]).read_text())
        lifecycle = [
            block
            for block in copied
            if item["information_requests"][0]["body"] in block
            or (action == "close" and '"state_event":"close"' in block)
        ]
        verify(
            len(lifecycle) == 1,
            "Information runbook lost the single guarded lifecycle block",
        )
        for index, block in enumerate(copied):
            execute_block(stand, block, directory, f"{action}-{index}", "reviewer")
        if action == "close":
            verify(
                '"state_event":"close"' in lifecycle[0]
                and lifecycle[0].index("--method POST")
                < lifecycle[0].index('"state_event":"close"'),
                "Closure block must publish the final message before the close event",
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

        # A repeated lifecycle block must stop on its own precondition.
        result = execute_stopped(stand, lifecycle[0], directory, f"{action}-replay", "reviewer")
        verify("regenerate" in result["stderr"], "Replay did not stop on a guard")

        # Another authenticated actor must be stopped before any write.
        result = execute_stopped(stand, lifecycle[0], directory, f"{action}-foreign", "author")
        verify(
            "user changed" in result["stderr"], "Foreign actor was not stopped by the user guard"
        )

        cycles.append(
            {
                "action": action,
                "discussion": thread["id"],
                "note_ids": list(prior),
                "blocks": copied,
            }
        )
        last_analysis = source
    assert last_analysis is not None

    # Two-actor current_user honesty: each actor's collection binds its own identity.
    for actor in ("author", "reviewer"):
        own = helper(stand, runner, ["collect", "--source", issue["web_url"]], actor)
        context = json.loads(Path(own["collection_path"]).read_text())["context"][
            f"localhost:{stand.manifest['fixtures']['id']}"
        ]
        verify(
            context["current_user"]["id"] == stand.manifest["users"][actor]["id"],
            "Collected current_user does not follow the authenticated actor",
        )

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
    recovery = blocks(Path(prepared["reports"][0]["report"]).read_text())
    verify(
        any("/links" in block and "--method POST" in block for block in recovery),
        "Recovery plan lost the link-creation block",
    )
    for index, block in enumerate(recovery):
        execute_block(stand, block, directory, f"recovery-{index}")
    restored = stand.request("GET", f["prefix"] + f"/issues/{f['issue']['iid']}/links")
    verify(
        sum(
            link["iid"] == relation["target_issue_iid"] and link["link_type"] == "relates_to"
            for link in restored
        )
        == 1,
        "CE relationship recovery missing or duplicated",
    )
    # Recreating an existing relation must stop on the absence guard.
    for index, block in enumerate(recovery):
        if "/links" in block and "--method POST" in block:
            result = execute_stopped(stand, block, directory, f"recovery-replay-{index}")
            verify("issue links changed" in result["stderr"], "Link replay did not stop on a guard")
    return {
        "origin": "real server with deterministic fixture analysis",
        "cycles": cycles,
        "stale_analysis_rejected": True,
        "relationship_restored": True,
    }


def execute_stopped(
    stand: Stand,
    block: str,
    directory: Path,
    name: str,
    actor: str = "reviewer",
) -> dict[str, Any]:
    """Run one copied block expecting a guard stop, never raising on failure."""
    from tests.integration.gitlab.scripts.publication_checks import validated_block

    validated_block(stand, block)
    result = subprocess.run(
        ["bash", "-ec", block + "\n"],
        cwd=ROOT,
        env=stand.isolated_env(actor),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    observation = {
        "block": block,
        "exit_code": result.returncode,
        "stdout": stand.redact(result.stdout),
        "stderr": stand.redact(result.stderr),
    }
    write_json(directory / (name + ".json"), observation)
    verify(
        result.returncode != 0,
        f"Expected the {name} guard to stop the block",
    )
    return observation
