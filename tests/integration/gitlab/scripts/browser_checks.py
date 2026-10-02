"""GitLab UI assertions using the existing verified agent-browser session driver."""

from __future__ import annotations

import base64
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from tests.integration.gitlab.scripts.stand import private_directory, write_json
from tests.integration.mattermost.scripts import browser_checks as shared


class Browser(shared.Browser):
    def __init__(self, stand: Any, report: Path):
        super().__init__(stand, report)
        self.session = "gl-test-" + stand.manifest["owner"]
        self.base[-1] = self.session
        self.env = stand.isolated_env("author")
        # Unix sockets need a short root; private_directory rejects symlinks and enforces 0700.
        temporary = Path("/tmp/opencode")
        if not temporary.is_dir():
            temporary = Path(tempfile.gettempdir())
        self.env["AGENT_BROWSER_SOCKET_DIR"] = str(
            private_directory(temporary / ("gl-" + stand.manifest["owner"]))
        )

    def start(self) -> None:
        self.open_verified("/version")
        # A private fixture URL stores the post-login destination. The personal
        # homepage/catalog is not an automation target, including on old stands.
        self.call("open", self.stand.manifest["fixtures"]["web_url"])
        self.call("wait", "#user_login")
        user = self.stand.manifest["users"]["author"]
        # Credentials travel through the driver's stdin, not the process arguments.
        self.evaluate(f"""(() => {{
          document.querySelector('#user_login').value = {json.dumps(user["username"])};
          document.querySelector('#user_login').dispatchEvent(new Event('input', {{bubbles: true}}));
          document.querySelector('#user_password').value = {json.dumps(user["password"])};
          document.querySelector('#user_password').dispatchEvent(new Event('input', {{bubbles: true}}));
          return true;
        }})()""")
        self.call("find", "role", "button", "click", "--name", "Sign in", "--exact")
        self.call(
            "wait",
            "--fn",
            "!document.querySelector('#user_login') && location.pathname.startsWith("
            + json.dumps("/" + self.stand.manifest["fixtures"]["path_with_namespace"])
            + ")",
        )


def run(stand: Any, f: dict[str, Any], directory: Path, report: dict[str, Any]) -> None:
    browser = Browser(stand, directory)
    try:
        browser.start()
        browser.call("set", "viewport", "1440", "1000")
        browser.call("open", f["mr"]["web_url"] + "/diffs")
        browser.call("wait", "--fn", "document.body.innerText.includes('Harness suggestion')")
        observations = browser.evaluate("""(() => {
          const notes = [...document.querySelectorAll('.discussion')];
          return notes.filter(n => n.innerText.includes('Harness')).map(n => ({
            text: n.innerText, visible: n.getBoundingClientRect().height > 0,
            diff: Boolean(n.closest('.diff-file,.diff-grid,.diff-content')),
          }));
        })()""")
        expected = [f"Harness {side} {directory.name}" for side in ("old", "new", "context")]
        expected.append("Harness suggestion")
        if (
            not observations
            or not all(item["visible"] and item["diff"] for item in observations)
            or not all(any(text in item["text"] for item in observations) for text in expected)
        ):
            raise RuntimeError("Inline comments are missing or invisible in GitLab diff UI")
        browser.call("screenshot", str(directory / "inline-before.png"))
        apply(browser, "Harness suggestion", directory, "single")
        browser.call("screenshot", str(directory / "inline-applied.png"))
        path = f["prefix"] + "/repository/files/sample%2Etxt?ref=" + f["branch"]
        content = stand.request("GET", path)
        if base64.b64decode(content["content"]).decode() != "context\nfixed\nkeep\nlast\nadded\n":
            raise RuntimeError("UI suggestion application did not produce the expected file")
        refresh(browser, stand, f, content["last_commit_id"], "Harness grouped first", directory)
        partial = {
            "grouped.txt": "before\nfixed first\nend\n",
            "grouped-extra.txt": "before\nnew second\nend\n",
        }
        complete = {**partial, "grouped-extra.txt": "before\nfixed second\nend\n"}
        for index, (body, expected_files) in enumerate(
            (("Harness grouped first", partial), ("Harness grouped second", complete))
        ):
            apply(browser, body, directory, f"grouped-{index}")
            file_commits = {}
            for filename, text in expected_files.items():
                actual = stand.request(
                    "GET",
                    f["prefix"]
                    + "/repository/files/"
                    + filename.replace(".", "%2E")
                    + "?ref="
                    + f["branch"],
                )
                if base64.b64decode(actual["content"]).decode() != text:
                    raise RuntimeError(
                        "Grouped suggestion application differs from the exact expected file"
                    )
                file_commits[filename] = actual["last_commit_id"]
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
            if sum(applied) != index + 1:
                raise RuntimeError(
                    "Server grouped application state does not match partial/full application"
                )
            report["checks"].append(
                {
                    "name": "browser-grouped-" + ("partial" if index == 0 else "complete"),
                    "status": "passed",
                    "evidence": {
                        "files": expected,
                        "file_commits": file_commits,
                        "applied": applied,
                        "complete_fix": index == 1,
                        "screenshot": f"grouped-{index}-applied.png",
                    },
                }
            )
            if index == 0:
                current_branch = stand.request(
                    "GET", f["prefix"] + "/repository/branches/" + f["branch"]
                )
                refresh(
                    browser,
                    stand,
                    f,
                    current_branch["commit"]["id"],
                    "Harness grouped second",
                    directory,
                )
        report["checks"].append(
            {
                "name": "browser-inline-and-application",
                "status": "passed",
                "evidence": {
                    "comments": observations,
                    "commit": content["last_commit_id"],
                    "screenshots": ["inline-before.png", "inline-applied.png"],
                    "refreshes": f.get("browser_refreshes", []),
                },
            }
        )
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
                browser.call("screenshot", str(directory / "browser-last.png"))
                (directory / "browser-last.txt").write_text(
                    stand.redact(browser.call("snapshot", "-i"))
                )
            finally:
                browser.close()


