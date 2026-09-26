#!/usr/bin/env python3
"""Local-first task board for people and agents with a markdown mirror and viewers."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

SNAPSHOT_SCHEMA = "taskmatic/snapshot/v1"
STATUSES = ("todo", "doing", "review", "blocked", "done")
PRIORITIES = ("low", "normal", "high", "urgent")
STATUS_ORDER = {status: index for index, status in enumerate(STATUSES)}
PRIORITY_ORDER = {
    priority: index for index, priority in enumerate(("urgent", "high", "normal", "low"))
}
DEFAULT_BOARD = "main"
DEFAULT_TTL_SECONDS = 30 * 60
DB_NAME = "taskmatic.db"
ACTIVITY_LIMIT = 20
EVENT_LOG_LIMIT = 200
PRIVATE_DIRECTORY_MODE = 0o700
DB_USER_VERSION = 1
ID_PATTERN = r"[0-9a-f]{8}"
SLUG_PATTERN = r"[a-z0-9][a-z0-9-]{0,38}"
SNAPSHOT_PLACEHOLDER = "__TASKMATIC_SNAPSHOT_JSON__"
VIEWER_RESOURCE = "viewer.html"
MCP_PROTOCOL_VERSION = "2024-11-05"


class TaskmaticError(ValueError):
    """Expected safe failure."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise TaskmaticError(message)


def now() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(now())


def parse_ttl(value: str) -> int:
    if value.isdigit():
        seconds = int(value)
    else:
        match = re.fullmatch(r"([0-9]+)([smhd])", value)
        if match is None:
            raise TaskmaticError("ttl must be seconds or like 30m, 2h, 1d")
        factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
        seconds = int(match.group(1)) * factor
    if seconds <= 0 or seconds > 30 * 86400:
        raise TaskmaticError("ttl must be between 1 second and 30 days")
    return seconds


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:40].strip("-")
    return slug or "card"


def validate_slug(slug: str) -> str:
    if re.fullmatch(SLUG_PATTERN, slug) is None:
        raise TaskmaticError(f"board slug must match {SLUG_PATTERN}")
    return slug


def validate_title(title: str) -> str:
    if not title.strip() or "\n" in title or len(title) > 200:
        raise TaskmaticError("title must be 1-200 characters without newlines")
    return title.strip()


def validate_labels(labels: list[str]) -> list[str]:
    for label in labels:
        if not label.strip() or len(label) > 40:
            raise TaskmaticError("labels must be non-empty and at most 40 characters")
    return sorted({label.strip() for label in labels})


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
        raise TaskmaticError("taskmatic home must be an absolute normalized path")
    return root


@dataclass(frozen=True)
class Store:
    root: Path
    connection: sqlite3.Connection

    @property
    def export_root(self) -> Path:
        return self.root / "export"

    @property
    def web_root(self) -> Path:
        return self.export_root / "web"

    @property
    def boards_root(self) -> Path:
        return self.export_root / "boards"


