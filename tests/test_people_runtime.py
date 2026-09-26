from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEAM_WORKFLOW = ROOT / "shared/references/team_runtime/team_workflow.py"
PEOPLE_JOURNAL = ROOT / "shared/references/people_runtime/people_journal.py"
EVIDENCE_STORE = ROOT / "shared/references/team_runtime/evidence_store.py"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run_script(script: Path, args: list[str], env: dict[str, str]) -> tuple[int, dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"stdout": result.stdout, "stderr": result.stderr}
    return result.returncode, payload


@pytest.fixture
def xdg(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }


def minimal_people_profile(name: str = "demo") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile": name,
        "manager": {"name": "Manager"},
        "reports": [
            {
                "name": "Gleb Example",
                "handle": "gleb",
                "role": "stream lead",
                "level": "senior",
                "strengths": ["argocd"],
                "growth_areas": ["delegation"],
                "motivators": ["ownership"],
                "caution": ["no public peer comparisons"],
                "notes": ["wants scope growth"],
                "one_on_one": {"frequency": "biweekly", "minutes": 30},
            }
        ],
        "stakeholders": [{"name": "Orkhan Example", "role": "director"}],
        "extensions": {},
    }


def write_private(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)
    return path


def test_people_profile_roundtrip(tmp_path: Path, xdg: dict[str, str]) -> None:
    source = write_private(tmp_path / "people.json", minimal_people_profile())
    code, inspect = run_script(
        TEAM_WORKFLOW, ["profile-inspect", "--input", str(source), "--kind", "people"], xdg
    )
    assert code == 0 and inspect["status"] == "ok"
    code, prepared = run_script(
        TEAM_WORKFLOW,
        [
            "profile-prepare",
            "--name",
            "demo",
            "--input",
            str(source),
            "--kind",
            "people",
            "--set-default",
        ],
        xdg,
    )
    assert code == 0 and prepared["status"] == "prepared"
    code, saved = run_script(TEAM_WORKFLOW, prepared["apply_command"].split(), xdg)
    assert code == 0 and saved["status"] == "applied"
    profile_path = Path(xdg["XDG_CONFIG_HOME"]) / "agent-skills/team/demo/people.json"
    assert profile_path.exists()
    assert profile_path.stat().st_mode & 0o077 == 0
    code, check = run_script(TEAM_WORKFLOW, ["action-check", "--kind", "people"], xdg)
    assert code == 0 and check["status"] == "ok"
    assert check["context_path"] == str(profile_path)
    assert check["reports"] == 1


def test_people_profile_rejects_unknown_fields(tmp_path: Path, xdg: dict[str, str]) -> None:
    payload = minimal_people_profile()
    payload["unknown_section"] = []
    source = write_private(tmp_path / "bad.json", payload)
    code, inspect = run_script(
        TEAM_WORKFLOW, ["profile-inspect", "--input", str(source), "--kind", "people"], xdg
    )
    assert code == 2 and inspect["status"] == "invalid"


def test_team_and_people_kinds_share_one_directory(tmp_path: Path, xdg: dict[str, str]) -> None:
    people = write_private(tmp_path / "people.json", minimal_people_profile("shared"))
    example = json.loads(
        (ROOT / "shared/references/team_runtime/team-context.example.json").read_text(
            encoding="utf-8"
        )
    )
    example["profile"] = "shared"
    team = write_private(tmp_path / "context.json", example)
    for kind, source in (("people", people), ("team", team)):
        code, prepared = run_script(
            TEAM_WORKFLOW,
            ["profile-prepare", "--name", "shared", "--input", str(source), "--kind", kind],
            xdg,
        )
        assert prepared["status"] == "prepared"
        code, saved = run_script(TEAM_WORKFLOW, prepared["apply_command"].split(), xdg)
        assert saved["status"] == "applied"
    root = Path(xdg["XDG_CONFIG_HOME"]) / "agent-skills/team/shared"
    assert (root / "context.json").exists() and (root / "people.json").exists()
    code, listing = run_script(TEAM_WORKFLOW, ["profile-list"], xdg)
    assert code == 0
    assert listing["profiles"] == [
        {"name": "shared", "kinds": ["people", "team"], "location": "current"}
    ]


def test_legacy_team_profile_resolves_and_migrates(tmp_path: Path, xdg: dict[str, str]) -> None:
    example = json.loads(
        (ROOT / "shared/references/team_runtime/team-context.example.json").read_text(
            encoding="utf-8"
        )
    )
    example["profile"] = "legacy-demo"
    legacy_root = Path(xdg["XDG_CONFIG_HOME"]) / "opencode/team-contexts"
    legacy = write_private(legacy_root / "legacy-demo.json", example)
    legacy_root.joinpath("settings.json").write_text(
        json.dumps({"schema_version": 1, "default_profile": "legacy-demo"})
    )
    legacy_root.joinpath("settings.json").chmod(0o600)
    code, check = run_script(TEAM_WORKFLOW, ["action-check"], xdg)
    assert code == 0 and check["context_location"] == "legacy"
    code, migrate = run_script(
        TEAM_WORKFLOW, ["profile-migrate", "--name", "legacy-demo", "--set-default"], xdg
    )
    assert migrate["status"] == "prepared"
    code, saved = run_script(TEAM_WORKFLOW, migrate["apply_command"].split(), xdg)
    assert saved["status"] == "applied"
    code, check = run_script(TEAM_WORKFLOW, ["action-check"], xdg)
    assert check["context_location"] == "current"
    assert check["context_path"].endswith("agent-skills/team/legacy-demo/context.json")
    assert legacy.exists(), "legacy file must stay until the user removes it"


