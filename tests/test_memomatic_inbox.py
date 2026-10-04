from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "shared/references/memomatic_inbox.py"
PEOPLE_JOURNAL = ROOT / "shared/references/people_runtime/people_journal.py"
TRIAGE = ROOT / "shared/references/work_item_runtime/triage.py"
CONTRACT = ROOT / "shared/references/work_item_runtime/contract.py"
BUILT_HANDOFF = ROOT / ".build/skills/handoff/scripts/handoff.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inbox_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    inbox = state / "memomatic" / "inbox"
    inbox.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return inbox


def test_drop_writes_bounded_private_file(inbox_env: Path) -> None:
    module = load_module("memomatic_inbox_test", HELPER)
    lines = module.entry_lines(
        ["Retro conclusion about release cadence"],
        source="team-retro",
        key="retro-cadence",
        project="skills",
    )
    path = module.drop_memory(lines, "team-retro")
    assert path is not None and path.parent == inbox_env
    assert path.name.startswith("team-retro-") and path.name.endswith(".md")
    assert path.stat().st_mode & 0o777 == 0o600
    body = path.read_text(encoding="utf-8")
    assert body.startswith("- Retro conclusion about release cadence ")
    assert "<!-- source: team-retro -->" in body
    assert "<!-- key: retro-cadence -->" in body
    assert "<!-- origin: agent -->" in body
    assert "<!-- project: skills -->" in body


def test_drop_skips_when_memomatic_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    module = load_module("memomatic_inbox_absent", HELPER)
    lines = module.entry_lines(["Any durable fact"], source="user")
    assert module.drop_memory(lines, "user") is None


def test_invalid_sources_and_bounds_are_rejected(inbox_env: Path) -> None:
    module = load_module("memomatic_inbox_invalid", HELPER)
    with pytest.raises(module.InboxError):
        module.entry_lines(["text"], source="UPPER")
    with pytest.raises(module.InboxError):
        module.entry_lines(["text"], source="team-retro", key="Not Kebab")
    with pytest.raises(module.InboxError):
        module.entry_lines(["text" * 5000], source="team-retro")


def test_cli_drop_emits_json(inbox_env: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "drop",
            "--source",
            "spec-manage",
            "--project",
            "skills",
            "--key",
            "spec-skills-0013",
            "--text",
            "Accepted the inbox architecture for memory synergy.",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "dropped"
    dropped = list(inbox_env.glob("spec-manage-*.md"))
    assert len(dropped) == 1
    assert "<!-- key: spec-skills-0013 -->" in dropped[0].read_text(encoding="utf-8")


def test_people_journal_appends_mirror_the_inbox(inbox_env: Path) -> None:
    journal = load_module("people_journal_mirror", PEOPLE_JOURNAL)
    outcome = journal.append_entry(
        "pipelines",
        "agreement",
        "anna",
        "Review backend PRs before Friday demo",
        due="2026-10-02",
    )
    assert outcome["duplicate"] is False
    drops = list(inbox_env.glob("people-journal-*.md"))
    assert len(drops) == 1
    body = drops[0].read_text(encoding="utf-8")
    assert body.startswith("- [pipelines] agreement (due 2026-10-02): anna: Review backend PRs")
    assert f"<!-- key: people-pipelines-{outcome['id']} -->" in body
    assert "<!-- source: people-journal -->" in body


def test_people_journal_works_without_memomatic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    journal = load_module("people_journal_nomem", PEOPLE_JOURNAL)
    outcome = journal.append_entry("pipelines", "note", None, "Plain note")
    assert outcome["duplicate"] is False


def test_triage_and_prepare_hooks_drop_entries(inbox_env: Path) -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from shared.references.work_item_runtime import contract, triage

    triage._drop_issue_memory(
        {"hostname": "gitlab.com", "project_id": "123", "iid": "42"},
        "Release preparation",
        "accepted",
        "ready for the milestone",
    )
    contract._drop_prepare_memory({"outcome": "Ship the inbox integration"})
    drops = {path.name.split("-2026")[0]: path for path in inbox_env.glob("*.md")}
    assert set(drops) == {"task-triage", "task-prepare"}
    triage_body = drops["task-triage"].read_text(encoding="utf-8")
    assert "triage gitlab.com/123#42" in triage_body
    assert "<!-- key: triage-gitlab-com-123-42 -->" in triage_body
    prepare_body = drops["task-prepare"].read_text(encoding="utf-8")
    assert "prepared task outcome: Ship the inbox integration" in prepare_body


@pytest.mark.skipif(
    not BUILT_HANDOFF.exists(),
    reason="built handoff archive is required",
)
def test_built_handoff_mirrors_the_inbox(inbox_env: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    helper = BUILT_HANDOFF.with_name("memomatic_inbox.py")
    assert helper.exists(), "memomatic_inbox.py must be materialized into the handoff archive"
    expected = subprocess.run(
        [
            sys.executable,
            str(BUILT_HANDOFF),
            "path",
            "--workspace",
            str(workspace),
            "--session",
            "ses_mirror",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    handoff = "Handoff: verify inbox mirroring before ending the session."
    subprocess.run(
        [
            sys.executable,
            str(BUILT_HANDOFF),
            "write",
            "--workspace",
            str(workspace),
            "--session",
            "ses_mirror",
            "--expected-path",
            expected,
        ],
        input=handoff,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "XDG_STATE_HOME": str(inbox_env.parents[1])},
    )
    drops = list(inbox_env.glob("handoff-*.md"))
    assert len(drops) == 1
    body = drops[0].read_text(encoding="utf-8")
    assert "<!-- source: handoff -->" in body
    assert "verify inbox mirroring" in body
    key = re.search(r"<!-- key: (handoff-[0-9a-f]{12}-[0-9a-f]{12}) -->", body)
    assert key is not None
    other_expected = subprocess.run(
        [
            sys.executable,
            str(BUILT_HANDOFF),
            "path",
            "--workspace",
            str(workspace),
            "--session",
            "ses_other",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert other_expected != expected
    subprocess.run(
        [
            sys.executable,
            str(BUILT_HANDOFF),
            "write",
            "--workspace",
            str(workspace),
            "--session",
            "ses_other",
            "--expected-path",
            other_expected,
        ],
        input=handoff,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "XDG_STATE_HOME": str(inbox_env.parents[1])},
    )
    drops = list(inbox_env.glob("handoff-*.md"))
    assert len(drops) == 2
    keys = {
        match.group(1)
        for drop in drops
        for match in [
            re.search(
                r"<!-- key: (handoff-[0-9a-f]{12}-[0-9a-f]{12}) -->",
                drop.read_text(encoding="utf-8"),
            )
        ]
        if match is not None
    }
    assert len(keys) == 2
    assert key.group(1) in keys
