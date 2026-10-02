"""Real GitLab postconditions. Fault injection is not server evidence."""

from __future__ import annotations

import base64
import json
import secrets
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

from stand import APP, ROOT, Stand, command, load, private_directory, write_json


def verify(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def record(report: dict[str, Any], name: str, evidence: object) -> None:
    report["checks"].append({"name": name, "status": "passed", "evidence": evidence})


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


def register_runner(stand: Stand) -> None:
    path = stand.state / "runner.json"
    if path.is_symlink():
        raise RuntimeError("Runner credentials must not be symlinks")
    if path.exists():
        runner = json.loads(path.read_text())
    else:
        runner = stand.request(
            "POST",
            "/user/runners",
            {
                "runner_type": "project_type",
                "project_id": stand.manifest["fixtures"]["id"],
                "description": "Owned shell harness",
                "run_untagged": True,
                "locked": True,
            },
        )
        write_json(path, runner)
    # Token is sent via stdin, never Docker process arguments.
    config = f"""concurrent = 2
check_interval = 1
[[runners]]
  name = "Owned shell harness"
  url = "http://gitlab"
  token = {json.dumps(runner["token"])}
  executor = "shell"
  clone_url = "http://gitlab"
  builds_dir = "/home/gitlab-runner/builds"
"""
    stand.docker(
        "exec",
        "-T",
        "runner",
        "sh",
        "-c",
        "umask 077; cat > /etc/gitlab-runner/config.toml",
        data=config,
    )
    stand.docker("restart", "runner")
    ids = stand.docker("ps", "-q", "runner").split()
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
    register_runner(stand)
    prefix = f["prefix"]
    created = stand.request("POST", prefix + "/pipeline", {"ref": f["branch"]})
    observed = []
    for _ in range(180):
        current = stand.request("GET", prefix + f"/pipelines/{created['id']}")
        observed.append(current["status"])
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
        verify("HARNESS_" + job["name"].upper() in output, "Real job trace is missing")
        (directory / f"job-{job['id']}.txt").write_text(stand.redact(output))
        traces.append(job["id"])
    bridges = stand.request("GET", prefix + f"/pipelines/{created['id']}/bridges")
    verify(
        len(bridges) == 1 and bridges[0]["downstream_pipeline"]["sha"] == f["head"],
        "Missing exact-commit child pipeline",
    )
    child = bridges[0]["downstream_pipeline"]
    child_jobs = stand.request("GET", prefix + f"/pipelines/{child['id']}/jobs")
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
    verify("HARNESS_CHILD" in child_trace, "Child trace missing")
    (directory / "child-trace.txt").write_text(stand.redact(child_trace))
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
        payload = {"body": f"Harness {side} {directory.name}", "position": position}
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
    suggestion = {
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
    for skill, runner in (
        ("mr-prepare", "prepare_mr.py"),
        ("release-prepare", "prepare_release.py"),
        ("release-review", "review_release.py"),
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
        output = command(args, env=stand.isolated_env("reviewer"), timeout=180).stdout
        result = json.loads(output)
        write_json(directory / (skill + ".json"), result)
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
        results[skill] = result
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
    task = {
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
    input_path = directory / "task-input.json"
    write_json(input_path, task)
    issues_before = stand.request("GET", f["prefix"] + "/issues?per_page=100")
    output = command(
        [
            sys.executable,
            str(ROOT / ".build/skills/task-prepare/scripts/prepare_publication.py"),
            "--input",
            str(input_path),
            "--output-dir",
            str((directory / "task-plan").relative_to(ROOT)),
        ],
        env=stand.isolated_env(),
        timeout=180,
    ).stdout
    results["task-prepare"] = json.loads(output)
    verify(
        results["task-prepare"]["external_mutations"] is False, "Task preparation claims a mutation"
    )
    verify(
        issues_before == stand.request("GET", f["prefix"] + "/issues?per_page=100"),
        "Task preparation created an issue",
    )
    write_json(directory / "task-prepare.json", results["task-prepare"])
    verify(before == stand.request("GET", endpoint), "Preparation published a discussion")
    record(report, "read-only-workflow-collection", results)


def review_plan(stand: Stand, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    environment = stand.isolated_env("reviewer")
    user = stand.manifest["users"]["reviewer"]
    authorization = base64.b64encode((user["username"] + ":" + user["token"]).encode()).decode()
    environment.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraHeader",
            "GIT_CONFIG_VALUE_0": "Authorization: Basic " + authorization,
        }
    )
    repo = stand.state / "repositories" / directory.name
    private_directory(repo.parent)
    if repo.is_symlink():
        raise RuntimeError("Fixture checkout must not be a symlink")
    command(
        ["git", "clone", stand.manifest["fixtures"]["http_url_to_repo"], str(repo)], env=environment
    )
    command(["git", "-C", str(repo), "checkout", "--detach", f["head"]], env=environment)
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
        },
    )
    drafted = json.loads(
        command(
            ["node", str(APP / "scripts/review_plan.mjs"), str(input_path)],
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
            ["node", str(APP / "scripts/review_plan.mjs"), str(input_path)],
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
        publication.execute(stand, action["command"], directory, f"reviewmatic-copied-{index}")
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
    record(
        report,
        "reviewmatic-copied-commands",
        {"actions": copied, "grouped_threads": [thread["id"] for thread in grouped]},
    )
    tui = load("gitlab_tui", APP / "scripts/tui_checks.py")
    record(report, "reviewmatic-real-tui", tui.run(stand, f, result, directory))
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
            ["node", str(APP / "scripts/refresh_review.mjs"), str(material_input)],
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


def reset_check(stand: Stand, directory: Path, report: dict[str, Any]) -> None:
    preservation = load("gitlab_reset_preservation", APP / "scripts/preservation_checks.py")
    primary = preservation.snapshot(stand)
    disposable = Stand(
        "gl-reset-" + secrets.token_hex(5), stand.port + 1, " ".join(stand.compose[:-4])
    )
    disposable.start()
    disposable.bootstrap()
    write_json(disposable.reports / "sentinel.json", {"retained": True})
    previous_owner = disposable.manifest["owner"]
    plan = disposable.reset_plan()
    write_json(directory / "reset-scope.json", plan)
    for confirmation in ("", "0" * 64):
        try:
            disposable.reset(confirmation)
        except RuntimeError as exc:
            verify("confirmation" in str(exc), "Reset refused for an unexpected reason")
        else:
            raise RuntimeError("Reset accepted absent or mismatched scope confirmation")
        verify(disposable.reset_plan() == plan, "Rejected reset mutated resources")
        verify(disposable.manifest["owner"] == previous_owner, "Rejected reset changed credentials")
    disposable.reset(plan["digest"])
    verify(disposable.manifest["owner"] != previous_owner, "Reset retained credentials")
    verify((disposable.reports / "sentinel.json").exists(), "Reset removed reports")
    preservation.verify(primary, preservation.snapshot(stand))
    record(
        report,
        "reset-isolation",
        {"project": disposable.project, "primary_free_preserved": True, "report": str(directory)},
    )
    # Disposable data remain until the user confirms that stand's separate reset.
    disposable.docker("down")


def run(stand: Stand, directory: Path, report: dict[str, Any], action: str) -> None:
    if action == "reset-test":
        reset_check(stand, directory, report)
        return
    report["coverage"] = {
        "status": "incomplete",
        "mandatory_remaining": [
            "exhaustive six-workflow helper pagination and author/reviewer matrix",
            "reviewmatic old/new/context and single-suggestion commands; separate resolve/reopen and issue actions in TUI/browser",
            "same-file grouped suggestion stale-state recovery and semantic complete-fix reassessment",
            "task-triage analysis/publication and supported CE relationships through actual helpers",
            "complete release inventory, readiness and manual publication workflows",
            "in-flight mutation cancellation, timeout and controlled retry after ambiguous writes",
            "free-zone upload/snippet payloads and arbitrary data beyond the fingerprinted local free directory",
        ],
        "fault_injection": "synthetic CLI transport rejection and separate real-server read-only retry; not server behavior",
    }
    preservation = load("gitlab_preservation", APP / "scripts/preservation_checks.py")
    free_before = preservation.snapshot(stand)
    write_json(directory / "free-before.json", free_before)
    names = (
        "fixture",
        "ce-api-matrix",
        "real-shell-ci",
        "real-inline-comments",
        "workflow-collection",
        "transport-fault-and-retry",
        "mr-copied-publication",
        "task-copied-publication",
        "reviewmatic",
        "browser",
        "free-zone-preservation",
        "down-up-preservation",
    )
    report["scenarios"] = [{"name": name, "status": "not-run"} for name in names]

    def scenario(name: str, operation: Any) -> Any:
        entry = next(item for item in report["scenarios"] if item["name"] == name)
        started = time.monotonic()
        try:
            result = operation()
        except Exception as exc:
            entry.update(status="failed", error=stand.redact(str(exc)))
            raise
        else:
            entry["status"] = "passed"
            return result
        finally:
            entry["duration_seconds"] = round(time.monotonic() - started, 3)

    f = scenario("fixture", lambda: fixture(stand, directory))
    write_json(directory / "fixture.json", f)
    scenario("ce-api-matrix", lambda: api_matrix(stand, f, directory, report))
    scenario("real-shell-ci", lambda: pipeline(stand, f, directory, report))
    scenario("real-inline-comments", lambda: review_comments(stand, f, directory, report))
    scenario("workflow-collection", lambda: preparation(stand, f, directory, report))
    faults = load("gitlab_faults", APP / "scripts/fault_checks.py")
    record(
        report,
        "transport-fault-and-retry",
        scenario("transport-fault-and-retry", lambda: faults.run(stand, f, directory)),
    )
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
    scenario("reviewmatic", lambda: review_plan(stand, f, directory, report))
    browser = load("gitlab_browser", APP / "scripts/browser_checks.py")
    scenario("browser", lambda: browser.run(stand, f, directory, report))

    def retained_free(filename: str) -> dict[str, Any]:
        observed = preservation.snapshot(stand)
        write_json(directory / filename, observed)
        preservation.verify(free_before, observed)
        return {"project_id": stand.manifest["free"]["id"], "fingerprints": len(observed)}

    record(
        report,
        "free-zone-preserved",
        scenario("free-zone-preservation", lambda: retained_free("free-after.json")),
    )

    def retaining_restart() -> dict[str, Any]:
        stand.resources()
        stand.docker("down")
        stand.start()
        return retained_free("free-after-restart.json")

    record(report, "free-zone-down-up", scenario("down-up-preservation", retaining_restart))
    if action == "live":
        report["live"] = load("gitlab_live", APP / "scripts/live_checks.py").run(
            stand, f, directory
        )
    if report["coverage"]["mandatory_remaining"]:
        raise RuntimeError(
            "Baseline scenarios completed but mandatory workflow coverage is incomplete; see result.json coverage"
        )
