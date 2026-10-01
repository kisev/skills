"""GitLab UI assertions using the existing verified agent-browser session driver."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from stand import ROOT, load

if TYPE_CHECKING:
    from pathlib import Path

shared = load("gitlab_shared_browser", ROOT / "apps/mattermost-test/scripts/browser_checks.py")


class Browser(shared.Browser):
    def __init__(self, stand: Any, report: Path):
        super().__init__(stand, report)
        self.session = "gl-test-" + stand.manifest["owner"]
        self.base[-1] = self.session

    def start(self) -> None:
        self.open_verified("/version")
        self.call("open", self.stand.origin + "/users/sign_in")
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
            "!document.querySelector('#user_login') && document.body.innerText.includes('Projects')",
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
        browser.call("find", "role", "button", "click", "--name", "Apply suggestion", "--exact")
        browser.call("wait", "--fn", "document.body.innerText.includes('Apply suggestion')")
        snapshot = browser.call("snapshot", "-i")
        (directory / "apply-snapshot.txt").write_text(snapshot)
        browser.call("find", "role", "button", "click", "--name", "Apply", "--exact")
        browser.call("wait", "--fn", "document.body.innerText.includes('Applied')")
        browser.call("screenshot", str(directory / "inline-applied.png"))
        path = f["prefix"] + "/repository/files/sample%2Etxt?ref=" + f["branch"]
        content = stand.request("GET", path)
        if base64.b64decode(content["content"]).decode() != "context\nfixed\nkeep\nlast\nadded\n":
            raise RuntimeError("UI suggestion application did not produce the expected file")
        report["checks"].append(
            {
                "name": "browser-inline-and-application",
                "status": "passed",
                "evidence": {
                    "comments": observations,
                    "commit": content["last_commit_id"],
                    "screenshots": ["inline-before.png", "inline-applied.png"],
                },
            }
        )
    finally:
        browser.call("screenshot", str(directory / "browser-last.png"))
        (directory / "browser-last.txt").write_text(stand.redact(browser.call("snapshot", "-i")))
        browser.close()
