from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "skill-doctor" / "scripts" / "skill_doctor.py"
HOST = "custom"
SESSION_A = "ses_current00000000000000000000000000000"
SESSION_B = "ses_other0000000000000000000000000000000"
WORKSPACE = "/tmp/doctor-fixture-workspace"

DIAGNOSIS_SCHEMA = "agent-skills/skill-doctor/diagnosis/v1"
REPORT_REQUEST_SCHEMA = "agent-skills/skill-doctor/report-request/v1"


def run_doctor(
    *arguments: str,
    state: Path,
    stdin: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(RUNNER), *arguments],
        input=stdin,
        capture_output=True,
        check=False,
        env={**os.environ, "XDG_STATE_HOME": str(state), "PYTHONPATH": "/invalid"},
    )


def run_doctor_json(
    *arguments: str,
    state: Path,
    stdin: bytes | None = None,
) -> Any:
    result = run_doctor(*arguments, state=state, stdin=stdin)
    assert result.returncode == 0, result.stderr.decode()
    return json.loads(result.stdout)


def create_session_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE session (
                id TEXT PRIMARY KEY, title TEXT, directory TEXT, time_created INTEGER);
            CREATE TABLE message (
                id TEXT PRIMARY KEY, session_id TEXT, data TEXT);
            CREATE TABLE part (
                id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                time_created INTEGER, data TEXT);
            """
        )
        error_part = json.dumps(
            {
                "type": "tool",
                "tool": "skill",
                "callID": "c1",
                "state": {
                    "status": "error",
                    "input": {"name": "stopit"},
                    "error": "boom",
                    "time": {"start": 150, "end": 250},
                },
            }
        )
        rows = [
            ("session", (SESSION_A, "Current", WORKSPACE, 100)),
            ("session", (SESSION_B, "Other", "/tmp/other", 500)),
            ("message", ("m1", SESSION_A, json.dumps({"role": "user"}))),
            ("message", ("m2", SESSION_A, json.dumps({"role": "assistant"}))),
            ("message", ("m3", SESSION_B, json.dumps({"role": "user"}))),
            (
                "part",
                (
                    "p1",
                    "m1",
                    SESSION_A,
                    110,
                    json.dumps({"type": "text", "text": "stopit failed again after a retry"}),
                ),
            ),
            ("part", ("p2", "m2", SESSION_A, 200, error_part)),
            (
                "part",
                (
                    "p3",
                    "m2",
                    SESSION_A,
                    300,
                    json.dumps(
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {"status": "completed", "input": {"command": "git status"}},
                        }
                    ),
                ),
            ),
            (
                "part",
                (
                    "p3b",
                    "m2",
                    SESSION_A,
                    310,
                    json.dumps(
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "input": {"command": "git diff --stat"},
                            },
                        }
                    ),
                ),
            ),
            ("part", ("broken", "m2", SESSION_A, 400, "not-json")),
            (
                "part",
                (
                    "p4",
                    "m3",
                    SESSION_B,
                    510,
                    json.dumps({"type": "text", "text": "unrelated other session"}),
                ),
            ),
        ]
        for table, values in rows:
            placeholders = ",".join("?" * len(values))
            statement = " ".join(["INSERT INTO " + table, "VALUES (" + placeholders + ")"])
            connection.execute(statement, values)
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def history(tmp_path: Path) -> Path:
    database = tmp_path / "history.db"
    create_session_database(database)
    return database


V2_ERROR_PART = {
    "type": "tool",
    "name": "skill",
    "id": "c1",
    "time": {"created": 200},
    "state": {
        "status": "error",
        "input": {"name": "stopit"},
        "error": "boom",
    },
}
V2_BASH_PART = {
    "type": "tool",
    "name": "bash",
    "id": "c2",
    "time": {"created": 300},
    "state": {"status": "completed", "input": {"command": "git status"}},
}
V2_REASONING_PART = {"type": "reasoning", "text": "internal reasoning is not an action"}

# Rows of the mixed-schema database: SESSION_A exists only in the V2 schema,
# SESSION_B only in the legacy schema, and SESSION_A additionally has a stale
# legacy session row that must never win over session_v2.
MIXED_V2_ROWS = [
    ("session_v2", (SESSION_A, "Current V2", WORKSPACE, 100)),
    (
        "session_message",
        ("v2-sys", SESSION_A, "system", 1, 5, json.dumps({"text": "internal system notice"})),
    ),
    (
        "session_message",
        (
            "v2-m1",
            SESSION_A,
            "user",
            2,
            110,
            json.dumps({"text": "stopit failed again after a retry", "time": {"created": 110}}),
        ),
    ),
    (
        "session_message",
        (
            "v2-m2",
            SESSION_A,
            "assistant",
            3,
            400,
            json.dumps(
                {
                    "finish": "tool-calls",
                    "content": [V2_ERROR_PART, V2_BASH_PART, V2_REASONING_PART],
                }
            ),
        ),
    ),
    ("session_message", ("v2-m3", SESSION_A, "assistant", 4, 500, "not-json")),
]
MIXED_LEGACY_ROWS = [
    ("session", (SESSION_A, "Current Legacy", WORKSPACE, 100)),
    ("session", (SESSION_B, "Other Legacy", "/tmp/other", 500)),
    ("message", ("m3", SESSION_B, json.dumps({"role": "user"}))),
    ("part", ("p4", "m3", SESSION_B, 510, json.dumps({"type": "text", "text": "unrelated"}))),
]


def create_mixed_session_database(path: Path, *, include_legacy: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        script = [
            """
            CREATE TABLE session_v2 (
                id TEXT PRIMARY KEY, title TEXT, directory TEXT, time_created INTEGER);
            CREATE TABLE session_message (
                id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER,
                time_created INTEGER, data TEXT);
            """
        ]
        if include_legacy:
            script.append(
                """
                CREATE TABLE session (
                    id TEXT PRIMARY KEY, title TEXT, directory TEXT, time_created INTEGER);
                CREATE TABLE message (
                    id TEXT PRIMARY KEY, session_id TEXT, data TEXT);
                CREATE TABLE part (
                    id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                    time_created INTEGER, data TEXT);
                """
            )
        for statement in script:
            connection.executescript(statement)
        rows: list[tuple[str, tuple[object, ...]]] = list(MIXED_V2_ROWS)
        if include_legacy:
            rows += MIXED_LEGACY_ROWS
        for table, values in rows:
            placeholders = ",".join("?" * len(values))
            statement = " ".join(["INSERT INTO " + table, "VALUES (" + placeholders + ")"])
            connection.execute(statement, values)
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def mixed_history(tmp_path: Path) -> Path:
    database = tmp_path / "mixed.db"
    create_mixed_session_database(database)
    return database


def diagnosis_for(session_id: str) -> dict[str, Any]:
    return {
        "schema": DIAGNOSIS_SCHEMA,
        "session": {
            "id": session_id,
            "host": HOST,
            "workspace": WORKSPACE,
            "title": "Current",
        },
        "recorded_at": "2026-10-03T10:00:00Z",
        "coverage": {
            "complete": False,
            "notes": ["1 of 5 parts could not be parsed"],
            "parts_scanned": 5,
            "parts_skipped": 1,
            "truncated": False,
        },
        "skills": [
            {
                "name": "stopit",
                "origin": {
                    "kind": "declared",
                    "source": "https://kisev.github.io/skills",
                    "root": None,
                },
            }
        ],
        "evidence": [
            {"id": "ev-001", "kind": "skill-error", "excerpt": "boom", "time": 200},
            {
                "id": "ev-002",
                "kind": "user-intervention",
                "excerpt": "stopit failed again after a retry",
                "time": 110,
            },
        ],
        "observations": [
            {
                "id": "obs-001",
                "classification": "skill-defect",
                "skill": "stopit",
                "status": "suspected",
                "summary": "stopit errored and the user repeated the request",
                "evidence": ["ev-001", "ev-002"],
                "fingerprints": ["atomic_write"],
                "proposal": "inspect the atomic write error path",
                "workaround": None,
            }
        ],
        "conclusions": ["suspected write-path defect in stopit"],
        "open_questions": ["reproduce outside this session"],
    }


def report_request() -> dict[str, Any]:
    return {
        "schema": REPORT_REQUEST_SCHEMA,
        "skill": "stopit",
        "source": "https://kisev.github.io/skills",
        "version": None,
        "reproduction": "unverified",
        "created_at": "2026-10-03T11:00:00Z",
        "report_md": (
            "# Bug report: stopit\n\n"
            "## Identification\n\nstopit from https://kisev.github.io/skills.\n\n"
            "## Expected behavior\n\nThe write succeeds.\n\n"
            "## Actual behavior\n\nThe runner reports a write failure.\n\n"
            "## Minimal example\n\nCall stopit with a read-only state root.\n\n"
            "## Workaround\n\nRepair the directory mode.\n\n"
            "## Recommendation\n\nFail with a clearer message.\n"
        ),
        "example_files": {"steps.md": "1. call stopit\n2. observe the failure\n"},
    }


# ---------------------------------------------------------------------------
# Session selection
# ---------------------------------------------------------------------------


class TestSessionSelection:
    def test_collect_returns_only_the_exact_requested_session(
        self, tmp_path: Path, history: Path
    ) -> None:
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect", "--session-id", SESSION_A, "--db", str(history), state=state
        )

        assert payload["session"]["id"] == SESSION_A
        assert payload["session"]["host"] == HOST
        assert [call["name"] for call in payload["skill_calls"]] == ["stopit"]
        assert payload["skill_calls"][0]["status"] == "error"
        assert payload["skill_calls"][0]["error"] == "boom"
        assert payload["user_messages"][0]["text"] == "stopit failed again after a retry"
        assert [action["action"] for action in payload["actions"]] == [
            "bash:git status",
            "bash:git diff",
        ]
        assert "unrelated other session" not in json.dumps(payload)
        assert SESSION_B not in json.dumps(payload)

    def test_collect_states_incomplete_coverage_explicitly(
        self, tmp_path: Path, history: Path
    ) -> None:
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect", "--session-id", SESSION_A, "--db", str(history), state=state
        )

        coverage = payload["coverage"]
        assert coverage["complete"] is False
        assert coverage["parts_skipped"] == 1
        assert coverage["notes"] == ["1 of 5 parts could not be parsed"]

    def test_collect_truncation_is_flagged_not_hidden(self, tmp_path: Path, history: Path) -> None:
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect",
            "--session-id",
            SESSION_A,
            "--db",
            str(history),
            "--max-actions",
            "1",
            state=state,
        )

        assert payload["coverage"]["truncated"] is True
        assert payload["coverage"]["complete"] is False
        assert payload["coverage"]["actions_seen"] > payload["coverage"]["actions_listed"]
        assert any("truncated" in note for note in payload["coverage"]["notes"])

    def test_unknown_session_is_refused_without_substitution(
        self, tmp_path: Path, history: Path
    ) -> None:
        state = tmp_path / "state"
        result = run_doctor(
            "collect",
            "--session-id",
            "ses_absent0000000000000000000000000000",
            "--db",
            str(history),
            state=state,
        )

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "collect_error"
        assert "does not exist" in payload["error"]["message"]
        assert "unrelated other session" not in result.stdout.decode()
        assert not state.exists()

    def test_collect_without_any_database_reports_the_error(self, tmp_path: Path) -> None:
        result = run_doctor(
            "collect",
            "--session-id",
            SESSION_A,
            "--host",
            "auto",
            state=tmp_path / "plain",
        )

        assert result.returncode == 2
        assert json.loads(result.stdout)["error"]["code"] == "collect_error"


# ---------------------------------------------------------------------------
# Session schema detection (V2 and legacy)
# ---------------------------------------------------------------------------


class TestSessionSchemaDetection:
    def test_v2_schema_is_preferred_over_a_stale_legacy_row(
        self, tmp_path: Path, mixed_history: Path
    ) -> None:
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect", "--session-id", SESSION_A, "--db", str(mixed_history), state=state
        )

        assert payload["session"]["title"] == "Current V2"
        assert [call["name"] for call in payload["skill_calls"]] == ["stopit"]
        assert payload["skill_calls"][0]["status"] == "error"
        assert payload["skill_calls"][0]["error"] == "boom"
        assert payload["skill_calls"][0]["time_created"] == 200
        assert payload["user_messages"][0]["text"] == "stopit failed again after a retry"
        assert [action["action"] for action in payload["actions"]] == ["bash:git status"]
        # The system row, the reasoning part, and the unparseable assistant
        # data are covered by the coverage counters.
        assert payload["coverage"]["parts_total"] == 5
        assert payload["coverage"]["parts_skipped"] == 1
        assert payload["coverage"]["notes"] == ["1 of 5 parts could not be parsed"]
        assert "internal system notice" not in json.dumps(payload)
        assert "internal reasoning" not in json.dumps(payload)

    def test_legacy_only_session_falls_back_to_legacy_tables(
        self, tmp_path: Path, mixed_history: Path
    ) -> None:
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect", "--session-id", SESSION_B, "--db", str(mixed_history), state=state
        )

        assert payload["session"]["title"] == "Other Legacy"
        assert payload["skill_calls"] == []
        assert payload["user_messages"][0]["text"] == "unrelated"
        assert payload["coverage"]["parts_skipped"] == 0

    def test_v2_only_database_collects_without_legacy_tables(self, tmp_path: Path) -> None:
        database = tmp_path / "v2-only.db"
        create_mixed_session_database(database, include_legacy=False)
        state = tmp_path / "state"
        payload = run_doctor_json(
            "collect", "--session-id", SESSION_A, "--db", str(database), state=state
        )

        assert payload["session"]["title"] == "Current V2"
        assert [call["name"] for call in payload["skill_calls"]] == ["stopit"]

    def test_unknown_session_stays_refused_on_a_mixed_database(
        self, tmp_path: Path, mixed_history: Path
    ) -> None:
        state = tmp_path / "state"
        result = run_doctor(
            "collect",
            "--session-id",
            "ses_absent0000000000000000000000000000",
            "--db",
            str(mixed_history),
            state=state,
        )

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["error"]["code"] == "collect_error"
        assert "does not exist" in payload["error"]["message"]
        assert "Current V2" not in result.stdout.decode()

    def test_database_with_partial_schemas_is_refused(self, tmp_path: Path) -> None:
        database = tmp_path / "partial.db"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE session (id TEXT PRIMARY KEY, title TEXT, directory TEXT,"
                " time_created INTEGER)"
            )
            connection.commit()
        finally:
            connection.close()
        result = run_doctor(
            "collect",
            "--session-id",
            SESSION_A,
            "--db",
            str(database),
            state=tmp_path / "state",
        )

        assert result.returncode == 2
        message = json.loads(result.stdout)["error"]["message"]
        assert "misses session tables" in message


# ---------------------------------------------------------------------------
# Incremental diagnosis records
# ---------------------------------------------------------------------------


class TestIncrementalRecords:
    def record(self, tmp_path: Path, state: Path, diagnosis: dict[str, Any]) -> Any:
        return run_doctor_json(
            "record",
            "--session-id",
            str(diagnosis["session"]["id"]),
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(diagnosis).encode(),
        )

    def test_first_record_then_incremental_revision_without_duplicates(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        first = diagnosis_for(SESSION_A)
        summary = self.record(tmp_path, state, first)
        assert summary["observations"] == {"total": 1, "added": 1, "revised": 0, "retained": 0}
        assert summary["evidence"] == {"total": 2, "added": 2}
        assert summary["history"] == []

        revised = diagnosis_for(SESSION_A)
        revised["evidence"].append(
            {"id": "ev-003", "kind": "workaround", "excerpt": "manual retry works", "time": 320}
        )
        revised["observations"][0]["status"] = "confirmed"
        revised["conclusions"] = ["confirmed write-path defect in stopit"]
        summary = self.record(tmp_path, state, revised)

        assert summary["observations"] == {"total": 1, "added": 0, "revised": 1, "retained": 0}
        assert summary["evidence"] == {"total": 3, "added": 1}
        assert len(summary["history"]) == 1
        history_files = list(
            (state / "agent-skills/skill-doctor/sessions").glob("*/history/diagnosis/*.json")
        )
        assert len(history_files) == 1

        stored = run_doctor_json("show", "--session-id", SESSION_A, "--host", HOST, state=state)
        assert stored["schema"] == DIAGNOSIS_SCHEMA
        assert stored["observations"][0]["status"] == "confirmed"
        assert [entry["id"] for entry in stored["evidence"]] == ["ev-001", "ev-002", "ev-003"]

    def test_duplicate_identifiers_and_unknown_evidence_are_rejected(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        duplicated = diagnosis_for(SESSION_A)
        duplicated["observations"].append(dict(duplicated["observations"][0]))
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(duplicated).encode(),
        )
        assert result.returncode == 2
        assert json.loads(result.stdout)["error"]["code"] == "record_error"

        dangling = diagnosis_for(SESSION_A)
        dangling["observations"][0]["evidence"].append("ev-missing")
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(dangling).encode(),
        )
        assert result.returncode == 2

        hypothesis_as_fact = diagnosis_for(SESSION_A)
        hypothesis_as_fact["observations"][0]["classification"] = "skill-defect"
        hypothesis_as_fact["observations"][0]["fingerprints"] = []
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(hypothesis_as_fact).encode(),
        )
        assert result.returncode == 2
        assert "fingerprints" in json.loads(result.stdout)["error"]["message"]

    def test_recorded_evidence_is_append_only(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        self.record(tmp_path, state, diagnosis_for(SESSION_A))

        dropped = diagnosis_for(SESSION_A)
        dropped["evidence"] = dropped["evidence"][:1]
        dropped["observations"][0]["evidence"] = ["ev-001"]
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(dropped).encode(),
        )
        assert result.returncode == 2
        assert "append-only" in json.loads(result.stdout)["error"]["message"]

        rewritten = diagnosis_for(SESSION_A)
        rewritten["evidence"][1]["excerpt"] = "mutated excerpt"
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(rewritten).encode(),
        )
        assert result.returncode == 2
        assert "rewritten in place" in json.loads(result.stdout)["error"]["message"]

    def test_records_of_different_sessions_do_not_overwrite_each_other(
        self, tmp_path: Path
    ) -> None:
        state = tmp_path / "state"
        self.record(tmp_path, state, diagnosis_for(SESSION_A))
        other = diagnosis_for(SESSION_B)
        other["session"]["workspace"] = "/tmp/other"
        self.record(tmp_path, state, other)

        sessions = sorted((state / "agent-skills/skill-doctor/sessions").iterdir())
        assert len(sessions) == 2
        stored_a = run_doctor_json("show", "--session-id", SESSION_A, "--host", HOST, state=state)
        stored_b = run_doctor_json("show", "--session-id", SESSION_B, "--host", HOST, state=state)
        assert stored_a["session"]["id"] == SESSION_A
        assert stored_b["session"]["id"] == SESSION_B

        mismatched = diagnosis_for(SESSION_A)
        mismatched["session"]["id"] = SESSION_B
        result = run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(mismatched).encode(),
        )
        assert result.returncode == 2
        assert "does not match --session-id" in json.loads(result.stdout)["error"]["message"]

    def test_private_storage_stays_private_and_atomic(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        self.record(tmp_path, state, diagnosis_for(SESSION_A))

        record = next((state / "agent-skills/skill-doctor/sessions").rglob("diagnosis.json"))
        assert record.parent.parent.parent.name == "skill-doctor"
        assert record.parent.parent.parent.parent.name == "agent-skills"
        assert stat.S_IMODE(record.stat().st_mode) == 0o600
        assert stat.S_IMODE(record.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(record.parent.parent.stat().st_mode) == 0o700


# ---------------------------------------------------------------------------
# Development-use matching
# ---------------------------------------------------------------------------


def write_skill(
    root: Path,
    name: str,
    *,
    source: str = "https://kisev.github.io/skills",
    body: str = "def atomic_write(payload):\n    return payload\n",
) -> None:
    skill = root / name
    (skill / "scripts").mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.source.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: probe\n"
        "license: MIT\n"
        "metadata:\n"
        '  author: "Test"\n'
        f'  source: "{source}"\n'
        "---\n",
        encoding="utf-8",
    )
    (skill / "scripts" / "runner.py").write_text(body, encoding="utf-8")


class TestMatch:
    def match(self, tmp_path: Path, skills_root: Path) -> Any:
        return run_doctor_json("match", "--skills-root", str(skills_root), state=tmp_path / "state")

    def test_verdicts_by_fingerprints_and_provenance(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        skills = tmp_path / "skills"
        write_skill(skills, "stopit")
        record = run_doctor_json(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(diagnosis_for(SESSION_A)).encode(),
        )
        assert record["status"] == "recorded"

        payload = self.match(tmp_path, skills)
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "relevant"
        assert observation["fingerprints"][0]["files"] == ["scripts/runner.py"]

        write_skill(skills, "stopit", body="def other_function():\n    return 1\n")
        payload = self.match(tmp_path, skills)
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "resolved"

        shutil.rmtree(skills / "stopit")
        payload = self.match(tmp_path, skills)
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "missing"

    def test_ambiguous_provenance_never_becomes_a_name_match(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        skills = tmp_path / "skills"
        write_skill(skills, "stopit")

        def record_with(origin: dict[str, Any]) -> Any:
            diagnosis = diagnosis_for(SESSION_A)
            diagnosis["skills"][0]["origin"] = origin
            run_doctor(
                "record",
                "--session-id",
                SESSION_A,
                "--host",
                HOST,
                state=state,
                stdin=json.dumps(diagnosis).encode(),
            )
            return self.match(tmp_path, skills)

        payload = record_with({"kind": "unknown", "source": None, "root": None})
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "needs-clarification"
        assert "name alone is insufficient" in observation["reason"]

        payload = record_with({"kind": "local", "source": None, "root": "/tmp/some-other-checkout"})
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "needs-clarification"
        assert "different tree" in observation["reason"]

        payload = record_with(
            {
                "kind": "declared",
                "source": "https://example.invalid/fork",
                "root": None,
            }
        )
        [observation] = payload["diagnoses"][0]["observations"]
        assert observation["verdict"] == "needs-clarification"
        assert "origin differs" in observation["reason"]

    def test_match_is_read_only_and_skips_unreadable_records(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        skills = tmp_path / "skills"
        write_skill(skills, "stopit")
        run_doctor(
            "record",
            "--session-id",
            SESSION_A,
            "--host",
            HOST,
            state=state,
            stdin=json.dumps(diagnosis_for(SESSION_A)).encode(),
        )
        corrupt = state / "agent-skills/skill-doctor/sessions"
        corrupt_dir = next(corrupt.iterdir())
        (corrupt_dir / "diagnosis.json").write_bytes(b"{broken")
        (corrupt_dir / "decoy.txt").write_text("ignored", encoding="utf-8")

        before = sorted(str(path) for path in state.rglob("*"))
        payload = run_doctor_json("match", "--skills-root", str(skills), state=state)
        after = sorted(str(path) for path in state.rglob("*"))

        assert payload["matched_observations"] == 0
        assert payload["diagnoses"] == []
        assert before == after


# ---------------------------------------------------------------------------
# Public bug-report archive
# ---------------------------------------------------------------------------


class TestPublicReport:
    def prepare(
        self,
        tmp_path: Path,
        request: dict[str, Any],
        *extra: str,
    ) -> subprocess.CompletedProcess[bytes]:
        return run_doctor(
            "report",
            "prepare",
            "--skill",
            "stopit",
            "--forbid-value",
            WORKSPACE,
            "--forbid-value",
            SESSION_A,
            *extra,
            state=tmp_path / "state",
            stdin=json.dumps(request).encode(),
        )

    def commit(
        self,
        tmp_path: Path,
        request: dict[str, Any],
        expected_dir: str,
    ) -> subprocess.CompletedProcess[bytes]:
        return run_doctor(
            "report",
            "commit",
            "--skill",
            "stopit",
            "--expected-dir",
            expected_dir,
            "--forbid-value",
            WORKSPACE,
            "--forbid-value",
            SESSION_A,
            state=tmp_path / "state",
            stdin=json.dumps(request).encode(),
        )

    def test_committed_archive_matches_the_preview_exactly(self, tmp_path: Path) -> None:
        preview = self.prepare(tmp_path, report_request())
        assert preview.returncode == 0, preview.stderr.decode()
        payload = json.loads(preview.stdout)
        assert payload["status"] == "preview"
        assert payload["excluded"] == [
            "conversation history",
            "raw session logs",
            "project files",
            "private diagnosis records",
            "anonymization mapping",
        ]
        manifest_entry = next(item for item in payload["files"] if item["path"] == "manifest.json")
        manifest = json.loads(manifest_entry["content"])
        assert manifest["version_status"] == "unknown"
        assert manifest["reproduction"] == "unverified"

        commit = self.commit(tmp_path, report_request(), payload["destination"])
        assert commit.returncode == 0, commit.stderr.decode()
        written = json.loads(commit.stdout)
        assert [item["path"] for item in written["files"]] == [
            item["path"] for item in payload["files"]
        ]
        assert [item["sha256"] for item in written["files"]] == [
            item["sha256"] for item in payload["files"]
        ]
        destination = Path(payload["destination"])
        for item in payload["files"]:
            assert (destination / item["path"]).read_text(encoding="utf-8") == item["content"]

    def test_archive_metadata_and_names_stay_neutral(self, tmp_path: Path) -> None:
        preview = self.prepare(tmp_path, report_request())
        destination = Path(json.loads(preview.stdout)["destination"])
        assert "skill-doctor" in str(destination.parent)
        assert destination.name == json.loads(preview.stdout)["destination"].split("/")[-1]

        commit = self.commit(tmp_path, report_request(), str(destination))
        assert commit.returncode == 0
        files = sorted(path for path in destination.rglob("*") if path.is_file())
        assert [path.name for path in files] == ["steps.md", "manifest.json", "report.md"]
        for path in files:
            assert path.stat().st_mtime == 946684800
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert "ses_current" not in json.dumps(
            {path.name: path.read_text(encoding="utf-8") for path in files}
        )

    def test_private_values_are_refused_in_content_and_names(self, tmp_path: Path) -> None:
        request = report_request()
        request["example_files"] = {"trace.md": "failed at " + WORKSPACE + " with the error\n"}
        result = self.prepare(tmp_path, request)
        assert result.returncode == 2
        assert "private value #0" in json.loads(result.stdout)["error"]["message"]
        assert WORKSPACE not in result.stdout.decode()

        named = report_request()
        named["example_files"] = {f"trace-{SESSION_A}.md": "content\n"}
        result = self.prepare(tmp_path, named)
        assert result.returncode == 2
        assert "file name" in json.loads(result.stdout)["error"]["message"]

    def test_changed_content_cannot_hijack_a_confirmed_destination(self, tmp_path: Path) -> None:
        preview = self.prepare(tmp_path, report_request())
        destination = json.loads(preview.stdout)["destination"]

        result = self.commit(tmp_path, report_request(), str(tmp_path / "elsewhere"))
        assert result.returncode == 2
        assert "changed after confirmation" in json.loads(result.stdout)["error"]["message"]

        commit = self.commit(tmp_path, report_request(), destination)
        assert commit.returncode == 0

        changed = report_request()
        changed["report_md"] = changed["report_md"].replace("clearer message", "different message")
        other_preview = self.prepare(tmp_path, changed)
        assert other_preview.returncode == 0
        other_destination = json.loads(other_preview.stdout)["destination"]
        assert other_destination != destination
        result = self.commit(tmp_path, changed, destination)
        assert result.returncode == 2
        assert "changed after confirmation" in json.loads(result.stdout)["error"]["message"]
        committed = {path.name for path in Path(destination).rglob("*") if path.is_file()}
        assert committed == {"manifest.json", "report.md", "steps.md"}

    def test_required_sections_and_unknown_version_marking_are_enforced(
        self, tmp_path: Path
    ) -> None:
        incomplete = report_request()
        del incomplete["report_md"]
        incomplete["report_md"] = "# Bug report\n\nNo sections.\n"
        result = self.prepare(tmp_path, incomplete)
        assert result.returncode == 2
        assert "required section" in json.loads(result.stdout)["error"]["message"]

        known = report_request()
        known["version"] = "2.0.19"
        known["reproduction"] = "verified"
        preview = json.loads(self.prepare(tmp_path, known).stdout)
        manifest = json.loads(
            next(item for item in preview["files"] if item["path"] == "manifest.json")["content"]
        )
        assert manifest["version_status"] == "known"
        assert manifest["reproduction"] == "verified"
        assert preview["notes"] == []
