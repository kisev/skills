from __future__ import annotations

import hashlib
import http.server
import io
import json
import tarfile
import threading
import urllib.request
from functools import partial
from pathlib import Path

from scripts import build_distribution


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".build" / "packages" / "skills"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def test_distribution_has_well_known_index_root_skill_archives_and_digest_lock() -> None:
    assert build_distribution.build(OUTPUT, False) == 0
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(OUTPUT))
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        index = json.loads(urllib.request.urlopen(f"{base}/.well-known/skills/index.json").read())
        lock = json.loads(urllib.request.urlopen(f"{base}/.well-known/skills/lock.json").read())
        assert index["schema"] == "@kisev/skills/index/v1"
        assert index["source_revision"] == lock["source_revision"]
        assert index["skills"]
        for skill in index["skills"]:
            archive = urllib.request.urlopen(f"{base}/{skill['archive']}").read()
            assert (
                hashlib.sha256(archive).hexdigest()
                == lock["archives"][skill["name"]]
                == skill["sha256"]
            )
            with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as document:
                assert "SKILL.md" in document.getnames()
    finally:
        server.shutdown()
        thread.join()
