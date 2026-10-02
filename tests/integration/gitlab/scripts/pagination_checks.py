"""Reusable real catalogs and shipped helper pagers; never synthetic page responses."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from tests.integration.gitlab.scripts.checks import verify
from tests.integration.gitlab.scripts.pagination_stress import resources
from tests.integration.gitlab.scripts.preservation_checks import pages
from tests.integration.gitlab.scripts.stand import APP, Stand, command, write_json

if TYPE_CHECKING:
    from pathlib import Path

CATALOG_SIZE = 101


def catalogs(stand: Stand) -> dict[str, str]:
    prefix = f"/projects/{stand.manifest['fixtures']['id']}"
    endpoint = {
        "issues": prefix + "/issues?state=all",
        "labels": prefix + "/labels?include_ancestor_groups=true",
        "active_milestones": prefix + "/milestones?state=active&include_parent_milestones=true",
        "closed_milestones": prefix + "/milestones?state=closed&include_parent_milestones=true",
        "milestones": prefix + "/milestones",
        "tags": prefix + "/repository/tags",
        "releases": prefix + "/releases",
    }
    for resource in ("issues", "active_milestones", "closed_milestones", "releases"):
        values = pages(stand, endpoint[resource])
        key = "tag_name" if resource == "releases" else "title"
        existing = {item[key] for item in values}
        names = {f"matrix-{resource}-{index:03}" for index in range(CATALOG_SIZE)}

        def create(name: str, resource: str = resource) -> None:
            if resource == "issues":
                stand.request("POST", prefix + "/issues", {"title": name})
            elif resource == "releases":
                stand.request(
                    "POST",
                    prefix + "/releases",
                    {
                        "tag_name": name,
                        "ref": "main",
                        "name": name,
                        "description": "Synthetic pagination catalog, not a product release.",
                    },
                )
            else:
                milestone = stand.request("POST", prefix + "/milestones", {"title": name})
                if resource == "closed_milestones":
                    stand.request(
                        "PUT", prefix + f"/milestones/{milestone['id']}", {"state_event": "close"}
                    )

        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(create, sorted(names - existing)))
        observed = pages(stand, endpoint[resource])
        verify(names <= {item[key] for item in observed}, "Real pagination catalog is incomplete")
    return {name: value.lstrip("/") for name, value in endpoint.items()}


def run(stand: Stand, directory: Path) -> dict[str, Any]:
    endpoints = catalogs(stand)
    endpoints.update(resources(stand))
    nonpaged = {"issue_links", "related_mrs", "closed_by", "closing_issues"}
    expected = {}
    for name, endpoint in endpoints.items():
        separator = "&" if "?" in endpoint else "?"
        first = stand.request("GET", "/" + endpoint + separator + "per_page=100&page=1")
        expected[name] = (
            first
            if name == "issue_links" or (name in nonpaged and len(first) > 100)
            else pages(stand, "/" + endpoint)
        )
    counts = {name: len(values) for name, values in expected.items()}
    write_json(directory / "pagination-resource-counts.json", counts)
    verify(
        all(
            count > 100 or (name == "issue_links" and count == 100)
            for name, count in counts.items()
        ),
        "Pager probes need actual second pages or the CE whole-collection link boundary: "
        + str(counts),
    )
    outcomes = {}
    common = {"labels", "mr_commits", "mr_discussions", "head_pipelines", "jobs", "bridges"}
    for skill in ("code-review", "mr-prepare", "release-prepare", "release-review", "task-triage"):
        # Python/TypeScript collectors share a pager across MR resources. Triage
        # additionally owns issue/milestone catalogs; release-review owns tags/releases.
        selected = {
            name: endpoint
            for name, endpoint in endpoints.items()
            if name
            in {
                "issues",
                "labels",
                "active_milestones",
                "closed_milestones",
                "tags",
                "releases",
                "issue_discussions",
                "issue_links",
                "related_mrs",
                "closed_by",
                "mr_discussions",
            }
        }
        if skill != "task-triage":
            selected = {
                name: endpoint
                for name, endpoint in endpoints.items()
                if name in common
                or (skill in ("code-review", "release-review") and name in ("tags", "releases"))
                or (skill == "mr-prepare" and name in ("tree", "template_tree"))
                or (
                    skill == "release-prepare"
                    and name
                    in (
                        "milestones",
                        "mr_notes",
                        "mr_pipelines",
                        "commit_associations",
                        "closing_issues",
                        "issue_links",
                    )
                )
            }
        for actor in ("author", "reviewer"):
            source = directory / f"pagination-{skill}-{actor}-input.json"
            write_json(source, {"skill": skill, "endpoints": selected})
            argv = (
                ["node", str(APP / "scripts/pagination_probe.mjs")]
                if skill == "code-review"
                else [sys.executable, str(APP / "scripts/pagination_probe.py")]
            )
            collected = json.loads(
                command([*argv, str(source)], env=stand.isolated_env(actor), timeout=240).stdout
            )
            write_json(directory / f"pagination-{skill}-{actor}.json", collected)
            for name, result in collected.items():
                key = (
                    "name"
                    if name == "tags"
                    else "tag_name"
                    if name == "releases"
                    else "path"
                    if name in ("tree", "template_tree")
                    else "id"
                )
                verify(
                    result["complete"] is True
                    and not result.get("errors")
                    and len(result["items"]) == len(expected[name])
                    and {item[key] for item in result["items"]}
                    == {item[key] for item in expected[name]},
                    f"{skill}/{actor} dropped real {name} pages: {result.get('errors', [])}",
                )
            outcomes[f"{skill}/{actor}"] = {
                name: {"count": len(result["items"]), "pages": result.get("pages")}
                for name, result in collected.items()
            }
    return {
        "catalogs": outcomes,
        "origin": "shipped helper pagers and real GitLab responses",
        "resource_counts": counts,
        "task_prepare": "No collection pager: supplied evidence is checked by the agent; copied publication is tested for both roles.",
    }
