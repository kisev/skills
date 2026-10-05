"""Same-file grouped suggestions, exact-head remapping and backend reassessment."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.browser_checks import (
    Browser,
    apply,
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


def run(
    stand: Stand, directory: Path, report: dict[str, Any], *, browser: bool = False
) -> dict[str, Any]:
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
            [sys.executable, str(APP / "scripts/review_plan.py"), str(source)],
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
    ui = Browser(stand, directory) if browser else None
    observations = []
    try:
        if ui is not None:
            ui.start()
            ui.call("set", "viewport", "1440", "1000")
            ui.call("open", f["mr"]["web_url"] + "/diffs")
            ui.call("wait", "--fn", "document.body.innerText.includes('Harness grouped first')")
        for index, (body, expected) in enumerate(
            (
                ("Harness grouped first", "before\nfixed first\nnew second\nend\n"),
                ("Harness grouped second", "before\nfixed first\nfixed second\nend\n"),
            )
        ):
            if ui is not None:
                apply(ui, body, directory, f"same-file-{index}")
            else:
                apply_api(stand, f, body, directory, index)
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
                        sys.executable,
                        str(APP / "scripts/same_file_reassessment.py"),
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
                    "application": "browser" if ui is not None else "real GitLab suggestion API",
                }
            )
            if index == 0 and ui is not None:
                refresh(ui, stand, f, head, "Harness grouped second", directory)
        return {
            "observations": observations,
            "remaps": f.get("browser_refreshes", []),
            "origin": "real GitLab application plus deterministic backend output assertions",
            "ui_verified": ui is not None,
        }
    finally:
        if ui is not None:
            try:
                write_json(
                    directory / "browser-network.json",
                    ui.diagnostics(),
                )
            finally:
                try:
                    ui.call("screenshot", str(directory / "last.png"))
                    (directory / "last-snapshot.txt").write_text(
                        stand.redact(ui.call("snapshot", "-i"))
                    )
                finally:
                    ui.close()


def apply_api(stand: Stand, f: dict[str, Any], body: str, directory: Path, index: int) -> None:
    # Suggestions have global API IDs. Bind the ID to an observed discussion in
    # the owned fixture MR before dispatch; never accept an arbitrary suggestion ID.
    thread = next(
        thread
        for thread in f["grouped_threads"]
        if any(note["body"].startswith(body) for note in thread["notes"])
    )
    observed = stand.request(
        "GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/discussions/{thread['id']}"
    )
    suggestions = [
        suggestion
        for note in observed["notes"]
        if note["body"].startswith(body)
        for suggestion in note.get("suggestions", [])
    ]
    verify(
        len(suggestions) == 1
        and type(suggestions[0].get("id")) is int
        and suggestions[0]["id"] > 0
        and suggestions[0].get("applied") is False,
        "No unique pending suggestion in the owned fixture discussion",
    )
    endpoint = f"suggestions/{suggestions[0]['id']}/apply"
    output = command(
        ["glab", "api", "--hostname", "localhost", "--method", "PUT", endpoint],
        env=stand.isolated_env("author"),
    )
    stand.access_log.append({"method": "PUT", "path": "/" + endpoint, "actor": "author"})
    write_json(directory / f"api-application-{index}.json", json.loads(output.stdout))
