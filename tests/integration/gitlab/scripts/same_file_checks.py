"""Same-file grouped suggestions, exact-head remapping and backend reassessment."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.browser_checks import (
    Browser,
    apply,
    network_metadata,
    refresh,
)
from tests.integration.gitlab.scripts.checks import fixture, pipeline, review_environment, verify
from tests.integration.gitlab.scripts.publication_checks import execute
from tests.integration.gitlab.scripts.release_checks import checkout
from tests.integration.gitlab.scripts.stand import (
    APP,
    Stand,
    command,
    private_directory,
    write_json,
)


def run(stand: Stand, directory: Path, report: dict[str, Any]) -> dict[str, Any]:
    directory = private_directory(directory / ("same-file-" + directory.name))
    f = fixture(stand, directory)
    pipeline(stand, f, directory, report)
    repo = checkout(stand, f, directory)
    environment = review_environment(stand)
    source = directory / "input.json"
    write_json(
        source,
        {
            "url": f["mr"]["web_url"],
            "repo": str(repo),
            "run": directory.name,
            "output": str(directory / "plan.json"),
            "same_file": True,
        },
    )
    before = stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions")
    result = json.loads(
        command(
            ["node", str(APP / "scripts/review_plan.mjs"), str(source)],
            env=environment,
            timeout=240,
        ).stdout
    )
    verify(
        before
        == stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"),
        "Same-file preparation published comments",
    )
    runbook = Path(result["finished"]["markdown_path"]).read_text()
    (directory / "runbook.md").write_text(runbook)
    for index, action in enumerate(result["actions"]):
        verify(action["command"] in runbook, "Same-file action missing from actual runbook")
        execute(stand, action["command"], directory, f"copied-{index}")
    f["grouped_threads"] = [
        thread
        for thread in stand.request(
            "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions"
        )
        if any(note["body"].startswith("Harness grouped") for note in thread["notes"])
    ]
    verify(len(f["grouped_threads"]) == 2, "Same-file grouped suggestions missing")
    draft = result["started"]["draft_path"]
    browser = Browser(stand, directory)
    observations = []
    try:
        browser.start()
        browser.call("set", "viewport", "1440", "1000")
        browser.call("open", f["mr"]["web_url"] + "/diffs")
        browser.call("wait", "--fn", "document.body.innerText.includes('Harness grouped first')")
        for index, (body, expected) in enumerate(
            (
                ("Harness grouped first", "before\nfixed first\nnew second\nend\n"),
                ("Harness grouped second", "before\nfixed first\nfixed second\nend\n"),
            )
        ):
            apply(browser, body, directory, f"same-file-{index}")
            file = stand.request(
                "GET", f["prefix"] + "/repository/files/same%2Etxt?ref=" + f["branch"]
            )
            verify(
                base64.b64decode(file["content"]).decode() == expected,
                "Same-file application differs from exact expected text",
            )
            head = stand.request("GET", f["prefix"] + "/repository/branches/" + f["branch"])[
                "commit"
            ]["id"]
            threads = [
                stand.request(
                    "GET",
                    f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions/" + thread["id"],
                )
                for thread in f["grouped_threads"]
            ]
            applied = [
                note["suggestions"][0]["applied"]
                for thread in threads
                for note in thread["notes"]
                if note.get("suggestions")
            ]
            verify(sum(applied) == index + 1, "Same-file partial/full application flags differ")
            reassessment_input = directory / f"reassessment-{index}-input.json"
            # Refresh reads exact Git objects; it deliberately does not fetch remote history.
            command(["git", "-C", str(repo), "fetch", "origin", f["branch"]], env=environment)
            write_json(
                reassessment_input,
                {
                    "draft": draft,
                    "artifact_root": result["started"]["artifact_root"],
                    "head": head,
                    "expected": expected,
                    "complete_fix": index == 1,
                },
            )
            reassessed = json.loads(
                command(
                    [
                        "node",
                        str(APP / "scripts/same_file_reassessment.mjs"),
                        str(reassessment_input),
                    ],
                    env=environment,
                    timeout=240,
                ).stdout
            )
            write_json(directory / f"reassessment-{index}.json", reassessed)
            draft = reassessed["refreshed_draft_path"]
            observations.append(
                {
                    "head": head,
                    "applied": applied,
                    "reassessment": reassessed,
                    "screenshot": f"same-file-{index}-applied.png",
                }
            )
            if index == 0:
                refresh(browser, stand, f, head, "Harness grouped second", directory)
        return {
            "observations": observations,
            "remaps": f["browser_refreshes"],
            "origin": "real server/browser plus deterministic backend output assertions",
        }
    finally:
        try:
            write_json(
                directory / "browser-network.json",
                network_metadata(
                    json.loads(browser.call("network", "requests", "--type", "xhr,fetch", "--json"))
                ),
            )
        finally:
            try:
                browser.call("screenshot", str(directory / "last.png"))
                (directory / "last-snapshot.txt").write_text(
                    stand.redact(browser.call("snapshot", "-i"))
                )
            finally:
                browser.close()
