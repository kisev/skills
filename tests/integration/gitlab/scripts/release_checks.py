"""Exact inventories/readiness and copied release commands on synthetic GitLab data."""

from __future__ import annotations

import copy
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
    results = {}
    for actor in ("author", "reviewer"):
        selected = private_directory(directory / ("release-" + actor + "-" + directory.name))
        issue = stand.request(
            "POST",
            original["prefix"] + "/issues",
            {"title": f"Release closure {actor} {directory.name}"},
            actor,
        )
        results[actor] = run_actor(stand, {**original, "issue": issue}, selected, report, actor)
        report["checks"].append(
            {"name": "release-role-" + actor, "status": "passed", "evidence": results[actor]}
        )
    return {"roles": results}


def run_actor(
    stand: Stand, original: dict[str, Any], directory: Path, report: dict[str, Any], actor: str
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
        stand,
        "release-prepare",
        ["prepare", "--url", f["mr"]["web_url"]],
        directory,
        "prepare",
        actor=actor,
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
        actor=actor,
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
        actor=actor,
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
        actor=actor,
    )
    negatives = publication_negatives(
        stand, f, directory, actor, evidence, inventory_result, source, plan, repo
    )
    readiness_evidence = readiness(stand, f, directory, actor)
    runbook = Path(plan["markdown_path"]).read_text()
    (directory / "pre-merge-runbook.md").write_text(runbook)
    copied = [text for text in commands(runbook) if "glab" in shlex.split(text)]
    verify(
        len(copied) == len([request for request in plan["requests"] if request["command"]]),
        "Pre-merge runbook lost a generated mutation command",
    )
    for index, text in enumerate(copied):
        execute(stand, text, directory, f"pre-merge-{index}", actor)
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
        actor=actor,
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
        and announcements[0]["author"]["id"] == stand.manifest["users"][actor]["id"],
        "Copied announcement or real prompt attachment is missing/duplicated",
    )
    write_json(directory / "server-announcement.json", announcements)
    post = invoke(
        stand,
        "release-prepare",
        ["post-merge", "--plan", plan["plan_path"], "--expected-binding", plan["binding"]],
        directory,
        "post-merge",
        actor=actor,
    )
    postbook = Path(post["markdown_path"]).read_text()
    (directory / "post-merge-runbook.md").write_text(postbook)
    for index, text in enumerate(
        text for text in commands(postbook) if "glab" in shlex.split(text)
    ):
        execute(stand, text, directory, f"post-merge-{index}", actor)
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
        "actor_id": stand.manifest["users"][actor]["id"],
        "negative_cases": negatives,
        "readiness": readiness_evidence,
        "receipt_origin": "deterministic content; not a real critic or agent run",
    }


