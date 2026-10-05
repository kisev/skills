"""Persistent synthetic MR/CI resources with real second pages, without executing jobs."""

from __future__ import annotations

import json
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast

from tests.integration.gitlab.scripts.checks import verify
from tests.integration.gitlab.scripts.preservation_checks import pages
from tests.integration.gitlab.scripts.stand import Stand, write_json


def resources(stand: Stand) -> dict[str, str]:
    pid = stand.manifest["fixtures"]["id"]
    prefix = f"/projects/{pid}"
    path = stand.state / "pagination-stress.json"
    if path.is_symlink():
        raise RuntimeError("Pagination state must not be a symlink")
    state: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {"project_id": pid}
    verify(state["project_id"] == pid, "Pagination fixture belongs to another project")
    if state.get("endpoints"):
        for endpoint in state["endpoints"].values():
            stand.fixture_scope("/" + endpoint)
        verify(
            stand.request("GET", prefix + "/repository/branches/matrix-pagination-source")[
                "commit"
            ]["id"]
            == state["head"],
            "Pagination fixture source head changed",
        )
        if state.get("version") == 3:
            return cast("dict[str, str]", state["endpoints"])
    if "base" not in state:
        state["base"] = stand.request("GET", prefix + "/repository/branches/main")["commit"]["id"]
        write_json(path, state)

    def branch(name: str, ref: str | None = None) -> None:
        try:
            observed = stand.request("GET", prefix + "/repository/branches/" + name)
            if ref is not None:
                verify(observed["commit"]["id"] == ref, "Pagination alias head changed")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            stand.request(
                "POST",
                prefix + "/repository/branches",
                {"branch": name, "ref": ref or state["base"]},
            )

    source = "matrix-pagination-source"
    branch(source)
    commits: dict[str, str] = {
        item["title"]: item["id"]
        for item in pages(stand, prefix + "/repository/commits?ref_name=" + source)
    }

    def commit(name: str, actions: list[dict[str, str]]) -> str:
        title = name + " [skip ci]"
        if title not in commits:
            commits[title] = stand.request(
                "POST",
                prefix + "/repository/commits",
                {"branch": source, "commit_message": title, "actions": actions},
            )["id"]
        return commits[title]

    big = "stages: [test]\n" + "".join(
        f"job_{i:03}:\n  stage: test\n  script: ['true']\n  when: manual\n  allow_failure: false\n"
        f"bridge_{i:03}:\n  stage: test\n  trigger:\n    include: child.yml\n  when: manual\n  allow_failure: false\n"
        for i in range(101)
    )
    actions = [
        {"action": "create", "file_path": filename, "content": content}
        for filename, content in (
            (".gitlab-ci.yml", big),
            ("child.yml", "child_job:\n  script: ['true']\n"),
            ("counter.txt", "0\n"),
            (".gitlab/merge_request_templates/Fixture.md", "Synthetic bounded template.\n"),
        )
    ]
    actions += [
        {"action": "create", "file_path": f"matrix-root-{i:03}.txt", "content": str(i)}
        for i in range(101)
    ]
    actions += [
        {
            "action": "create",
            "file_path": f".gitlab/merge_request_templates/matrix-{i:03}.txt",
            "content": str(i),
        }
        for i in range(101)
    ]
    for index in range(0, len(actions), 50):
        big_head = commit(f"Matrix files {index}", actions[index : index + 50])
    if "big_pipeline" not in state:
        existing = pages(stand, prefix + f"/pipelines?sha={big_head}&ref={source}")
        verify(len(existing) <= 1, "Unexpected duplicate large fixture pipelines")
        state["big_pipeline"] = (
            existing[0]
            if existing
            else stand.request("POST", prefix + "/pipeline", {"ref": source})
        )["id"]
        write_json(path, state)
    commit(
        "Matrix small CI",
        [
            {
                "action": "update",
                "file_path": ".gitlab-ci.yml",
                "content": "manual_job:\n  script: ['true']\n  when: manual\n  allow_failure: false\n",
            }
        ],
    )
    for index in range(1, 102):
        state["head"] = commit(
            f"Matrix commit {index:03}",
            [{"action": "update", "file_path": "counter.txt", "content": f"{index}\n"}],
        )
    write_json(path, state)
    pipelines = pages(stand, prefix + f"/pipelines?sha={state['head']}&ref={source}")
    api_pipelines = [pipeline for pipeline in pipelines if pipeline["source"] == "api"]
    verify(len(api_pipelines) <= 101, "Unexpected duplicate fixture API pipelines")
    # Manual jobs/bridges are deliberately not played: this measures collection,
    # while the ordinary shell-CI scenario independently verifies actual execution.
    for _ in range(101 - len(api_pipelines)):
        stand.request("POST", prefix + "/pipeline", {"ref": source})
    issues = [
        item
        for item in pages(stand, prefix + "/issues?state=all")
        if item["title"].startswith("matrix-issues-")
    ]
    verify(len(issues) == 101, "Missing issue catalog for relationship probes")
    hubs = [
        item
        for item in pages(stand, prefix + "/issues?state=all")
        if item["title"] == "matrix-pagination-hub"
    ]
    verify(len(hubs) <= 1, "Duplicate relationship hub")
    hub = (
        hubs[0]
        if hubs
        else stand.request("POST", prefix + "/issues", {"title": "matrix-pagination-hub"})
    )
    hub_endpoint = prefix + f"/issues/{hub['iid']}"
    first_links = stand.request("GET", hub_endpoint + "/links?per_page=100&page=1")
    linked = {item["iid"] for item in first_links}
    for issue in issues:
        if len(linked) < 100 and issue["iid"] not in linked:
            stand.request(
                "POST",
                hub_endpoint + "/links",
                {
                    "target_project_id": pid,
                    "target_issue_iid": issue["iid"],
                    "link_type": "relates_to",
                },
            )
            linked.add(issue["iid"])
    verify(len(linked) == 100, "The CE issue-link boundary is not fully populated")
    description = "Synthetic paging references.\n" + "\n".join(
        "Closes " + stand.manifest["fixtures"]["web_url"] + f"/-/issues/{item['iid']}"
        for item in [hub, *issues]
    )
    existing_mrs = pages(stand, prefix + f"/merge_requests?state=all&source_branch={source}")
    targets: dict[str, dict[str, Any]] = {item["target_branch"]: item for item in existing_mrs}

    def create_mr(index: int) -> dict[str, Any]:
        target = f"matrix-pagination-target-{index:03}"
        branch(target)
        if target in targets:
            return targets[target]
        created: dict[str, Any] = stand.request(
            "POST",
            prefix + "/merge_requests",
            {
                "source_branch": source,
                "target_branch": target,
                "title": f"Matrix association {index:03}",
                "description": description,
            },
        )
        return created

    mrs = [create_mr(0)]
    # GitLab recognizes automatic closing relationships only when the MR targets
    # the default branch. Use distinct source aliases rather than duplicate MRs.
    default_existing = {
        item["source_branch"]: item
        for item in pages(stand, prefix + "/merge_requests?state=all&target_branch=main")
    }
    thin_source = "matrix-pagination-thin-source"
    branch(thin_source)
    thin_commits = {
        item["title"]: item["id"]
        for item in pages(stand, prefix + "/repository/commits?ref_name=" + thin_source)
    }
    thin_title = "Matrix thin default fixture [skip ci]"
    state["thin_head"] = thin_commits.get(thin_title)
    if state["thin_head"] is None:
        state["thin_head"] = stand.request(
            "POST",
            prefix + "/repository/commits",
            {
                "branch": thin_source,
                "commit_message": thin_title,
                "actions": [
                    {
                        "action": "create",
                        "file_path": "matrix-thin.txt",
                        "content": "Synthetic single-file closing fixture.\n",
                    }
                ],
            },
        )["id"]
    write_json(path, state)
    thin_hubs = [
        item
        for item in pages(stand, prefix + "/issues?state=all")
        if item["title"] == "matrix-pagination-closing-hub"
    ]
    verify(len(thin_hubs) <= 1, "Duplicate closing relationship hub")
    thin_hub = (
        thin_hubs[0]
        if thin_hubs
        else stand.request("POST", prefix + "/issues", {"title": "matrix-pagination-closing-hub"})
    )
    thin_hub_endpoint = prefix + f"/issues/{thin_hub['iid']}"
    thin_reference = (
        "Closes " + stand.manifest["fixtures"]["web_url"] + f"/-/issues/{thin_hub['iid']}"
    )

    def create_default(index: int) -> dict[str, Any]:
        alias = f"matrix-pagination-thin-{index:03}"
        branch(alias, state["thin_head"])
        if alias in default_existing:
            return default_existing[alias]
        created: dict[str, Any] = stand.request(
            "POST",
            prefix + "/merge_requests",
            {
                "source_branch": alias,
                "target_branch": "main",
                "title": f"Matrix default closing {index:03}",
                "description": thin_reference + ("\n" + description if index == 0 else ""),
            },
        )
        return created

    default_mrs = []
    for start in range(0, 101, 10):
        with ThreadPoolExecutor(max_workers=4) as workers:
            batch = list(workers.map(create_default, range(start, min(start + 10, 101))))
        default_mrs.extend(batch)
        pending = [item["iid"] for item in batch]
        deadline = time.monotonic() + 60
        while pending and time.monotonic() < deadline:
            with ThreadPoolExecutor(max_workers=4) as workers:
                observed = list(
                    workers.map(
                        lambda iid: stand.request("GET", prefix + f"/merge_requests/{iid}"), pending
                    )
                )
            pending = [
                item["iid"]
                for item in observed
                if (item.get("diff_refs") or {}).get("head_sha") != state["thin_head"]
            ]
            if pending:
                time.sleep(1)
        verify(
            not pending,
            "Pagination MRs did not acquire their exact diff refs in 60 seconds: " + str(pending),
        )
    mr = mrs[0]
    mr_endpoint = prefix + f"/merge_requests/{mr['iid']}"
    notes = pages(stand, mr_endpoint + "/notes")
    bodies = {item["body"] for item in notes}
    for index in range(101):
        body = f"Matrix conversation {index:03}"
        if body not in bodies:
            stand.request("POST", mr_endpoint + "/notes", {"body": body}, "reviewer")
    issue_notes = {item["body"] for item in pages(stand, hub_endpoint + "/notes")}
    for index in range(101):
        body = f"Matrix issue conversation {index:03}"
        if body not in issue_notes:
            stand.request("POST", hub_endpoint + "/notes", {"body": body}, "reviewer")
    result = {
        "mr_commits": mr_endpoint + "/commits",
        "mr_discussions": mr_endpoint + "/discussions",
        "mr_notes": mr_endpoint + "/notes",
        "mr_pipelines": mr_endpoint + "/pipelines",
        "head_pipelines": prefix + f"/pipelines?sha={state['head']}",
        "jobs": prefix + f"/pipelines/{state['big_pipeline']}/jobs",
        "bridges": prefix + f"/pipelines/{state['big_pipeline']}/bridges",
        "tree": prefix + f"/repository/tree?ref={state['head']}",
        "template_tree": prefix
        + f"/repository/tree?ref={state['head']}&path=.gitlab%2Fmerge_request_templates",
        "commit_associations": prefix + f"/repository/commits/{state['thin_head']}/merge_requests",
        "closing_issues": prefix + f"/merge_requests/{default_mrs[0]['iid']}/closes_issues",
        "issue_links": hub_endpoint + "/links",
        "issue_discussions": hub_endpoint + "/discussions",
        "related_mrs": thin_hub_endpoint + "/related_merge_requests",
        "closed_by": thin_hub_endpoint + "/closed_by",
    }
    state["endpoints"] = {name: endpoint.lstrip("/") for name, endpoint in result.items()}
    state["version"] = 3
    write_json(path, state)
    return cast("dict[str, str]", state["endpoints"])
