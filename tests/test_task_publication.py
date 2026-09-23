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

from shared.references.work_item_runtime import publication
from shared.references.work_item_runtime.contract import WorkflowError
from shared.references.work_item_runtime.publication import CHECKS, render, run, validate

ROOT = Path(__file__).resolve().parents[1]


def draft() -> dict[str, Any]:
    return {
        "version": 2,
        "plan_key": "configuration-contract",
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
        if " marker-run " in line
    ]


def mutation_args(command: str) -> list[str]:
    args = shlex.split(command)
    if "#" in args:
        args = args[: args.index("#")]
    return args[args.index("--") + 1 :]


def support(files: dict[str, bytes], name: str) -> bytes:
    matches = [content for path, content in files.items() if path.endswith(f"/{name}")]
    assert len(matches) == 1
    return matches[0]


def test_creation_command_preserves_literal_markdown_and_pins_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "plan with 'quotes' and spaces"
    root.mkdir()
    plan = draft()
    files, complete = render(validate(plan), root)
    publication.write_bundle(root, files)
    assert complete
    (command,) = commands(files)
    assert "# execution-status=not_run" in files["task-publication.md"].decode()
    wrapper = shlex.split(command)
    assert wrapper[5:9] == ["marker-run", "--skill", "task-prepare", "--action"]
    args = mutation_args(command)
    assert args[:7] == [
        "glab",
        "api",
        "--hostname",
        "gitlab.example.org",
        "--method",
        "POST",
        "projects/42/issues",
    ]
    assert args.count("--silent") == 1
    payload_path = Path(args[-1])
    payload = json.loads(payload_path.read_text())
    assert payload["description"] == plan["items"][0]["description"]
    assert payload["title"] == plan["items"][0]["title"]
    assert payload["labels"] == "type::feature"
    assert payload["assignee_ids"] == [7]
    assert "checks" not in payload
    assert support(files, "contract.md").decode() == payload["description"]
    # Execute only against a recording fake; shell parsing must not execute prose.
    fake = tmp_path / "glab"
    fake.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    fake.chmod(0o700)
    result = subprocess.run(
        ["sh", "-c", command],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "XDG_STATE_HOME": os.environ["XDG_STATE_HOME"],
        },
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == args[1:]
    assert not (tmp_path / "injected").exists()
    rerendered, _ = render(validate(plan), root)
    assert "# execution-status=run_unverified" in rerendered["task-publication.md"].decode()


def test_ready_issue_requires_milestone_and_existing_issue_gets_assignment(
    tmp_path: Path,
) -> None:
    plan = draft()
    plan["items"][0]["metadata"].pop("milestone_id")
    with pytest.raises(WorkflowError, match="requires an observed milestone_id"):
        validate(plan)

    plan = draft()
    plan["items"][0]["existing_iid"] = 17
    files, complete = render(validate(plan), tmp_path)
    assert complete
    (command,) = commands(files)
    assert "--method PUT" in command
    assert "projects/42/issues/17" in command
    assert json.loads(support(files, "contract-milestone.json")) == {"milestone_id": 9}


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_incomplete_evidence_suppresses_creation(name: str, tmp_path: Path) -> None:
    plan = draft()
    plan["items"][0]["checks"][name] = {"status": "blocked", "detail": "Evidence unavailable"}
    files, complete = render(validate(plan), tmp_path)
    assert not complete
    assert not commands(files)
    assert not any(path.endswith("/contract.json") for path in files)
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
    generated = commands(files)
    assert len(generated) == 3
    assert all(command.count("--silent") == 1 for command in generated)
    assert all("--method PUT" in command for command in generated[:2])
    assert "projects/42/issues/10" in generated[0]
    assert "projects/43/issues/20" in generated[1]
    assert "projects/43/issues/20/links" in generated[2]
    payload = json.loads(support(files, "link-1.json"))
    assert payload == {
        "target_project_id": 42,
        "target_issue_iid": 10,
        "link_type": "is_blocked_by",
    }
    assert not any(path.endswith(("/consumer.json", "/contract.json")) for path in files)
    plan["items"][1]["target"]["url"] = "https://other.example.org/team/consumer"
    files, complete = render(validate(plan), tmp_path)
    assert not complete
    assert len(commands(files)) == 2
    assert not any("/links" in command for command in commands(files))


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


