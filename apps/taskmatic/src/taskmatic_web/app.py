"""Serve the live read-only taskmatic web board from the private SQLite store."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, NoReturn

SNAPSHOT_SCHEMA = "taskmatic/snapshot/v1"
STATUSES = ("todo", "doing", "review", "blocked", "done")
STATUS_ORDER = {status: index for index, status in enumerate(STATUSES)}
PRIORITY_ORDER = {
    priority: index for index, priority in enumerate(("urgent", "high", "normal", "low"))
}
DB_NAME = "taskmatic.db"
ACTIVITY_LIMIT = 20
SNAPSHOT_PLACEHOLDER = "__TASKMATIC_SNAPSHOT_JSON__"
VIEWER_RESOURCE = "viewer.html"
DEFAULT_PORT = 8765


class WebBoardError(ValueError):
    """Expected safe failure."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise WebBoardError(message)


def resolve_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit)
    elif os.environ.get("TASKMATIC_HOME"):
        root = Path(os.environ["TASKMATIC_HOME"])
    else:
        base = os.environ.get("XDG_STATE_HOME")
        state = Path(base) if base else Path.home() / ".local" / "state"
        root = state / "agent-skills" / "taskmatic"
    if not root.is_absolute() or any(part in {"", ".", ".."} for part in root.parts[1:]):
        raise WebBoardError("taskmatic home must be an absolute normalized path")
    return root


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def claim_state(claimed_by: str | None, expires: str | None) -> dict[str, Any]:
    if claimed_by is None or expires is None:
        return {
            "claimed_by": None,
            "claim_expires_at": None,
            "claim_state": None,
            "claim_remaining_seconds": None,
        }
    remaining = int(
        (
            datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - datetime.now(UTC)
        ).total_seconds()
    )
    return {
        "claimed_by": claimed_by,
        "claim_expires_at": expires,
        "claim_state": "held" if remaining > 0 else "expired",
        "claim_remaining_seconds": max(remaining, 0),
    }


@dataclass(frozen=True)
class Board:
    root: Path

    @classmethod
    def open(cls, explicit_root: str | None = None) -> Board:
        root = resolve_root(explicit_root)
        if not (root / DB_NAME).is_file():
            raise WebBoardError(f"no taskmatic store at {root / DB_NAME}; create cards first")
        return cls(root=root)

    def snapshot(self) -> dict[str, Any]:
        connection = sqlite3.connect(f"file:{self.root / DB_NAME}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            boards = [
                {"slug": row["slug"], "title": row["title"], "created_at": row["created_at"]}
                for row in connection.execute(
                    "SELECT slug, title, created_at FROM boards ORDER BY slug"
                ).fetchall()
            ]
            rows = connection.execute("SELECT * FROM cards ORDER BY board, created_at").fetchall()
            cards = [self._card(connection, row) for row in rows]
            cards.sort(
                key=lambda card: (
                    card["board"],
                    STATUS_ORDER[card["status"]],
                    PRIORITY_ORDER[card["priority"]],
                    card["created_at"],
                )
            )
        finally:
            connection.close()
        return {
            "schema": SNAPSHOT_SCHEMA,
            "generated_at": iso(datetime.now(UTC)),
            "boards": boards,
            "cards": cards,
        }

    def _card(self, connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        activity = [
            {
                "at": event["at"],
                "kind": event["kind"],
                "actor": event["actor"],
                "detail": event["detail"],
            }
            for event in connection.execute(
                "SELECT at, kind, actor, detail FROM events WHERE card = ?"
                " ORDER BY id DESC LIMIT ?",
                (row["id"], ACTIVITY_LIMIT),
            ).fetchall()
        ]
        children = [
            child["id"]
            for child in connection.execute(
                "SELECT id FROM cards WHERE parent = ? ORDER BY created_at", (row["id"],)
            ).fetchall()
        ]
        return {
            "id": row["id"],
            "board": row["board"],
            "title": row["title"],
            "notes": row["notes"],
            "status": row["status"],
            "priority": row["priority"],
            "labels": json.loads(row["labels"]),
            "assignee": row["assignee"],
            "parent": row["parent"],
            "children": children,
            "linked": row["linked"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "activity": activity,
            **claim_state(row["claimed_by"], row["claim_expires_at"]),
        }


def load_viewer_template() -> str:
    return Path(__file__).with_name(VIEWER_RESOURCE).read_text(encoding="utf-8")


def render_page(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c")
    return load_viewer_template().replace(SNAPSHOT_PLACEHOLDER, payload)


class BoardHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], board: Board) -> None:
        self.taskmatic_board = board
        super().__init__(address, BoardHandler)


class BoardHandler(BaseHTTPRequestHandler):
    server: BoardHTTPServer

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        snapshot = self.server.taskmatic_board.snapshot()
        if path == "/":
            body = render_page(snapshot).encode("utf-8")
            self.respond(HTTPStatus.OK, "text/html; charset=utf-8", body)
        elif path == "/snapshot.json":
            body = (
                json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            self.respond(HTTPStatus.OK, "application/json", body)
        else:
            self.respond(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"not found\n")

    def respond(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: Any) -> None:
        pass


def serve(board: Board, host: str, port: int) -> None:
    server = BoardHTTPServer((host, port), board)
    assigned = server.server_address[1]
    print(f"taskmatic board: http://{host}:{assigned}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> Parser:
    parser = Parser(prog="taskmatic-web", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve_parser = subparsers.add_parser("serve", help="serve the live read-only web board")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--home", help="taskmatic state root (default: taskmatic XDG state)")
    snapshot_parser = subparsers.add_parser("snapshot", help="print the live snapshot JSON")
    snapshot_parser.add_argument("--home")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "serve":
            serve(Board.open(getattr(args, "home", None)), args.host, args.port)
            return 0
        if args.command == "snapshot":
            print(
                json.dumps(
                    Board.open(getattr(args, "home", None)).snapshot(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except (WebBoardError, OSError, sqlite3.Error) as error:
        print(f"taskmatic-web: {error}", file=sys.stderr)
        return 2
    raise WebBoardError(f"unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
