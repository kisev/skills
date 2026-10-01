"""Fixture administration through this Compose stack's private Unix socket."""

from __future__ import annotations

import http.client
import json
import socket
import sys


class LocalConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect("/var/tmp/mattermost_local.socket")  # noqa: S108 - Server-owned socket in the private Compose volume.


def main() -> None:
    request = json.load(sys.stdin)
    connection = LocalConnection("localhost", timeout=30)
    data = json.dumps(request.get("data")).encode() if "data" in request else None
    connection.request(
        request["method"], "/api/v4" + request["path"], data, {"Content-Type": "application/json"}
    )
    response = connection.getresponse()
    body = response.read()
    print(json.dumps({"status": response.status, "body": json.loads(body) if body else None}))
    connection.close()


if __name__ == "__main__":
    main()
