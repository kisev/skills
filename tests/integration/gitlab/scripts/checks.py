"""Real GitLab postconditions. Fault injection is not server evidence."""

from __future__ import annotations

import base64
import json
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.stand import (
    APP,
    ROOT,
    Stand,
    command,
    load,
    private_directory,
    write_json,
)


def verify(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def record(report: dict[str, Any], name: str, evidence: object) -> None:
    report["checks"].append({"name": name, "status": "passed", "evidence": evidence})


def completed_coverage(report: dict[str, Any]) -> None:
    proven = {
        "exhaustive six-workflow helper pagination and author/reviewer matrix": {
            "helper-catalog-pagination",
            "read-only-workflow-collection",
            "reviewmatic-author-collection",
            "reviewmatic-plan",
            "mr-copied-publication",
            "task-copied-publication",
            "task-triage-publication",
            "release-role-author",
            "release-role-reviewer",
        },
        "complete release inventory/readiness/publication roles and negative-outcome matrix": {
            "release-role-author",
            "release-role-reviewer",
            "release-workflows",
        },
        "reviewmatic direct old/new/context, single-suggestion, reply and separate resolve/reopen commands": {
            "reviewmatic-direct-positions-and-single-suggestion",
            "reviewmatic-separate-replies-resolve-reopen",
        },
        "task-triage information-request lifecycle, stale analysis and relationship recovery": {
            "task-triage-lifecycle",
        },
        "same-file grouped suggestion stale-state recovery and semantic complete-fix reassessment": {
            "same-file-grouped-recovery",
        },
        "CLI faults, timeout and ambiguous-publication reconciliation": {
            "transport-fault-and-retry",
        },
    }
    passed = {entry["name"] for entry in report["checks"] if entry["status"] == "passed"}
    coverage = report["coverage"]
    coverage["proven"] = [
        {"criterion": criterion, "checks": sorted(required)}
        for criterion, required in proven.items()
        if required <= passed
    ]
    coverage["mandatory_remaining"] = [
        criterion
        for criterion in coverage["mandatory_remaining"]
        if criterion not in proven or not proven[criterion] <= passed
    ]
    coverage["status"] = "incomplete" if coverage["mandatory_remaining"] else "complete"


def fixture(stand: Stand, directory: Path) -> dict[str, Any]:
    pid = stand.manifest["fixtures"]["id"]
    prefix = f"/projects/{pid}"
    run_id = directory.name
    branch = "test-" + run_id
    stand.request("POST", prefix + "/repository/branches", {"branch": branch, "ref": "main"})
    actions = [
        {"action": "create", "file_path": "sample.txt", "content": "context\nold\nkeep\nlast\n"},
        {"action": "create", "file_path": "grouped.txt", "content": "before\nold first\nend\n"},
        {
            "action": "create",
            "file_path": "same.txt",
            "content": "before\nold first\nold second\nend\n",
        },
        {
            "action": "create",
            "file_path": "grouped-extra.txt",
            "content": "before\nold second\nend\n",
        },
        {
            "action": "create",
            "file_path": ".gitlab-ci.yml",
            "content": """stages: [test, child]
success:
  stage: test
  script: ['echo HARNESS_SUCCESS']
failure:
  stage: test
  script: ['echo HARNESS_FAILURE; exit 1']
  allow_failure: true
child:
  stage: child
  trigger:
    include: child.yml
    strategy: depend
""",
        },
        {
            "action": "create",
            "file_path": "child.yml",
            "content": "child_success:\n  script: ['echo HARNESS_CHILD']\n",
        },
    ]
    base = stand.request(
        "POST",
        prefix + "/repository/commits",
        {"branch": branch, "commit_message": "Add synthetic fixture", "actions": actions},
    )
    # Target contains the base fixture, so old, new and unchanged diff positions exist.
    target = "base-" + run_id
    stand.request("POST", prefix + "/repository/branches", {"branch": target, "ref": base["id"]})
    head = stand.request(
        "POST",
        prefix + "/repository/commits",
        {
            "branch": branch,
            "commit_message": "Change synthetic fixture",
            "actions": [
                {
                    "action": "update",
                    "file_path": "sample.txt",
                    "content": "context\nnew\nkeep\nlast\nadded\n",
                },
                {
                    "action": "update",
                    "file_path": "grouped.txt",
                    "content": "before\nnew first\nend\n",
                },
                {
                    "action": "update",
                    "file_path": "same.txt",
                    "content": "before\nnew first\nnew second\nend\n",
                },
                {
                    "action": "update",
                    "file_path": "grouped-extra.txt",
                    "content": "before\nnew second\nend\n",
                },
            ],
        },
    )
    mr = stand.request(
        "POST",
        prefix + "/merge_requests",
        {
            "source_branch": branch,
            "target_branch": target,
            "title": "Harness " + run_id,
            "description": "Synthetic review fixture. No production repository.",
        },
    )
    for _ in range(60):
        current = stand.request("GET", prefix + f"/merge_requests/{mr['iid']}")
        if (current.get("diff_refs") or {}).get("head_sha") == head["id"]:
            break
        time.sleep(1)
    else:
        raise RuntimeError("GitLab did not prepare the exact MR diff in 60 seconds")
    return {
        "prefix": prefix,
        "branch": branch,
        "target": target,
        "mr": current,
        "head": head["id"],
        "base": base["id"],
    }


def verify_runner(stand: Stand) -> None:
    path = stand.state / "runner.json"
    if path.is_symlink():
        raise RuntimeError("Runner credentials must not be symlinks")
    if not path.is_file():
        raise RuntimeError("Fixture Runner is not initialized; run task env:gitlab:up")
    ids = stand.docker("ps", "-q", "gitlab-runner").split()
    inspect = json.loads(command(["docker", "inspect", *ids]).stdout)[0]
    verify(not inspect["HostConfig"]["Privileged"], "Runner must not be privileged")
    verify(
        not any(
            "docker.sock" in mount["Source"] or "docker.sock" in mount["Destination"]
            for mount in inspect["Mounts"]
        ),
        "Runner has Docker socket",
    )


def pipeline(stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    verify_runner(stand)
    prefix = f["prefix"]
    created = stand.request("POST", prefix + "/pipeline", {"ref": f["branch"]})
    write_json(directory / "pipeline-created.json", created)
    observed = []
    for _ in range(180):
        current = stand.request("GET", prefix + f"/pipelines/{created['id']}")
        observed.append(current["status"])
        write_json(
            directory / "pipeline-observations.json",
            {"expected_sha": f["head"], "pipeline": current, "states": observed},
        )
        if current["status"] in ("success", "failed", "canceled", "skipped"):
            break
        time.sleep(2)
    else:
        raise RuntimeError("Real shell pipeline exceeded 360 seconds")
    verify(
        current["status"] == "success" and current["sha"] == f["head"],
        "Pipeline is unsuccessful or bound to another commit",
    )
    jobs = stand.request("GET", prefix + f"/pipelines/{created['id']}/jobs?per_page=100")
    write_json(directory / "jobs.json", jobs)
    verify(
        {j["name"]: j["status"] for j in jobs} == {"success": "success", "failure": "failed"},
        "Missing successful/failing shell jobs",
    )
    traces = []
    for job in jobs:
        output = command(
            ["glab", "api", f"projects/{stand.manifest['fixtures']['id']}/jobs/{job['id']}/trace"],
            env=stand.isolated_env(),
        ).stdout
        (directory / f"job-{job['id']}.txt").write_text(stand.redact(output))
        verify("HARNESS_" + job["name"].upper() in output, "Real job trace is missing")
        traces.append(job["id"])
    bridges = stand.request("GET", prefix + f"/pipelines/{created['id']}/bridges")
    write_json(directory / "bridges.json", bridges)
    verify(
        len(bridges) == 1 and bridges[0]["downstream_pipeline"]["sha"] == f["head"],
        "Missing exact-commit child pipeline",
    )
    child = bridges[0]["downstream_pipeline"]
    child_jobs = stand.request("GET", prefix + f"/pipelines/{child['id']}/jobs")
    write_json(directory / "child-jobs.json", child_jobs)
    verify(
        len(child_jobs) == 1 and child_jobs[0]["status"] == "success",
        "Child pipeline did not execute",
    )
    child_trace = command(
        [
            "glab",
            "api",
            f"projects/{stand.manifest['fixtures']['id']}/jobs/{child_jobs[0]['id']}/trace",
        ],
        env=stand.isolated_env(),
    ).stdout
    (directory / "child-trace.txt").write_text(stand.redact(child_trace))
    verify("HARNESS_CHILD" in child_trace, "Child trace missing")
    write_json(
        directory / "pipeline.json",
        {
            "pipeline": current,
            "jobs": jobs,
            "bridges": bridges,
            "child_jobs": child_jobs,
            "states": observed,
        },
    )
    record(
        report,
        "real-shell-ci",
        {
            "pipeline": current["id"],
            "sha": current["sha"],
            "states": sorted(set(observed)),
            "trace_jobs": traces,
            "child": child["id"],
        },
    )


def api_matrix(stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    prefix = f["prefix"]
    label = "harness-" + directory.name
    created_label = stand.request("POST", prefix + "/labels", {"name": label, "color": "#428BCA"})
    milestone = stand.request("POST", prefix + "/milestones", {"title": "v1.0.1-" + directory.name})
    issues = []
    for index in range(3):
        issues.append(
            stand.request(
                "POST",
                prefix + "/issues",
                {
                    "title": f"Harness {directory.name} {index}",
                    "description": "Synthetic bounded task",
                    "labels": label,
                    "milestone_id": milestone["id"],
                },
            )
        )
    linked = stand.request(
        "POST",
        prefix + f"/issues/{issues[0]['iid']}/links",
        {
            "target_project_id": stand.manifest["fixtures"]["id"],
            "target_issue_iid": issues[1]["iid"],
            "link_type": "relates_to",
        },
    )
    pages = command(
        [
            "glab",
            "api",
            f"projects/{stand.manifest['fixtures']['id']}/issues?labels={label}&per_page=1",
            "--paginate",
        ],
        env=stand.isolated_env(),
    ).stdout
    decoder = json.JSONDecoder()
    collected = []
    while pages.strip():
        page, end = decoder.raw_decode(pages.lstrip())
        collected.extend(page)
        pages = pages.lstrip()[end:]
    verify(
        {item["iid"] for item in collected} == {item["iid"] for item in issues},
        "CLI pagination incomplete",
    )
    for issue in issues:
        actual = stand.request("GET", prefix + f"/issues/{issue['iid']}")
        verify(
            label in actual["labels"] and actual["milestone"]["id"] == milestone["id"],
            "Label/milestone did not persist",
        )
    links = stand.request("GET", prefix + f"/issues/{issues[0]['iid']}/links")
    verify(any(item["iid"] == issues[1]["iid"] for item in links), "CE relates_to link missing")
    tag = "harness-" + directory.name
    stand.request("POST", prefix + "/repository/tags", {"tag_name": tag, "ref": f["head"]})
    release = stand.request(
        "POST",
        prefix + "/releases",
        {"tag_name": tag, "name": tag, "description": "Synthetic local release"},
    )
    actual = stand.request("GET", prefix + "/releases/" + tag)
    verify(actual["commit"]["id"] == f["head"], "Release bound to wrong commit")
    record(
        report,
        "ce-api-matrix",
        {
            "issues": [i["iid"] for i in issues],
            "label": created_label["id"],
            "milestone": milestone["id"],
            "link": linked,
            "release": release["tag_name"],
        },
    )
    f["issue"] = issues[0]
    f["issues"] = issues


def pagination_fixture(stand: Stand, directory: Path, report: dict[str, Any]) -> None:
    """Reuse a two-page catalog consumed by the actual workflow collectors."""
    preservation = load("gitlab_catalog_pages", APP / "scripts/preservation_checks.py")
    prefix = f"/projects/{stand.manifest['fixtures']['id']}"
    names = {f"matrix-page-{index:03}" for index in range(101)}
    current = {label["name"] for label in preservation.pages(stand, prefix + "/labels")}

    def create(name: str) -> Any:
        return stand.request("POST", prefix + "/labels", {"name": name, "color": "#428BCA"})

    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(create, sorted(names - current)))
    actual = preservation.pages(stand, prefix + "/labels")
    verify(names <= {label["name"] for label in actual}, "Two-page fixture catalog is incomplete")
    write_json(
        directory / "pagination-fixture.json", {"labels": sorted(names), "count": len(actual)}
    )
    record(
        report,
        "reused-two-page-label-catalog",
        {"count": len(actual), "fixture_labels": sorted(names)},
    )


def review_comments(
    stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]
) -> None:
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
    refs = f["mr"]["diff_refs"]
    threads = []
    for side, line in (("old", 2), ("new", 2), ("context", 3)):
        position: dict[str, Any] = {
            "position_type": "text",
            "base_sha": refs["base_sha"],
            "start_sha": refs["start_sha"],
            "head_sha": refs["head_sha"],
            "old_path": "sample.txt",
            "new_path": "sample.txt",
        }
        position.update({"old_line": line} if side == "old" else {"new_line": line})
        if side == "context":
            position["old_line"] = line
        payload: dict[str, Any] = {"body": f"Harness {side} {directory.name}", "position": position}
        path = directory / (side + "-payload.json")
        write_json(path, payload)
        output = command(
            [
                "glab",
                "api",
                endpoint.lstrip("/"),
                "--method",
                "POST",
                "--input",
                str(path),
                "-H",
                "Content-Type: application/json",
            ],
            env=stand.isolated_env("reviewer"),
        ).stdout
        thread = json.loads(output)
        verify(
            thread["notes"][0]["position"]["head_sha"] == f["head"],
            "Inline position bound to wrong head",
        )
        threads.append(thread)
    suggestion: dict[str, Any] = {
        "body": "Harness suggestion\n\n```suggestion:-0+0\nfixed\n```",
        "position": {
            "position_type": "text",
            "base_sha": refs["base_sha"],
            "start_sha": refs["start_sha"],
            "head_sha": refs["head_sha"],
            "old_path": "sample.txt",
            "new_path": "sample.txt",
            "new_line": 2,
        },
    }
    thread = stand.request("POST", endpoint, suggestion, "reviewer")
    verify(thread["notes"][0].get("suggestions"), "GitLab did not accept suggestion")
    threads.append(thread)
    first = threads[0]
    reply = stand.request(
        "POST", endpoint + "/" + first["id"] + "/notes", {"body": "Harness author reply"}
    )
    verify(reply["author"]["id"] == stand.manifest["users"]["author"]["id"], "Reply role mismatch")
    for resolved in (True, False):
        stand.request("PUT", endpoint + "/" + first["id"], {"resolved": resolved}, "reviewer")
        actual = stand.request("GET", endpoint + "/" + first["id"])
        verify(actual["notes"][0]["resolved"] == resolved, "Separate resolve/reopen failed")
    for actor, payload, expected in (
        ("outsider", {"body": "Denied"}, (403, 404)),
        (
            "reviewer",
            {"body": "Invalid", "position": {**suggestion["position"], "new_line": 9999}},
            (400, 422),
        ),
    ):
        try:
            stand.request("POST", endpoint, payload, actor)
        except urllib.error.HTTPError as exc:
            verify(exc.code in expected, "Unexpected rejection status")
        else:
            raise RuntimeError("GitLab accepted denied/invalid comment")
    f["threads"] = threads
    states = []
    for resolved in (True, False):
        thread = stand.request(
            "POST",
            endpoint,
            {
                "body": "Harness state " + ("closed" if resolved else "open"),
                "position": suggestion["position"],
            },
            "reviewer",
        )
        if resolved:
            stand.request("PUT", endpoint + "/" + thread["id"], {"resolved": True}, "reviewer")
        states.append({"id": thread["id"], "resolved": resolved})
    f["state_threads"] = states
    write_json(directory / "discussions.json", stand.request("GET", endpoint))
    record(
        report,
        "real-inline-comments",
        {
            "threads": [t["id"] for t in threads],
            "positions": [t["notes"][0].get("position") for t in threads],
            "suggestion": thread["notes"][0]["suggestions"],
        },
    )


def preparation(stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    mr_url = f["mr"]["web_url"]
    endpoint = f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
    before = stand.request("GET", endpoint)
    results = {}
    for actor, skill, runner in (
        (actor, skill, runner)
        for actor in ("author", "reviewer")
        for skill, runner in (
            ("mr-prepare", "prepare_mr.py"),
            ("release-prepare", "prepare_release.py"),
            ("release-review", "review_release.py"),
        )
    ):
        args = [
            sys.executable,
            str(ROOT / ".build/skills" / skill / "scripts" / runner),
            "prepare",
            "--url",
            mr_url,
        ]
        if skill == "mr-prepare":
            args.extend(["--locale", "en"])
        output = command(args, env=stand.isolated_env(actor), timeout=180).stdout
        result = json.loads(output)
        write_json(directory / (skill + "-" + actor + ".json"), result)
        verify(
            result["status"] == "ok"
            and all(
                item["status"] == "ok"
                and item["complete"] is True
                and all(item["components_complete"].values())
                and item["head_sha"] == f["head"]
                for item in result["items"]
            ),
            skill + " returned incomplete or wrong-commit evidence",
        )
        for item in result["items"]:
            bundle = json.loads(Path(item["artifact_path"]).read_text())["payload"]
            verify(
                {f"matrix-page-{index:03}" for index in range(101)}
                <= {label["name"] for label in bundle["labels"]["items"]}
                and bundle["labels"]["pages"] >= 2,
                skill + " helper lost a label catalog page",
            )
        results[skill + "-" + actor] = result
    output = command(
        [
            sys.executable,
            str(ROOT / ".build/skills/task-triage/scripts/triage_task.py"),
            "collect",
            "--source",
            f["issue"]["web_url"],
            "--locale",
            "en",
        ],
        env=stand.isolated_env(),
        timeout=180,
    ).stdout
    results["task-triage"] = json.loads(output)
    write_json(directory / "task-triage.json", results["task-triage"])
    verify(
        results["task-triage"]["status"] == "ok" and not results["task-triage"]["errors"],
        "Task triage collection is incomplete",
    )
    task: dict[str, Any] = {
        "version": 2,
        "plan_key": "harness-" + directory.name.lower(),
        "locale": "en",
        "batch_agreement": "",
        "items": [
            {
                "key": "synthetic",
                "title": "Synthetic task " + directory.name,
                "description": "Problem: exercise GitLab task publication.\nOutcome: preserve a local plan without creating an issue.\nVerification: compare the server issue catalog before and after preparation.",
                "target": {
                    "kind": "project",
                    "id": stand.manifest["fixtures"]["id"],
                    "url": stand.manifest["fixtures"]["web_url"],
                },
                "type": "issue",
                "metadata": {
                    "milestone_id": f["issue"]["milestone"]["id"],
                    "labels": f["issue"]["labels"],
                },
                "existing_iid": None,
                "checks": {
                    name: {
                        "status": "verified",
                        "detail": "Synthetic fixture input, not a model semantic assessment",
                    }
                    for name in ("target", "templates", "metadata", "duplicates", "semantics")
                },
            }
        ],
        "links": [],
    }
    issues_before = stand.request("GET", f["prefix"] + "/issues?per_page=100")
    for actor in ("author", "reviewer"):
        task["plan_key"] = "harness-" + directory.name.lower() + "-" + actor
        task["items"][0]["title"] = "Synthetic task " + directory.name + " " + actor
        input_path = directory / (
            "task-input.json" if actor == "author" else "task-reviewer-input.json"
        )
        write_json(input_path, task)
        output = command(
            [
                sys.executable,
                str(ROOT / ".build/skills/task-prepare/scripts/prepare_publication.py"),
                "--input",
                str(input_path),
                "--output-dir",
                str((directory / ("task-plan-" + actor)).relative_to(ROOT)),
            ],
            env=stand.isolated_env(actor),
            timeout=180,
        ).stdout
        result = json.loads(output)
        results["task-prepare-" + actor] = result
        verify(result["external_mutations"] is False, "Task preparation claims a mutation")
        write_json(directory / ("task-prepare-" + actor + ".json"), result)
    verify(
        issues_before == stand.request("GET", f["prefix"] + "/issues?per_page=100"),
        "Task preparation created an issue",
    )
    verify(before == stand.request("GET", endpoint), "Preparation published a discussion")
    record(report, "read-only-workflow-collection", results)


def review_environment(stand: Stand, actor: str = "reviewer") -> dict[str, str]:
    environment = stand.isolated_env(actor)
    user = stand.manifest["users"][actor]
    authorization = base64.b64encode((user["username"] + ":" + user["token"]).encode()).decode()
    environment.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": "Authorization: Basic " + authorization,
        }
    )
    return environment


