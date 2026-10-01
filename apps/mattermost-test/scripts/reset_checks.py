"""Exercise full reset on a separate, automatically owned disposable instance."""

from __future__ import annotations

import json
import secrets
import shlex
import shutil
import socket
from typing import Any

from stand import Stand, write_json


def run(primary: Any) -> dict[str, Any]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    project = "mm-reset-" + secrets.token_hex(4)
    secondary = Stand(project, port, shlex.join(primary.compose[: primary.compose.index("-p")]))
    before_primary = primary.resources()
    secondary.start()
    secondary.bootstrap()
    old_user = secondary.manifest["users"]["reader"]["id"]
    marker = secondary.reports / "preserved.json"
    write_json(marker, {"preserve": True})
    plan = secondary.reset_plan()
    secondary.reset(plan["digest"])
    if secondary.manifest["users"]["reader"]["id"] == old_user:
        raise RuntimeError("Reset reused the old database")
    if (
        json.loads(marker.read_text()) != {"preserve": True}
        or primary.resources() != before_primary
    ):
        raise RuntimeError("Reset damaged reports or the primary environment")
    result = {
        "status": "passed",
        "project": project,
        "new_fixture_identities": True,
        "reports_retained": True,
        "primary_unchanged": True,
    }
    write_json(primary.reports / "reset-check.json", result)
    # This separate random project is entirely owned by this reset test, not the
    # persistent primary stand or its free zone. Retain its reports for diagnosis.
    secondary.resources()
    secondary.docker("down", "--volumes")
    shutil.rmtree(secondary.state)
    return result
