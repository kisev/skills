from __future__ import annotations

import copy
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from shared.references.work_item_runtime.contract import WorkflowError
from shared.references.work_item_runtime.publication import CHECKS, render, run, validate

ROOT = Path(__file__).resolve().parents[1]


def draft() -> dict[str, Any]:
    return {
        "version": 1,
        "locale": "ru",
        "batch_agreement": "",
        "items": [
            {
                "key": "contract",
                "title": "Согласовать `API` и $values",
                "description": "Результат: единый API.\n\n```yaml\nname: '$HOME'\n```\n`$(touch injected)`\n",
                "target": {
                    "kind": "project",
                    "id": 42,
                    "url": "https://gitlab.example.org/team/chart",
                },
                "type": "issue",
                "metadata": {"labels": ["type::feature"], "assignee_ids": [7], "milestone_id": 9},
                "checks": {
                    name: {"status": "verified", "detail": f"Observed {name} evidence"}
                    for name in CHECKS
                },
                "existing_iid": None,
            }
        ],
        "links": [],
    }


def batch() -> dict[str, Any]:
    plan = draft()
    second = copy.deepcopy(plan["items"][0])
    second["key"] = "consumer"
    second["target"]["id"] = 43
    second["target"]["url"] = "https://gitlab.example.org/team/consumer"
    plan["items"].append(second)
    plan["batch_agreement"] = "User requested separate tasks for both projects."
    plan["links"] = [
        {
            "source": "consumer",
            "target": "contract",
            "rationale": "Contract first",
            "verified": True,
        }
    ]
    return plan


def commands(files: dict[str, bytes]) -> list[str]:
    return [
        line
        for line in files["task-publication.md"].decode().splitlines()
        if line.startswith("glab api ")
    ]