def review_plan(stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    environment = review_environment(stand)
    repo = stand.state / "repositories" / directory.name
    private_directory(repo.parent)
    if repo.is_symlink():
        raise RuntimeError("Fixture checkout must not be a symlink")
    command(
        ["git", "clone", stand.manifest["fixtures"]["http_url_to_repo"], str(repo)], env=environment
    )
    command(["git", "-C", str(repo), "checkout", "--detach", f["head"]], env=environment)
    # The author collector prepares its own review worktrees next to its clone;
    # a shared clone would put them beside the reviewer's worktrees, whose
    # registry is per actor and would reject the unmanaged paths.
    author_repo = stand.state / "repositories" / (directory.name + "-author")
    private_directory(author_repo.parent)
    command(
        ["git", "clone", stand.manifest["fixtures"]["http_url_to_repo"], str(author_repo)],
        env=review_environment(stand, "author"),
    )
    command(
        ["git", "-C", str(author_repo), "checkout", "--detach", f["head"]],
        env=review_environment(stand, "author"),
    )
    author_input = directory / "author-collector-input.json"
    write_json(
        author_input, {"url": f["mr"]["web_url"], "repo": str(author_repo), "head": f["head"]}
    )
    author_before = stand.request(
        "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
    )
    author_collected = json.loads(
        command(
            [sys.executable, str(APP / "scripts/collector_roles.py"), str(author_input)],
            env=review_environment(stand, "author"),
            timeout=240,
        ).stdout
    )
    verify(
        author_before
        == stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"),
        "Author reviewmatic collection published discussions",
    )
    write_json(directory / "author-collector.json", author_collected)
    record(report, "reviewmatic-author-collection", author_collected)
    before = stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions")
    input_path = directory / "review-input.json"
    write_json(
        input_path,
        {
            "url": f["mr"]["web_url"],
            "repo": str(repo),
            "run": directory.name,
            "output": str(directory / "review-plan.json"),
            "phase": "draft",
            "require_pagination": True,
        },
    )
    drafted = json.loads(
        command(
            [sys.executable, str(APP / "scripts/review_plan.py"), str(input_path)],
            env=environment,
            timeout=240,
        ).stdout
    )
    pipeline(stand, f, private_directory(directory / "ci-refresh"), report)
    input_value = json.loads(input_path.read_text())
    input_value.update(phase="ci-finish", started=drafted["started"])
    write_json(input_path, input_value)
    result = json.loads(
        command(
            [sys.executable, str(APP / "scripts/review_plan.py"), str(input_path)],
            env=environment,
            timeout=240,
        ).stdout
    )
    verify(
        before
        == stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"),
        "Review preparation published comments",
    )
    record(
        report,
        "reviewmatic-plan",
        {
            "artifact_root": result["started"]["artifact_root"],
            "receipts": result["receipts"],
            "receipt_origin": "deterministic fixture, not a real critic run",
        },
    )
    record(report, "reviewmatic-presentation-repair", result["repair"])
    record(report, "reviewmatic-ci-only-refresh", result["ci_refresh"])
    publication = load("gitlab_review_publication", APP / "scripts/publication_checks.py")
    runbook = Path(result["finished"]["markdown_path"]).read_text()
    copied = []
    for index, action in enumerate(result["actions"]):
        if action["command"] not in runbook:
            raise RuntimeError("Reviewmatic action is absent from the copied runbook")
        state_before = {
            thread["id"]: stand.request(
                "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions/" + thread["id"]
            )
            for thread in f["state_threads"]
        }
        publication.execute(stand, action["command"], directory, f"reviewmatic-copied-{index}")
        for thread in f["state_threads"]:
            after = stand.request(
                "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions/" + thread["id"]
            )
            if action["operation"] == "reply":
                verify(
                    after["notes"][0]["resolved"]
                    == state_before[thread["id"]]["notes"][0]["resolved"],
                    "Copied reply implicitly changed thread state",
                )
            elif action["operation"] in ("resolve", "reopen"):
                verify(
                    len(after["notes"]) == len(state_before[thread["id"]]["notes"]),
                    "Separate state command unexpectedly published a reply",
                )
        copied.append(action["id"])
    actual = stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions")
    grouped = [
        thread
        for thread in actual
        if any("Harness grouped" in note["body"] for note in thread["notes"])
    ]
    verify(
        len(grouped) == 2 and all(thread["notes"][0].get("suggestions") for thread in grouped),
        "Reviewmatic copied grouped suggestions missing on server",
    )
    f["grouped_threads"] = grouped
    direct = {}
    for side in ("old", "new", "context"):
        matches = [
            note
            for thread in actual
            for note in thread["notes"]
            if note["body"].startswith("Harness direct " + side)
        ]
        verify(len(matches) == 1, "Copied direct " + side + " command missing or duplicated")
        note = matches[0]
        position = note["position"]
        expected = (
            {"old_line": 2, "new_line": None}
            if side == "old"
            else (
                {"old_line": None, "new_line": 5}
                if side == "new"
                else {"old_line": 3, "new_line": 3}
            )
        )
        verify(
            position["head_sha"] == f["head"]
            and position["old_path"] == position["new_path"] == "sample.txt"
            and all(position.get(key) == value for key, value in expected.items()),
            "Copied direct " + side + " position differs from the prepared exact-head command",
        )
        verify(
            note["author"]["id"] == stand.manifest["users"]["reviewer"]["id"],
            "Copied direct comment role mismatch",
        )
        if side == "new":
            verify(
                bool(note.get("suggestions")), "Copied single suggestion not recognized by GitLab"
            )
        direct[side] = {
            "note": note["id"],
            "position": position,
            "suggestions": note.get("suggestions", []),
        }
    record(report, "reviewmatic-direct-positions-and-single-suggestion", direct)
    states = [
        stand.request(
            "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions/" + thread["id"]
        )
        for thread in f["state_threads"]
    ]
    for original, actual_state in zip(f["state_threads"], states, strict=True):
        verify(
            actual_state["notes"][0]["resolved"] is not original["resolved"],
            "Copied independent resolve/reopen state missing",
        )
        replies = [
            note
            for note in actual_state["notes"][1:]
            if note["body"].startswith("Harness reviewmatic state")
        ]
        verify(
            len(replies) == 1
            and replies[0]["author"]["id"] == stand.manifest["users"]["reviewer"]["id"],
            "Copied state-thread reply missing, duplicated or wrong role",
        )
    record(report, "reviewmatic-separate-replies-resolve-reopen", {"threads": states})
    record(
        report,
        "reviewmatic-copied-commands",
        {"actions": copied, "grouped_threads": [thread["id"] for thread in grouped]},
    )
    material_input = directory / "material-refresh-input.json"
    write_json(
        material_input,
        {
            "draft": result["started"]["draft_path"],
            "artifact_root": result["started"]["artifact_root"],
            "output": str(directory / "material-refresh.json"),
        },
    )
    before_refresh = stand.request(
        "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
    )
    refreshed = json.loads(
        command(
            [sys.executable, str(APP / "scripts/refresh_review.py"), str(material_input)],
            env=environment,
            timeout=240,
        ).stdout
    )
    verify(
        before_refresh
        == stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"),
        "Material review refresh published a discussion",
    )
    record(report, "reviewmatic-material-refresh", refreshed)


# Dependency-closed smoke subset: it needs only the fixture project and the
# stand itself - no reviewmatic install, no publication or triage chains - and
# skips the coverage gate by design (the full run owns the gate).
SMOKE_SCENARIOS = (
    "fixture",
    "pagination-fixture",
    "ce-api-matrix",
    "real-shell-ci",
    "real-inline-comments",
)


def scenario_names(action: str) -> tuple[str, ...]:
    """The scenario set for one action: smoke is a subset of the full run."""
    if action == "smoke":
        return SMOKE_SCENARIOS
    return (
        "fixture",
        "pagination-fixture",
        "helper-catalog-pagination",
        "ce-api-matrix",
        "real-shell-ci",
        "real-inline-comments",
        "workflow-collection",
        "transport-fault-and-retry",
        "mr-copied-publication",
        "task-copied-publication",
        "task-triage-publication",
        "task-triage-lifecycle",
        "reviewmatic",
        "same-file-grouped-recovery",
        "release-workflows",
        "automation-scope",
    )


def run(stand: Stand, directory: Path, report: dict[str, Any], action: str) -> None:
    if action == "live":
        f = fixture(stand, directory)
        write_json(directory / "fixture.json", f)
        report["coverage"] = {
            "status": "optional-live",
            "workflows": ["mr-prepare"],
            "mandatory_matrix_proven": False,
        }
        report["live"] = load("gitlab_live", APP / "scripts/live_checks.py").run(
            stand, f, directory
        )
        return
    if action == "browser":
        report["coverage"] = {"status": "deferred-browser", "mandatory_matrix_proven": False}
        f = fixture(stand, directory)
        api_matrix(stand, f, directory, report)
        pipeline(stand, f, directory, report)
        review_comments(stand, f, directory, report)
        pagination_fixture(stand, directory, report)
        review_plan(stand, f, directory, report)
        load("gitlab_browser", APP / "scripts/browser_checks.py").run(stand, f, directory, report)
        record(
            report,
            "same-file-browser-recovery",
            load("gitlab_same_file", APP / "scripts/same_file_checks.py").run(
                stand, directory, report, browser=True
            ),
        )
        return
    if action == "smoke":
        report["coverage"] = {
            "status": "smoke",
            "scope": "dependency-closed API/backend subset; the full run owns the coverage gate",
            "deferred": [
                "helper catalog pagination and the workflow matrix",
                "reviewmatic, same-file, triage, and release scenarios",
            ],
            "mandatory_matrix_proven": False,
        }
    else:
        report["coverage"] = {
            "status": "incomplete",
            "scope": "GitLab API/backend acceptance; browser behavior is deferred and unverified",
            "deferred": [
                "all GitLab browser scenarios, including exact-head UI remapping and application"
            ],
            "mandatory_remaining": [
                "exhaustive six-workflow helper pagination and author/reviewer matrix",
                "reviewmatic direct old/new/context, single-suggestion, reply and separate resolve/reopen commands",
                "same-file grouped suggestion stale-state recovery and semantic complete-fix reassessment",
                "task-triage information-request lifecycle, stale analysis and relationship recovery",
                "complete release inventory/readiness/publication roles and negative-outcome matrix",
                "CLI faults, timeout and ambiguous-publication reconciliation",
            ],
            "fault_injection": "synthetic CLI transport rejection and separate real-server read-only retry; not server behavior",
        }
    names = scenario_names(action)
    report["scenarios"] = [{"name": name, "status": "not-run"} for name in names]

    def scenario(name: str, operation: Any) -> Any:
        entry = next(item for item in report["scenarios"] if item["name"] == name)
        entry["started_at"] = datetime.now(UTC).isoformat()
        started = time.monotonic()
        try:
            result = operation()
        except Exception as exc:
            entry.update(status="failed", error=stand.redact(str(exc)))
            if action != "smoke":
                completed_coverage(report)
            raise
        else:
            entry["status"] = "passed"
            return result
        finally:
            entry["duration_seconds"] = round(time.monotonic() - started, 3)

    selected = set(names)
    f = scenario("fixture", lambda: fixture(stand, directory))
    write_json(directory / "fixture.json", f)
    scenario("pagination-fixture", lambda: pagination_fixture(stand, directory, report))
    if "helper-catalog-pagination" in selected:
        record(
            report,
            "helper-catalog-pagination",
            scenario(
                "helper-catalog-pagination",
                lambda: load("gitlab_pagination_checks", APP / "scripts/pagination_checks.py").run(
                    stand, directory
                ),
            ),
        )
    scenario("ce-api-matrix", lambda: api_matrix(stand, f, directory, report))
    scenario("real-shell-ci", lambda: pipeline(stand, f, directory, report))
    scenario("real-inline-comments", lambda: review_comments(stand, f, directory, report))
    if "workflow-collection" in selected:
        scenario("workflow-collection", lambda: preparation(stand, f, directory, report))
    if "transport-fault-and-retry" in selected:
        faults = load("gitlab_faults", APP / "scripts/fault_checks.py")
        record(
            report,
            "transport-fault-and-retry",
            scenario("transport-fault-and-retry", lambda: faults.run(stand, f, directory)),
        )
    if "mr-copied-publication" in selected:
        publication = load("gitlab_publication", APP / "scripts/publication_checks.py")
        record(
            report,
            "mr-copied-publication",
            scenario("mr-copied-publication", lambda: publication.mr(stand, f, directory)),
        )
        record(
            report,
            "task-copied-publication",
            scenario("task-copied-publication", lambda: publication.task(stand, f, directory)),
        )
    if "task-triage-publication" in selected:
        triage = load("gitlab_triage_checks", APP / "scripts/triage_checks.py")
        record(
            report,
            "task-triage-publication",
            scenario("task-triage-publication", lambda: triage.run(stand, f, directory)),
        )
        triage_lifecycle = load(
            "gitlab_triage_lifecycle", APP / "scripts/triage_lifecycle_checks.py"
        )
        record(
            report,
            "task-triage-lifecycle",
            scenario("task-triage-lifecycle", lambda: triage_lifecycle.run(stand, f, directory)),
        )
    if "reviewmatic" in selected:
        scenario("reviewmatic", lambda: review_plan(stand, f, directory, report))
    if "same-file-grouped-recovery" in selected:
        same_file = load("gitlab_same_file_checks", APP / "scripts/same_file_checks.py")
        record(
            report,
            "same-file-grouped-recovery",
            scenario("same-file-grouped-recovery", lambda: same_file.run(stand, directory, report)),
        )
    if "release-workflows" in selected:
        releases = load("gitlab_release_checks", APP / "scripts/release_checks.py")
        record(
            report,
            "release-workflows",
            scenario("release-workflows", lambda: releases.run(stand, f, directory, report)),
        )
    if "automation-scope" in selected:
        record(
            report,
            "automation-scope",
            scenario(
                "automation-scope",
                lambda: {"scope": "fixtures only", "manual_contents_inspected": False},
            ),
        )

    if action == "smoke":
        return
    completed_coverage(report)
    if report["coverage"]["mandatory_remaining"]:
        raise RuntimeError(
            "Baseline scenarios completed but mandatory workflow coverage is incomplete; see result.json coverage"
        )