def publication_negatives(
    stand: Stand,
    f: dict[str, Any],
    directory: Path,
    actor: str,
    evidence: dict[str, Any],
    inventory: dict[str, Any],
    source: Path,
    plan: dict[str, Any],
    repo: Path,
) -> list[str]:
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}"
    before = stand.request("GET", endpoint)
    discussions = pages(stand, endpoint + "/discussions")
    damaged = json.loads(Path(inventory["artifact_path"]).read_text())
    damaged["payload"]["complete"] = False
    damaged["payload"]["collection_completeness"]["work_items"] = False
    damaged_input = directory / "incomplete-inventory-input.json"
    write_json(damaged_input, damaged["payload"])
    incomplete = command(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            (
                "import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                "from portable_runtime.contract import write_artifact; "
                "print(write_artifact(Path(sys.argv[2]),'release_inventory',"
                "json.loads(Path(sys.argv[3]).read_text()))[0])"
            ),
            str(ROOT / ".build/skills/release-prepare/scripts"),
            evidence["artifact_root"],
            str(damaged_input),
        ],
        env=stand.isolated_env(actor),
    ).stdout.strip()
    cases = {
        "missing-inventory-boundary": [
            "inventory",
            "--evidence",
            evidence["artifact_path"],
            "--repo-root",
            str(repo),
            "--previous-ref",
            "absent-fixture-boundary",
        ],
        "incomplete-inventory": [
            "scaffold",
            "--bundle",
            evidence["artifact_path"],
            "--inventory",
            str(incomplete),
            "--content",
            str(source),
        ],
        "wrong-publication-binding": [
            "finalize",
            "--plan",
            plan["plan_path"],
            "--expected-binding",
            "0" * 64,
        ],
        "post-merge-before-merge": [
            "post-merge",
            "--plan",
            plan["plan_path"],
            "--expected-binding",
            plan["binding"],
        ],
    }
    for name, args in cases.items():
        refused = invoke(
            stand,
            "release-prepare",
            args,
            directory,
            name,
            actor=actor,
            expected=0 if name == "incomplete-inventory" else 2,
        )
        verify(refused["status"] != "ok", name + " was accepted")
        if name == "incomplete-inventory":
            verify(
                refused["status"] == "incomplete"
                and refused["plan_path"] is None
                and refused["markdown_path"] is None
                and not any(request["command"] for request in refused["requests"]),
                "Incomplete inventory exposed a publishable runbook",
            )
            finalized = invoke(
                stand,
                "release-prepare",
                [
                    "finalize",
                    "--plan",
                    refused["artifact_path"],
                    "--expected-binding",
                    refused["binding"],
                ],
                directory,
                "incomplete-inventory-finalize",
                actor=actor,
                expected=2,
            )
            verify(finalized["status"] != "ok", "Incomplete release plan finalized successfully")
        verify(
            before == stand.request("GET", endpoint)
            and discussions == pages(stand, endpoint + "/discussions"),
            name + " mutated the server",
        )
    return list(cases)


def readiness(
    stand: Stand, f: dict[str, Any], directory: Path, actor: str = "reviewer"
) -> dict[str, Any]:
    prepared = invoke(
        stand,
        "release-review",
        ["prepare", "--url", f["mr"]["web_url"]],
        directory,
        "review-prepare",
        actor=actor,
    )
    denied = invoke(
        stand,
        "release-review",
        ["prepare", "--url", f["mr"]["web_url"]],
        directory,
        "outsider-review-prepare",
        actor="outsider",
        expected=1,
    )
    verify(denied["status"] != "ok", "Unauthorized release review was accepted")
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
            actor=actor,
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
            actor=actor,
        )
        stored = json.loads(Path(recorded["artifact_path"]).read_text())["payload"]
        verify(
            stored["verdict"] == verdict
            and stored["readiness"] == (verdict == "ready")
            and finalized["result"]["release_readiness_valid"],
            "Readiness verdict or exact binding was lost",
        )
    negative_inputs: dict[str, dict[str, Any]] = {
        "wrong-evidence-digest": {"evidence_digest": "0" * 64},
        "inconsistent-verdict": {"verdict": "ready", "readiness": False},
        "external-mutation": {"external_mutations": True},
    }
    ready_source = json.loads((directory / "readiness-input-ready.json").read_text())
    stale_range = copy.deepcopy(ready_source)
    stale_range["gates"]["ci"]["range"]["head_sha"] = "0" * 40
    missing_gate = copy.deepcopy(ready_source)
    del missing_gate["gates"]["rollback"]
    candidates = {name: {**ready_source, **changes} for name, changes in negative_inputs.items()}
    candidates.update({"stale-gate-range": stale_range, "missing-gate": missing_gate})
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}"
    before = stand.request("GET", endpoint)
    discussions = pages(stand, endpoint + "/discussions")
    for name, value in candidates.items():
        source = directory / ("readiness-invalid-" + name + ".json")
        write_json(source, value)
        refused = invoke(
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
            "readiness-refused-" + name,
            actor=actor,
            expected=2,
        )
        verify(refused["status"] != "ok", "Invalid readiness was accepted")
    verify(
        before == stand.request("GET", endpoint)
        and discussions == pages(stand, endpoint + "/discussions"),
        "Readiness checks mutated the server",
    )
    return {
        "verdicts": ["ready", "not_ready", "blocked"],
        "negative_cases": list(candidates),
        "actor_id": stand.manifest["users"][actor]["id"],
    }