def open_store(explicit_root: str | None = None) -> Store:
    root = resolve_root(explicit_root)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, PRIVATE_DIRECTORY_MODE)
    connection = sqlite3.connect(root / DB_NAME, timeout=15.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA foreign_keys=ON")
    migrate(connection)
    return Store(root=root, connection=connection)


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")


def migrate(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version == DB_USER_VERSION:
        return
    if version != 0:
        raise TaskmaticError(f"unsupported taskmatic database version {version}")
    connection.executescript(
        """
        CREATE TABLE boards (
            slug TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE cards (
            id TEXT PRIMARY KEY,
            board TEXT NOT NULL REFERENCES boards(slug),
            title TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'normal',
            labels TEXT NOT NULL DEFAULT '[]',
            assignee TEXT,
            parent TEXT REFERENCES cards(id),
            linked TEXT,
            claimed_by TEXT,
            claim_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX cards_board_status ON cards(board, status);
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card TEXT NOT NULL REFERENCES cards(id),
            kind TEXT NOT NULL,
            actor TEXT NOT NULL,
            at TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX events_card ON events(card, id);
        PRAGMA user_version = 1;
        """
    )


def record_event(
    connection: sqlite3.Connection,
    card_id: str,
    kind: str,
    actor: str,
    detail: str = "",
) -> dict[str, str]:
    moment = now_iso()
    connection.execute(
        "INSERT INTO events(card, kind, actor, at, detail) VALUES (?, ?, ?, ?, ?)",
        (card_id, kind, actor, moment, detail),
    )
    return {"at": moment, "kind": kind, "actor": actor, "detail": detail}


def ensure_board(
    connection: sqlite3.Connection, slug: str, title: str | None = None
) -> sqlite3.Row:
    board = fetch_board(connection, slug)
    if board is not None:
        return board
    moment = now_iso()
    connection.execute(
        "INSERT INTO boards(slug, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (slug, title or slug, moment, moment),
    )
    return fetch_board(connection, slug)


def fetch_board(connection: sqlite3.Connection, slug: str) -> sqlite3.Row:
    return cast(
        "sqlite3.Row",
        connection.execute("SELECT * FROM boards WHERE slug = ?", (slug,)).fetchone(),
    )


def list_boards(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute("SELECT slug, title, created_at FROM boards ORDER BY slug").fetchall()
    return [
        {"slug": row["slug"], "title": row["title"], "created_at": row["created_at"]}
        for row in rows
    ]


def get_card(connection: sqlite3.Connection, card_id: str) -> sqlite3.Row:
    row = cast(
        "sqlite3.Row | None",
        connection.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone(),
    )
    if row is None:
        raise TaskmaticError(f"unknown card {card_id}")
    return row


def card_activity(connection: sqlite3.Connection, card_id: str) -> list[dict[str, str]]:
    rows = connection.execute(
        "SELECT at, kind, actor, detail FROM events WHERE card = ? ORDER BY id DESC LIMIT ?",
        (card_id, ACTIVITY_LIMIT),
    ).fetchall()
    return [
        {"at": row["at"], "kind": row["kind"], "actor": row["actor"], "detail": row["detail"]}
        for row in rows
    ]


def claim_state(row: sqlite3.Row) -> dict[str, Any]:
    claimed_by = row["claimed_by"]
    expires = row["claim_expires_at"]
    if claimed_by is None or expires is None:
        return {
            "claimed_by": None,
            "claim_expires_at": None,
            "claim_state": None,
            "claim_remaining_seconds": None,
        }
    remaining = int(
        (
            datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - now()
        ).total_seconds()
    )
    return {
        "claimed_by": claimed_by,
        "claim_expires_at": expires,
        "claim_state": "held" if remaining > 0 else "expired",
        "claim_remaining_seconds": max(remaining, 0),
    }


def card_payload(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    with_activity: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row["id"],
        "board": row["board"],
        "title": row["title"],
        "notes": row["notes"],
        "status": row["status"],
        "priority": row["priority"],
        "labels": json.loads(row["labels"]),
        "assignee": row["assignee"],
        "parent": row["parent"],
        "children": [
            child["id"]
            for child in connection.execute(
                "SELECT id FROM cards WHERE parent = ? ORDER BY created_at", (row["id"],)
            ).fetchall()
        ],
        "linked": row["linked"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        **claim_state(row),
    }
    if with_activity:
        payload["activity"] = card_activity(connection, row["id"])
    return payload


def create_card(
    connection: sqlite3.Connection,
    *,
    board: str,
    title: str,
    priority: str = "normal",
    labels: list[str] | None = None,
    assignee: str | None = None,
    parent: str | None = None,
    linked: str | None = None,
    notes: str = "",
    actor: str = "cli",
) -> str:
    validate_title(title)
    validate_slug(board)
    if priority not in PRIORITIES:
        raise TaskmaticError(f"priority must be one of {', '.join(PRIORITIES)}")
    card_labels = validate_labels(labels or [])
    with transaction(connection):
        ensure_board(connection, board)
        if parent is not None:
            get_card(connection, parent)
        moment = now_iso()
        for _ in range(8):
            card_id = secrets.token_hex(4)
            existing = connection.execute("SELECT 1 FROM cards WHERE id = ?", (card_id,)).fetchone()
            if existing is None:
                break
        else:
            raise TaskmaticError("could not allocate a unique card id")
        connection.execute(
            """
            INSERT INTO cards(id, board, title, notes, status, priority, labels, assignee,
                              parent, linked, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'todo', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                board,
                title,
                notes,
                priority,
                json.dumps(card_labels),
                assignee,
                parent,
                linked,
                moment,
                moment,
            ),
        )
        record_event(connection, card_id, "created", actor, f"status=todo priority={priority}")
        if parent is not None:
            record_event(connection, card_id, "linked", actor, f"parent={parent}")
    return card_id


def edit_card(
    connection: sqlite3.Connection,
    card_id: str,
    *,
    title: str | None = None,
    priority: str | None = None,
    labels: list[str] | None = None,
    assignee: str | bool | None = False,
    linked: str | bool | None = False,
    notes: str | None = None,
    actor: str = "cli",
) -> sqlite3.Row:
    changes: list[tuple[str, object]] = []
    if title is not None:
        changes.append(("title", validate_title(title)))
    if priority is not None:
        if priority not in PRIORITIES:
            raise TaskmaticError(f"priority must be one of {', '.join(PRIORITIES)}")
        changes.append(("priority", priority))
    if labels is not None:
        changes.append(("labels", json.dumps(validate_labels(labels))))
    if assignee is not False:
        changes.append(("assignee", assignee))
    if linked is not False:
        changes.append(("linked", linked))
    if notes is not None:
        changes.append(("notes", notes))
    if not changes:
        raise TaskmaticError("edit requires at least one field")
    with transaction(connection):
        get_card(connection, card_id)
        assignments = ", ".join(f"{column} = ?" for column, _ in changes)
        values = [value for _, value in changes]
        connection.execute(
            f"UPDATE cards SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, now_iso(), card_id),
        )
        record_event(
            connection,
            card_id,
            "edited",
            actor,
            ", ".join(column for column, _ in changes),
        )
        return get_card(connection, card_id)


def move_card(
    connection: sqlite3.Connection,
    card_id: str,
    status: str,
    *,
    actor: str = "cli",
) -> sqlite3.Row:
    if status not in STATUSES:
        raise TaskmaticError(f"status must be one of {', '.join(STATUSES)}")
    with transaction(connection):
        row = get_card(connection, card_id)
        previous = row["status"]
        connection.execute(
            "UPDATE cards SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), card_id),
        )
        record_event(
            connection,
            card_id,
            "status",
            actor,
            f"{previous} -> {status}",
        )
        return get_card(connection, card_id)


def claim_card(
    connection: sqlite3.Connection,
    card_id: str,
    agent: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> sqlite3.Row:
    if not agent.strip() or len(agent) > 60:
        raise TaskmaticError("agent must be a non-empty identifier of at most 60 characters")
    with transaction(connection):
        row = get_card(connection, card_id)
        state = claim_state(row)
        if state["claim_state"] == "held" and row["claimed_by"] != agent:
            raise TaskmaticError(
                f"card {card_id} is claimed by {row['claimed_by']} "
                f"for another {state['claim_remaining_seconds']}s"
            )
        expires = iso(now() + timedelta(seconds=ttl_seconds))
        next_status = "doing" if row["status"] == "todo" else row["status"]
        connection.execute(
            "UPDATE cards SET claimed_by = ?, claim_expires_at = ?, status = ?, updated_at = ?"
            " WHERE id = ?",
            (agent, expires, next_status, now_iso(), card_id),
        )
        record_event(connection, card_id, "claim", agent, f"ttl={ttl_seconds}s")
        return get_card(connection, card_id)


def heartbeat_card(
    connection: sqlite3.Connection,
    card_id: str,
    agent: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> sqlite3.Row:
    with transaction(connection):
        row = get_card(connection, card_id)
        if row["claimed_by"] != agent or claim_state(row)["claim_state"] != "held":
            raise TaskmaticError(f"card {card_id} is not held by {agent}")
        expires = iso(now() + timedelta(seconds=ttl_seconds))
        connection.execute(
            "UPDATE cards SET claim_expires_at = ? WHERE id = ?",
            (expires, card_id),
        )
        return get_card(connection, card_id)


def release_card(
    connection: sqlite3.Connection,
    card_id: str,
    agent: str,
) -> sqlite3.Row:
    with transaction(connection):
        row = get_card(connection, card_id)
        state = claim_state(row)
        if (
            row["claimed_by"] is not None
            and row["claimed_by"] != agent
            and state["claim_state"] == "held"
        ):
            raise TaskmaticError(f"card {card_id} is claimed by {row['claimed_by']}")
        connection.execute(
            "UPDATE cards SET claimed_by = NULL, claim_expires_at = NULL, updated_at = ?"
            " WHERE id = ?",
            (now_iso(), card_id),
        )
        record_event(connection, card_id, "release", agent)
        return get_card(connection, card_id)


def complete_card(
    connection: sqlite3.Connection, card_id: str, *, actor: str = "cli"
) -> sqlite3.Row:
    with transaction(connection):
        row = get_card(connection, card_id)
        agent = row["claimed_by"]
        if agent is not None:
            record_event(connection, card_id, "release", agent)
        connection.execute(
            "UPDATE cards SET status = 'done', claimed_by = NULL, claim_expires_at = NULL,"
            " updated_at = ? WHERE id = ?",
            (now_iso(), card_id),
        )
        previous = row["status"]
        record_event(connection, card_id, "status", actor, f"{previous} -> done")
        return get_card(connection, card_id)


def append_note(
    connection: sqlite3.Connection,
    card_id: str,
    text: str,
    *,
    actor: str = "cli",
) -> sqlite3.Row:
    if not text.strip():
        raise TaskmaticError("note text must not be empty")
    if len(text) > 8000:
        raise TaskmaticError("note text must be at most 8000 characters")
    with transaction(connection):
        get_card(connection, card_id)
        record_event(connection, card_id, "note", actor, text.strip())
        connection.execute(
            "UPDATE cards SET updated_at = ? WHERE id = ?",
            (now_iso(), card_id),
        )
        return get_card(connection, card_id)


def card_events(connection: sqlite3.Connection, card_id: str) -> list[dict[str, str]]:
    rows = connection.execute(
        "SELECT at, kind, actor, detail FROM events WHERE card = ? ORDER BY id DESC LIMIT ?",
        (card_id, EVENT_LOG_LIMIT),
    ).fetchall()
    return [
        {"at": row["at"], "kind": row["kind"], "actor": row["actor"], "detail": row["detail"]}
        for row in rows
    ]


def build_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    boards = list_boards(connection)
    rows = connection.execute("SELECT * FROM cards ORDER BY board, created_at").fetchall()
    cards = [card_payload(connection, row) for row in rows]
    cards.sort(
        key=lambda card: (
            card["board"],
            STATUS_ORDER[card["status"]],
            PRIORITY_ORDER[card["priority"]],
            card["created_at"],
        )
    )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "generated_at": now_iso(),
        "boards": boards,
        "cards": cards,
    }


def snapshot_filter(
    snapshot: dict[str, Any],
    *,
    board: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = snapshot["cards"]
    if board is not None:
        cards = [card for card in cards if card["board"] == board]
    if status is not None:
        cards = [card for card in cards if card["status"] == status]
    if assignee is not None:
        cards = [card for card in cards if card["assignee"] == assignee]
    if label is not None:
        cards = [card for card in cards if label in card["labels"]]
    return cards


def yaml_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def render_card_markdown(card: dict[str, Any]) -> str:
    frontmatter = {
        "id": card["id"],
        "title": card["title"],
        "board": card["board"],
        "status": card["status"],
        "priority": card["priority"],
        "labels": card["labels"],
        "assignee": card["assignee"],
        "parent": card["parent"],
        "children": card["children"],
        "linked": card["linked"],
        "claimed_by": card["claimed_by"] if card["claim_state"] == "held" else None,
        "claim_expires_at": card["claim_expires_at"] if card["claim_state"] == "held" else None,
        "created_at": card["created_at"],
        "updated_at": card["updated_at"],
    }
    lines = ["---"]
    lines.extend(f"{key}: {yaml_scalar(value)}" for key, value in frontmatter.items())
    lines.append("---")
    lines.append("")
    lines.append(f"# {card['title']}")
    lines.append("")
    body = card["notes"].strip()
    lines.append(body if body else "_No notes._")
    lines.append("")
    lines.append("## Activity")
    lines.append("")
    if card["activity"]:
        for event in reversed(card["activity"]):
            detail = f" — {event['detail']}" if event["detail"] else ""
            lines.append(f"- {event['at']} `{event['kind']}` by {event['actor']}{detail}")
    else:
        lines.append("_No recorded activity._")
    lines.append("")
    return "\n".join(lines)


def render_board_markdown(
    board: dict[str, str],
    cards: list[dict[str, Any]],
    generated_at: str,
) -> str:
    counts = dict.fromkeys(STATUSES, 0)
    for card in cards:
        counts[card["status"]] += 1
    summary = ", ".join(f"{status}: {counts[status]}" for status in STATUSES)
    lines = [
        f"# Board {board['title']}",
        "",
        f"_Slug `{board['slug']}`. Generated {generated_at}. {len(cards)} cards ({summary})._",
        "",
    ]
    for status in STATUSES:
        lines.append(f"## {status.capitalize()}")
        lines.append("")
        status_cards = [card for card in cards if card["status"] == status]
        if not status_cards:
            lines.append("_None._")
            lines.append("")
            continue
        for card in status_cards:
            meta: list[str] = [card["priority"]]
            if card["labels"]:
                meta.append(", ".join(card["labels"]))
            if card["assignee"]:
                meta.append(f"assignee: {card['assignee']}")
            if card["claim_state"] == "held":
                meta.append(f"claim: {card['claimed_by']} {card['claim_remaining_seconds']}s left")
            elif card["claim_state"] == "expired":
                meta.append(f"claim expired: {card['claimed_by']}")
            if card["parent"]:
                meta.append(f"parent: {card['parent']}")
            if card["children"]:
                meta.append(f"children: {', '.join(card['children'])}")
            if card["linked"]:
                meta.append(f"linked: {card['linked']}")
            filename = card_filename(card)
            lines.append(
                f"- `{card['id']}` [{card['title']}](cards/{filename}) ({'; '.join(meta)})"
            )
        lines.append("")
    return "\n".join(lines)


def card_filename(card: dict[str, Any]) -> str:
    return f"{card['id']}-{slugify_title(card['title'])}.md"


def export_all(store: Store, snapshot: dict[str, Any]) -> None:
    boards_root = store.boards_root
    boards_root.mkdir(parents=True, exist_ok=True)
    wanted: set[Path] = set()
    for board in snapshot["boards"]:
        cards = [card for card in snapshot["cards"] if card["board"] == board["slug"]]
        board_dir = boards_root / board["slug"]
        board_file = board_dir / "BOARD.md"
        wanted.add(board_file)
        atomic_write(board_file, render_board_markdown(board, cards, snapshot["generated_at"]))
        cards_dir = board_dir / "cards"
        for card in cards:
            card_file = cards_dir / card_filename(card)
            wanted.add(card_file)
            atomic_write(card_file, render_card_markdown(card))
    for path in boards_root.rglob("*.md"):
        if path not in wanted:
            path.unlink()
    web_root = store.web_root
    web_root.mkdir(parents=True, exist_ok=True)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(web_root / "snapshot.json", snapshot_text)
    atomic_write(web_root / "index.html", render_page(snapshot))


def load_viewer_template() -> str:
    return Path(__file__).with_name(VIEWER_RESOURCE).read_text(encoding="utf-8")


def render_page(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c")
    return load_viewer_template().replace(SNAPSHOT_PLACEHOLDER, payload)


class ViewerHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], store: Store) -> None:
        self.taskmatic_store = store
        super().__init__(address, ViewerHandler)


class ViewerHandler(BaseHTTPRequestHandler):
    server: ViewerHTTPServer

    def fresh_snapshot(self) -> dict[str, Any]:
        connection = sqlite3.connect(self.server.taskmatic_store.root / DB_NAME)
        connection.row_factory = sqlite3.Row
        try:
            return build_snapshot(connection)
        finally:
            connection.close()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = render_page(self.fresh_snapshot()).encode("utf-8")
            self.respond(HTTPStatus.OK, "text/html; charset=utf-8", body)
        elif path == "/snapshot.json":
            snapshot = self.fresh_snapshot()
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


def serve(store: Store, host: str, port: int) -> None:
    server = ViewerHTTPServer((host, port), store)
    assigned = server.server_address[1]
    print(f"taskmatic board: http://{host}:{assigned}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "taskmatic_boards",
        "description": "List boards with card counts.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "taskmatic_list",
        "description": "List cards with computed claim state; filter by board, status, assignee, or label.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "board": {"type": "string"},
                "status": {"type": "string", "enum": list(STATUSES)},
                "assignee": {"type": "string"},
                "label": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_read",
        "description": "Read one card with notes and recent activity.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "pattern": ID_PATTERN}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_create",
        "description": "Create a card on a board (default board: main).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "board": {"type": "string"},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "labels": {"type": "array", "items": {"type": "string"}},
                "assignee": {"type": "string"},
                "parent": {"type": "string", "pattern": ID_PATTERN},
                "linked": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_edit",
        "description": "Edit card fields; omitted fields stay unchanged.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "priority": {"type": "string", "enum": list(PRIORITIES)},
                "labels": {"type": "array", "items": {"type": "string"}},
                "assignee": {"type": ["string", "null"]},
                "linked": {"type": ["string", "null"]},
                "notes": {"type": "string"},
            },
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_move",
        "description": "Move a card to another status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "status": {"type": "string", "enum": list(STATUSES)},
            },
            "required": ["id", "status"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_claim",
        "description": "Claim a free or expired card; rejects cards held by another agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "agent": {"type": "string", "minLength": 1, "maxLength": 60},
                "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 2592000},
            },
            "required": ["id", "agent"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_heartbeat",
        "description": "Refresh your claim before it expires.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "agent": {"type": "string", "minLength": 1, "maxLength": 60},
                "ttl_seconds": {"type": "integer", "minimum": 1, "maximum": 2592000},
            },
            "required": ["id", "agent"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_release",
        "description": "Release your claim so another agent can take the card.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "agent": {"type": "string", "minLength": 1, "maxLength": 60},
            },
            "required": ["id", "agent"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_complete",
        "description": "Mark a card done and clear its claim.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "pattern": ID_PATTERN}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "taskmatic_note",
        "description": "Append a bounded note to the card activity log.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": ID_PATTERN},
                "text": {"type": "string", "minLength": 1, "maxLength": 8000},
                "actor": {"type": "string"},
            },
            "required": ["id", "text"],
            "additionalProperties": False,
        },
    },
]

MCP_TOOL_NAMES = tuple(tool["name"] for tool in MCP_TOOLS)


def mcp_tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def mcp_call_tool(store: Store, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    connection = store.connection
    try:
        if name == "taskmatic_boards":
            snapshot = build_snapshot(store.connection)
            boards = [
                {
                    **board,
                    "cards": sum(1 for card in snapshot["cards"] if card["board"] == board["slug"]),
                }
                for board in snapshot["boards"]
            ]
            return mcp_tool_result({"boards": boards})
        if name == "taskmatic_list":
            snapshot = build_snapshot(store.connection)
            cards = snapshot_filter(
                snapshot,
                board=arguments.get("board"),
                status=arguments.get("status"),
                assignee=arguments.get("assignee"),
                label=arguments.get("label"),
            )
            return mcp_tool_result({"cards": cards})
        if name == "taskmatic_read":
            row = get_card(connection, arguments["id"])
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_create":
            card_id = create_card(
                connection,
                board=arguments.get("board", DEFAULT_BOARD),
                title=arguments["title"],
                priority=arguments.get("priority", "normal"),
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee"),
                parent=arguments.get("parent"),
                linked=arguments.get("linked"),
                notes=arguments.get("notes", ""),
                actor="mcp",
            )
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, get_card(connection, card_id)))
        if name == "taskmatic_edit":
            row = edit_card(
                connection,
                arguments["id"],
                title=arguments.get("title"),
                priority=arguments.get("priority"),
                labels=arguments.get("labels"),
                assignee=arguments.get("assignee", False),
                linked=arguments.get("linked", False),
                notes=arguments.get("notes"),
                actor="mcp",
            )
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_move":
            row = move_card(connection, arguments["id"], arguments["status"], actor="mcp")
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_claim":
            row = claim_card(
                connection,
                arguments["id"],
                arguments["agent"],
                arguments.get("ttl_seconds", DEFAULT_TTL_SECONDS),
            )
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_heartbeat":
            row = heartbeat_card(
                connection,
                arguments["id"],
                arguments["agent"],
                arguments.get("ttl_seconds", DEFAULT_TTL_SECONDS),
            )
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_release":
            row = release_card(connection, arguments["id"], arguments["agent"])
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_complete":
            row = complete_card(connection, arguments["id"], actor="mcp")
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
        if name == "taskmatic_note":
            row = append_note(
                connection,
                arguments["id"],
                arguments["text"],
                actor=arguments.get("actor", "mcp"),
            )
            export_all(store, build_snapshot(store.connection))
            return mcp_tool_result(card_payload(connection, row))
    except TaskmaticError as error:
        return {
            "content": [{"type": "text", "text": f"taskmatic: {error}"}],
            "isError": True,
        }
    raise TaskmaticError(f"unknown tool {name}")


def mcp_dispatch(store: Store, request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}
    if not isinstance(method, str):
        return None
    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else MCP_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "taskmatic", "version": "1.0.0"},
            },
        }
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "invalid tools/call parameters"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": mcp_call_tool(store, name, arguments)}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"unknown method {method}"},
    }


def run_mcp(store: Store) -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(request, dict):
            continue
        response = mcp_dispatch(store, request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def print_card_line(card: dict[str, Any]) -> None:
    parts = [card["id"], card["board"], card["status"], f"p:{card['priority']}", card["title"]]
    if card["labels"]:
        parts.append("[" + ",".join(card["labels"]) + "]")
    if card["assignee"]:
        parts.append(f"@{card['assignee']}")
    if card["claim_state"] == "held":
        parts.append(f"claim:{card['claimed_by']}({card['claim_remaining_seconds']}s)")
    elif card["claim_state"] == "expired":
        parts.append(f"claim-expired:{card['claimed_by']}")
    print("  ".join(parts))


def read_notes(argument: str | None, inline: str | None) -> str:
    if inline is not None and argument is not None:
        raise TaskmaticError("use either --notes or --notes-file, not both")
    if argument == "-":
        return sys.stdin.read()
    if argument is not None:
        return Path(argument).read_text(encoding="utf-8")
    return inline or ""


def comma_labels(value: str | None) -> list[str] | None:
    return [label for label in (value or "").split(",") if label.strip()] if value else None


def build_parser() -> Parser:
    parser = Parser(prog="taskmatic", description=__doc__)
    parser.add_argument("--home", help="taskmatic state root (default: taskmatic XDG state)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    boards = subparsers.add_parser("boards", help="list boards")
    boards.add_argument("--json", action="store_true")

    board_create = subparsers.add_parser("board-create", help="create or rename a board")
    board_create.add_argument("slug")
    board_create.add_argument("--title")
    board_create.add_argument("--json", action="store_true")

    add = subparsers.add_parser("add", help="create a card")
    add.add_argument("title")
    add.add_argument("--board", default=DEFAULT_BOARD)
    add.add_argument("--priority", choices=PRIORITIES, default="normal")
    add.add_argument("--labels", help="comma-separated labels")
    add.add_argument("--assignee")
    add.add_argument("--parent")
    add.add_argument("--linked")
    add.add_argument("--notes")
    add.add_argument("--notes-file", help="file path or - for stdin")
    add.add_argument("--json", action="store_true")

    list_parser = subparsers.add_parser("list", help="list cards")
    list_parser.add_argument("--board")
    list_parser.add_argument("--status", choices=STATUSES)
    list_parser.add_argument("--assignee")
    list_parser.add_argument("--label")
    list_parser.add_argument("--json", action="store_true")

    show = subparsers.add_parser("show", help="show one card")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")

    edit = subparsers.add_parser("edit", help="edit card fields")
    edit.add_argument("id")
    edit.add_argument("--title")
    edit.add_argument("--priority", choices=PRIORITIES)
    edit.add_argument("--labels")
    edit.add_argument("--assignee", default=False)
    edit.add_argument("--linked", default=False)
    edit.add_argument("--notes")
    edit.add_argument("--notes-file")
    edit.add_argument("--json", action="store_true")

    move = subparsers.add_parser("move", help="change card status")
    move.add_argument("id")
    move.add_argument("status", choices=STATUSES)
    move.add_argument("--json", action="store_true")

    claim = subparsers.add_parser("claim", help="claim a card for an agent")
    claim.add_argument("id")
    claim.add_argument("--agent", required=True)
    claim.add_argument("--ttl", default=f"{DEFAULT_TTL_SECONDS}s")
    claim.add_argument("--json", action="store_true")

    heartbeat = subparsers.add_parser("heartbeat", help="refresh a held claim")
    heartbeat.add_argument("id")
    heartbeat.add_argument("--agent", required=True)
    heartbeat.add_argument("--ttl", default=f"{DEFAULT_TTL_SECONDS}s")
    heartbeat.add_argument("--json", action="store_true")

    release = subparsers.add_parser("release", help="release a claim")
    release.add_argument("id")
    release.add_argument("--agent", required=True)
    release.add_argument("--json", action="store_true")

    complete = subparsers.add_parser("complete", help="mark done and clear the claim")
    complete.add_argument("id")
    complete.add_argument("--json", action="store_true")

    note = subparsers.add_parser("note", help="append a note to the activity log")
    note.add_argument("id")
    note.add_argument("text")
    note.add_argument("--actor", default="human")
    note.add_argument("--json", action="store_true")

    subparsers.add_parser("export", help="regenerate the markdown mirror and web export")

    snapshot = subparsers.add_parser("snapshot", help="print the snapshot JSON document")
    snapshot.add_argument("--board")
    snapshot.add_argument("--status", choices=STATUSES)
    snapshot.add_argument("--assignee")
    snapshot.add_argument("--label")

    serve_parser = subparsers.add_parser("serve", help="serve the read-only web board")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)

    subparsers.add_parser("mcp", help="run the MCP stdio server")

    path = subparsers.add_parser("path", help="print resolved state paths")
    path.add_argument("which", nargs="?", choices=("root", "db", "export", "web"), default="root")
    return parser


def dispatch(store: Store, args: argparse.Namespace) -> int:
    connection = store.connection
    command = args.command
    if command == "boards":
        boards = list_boards(connection)
        snapshot = build_snapshot(store.connection)
        if args.json:
            print_json(
                [
                    {
                        **board,
                        "cards": sum(
                            1 for card in snapshot["cards"] if card["board"] == board["slug"]
                        ),
                    }
                    for board in boards
                ]
            )
        else:
            for board in boards:
                count = sum(1 for card in snapshot["cards"] if card["board"] == board["slug"])
                print(f"{board['slug']}\t{board['title']}\t{count} cards")
        return 0
    if command == "board-create":
        slug = validate_slug(args.slug)
        with transaction(connection):
            created = ensure_board(connection, slug, args.title)
        if args.json:
            print_json({"slug": created["slug"], "title": created["title"]})
        else:
            print(f"board {created['slug']}: {created['title']}")
        export_all(store, build_snapshot(store.connection))
        return 0
    if command == "add":
        card_id = create_card(
            connection,
            board=args.board,
            title=args.title,
            priority=args.priority,
            labels=comma_labels(args.labels),
            assignee=args.assignee,
            parent=args.parent,
            linked=args.linked,
            notes=read_notes(args.notes_file, args.notes),
        )
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, get_card(connection, card_id)))
        else:
            print(f"created {card_id} on {args.board}")
        return 0
    if command == "list":
        snapshot = build_snapshot(store.connection)
        cards = snapshot_filter(
            snapshot,
            board=args.board,
            status=args.status,
            assignee=args.assignee,
            label=args.label,
        )
        if args.json:
            print_json(cards)
        elif cards:
            for card in cards:
                print_card_line(card)
        else:
            print("no cards match")
        return 0
    if command == "show":
        row = get_card(connection, args.id)
        payload = card_payload(connection, row)
        if args.json:
            print_json(payload)
        else:
            print(f"{payload['id']}  {payload['title']}")
            print(
                f"board: {payload['board']}  status: {payload['status']}"
                f"  priority: {payload['priority']}"
            )
            details = [f"labels: {', '.join(payload['labels'])}"] if payload["labels"] else []
            if payload["assignee"]:
                details.append(f"assignee: {payload['assignee']}")
            if payload["parent"]:
                details.append(f"parent: {payload['parent']}")
            if payload["children"]:
                details.append(f"children: {', '.join(payload['children'])}")
            if payload["linked"]:
                details.append(f"linked: {payload['linked']}")
            if payload["claim_state"] == "held":
                details.append(
                    f"claim: {payload['claimed_by']} ({payload['claim_remaining_seconds']}s left)"
                )
            elif payload["claim_state"] == "expired":
                details.append(f"claim expired: {payload['claimed_by']}")
            if details:
                print("  ".join(details))
            if payload["notes"].strip():
                print()
                print(payload["notes"].rstrip())
            print()
            print("activity:")
            for event in payload["activity"]:
                detail = f" — {event['detail']}" if event["detail"] else ""
                print(f"  {event['at']} {event['kind']} by {event['actor']}{detail}")
        return 0
    if command == "edit":
        row = edit_card(
            connection,
            args.id,
            title=args.title,
            priority=args.priority,
            labels=comma_labels(args.labels),
            assignee=args.assignee,
            linked=args.linked,
            notes=read_notes(args.notes_file, args.notes)
            if args.notes is not None or args.notes_file is not None
            else None,
        )
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"edited {row['id']}")
        return 0
    if command == "move":
        row = move_card(connection, args.id, args.status)
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"moved {row['id']} to {row['status']}")
        return 0
    if command == "claim":
        row = claim_card(connection, args.id, args.agent, parse_ttl(args.ttl))
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"claimed {row['id']} by {args.agent}")
        return 0
    if command == "heartbeat":
        row = heartbeat_card(connection, args.id, args.agent, parse_ttl(args.ttl))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            state = claim_state(row)
            print(f"heartbeat {row['id']}: {state['claim_remaining_seconds']}s left")
        return 0
    if command == "release":
        row = release_card(connection, args.id, args.agent)
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"released {row['id']}")
        return 0
    if command == "complete":
        row = complete_card(connection, args.id)
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"completed {row['id']}")
        return 0
    if command == "note":
        row = append_note(connection, args.id, args.text, actor=args.actor)
        export_all(store, build_snapshot(store.connection))
        if args.json:
            print_json(card_payload(connection, row))
        else:
            print(f"noted {row['id']}")
        return 0
    if command == "export":
        export_all(store, build_snapshot(store.connection))
        print(str(store.export_root))
        return 0
    if command == "snapshot":
        snapshot = build_snapshot(store.connection)
        snapshot["cards"] = snapshot_filter(
            snapshot,
            board=args.board,
            status=args.status,
            assignee=args.assignee,
            label=args.label,
        )
        print_json(snapshot)
        return 0
    if command == "serve":
        serve(store, args.host, args.port)
        return 0
    if command == "mcp":
        return run_mcp(store)
    if command == "path":
        targets = {
            "root": store.root,
            "db": store.root / DB_NAME,
            "export": store.export_root,
            "web": store.web_root,
        }
        print(targets[args.which])
        return 0
    raise TaskmaticError(f"unhandled command {command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        store = open_store(args.home)
        try:
            return dispatch(store, args)
        finally:
            store.connection.close()
    except TaskmaticError as error:
        print(f"taskmatic: {error}", file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error) as error:
        print(f"taskmatic: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
