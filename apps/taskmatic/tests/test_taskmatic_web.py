#!/usr/bin/env python3

import importlib.util
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

sys.dont_write_bytecode = True

APP = Path(__file__).resolve().parents[1] / "src" / "taskmatic_web" / "app.py"
SKILL = Path(__file__).resolve().parents[3] / "skills" / "taskmatic" / "scripts" / "taskmatic.py"
SKILL_VIEWER = SKILL.with_name("viewer.html")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


APP_MODULE = load("taskmatic_web_app_test", APP)
SKILL_MODULE = load("taskmatic_skill_app_test", SKILL)


class WebBoardTestCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.store = SKILL_MODULE.open_store(self.home.name)
        self.addCleanup(self.store.connection.close)
        parent = SKILL_MODULE.create_card(
            self.store.connection, board="main", title="Parent card", priority="high"
        )
        child = SKILL_MODULE.create_card(
            self.store.connection,
            board="ops",
            title="Child card",
            parent=parent,
            labels=["web"],
            notes="check the board",
        )
        SKILL_MODULE.claim_card(self.store.connection, child, "agent-a", 600)
        SKILL_MODULE.append_note(self.store.connection, child, "in progress", actor="agent-a")

    def test_snapshot_matches_the_skill_runtime(self):
        app_snapshot = APP_MODULE.Board.open(self.home.name).snapshot()
        skill_snapshot = SKILL_MODULE.build_snapshot(self.store.connection)
        self.assertEqual(app_snapshot["schema"], skill_snapshot["schema"])
        self.assertEqual(app_snapshot["boards"], skill_snapshot["boards"])
        self.assertEqual(app_snapshot["cards"], skill_snapshot["cards"])
        self.assertEqual(app_snapshot["generated_at"][:10], skill_snapshot["generated_at"][:10])

    def test_missing_store_is_rejected(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(APP_MODULE.WebBoardError):
                APP_MODULE.Board.open(empty)

    def test_page_embeds_escaped_snapshot(self):
        SKILL_MODULE.create_card(
            self.store.connection, board="main", title="</script><b>markup</b>"
        )
        page = APP_MODULE.render_page(APP_MODULE.Board.open(self.home.name).snapshot())
        self.assertNotIn("</script><b>", page)
        self.assertIn("\\u003c/script>", page)

    def test_viewer_template_stays_in_sync_with_the_skill(self):
        app_viewer = Path(APP_MODULE.__file__).with_name("viewer.html").read_bytes()
        self.assertEqual(app_viewer, SKILL_VIEWER.read_bytes())

    def test_serves_live_board(self):
        server = APP_MODULE.BoardHTTPServer(("127.0.0.1", 0), APP_MODULE.Board.open(self.home.name))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
            self.assertIn("Parent card", page)
        with urllib.request.urlopen(base + "/snapshot.json", timeout=5) as response:
            snapshot = json.loads(response.read().decode("utf-8"))
            self.assertEqual(snapshot["schema"], "taskmatic/snapshot/v1")
        SKILL_MODULE.create_card(self.store.connection, board="main", title="Added while serving")
        with urllib.request.urlopen(base + "/snapshot.json", timeout=5) as response:
            snapshot = json.loads(response.read().decode("utf-8"))
            self.assertTrue(
                any(card["title"] == "Added while serving" for card in snapshot["cards"])
            )
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(base + "/missing", timeout=5)

    def test_cli_snapshot_and_errors(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = APP_MODULE.main(["snapshot", "--home", self.home.name])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buffer.getvalue())["schema"], "taskmatic/snapshot/v1")
        self.assertEqual(APP_MODULE.main(["snapshot", "--home", "/nonexistent/taskmatic"]), 2)


if __name__ == "__main__":
    unittest.main()
