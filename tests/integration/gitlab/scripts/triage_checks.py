"""Run actual task-triage collection/rendering and copy its CE publication commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.checks import verify
from tests.integration.gitlab.scripts.publication_checks import commands, execute, helper
from tests.integration.gitlab.scripts.stand import ROOT, Stand, private_directory, write_json


def run(stand: Stand, f: dict[str, Any], directory: Path) -> dict[str, Any]:
    directory = private_directory(directory / "task-triage-workflows")
    runner = ROOT / ".build/skills/task-triage/scripts/triage_task.py"
    milestone = stand.request(
        "POST", f["prefix"] + "/milestones", {"title": f"v2.0.{f['mr']['iid']}"}
    )
    results = {}
    for actor in ("author", "reviewer"):
        argv = [
            "collect",
            "--source",
            f["issues"][0]["web_url"],
            "--source",
            f["issues"][2]["web_url"],
            "--locale",
            "en",
        ]
        collected = helper(stand, runner, argv, actor)
        write_json(directory / (actor + "-collection.json"), collected)
        verify(
            collected["status"] == "ok" and not collected["errors"],
            "Triage helper collection is incomplete",
        )
        collection = json.loads(Path(collected["collection_path"]).read_text())
        context = collection["context"][f"localhost:{stand.manifest['fixtures']['id']}"]
        verify(
            context["current_user"]["id"] == stand.manifest["users"][actor]["id"],
            "Triage authenticated role mismatch",
        )
        verify(
            {f"matrix-page-{index:03}" for index in range(101)}
            <= {label["name"] for label in context["labels"]},
            "Triage helper dropped a catalog page",
        )
        items = []
        before = {}
        for item in collected["items"]:
            snapshot = json.loads(Path(item["evidence_path"]).read_text())
            issue = snapshot["issue"]
            before[issue["iid"]] = issue
            selected = issue["iid"] == f["issue"]["iid"]
            relations = []
            proposed: dict[str, Any] = {}
            if selected:
                target_iid = f["issues"][2]["iid"]
                existing = next(
                    (link for link in snapshot["links"] if link.get("iid") == target_iid), None
                )
                relations = [
                    {
                        "target_hostname": "localhost",
                        "target_project_id": stand.manifest["fixtures"]["id"],
                        "target_issue_iid": target_iid,
                        "relation_type": "relates_to",
                        "rationale": "The two synthetic outputs belong to the same fixture contract.",
                        "existing_link": {
                            "id": existing.get("issue_link_id", existing["id"]),
                            "relation_type": existing["link_type"],
                        }
                        if existing
                        else None,
                        "comment": None,
                    }
                ]
                proposed = {
                    "title": f"Triage {actor} {directory.parent.name}; $value",
                    "description": "Synthetic triage publication. Literal `code`, $value and @here.",
                    "labels": [*f["issue"]["labels"], "matrix-page-100"],
                    "links": []
                    if existing
                    else [
                        {
                            "target_project_id": stand.manifest["fixtures"]["id"],
                            "target_issue_iid": target_iid,
                            "link_type": "relates_to",
                        }
                    ],
                }
            items.append(
                {
                    "evidence_digest": item["evidence_digest"],
                    "actuality": {
                        "status": "current",
                        "rationale": "The observed fixture issue is open.",
                        "confidence": "high",
                    },
                    "duplicates": [],
                    "quality": {"verdict": "ready", "findings": []},
                    "issue_relations": relations,
                    "merge_requests": [],
                    "release_plan": {
                        "decision": {
                            "status": "accepted",
                            "rationale": "Deterministic fixture input; not a model semantic assessment.",
                            "confidence": "high",
                        },
                        "semver": {
                            "level": "patch",
                            "rationale": "Synthetic compatible text correction.",
                            "confidence": "high",
                        },
                        "release": {
                            "policy": "Synthetic test release policy, not a product release decision.",
                            "baseline_version": "1.0.0",
                            "target_version": milestone["title"][1:],
                            "impact": "major",
                            "rationale": "Exercise an observed active milestone on a compatible future line.",
                            "confidence": "high",
                        },
                        "milestone": {
                            "status": "selected",
                            "candidate": {
                                "project_id": stand.manifest["fixtures"]["id"],
                                "id": milestone["id"],
                                "title": milestone["title"],
                                "state": "active",
                                "version": milestone["title"][1:],
                            },
                            "rationale": "Exact milestone was collected from this fixture project.",
                            "confidence": "high",
                        },
                    },
                    "severity": "low",
                    "priority": "low",
                    "agent_recommendation": {
                        "proposal": "Publish the synthetic fixture metadata.",
                        "rationale": "Exercise copied commands against the real CE server.",
                        "assumptions": [
                            "These are fixture decisions, not a real agent assessment."
                        ],
                        "confidence": "high",
                        "alternatives": ["Leave the fixture unchanged."],
                        "reconsider_if": "The server snapshot changes.",
                    },
                    "recommendations": [],
                    "proposed_changes": proposed,
                }
            )
        source = directory / (actor + "-analysis-input.json")
        write_json(
            source,
            {
                "collection_digest": collected["collection_digest"],
                "items": items,
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
                str(Path(collected["artifact_root"]) / "current.json"),
                "--analysis",
                str(source),
            ],
            actor,
        )
        write_json(directory / (actor + "-plan.json"), prepared)
        verify(
            prepared["external_mutations"] is False and prepared["status"] == "ok",
            "Triage preparation is incomplete",
        )
        for iid, issue in before.items():
            verify(
                issue == stand.request("GET", f["prefix"] + f"/issues/{iid}", actor=actor),
                "Triage preparation mutated an issue",
            )
        copied = []
        for entry in prepared["reports"]:
            text = Path(entry["report"]).read_text()
            (directory / (actor + "-" + entry["iid"] + "-runbook.md")).write_text(text)
            copied.extend(commands(text))
        verify(bool(copied), "Triage produced no copied commands")
        for index, text in enumerate(copied):
            execute(stand, text, directory, f"{actor}-copied-{index}", actor)
        actual = stand.request("GET", f["prefix"] + f"/issues/{f['issue']['iid']}")
        desired = next(item["proposed_changes"] for item in items if item["proposed_changes"])
        verify(
            all(actual[key] == desired[key] for key in ("title", "description"))
            and set(actual["labels"]) == set(desired["labels"]),
            "Triage copied metadata differs from the plan",
        )
        verify(actual["milestone"]["id"] == milestone["id"], "Triage milestone command failed")
        links = stand.request("GET", f["prefix"] + f"/issues/{f['issue']['iid']}/links")
        verify(
            any(
                link["iid"] == f["issues"][2]["iid"] and link["link_type"] == "relates_to"
                for link in links
            ),
            "Copied CE relationship is missing",
        )
        results[actor] = {
            "commands": copied,
            "issue": actual,
            "links": links,
            "origin": "actual helpers with deterministic fixture decisions",
        }
    return results
