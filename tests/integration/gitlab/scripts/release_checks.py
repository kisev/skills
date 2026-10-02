"""Exact inventories/readiness and copied release commands on synthetic GitLab data."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.checks import fixture, pipeline, review_environment, verify
from tests.integration.gitlab.scripts.preservation_checks import pages
from tests.integration.gitlab.scripts.publication_checks import commands, execute
from tests.integration.gitlab.scripts.stand import (
    ROOT,
    Stand,
    command,
    private_directory,
    write_json,
)


def invoke(
    stand: Stand,
    skill: str,
    args: list[str],
    directory: Path,
    name: str,
    actor: str = "reviewer",
    expected: int = 0,
) -> dict[str, Any]:
    runner = "prepare_release.py" if skill == "release-prepare" else "review_release.py"
    result = subprocess.run(
        [sys.executable, str(ROOT / ".build/skills" / skill / "scripts" / runner), *args],
        env=stand.isolated_env(actor),
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    observation = {
        "exit_code": result.returncode,
        "stdout": stand.redact(result.stdout),
        "stderr": stand.redact(result.stderr),
    }
    write_json(directory / (name + ".json"), observation)
    verify(
        result.returncode == expected,
        f"{name} exited {result.returncode}, expected {expected}: {observation['stderr']}",
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("Release helper returned a non-object result")
    return value


def checkout(stand: Stand, f: dict[str, Any], directory: Path) -> Path:
    repo = private_directory(stand.state / "release-repositories") / directory.name
    env = review_environment(stand)
    command(["git", "clone", stand.manifest["fixtures"]["http_url_to_repo"], str(repo)], env=env)
    command(["git", "-C", str(repo), "checkout", "--detach", f["head"]], env=env)
    return repo


def run(
    stand: Stand, original: dict[str, Any], directory: Path, report: dict[str, Any]
) -> dict[str, Any]:
    directory = private_directory(directory / "release-workflows")
    f = fixture(stand, private_directory(directory / ("release-" + directory.parent.name)))
    prefix = f["prefix"]
    component_branch = "component-" + directory.parent.name
    stand.request(
        "POST", prefix + "/repository/branches", {"branch": component_branch, "ref": f["head"]}
    )
    component_commit = stand.request(
        "POST",
        prefix + "/repository/commits",
        {
            "branch": component_branch,
            "commit_message": "Add synthetic release component",
            "actions": [
                {"action": "create", "file_path": "component.txt", "content": "component output\n"}
            ],
        },
    )
    component = stand.request(
        "POST",
        prefix + "/merge_requests",
        {
            "source_branch": component_branch,
            "target_branch": f["branch"],
            "title": "Synthetic release component",
            "description": "Component inventory fixture",
            "reviewer_ids": [stand.manifest["users"]["reviewer"]["id"]],
        },
    )
    for _ in range(60):
        actual = stand.request("GET", prefix + f"/merge_requests/{component['iid']}")
        write_json(directory / "component-before-merge.json", actual)
        if (actual.get("diff_refs") or {}).get("head_sha") == component_commit["id"] and actual.get(
            "detailed_merge_status"
        ) == "mergeable":
            break
        time.sleep(1)
    else:
        raise RuntimeError("Component exact diff and mergeability did not become ready")
    stand.request(
        "POST",
        prefix + f"/merge_requests/{component['iid']}/notes",
        {"body": "Reviewed synthetic component inventory"},
        "reviewer",
    )
    merged = stand.request(
        "PUT", prefix + f"/merge_requests/{component['iid']}/merge", {"sha": component_commit["id"]}
    )
    verify(merged["state"] == "merged", "Component fixture did not merge")
    f["head"] = stand.request("GET", prefix + "/repository/branches/" + f["branch"])["commit"]["id"]
    endpoint = prefix + f"/merge_requests/{f['mr']['iid']}"
    # Use the issue route recognized by GitLab closing references, not a guessed IID.
    issue_url = original["issue"]["web_url"].replace("/-/work_items/", "/-/issues/")
    stand.request("PUT", endpoint, {"description": "Synthetic release. Closes " + issue_url})
    for _ in range(60):
        f["mr"] = stand.request("GET", endpoint)
        if (f["mr"].get("diff_refs") or {}).get("head_sha") == f["head"]:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Release MR did not acquire the component head")
    write_json(directory / "fixture.json", {**f, "component": merged})
    pipeline(stand, f, directory, report)
    repo = checkout(stand, f, directory.parent)
    catalogs = {label["name"] for label in pages(stand, prefix + "/labels")}
    for name in ("type::release", "semver::patch"):
        if name not in catalogs:
            stand.request("POST", prefix + "/labels", {"name": name, "color": "#428BCA"})
    prepared = invoke(
        stand, "release-prepare", ["prepare", "--url", f["mr"]["web_url"]], directory, "prepare"
    )
    evidence = prepared["items"][0]
    denied = invoke(
        stand,
        "release-prepare",
        ["prepare", "--url", f["mr"]["web_url"]],
        directory,
        "outsider-prepare",
        actor="outsider",
        expected=1,
    )
    verify(denied["status"] != "ok", "Unauthorized release collection was accepted")
    inventory_result = invoke(
        stand,
        "release-prepare",
        [
            "inventory",
            "--evidence",
            evidence["artifact_path"],
            "--repo-root",
            str(repo),
            "--previous-ref",
            f["base"],
        ],
        directory,
        "inventory",
    )
    inventory = json.loads(Path(inventory_result["artifact_path"]).read_text())["payload"]
    verify(
        inventory["complete"]
        and inventory["head_sha"] == f["head"]
        and inventory["previous_sha"] == f["base"],
        "Inventory range is incomplete or stale",
    )
    verify(
        component["iid"] in {mr["iid"] for mr in inventory["merge_requests"]},
        "Actual merged component absent from inventory",
    )
    verify(
        any(item["iid"] == original["issue"]["iid"] for item in inventory["work_item_candidates"]),
        "Closing work item absent from inventory",
    )
    verify(
        any(
            user["username"] == stand.manifest["users"]["reviewer"]["username"]
            for user in inventory["reviewers"]
        ),
        "Actual component reviewer missing",
    )
    version = f"1.0.{1000 + f['mr']['iid']}"
    content = {
        "title": "Synthetic release v" + version,
        "description": "Release the exact synthetic inventory.\nLiteral `code`, $value and @here.\nCloses "
        + issue_url,
        "version": version,
        "announcement": "Synthetic release announcement; not a repository release.",
        "illustration_prompt": "Neutral abstract fixture illustration.",
        "label_intent": {
            "change_type": "release",
            "compatibility": "patch",
            "workflow_state": None,
            "urgency": None,
            "impact": None,
            "origin": None,
        },
        "milestone_title": "v" + version,
        "contributors": [person["display"] for person in inventory["contributors"]],
        "reviewers": ["@" + person["username"] for person in inventory["reviewers"]],
        "illustration_style": {"preset": "neutral_abstract", "reference": None, "custom": None},
        "work_items": [
            {
                "project_id": item["project_id"],
                "iid": item["iid"],
                "action": "close" if item["iid"] == original["issue"]["iid"] else "no_action",
                "rationale": "Close the completed synthetic release issue explicitly; retain related fixture issues that are not completed.",
                "uncertain": False,
                "comment": None,
            }
            for item in inventory["work_item_candidates"]
        ],
    }
    source = directory / "content.json"
    write_json(source, content)
    before = stand.request("GET", endpoint)
    plan = invoke(
        stand,
        "release-prepare",
        [
            "scaffold",
            "--bundle",
            evidence["artifact_path"],
            "--inventory",
            inventory_result["artifact_path"],
            "--content",
            str(source),
        ],
        directory,
        "scaffold",
    )
    verify(
        plan["status"] == "ok" and before == stand.request("GET", endpoint),
        "Release scaffold published or returned incomplete plan",
    )
    invoke(
        stand,
        "release-prepare",
        ["finalize", "--plan", plan["plan_path"], "--expected-binding", plan["binding"]],
        directory,
        "finalize",
    )
    readiness(stand, f, directory)
    runbook = Path(plan["markdown_path"]).read_text()
    (directory / "pre-merge-runbook.md").write_text(runbook)
    copied = [text for text in commands(runbook) if "glab" in shlex.split(text)]
    verify(
        len(copied) == len([request for request in plan["requests"] if request["command"]]),
        "Pre-merge runbook lost a generated mutation command",
    )
    for index, text in enumerate(copied):
        execute(stand, text, directory, f"pre-merge-{index}")
    actual = stand.request("GET", endpoint)
    verify(
        actual["state"] == "merged"
        and actual["title"] == content["title"]
        and actual["description"] == content["description"]
        and actual["milestone"]["title"] == content["milestone_title"]
        and set(actual["labels"]) == {"type::release", "semver::patch"},
        "Copied release MR publication differs from the approved content",
    )
    stale = invoke(
        stand,
        "release-prepare",
        ["finalize", "--plan", plan["plan_path"], "--expected-binding", plan["binding"]],
        directory,
        "stale-pre-merge-finalize",
        expected=2,
    )
    verify(stale["status"] == "stale", "Changed release evidence was incorrectly accepted as fresh")
    notes = pages(stand, endpoint + "/notes")
    announcements = [
        note for note in notes if not note["system"] and content["announcement"] in note["body"]
    ]
    verify(
        len(announcements) == 1
        and "/uploads/" in announcements[0]["body"]
        and announcements[0]["author"]["id"] == stand.manifest["users"]["reviewer"]["id"],
        "Copied announcement or real prompt attachment is missing/duplicated",
    )
    write_json(directory / "server-announcement.json", announcements)
    post = invoke(
        stand,
        "release-prepare",
        ["post-merge", "--plan", plan["plan_path"], "--expected-binding", plan["binding"]],
        directory,
        "post-merge",
    )
    postbook = Path(post["markdown_path"]).read_text()
    (directory / "post-merge-runbook.md").write_text(postbook)
    for index, text in enumerate(
        text for text in commands(postbook) if "glab" in shlex.split(text)
    ):
        execute(stand, text, directory, f"post-merge-{index}")
    release = stand.request("GET", prefix + "/releases/v" + version)
    verify(
        release["commit"]["id"] == actual["merge_commit_sha"]
        and release["description"] == content["description"],
        "Copied release publication is not bound to the exact merge commit/content",
    )
    write_json(directory / "server-release.json", release)
    milestones = pages(stand, prefix + "/milestones")
    selected = next(item for item in milestones if item["title"] == content["milestone_title"])
    verify(
        selected["state"] == "closed", "Copied release command did not close its selected milestone"
    )
    closed_issue = stand.request("GET", prefix + f"/issues/{original['issue']['iid']}")
    verify(closed_issue["state"] == "closed", "Copied release work-item closure failed")
    write_json(directory / "server-closed-issue.json", closed_issue)
    return {
        "head": f["head"],
        "component_mr": component["iid"],
        "inventory": inventory_result,
        "release": release["tag_name"],
        "publication_sha": release["commit"]["id"],
        "receipt_origin": "deterministic content; not a real critic or agent run",
    }


def readiness(stand: Stand, f: dict[str, Any], directory: Path) -> None:
    prepared = invoke(
        stand,
        "release-review",
        ["prepare", "--url", f["mr"]["web_url"]],
        directory,
        "review-prepare",
    )
    item = prepared["items"][0]
    bundle = json.loads(Path(item["artifact_path"]).read_text())["payload"]
    identity = {key: bundle[key] for key in ("base_sha", "start_sha", "head_sha")}
    for verdict in ("ready", "not_ready", "blocked"):
        value: dict[str, Any] = {
            "schema": "portable-gitlab/release-readiness/v2",
            "external_mutations": False,
            "evidence_digest": hashlib.sha256(Path(item["artifact_path"]).read_bytes()).hexdigest(),
            "verdict": verdict,
            "readiness": verdict == "ready",
            "gates": {
                name: {
                    "status": "passed",
                    "evidence": [
                        "Deterministic fixture assessment; exact files in fixture.json and real shell jobs/traces in pipeline.json. No model assessment claimed."
                    ],
                    "range": identity,
                }
                for name in ("semver", "compatibility", "migration", "rollback", "ci")
            },
        }
        if verdict != "ready":
            value["gates"]["ci"]["status"] = "failed" if verdict == "not_ready" else "blocked"
        source = directory / ("readiness-input-" + verdict + ".json")
        write_json(source, value)
        recorded = invoke(
            stand,
            "release-review",
            [
                "record-artifact",
                "--kind",
                "release_readiness",
                "--evidence",
                item["artifact_path"],
                "--input",
                str(source),
            ],
            directory,
            "readiness-record-" + verdict,
        )
        finalized = invoke(
            stand,
            "release-review",
            [
                "finalize",
                "--artifact-root",
                item["artifact_root"],
                "--report",
                recorded["artifact_path"],
            ],
            directory,
            "readiness-finalize-" + verdict,
        )
        stored = json.loads(Path(recorded["artifact_path"]).read_text())["payload"]
        verify(
            stored["verdict"] == verdict
            and stored["readiness"] == (verdict == "ready")
            and finalized["result"]["release_readiness_valid"],
            "Readiness verdict or exact binding was lost",
        )