def test_default_bundle_uses_stable_slot_and_replaces_changed_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    assert run(["--input", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    output = Path(report["output"])
    assert output == publication.default_root("configuration-contract") / "task-publication.md"
    assert report["external_mutations"] is False
    before = output.stat().st_mtime_ns
    assert run(["--input", str(path)]) == 0
    assert output.stat().st_mtime_ns == before
    capsys.readouterr()
    changed = draft()
    changed["items"][0]["description"] = "Changed publication body"
    path.write_text(json.dumps(changed))
    assert run(["--input", str(path)]) == 0
    assert Path(json.loads(capsys.readouterr().out)["output"]) == output
    assert "Changed publication body" in output.read_text()
    internal = output.parent / ".task-publication"
    assert len([path for path in internal.iterdir() if path.is_dir()]) == 2


def test_stale_command_keeps_its_content_after_stable_plan_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = tmp_path / "draft.json"
    plan_a = draft()
    path.write_text(json.dumps(plan_a))
    assert run(["--input", str(path)]) == 0
    output = Path(json.loads(capsys.readouterr().out)["output"])
    command_a = next(line for line in output.read_text().splitlines() if " marker-run " in line)
    payload_a_path = Path(mutation_args(command_a)[-1])
    payload_a = json.loads(payload_a_path.read_text())

    plan_b = draft()
    plan_b["items"][0]["title"] = "Replacement title"
    plan_b["items"][0]["description"] = "Replacement body"
    path.write_text(json.dumps(plan_b))
    assert run(["--input", str(path)]) == 0
    capsys.readouterr()
    command_b = next(line for line in output.read_text().splitlines() if " marker-run " in line)
    payload_b_path = Path(mutation_args(command_b)[-1])

    assert payload_a_path != payload_b_path
    assert payload_a_path.is_file()
    assert json.loads(payload_a_path.read_text()) == payload_a
    assert payload_a["description"] == plan_a["items"][0]["description"]
    assert json.loads(payload_b_path.read_text())["description"] == "Replacement body"
    fake = tmp_path / "glab"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        "path = pathlib.Path(sys.argv[sys.argv.index('--input') + 1])\n"
        "print(json.dumps(json.loads(path.read_text())))\n"
    )
    fake.chmod(0o700)
    result = subprocess.run(
        ["sh", "-c", command_a],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == payload_a


def test_plan_replacement_failure_keeps_stable_plan_and_new_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / ".task-prepare" / "configuration-contract"
    old_files, _ = render(validate(draft()), root)
    publication.write_bundle(root, old_files)
    old_plan = (root / "task-publication.md").read_bytes()
    changed = draft()
    changed["items"][0]["description"] = "Replacement"
    new_files, _ = render(validate(changed), root)
    replace = os.replace

    def fail_plan_replace(source: Path, destination: Path) -> None:
        if destination == root / "task-publication.md":
            raise OSError("simulated swap failure")
        replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_plan_replace)
    with pytest.raises(OSError, match="simulated swap failure"):
        publication.write_bundle(root, new_files)
    assert (root / "task-publication.md").read_bytes() == old_plan
    new_payload = Path(mutation_args(commands(new_files)[0])[-1])
    assert json.loads(new_payload.read_text())["description"] == "Replacement"


def test_held_slot_lock_prevents_replacement(tmp_path: Path) -> None:
    root = tmp_path / ".task-prepare" / "configuration-contract"
    old_files, _ = render(validate(draft()), root)
    publication.write_bundle(root, old_files)
    lock = root.with_name(".configuration-contract.task-publication.lock")
    lock.mkdir()
    changed = draft()
    changed["items"][0]["description"] = "Replacement"
    new_files, _ = render(validate(changed), root)
    with pytest.raises(WorkflowError, match="holds this slot lock"):
        publication.write_bundle(root, new_files)
    assert "Replacement" not in (root / "task-publication.md").read_text()


@pytest.mark.parametrize("plan_key", ["../outside", "Uppercase", "two_words", "-leading", "a" * 65])
def test_unsafe_plan_keys_are_rejected(plan_key: str) -> None:
    plan = draft()
    plan["plan_key"] = plan_key
    with pytest.raises(WorkflowError, match="safe lowercase"):
        validate(plan)


def test_version_one_publication_draft_is_rejected() -> None:
    plan = draft()
    plan["version"] = 1
    with pytest.raises(WorkflowError, match="unsupported publication version"):
        validate(plan)


def test_default_slot_rejects_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    root = publication.default_root("configuration-contract")
    root.parent.mkdir(parents=True)
    root.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert run(["--input", str(path)]) == 2
    error = capsys.readouterr().out
    assert "unsafe" in error or "symlink" in error
    assert not (tmp_path / "elsewhere").exists()


def test_internal_content_directory_rejects_symlinks(tmp_path: Path) -> None:
    root = tmp_path / ".task-prepare" / "configuration-contract"
    root.mkdir(parents=True)
    (root / ".task-publication").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    files, _ = render(validate(draft()), root)
    with pytest.raises(WorkflowError, match="content path"):
        publication.write_bundle(root, files)
    assert not (tmp_path / "elsewhere").exists()


def test_explicit_output_directory_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft()))
    assert run(["--input", str(path), "--output-dir", "custom/publication"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert Path(report["output"]) == tmp_path / "custom/publication/task-publication.md"


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
    capabilities = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(scripts / "prepare_publication.py"),
            "--capabilities",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    built_draft = draft()
    if json.loads(capabilities.stdout).get("publication_version") != 2:
        built_draft["version"] = 1
        del built_draft["plan_key"]
    path.write_text(json.dumps(built_draft))
    environment = {**os.environ, "XDG_STATE_HOME": str(tmp_path / "state")}
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
        env=environment,
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
    assert len(list((tmp_path / "state/agent-skills/task-prepare").iterdir())) == 1
