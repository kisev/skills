"""Real Mattermost browser checks through the shared agent-browser CLI."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import subprocess
from pathlib import Path
from typing import Any


class Browser:
    def __init__(self, stand: Any, report: Path):
        self.stand, self.report = stand, Path(report)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_BROWSER_")}
        self.session = "mm-test-" + stand.manifest["owner"]
        config = stand.state / "browser-config.json"
        config.write_text("{}\n")
        self.base = ["agent-browser", "--config", str(config), "--session", self.session]

    def call(self, *args: str, data: str | None = None) -> str:
        result = subprocess.run(  # noqa: S603 - Fixed browser CLI in an isolated session.
            [*self.base, *args],
            input=data,
            text=True,
            capture_output=True,
            env=self.env,
            timeout=90,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Browser {args[:2]} failed: " + result.stderr[-1000:])
        return result.stdout

    def evaluate(self, script: str) -> Any:
        output = json.loads(self.call("eval", "--stdin", "--json", data=script))
        if not output.get("success"):
            raise RuntimeError("Browser evaluation failed")
        return output["data"]["result"]

    def start(self) -> None:
        self.call("close")
        # Verify hostname and chain first; Chromium trusts only this test CA's
        # public key in this ephemeral session, without certutil or host trust edits.
        self.stand.request("GET", "/system/ping")
        with (
            socket.create_connection(("localhost", self.stand.port), timeout=10) as connection,
            self.stand.context.wrap_socket(connection, server_hostname="localhost") as secure,
        ):
            pem = ssl.DER_cert_to_PEM_cert(secure.getpeercert(binary_form=True)).encode()
        public = subprocess.run(
            ["openssl", "x509", "-pubkey", "-noout"],  # noqa: S607 - Required system OpenSSL tool.
            input=pem,
            capture_output=True,
            check=True,
        ).stdout
        der = subprocess.run(
            ["openssl", "pkey", "-pubin", "-outform", "DER"],  # noqa: S607 - Required system OpenSSL tool.
            input=public,
            capture_output=True,
            check=True,
        ).stdout
        pin = base64.b64encode(hashlib.sha256(der).digest()).decode()
        self.call(
            "--args",
            "--ignore-certificate-errors-spki-list=" + pin,
            "--allowed-domains",
            "localhost",
            "open",
            self.stand.origin,
        )
        user = self.stand.manifest["users"]["reader"]
        cookies = self.stand.state / "browser-cookies.json"
        cookies.write_text(
            json.dumps(
                [
                    {
                        "name": "MMAUTHTOKEN",
                        "value": user["token"],
                        "domain": "localhost",
                        "path": "/",
                        "httpOnly": True,
                        "secure": True,
                    },
                    {
                        "name": "MMUSERID",
                        "value": user["id"],
                        "domain": "localhost",
                        "path": "/",
                        "secure": True,
                    },
                ]
            )
        )
        cookies.chmod(0o600)
        try:
            self.call("cookies", "set", "--curl", str(cookies))
        finally:
            cookies.unlink()
        self.call("open", self.stand.url("cards"))
        self.call("wait", "#postListContent")
        if self.evaluate("document.body.innerText.includes('No thanks, I')"):
            self.call("find", "text", "No thanks, I’ll figure it out myself", "click")  # noqa: RUF001 - Exact upstream UI label.

    def check(self, post_id: str, title: str, name: str, summary: str = "") -> list[dict[str, Any]]:
        url = f"{self.stand.origin}/{self.stand.manifest['team']['name']}/pl/{post_id}"
        self.call("set", "viewport", "1440", "1000")
        self.call("open", url)
        self.call("wait", "--fn", f"document.body.innerText.includes({json.dumps(title)})")
        results = []
        for mode in ("channel", "thread"):
            if mode == "thread":
                # Mattermost's supported thread action, not a synthetic DOM mock.
                self.call("hover", f"#post_{post_id}")
                self.call("click", f"#CENTER_commentIcon_{post_id}")
                self.call("wait", "#rhsContainer")
            scope = "#rhsContainer" if mode == "thread" else f"#post_{post_id}"
            result = self.evaluate(f"""(() => {{
              const scope = document.querySelector({json.dumps(scope)});
              const cards = [...scope.querySelectorAll('.attachment')];
              const card = cards.find(el => el.innerText.includes({json.dumps(title)}));
              if (!card) throw new Error('Card is not visible');
              const bounds = card.getBoundingClientRect();
              const collapsed = [...card.querySelectorAll('button,a,[role=button]')]
                .some(el => /show more|показать больше/i.test(el.textContent));
              const overflow = [...card.querySelectorAll('.attachment-field,.attachment__title')]
                .some(el => el.scrollWidth > el.clientWidth + 2);
              return {{mode: {json.dumps(mode)}, width: bounds.width, height: bounds.height,
                       collapsed, overflow, text: card.innerText}};
            }})()""")
            if result["collapsed"] or result["overflow"] or result["width"] <= 0:
                raise RuntimeError(f"{name}/{mode}: collapsed or overflowing card")
            if summary and " ".join(summary.split()) not in " ".join(result["text"].split()):
                raise RuntimeError(
                    f"{name}/{mode}: rendered summary differs from the prepared card"
                )
            self.call("screenshot", str(self.report / f"{name}-{mode}.png"))
            results.append(result)
        return results

    def close(self) -> None:
        self.call("close")