def apply(browser: Browser, body: str, directory: Path, name: str) -> None:
    clicked = browser.evaluate(f"""(() => {{
      const thread = [...document.querySelectorAll('.discussion')].find(n => n.innerText.includes({json.dumps(body)}));
      const button = thread && [...thread.querySelectorAll('button')].find(n => n.innerText.trim() === 'Apply suggestion');
      if (!button) return false;
      button.click(); return true;
    }})()""")
    if clicked is not True:
        raise RuntimeError("The expected suggestion has no scoped UI apply button")
    browser.call(
        "wait",
        "--fn",
        "[...document.querySelectorAll('button')].some(n => n.innerText.trim() === 'Apply')",
    )
    (directory / (name + "-apply-snapshot.txt")).write_text(browser.call("snapshot", "-i"))
    browser.call("find", "role", "button", "click", "--name", "Apply", "--exact")
    browser.call(
        "wait",
        "--fn",
        f"[...document.querySelectorAll('.discussion')].some(n => n.innerText.includes({json.dumps(body)}) && n.innerText.includes('Applied'))",
    )
    browser.call("screenshot", str(directory / (name + "-applied.png")))


def refresh(
    browser: Browser, stand: Any, f: dict[str, Any], head: str, body: str, directory: Path
) -> None:
    thread_id = next(
        thread["id"]
        for thread in f["grouped_threads"]
        if any(body in note["body"] for note in thread["notes"])
    )
    observations = []
    diff_id = None
    deadline = time.monotonic() + 60
    endpoint = (
        f["mr"]["web_url"] + "/discussions.json?notes_filter=0&persist_filter=false&per_page=20"
    )
    try:
        # GitLab's UI serializer exposes the remapped current position; REST's
        # original note position and MR diff_refs alone do not establish placement.
        while time.monotonic() < deadline:
            mr = stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}")
            discussion = browser.evaluate(f"""(async () => {{
              const response = await fetch({json.dumps(endpoint)}, {{cache: 'no-store'}});
              if (!response.ok) throw new Error('Discussion serializer HTTP ' + response.status);
              const values = await response.json();
              const thread = values.find(value => value.id === {json.dumps(thread_id)});
              return {{status: response.status, id: thread?.id ?? null,
                active: thread?.active ?? null, position: thread?.position ?? null,
                resolved: thread?.resolved ?? null}};
            }})()""")
            observation = {"mr_head": (mr.get("diff_refs") or {}).get("head_sha"), **discussion}
            observations.append(observation)
            if remapped(observation, head, thread_id):
                break
            time.sleep(1)
        else:
            raise RuntimeError(
                "Pending discussion did not acquire an active exact-head UI position"
            )
        versions = stand.request("GET", f["prefix"] + f"/merge_requests/{f['mr']['iid']}/versions")
        exact = [
            version["id"]
            for version in versions
            if version.get("head_commit_sha") == head and isinstance(version.get("id"), int)
        ]
        if not exact:
            raise RuntimeError("No exact-head diff version is available for the pending discussion")
        diff_id = max(exact)
        # Head-diff previews may use a synthetic merge SHA, not the discussion's source SHA.
        browser.call("open", f["mr"]["web_url"] + f"/diffs?diff_id={diff_id}")
        browser.call(
            "wait",
            "--fn",
            f"[...document.querySelectorAll('.discussion')].some(n => n.innerText.includes({json.dumps(body)}))",
        )
        f.setdefault("browser_refreshes", []).append(
            {
                "head": head,
                "diff_id": diff_id,
                "thread": thread_id,
                "body": body,
                "navigation_attempts": 1,
                "server_observations": len(observations),
            }
        )
    finally:
        write_json(
            directory / ("browser-remap-" + head + ".json"),
            {
                "origin": "real-server-ui-serializer",
                "fault_injection": False,
                "expected_head": head,
                "diff_id": diff_id,
                "thread": thread_id,
                "observations": observations,
            },
        )


def remapped(value: dict[str, Any], head: str, thread_id: str) -> bool:
    return (
        value.get("status") == 200
        and value.get("id") == thread_id
        and value.get("mr_head") == head
        and value.get("active") is True
        and (value.get("position") or {}).get("head_sha") == head
    )


def network_metadata(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("success") is not True or not isinstance(
        value.get("data", {}).get("requests"), list
    ):
        raise RuntimeError("Browser network diagnostics are incomplete")
    # Keep request/response status evidence, never cookies, headers or bodies.
    fields = {
        "requestId",
        "url",
        "method",
        "status",
        "statusText",
        "resourceType",
        "error",
        "errorText",
    }
    return {
        "origin": "real-browser",
        "fault_injection": False,
        "requests": [
            {key: item[key] for key in fields if key in item} for item in value["data"]["requests"]
        ],
    }