def test_creation_command_preserves_literal_markdown_and_pins_target(tmp_path: Path) -> None:
    root = tmp_path / "plan with 'quotes' and spaces"
    root.mkdir()
    plan = draft()
    files, complete = render(validate(plan), root)
    for name, content in files.items():
        (root / name).write_bytes(content)
    assert complete
    (command,) = commands(files)
    args = shlex.split(command)
    assert args[:7] == [
        "glab",
        "api",
        "--hostname",
        "gitlab.example.org",
        "--method",
        "POST",
        "projects/42/issues",
    ]
    payload_path = Path(args[-1])
    payload = json.loads(payload_path.read_text())
    assert payload["description"] == plan["items"][0]["description"]
    assert payload["title"] == plan["items"][0]["title"]
    assert payload["labels"] == "type::feature"
    assert payload["assignee_ids"] == [7]
    assert "checks" not in payload
    assert files["contract.md"].decode() == payload["description"]
    # Execute only against a recording fake; shell parsing must not execute prose.
    fake = tmp_path / "glab"
    fake.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    fake.chmod(0o700)
    result = subprocess.run(
        ["sh", "-c", command],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == args[1:]
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_incomplete_evidence_suppresses_creation(name: str, tmp_path: Path) -> None:
    plan = draft()
    plan["items"][0]["checks"][name] = {"status": "blocked", "detail": "Evidence unavailable"}
    files, complete = render(validate(plan), tmp_path)
    assert not complete
    assert not commands(files)
    assert "contract.json" not in files
    assert "Evidence unavailable" in files["task-publication.md"].decode()


def test_group_url_cannot_be_used_as_project_issue_target(tmp_path: Path) -> None:
    plan = draft()
    plan["items"][0]["target"] = {
        "kind": "group",
        "id": 12,
        "url": "https://gitlab.example.org/groups/team/charts",
    }
    with pytest.raises(WorkflowError, match="issues require projects"):
        validate(plan)
    plan["items"][0]["target"] = None
    files, complete = render(validate(plan), tmp_path)
    assert not complete and not commands(files)
    plan["items"][0]["target"] = {
        "kind": "group",
        "id": 12,
        "url": "https://gitlab.example.org/groups/team/charts",
    }
    plan["items"][0]["type"] = "epic"
    plan["items"][0]["metadata"] = {}
    files, complete = render(validate(plan), tmp_path)
    assert complete
    assert "groups/12/epics" in commands(files)[0]


def test_batch_requires_agreement_and_defers_unknown_iids(tmp_path: Path) -> None:
    plan = batch()
    plan["batch_agreement"] = ""
    with pytest.raises(WorkflowError, match="batch agreement"):
        validate(plan)
    plan["batch_agreement"] = "Requested by user"
    files, complete = render(validate(plan), tmp_path)
    assert not complete
    assert len(commands(files)) == 2
    assert "projects/43/issues" in commands(files)[1]
    assert not any("/links" in command for command in commands(files))
    assert "реальные IID" in files["task-publication.md"].decode()


def test_resume_uses_real_iids_without_recreating_issues(tmp_path: Path) -> None:
    plan = batch()
    plan["items"][0]["existing_iid"] = 10
    plan["items"][1]["existing_iid"] = 20
    files, complete = render(validate(plan), tmp_path)
    assert complete
    (command,) = commands(files)
    assert "projects/43/issues/20/links" in command
    payload = json.loads(files["link-1.json"])
    assert payload == {
        "target_project_id": 42,
        "target_issue_iid": 10,
        "link_type": "is_blocked_by",
    }
    assert "consumer.json" not in files and "contract.json" not in files
    plan["items"][1]["target"]["url"] = "https://other.example.org/team/consumer"
    files, complete = render(validate(plan), tmp_path)
    assert not complete and not commands(files)


@pytest.mark.parametrize("key", ["task-publication", "link-1", "link-42"])
def test_item_keys_cannot_overwrite_plan_or_link_payloads(key: str) -> None:
    plan = draft()
    plan["items"][0]["key"] = key
    with pytest.raises(WorkflowError, match="reserved artifact"):
        validate(plan)


def test_invalid_dependencies_and_metadata_are_rejected() -> None:
    plan = batch()
    plan["links"].append(
        {"source": "contract", "target": "consumer", "rationale": "Cycle", "verified": True}
    )
    with pytest.raises(WorkflowError, match="cycle"):
        validate(plan)
    plan = draft()
    plan["items"][0]["metadata"]["assignee_ids"] = ["guessed-user"]
    with pytest.raises(WorkflowError, match="assignees"):
        validate(plan)
    plan = draft()
    plan["items"][0]["target"]["url"] = "https://gitlab.example.org/team/chart/-/issues/2"
    with pytest.raises(WorkflowError, match="namespace URL"):
        validate(plan)


def test_atomic_default_bundle_is_repeatable_and_preserves_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    assert run(["--input", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    output = Path(report["output"])
    assert output.name == "task-publication.md"
    assert output.parent.parent == tmp_path / ".task-prepare"
    assert report["external_mutations"] is False
    before = output.stat().st_mtime_ns
    assert run(["--input", str(path)]) == 0
    assert output.stat().st_mtime_ns == before
    capsys.readouterr()
    output.write_text("User edits")
    assert run(["--input", str(path)]) == 2
    assert "artifact changed" in capsys.readouterr().out
    assert output.read_text() == "User edits"


@pytest.mark.parametrize("directory", ["../outside", "/tmp/task-publication-outside", "link/out"])
def test_unsafe_output_paths_do_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str
) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    (tmp_path / "link").symlink_to(tmp_path / "missing", target_is_directory=True)
    assert run(["--input", str(path), "--output-dir", directory]) == 2
    assert not (tmp_path / "missing").exists()


def test_built_script_is_standalone_and_neutral_mode_stays_chat_first(tmp_path: Path) -> None:
    scripts = ROOT / ".build/skills/task-prepare/scripts"
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(scripts / "prepare_publication.py"),
            "--input",
            str(path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert Path(json.loads(result.stdout)["output"]).is_file()
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(scripts / "prepare_task.py"),
            "prepare",
            "--text",
            "Source: https://gitlab.example.org/team/project/-/issues/5",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"
    assert len(list((tmp_path / ".task-prepare").iterdir())) == 1