def test_journal_append_open_resolve(tmp_path: Path, xdg: dict[str, str]) -> None:
    code, agreement = run_script(
        PEOPLE_JOURNAL,
        [
            "journal-append",
            "--profile",
            "demo",
            "--type",
            "agreement",
            "--person",
            "Gleb Example",
            "--text",
            "Send the promotion ladder by Friday",
            "--due",
            "2026-10-02",
        ],
        xdg,
    )
    assert code == 0 and agreement["status"] == "ok"
    code, opened = run_script(PEOPLE_JOURNAL, ["journal-open", "--profile", "demo"], xdg)
    assert code == 0 and len(opened["open"]) == 1
    entry_id = opened["open"][0]["id"]
    code, resolved = run_script(
        PEOPLE_JOURNAL,
        [
            "journal-append",
            "--profile",
            "demo",
            "--type",
            "agreement",
            "--person",
            "Gleb Example",
            "--text",
            "Ladder sent",
            "--resolves",
            entry_id,
        ],
        xdg,
    )
    assert resolved["status"] == "ok"
    code, opened = run_script(PEOPLE_JOURNAL, ["journal-open", "--profile", "demo"], xdg)
    assert opened["open"] == []
    code, original = run_script(
        PEOPLE_JOURNAL, ["journal-show", "--profile", "demo", "--id", entry_id], xdg
    )
    assert original["entry"]["status"] == "open", "resolutions never rewrite history"
    journal_entry = Path(xdg["XDG_STATE_HOME"]) / "agent-skills/team/demo/journal"
    assert journal_entry.exists()
    assert journal_entry.stat().st_mode & 0o077 == 0


def test_journal_rejects_bad_input(xdg: dict[str, str]) -> None:
    code, payload = run_script(
        PEOPLE_JOURNAL,
        ["journal-append", "--profile", "demo", "--type", "mood", "--text", "nope"],
        xdg,
    )
    assert code == 2 and payload["code"] == "invalid_input"
    code, payload = run_script(
        PEOPLE_JOURNAL,
        ["journal-append", "--profile", "demo", "--type", "note", "--text", "x" * 4001],
        xdg,
    )
    assert code == 2
    code, payload = run_script(
        PEOPLE_JOURNAL,
        [
            "journal-append",
            "--profile",
            "demo",
            "--type",
            "note",
            "--text",
            "ok",
            "--resolves",
            "deadbeef",
        ],
        xdg,
    )
    assert code == 2


def test_evidence_store_legacy_fallback_and_migration(
    tmp_path: Path, xdg: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in xdg.items():
        monkeypatch.setenv(key, value)
    store = load_module("evidence_store_test", EVIDENCE_STORE)
    legacy_root = Path(xdg["XDG_STATE_HOME"]) / "agent-skills/team-evidence/demo"
    legacy_root.mkdir(parents=True, mode=0o700)
    current_root = Path(xdg["XDG_STATE_HOME"]) / "agent-skills/team/demo/evidence"
    assert not current_root.exists()
    assert store.resolve_store("demo") == legacy_root
    result = store.migrate_store("demo")
    assert result["migrated_to"].endswith("agent-skills/team/demo/evidence")
    assert store.resolve_store("demo") == current_root
    assert not legacy_root.exists()
    with pytest.raises(store.EvidenceError):
        store.migrate_store("demo")


def test_built_people_runtime_matches_shared_sources() -> None:
    built = ROOT / ".build/skills"
    checks = {
        "scripts/team_workflow.py": ROOT / "shared/references/team_runtime/team_workflow.py",
        "scripts/people_journal.py": ROOT / "shared/references/people_runtime/people_journal.py",
        "references/people-context.schema.json": ROOT
        / "shared/references/people_runtime/people-context.schema.json",
        "references/people-workflow.md": ROOT
        / "shared/references/people_runtime/people-workflow.md",
    }
    people_only = ["team-people", "team-1on1", "team-feedback", "team-agreements"]
    both = ["team-onboarding", "team-incident", "team-performance", "team-report", "team-health"]
    for skill in people_only + both:
        for relative, source in checks.items():
            target = built / skill / relative
            assert target.is_file(), target
            assert target.read_bytes() == source.read_bytes(), target
    for skill in both:
        for relative in (
            "references/team-profile-workflow.md",
            "references/team-context.schema.json",
            "references/team-context.example.json",
        ):
            assert (built / skill / relative).is_file(), (skill, relative)
    for skill in ("team-performance", "team-report", "team-health"):
        assert (built / skill / "scripts/evidence_store.py").is_file(), skill
        assert (built / skill / "scripts/gitlab_period_metrics.py").is_file(), skill
