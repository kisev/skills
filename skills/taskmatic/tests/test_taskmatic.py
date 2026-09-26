#!/usr/bin/env python3

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "taskmatic.py"


def load_runtime():
    spec = importlib.util.spec_from_file_location("taskmatic_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["taskmatic_test"] = module
    spec.loader.exec_module(module)
    return module


TASKMATIC = load_runtime()


class RuntimeTestCase(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        self.store = TASKMATIC.open_store(self.home.name)
        self.addCleanup(self.store.connection.close)

    def cli(self, *argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = TASKMATIC.main(["--home", self.home.name, *argv])
        return code, buffer.getvalue()

    def add_card(self, title="Write the report", **kwargs):
        kwargs.setdefault("board", "main")
        return TASKMATIC.create_card(self.store.connection, title=title, **kwargs)

    def snapshot(self):
        return TASKMATIC.build_snapshot(self.store.connection)

    def payload(self, card_id):
        row = TASKMATIC.get_card(self.store.connection, card_id)
        return TASKMATIC.card_payload(self.store.connection, row)


class StorageTests(RuntimeTestCase):
    def test_default_board_is_created_with_first_card(self):
        card_id = self.add_card()
        payload = self.payload(card_id)
        self.assertEqual(payload["board"], "main")
        self.assertEqual([board["slug"] for board in self.snapshot()["boards"]], ["main"])

    def test_boards_and_counts(self):
        self.add_card()
        self.add_card("Second", board="ops")
        boards = TASKMATIC.list_boards(self.store.connection)
        self.assertEqual([board["slug"] for board in boards], ["main", "ops"])

    def test_invalid_board_slug_rejected(self):
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.create_card(self.store.connection, title="x", board="Not A Slug")

    def test_invalid_title_and_priority_rejected(self):
        with self.assertRaises(TASKMATIC.TaskmaticError):
            self.add_card("")
        with self.assertRaises(TASKMATIC.TaskmaticError):
            self.add_card("x\ny")
        with self.assertRaises(TASKMATIC.TaskmaticError):
            self.add_card("x", priority="urgent-ish")

    def test_parent_must_exist(self):
        with self.assertRaises(TASKMATIC.TaskmaticError):
            self.add_card("child", parent="deadbeef")

    def test_labels_are_deduplicated_and_sorted(self):
        card_id = self.add_card("x", labels=["b", "a", "b"])
        self.assertEqual(self.payload(card_id)["labels"], ["a", "b"])

    def test_unknown_card_rejected(self):
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.get_card(self.store.connection, "deadbeef")

    def test_ttl_parsing(self):
        self.assertEqual(TASKMATIC.parse_ttl("90"), 90)
        self.assertEqual(TASKMATIC.parse_ttl("30m"), 1800)
        self.assertEqual(TASKMATIC.parse_ttl("2h"), 7200)
        self.assertEqual(TASKMATIC.parse_ttl("1d"), 86400)
        for bad in ("0", "-5", "30x", "m5", ""):
            with self.assertRaises(TASKMATIC.TaskmaticError):
                TASKMATIC.parse_ttl(bad)

    def test_relative_home_rejected(self):
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.resolve_root("relative/path")

    def test_xdg_relative_state_rejected(self):
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("TASKMATIC_HOME", "XDG_STATE_HOME")
        }
        environment["XDG_STATE_HOME"] = "relative/state"
        with mock.patch.dict(os.environ, environment, clear=True):
            with self.assertRaises(TASKMATIC.TaskmaticError):
                TASKMATIC.resolve_root(None)

    def test_xdg_default_root(self):
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in ("TASKMATIC_HOME", "XDG_STATE_HOME")
        }
        with tempfile.TemporaryDirectory() as base:
            environment["XDG_STATE_HOME"] = base
            with mock.patch.dict(os.environ, environment, clear=True):
                root = TASKMATIC.resolve_root(None)
            self.assertEqual(root, Path(base) / "agent-skills" / "taskmatic")


class StatusTests(RuntimeTestCase):
    def test_move_records_activity(self):
        card_id = self.add_card()
        TASKMATIC.move_card(self.store.connection, card_id, "review")
        payload = self.payload(card_id)
        self.assertEqual(payload["status"], "review")
        kinds = [event["kind"] for event in payload["activity"]]
        self.assertIn("status", kinds)

    def test_move_rejects_unknown_status(self):
        card_id = self.add_card()
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.move_card(self.store.connection, card_id, "archived")

    def test_edit_changes_only_given_fields(self):
        card_id = self.add_card("Old", priority="low", notes="keep")
        TASKMATIC.edit_card(self.store.connection, card_id, title="New")
        payload = self.payload(card_id)
        self.assertEqual(payload["title"], "New")
        self.assertEqual(payload["priority"], "low")
        self.assertEqual(payload["notes"], "keep")

    def test_edit_requires_a_field(self):
        card_id = self.add_card()
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.edit_card(self.store.connection, card_id)

    def test_note_appends_bounded_activity(self):
        card_id = self.add_card()
        TASKMATIC.append_note(self.store.connection, card_id, "first step done")
        payload = self.payload(card_id)
        self.assertEqual(payload["activity"][0]["kind"], "note")
        self.assertEqual(payload["activity"][0]["detail"], "first step done")
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.append_note(self.store.connection, card_id, "  ")

    def test_complete_clears_claim(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a")
        row = TASKMATIC.complete_card(self.store.connection, card_id)
        payload = TASKMATIC.card_payload(self.store.connection, row)
        self.assertEqual(payload["status"], "done")
        self.assertIsNone(payload["claimed_by"])
        self.assertIsNone(payload["claim_state"])


class ClaimTests(RuntimeTestCase):
    def test_claim_moves_todo_to_doing(self):
        card_id = self.add_card()
        row = TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        payload = TASKMATIC.card_payload(self.store.connection, row)
        self.assertEqual(payload["status"], "doing")
        self.assertEqual(payload["claim_state"], "held")
        self.assertGreater(payload["claim_remaining_seconds"], 590)

    def test_claim_conflict_rejected(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.claim_card(self.store.connection, card_id, "agent-b", 600)

    def test_expired_claim_can_be_taken_over(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        self.store.connection.execute(
            "UPDATE cards SET claim_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (card_id,),
        )
        payload = self.payload(card_id)
        self.assertEqual(payload["claim_state"], "expired")
        self.assertEqual(payload["claim_remaining_seconds"], 0)
        row = TASKMATIC.claim_card(self.store.connection, card_id, "agent-b", 600)
        self.assertEqual(row["claimed_by"], "agent-b")

    def test_same_agent_can_reclaim(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        row = TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 300)
        self.assertEqual(row["claimed_by"], "agent-a")

    def test_heartbeat_refreshes_and_rejects_foreign_card(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 60)
        row = TASKMATIC.heartbeat_card(self.store.connection, card_id, "agent-a", 600)
        payload = TASKMATIC.card_payload(self.store.connection, row)
        self.assertGreater(payload["claim_remaining_seconds"], 590)
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.heartbeat_card(self.store.connection, card_id, "agent-b", 600)

    def test_release_allows_next_claimer(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        TASKMATIC.release_card(self.store.connection, card_id, "agent-a")
        payload = self.payload(card_id)
        self.assertIsNone(payload["claim_state"])
        row = TASKMATIC.claim_card(self.store.connection, card_id, "agent-b", 600)
        self.assertEqual(row["claimed_by"], "agent-b")

    def test_release_rejects_held_foreign_claim(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.release_card(self.store.connection, card_id, "agent-b")

    def test_claim_rejects_blank_agent(self):
        card_id = self.add_card()
        with self.assertRaises(TASKMATIC.TaskmaticError):
            TASKMATIC.claim_card(self.store.connection, card_id, "  ")


class SnapshotTests(RuntimeTestCase):
    def test_snapshot_shape_and_children(self):
        parent = self.add_card("Parent")
        child = self.add_card("Child", parent=parent)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["schema"], "taskmatic/snapshot/v1")
        cards = {card["id"]: card for card in snapshot["cards"]}
        self.assertEqual(cards[parent]["children"], [child])
        self.assertEqual(cards[child]["parent"], parent)
        for card in snapshot["cards"]:
            self.assertIn("claim_state", card)
            self.assertIn("claim_remaining_seconds", card)
            self.assertIn("activity", card)

    def test_filter_by_label_board_and_status(self):
        first = self.add_card("First", labels=["ops"], board="ops")
        self.add_card("Second", labels=["dev"])
        TASKMATIC.move_card(self.store.connection, first, "doing")
        snapshot = self.snapshot()
        by_label = TASKMATIC.snapshot_filter(snapshot, label="ops")
        by_status = TASKMATIC.snapshot_filter(snapshot, status="doing")
        by_board = TASKMATIC.snapshot_filter(snapshot, board="ops")
        self.assertEqual([card["title"] for card in by_label], ["First"])
        self.assertEqual([card["title"] for card in by_status], ["First"])
        self.assertEqual([card["title"] for card in by_board], ["First"])


class ExportTests(RuntimeTestCase):
    def test_export_writes_mirror_and_web(self):
        card_id = self.add_card("Write the report", notes="Draft first.")
        TASKMATIC.move_card(self.store.connection, card_id, "doing")
        snapshot = self.snapshot()
        TASKMATIC.export_all(self.store, snapshot)
        board = self.store.boards_root / "main" / "BOARD.md"
        card_file = self.store.boards_root / "main" / "cards" / f"{card_id}-write-the-report.md"
        self.assertTrue(board.is_file())
        board_text = board.read_text(encoding="utf-8")
        self.assertIn("## Doing", board_text)
        self.assertIn(f"[Write the report](cards/{card_id}-write-the-report.md)", board_text)
        card_text = card_file.read_text(encoding="utf-8")
        self.assertIn(f'id: "{card_id}"', card_text)
        self.assertIn('status: "doing"', card_text)
        self.assertIn("Draft first.", card_text)
        self.assertTrue((self.store.web_root / "index.html").is_file())
        self.assertTrue((self.store.web_root / "snapshot.json").is_file())

    def test_export_removes_stale_files_and_is_idempotent(self):
        card_id = self.add_card("Old title")
        TASKMATIC.export_all(self.store, self.snapshot())
        stale = self.store.boards_root / "main" / "cards" / "deadbeee-stale.md"
        stale.write_text("stale", encoding="utf-8")
        TASKMATIC.edit_card(self.store.connection, card_id, title="New title")
        TASKMATIC.export_all(self.store, self.snapshot())
        self.assertFalse(stale.exists())
        new_file = self.store.boards_root / "main" / "cards" / f"{card_id}-new-title.md"
        old_file = self.store.boards_root / "main" / "cards" / f"{card_id}-old-title.md"
        self.assertTrue(new_file.is_file())
        self.assertFalse(old_file.exists())
        first = new_file.read_text(encoding="utf-8")
        TASKMATIC.export_all(self.store, self.snapshot())
        self.assertEqual(new_file.read_text(encoding="utf-8"), first)

    def test_expired_claims_are_not_written_as_held(self):
        card_id = self.add_card()
        TASKMATIC.claim_card(self.store.connection, card_id, "agent-a", 600)
        self.store.connection.execute(
            "UPDATE cards SET claim_expires_at = '2000-01-01T00:00:00Z' WHERE id = ?",
            (card_id,),
        )
        TASKMATIC.export_all(self.store, self.snapshot())
        card_file = next((self.store.boards_root / "main" / "cards").glob(f"{card_id}-*.md"))
        text = card_file.read_text(encoding="utf-8")
        self.assertIn("claimed_by: null", text)

    def test_page_embeds_escaped_snapshot(self):
        card_id = self.add_card("</script><b>markup</b>")
        page = TASKMATIC.render_page(self.snapshot())
        self.assertNotIn("</script><b>", page)
        self.assertIn("\\u003c/script>", page)
        self.assertIn(card_id, page)


class ServeTests(RuntimeTestCase):
    def test_serves_board_and_snapshot(self):
        self.add_card("Visible card", labels=["ops"])
        server = TASKMATIC.ViewerHTTPServer(("127.0.0.1", 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("Visible card", page)
        with urllib.request.urlopen(base + "/snapshot.json", timeout=5) as response:
            snapshot = json.loads(response.read().decode("utf-8"))
            self.assertEqual(snapshot["schema"], "taskmatic/snapshot/v1")
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(base + "/missing", timeout=5)


class McpTests(RuntimeTestCase):
    def test_tool_surface_is_pinned(self):
        self.assertEqual(
            TASKMATIC.MCP_TOOL_NAMES,
            (
                "taskmatic_boards",
                "taskmatic_list",
                "taskmatic_read",
                "taskmatic_create",
                "taskmatic_edit",
                "taskmatic_move",
                "taskmatic_claim",
                "taskmatic_heartbeat",
                "taskmatic_release",
                "taskmatic_complete",
                "taskmatic_note",
            ),
        )

    def test_initialize_and_ping_and_unknown_method(self):
        initialize = TASKMATIC.mcp_dispatch(
            self.store, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "taskmatic")
        ping = TASKMATIC.mcp_dispatch(self.store, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(ping["result"], {})
        unknown = TASKMATIC.mcp_dispatch(self.store, {"jsonrpc": "2.0", "id": 3, "method": "bogus"})
        self.assertEqual(unknown["error"]["code"], -32601)
        notification = TASKMATIC.mcp_dispatch(
            self.store, {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        self.assertIsNone(notification)

    def test_call_claim_and_conflict(self):
        card_id = self.add_card()
        claimed = TASKMATIC.mcp_call_tool(
            self.store,
            "taskmatic_claim",
            {"id": card_id, "agent": "agent-a", "ttl_seconds": 600},
        )
        self.assertFalse(claimed["isError"])
        self.assertEqual(claimed["structuredContent"]["status"], "doing")
        conflict = TASKMATIC.mcp_call_tool(
            self.store, "taskmatic_claim", {"id": card_id, "agent": "agent-b"}
        )
        self.assertTrue(conflict["isError"])
        self.assertIn("claimed by agent-a", conflict["content"][0]["text"])

    def test_call_create_and_read_and_list_and_note(self):
        created = TASKMATIC.mcp_call_tool(
            self.store,
            "taskmatic_create",
            {"title": "From MCP", "labels": ["mcp"], "notes": "body"},
        )
        card_id = created["structuredContent"]["id"]
        read = TASKMATIC.mcp_call_tool(self.store, "taskmatic_read", {"id": card_id})
        self.assertEqual(read["structuredContent"]["title"], "From MCP")
        listed = TASKMATIC.mcp_call_tool(self.store, "taskmatic_list", {"label": "mcp"})
        self.assertEqual([card["id"] for card in listed["structuredContent"]["cards"]], [card_id])
        noted = TASKMATIC.mcp_call_tool(
            self.store, "taskmatic_note", {"id": card_id, "text": "progress", "actor": "agent-a"}
        )
        self.assertEqual(noted["structuredContent"]["activity"][0]["detail"], "progress")

    def test_call_heartbeat_and_complete(self):
        card_id = self.add_card()
        TASKMATIC.mcp_call_tool(self.store, "taskmatic_claim", {"id": card_id, "agent": "agent-a"})
        heartbeat = TASKMATIC.mcp_call_tool(
            self.store,
            "taskmatic_heartbeat",
            {"id": card_id, "agent": "agent-a", "ttl_seconds": 900},
        )
        self.assertGreater(heartbeat["structuredContent"]["claim_remaining_seconds"], 890)
        done = TASKMATIC.mcp_call_tool(self.store, "taskmatic_complete", {"id": card_id})
        self.assertEqual(done["structuredContent"]["status"], "done")
        self.assertIsNone(done["structuredContent"]["claimed_by"])

    def test_call_invalid_parameters_reported_as_error(self):
        result = TASKMATIC.mcp_call_tool(self.store, "taskmatic_read", {"id": "deadbeef"})
        self.assertTrue(result["isError"])


class CliTests(RuntimeTestCase):
    def test_add_list_show_and_json(self):
        code, output = self.cli("add", "Cli card", "--labels", "ops", "--priority", "high")
        self.assertEqual(code, 0)
        self.assertIn("created", output)
        code, output = self.cli("list", "--json")
        self.assertEqual(code, 0)
        cards = json.loads(output)
        self.assertEqual(cards[0]["title"], "Cli card")
        card_id = cards[0]["id"]
        code, output = self.cli("show", card_id, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["id"], card_id)

    def test_add_reads_notes_from_stdin(self):
        with mock.patch("sys.stdin", io.StringIO("from stdin")):
            code, output = self.cli("add", "Notes card", "--notes-file", "-", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["notes"], "from stdin")

    def test_claim_and_heartbeat_cli(self):
        card_id = self.add_card()
        code, output = self.cli("claim", card_id, "--agent", "agent-a", "--ttl", "10m")
        self.assertEqual(code, 0)
        self.assertIn("claimed", output)
        code, output = self.cli("heartbeat", card_id, "--agent", "agent-a")
        self.assertEqual(code, 0)
        self.assertIn("left", output)
        code, _ = self.cli("move", card_id, "review")
        self.assertEqual(code, 0)
        code, _ = self.cli("complete", card_id)
        self.assertEqual(code, 0)
        payload = self.payload(card_id)
        self.assertEqual(payload["status"], "done")

    def test_invalid_choice_returns_two(self):
        code = TASKMATIC.main(["--home", self.home.name, "move", "deadbeef", "bogus"])
        self.assertEqual(code, 2)

    def test_unknown_card_show_returns_two(self):
        code = TASKMATIC.main(["--home", self.home.name, "show", "deadbeef"])
        self.assertEqual(code, 2)

    def test_export_command_updates_mirror(self):
        self.add_card("Exported")
        code, output = self.cli("export")
        self.assertEqual(code, 0)
        self.assertIn("export", output)
        self.assertTrue((self.store.boards_root / "main" / "BOARD.md").is_file())

    def test_snapshot_command_filters(self):
        self.add_card("A", board="ops")
        card_id = self.add_card("B")
        code, output = self.cli("snapshot", "--board", "ops")
        self.assertEqual(code, 0)
        snapshot = json.loads(output)
        self.assertEqual([card["title"] for card in snapshot["cards"]], ["A"])
        self.assertNotIn(card_id, output)

    def test_path_command(self):
        code, output = self.cli("path", "web")
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), str(Path(self.home.name) / "export" / "web"))

    def test_mutation_regenerates_export(self):
        self.cli("add", "Mirrored", "--board", "alpha")
        board = self.store.boards_root / "alpha" / "BOARD.md"
        self.assertTrue(board.is_file())


if __name__ == "__main__":
    unittest.main()
